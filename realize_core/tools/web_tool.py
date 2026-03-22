"""
Web Tool: Reference BaseTool implementation wrapping the existing web.py functions.

Demonstrates how to wrap existing tool functions into the BaseTool interface.
"""
import logging
from typing import Any

from realize_core.tools.base_tool import (
    BaseTool,
    ToolCategory,
    ToolResult,
    ToolSchema,
)

logger = logging.getLogger(__name__)


class WebTool(BaseTool):
    """
    Web research tool: search and fetch web pages.

    This is a reference implementation showing how existing tool functions
    can be wrapped in the BaseTool interface for unified discovery and execution.
    """

    @property
    def name(self) -> str:
        return "web"

    @property
    def description(self) -> str:
        return "Search the web and fetch/read web pages"

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.RESEARCH

    def get_schemas(self) -> list[ToolSchema]:
        return [
            ToolSchema(
                name="web_search",
                description="Search the web using Brave Search. Returns titles, URLs, and descriptions.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The search query."},
                        "count": {
                            "type": "integer",
                            "description": "Number of results (1-20, default 5).",
                            "default": 5,
                        },
                        "freshness": {
                            "type": "string",
                            "enum": ["pd", "pw", "pm", "py"],
                            "description": "Freshness filter: pd/pw/pm/py or omit for all time.",
                        },
                    },
                    "required": ["query"],
                },
                category=ToolCategory.RESEARCH,
                requires_auth=True,  # Brave API key required
                is_destructive=False,
            ),
            ToolSchema(
                name="web_fetch",
                description="Fetch a web page and extract readable content as clean text.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "The URL to fetch."},
                        "max_chars": {
                            "type": "integer",
                            "description": "Max characters (default 8000).",
                            "default": 8000,
                        },
                    },
                    "required": ["url"],
                },
                category=ToolCategory.RESEARCH,
                requires_auth=False,
                is_destructive=False,
            ),
        ]

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        from realize_core.tools.web import web_fetch, web_search

        if action == "web_search":
            results = await web_search(
                query=params["query"],
                count=params.get("count", 5),
                freshness=params.get("freshness"),
            )
            if results and "error" in results[0]:
                return ToolResult.fail(results[0]["error"])
            return ToolResult.ok(
                output="\n".join(
                    f"- [{r['title']}]({r['url']}): {r['description']}"
                    for r in results
                ),
                data=results,
                result_count=len(results),
            )

        elif action == "web_fetch":
            result = await web_fetch(
                url=params["url"],
                max_chars=params.get("max_chars", 8000),
            )
            if "error" in result:
                return ToolResult.fail(result["error"])
            return ToolResult.ok(
                output=result.get("content", ""),
                data=result,
                url=result["url"],
                title=result.get("title", ""),
                truncated=result.get("truncated", False),
            )

        return ToolResult.fail(f"Unknown action: {action}")

    def is_available(self) -> bool:
        # web_search requires Brave API key; web_fetch works without
        return True  # At minimum web_fetch always works


def get_tool() -> WebTool:
    """Factory function for auto-discovery."""
    return WebTool()
