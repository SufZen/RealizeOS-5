"""``realize-os config`` — manage CLI configuration and profiles."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

from realize_core.cli_app.profiles import ProfileManager

config_app = typer.Typer(no_args_is_help=True)
profile_app = typer.Typer(no_args_is_help=True, help="Manage named profiles for multi-instance support.")
config_app.add_typer(profile_app, name="profile")


@profile_app.command("list")
def profile_list() -> None:
    """List all configured profiles."""
    pm = ProfileManager()
    profiles = pm.list_profiles()
    if not profiles:
        typer.echo("No profiles configured. Run: realize-os config profile add default")
        raise typer.Exit(code=0)

    raw = pm._load_raw()
    default_name = raw.get("default_profile", "default")

    for p in profiles:
        marker = " *" if p.name == default_name else ""
        typer.echo(f"  {p.name}{marker}  ->  {p.endpoint}")


@profile_app.command("add")
def profile_add(
    name: Annotated[str, typer.Argument(help="Profile name.")],
    endpoint: Annotated[str, typer.Option("--endpoint", help="API endpoint URL.")] = "http://localhost:8080",
    api_key_env: Annotated[
        str, typer.Option("--api-key-env", help="Env var name holding the API key.")
    ] = "REALIZE_API_KEY",
    default_system: Annotated[str, typer.Option("--default-system", help="Default system key.")] = "",
) -> None:
    """Add or update a named profile."""
    pm = ProfileManager()
    p = pm.add_profile(name, endpoint=endpoint, api_key_env=api_key_env, default_system=default_system)
    typer.echo(f"Profile '{p.name}' saved -> {p.endpoint}")


@profile_app.command("set-default")
def profile_set_default(
    name: Annotated[str, typer.Argument(help="Profile name to set as default.")],
) -> None:
    """Set a profile as the default."""
    pm = ProfileManager()
    try:
        pm.set_default(name)
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Default profile set to '{name}'.")


@profile_app.command("show")
def profile_show(
    name: Annotated[str | None, typer.Argument(help="Profile name (default: active profile).")] = None,
) -> None:
    """Show details for a profile."""
    pm = ProfileManager()
    p = pm.show_profile(name)
    typer.echo(f"Profile:        {p.name}")
    typer.echo(f"Endpoint:       {p.endpoint}")
    typer.echo(f"API Key Env:    {p.api_key_env}")
    typer.echo(f"Default System: {p.default_system or '(none)'}")


# ------------------------------------------------------------------ #
#  config show / set / unset — read/write realize-os.yaml              #
# ------------------------------------------------------------------ #


def _find_config_path() -> Path:
    """Locate the ``realize-os.yaml`` config file, searching CWD upward."""
    for name in ("realize-os.yaml", "realize-os.yml"):
        p = Path.cwd() / name
        if p.exists():
            return p
    return Path.cwd() / "realize-os.yaml"


@config_app.command("show")
def config_show(
    key: Annotated[str | None, typer.Argument(help="Dotted key to show (e.g. mcp.enabled). Omit to show all.")] = None,
) -> None:
    """Show a config value from realize-os.yaml (or the full file)."""
    cfg_path = _find_config_path()
    if not cfg_path.exists():
        typer.echo(f"Config file not found: {cfg_path}", err=True)
        raise typer.Exit(code=1)

    import yaml

    with cfg_path.open() as fh:
        data = yaml.safe_load(fh) or {}

    if key is None:
        yaml.dump(data, sys.stdout, default_flow_style=False, sort_keys=False)
        return

    value = _get_nested(data, key)
    if value is _MISSING:
        typer.echo(f"Key '{key}' not found.", err=True)
        raise typer.Exit(code=1)

    if isinstance(value, dict):
        yaml.dump(value, sys.stdout, default_flow_style=False, sort_keys=False)
    else:
        typer.echo(str(value))


@config_app.command("set")
def config_set(
    key: Annotated[str, typer.Argument(help="Dotted key to set (e.g. mcp.enabled).")],
    value: Annotated[str, typer.Argument(help="Value to set (auto-casts booleans and numbers).")],
) -> None:
    """Set a config value in realize-os.yaml."""
    cfg_path = _find_config_path()

    import yaml

    data: dict = {}
    if cfg_path.exists():
        with cfg_path.open() as fh:
            data = yaml.safe_load(fh) or {}

    parsed = _auto_cast(value)
    _set_nested(data, key, parsed)

    with cfg_path.open("w") as fh:
        yaml.dump(data, fh, default_flow_style=False, sort_keys=False)

    typer.echo(f"{key} = {parsed}")


@config_app.command("unset")
def config_unset(
    key: Annotated[str, typer.Argument(help="Dotted key to remove (e.g. mcp.allow_admin).")],
) -> None:
    """Remove a config key from realize-os.yaml."""
    cfg_path = _find_config_path()
    if not cfg_path.exists():
        typer.echo(f"Config file not found: {cfg_path}", err=True)
        raise typer.Exit(code=1)

    import yaml

    with cfg_path.open() as fh:
        data = yaml.safe_load(fh) or {}

    if not _del_nested(data, key):
        typer.echo(f"Key '{key}' not found.", err=True)
        raise typer.Exit(code=1)

    with cfg_path.open("w") as fh:
        yaml.dump(data, fh, default_flow_style=False, sort_keys=False)

    typer.echo(f"Removed: {key}")


# ------------------------------------------------------------------ #
#  Internal helpers for nested dict navigation                         #
# ------------------------------------------------------------------ #

_MISSING = object()


def _get_nested(data: dict, dotted_key: str) -> object:
    """Retrieve a value from a nested dict using a dotted key."""
    keys = dotted_key.split(".")
    cur: object = data
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return _MISSING
        cur = cur[k]
    return cur


def _set_nested(data: dict, dotted_key: str, value: object) -> None:
    """Set a value in a nested dict, creating intermediates as needed."""
    keys = dotted_key.split(".")
    cur = data
    for k in keys[:-1]:
        if k not in cur or not isinstance(cur[k], dict):
            cur[k] = {}
        cur = cur[k]
    cur[keys[-1]] = value


def _del_nested(data: dict, dotted_key: str) -> bool:
    """Delete a key from a nested dict. Returns True if found and deleted."""
    keys = dotted_key.split(".")
    cur = data
    for k in keys[:-1]:
        if not isinstance(cur, dict) or k not in cur:
            return False
        cur = cur[k]
    if isinstance(cur, dict) and keys[-1] in cur:
        del cur[keys[-1]]
        return True
    return False


def _auto_cast(value: str) -> object:
    """Auto-cast a string to bool, int, float, or leave as str."""
    low = value.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if low == "null" or low == "none":
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value
