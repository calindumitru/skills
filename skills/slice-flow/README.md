# slice-flow

My way of shipping with agents, on top of [Matt Pocock's engineering skills](https://github.com/mattpocock/skills). His skills take an idea to a spec and tickets (`/grill-with-docs`, `/wayfinder`, `/to-spec`, `/to-tickets`) and review the result (`/code-review`). The slice flow is what happens between: a **slice** (a `ready-for-agent` ticket with a size label) goes to a **builder** agent picked by size, up to an open PR with CI green; the **main session** reviews and merges it, and the slice closes only once it is live and checked.

Two skills, one set of agents, three repo templates:

| Piece | What it is |
|---|---|
| [`SKILL.md`](SKILL.md) | `/slice-flow`: the main session's steps from a ready ticket to a closed one, the size table, check tasks. Model-invoked: "build #42" reaches it. |
| [`agents/`](agents) | Five builder agents, one per size and one for escalations. Generic: no project name inside. |
| [`templates/building-slices.md`](templates/building-slices.md) | The builder's steps, the prototype rules and the PR body; one *Repo-specific* section for what the repo must say itself. |
| [`templates/issue-tracker-addendum.md`](templates/issue-tracker-addendum.md) | What gets appended to Matt's `docs/agents/issue-tracker.md`: the labels, abandoned claims, the fold-in ticket, prototype resolutions. |
| [`templates/workflow.md`](templates/workflow.md) | The two diagrams below, as `docs/agents/workflow.md` in the repo. |
| [`../setup-slice-flow`](../setup-slice-flow) | `/setup-slice-flow`: wires a repo in one run. |

## The route

```mermaid
flowchart TB
    idea([Idea]) --> grill
    bug([Bug or request]) --> triage

    subgraph decide [Decide]
        direction TB
        grill["/grill-with-docs"]
        map["/wayfinder map"]
    end
    subgraph spec [Spec]
        direction TB
        tospec["/to-spec"] --> totickets["/to-tickets"]
    end
    subgraph build [Build]
        direction TB
        builder["builder by size"] --> pr["PR, CI green"] --> review["reviewer agents"]
    end
    subgraph ship [Ship]
        direction TB
        merge["merge, review and CI green"] --> deploy["deploy watched"] --> checks["live checks"]
    end

    idea -.-> map
    grill --> tospec
    map -- fold-in ticket --> tospec
    totickets -- ready-for-agent + size --> builder
    triage["/triage"] -- ready-for-agent --> builder
    review --> merge
    checks --> closed([Closed]) --> retro["/retro"]

    classDef decide fill:#EEEDFE,stroke:#534AB7,color:#26215C
    classDef spec fill:#F4F3FD,stroke:#7F77DD,color:#26215C
    classDef build fill:#E1F5EE,stroke:#0F6E56,color:#04342C
    classDef ship fill:#F0FAF6,stroke:#1D9E75,color:#04342C
    classDef edge fill:#F1EFE8,stroke:#888780,color:#2C2C2A
    classDef retro fill:#FAECE7,stroke:#993C1D,color:#4A1B0C
    class grill,map decide
    class tospec,totickets spec
    class builder,pr,review build
    class merge,deploy,checks ship
    class idea,bug,triage,closed edge
    class retro retro
    style decide fill:#FBFAFE,stroke:#AFA9EC
    style spec fill:#FBFAFE,stroke:#CECBF6
    style build fill:#F7FCFA,stroke:#9FE1CB
    style ship fill:#F7FCFA,stroke:#9FE1CB
```

Decisions happen on the left and produce decisions, never code. Code happens on the right, one ticket per session. The only way from one side to the other is a spec. `/retro` after shipping changes the environment the next decide starts from: these docs, the checks, the standards the reviewer agents enforce.

## The full map

```mermaid
stateDiagram-v2
    [*] --> Idea
    Idea --> Grilling: fits one session
    Idea --> Charting: too big or foggy

    state "Decide" as Decide {
        Grilling: Grilling with /grill-with-docs
        state "Wayfinder map" as Map {
            Charting: Charting the map with /wayfinder
            Deciding: Deciding one ticket (research, prototype, grilling or task)
            FoldIn: Fold-in ticket, a task on the map
            Charting --> Frontier: tickets wired, research fired
            Frontier --> Deciding: claim the first open ticket
            Deciding --> Frontier: resolve, close, index on the map
            Frontier --> FoldIn: a part's last decision closes
        }
    }

    Grilling --> Implement: one session is enough
    Grilling --> Spec: more than one session
    FoldIn --> Spec

    Spec: Spec with /to-spec (seams agreed, spec and glossary written)
    Tickets: Tickets with /to-tickets (vertical slices, blocking edges)
    Spec --> Tickets
    Tickets --> Ready: agent-ready, sized

    Bug --> Triage
    Triage: Triage with /triage
    Triage --> Ready: agent-ready

    state "Build (docs/building-slices.md)" as Build {
        Ready --> Building: builder agent by size
        Building --> PullRequest: /tdd at the seams, CI green
        PullRequest --> Review: the reviewer agents, by the main session
        Review --> Building: changes asked
        Review --> Merged: review passed and CI green
    }
    Implement --> PullRequest: /implement here

    state "Ship" as Ship {
        Merged --> Deployed: deploy watched
        Deployed --> LiveChecks: the PR's After merge section
        LiveChecks --> Closed: evidence posted
        LiveChecks --> CheckTask: cannot check yet
        CheckTask: Check task for the owner or an agent
        CheckTask --> Closed: passes later
    }

    Closed --> Retro: /retro, same session
    Retro --> [*]

    classDef decide fill:#EEEDFE,stroke:#534AB7,color:#26215C
    classDef spec fill:#F4F3FD,stroke:#7F77DD,color:#26215C
    classDef build fill:#E1F5EE,stroke:#0F6E56,color:#04342C
    classDef ship fill:#F0FAF6,stroke:#1D9E75,color:#04342C
    classDef retro fill:#FAECE7,stroke:#993C1D,color:#4A1B0C
    class Grilling,Charting,Frontier,Deciding,FoldIn decide
    class Spec,Tickets,Triage spec
    class Ready,Building,PullRequest,Review,Implement build
    class Merged,Deployed,LiveChecks,CheckTask,Closed ship
    class Retro retro
```

Mermaid can't show colons, so the labels read: the map is `wayfinder:map`, the fold-in is a `wayfinder:task`, agent-ready is `ready-for-agent`, sizes are `size:xs` to `size:l` plus `escalate`, check tasks are `check:owner` or `check:agent`.

## What it adds to Matt's flow

| Gap in the default flow | What the slice flow does |
|---|---|
| Implementer agents inherit the parent model. | A size label routes each ticket to its builder agent, on Claude at the effort the size earns; the reviewers try GPT first for a second model's read, Claude as fallback (below). Never Sonnet or Fable. |
| `/implement` reviews its own work in the same context. | The builder stops at an open PR. The main session reviews with `/code-review` and merges once the review passes and CI is green; the owner is asked only on a product decision not yet made, or an `escalate` slice. |
| Nothing happens after code review. | A slice closes only after the deploy and the live checks an agent can run now. What can't be checked yet becomes a `check:owner` or `check:agent` task, so no slice and no session waits. |
| A wayfinder map hands off by convention, and an empty frontier reads as done. | The fold-in is a `wayfinder:task` on the map, created when the last decision it needs closes. An assigned ticket with no comment from its assignee is abandoned, not claimed. |
| `/prototype` folds the decision into code, and the builder reads prose. | A slice built from a prototype names branch, commit, variant and file as an acceptance criterion, the builder reads that code first, and the PR shows the two side by side. The resolution lists the intended differences. |
| `/pr` has no view past merge. | The PR body gains an **After merge** section: what the deploy applies and which checks to run, marked agent now, agent later or owner. It is the only place a slice's live checks are written; check tasks are made from it verbatim. |

## Sizes and models

| Label | Amount of work | Agent |
|---|---|---|
| `size:xs` | Text, docs or config only | the main session |
| `size:s` | A vertical slice so small that one layer changes | `slice-builder-s` |
| `size:m` | One vertical slice across layers; any migration or infrastructure | `slice-builder-m` |
| `size:l` | Several slices' worth in one issue | `slice-builder-l` |
| `escalate` (wins) | A costly mistake, or a rebuild after a failed review | `slice-builder-escalated` |

Claude builds, GPT reviews (the owner, 2026-10-24):

| Agent | Model · effort | Intelligence | Cost a task | Time a task |
|---|---|---|---|---|
| builders s, m; the main session on xs | Claude Opus 5.5 · medium, the agent files | 51.2 | $1.34 | 3.4 min |
| builders l, escalated | Claude Opus 5.5 · high, the agent files | 53.6 | $1.82 | 4.5 min |
| reviewers, first choice | GPT-6.1 Sol · high, through `scripts/codex-agent.sh` | 50.2 | $0.32 | 3.8 min |
| reviewers, fallback | Claude Opus 5.5 · medium, the agent files | 51.2 | $1.34 | 3.4 min |

The chart numbers are the cost-vs-intelligence Pareto frontier on [slopalytics.com](https://slopalytics.com/) (Artificial Analysis data, re-read 2026-10-24; its snapshot is dated 2026-10-13 and unchanged since the first read on 2026-10-21; max and no-reasoning settings hidden). Across GPT and Claude the frontier runs GPT-6 Luna, Haiku 5.5 low to xhigh, GPT-6.1 Sol low to xhigh, then Opus 5.5 medium, high and xhigh. No Sonnet, Fable, GPT-6 Astra, Gemini or Grok setting sits on it.

The split comes from measuring the runs, not the chart. The chart's cost is a proxy for how fast a flat-rate plan's usage window empties, and the Codex plan is the smaller budget: one GPT builder ran 20 to 30 minutes and spent 50 to 85 points of the 5-hour window (10 to 13 of the weekly one); three m builders at once took it from 7% to 91%, the next reviewers died mid-run and GPT was locked for six hours (2026-10-24). A reviewer spends 10 to 15 points in 2 to 6 minutes. Build time was never the model's: an m slice took 12 to 27 minutes on either model, 93 to 95% of it model turns (40 to 60 on GPT, 130 to 340 tool uses on Claude), commands about a minute. So builders run where the budget is, at Opus medium, and l and escalate spend Opus high where a mistake costs most; the reviewers spend the GPT budget on a second model's read, at Sol high (0.8 points under xhigh for a quarter less of the window). Re-check the chart when new models ship, and update SKILL.md, this table, the agents and the script's defaults together.

The script runs `codex exec` with the agent file's body and the brief as the prompt. A reviewer runs read-only; a builder, when the script is asked for one, gets a fresh worktree and a sandbox that writes only there and in the repo's git dir, with network on for `git push` and `gh`. It exits 75 when GPT is unavailable (no CLI, a usage limit, a refused model), and before starting when the newest Codex rollout's last rate-limit record puts the 5-hour window above 70% used or the weekly window above 85% (`SLICE_GPT_PRIMARY_MAX`, `SLICE_GPT_WEEKLY_MAX`), so the main session starts the Claude agent instead. Either is remembered until the window's reset time (`~/.cache/slice-flow/gpt-unavailable-until`): until then the script exits 75 before making a worktree. A builder's run whose report names no PR and no open decision exits 1: a sandbox once denied `git fetch` and the run came back clean and empty.

## Install

1. Matt's skills, then this repo's two skills into `~/.claude/skills/` (the root README has the one-liner).
2. In each repo: `/setup-matt-pocock-skills`, then `/setup-slice-flow`. The second one copies the agents, writes `docs/building-slices.md` with only its *Repo-specific* section asked about, appends to the tracker doc, writes `docs/agents/workflow.md`, creates the labels and points `CLAUDE.md` at it all.

Sessions started outside a repo don't load its `.claude/agents/`: install the agents at user scope (`ln -s ~/.claude/skills/slice-flow/agents/slice-*.md ~/.claude/agents/`), or the skill falls back to a general-purpose agent on Opus medium with worktree isolation. The GPT path needs the Codex CLI signed in (`codex login`); the script also finds the copy inside the ChatGPT app.

## Example prompts

- "Build #42." / "Pick up the next two slices."
- "What's ready to build?"
- "Size this ticket." / "Should this one be escalated?"
- "#42 is merged and deployed, close it."
- "Add the slice flow to this repo." (runs `/setup-slice-flow`)
