"""
Project management integration — ClickUp task CRUD.

Configure in .env:
  CLICKUP_API_KEY=pk_...
  CLICKUP_TEAM_ID=...
"""

import logging
import os

logger = logging.getLogger(__name__)


def is_available() -> bool:
    return bool(os.getenv("CLICKUP_API_KEY", ""))


async def list_tasks(list_id: str, status: str = "") -> dict:
    """List tasks from a ClickUp list."""
    api_key = os.getenv("CLICKUP_API_KEY", "")
    if not api_key:
        return {"error": "CLICKUP_API_KEY not configured"}

    try:
        import httpx

        headers = {"Authorization": api_key}
        params = {}
        if status:
            params["statuses[]"] = status

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"https://api.clickup.com/api/v2/list/{list_id}/task",
                headers=headers,
                params=params,
            )
            data = resp.json()
            tasks = data.get("tasks", [])
            return {
                "tasks": [
                    {
                        "id": t["id"],
                        "name": t["name"],
                        "status": t.get("status", {}).get("status", ""),
                        "assignees": [a.get("username", "") for a in t.get("assignees", [])],
                        "due_date": t.get("due_date"),
                        "priority": t.get("priority", {}).get("priority") if t.get("priority") else None,
                    }
                    for t in tasks
                ],
                "count": len(tasks),
            }
    except ImportError:
        return {"error": "httpx not installed"}
    except Exception as e:
        return {"error": str(e)[:200]}


async def create_task(list_id: str, name: str, description: str = "", priority: int = 3) -> dict:
    """Create a task in ClickUp."""
    api_key = os.getenv("CLICKUP_API_KEY", "")
    if not api_key:
        return {"error": "CLICKUP_API_KEY not configured"}

    try:
        import httpx

        headers = {"Authorization": api_key, "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"https://api.clickup.com/api/v2/list/{list_id}/task",
                headers=headers,
                json={"name": name, "description": description, "priority": priority},
            )
            task = resp.json()
            return {
                "task_id": task.get("id", ""),
                "name": task.get("name", ""),
                "url": task.get("url", ""),
                "status": task.get("status", {}).get("status", ""),
            }
    except ImportError:
        return {"error": "httpx not installed"}
    except Exception as e:
        return {"error": str(e)[:200]}


async def update_task_status(task_id: str, status: str) -> dict:
    """Update a task's status in ClickUp."""
    api_key = os.getenv("CLICKUP_API_KEY", "")
    if not api_key:
        return {"error": "CLICKUP_API_KEY not configured"}

    try:
        import httpx

        headers = {"Authorization": api_key, "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.put(
                f"https://api.clickup.com/api/v2/task/{task_id}",
                headers=headers,
                json={"status": status},
            )
            task = resp.json()
            return {
                "task_id": task.get("id", ""),
                "status": task.get("status", {}).get("status", ""),
            }
    except ImportError:
        return {"error": "httpx not installed"}
    except Exception as e:
        return {"error": str(e)[:200]}


def get_pm_status() -> dict:
    return {
        "configured": is_available(),
        "provider": "clickup",
        "description": "Task management, sprint planning",
    }
