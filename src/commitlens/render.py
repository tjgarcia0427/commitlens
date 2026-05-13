"""Rich-rendered report output.

Kept deliberately separate from :mod:`aggregate` so the aggregation layer
stays pure-Python and unit-testable without a terminal.
"""
from __future__ import annotations

from datetime import datetime, timezone

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .aggregate import AuthorActivity, CoChangePair, CorpusStats, FileChurn


def render_report(
    console: Console,
    *,
    repo_label: str,
    since: str | None,
    files: list[FileChurn],
    authors: list[AuthorActivity],
    pairs: list[CoChangePair],
    stats: CorpusStats,
    top: int,
) -> None:
    """Print the full report to ``console``."""
    _render_header(console, repo_label=repo_label, since=since, stats=stats)
    if stats.is_empty:
        console.print(
            "[yellow]No commits in the requested window. Try a wider --since.[/yellow]"
        )
        return
    _render_file_table(console, files=files, top=top)
    _render_author_table(console, authors=authors)
    if pairs:
        _render_cochange(console, pairs=pairs)


def _render_header(
    console: Console,
    *,
    repo_label: str,
    since: str | None,
    stats: CorpusStats,
) -> None:
    window = f"last {since}" if since else "full history"
    summary = (
        f"[bold]{stats.commits}[/bold] commits  ·  "
        f"[bold]{stats.authors}[/bold] author"
        + ("s" if stats.authors != 1 else "")
        + f"  ·  [bold]{stats.files}[/bold] files touched"
    )
    console.print(
        Panel.fit(
            summary,
            title=f"[bold cyan]commitlens[/bold cyan]  ·  {repo_label}  ·  {window}",
            border_style="cyan",
        )
    )


def _render_file_table(console: Console, *, files: list[FileChurn], top: int) -> None:
    table = Table(
        title=f"Top {min(top, len(files))} churned files",
        title_justify="left",
        show_lines=False,
        header_style="bold magenta",
    )
    table.add_column("Path")
    table.add_column("±Lines", justify="right")
    table.add_column("Commits", justify="right")
    table.add_column("Authors", justify="right")
    table.add_column("Last touched", justify="right")

    now = datetime.now(timezone.utc)
    for fc in files[:top]:
        last = fc.last_touched
        if last is None:
            last_str = "—"
        else:
            days = max(0, (now - last).days)
            last_str = "today" if days == 0 else f"{days}d ago"
        table.add_row(
            fc.path,
            f"{fc.total_lines:,}",
            str(fc.commits),
            str(fc.distinct_authors),
            last_str,
        )
    console.print(table)


def _render_author_table(console: Console, *, authors: list[AuthorActivity]) -> None:
    table = Table(
        title="Author activity",
        title_justify="left",
        show_lines=False,
        header_style="bold magenta",
    )
    table.add_column("Author")
    table.add_column("Commits", justify="right")
    table.add_column("±Lines", justify="right")
    table.add_column("Distinct files", justify="right")

    for author in authors[:15]:
        table.add_row(
            author.name,
            str(author.commits),
            f"{author.total_lines:,}",
            str(author.distinct_files),
        )
    console.print(table)


def _render_cochange(console: Console, *, pairs: list[CoChangePair]) -> None:
    table = Table(
        title="Co-change clusters",
        title_justify="left",
        show_lines=False,
        header_style="bold magenta",
    )
    table.add_column("File A")
    table.add_column("File B")
    table.add_column("Shared commits", justify="right")

    for pair in pairs[:20]:
        table.add_row(pair.file_a, pair.file_b, str(pair.shared_commits))
    console.print(table)
