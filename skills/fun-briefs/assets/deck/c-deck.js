// Starter deck. Copy it beside index.html and build.py, then replace every card.
// Card types and fields: references/deck.md in the fun-briefs skill.
window.R = f => 'https://example.com/source/' + f;   // link to a source file
window.I = n => 'https://example.com/issues/' + n;    // link to a ticket

Q.ui = {
  key: 'brief:example:v1', docTitle: 'Example brief',
  kicker: 'Research brief · topic · date',
  title: 'The headline, {with the hook in colour}',
  lead: 'Four worlds, any order, about 15 minutes. Progress saves itself.',
  gistTitle: '⚡ The 60-second version',
  gist: ['**Point one** in a line.', '**Point two** in a line.', '**Point three** in a line.'],
  planQ: 'Quick plan, if you like: when will you play the first world?',
  planOpts: ['Right now', 'After my next coffee', 'Before lunch', 'Tonight'],
  planThen: 'Plan: {when}, I open the first world I haven\'t finished. One world, 3–4 minutes.',
  left: '{n} cards left · ~{m} min', allDoneShort: 'All done', secsPerCard: 35,
  calmOn: 'Calm mode: no XP or confetti', calmOff: 'Show XP and confetti',
  speak: 'Read this card aloud',
  anyOrder: 'Play in any order', resume: 'Pick up where you stopped',
  fullLink: R('full.md'), fullText: 'The full source',
  reset: 'Start over', resetAsk: 'Clear your progress and XP?',
  finaleLink: '🏆 See your trophy screen',
  tags: { info: 'Know this', big: 'One number', quiz: 'Quick quiz', guess: 'Guess', order: 'Put in order', multi: 'Pick all that apply', challenge: 'Challenge', decide: 'Your call', summary: 'Your picks' },
  more: 'Tell me more', next: 'Next →', finishWorld: 'Finish world ★',
  lock: 'Lock it in', undo: 'Undo last',
  yes: ['Nailed it.', 'Spot on.', 'Yes!', 'Exactly.'],
  no: 'Not quite. Here\'s the answer:', close: 'Close. The full answer:', orderWas: 'Here\'s the real order:',
  actual: 'The real number: {v}.',
  lean: 'research leans', noted: 'Noted. You can change it any time.', changeAny: 'You can change it any time.',
  copy: 'Copy my picks', copied: 'Copied ✓',
  whyRight: 'right first try', whyTried: 'for trying', whyClose: 'close guess', whyWin: 'challenge won', whyDecide: 'decision made', whyRead: 'all picked',
  badgeGot: 'Badge unlocked: {b}', bonus: '+50 XP world bonus', again: 'You already had this one.',
  recapTitle: 'Three things to keep',
  nextWorld: 'Next: {w} →', finaleBtn: '🏆 Finish', map: 'Map',
  finaleTitle: 'Brief cleared!', badges: 'badges', minutes: 'minutes',
  finaleText: 'One line on what the reader now has.',
  finaleNext: ['The next action, linked.'],
};

Q.worlds = [
  {
    id: 'one', c: 'w1', title: 'World one', mins: 3, tease: 'What this world gives you, in one line.',
    badge: { ico: '🎟️', name: 'Badge name' },
    recap: ['First thing to keep.', 'Second.', 'Third.'],
    cards: [
      { type: 'info', h: 'One idea, as a headline', p: 'One or two sentences.', more: 'Detail behind a tap.', src: `[Source](${R('file.md')})` },
      { type: 'quiz', h: 'A question the last card answered?', opts: ['Wrong', 'Right', 'Wrong'], right: 1, why: 'Why it is right, with the number.' },
    ],
  },
];
