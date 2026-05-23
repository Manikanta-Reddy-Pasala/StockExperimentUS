#!/bin/bash

# Simple Docker Compose Runner Script for Trading System

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install Docker to run this application."
    exit 1
fi

# Check if Docker Compose is available
if ! docker compose version &> /dev/null; then
    print_error "Docker Compose is not available. Please install Docker Compose to run this application."
    exit 1
fi

# Create necessary directories
print_status "Creating necessary directories..."
mkdir -p logs
mkdir -p init-scripts

# Check if .env file exists
if [ ! -f .env ]; then
    print_error ".env file not found!"
    print_status "Please create a .env file with your configuration."
    print_status "You can copy the example from the repository or create one manually."
    exit 1
fi

# Function to start the application
start_app() {
    print_status "Starting Trading System with Docker Compose..."
    
    # Build and start services
    docker compose up --build -d
    
    print_success "Trading System started successfully!"
    print_status "Services running:"
    echo "  - Web Interface: http://localhost:5001"
    echo "  - Database: localhost:5432"
    echo "  - Redis: localhost:6379"
    echo ""
    print_status "To view logs: docker compose logs -f"
    print_status "To stop: docker compose down"
}

# Function to start the application in development mode
start_dev() {
    print_status "Starting Trading System in Development Mode with Auto-reloading..."

    # Build and start services with development override
    docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build -d

    print_success "Trading System started in Development Mode!"
    print_status "Services running:"
    echo "  - Web Interface: http://localhost:5001"
    echo "  - Database: localhost:5432"
    echo "  - Redis: localhost:6379"
    echo ""
    print_status "Development features enabled:"
    echo "  - Auto-reloading on Python file changes"
    echo "  - Auto-reloading on HTML template changes"
    echo "  - Debug mode enabled"
    echo ""
    print_status "To view logs: docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f"
    print_status "To stop: docker compose -f docker-compose.yml -f docker-compose.dev.yml down"
}

# Function to start databases only and run Flask locally
start_local() {
    print_status "Starting databases only (PostgreSQL + Redis) and running Flask locally..."

    # Start only databases
    docker compose -f docker-compose.db-only.yml up -d

    print_status "Waiting for databases to be ready..."
    sleep 5

    # Check if virtual environment exists
    if [ ! -d "venv" ]; then
        print_error "Virtual environment not found. Please create it first:"
        echo "  python -m venv venv"
        echo "  source venv/bin/activate"
        echo "  pip install -r requirements.txt"
        exit 1
    fi

    print_success "Databases started successfully!"
    print_status "Docker services running:"
    echo "  - Database: localhost:5432"
    echo "  - Redis: localhost:6379"
    echo ""
    print_status "Now starting Flask app locally..."
    echo ""
    print_warning "Make sure to activate your virtual environment:"
    echo "  source venv/bin/activate"
    echo "  python run.py --dev"
    echo ""
    print_status "This will give you:"
    echo "  - Immediate file reloading (templates, Python files)"
    echo "  - Direct debugging access"
    echo "  - Faster development cycle"
    echo ""
    print_status "To stop databases: docker compose -f docker-compose.db-only.yml down"
}

# Function to stop the application
stop_app() {
    print_status "Stopping Trading System..."
    # Try to stop both production and development modes
    docker compose down 2>/dev/null || true
    docker compose -f docker-compose.yml -f docker-compose.dev.yml down 2>/dev/null || true
    print_success "Trading System stopped successfully!"
}

# Function to show logs
show_logs() {
    print_status "Showing Trading System logs..."
    # Try to show logs from development mode first, then production
    if docker compose -f docker-compose.yml -f docker-compose.dev.yml ps --services --filter "status=running" | grep -q trading_system; then
        docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f
    else
        docker compose logs -f
    fi
}

# Function to show status
show_status() {
    print_status "Trading System Status:"
    # Show status for both production and development modes
    if docker compose -f docker-compose.yml -f docker-compose.dev.yml ps --services --filter "status=running" | grep -q trading_system; then
        print_status "Development Mode:"
        docker compose -f docker-compose.yml -f docker-compose.dev.yml ps
    else
        print_status "Production Mode:"
        docker compose ps
    fi
}

# Function to restart the application
restart_app() {
    print_status "Restarting Trading System..."
    docker compose restart
    print_success "Trading System restarted successfully!"
}

# Function to clean up everything
cleanup() {
    print_warning "This will remove all containers, volumes, and data. Are you sure? (y/N)"
    read -r response
    if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        print_status "Cleaning up Trading System..."
        docker compose down -v --remove-orphans
        docker system prune -f
        print_success "Cleanup completed!"
    else
        print_status "Cleanup cancelled."
    fi
}

# Main script logic
case "${1:-start}" in
    start)
        start_app
        ;;
    dev)
        start_dev
        ;;
    local)
        start_local
        ;;
    stop)
        stop_app
        ;;
    restart)
        restart_app
        ;;
    logs)
        show_logs
        ;;
    status)
        show_status
        ;;
    cleanup)
        cleanup
        ;;
    *)
        echo "Usage: $0 {start|dev|local|stop|restart|logs|status|cleanup}"
        echo ""
        echo "Commands:"
        echo "  start   - Start the Trading System in production mode (default)"
        echo "  dev     - Start the Trading System in development mode with auto-reloading"
        echo "  local   - Start databases only, run Flask locally for faster development"
        echo "  stop    - Stop the Trading System"
        echo "  restart - Restart the Trading System"
        echo "  logs    - Show application logs"
        echo "  status  - Show service status"
        echo "  cleanup - Remove all containers and data"
        exit 1
        ;;
esac
