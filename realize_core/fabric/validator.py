"""
FABRIC Soft Schema Validator.

Validates entities against JSON Schemas stored in docs/fabric-schemas/.
Soft validation: produces warnings, never errors. Unknown fields are allowed.
FABRIC never refuses content.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ValidationWarning:
    """A single validation warning."""

    entity_id: str
    field: str
    message: str
    suggestion: str = ""

    def __str__(self) -> str:
        s = f"[{self.entity_id}] {self.field}: {self.message}"
        if self.suggestion:
            s += f" (suggestion: {self.suggestion})"
        return s


@dataclass
class ValidationResult:
    """Result of validating a FABRIC entity."""

    entity_id: str
    entity_type: str
    valid: bool = True
    warnings: list[ValidationWarning] = field(default_factory=list)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)


class SchemaRegistry:
    """
    Registry of FABRIC entity schemas.

    Loads JSON Schema files from docs/fabric-schemas/ and provides
    soft validation for entities.
    """

    def __init__(self, schemas_dir: Path | None = None):
        self._schemas: dict[str, dict] = {}
        self._schemas_dir = schemas_dir or self._default_schemas_dir()
        self._load_schemas()

    @staticmethod
    def _default_schemas_dir() -> Path:
        """Default location: docs/fabric-schemas/ relative to project root."""
        return Path(__file__).parent.parent.parent / "docs" / "fabric-schemas"

    def _load_schemas(self) -> None:
        """Load all JSON schema files from the schemas directory."""
        if not self._schemas_dir.exists():
            logger.info(f"Schema directory not found: {self._schemas_dir}")
            return

        for schema_file in self._schemas_dir.glob("*.json"):
            if schema_file.name.startswith("_"):
                continue  # Skip _common.json and other meta files

            try:
                schema = json.loads(schema_file.read_text(encoding="utf-8"))
                entity_type = schema_file.stem  # e.g., "decision" from "decision.json"
                self._schemas[entity_type] = schema
                logger.debug(f"Loaded schema: {entity_type}")
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to load schema {schema_file}: {e}")

        logger.info(f"Loaded {len(self._schemas)} FABRIC schemas")

    def get_schema(self, entity_type: str) -> dict | None:
        """Get the JSON Schema for a given entity type."""
        return self._schemas.get(entity_type)

    @property
    def known_types(self) -> list[str]:
        """List all entity types with registered schemas."""
        return sorted(self._schemas.keys())


def validate_entity(
    frontmatter: dict,
    entity_type: str = "",
    entity_id: str = "",
    registry: SchemaRegistry | None = None,
) -> ValidationResult:
    """
    Validate a FABRIC entity's frontmatter against its schema.

    This is soft validation: it produces warnings, never errors.
    Unknown fields are always allowed.

    Args:
        frontmatter: The parsed YAML frontmatter dict.
        entity_type: Entity type (inferred from frontmatter if empty).
        entity_id: Entity ID (inferred from frontmatter if empty).
        registry: Schema registry (created with defaults if None).

    Returns:
        ValidationResult with any warnings found.
    """
    entity_type = entity_type or frontmatter.get("type", "")
    entity_id = entity_id or frontmatter.get("id", "<unknown>")

    result = ValidationResult(entity_id=entity_id, entity_type=entity_type)

    if not entity_type:
        result.warnings.append(
            ValidationWarning(
                entity_id=entity_id,
                field="type",
                message="Missing entity type",
                suggestion="Add 'type' field to frontmatter",
            )
        )
        return result

    if registry is None:
        registry = SchemaRegistry()

    schema = registry.get_schema(entity_type)
    if schema is None:
        # Unknown type — not an error, just no validation
        return result

    # Check required fields
    required = schema.get("required", [])
    properties = schema.get("properties", {})

    for field_name in required:
        if field_name not in frontmatter:
            prop_info = properties.get(field_name, {})
            result.warnings.append(
                ValidationWarning(
                    entity_id=entity_id,
                    field=field_name,
                    message=f"Missing required field: {field_name}",
                    suggestion=prop_info.get("description", ""),
                )
            )

    # Check enum constraints
    for field_name, value in frontmatter.items():
        if field_name in properties:
            prop = properties[field_name]

            # Enum check
            if "enum" in prop and value not in prop["enum"]:
                result.warnings.append(
                    ValidationWarning(
                        entity_id=entity_id,
                        field=field_name,
                        message=f"Value '{value}' not in allowed values: {prop['enum']}",
                    )
                )

            # Type check (basic)
            expected_type = prop.get("type")
            if expected_type and not _type_matches(value, expected_type):
                result.warnings.append(
                    ValidationWarning(
                        entity_id=entity_id,
                        field=field_name,
                        message=f"Expected type '{expected_type}', got '{type(value).__name__}'",
                    )
                )

    result.valid = len(result.warnings) == 0
    return result


def _type_matches(value, expected_type: str) -> bool:
    """Check if a value matches a JSON Schema type string."""
    type_map = {
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    expected = type_map.get(expected_type)
    if expected is None:
        return True  # Unknown type, don't warn
    return isinstance(value, expected)
