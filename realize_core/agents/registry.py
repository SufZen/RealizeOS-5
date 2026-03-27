"""
Agent Registry — centralised store for loaded agent definitions.

Provides:
- Register / unregister agents at runtime
- Lookup by key
- Hot-reload from directory (file-watcher friendly)
- Enumerate all agents with optional filters
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from pathlib import Path
from threading import Lock

from realize_core.agents.loader import AgentDef, load_agents_from_directory
from realize_core.agents.schema import V1AgentDef, V2AgentDef

logger = logging.getLogger(__name__)


class AgentRegistry:
    """
    Thread-safe registry of agent definitions with hot-reload support.

    Usage::

        registry = AgentRegistry()
        registry.load_from_directory(Path("systems/my-biz/A-agents"))
        writer = registry.get("writer")
    """

    def __init__(self) -> None:
        self._agents: dict[str, AgentDef] = {}
        self._lock = Lock()
        self._load_timestamp: float = 0.0
        self._source_dirs: list[Path] = []

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def register(self, agent: AgentDef) -> None:
        """Add or replace an agent definition in the registry."""
        with self._lock:
            self._agents[agent.key] = agent
            logger.debug("Registered agent '%s' (v%s)", agent.key, agent.version)

    def unregister(self, key: str) -> bool:
        """
        Remove an agent by key.

        Returns:
            True if the agent existed and was removed.
        """
        with self._lock:
            if key in self._agents:
                del self._agents[key]
                logger.debug("Unregistered agent '%s'", key)
                return True
            return False

    def get(self, key: str) -> AgentDef | None:
        """Lookup an agent by key, or ``None`` if not found."""
        with self._lock:
            return self._agents.get(key)

    def get_or_raise(self, key: str) -> AgentDef:
        """Lookup an agent by key; raise ``KeyError`` if missing."""
        agent = self.get(key)
        if agent is None:
            raise KeyError(f"Agent '{key}' not found in registry")
        return agent

    def keys(self) -> list[str]:
        """Return a snapshot of all registered agent keys."""
        with self._lock:
            return list(self._agents.keys())

    def all(self) -> list[AgentDef]:
        """Return a snapshot of all registered agent definitions."""
        with self._lock:
            return list(self._agents.values())

    def __len__(self) -> int:
        with self._lock:
            return len(self._agents)

    def __contains__(self, key: str) -> bool:
        with self._lock:
            return key in self._agents

    def __iter__(self) -> Iterator[AgentDef]:
        with self._lock:
            return iter(list(self._agents.values()))

    # ------------------------------------------------------------------
    # Filtered queries
    # ------------------------------------------------------------------

    def v1_agents(self) -> list[V1AgentDef]:
        """Return all V1 (markdown) agents."""
        with self._lock:
            return [a for a in self._agents.values() if isinstance(a, V1AgentDef)]

    def v2_agents(self) -> list[V2AgentDef]:
        """Return all V2 (YAML composable) agents."""
        with self._lock:
            return [a for a in self._agents.values() if isinstance(a, V2AgentDef)]

    def agents_with_pipeline(self) -> list[V2AgentDef]:
        """Return V2 agents that define a pipeline."""
        return [a for a in self.v2_agents() if a.has_pipeline]

    def agents_by_persona(self, persona: str) -> list[V2AgentDef]:
        """Return V2 agents matching a persona bundle."""
        return [a for a in self.v2_agents() if a.persona == persona]

    # ------------------------------------------------------------------
    # Directory loading & hot-reload
    # ------------------------------------------------------------------

    def load_from_directory(self, directory: Path | str) -> int:
        """
        Discover and register all agents from a directory.

        Args:
            directory: Path to scan (e.g. ``systems/my-biz/A-agents``).

        Returns:
            Number of agents loaded.
        """
        directory = Path(directory)
        agents = load_agents_from_directory(directory)

        with self._lock:
            for agent in agents:
                self._agents[agent.key] = agent
            if directory not in self._source_dirs:
                self._source_dirs.append(directory)
            self._load_timestamp = time.time()

        logger.info(
            "Loaded %d agents from %s",
            len(agents),
            directory,
        )
        return len(agents)

    def reload(self) -> int:
        """
        Re-scan all previously loaded directories and refresh atomically.

        Returns:
            Total number of agents after reload.
        """
        with self._lock:
            dirs = list(self._source_dirs)

        new_agents: dict[str, AgentDef] = {}
        for d in dirs:
            agents = load_agents_from_directory(d)
            for agent in agents:
                if agent.key in new_agents:
                    logger.warning("Duplicate agent key '%s' — overwriting", agent.key)
                new_agents[agent.key] = agent

        with self._lock:
            self._agents = new_agents
            self._load_timestamp = time.time()

        total = len(new_agents)
        logger.info("Registry reloaded: %d agents from %d directories", total, len(dirs))
        return total

    def clear(self) -> None:
        """Remove all agents and forget source directories."""
        with self._lock:
            self._agents.clear()
            self._source_dirs.clear()
            self._load_timestamp = 0.0

    @property
    def load_timestamp(self) -> float:
        """Epoch time of the last load/reload."""
        return self._load_timestamp

    @property
    def source_dirs(self) -> list[Path]:
        """Directories that have been loaded."""
        with self._lock:
            return list(self._source_dirs)

    def health(self) -> dict:
        """Return diagnostic health information for the registry."""
        with self._lock:
            return {
                "agent_count": len(self._agents),
                "v1_count": len(self.v1_agents()),
                "v2_count": len(self.v2_agents()),
                "source_dirs": [str(d) for d in self._source_dirs],
                "last_load_timestamp": self._load_timestamp,
                "uptime_seconds": time.time() - self._load_timestamp if self._load_timestamp else 0.0,
            }
