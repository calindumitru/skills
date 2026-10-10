---
name: slice-builders
description: Pick, start and install the slice-builder agents that turn one `build:slice` issue into an open PR with CI green, with the model and effort chosen by the slice's size label (size:xs/s → Haiku, size:m/l → Opus, build:escalate → Opus xhigh; never Sonnet or Fable). Use when building a slice ("build #42", "pick up the next slices"), when writing or relabelling a slice's size, or when adding slice builders to a repo.
---

# Slice builders

One `build:slice` issue → one builder agent in its own worktree → an open PR with CI green. The builder never merges. The main session (the one talking to the owner) reviews, reports and merges only when the owner says so.

## Pick the builder

| Label | Amount of work | Agent | Model | Effort |
|---|---|---|---|---|
| `size:xs` | Text, docs or config only. No logic. | `slice-builder-xs` | Haiku | high |
| `size:s` | One layer: one endpoint, one UI piece, one parser, one adapter on an existing pattern. No migration, no infrastructure. | `slice-builder-s` | Haiku | xhigh |
| `size:m` | One vertical slice across layers on patterns already in the code; or any migration or infrastructure change. | `slice-builder-m` | Opus | medium |
| `size:l` | Several slices' worth: new storage shapes, several adapters, or changes across many layers at once. | `slice-builder-l` | Opus | high |
| `build:escalate` (with any size; wins) | A mistake is costly: security, credentials, privacy, deletion, data migrations on live data. Also any rebuild after a failed review. | `slice-builder-escalated` | Opus | xhigh |

- **Every open slice carries exactly one size label**, set by amount of work when the slice is written, without asking the owner; relabel it when a rewrite changes the amount. Add `build:escalate` on top when a mistake would be costly.
- **On the boundary between s and m, it's m.** Use Haiku only where a mistake would be caught by the tests.
- **Never Sonnet or Fable for implementation**, even when an agent file is missing: fall back to a general-purpose agent with the table's model (and effort, since this table asks for it) and worktree isolation.
- Run slices in parallel only when they don't touch the same files or need the same ports.

### Why these models

Taken from the cost-vs-intelligence Pareto frontier on [slopalytics.com](https://slopalytics.com/) (Artificial Analysis data, October 2026). Claude settings on the frontier: Haiku high/xhigh and Opus medium/high/xhigh, at roughly 38 / 41 / 51 / 54 / 56 on the intelligence index for about $0.08 / $0.12 / $1.34 / $1.82 / $3.46 a benchmark task.

- An Opus setting beats every Sonnet and Fable setting on both cost and intelligence, except Sonnet high (46.8, $0.88). That one buys fewer points per dollar than going on to Opus medium, and sits below the line joining its neighbours.
- Opus low (42.3, $0.55) is beaten by Haiku max (43.4, $0.21); Opus max adds 1.6 points for 73% more cost.
- Haiku tops out around 41–43 and Opus medium starts at 51, with nothing on the frontier between: that gap is why the s/m boundary matters most.

Re-check the chart when new models ship, and update this table and the agents together.

## Start a builder

Start the agent from the table with the issue URL. When it reports back:

1. Review the PR (e.g. `/code-review`), fix it or send it back. A rebuild after a failed review goes to `slice-builder-escalated`.
2. Report to the owner: PR, CI state, what was checked, judgement calls, open questions.
3. Merge only when the owner says so; then post the outcome on the issue.

## Install in a repo

1. Copy `agents/*.md` into `<repo>/.claude/agents/`. Replace `<project>` in them with the project's name and add any repo-wide "never" rules (ports, secrets, profiles) to the paragraph that has them.
2. Copy `templates/building-slices.md` to `<repo>/docs/building-slices.md` and fill in its `<...>` placeholders (test commands, how to run the app, docs to update).
3. Create the labels:
   ```bash
   for l in size:xs size:s size:m size:l; do gh label create "$l" --force; done
   gh label create build:escalate --color b60205 --force
   ```
4. Point `CLAUDE.md` at `docs/building-slices.md`. Sessions started outside the repo don't load `.claude/agents/`: use the general-purpose fallback above.
