"""Output formatters for schema diffs (rich terminal + markdown)."""

from __future__ import annotations

from strawberry.schema_registry.types import DiffEntry, SchemaDiff, Severity

_SEVERITY_STYLE = {
    Severity.BREAKING: "bold red",
    Severity.DANGEROUS: "bold yellow",
    Severity.SAFE: "green",
}

_SEVERITY_EMOJI = {
    Severity.BREAKING: "BREAKING",
    Severity.DANGEROUS: "DANGEROUS",
    Severity.SAFE: "SAFE",
}


def format_diff_rich(diff: SchemaDiff) -> None:
    """Print a coloured summary to the terminal via ``rich``."""
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.text import Text
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "The 'rich' package is required for terminal output. "
            "Install it with: pip install rich"
        ) from exc

    console = Console()

    if not diff.entries:
        console.print("[bold green]No schema changes detected.[/bold green]")
        return

    # Summary line
    console.print(
        f"[bold]Schema diff summary:[/bold] "
        f"[red]{len(diff.breaking)} breaking[/red], "
        f"[yellow]{len(diff.dangerous)} dangerous[/yellow], "
        f"[green]{len(diff.safe)} safe[/green] "
        f"({len(diff.entries)} total)"
    )
    console.print()

    table = Table(show_header=True, header_style="bold", expand=True)
    table.add_column("Severity", style="bold", width=12)
    table.add_column("Code", width=32)
    table.add_column("Path", width=28)
    table.add_column("Message")

    for entry in diff.entries:
        sev_label = Text(
            _SEVERITY_EMOJI[entry.severity],
            style=_SEVERITY_STYLE[entry.severity],
        )
        table.add_row(
            sev_label,
            entry.change_kind.value,
            entry.path,
            entry.message,
        )

    console.print(table)


def format_diff_markdown(diff: SchemaDiff) -> str:
    """Return a GitHub-PR compatible markdown table of the diff."""
    lines: list[str] = []
    lines.append("## Schema Diff")
    lines.append("")
    lines.append(
        f"**Summary:** {len(diff.breaking)} breaking · "
        f"{len(diff.dangerous)} dangerous · {len(diff.safe)} safe "
        f"({len(diff.entries)} total)"
    )
    lines.append("")

    if not diff.entries:
        lines.append("_No schema changes detected._")
        return "\n".join(lines) + "\n"

    lines.append("| Severity | Code | Path | Message |")
    lines.append("| --- | --- | --- | --- |")
    for entry in diff.entries:
        msg = entry.message.replace("|", "\\|")
        path = entry.path.replace("|", "\\|")
        lines.append(
            f"| {entry.severity.value} | `{entry.change_kind.value}` "
            f"| `{path}` | {msg} |"
        )
    lines.append("")
    return "\n".join(lines)
