---
name: setup-slice-flow
description: "Wire a repo for the slice flow on top of Matt Pocock's engineering skills: builder agents, docs/building-slices.md, the tracker additions, the workflow map, the labels and the CLAUDE.md pointer. Run once per repo, after /setup-matt-pocock-skills."
disable-model-invocation: true
---

# Setup slice flow

Scaffold what the `slice-flow` skill and its builder agents assume in a repo. Prompt-driven: explore, show what you found, ask the few things only the owner knows, then write. The templates live in the `slice-flow` skill folder beside this one (`../slice-flow/`).

## 1. Explore

- **Matt's skills:** `wayfinder`, `to-spec`, `to-tickets`, `code-review`, `tdd`, `pr`, `triage` and `setup-matt-pocock-skills` in `~/.claude/skills/` or `<repo>/.claude/skills/`. Name any that are missing; the flow calls them.
- **His setup's output:** `docs/agents/issue-tracker.md`. Without it, stop and tell the owner to run `/setup-matt-pocock-skills` first: the tracker doc is where this setup appends.
- **Prior output of this setup:** `.claude/agents/slice-builder-*.md`, `docs/building-slices.md`, `docs/agents/workflow.md`, a `## Slice flow` section in the tracker doc, a `### Slice flow` block in `CLAUDE.md` or `AGENTS.md`. Existing files get updated in place, never duplicated.
- **The repo's own facts**, so you ask only for what it can't tell you: default branch (`git symbolic-ref refs/remotes/origin/HEAD`), package scripts or build files (install, typecheck, test, dev), a deploy workflow (`.github/workflows/*.yml` with a deploy job), a spec and glossary at the root, existing labels (`gh label list`).

## 2. Present and ask

Summarise what is present and what is missing, then ask one round of questions, each led by the answer the exploration suggests so the owner can accept it in a word:

1. **Run and test:** the install, typecheck, single-test, full-suite and run-the-app commands, and how a session picks a port.
2. **Docs a slice updates:** the spec, glossary and infra notes.
3. **Deploy and live checks:** how a merge deploys, how to watch it, how to read the deployed version.
4. **Repo rules:** migration, expand/contract, infrastructure or platform rules the builder must follow. Link the repo's own docs rather than restating them.
5. **Never-rules:** profiles, secrets, environments a builder must not touch.

Everything else is fixed by the flow and needs no question.

## 3. Write

1. **Agents:** copy `../slice-flow/agents/*.md` into `<repo>/.claude/agents/`, replacing any `slice-builder-*` already there.
2. **`docs/building-slices.md`** from `../slice-flow/templates/building-slices.md`, with only the *Repo-specific* section's placeholders filled from the answers. Where the file already exists, keep any repo-specific content it has beyond that section only if the owner wants it; the generic steps come from the template.
3. **Tracker doc:** append `../slice-flow/templates/issue-tracker-addendum.md` to `docs/agents/issue-tracker.md` unless a `## Slice flow` section is already there (then replace that section).
4. **`docs/agents/workflow.md`** from `../slice-flow/templates/workflow.md`, as is.
5. **Labels**, created only where missing, with `gh label create <name> --description "..." --color <hex> --force`: `size:xs`, `size:s`, `size:m`, `size:l` (`c5def5`), `escalate` (`b60205`), `check:owner` and `check:agent` (`fbca04`). `ready-for-agent` and `ready-for-human` come from Matt's setup; create them the same way if that setup skipped its label section. Where the repo already uses other names for the same roles (for example `build:slice` for `ready-for-agent`), ask whether to relabel the open issues now and do it with `gh issue edit --add-label/--remove-label`, closed issues left as they are.
6. **`CLAUDE.md` or `AGENTS.md`** (whichever exists; Matt's setup chose): under its `## Agent skills` heading add

   ```markdown
   ### Slice flow

   A `ready-for-agent` issue carries one `size:*` label and is built by the
   matching `slice-builder-*` agent up to an open PR; the main session
   reviews and merges, and the slice closes only once it is live and
   checked. Builder steps: `docs/building-slices.md`. The whole route:
   `docs/agents/workflow.md`.
   ```

Done when every file above exists with no placeholder left, the labels exist, and `gh issue list --label ready-for-agent` is what the builders will read. Say what was written, and that `/slice-flow` now builds a ticket ("build #42").
