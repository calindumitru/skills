---
name: slice-flow
description: Take one ready-for-agent ticket from the tracker to live. Picks the builder agent by the ticket's size label, reviews its PR, merges once the review passes and CI is green, watches the deploy, closes the ticket with evidence or writes check tasks for what can't be checked yet. Use when asked to build a ticket ("build #42", "pick up the next slices"), to say what is ready to build, to size or escalate a ticket, or to close a merged one.
---

# Slice flow

A **slice** is a `ready-for-agent` ticket: a tracer-bullet vertical slice that `/to-tickets` or `/triage` wrote, carrying one `size:*` label. One slice goes to one **builder** agent in its own worktree, which stops at an open PR with CI green. The **main session** (you, talking to the owner) reviews, reports, merges once the review passes and CI is green, and closes the slice only once it is live and checked. The whole route is drawn in `docs/agents/workflow.md`; the builder's own steps are in `docs/building-slices.md`; the tracker's frontier, claims and fold-in rules are in `docs/agents/issue-tracker.md`.

## Sizes

Every open slice carries exactly one size label, set by **amount of work** when the slice is written, without asking the owner, and relabelled when a rewrite changes the amount. `escalate` goes on top when a mistake would be costly, and wins.

| Label | Amount of work | Agent | Model | Effort |
|---|---|---|---|---|
| `size:xs` | Text, docs or config only. No logic. | `slice-builder-xs` | Haiku | high |
| `size:s` | A vertical slice so small that one layer changes: one endpoint, one UI piece, one parser, one adapter on an existing pattern. No migration, no infrastructure. | `slice-builder-s` | Haiku | xhigh |
| `size:m` | One vertical slice across layers on patterns already in the code; or any migration or infrastructure change. | `slice-builder-m` | Opus | medium |
| `size:l` | Several slices' worth: new storage shapes, several adapters, or changes across many layers at once. | `slice-builder-l` | Opus | high |
| `escalate` (with any size; wins) | A mistake is costly: security, credentials, privacy, deletion, data migrations on live data. Also any rebuild after a failed review. | `slice-builder-escalated` | Opus | xhigh |

- **On the boundary between s and m, it's m.** Haiku only where a mistake would be caught by the tests.
- **A slice built from a prototype is at least m**, whatever its amount of work: matching a look is a judgement call.
- **Never Sonnet or Fable for implementation**, even when an agent file is missing: fall back to a general-purpose agent with the table's model and effort, in worktree isolation. The numbers behind the table are in this skill's README.

## Steps

1. **Pick.** The frontier is every open `ready-for-agent` ticket with no open blocker and no live claim (`docs/agents/issue-tracker.md` says what counts as abandoned). If the owner named a ticket, take that one. Claim it by assigning it before anything else. Run slices in parallel only when they touch different files and need different ports.
2. **Start the builder** from the table, with the issue URL. Done when the builder reports: PR URL, CI state, what it checked with numbers, judgement calls, anything left open.
3. **Review.** Call the Skill tool with `code-review` on the PR. Fix small things or send it back; a rebuild after a failed review goes to `slice-builder-escalated`. A product decision the issue leaves open goes to the owner, never guessed; a product *question* becomes a `wayfinder:grilling` ticket on the relevant map, not an answer inside the slice.
4. **Report and merge.** Tell the owner: PR, CI, what was checked, judgement calls, open points. Then merge (squash) once the review passes and CI is green, without asking. Wait for the owner's word only when the review or the builder flags a product decision the owner has not made, or the slice carries `escalate`. Watch the deploy until it is live. Done when the deployed version is the merged commit.
5. **Check and close.** The PR body's *After merge* section lists the slice's live checks, each marked *agent now*, *agent later (when)* or *owner*. Run every *agent now* check and post the evidence on the slice. Close it when every check passes. Each *agent later* or *owner* check becomes a **check task** (below) outside the slice; a failed check keeps the slice open and goes back to the builder, or to the owner when it is a product call. Done when the slice is closed or has a check task for everything still open.

## Check tasks

A live check that can't be done when the slice closes is its own issue, so no slice and no session waits on it:

- `check:owner`, assigned to the owner: anything needing a sign-in, a device, a form, an email, an admin UI or a setting agents can't read. Bundle the owner's checks on one screen into one sitting.
- `check:agent`, unassigned, with a due date: a read-only check that has to wait (a first scheduled run, a nightly sweep, a day's usage). Any session picks it up on or after that date. Native-block it on the owner's `check:owner` when it needs the owner's step first.

A check task is titled "Check: <what>", names the slice and its PR, carries the check's steps and what passing looks like verbatim from the PR's *After merge* section, starts with "**Due:** YYYY-MM-DD" (or "when #N is done") for `check:agent`, is closed with its evidence, and turns a failure into a new slice (or a grilling ticket when the failure is a product question). Write check tasks only for what really needs checking: a check that adds nothing beyond the tests is dropped, not ticketed.

## Sizing a ticket

When asked to size or escalate: read the ticket, state the amount of work in one line against the table, apply the one size label (and `escalate` if a mistake is costly), and say why. A ticket on the s/m boundary is m.
