# Azure DevOps integration

The checker is a plain script with an exit code, so it runs in a PR build without Claude.

## Steps

1. Vendor the skill into the repo: `.claude/skills/db-migration-review/` (commit it).
2. Add the template to `azure-pipelines.yml`:
   ```yaml
   stages:
     - stage: db_review
       jobs:
         - job: review
           pool: { vmImage: ubuntu-latest }
           steps:
             - template: .claude/skills/db-migration-review/pipeline/azure-pipelines-db-review.yml
   ```
3. Let the build job write PR comments: **Project settings → Repositories → (repo) → Security →
   `<project> Build Service (<org>)` → "Contribute to pull requests" = Allow.** Without it the comment step
   fails with 403; drop that step if you only want the artifact.
4. Make the stage a required check: **Branches → (target branch) → Branch policies → Build validation**.
5. Optional path filter so the job only runs when changelogs change: add a `condition` on
   `git diff --name-only origin/<target>...HEAD | grep -q changelog`, or use the pipeline trigger `paths`.

## What it does

- `fetchDepth: 0` so the merge-base with the target branch exists; `review.py` discovers changelog files
  **added** in the PR and grades them.
- `--fail-on critical` returns exit 2 on any CRITICAL finding; the final step turns that into a build failure.
  Change to `--fail-on high` once the team is used to it.
- `report.md` and `report.json` are published as the `db-migration-review` artifact and the markdown is posted
  as a PR comment thread (status "active").
- The pipeline run has no model behind it, so findings marked "Needs a human/model judgement" (drops, renames)
  show the grep evidence only. Have Claude run the skill on the PR for the judgement call.

## Changesets appended to existing files

The build reviews new files only. To also review a changelog that was edited, pass it explicitly in the step:
`review.py --base "$TARGET" src/main/resources/db/changelog/2026-release.xml`. Explicit mode additionally flags
modified already-applied changesets (`LB-CHK-001`).
