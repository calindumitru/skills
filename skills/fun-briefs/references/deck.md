# The deck format

A deck is `assets/deck/index.html` (the engine: layout, card plays, rewards, saved progress) plus one
content file, `c-deck.js`, which sets `Q.ui` (strings) and `Q.worlds` (the cards). `build.py` inlines
the content into one self-contained page. Start from `assets/deck/c-deck.js`: it carries every `Q.ui`
key the engine reads.

## What the engine already does

Each of these maps to a row of `evidence.md`; keep them on.

- The home screen has three things: a "60-second version" (`gist`), an optional if-then start plan
  (`planQ`, `planOpts`, `planThen`), and the worlds as tiles the reader can open in any order.
- The top bar shows the work left in plain units: "N cards left · ~M min" (`left`, `secsPerCard`).
  On phones it replaces the progress bar.
- Progress saves to `localStorage` under `Q.ui.key`, and the home screen offers "pick up where you
  stopped". Give each brief its own key.
- Calm mode hides XP, toasts and confetti. Each card has read-aloud. ← → and 1–4 work on the
  keyboard, and the reader can swipe on touch. Reduced motion turns off all animation.
- A play must be answered before Next unlocks. Reading cards never block.
- XP: +20 for a quiz right first time, +5 for a wrong try, +25 for a close guess, +15 per decision,
  +50 and a badge per world. XP only ever comes after informational feedback, never instead of it.

## Worlds

```js
{ id: 'money', c: 'w2', title: 'Money', mins: 4, tease: 'One line on what this world gives you.',
  badge: { ico: '💰', name: 'Box Office' },
  recap: ['Three', 'things', 'to keep'],      // shown on the world-end card
  cards: [ /* 5–8 cards */ ] }
```

`c` is `w1`–`w4`. Those are the four colours: give each world its own. More than four worlds needs
new `--w5`/`--w5s` variables in the engine's CSS. Keep `mins` honest: about 35 seconds a card.

## Cards

Every card takes `h` (a headline of at most 12 words, which states the point), plus optional `tag`,
`p` (a string or an array of strings), `ul`, `more` (detail behind a tap) and `src` (the source line,
in Markdown). Inline Markdown works: `**bold**`, `` `code` ``, `[text](url)`.

| `type` | Extra fields | Use it for |
|---|---|---|
| `info` | none | One idea. Put the evidence grade in `tag` ("Strong evidence"). |
| `big` | `big` (the number) | One striking number with its meaning in `p`. |
| `quiz` | `opts` (2–4), `right` (index), `why` | Retrieval after the card that taught it, or a prediction before the reveal. True/false is `opts: ['True','False']` with `tag: 'True or false'`. |
| `guess` | `min`, `max`, `step`, `start`, `answer`, `tol`, `fmt(v)`, `why` | Slide to estimate a number, then reveal it. Surprising numbers make the best ones. |
| `order` | `items` (in the right order), `shown` (the display order, as indices), `why` | Ranking a priority order or a sequence. |
| `multi` | `opts`, `right` (an array of indices), `why` | "Which of these…": status checks and myth sorting. |
| `challenge` | `min`, `max`, `step`, `start`, `fmt(v)`, `calc(v)` → `{ win, cells: [[label, value, 'neg'\|'pos']] }`, `goalText`, `win`, `why` | Turning a model into a goal ("drag until it breaks even"). Use one per deck at most. |
| `decide` | `opts`, `lean` (index of the recommendation), `after` (one line per option), `short`, `ticket` (URL) | Decisions that belong to the reader. There's no right answer, and the pick is recorded. |
| `summary` | `from: [[worldId, cardIndex], …]`, `xp` | Collecting the `decide` picks into copyable text with their ticket links. |

`why` always explains: it names the number, the reason or the source. It never just says "correct".

## Shape of a good deck

- Four worlds of 5–8 cards each, about 15 minutes in all. The last world is the "boss level": the
  decisions, or the myths, whichever the brief builds towards.
- Within a world, alternate: an `info` card, then a play that retrieves it or predicts the next one.
  Never put three `info` cards in a row.
- Each world's `recap` gives exactly three lines: the things the reader should still know tomorrow.
- Use emoji only as signals (the world's badge, one per tag). Leave decoration and images out.
