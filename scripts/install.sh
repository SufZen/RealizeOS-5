#!/usr/bin/env bash
# =============================================================================
# RealizeOS — One-Command Installer
# =============================================================================
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/SufZen/RealizeOS-5/main/scripts/install.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/SufZen/RealizeOS-5/main/scripts/install.sh | bash -s -- --local
#
# Flags:
#   --local      Install Python-native (no Docker), runs from source
#   --dir DIR    Installation directory (default: ./realizeos)
#   --port PORT  API port (default: 8080)
#   --version V  Docker image version tag (default: latest)
# =============================================================================

set -euo pipefail

# --- Configuration ---
REPO="SufZen/RealizeOS-5"
BRANCH="main"
RAW_BASE="https://raw.githubusercontent.com/${REPO}/${BRANCH}"
DEFAULT_DIR="./realizeos"
DEFAULT_PORT="8080"
DEFAULT_VERSION="latest"
DOCKER_IMAGE="ghcr.io/sufzen/realizeos"

# --- Colors (only if terminal supports them) ---
if [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    DIM='\033[2m'
    NC='\033[0m'
else
    RED='' GREEN='' YELLOW='' CYAN='' BOLD='' DIM='' NC=''
fi

# --- Helper functions ---
info()  { printf "${CYAN}[INFO]${NC}  %s\n" "$1"; }
ok()    { printf "${GREEN}[OK]${NC}    %s\n" "$1"; }
warn()  { printf "${YELLOW}[WARN]${NC}  %s\n" "$1"; }
fail()  { printf "${RED}[ERROR]${NC} %s\n" "$1" >&2; exit 1; }

command_exists() { command -v "$1" >/dev/null 2>&1; }

# --- Parse arguments ---
INSTALL_DIR="$DEFAULT_DIR"
PORT="$DEFAULT_PORT"
VERSION="$DEFAULT_VERSION"
LOCAL_MODE=false

while [ $# -gt 0 ]; do
    case "$1" in
        --local)    LOCAL_MODE=true; shift ;;
        --dir)      INSTALL_DIR="$2"; shift 2 ;;
        --port)     PORT="$2"; shift 2 ;;
        --version)  VERSION="$2"; shift 2 ;;
        --help|-h)
            echo "Usage: install.sh [--local] [--dir DIR] [--port PORT] [--version TAG]"
            echo ""
            echo "  --local       Install Python-native (no Docker required)"
            echo "  --dir DIR     Installation directory (default: ./realizeos)"
            echo "  --port PORT   API port (default: 8080)"
            echo "  --version V   Docker image version (default: latest)"
            exit 0
            ;;
        *) warn "Unknown option: $1"; shift ;;
    esac
done

# --- Banner ---
echo ""
printf "${BOLD}${CYAN}🚀 RealizeOS Installer${NC}\n"
printf "${DIM}   The AI operations system for your business${NC}\n"
echo ""

# --- Detect OS ---
OS="$(uname -s)"
ARCH="$(uname -m)"
info "Detected: ${OS} (${ARCH})"

case "$OS" in
    Linux*)  OS_TYPE="linux" ;;
    Darwin*) OS_TYPE="macos" ;;
    *)       fail "Unsupported OS: ${OS}. Use the PowerShell installer on Windows." ;;
esac

# --- Check prerequisites ---
if [ "$LOCAL_MODE" = true ]; then
    # Local mode: Python required, Docker optional
    if ! command_exists python3; then
        fail "Python 3.11+ is required for local mode. Install from https://python.org"
    fi

    PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
    PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

    if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]; }; then
        fail "Python 3.11+ is required (found ${PY_VERSION}). Upgrade from https://python.org"
    fi
    ok "Python ${PY_VERSION} found"

    if ! command_exists git; then
        fail "git is required for local installation. Install from https://git-scm.com"
    fi
    ok "git found"
else
    # Docker mode: Docker required
    if ! command_exists docker; then
        fail "Docker is required. Install Docker Desktop from https://docker.com"
    fi

    if ! docker compose version >/dev/null 2>&1; then
        fail "Docker Compose v2 is required. Update Docker Desktop or install the compose plugin."
    fi
    ok "Docker Compose found"

    # Check Docker daemon is running
    if ! docker info >/dev/null 2>&1; then
        fail "Docker daemon is not running. Start Docker Desktop and try again."
    fi
    ok "Docker daemon is running"
fi

# --- Create project directory ---
info "Creating project at: ${INSTALL_DIR}"
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

if [ "$LOCAL_MODE" = true ]; then
    # ── Local (Python) installation ──────────────────────────────────────────

    info "Cloning RealizeOS from GitHub..."
    if [ -d ".git" ]; then
        warn "Git repo already exists, pulling latest..."
        git pull --rebase || warn "Git pull failed, continuing with existing code"
    else
        git clone "https://github.com/${REPO}.git" .
    fi

    info "Creating Python virtual environment..."
    python3 -m venv .venv
    # shellcheck disable=SC1091
    source .venv/bin/activate

    info "Installing Python dependencies (this may take a few minutes)..."
    pip install --upgrade pip >/dev/null 2>&1
    pip install -r requirements.txt

    # Create .env if not exists
    if [ ! -f ".env" ]; then
        cp .env.example .env
        ok "Created .env from .env.example"
    else
        warn ".env already exists, skipping"
    fi

    # Run migrations
    info "Running database migrations..."
    python -c "from realize_core.db.migrations import run_migrations; run_migrations()" 2>/dev/null || warn "Migrations skipped"

    # Build dashboard if Node.js is available
    if command_exists node && command_exists npm; then
        NODE_VERSION=$(node --version)
        ok "Node.js ${NODE_VERSION} found — building dashboard..."
        if [ -d "dashboard" ]; then
            (cd dashboard && npm install --silent 2>/dev/null && npm run build 2>/dev/null) && \
                ok "Dashboard built successfully" || \
                warn "Dashboard build failed — you can build it later with: cd dashboard && npm install && npm run build"
        fi
    else
        warn "Node.js not found — dashboard will not be pre-built"
        info "Install Node.js 20+ and run: cd dashboard && npm install && npm run build"
        info "The API will still work without the dashboard"
    fi

    echo ""
    printf "${GREEN}${BOLD}✅ RealizeOS installed successfully!${NC}\n"
    echo ""
    echo "Next steps:"
    printf "  ${DIM}1.${NC} Edit ${CYAN}.env${NC} and add your API keys\n"
    printf "  ${DIM}2.${NC} Activate venv: ${CYAN}source .venv/bin/activate${NC}\n"
    printf "  ${DIM}3.${NC} Start the server: ${CYAN}python cli.py serve --port ${PORT}${NC}\n"
    printf "  ${DIM}4.${NC} Open ${CYAN}http://localhost:${PORT}${NC}\n"
    echo ""

else
    # ── Docker installation ──────────────────────────────────────────────────

    # Download config files from GitHub
    download_file() {
        local url="$1"
        local dest="$2"
        if [ -f "$dest" ]; then
            warn "${dest} already exists, skipping"
            return
        fi
        if command_exists curl; then
            curl -fsSL "$url" -o "$dest"
        elif command_exists wget; then
            wget -q "$url" -O "$dest"
        else
            fail "curl or wget is required"
        fi
    }

    info "Downloading configuration files..."

    # Create docker-compose.yml (production version)
    if [ ! -f "docker-compose.yml" ]; then
        cat > docker-compose.yml <<COMPOSE_EOF
# RealizeOS — Docker Compose (generated by install.sh)
services:
  api:
    image: ${DOCKER_IMAGE}:${VERSION}
    container_name: realizeos-api
    ports:
      - "${PORT}:8080"
    volumes:
      - realize-data:/app/data
      - realize-shared:/app/shared
      - ./realize-os.yaml:/app/realize-os.yaml:ro
      - ./systems:/app/systems
    env_file:
      - .env
    environment:
      - DATA_DIR=/app/data
      - KB_PATH=/app
      - REALIZE_HOST=0.0.0.0
      - REALIZE_PORT=8080
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      start_period: 15s
      retries: 3

volumes:
  realize-data:
    name: realizeos-data
    driver: local
  realize-shared:
    name: realizeos-shared
    driver: local
COMPOSE_EOF
        ok "Created docker-compose.yml"
    fi

    # Download .env.example and create .env
    download_file "${RAW_BASE}/.env.example" ".env.example"
    if [ ! -f ".env" ]; then
        cp .env.example .env
        ok "Created .env from .env.example"
    fi

    # Download default config
    download_file "${RAW_BASE}/setup.yaml.example" "realize-os.yaml.example"
    if [ ! -f "realize-os.yaml" ]; then
        cat > realize-os.yaml <<CONFIG_EOF
# RealizeOS Configuration
# See docs: https://github.com/SufZen/RealizeOS-5

systems:
  my-venture:
    name: "My Venture"
    directory: systems/my-venture
    agents:
      chief:
        role: chief-of-staff
        model: gemini_flash
        skills: ["*"]

settings:
  default_model: gemini_flash
  timezone: UTC
CONFIG_EOF
        ok "Created realize-os.yaml"
    fi

    # Create directories
    mkdir -p systems/my-venture/F-foundations

    # Create venture identity stub
    if [ ! -f "systems/my-venture/F-foundations/venture-identity.md" ]; then
        cat > "systems/my-venture/F-foundations/venture-identity.md" <<IDENTITY_EOF
# Venture Identity

## Name
My Venture

## Mission
[Describe your venture's mission]

## Voice & Tone
[Describe the communication style]
IDENTITY_EOF
    fi

    # Create .gitignore
    if [ ! -f ".gitignore" ]; then
        cat > .gitignore <<GITIGNORE_EOF
.env
setup.yaml
data/
*.db
__pycache__/
.credentials/
GITIGNORE_EOF
    fi

    # Prompt for API key if interactive
    if [ -t 0 ]; then
        echo ""
        printf "${BOLD}API Key Setup${NC}\n"
        printf "${DIM}At least one LLM provider API key is required.${NC}\n"
        echo ""
        printf "Enter your Anthropic API key (or press Enter to skip): "
        read -r ANTHROPIC_KEY
        if [ -n "$ANTHROPIC_KEY" ]; then
            sed -i.bak "s/^ANTHROPIC_API_KEY=$/ANTHROPIC_API_KEY=${ANTHROPIC_KEY}/" .env
            rm -f .env.bak
            ok "Anthropic API key saved to .env"
        fi

        printf "Enter your Google AI API key (or press Enter to skip): "
        read -r GOOGLE_KEY
        if [ -n "$GOOGLE_KEY" ]; then
            sed -i.bak "s/^GOOGLE_AI_API_KEY=$/GOOGLE_AI_API_KEY=${GOOGLE_KEY}/" .env
            rm -f .env.bak
            ok "Google AI API key saved to .env"
        fi
    fi

    # Pull and start
    info "Pulling Docker image: ${DOCKER_IMAGE}:${VERSION}..."
    if docker compose pull 2>/dev/null; then
        ok "Image pulled successfully"
    else
        warn "Pre-built image not available. Building from source instead..."
        info "Cloning RealizeOS repository..."

        if ! command_exists git; then
            fail "git is required to build from source. Install from https://git-scm.com"
        fi

        git clone --depth 1 "https://github.com/${REPO}.git" _build_src 2>/dev/null || \
            fail "Could not clone repository. Check your internet connection."

        # Copy build files into the project directory
        cp _build_src/Dockerfile .
        cp _build_src/requirements.txt .
        cp _build_src/.env.example .env.example.repo 2>/dev/null || true
        cp -r _build_src/realize_core _build_src/realize_api _build_src/realize_lite .
        cp -r _build_src/templates _build_src/cli.py .
        cp -r _build_src/dashboard . 2>/dev/null || true

        rm -rf _build_src

        # Update compose to use local build context
        if [ -f "docker-compose.yml" ]; then
            # Replace the image line with a build context
            sed -i.bak '/^[[:space:]]*image:/d' docker-compose.yml
            sed -i.bak 's|services:|services:\n|' docker-compose.yml
            # Insert build directive after container_name
            sed -i.bak '/container_name: realizeos-api/a\    build: .' docker-compose.yml
            rm -f docker-compose.yml.bak
        fi

        info "Building Docker image locally (this may take a few minutes)..."
        docker compose build || fail "Docker build failed. Check the output above."
        ok "Local build completed"
    fi

    info "Starting RealizeOS..."
    docker compose up -d

    echo ""
    printf "${GREEN}${BOLD}✅ RealizeOS is running!${NC}\n"
    echo ""
    printf "  ${DIM}Dashboard:${NC}  ${CYAN}http://localhost:${PORT}${NC}\n"
    printf "  ${DIM}API Docs:${NC}   ${CYAN}http://localhost:${PORT}/docs${NC}\n"
    printf "  ${DIM}Health:${NC}     ${CYAN}http://localhost:${PORT}/health${NC}\n"
    echo ""
    echo "Next steps:"
    printf "  ${DIM}1.${NC} Edit ${CYAN}.env${NC} and add your API keys (if not done above)\n"
    printf "  ${DIM}2.${NC} Edit ${CYAN}realize-os.yaml${NC} to configure your ventures\n"
    printf "  ${DIM}3.${NC} View logs: ${CYAN}docker compose logs -f${NC}\n"
    printf "  ${DIM}4.${NC} Stop:      ${CYAN}docker compose down${NC}\n"
    echo ""
fi
