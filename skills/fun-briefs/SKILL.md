---
name: fun-briefs
description: Turn research, a wayfinder map or a long document into a brief that is fun to read and still accurate, as a playable card deck built from graded engagement evidence (ADHD-friendly by design). Use when asked for a brief, to present research results, or for a fun, gamified or ADHD-friendly version of a document.
---

# Fun briefs

A **brief** gets a reader through a body of work quickly and leaves them able to act on it. Here
"fun" is a means, not decoration: every playful element is a **payoff**, meaning something the reader
gains within a minute (an answer, a number, a decision), because later rewards are worth less to the
reader you are designing for. The design rules come from [`references/evidence.md`](references/evidence.md),
which grades each one. Read it before writing; it also lists the popular tricks that fail.

The default format is the **deck**: four worlds of short cards, with plays that give feedback
straight away. It is described in [`references/deck.md`](references/deck.md). The engine lives in
`assets/deck/`. A **booklet** is a long interactive page with widgets, kept as the reference companion;
make one only when the reader also needs every figure and source in one place. The examples to adapt
are `docs/business/site/` in fatto-giusto (the Libretto di Bottega) and `research/audiences-event-needs-2026-10-13/brief/`
on funvenio's research branch of the same name.

## 1. Gather the facts

Read the synthesis first: the map body and its Decisions so far, the summary files, and the
resolution comments. Read individual source files only for the numbers and caveats a card will
quote. Write down each number with its source file. Keep three kinds of claim apart: what was
measured, what was judged (scores, recommendations), and what is unknown. "Unknown" is a fact the
brief must show, and must never be shown as zero.

Done when every claim you plan to use has a source file and its kind.

## 2. Shape the deck

- **The 60-second version:** three to five lines that would do even if nothing else got read.
- **Worlds:** four, each one an area the reader would open on its own. Order them so the last is the
  boss level: the decisions the reader owns, or the myths the material exposes.
- **Cards:** each world gets 5–8 cards with one idea each. Each headline states the point. Use an
  `info` card to teach and a play to make it stick, either by retrieving the point or by predicting
  the next one. Turn every surprising number into a `guess`, and every decision the reader owns into
  a `decide` card that marks the recommendation.
- **Feedback:** each play's `why` explains the answer with its number or reason. XP is the garnish
  on that, not the meal.
- **Evidence grades:** when the material is research, every card's `tag` carries its strength
  ("Strong evidence", "No trial yet").

Done when every world has exactly three recap lines, and every `quiz`, `guess` and `order` card has a
`why` that would teach someone who guessed wrong.

## 3. Build

Copy `assets/deck/index.html` and `assets/deck/build.py` into the brief's folder and write its own
`c-deck.js`, starting from `assets/deck/c-deck.js`. Set a unique `Q.ui.key` and point `R()`/`I()` at
the real sources. Then run `python3 build.py <out.html>`.

## 4. Verify

Run `node <skill>/scripts/autoplay.mjs <out.html> <shots-dir>` from a directory where `playwright`
resolves. It plays every card in light and dark mode and fails on any page error or card that gets
stuck. Then look at the home screen and at one play per world at phone width, and fix anything that
wraps badly or crowds the card. Finally check every number in the deck against the source file
noted in step 1.

Done when autoplay prints OK and each number matches its source.

## 5. Deliver

Commit the brief's source (the engine copy, `c-deck.js`, `build.py` and a short README) beside the
research it presents. On a wayfinder research branch, push it without a PR. Put the built page where
the user can open it, and give them its absolute path. If a booklet exists, link it from
`Q.ui.fullLink`.
