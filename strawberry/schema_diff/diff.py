"""Core schema diff engine using GraphQL's parsed type system."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Union, cast

from graphql import (
    GraphQLArgument,
    GraphQLEnumType,
    GraphQLField,
    GraphQLInputObjectType,
    GraphQLInterfaceType,
    GraphQLNamedType,
    GraphQLObjectType,
    GraphQLSchema,
    GraphQLType,
    GraphQLUnionType,
    build_ast_schema,
    build_schema,
    is_enum_type,
    is_input_object_type,
    is_interface_type,
    is_list_type,
    is_non_null_type,
    is_object_type,
    is_scalar_type,
    is_union_type,
    parse,
)

from .config import SchemaDiffConfig
from .federation import diff_federation_directives
from .models import (
    DEFAULT_SEVERITY,
    ChangeCode,
    ChangeSeverity,
    SchemaChange,
    SchemaDiffResult,
)

if TYPE_CHECKING:
    pass

_SKIP_TYPES = frozenset({
    "__Schema", "__Type", "__TypeKind", "__Field",
    "__InputValue", "__EnumValue", "__Directive", "__DirectiveLocation",
})

_BUILTIN_SCALARS = frozenset({"String", "Int", "Float", "Boolean", "ID"})


def _type_kind_name(gql_type: GraphQLNamedType) -> str:
    if is_scalar_type(gql_type):
        return "SCALAR"
    if is_object_type(gql_type):
        return "OBJECT"
    if is_interface_type(gql_type):
        return "INTERFACE"
    if is_union_type(gql_type):
        return "UNION"
    if is_enum_type(gql_type):
        return "ENUM"
    if is_input_object_type(gql_type):
        return "INPUT_OBJECT"
    return "UNKNOWN"


def type_to_string(gql_type: GraphQLType) -> str:
    """Render a GraphQL type as an SDL type reference string."""
    if is_non_null_type(gql_type):
        return f"{type_to_string(cast(Any, gql_type).of_type)}!"
    if is_list_type(gql_type):
        return f"[{type_to_string(cast(Any, gql_type).of_type)}]"
    return cast(Any, gql_type).name


def _unwrap_non_null(gql_type: GraphQLType) -> GraphQLType:
    if is_non_null_type(gql_type):
        return cast(Any, gql_type).of_type
    return gql_type


def _is_non_null(gql_type: GraphQLType) -> bool:
    return is_non_null_type(gql_type)


def _serialize_default(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return repr(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        items = ", ".join(_serialize_default(v) or "null" for v in value)
        return f"[{items}]"
    if isinstance(value, dict):
        items = ", ".join(
            f"{k}: {_serialize_default(v) or 'null'}" for k, v in sorted(value.items())
        )
        return f"{{{items}}}"
    return str(value)


SchemaInput = Union[str, Any]


def _is_undefined(value: Any) -> bool:
    try:
        from graphql.pyutils import Undefined
        return value is Undefined
    except ImportError:
        return False


def _resolve_to_graphql_schema(schema: SchemaInput) -> GraphQLSchema:
    """Accept SDL string, strawberry.Schema, or GraphQLSchema."""
    if isinstance(schema, GraphQLSchema):
        return schema

    if isinstance(schema, str):
        sdl = schema.strip()
        if not sdl:
            raise ValueError("Schema SDL string is empty")
        try:
            return build_schema(sdl)
        except Exception:
            document = parse(sdl)
            return build_ast_schema(document, assume_valid=True)

    if hasattr(schema, "_schema") and isinstance(schema._schema, GraphQLSchema):
        return schema._schema

    if hasattr(schema, "as_str") and callable(schema.as_str):
        return build_schema(schema.as_str())

    raise TypeError(
        f"Unsupported schema type: {type(schema)!r}. "
        "Expected strawberry.Schema, GraphQLSchema, or SDL string."
    )


def _source_label(schema: SchemaInput) -> str:
    if isinstance(schema, str):
        return "sdl"
    if isinstance(schema, GraphQLSchema):
        return "graphql_schema"
    if hasattr(schema, "__class__"):
        return schema.__class__.__module__ + "." + schema.__class__.__name__
    return "unknown"


class SchemaDiffer:
    """Compare two GraphQL schemas structurally."""

    def __init__(
        self,
        old_schema: GraphQLSchema,
        new_schema: GraphQLSchema,
        config: SchemaDiffConfig | None = None,
    ) -> None:
        self.old = old_schema
        self.new = new_schema
        self.config = config or SchemaDiffConfig()
        self._changes: list[SchemaChange] = []

    def diff(self) -> list[SchemaChange]:
        self._changes = []
        self._diff_schema_roots()
        self._diff_types()
        self._diff_directives()
        fed_changes = diff_federation_directives(
            self.old, self.new, self._make_change_obj
        )
        for ch in fed_changes:
            self._maybe_add(ch)
        return self._sorted_changes()

    def _sorted_changes(self) -> list[SchemaChange]:
        return sorted(self._changes, key=lambda c: c.sort_key())

    def _make_change_obj(
        self,
        code: ChangeCode,
        path: str,
        message: str,
        *,
        old_value: Any = None,
        new_value: Any = None,
        meta: dict[str, Any] | None = None,
    ) -> SchemaChange:
        default_sev = DEFAULT_SEVERITY.get(code, ChangeSeverity.SAFE)
        severity = self.config.resolve_severity(code, default_sev)
        return SchemaChange(
            code=code,
            severity=severity,
            path=path,
            message=message,
            old_value=old_value,
            new_value=new_value,
            meta=meta or {},
        )

    def _add(
        self,
        code: ChangeCode,
        path: str,
        message: str,
        *,
        old_value: Any = None,
        new_value: Any = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        if self.config.is_code_ignored(code):
            return
        if not self.config.include_descriptions and code in (
            ChangeCode.TYPE_DESCRIPTION_CHANGED,
            ChangeCode.FIELD_DESCRIPTION_CHANGED,
            ChangeCode.ARG_DESCRIPTION_CHANGED,
            ChangeCode.ENUM_VALUE_DESCRIPTION_CHANGED,
        ):
            return
        if self.config.should_ignore_path(path):
            return
        type_name = path.split(".")[0].split("(")[0]
        if type_name and self.config.should_ignore_type(type_name):
            return
        change = self._make_change_obj(
            code, path, message, old_value=old_value, new_value=new_value, meta=meta
        )
        self._changes.append(change)

    def _maybe_add(self, change: SchemaChange) -> None:
        if self.config.is_code_ignored(change.code):
            return
        if self.config.should_ignore_path(change.path):
            return
        type_name = change.path.split(".")[0].split("(")[0]
        if type_name and self.config.should_ignore_type(type_name):
            return
        default_sev = DEFAULT_SEVERITY.get(change.code, change.severity)
        severity = self.config.resolve_severity(change.code, default_sev)
        if severity != change.severity:
            change = SchemaChange(
                code=change.code,
                severity=severity,
                path=change.path,
                message=change.message,
                old_value=change.old_value,
                new_value=change.new_value,
                meta=change.meta,
            )
        self._changes.append(change)

    def _add_with_severity(
        self,
        code: ChangeCode,
        severity: ChangeSeverity,
        path: str,
        message: str,
        *,
        old_value: Any = None,
        new_value: Any = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        if self.config.is_code_ignored(code):
            return
        if self.config.should_ignore_path(path):
            return
        severity = self.config.resolve_severity(code, severity)
        self._changes.append(
            SchemaChange(
                code=code,
                severity=severity,
                path=path,
                message=message,
                old_value=old_value,
                new_value=new_value,
                meta=meta or {},
            )
        )

    def _diff_schema_roots(self) -> None:
        for attr, code in (
            ("query_type", ChangeCode.SCHEMA_QUERY_TYPE_CHANGED),
            ("mutation_type", ChangeCode.SCHEMA_MUTATION_TYPE_CHANGED),
            ("subscription_type", ChangeCode.SCHEMA_SUBSCRIPTION_TYPE_CHANGED),
        ):
            old_t = getattr(self.old, attr, None)
            new_t = getattr(self.new, attr, None)
            old_name = old_t.name if old_t else None
            new_name = new_t.name if new_t else None
            if old_name != new_name:
                self._add(
                    code,
                    f"schema.{attr}",
                    f"Schema {attr} changed from {old_name!r} to {new_name!r}",
                    old_value=old_name,
                    new_value=new_name,
                )


    def _user_types(self, schema: GraphQLSchema) -> dict[str, GraphQLNamedType]:
        result: dict[str, GraphQLNamedType] = {}
        for name, t in schema.type_map.items():
            if name.startswith("__") or name in _SKIP_TYPES:
                continue
            if name in _BUILTIN_SCALARS and is_scalar_type(t):
                continue
            result[name] = t
        return result

    def _diff_types(self) -> None:
        old_types = self._user_types(self.old)
        new_types = self._user_types(self.new)

        for name in sorted(set(self.old.type_map) | set(self.new.type_map)):
            if name.startswith("__") or name in _SKIP_TYPES:
                continue
            if name in _BUILTIN_SCALARS:
                old_t = self.old.type_map.get(name)
                new_t = self.new.type_map.get(name)
                if old_t and new_t and is_scalar_type(old_t) and is_scalar_type(new_t):
                    continue
            if name in self.old.type_map:
                old_types[name] = self.old.type_map[name]
            if name in self.new.type_map:
                new_types[name] = self.new.type_map[name]

        all_names = sorted(set(old_types) | set(new_types))

        for name in all_names:
            if self.config.should_ignore_type(name):
                continue
            old_t = old_types.get(name)
            new_t = new_types.get(name)

            if old_t is None and new_t is not None:
                self._add(
                    ChangeCode.TYPE_ADDED,
                    name,
                    f"Type `{name}` was added ({_type_kind_name(new_t)})",
                    new_value=_type_kind_name(new_t),
                )
                continue

            if old_t is not None and new_t is None:
                self._add(
                    ChangeCode.TYPE_REMOVED,
                    name,
                    f"Type `{name}` was removed ({_type_kind_name(old_t)})",
                    old_value=_type_kind_name(old_t),
                )
                continue

            assert old_t is not None and new_t is not None
            old_kind = _type_kind_name(old_t)
            new_kind = _type_kind_name(new_t)
            if old_kind != new_kind:
                self._add(
                    ChangeCode.TYPE_KIND_CHANGED,
                    name,
                    f"Type `{name}` kind changed from {old_kind} to {new_kind}",
                    old_value=old_kind,
                    new_value=new_kind,
                )
                continue

            if (old_t.description or "") != (new_t.description or ""):
                self._add(
                    ChangeCode.TYPE_DESCRIPTION_CHANGED,
                    name,
                    f"Description of type `{name}` changed",
                    old_value=old_t.description,
                    new_value=new_t.description,
                )

            if is_object_type(old_t) and is_object_type(new_t):
                self._diff_object_type(
                    name, cast(GraphQLObjectType, old_t), cast(GraphQLObjectType, new_t)
                )
            elif is_interface_type(old_t) and is_interface_type(new_t):
                self._diff_interface_type(
                    name,
                    cast(GraphQLInterfaceType, old_t),
                    cast(GraphQLInterfaceType, new_t),
                )
            elif is_input_object_type(old_t) and is_input_object_type(new_t):
                self._diff_input_type(
                    name,
                    cast(GraphQLInputObjectType, old_t),
                    cast(GraphQLInputObjectType, new_t),
                )
            elif is_enum_type(old_t) and is_enum_type(new_t):
                self._diff_enum_type(
                    name, cast(GraphQLEnumType, old_t), cast(GraphQLEnumType, new_t)
                )
            elif is_union_type(old_t) and is_union_type(new_t):
                self._diff_union_type(
                    name, cast(GraphQLUnionType, old_t), cast(GraphQLUnionType, new_t)
                )

    def _diff_object_type(
        self, type_name: str, old_t: GraphQLObjectType, new_t: GraphQLObjectType
    ) -> None:
        self._diff_fields(type_name, old_t.fields, new_t.fields)
        self._diff_interfaces(type_name, old_t, new_t)

    def _diff_interface_type(
        self,
        type_name: str,
        old_t: GraphQLInterfaceType,
        new_t: GraphQLInterfaceType,
    ) -> None:
        self._diff_fields(type_name, old_t.fields, new_t.fields)
        old_ifaces = {i.name for i in (old_t.interfaces or [])}
        new_ifaces = {i.name for i in (new_t.interfaces or [])}
        for iface in sorted(new_ifaces - old_ifaces):
            self._add(
                ChangeCode.INTERFACE_ADDED_TO_OBJECT,
                f"{type_name} implements {iface}",
                f"Interface `{type_name}` now implements `{iface}`",
                new_value=iface,
            )
        for iface in sorted(old_ifaces - new_ifaces):
            self._add(
                ChangeCode.INTERFACE_REMOVED_FROM_OBJECT,
                f"{type_name} implements {iface}",
                f"Interface `{type_name}` no longer implements `{iface}`",
                old_value=iface,
            )

    def _diff_interfaces(
        self, type_name: str, old_t: GraphQLObjectType, new_t: GraphQLObjectType
    ) -> None:
        old_ifaces = {i.name for i in (old_t.interfaces or [])}
        new_ifaces = {i.name for i in (new_t.interfaces or [])}
        for iface in sorted(new_ifaces - old_ifaces):
            self._add(
                ChangeCode.INTERFACE_ADDED_TO_OBJECT,
                f"{type_name} implements {iface}",
                f"Type `{type_name}` now implements interface `{iface}`",
                new_value=iface,
            )
        for iface in sorted(old_ifaces - new_ifaces):
            self._add(
                ChangeCode.INTERFACE_REMOVED_FROM_OBJECT,
                f"{type_name} implements {iface}",
                f"Type `{type_name}` no longer implements interface `{iface}`",
                old_value=iface,
            )


    def _diff_fields(
        self,
        type_name: str,
        old_fields: dict[str, GraphQLField],
        new_fields: dict[str, GraphQLField],
    ) -> None:
        all_names = sorted(set(old_fields) | set(new_fields))
        for field_name in all_names:
            path = f"{type_name}.{field_name}"
            old_f = old_fields.get(field_name)
            new_f = new_fields.get(field_name)

            if old_f is None and new_f is not None:
                self._add(
                    ChangeCode.FIELD_ADDED,
                    path,
                    f"Field `{path}` was added with type `{type_to_string(new_f.type)}`",
                    new_value=type_to_string(new_f.type),
                )
                continue

            if old_f is not None and new_f is None:
                self._add(
                    ChangeCode.FIELD_REMOVED,
                    path,
                    f"Field `{path}` was removed (was `{type_to_string(old_f.type)}`)",
                    old_value=type_to_string(old_f.type),
                )
                continue

            assert old_f is not None and new_f is not None
            self._diff_field_type(path, old_f.type, new_f.type)
            self._diff_field_deprecation(path, old_f, new_f)
            if (old_f.description or "") != (new_f.description or ""):
                self._add(
                    ChangeCode.FIELD_DESCRIPTION_CHANGED,
                    path,
                    f"Description of field `{path}` changed",
                    old_value=old_f.description,
                    new_value=new_f.description,
                )
            self._diff_args(path, old_f.args, new_f.args)

    def _diff_field_type(
        self, path: str, old_type: GraphQLType, new_type: GraphQLType
    ) -> None:
        old_str = type_to_string(old_type)
        new_str = type_to_string(new_type)
        if old_str == new_str:
            return

        old_inner = _unwrap_non_null(old_type)
        new_inner = _unwrap_non_null(new_type)
        if type_to_string(old_inner) == type_to_string(new_inner):
            if _is_non_null(old_type) and not _is_non_null(new_type):
                self._add(
                    ChangeCode.FIELD_MADE_NULLABLE,
                    path,
                    f"Field `{path}` made nullable (`{old_str}` -> `{new_str}`)",
                    old_value=old_str,
                    new_value=new_str,
                )
                return
            if not _is_non_null(old_type) and _is_non_null(new_type):
                self._add(
                    ChangeCode.FIELD_MADE_NON_NULL,
                    path,
                    f"Field `{path}` made non-null (`{old_str}` -> `{new_str}`)",
                    old_value=old_str,
                    new_value=new_str,
                )
                return

        self._add(
            ChangeCode.FIELD_TYPE_CHANGED,
            path,
            f"Field `{path}` type changed from `{old_str}` to `{new_str}`",
            old_value=old_str,
            new_value=new_str,
        )

    def _diff_field_deprecation(
        self, path: str, old_f: GraphQLField, new_f: GraphQLField
    ) -> None:
        old_dep = old_f.deprecation_reason
        new_dep = new_f.deprecation_reason
        if old_dep is None and new_dep is not None:
            self._add(
                ChangeCode.FIELD_DEPRECATION_ADDED,
                path,
                f"Field `{path}` deprecated: {new_dep}",
                new_value=new_dep,
            )
        elif old_dep is not None and new_dep is None:
            self._add(
                ChangeCode.FIELD_DEPRECATION_REMOVED,
                path,
                f"Field `{path}` deprecation removed (was: {old_dep})",
                old_value=old_dep,
            )
        elif old_dep is not None and new_dep is not None and old_dep != new_dep:
            self._add(
                ChangeCode.FIELD_DEPRECATION_REASON_CHANGED,
                path,
                f"Field `{path}` deprecation reason changed",
                old_value=old_dep,
                new_value=new_dep,
            )


    def _diff_args(
        self,
        field_path: str,
        old_args: dict[str, GraphQLArgument],
        new_args: dict[str, GraphQLArgument],
    ) -> None:
        all_names = sorted(set(old_args) | set(new_args))
        for arg_name in all_names:
            path = f"{field_path}({arg_name}:)"
            old_a = old_args.get(arg_name)
            new_a = new_args.get(arg_name)

            if old_a is None and new_a is not None:
                # Required (non-null, no default) arguments are breaking additions
                if _is_non_null(new_a.type) and _is_undefined(
                    getattr(new_a, "default_value", None)
                ):
                    self._add_with_severity(
                        ChangeCode.ARG_ADDED,
                        ChangeSeverity.BREAKING,
                        path,
                        f"Required argument `{arg_name}` added to `{field_path}` "
                        f"with type `{type_to_string(new_a.type)}` (breaking)",
                        new_value=type_to_string(new_a.type),
                    )
                    continue
                self._add(
                    ChangeCode.ARG_ADDED,
                    path,
                    f"Argument `{arg_name}` added to `{field_path}` "
                    f"with type `{type_to_string(new_a.type)}`",
                    new_value=type_to_string(new_a.type),
                )
                continue

            if old_a is not None and new_a is None:
                self._add(
                    ChangeCode.ARG_REMOVED,
                    path,
                    f"Argument `{arg_name}` removed from `{field_path}`",
                    old_value=type_to_string(old_a.type),
                )
                continue

            assert old_a is not None and new_a is not None
            self._diff_arg_type(path, arg_name, field_path, old_a, new_a)
            self._diff_arg_default(path, arg_name, field_path, old_a, new_a)
            if (old_a.description or "") != (new_a.description or ""):
                self._add(
                    ChangeCode.ARG_DESCRIPTION_CHANGED,
                    path,
                    f"Description of argument `{arg_name}` on `{field_path}` changed",
                    old_value=old_a.description,
                    new_value=new_a.description,
                )

    def _diff_arg_type(
        self,
        path: str,
        arg_name: str,
        field_path: str,
        old_a: GraphQLArgument,
        new_a: GraphQLArgument,
    ) -> None:
        old_str = type_to_string(old_a.type)
        new_str = type_to_string(new_a.type)
        if old_str == new_str:
            return

        old_inner = _unwrap_non_null(old_a.type)
        new_inner = _unwrap_non_null(new_a.type)
        if type_to_string(old_inner) == type_to_string(new_inner):
            if _is_non_null(old_a.type) and not _is_non_null(new_a.type):
                self._add(
                    ChangeCode.ARG_MADE_NULLABLE,
                    path,
                    f"Argument `{arg_name}` on `{field_path}` made nullable "
                    f"(`{old_str}` -> `{new_str}`)",
                    old_value=old_str,
                    new_value=new_str,
                )
                return
            if not _is_non_null(old_a.type) and _is_non_null(new_a.type):
                self._add(
                    ChangeCode.ARG_MADE_NON_NULL,
                    path,
                    f"Argument `{arg_name}` on `{field_path}` made non-null "
                    f"(`{old_str}` -> `{new_str}`)",
                    old_value=old_str,
                    new_value=new_str,
                )
                return

        self._add(
            ChangeCode.ARG_TYPE_CHANGED,
            path,
            f"Argument `{arg_name}` on `{field_path}` type changed "
            f"from `{old_str}` to `{new_str}`",
            old_value=old_str,
            new_value=new_str,
        )

    def _diff_arg_default(
        self,
        path: str,
        arg_name: str,
        field_path: str,
        old_a: GraphQLArgument,
        new_a: GraphQLArgument,
    ) -> None:
        from graphql.pyutils import Undefined

        old_has = old_a.default_value is not Undefined
        new_has = new_a.default_value is not Undefined
        old_ser = _serialize_default(old_a.default_value) if old_has else None
        new_ser = _serialize_default(new_a.default_value) if new_has else None

        if not old_has and new_has:
            self._add(
                ChangeCode.ARG_DEFAULT_ADDED,
                path,
                f"Default value added to argument `{arg_name}` on `{field_path}`: {new_ser}",
                new_value=new_ser,
            )
        elif old_has and not new_has:
            self._add(
                ChangeCode.ARG_DEFAULT_REMOVED,
                path,
                f"Default value removed from argument `{arg_name}` on `{field_path}` "
                f"(was {old_ser})",
                old_value=old_ser,
            )
        elif old_has and new_has and old_ser != new_ser:
            self._add(
                ChangeCode.ARG_DEFAULT_CHANGED,
                path,
                f"Default value of argument `{arg_name}` on `{field_path}` changed "
                f"from {old_ser} to {new_ser}",
                old_value=old_ser,
                new_value=new_ser,
            )


    def _diff_input_type(
        self,
        type_name: str,
        old_t: GraphQLInputObjectType,
        new_t: GraphQLInputObjectType,
    ) -> None:
        old_fields = old_t.fields
        new_fields = new_t.fields
        all_names = sorted(set(old_fields) | set(new_fields))
        for field_name in all_names:
            path = f"{type_name}.{field_name}"
            old_f = old_fields.get(field_name)
            new_f = new_fields.get(field_name)

            if old_f is None and new_f is not None:
                if _is_non_null(new_f.type) and _is_undefined(
                    getattr(new_f, "default_value", None)
                ):
                    self._add_with_severity(
                        ChangeCode.FIELD_ADDED,
                        ChangeSeverity.BREAKING,
                        path,
                        f"Required input field `{path}` was added (breaking)",
                        new_value=type_to_string(new_f.type),
                    )
                else:
                    self._add(
                        ChangeCode.FIELD_ADDED,
                        path,
                        f"Input field `{path}` was added with type "
                        f"`{type_to_string(new_f.type)}`",
                        new_value=type_to_string(new_f.type),
                    )
                continue

            if old_f is not None and new_f is None:
                self._add(
                    ChangeCode.FIELD_REMOVED,
                    path,
                    f"Input field `{path}` was removed",
                    old_value=type_to_string(old_f.type),
                )
                continue

            assert old_f is not None and new_f is not None
            self._diff_field_type(path, old_f.type, new_f.type)
            if (old_f.description or "") != (new_f.description or ""):
                self._add(
                    ChangeCode.FIELD_DESCRIPTION_CHANGED,
                    path,
                    f"Description of input field `{path}` changed",
                    old_value=old_f.description,
                    new_value=new_f.description,
                )

    def _diff_enum_type(
        self, type_name: str, old_t: GraphQLEnumType, new_t: GraphQLEnumType
    ) -> None:
        old_vals = old_t.values
        new_vals = new_t.values
        all_names = sorted(set(old_vals) | set(new_vals))
        for val_name in all_names:
            path = f"{type_name}.{val_name}"
            old_v = old_vals.get(val_name)
            new_v = new_vals.get(val_name)

            if old_v is None and new_v is not None:
                self._add(
                    ChangeCode.ENUM_VALUE_ADDED,
                    path,
                    f"Enum value `{val_name}` added to `{type_name}`",
                    new_value=val_name,
                )
                continue

            if old_v is not None and new_v is None:
                self._add(
                    ChangeCode.ENUM_VALUE_REMOVED,
                    path,
                    f"Enum value `{val_name}` removed from `{type_name}`",
                    old_value=val_name,
                )
                continue

            assert old_v is not None and new_v is not None
            if (old_v.description or "") != (new_v.description or ""):
                self._add(
                    ChangeCode.ENUM_VALUE_DESCRIPTION_CHANGED,
                    path,
                    f"Description of enum value `{path}` changed",
                    old_value=old_v.description,
                    new_value=new_v.description,
                )
            old_dep = old_v.deprecation_reason
            new_dep = new_v.deprecation_reason
            if old_dep is None and new_dep is not None:
                self._add(
                    ChangeCode.ENUM_VALUE_DEPRECATION_ADDED,
                    path,
                    f"Enum value `{path}` deprecated: {new_dep}",
                    new_value=new_dep,
                )
            elif old_dep is not None and new_dep is None:
                self._add(
                    ChangeCode.ENUM_VALUE_DEPRECATION_REMOVED,
                    path,
                    f"Enum value `{path}` deprecation removed",
                    old_value=old_dep,
                )

    def _diff_union_type(
        self, type_name: str, old_t: GraphQLUnionType, new_t: GraphQLUnionType
    ) -> None:
        old_members = {t.name for t in old_t.types}
        new_members = {t.name for t in new_t.types}
        for member in sorted(new_members - old_members):
            self._add(
                ChangeCode.UNION_MEMBER_ADDED,
                f"{type_name}.{member}",
                f"Union member `{member}` added to `{type_name}`",
                new_value=member,
            )
        for member in sorted(old_members - new_members):
            self._add(
                ChangeCode.UNION_MEMBER_REMOVED,
                f"{type_name}.{member}",
                f"Union member `{member}` removed from `{type_name}`",
                old_value=member,
            )

    def _diff_directives(self) -> None:
        old_dirs = {d.name: d for d in self.old.directives if not d.name.startswith("__")}
        new_dirs = {d.name: d for d in self.new.directives if not d.name.startswith("__")}
        _BUILTIN_DIRS = frozenset({"skip", "include", "deprecated", "specifiedBy", "oneOf"})

        all_names = sorted(set(old_dirs) | set(new_dirs))
        for name in all_names:
            old_d = old_dirs.get(name)
            new_d = new_dirs.get(name)
            path = f"@{name}"

            if old_d is None and new_d is not None:
                if name in _BUILTIN_DIRS:
                    continue
                self._add(
                    ChangeCode.DIRECTIVE_ADDED,
                    path,
                    f"Directive `@{name}` was added",
                    new_value=name,
                )
                continue

            if old_d is not None and new_d is None:
                if name in _BUILTIN_DIRS:
                    continue
                self._add(
                    ChangeCode.DIRECTIVE_REMOVED,
                    path,
                    f"Directive `@{name}` was removed",
                    old_value=name,
                )
                continue

            if old_d is None or new_d is None:
                continue
            if name in _BUILTIN_DIRS:
                continue

            old_locs = {loc.name for loc in old_d.locations}
            new_locs = {loc.name for loc in new_d.locations}
            for loc in sorted(new_locs - old_locs):
                self._add(
                    ChangeCode.DIRECTIVE_LOCATION_ADDED,
                    f"{path}.{loc}",
                    f"Location `{loc}` added to directive `@{name}`",
                    new_value=loc,
                )
            for loc in sorted(old_locs - new_locs):
                self._add(
                    ChangeCode.DIRECTIVE_LOCATION_REMOVED,
                    f"{path}.{loc}",
                    f"Location `{loc}` removed from directive `@{name}`",
                    old_value=loc,
                )

            old_args = old_d.args
            new_args = new_d.args
            all_arg_names = sorted(set(old_args) | set(new_args))
            for arg_name in all_arg_names:
                arg_path = f"{path}({arg_name}:)"
                old_a = old_args.get(arg_name)
                new_a = new_args.get(arg_name)
                if old_a is None and new_a is not None:
                    self._add(
                        ChangeCode.DIRECTIVE_ARG_ADDED,
                        arg_path,
                        f"Argument `{arg_name}` added to directive `@{name}`",
                        new_value=type_to_string(new_a.type),
                    )
                elif old_a is not None and new_a is None:
                    self._add(
                        ChangeCode.DIRECTIVE_ARG_REMOVED,
                        arg_path,
                        f"Argument `{arg_name}` removed from directive `@{name}`",
                        old_value=type_to_string(old_a.type),
                    )
                elif old_a is not None and new_a is not None:
                    old_str = type_to_string(old_a.type)
                    new_str = type_to_string(new_a.type)
                    if old_str != new_str:
                        self._add(
                            ChangeCode.DIRECTIVE_ARG_TYPE_CHANGED,
                            arg_path,
                            f"Directive argument `@{name}({arg_name}:)` type changed "
                            f"from `{old_str}` to `{new_str}`",
                            old_value=old_str,
                            new_value=new_str,
                        )


def diff_schemas(
    old_schema: SchemaInput,
    new_schema: SchemaInput,
    config: SchemaDiffConfig | None = None,
) -> SchemaDiffResult:
    """Compare two GraphQL schemas and return structured diff results.

    Args:
        old_schema: Previous schema as ``strawberry.Schema``, ``GraphQLSchema``,
            or SDL string.
        new_schema: New/candidate schema in the same accepted forms.
        config: Optional configuration for filtering and severity overrides.

    Returns:
        :class:`SchemaDiffResult` with deterministically ordered changes.
    """
    config = config or SchemaDiffConfig()
    old_gql = _resolve_to_graphql_schema(old_schema)
    new_gql = _resolve_to_graphql_schema(new_schema)

    differ = SchemaDiffer(old_gql, new_gql, config)
    changes = differ.diff()

    return SchemaDiffResult(
        changes=changes,
        old_schema_source=_source_label(old_schema),
        new_schema_source=_source_label(new_schema),
    )
