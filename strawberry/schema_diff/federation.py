"""Apollo Federation v2 directive handling for schema diffs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from graphql import GraphQLSchema
from graphql.language import ast
from graphql.language.printer import print_ast

from .models import ChangeCode, ChangeSeverity, DEFAULT_SEVERITY, SchemaChange

# Federation directive names (without @)
FED_DIRECTIVES = frozenset({
    "key",
    "requires",
    "provides",
    "shareable",
    "inaccessible",
    "external",
    "override",
    "tag",
    "extends",
    "link",
    "composeDirective",
    "interfaceObject",
    "authenticated",
    "requiresScopes",
    "policy",
    "context",
    "fromContext",
})

# Directives we diff with dedicated change codes
_SPECIAL_FED = frozenset({
    "key",
    "requires",
    "provides",
    "shareable",
    "inaccessible",
    "external",
    "override",
    "tag",
})


@dataclass(frozen=True)
class AppliedDirective:
    """Normalized representation of an applied directive."""

    name: str
    args: tuple[tuple[str, str], ...]  # sorted (arg_name, printed_value) pairs

    @property
    def signature(self) -> str:
        if not self.args:
            return f"@{self.name}"
        args_str = ", ".join(f"{k}: {v}" for k, v in self.args)
        return f"@{self.name}({args_str})"

    def arg_value(self, name: str) -> str | None:
        for k, v in self.args:
            if k == name:
                return v
        return None


def _print_value_node(node: ast.ValueNode | None) -> str:
    if node is None:
        return "null"
    return print_ast(node)


def extract_applied_directives(
    ast_node: ast.Node | None,
) -> list[AppliedDirective]:
    """Extract applied directives from a type/field/enum AST node."""
    if ast_node is None:
        return []
    directives = getattr(ast_node, "directives", None) or []
    result: list[AppliedDirective] = []
    for d in directives:
        name = d.name.value
        args: list[tuple[str, str]] = []
        for arg in d.arguments or []:
            args.append((arg.name.value, _print_value_node(arg.value)))
        args.sort(key=lambda x: x[0])
        result.append(AppliedDirective(name=name, args=tuple(args)))
    result.sort(key=lambda d: (d.name, d.signature))
    return result


def _collect_type_directives_from_schema(
    schema: GraphQLSchema,
) -> dict[str, list[AppliedDirective]]:
    """Map type name -> applied directives from the SDL AST extensions."""
    out: dict[str, list[AppliedDirective]] = {}
    for type_name, gql_type in schema.type_map.items():
        if type_name.startswith("__"):
            continue
        ast_node = getattr(gql_type, "ast_node", None)
        dirs = extract_applied_directives(ast_node)
        if dirs:
            out[type_name] = dirs
        # Field-level directives
        fields = getattr(gql_type, "fields", None)
        if fields:
            for field_name, field in fields.items():
                field_ast = getattr(field, "ast_node", None)
                field_dirs = extract_applied_directives(field_ast)
                if field_dirs:
                    out[f"{type_name}.{field_name}"] = field_dirs
        # Enum values
        values = getattr(gql_type, "values", None)
        if values:
            for val_name, val in values.items():
                val_ast = getattr(val, "ast_node", None)
                val_dirs = extract_applied_directives(val_ast)
                if val_dirs:
                    out[f"{type_name}.{val_name}"] = val_dirs
    return out


def _fed_add_code(name: str) -> ChangeCode | None:
    return {
        "key": ChangeCode.FED_KEY_ADDED,
        "requires": ChangeCode.FED_REQUIRES_ADDED,
        "provides": ChangeCode.FED_PROVIDES_ADDED,
        "shareable": ChangeCode.FED_SHAREABLE_ADDED,
        "inaccessible": ChangeCode.FED_INACCESSIBLE_ADDED,
        "external": ChangeCode.FED_EXTERNAL_ADDED,
        "override": ChangeCode.FED_OVERRIDE_ADDED,
        "tag": ChangeCode.FED_TAG_ADDED,
    }.get(name)


def _fed_remove_code(name: str) -> ChangeCode | None:
    return {
        "key": ChangeCode.FED_KEY_REMOVED,
        "requires": ChangeCode.FED_REQUIRES_REMOVED,
        "provides": ChangeCode.FED_PROVIDES_REMOVED,
        "shareable": ChangeCode.FED_SHAREABLE_REMOVED,
        "inaccessible": ChangeCode.FED_INACCESSIBLE_REMOVED,
        "external": ChangeCode.FED_EXTERNAL_REMOVED,
        "override": ChangeCode.FED_OVERRIDE_REMOVED,
        "tag": ChangeCode.FED_TAG_REMOVED,
    }.get(name)


def _match_directives(
    old_dirs: list[AppliedDirective],
    new_dirs: list[AppliedDirective],
    directive_name: str,
) -> tuple[list[AppliedDirective], list[AppliedDirective], list[tuple[AppliedDirective, AppliedDirective]]]:
    """Split old/new directives of a given name into removed, added, and potentially modified pairs."""
    old_matching = [d for d in old_dirs if d.name == directive_name]
    new_matching = [d for d in new_dirs if d.name == directive_name]

    if directive_name == "key":
        # Match by fields argument
        old_by_fields = {d.arg_value("fields") or "": d for d in old_matching}
        new_by_fields = {d.arg_value("fields") or "": d for d in new_matching}
        common = set(old_by_fields) & set(new_by_fields)
        removed = [old_by_fields[k] for k in sorted(set(old_by_fields) - set(new_by_fields))]
        added = [new_by_fields[k] for k in sorted(set(new_by_fields) - set(old_by_fields))]
        modified = [(old_by_fields[k], new_by_fields[k]) for k in sorted(common)]
        return removed, added, modified

    if directive_name in ("requires", "provides"):
        old_by_fields = {d.arg_value("fields") or d.signature: d for d in old_matching}
        new_by_fields = {d.arg_value("fields") or d.signature: d for d in new_matching}
        removed = [old_by_fields[k] for k in sorted(set(old_by_fields) - set(new_by_fields))]
        added = [new_by_fields[k] for k in sorted(set(new_by_fields) - set(old_by_fields))]
        return removed, added, []

    if directive_name == "tag":
        old_by_name = {d.arg_value("name") or d.signature: d for d in old_matching}
        new_by_name = {d.arg_value("name") or d.signature: d for d in new_matching}
        removed = [old_by_name[k] for k in sorted(set(old_by_name) - set(new_by_name))]
        added = [new_by_name[k] for k in sorted(set(new_by_name) - set(old_by_name))]
        return removed, added, []

    # shareable, inaccessible, external, override — presence-based
    if not old_matching and not new_matching:
        return [], [], []
    if old_matching and not new_matching:
        return old_matching, [], []
    if new_matching and not old_matching:
        return [], new_matching, []
    # both present — check if args changed (override has `from`)
    if old_matching[0].signature != new_matching[0].signature:
        return [], [], [(old_matching[0], new_matching[0])]
    return [], [], []


def diff_federation_directives(
    old_schema: GraphQLSchema,
    new_schema: GraphQLSchema,
    make_change,  # callable accepting (code, path, message, ...)
) -> list[SchemaChange]:
    """Compare Federation directives between schemas and emit specialized changes."""
    changes: list[SchemaChange] = []
    old_map = _collect_type_directives_from_schema(old_schema)
    new_map = _collect_type_directives_from_schema(new_schema)

    all_paths = sorted(set(old_map) | set(new_map))

    for path in all_paths:
        old_dirs = old_map.get(path, [])
        new_dirs = new_map.get(path, [])

        old_fed = [d for d in old_dirs if d.name in _SPECIAL_FED]
        new_fed = [d for d in new_dirs if d.name in _SPECIAL_FED]
        old_other = [d for d in old_dirs if d.name not in _SPECIAL_FED]
        new_other = [d for d in new_dirs if d.name not in _SPECIAL_FED]

        # Non-federation applied directives (generic)
        old_other_sigs = {d.signature: d for d in old_other}
        new_other_sigs = {d.signature: d for d in new_other}
        for sig in sorted(set(old_other_sigs) - set(new_other_sigs)):
            d = old_other_sigs[sig]
            changes.append(
                make_change(
                    ChangeCode.APPLIED_DIRECTIVE_REMOVED,
                    path,
                    f"Removed directive {d.signature}",
                    old_value=d.signature,
                )
            )
        for sig in sorted(set(new_other_sigs) - set(old_other_sigs)):
            d = new_other_sigs[sig]
            changes.append(
                make_change(
                    ChangeCode.APPLIED_DIRECTIVE_ADDED,
                    path,
                    f"Added directive {d.signature}",
                    new_value=d.signature,
                )
            )

        # Federation special directives
        for fed_name in sorted(_SPECIAL_FED):
            removed, added, modified = _match_directives(old_fed, new_fed, fed_name)

            for d in removed:
                code = _fed_remove_code(fed_name)
                if code is None:
                    continue
                changes.append(
                    make_change(
                        code,
                        path,
                        f"Removed federation directive {d.signature}",
                        old_value=d.signature,
                        meta={"directive": fed_name},
                    )
                )

            for d in added:
                code = _fed_add_code(fed_name)
                if code is None:
                    continue
                changes.append(
                    make_change(
                        code,
                        path,
                        f"Added federation directive {d.signature}",
                        new_value=d.signature,
                        meta={"directive": fed_name},
                    )
                )

            for old_d, new_d in modified:
                if fed_name == "key":
                    old_res = old_d.arg_value("resolvable")
                    new_res = new_d.arg_value("resolvable")
                    if old_res != new_res:
                        changes.append(
                            make_change(
                                ChangeCode.FED_KEY_RESOLVABLE_CHANGED,
                                path,
                                f"@key resolvable changed from {old_res} to {new_res}",
                                old_value=old_res,
                                new_value=new_res,
                                meta={"directive": "key", "fields": old_d.arg_value("fields")},
                            )
                        )
                elif fed_name == "override":
                    changes.append(
                        make_change(
                            ChangeCode.APPLIED_DIRECTIVE_ARG_CHANGED,
                            path,
                            f"@override changed from {old_d.signature} to {new_d.signature}",
                            old_value=old_d.signature,
                            new_value=new_d.signature,
                            meta={"directive": "override"},
                        )
                    )

            # Detect field-set changes for requires/provides that appear as remove+add
            # (already handled via removed/added above with specific codes)

        # Detect requires/provides fields changes when only fields arg differs
        # but signature still has same directive name count — handled via match by fields

    return changes


def is_federation_directive_name(name: str) -> bool:
    return name in FED_DIRECTIVES
