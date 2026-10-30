// Plays every card of a built deck in headless Chromium and fails on any page error or stuck card.
// Usage: node autoplay.mjs <built.html> [shots-dir]   (needs the `playwright` package resolvable from the cwd)
import { chromium } from 'playwright';
import { pathToFileURL } from 'node:url';
import path from 'node:path';
const [file, shots] = process.argv.slice(2);
const b = await chromium.launch();
const errs = [];
for (const scheme of ['light', 'dark']) {
  const p = await b.newPage({ viewport: { width: 400, height: 860 }, colorScheme: scheme });
  p.on('pageerror', e => errs.push(e.message)); p.on('console', m => m.type() === 'error' && errs.push(m.text()));
  await p.goto(pathToFileURL(path.resolve(file)).href); await p.waitForTimeout(1000);
  if (shots) await p.screenshot({ path: `${shots}/home-${scheme}.png` });
  const worlds = await p.$$eval('.worlds [data-world]', x => x.length);
  let cards = 0;
  for (let w = 0; w < worlds; w++) {
    await p.click(`.worlds [data-world="${w}"]`);
    for (let i = 0; i < 40; i++) {
      if (await p.$('[data-quiz]:not([disabled])')) await p.click('[data-quiz="0"]');
      else if (await p.$('[data-act="lock"]')) await p.click('[data-act="lock"]');
      else if (await p.$('[data-order]:not([disabled])')) { const n = await p.$$eval('[data-order]', x => x.length); for (let j = 0; j < n; j++) await p.click(`[data-order="${j}"]`); }
      else if (await p.$('[data-multi]:not([disabled])')) { await p.click('[data-multi="0"]'); await p.click('[data-act="lock-multi"]'); }
      else if (await p.$('#cr')) await p.$eval('#cr', el => { el.value = el.max; el.dispatchEvent(new Event('input', { bubbles: true })); });
      else if (await p.$('[data-decide]')) await p.click('[data-decide="0"]');
      await p.waitForTimeout(450);
      if (shots && scheme === 'light' && i === 1) await p.screenshot({ path: `${shots}/w${w}-card.png` });
      cards++;
      const label = await p.textContent('#next');
      if (await p.$eval('#next', el => el.disabled)) { errs.push(`stuck: world ${w + 1}, card ${i + 1}`); break; }
      await p.click('#next'); await p.waitForTimeout(150);
      if (label.includes('Finish')) break;
    }
    await p.click('[data-act="home"]');
  }
  if (scheme === 'light') console.log(`${worlds} worlds, ${cards} cards played; ${await p.textContent('#left')}; ${await p.textContent('#xp')}`);
}
await b.close();
if (errs.length) { console.error('FAIL\n' + errs.join('\n')); process.exit(1); }
console.log('OK: no errors, no stuck cards, light and dark');
