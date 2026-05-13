"""``commitlens`` command-line entry point.

This module is intentionally thin — it parses flags, calls into
``git_log``, ``aggregate``, and ``render``, and exits. Keeping the
business logic out of here makes every other module unit-testable
without invoking Click.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console

from . import __version__
from .aggregate import aggregate, co_change_pairs
from .git_log import GitError, collect_commits


@click.command(
    context_settings={"help_option_names": ["-h", "--help"]},
    epilog="Examples: 'commitlens --since 30d', 'commitlens src/ --top 30 --json'",
)
@click.argument(
    "repo_path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=".",
    metavar="[REPO_PATH]",
)
@click.option(
    "--since",
    default="90d",
    show_default=True,
    help="Time window. Accepts any expression `git log --since=` understands (90d, 2 weeks, 2025-01-01).",
)
@click.option(
    "--top",
    type=click.IntRange(min=1),
    default=20,
    show_default=True,
    help="Number of files to show in the churn table.",
)
@click.option(
    "--min-cochange",
    type=click.IntRange(min=2),
    default=4,
    show_default=True,
    help="Minimum shared commits to flag a co-change pair.",
)
@click.option(
    "--no-clusters",
    is_flag=True,
    help="Skip co-change cluster analysis (faster on huge repos).",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit JSON instead of the Rich-rendered TUI.",
)
@click.version_option(__version__, "--version", prog_name="commitlens")
def main(
    repo_path: Path,
    since: str,
    top: int,
    min_cochange: int,
    no_clusters: bool,
    as_json: bool,
) -> None:
    """Analyze a git repository's recent commit activity.

    REPO_PATH defaults to the current directory. A subpath restricts the
    analysis to that subtree (e.g. ``commitlens src/``).
    """
    abs_path = repo_path.resolve()
    repo_root, scope = _split_repo_and_scope(abs_path)
    repo_label = _repo_label(repo_root, scope)

    try:
        commits = collect_commits(repo_root, since=since, path_scope=scope)
    except GitError as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(1)

    files, authors, stats = aggregate(commits)
    pairs = [] if no_clusters else co_change_pairs(commits, min_shared=min_cochange)

    if as_json:
        _emit_json(
            repo_label=repo_label,
            since=since,
            files=files,
            authors=authors,
            pairs=pairs,
            stats=stats,
            top=top,
        )
        return

    # Late import keeps the JSON path from paying the Rich import cost.
    from .render import render_report

    render_report(
        Console(),
        repo_label=repo_label,
        since=since,
        files=files,
        authors=authors,
        pairs=pairs,
        stats=stats,
        top=top,
    )


def _split_repo_and_scope(abs_path: Path) -> tuple[Path, str | None]:
    """Locate the repo root and the subpath the user pointed at (if any)."""
    current = abs_path
    while True:
        if (current / ".git").exists():
            scope = abs_path.relative_to(current).as_posix() if abs_path != current else None
            return current, scope or None
        if current.parent == current:
            raise click.ClickException(
                f"{abs_path} is not inside a git repository."
            )
        current = current.parent


def _repo_label(repo_root: Path, scope: str | None) -> str:
    name = repo_root.name or str(repo_root)
    return f"{name}/{scope}" if scope else name


def _emit_json(
    *,
    repo_label: str,
    since: str | None,
    files,
    authors,
    pairs,
    stats,
    top: int,
) -> None:
    payload = {
        "repo": repo_label,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "since": since,
        "stats": {
            "commits": stats.commits,
            "authors": stats.authors,
            "files_touched": stats.files,
        },
        "files": [_dump(fc) for fc in files[:top]],
        "authors": [_dump(a) for a in authors],
        "co_change_pairs": [_dump(p) for p in pairs],
    }
    click.echo(json.dumps(payload, indent=2, default=_json_default))


def _dump(obj):
    if is_dataclass(obj):
        d = asdict(obj)
        # Sets aren't JSON-serializable; aggregate.py stores authors/files as sets.
        for k, v in list(d.items()):
            if isinstance(v, set):
                d[k] = sorted(v)
        return d
    return obj


def _json_default(obj):
    if isinstance(obj, datetime):
        return obj.astimezone().isoformat(timespec="seconds")
    if isinstance(obj, set):
        return sorted(obj)
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")


if __name__ == "__main__":  # pragma: no cover - module guard
    main()
