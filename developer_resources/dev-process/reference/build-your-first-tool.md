# Build Your First Custom Tool

> **Time:** 10 minutes | **Prerequisites:** Python 3.11+, realize_core installed

## How Tools Work

Every tool in RealizeOS follows the same pattern:

1. **Extend `BaseTool`** — define name, description, and schemas
2. **Implement `execute()`** — the logic that runs when the LLM calls your tool
3. **Register** — the `ToolRegistry` discovers and manages your tool
4. **LLM uses it** — schemas are sent to the LLM, which calls actions by name

## Step 1: Create Your Tool File

Create a new file in `realize_core/tools/`:

```python
# realize_core/tools/weather_tool.py
"""Example: Weather lookup tool."""
import httpx
from typing import Any

from realize_core.tools.base_tool import (
    BaseTool,
    ToolCategory,
    ToolResult,
    ToolSchema,
)


class WeatherTool(BaseTool):
    """Look up current weather for a location."""

    @property
    def name(self) -> str:
        return "weather"

    @property
    def description(self) -> str:
        return "Get current weather conditions for any city"

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.RESEARCH

    def get_schemas(self) -> list[ToolSchema]:
        return [
            ToolSchema(
                name="get_weather",
                description="Get current weather for a city.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                            "description": "City name (e.g., 'London')",
                        },
                    },
                    "required": ["city"],
                },
                category=ToolCategory.RESEARCH,
                is_destructive=False,
            ),
        ]

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        if action != "get_weather":
            return ToolResult.fail(f"Unknown action: {action}")

        city = params["city"]
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"https://wttr.in/{city}?format=j1",
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()

            current = data["current_condition"][0]
            return ToolResult.ok(
                output=(
                    f"Weather in {city}: {current['weatherDesc'][0]['value']}, "
                    f"{current['temp_C']}°C, "
                    f"Wind: {current['windspeedKmph']} km/h"
                ),
                data=current,
            )
        except Exception as e:
            return ToolResult.fail(f"Weather lookup failed: {e}")

    def is_available(self) -> bool:
        return True  # No API key needed (uses wttr.in)


def get_tool() -> WeatherTool:
    """Factory function for auto-discovery."""
    return WeatherTool()
```

## Step 2: Register Your Tool

Two options:

### Option A: Auto-discovery (recommended)

Add your module to the `known_modules` list in `realize_core/tools/tool_registry.py`:

```python
known_modules = [
    "realize_core.tools.web_tool",
    "realize_core.tools.weather_tool",  # ← Add this
]
```

### Option B: YAML config

Create or edit `realize_core/tools.yaml`:

```yaml
tools:
  weather:
    module: realize_core.tools.weather_tool
    enabled: true
```

### Option C: Manual registration

```python
from realize_core.tools.tool_registry import get_tool_registry
from realize_core.tools.weather_tool import WeatherTool

registry = get_tool_registry()
registry.register(WeatherTool())
```

## Step 3: Test Your Tool

```python
# tests/test_weather_tool.py
import pytest
from realize_core.tools.weather_tool import WeatherTool


class TestWeatherTool:
    def test_name(self):
        tool = WeatherTool()
        assert tool.name == "weather"

    def test_schemas(self):
        tool = WeatherTool()
        schemas = tool.get_schemas()
        assert len(schemas) == 1
        assert schemas[0].name == "get_weather"

    def test_claude_format(self):
        tool = WeatherTool()
        claude = tool.get_claude_schemas()
        assert claude[0]["name"] == "get_weather"
        assert "input_schema" in claude[0]

    def test_is_available(self):
        tool = WeatherTool()
        assert tool.is_available()

    @pytest.mark.asyncio
    async def test_execute(self):
        tool = WeatherTool()
        result = await tool.execute("get_weather", {"city": "London"})
        assert result.success
        assert "London" in result.output
```

## Step 4: Use It

The LLM will automatically see your tool when it's registered:

```text
User: "What's the weather in Tokyo?"
→ Classifier detects: web_research task
→ Router loads tool schemas including get_weather
→ LLM calls: get_weather(city="Tokyo")
→ Your execute() runs and returns the result
```

## Key Concepts

### Schemas define what the LLM sees

```python
ToolSchema(
    name="action_name",           # What the LLM calls
    description="What it does",    # Helps the LLM decide when to use it
    input_schema={...},            # JSON Schema for parameters
    is_destructive=False,          # True = write/delete operations
)
```

### ToolResult tells the LLM what happened

```python
# Success
ToolResult.ok("The answer is 42", data={"value": 42})

# Failure
ToolResult.fail("API key not configured")
```

### Categories help organize tools

| Category | Use for |
|----------|---------|
| `RESEARCH` | Read-only lookups (search, weather, data) |
| `COMMUNICATION` | Email, messaging |
| `PRODUCTIVITY` | Calendar, docs, tasks |
| `DEVELOPMENT` | Code, git, CI/CD |
| `MEDIA` | Image/video/audio generation |
| `DATA` | Database, analytics |
| `AUTOMATION` | Browser automation, workflows |
| `CUSTOM` | Everything else |

## Reference Implementation

See `realize_core/tools/web_tool.py` for a complete reference showing:

- Multiple actions in one tool (`web_search`, `web_fetch`)
- Wrapping existing functions
- Error handling with `ToolResult.fail()`
- The `get_tool()` factory pattern
