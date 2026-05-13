"""Parser tests for git_log.

We build raw `git log --numstat` strings by hand so the tests don't need a
real git binary or repo. The format mirrors what
``--pretty=format:%x00%H%x09%an%x09%aI`` produces.
"""
from __future__ import annotations

from datetime import datetime

from commitlens.git_log import (
    FileChange,
    _canonicalize_path,
    _parse_numstat_line,
    parse_log,
)


def make_chunk(sha: str, author: str, when: str, numstat_lines: list[str]) -> str:
    header = f"\x00{sha}\x09{author}\x09{when}"
    body = "\n".join(numstat_lines)
    return f"{header}\n{body}\n"


# ---------------------------------------------------------------------------


class TestNumstatLine:
    def test_basic(self):
        fc = _parse_numstat_line("5\t3\tsrc/foo.py")
        assert fc == FileChange(path="src/foo.py", additions=5, deletions=3)

    def test_binary_file(self):
        fc = _parse_numstat_line("-\t-\tassets/logo.png")
        assert fc.additions == 0
        assert fc.deletions == 0
        assert fc.path == "assets/logo.png"

    def test_path_with_spaces(self):
        fc = _parse_numstat_line("10\t0\tdocs/A README.md")
        assert fc.path == "docs/A README.md"
        assert fc.additions == 10


class TestRenameCanonicalization:
    def test_simple_rename(self):
        assert _canonicalize_path("old/path.py => new/path.py") == "new/path.py"

    def test_brace_rename(self):
        # `src/{old => new}/foo.py` should resolve to `src/new/foo.py`
        assert _canonicalize_path("src/{old => new}/foo.py") == "src/new/foo.py"

    def test_no_rename_passthrough(self):
        assert _canonicalize_path("src/main.py") == "src/main.py"


class TestParseLog:
    def test_single_commit(self):
        raw = make_chunk(
            "abc123",
            "Alice",
            "2026-05-12T10:00:00+00:00",
            ["5\t3\tsrc/foo.py", "1\t0\tREADME.md"],
        )
        commits = list(parse_log(raw))
        assert len(commits) == 1
        c = commits[0]
        assert c.sha == "abc123"
        assert c.author == "Alice"
        assert c.when == datetime.fromisoformat("2026-05-12T10:00:00+00:00")
        assert len(c.files) == 2
        assert c.files[0].path == "src/foo.py"
        assert c.total_lines == 9

    def test_two_commits(self):
        raw = make_chunk(
            "aaa",
            "Alice",
            "2026-05-11T10:00:00+00:00",
            ["1\t1\ta.py"],
        ) + make_chunk(
            "bbb",
            "Bob",
            "2026-05-12T11:00:00+00:00",
            ["2\t0\tb.py"],
        )
        commits = list(parse_log(raw))
        assert [c.sha for c in commits] == ["aaa", "bbb"]
        assert [c.author for c in commits] == ["Alice", "Bob"]

    def test_empty_log_yields_nothing(self):
        assert list(parse_log("")) == []
        assert list(parse_log("\n\n\n")) == []

    def test_commit_with_no_files(self):
        # A `git commit --allow-empty` produces a header with zero numstat lines.
        raw = make_chunk("empty1", "Alice", "2026-05-12T10:00:00+00:00", [])
        commits = list(parse_log(raw))
        assert len(commits) == 1
        assert commits[0].files == ()

    def test_malformed_header_skipped(self):
        # Missing the timestamp field — parser should drop this chunk rather than crash.
        raw = "\x00deadbeef\x09Alice\n5\t0\tfoo.py\n"
        commits = list(parse_log(raw))
        assert commits == []

    def test_binary_file_in_commit(self):
        raw = make_chunk(
            "img1",
            "Alice",
            "2026-05-12T10:00:00+00:00",
            ["-\t-\tdocs/screenshot.png", "5\t0\tdocs/README.md"],
        )
        c = next(parse_log(raw))
        assert len(c.files) == 2
        binary, text = c.files
        assert binary.additions == 0 and binary.deletions == 0
        assert text.additions == 5

    def test_rename_canonicalized_in_commit(self):
        raw = make_chunk(
            "ren1",
            "Alice",
            "2026-05-12T10:00:00+00:00",
            ["3\t2\tsrc/{old => new}/feature.py"],
        )
        c = next(parse_log(raw))
        assert c.files[0].path == "src/new/feature.py"
