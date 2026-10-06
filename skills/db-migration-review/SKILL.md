---
name: db-migration-review
description: Review Liquibase changesets (XML, YAML, formatted SQL) in a Kotlin/Hibernate/MyBatis project for blue-green deployment safety on a hot Postgres 16 database (Azure Flexible Server, Cloud Foundry blue-green). Use after writing or editing changelog files, when reviewing a pull request that touches db/changelog, or when the user asks "is this migration safe", "check my changesets", "review the DB changes", "will this index lock the table", or mentions Liquibase, CREATE INDEX, ALTER TABLE, dropColumn, expand/contract.
---

# DB migration review

Grade Liquibase changesets by what they do to a **highly used Postgres database during a blue-green deploy**:
the old app version keeps serving REST traffic and running batch jobs that row-lock in batches while the
new schema is already applied. The developer usually has **no direct database access**, so every finding must
include the production consequence and a copy-ready fix.

The deterministic work is done by `scripts/review.py` (Python, run via `uv`). Your job is to run it, judge the
few findings it marks `needs_model_review`, read anything it marks unreviewed, and deliver the report.

## 1. Decide what to review

| Situation | Command |
|---|---|
| Developer just edited/added changelogs (default) | `uv run --quiet <skill>/scripts/review.py --root <repo> --format both --output <scratch>/db-review` |
| Developer names specific files | add the file paths as positional arguments (this also detects edits to already-applied changesets) |
| Reviewing a PR fetched through the Azure DevOps skills | check out the PR branch if possible and run the default; otherwise save the changed changelog files to a scratch folder and run with the paths plus `--no-git` |

`<skill>` is this skill's directory. Default mode reviews **new changelog files only** (added vs the base branch,
staged, or untracked). If the report says no new changelog files were found, ask for file paths or review the
files the user mentioned.

Optional repo config `.db-migration-review.toml` (see `config.example.toml`) sets the base branch, changelog
and source directories, lock_timeout, small tables and rule overrides. Do not create it unprompted.

## 2. Read the JSON, then judge

Open `<output>.json`. For each finding:

- **`needs_model_review: true`** (drop/rename/truncate, new NOT NULL column): the script already grepped the
  source directories and put hits in `evidence`. Open those hits. Decide whether the **currently deployed**
  version (not just this branch) still reads or writes the object: Hibernate `@Entity` fields and `@Column`
  names, MyBatis mapper XML `<select>/<insert>/<resultMap>`, native queries, views. If it clearly does not,
  say so and downgrade the finding to MEDIUM with the reason ("unreferenced on this branch; confirm the release
  branch"). Never downgrade below MEDIUM: the deployed version may differ from the branch you can see.
- **`unreviewed`** entries (statements the parser could not classify, `customChange`, unresolved `sqlFile`):
  read the raw SQL and judge it against `rules/CATALOG.md`. Add a finding yourself if it matches a rule.
- Everything else: trust the script. Do not re-derive the lock analysis.

Keep connection-pool, thread and timeout tuning out of the report unless a finding cannot be fixed in the
changeset itself (for example a backfill that must become an application job).

## 3. Deliver the report

Use the markdown the script produced (`<output>.md`) as the body. Rewrite the **TL;DR** into three to five
plain sentences for the developer: verdict, the one or two things that would hurt production, what to do first,
and whether the change needs to be split across releases. Fold your code-lookup judgements into the relevant
findings. Keep the section order: verdict line, summary table, TL;DR, findings by level, unreviewed, passed,
rollout order.

Verdicts: **BLOCK** (any CRITICAL), **NEEDS PLAN** (HIGH), **REVIEW** (MEDIUM), **SAFE**.

Do not edit the changelog files unless the user asks. When they do, apply the fix snippets from the findings,
re-run the script, and show the new verdict.

## Severity levels

| Level | Meaning during blue-green deploy |
|---|---|
| CRITICAL | Breaks production, halts the deploy (Liquibase error at startup), or breaks the old app version still serving traffic |
| HIGH | Likely stall or outage under load; needs a plan |
| MEDIUM | Deploys, but violates expand/contract, leaves a trap, or cannot be undone |
| LOW | Hygiene |

Full rule list with rationale: `rules/CATALOG.md`. `uv run scripts/review.py --list-rules` prints ids and levels.
