"""Lint rule: federation entity types must declare ``@key``."""

from __future__ import annotations

from typing import Any

from graphql import DocumentNode
from graphql.language import ast as gql_ast

from strawberry.schema_registry.linter import LintRule
from strawberry.schema_registry.types import LintViolation


def _has_key_directive(node: gql_ast.Node) -> bool:
    """Check whether a type definition has the ``@key`` directive."""
    directives = getattr(node, "directives", None) or ()
    return any(d.name.value == "key" for d in directives)


class FederationKeyRequiredOnEntities(LintRule):
    """Types used in unions or implementing interfaces must have ``@key``.

    In Apollo Federation, any type that participates in a union or
    implements an interface that could be used for cross-subgraph data
    resolution should carry a ``@key`` directive.

    This rule collects all object types that appear as union members
    or implement any interface, and checks that they have ``@key``.
    """

    name = "federation-key-required-on-entities"
    description = (
        "Types used in unions or implementing interfaces must have @key "
        "for federation."
    )

    def check(self, document: DocumentNode) -> list[LintViolation]:
        """Check that entity-like types have @key."""
        violations: list[LintViolation] = []

        # Collect object type definitions by name
        object_types: dict[str, gql_ast.ObjectTypeDefinitionNode] = {}
        union_member_names: set[str] = set()
        interface_implementor_names: set[str] = set()

        for defn in document.definitions:
            if isinstance(defn, gql_ast.ObjectTypeDefinitionNode):
                object_types[defn.name.value] = defn
                # Types that implement any interface
                if defn.interfaces:
                    interface_implementor_names.add(defn.name.value)
            elif isinstance(defn, gql_ast.UnionTypeDefinitionNode):
                for member in defn.types or ():
                    union_member_names.add(member.name.value)

        # Types that need @key: union members + interface implementors
        entity_candidates = union_member_names | interface_implementor_names

        for type_name in sorted(entity_candidates):
            node = object_types.get(type_name)
            if node is None:
                continue
            if not _has_key_directive(node):
                violations.append(
                    self._violation(
                        (
                            f"Type '{type_name}' is used in a union or "
                            f"implements an interface but is missing "
                            f"the @key directive."
                        ),
                        path=type_name,
                        node=node,
                    )
                )

        return violations
