"""Aggregate tests — pure functions over Commit objects, no git required."""
from __future__ import annotations

from datetime import datetime, timezone

from commitlens.aggregate import aggregate, co_change_pairs
from commitlens.git_log import Commit, FileChange


def _commit(sha: str, author: str, day: int, files: list[tuple[str, int, int]]) -> Commit:
    return Commit(
        sha=sha,
        author=author,
        when=datetime(2026, 5, day, 12, 0, tzinfo=timezone.utc),
        files=tuple(FileChange(path=p, additions=a, deletions=d) for p, a, d in files),
    )


class TestAggregate:
    def test_file_churn_totals(self):
        commits = [
            _commit("aaa", "Alice", 1, [("src/foo.py", 5, 0)]),
            _commit("bbb", "Bob", 2, [("src/foo.py", 3, 2)]),
            _commit("ccc", "Alice", 3, [("src/bar.py", 10, 0)]),
        ]
        files, _, stats = aggregate(commits)
        by_path = {f.path: f for f in files}
        assert by_path["src/foo.py"].additions == 8
        assert by_path["src/foo.py"].deletions == 2
        assert by_path["src/foo.py"].commits == 2
        assert by_path["src/foo.py"].distinct_authors == 2
        assert by_path["src/bar.py"].distinct_authors == 1
        assert stats.commits == 3
        assert stats.authors == 2
        assert stats.files == 2

    def test_files_sorted_by_total_lines_desc(self):
        commits = [
            _commit("aaa", "Alice", 1, [("a.py", 50, 0)]),
            _commit("bbb", "Alice", 2, [("b.py", 60, 60)]),
            _commit("ccc", "Alice", 3, [("c.py", 10, 0)]),
        ]
        files, _, _ = aggregate(commits)
        assert [f.path for f in files] == ["b.py", "a.py", "c.py"]

    def test_last_touched_tracks_max_timestamp(self):
        commits = [
            _commit("old", "Alice", 1, [("foo.py", 1, 0)]),
            _commit("new", "Alice", 5, [("foo.py", 1, 0)]),
            _commit("mid", "Alice", 3, [("foo.py", 1, 0)]),
        ]
        files, _, _ = aggregate(commits)
        assert files[0].last_touched.day == 5

    def test_author_aggregation(self):
        commits = [
            _commit("aaa", "Alice", 1, [("foo.py", 5, 0), ("bar.py", 3, 0)]),
            _commit("bbb", "Bob", 2, [("foo.py", 1, 0)]),
            _commit("ccc", "Alice", 3, [("bar.py", 2, 1)]),
        ]
        _, authors, _ = aggregate(commits)
        by_name = {a.name: a for a in authors}
        assert by_name["Alice"].commits == 2
        assert by_name["Alice"].distinct_files == 2
        assert by_name["Bob"].commits == 1
        assert by_name["Bob"].distinct_files == 1

    def test_empty_corpus(self):
        files, authors, stats = aggregate([])
        assert files == []
        assert authors == []
        assert stats.is_empty


class TestCoChange:
    def test_finds_co_changing_pair(self):
        commits = [
            _commit(f"c{i}", "Alice", i + 1, [("a.py", 1, 0), ("b.py", 1, 0)])
            for i in range(5)
        ]
        pairs = co_change_pairs(commits, min_shared=4)
        assert len(pairs) == 1
        assert pairs[0].file_a == "a.py"
        assert pairs[0].file_b == "b.py"
        assert pairs[0].shared_commits == 5

    def test_below_threshold_dropped(self):
        commits = [
            _commit("c1", "Alice", 1, [("a.py", 1, 0), ("b.py", 1, 0)]),
            _commit("c2", "Alice", 2, [("a.py", 1, 0), ("b.py", 1, 0)]),
        ]
        # min_shared=4, only 2 shared commits — should be dropped
        assert co_change_pairs(commits, min_shared=4) == []

    def test_huge_commits_skipped(self):
        # A massive cross-file refactor shouldn't make every pair "co-change"
        huge = _commit(
            "huge",
            "Alice",
            1,
            [(f"f{i}.py", 1, 1) for i in range(30)],
        )
        commits = [huge] * 10
        # max_files_per_commit defaults to 25 → all our 30-file commits skipped
        assert co_change_pairs(commits, min_shared=4) == []

    def test_sort_descending_then_alphabetic(self):
        commits = [
            _commit("c1", "Alice", 1, [("a.py", 1, 0), ("b.py", 1, 0)]),
            _commit("c2", "Alice", 2, [("a.py", 1, 0), ("b.py", 1, 0)]),
            _commit("c3", "Alice", 3, [("a.py", 1, 0), ("b.py", 1, 0)]),
            _commit("c4", "Alice", 4, [("a.py", 1, 0), ("b.py", 1, 0)]),
            _commit("c5", "Alice", 5, [("x.py", 1, 0), ("y.py", 1, 0)]),
            _commit("c6", "Alice", 6, [("x.py", 1, 0), ("y.py", 1, 0)]),
            _commit("c7", "Alice", 7, [("x.py", 1, 0), ("y.py", 1, 0)]),
            _commit("c8", "Alice", 8, [("x.py", 1, 0), ("y.py", 1, 0)]),
            _commit("c9", "Alice", 9, [("x.py", 1, 0), ("y.py", 1, 0)]),
        ]
        pairs = co_change_pairs(commits, min_shared=4)
        # (x.py, y.py) has 5 shared > (a.py, b.py) with 4 shared
        assert pairs[0].file_a == "x.py"
        assert pairs[0].shared_commits == 5
        assert pairs[1].file_a == "a.py"
        assert pairs[1].shared_commits == 4
