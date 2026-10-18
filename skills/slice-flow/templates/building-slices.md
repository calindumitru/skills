# Building a slice

How a `ready-for-agent` issue goes from ticket to an open pull request. The
slice builder agents in `.claude/agents/` follow this, and so does any session
that builds a slice by hand. The size table and the main session's steps
(review, merge, deploy, close, check tasks) are in the `slice-flow` skill; the
whole route is in [docs/agents/workflow.md](agents/workflow.md).

## Who does what

- **The main session** (the one talking to the owner) picks the builder from
  the issue's size label (`escalate` wins) and starts it with the issue URL.
- **The builder** works in its own worktree, up to an open PR with CI green,
  then reports back (step 8). It never merges or deploys.
- **The main session** reviews the PR with `/code-review`, fixes it or sends
  it back, reports to the owner, merges (squash) once the review passes and
  CI is green, watches the deploy, runs the checks the PR's *After merge*
  section marks *agent now*, and closes the slice with the evidence. It
  waits for the owner's word only on a product decision the owner has not
  made, or an `escalate` slice. Every *agent later* or *owner* check becomes
  a `check:owner` or `check:agent` issue outside the slice, taken from that
  section verbatim.

## Steps for the builder

1. **Read the whole issue:** its body and **every comment**. Notes from later
   decisions are posted as comments, and they win where they conflict with
   the body. Open the tickets it links when something is unclear, and read
   the spec sections and glossary terms it names. Use the glossary's terms in
   code, commits and the PR.
   - **If the issue names a prototype** (a `prototype/<name>` branch, a
     commit and a variant), read that code before building: `git fetch
     origin prototype/<name>` then `git show <commit>:<path>` for each file
     the variant renders, and run it when the look matters (`git worktree
     add` on that commit). The prototype is the reference where the slice's
     prose is silent, and the slice's intended-differences list says where
     it isn't. Take none of its shortcuts: stub data, missing states, no
     tests.
2. **Start from a fresh default branch.** Your worktree may have started
   from a stale checkout: `git fetch origin` then
   `git switch -c <feat|fix|chore>/<slug> origin/<default>`, and install
   dependencies in the worktree (*Repo-specific* says how).
3. **Build it.** Call the Skill tool with `tdd` at the seams the issue names.
   Run the typecheck and single test files often, and the full suite once at
   the end (*Repo-specific* has the commands and the repo's own rules for
   migrations, deploys and infrastructure).
4. **Check user-facing changes in the real app** (*Repo-specific* says how
   to run it; pick non-default ports, other sessions run servers too).
   Measure rather than eyeball: sizes, timings, counts, and no horizontal
   scroll at phone width.
   - **Against a prototype,** run the prototype's variant and the build side
     by side at phone and desktop width, screenshot both, and list every
     visible difference: each is either on the intended-differences list or
     a bug to fix before the PR. Compare the behaviour the resolution
     describes too (what a tap, a drag or a resize does), not only the first
     paint.
5. **Update the docs** the issue's Docs section names.
6. **Open the PR** to the default branch. Commit in small steps and push.
   - **Title:** an imperative sentence naming the change.
   - **Body:** call the Skill tool with `pr` (Summary, Evidence, Merge
     Danger), then add one more section, **After merge**: what the deploy
     applies and which live checks to run, each marked *agent now*, *agent
     later (when)* or *owner*, with the exact steps and what passing looks
     like. This section is the only place the slice's checks are written:
     the main session runs the *agent now* ones and makes check tasks from
     the rest verbatim. For a slice built from a prototype, Evidence holds the
     side-by-side screenshots (prototype left, build right, both widths) and
     the difference list, each marked intended or fixed.
   - **No closing keyword before an issue number** (close, closes, closed,
     fix, fixes, fixed, resolve, resolves, resolved): the main session closes
     the slice after the deploy and the live checks, and GitHub would close
     it on merge whatever words follow.
   - Follow the commit and PR attribution your harness gives you. Wait for CI
     and fix it until it's green.
7. **Never:** merge, deploy or re-run a deploy; change repository settings
   or variables; print a secret or anyone's email. *Repo-specific* adds the
   repo's own never-rules.
8. **Report back** to the main session: the PR URL and CI state; what you
   checked, with numbers; your judgement calls; anything left open. If the
   issue leaves a **product decision** open, stop and report it rather than
   guess.

## Slices built from a prototype

A slice that builds what a `wayfinder:prototype` ticket settled is a copy
job, not a fresh design: the owner approved a component, and the build has
to look and behave like it. Prose never carries that fully, so the slice
points at the code the owner saw and the build is checked against it.

- **The slice names the reference** as an acceptance criterion: the
  `prototype/<name>` branch, the commit, the variant and the file that
  renders it, plus the ticket's resolution comment. For example: "Matches
  `prototype/map-list` @ `0631bae`, `?variant=B4`,
  `src/components/prototype-map/Canvas.tsx`, apart from the intended
  differences in #235's resolution."
- **Intended differences are listed, not implied.** The prototype runs on
  stub data in a dev build and skips polish, so some things may differ: real
  data, the shared component's existing furniture, loading and error states.
  The prototype ticket's resolution names those; everything it doesn't name
  is meant to match. The slice repeats the list or links it.
- **Layout work is at least `size:m`.**

## Repo-specific

<!-- The only section /setup-slice-flow fills in. Keep it to what the
     environment can't tell an agent: commands, conventions, never-rules. -->

- **Default branch:** `<main>`.
- **Install and test:** `<install command>`; typecheck `<command>`; one test
  file `<command>`; full suite `<command>`.
- **Run the app locally:** `<commands, with how to pick a port>`.
- **Docs a slice updates:** `<spec file, glossary, infra notes>`.
- **Deploy and live checks:** `<how a merge deploys, how to watch it, how to
  read the deployed version>`.
- **Repo rules the builder follows:** `<migrations, expand/contract,
  infrastructure, platform gotchas: link the docs rather than restate them>`.
- **Never:** `<profiles, secrets, environments the builder must not touch>`.
