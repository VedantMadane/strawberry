"""Basic schema diff tests covering core change categories."""

from __future__ import annotations

import strawberry
from strawberry.schema_diff import (
    ChangeCode,
    ChangeSeverity,
    SchemaDiffConfig,
    diff_schemas,
)
from strawberry.schema_diff.report import format_markdown, format_terminal


def _codes(result):
    return {c.code for c in result.changes}


def _codes_for_path(result, path_substr: str):
    return {c.code for c in result.changes if path_substr in c.path}


OLD_SDL = """
type Query {
  user(id: ID!): User
  users: [User!]!
}

type User {
  id: ID!
  name: String!
  email: String
}

type Post {
  id: ID!
  title: String!
}

enum Role {
  ADMIN
  USER
}

input CreateUserInput {
  name: String!
  email: String
}

union SearchResult = User | Post

interface Node {
  id: ID!
}

type Comment implements Node {
  id: ID!
  body: String!
}
"""

NEW_SDL_IDENTICAL = OLD_SDL


class TestIdenticalSchemas:
    def test_no_changes_sdl(self):
        result = diff_schemas(OLD_SDL, NEW_SDL_IDENTICAL)
        assert result.changes == []
        assert not result.has_breaking
        assert result.summary()["total"] == 0

    def test_no_changes_strawberry_schema(self):
        @strawberry.type
        class Query:
            hello: str = "world"

        schema = strawberry.Schema(query=Query)
        result = diff_schemas(schema, schema)
        assert result.changes == []


class TestTypeChanges:
    def test_type_removed(self):
        new = OLD_SDL.replace(
            """
type Post {
  id: ID!
  title: String!
}
""",
            "",
        ).replace("union SearchResult = User | Post", "union SearchResult = User")
        result = diff_schemas(OLD_SDL, new)
        assert ChangeCode.TYPE_REMOVED in _codes(result)
        post_changes = [c for c in result.changes if c.path == "Post"]
        assert any(c.code == ChangeCode.TYPE_REMOVED for c in post_changes)
        assert any(c.severity == ChangeSeverity.BREAKING for c in post_changes)

    def test_type_added(self):
        new = OLD_SDL + """
type Tag {
  name: String!
}
"""
        result = diff_schemas(OLD_SDL, new)
        assert ChangeCode.TYPE_ADDED in _codes(result)
        tag = [c for c in result.changes if c.path == "Tag"]
        assert tag[0].severity == ChangeSeverity.SAFE

    def test_type_kind_changed(self):
        old = "type Query { x: Int }\ntype Foo { a: String }\n"
        new = "type Query { x: Int }\ninput Foo { a: String }\n"
        result = diff_schemas(old, new)
        assert ChangeCode.TYPE_KIND_CHANGED in _codes(result)


class TestFieldChanges:
    def test_field_removed_is_breaking(self):
        new = OLD_SDL.replace(
            "type User {\n  id: ID!\n  name: String!\n  email: String\n}",
            "type User {\n  id: ID!\n  name: String!\n}",
        )
        result = diff_schemas(OLD_SDL, new)
        assert ChangeCode.FIELD_REMOVED in _codes(result)
        ch = next(
            c for c in result.changes
            if c.code == ChangeCode.FIELD_REMOVED and "User.email" in c.path
        )
        assert ch.severity == ChangeSeverity.BREAKING
        assert "User.email" in ch.path

    def test_field_added_is_safe(self):
        new = OLD_SDL.replace(
            "type User {\n  id: ID!\n  name: String!\n  email: String\n}",
            "type User {\n  id: ID!\n  name: String!\n  email: String\n  age: Int\n}",
        )
        result = diff_schemas(OLD_SDL, new)
        assert ChangeCode.FIELD_ADDED in _codes(result)
        ch = next(c for c in result.changes if c.code == ChangeCode.FIELD_ADDED)
        assert ch.severity == ChangeSeverity.SAFE

    def test_field_made_nullable_is_dangerous(self):
        new = OLD_SDL.replace("  name: String!\n", "  name: String\n")
        result = diff_schemas(OLD_SDL, new)
        assert ChangeCode.FIELD_MADE_NULLABLE in _codes(result)
        ch = next(c for c in result.changes if c.code == ChangeCode.FIELD_MADE_NULLABLE)
        assert ch.severity == ChangeSeverity.DANGEROUS

    def test_field_made_non_null_is_breaking(self):
        new = OLD_SDL.replace("  email: String\n", "  email: String!\n")
        result = diff_schemas(OLD_SDL, new)
        assert ChangeCode.FIELD_MADE_NON_NULL in _codes(result)
        ch = next(c for c in result.changes if c.code == ChangeCode.FIELD_MADE_NON_NULL)
        assert ch.severity == ChangeSeverity.BREAKING

    def test_field_type_changed_is_breaking(self):
        new = OLD_SDL.replace("  email: String\n", "  email: Int\n")
        result = diff_schemas(OLD_SDL, new)
        assert ChangeCode.FIELD_TYPE_CHANGED in _codes(result)

    def test_field_deprecation_added(self):
        new = OLD_SDL.replace(
            "  email: String\n",
            '  email: String @deprecated(reason: "use contact")\n',
        )
        result = diff_schemas(OLD_SDL, new)
        assert ChangeCode.FIELD_DEPRECATION_ADDED in _codes(result)


class TestArgumentChanges:
    def test_arg_removed_is_breaking(self):
        new = OLD_SDL.replace("  user(id: ID!): User\n", "  user: User\n")
        result = diff_schemas(OLD_SDL, new)
        assert ChangeCode.ARG_REMOVED in _codes(result)

    def test_arg_added_optional_is_safe(self):
        new = OLD_SDL.replace(
            "  users: [User!]!\n",
            "  users(limit: Int): [User!]!\n",
        )
        result = diff_schemas(OLD_SDL, new)
        arg_added = [c for c in result.changes if c.code == ChangeCode.ARG_ADDED]
        assert arg_added
        assert all(c.severity == ChangeSeverity.SAFE for c in arg_added)

    def test_arg_added_required_is_breaking(self):
        new = OLD_SDL.replace(
            "  users: [User!]!\n",
            "  users(limit: Int!): [User!]!\n",
        )
        result = diff_schemas(OLD_SDL, new)
        arg_added = [c for c in result.changes if c.code == ChangeCode.ARG_ADDED]
        assert arg_added
        assert any(c.severity == ChangeSeverity.BREAKING for c in arg_added)

    def test_arg_default_added(self):
        old = "type Query { items(limit: Int): [String] }\n"
        new = "type Query { items(limit: Int = 10): [String] }\n"
        result = diff_schemas(old, new)
        assert ChangeCode.ARG_DEFAULT_ADDED in _codes(result)

    def test_arg_default_removed(self):
        old = "type Query { items(limit: Int = 10): [String] }\n"
        new = "type Query { items(limit: Int): [String] }\n"
        result = diff_schemas(old, new)
        assert ChangeCode.ARG_DEFAULT_REMOVED in _codes(result)
        ch = next(c for c in result.changes if c.code == ChangeCode.ARG_DEFAULT_REMOVED)
        assert ch.severity == ChangeSeverity.BREAKING

    def test_arg_default_changed(self):
        old = "type Query { items(limit: Int = 10): [String] }\n"
        new = "type Query { items(limit: Int = 20): [String] }\n"
        result = diff_schemas(old, new)
        assert ChangeCode.ARG_DEFAULT_CHANGED in _codes(result)

    def test_arg_made_non_null(self):
        old = "type Query { items(limit: Int): [String] }\n"
        new = "type Query { items(limit: Int!): [String] }\n"
        result = diff_schemas(old, new)
        assert ChangeCode.ARG_MADE_NON_NULL in _codes(result)


class TestEnumChanges:
    def test_enum_value_added(self):
        new = OLD_SDL.replace(
            "enum Role {\n  ADMIN\n  USER\n}",
            "enum Role {\n  ADMIN\n  USER\n  GUEST\n}",
        )
        result = diff_schemas(OLD_SDL, new)
        assert ChangeCode.ENUM_VALUE_ADDED in _codes(result)
        ch = next(c for c in result.changes if c.code == ChangeCode.ENUM_VALUE_ADDED)
        assert ch.severity == ChangeSeverity.SAFE

    def test_enum_value_removed_is_breaking(self):
        new = OLD_SDL.replace(
            "enum Role {\n  ADMIN\n  USER\n}",
            "enum Role {\n  ADMIN\n}",
        )
        result = diff_schemas(OLD_SDL, new)
        assert ChangeCode.ENUM_VALUE_REMOVED in _codes(result)
        ch = next(c for c in result.changes if c.code == ChangeCode.ENUM_VALUE_REMOVED)
        assert ch.severity == ChangeSeverity.BREAKING


class TestUnionAndInterfaceChanges:
    def test_union_member_added(self):
        new = OLD_SDL.replace(
            "union SearchResult = User | Post",
            "union SearchResult = User | Post | Comment",
        )
        result = diff_schemas(OLD_SDL, new)
        assert ChangeCode.UNION_MEMBER_ADDED in _codes(result)
        ch = next(c for c in result.changes if c.code == ChangeCode.UNION_MEMBER_ADDED)
        assert ch.severity == ChangeSeverity.DANGEROUS

    def test_union_member_removed(self):
        new = OLD_SDL.replace(
            "union SearchResult = User | Post",
            "union SearchResult = User",
        )
        result = diff_schemas(OLD_SDL, new)
        assert ChangeCode.UNION_MEMBER_REMOVED in _codes(result)

    def test_interface_added_to_object(self):
        new = OLD_SDL.replace(
            "type User {\n  id: ID!\n  name: String!\n  email: String\n}",
            "type User implements Node {\n  id: ID!\n  name: String!\n  email: String\n}",
        )
        result = diff_schemas(OLD_SDL, new)
        assert ChangeCode.INTERFACE_ADDED_TO_OBJECT in _codes(result)

    def test_interface_removed_from_object(self):
        new = OLD_SDL.replace(
            "type Comment implements Node {\n  id: ID!\n  body: String!\n}",
            "type Comment {\n  id: ID!\n  body: String!\n}",
        )
        result = diff_schemas(OLD_SDL, new)
        assert ChangeCode.INTERFACE_REMOVED_FROM_OBJECT in _codes(result)


class TestInputChanges:
    def test_input_field_added_optional(self):
        new = OLD_SDL.replace(
            "input CreateUserInput {\n  name: String!\n  email: String\n}",
            "input CreateUserInput {\n  name: String!\n  email: String\n  phone: String\n}",
        )
        result = diff_schemas(OLD_SDL, new)
        assert ChangeCode.FIELD_ADDED in _codes_for_path(result, "CreateUserInput")

    def test_input_field_added_required_is_breaking(self):
        new = OLD_SDL.replace(
            "input CreateUserInput {\n  name: String!\n  email: String\n}",
            "input CreateUserInput {\n  name: String!\n  email: String\n  phone: String!\n}",
        )
        result = diff_schemas(OLD_SDL, new)
        added = [
            c
            for c in result.changes
            if c.code == ChangeCode.FIELD_ADDED and "CreateUserInput.phone" in c.path
        ]
        assert added
        assert added[0].severity == ChangeSeverity.BREAKING


class TestDeterministicOrdering:
    def test_changes_are_sorted_by_severity_then_path(self):
        new = OLD_SDL.replace("  email: String\n", "  email: Int\n")
        new = new.replace(
            "enum Role {\n  ADMIN\n  USER\n}",
            "enum Role {\n  ADMIN\n  USER\n  GUEST\n}",
        )
        new = new + "\ntype Extra { x: Int }\n"
        result = diff_schemas(OLD_SDL, new)
        keys = [c.sort_key() for c in result.changes]
        assert keys == sorted(keys)

        # Breaking comes before safe
        severities = [c.severity for c in result.changes]
        if ChangeSeverity.BREAKING in severities and ChangeSeverity.SAFE in severities:
            first_breaking = severities.index(ChangeSeverity.BREAKING)
            # All breaking should come before safe
            for i, sev in enumerate(severities):
                if sev == ChangeSeverity.SAFE:
                    assert i > first_breaking or ChangeSeverity.BREAKING not in severities[:i]


class TestConfig:
    def test_ignore_codes(self):
        new = OLD_SDL.replace("  email: String\n", "")
        config = SchemaDiffConfig(ignore_codes={ChangeCode.FIELD_REMOVED})
        result = diff_schemas(OLD_SDL, new, config=config)
        assert ChangeCode.FIELD_REMOVED not in _codes(result)

    def test_ignore_field_patterns(self):
        old = "type Query { ok: Boolean\n  _internal: String\n}\n"
        new = "type Query { ok: Boolean\n}\n"
        config = SchemaDiffConfig(ignore_field_patterns=[r"\._"])
        result = diff_schemas(old, new, config=config)
        # _internal removal should be ignored
        assert not any("_internal" in c.path for c in result.changes)

    def test_ignore_type_patterns(self):
        new = OLD_SDL.replace(
            """
type Post {
  id: ID!
  title: String!
}
""",
            "",
        ).replace("union SearchResult = User | Post", "union SearchResult = User")
        config = SchemaDiffConfig(ignore_type_patterns=[r"^Post$"])
        result = diff_schemas(OLD_SDL, new, config=config)
        assert not any(c.path == "Post" for c in result.changes)

    def test_severity_override(self):
        new = OLD_SDL + "\ntype Tag { name: String! }\n"
        config = SchemaDiffConfig(
            severity_overrides={ChangeCode.TYPE_ADDED: ChangeSeverity.DANGEROUS}
        )
        result = diff_schemas(OLD_SDL, new, config=config)
        tag = next(c for c in result.changes if c.path == "Tag")
        assert tag.severity == ChangeSeverity.DANGEROUS

    def test_no_descriptions(self):
        old = '"""Old"""\ntype Query { x: Int }\n'
        new = '"""New"""\ntype Query { x: Int }\n'
        config = SchemaDiffConfig(include_descriptions=False)
        result = diff_schemas(old, new, config=config)
        assert ChangeCode.TYPE_DESCRIPTION_CHANGED not in _codes(result)


class TestReporting:
    def test_markdown_output(self):
        new = OLD_SDL.replace("  email: String\n", "")
        result = diff_schemas(OLD_SDL, new)
        md = format_markdown(result)
        assert "## Schema Diff" in md
        assert "FIELD_REMOVED" in md
        assert "| Severity |" in md

    def test_terminal_output_plain(self):
        new = OLD_SDL.replace("  email: String\n", "")
        result = diff_schemas(OLD_SDL, new)
        text = format_terminal(result, use_rich=False)
        assert "Schema Diff Summary" in text
        assert "FIELD_REMOVED" in text

    def test_to_dict(self):
        result = diff_schemas(OLD_SDL, OLD_SDL)
        d = result.to_dict()
        assert "summary" in d
        assert d["summary"]["total"] == 0
        assert d["has_breaking"] is False


class TestStrawberrySchemaInput:
    def test_diff_strawberry_schemas(self):
        @strawberry.type
        class Query:
            hello: str
            old_field: int

        s1 = strawberry.Schema(query=Query)

        @strawberry.type
        class Query2:
            hello: str
            new_field: str

        # Compare via SDL with consistent root type name
        old_sdl = """
type Query {
  hello: String!
  oldField: Int!
}
"""
        new_sdl = """
type Query {
  hello: String!
  newField: String!
}
"""
        result = diff_schemas(old_sdl, new_sdl)
        assert ChangeCode.FIELD_REMOVED in _codes(result)
        assert ChangeCode.FIELD_ADDED in _codes(result)

        # Also verify strawberry.Schema objects are accepted
        s2_sdl = s1.as_str()
        result2 = diff_schemas(s1, s2_sdl)
        assert result2.changes == []

    def test_mixed_sdl_and_strawberry(self):
        @strawberry.type
        class Query:
            hello: str

        schema = strawberry.Schema(query=Query)
        sdl = schema.as_str()
        result = diff_schemas(sdl, schema)
        assert result.changes == []
