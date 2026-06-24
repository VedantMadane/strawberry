"""Schema registry shared types for diffs and linting."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SourceLocation:
    """A precise location in a GraphQL SDL source string."""

    line: int
    column: int

    def __str__(self) -> str:
        return f"{self.line}:{self.column}"


class Severity(enum.Enum):
    """Impact classification for a schema change."""

    BREAKING = "breaking"
    DANGEROUS = "dangerous"
    SAFE = "safe"


class ChangeKind(enum.Enum):
    """Stable identifier codes for every detectable schema change."""

    # Types
    TYPE_ADDED = "TYPE_ADDED"
    TYPE_REMOVED = "TYPE_REMOVED"
    TYPE_KIND_CHANGED = "TYPE_KIND_CHANGED"
    TYPE_DESCRIPTION_CHANGED = "TYPE_DESCRIPTION_CHANGED"

    # Object / interface fields
    FIELD_ADDED = "FIELD_ADDED"
    FIELD_REMOVED = "FIELD_REMOVED"
    FIELD_TYPE_CHANGED = "FIELD_TYPE_CHANGED"
    FIELD_DESCRIPTION_CHANGED = "FIELD_DESCRIPTION_CHANGED"
    FIELD_DEPRECATION_ADDED = "FIELD_DEPRECATION_ADDED"
    FIELD_DEPRECATION_REMOVED = "FIELD_DEPRECATION_REMOVED"
    FIELD_DEPRECATION_REASON_CHANGED = "FIELD_DEPRECATION_REASON_CHANGED"

    # Nullability / list wrappers (also covered under FIELD_TYPE_CHANGED, but
    # we emit a specific code when only nullability flips)
    FIELD_NULLABILITY_CHANGED = "FIELD_NULLABILITY_CHANGED"
    ARG_NULLABILITY_CHANGED = "ARG_NULLABILITY_CHANGED"

    # Field arguments
    ARG_ADDED = "ARG_ADDED"
    ARG_REMOVED = "ARG_REMOVED"
    ARG_TYPE_CHANGED = "ARG_TYPE_CHANGED"
    ARG_DEFAULT_ADDED = "ARG_DEFAULT_ADDED"
    ARG_DEFAULT_REMOVED = "ARG_DEFAULT_REMOVED"
    ARG_DEFAULT_CHANGED = "ARG_DEFAULT_CHANGED"
    ARG_DESCRIPTION_CHANGED = "ARG_DESCRIPTION_CHANGED"

    # Input object fields
    INPUT_FIELD_ADDED = "INPUT_FIELD_ADDED"
    INPUT_FIELD_REMOVED = "INPUT_FIELD_REMOVED"
    INPUT_FIELD_TYPE_CHANGED = "INPUT_FIELD_TYPE_CHANGED"
    INPUT_FIELD_DEFAULT_ADDED = "INPUT_FIELD_DEFAULT_ADDED"
    INPUT_FIELD_DEFAULT_REMOVED = "INPUT_FIELD_DEFAULT_REMOVED"
    INPUT_FIELD_DEFAULT_CHANGED = "INPUT_FIELD_DEFAULT_CHANGED"

    # Enums
    ENUM_VALUE_ADDED = "ENUM_VALUE_ADDED"
    ENUM_VALUE_REMOVED = "ENUM_VALUE_REMOVED"
    ENUM_VALUE_DEPRECATION_ADDED = "ENUM_VALUE_DEPRECATION_ADDED"
    ENUM_VALUE_DEPRECATION_REMOVED = "ENUM_VALUE_DEPRECATION_REMOVED"
    ENUM_VALUE_DESCRIPTION_CHANGED = "ENUM_VALUE_DESCRIPTION_CHANGED"

    # Unions
    UNION_MEMBER_ADDED = "UNION_MEMBER_ADDED"
    UNION_MEMBER_REMOVED = "UNION_MEMBER_REMOVED"

    # Interfaces implemented by object types
    INTERFACE_ADDED_TO_TYPE = "INTERFACE_ADDED_TO_TYPE"
    INTERFACE_REMOVED_FROM_TYPE = "INTERFACE_REMOVED_FROM_TYPE"

    # Directives (generic)
    DIRECTIVE_ADDED = "DIRECTIVE_ADDED"
    DIRECTIVE_REMOVED = "DIRECTIVE_REMOVED"
    DIRECTIVE_LOCATION_ADDED = "DIRECTIVE_LOCATION_ADDED"
    DIRECTIVE_LOCATION_REMOVED = "DIRECTIVE_LOCATION_REMOVED"
    DIRECTIVE_ARG_ADDED = "DIRECTIVE_ARG_ADDED"
    DIRECTIVE_ARG_REMOVED = "DIRECTIVE_ARG_REMOVED"

    # Applied directives on types/fields
    APPLIED_DIRECTIVE_ADDED = "APPLIED_DIRECTIVE_ADDED"
    APPLIED_DIRECTIVE_REMOVED = "APPLIED_DIRECTIVE_REMOVED"
    APPLIED_DIRECTIVE_ARG_CHANGED = "APPLIED_DIRECTIVE_ARG_CHANGED"

    # Apollo Federation v2 specific
    FEDERATION_KEY_ADDED = "FEDERATION_KEY_ADDED"
    FEDERATION_KEY_REMOVED = "FEDERATION_KEY_REMOVED"
    FEDERATION_KEY_FIELDS_CHANGED = "FEDERATION_KEY_FIELDS_CHANGED"
    FEDERATION_REQUIRES_ADDED = "FEDERATION_REQUIRES_ADDED"
    FEDERATION_REQUIRES_REMOVED = "FEDERATION_REQUIRES_REMOVED"
    FEDERATION_REQUIRES_FIELDS_CHANGED = "FEDERATION_REQUIRES_FIELDS_CHANGED"
    FEDERATION_PROVIDES_ADDED = "FEDERATION_PROVIDES_ADDED"
    FEDERATION_PROVIDES_REMOVED = "FEDERATION_PROVIDES_REMOVED"
    FEDERATION_PROVIDES_FIELDS_CHANGED = "FEDERATION_PROVIDES_FIELDS_CHANGED"
    FEDERATION_SHAREABLE_ADDED = "FEDERATION_SHAREABLE_ADDED"
    FEDERATION_SHAREABLE_REMOVED = "FEDERATION_SHAREABLE_REMOVED"
    FEDERATION_INACCESSIBLE_ADDED = "FEDERATION_INACCESSIBLE_ADDED"
    FEDERATION_INACCESSIBLE_REMOVED = "FEDERATION_INACCESSIBLE_REMOVED"


# Default severity mapping for each change kind.
DEFAULT_SEVERITY: dict[ChangeKind, Severity] = {
    ChangeKind.TYPE_REMOVED: Severity.BREAKING,
    ChangeKind.TYPE_ADDED: Severity.SAFE,
    ChangeKind.TYPE_KIND_CHANGED: Severity.BREAKING,
    ChangeKind.TYPE_DESCRIPTION_CHANGED: Severity.SAFE,
    ChangeKind.FIELD_REMOVED: Severity.BREAKING,
    ChangeKind.FIELD_ADDED: Severity.SAFE,
    ChangeKind.FIELD_TYPE_CHANGED: Severity.BREAKING,
    ChangeKind.FIELD_NULLABILITY_CHANGED: Severity.BREAKING,
    ChangeKind.FIELD_DESCRIPTION_CHANGED: Severity.SAFE,
    ChangeKind.FIELD_DEPRECATION_ADDED: Severity.DANGEROUS,
    ChangeKind.FIELD_DEPRECATION_REMOVED: Severity.BREAKING,
    ChangeKind.FIELD_DEPRECATION_REASON_CHANGED: Severity.SAFE,
    ChangeKind.ARG_ADDED: Severity.DANGEROUS,  # required arg without default is breaking; refined in engine
    ChangeKind.ARG_REMOVED: Severity.BREAKING,
    ChangeKind.ARG_TYPE_CHANGED: Severity.BREAKING,
    ChangeKind.ARG_NULLABILITY_CHANGED: Severity.BREAKING,
    ChangeKind.ARG_DEFAULT_ADDED: Severity.SAFE,
    ChangeKind.ARG_DEFAULT_REMOVED: Severity.DANGEROUS,
    ChangeKind.ARG_DEFAULT_CHANGED: Severity.DANGEROUS,
    ChangeKind.ARG_DESCRIPTION_CHANGED: Severity.SAFE,
    ChangeKind.INPUT_FIELD_ADDED: Severity.DANGEROUS,
    ChangeKind.INPUT_FIELD_REMOVED: Severity.BREAKING,
    ChangeKind.INPUT_FIELD_TYPE_CHANGED: Severity.BREAKING,
    ChangeKind.INPUT_FIELD_DEFAULT_ADDED: Severity.SAFE,
    ChangeKind.INPUT_FIELD_DEFAULT_REMOVED: Severity.DANGEROUS,
    ChangeKind.INPUT_FIELD_DEFAULT_CHANGED: Severity.DANGEROUS,
    ChangeKind.ENUM_VALUE_ADDED: Severity.SAFE,
    ChangeKind.ENUM_VALUE_REMOVED: Severity.BREAKING,
    ChangeKind.ENUM_VALUE_DEPRECATION_ADDED: Severity.DANGEROUS,
    ChangeKind.ENUM_VALUE_DEPRECATION_REMOVED: Severity.BREAKING,
    ChangeKind.ENUM_VALUE_DESCRIPTION_CHANGED: Severity.SAFE,
    ChangeKind.UNION_MEMBER_ADDED: Severity.DANGEROUS,
    ChangeKind.UNION_MEMBER_REMOVED: Severity.BREAKING,
    ChangeKind.INTERFACE_ADDED_TO_TYPE: Severity.SAFE,
    ChangeKind.INTERFACE_REMOVED_FROM_TYPE: Severity.BREAKING,
    ChangeKind.DIRECTIVE_ADDED: Severity.SAFE,
    ChangeKind.DIRECTIVE_REMOVED: Severity.BREAKING,
    ChangeKind.DIRECTIVE_LOCATION_ADDED: Severity.SAFE,
    ChangeKind.DIRECTIVE_LOCATION_REMOVED: Severity.BREAKING,
    ChangeKind.DIRECTIVE_ARG_ADDED: Severity.DANGEROUS,
    ChangeKind.DIRECTIVE_ARG_REMOVED: Severity.BREAKING,
    ChangeKind.APPLIED_DIRECTIVE_ADDED: Severity.SAFE,
    ChangeKind.APPLIED_DIRECTIVE_REMOVED: Severity.DANGEROUS,
    ChangeKind.APPLIED_DIRECTIVE_ARG_CHANGED: Severity.DANGEROUS,
    # Federation
    ChangeKind.FEDERATION_KEY_ADDED: Severity.SAFE,
    ChangeKind.FEDERATION_KEY_REMOVED: Severity.BREAKING,
    ChangeKind.FEDERATION_KEY_FIELDS_CHANGED: Severity.BREAKING,
    ChangeKind.FEDERATION_REQUIRES_ADDED: Severity.SAFE,
    ChangeKind.FEDERATION_REQUIRES_REMOVED: Severity.BREAKING,
    ChangeKind.FEDERATION_REQUIRES_FIELDS_CHANGED: Severity.BREAKING,
    ChangeKind.FEDERATION_PROVIDES_ADDED: Severity.SAFE,
    ChangeKind.FEDERATION_PROVIDES_REMOVED: Severity.BREAKING,
    ChangeKind.FEDERATION_PROVIDES_FIELDS_CHANGED: Severity.BREAKING,
    ChangeKind.FEDERATION_SHAREABLE_ADDED: Severity.SAFE,
    ChangeKind.FEDERATION_SHAREABLE_REMOVED: Severity.DANGEROUS,
    ChangeKind.FEDERATION_INACCESSIBLE_ADDED: Severity.DANGEROUS,
    ChangeKind.FEDERATION_INACCESSIBLE_REMOVED: Severity.BREAKING,
}


@dataclass(frozen=True)
class DiffEntry:
    """A single schema difference.

    Attributes:
        change_kind: Stable identifier code for the change category.
        severity: Impact classification (breaking / dangerous / safe).
        path: Dot-separated schema path (e.g. ``Query.user.name``).
        message: Human-readable description of the change.
        old_value: Optional string representation of the prior value.
        new_value: Optional string representation of the new value.
    """

    change_kind: ChangeKind
    severity: Severity
    path: str
    message: str
    old_value: str | None = None
    new_value: str | None = None


@dataclass
class SchemaDiff:
    """Result of comparing two schemas."""

    entries: list[DiffEntry] = field(default_factory=list)

    @property
    def breaking(self) -> list[DiffEntry]:
        return [e for e in self.entries if e.severity is Severity.BREAKING]

    @property
    def dangerous(self) -> list[DiffEntry]:
        return [e for e in self.entries if e.severity is Severity.DANGEROUS]

    @property
    def safe(self) -> list[DiffEntry]:
        return [e for e in self.entries if e.severity is Severity.SAFE]

    @property
    def has_breaking(self) -> bool:
        return bool(self.breaking)

    def __iter__(self):
        return iter(self.entries)

    def __len__(self) -> int:
        return len(self.entries)


class LintSeverity(enum.Enum):
    """Severity of a lint rule violation."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class LintViolation:
    """A single lint rule violation."""

    rule_name: str
    message: str
    path: str
    location: SourceLocation | None = None
    severity: LintSeverity = LintSeverity.ERROR
