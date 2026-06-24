"""AST / type-system aware schema diff engine.

Compares two GraphQL schemas using graphql-core's parsed type system rather
than plain-text SDL diffs, producing deterministically ordered ``DiffEntry``
records.
"""

from __future__ import annotations

from typing import Any, Iterable

from graphql import (
    GraphQLArgument,
    GraphQLDirective,
    GraphQLEnumType,
    GraphQLField,
    GraphQLInputField,
    GraphQLInputObjectType,
    GraphQLInterfaceType,
    GraphQLList,
    GraphQLNamedType,
    GraphQLNonNull,
    GraphQLObjectType,
    GraphQLScalarType,
    GraphQLSchema,
    GraphQLType,
    GraphQLUnionType,
    Undefined,
    build_ast_schema,
    parse,
)
from graphql.language.printer import print_ast
from graphql.type.directives import specified_directives

from strawberry.schema_registry.config import SchemaDiffConfig
from strawberry.schema_registry.types import (
    DEFAULT_SEVERITY,
    ChangeKind,
    DiffEntry,
    SchemaDiff,
    Severity,
)

# Built-in type names we never report as added/removed.
_BUILTIN_TYPE_NAMES = frozenset(
    {
        "String",
        "Int",
        "Float",
        "Boolean",
        "ID",
        "__Schema",
        "__Type",
        "__TypeKind",
        "__Field",
        "__InputValue",
        "__EnumValue",
        "__Directive",
        "__DirectiveLocation",
    }
)

_BUILTIN_DIRECTIVE_NAMES = frozenset(d.name for d in specified_directives)

# Federation directive names we special-case for severity / codes.
_FED_KEY = "key"
_FED_REQUIRES = "requires"
_FED_PROVIDES = "provides"
_FED_SHAREABLE = "shareable"
_FED_INACCESSIBLE = "inaccessible"
_FEDERATION_DIRECTIVES = frozenset(
    {_FED_KEY, _FED_REQUIRES, _FED_PROVIDES, _FED_SHAREABLE, _FED_INACCESSIBLE}
)


def _type_name(t: GraphQLType) -> str:
    """Render a GraphQL type reference (with list / non-null wrappers)."""
    if isinstance(t, GraphQLNonNull):
        return f"{_type_name(t.of_type)}!"
    if isinstance(t, GraphQLList):
        return f"[{_type_name(t.of_type)}]"
    return getattr(t, "name", str(t))


def _named_type(t: GraphQLType) -> GraphQLNamedType | None:
    while isinstance(t, (GraphQLNonNull, GraphQLList)):
        t = t.of_type  # type: ignore[assignment]
    if isinstance(t, GraphQLNamedType):
        return t
    return None


def _is_non_null(t: GraphQLType) -> bool:
    return isinstance(t, GraphQLNonNull)


def _unwrap_non_null(t: GraphQLType) -> GraphQLType:
    return t.of_type if isinstance(t, GraphQLNonNull) else t


def _default_value_str(value: Any) -> str | None:
    if value is None or value is Undefined:
        return None
    # graphql-core stores Python values; repr is stable enough for messages.
    return repr(value)


def _has_explicit_default(arg_or_field: Any) -> bool:
    """True when the definition carries an explicit default in the AST or value."""
    ast_node = getattr(arg_or_field, "ast_node", None)
    if ast_node is not None and getattr(ast_node, "default_value", None) is not None:
        return True
    value = getattr(arg_or_field, "default_value", Undefined)
    return value is not Undefined and value is not None


def _printed_default(arg_or_field: Any) -> str | None:
    ast_node = getattr(arg_or_field, "ast_node", None)
    if ast_node is not None and getattr(ast_node, "default_value", None) is not None:
        return print_ast(ast_node.default_value)
    value = getattr(arg_or_field, "default_value", Undefined)
    if value is Undefined or value is None:
        return None
    return repr(value)


def _is_required_input(arg_or_field: Any) -> bool:
    """Non-null type without an explicit default => required for callers."""
    gql_type = arg_or_field.type
    return isinstance(gql_type, GraphQLNonNull) and not _has_explicit_default(arg_or_field)


def _kind_label(t: GraphQLNamedType) -> str:
    if isinstance(t, GraphQLObjectType):
        return "OBJECT"
    if isinstance(t, GraphQLInterfaceType):
        return "INTERFACE"
    if isinstance(t, GraphQLUnionType):
        return "UNION"
    if isinstance(t, GraphQLEnumType):
        return "ENUM"
    if isinstance(t, GraphQLInputObjectType):
        return "INPUT_OBJECT"
    if isinstance(t, GraphQLScalarType):
        return "SCALAR"
    return type(t).__name__


class SchemaDiffEngine:
    """Compare two ``GraphQLSchema`` instances and emit structured diffs."""

    def __init__(self, config: SchemaDiffConfig | None = None) -> None:
        self.config = config or SchemaDiffConfig()
        self._entries: list[DiffEntry] = []

    # ------------------------------------------------------------------ public
    def diff(self, old: GraphQLSchema, new: GraphQLSchema) -> SchemaDiff:
        self._entries = []
        self._diff_types(old, new)
        self._diff_directives(old, new)
        # Deterministic ordering for CI stability.
        self._entries.sort(
            key=lambda e: (e.path, e.change_kind.value, e.message, e.severity.value)
        )
        return SchemaDiff(entries=list(self._entries))

    # --------------------------------------------------------------- recording
    def _add(
        self,
        change_kind: ChangeKind,
        path: str,
        message: str,
        *,
        severity: Severity | None = None,
        old_value: str | None = None,
        new_value: str | None = None,
    ) -> None:
        if self.config.should_ignore(change_kind, path):
            return
        default_sev = DEFAULT_SEVERITY.get(change_kind, Severity.SAFE)
        if severity is None:
            severity = default_sev
        severity = self.config.resolve_severity(change_kind, severity)
        self._entries.append(
            DiffEntry(
                change_kind=change_kind,
                severity=severity,
                path=path,
                message=message,
                old_value=old_value,
                new_value=new_value,
            )
        )

    # ------------------------------------------------------------------- types
    def _diff_types(self, old: GraphQLSchema, new: GraphQLSchema) -> None:
        old_types = {
            name: t
            for name, t in old.type_map.items()
            if name not in _BUILTIN_TYPE_NAMES and not name.startswith("__")
        }
        new_types = {
            name: t
            for name, t in new.type_map.items()
            if name not in _BUILTIN_TYPE_NAMES and not name.startswith("__")
        }

        for name in sorted(set(old_types) - set(new_types)):
            self._add(
                ChangeKind.TYPE_REMOVED,
                name,
                f"Type '{name}' was removed.",
                old_value=_kind_label(old_types[name]),
            )

        for name in sorted(set(new_types) - set(old_types)):
            self._add(
                ChangeKind.TYPE_ADDED,
                name,
                f"Type '{name}' was added.",
                new_value=_kind_label(new_types[name]),
            )

        for name in sorted(set(old_types) & set(new_types)):
            self._diff_named_type(name, old_types[name], new_types[name])

    def _diff_named_type(
        self, name: str, old_t: GraphQLNamedType, new_t: GraphQLNamedType
    ) -> None:
        old_kind = _kind_label(old_t)
        new_kind = _kind_label(new_t)
        if old_kind != new_kind:
            self._add(
                ChangeKind.TYPE_KIND_CHANGED,
                name,
                f"Type '{name}' changed kind from {old_kind} to {new_kind}.",
                old_value=old_kind,
                new_value=new_kind,
            )
            return  # further field-level comparison is meaningless

        old_desc = getattr(old_t, "description", None)
        new_desc = getattr(new_t, "description", None)
        if old_desc != new_desc:
            self._add(
                ChangeKind.TYPE_DESCRIPTION_CHANGED,
                name,
                f"Description of type '{name}' changed.",
                old_value=old_desc,
                new_value=new_desc,
            )

        # Applied directives on the type (federation keys live here).
        self._diff_applied_directives(name, old_t, new_t)

        if isinstance(old_t, GraphQLObjectType) and isinstance(new_t, GraphQLObjectType):
            self._diff_object_like(name, old_t, new_t)
            self._diff_interfaces(name, old_t, new_t)
        elif isinstance(old_t, GraphQLInterfaceType) and isinstance(
            new_t, GraphQLInterfaceType
        ):
            self._diff_object_like(name, old_t, new_t)
        elif isinstance(old_t, GraphQLUnionType) and isinstance(new_t, GraphQLUnionType):
            self._diff_union(name, old_t, new_t)
        elif isinstance(old_t, GraphQLEnumType) and isinstance(new_t, GraphQLEnumType):
            self._diff_enum(name, old_t, new_t)
        elif isinstance(old_t, GraphQLInputObjectType) and isinstance(
            new_t, GraphQLInputObjectType
        ):
            self._diff_input_object(name, old_t, new_t)

    # -------------------------------------------------------- object / iface
    def _diff_object_like(
        self,
        type_name: str,
        old_t: GraphQLObjectType | GraphQLInterfaceType,
        new_t: GraphQLObjectType | GraphQLInterfaceType,
    ) -> None:
        old_fields = old_t.fields
        new_fields = new_t.fields

        for fname in sorted(set(old_fields) - set(new_fields)):
            self._add(
                ChangeKind.FIELD_REMOVED,
                f"{type_name}.{fname}",
                f"Field '{type_name}.{fname}' was removed.",
                old_value=_type_name(old_fields[fname].type),
            )

        for fname in sorted(set(new_fields) - set(old_fields)):
            self._add(
                ChangeKind.FIELD_ADDED,
                f"{type_name}.{fname}",
                f"Field '{type_name}.{fname}' was added.",
                new_value=_type_name(new_fields[fname].type),
            )

        for fname in sorted(set(old_fields) & set(new_fields)):
            self._diff_field(
                f"{type_name}.{fname}", old_fields[fname], new_fields[fname]
            )

    def _diff_field(
        self, path: str, old_f: GraphQLField, new_f: GraphQLField
    ) -> None:
        old_type_s = _type_name(old_f.type)
        new_type_s = _type_name(new_f.type)

        if old_type_s != new_type_s:
            # Prefer a specific nullability code when only nullability flipped.
            old_inner = _unwrap_non_null(old_f.type)
            new_inner = _unwrap_non_null(new_f.type)
            only_nullability = (
                _type_name(old_inner) == _type_name(new_inner)
                and _is_non_null(old_f.type) != _is_non_null(new_f.type)
            )
            kind = (
                ChangeKind.FIELD_NULLABILITY_CHANGED
                if only_nullability
                else ChangeKind.FIELD_TYPE_CHANGED
            )
            self._add(
                kind,
                path,
                f"Field '{path}' type changed from '{old_type_s}' to '{new_type_s}'.",
                old_value=old_type_s,
                new_value=new_type_s,
            )

        if old_f.description != new_f.description:
            self._add(
                ChangeKind.FIELD_DESCRIPTION_CHANGED,
                path,
                f"Description of field '{path}' changed.",
                old_value=old_f.description,
                new_value=new_f.description,
            )

        old_dep = old_f.deprecation_reason
        new_dep = new_f.deprecation_reason
        if old_dep is None and new_dep is not None:
            self._add(
                ChangeKind.FIELD_DEPRECATION_ADDED,
                path,
                f"Field '{path}' was deprecated.",
                new_value=new_dep,
            )
        elif old_dep is not None and new_dep is None:
            self._add(
                ChangeKind.FIELD_DEPRECATION_REMOVED,
                path,
                f"Deprecation removed from field '{path}'.",
                old_value=old_dep,
            )
        elif old_dep != new_dep:
            self._add(
                ChangeKind.FIELD_DEPRECATION_REASON_CHANGED,
                path,
                f"Deprecation reason on field '{path}' changed.",
                old_value=old_dep,
                new_value=new_dep,
            )

        # Applied directives on the field (requires / provides / shareable / inaccessible).
        self._diff_applied_directives(path, old_f, new_f)

        self._diff_args(path, old_f.args, new_f.args)

    def _diff_args(
        self,
        field_path: str,
        old_args: dict[str, GraphQLArgument],
        new_args: dict[str, GraphQLArgument],
    ) -> None:
        for aname in sorted(set(old_args) - set(new_args)):
            self._add(
                ChangeKind.ARG_REMOVED,
                f"{field_path}({aname})",
                f"Argument '{aname}' was removed from '{field_path}'.",
                old_value=_type_name(old_args[aname].type),
            )

        for aname in sorted(set(new_args) - set(old_args)):
            arg = new_args[aname]
            # Required arg without default is breaking; optional is dangerous.
            sev = Severity.BREAKING if _is_required_input(arg) else Severity.DANGEROUS
            self._add(
                ChangeKind.ARG_ADDED,
                f"{field_path}({aname})",
                f"Argument '{aname}' was added to '{field_path}'.",
                severity=sev,
                new_value=_type_name(arg.type),
            )

        for aname in sorted(set(old_args) & set(new_args)):
            self._diff_arg(f"{field_path}({aname})", old_args[aname], new_args[aname])

    def _diff_arg(
        self, path: str, old_a: GraphQLArgument, new_a: GraphQLArgument
    ) -> None:
        old_type_s = _type_name(old_a.type)
        new_type_s = _type_name(new_a.type)
        if old_type_s != new_type_s:
            old_inner = _unwrap_non_null(old_a.type)
            new_inner = _unwrap_non_null(new_a.type)
            only_nullability = (
                _type_name(old_inner) == _type_name(new_inner)
                and _is_non_null(old_a.type) != _is_non_null(new_a.type)
            )
            kind = (
                ChangeKind.ARG_NULLABILITY_CHANGED
                if only_nullability
                else ChangeKind.ARG_TYPE_CHANGED
            )
            self._add(
                kind,
                path,
                f"Argument '{path}' type changed from '{old_type_s}' to '{new_type_s}'.",
                old_value=old_type_s,
                new_value=new_type_s,
            )

        old_has_default = _has_explicit_default(old_a)
        new_has_default = _has_explicit_default(new_a)
        old_def = _printed_default(old_a)
        new_def = _printed_default(new_a)

        if not old_has_default and new_has_default:
            self._add(
                ChangeKind.ARG_DEFAULT_ADDED,
                path,
                f"Default value added to argument '{path}'.",
                new_value=new_def,
            )
        elif old_has_default and not new_has_default:
            self._add(
                ChangeKind.ARG_DEFAULT_REMOVED,
                path,
                f"Default value removed from argument '{path}'.",
                old_value=old_def,
            )
        elif old_has_default and new_has_default and old_def != new_def:
            self._add(
                ChangeKind.ARG_DEFAULT_CHANGED,
                path,
                f"Default value of argument '{path}' changed.",
                old_value=old_def,
                new_value=new_def,
            )

        if old_a.description != new_a.description:
            self._add(
                ChangeKind.ARG_DESCRIPTION_CHANGED,
                path,
                f"Description of argument '{path}' changed.",
                old_value=old_a.description,
                new_value=new_a.description,
            )

    # ------------------------------------------------------------- interfaces
    def _diff_interfaces(
        self, type_name: str, old_t: GraphQLObjectType, new_t: GraphQLObjectType
    ) -> None:
        old_ifaces = {i.name for i in old_t.interfaces}
        new_ifaces = {i.name for i in new_t.interfaces}

        for iface in sorted(new_ifaces - old_ifaces):
            self._add(
                ChangeKind.INTERFACE_ADDED_TO_TYPE,
                type_name,
                f"Type '{type_name}' now implements interface '{iface}'.",
                new_value=iface,
            )
        for iface in sorted(old_ifaces - new_ifaces):
            self._add(
                ChangeKind.INTERFACE_REMOVED_FROM_TYPE,
                type_name,
                f"Type '{type_name}' no longer implements interface '{iface}'.",
                old_value=iface,
            )

    # ----------------------------------------------------------------- unions
    def _diff_union(
        self, name: str, old_t: GraphQLUnionType, new_t: GraphQLUnionType
    ) -> None:
        old_members = {t.name for t in old_t.types}
        new_members = {t.name for t in new_t.types}

        for member in sorted(new_members - old_members):
            self._add(
                ChangeKind.UNION_MEMBER_ADDED,
                name,
                f"Union member '{member}' was added to '{name}'.",
                new_value=member,
            )
        for member in sorted(old_members - new_members):
            self._add(
                ChangeKind.UNION_MEMBER_REMOVED,
                name,
                f"Union member '{member}' was removed from '{name}'.",
                old_value=member,
            )

    # ------------------------------------------------------------------ enums
    def _diff_enum(
        self, name: str, old_t: GraphQLEnumType, new_t: GraphQLEnumType
    ) -> None:
        old_vals = old_t.values
        new_vals = new_t.values

        for vname in sorted(set(old_vals) - set(new_vals)):
            self._add(
                ChangeKind.ENUM_VALUE_REMOVED,
                f"{name}.{vname}",
                f"Enum value '{name}.{vname}' was removed.",
            )

        for vname in sorted(set(new_vals) - set(old_vals)):
            self._add(
                ChangeKind.ENUM_VALUE_ADDED,
                f"{name}.{vname}",
                f"Enum value '{name}.{vname}' was added.",
            )

        for vname in sorted(set(old_vals) & set(new_vals)):
            old_v = old_vals[vname]
            new_v = new_vals[vname]
            path = f"{name}.{vname}"
            if old_v.description != new_v.description:
                self._add(
                    ChangeKind.ENUM_VALUE_DESCRIPTION_CHANGED,
                    path,
                    f"Description of enum value '{path}' changed.",
                    old_value=old_v.description,
                    new_value=new_v.description,
                )
            old_dep = old_v.deprecation_reason
            new_dep = new_v.deprecation_reason
            if old_dep is None and new_dep is not None:
                self._add(
                    ChangeKind.ENUM_VALUE_DEPRECATION_ADDED,
                    path,
                    f"Enum value '{path}' was deprecated.",
                    new_value=new_dep,
                )
            elif old_dep is not None and new_dep is None:
                self._add(
                    ChangeKind.ENUM_VALUE_DEPRECATION_REMOVED,
                    path,
                    f"Deprecation removed from enum value '{path}'.",
                    old_value=old_dep,
                )

    # ---------------------------------------------------------- input objects
    def _diff_input_object(
        self, name: str, old_t: GraphQLInputObjectType, new_t: GraphQLInputObjectType
    ) -> None:
        old_fields = old_t.fields
        new_fields = new_t.fields

        for fname in sorted(set(old_fields) - set(new_fields)):
            self._add(
                ChangeKind.INPUT_FIELD_REMOVED,
                f"{name}.{fname}",
                f"Input field '{name}.{fname}' was removed.",
                old_value=_type_name(old_fields[fname].type),
            )

        for fname in sorted(set(new_fields) - set(old_fields)):
            field = new_fields[fname]
            sev = (
                Severity.BREAKING
                if _is_required_input(field)
                else Severity.DANGEROUS
            )
            self._add(
                ChangeKind.INPUT_FIELD_ADDED,
                f"{name}.{fname}",
                f"Input field '{name}.{fname}' was added.",
                severity=sev,
                new_value=_type_name(field.type),
            )

        for fname in sorted(set(old_fields) & set(new_fields)):
            self._diff_input_field(
                f"{name}.{fname}", old_fields[fname], new_fields[fname]
            )

    def _diff_input_field(
        self, path: str, old_f: GraphQLInputField, new_f: GraphQLInputField
    ) -> None:
        old_type_s = _type_name(old_f.type)
        new_type_s = _type_name(new_f.type)
        if old_type_s != new_type_s:
            self._add(
                ChangeKind.INPUT_FIELD_TYPE_CHANGED,
                path,
                f"Input field '{path}' type changed from '{old_type_s}' to '{new_type_s}'.",
                old_value=old_type_s,
                new_value=new_type_s,
            )

        old_has = _has_explicit_default(old_f)
        new_has = _has_explicit_default(new_f)
        old_def = _printed_default(old_f)
        new_def = _printed_default(new_f)

        if not old_has and new_has:
            self._add(
                ChangeKind.INPUT_FIELD_DEFAULT_ADDED,
                path,
                f"Default value added to input field '{path}'.",
                new_value=new_def,
            )
        elif old_has and not new_has:
            self._add(
                ChangeKind.INPUT_FIELD_DEFAULT_REMOVED,
                path,
                f"Default value removed from input field '{path}'.",
                old_value=old_def,
            )
        elif old_has and new_has and old_def != new_def:
            self._add(
                ChangeKind.INPUT_FIELD_DEFAULT_CHANGED,
                path,
                f"Default value of input field '{path}' changed.",
                old_value=old_def,
                new_value=new_def,
            )

    # ------------------------------------------------------------- directives
    def _diff_directives(self, old: GraphQLSchema, new: GraphQLSchema) -> None:
        old_dirs = {
            d.name: d
            for d in old.directives
            if d.name not in _BUILTIN_DIRECTIVE_NAMES
        }
        new_dirs = {
            d.name: d
            for d in new.directives
            if d.name not in _BUILTIN_DIRECTIVE_NAMES
        }

        for name in sorted(set(old_dirs) - set(new_dirs)):
            # Skip federation directive *definitions* removal noise when they
            # only appear because of applied-directive usage — still report.
            self._add(
                ChangeKind.DIRECTIVE_REMOVED,
                f"@{name}",
                f"Directive '@{name}' was removed.",
            )

        for name in sorted(set(new_dirs) - set(old_dirs)):
            self._add(
                ChangeKind.DIRECTIVE_ADDED,
                f"@{name}",
                f"Directive '@{name}' was added.",
            )

        for name in sorted(set(old_dirs) & set(new_dirs)):
            self._diff_directive_def(name, old_dirs[name], new_dirs[name])

    def _diff_directive_def(
        self, name: str, old_d: GraphQLDirective, new_d: GraphQLDirective
    ) -> None:
        path = f"@{name}"
        old_locs = {loc.name for loc in old_d.locations}
        new_locs = {loc.name for loc in new_d.locations}

        for loc in sorted(new_locs - old_locs):
            self._add(
                ChangeKind.DIRECTIVE_LOCATION_ADDED,
                path,
                f"Location '{loc}' added to directive '@{name}'.",
                new_value=loc,
            )
        for loc in sorted(old_locs - new_locs):
            self._add(
                ChangeKind.DIRECTIVE_LOCATION_REMOVED,
                path,
                f"Location '{loc}' removed from directive '@{name}'.",
                old_value=loc,
            )

        old_args = old_d.args
        new_args = new_d.args
        for aname in sorted(set(old_args) - set(new_args)):
            self._add(
                ChangeKind.DIRECTIVE_ARG_REMOVED,
                f"{path}({aname})",
                f"Argument '{aname}' removed from directive '@{name}'.",
            )
        for aname in sorted(set(new_args) - set(old_args)):
            self._add(
                ChangeKind.DIRECTIVE_ARG_ADDED,
                f"{path}({aname})",
                f"Argument '{aname}' added to directive '@{name}'.",
            )

    # --------------------------------------------------- applied directives
    def _directive_apps(self, node: Any) -> dict[str, list[dict[str, str]]]:
        """Collect applied directives from ast_node extensions.

        Returns a mapping of directive name -> list of arg-dicts (sorted keys).
        Multiple applications of the same directive (e.g. multiple @key) are kept.
        """
        result: dict[str, list[dict[str, str]]] = {}
        ast_node = getattr(node, "ast_node", None)
        if ast_node is None:
            return result
        directives = getattr(ast_node, "directives", None) or ()
        for d in directives:
            args: dict[str, str] = {}
            for arg in d.arguments or ():
                args[arg.name.value] = print_ast(arg.value)
            result.setdefault(d.name.value, []).append(args)
        # Sort applications by serialized args for deterministic compare.
        for name in result:
            result[name].sort(key=lambda a: sorted(a.items()))
        return result

    def _diff_applied_directives(self, path: str, old_node: Any, new_node: Any) -> None:
        old_apps = self._directive_apps(old_node)
        new_apps = self._directive_apps(new_node)

        all_names = sorted(set(old_apps) | set(new_apps))
        for dname in all_names:
            old_list = old_apps.get(dname, [])
            new_list = new_apps.get(dname, [])

            if dname in _FEDERATION_DIRECTIVES:
                self._diff_federation_directive(path, dname, old_list, new_list)
                continue

            # Generic applied directive handling.
            if not old_list and new_list:
                self._add(
                    ChangeKind.APPLIED_DIRECTIVE_ADDED,
                    path,
                    f"Directive '@{dname}' applied on '{path}'.",
                    new_value=str(new_list),
                )
            elif old_list and not new_list:
                self._add(
                    ChangeKind.APPLIED_DIRECTIVE_REMOVED,
                    path,
                    f"Directive '@{dname}' removed from '{path}'.",
                    old_value=str(old_list),
                )
            elif old_list != new_list:
                self._add(
                    ChangeKind.APPLIED_DIRECTIVE_ARG_CHANGED,
                    path,
                    f"Arguments of directive '@{dname}' on '{path}' changed.",
                    old_value=str(old_list),
                    new_value=str(new_list),
                )

    def _diff_federation_directive(
        self,
        path: str,
        dname: str,
        old_list: list[dict[str, str]],
        new_list: list[dict[str, str]],
    ) -> None:
        """Emit federation-specific change codes and severities."""
        mapping_added = {
            _FED_KEY: ChangeKind.FEDERATION_KEY_ADDED,
            _FED_REQUIRES: ChangeKind.FEDERATION_REQUIRES_ADDED,
            _FED_PROVIDES: ChangeKind.FEDERATION_PROVIDES_ADDED,
            _FED_SHAREABLE: ChangeKind.FEDERATION_SHAREABLE_ADDED,
            _FED_INACCESSIBLE: ChangeKind.FEDERATION_INACCESSIBLE_ADDED,
        }
        mapping_removed = {
            _FED_KEY: ChangeKind.FEDERATION_KEY_REMOVED,
            _FED_REQUIRES: ChangeKind.FEDERATION_REQUIRES_REMOVED,
            _FED_PROVIDES: ChangeKind.FEDERATION_PROVIDES_REMOVED,
            _FED_SHAREABLE: ChangeKind.FEDERATION_SHAREABLE_REMOVED,
            _FED_INACCESSIBLE: ChangeKind.FEDERATION_INACCESSIBLE_REMOVED,
        }
        mapping_changed = {
            _FED_KEY: ChangeKind.FEDERATION_KEY_FIELDS_CHANGED,
            _FED_REQUIRES: ChangeKind.FEDERATION_REQUIRES_FIELDS_CHANGED,
            _FED_PROVIDES: ChangeKind.FEDERATION_PROVIDES_FIELDS_CHANGED,
        }

        if not old_list and new_list:
            self._add(
                mapping_added[dname],
                path,
                f"Federation '@{dname}' added on '{path}'.",
                new_value=str(new_list),
            )
            return
        if old_list and not new_list:
            self._add(
                mapping_removed[dname],
                path,
                f"Federation '@{dname}' removed from '{path}'.",
                old_value=str(old_list),
            )
            return
        if old_list != new_list:
            # shareable / inaccessible have no args; treat arg change as remove+add
            # for directives with fields selection sets use the _FIELDS_CHANGED code.
            kind = mapping_changed.get(dname)
            if kind is None:
                # arg-less directives shouldn't differ unless presence changed
                # (already handled above), so fall through to generic.
                self._add(
                    ChangeKind.APPLIED_DIRECTIVE_ARG_CHANGED,
                    path,
                    f"Federation '@{dname}' on '{path}' changed.",
                    old_value=str(old_list),
                    new_value=str(new_list),
                )
            else:
                self._add(
                    kind,
                    path,
                    f"Federation '@{dname}' fields selection on '{path}' changed.",
                    old_value=str(old_list),
                    new_value=str(new_list),
                )


def schema_from_sdl(sdl: str) -> GraphQLSchema:
    """Build an executable schema from an SDL string (with assume_valid)."""
    document = parse(sdl)
    return build_ast_schema(document, assume_valid=True)
