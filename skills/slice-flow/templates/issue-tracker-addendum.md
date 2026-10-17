
## Slice flow

Added by `/setup-slice-flow`. The `slice-flow` skill and the slice builder
agents read this with the sections above.

### Build work

Work an agent can build is a `ready-for-agent` issue with exactly one size
label, `size:xs`, `size:s`, `size:m` or `size:l`, by amount of work, and
`escalate` on top when a mistake would be costly. A human prerequisite for a
build is `ready-for-human`. A live check that outlives a slice is
`check:owner` or `check:agent`. The size table is in the `slice-flow` skill;
the builder's steps are in `docs/building-slices.md`.

### Wayfinding additions

- **Abandoned claims.** Sessions here are short and end at a phase boundary,
  so a claim can outlive its session. An open ticket that is assigned but
  has **no comment from the assignee** is abandoned, not claimed: treat it as
  on the frontier, and remove the stale assignee before claiming it. A
  claimed ticket with at least one comment from the assignee is in progress;
  leave it. This refines the **Frontier query** above.
- **The fold-in is a ticket, never only fog.** A map's decisions become work
  outside the map: spec and glossary edits with `/to-spec`, then
  `ready-for-agent` slices with `/to-tickets`. That step is a `wayfinder:task`
  child of the map, titled "Fold … into the spec and write the slices",
  created by whichever session **closes the last decision it depends on**,
  blocked by any decision still open. It stays on the map until the slices
  exist. "All decisions are taken" with no fold-in ticket means the map is
  not done; create the ticket. A map whose decisions can be built in parts
  gets one fold-in ticket per part, blocked by that part's decisions, so
  building starts before the whole map clears.
- **Done** means no open sub-issues (the fold-in included) and *Not yet
  specified* empty. An empty frontier alone is not done: check for blocked
  and abandoned tickets and for fog first, and say which it is.
- **Prototype resolutions** also name the reference the build must match
  (branch, commit, variant, file) and end with an **Intended differences**
  list: what the real build may do differently from the prototype (real
  data, the shared component's furniture, loading and error states, anything
  the owner waved through). Write "none" rather than leaving it out: the
  builder treats everything not listed as meant to match.
