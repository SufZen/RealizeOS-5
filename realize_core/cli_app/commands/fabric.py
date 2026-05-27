"""
``realize-os fabric`` — FABRIC knowledge system CLI commands.

Commands:
    realize-os fabric lint [--venture KEY]    Validate entities against schemas
    realize-os fabric reindex [--venture KEY] Rebuild the Synapse index
    realize-os fabric stats [--venture KEY]   Show index statistics
    realize-os fabric search QUERY            Search entities
    realize-os fabric toc [--venture KEY]     Show Table of Contents
    realize-os fabric dream [--venture KEY]   Run Dreaming maintenance cycle
"""

from __future__ import annotations

from pathlib import Path

import typer

fabric_app = typer.Typer(no_args_is_help=True)


@fabric_app.command()
def lint(
    venture: str = typer.Option("", "--venture", "-v", help="Venture key to validate"),
    directory: str = typer.Option(".", "--directory", "-d", help="Project root"),
) -> None:
    """Validate all FABRIC entities against their schemas."""
    from realize_core.config import load_config
    from realize_core.fabric.crud import scan_venture
    from realize_core.fabric.validator import SchemaRegistry, validate_entity

    config = load_config()
    kb_path = Path(config.get("kb_path", "."))

    if venture:
        ventures = [venture]
    else:
        systems_dir = kb_path / "systems"
        if systems_dir.exists():
            ventures = [d.name for d in systems_dir.iterdir() if d.is_dir()]
        else:
            typer.echo("No ventures found. Run: realize-os venture create --key my-venture")
            raise typer.Exit(1)

    registry = SchemaRegistry()
    total_entities = 0
    total_warnings = 0

    for v in ventures:
        venture_dir = kb_path / "systems" / v
        if not venture_dir.exists():
            typer.echo(f"  SKIP Venture '{v}' not found on disk")
            continue

        entities = scan_venture(venture_dir, venture=v)
        v_warnings = 0

        for entity in entities:
            result = validate_entity(
                entity.frontmatter,
                entity_type=entity.type,
                entity_id=entity.id,
                registry=registry,
            )
            if result.warnings:
                for w in result.warnings:
                    typer.echo(f"  WARN {w}")
                v_warnings += len(result.warnings)

        total_entities += len(entities)
        total_warnings += v_warnings
        status = "OK" if v_warnings == 0 else f"{v_warnings} warning(s)"
        typer.echo(f"  {status}  {v}: {len(entities)} entities")

    typer.echo(f"\nTotal: {total_entities} entities, {total_warnings} warnings")


@fabric_app.command()
def reindex(
    venture: str = typer.Option("", "--venture", "-v", help="Venture key to reindex"),
    directory: str = typer.Option(".", "--directory", "-d", help="Project root"),
) -> None:
    """Rebuild the Synapse knowledge index from FABRIC files."""
    from realize_core.config import load_config
    from realize_core.fabric.crud import scan_venture
    from realize_core.fabric.synapse import Synapse

    config = load_config()
    kb_path = Path(config.get("kb_path", "."))

    db_path = kb_path / ".synapse" / "synapse.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    synapse = Synapse(db_path=db_path)

    if venture:
        ventures = [venture]
    else:
        systems_dir = kb_path / "systems"
        if systems_dir.exists():
            ventures = [d.name for d in systems_dir.iterdir() if d.is_dir()]
        else:
            typer.echo("No ventures found.")
            raise typer.Exit(1)

    total = 0
    for v in ventures:
        venture_dir = kb_path / "systems" / v
        if not venture_dir.exists():
            continue

        entities = scan_venture(venture_dir, venture=v)
        synapse.index_venture(v, entities)
        total += len(entities)
        typer.echo(f"  OK  {v}: {len(entities)} entities indexed")

    typer.echo(f"\nTotal: {total} entities indexed to {db_path}")


@fabric_app.command()
def stats(
    venture: str = typer.Option("", "--venture", "-v", help="Venture key"),
    directory: str = typer.Option(".", "--directory", "-d", help="Project root"),
) -> None:
    """Show Synapse index statistics."""
    from realize_core.config import load_config
    from realize_core.fabric.synapse import Synapse

    config = load_config()
    kb_path = Path(config.get("kb_path", "."))

    db_path = kb_path / ".synapse" / "synapse.db"
    if not db_path.exists():
        typer.echo("No Synapse index found. Run: realize-os fabric reindex")
        raise typer.Exit(1)

    synapse = Synapse(db_path=db_path)
    s = synapse.stats(venture=venture or None)

    typer.echo("Synapse Index Statistics")
    typer.echo(f"{'=' * 40}")
    for key, value in s.items():
        typer.echo(f"  {key}: {value}")


@fabric_app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    venture: str = typer.Option("", "--venture", "-v", help="Scope to venture"),
    n: int = typer.Option(10, "--n", help="Max results"),
    directory: str = typer.Option(".", "--directory", "-d", help="Project root"),
) -> None:
    """Search FABRIC entities using full-text search."""
    from realize_core.config import load_config
    from realize_core.fabric.synapse import Synapse

    config = load_config()
    kb_path = Path(config.get("kb_path", "."))

    db_path = kb_path / ".synapse" / "synapse.db"
    if not db_path.exists():
        typer.echo("No Synapse index found. Run: realize-os fabric reindex")
        raise typer.Exit(1)

    synapse = Synapse(db_path=db_path)
    results = synapse.search(query=query, scope=venture or None, n=n)

    if not results:
        typer.echo(f"No results for '{query}'")
        return

    typer.echo(f"Results for '{query}' ({len(results)}):\n")
    for r in results:
        typer.echo(f"  [{r.get('type', '?')}] {r.get('title', 'Untitled')}")
        typer.echo(f"    ID: {r.get('id', '')}  Venture: {r.get('venture', '')}")
        typer.echo()


@fabric_app.command()
def toc(
    venture: str = typer.Option("", "--venture", "-v", help="Venture key"),
    directory: str = typer.Option(".", "--directory", "-d", help="Project root"),
) -> None:
    """Show the FABRIC Table of Contents (L1 index)."""
    from realize_core.config import load_config
    from realize_core.fabric.synapse import Synapse

    config = load_config()
    kb_path = Path(config.get("kb_path", "."))

    db_path = kb_path / ".synapse" / "synapse.db"
    if not db_path.exists():
        typer.echo("No Synapse index found. Run: realize-os fabric reindex")
        raise typer.Exit(1)

    synapse = Synapse(db_path=db_path)
    entries = synapse.toc(venture=venture or None)

    if not entries:
        typer.echo("TOC is empty. Run: realize-os fabric reindex")
        return

    typer.echo(f"FABRIC Table of Contents ({len(entries)} entities):\n")
    for e in entries:
        tags = ", ".join(e.get("tags", [])[:3])
        typer.echo(f"  [{e.get('type', '?'):12s}] {e.get('title', 'Untitled')}")
        if tags:
            typer.echo(f"                 tags: {tags}")


@fabric_app.command()
def dream(
    venture: str = typer.Option("", "--venture", "-v", help="Venture key"),
    directory: str = typer.Option(".", "--directory", "-d", help="Project root"),
) -> None:
    """Run a Dreaming maintenance cycle (Curator)."""
    from realize_core.config import load_config
    from realize_core.dreaming.curator import CuratorCycle
    from realize_core.dreaming.inbox import DreamInbox
    from realize_core.dreaming.policy import TrustPolicy
    from realize_core.fabric.synapse import Synapse

    config = load_config()
    kb_path = Path(config.get("kb_path", "."))

    db_path = kb_path / ".synapse" / "synapse.db"
    if not db_path.exists():
        typer.echo("No Synapse index found. Run: realize-os fabric reindex")
        raise typer.Exit(1)

    synapse = Synapse(db_path=db_path)
    policy = TrustPolicy.load(kb_path / "shared" / "trust-policy.yaml")
    curator = CuratorCycle(synapse=synapse, policy=policy)
    inbox = DreamInbox(
        inbox_path=kb_path / ".synapse" / "dream-inbox.jsonl",
        policy=policy,
    )

    proposals = curator.run(venture=venture)

    if not proposals:
        typer.echo("No maintenance proposals generated. Knowledge graph looks healthy!")
        return

    pids = inbox.submit_batch(proposals)

    auto_approved = sum(1 for pid in pids if inbox.get(pid).status.value == "approved")
    pending = sum(1 for pid in pids if inbox.get(pid).status.value == "pending")
    denied = sum(1 for pid in pids if inbox.get(pid).status.value == "rejected")

    typer.echo(f"Curator cycle complete: {len(proposals)} proposals")
    typer.echo(f"  Auto-approved: {auto_approved}")
    typer.echo(f"  Pending review: {pending}")
    typer.echo(f"  Denied: {denied}")

    if pending > 0:
        typer.echo("\nReview pending proposals in the Dream Inbox:")
        for pid in pids:
            p = inbox.get(pid)
            if p and p.status.value == "pending":
                typer.echo(f"  [{p.action}] {p.title}")
