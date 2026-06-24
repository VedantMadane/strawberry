"""Configuration for the schema diff utility."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from strawberry.schema_registry.types import ChangeKind, Severity


@dataclass
class SchemaDiffConfig:
    """Controls filtering and severity behaviour of schema diffs.

    Attributes:
        ignore_change_kinds: Change codes that should be omitted entirely.
        ignore_path_patterns: Compiled or string regexes; matching entry paths
            are ignored (e.g. ``r"^.*\\._"`` for underscore-prefixed fields).
        severity_overrides: Map of change codes to a forced severity.
    """

    ignore_change_kinds: set[ChangeKind] = field(default_factory=set)
    ignore_path_patterns: list[str | re.Pattern[str]] = field(default_factory=list)
    severity_overrides: dict[ChangeKind, Severity] = field(default_factory=dict)

    def __post_init__(self) -> None:
        compiled: list[re.Pattern[str]] = []
        for pattern in self.ignore_path_patterns:
            if isinstance(pattern, re.Pattern):
                compiled.append(pattern)
            else:
                compiled.append(re.compile(pattern))
        # Store only compiled patterns for runtime checks.
        object.__setattr__(self, "_compiled_path_patterns", compiled)

    @property
    def compiled_path_patterns(self) -> list[re.Pattern[str]]:
        return getattr(self, "_compiled_path_patterns", [])

    def should_ignore(self, change_kind: ChangeKind, path: str) -> bool:
        """Return True when an entry should be dropped from the result."""
        if change_kind in self.ignore_change_kinds:
            return True
        for pattern in self.compiled_path_patterns:
            if pattern.search(path):
                return True
        return False

    def resolve_severity(
        self, change_kind: ChangeKind, default: Severity
    ) -> Severity:
        """Return the effective severity, honouring overrides."""
        return self.severity_overrides.get(change_kind, default)
