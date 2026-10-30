# fun-briefs

Turns research, a wayfinder map or a long document into a brief that is fun to read and still
accurate: a playable card deck with four worlds, one idea per card, quizzes, guesses, a challenge,
the reader's decisions as a boss level, saved progress and a calm mode. Every design choice comes from
graded evidence on what keeps readers with ADHD engaged (`references/evidence.md`), including the
popular tricks that don't work (Bionic Reading, streaks, points as the engine).

- `SKILL.md`: gather, shape, build, verify, deliver.
- `references/evidence.md`: the graded principles and myths. `fun-grilling` reads it too.
- `references/deck.md`: the deck format and every card type.
- `assets/deck/`: the engine (`index.html`), `build.py` and a starter `c-deck.js`.
- `scripts/autoplay.mjs`: plays every card in headless Chromium and fails on errors or stuck cards.

Examples: the Funvenio audience brief's quest edition and the ADHD learning-engagement brief, both on
funvenio research branches (`brief-quest/`, `brief/`).

Example prompts: "turn this map into a brief", "make an ADHD-friendly version of this doc",
"present the research results as a fun brief".
