"""Terminal and markdown report formatters for schema diffs."""

from __future__ import annotations

from .models import ChangeSeverity, SchemaChange, SchemaDiffResult

_SEVERITY_EMOJI = {
    ChangeSeverity.BREAKING: "\u274c",
    ChangeSeverity.DANGEROUS: "\u26a0\ufe0f",
    ChangeSeverity.SAFE: "\u2705",
}

_SEVERITY_RICH_STYLE = {
    ChangeSeverity.BREAKING: "bold red",
    ChangeSeverity.DANGEROUS: "bold yellow",
    ChangeSeverity.SAFE: "bold green",
}


def format_terminal(result: SchemaDiffResult, *, use_rich: bool = True) -> str:
    """Format a schema diff as coloured terminal output.

    Falls back to plain text when ``rich`` is unavailable or ``use_rich`` is False.
    """
    if use_rich:
        try:
            return _format_rich(result)
        except ImportError:
            pass
    return _format_plain(result)


def _format_plain(result: SchemaDiffResult) -> str:
    lines: list[str] = []
    summary = result.summary()
    lines.append("Schema Diff Summary")
    lines.append("=" * 40)
    lines.append(
        f"  Breaking:  {summary['breaking']}  |  "
        f"Dangerous: {summary['dangerous']}  |  "
        f"Safe: {summary['safe']}  |  "
        f"Total: {summary['total']}"
    )
    lines.append("")

    if not result.changes:
        lines.append("No schema changes detected.")
        return "\n".join(lines)

    current_sev: ChangeSeverity | None = None
    for change in result.changes:
        if change.severity != current_sev:
            current_sev = change.severity
            lines.append("")
            lines.append(f"--- {current_sev.value} ---")
        emoji = _SEVERITY_EMOJI.get(change.severity, "")
        lines.append(
            f"  {emoji} [{change.code.value}] {change.path}"
        )
        lines.append(f"      {change.message}")

    return "\n".join(lines)


def _format_rich(result: SchemaDiffResult) -> str:
    from io import StringIO

    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    buf = StringIO()
    console = Console(file=buf, force_terminal=True, width=100, color_system="truecolor")

    summary = result.summary()
    header = Text()
    header.append("Schema Diff Summary\n", style="bold")
    header.append(f"  Breaking:  {summary['breaking']}", style="bold red")
    header.append("  |  ")
    header.append(f"Dangerous: {summary['dangerous']}", style="bold yellow")
    header.append("  |  ")
    header.append(f"Safe: {summary['safe']}", style="bold green")
    header.append("  |  ")
    header.append(f"Total: {summary['total']}", style="bold")

    console.print(Panel(header, title="strawberry schema diff", border_style="cyan"))

    if not result.changes:
        console.print("[green]No schema changes detected.[/green]")
        return buf.getvalue()

    table = Table(show_header=True, header_style="bold", expand=True)
    table.add_column("Severity", style="bold", width=12)
    table.add_column("Code", width=32)
    table.add_column("Path", width=28)
    table.add_column("Message")

    for change in result.changes:
        sev_style = _SEVERITY_RICH_STYLE.get(change.severity, "")
        table.add_row(
            f"[{sev_style}]{change.severity.value}[/{sev_style}]",
            change.code.value,
            change.path,
            change.message,
        )

    console.print(table)
    return buf.getvalue()


def format_markdown(result: SchemaDiffResult) -> str:
    """Format a schema diff as a GitHub PR-compatible markdown table."""
    lines: list[str] = []
    summary = result.summary()

    lines.append("## Schema Diff")
    lines.append("")
    lines.append("| Severity | Count |")
    lines.append("|----------|------:|")
    lines.append(f"| :x: Breaking | {summary['breaking']} |")
    lines.append(f"| :warning: Dangerous | {summary['dangerous']} |")
    lines.append(f"| :white_check_mark: Safe | {summary['safe']} |")
    lines.append(f"| **Total** | **{summary['total']}** |")
    lines.append("")

    if result.has_breaking:
        lines.append("> :no_entry: **This PR introduces breaking schema changes.**")
        lines.append("")
    elif result.has_dangerous:
        lines.append("> :warning: **This PR introduces dangerous schema changes.**")
        lines.append("")
    elif not result.changes:
        lines.append("> :white_check_mark: **No schema changes detected.**")
        lines.append("")
        return "\n".join(lines)

    lines.append("### Changes")
    lines.append("")
    lines.append("| Severity | Code | Path | Message |")
    lines.append("|----------|------|------|---------|")

    for change in result.changes:
        icon = {
            ChangeSeverity.BREAKING: ":x:",
            ChangeSeverity.DANGEROUS: ":warning:",
            ChangeSeverity.SAFE: ":white_check_mark:",
        }.get(change.severity, "")
        # Escape pipe characters in message/path for markdown tables
        path = change.path.replace("|", "\\|")
        message = change.message.replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {icon} {change.severity.value} "
            f"| `{change.code.value}` "
            f"| `{path}` "
            f"| {message} |"
        )

    lines.append("")
    return "\n".join(lines)


def print_terminal(result: SchemaDiffResult) -> None:
    """Print a coloured terminal report to stdout."""
    try:
        from rich.console import Console

        summary = result.summary()
        console = Console()

        header = (
            f"[bold]Schema Diff[/bold]  "
            f"[bold red]Breaking: {summary['breaking']}[/bold red]  "
            f"[bold yellow]Dangerous: {summary['dangerous']}[/bold yellow]  "
            f"[bold green]Safe: {summary['safe']}[/bold green]  "
            f"Total: {summary['total']}"
        )
        console.print(header)
        console.print()

        if not result.changes:
            console.print("[green]No schema changes detected.[/green]")
            return

        table_rows: list[tuple[str, str, str, str]] = []
        for change in result.changes:
            style = _SEVERITY_RICH_STYLE.get(change.severity, "")
            table_rows.append(
                (
                    f"[{style}]{change.severity.value}[/{style}]",
                    change.code.value,
                    change.path,
                    change.message,
                )
            )

        from rich.table import Table

        table = Table(show_header=True, header_style="bold cyan", expand=True)
        table.add_column("Severity", width=12)
        table.add_column("Code", width=32)
        table.add_column("Path", width=28)
        table.add_column("Message")
        for row in table_rows:
            table.add_row(*row)
        console.print(table)
    except ImportError:
        print(_format_plain(result))  # noqa: T201
