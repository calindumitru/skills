# slice-builders

Claude Code builder agents that take one `build:slice` issue to an open PR with CI green, with the model and effort picked by the slice's size label, plus the skill that tells the main session which one to start.

| Label | Builder | Model · effort |
|---|---|---|
| `size:xs` | `slice-builder-xs` | Haiku high |
| `size:s` | `slice-builder-s` | Haiku xhigh |
| `size:m` | `slice-builder-m` | Opus medium |
| `size:l` | `slice-builder-l` | Opus high |
| `build:escalate` | `slice-builder-escalated` | Opus xhigh |

Never Sonnet or Fable: on the cost-vs-intelligence frontier an Opus setting beats them. The reasoning and numbers are in [SKILL.md](SKILL.md).

## Install

1. The skill (personal, all repos):
   ```bash
   cp -R skills/slice-builders ~/.claude/skills/
   ```
2. In each repo that builds slices: copy `agents/*.md` to `<repo>/.claude/agents/` (replace `<project>`), copy `templates/building-slices.md` to `<repo>/docs/building-slices.md` and fill in its placeholders, and create the labels:
   ```bash
   for l in size:xs size:s size:m size:l; do gh label create "$l" --force; done
   gh label create build:escalate --color b60205 --force
   ```

## Example prompts

- "Build #42."
- "Pick up the next two build slices."
- "Size this slice" / "Should this one be escalated?"
- "Add the slice builders to this repo."
