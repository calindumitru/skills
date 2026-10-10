# Building a slice

How a `build:slice` issue goes from ticket to an open pull request. The slice builder agents in `.claude/agents/` follow this, and so does any session that builds a slice by hand.

## Sizes

Every open `build:slice` issue carries exactly one size label, set **by amount of work**, plus `build:escalate` when a mistake would be costly. The main session sets them when it writes or rewrites a slice, without asking the owner, and relabels the slice when a rewrite changes the amount.

| Label | Amount of work | Agent | Model | Effort |
|---|---|---|---|---|
| `size:xs` | Text, docs or config only. No logic. | `slice-builder-xs` | Haiku | high |
| `size:s` | One layer: <one endpoint, one UI piece, one parser>. No migration, no infrastructure. | `slice-builder-s` | Haiku | xhigh |
| `size:m` | One vertical slice across <layers> on patterns already in the code; or any migration or infrastructure change. | `slice-builder-m` | Opus | medium |
| `size:l` | Several slices' worth: new storage shapes, or changes across <layers> at once. | `slice-builder-l` | Opus | high |
| `build:escalate` (with any size) | A mistake is costly: <security, credentials, privacy, deletion, data migrations on live data>. Also any rebuild after a failed review. | `slice-builder-escalated` | Opus | xhigh |

Never Sonnet or Fable for building. A slice on the boundary between s and m is m. (Why: the `slice-builders` skill, from the cost-vs-intelligence frontier.)

## Who does what

- **The main session** (the one talking to the owner) picks the agent from the slice's size label (or `build:escalate`, which wins) and starts it with the issue URL. A slice rebuilt after a failed review goes to `slice-builder-escalated`.
- **The builder** builds in its own worktree, up to an open PR with CI green, then reports back.
- **The main session** reviews the PR, fixes it or sends it back, and reports to the owner. It merges **only when the owner says so**, then posts the outcome on the slice issue.

## Steps for the builder

1. **Read the whole issue**: its body and every comment (`gh issue view <n> --comments`). Comments win where they conflict with the body. Open the tickets it links when something is unclear, and use the glossary's terms in code, commits and the PR.
2. **Start from a fresh `main` in your own worktree.** Never check out a branch in the repo root; other sessions share it.
   ```bash
   git fetch origin
   git switch -c <feat|fix|chore>/<slug> origin/main
   ```
3. **Build it**, test first at the seams the issue names. Run `<fast checks>` often and `<full test command>` once at the end.
4. **Check user-facing changes in the running app**: `<how to run it locally>`. Measure rather than eyeball.
5. **Update the docs** the issue names: `<spec, glossary, runbooks>`.
6. **Open the PR to `main`**: an imperative title naming the change; a body with the issue link (no closing keyword if the issue stays open for later checks), **What changes**, **Judgement calls**, **Checked** (commands and numbers), **After merge**. Wait for CI and fix it until it's green.
7. **Never** merge, deploy, push to `main`, or print a secret. <Repo-specific rules: ports, profiles, environments.>
8. **Report back**: the PR URL and CI state, what you checked (with numbers), your judgement calls, and anything left open. If the issue leaves a **product decision** open, don't guess: stop and report it.
