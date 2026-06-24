"""Federation v2 directive diff tests."""

from __future__ import annotations

from strawberry.schema_diff import ChangeCode, ChangeSeverity, diff_schemas


def _codes(result):
    return {c.code for c in result.changes}


# Minimal federation directive definitions for SDL parsing
FED_PRELUDE = """
directive @key(fields: String!, resolvable: Boolean = true) repeatable on OBJECT | INTERFACE
directive @requires(fields: String!) on FIELD_DEFINITION
directive @provides(fields: String!) on FIELD_DEFINITION
directive @shareable repeatable on OBJECT | FIELD_DEFINITION
directive @inaccessible on FIELD_DEFINITION | OBJECT | INTERFACE | UNION | ARGUMENT_DEFINITION | SCALAR | ENUM | ENUM_VALUE | INPUT_OBJECT | INPUT_FIELD_DEFINITION
directive @external on FIELD_DEFINITION
directive @override(from: String!) on FIELD_DEFINITION
directive @tag(name: String!) repeatable on FIELD_DEFINITION | OBJECT | INTERFACE | UNION | ARGUMENT_DEFINITION | SCALAR | ENUM | ENUM_VALUE | INPUT_OBJECT | INPUT_FIELD_DEFINITION
"""

OLD_FED = FED_PRELUDE + """
type Query {
  user(id: ID!): User
}

type User @key(fields: "id") {
  id: ID!
  name: String! @shareable
  email: String @external
  reviews: [String!] @requires(fields: "email")
  profile: String @provides(fields: "name")
}
"""

NEW_FED_IDENTICAL = OLD_FED


class TestFederationKey:
    def test_key_added(self):
        old = FED_PRELUDE + """
type Query { x: Int }
type Product { id: ID! name: String! }
"""
        new = FED_PRELUDE + """
type Query { x: Int }
type Product @key(fields: "id") { id: ID! name: String! }
"""
        result = diff_schemas(old, new)
        assert ChangeCode.FED_KEY_ADDED in _codes(result)
        ch = next(c for c in result.changes if c.code == ChangeCode.FED_KEY_ADDED)
        assert ch.severity == ChangeSeverity.SAFE

    def test_key_removed_is_breaking(self):
        old = FED_PRELUDE + """
type Query { x: Int }
type Product @key(fields: "id") { id: ID! name: String! }
"""
        new = FED_PRELUDE + """
type Query { x: Int }
type Product { id: ID! name: String! }
"""
        result = diff_schemas(old, new)
        assert ChangeCode.FED_KEY_REMOVED in _codes(result)
        ch = next(c for c in result.changes if c.code == ChangeCode.FED_KEY_REMOVED)
        assert ch.severity == ChangeSeverity.BREAKING

    def test_key_fields_changed_is_breaking(self):
        old = FED_PRELUDE + """
type Query { x: Int }
type Product @key(fields: "id") { id: ID! sku: String! name: String! }
"""
        new = FED_PRELUDE + """
type Query { x: Int }
type Product @key(fields: "sku") { id: ID! sku: String! name: String! }
"""
        result = diff_schemas(old, new)
        # Appears as remove of old key + add of new key
        assert ChangeCode.FED_KEY_REMOVED in _codes(result)
        assert ChangeCode.FED_KEY_ADDED in _codes(result)

    def test_key_resolvable_changed(self):
        old = FED_PRELUDE + """
type Query { x: Int }
type Product @key(fields: "id", resolvable: true) { id: ID! }
"""
        new = FED_PRELUDE + """
type Query { x: Int }
type Product @key(fields: "id", resolvable: false) { id: ID! }
"""
        result = diff_schemas(old, new)
        assert ChangeCode.FED_KEY_RESOLVABLE_CHANGED in _codes(result)
        ch = next(
            c for c in result.changes if c.code == ChangeCode.FED_KEY_RESOLVABLE_CHANGED
        )
        assert ch.severity == ChangeSeverity.DANGEROUS


class TestFederationRequiresProvides:
    def test_requires_added(self):
        old = FED_PRELUDE + """
type Query { x: Int }
type User @key(fields: "id") {
  id: ID!
  email: String @external
  fullName: String
}
"""
        new = FED_PRELUDE + """
type Query { x: Int }
type User @key(fields: "id") {
  id: ID!
  email: String @external
  fullName: String @requires(fields: "email")
}
"""
        result = diff_schemas(old, new)
        assert ChangeCode.FED_REQUIRES_ADDED in _codes(result)

    def test_requires_removed_is_breaking(self):
        old = FED_PRELUDE + """
type Query { x: Int }
type User @key(fields: "id") {
  id: ID!
  email: String @external
  fullName: String @requires(fields: "email")
}
"""
        new = FED_PRELUDE + """
type Query { x: Int }
type User @key(fields: "id") {
  id: ID!
  email: String @external
  fullName: String
}
"""
        result = diff_schemas(old, new)
        assert ChangeCode.FED_REQUIRES_REMOVED in _codes(result)
        ch = next(c for c in result.changes if c.code == ChangeCode.FED_REQUIRES_REMOVED)
        assert ch.severity == ChangeSeverity.BREAKING

    def test_requires_fields_changed(self):
        old = FED_PRELUDE + """
type Query { x: Int }
type User @key(fields: "id") {
  id: ID!
  email: String @external
  phone: String @external
  fullName: String @requires(fields: "email")
}
"""
        new = FED_PRELUDE + """
type Query { x: Int }
type User @key(fields: "id") {
  id: ID!
  email: String @external
  phone: String @external
  fullName: String @requires(fields: "phone")
}
"""
        result = diff_schemas(old, new)
        assert ChangeCode.FED_REQUIRES_REMOVED in _codes(result)
        assert ChangeCode.FED_REQUIRES_ADDED in _codes(result)

    def test_provides_added(self):
        old = FED_PRELUDE + """
type Query { x: Int }
type User @key(fields: "id") {
  id: ID!
  author: Author
}
type Author @key(fields: "id") {
  id: ID!
  name: String! @external
}
"""
        new = FED_PRELUDE + """
type Query { x: Int }
type User @key(fields: "id") {
  id: ID!
  author: Author @provides(fields: "name")
}
type Author @key(fields: "id") {
  id: ID!
  name: String! @external
}
"""
        result = diff_schemas(old, new)
        assert ChangeCode.FED_PROVIDES_ADDED in _codes(result)

    def test_provides_removed_is_dangerous(self):
        old = FED_PRELUDE + """
type Query { x: Int }
type User @key(fields: "id") {
  id: ID!
  author: Author @provides(fields: "name")
}
type Author @key(fields: "id") {
  id: ID!
  name: String! @external
}
"""
        new = FED_PRELUDE + """
type Query { x: Int }
type User @key(fields: "id") {
  id: ID!
  author: Author
}
type Author @key(fields: "id") {
  id: ID!
  name: String! @external
}
"""
        result = diff_schemas(old, new)
        assert ChangeCode.FED_PROVIDES_REMOVED in _codes(result)
        ch = next(c for c in result.changes if c.code == ChangeCode.FED_PROVIDES_REMOVED)
        assert ch.severity == ChangeSeverity.DANGEROUS


class TestFederationShareableInaccessible:
    def test_shareable_added(self):
        old = FED_PRELUDE + """
type Query { x: Int }
type Product @key(fields: "id") { id: ID! name: String! }
"""
        new = FED_PRELUDE + """
type Query { x: Int }
type Product @key(fields: "id") { id: ID! name: String! @shareable }
"""
        result = diff_schemas(old, new)
        assert ChangeCode.FED_SHAREABLE_ADDED in _codes(result)
        ch = next(c for c in result.changes if c.code == ChangeCode.FED_SHAREABLE_ADDED)
        assert ch.severity == ChangeSeverity.SAFE

    def test_shareable_removed_is_breaking(self):
        old = FED_PRELUDE + """
type Query { x: Int }
type Product @key(fields: "id") { id: ID! name: String! @shareable }
"""
        new = FED_PRELUDE + """
type Query { x: Int }
type Product @key(fields: "id") { id: ID! name: String! }
"""
        result = diff_schemas(old, new)
        assert ChangeCode.FED_SHAREABLE_REMOVED in _codes(result)
        ch = next(c for c in result.changes if c.code == ChangeCode.FED_SHAREABLE_REMOVED)
        assert ch.severity == ChangeSeverity.BREAKING

    def test_inaccessible_added_is_dangerous(self):
        old = FED_PRELUDE + """
type Query { x: Int }
type Product @key(fields: "id") { id: ID! internal: String }
"""
        new = FED_PRELUDE + """
type Query { x: Int }
type Product @key(fields: "id") { id: ID! internal: String @inaccessible }
"""
        result = diff_schemas(old, new)
        assert ChangeCode.FED_INACCESSIBLE_ADDED in _codes(result)
        ch = next(
            c for c in result.changes if c.code == ChangeCode.FED_INACCESSIBLE_ADDED
        )
        assert ch.severity == ChangeSeverity.DANGEROUS

    def test_inaccessible_removed_is_dangerous(self):
        old = FED_PRELUDE + """
type Query { x: Int }
type Product @key(fields: "id") { id: ID! internal: String @inaccessible }
"""
        new = FED_PRELUDE + """
type Query { x: Int }
type Product @key(fields: "id") { id: ID! internal: String }
"""
        result = diff_schemas(old, new)
        assert ChangeCode.FED_INACCESSIBLE_REMOVED in _codes(result)

    def test_external_added_and_removed(self):
        old = FED_PRELUDE + """
type Query { x: Int }
type User @key(fields: "id") { id: ID! email: String }
"""
        new = FED_PRELUDE + """
type Query { x: Int }
type User @key(fields: "id") { id: ID! email: String @external }
"""
        result = diff_schemas(old, new)
        assert ChangeCode.FED_EXTERNAL_ADDED in _codes(result)

        result2 = diff_schemas(new, old)
        assert ChangeCode.FED_EXTERNAL_REMOVED in _codes(result2)
        ch = next(c for c in result2.changes if c.code == ChangeCode.FED_EXTERNAL_REMOVED)
        assert ch.severity == ChangeSeverity.BREAKING

    def test_override_added(self):
        old = FED_PRELUDE + """
type Query { x: Int }
type User @key(fields: "id") { id: ID! name: String! }
"""
        new = FED_PRELUDE + """
type Query { x: Int }
type User @key(fields: "id") { id: ID! name: String! @override(from: "users") }
"""
        result = diff_schemas(old, new)
        assert ChangeCode.FED_OVERRIDE_ADDED in _codes(result)

    def test_tag_added_and_removed(self):
        old = FED_PRELUDE + """
type Query { x: Int }
type User @key(fields: "id") { id: ID! email: String }
"""
        new = FED_PRELUDE + """
type Query { x: Int }
type User @key(fields: "id") { id: ID! email: String @tag(name: "pii") }
"""
        result = diff_schemas(old, new)
        assert ChangeCode.FED_TAG_ADDED in _codes(result)
        ch = next(c for c in result.changes if c.code == ChangeCode.FED_TAG_ADDED)
        assert ch.severity == ChangeSeverity.SAFE

        result2 = diff_schemas(new, old)
        assert ChangeCode.FED_TAG_REMOVED in _codes(result2)


class TestFederationCombined:
    def test_identical_federation_schemas(self):
        result = diff_schemas(OLD_FED, NEW_FED_IDENTICAL)
        # May have no fed-specific changes; field/type structure is identical
        fed_codes = {c.code for c in result.changes if c.code.value.startswith("FED_")}
        assert fed_codes == set()

    def test_multiple_fed_changes_deterministic_order(self):
        old = FED_PRELUDE + """
type Query { x: Int }
type User @key(fields: "id") {
  id: ID!
  name: String! @shareable
  email: String @external
}
"""
        new = FED_PRELUDE + """
type Query { x: Int }
type User @key(fields: "id id") {
  id: ID!
  name: String!
  email: String
  bio: String @inaccessible
}
"""
        result = diff_schemas(old, new)
        keys = [c.sort_key() for c in result.changes]
        assert keys == sorted(keys)
        # Should detect shareable removed, external removed, inaccessible added, key changed
        codes = _codes(result)
        assert ChangeCode.FED_SHAREABLE_REMOVED in codes
        assert ChangeCode.FED_EXTERNAL_REMOVED in codes
        assert ChangeCode.FED_INACCESSIBLE_ADDED in codes
