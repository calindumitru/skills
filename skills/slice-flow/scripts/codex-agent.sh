#!/usr/bin/env bash
# Run one slice-flow agent on GPT through the Codex CLI: the first choice for
# the reviewers (SKILL.md, Models). The Claude agent of the same name is the
# fallback. Builders run on Claude; the script still runs one when asked.
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
# Exit 75: GPT is unavailable (no Codex CLI, usage limit, model refused), or
#          the last Codex run left too little of a usage window for another
#          agent. Start the Claude agent of the same name instead.
# Other non-zero: the GPT run failed, or a builder's report names no PR and
#          no open decision. Fall back to the Claude agent too; a failed run
#          is not retried on GPT.
#
# SLICE_GPT_MODEL (default gpt-6.1-sol) and SLICE_GPT_EFFORT (default high)
# override the choice; CODEX overrides the CLI path. SLICE_GPT_PRIMARY_MAX
# (default 70) and SLICE_GPT_WEEKLY_MAX (default 85) are the used-percent
# ceilings on the 5-hour and weekly windows above which no agent starts: a
# reviewer uses 10 to 15 points of the 5-hour window, a builder 50 to 85.
set -uo pipefail

agent=${1:?agent name}; repo=${2:?repo dir}; brief=${3:?brief file}; report=${4:?report file}
model=${SLICE_GPT_MODEL:-gpt-6.1-sol}
effort=${SLICE_GPT_EFFORT:-high}
primary_max=${SLICE_GPT_PRIMARY_MAX:-70}
weekly_max=${SLICE_GPT_WEEKLY_MAX:-85}

codex=${CODEX:-$(command -v codex || true)}
[ -z "$codex" ] && [ -x /Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex ] \
  && codex=/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex
if [ -z "$codex" ]; then echo "codex-agent: no Codex CLI found" >&2; exit 75; fi

# A usage limit holds until the reset time Codex names: until then, answer 75
# at once, before any worktree or run (the stamp holds the reset's epoch).
stamp=${XDG_CACHE_HOME:-$HOME/.cache}/slice-flow/gpt-unavailable-until
epoch_time() { date -d "@$1" '+%H:%M' 2>/dev/null || date -r "$1" '+%H:%M'; }
if [ -s "$stamp" ] && [ "$(date +%s)" -lt "$(cat "$stamp")" ]; then
  echo "codex-agent: GPT usage limit until $(epoch_time "$(cat "$stamp")"); start the Claude agent $agent" >&2
  exit 75
fi

# Headroom: the newest Codex rollout's last rate-limit record says how much of
# each usage window the previous run left, and when the window resets (a run
# that hit the limit logs a record without numbers, so walk back to one that
# has them). Above the ceiling, stamp the reset time and answer 75 before any
# worktree or run.
headroom=$(ls -t "${CODEX_HOME:-$HOME/.codex}"/sessions/*/*/*/rollout-*.jsonl 2>/dev/null | head -8 \
  | xargs -I{} sh -c 'grep -o "\"rate_limits\":{.*" "{}" | tail -1' 2>/dev/null \
  | python3 -I -c '
import sys,json
for raw in sys.stdin:
    raw=raw.strip()[len("\"rate_limits\":"):]
    depth=0
    for i,ch in enumerate(raw):
        depth+= ch=="{"; depth-= ch=="}"
        if depth==0: raw=raw[:i+1]; break
    try: rl=json.loads(raw)
    except Exception: continue
    p=rl.get("primary"); s=rl.get("secondary")
    if not p or p.get("used_percent") is None: continue
    s=s or {}
    print(int(p.get("used_percent") or 0), int(p.get("resets_at") or 0), int(s.get("used_percent") or 0), int(s.get("resets_at") or 0))
    break' 2>/dev/null)
if [ -n "$headroom" ]; then
  read -r p_used p_reset s_used s_reset <<< "$headroom"
  now=$(date +%s)
  if [ "$p_used" -gt "$primary_max" ] && [ "$p_reset" -gt "$now" ]; then
    mkdir -p "$(dirname "$stamp")" && echo "$p_reset" > "$stamp"
    echo "codex-agent: GPT 5-hour window $p_used% used (ceiling $primary_max%), resets $(epoch_time "$p_reset"); start the Claude agent $agent" >&2
    exit 75
  fi
  if [ "$s_used" -gt "$weekly_max" ] && [ "$s_reset" -gt "$now" ]; then
    mkdir -p "$(dirname "$stamp")" && echo "$s_reset" > "$stamp"
    echo "codex-agent: GPT weekly window $s_used% used (ceiling $weekly_max%), resets $(date -d "@$s_reset" '+%a %H:%M' 2>/dev/null || date -r "$s_reset" '+%a %H:%M'); start the Claude agent $agent" >&2
    exit 75
  fi
fi

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
# A builder's report must name its PR, or the open decision that stopped it:
# a run that ends with neither (a sandbox denied git, #707) is a failed run.
if [ "$status" -eq 0 ] && [ -s "$report" ]; then
  case $agent in
    slice-builder-*)
      if ! grep -qE 'github\.com/[^ )]+/pull/[0-9]+' "$report" \
         && ! grep -qiE 'product decision|open decision|blocked on|left open' "$report"; then
        snapshot
        echo "codex-agent: the GPT builder reported no PR and no open decision; start the Claude agent $agent" >&2
        exit 1
      fi ;;
  esac
  exit 0
fi
# On failure, Codex's own error is at the end of the log.
if tail -n 20 "$log" | grep -qiE 'usage limit|rate limit|not supported when using|model_not_found|does not exist or you do not have access|insufficient_quota'; then
  if tail -n 20 "$log" | grep -qiE 'usage limit|insufficient_quota'; then
    # "try again at 2:25 AM": the next such time; else an hour from now.
    at=$(tail -n 20 "$log" | grep -oiE 'try again at [0-9]{1,2}:[0-9]{2} ?[AP]M' | tail -1 | sed -E 's/^[Tt]ry again at //')
    now=$(date +%s)
    reset=$( [ -n "$at" ] && { date -d "$at" +%s 2>/dev/null || date -j -f '%I:%M %p' "$(echo "$at" | sed -E 's/ ?([AaPp][Mm])$/ \1/')" +%s 2>/dev/null; } )
    [ -n "$reset" ] || reset=$((now + 3600))
    [ "$reset" -gt "$now" ] || reset=$((reset + 86400))
    mkdir -p "$(dirname "$stamp")" && echo "$reset" > "$stamp"
  fi
  echo "codex-agent: GPT unavailable; start the Claude agent $agent" >&2
  exit 75
fi
if [ "$status" -ne 0 ] || [ ! -s "$report" ]; then
  snapshot
  echo "codex-agent: GPT run failed (exit $status); start the Claude agent $agent" >&2
  exit "$(( status == 0 ? 1 : status ))"
fi
exit 0
