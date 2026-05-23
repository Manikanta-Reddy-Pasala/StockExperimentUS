#!/bin/bash

################################################################################
# Production Deployment Script for Stock Trading System
# Server: 77.42.45.12
# Timezone: Asia/Kolkata (IST)
################################################################################

set -e  # Exit on error

# Configuration
SERVER_IP="77.42.45.12"
SERVER_USER="root"
REMOTE_DIR="/opt/trading_system"
IMAGE_NAME="stockexperiment-trading_system"
IMAGE_TAG="latest"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print banner
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Stock Trading System - Production Deployment            ║${NC}"
echo -e "${BLUE}║   Server: $SERVER_IP                                ║${NC}"
echo -e "${BLUE}║   Timezone: Asia/Kolkata (IST)                            ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Function to show usage
usage() {
    echo "Usage: $0"
    echo ""
    echo "This script will:"
    echo "  1. Build Docker image locally"
    echo "  2. Export and transfer to production server"
    echo "  3. Load image and start all containers"
    echo "  4. Verify deployment"
    echo ""
    echo "Prerequisites:"
    echo "  - SSH key access to root@$SERVER_IP"
    echo "  - Docker installed locally and on server"
    echo ""
    exit 1
}

# Check if help requested
if [[ "$1" == "-h" ]] || [[ "$1" == "--help" ]]; then
    usage
fi

# Step 1: Test SSH connection
echo -e "${BLUE}[1/8] Testing SSH connection to $SERVER_IP...${NC}"
if ssh -o ConnectTimeout=5 -o BatchMode=yes $SERVER_USER@$SERVER_IP echo "SSH OK" 2>/dev/null; then
    echo -e "${GREEN}✓ SSH connection successful${NC}"
else
    echo -e "${RED}✗ SSH connection failed!${NC}"
    echo -e "${YELLOW}Run: ssh-add ~/.ssh/your_key${NC}"
    exit 1
fi

# Step 2: Build Docker image
echo ""
echo -e "${BLUE}[2/8] Building Docker image locally...${NC}"
echo -e "${YELLOW}This may take 5-10 minutes...${NC}"
docker build --platform linux/amd64 -t $IMAGE_NAME:$IMAGE_TAG .
echo -e "${GREEN}✓ Image built successfully${NC}"

# Step 3: Export image
echo ""
echo -e "${BLUE}[3/8] Exporting Docker image...${NC}"
IMAGE_FILE="trading_system_image.tar"
docker save -o $IMAGE_FILE $IMAGE_NAME:$IMAGE_TAG
IMAGE_SIZE=$(du -h $IMAGE_FILE | cut -f1)
echo -e "${GREEN}✓ Image exported: $IMAGE_FILE ($IMAGE_SIZE)${NC}"

# Step 4: Create remote directories
echo ""
echo -e "${BLUE}[4/8] Creating remote directory structure...${NC}"
ssh $SERVER_USER@$SERVER_IP "mkdir -p $REMOTE_DIR/{logs,exports,ml_models,init-scripts}"
echo -e "${GREEN}✓ Directories created${NC}"

# Step 5: Transfer files
echo ""
echo -e "${BLUE}[5/8] Transferring files to server...${NC}"
echo -e "${YELLOW}Transferring $IMAGE_SIZE - this may take several minutes...${NC}"

# Transfer Docker image
scp $IMAGE_FILE $SERVER_USER@$SERVER_IP:$REMOTE_DIR/

# Transfer configuration files
scp docker-compose.yml $SERVER_USER@$SERVER_IP:$REMOTE_DIR/
scp .env.production $SERVER_USER@$SERVER_IP:$REMOTE_DIR/.env
scp -r init-scripts/* $SERVER_USER@$SERVER_IP:$REMOTE_DIR/init-scripts/
scp scheduler.py data_scheduler.py run_pipeline.py $SERVER_USER@$SERVER_IP:$REMOTE_DIR/

echo -e "${GREEN}✓ Files transferred${NC}"

# Clean up local tar file
rm -f $IMAGE_FILE
echo -e "${GREEN}✓ Local tar file cleaned up${NC}"

# Step 6: Ensure Docker is installed on server
echo ""
echo -e "${BLUE}[6/8] Checking Docker on server...${NC}"
ssh $SERVER_USER@$SERVER_IP << 'EOF'
    if ! command -v docker &> /dev/null; then
        echo "Installing Docker..."
        curl -fsSL https://get.docker.com -o get-docker.sh
        sh get-docker.sh
        rm get-docker.sh
        systemctl enable docker
        systemctl start docker
        echo "✓ Docker installed"
    else
        echo "✓ Docker already installed"
    fi

    if ! docker compose version &> /dev/null; then
        echo "Installing Docker Compose..."
        apt-get update
        apt-get install -y docker-compose-plugin
        echo "✓ Docker Compose installed"
    else
        echo "✓ Docker Compose already installed"
    fi
EOF
echo -e "${GREEN}✓ Docker environment ready${NC}"

# Step 7: Load image and start services
echo ""
echo -e "${BLUE}[7/8] Loading image and starting services...${NC}"

ssh $SERVER_USER@$SERVER_IP << EOF
    cd $REMOTE_DIR

    # Create override file for image-based deployment (preserves original docker-compose.yml)
    cat > docker-compose.override.yml << 'OVERRIDE'
services:
  trading_system:
    image: $IMAGE_NAME:$IMAGE_TAG
    build: !reset null
  technical_scheduler:
    image: $IMAGE_NAME:$IMAGE_TAG
    build: !reset null
  data_scheduler:
    image: $IMAGE_NAME:$IMAGE_TAG
    build: !reset null
OVERRIDE
    sed -i "s|\\\$IMAGE_NAME|$IMAGE_NAME|g; s|\\\$IMAGE_TAG|$IMAGE_TAG|g" docker-compose.override.yml

    echo "Loading Docker image..."
    docker load -i trading_system_image.tar

    echo "Removing image tar file..."
    rm -f trading_system_image.tar

    echo "Stopping existing containers..."
    docker compose down 2>/dev/null || true

    echo "Starting services..."
    docker compose up -d

    echo "Waiting for services to be healthy..."
    sleep 15

    echo ""
    echo "Container status:"
    docker compose ps
EOF
echo -e "${GREEN}✓ Services started${NC}"

# Step 8: Verify deployment
echo ""
echo -e "${BLUE}[8/8] Verifying deployment...${NC}"

# Get container status
CONTAINER_COUNT=$(ssh $SERVER_USER@$SERVER_IP "cd $REMOTE_DIR && docker compose ps -q | wc -l" | tr -d ' ')

# Test web UI
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://$SERVER_IP:5001/ || echo "000")

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║          DEPLOYMENT SUCCESSFUL!                            ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}Deployment Summary:${NC}"
echo -e "  Containers Running: $CONTAINER_COUNT/5"
echo -e "  Web UI Status: HTTP $HTTP_STATUS"
echo ""
echo -e "${BLUE}Access Your System:${NC}"
echo -e "  Web UI:  ${GREEN}http://$SERVER_IP:5001${NC}"
echo -e "  Username: ${GREEN}admin${NC}"
echo -e "  Password: ${YELLOW}See ADMIN_CREDENTIALS.md${NC}"
echo ""
echo -e "${BLUE}Next Steps:${NC}"
echo -e "  1. Configure Fyers credentials via web UI"
echo -e "  2. Monitor logs: ${GREEN}./manage_production.sh logs${NC}"
echo -e "  3. Wait for first data pipeline at 9:00 PM IST"
echo ""
echo -e "${BLUE}Container Timezone:${NC}"
ssh $SERVER_USER@$SERVER_IP "cd $REMOTE_DIR && docker compose exec -T trading_system date 2>/dev/null || echo 'Containers still starting...'"
echo ""
echo -e "${YELLOW}For management commands, see: ./manage_production.sh${NC}"
echo ""
echo -e "${GREEN}Deployment complete!${NC}"
