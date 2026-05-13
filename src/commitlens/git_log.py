"""Thin wrapper around `git log --numstat` plus a parser for its output.

We deliberately avoid GitPython / pygit2 / dulwich. The plumbing output of
`git` is stable across versions and gives us everything we need with no
third-party dependency.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator


# Each commit is delimited by a NUL byte so the parser doesn't have to guess
# where a commit ends. The header line uses tab as the separator between
# fields so it can't collide with file paths (git already escapes tabs).
_RECORD_SEP = "\x00"
_FIELD_SEP = "\x09"  # literal TAB
_LOG_FORMAT = f"%x00%H{_FIELD_SEP}%an{_FIELD_SEP}%aI"


class GitError(RuntimeError):
    """Raised when git is missing, the path isn't a repo, or git exits non-zero."""


@dataclass(frozen=True)
class FileChange:
    """One file touched in one commit."""

    path: str
    additions: int
    deletions: int

    @property
    def total(self) -> int:
        return self.additions + self.deletions


@dataclass(frozen=True)
class Commit:
    """One commit and the files it changed."""

    sha: str
    author: str
    when: datetime
    files: tuple[FileChange, ...]

    @property
    def total_lines(self) -> int:
        return sum(f.total for f in self.files)


def run_git_log(
    repo: Path,
    *,
    since: str | None = None,
    path_scope: str | None = None,
) -> str:
    """Invoke `git log --numstat ...` and return the raw output."""
    if shutil.which("git") is None:
        raise GitError("git executable not found on PATH")

    args = [
        "git",
        "-C",
        str(repo),
        "log",
        "--numstat",
        f"--pretty=format:{_LOG_FORMAT}",
        "--no-merges",
        # Without an explicit encoding, git on Windows can emit author names in
        # cp1252. Force utf-8 so the Python decode step below is reliable.
        "--encoding=utf-8",
    ]
    if since:
        args += [f"--since={since}"]
    if path_scope:
        args += ["--", path_scope]

    proc = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        stderr = proc.stderr.strip() or "git returned a non-zero exit code"
        raise GitError(stderr)
    return proc.stdout


def parse_log(raw: str) -> Iterator[Commit]:
    """Yield Commit records from the raw `git log --numstat` output.

    The parser is deliberately permissive about edge cases:

    - Binary files appear as ``- - path`` (dashes instead of integers). We
      surface those with ``additions = deletions = 0`` so they still count
      toward commit-touch metrics but don't skew ±lines.
    - Renames appear as ``a => b`` or ``{old => new}/path``. We canonicalize
      to the NEW path so churn aggregates against the live filename.
    - Empty commits (no file changes) still yield a Commit with no files.
    """
    if not raw:
        return

    # Each commit chunk starts with our NUL marker. The first split is empty
    # if the output begins with NUL, so filter that.
    for chunk in raw.split(_RECORD_SEP):
        chunk = chunk.strip("\n")
        if not chunk:
            continue
        lines = chunk.split("\n")
        header = lines[0]
        parts = header.split(_FIELD_SEP)
        if len(parts) < 3:
            continue  # malformed; skip rather than crash
        sha, author, when_str = parts[0], parts[1], parts[2]
        try:
            when = datetime.fromisoformat(when_str)
        except ValueError:
            continue

        files: list[FileChange] = []
        for raw_line in lines[1:]:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            files.append(_parse_numstat_line(raw_line))

        yield Commit(sha=sha, author=author, when=when, files=tuple(files))


def _parse_numstat_line(line: str) -> FileChange:
    """Parse one ``--numstat`` line: ``<adds>\\t<dels>\\t<path>``."""
    fields = line.split(_FIELD_SEP, 2)
    if len(fields) < 3:
        # Fallback: collapse repeated whitespace
        fields = line.split(None, 2)
    if len(fields) < 3:
        return FileChange(path=line, additions=0, deletions=0)
    adds_raw, dels_raw, path = fields
    adds = _safe_int(adds_raw)
    dels = _safe_int(dels_raw)
    return FileChange(path=_canonicalize_path(path), additions=adds, deletions=dels)


def _safe_int(s: str) -> int:
    try:
        return int(s)
    except (TypeError, ValueError):
        return 0  # binary files show "-" in numstat


def _canonicalize_path(path: str) -> str:
    """For renames, prefer the NEW path so aggregation tracks the live name."""
    # Two rename shapes git uses:
    #   1) "old/path => new/path"
    #   2) "shared/{old => new}/tail"
    if " => " in path:
        if "{" in path and "}" in path:
            # Brace form
            prefix, _, rest = path.partition("{")
            inner, _, suffix = rest.partition("}")
            _, _, new = inner.partition(" => ")
            return (prefix + new + suffix).replace("//", "/")
        # Simple "old => new"
        _, _, new = path.partition(" => ")
        return new.strip()
    return path


def collect_commits(
    repo: Path,
    *,
    since: str | None = None,
    path_scope: str | None = None,
) -> list[Commit]:
    """Convenience: run git log and materialize the parsed commits."""
    raw = run_git_log(repo, since=since, path_scope=path_scope)
    return list(parse_log(raw))
