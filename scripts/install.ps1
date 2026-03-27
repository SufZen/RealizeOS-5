# =============================================================================
# RealizeOS — One-Command PowerShell Installer
# =============================================================================
# Usage:
#   irm https://raw.githubusercontent.com/SufZen/RealizeOS-5/main/scripts/install.ps1 | iex
#
# Or with parameters:
#   & ([scriptblock]::Create((irm https://raw.githubusercontent.com/SufZen/RealizeOS-5/main/scripts/install.ps1))) -Dir .\my-project -Port 9090
# =============================================================================

[CmdletBinding()]
param(
    [string]$Dir = ".\realizeos",
    [string]$Port = "8080",
    [string]$Version = "latest",
    [switch]$Local
)

$ErrorActionPreference = "Stop"

# --- Configuration ---
$Repo = "SufZen/RealizeOS-5"
$Branch = "main"
$RawBase = "https://raw.githubusercontent.com/$Repo/$Branch"
$DockerImage = "ghcr.io/sufzen/realizeos"

# --- Helper functions ---
function Write-Status { param([string]$Message) Write-Host "[INFO]  $Message" -ForegroundColor Cyan }
function Write-Ok { param([string]$Message) Write-Host "[OK]    $Message" -ForegroundColor Green }
function Write-Warn { param([string]$Message) Write-Host "[WARN]  $Message" -ForegroundColor Yellow }
function Write-Fail { param([string]$Message) Write-Host "[ERROR] $Message" -ForegroundColor Red; exit 1 }

function Test-Command { param([string]$Name) return [bool](Get-Command $Name -ErrorAction SilentlyContinue) }

# --- Banner ---
Write-Host ""
Write-Host "🚀 RealizeOS Installer" -ForegroundColor Cyan -NoNewline
Write-Host " (PowerShell)" -ForegroundColor DarkGray
Write-Host "   The AI operations system for your business" -ForegroundColor DarkGray
Write-Host ""

# --- Check prerequisites ---
if ($Local) {
    # Local mode: Python required
    if (-not (Test-Command "python")) {
        Write-Fail "Python 3.11+ is required for local mode. Install from https://python.org"
    }

    $pyVer = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
    if (-not $pyVer) {
        Write-Fail "Could not determine Python version."
    }

    $parts = $pyVer.Split(".")
    if ([int]$parts[0] -lt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -lt 11)) {
        Write-Fail "Python 3.11+ is required (found $pyVer). Upgrade from https://python.org"
    }
    Write-Ok "Python $pyVer found"

    if (-not (Test-Command "git")) {
        Write-Fail "git is required for local installation. Install from https://git-scm.com"
    }
    Write-Ok "git found"
}
else {
    # Docker mode
    if (-not (Test-Command "docker")) {
        Write-Fail "Docker is required. Install Docker Desktop from https://docker.com"
    }

    try {
        docker compose version 2>$null | Out-Null
    }
    catch {
        Write-Fail "Docker Compose v2 is required. Update Docker Desktop."
    }
    Write-Ok "Docker Compose found"

    # Check Docker daemon
    try {
        docker info 2>$null | Out-Null
    }
    catch {
        Write-Fail "Docker daemon is not running. Start Docker Desktop and try again."
    }
    Write-Ok "Docker daemon is running"
}

# --- Create project directory ---
Write-Status "Creating project at: $Dir"
New-Item -ItemType Directory -Path $Dir -Force | Out-Null
Set-Location $Dir

if ($Local) {
    # ── Local (Python) installation ────────────────────────────────────────

    Write-Status "Cloning RealizeOS from GitHub..."
    if (Test-Path ".git") {
        Write-Warn "Git repo already exists, pulling latest..."
        git pull --rebase 2>$null
    }
    else {
        git clone "https://github.com/$Repo.git" .
    }

    Write-Status "Creating Python virtual environment..."
    python -m venv .venv
    & .\.venv\Scripts\Activate.ps1

    Write-Status "Installing Python dependencies (this may take a few minutes)..."
    pip install --upgrade pip 2>$null | Out-Null
    pip install -r requirements.txt

    # Create .env if not exists
    if (-not (Test-Path ".env")) {
        Copy-Item ".env.example" ".env"
        Write-Ok "Created .env from .env.example"
    }
    else {
        Write-Warn ".env already exists, skipping"
    }

    # Run migrations
    Write-Status "Running database migrations..."
    try {
        python -c "from realize_core.db.migrations import run_migrations; run_migrations()" 2>$null
    }
    catch {
        Write-Warn "Migrations skipped"
    }

    Write-Host ""
    Write-Host "✅ RealizeOS installed successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor White
    Write-Host "  1. Edit " -NoNewline; Write-Host ".env" -ForegroundColor Cyan -NoNewline; Write-Host " and add your API keys"
    Write-Host "  2. Activate venv: " -NoNewline; Write-Host ".\.venv\Scripts\Activate.ps1" -ForegroundColor Cyan
    Write-Host "  3. Start the server: " -NoNewline; Write-Host "python cli.py serve --port $Port" -ForegroundColor Cyan
    Write-Host "  4. Open " -NoNewline; Write-Host "http://localhost:$Port" -ForegroundColor Cyan
    Write-Host ""
}
else {
    # ── Docker installation ────────────────────────────────────────────────

    function Download-FileIfMissing {
        param([string]$Url, [string]$Dest)
        if (Test-Path $Dest) {
            Write-Warn "$Dest already exists, skipping"
            return
        }
        try {
            Invoke-WebRequest -Uri $Url -OutFile $Dest -UseBasicParsing
        }
        catch {
            Write-Fail "Failed to download $Url"
        }
    }

    Write-Status "Downloading configuration files..."

    # Create docker-compose.yml
    if (-not (Test-Path "docker-compose.yml")) {
        @"
# RealizeOS — Docker Compose (generated by install.ps1)
services:
  api:
    image: ${DockerImage}:${Version}
    container_name: realizeos-api
    ports:
      - "${Port}:8080"
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
"@ | Out-File -FilePath "docker-compose.yml" -Encoding UTF8
        Write-Ok "Created docker-compose.yml"
    }

    # Download .env.example and create .env
    Download-FileIfMissing "$RawBase/.env.example" ".env.example"
    if (-not (Test-Path ".env")) {
        Copy-Item ".env.example" ".env"
        Write-Ok "Created .env from .env.example"
    }

    # Create default config
    if (-not (Test-Path "realize-os.yaml")) {
        @"
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
"@ | Out-File -FilePath "realize-os.yaml" -Encoding UTF8
        Write-Ok "Created realize-os.yaml"
    }

    # Create directories
    New-Item -ItemType Directory -Path "systems\my-venture\F-foundations" -Force | Out-Null

    # Create venture identity stub
    $identityPath = "systems\my-venture\F-foundations\venture-identity.md"
    if (-not (Test-Path $identityPath)) {
        @"
# Venture Identity

## Name
My Venture

## Mission
[Describe your venture's mission]

## Voice & Tone
[Describe the communication style]
"@ | Out-File -FilePath $identityPath -Encoding UTF8
    }

    # Create .gitignore
    if (-not (Test-Path ".gitignore")) {
        @"
.env
setup.yaml
data/
*.db
__pycache__/
.credentials/
"@ | Out-File -FilePath ".gitignore" -Encoding UTF8
    }

    # Prompt for API key
    Write-Host ""
    Write-Host "API Key Setup" -ForegroundColor White
    Write-Host "At least one LLM provider API key is required." -ForegroundColor DarkGray
    Write-Host ""

    $anthropicKey = Read-Host "Enter your Anthropic API key (or press Enter to skip)"
    if ($anthropicKey) {
        (Get-Content .env) -replace "^ANTHROPIC_API_KEY=$", "ANTHROPIC_API_KEY=$anthropicKey" | Set-Content .env
        Write-Ok "Anthropic API key saved to .env"
    }

    $googleKey = Read-Host "Enter your Google AI API key (or press Enter to skip)"
    if ($googleKey) {
        (Get-Content .env) -replace "^GOOGLE_AI_API_KEY=$", "GOOGLE_AI_API_KEY=$googleKey" | Set-Content .env
        Write-Ok "Google AI API key saved to .env"
    }

    # Pull and start
    Write-Status "Pulling Docker image: ${DockerImage}:${Version}..."
    docker compose pull

    Write-Status "Starting RealizeOS..."
    docker compose up -d

    Write-Host ""
    Write-Host "✅ RealizeOS is running!" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Dashboard:  " -NoNewline -ForegroundColor DarkGray; Write-Host "http://localhost:$Port" -ForegroundColor Cyan
    Write-Host "  API Docs:   " -NoNewline -ForegroundColor DarkGray; Write-Host "http://localhost:$Port/docs" -ForegroundColor Cyan
    Write-Host "  Health:     " -NoNewline -ForegroundColor DarkGray; Write-Host "http://localhost:$Port/health" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor White
    Write-Host "  1. Edit " -NoNewline; Write-Host ".env" -ForegroundColor Cyan -NoNewline; Write-Host " and add your API keys (if not done above)"
    Write-Host "  2. Edit " -NoNewline; Write-Host "realize-os.yaml" -ForegroundColor Cyan -NoNewline; Write-Host " to configure your ventures"
    Write-Host "  3. View logs: " -NoNewline; Write-Host "docker compose logs -f" -ForegroundColor Cyan
    Write-Host "  4. Stop:      " -NoNewline; Write-Host "docker compose down" -ForegroundColor Cyan
    Write-Host ""
}
