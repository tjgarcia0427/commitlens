"""Aggregate parsed commits into the metrics we report on.

Three views are computed from one pass over the commit stream:

1. ``FileChurn`` per file path — total ±lines, distinct commits, distinct
   authors, last-touched datetime.
2. ``AuthorActivity`` per author — total ±lines, commit count, files
   touched.
3. ``co_change_pairs`` — pairs of files frequently changed in the same
   commit, sorted by descending shared-commit count.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from itertools import combinations
from typing import Iterable

from .git_log import Commit


@dataclass
class FileChurn:
    path: str
    additions: int = 0
    deletions: int = 0
    commits: int = 0
    authors: set[str] = field(default_factory=set)
    last_touched: datetime | None = None

    @property
    def total_lines(self) -> int:
        return self.additions + self.deletions

    @property
    def distinct_authors(self) -> int:
        return len(self.authors)


@dataclass
class AuthorActivity:
    name: str
    additions: int = 0
    deletions: int = 0
    commits: int = 0
    files: set[str] = field(default_factory=set)

    @property
    def total_lines(self) -> int:
        return self.additions + self.deletions

    @property
    def distinct_files(self) -> int:
        return len(self.files)


@dataclass
class CoChangePair:
    file_a: str
    file_b: str
    shared_commits: int


@dataclass
class CorpusStats:
    commits: int
    authors: int
    files: int

    @property
    def is_empty(self) -> bool:
        return self.commits == 0


def aggregate(commits: Iterable[Commit]) -> tuple[
    list[FileChurn], list[AuthorActivity], CorpusStats
]:
    """Compute file and author aggregates plus headline corpus stats."""
    files: dict[str, FileChurn] = {}
    authors: dict[str, AuthorActivity] = {}
    commit_count = 0

    for commit in commits:
        commit_count += 1
        author = authors.setdefault(commit.author, AuthorActivity(name=commit.author))
        author.commits += 1
        for fc in commit.files:
            churn = files.setdefault(fc.path, FileChurn(path=fc.path))
            churn.additions += fc.additions
            churn.deletions += fc.deletions
            churn.commits += 1
            churn.authors.add(commit.author)
            if churn.last_touched is None or commit.when > churn.last_touched:
                churn.last_touched = commit.when

            author.additions += fc.additions
            author.deletions += fc.deletions
            author.files.add(fc.path)

    file_list = sorted(files.values(), key=lambda c: c.total_lines, reverse=True)
    author_list = sorted(authors.values(), key=lambda a: a.commits, reverse=True)
    stats = CorpusStats(
        commits=commit_count, authors=len(authors), files=len(files)
    )
    return file_list, author_list, stats


def co_change_pairs(
    commits: Iterable[Commit],
    *,
    min_shared: int = 4,
    max_files_per_commit: int = 25,
) -> list[CoChangePair]:
    """Find pairs of files that change together at least `min_shared` times.

    Commits touching more than ``max_files_per_commit`` files are skipped —
    they're typically refactors / formatter sweeps that would create
    O(n²) noise and inflate every pair count.
    """
    pair_counts: dict[tuple[str, str], int] = defaultdict(int)
    for commit in commits:
        paths = sorted({fc.path for fc in commit.files})
        if not paths or len(paths) > max_files_per_commit:
            continue
        for a, b in combinations(paths, 2):
            pair_counts[(a, b)] += 1

    pairs = [
        CoChangePair(file_a=a, file_b=b, shared_commits=count)
        for (a, b), count in pair_counts.items()
        if count >= min_shared
    ]
    pairs.sort(key=lambda p: (p.shared_commits, p.file_a, p.file_b), reverse=True)
    return pairs
