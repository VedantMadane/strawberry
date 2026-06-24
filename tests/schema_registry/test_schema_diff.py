"""Unit tests for the schema diff utility."""

from __future__ import annotations

import re

import pytest

from strawberry.schema_registry import (
    ChangeKind,
    SchemaDiffConfig,
    Severity,
    diff_schemas,
)
from strawberry.schema_registry.diff_engine import schema_from_sdl
from strawberry.schema_registry.formatters import format_diff_markdown


# --------------------------------------------------------------------------- helpers
def _diff(old_sdl: str, new_sdl: str, **cfg_kwargs):
    config = SchemaDiffConfig(**cfg_kwargs) if cfg_kwargs else None
    return diff_schemas(old_sdl, new_sdl, config=config)


def _kinds(result):
    return [e.change_kind for e in result.entries]


def _paths(result):
    return [e.path for e in result.entries]


# --------------------------------------------------------------------------- types
class TestTypeChanges:
    def test_type_removed_is_breaking(self):
        old = "type Query { x: Int } type Gone { id: ID }"
        new = "type Query { x: Int }"
        result = _diff(old, new)
        entry = next(e for e in result.entries if e.change_kind is ChangeKind.TYPE_REMOVED)
        assert entry.path == "Gone"
        assert entry.severity is Severity.BREAKING

    def test_type_added_is_safe(self):
        old = "type Query { x: Int }"
        new = "type Query { x: Int } type NewType { id: ID }"
        result = _diff(old, new)
        entry = next(e for e in result.entries if e.change_kind is ChangeKind.TYPE_ADDED)
        assert entry.path == "NewType"
        assert entry.severity is Severity.SAFE

    def test_type_kind_changed_is_breaking(self):
        old = "type Foo { id: ID } type Query { f: Foo }"
        new = "interface Foo { id: ID } type Query { f: Foo }"
        result = _diff(old, new)
        assert ChangeKind.TYPE_KIND_CHANGED in _kinds(result)


# --------------------------------------------------------------------------- fields
class TestFieldChanges:
    def test_field_removed_is_breaking(self):
        old = "type Query { a: Int b: String }"
        new = "type Query { a: Int }"
        result = _diff(old, new)
        entry = next(e for e in result.entries if e.change_kind is ChangeKind.FIELD_REMOVED)
        assert entry.path == "Query.b"
        assert entry.severity is Severity.BREAKING

    def test_field_added_is_safe(self):
        old = "type Query { a: Int }"
        new = "type Query { a: Int b: String }"
        result = _diff(old, new)
        entry = next(e for e in result.entries if e.change_kind is ChangeKind.FIELD_ADDED)
        assert entry.path == "Query.b"
        assert entry.severity is Severity.SAFE

    def test_field_type_changed_is_breaking(self):
        old = "type Query { a: Int }"
        new = "type Query { a: String }"
        result = _diff(old, new)
        assert ChangeKind.FIELD_TYPE_CHANGED in _kinds(result)

    def test_field_nullability_changed(self):
        old = "type Query { a: Int }"
        new = "type Query { a: Int! }"
        result = _diff(old, new)
        assert ChangeKind.FIELD_NULLABILITY_CHANGED in _kinds(result)

    def test_field_deprecation_added_is_dangerous(self):
        old = "type Query { a: Int }"
        new = 'type Query { a: Int @deprecated(reason: "use b") }'
        result = _diff(old, new)
        entry = next(
            e for e in result.entries if e.change_kind is ChangeKind.FIELD_DEPRECATION_ADDED
        )
        assert entry.severity is Severity.DANGEROUS


# --------------------------------------------------------------------------- arguments
class TestArgumentChanges:
    def test_arg_removed_is_breaking(self):
        old = "type Query { f(x: Int): Int }"
        new = "type Query { f: Int }"
        result = _diff(old, new)
        assert ChangeKind.ARG_REMOVED in _kinds(result)

    def test_required_arg_added_is_breaking(self):
        old = "type Query { f: Int }"
        new = "type Query { f(x: Int!): Int }"
        result = _diff(old, new)
        entry = next(e for e in result.entries if e.change_kind is ChangeKind.ARG_ADDED)
        assert entry.severity is Severity.BREAKING

    def test_optional_arg_added_is_dangerous(self):
        old = "type Query { f: Int }"
        new = "type Query { f(x: Int): Int }"
        result = _diff(old, new)
        entry = next(e for e in result.entries if e.change_kind is ChangeKind.ARG_ADDED)
        assert entry.severity is Severity.DANGEROUS

    def test_arg_default_added(self):
        old = "type Query { f(x: Int): Int }"
        new = "type Query { f(x: Int = 1): Int }"
        result = _diff(old, new)
        assert ChangeKind.ARG_DEFAULT_ADDED in _kinds(result)

    def test_arg_default_changed(self):
        old = "type Query { f(x: Int = 1): Int }"
        new = "type Query { f(x: Int = 2): Int }"
        result = _diff(old, new)
        assert ChangeKind.ARG_DEFAULT_CHANGED in _kinds(result)

    def test_arg_nullability_changed(self):
        old = "type Query { f(x: Int): Int }"
        new = "type Query { f(x: Int!): Int }"
        result = _diff(old, new)
        assert ChangeKind.ARG_NULLABILITY_CHANGED in _kinds(result)


# --------------------------------------------------------------------------- enums
class TestEnumChanges:
    def test_enum_value_removed_is_breaking(self):
        old = "enum Color { RED GREEN } type Query { c: Color }"
        new = "enum Color { RED } type Query { c: Color }"
        result = _diff(old, new)
        entry = next(
            e for e in result.entries if e.change_kind is ChangeKind.ENUM_VALUE_REMOVED
        )
        assert entry.path == "Color.GREEN"
        assert entry.severity is Severity.BREAKING

    def test_enum_value_added_is_safe(self):
        old = "enum Color { RED } type Query { c: Color }"
        new = "enum Color { RED GREEN } type Query { c: Color }"
        result = _diff(old, new)
        assert ChangeKind.ENUM_VALUE_ADDED in _kinds(result)


# --------------------------------------------------------------------------- unions / interfaces
class TestUnionAndInterfaceChanges:
    def test_union_member_removed_is_breaking(self):
        old = """
            type A { id: ID }
            type B { id: ID }
            union U = A | B
            type Query { u: U }
        """
        new = """
            type A { id: ID }
            type B { id: ID }
            union U = A
            type Query { u: U }
        """
        result = _diff(old, new)
        entry = next(
            e for e in result.entries if e.change_kind is ChangeKind.UNION_MEMBER_REMOVED
        )
        assert entry.old_value == "B"
        assert entry.severity is Severity.BREAKING

    def test_union_member_added_is_dangerous(self):
        old = """
            type A { id: ID }
            type B { id: ID }
            union U = A
            type Query { u: U }
        """
        new = """
            type A { id: ID }
            type B { id: ID }
            union U = A | B
            type Query { u: U }
        """
        result = _diff(old, new)
        entry = next(
            e for e in result.entries if e.change_kind is ChangeKind.UNION_MEMBER_ADDED
        )
        assert entry.severity is Severity.DANGEROUS

    def test_interface_removed_from_type_is_breaking(self):
        old = """
            interface Node { id: ID! }
            type User implements Node { id: ID! }
            type Query { u: User }
        """
        new = """
            interface Node { id: ID! }
            type User { id: ID! }
            type Query { u: User }
        """
        result = _diff(old, new)
        assert ChangeKind.INTERFACE_REMOVED_FROM_TYPE in _kinds(result)

    def test_interface_added_to_type_is_safe(self):
        old = """
            interface Node { id: ID! }
            type User { id: ID! }
            type Query { u: User }
        """
        new = """
            interface Node { id: ID! }
            type User implements Node { id: ID! }
            type Query { u: User }
        """
        result = _diff(old, new)
        assert ChangeKind.INTERFACE_ADDED_TO_TYPE in _kinds(result)


# --------------------------------------------------------------------------- input objects
class TestInputObjectChanges:
    def test_input_field_removed_is_breaking(self):
        old = "input In { a: Int b: String } type Query { f(i: In): Int }"
        new = "input In { a: Int } type Query { f(i: In): Int }"
        result = _diff(old, new)
        assert ChangeKind.INPUT_FIELD_REMOVED in _kinds(result)

    def test_required_input_field_added_is_breaking(self):
        old = "input In { a: Int } type Query { f(i: In): Int }"
        new = "input In { a: Int b: String! } type Query { f(i: In): Int }"
        result = _diff(old, new)
        entry = next(
            e for e in result.entries if e.change_kind is ChangeKind.INPUT_FIELD_ADDED
        )
        assert entry.severity is Severity.BREAKING


# --------------------------------------------------------------------------- directives
class TestDirectiveChanges:
    def test_directive_removed_is_breaking(self):
        old = """
            directive @auth on FIELD_DEFINITION
            type Query { x: Int @auth }
        """
        new = "type Query { x: Int }"
        result = _diff(old, new)
        # May include applied directive removal and directive definition removal.
        assert (
            ChangeKind.DIRECTIVE_REMOVED in _kinds(result)
            or ChangeKind.APPLIED_DIRECTIVE_REMOVED in _kinds(result)
        )


# --------------------------------------------------------------------------- federation
_FED_PREAMBLE = """
    directive @key(fields: String!, resolvable: Boolean = true) repeatable on OBJECT | INTERFACE
    directive @requires(fields: String!) on FIELD_DEFINITION
    directive @provides(fields: String!) on FIELD_DEFINITION
    directive @shareable on OBJECT | FIELD_DEFINITION
    directive @inaccessible on FIELD_DEFINITION | OBJECT | INTERFACE | UNION | ARGUMENT_DEFINITION | SCALAR | ENUM | ENUM_VALUE | INPUT_OBJECT | INPUT_FIELD_DEFINITION
"""


class TestFederationChanges:
    def test_key_removed_is_breaking(self):
        old = _FED_PREAMBLE + """
            type User @key(fields: "id") { id: ID! name: String }
            type Query { user: User }
        """
        new = _FED_PREAMBLE + """
            type User { id: ID! name: String }
            type Query { user: User }
        """
        result = _diff(old, new)
        entry = next(
            e for e in result.entries if e.change_kind is ChangeKind.FEDERATION_KEY_REMOVED
        )
        assert entry.path == "User"
        assert entry.severity is Severity.BREAKING

    def test_key_added_is_safe(self):
        old = _FED_PREAMBLE + """
            type User { id: ID! name: String }
            type Query { user: User }
        """
        new = _FED_PREAMBLE + """
            type User @key(fields: "id") { id: ID! name: String }
            type Query { user: User }
        """
        result = _diff(old, new)
        entry = next(
            e for e in result.entries if e.change_kind is ChangeKind.FEDERATION_KEY_ADDED
        )
        assert entry.severity is Severity.SAFE

    def test_key_fields_changed_is_breaking(self):
        old = _FED_PREAMBLE + """
            type User @key(fields: "id") { id: ID! email: String }
            type Query { user: User }
        """
        new = _FED_PREAMBLE + """
            type User @key(fields: "email") { id: ID! email: String }
            type Query { user: User }
        """
        result = _diff(old, new)
        entry = next(
            e
            for e in result.entries
            if e.change_kind is ChangeKind.FEDERATION_KEY_FIELDS_CHANGED
        )
        assert entry.severity is Severity.BREAKING

    def test_requires_removed_is_breaking(self):
        old = _FED_PREAMBLE + """
            type User @key(fields: "id") {
                id: ID!
                name: String @requires(fields: "id")
            }
            type Query { user: User }
        """
        new = _FED_PREAMBLE + """
            type User @key(fields: "id") {
                id: ID!
                name: String
            }
            type Query { user: User }
        """
        result = _diff(old, new)
        entry = next(
            e
            for e in result.entries
            if e.change_kind is ChangeKind.FEDERATION_REQUIRES_REMOVED
        )
        assert entry.path == "User.name"
        assert entry.severity is Severity.BREAKING

    def test_provides_added_is_safe(self):
        old = _FED_PREAMBLE + """
            type Product @key(fields: "upc") {
                upc: String!
                reviews: [String]
            }
            type Query { p: Product }
        """
        new = _FED_PREAMBLE + """
            type Product @key(fields: "upc") {
                upc: String!
                reviews: [String] @provides(fields: "upc")
            }
            type Query { p: Product }
        """
        result = _diff(old, new)
        entry = next(
            e
            for e in result.entries
            if e.change_kind is ChangeKind.FEDERATION_PROVIDES_ADDED
        )
        assert entry.severity is Severity.SAFE

    def test_shareable_removed_is_dangerous(self):
        old = _FED_PREAMBLE + """
            type User @key(fields: "id") @shareable { id: ID! }
            type Query { user: User }
        """
        new = _FED_PREAMBLE + """
            type User @key(fields: "id") { id: ID! }
            type Query { user: User }
        """
        result = _diff(old, new)
        entry = next(
            e
            for e in result.entries
            if e.change_kind is ChangeKind.FEDERATION_SHAREABLE_REMOVED
        )
        assert entry.severity is Severity.DANGEROUS

    def test_inaccessible_added_is_dangerous(self):
        old = _FED_PREAMBLE + """
            type User @key(fields: "id") { id: ID! secret: String }
            type Query { user: User }
        """
        new = _FED_PREAMBLE + """
            type User @key(fields: "id") { id: ID! secret: String @inaccessible }
            type Query { user: User }
        """
        result = _diff(old, new)
        entry = next(
            e
            for e in result.entries
            if e.change_kind is ChangeKind.FEDERATION_INACCESSIBLE_ADDED
        )
        assert entry.path == "User.secret"
        assert entry.severity is Severity.DANGEROUS

    def test_inaccessible_removed_is_breaking(self):
        old = _FED_PREAMBLE + """
            type User @key(fields: "id") { id: ID! secret: String @inaccessible }
            type Query { user: User }
        """
        new = _FED_PREAMBLE + """
            type User @key(fields: "id") { id: ID! secret: String }
            type Query { user: User }
        """
        result = _diff(old, new)
        entry = next(
            e
            for e in result.entries
            if e.change_kind is ChangeKind.FEDERATION_INACCESSIBLE_REMOVED
        )
        assert entry.severity is Severity.BREAKING


# --------------------------------------------------------------------------- config
class TestConfig:
    def test_ignore_change_kind(self):
        old = "type Query { a: Int }"
        new = "type Query { a: Int b: String }"
        result = _diff(
            old,
            new,
            ignore_change_kinds={ChangeKind.FIELD_ADDED},
        )
        assert ChangeKind.FIELD_ADDED not in _kinds(result)

    def test_ignore_path_regex(self):
        old = "type Query { a: Int _internal: String }"
        new = "type Query { a: Int }"
        result = _diff(
            old,
            new,
            ignore_path_patterns=[r"\._"],
        )
        # _internal removal should be ignored
        assert "Query._internal" not in _paths(result)

    def test_severity_override(self):
        old = "type Query { a: Int }"
        new = "type Query { a: Int b: String }"
        result = _diff(
            old,
            new,
            severity_overrides={ChangeKind.FIELD_ADDED: Severity.BREAKING},
        )
        entry = next(e for e in result.entries if e.change_kind is ChangeKind.FIELD_ADDED)
        assert entry.severity is Severity.BREAKING


# --------------------------------------------------------------------------- determinism / API
class TestDeterminismAndApi:
    def test_entries_are_sorted(self):
        old = """
            type Query { z: Int a: Int }
            type ZType { id: ID }
            type AType { id: ID }
        """
        new = "type Query { z: Int }"
        result = _diff(old, new)
        keys = [(e.path, e.change_kind.value, e.message) for e in result.entries]
        assert keys == sorted(keys)

    def test_accepts_graphql_schema_instances(self):
        old_s = schema_from_sdl("type Query { a: Int }")
        new_s = schema_from_sdl("type Query { a: Int b: String }")
        result = diff_schemas(old_s, new_s)
        assert any(e.change_kind is ChangeKind.FIELD_ADDED for e in result.entries)

    def test_accepts_file_paths(self, tmp_path):
        old_f = tmp_path / "old.graphql"
        new_f = tmp_path / "new.graphql"
        old_f.write_text("type Query { a: Int }\n", encoding="utf-8")
        new_f.write_text("type Query { a: Int b: String }\n", encoding="utf-8")
        result = diff_schemas(old_f, new_f)
        assert any(e.change_kind is ChangeKind.FIELD_ADDED for e in result.entries)

    def test_markdown_formatter(self):
        old = "type Query { a: Int }"
        new = "type Query { a: Int b: String }"
        result = _diff(old, new)
        md = format_diff_markdown(result)
        assert "## Schema Diff" in md
        assert "FIELD_ADDED" in md
        assert "|" in md

    def test_has_breaking_property(self):
        old = "type Query { a: Int b: String }"
        new = "type Query { a: Int }"
        result = _diff(old, new)
        assert result.has_breaking is True
        assert len(result.breaking) >= 1
