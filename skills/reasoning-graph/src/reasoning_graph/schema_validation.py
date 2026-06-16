"""JSON Schema validation for reasoning graph state and patch documents."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any

import jsonschema

SCHEMA_PACKAGE = "reasoning_graph.schemas"
STATE_SCHEMA = "state.schema.json"
PATCH_SCHEMA = "patch.schema.json"


@lru_cache(maxsize=None)
def load_schema(name: str) -> dict[str, Any]:
    """Load a packaged JSON Schema by filename."""

    schema_text = resources.files(SCHEMA_PACKAGE).joinpath(name).read_text(encoding="utf-8")
    return json.loads(schema_text)


@lru_cache(maxsize=1)
def schema_store() -> dict[str, dict[str, Any]]:
    state_schema = load_schema(STATE_SCHEMA)
    patch_schema = load_schema(PATCH_SCHEMA)
    return {
        STATE_SCHEMA: state_schema,
        PATCH_SCHEMA: patch_schema,
        state_schema["$id"]: state_schema,
        patch_schema["$id"]: patch_schema,
    }


def schema_path(error: jsonschema.ValidationError) -> str:
    if not error.absolute_path:
        return "$"
    return "$" + "".join(f"[{part}]" if isinstance(part, int) else f".{part}" for part in error.absolute_path)


def format_schema_error(error: jsonschema.ValidationError) -> str:
    return f"schema {schema_path(error)}: {error.message}"


def schema_validation_errors(document: dict[str, Any], schema_name: str) -> list[str]:
    schema = load_schema(schema_name)
    if schema_name == STATE_SCHEMA:
        validator = jsonschema.Draft202012Validator(schema)
    else:
        resolver = jsonschema.RefResolver.from_schema(schema, store=schema_store())
        validator = jsonschema.Draft202012Validator(schema, resolver=resolver)
    errors = sorted(validator.iter_errors(document), key=lambda error: (list(error.absolute_path), error.message))
    return [format_schema_error(error) for error in errors]


def state_schema_errors(state: dict[str, Any]) -> list[str]:
    return schema_validation_errors(state, STATE_SCHEMA)


def patch_schema_errors(patch: dict[str, Any]) -> list[str]:
    return schema_validation_errors(patch, PATCH_SCHEMA)
