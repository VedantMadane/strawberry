"""Data models for schema diff results."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ChangeSeverity(str, Enum):
    """Severity level of a schema change."""

    BREAKING = "BREAKING"
    DANGEROUS = "DANGEROUS"
    SAFE = "SAFE"

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, ChangeSeverity):
            return NotImplemented
        order = {
            ChangeSeverity.BREAKING: 0,
            ChangeSeverity.DANGEROUS: 1,
            ChangeSeverity.SAFE: 2,
        }
        return order[self] < order[other]


class ChangeCode(str, Enum):
    """Stable identifiers for each kind of schema change."""

    TYPE_ADDED = "TYPE_ADDED"
    TYPE_REMOVED = "TYPE_REMOVED"
    TYPE_KIND_CHANGED = "TYPE_KIND_CHANGED"
    TYPE_DESCRIPTION_CHANGED = "TYPE_DESCRIPTION_CHANGED"

    FIELD_ADDED = "FIELD_ADDED"
    FIELD_REMOVED = "FIELD_REMOVED"
    FIELD_TYPE_CHANGED = "FIELD_TYPE_CHANGED"
    FIELD_MADE_NULLABLE = "FIELD_MADE_NULLABLE"
    FIELD_MADE_NON_NULL = "FIELD_MADE_NON_NULL"
    FIELD_DESCRIPTION_CHANGED = "FIELD_DESCRIPTION_CHANGED"
    FIELD_DEPRECATION_ADDED = "FIELD_DEPRECATION_ADDED"
    FIELD_DEPRECATION_REMOVED = "FIELD_DEPRECATION_REMOVED"
    FIELD_DEPRECATION_REASON_CHANGED = "FIELD_DEPRECATION_REASON_CHANGED"

    ARG_ADDED = "ARG_ADDED"
    ARG_REMOVED = "ARG_REMOVED"
    ARG_TYPE_CHANGED = "ARG_TYPE_CHANGED"
    ARG_MADE_NULLABLE = "ARG_MADE_NULLABLE"
    ARG_MADE_NON_NULL = "ARG_MADE_NON_NULL"
    ARG_DEFAULT_ADDED = "ARG_DEFAULT_ADDED"
    ARG_DEFAULT_REMOVED = "ARG_DEFAULT_REMOVED"
    ARG_DEFAULT_CHANGED = "ARG_DEFAULT_CHANGED"
    ARG_DESCRIPTION_CHANGED = "ARG_DESCRIPTION_CHANGED"

    ENUM_VALUE_ADDED = "ENUM_VALUE_ADDED"
    ENUM_VALUE_REMOVED = "ENUM_VALUE_REMOVED"
    ENUM_VALUE_DESCRIPTION_CHANGED = "ENUM_VALUE_DESCRIPTION_CHANGED"
    ENUM_VALUE_DEPRECATION_ADDED = "ENUM_VALUE_DEPRECATION_ADDED"
    ENUM_VALUE_DEPRECATION_REMOVED = "ENUM_VALUE_DEPRECATION_REMOVED"

    UNION_MEMBER_ADDED = "UNION_MEMBER_ADDED"
    UNION_MEMBER_REMOVED = "UNION_MEMBER_REMOVED"

    INTERFACE_ADDED_TO_OBJECT = "INTERFACE_ADDED_TO_OBJECT"
    INTERFACE_REMOVED_FROM_OBJECT = "INTERFACE_REMOVED_FROM_OBJECT"

    DIRECTIVE_ADDED = "DIRECTIVE_ADDED"
    DIRECTIVE_REMOVED = "DIRECTIVE_REMOVED"
    DIRECTIVE_LOCATION_ADDED = "DIRECTIVE_LOCATION_ADDED"
    DIRECTIVE_LOCATION_REMOVED = "DIRECTIVE_LOCATION_REMOVED"
    DIRECTIVE_ARG_ADDED = "DIRECTIVE_ARG_ADDED"
    DIRECTIVE_ARG_REMOVED = "DIRECTIVE_ARG_REMOVED"
    DIRECTIVE_ARG_TYPE_CHANGED = "DIRECTIVE_ARG_TYPE_CHANGED"
    DIRECTIVE_ARG_DEFAULT_CHANGED = "DIRECTIVE_ARG_DEFAULT_CHANGED"

    APPLIED_DIRECTIVE_ADDED = "APPLIED_DIRECTIVE_ADDED"
    APPLIED_DIRECTIVE_REMOVED = "APPLIED_DIRECTIVE_REMOVED"
    APPLIED_DIRECTIVE_ARG_CHANGED = "APPLIED_DIRECTIVE_ARG_CHANGED"

    SCHEMA_QUERY_TYPE_CHANGED = "SCHEMA_QUERY_TYPE_CHANGED"
    SCHEMA_MUTATION_TYPE_CHANGED = "SCHEMA_MUTATION_TYPE_CHANGED"
    SCHEMA_SUBSCRIPTION_TYPE_CHANGED = "SCHEMA_SUBSCRIPTION_TYPE_CHANGED"

    FED_KEY_ADDED = "FED_KEY_ADDED"
    FED_KEY_REMOVED = "FED_KEY_REMOVED"
    FED_KEY_FIELDS_CHANGED = "FED_KEY_FIELDS_CHANGED"
    FED_KEY_RESOLVABLE_CHANGED = "FED_KEY_RESOLVABLE_CHANGED"
    FED_REQUIRES_ADDED = "FED_REQUIRES_ADDED"
    FED_REQUIRES_REMOVED = "FED_REQUIRES_REMOVED"
    FED_REQUIRES_FIELDS_CHANGED = "FED_REQUIRES_FIELDS_CHANGED"
    FED_PROVIDES_ADDED = "FED_PROVIDES_ADDED"
    FED_PROVIDES_REMOVED = "FED_PROVIDES_REMOVED"
    FED_PROVIDES_FIELDS_CHANGED = "FED_PROVIDES_FIELDS_CHANGED"
    FED_SHAREABLE_ADDED = "FED_SHAREABLE_ADDED"
    FED_SHAREABLE_REMOVED = "FED_SHAREABLE_REMOVED"
    FED_INACCESSIBLE_ADDED = "FED_INACCESSIBLE_ADDED"
    FED_INACCESSIBLE_REMOVED = "FED_INACCESSIBLE_REMOVED"
    FED_EXTERNAL_ADDED = "FED_EXTERNAL_ADDED"
    FED_EXTERNAL_REMOVED = "FED_EXTERNAL_REMOVED"
    FED_OVERRIDE_ADDED = "FED_OVERRIDE_ADDED"
    FED_OVERRIDE_REMOVED = "FED_OVERRIDE_REMOVED"
    FED_TAG_ADDED = "FED_TAG_ADDED"
    FED_TAG_REMOVED = "FED_TAG_REMOVED"


DEFAULT_SEVERITY: dict[ChangeCode, ChangeSeverity] = {
    ChangeCode.TYPE_REMOVED: ChangeSeverity.BREAKING,
    ChangeCode.TYPE_KIND_CHANGED: ChangeSeverity.BREAKING,
    ChangeCode.FIELD_REMOVED: ChangeSeverity.BREAKING,
    ChangeCode.FIELD_TYPE_CHANGED: ChangeSeverity.BREAKING,
    ChangeCode.FIELD_MADE_NON_NULL: ChangeSeverity.BREAKING,
    ChangeCode.FIELD_DEPRECATION_REMOVED: ChangeSeverity.DANGEROUS,
    ChangeCode.ARG_REMOVED: ChangeSeverity.BREAKING,
    ChangeCode.ARG_TYPE_CHANGED: ChangeSeverity.BREAKING,
    ChangeCode.ARG_MADE_NON_NULL: ChangeSeverity.BREAKING,
    ChangeCode.ARG_DEFAULT_REMOVED: ChangeSeverity.BREAKING,
    ChangeCode.ARG_DEFAULT_CHANGED: ChangeSeverity.DANGEROUS,
    ChangeCode.ENUM_VALUE_REMOVED: ChangeSeverity.BREAKING,
    ChangeCode.UNION_MEMBER_REMOVED: ChangeSeverity.BREAKING,
    ChangeCode.INTERFACE_REMOVED_FROM_OBJECT: ChangeSeverity.BREAKING,
    ChangeCode.DIRECTIVE_REMOVED: ChangeSeverity.BREAKING,
    ChangeCode.DIRECTIVE_LOCATION_REMOVED: ChangeSeverity.BREAKING,
    ChangeCode.DIRECTIVE_ARG_REMOVED: ChangeSeverity.BREAKING,
    ChangeCode.DIRECTIVE_ARG_TYPE_CHANGED: ChangeSeverity.BREAKING,
    ChangeCode.SCHEMA_QUERY_TYPE_CHANGED: ChangeSeverity.BREAKING,
    ChangeCode.SCHEMA_MUTATION_TYPE_CHANGED: ChangeSeverity.BREAKING,
    ChangeCode.SCHEMA_SUBSCRIPTION_TYPE_CHANGED: ChangeSeverity.BREAKING,
    ChangeCode.FED_KEY_REMOVED: ChangeSeverity.BREAKING,
    ChangeCode.FED_KEY_FIELDS_CHANGED: ChangeSeverity.BREAKING,
    ChangeCode.FED_REQUIRES_REMOVED: ChangeSeverity.BREAKING,
    ChangeCode.FED_REQUIRES_FIELDS_CHANGED: ChangeSeverity.BREAKING,
    ChangeCode.FED_PROVIDES_REMOVED: ChangeSeverity.DANGEROUS,
    ChangeCode.FED_PROVIDES_FIELDS_CHANGED: ChangeSeverity.DANGEROUS,
    ChangeCode.FED_SHAREABLE_REMOVED: ChangeSeverity.BREAKING,
    ChangeCode.FED_INACCESSIBLE_REMOVED: ChangeSeverity.DANGEROUS,
    ChangeCode.FED_EXTERNAL_REMOVED: ChangeSeverity.BREAKING,
    ChangeCode.FED_OVERRIDE_REMOVED: ChangeSeverity.BREAKING,
    ChangeCode.FIELD_MADE_NULLABLE: ChangeSeverity.DANGEROUS,
    ChangeCode.ARG_MADE_NULLABLE: ChangeSeverity.DANGEROUS,
    ChangeCode.ARG_DEFAULT_ADDED: ChangeSeverity.DANGEROUS,
    ChangeCode.FIELD_DEPRECATION_ADDED: ChangeSeverity.DANGEROUS,
    ChangeCode.ENUM_VALUE_DEPRECATION_ADDED: ChangeSeverity.DANGEROUS,
    ChangeCode.ENUM_VALUE_DEPRECATION_REMOVED: ChangeSeverity.DANGEROUS,
    ChangeCode.UNION_MEMBER_ADDED: ChangeSeverity.DANGEROUS,
    ChangeCode.INTERFACE_ADDED_TO_OBJECT: ChangeSeverity.DANGEROUS,
    ChangeCode.APPLIED_DIRECTIVE_REMOVED: ChangeSeverity.DANGEROUS,
    ChangeCode.APPLIED_DIRECTIVE_ARG_CHANGED: ChangeSeverity.DANGEROUS,
    ChangeCode.FED_KEY_RESOLVABLE_CHANGED: ChangeSeverity.DANGEROUS,
    ChangeCode.FED_INACCESSIBLE_ADDED: ChangeSeverity.DANGEROUS,
    ChangeCode.FED_OVERRIDE_ADDED: ChangeSeverity.DANGEROUS,
    ChangeCode.TYPE_ADDED: ChangeSeverity.SAFE,
    ChangeCode.TYPE_DESCRIPTION_CHANGED: ChangeSeverity.SAFE,
    ChangeCode.FIELD_ADDED: ChangeSeverity.SAFE,
    ChangeCode.FIELD_DESCRIPTION_CHANGED: ChangeSeverity.SAFE,
    ChangeCode.FIELD_DEPRECATION_REASON_CHANGED: ChangeSeverity.SAFE,
    ChangeCode.ARG_ADDED: ChangeSeverity.SAFE,
    ChangeCode.ARG_DESCRIPTION_CHANGED: ChangeSeverity.SAFE,
    ChangeCode.ENUM_VALUE_ADDED: ChangeSeverity.SAFE,
    ChangeCode.ENUM_VALUE_DESCRIPTION_CHANGED: ChangeSeverity.SAFE,
    ChangeCode.DIRECTIVE_ADDED: ChangeSeverity.SAFE,
    ChangeCode.DIRECTIVE_LOCATION_ADDED: ChangeSeverity.SAFE,
    ChangeCode.DIRECTIVE_ARG_ADDED: ChangeSeverity.SAFE,
    ChangeCode.DIRECTIVE_ARG_DEFAULT_CHANGED: ChangeSeverity.DANGEROUS,
    ChangeCode.APPLIED_DIRECTIVE_ADDED: ChangeSeverity.SAFE,
    ChangeCode.FED_KEY_ADDED: ChangeSeverity.SAFE,
    ChangeCode.FED_REQUIRES_ADDED: ChangeSeverity.SAFE,
    ChangeCode.FED_PROVIDES_ADDED: ChangeSeverity.SAFE,
    ChangeCode.FED_SHAREABLE_ADDED: ChangeSeverity.SAFE,
    ChangeCode.FED_EXTERNAL_ADDED: ChangeSeverity.SAFE,
    ChangeCode.FED_TAG_ADDED: ChangeSeverity.SAFE,
    ChangeCode.FED_TAG_REMOVED: ChangeSeverity.SAFE,
}


@dataclass(frozen=True, order=False)
class SchemaChange:
    """A single detected difference between two schemas."""

    code: ChangeCode
    severity: ChangeSeverity
    path: str
    message: str
    old_value: Any | None = None
    new_value: Any | None = None
    meta: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)

    def sort_key(self) -> tuple[int, str, str]:
        sev_order = {
            ChangeSeverity.BREAKING: 0,
            ChangeSeverity.DANGEROUS: 1,
            ChangeSeverity.SAFE: 2,
        }
        return (sev_order[self.severity], self.path, self.code.value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "severity": self.severity.value,
            "path": self.path,
            "message": self.message,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "meta": self.meta,
        }


@dataclass
class SchemaDiffResult:
    """Complete result of a schema comparison."""

    changes: list[SchemaChange] = field(default_factory=list)
    old_schema_source: str = ""
    new_schema_source: str = ""

    @property
    def breaking(self) -> list[SchemaChange]:
        return [c for c in self.changes if c.severity == ChangeSeverity.BREAKING]

    @property
    def dangerous(self) -> list[SchemaChange]:
        return [c for c in self.changes if c.severity == ChangeSeverity.DANGEROUS]

    @property
    def safe(self) -> list[SchemaChange]:
        return [c for c in self.changes if c.severity == ChangeSeverity.SAFE]

    @property
    def has_breaking(self) -> bool:
        return any(c.severity == ChangeSeverity.BREAKING for c in self.changes)

    @property
    def has_dangerous(self) -> bool:
        return any(c.severity == ChangeSeverity.DANGEROUS for c in self.changes)

    def summary(self) -> dict[str, int]:
        return {
            "breaking": len(self.breaking),
            "dangerous": len(self.dangerous),
            "safe": len(self.safe),
            "total": len(self.changes),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary(),
            "has_breaking": self.has_breaking,
            "changes": [c.to_dict() for c in self.changes],
        }

    def __bool__(self) -> bool:
        return len(self.changes) > 0
