#!/bin/bash
################################################################################
# NUC Deployment — isolated stack (own compose project + network), US timezone.
#
# Ships this repo to a NUC and brings it up via docker-compose.nuc.yml under a
# dedicated compose project so it cannot clash with other docker apps on the box.
#
# Usage:
#   NUC_HOST=user@192.168.1.50 ./deploy_nuc.sh
#   NUC_HOST=root@nuc.local NUC_DIR=/opt/stockexp_us ./deploy_nuc.sh
#
# Env (all optional except NUC_HOST):
#   NUC_HOST   ssh target, e.g. user@192.168.1.50         (REQUIRED)
#   NUC_DIR    remote dir            (default /opt/stockexp_us)
#   PROJECT    compose project name  (default stockexp_nuc)
#   TZ         container timezone    (default America/New_York)
################################################################################
set -euo pipefail

NUC_HOST="${NUC_HOST:-}"
NUC_DIR="${NUC_DIR:-/home/ai/stockexp_us}"
PROJECT="${PROJECT:-stockexp_nuc}"
TZ="${TZ:-America/New_York}"
COMPOSE="docker-compose.nuc.yml"

GREEN='\033[0;32m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'
say() { echo -e "${BLUE}[deploy-nuc]${NC} $*"; }
ok()  { echo -e "${GREEN}✓${NC} $*"; }
die() { echo -e "${RED}✗ $*${NC}"; exit 1; }

[ -n "$NUC_HOST" ] || die "Set NUC_HOST, e.g. NUC_HOST=user@192.168.1.50 ./deploy_nuc.sh"
[ -f "$COMPOSE" ] || die "$COMPOSE not found — run from repo root."

say "Target: $NUC_HOST  dir=$NUC_DIR  project=$PROJECT  tz=$TZ"

# 1) SSH reachable?
say "[1/5] SSH check…"
ssh -o ConnectTimeout=8 -o BatchMode=yes "$NUC_HOST" 'echo ok' >/dev/null 2>&1 \
  || die "SSH to $NUC_HOST failed (key auth?). Try: ssh-copy-id $NUC_HOST"
ok "SSH ok"

# 2) Docker present on NUC? Detect whether we need sudo (user not in docker group).
say "[2/5] Docker check on NUC…"
ssh "$NUC_HOST" 'command -v docker >/dev/null && docker compose version >/dev/null 2>&1' \
  || die "docker + compose plugin required on the NUC."
if ssh "$NUC_HOST" 'docker ps >/dev/null 2>&1'; then
  SUDO=""
elif ssh "$NUC_HOST" 'sudo -n docker ps >/dev/null 2>&1'; then
  SUDO="sudo"
else
  die "docker needs sudo but passwordless sudo unavailable for $NUC_HOST."
fi
ok "docker present (sudo='${SUDO:-none}')"

# 3) Sync repo (rsync; excludes heavy/local-only paths).
say "[3/5] Syncing repo → $NUC_HOST:$NUC_DIR …"
ssh "$NUC_HOST" "mkdir -p '$NUC_DIR'"
rsync -az --delete \
  --exclude '.git' --exclude '__pycache__' --exclude '*.pyc' \
  --exclude 'venv' --exclude '.venv' --exclude 'node_modules' \
  --exclude 'logs/*' --exclude '.env' \
  ./ "$NUC_HOST:$NUC_DIR/"
ok "synced"

# 3b) Writable logs/exports for the in-container 'trader' user (uid 100 != ai uid 1000).
ssh "$NUC_HOST" "cd '$NUC_DIR' && mkdir -p logs exports && chmod 777 logs exports"
ok "logs/exports writable"

# 4) Preserve remote .env if present; warn if missing.
say "[4/5] Checking remote .env …"
if ssh "$NUC_HOST" "[ -f '$NUC_DIR/.env' ]"; then
  ok ".env present on NUC"
else
  echo -e "${RED}⚠ no $NUC_DIR/.env on NUC${NC} — set secrets (SECRET_KEY, IBKR_*, TG_*, POSTGRES_PASSWORD) before going live."
fi

# 5) Build + up under the isolated project.
# NOTE: docker-compose.nuc.yml sets build.network=host on each image so buildkit's
# RUN steps use host networking — works around this NUC's buildkit DNS failure
# (systemd-resolved 127.0.0.53 loopback doesn't route inside the buildkit sandbox)
# without restarting dockerd / bouncing other stacks on the box.
say "[5/5] Build + up (project=$PROJECT)…"
ssh "$NUC_HOST" "cd '$NUC_DIR' && TZ='$TZ' $SUDO docker compose -p '$PROJECT' -f '$COMPOSE' up -d --build"

echo
ssh "$NUC_HOST" "cd '$NUC_DIR' && $SUDO docker compose -p '$PROJECT' -f '$COMPOSE' ps" || true
echo
ok "Deployed. Web (localhost on NUC): http://127.0.0.1:\${NUC_WEB_PORT:-55001}"
say "Tunnel from your machine:  ssh -L 55001:127.0.0.1:55001 $NUC_HOST   then open http://localhost:55001"
say "Logs:    ssh $NUC_HOST 'docker compose -p $PROJECT -f $NUC_DIR/$COMPOSE logs -f trading_system'"
say "Down:    ssh $NUC_HOST 'docker compose -p $PROJECT -f $NUC_DIR/$COMPOSE down'"
