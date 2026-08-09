from re import Pattern
"""CLI command: strawberry schema diff <old> <new>."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional, cast

import typer

from strawberry.cli.app import app
from strawberry.schema_diff import (
    ChangeCode,
    ChangeSeverity,
    SchemaDiffConfig,
    diff_schemas,
)
from strawberry.schema_diff.report import format_markdown, print_terminal


class OutputFormat(str, Enum):
    terminal = "terminal"
    markdown = "markdown"
    json = "json"


def _load_schema_source(source: str, app_dir: str) -> str | object:
    """Load a schema from an SDL file path, module:attr path, or inline SDL."""
    path = Path(source)
    if path.exists() and path.is_file():
        content = path.read_text(encoding="utf-8")
        # Heuristic: .graphql/.gql files are always SDL
        if path.suffix in (".graphql", ".gql", ".sdl"):
            return content
        # .py files or module paths handled below
        if path.suffix == ".py":
            # Treat as module path relative to app_dir
            pass
        else:
            # Assume SDL for unknown extensions with type/schema keywords
            if "type " in content or "schema " in content or "scalar " in content:
                return content

    # Try loading as strawberry schema module path (e.g. myapp.schema:schema)
    if ":" in source or (not path.exists() and "." in source):
        try:
            from strawberry.cli.utils import load_schema

            return load_schema(source, app_dir)
        except (SystemExit, Exception):
            pass

    # Fall back: if file exists, treat as SDL
    if path.exists():
        return path.read_text(encoding="utf-8")

    # Maybe the source itself is inline SDL
    if "type " in source or source.strip().startswith("schema"):
        return source

    # Last attempt: module path
    from strawberry.cli.utils import load_schema

    return load_schema(source, app_dir)


def _build_config(
    ignore_code: list[str] | None,
    ignore_field: list[str] | None,
    ignore_type: list[str] | None,
    severity_override: list[str] | None,
    include_descriptions: bool,
) -> SchemaDiffConfig:
    ignore_codes: set[str] = set(ignore_code or [])
    ignore_field_patterns: list[str] = list(ignore_field or [])
    ignore_type_patterns: list[str] = list(ignore_type or [])
    severity_overrides: dict[str, str] = {}

    for item in severity_override or []:
        # Format: CODE=SEVERITY
        if "=" not in item:
            raise typer.BadParameter(
                f"Invalid severity override '{item}'. Expected CODE=SEVERITY"
            )
        code, sev = item.split("=", 1)
        severity_overrides[code.strip()] = sev.strip().upper()

    return SchemaDiffConfig(
        ignore_codes=ignore_codes,  # type: ignore[arg-type]
        ignore_field_patterns=cast(list[str | Pattern[str]], ignore_field_patterns),
        ignore_type_patterns=cast(list[str | Pattern[str]], ignore_type_patterns),
        severity_overrides=severity_overrides,  # type: ignore[arg-type]
        include_descriptions=include_descriptions,
    )


# Create a sub-app for `strawberry schema ...`
schema_app = typer.Typer(no_args_is_help=True, help="Schema-related commands")
app.add_typer(schema_app, name="schema")


@schema_app.command("diff", help="Compare two GraphQL schemas and report changes")
def schema_diff(
    old: str = typer.Argument(
        ...,
        help="Old/baseline schema: path to .graphql file, module:attr, or SDL",
    ),
    new: str = typer.Argument(
        ...,
        help="New/candidate schema: path to .graphql file, module:attr, or SDL",
    ),
    app_dir: str = typer.Option(
        ".",
        "--app-dir",
        show_default=True,
        help="Directory to add to PYTHONPATH when loading Python schemas",
    ),
    output: OutputFormat = typer.Option(
        OutputFormat.terminal,
        "--output",
        "-o",
        help="Output format: terminal (coloured), markdown (PR table), or json",
    ),
    output_file: Optional[Path] = typer.Option(
        None,
        "--output-file",
        "-f",
        help="Write output to a file instead of stdout",
    ),
    ignore_code: Optional[list[str]] = typer.Option(
        None,
        "--ignore-code",
        help="Change code to ignore (repeatable), e.g. TYPE_DESCRIPTION_CHANGED",
    ),
    ignore_field: Optional[list[str]] = typer.Option(
        None,
        "--ignore-field",
        help="Regex for field paths to ignore (repeatable), e.g. '\\._' for _prefixed",
    ),
    ignore_type: Optional[list[str]] = typer.Option(
        None,
        "--ignore-type",
        help="Regex for type names to ignore (repeatable)",
    ),
    severity_override: Optional[list[str]] = typer.Option(
        None,
        "--severity",
        help="Override severity as CODE=SEVERITY (repeatable), e.g. FIELD_ADDED=DANGEROUS",
    ),
    no_descriptions: bool = typer.Option(
        False,
        "--no-descriptions",
        help="Suppress description-only changes",
    ),
    fail_on_breaking: bool = typer.Option(
        True,
        "--fail-on-breaking/--no-fail-on-breaking",
        help="Exit with code 1 when breaking changes are found (default: true)",
    ),
    fail_on_dangerous: bool = typer.Option(
        False,
        "--fail-on-dangerous/--no-fail-on-dangerous",
        help="Exit with code 1 when dangerous changes are found",
    ),
) -> None:
    """Diff two GraphQL schemas and print a structured report.

    Examples::

        strawberry schema diff old.graphql new.graphql
        strawberry schema diff old.graphql new.graphql --output=markdown
        strawberry schema diff myapp.schema:schema myapp.schema_v2:schema
        strawberry schema diff old.graphql new.graphql --ignore-field '\\._'
    """
    config = _build_config(
        ignore_code=ignore_code,
        ignore_field=ignore_field,
        ignore_type=ignore_type,
        severity_override=severity_override,
        include_descriptions=not no_descriptions,
    )

    try:
        old_schema = _load_schema_source(old, app_dir)
        new_schema = _load_schema_source(new, app_dir)
    except Exception as exc:
        typer.echo(f"Error loading schema: {exc}", err=True)
        raise typer.Exit(2) from exc

    try:
        result = diff_schemas(old_schema, new_schema, config=config)
    except Exception as exc:
        typer.echo(f"Error diffing schemas: {exc}", err=True)
        raise typer.Exit(2) from exc

    if output == OutputFormat.markdown:
        text = format_markdown(result)
        if output_file:
            output_file.write_text(text, encoding="utf-8")
            typer.echo(f"Markdown report written to {output_file}")
        else:
            typer.echo(text)
    elif output == OutputFormat.json:
        import json

        text = json.dumps(result.to_dict(), indent=2)
        if output_file:
            output_file.write_text(text, encoding="utf-8")
            typer.echo(f"JSON report written to {output_file}")
        else:
            typer.echo(text)
    else:
        if output_file:
            from strawberry.schema_diff.report import format_terminal

            output_file.write_text(
                format_terminal(result, use_rich=False), encoding="utf-8"
            )
            typer.echo(f"Report written to {output_file}")
        else:
            print_terminal(result)

    exit_code = 0
    if fail_on_breaking and result.has_breaking:
        exit_code = 1
    elif fail_on_dangerous and result.has_dangerous:
        exit_code = 1

    if exit_code != 0:
        raise typer.Exit(exit_code)
