#!/bin/bash
# RealizeOS Deploy Script
# Usage: ./scripts/deploy.sh [--build-dashboard] [--docker]

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== RealizeOS Deploy ==="
echo "Project: $PROJECT_DIR"

# Parse args
BUILD_DASHBOARD=false
USE_DOCKER=false
for arg in "$@"; do
    case $arg in
        --build-dashboard) BUILD_DASHBOARD=true ;;
        --docker) USE_DOCKER=true ;;
    esac
done

# 1. Pull latest code (if git repo)
if [ -d "$PROJECT_DIR/.git" ]; then
    echo "[..] Pulling latest code..."
    cd "$PROJECT_DIR"
    git pull --rebase || echo "[!!] Git pull failed, continuing with local code"
fi

# 2. Install Python dependencies
echo "[..] Installing Python dependencies..."
cd "$PROJECT_DIR"
pip install -q -r requirements.txt

# 3. Build dashboard (optional)
if [ "$BUILD_DASHBOARD" = true ]; then
    echo "[..] Building dashboard..."
    cd "$PROJECT_DIR/dashboard"
    pnpm install --frozen-lockfile
    pnpm build
    echo "[OK] Dashboard built"
fi

# 4. Run migrations
echo "[..] Running database migrations..."
cd "$PROJECT_DIR"
python -c "from realize_core.db.migrations import run_migrations; run_migrations()" 2>/dev/null || echo "[--] Migrations skipped"

# 5. Docker or direct
if [ "$USE_DOCKER" = true ]; then
    echo "[..] Building and starting Docker containers..."
    cd "$PROJECT_DIR"
    docker compose up --build -d
    echo "[OK] Docker containers started"
else
    echo "[OK] Deploy complete. Start with: python cli.py serve"
fi

echo "=== Done ==="
