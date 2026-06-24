"""Schema diff utility for comparing GraphQL schemas structurally."""

from .config import SchemaDiffConfig
from .diff import diff_schemas
from .models import ChangeCode, ChangeSeverity, SchemaChange, SchemaDiffResult
from .report import format_markdown, format_terminal

__all__ = [
    "ChangeCode",
    "ChangeSeverity",
    "SchemaChange",
    "SchemaDiffConfig",
    "SchemaDiffResult",
    "diff_schemas",
    "format_markdown",
    "format_terminal",
]
