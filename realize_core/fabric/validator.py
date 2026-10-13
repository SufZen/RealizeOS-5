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
        #: The core families loaded from the schemas folder; :meth:`extend` never replaces them.
        self._core: frozenset[str] = frozenset(self._schemas)

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
        """Get the JSON Schema for a given entity type, with ``allOf`` references resolved.

        Pack schemas (spec 010) extend a core family with ``allOf: [{"$ref": ...}]``.
        The returned schema merges the referenced schemas' ``properties`` and
        ``required`` with the extension's own; the extension wins per property.
        """
        schema = self._schemas.get(entity_type)
        if schema is None:
            return None
        return self._resolve(schema, seen=set())

    def register(self, name: str, schema: dict) -> list[str]:
        """Register an extra schema (e.g. from a pack) and return extension problems.

        Args:
            name: Entity type the schema validates (e.g. ``payment-claim``).
            schema: JSON Schema dict, usually ``allOf`` a core family.

        Returns:
            Human-readable problems, such as an extension retyping a core property.
            Registration happens regardless; validation stays soft.
        """
        props = schema.get("properties", {})
        if "allOf" in schema and "type" not in props:
            # An extension validates entities of its own type, not the core family's.
            schema = {**schema, "properties": {**props, "type": {"type": "string", "const": name}}}
        self._schemas[name] = schema
        return self.check_extension(schema)

    @property
    def core_types(self) -> frozenset[str]:
        """The core families (the schemas folder's files), which extensions may not replace."""
        return self._core

    def _rooted_in_core(self, schema: dict, seen: frozenset[int] = frozenset()) -> bool:
        """True when the schema's ``allOf`` chain reaches a core family."""
        if id(schema) in seen:
            return False
        for base in self._referenced(schema):
            if any(self._schemas.get(name) is base for name in self._core):
                return True
            if self._rooted_in_core(base, seen | {id(schema)}):
                return True
        return False

    def extend(self, name: str, schema: dict) -> tuple[bool, list[str]]:
        """Register a pack's extension of a core family, refusing anything that isn't one.

        A pack extends core objects and never forks them (ADR 0005), so an
        extension is refused when it would take a core family's name or
        ``$id``, or when it doesn't build on a core family through ``allOf``
        (directly or through an extension already registered). A property
        that retypes a core property is dropped, so the core type still holds.

        Args:
            name: Entity type the extension validates (e.g. ``payment-claim``).
            schema: The extension's JSON Schema.

        Returns:
            ``(registered, problems)``: whether it was registered, and why not
            or what was dropped.
        """
        if not isinstance(schema, dict):
            return False, [f"'{name}' is not a JSON object"]
        shape = _extension_shape_problem(schema)
        if shape:
            return False, [f"'{name}': {shape}"]
        if name in self._core:
            return False, [f"'{name}' would replace the core schema of the same name"]
        core_ids = {self._schemas[c].get("$id") for c in self._core} - {None}
        if schema.get("$id") in core_ids:
            return False, [f"'{name}' reuses the $id of a core schema ({schema.get('$id')})"]
        if not self._rooted_in_core(schema):
            return False, [f"'{name}' doesn't extend a core family with allOf"]
        problems = self.check_extension(schema)
        retyped = self._retyped(schema)
        if retyped:
            props = {k: v for k, v in schema.get("properties", {}).items() if k not in retyped}
            schema = {**schema, "properties": props}
        self.register(name, schema)
        return True, problems

    def _retyped(self, schema: dict) -> set[str]:
        """Own properties whose type differs from the type a referenced schema gives them."""
        out: set[str] = set()
        own = schema.get("properties", {})
        for base in self._referenced(schema):
            base_props = self._resolve(base, seen=set()).get("properties", {})
            for prop_name, prop in own.items():
                base_type = base_props.get(prop_name, {}).get("type")
                new_type = prop.get("type") if isinstance(prop, dict) else None
                if base_type and new_type and base_type != new_type:
                    out.add(prop_name)
        return out

    def check_extension(self, schema: dict) -> list[str]:
        """List places where ``schema`` retypes a property defined by a schema it extends."""
        problems: list[str] = []
        own = schema.get("properties", {})
        for base in self._referenced(schema):
            base_props = self._resolve(base, seen=set()).get("properties", {})
            for prop_name, prop in own.items():
                if prop_name in base_props:
                    base_type = base_props[prop_name].get("type")
                    new_type = prop.get("type")
                    if base_type and new_type and base_type != new_type:
                        problems.append(f"Property '{prop_name}' retypes core type '{base_type}' as '{new_type}'")
        return problems

    def _lookup_ref(self, ref: str) -> dict | None:
        """Find a schema by ``$id``, file name (``money-event.json``) or type name."""
        for schema in self._schemas.values():
            if schema.get("$id") == ref:
                return schema
        stem = ref.rsplit("/", 1)[-1].removesuffix(".json")
        return self._schemas.get(stem)

    def _referenced(self, schema: dict) -> list[dict]:
        """Schemas referenced from ``allOf`` entries."""
        found = []
        for part in schema.get("allOf", []):
            if isinstance(part, dict) and "$ref" in part:
                target = self._lookup_ref(part["$ref"])
                if target is None:
                    logger.warning("Schema reference not found: %s", part["$ref"])
                else:
                    found.append(target)
        return found

    def _resolve(self, schema: dict, seen: set[int]) -> dict:
        """Flatten ``allOf`` references into one schema (properties and required)."""
        if id(schema) in seen or "allOf" not in schema:
            return schema
        seen = seen | {id(schema)}
        properties: dict = {}
        required: list = []
        for base in self._referenced(schema):
            resolved = self._resolve(base, seen)
            properties.update(resolved.get("properties", {}))
            required.extend(r for r in resolved.get("required", []) if r not in required)
        properties.update(schema.get("properties", {}))
        required.extend(r for r in schema.get("required", []) if r not in required)
        merged = {k: v for k, v in schema.items() if k != "allOf"}
        merged["properties"] = properties
        merged["required"] = required
        return merged

    @property
    def known_types(self) -> list[str]:
        """List all entity types with registered schemas."""
        return sorted(self._schemas.keys())


def _extension_shape_problem(schema: dict) -> str:
    """Why a pack schema can't be used as an extension ('' when its shape is fine)."""
    all_of = schema.get("allOf", [])
    if not isinstance(all_of, list) or not all(
        isinstance(part, dict) and isinstance(part.get("$ref", ""), str) for part in all_of
    ):
        return "allOf must be a list of {$ref: text} objects"
    props = schema.get("properties", {})
    if not isinstance(props, dict) or not all(isinstance(p, dict) for p in props.values()):
        return "properties must map names to objects"
    required = schema.get("required", [])
    if not isinstance(required, list) or not all(isinstance(r, str) for r in required):
        return "required must be a list of property names"
    return ""


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

    # Check enum and const constraints
    for field_name, value in frontmatter.items():
        if field_name in properties:
            prop = properties[field_name]

            # Const check (JSON Schema 2020-12)
            if "const" in prop and value != prop["const"]:
                result.warnings.append(
                    ValidationWarning(
                        entity_id=entity_id,
                        field=field_name,
                        message=f"Value '{value}' does not match required const '{prop['const']}'",
                    )
                )
                continue  # Don't also warn about type if const mismatches

            # Enum check
            if "enum" in prop and value not in prop["enum"]:
                result.warnings.append(
                    ValidationWarning(
                        entity_id=entity_id,
                        field=field_name,
                        message=f"Value '{value}' not in allowed values: {prop['enum']}",
                    )
                )

            # Type check (basic — skip if const is used, since const implies type)
            expected_type = prop.get("type")
            if expected_type and "const" not in prop and not _type_matches(value, expected_type):
                result.warnings.append(
                    ValidationWarning(
                        entity_id=entity_id,
                        field=field_name,
                        message=f"Expected type '{expected_type}', got '{type(value).__name__}'",
                    )
                )

    result.valid = len(result.warnings) == 0
    return result


def _type_matches(value, expected_type: str | list[str]) -> bool:
    """Check if a value matches a JSON Schema type string or list of type strings."""
    if isinstance(expected_type, list):
        return any(_type_matches(value, t) for t in expected_type)
    if expected_type == "null":
        return value is None
    if isinstance(value, bool) and expected_type in ("number", "integer"):
        return False
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
