# skills

Claude Code skills I use across projects.

| Skill | What it does |
|---|---|
| [slice-flow](skills/slice-flow) | My way of working on top of [Matt Pocock's engineering skills](https://github.com/mattpocock/skills): one `ready-for-agent` ticket goes to a builder agent picked by size label (GPT-6.1 Sol first, Claude Opus as fallback), up to an open PR; the main session reviews and merges, and the ticket closes only once it is live and checked. Comes with the workflow map, the builder agents and the repo templates. |
| [setup-slice-flow](skills/setup-slice-flow) | Wires a repo for the slice flow in one run: agents, `docs/building-slices.md`, the tracker additions (abandoned claims, fold-in ticket), the workflow map, the labels and the `CLAUDE.md` pointer. |
| [db-migration-review](skills/db-migration-review) | Grades Liquibase changesets (XML, YAML, formatted SQL) by blue-green deployment risk on a hot Postgres database. Python checker with a CI exit code, plus the Claude skill that judges the rest. |

## Install a skill

Personal (every repo):

```bash
for s in slice-flow setup-slice-flow; do rm -rf ~/.claude/skills/$s && cp -R skills/$s ~/.claude/skills/; done
```

Per project (teammates get it too): copy it to `<repo>/.claude/skills/`.

Each skill's README lists its one-off setup and example prompts. The slice flow assumes Matt's skills are installed the same way; then run `/setup-matt-pocock-skills` once in a repo, and `/setup-slice-flow` after it.
