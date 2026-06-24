"""Extensible schema linting engine.

Provides a base ``LintRule`` class and a ``SchemaLinter`` that runs a
configurable set of rules against a parsed GraphQL SDL document.
"""

from __future__ import annotations

import abc
from typing import Any

from graphql import DocumentNode, parse as gql_parse
from graphql.language import ast as gql_ast

from strawberry.schema_registry.types import (
    LintSeverity,
    LintViolation,
    SourceLocation,
)


def _loc(node: gql_ast.Node | None) -> SourceLocation | None:
    """Extract a ``SourceLocation`` from a graphql-core AST node."""
    if node is None or node.loc is None:
        return None
    source = node.loc.source
    body = source.body
    line = 1
    col = 1
    for i in range(node.loc.start):
        if body[i] == "\n":
            line += 1
            col = 1
        else:
            col += 1
    return SourceLocation(line=line, column=col)


class LintRule(abc.ABC):
    """Base class for all schema lint rules.

    Subclasses must implement :meth:`check` and provide a ``name`` attribute.

    Attributes:
        name: A unique identifier for the rule (e.g. ``"require-descriptions"``).
        description: A human-readable explanation of the rule.
        severity: The default severity of violations from this rule.
    """

    name: str = ""
    description: str = ""
    severity: LintSeverity = LintSeverity.ERROR

    def __init__(self, **kwargs: Any) -> None:
        """Initialize the rule with optional configuration keyword arguments."""
        self.config = kwargs

    @abc.abstractmethod
    def check(self, document: DocumentNode) -> list[LintViolation]:
        """Run the rule against a parsed SDL document.

        Args:
            document: A parsed ``graphql.DocumentNode``.

        Returns:
            A list of ``LintViolation`` objects for each finding.
        """
        ...

    def _violation(
        self,
        message: str,
        path: str,
        node: gql_ast.Node | None = None,
        severity: LintSeverity | None = None,
    ) -> LintViolation:
        """Helper to create a ``LintViolation`` with consistent metadata."""
        return LintViolation(
            rule_name=self.name,
            message=message,
            path=path,
            location=_loc(node),
            severity=severity or self.severity,
        )


class SchemaLinter:
    """Run a collection of lint rules against a GraphQL schema.

    Args:
        rules: The list of ``LintRule`` instances to execute.
    """

    def __init__(self, rules: list[LintRule] | None = None) -> None:
        self._rules: list[LintRule] = rules or []

    def add_rule(self, rule: LintRule) -> None:
        """Register an additional lint rule."""
        self._rules.append(rule)

    @property
    def rules(self) -> list[LintRule]:
        """Return the list of registered rules."""
        return list(self._rules)

    def lint(self, sdl: str) -> list[LintViolation]:
        """Parse and lint a schema SDL string.

        Args:
            sdl: The schema in SDL format.

        Returns:
            A sorted list of ``LintViolation`` objects.

        Raises:
            graphql.error.GraphQLSyntaxError: If the SDL string is invalid.
        """
        document = gql_parse(sdl)
        violations: list[LintViolation] = []
        for rule in self._rules:
            violations.extend(rule.check(document))
        violations.sort(key=lambda v: (v.path, v.rule_name, v.message))
        return violations
