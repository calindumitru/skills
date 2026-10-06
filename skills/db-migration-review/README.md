# db-migration-review

A Claude Code skill plus a standalone Python checker that grades Liquibase changesets by how they behave during a
**blue-green deploy on a hot Postgres database** (Azure Database for PostgreSQL Flexible Server, Cloud Foundry
blue-green, Kotlin app with Hibernate or MyBatis, REST traffic plus batch jobs holding row locks).

Every finding states what happens in production and gives a copy-ready fix, because the developer usually
cannot reach the database.

## One-off setup

1. **uv** (runs the scripts with their own dependency, PyYAML, cached after the first run):
   ```bash
   brew install uv
   ```
   or `curl -LsSf https://astral.sh/uv/install.sh | sh`. Python 3.11+ is fetched by uv if missing.
2. **Install the skill** (personal, all repos):
   ```bash
   cp -r db-migration-review ~/.claude/skills/
   ```
   or vendor it into a repo so teammates get it: copy to `<repo>/.claude/skills/db-migration-review`.
3. **First run** (warms the uv cache, ~2 s):
   ```bash
   uv run ~/.claude/skills/db-migration-review/scripts/review.py --list-rules
   ```
4. Optional: drop `config.example.toml` into the repo root as `.db-migration-review.toml` and edit it
   (base branch, changelog dirs, small tables, lock_timeout, rule overrides). Everything works without it.

## Example prompts

- "Review the Liquibase changes I just added for blue-green safety."
- "Is `db/changelog/2026-10-06-orders.xml` safe to deploy?"
- "Check the migrations in PR 4123 on Azure DevOps" (the ADO skill fetches the files, this skill reviews them).
- "Will creating this index lock the orders table?"
- "Apply the fixes from the migration review and re-run it."
- "Explain why dropping `legacy_region_code` is critical and how to do it in two releases."

## Running the checker by hand

From the repo root:

```bash
uv run ~/.claude/skills/db-migration-review/scripts/review.py --format md
```

| Flag | Meaning |
|---|---|
| `file ...` | Review these changelog files instead of discovering new ones. Also flags edits to already-applied changesets (checksum breaks). |
| `--base origin/main` | Base ref for "new file" discovery. Default: config, then `origin/HEAD`, main, master, develop. |
| `--format json\|md\|both` | `both` with `--output name` writes `name.json` and `name.md`. |
| `--fail-on critical\|high\|medium\|low\|none` | Exit code 2 when a finding at or above this level exists. Default `critical`. |
| `--config path` | Explicit config file. |
| `--no-git` / `--no-grep` | Never call git / skip the source-code lookup. |
| `--list-rules` | Print the rule ids and default levels. |

Default mode reviews **new changelog files only** (added vs the base branch, staged, or untracked).
Changesets appended to existing files are not seen unless you pass the file explicitly.

## Severity

| Level | Meaning during blue-green deploy | Examples |
|---|---|---|
| CRITICAL | Breaks production, halts the deploy, or breaks the old app version still serving traffic | index without CONCURRENTLY, CONCURRENTLY inside a transaction, drop/rename column, SET NOT NULL directly, FK without NOT VALID, VACUUM FULL |
| HIGH | Likely stall or outage under load; needs a plan | DDL without `lock_timeout`, unbatched backfill, UNIQUE/PK built inline, CHECK without NOT VALID |
| MEDIUM | Deploys, but violates expand/contract, leaves a trap, or cannot be undone | several locking DDLs in one changeset, non-transactional changeset without preconditions, missing rollback for DDL, NOT VALID never validated |
| LOW | Hygiene | runOnChange on DDL, raw SQL data change without rollback |

The full catalog with rationale and fixes is in [rules/CATALOG.md](rules/CATALOG.md).

## Azure DevOps pipeline gate

See [pipeline/README.md](pipeline/README.md) and [pipeline/azure-pipelines-db-review.yml](pipeline/azure-pipelines-db-review.yml).
The same script runs in the PR build, fails the build on CRITICAL, publishes the markdown report as an artifact,
and can post it as a PR comment.

## Tests

```bash
uv run ~/.claude/skills/db-migration-review/tests/test_review.py
```

Fixtures live in `fixtures/bad` (every rule fires) and `fixtures/good` (the same change done safely). Add a
fixture whenever a rule changes.

## Layout

```
SKILL.md                 what Claude does when the skill triggers
README.md                this file
config.example.toml      optional per-repo config
scripts/review.py        CLI: discovery, grep evidence, JSON/markdown report, exit code
scripts/liquibase_parser.py  XML / YAML / formatted-SQL -> neutral changeset model
scripts/rules.py         rule catalog and severity engine
rules/CATALOG.md         human-readable rules with rationale
fixtures/                good and bad changelogs
tests/test_review.py     pytest suite (run via uv)
pipeline/                Azure DevOps integration
```
