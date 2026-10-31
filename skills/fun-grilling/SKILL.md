---
name: fun-grilling
description: Make a grilling session engaging without making it lighter. Show a map of the design tree, ask short rounds through the question UI, give a payoff after every round (what was settled, unlocked and ruled out), vary the question formats, and offer playbacks and painless pause points. Use alongside the grilling skill whenever you grill the user, including on wayfinder grilling tickets.
---

# Fun grilling

This runs on top of `grilling`, which still decides *what* to ask: the design tree, the frontier, one
round at a time, a recommended answer for each question. This skill decides how a round *feels*.
The reader it is designed for discounts delayed rewards steeply and gets bored easily, so each round
has to pay off on its own instead of saving the reward for the end of the session. The rules come
from [`references/evidence.md`](references/evidence.md), graded there.
In this skill a **payoff** is visible progress plus an explained consequence. Points, scores and
streaks are not used (the evidence grades them no-evidence or harmful).

## Open with the map

Before round 1, send one short message:

- **The goal in one line**, and what the user will hold when the session ends ("a settled pricing model and three tickets").
- **The tree as branches:** a compact list of the areas still to decide, each with its rough number of
  decisions, then the total in plain units: "about 12 decisions, 4 rounds".
- **The exit:** say that "park" at any point saves the ledger and stops, and resuming costs nothing.

## Run each round

Ask the round's frontier through the question UI (`AskUserQuestion`): at most four questions, so a
bigger frontier becomes two rounds.

- **Header chip:** the branch name, kept short ("Pricing").
- **Options:** concrete labels of five words or fewer. Put your recommendation first, marked "(Recommended)".
- **Previews:** when a choice changes something the user can see (a screen, a message, a schema, an
  API shape), put the result in each option's `preview`. Seeing the consequence is the fastest payoff
  there is.

Vary the format from round to round so no two rounds in a row feel the same. Pick whichever fits the decision:

| Format | Shape |
|---|---|
| Either/or | Two or three options; the default. |
| Pick the mockup | Options whose previews show the outcome. |
| Rank the stakes | `multiSelect`: "Which two of these matter most?", to narrow a broad branch before deciding it. |
| Bet, then reveal | The user predicts a fact you've already looked up (usage, cost, what the code does), and the reveal comes in the payoff. Only use this when the fact is in hand. |
| Pre-mortem | "Six months on, this failed. Which cause is most likely?" Each option is a risk, and the pick decides what to guard against. |
| Steelman | "Strongest case for the option you're leaning against?" Use it only on a close call. |

## Pay off every round

After the answers, before the next round, send a short message:

```
✅ Settled: <decision>, <decision>
🔓 Unlocked: <the questions these answers made askable>
✂️ Ruled out: <options or branches now gone>
<N> decisions left · ~<R> rounds
```

Add one line of consequence when an answer changes something non-obvious ("so the API needs a
version field"). These three emoji are the only ones. If a bet was placed, reveal it here, with its source.

## Playback and pause points

When a branch closes, or after every third round, give a **playback**: the branch's decisions in
three lines or fewer. Then offer the user a choice between going on and parking.

To **park**, write the ledger where the grilling records its outcome (the wayfinder ticket's comment,
the spec draft), with the open frontier listed. Resuming starts from that ledger and its next round.

If the answers grow terse or the user starts picking the first option every time, offer two ways out:
take all the remaining recommendations for the current branch as one batch, which the user still
confirms, or park.

## Close with the decision card

When the frontier is empty, show the whole ledger grouped by branch. Under it, list what is now
unblocked (tickets, slices, the next map step) and the single next action. Then do grilling's own
close: confirm the shared understanding before acting on any of it.
