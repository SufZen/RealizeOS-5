# RealizeOS V5 — Quality Configuration

> Python stack with RealizeOS-specific command paths.

## Check Commands

| Check | Command | Expected Output |
| --- | --- | --- |
| **Tests** | `python -m pytest tests/ -v` | Exit code 0 |
| **Lint / Format** | `ruff check realize_core/ realize_api/ && ruff format --check realize_core/ realize_api/` | Exit code 0 |
| **Type Check** | `mypy realize_core/ realize_api/` | Exit code 0 |
| **Security** | `bandit -r realize_core/ realize_api/ -ll && pip-audit` | No critical findings |
| **Complexity** | Manual review or `radon cc realize_core/ -a -nc` | Complexity observations |
| **Coverage** | `python -m pytest tests/ --cov=realize_core --cov-report=term` | Coverage % |
| **Architecture** | Manual review against project-context.md | Compliance observations |

## Weights

| Check | Weight |
| --- | --- |
| Tests | 35% |
| Lint / Format | 15% |
| Security (bandit + pip-audit) | 15% |
| Type Safety (mypy) | 10% |
| Complexity | 10% |
| Coverage | 5% |
| Architecture | 10% |

## Notes

- `mypy` path targets `realize_core/` and `realize_api/` (not `dashboard/`)
- For PowerShell: replace `&&` with `;` or run commands separately
- Dashboard quality is manually reviewed (TypeScript linting is separate)
- Security weight is elevated because this project will be public open-source
