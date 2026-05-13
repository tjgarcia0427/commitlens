"""End-to-end CLI tests against a synthetic git repo.

These are slower than the parser/aggregator tests because they actually
shell out to git, but they verify the whole pipeline.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from commitlens.cli import main


def git(repo: Path, *args: str) -> str:
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "Tester",
            "GIT_AUTHOR_EMAIL": "tester@example.com",
            "GIT_COMMITTER_NAME": "Tester",
            "GIT_COMMITTER_EMAIL": "tester@example.com",
        }
    )
    return subprocess.check_output(
        ["git", *args], cwd=repo, text=True, env=env, stderr=subprocess.PIPE,
    )


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "b.py").write_text("y = 2\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "initial: a + b")

    (tmp_path / "a.py").write_text("x = 1\nx2 = 2\nx3 = 3\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "feat: extend a")

    (tmp_path / "b.py").write_text("y = 2\ny2 = 3\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "fix: tweak b")
    return tmp_path


class TestCLI:
    def test_runs_against_real_repo(self, sample_repo: Path):
        runner = CliRunner()
        result = runner.invoke(main, [str(sample_repo)])
        assert result.exit_code == 0, result.output
        # Header summary contains the right counts
        assert "3 commits" in result.output
        assert "Tester" in result.output

    def test_json_output_is_valid(self, sample_repo: Path):
        runner = CliRunner()
        result = runner.invoke(main, [str(sample_repo), "--json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["stats"]["commits"] == 3
        assert payload["stats"]["authors"] == 1
        paths = {f["path"] for f in payload["files"]}
        assert paths == {"a.py", "b.py"}

    def test_no_clusters_skips_pair_pass(self, sample_repo: Path):
        runner = CliRunner()
        result = runner.invoke(main, [str(sample_repo), "--no-clusters", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["co_change_pairs"] == []

    def test_non_repo_exits_with_message(self, tmp_path: Path):
        # tmp_path is not a git repo
        runner = CliRunner()
        result = runner.invoke(main, [str(tmp_path)])
        assert result.exit_code != 0
        assert "not inside a git repository" in result.output.lower()
