import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.TV_PLAYWRIGHT_MODULE || 'playwright-core');

const [feedPath, templatePath, outDir] = process.argv.slice(2);
if (!feedPath || !templatePath || !outDir) throw new Error('Usage: node capture.mjs feed.json template.html frame-dir');
const feed = JSON.parse(fs.readFileSync(feedPath, 'utf8'));
if (!['TEST', 'MARKET'].includes(feed.mode) || !Array.isArray(feed.snapshots) || feed.snapshots.length !== 6) {
  throw new Error('Expected six TEST or MARKET snapshots');
}
fs.mkdirSync(outDir, { recursive: true });
const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH || undefined, args: ['--no-sandbox', '--disable-gpu'] });
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 });
  await page.goto(pathToFileURL(path.resolve(templatePath)).href);
  // Freeze the template's browser-only mock timers. The six input snapshots,
  // not setInterval, must be the sole source of each encoded video state.
  await page.evaluate(() => {
    const lastTimer = window.setInterval(() => {}, 60000);
    for (let timer = 1; timer <= lastTimer; timer += 1) window.clearInterval(timer);
  });
  await page.addStyleTag({ content: `body { width:1280px!important;height:720px!important;min-height:720px!important }
    .screen { width:1280px!important;height:720px!important;aspect-ratio:auto!important;border-width:0!important }
    .ticker-track { display:none!important } .scanlines { opacity:.35!important }` });
  for (let i = 0; i < 6; i++) {
    const snapshot = feed.snapshots[i];
    await page.evaluate(({ snapshot, mode, index }) => {
      const safeQuotes = snapshot.quotes.filter(q => /^[A-Z0-9]{1,6}$/.test(q.symbol) && Number.isFinite(q.price) && Number.isFinite(q.changePercent));
      if (!safeQuotes.length) throw new Error('Snapshot has no valid quotes');
      const money = v => '$' + v.toFixed(2);
      document.getElementById('quotes').innerHTML = safeQuotes.slice(0, 5).map(q => `<tr><td>${q.symbol}</td><td>${money(q.price)}</td><td class="${q.changePercent >= 0 ? 'up' : 'down'}">${q.changePercent >= 0 ? '▲' : '▼'} ${Math.abs(q.changePercent).toFixed(2)}%</td></tr>`).join('');
      document.querySelector('.ledbar').textContent = safeQuotes.slice(0, 4).map(q => `${q.symbol} ${q.price.toFixed(2)} ${q.changePercent >= 0 ? '▲' : '▼'}${Math.abs(q.changePercent).toFixed(2)}`).join('  ');
      document.getElementById('eyebrow').textContent = `MARKET DESK / ${String(index + 1).padStart(2, '0')}`;
      document.getElementById('headline').textContent = String(snapshot.headline || '').slice(0, 120);
      document.getElementById('deck').textContent = String(snapshot.deck || '').slice(0, 180);
      document.querySelector('.status').firstChild.textContent = mode === 'MARKET' ? '● MARKET TEST ' : '● TEST MODE ';
      document.getElementById('updated').textContent = mode === 'MARKET' ? 'READ-ONLY QUOTE SNAPSHOT' : 'MOCK QUOTE SNAPSHOT';
      document.querySelector('.clock span:last-child').textContent = mode === 'MARKET' ? 'MARKET TEST • NOT TRADING' : 'NOT A LIVE MARKET FEED';
      document.querySelector('.clock strong').textContent = mode === 'MARKET' ? 'MARKET SNAPSHOT' : 'TEST CLOCK';
      if (mode === 'MARKET') {
        document.querySelector('.board h2').textContent = 'MARKET NOTES';
        const notes = [
          ['LEAD QUOTE', `${safeQuotes[0].symbol} last ${money(safeQuotes[0].price)}.`],
          ['BOARD', `${safeQuotes.length} LCN symbols on this tape.`],
          ['SOURCE', 'Read-only market prices; no trades.'],
        ];
        document.querySelectorAll('.topnews').forEach((item, i) => {
          item.querySelector('strong').textContent = notes[i][0];
          item.lastChild.textContent = ` ${notes[i][1]}`;
        });
      }
    }, { snapshot, mode: feed.mode, index: i });
    await page.locator('.screen').screenshot({ path: path.join(outDir, `screen-${i}.png`) });
  }
} finally { await browser.close(); }
