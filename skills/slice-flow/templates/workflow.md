# How work moves: from idea to live

The reference for every session. Each state names the skill, document or
label behind it. Decisions happen on the left, code on the right, and nothing
crosses from one to the other except through a spec.

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

## Reading the map

- **Decide** produces decisions, never code. A map is done when no sub-issue
  is open, the fold-in included, and *Not yet specified* is empty. An empty
  frontier alone is not done; see [issue-tracker.md](issue-tracker.md) for
  abandoned claims and the fold-in.
- **Spec** is the only way from decisions to work. `/to-spec` synthesises the
  conversation or the map's decisions, agrees the test seams, and writes the
  spec and glossary. `/to-tickets` cuts it into vertical slices, each
  `ready-for-agent` with a size from the table in the `slice-flow` skill.
- **Build** is one ticket per builder session, in its own worktree, up to an
  open PR with CI green. The main session reviews and merges once the review
  passes and CI is green; the owner is asked only on a product decision the
  owner has not made, or an `escalate` slice. A slice
  built from a prototype is checked against the prototype's code, not its
  prose ([building-slices.md](../building-slices.md)).
- **Ship** closes the ticket only after the deploy and the live checks an
  agent can run now. What cannot be checked yet becomes a check task outside
  the ticket.
- **Labels** (Mermaid can't show colons): the map is `wayfinder:map`, the
  fold-in is a `wayfinder:task`, agent-ready is `ready-for-agent`, sizes are
  `size:xs` to `size:l` plus `escalate`, check tasks are `check:owner` or
  `check:agent`.
- **Retro** runs in the session that built, before it is cleared, and
  changes the environment: these docs, the checks, the standards
  the reviewer agents enforce.

## On-ramps

- A bug or request you did not write: **Bug → Triage**. Tickets `/to-tickets`
  wrote are agent-ready already and never go through triage.
- A small fix you report yourself while testing live: straight to **Ready**
  as a sized ticket.
- A product question that comes up while building: a `wayfinder:grilling`
  ticket on the relevant map, never answered inside the slice.
