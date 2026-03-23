"""
RealizeOS CLI: Entry point for the `realize` command.

Commands:
- realize init         — Scaffold a new RealizeOS project
- realize run          — Start the engine
- realize status       — Show system status
- realize workflows    — List and manage workflows
"""

import argparse
import sys
import textwrap
from pathlib import Path


def main(args: list[str] | None = None):
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="realize",
        description="RealizeOS — Your intelligent operating system",
    )
    subs = parser.add_subparsers(dest="command")

    # realize init
    init_parser = subs.add_parser("init", help="Scaffold a new RealizeOS project")
    init_parser.add_argument("path", nargs="?", default=".", help="Project directory")
    init_parser.add_argument("--tier", choices=["lite", "full"], default="full")
    init_parser.add_argument("--name", default="my-realize-project")

    # realize status
    subs.add_parser("status", help="Show system status")

    # realize workflows
    wf_parser = subs.add_parser("workflows", help="List workflows")
    wf_parser.add_argument("--dir", default="workflows/")

    parsed = parser.parse_args(args)

    if parsed.command == "init":
        return cmd_init(parsed.path, parsed.tier, parsed.name)
    elif parsed.command == "status":
        return cmd_status()
    elif parsed.command == "workflows":
        return cmd_workflows(parsed.dir)
    else:
        parser.print_help()
        return 0


def cmd_init(path: str, tier: str, name: str) -> int:
    """Scaffold a new RealizeOS project."""
    project_dir = Path(path).resolve()
    print(f"🚀 Initializing RealizeOS project: {name}")
    print(f"   Tier: {tier}")
    print(f"   Path: {project_dir}")

    # Create directory structure
    dirs = [
        "config",
        "skills",
        "workflows",
        "docs/dev-process/active",
        "docs/dev-process/plans",
        "docs/dev-process/reference",
    ]
    if tier == "full":
        dirs.extend(["channels", "tools", "media"])

    for d in dirs:
        (project_dir / d).mkdir(parents=True, exist_ok=True)

    # Create workspace.yaml
    workspace_yaml = project_dir / "config" / "workspace.yaml"
    if not workspace_yaml.exists():
        workspace_yaml.write_text(
            textwrap.dedent(f"""\
            # RealizeOS Workspace Configuration
            project:
              name: {name}
              tier: {tier}
              version: "0.1.0"

            systems: {{}}
              # Define your systems here:
              # my-business:
              #   display_name: "My Business"
              #   agent_key: default

            channels: {{}}
              # telegram:
              #   enabled: false
              #   token: ${{TELEGRAM_BOT_TOKEN}}

            security:
              default_role: guest
              # users:
              #   admin:
              #     role: owner
              #     channels:
              #       telegram: "123456789"
        """)
        )

    # Create .env.example
    dotenv_example = project_dir / ".env.example"
    if not dotenv_example.exists():
        dotenv_example.write_text(
            textwrap.dedent("""\
            # RealizeOS Environment Variables
            # Copy this to .env and fill in your values

            # LLM API Keys (at least one required)
            ANTHROPIC_API_KEY=
            GOOGLE_API_KEY=
            OPENAI_API_KEY=

            # Channels (optional)
            TELEGRAM_BOT_TOKEN=
            WHATSAPP_PHONE_NUMBER_ID=
            WHATSAPP_ACCESS_TOKEN=

            # Tools (optional)
            BRAVE_API_KEY=
        """)
        )

    # Create initial dev-process files
    _write_if_missing(
        project_dir / "docs" / "dev-process" / "active" / "current-focus.md",
        "# Current Focus\n\n> Project initialized. Begin by defining your first system.\n",
    )

    _write_if_missing(
        project_dir / "docs" / "dev-process" / "active" / "session-log.md",
        "# Session Log\n\n> Append each work session below.\n",
    )

    # Create CLAUDE.md
    _write_if_missing(
        project_dir / "CLAUDE.md",
        textwrap.dedent(f"""\
        # CLAUDE.md — {name}

        ## Project Identity
        - Name: {name}
        - Tier: {tier}
        - Framework: RealizeOS

        ## Quick Commands
        - `realize status` — Show system status
        - `realize workflows` — List workflows

        ## Media Handling
        When receiving images, use the vision-capable model to analyze them.
        When receiving audio/voice messages, transcribe them before processing.
        Always describe what you see in images when asked.
    """),
    )

    print("\n✅ Project scaffolded! Next steps:")
    print("   1. cp .env.example .env    → Add your API keys")
    print("   2. Edit config/workspace.yaml → Define your first system")
    print("   3. realize run             → Start the engine")
    return 0


def cmd_status() -> int:
    """Show system status."""
    print("📊 RealizeOS Status")
    print("=" * 40)

    # Check for workspace config
    ws = Path("config/workspace.yaml")
    print(f"  Workspace config: {'✅' if ws.exists() else '❌ not found'}")

    # Check for .env
    env = Path(".env")
    print(f"  Environment file: {'✅' if env.exists() else '⚠️ not found'}")

    # Check key deps
    for pkg, name in [("anthropic", "Claude"), ("google.generativeai", "Gemini"), ("openai", "OpenAI")]:
        try:
            __import__(pkg)
            print(f"  {name} SDK: ✅")
        except ImportError:
            print(f"  {name} SDK: ❌")

    return 0


def cmd_workflows(directory: str) -> int:
    """List available workflows."""
    from realize_core.workflows import discover_workflows

    workflows = discover_workflows(directory)
    if not workflows:
        print("No workflows found.")
        return 0

    print(f"📋 Workflows ({len(workflows)}):")
    for wf in workflows:
        print(f"  • {wf.name}: {wf.description} ({len(wf.nodes)} steps, trigger={wf.trigger})")
    return 0


def _write_if_missing(path: Path, content: str):
    if not path.exists():
        path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
