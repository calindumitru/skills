# skills

Claude Code skills I use across projects.

| Skill | What it does |
|---|---|
| [db-migration-review](skills/db-migration-review) | Grades Liquibase changesets (XML, YAML, formatted SQL) by blue-green deployment risk on a hot Postgres database. Python checker with a CI exit code, plus the Claude skill that judges the rest. |

## Install a skill

Personal (every repo):

```bash
cp -R skills/db-migration-review ~/.claude/skills/
```

Per project (teammates get it too): copy it to `<repo>/.claude/skills/`.

Each skill's README lists its one-off setup and example prompts.
