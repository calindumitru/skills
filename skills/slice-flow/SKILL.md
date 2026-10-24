---
name: slice-flow
description: Take one ready-for-agent ticket from the tracker to live. Picks the builder agent by the ticket's size label, reviews its PR, merges once the review passes and CI is green, watches the deploy, closes the ticket with evidence or writes check tasks for what can't be checked yet. Use when asked to build a ticket ("build #42", "pick up the next slices"), to say what is ready to build, to size or escalate a ticket, or to close a merged one.
---

# Slice flow

A **slice** is a `ready-for-agent` ticket: a tracer-bullet vertical slice that `/to-tickets` or `/triage` wrote, carrying one `size:*` label. One slice goes to one **builder** agent in its own worktree, which stops at an open PR with CI green. The **main session** (you, talking to the owner) reviews, reports, merges once the review passes and CI is green, and closes the slice only once it is live and checked. The whole route is drawn in `docs/agents/workflow.md`; the builder's own steps are in `docs/building-slices.md`; the tracker's frontier, claims and fold-in rules are in `docs/agents/issue-tracker.md`.

## Sizes

Every open slice carries exactly one size label, set by **amount of work** when the slice is written, without asking the owner, and relabelled when a rewrite changes the amount. `escalate` goes on top when a mistake would be costly, and wins.

| Label | Amount of work | Agent |
|---|---|---|
| `size:xs` | Text, docs or config only. No logic. | the main session itself, on a branch of its own |
| `size:s` | A vertical slice so small that one layer changes: one endpoint, one UI piece, one parser, one adapter on an existing pattern. No migration, no infrastructure. | `slice-builder-s` |
| `size:m` | One vertical slice across layers on patterns already in the code; or any migration or infrastructure change. | `slice-builder-m` |
| `size:l` | Several slices' worth: new storage shapes, several adapters, or changes across many layers at once. | `slice-builder-l` |
| `escalate` (with any size; wins) | A mistake is costly: security, credentials, privacy, deletion, data migrations on live data. Also any rebuild after a failed review. | `slice-builder-escalated` |

- **On the boundary between s and m, it's m.** **A slice built from a prototype is at least m**: matching a look is a judgement call.
- **xs is yours.** The main session builds a `size:xs` slice itself (no builder, no worktree hand-off) and one reviewer carries both review axes; every other size gets a builder and the two-axis review.

## Models

**One pair for every size and every reviewer, for now (the owner, 2026-10-21).** The size still picks the agent, its instructions and the review; it no longer picks the model.

| | Model · effort | Intelligence | Cost a task | Runs through |
|---|---|---|---|---|
| First choice | GPT-6.1 Sol · xhigh | 51.0 | $0.39 | this skill's `scripts/codex-agent.sh` (the Codex CLI) |
| Fallback | Claude Opus 5.5 · medium | 51.2 | $1.34 | the Agent tool with the agent's name (its file says `model: opus`, `effort: medium`) |

- **Start every agent on the first choice:** write the brief to a file and run `scripts/codex-agent.sh <agent> <repo> <brief> <report>` in the background (a builder runs for many minutes). A builder gets its own worktree under `.claude/worktrees/`; a reviewer runs read-only in the PR's worktree.
- **Fall back** when the script exits non-zero: 75 means GPT is unavailable (no CLI, usage limit, model refused), anything else a failed run; after a usage limit it answers 75 at once, with no worktree, until the reset time Codex named, so start every later agent the same way and let it answer. Start the Claude agent of the same name with the same brief, and remove a GPT worktree that left no PR. Never retry a failed run on GPT, and say in the report which model built and reviewed.
- **Never Sonnet or Fable**, even when an agent file is missing: fall back to a general-purpose agent on Opus medium, in worktree isolation. The numbers behind the pair are in this skill's README.

## Steps

1. **Pick.** The frontier is every open `ready-for-agent` ticket with no open blocker and no live claim (`docs/agents/issue-tracker.md` says what counts as abandoned); where the repo has `scripts/frontier.sh`, run it, and treat a slice it flags `shipped?` as the tracker doc says (strip its labels, ticket its checks, close it, never rebuild it). If the owner named a ticket, take that one. Claim it by assigning it before anything else. **A session takes at most three slices**, then posts its map note and ends; a slice that should run at the same time as another runs in its own session (`start_session`, fresh context), never as a subagent of this thread, because this thread's whole context is re-read on every turn (one session of ten slices re-read 250M cached tokens). Slices run in parallel only when they touch different files and need different ports. **A `size:l` or `escalate` slice always gets its own session** (`t3_thread_launch` in T3 Code), even alone: its builder runs for half an hour or more, and a background job dies when this thread's session ends (#679's first builder did, with nothing committed).
2. **Start the builder** from the tables (agent by size, model by *Models*), with the brief in `docs/agents/briefs.md` (where the repo has it; else this skill's `templates/briefs.md`): the issue URL and the lines the issue can't carry, nothing restated from the docs. Done when the builder reports in the brief's report shape: PR URL, CI state, numbers first, judgement calls, open points, under 200 words.
3. **Review.** Start the two reviewer agents together, `slice-reviewer-standards` and `slice-reviewer-spec`, each with the PR number, the fixed point (the default branch) and the issue, on the first choice with the fallback as *Models* says; a docs-only PR (CI skipped the code jobs) gets `slice-reviewer-docs` alone. Present their reports side by side under `## Standards` and `## Spec`, never merged or reranked: a change can pass one axis and fail the other. Fix small things or send it back; a rebuild after a failed review goes to `slice-builder-escalated`. A product decision the issue leaves open goes to the owner, never guessed; a product *question* becomes a `wayfinder:grilling` ticket on the relevant map, not an answer inside the slice.
4. **Report and merge.** Tell the owner: PR, CI, what was checked, judgement calls, open points. Then merge (squash) once the review passes and CI is green, without asking. Wait for the owner's word only when the review or the builder flags a product decision the owner has not made, or the slice carries `escalate`. Where the repo has `scripts/ship.sh`, run `scripts/ship.sh <pr>` once: it waits for CI, merges, waits for the deploy and prints the deployed commit, and when the session ends mid-run, running it again on the merged PR resumes at the deploy; otherwise gate the merge on `gh pr checks <pr> --watch --fail-fast && gh pr merge <pr> --squash` and watch the deploy run. Done when the deployed version is the merged commit, or, where the repo skips deploys for docs-only merges, when the two differ only by files that deploy ignores (the repo's own currency check says how). **In T3 Code the merge settles the thread that linked the PR**, though the slice isn't done: straight after the merge, call `t3_thread_organize` with `unsettle` (this thread, and a slice session's thread from step 1 too), and settle it only when step 5 is done.
5. **Check and close.** The PR body's *After merge* section lists the slice's live checks, each marked *agent now*, *agent later (when)* or *owner*. Run every *agent now* check and post the evidence on the slice. Close it when every check passes. Each *agent later* or *owner* check becomes a **check task** (below) outside the slice; a failed check keeps the slice open and goes back to the builder, or to the owner when it is a product call. Done when the slice is closed or has a check task for everything still open. Then remove the builder's worktree and branch (where the repo has `scripts/prune-worktrees.sh`, a dry run and then `--apply`), and settle the thread (`t3_thread_organize` `settle`) when no check of this session's is left to run.

## Check tasks

A live check that can't be done when the slice closes is its own issue, so no slice and no session waits on it:

- `check:owner`, assigned to the owner: anything needing a sign-in, a device, a form, an email, an admin UI or a setting agents can't read. Bundle the owner's checks on one screen into one sitting.
- `check:agent`, unassigned, with a due date: a read-only check that has to wait (a first scheduled run, a nightly sweep, a day's usage). Any session picks it up on or after that date. Native-block it on the owner's `check:owner` when it needs the owner's step first.

A check task is titled "Check: <what>", names the slice and its PR, carries the check's steps and what passing looks like verbatim from the PR's *After merge* section, starts with "**Due:** YYYY-MM-DD" (or "when #N is done") for `check:agent`, is closed with its evidence, and turns a failure into a new slice (or a grilling ticket when the failure is a product question). Write check tasks only for what really needs checking: a check that adds nothing beyond the tests is dropped, not ticketed.

## Sizing a ticket

When asked to size or escalate: read the ticket, state the amount of work in one line against the table, apply the one size label (and `escalate` if a mistake is costly), and say why. A ticket on the s/m boundary is m.
