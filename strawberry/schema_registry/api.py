"""Public API for comparing GraphQL schemas."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Union

from graphql import GraphQLSchema

from strawberry.schema_registry.config import SchemaDiffConfig
from strawberry.schema_registry.diff_engine import SchemaDiffEngine, schema_from_sdl
from strawberry.schema_registry.types import SchemaDiff

if TYPE_CHECKING:
    from strawberry.schema.base import BaseSchema

SchemaInput = Union[str, Path, "BaseSchema", GraphQLSchema]


def _to_graphql_schema(source: SchemaInput) -> GraphQLSchema:
    """Normalise any accepted input into a ``GraphQLSchema``."""
    if isinstance(source, GraphQLSchema):
        return source

    # Path or filesystem string pointing at an .graphql / .gql file.
    if isinstance(source, Path) or (
        isinstance(source, str)
        and ("\n" not in source)
        and (source.endswith((".graphql", ".gql", ".sdl")) or Path(source).is_file())
    ):
        path = Path(source)
        if path.is_file():
            return schema_from_sdl(path.read_text(encoding="utf-8"))

    # Raw SDL string.
    if isinstance(source, str):
        # Heuristic: looks like SDL if it contains type/schema keywords.
        stripped = source.lstrip()
        if stripped.startswith(("type ", "schema ", "scalar ", "enum ", "input ", "union ", "interface ", "directive ", '"', "#")):
            return schema_from_sdl(source)
        # Otherwise treat as a module:symbol reference only when it has no spaces —
        # callers should pass a Schema instance for that case. Fall through.
        if "\n" in source or "{" in source:
            return schema_from_sdl(source)
        # Last resort: try as SDL (build_ast_schema will raise on garbage).
        return schema_from_sdl(source)

    # strawberry.Schema / BaseSchema — prefer as_str() then re-parse so applied
    # directive ast_nodes are preserved on the resulting GraphQLSchema.
    as_str = getattr(source, "as_str", None)
    if callable(as_str):
        return schema_from_sdl(as_str())

    # Fallback: internal _schema attribute.
    internal = getattr(source, "_schema", None)
    if isinstance(internal, GraphQLSchema):
        return internal

    raise TypeError(
        f"Unsupported schema input type: {type(source)!r}. "
        "Pass a strawberry.Schema, GraphQLSchema, SDL string, or file path."
    )


def diff_schemas(
    old: SchemaInput,
    new: SchemaInput,
    *,
    config: SchemaDiffConfig | None = None,
) -> SchemaDiff:
    """Compare two schemas and return a structured, deterministically ordered diff.

    Args:
        old: Previous schema — ``strawberry.Schema``, ``GraphQLSchema``,
            SDL string, or path to a ``.graphql`` file.
        new: Newer schema in the same accepted forms.
        config: Optional :class:`SchemaDiffConfig` controlling ignores and
            severity overrides.

    Returns:
        A :class:`SchemaDiff` whose ``entries`` are sorted by
        ``(path, change_kind, message, severity)`` for CI stability.
    """
    old_schema = _to_graphql_schema(old)
    new_schema = _to_graphql_schema(new)
    engine = SchemaDiffEngine(config=config)
    return engine.diff(old_schema, new_schema)
