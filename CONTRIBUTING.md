# Contributing to RealizeOS

Welcome! We're glad you're interested in contributing.

## Quick Start

```bash
git clone https://github.com/SufZen/realize-os.git
cd realize-os
pip install -e ".[dev]"
pytest
```

## Development Setup

1. **Fork and clone** the repository
2. **Create a virtual environment**: `python -m venv venv && venv\Scripts\activate` (Windows) or `source venv/bin/activate` (Unix)
3. **Install dependencies**: `pip install -e ".[dev]"`
4. **Run tests**: `pytest`
5. **Check linting**: `python -m py_compile realize_core/your_file.py`

## How to Contribute

### Report Bugs

Open an issue with:
- Steps to reproduce
- Expected vs actual behavior
- Python version and OS

### Add a New Tool

Follow the [Build Your First Tool](docs/dev-process/reference/build-your-first-tool.md) guide:

1. Create a class extending `BaseTool`
2. Define schemas with `ToolSchema`
3. Implement `execute()` and `is_available()`
4. Register with `ToolRegistry`
5. Add tests

### Add a New Channel

Follow the [Build Your Own Channel](docs/dev-process/reference/build-your-own-channel.md) guide:

1. Create a class extending `BaseChannel`
2. Implement `start()`, `stop()`, `send_message()`, `format_instructions()`
3. Add tests

### Add a Skill

1. Create a YAML skill file in `skills/`
2. Define system prompt, agent key, and tools
3. Test via the API channel

## Code Standards

- **Python 3.11+** with type hints
- **pytest** for all tests
- **Docstrings** on all public functions and classes
- **No unused imports** — CI will catch these
- Follow existing patterns observed in the codebase

## Project Structure

```
realize_core/
├── channels/     # Communication adapters
├── evolution/    # Self-evolution engine
├── llm/          # LLM abstraction + routing
├── media/        # Media processing pipeline
├── security/     # RBAC, audit, vault
├── tools/        # Tool SDK + implementations
├── workflows/    # Workflow engine
└── cli.py        # CLI entry point
```

## Pull Request Process

1. Create a feature branch from `main`
2. Write tests for new functionality
3. Ensure all tests pass (`pytest`)
4. Update docs if adding new features
5. Submit a PR with a clear description

## License

By contributing, you agree that your contributions will be licensed under the same license as the project.
