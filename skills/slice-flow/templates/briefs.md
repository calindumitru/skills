# Briefs and reports

What the main session sends an agent, and what the agent sends back. The
docs carry the steps; a brief carries only what the docs can't: the ticket,
the neighbours, the owner's word. A report carries numbers before prose.

## Builder brief

Send the builder agent exactly this, with the placeholders filled:

> Build <issue URL>. Follow `docs/building-slices.md` step by step, its
> *Repo-specific* section included, and `CLAUDE.md`. The slice is claimed.
> <One line per thing the issue can't carry: files other builders are
> touching right now; the owner's word for an edit the classifier would
> block; a decision made in chat since the issue was written.>
> Report as `docs/agents/briefs.md` → Report.

Nothing else. The size table, the PR shape, the never-rules and the check
rules are in the docs the brief names.

## Single-reviewer brief

For a docs-only PR (CI skipped the app and infra jobs), one reviewer carries
both axes of the `code-review` skill, on Opus at `low` effort:

> Review PR <n> on both axes. Standards: `CODING_STANDARDS.md` and the docs
> it points at. Spec: issue <n>'s Scope and Acceptance. Open every pointer
> the diff adds and confirm the target says what the line claims. Report as
> `docs/agents/briefs.md` → Report (reviewer).

## Report

Under 200 words for a builder, 300 for a reviewer. In this order, numbers
before prose, each item one line where it can be:

1. PR URL and CI state (a reviewer: blocks merge, yes or no).
2. Files changed, with counts.
3. What was measured, with the figures (a reviewer: hard findings first,
   each with file and line).
4. Judgement calls, one line each.
5. Open points.

Write it as the `unslop` skill says (rules 13, 16, 20, 23, 31, 33): no em
dashes, no bold label that restates its line, no closing remark, no filler,
plain words, whole sentences. The main session pastes the numbers into the
PR and the issue, so include every figure you measured.

## Ship

After the review passes, the main session runs `<ship command>` once (for
example `scripts/ship.sh <pr>`): it waits for CI, merges, waits for the
deploy and prints the deployed commit, so the merge-to-deploy wait is one
call, not five turns of reading a watch.
