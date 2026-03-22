#!/usr/bin/env python3
"""
RealizeOS CLI — Initialize, serve, and manage your AI operations system.

Usage:
    python cli.py init [--template NAME]       Create a new system from a template
    python cli.py init --setup setup.yaml      Create system from a setup file
    python cli.py serve [--port PORT]          Start the API server
    python cli.py bot                          Start the Telegram bot
    python cli.py status                       Show system status
    python cli.py index                        Rebuild the KB search index
    python cli.py venture create               Create a new venture
    python cli.py venture delete               Delete a venture
    python cli.py venture list                 List all ventures
"""
import argparse
import logging
import os
import shutil
import sys
from pathlib import Path

# Load .env automatically for non-Docker users
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("realize")

# .gitignore content for new projects
_GITIGNORE_CONTENT = """\
# Secrets — never commit these
.env
setup.yaml

# Data
data/
*.db

# Python
__pycache__/
*.pyc
.venv/
venv/

# OS
.DS_Store
Thumbs.db

# Credentials
.credentials/
"""


def _init_from_setup_file(setup_path: Path, target_dir: Path):
    """Initialize RealizeOS from a setup.yaml file (delegates to shared init logic)."""
    import yaml

    if not setup_path.exists():
        print(f"Error: Setup file not found: {setup_path}")
        sys.exit(1)

    with open(setup_path, encoding="utf-8") as f:
        setup = yaml.safe_load(f)

    if not setup:
        print("Error: Setup file is empty or invalid YAML.")
        sys.exit(1)

    from realize_core.init import initialize_project
    result = initialize_project(setup, target_dir)

    if result.get("errors"):
        for err in result["errors"]:
            print(f"  Error: {err}")
        sys.exit(1)

    if result["env_created"]:
        print("  Created .env with your API keys")
    if result["config_created"]:
        print(f"  Created realize-os.yaml from '{setup.get('template', 'consulting')}' template")
    if result["files_copied"]:
        print(f"  Created FABRIC structure ({result['files_copied']} files)")


def cmd_init(args):
    """Initialize a new system from a template or setup file."""
    target_dir = Path(args.directory or ".")

    # Setup file mode: reads setup.yaml and configures everything
    if args.setup:
        setup_path = Path(args.setup)
        print(f"Initializing RealizeOS from {setup_path}...")
        _init_from_setup_file(setup_path, target_dir)
        print()
        print("Initialization complete!")
        print()
        print("Next steps:")
        print("  1. Review and customize your venture identity:")
        print("     Edit systems/*/F-foundations/venture-identity.md")
        print("  2. Start the server:")
        print("     python cli.py serve")
        print("  3. Or deploy with Docker:")
        print("     docker compose up --build")
        return

    # Template mode (original flow, enhanced)
    template_name = args.template or "consulting"

    templates_dir = Path(__file__).parent / "templates"
    template_file = templates_dir / f"{template_name}.yaml"

    if not template_file.exists():
        available = [f.stem for f in templates_dir.glob("*.yaml") if not f.stem.startswith("_")]
        print(f"Template '{template_name}' not found.")
        print(f"Available: {', '.join(available)}")
        sys.exit(1)

    # Copy the Lite vault structure as a starting point
    lite_src = Path(__file__).parent / "realize_lite"
    if not lite_src.exists():
        print("Error: realize_lite directory not found.")
        sys.exit(1)

    # Create target if it doesn't exist
    target_dir.mkdir(parents=True, exist_ok=True)

    # Copy vault structure
    for item in lite_src.rglob("*"):
        if item.is_file() and ".obsidian" not in str(item):
            relative = item.relative_to(lite_src)
            dest = target_dir / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                shutil.copy2(item, dest)

    # Copy template config
    config_dest = target_dir / "realize-os.yaml"
    if not config_dest.exists():
        shutil.copy2(template_file, config_dest)

    # Copy .env.example
    env_example = Path(__file__).parent / ".env.example"
    env_dest = target_dir / ".env.example"
    if env_example.exists() and not env_dest.exists():
        shutil.copy2(env_example, env_dest)

    # Auto-create .env from .env.example (so users don't need cp/copy)
    env_file = target_dir / ".env"
    env_example_local = target_dir / ".env.example"
    if not env_file.exists() and env_example_local.exists():
        shutil.copy2(env_example_local, env_file)
        print("  ✓ Created .env from .env.example — edit it to add your API keys")

    # Create .gitignore
    gitignore_dest = target_dir / ".gitignore"
    if not gitignore_dest.exists():
        gitignore_dest.write_text(_GITIGNORE_CONTENT, encoding="utf-8")

    print(f"Initialized RealizeOS with '{template_name}' template at {target_dir.resolve()}")
    print()
    print("Next steps:")
    print(f"  1. Edit .env and add your API keys")
    print(f"  2. Edit {config_dest} to configure your system")
    print(f"  3. Fill in your venture identity and agent definitions")
    print(f"  4. Run: python cli.py serve")


def cmd_serve(args):
    """Start the API server."""
    host = args.host or os.environ.get("REALIZE_HOST", "127.0.0.1")
    port = int(args.port or os.environ.get("REALIZE_PORT", "8080"))

    try:
        import uvicorn
    except ImportError:
        print("Error: uvicorn not installed. Run: pip install uvicorn")
        sys.exit(1)

    print(f"Starting RealizeOS API on {host}:{port}")
    uvicorn.run(
        "realize_api.main:app",
        host=host,
        port=port,
        reload=args.reload,
        log_level="info",
    )


def cmd_bot(args):
    """Start the Telegram bot."""
    import asyncio

    async def run_bot():
        from realize_core.config import load_config
        config = load_config()

        channels = config.get("channels", [])
        telegram_config = None
        for ch in channels:
            if ch.get("type") == "telegram":
                telegram_config = ch
                break

        if not telegram_config:
            print("No Telegram channel configured in realize-os.yaml")
            sys.exit(1)

        token = telegram_config.get("token", "")
        if token.startswith("${"):
            env_var = token[2:-1]
            token = os.environ.get(env_var, "")

        if not token:
            print("Telegram bot token not found. Set it in .env or realize-os.yaml")
            sys.exit(1)

        from realize_core.channels.telegram import TelegramChannel
        channel = TelegramChannel(bot_token=token, config=config)
        print("Starting Telegram bot...")
        await channel.start()

    asyncio.run(run_bot())


def cmd_status(args):
    """Show system status."""
    from realize_core.config import load_config, build_systems_dict

    try:
        config = load_config()
    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)

    systems = build_systems_dict(config)

    print("RealizeOS Status")
    print("=" * 40)
    print(f"Systems: {len(systems)}")

    for key, sys_config in systems.items():
        agents = list(sys_config.get("agents", {}).keys())
        print(f"\n  {key} ({sys_config.get('name', key)})")
        print(f"    Agents: {', '.join(agents) if agents else 'none'}")
        routing = sys_config.get("routing", {})
        if routing:
            print(f"    Pipelines: {', '.join(routing.keys())}")

    # Check API keys
    print(f"\nLLM Providers:")
    if os.environ.get("ANTHROPIC_API_KEY"):
        print("  Anthropic: configured")
    else:
        print("  Anthropic: NOT configured")
    if os.environ.get("GOOGLE_AI_API_KEY"):
        print("  Google AI: configured")
    else:
        print("  Google AI: NOT configured")

    # Check tools
    print(f"\nTools:")
    print(f"  Web Search: {'configured' if os.environ.get('BRAVE_API_KEY') else 'not configured'}")
    print(f"  Browser: {'enabled' if os.environ.get('BROWSER_ENABLED') else 'disabled'}")


def cmd_index(args):
    """Rebuild the KB search index."""
    from realize_core.config import load_config
    config = load_config()
    kb_path = config.get("kb_path", ".")

    from realize_core.kb.indexer import index_kb_files
    count = index_kb_files(kb_path, force_reindex=True)
    print(f"Indexed {count} files from {kb_path}")


def cmd_venture(args):
    """Manage ventures (create, delete, list)."""
    from realize_core.scaffold import scaffold_venture, delete_venture, list_ventures

    project_root = Path(args.directory or ".")

    if args.venture_action == "create":
        if not args.key:
            print("Error: --key is required for venture create")
            sys.exit(1)
        try:
            stats = scaffold_venture(
                project_root=project_root,
                key=args.key,
                name=args.name or "",
                description=args.description or "",
            )
            print(f"Created venture '{args.key}' at systems/{args.key}/")
            print(f"  {stats['dirs_created']} directories, {stats['files_created']} files")
            print(f"\nThe venture has been added to realize-os.yaml.")
            print(f"Next: customize systems/{args.key}/F-foundations/venture-identity.md")
        except FileExistsError as e:
            print(f"Error: {e}")
            sys.exit(1)
        except FileNotFoundError as e:
            print(f"Error: {e}")
            sys.exit(1)

    elif args.venture_action == "delete":
        if not args.key:
            print("Error: --key is required for venture delete")
            sys.exit(1)
        confirm = args.confirm or ""
        if confirm != args.key:
            print(f"To delete venture '{args.key}', pass --confirm {args.key}")
            sys.exit(1)
        try:
            delete_venture(project_root, args.key, confirm_name=confirm)
            print(f"Deleted venture '{args.key}' and removed from realize-os.yaml.")
        except (FileNotFoundError, ValueError) as e:
            print(f"Error: {e}")
            sys.exit(1)

    elif args.venture_action == "list":
        ventures = list_ventures(project_root)
        if not ventures:
            print("No ventures configured. Run: python cli.py venture create --key my-venture")
            return
        print(f"Ventures ({len(ventures)}):")
        for v in ventures:
            status = "OK" if v["exists"] else "MISSING"
            print(f"  {v['key']} — {v['name']} ({v['directory']}) [{status}]")

    else:
        print("Usage: python cli.py venture {create|delete|list}")
        sys.exit(1)


def cmd_setup(args):
    """Run the interactive setup wizard."""
    from realize_core.setup_wizard import run_wizard
    target_dir = Path(args.directory or ".")
    run_wizard(target_dir, skip_dashboard=args.skip_dashboard)


def cmd_doctor(args):
    """Diagnose installation issues."""
    from realize_core.setup_wizard import run_doctor
    project_root = Path(args.directory or ".")
    run_doctor(project_root)


def main():
    parser = argparse.ArgumentParser(
        description="RealizeOS — AI Operations System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init
    init_parser = subparsers.add_parser("init", help="Initialize a new system")
    init_parser.add_argument("--template", "-t", default="consulting", help="Template name")
    init_parser.add_argument("--setup", "-s", default=None,
                             help="Path to setup.yaml for one-command init")
    init_parser.add_argument("--directory", "-d", default=".", help="Target directory")

    # serve
    serve_parser = subparsers.add_parser("serve", help="Start the API server")
    serve_parser.add_argument("--host", default=None, help="Host (default: 127.0.0.1)")
    serve_parser.add_argument("--port", "-p", default=None, help="Port (default: 8080)")
    serve_parser.add_argument("--reload", action="store_true", help="Enable auto-reload")

    # bot
    subparsers.add_parser("bot", help="Start the Telegram bot")

    # status
    subparsers.add_parser("status", help="Show system status")

    # index
    subparsers.add_parser("index", help="Rebuild KB search index")

    # venture
    venture_parser = subparsers.add_parser("venture", help="Manage ventures")
    venture_parser.add_argument("venture_action", choices=["create", "delete", "list"],
                                help="Action: create, delete, or list")
    venture_parser.add_argument("--key", "-k", help="Venture key (directory name)")
    venture_parser.add_argument("--name", "-n", help="Display name")
    venture_parser.add_argument("--description", help="Venture description")
    venture_parser.add_argument("--directory", "-d", default=".", help="Project root directory")
    venture_parser.add_argument("--confirm", help="Confirm deletion (must match --key)")

    # setup (interactive wizard)
    setup_parser = subparsers.add_parser("setup", help="Interactive setup wizard")
    setup_parser.add_argument("--directory", "-d", default=".", help="Target directory")
    setup_parser.add_argument("--skip-dashboard", action="store_true", help="Skip dashboard setup")

    # doctor (diagnose installation)
    doctor_parser = subparsers.add_parser("doctor", help="Diagnose installation issues")
    doctor_parser.add_argument("--directory", "-d", default=".", help="Project root directory")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    commands = {
        "init": cmd_init,
        "serve": cmd_serve,
        "bot": cmd_bot,
        "status": cmd_status,
        "index": cmd_index,
        "venture": cmd_venture,
        "setup": cmd_setup,
        "doctor": cmd_doctor,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
