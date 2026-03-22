"""
Automation integration — trigger n8n/Make.com workflows.

Configure in .env:
  N8N_BASE_URL=https://your-n8n.example.com
  N8N_API_KEY=...
"""
import logging
import os

logger = logging.getLogger(__name__)


def is_available() -> bool:
    return bool(os.getenv("N8N_BASE_URL", ""))


async def trigger_workflow(workflow_id: str, data: dict = None) -> dict:
    """
    Trigger an n8n workflow via webhook.

    Args:
        workflow_id: The n8n workflow ID or webhook path
        data: Payload data to send

    Returns:
        {triggered: bool, response, error}
    """
    base_url = os.getenv("N8N_BASE_URL", "").rstrip("/")
    api_key = os.getenv("N8N_API_KEY", "")
    if not base_url:
        return {"triggered": False, "error": "N8N_BASE_URL not configured"}

    try:
        import httpx
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        url = f"{base_url}/webhook/{workflow_id}"

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=headers, json=data or {})
            return {
                "triggered": resp.status_code in (200, 201),
                "status_code": resp.status_code,
                "response": resp.text[:500],
            }
    except ImportError:
        return {"triggered": False, "error": "httpx not installed"}
    except Exception as e:
        return {"triggered": False, "error": str(e)[:200]}


async def list_workflows() -> dict:
    """List available n8n workflows."""
    base_url = os.getenv("N8N_BASE_URL", "").rstrip("/")
    api_key = os.getenv("N8N_API_KEY", "")
    if not base_url or not api_key:
        return {"workflows": [], "error": "N8N not configured"}

    try:
        import httpx
        headers = {"Authorization": f"Bearer {api_key}"}

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{base_url}/api/v1/workflows", headers=headers)
            data = resp.json()
            workflows = data.get("data", [])
            return {
                "workflows": [
                    {
                        "id": w.get("id", ""),
                        "name": w.get("name", ""),
                        "active": w.get("active", False),
                    }
                    for w in workflows
                ],
            }
    except ImportError:
        return {"workflows": [], "error": "httpx not installed"}
    except Exception as e:
        return {"workflows": [], "error": str(e)[:200]}


def get_automation_status() -> dict:
    return {
        "configured": is_available(),
        "provider": "n8n",
        "description": "Workflow automation triggers",
    }
