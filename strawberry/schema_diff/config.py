"""Configuration for schema diff behaviour."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Pattern

from .models import ChangeCode, ChangeSeverity


@dataclass
class SchemaDiffConfig:
    """Tune which changes are reported and at what severity.

    Attributes:
        ignore_codes: Change codes to completely suppress.
        ignore_field_patterns: Regex patterns matched against field paths
            (e.g. ``r"\\._"`` to ignore internal ``_``-prefixed fields).
        ignore_type_patterns: Regex patterns matched against type names.
        severity_overrides: Map of change codes to a custom severity.
        include_descriptions: Whether to report description-only changes.
        fail_on_breaking: Hint for CLI/CI (does not affect diff computation).
        fail_on_dangerous: Hint for CLI/CI (does not affect diff computation).
    """

    ignore_codes: set[ChangeCode | str] = field(default_factory=set)
    ignore_field_patterns: list[str | Pattern[str]] = field(default_factory=list)
    ignore_type_patterns: list[str | Pattern[str]] = field(default_factory=list)
    severity_overrides: dict[ChangeCode | str, ChangeSeverity | str] = field(
        default_factory=dict
    )
    include_descriptions: bool = True
    fail_on_breaking: bool = True
    fail_on_dangerous: bool = False

    def __post_init__(self) -> None:
        self._compiled_field_patterns: list[Pattern[str]] = [
            re.compile(p) if isinstance(p, str) else p
            for p in self.ignore_field_patterns
        ]
        self._compiled_type_patterns: list[Pattern[str]] = [
            re.compile(p) if isinstance(p, str) else p
            for p in self.ignore_type_patterns
        ]
        self._ignore_codes_norm: set[str] = {
            c.value if isinstance(c, ChangeCode) else str(c) for c in self.ignore_codes
        }
        self._severity_overrides_norm: dict[str, ChangeSeverity] = {}
        for key, val in self.severity_overrides.items():
            k = key.value if isinstance(key, ChangeCode) else str(key)
            if isinstance(val, ChangeSeverity):
                self._severity_overrides_norm[k] = val
            else:
                self._severity_overrides_norm[k] = ChangeSeverity(str(val))

    def is_code_ignored(self, code: ChangeCode) -> bool:
        return code.value in self._ignore_codes_norm

    def should_ignore_path(self, path: str) -> bool:
        """Return True if *path* matches any ignore_field_patterns."""
        for pattern in self._compiled_field_patterns:
            if pattern.search(path):
                return True
        return False

    def should_ignore_type(self, type_name: str) -> bool:
        for pattern in self._compiled_type_patterns:
            if pattern.search(type_name):
                return True
        return False

    def resolve_severity(
        self, code: ChangeCode, default: ChangeSeverity
    ) -> ChangeSeverity:
        return self._severity_overrides_norm.get(code.value, default)
