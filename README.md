# skills

Claude Code skills I use across projects.

| Skill | What it does |
|---|---|
| [db-migration-review](skills/db-migration-review) | Grades Liquibase changesets (XML, YAML, formatted SQL) by blue-green deployment risk on a hot Postgres database. Python checker with a CI exit code, plus the Claude skill that judges the rest. |
| [slice-builders](skills/slice-builders) | Builder agents that take one `build:slice` issue to an open PR, with the model and effort picked by size label from the cost-vs-intelligence frontier (Haiku for xs/s, Opus for m/l/escalate, never Sonnet or Fable), plus the skill that picks and starts them. |

## Install a skill

Personal (every repo):

```bash
cp -R skills/db-migration-review ~/.claude/skills/
```

Per project (teammates get it too): copy it to `<repo>/.claude/skills/`.

Each skill's README lists its one-off setup and example prompts.
