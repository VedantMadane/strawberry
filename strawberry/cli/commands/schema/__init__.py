"""CLI subcommands under ``strawberry schema``."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer

from strawberry.cli.app import app
from strawberry.schema_registry.api import diff_schemas
from strawberry.schema_registry.config import SchemaDiffConfig
from strawberry.schema_registry.formatters import format_diff_markdown, format_diff_rich
from strawberry.schema_registry.types import ChangeKind, Severity

schema_app = typer.Typer(
    name="schema",
    help="Schema evolution utilities (diff, lint, changelog).",
    no_args_is_help=True,
)
app.add_typer(schema_app, name="schema")


def _load_config(
    ignore_code: list[str] | None,
    ignore_path: list[str] | None,
    severity_override: list[str] | None,
) -> SchemaDiffConfig:
    ignore_kinds: set[ChangeKind] = set()
    for code in ignore_code or []:
        try:
            ignore_kinds.add(ChangeKind(code))
        except ValueError as exc:
            raise typer.BadParameter(f"Unknown change code: {code}") from exc

    overrides: dict[ChangeKind, Severity] = {}
    for item in severity_override or []:
        # format: CODE=severity
        if "=" not in item:
            raise typer.BadParameter(
                f"Severity override must be CODE=severity, got: {item}"
            )
        code_s, sev_s = item.split("=", 1)
        try:
            kind = ChangeKind(code_s)
            sev = Severity(sev_s.lower())
        except ValueError as exc:
            raise typer.BadParameter(f"Invalid override '{item}': {exc}") from exc
        overrides[kind] = sev

    return SchemaDiffConfig(
        ignore_change_kinds=ignore_kinds,
        ignore_path_patterns=list(ignore_path or []),
        severity_overrides=overrides,
    )


@schema_app.command("diff")
def schema_diff(
    old: Path = typer.Argument(..., help="Old schema file (.graphql) or path."),
    new: Path = typer.Argument(..., help="New schema file (.graphql) or path."),
    output: Optional[str] = typer.Option(
        "term",
        "--output",
        "-o",
        help="Output format: 'term' (rich coloured table) or 'markdown'.",
    ),
    ignore_code: Optional[list[str]] = typer.Option(
        None,
        "--ignore-code",
        help="Change code(s) to ignore (repeatable). Example: TYPE_DESCRIPTION_CHANGED",
    ),
    ignore_path: Optional[list[str]] = typer.Option(
        None,
        "--ignore-path",
        help="Regex for schema paths to ignore (repeatable). Example: '.*\\._.*'",
    ),
    severity_override: Optional[list[str]] = typer.Option(
        None,
        "--severity",
        help="Override severity as CODE=severity (repeatable). Example: FIELD_ADDED=breaking",
    ),
    fail_on_breaking: bool = typer.Option(
        False,
        "--fail-on-breaking",
        help="Exit with code 1 when any breaking changes are present.",
    ),
) -> None:
    """Compare two GraphQL schemas and report structural differences.

    Example::

        strawberry schema diff old.graphql new.graphql
        strawberry schema diff old.graphql new.graphql --output=markdown
    """
    if not old.is_file():
        typer.echo(f"Old schema not found: {old}", err=True)
        raise typer.Exit(code=2)
    if not new.is_file():
        typer.echo(f"New schema not found: {new}", err=True)
        raise typer.Exit(code=2)

    config = _load_config(ignore_code, ignore_path, severity_override)
    result = diff_schemas(old, new, config=config)

    fmt = (output or "term").lower()
    if fmt in {"markdown", "md"}:
        sys.stdout.write(format_diff_markdown(result))
    elif fmt in {"term", "terminal", "rich"}:
        format_diff_rich(result)
    else:
        typer.echo(f"Unknown output format: {output}", err=True)
        raise typer.Exit(code=2)

    if fail_on_breaking and result.has_breaking:
        raise typer.Exit(code=1)
