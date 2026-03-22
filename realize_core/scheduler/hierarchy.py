"""
Agent Hierarchy: derives org tree from agent .md frontmatter.

Agent definitions can include a YAML frontmatter field:
```
---
reports_to: orchestrator
---
# Writer
You create compelling content...
```

The hierarchy is derived at read-time from the filesystem — no DB storage needed.
"""
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def parse_agent_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter from an agent .md file."""
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if not match:
        return {}

    frontmatter = {}
    for line in match.group(1).strip().split("\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            frontmatter[key.strip()] = value.strip().strip('"').strip("'")
    return frontmatter


def build_org_tree(kb_path: Path, sys_conf: dict) -> dict:
    """
    Build an org tree from agent definitions.

    Returns:
        {
            "agents": { "orchestrator": {...}, "writer": {...}, ... },
            "tree": [
                { "key": "orchestrator", "children": [
                    { "key": "writer", "children": [] },
                    { "key": "analyst", "children": [] },
                ]}
            ]
        }
    """
    agents_info = {}
    agents_map = sys_conf.get("agents", {})

    for agent_key, rel_path in agents_map.items():
        agent_path = kb_path / rel_path
        frontmatter = {}
        if agent_path.exists():
            try:
                content = agent_path.read_text(encoding="utf-8")
                frontmatter = parse_agent_frontmatter(content)
            except Exception:
                pass

        agents_info[agent_key] = {
            "key": agent_key,
            "reports_to": frontmatter.get("reports_to"),
            "role": frontmatter.get("role", ""),
        }

    # Build tree structure
    children_map: dict[str | None, list[str]] = {}
    for key, info in agents_info.items():
        parent = info["reports_to"]
        if parent and parent not in agents_info:
            parent = None  # Invalid parent — treat as root
        children_map.setdefault(parent, []).append(key)

    def build_node(key: str) -> dict:
        return {
            "key": key,
            "reports_to": agents_info[key]["reports_to"],
            "role": agents_info[key]["role"],
            "children": [build_node(c) for c in sorted(children_map.get(key, []))],
        }

    # Root nodes: agents with no parent or parent=None
    roots = sorted(children_map.get(None, []))
    tree = [build_node(r) for r in roots]

    return {
        "agents": agents_info,
        "tree": tree,
    }
