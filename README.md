# commitlens

> Surface code-churn hotspots, author distribution, and co-change clusters
> from any git repository — straight from the command line.

`commitlens` is a small, fast CLI that reads `git log` and tells you which
files in a repository are *actually* under active change, who's changing
them, and which files tend to move together. Useful for code-review
prioritization, finding architectural seams that want refactoring, and
onboarding into an unfamiliar codebase.

It runs against any git repo you can `cd` into. No server, no database,
no telemetry — `git log --numstat` and pure Python.

## Quick start

```bash
pipx install commitlens                  # or: pip install commitlens
commitlens                                # analyze the current repo, last 90 days
commitlens path/to/repo --since 30d --top 25
commitlens . --json > churn.json          # machine-readable output
```

Sample output (Rich-rendered to your terminal):

```
╭─ commitlens · path/to/repo · last 30 days ──────────────────────────╮
│ 142 commits · 38 authors · 612 files touched                        │
╰─────────────────────────────────────────────────────────────────────╯

Top 10 churned files
┌──────────────────────────────────────┬────────┬──────────┬──────────┐
│ Path                                 │ ±Lines │ Commits  │ Authors  │
├──────────────────────────────────────┼────────┼──────────┼──────────┤
│ src/api/orders.py                    │   2118 │   24     │    9     │
│ web/components/Cart.tsx              │   1763 │   31     │   14     │
│ src/db/migrations/0042_orders.sql    │    893 │    2     │    1     │
│ ...                                                                 │
└──────────────────────────────────────┴────────┴──────────┴──────────┘

Co-change clusters (≥4 commits in common)
- src/api/orders.py  ↔  src/db/schema.py        (8 shared commits)
- web/components/Cart.tsx  ↔  web/hooks/useCart.ts  (12 shared commits)
```

## Why this exists

When reviewing PRs, the most useful prior I have isn't "what does the
diff say" — it's "how often has this code been touched lately, and by
whom?" Files that churn weekly often hide bugs *and* the institutional
knowledge of how to spot them. Files that churn together imply a
hidden coupling worth naming.

GitHub's insights panel hints at this, but it's hard to scope to a
folder, hard to export, and only works on github.com-hosted repos.
`commitlens` is the local-first, stdlib-first version: point it at any
working copy, get the same insight in <2 seconds.

## Features

- **File churn ranking** — lines changed + commit count + distinct
  authors, sortable by any axis.
- **Author hot spots** — who's most active where, useful when a PR is
  in territory that has a clear domain owner.
- **Co-change clusters** — pairs of files that get edited together far
  more often than chance. Catches hidden module boundaries.
- **Time windowing** — `--since 30d`, `--since 2025-01-01`, or any
  expression `git log` accepts.
- **Path scoping** — `commitlens src/` limits analysis to one subtree.
- **Multiple outputs** — Rich-rendered TUI by default, JSON for tooling.

## Install

Requires Python 3.10+ and `git` on PATH.

```bash
pipx install commitlens
# or
pip install --user commitlens
```

For local development:

```bash
git clone https://github.com/tjgarcia0427/commitlens
cd commitlens
pip install -e ".[dev]"
pytest
```

## Usage

```text
Usage: commitlens [OPTIONS] [REPO_PATH]

  Analyze a git repository's recent commit activity.

  REPO_PATH defaults to the current directory. Subpaths work too:

      commitlens src/             # only analyze src/

Options:
  --since TEXT             Time window (any git log expression). Default: 90d
  --top INTEGER            Number of files to show in the churn table. Default: 20
  --min-cochange INTEGER   Minimum shared commits to flag a co-change pair. Default: 4
  --json                   Emit JSON instead of the rendered TUI.
  --no-clusters            Skip co-change cluster analysis.
  --version                Show version and exit.
  --help                   Show this help and exit.
```

## How it works

1. Shells out to `git log --numstat --pretty=format:%H%x09%an%x09%aI`
   over the requested time window.
2. Parses the structured output into per-file change records
   (additions, deletions, commit SHA, author, timestamp).
3. Aggregates into per-file metrics (total ±lines, distinct commits,
   distinct authors, last-touched date).
4. For co-change clusters, builds a per-commit set of touched files,
   then pairwise counts shared commits across the corpus. Pairs with
   `n ≥ min_cochange` are surfaced, ranked by descending shared count.
5. Renders the result with Rich, or emits JSON.

No third-party git library is used — `subprocess` + `git`'s plumbing
output is enough, fast, and works on any git version since 2.x.

## Performance

On a 5k-commit, 6k-file monorepo, `commitlens --since 90d` finishes in
under 2 seconds on a 2024 M2 laptop. Most of the time is the initial
`git log` invocation; aggregation is `O(commits × files-per-commit)`
with linear-scan dict updates.

For huge repos (Linux kernel scale), use `--no-clusters` to skip the
pairwise pass.

## Roadmap

- HTML / SVG report output (for sharing in PR descriptions)
- Per-extension scoping (`--ext .py,.ts`)
- Author churn-velocity over time
- Git blame survival analysis (lines still live after N days)

PRs welcome — open an issue first for anything bigger than a small bug fix
so we can agree on shape before you spend time on it.

## License

MIT.

---

> **About this codebase:** built collaboratively with AI assistance
> (Claude). Architecture, scope, and design decisions are mine; I use
> AI as a senior pair-programmer for code generation and review. Happy
> to walk through any part of this codebase in detail in an interview.
