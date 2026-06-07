# Writable Config and Safe Venture Deletion Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Allow RealizeOS API/admin tools to safely create and delete ventures in the next version without ghost ventures when `realize-os.yaml` is currently mounted read-only.

**Architecture:** Introduce an explicit writable workspace config path, make config mutations atomic and preflighted, and return structured API errors when mutation is disabled instead of partially deleting FABRIC directories. Update Docker Compose so users can opt into writable config management by mounting a writable config file/path while preserving read-only production hardening as an explicit mode.

**Tech Stack:** Python, FastAPI, PyYAML, pytest, Docker Compose.

---

## Current failure mode

Observed on the VPS:

- `DELETE /api/ventures/mioliving_partnership` reaches `realize_core.scaffold.delete_venture()`.
- `delete_venture()` calls `_remove_venture_from_config(root, key)`.
- `_remove_venture_from_config()` tries to write `/app/realize-os.yaml`.
- Docker Compose mounts `./realize-os.yaml:/app/realize-os.yaml:ro`, so the write fails with `Errno 30 Read-only file system`.
- If FABRIC folders are already absent, the venture remains in the registry as a ghost entry.

Relevant files:

- `realize_api/routes/ventures.py`
- `realize_core/scaffold.py`
- `realize_core/config.py`
- `docker-compose.yml`
- `docker-compose.prod.yml`
- `tests/test_scaffold.py`
- `tests/test_api_routes_v2.py` or a new focused route test file

## Recommended product decision

Do **not** silently mutate a read-only deployment. RealizeOS should support two modes:

1. **Managed config mode** — default for dashboard/API venture CRUD.
   - `realize-os.yaml` is mounted writable.
   - API create/delete venture can persist config changes.

2. **Locked config mode** — explicit hardened mode.
   - Config is read-only.
   - Venture create/delete endpoints return `409 Conflict` / `423 Locked`-style structured errors before touching files.
   - Error tells the operator how to enable managed config mode.

This preserves security while making the operational path clear and safe.

---

## Task 1: Add config path + writeability helpers

**Objective:** Centralize config path resolution and mutation preflight so route code stops guessing `kb_path / "realize-os.yaml"`.

**Files:**

- Modify: `realize_core/config.py`
- Test: `tests/test_config_mutability.py` (new)

**Step 1: Write failing tests**

Create `tests/test_config_mutability.py`:

```python
from pathlib import Path

from realize_core.config import get_config_path, is_config_writable


def test_get_config_path_defaults_to_realize_config_env(monkeypatch, tmp_path):
    cfg = tmp_path / "realize-os.yaml"
    monkeypatch.setenv("REALIZE_CONFIG", str(cfg))

    assert get_config_path() == cfg


def test_get_config_path_falls_back_to_workspace_root(monkeypatch, tmp_path):
    monkeypatch.delenv("REALIZE_CONFIG", raising=False)

    assert get_config_path(tmp_path) == tmp_path / "realize-os.yaml"


def test_is_config_writable_false_for_missing_parent(tmp_path):
    cfg = tmp_path / "missing" / "realize-os.yaml"

    assert is_config_writable(cfg) is False


def test_is_config_writable_true_for_existing_writable_file(tmp_path):
    cfg = tmp_path / "realize-os.yaml"
    cfg.write_text("systems: []\n", encoding="utf-8")

    assert is_config_writable(cfg) is True
```

**Step 2: Run test to verify failure**

Run:

```bash
pytest tests/test_config_mutability.py -v
```

Expected: FAIL because `get_config_path` and `is_config_writable` do not exist.

**Step 3: Implement helpers**

Add to `realize_core/config.py`:

```python
def get_config_path(workspace_root: str | Path | None = None) -> Path:
    """Resolve the active realize-os.yaml path.

    REALIZE_CONFIG wins. Relative REALIZE_CONFIG paths are resolved against
    workspace_root when provided, otherwise against the current working directory.
    """
    raw = os.getenv("REALIZE_CONFIG", "realize-os.yaml")
    path = Path(raw)
    if path.is_absolute():
        return path
    base = Path(workspace_root) if workspace_root is not None else Path.cwd()
    return (base / path).resolve()


def is_config_writable(config_path: str | Path) -> bool:
    """Return whether config_path can be written/created by this process."""
    path = Path(config_path)
    if path.exists():
        return os.access(path, os.W_OK)
    return path.parent.exists() and os.access(path.parent, os.W_OK)
```

Update `load_config()` line 61 to use `get_config_path()` when `config_path is None`.

**Step 4: Run test to verify pass**

Run:

```bash
pytest tests/test_config_mutability.py -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add realize_core/config.py tests/test_config_mutability.py
git commit -m "feat(config): add writable config path helpers"
```

---

## Task 2: Make config mutations atomic and explicit

**Objective:** Ensure add/remove venture config changes either fully persist or fail before FABRIC deletion/creation side effects proceed.

**Files:**

- Modify: `realize_core/scaffold.py`
- Test: `tests/test_scaffold.py`

**Step 1: Write failing tests**

Append to `tests/test_scaffold.py`:

```python
import os
import stat

import pytest
import yaml

from realize_core.scaffold import ConfigMutationError, delete_venture


def test_delete_venture_refuses_when_config_not_writable(tmp_path, monkeypatch):
    config = tmp_path / "realize-os.yaml"
    config.write_text(
        yaml.dump({"systems": [{"key": "ghost", "directory": "systems/ghost"}]}),
        encoding="utf-8",
    )
    venture_dir = tmp_path / "systems" / "ghost"
    venture_dir.mkdir(parents=True)

    monkeypatch.setattr("realize_core.scaffold.is_config_writable", lambda path: False)

    with pytest.raises(ConfigMutationError) as exc:
        delete_venture(tmp_path, "ghost", confirm_name="ghost")

    assert "not writable" in str(exc.value).lower()
    assert venture_dir.exists(), "files must remain when config cannot be updated"


def test_delete_venture_removes_config_and_directory_when_writable(tmp_path):
    config = tmp_path / "realize-os.yaml"
    config.write_text(
        yaml.dump({"systems": [{"key": "ghost", "directory": "systems/ghost"}]}),
        encoding="utf-8",
    )
    venture_dir = tmp_path / "systems" / "ghost"
    venture_dir.mkdir(parents=True)

    assert delete_venture(tmp_path, "ghost", confirm_name="ghost") is True

    assert not venture_dir.exists()
    updated = yaml.safe_load(config.read_text(encoding="utf-8"))
    assert updated["systems"] == []
```

**Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_scaffold.py -v
```

Expected: FAIL because `ConfigMutationError` does not exist and config preflight is not implemented.

**Step 3: Implement explicit exception + atomic writes**

In `realize_core/scaffold.py`:

- Import `tempfile` if needed.
- Import helpers from `realize_core.config`.
- Add:

```python
class ConfigMutationError(RuntimeError):
    """Raised when RealizeOS cannot safely persist realize-os.yaml changes."""
```

- Add helper:

```python
def _write_yaml_atomic(config_path: Path, config: dict):
    import os
    import tempfile
    import yaml

    if not is_config_writable(config_path):
        raise ConfigMutationError(f"Config file is not writable: {config_path}")

    config_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=config_path.parent,
        delete=False,
        prefix=f".{config_path.name}.",
        suffix=".tmp",
    ) as tmp:
        yaml.dump(config, tmp, default_flow_style=False, sort_keys=False, allow_unicode=True)
        temp_name = tmp.name

    os.replace(temp_name, config_path)
```

- Replace direct `open(config_path, "w")` writes in `_add_venture_to_config()` and `_remove_venture_from_config()` with `_write_yaml_atomic(config_path, config)`.
- Before copying venture template in `scaffold_venture()`, preflight `_config_path = get_config_path(root)` and `is_config_writable(_config_path)`; if false, raise `ConfigMutationError` before creating directories.
- In `_add_venture_to_config()` and `_remove_venture_from_config()`, resolve config with `get_config_path(root)`, not `root / "realize-os.yaml"`.

**Step 4: Run tests to verify pass**

Run:

```bash
pytest tests/test_scaffold.py tests/test_config_mutability.py -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add realize_core/scaffold.py tests/test_scaffold.py
git commit -m "fix(ventures): make config mutations atomic and preflighted"
```

---

## Task 3: Return structured API errors instead of 500

**Objective:** When config is locked, API routes should return a clear operator-facing response and not delete any files.

**Files:**

- Modify: `realize_api/routes/ventures.py`
- Test: `tests/test_venture_routes_config_lock.py` (new)

**Step 1: Write failing route tests**

Create `tests/test_venture_routes_config_lock.py`:

```python
from pathlib import Path

from fastapi.testclient import TestClient

from realize_api.main import create_app


def test_delete_venture_returns_conflict_when_config_locked(monkeypatch, tmp_path):
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.kb_path = tmp_path
        app.state.systems = {"ghost": {"name": "Ghost", "agents": {}}}
        monkeypatch.setattr("realize_core.scaffold.is_config_writable", lambda path: False)

        resp = client.delete("/api/ventures/ghost")

    assert resp.status_code == 409
    data = resp.json()
    assert data["detail"]["code"] == "CONFIG_NOT_WRITABLE"
    assert "realize-os.yaml" in data["detail"]["message"]
```

**Step 2: Run test to verify failure**

Run:

```bash
pytest tests/test_venture_routes_config_lock.py -v
```

Expected: FAIL with 500 or different detail shape.

**Step 3: Catch `ConfigMutationError` in route**

In `realize_api/routes/ventures.py`:

- Import `ConfigMutationError` near the delete/create route code or inside functions.
- In `create_venture()` and `delete_venture()`, wrap scaffold calls:

```python
try:
    result = scaffold_venture(...)
except ConfigMutationError as exc:
    raise HTTPException(
        status_code=409,
        detail={
            "code": "CONFIG_NOT_WRITABLE",
            "message": str(exc),
            "hint": "Mount realize-os.yaml as writable or set REALIZE_CONFIG to a writable config path.",
        },
    ) from exc
```

And similarly around `_delete(...)`.

**Step 4: Run tests**

```bash
pytest tests/test_venture_routes_config_lock.py tests/test_scaffold.py -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add realize_api/routes/ventures.py tests/test_venture_routes_config_lock.py
git commit -m "fix(api): report locked config on venture mutations"
```

---

## Task 4: Update Docker Compose for managed config mode

**Objective:** Make the default Docker deployment compatible with API-managed venture create/delete, while keeping hardened read-only examples documented.

**Files:**

- Modify: `docker-compose.yml`
- Modify: `docker-compose.prod.yml`
- Possibly modify: `.env.example`
- Possibly modify docs: `docs/` deployment guide if present

**Step 1: Update default compose**

Change in `docker-compose.yml`:

```yaml
- ./realize-os.yaml:/app/realize-os.yaml:rw        # System configuration (writable for dashboard/API venture CRUD)
```

Keep `.credentials` read-only.

**Step 2: Update prod compose**

Because `docker-compose.prod.yml` has `read_only: true`, either:

Option A — preferred:

```yaml
volumes:
  - ./config:/app/config:rw
  - ./systems:/app/systems:rw

environment:
  - REALIZE_CONFIG=/app/config/realize-os.yaml
```

Host migration requirement: move/copy `./realize-os.yaml` to `./config/realize-os.yaml` before starting prod.

Option B — simpler but less clean:

```yaml
- ./realize-os.yaml:/app/realize-os.yaml:rw
```

and keep `read_only: true`; Docker bind mount can still be writable even when the container root filesystem is read-only.

**Recommendation:** Use Option B for lowest migration friction in this PR, then consider `/app/config` in a later cleanup.

**Step 3: Add compose comments**

Document:

- `:rw` is required for `/api/ventures` create/delete.
- Operators can switch to `:ro` to lock config, but API mutation endpoints will return `CONFIG_NOT_WRITABLE`.

**Step 4: Run compose config validation**

```bash
docker compose -f docker-compose.yml config >/tmp/realizeos-compose.yml
docker compose -f docker-compose.prod.yml config >/tmp/realizeos-compose-prod.yml
```

Expected: both commands exit 0.

**Step 5: Commit**

```bash
git add docker-compose.yml docker-compose.prod.yml .env.example docs || true
git commit -m "chore(docker): allow managed config mutations"
```

---

## Task 5: Add end-to-end regression test for no ghost ventures

**Objective:** Prove deletion does not leave a venture in `app.state.systems` after successful config write and reload.

**Files:**

- Modify/new: `tests/test_venture_routes_config_lock.py`

**Step 1: Write test**

Add:

```python
import yaml


def test_delete_venture_reloads_systems_without_ghost(tmp_path):
    config = tmp_path / "realize-os.yaml"
    config.write_text(
        yaml.dump({"systems": [{"key": "ghost", "name": "Ghost", "directory": "systems/ghost"}]}),
        encoding="utf-8",
    )
    venture_dir = tmp_path / "systems" / "ghost"
    venture_dir.mkdir(parents=True)

    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.kb_path = tmp_path
        app.state.systems = {"ghost": {"name": "Ghost", "agents": {}}}

        resp = client.delete("/api/ventures/ghost")

        assert resp.status_code == 200
        assert "ghost" not in app.state.systems
        updated = yaml.safe_load(config.read_text(encoding="utf-8"))
        assert updated["systems"] == []
```

**Step 2: Run targeted tests**

```bash
pytest tests/test_venture_routes_config_lock.py tests/test_scaffold.py tests/test_config_mutability.py -v
```

Expected: PASS.

**Step 3: Commit**

```bash
git add tests/test_venture_routes_config_lock.py
git commit -m "test(ventures): prevent ghost ventures after deletion"
```

---

## Task 6: Full verification and PR

**Objective:** Verify the branch is safe and open a focused PR.

**Files:**

- No new source files unless verification reveals issues.

**Step 1: Run focused suite**

```bash
pytest tests/test_config_mutability.py tests/test_scaffold.py tests/test_venture_routes_config_lock.py -v
```

Expected: PASS.

**Step 2: Run broader API/scaffold suite**

```bash
pytest tests/test_api_routes_v2.py tests/test_api_integration.py tests/test_install_package.py tests/test_product_invariants.py -v
```

Expected: PASS or only pre-existing unrelated failures, documented in PR.

**Step 3: Check git status**

```bash
git status --short --branch
```

Expected: only intended committed changes; no accidental deletions like `tests/test_api_routes.py` unless intentionally explained.

**Step 4: Push branch**

Branch name:

```bash
fix/writable-config-venture-deletion
```

Commands:

```bash
git checkout -b fix/writable-config-venture-deletion
# or rename current branch if appropriate:
# git branch -m fix/writable-config-venture-deletion

git push -u origin HEAD
```

**Step 5: Open PR**

PR title:

```text
fix: support safe API-managed venture deletion
```

PR body:

```markdown
## Summary
- Adds config path/writeability helpers for `realize-os.yaml`
- Makes venture config mutations atomic and preflighted
- Returns structured `CONFIG_NOT_WRITABLE` errors instead of partial deletion/500s
- Updates Docker Compose comments/mounts so dashboard/API venture CRUD can persist config changes
- Adds regression coverage to prevent ghost ventures after deletion

## Why
Current Docker deployments mount `/app/realize-os.yaml` as read-only. `DELETE /api/ventures/{key}` can fail when trying to persist registry cleanup, leaving ghost ventures in `/api/systems`.

## Test Plan
- `pytest tests/test_config_mutability.py tests/test_scaffold.py tests/test_venture_routes_config_lock.py -v`
- `pytest tests/test_api_routes_v2.py tests/test_api_integration.py tests/test_install_package.py tests/test_product_invariants.py -v`
- `docker compose -f docker-compose.yml config`
- `docker compose -f docker-compose.prod.yml config`
```

---

## Acceptance criteria

- Deleting a venture with writable config:
  - removes the venture from `realize-os.yaml`
  - removes its FABRIC directory if present
  - clears related DB/index state where available
  - reloads `app.state.systems`
  - `GET /api/systems` no longer shows the deleted venture

- Deleting a venture with locked config:
  - returns `409` with `detail.code == "CONFIG_NOT_WRITABLE"`
  - does **not** delete FABRIC directories
  - does **not** mutate runtime systems
  - includes an operator hint for enabling writable config

- Creating a venture follows the same config preflight rule:
  - no copied directories if config cannot be persisted
  - structured API error instead of half-created venture

- Docker deployment supports a documented API-managed config mode.

## Risk notes

- Changing `realize-os.yaml` from `:ro` to `:rw` is an intentional product/security tradeoff. The PR should explicitly document that locked config mode remains available by switching back to `:ro`.
- Atomic write uses `os.replace`; it requires the temporary file to be created in the same directory as `realize-os.yaml`.
- In prod with `read_only: true`, bind-mounted files/directories can still be writable if the mount is `:rw`, but this should be verified with compose + container smoke testing.

## Optional follow-up after PR

Add a `/api/admin/config/status` endpoint returning:

```json
{
  "config_path": "/app/realize-os.yaml",
  "exists": true,
  "writable": true,
  "mutation_mode": "managed"
}
```

This would let the dashboard show whether venture CRUD is enabled before the user clicks delete/create.
