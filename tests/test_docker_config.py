"""
Tests for Docker configuration validation.

Validates that the Dockerfile and docker-compose.yml follow
RealizeOS V5 conventions:
- Multi-stage build (dashboard → runtime)
- Non-root user
- Named volumes for persistent data
- Healthcheck configuration
- Optional GWS CLI support
"""
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = ROOT / "Dockerfile"
COMPOSE_FILE = ROOT / "docker-compose.yml"


# ---------------------------------------------------------------------------
# Fixture: load files once
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def dockerfile_content() -> str:
    """Read the Dockerfile content."""
    assert DOCKERFILE.exists(), f"Dockerfile not found at {DOCKERFILE}"
    return DOCKERFILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def compose_config() -> dict:
    """Parse docker-compose.yml into a dict."""
    assert COMPOSE_FILE.exists(), f"docker-compose.yml not found at {COMPOSE_FILE}"
    with open(COMPOSE_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def compose_raw() -> str:
    """Raw docker-compose.yml text."""
    return COMPOSE_FILE.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Dockerfile Tests
# ---------------------------------------------------------------------------

class TestDockerfile:
    """Validate the multi-stage Dockerfile."""

    def test_has_multi_stage_build(self, dockerfile_content: str):
        """Dockerfile must have at least 2 FROM statements (multi-stage)."""
        from_statements = re.findall(r"^FROM\s+", dockerfile_content, re.MULTILINE)
        assert len(from_statements) >= 2, (
            f"Expected multi-stage build with >=2 FROM statements, found {len(from_statements)}"
        )

    def test_dashboard_builder_stage(self, dockerfile_content: str):
        """Stage 1 must build the dashboard with Node."""
        assert re.search(
            r"FROM\s+node:.*\s+AS\s+dashboard-builder",
            dockerfile_content,
            re.IGNORECASE,
        ), "Missing 'dashboard-builder' stage using Node image"

    def test_python_runtime_stage(self, dockerfile_content: str):
        """Stage 2 must use Python as the runtime."""
        assert re.search(
            r"FROM\s+python:.*\s+AS\s+runtime",
            dockerfile_content,
            re.IGNORECASE,
        ), "Missing 'runtime' stage using Python image"

    def test_copies_static_from_builder(self, dockerfile_content: str):
        """Runtime stage must COPY --from dashboard-builder."""
        assert re.search(
            r"COPY\s+--from=dashboard-builder",
            dockerfile_content,
        ), "Runtime stage must copy static assets from dashboard-builder stage"

    def test_non_root_user(self, dockerfile_content: str):
        """Dockerfile must create and switch to a non-root user."""
        assert "useradd" in dockerfile_content or "adduser" in dockerfile_content, (
            "Must create a non-root user"
        )
        assert re.search(
            r"^USER\s+\w+",
            dockerfile_content,
            re.MULTILINE,
        ), "Must switch to non-root USER"

    def test_non_root_user_is_not_root(self, dockerfile_content: str):
        """The USER directive must not be 'root'."""
        user_match = re.findall(r"^USER\s+(\w+)", dockerfile_content, re.MULTILINE)
        assert user_match, "No USER directive found"
        # The last USER statement (active at runtime) must not be root
        assert user_match[-1] != "root", "USER must not be root"

    def test_exposes_port_8080(self, dockerfile_content: str):
        """Must expose port 8080."""
        assert re.search(
            r"^EXPOSE\s+8080",
            dockerfile_content,
            re.MULTILINE,
        ), "Must EXPOSE 8080"

    def test_healthcheck_present(self, dockerfile_content: str):
        """Dockerfile must include a HEALTHCHECK."""
        assert "HEALTHCHECK" in dockerfile_content, "Must include HEALTHCHECK"

    def test_gws_build_arg(self, dockerfile_content: str):
        """Must support INSTALL_GWS build arg for optional Google Workspace."""
        assert re.search(
            r"^ARG\s+INSTALL_GWS",
            dockerfile_content,
            re.MULTILINE,
        ), "Must declare INSTALL_GWS build argument"

    def test_cmd_runs_uvicorn(self, dockerfile_content: str):
        """Default CMD must start uvicorn."""
        assert "uvicorn" in dockerfile_content, "Default CMD must run uvicorn"


# ---------------------------------------------------------------------------
# docker-compose.yml Tests
# ---------------------------------------------------------------------------

class TestDockerCompose:
    """Validate docker-compose.yml configuration."""

    def test_api_service_exists(self, compose_config: dict):
        """Must define an 'api' service."""
        assert "services" in compose_config, "Missing 'services' key"
        assert "api" in compose_config["services"], "Missing 'api' service"

    def test_api_port_mapping(self, compose_config: dict):
        """API service must expose port 8080."""
        api = compose_config["services"]["api"]
        ports = api.get("ports", [])
        port_strings = [str(p) for p in ports]
        assert any("8080" in p for p in port_strings), (
            f"API service must map port 8080, got: {port_strings}"
        )

    def test_healthcheck_configured(self, compose_config: dict):
        """API service must have a healthcheck."""
        api = compose_config["services"]["api"]
        assert "healthcheck" in api, "API service must define a healthcheck"
        hc = api["healthcheck"]
        assert "test" in hc, "Healthcheck must have a 'test' command"
        assert "interval" in hc, "Healthcheck must have an 'interval'"

    def test_restart_policy(self, compose_config: dict):
        """API service must have a restart policy."""
        api = compose_config["services"]["api"]
        assert "restart" in api, "API service must have a restart policy"
        assert api["restart"] in ("always", "unless-stopped", "on-failure"), (
            f"Unexpected restart policy: {api['restart']}"
        )

    def test_named_volumes_defined(self, compose_config: dict):
        """docker-compose.yml must define named volumes."""
        assert "volumes" in compose_config, "Must define top-level 'volumes'"
        volumes = compose_config["volumes"]
        assert len(volumes) >= 2, (
            f"Expected at least 2 named volumes, found {len(volumes)}"
        )

    def test_data_volume_exists(self, compose_config: dict):
        """Must define a volume for /app/data persistence."""
        volumes = compose_config.get("volumes", {})
        # Check that at least one volume relates to data
        volume_names = list(volumes.keys())
        assert any("data" in v for v in volume_names), (
            f"Expected a 'data' named volume, got: {volume_names}"
        )

    def test_shared_volume_exists(self, compose_config: dict):
        """Must define a volume for /app/shared KB content."""
        volumes = compose_config.get("volumes", {})
        volume_names = list(volumes.keys())
        assert any("shared" in v for v in volume_names), (
            f"Expected a 'shared' named volume, got: {volume_names}"
        )

    def test_api_mounts_named_volumes(self, compose_config: dict):
        """API service must mount the named volumes."""
        api = compose_config["services"]["api"]
        mounts = api.get("volumes", [])
        mount_strings = [str(m) for m in mounts]

        # Check at least one named volume is mounted to /app/data
        has_data = any("/app/data" in m for m in mount_strings)
        assert has_data, f"Must mount named volume to /app/data, got: {mount_strings}"

    def test_config_mounted_readonly(self, compose_config: dict):
        """realize-os.yaml must be bind-mounted read-only."""
        api = compose_config["services"]["api"]
        mounts = api.get("volumes", [])
        mount_strings = [str(m) for m in mounts]

        config_mount = [m for m in mount_strings if "realize-os.yaml" in m]
        assert config_mount, "Must bind-mount realize-os.yaml"
        assert any(":ro" in m for m in config_mount), (
            f"realize-os.yaml should be mounted read-only, got: {config_mount}"
        )

    def test_env_file_configured(self, compose_config: dict):
        """API service must load from .env file."""
        api = compose_config["services"]["api"]
        env_file = api.get("env_file", [])
        if isinstance(env_file, str):
            env_file = [env_file]
        assert any(".env" in f for f in env_file), "Must load .env file"

    def test_build_context(self, compose_config: dict):
        """API service must reference the Dockerfile build."""
        api = compose_config["services"]["api"]
        build = api.get("build", {})
        if isinstance(build, str):
            assert build in (".", "./"), f"Build context should be '.', got: {build}"
        else:
            assert build.get("context") in (".", "./"), (
                f"Build context should be '.', got: {build.get('context')}"
            )
            assert build.get("dockerfile") == "Dockerfile", (
                f"Dockerfile should be 'Dockerfile', got: {build.get('dockerfile')}"
            )

    def test_gws_build_arg_passthrough(self, compose_config: dict):
        """Build args must pass through INSTALL_GWS."""
        api = compose_config["services"]["api"]
        build = api.get("build", {})
        if isinstance(build, dict):
            args = build.get("args", {})
            assert "INSTALL_GWS" in args, (
                "Build args must include INSTALL_GWS for optional GWS CLI"
            )
