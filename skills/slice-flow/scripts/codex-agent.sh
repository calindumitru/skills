#!/usr/bin/env bash
# Run one slice-flow agent on GPT through the Codex CLI: the first choice for
# every size and every reviewer. The Claude agent of the same name is the
# fallback.
#
# Usage: codex-agent.sh <agent-name> <repo-dir> <brief-file> <report-file>
#   agent-name   slice-builder-* or slice-reviewer-*; its file is read from
#                <repo-dir>/.claude/agents/, else ~/.claude/agents/.
#   repo-dir     the repo's checkout. A builder gets a fresh worktree under
#                <repo-dir>/.claude/worktrees/, detached at origin's default
#                branch; a reviewer runs read-only in <repo-dir> as given
#                (pass the PR's worktree).
#   brief-file   the brief, as docs/agents/briefs.md shapes it.
#   report-file  where the agent's last message (its report) is written.
#
# Exit 0: the report is in <report-file>.
# Exit 75: GPT is unavailable (no Codex CLI, usage limit, model refused).
#          Start the Claude agent of the same name instead.
# Other non-zero: the GPT run failed. Fall back to the Claude agent too;
#          a failed run is not retried on GPT.
#
# SLICE_GPT_MODEL (default gpt-6.1-sol) and SLICE_GPT_EFFORT (default xhigh)
# override the choice; CODEX overrides the CLI path.
set -uo pipefail

agent=${1:?agent name}; repo=${2:?repo dir}; brief=${3:?brief file}; report=${4:?report file}
model=${SLICE_GPT_MODEL:-gpt-6.1-sol}
effort=${SLICE_GPT_EFFORT:-xhigh}

codex=${CODEX:-$(command -v codex || true)}
[ -z "$codex" ] && [ -x /Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex ] \
  && codex=/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex
if [ -z "$codex" ]; then echo "codex-agent: no Codex CLI found" >&2; exit 75; fi

file=$repo/.claude/agents/$agent.md
[ -f "$file" ] || file=$HOME/.claude/agents/$agent.md
if [ ! -f "$file" ]; then echo "codex-agent: no agent file for $agent" >&2; exit 2; fi

case $agent in
  slice-reviewer-*)
    dir=$repo
    sandbox=(-s read-only) ;;
  slice-builder-*)
    git -C "$repo" fetch -q origin || exit 1
    base=$(git -C "$repo" symbolic-ref -q --short refs/remotes/origin/HEAD || echo origin/main)
    dir=$repo/.claude/worktrees/gpt-$agent-$(date +%Y%m%d-%H%M%S)
    git -C "$repo" worktree add -q --detach "$dir" "$base" || exit 1
    echo "codex-agent: worktree $dir" >&2
    common=$(cd "$repo" && cd "$(git rev-parse --git-common-dir)" && pwd)
    # Writes stay in the worktree and the repo's git dir; network on for git push and gh.
    sandbox=(-s workspace-write --add-dir "$common" -c sandbox_workspace_write.network_access=true) ;;
  *) echo "codex-agent: $agent is not a slice-flow agent" >&2; exit 2 ;;
esac

prompt=$(mktemp); log=$(mktemp); ctx=$(mktemp -d)
trap 'rm -rf "$prompt" "$log" "$ctx"' EXIT

# A reviewer's sandbox has no network, so it can't run gh: copy what it reads from
# GitHub (the issue with its comments, the PR body, CI) into files it can read.
# The brief names them as "PR <n>" and "issue <n>" (docs/agents/briefs.md).
if [ "${agent#slice-reviewer-}" != "$agent" ]; then
  pr=$(grep -oE 'PR #?[0-9]+' "$brief" | head -1 | grep -oE '[0-9]+')
  issue=$(grep -oE 'issue #?[0-9]+' "$brief" | head -1 | grep -oE '[0-9]+')
  if [ -n "$issue" ]; then
    (cd "$dir" && gh issue view "$issue" --json title,body,comments \
      --jq '"# \(.title)\n\n\(.body)\n\n## Comments\n\(.comments|map(.body)|join("\n\n---\n\n"))"') > "$ctx/issue.md" 2>&1
  fi
  if [ -n "$pr" ]; then
    (cd "$dir" && gh pr view "$pr" --json title,body --jq '"# \(.title)\n\n\(.body)"') > "$ctx/pr.md" 2>&1
    (cd "$dir" && gh pr checks "$pr") > "$ctx/ci.txt" 2>&1
  fi
fi

# A builder cut off mid-run (the session ended) keeps its work: commit whatever
# the worktree holds to a wip/ branch and push it, so the next builder starts from it.
snapshot() {
  case $agent in slice-builder-*) ;; *) return ;; esac
  [ -n "$(git -C "$dir" status --porcelain 2>/dev/null)" ] || return
  branch=$(git -C "$dir" branch --show-current)
  [ -n "$branch" ] || { branch=wip/$(basename "$dir"); git -C "$dir" switch -q -c "$branch"; }
  git -C "$dir" add -A && git -C "$dir" commit -q -m "WIP: snapshot of an interrupted $agent run" --no-verify \
    && git -C "$dir" push -q -u origin "$branch" && echo "codex-agent: interrupted; work pushed to $branch" >&2
}
trap 'snapshot; exit 130' INT TERM HUP
{
  echo "You are the $agent agent of the slice flow, running on $model through Codex."
  echo "Your instructions are below; read CLAUDE.md where they say so (Codex does not load it for you)."
  echo
  awk 'f>=2; /^---$/{f++}' "$file"
  echo
  echo "## Brief"
  echo
  cat "$brief"
  if [ -n "$(ls -A "$ctx")" ]; then
    echo
    echo "Your sandbox has no network, so gh fails. Read GitHub from these copies, made just now:"
    for f in "$ctx"/*; do echo "- $f"; done
  fi
} > "$prompt"

"$codex" exec --skip-git-repo-check -C "$dir" -m "$model" -c model_reasoning_effort="$effort" \
  "${sandbox[@]}" -o "$report" - < "$prompt" 2>&1 | tee "$log" >&2
status=${PIPESTATUS[0]}

# A clean exit with a report is a success, whatever the log says: the log
# also holds every file and diff the agent read, which can name a rate limit.
[ "$status" -eq 0 ] && [ -s "$report" ] && exit 0
# On failure, Codex's own error is at the end of the log.
if tail -n 20 "$log" | grep -qiE 'usage limit|rate limit|not supported when using|model_not_found|does not exist or you do not have access|insufficient_quota'; then
  echo "codex-agent: GPT unavailable; start the Claude agent $agent" >&2
  exit 75
fi
if [ "$status" -ne 0 ] || [ ! -s "$report" ]; then
  snapshot
  echo "codex-agent: GPT run failed (exit $status); start the Claude agent $agent" >&2
  exit "$(( status == 0 ? 1 : status ))"
fi
exit 0
