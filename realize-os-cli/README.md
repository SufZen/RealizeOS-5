# @realize-os/cli

Deploy and manage your **RealizeOS** AI operations system with Docker — from a single command.

## Quick Start

```bash
# Create a new project
npx realize-os init my-project
cd my-project

# Add your API keys
nano .env

# Start the system
npx realize-os start

# Check status
npx realize-os status
```

## Commands

| Command | Description |
|---------|-------------|
| `realize-os init [dir]` | Scaffold a new project (docker-compose, .env, config) |
| `realize-os start [dir]` | Start Docker containers |
| `realize-os stop [dir]` | Stop Docker containers |
| `realize-os status [dir]` | Check system health and container status |
| `realize-os logs [dir]` | Tail container logs |
| `realize-os upgrade [dir]` | Pull latest image and restart |
| `realize-os venture list` | List all configured ventures |
| `realize-os venture create` | Create a new venture |
| `realize-os venture export` | Export a venture |
| `realize-os venture import` | Import a venture |

## Init Options

```bash
npx realize-os init my-project \
  --port 9090 \
  --with-telegram \
  --with-gws \
  --image ghcr.io/sufzen/realizeos:v5.0.0
```

| Option | Default | Description |
|--------|---------|-------------|
| `--name` | `realize-os` | Project name |
| `--port` | `8080` | API port |
| `--image` | `ghcr.io/sufzen/realizeos:latest` | Docker image |
| `--with-telegram` | `false` | Include Telegram bot service |
| `--with-gws` | `false` | Include Google Workspace support |
| `--force` | `false` | Overwrite existing files |

## Requirements

- **Node.js** 18+ (for `npx`)
- **Docker** with Compose v2

## Development

```bash
cd realize-os-cli
npm install
npm run dev -- --help    # Run from source
npm run build            # Compile TypeScript
npm test                 # Run tests
```

## License

MIT
