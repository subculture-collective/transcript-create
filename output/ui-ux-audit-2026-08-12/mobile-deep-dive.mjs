import playwright from '../../e2e/node_modules/@playwright/test/index.js';
import fs from 'node:fs/promises';
import path from 'node:path';

const { chromium } = playwright;
const outDir = new URL('./', import.meta.url).pathname;
const baseURL = 'http://10.0.0.200:5173';
const videoId = '442156c6-e43e-46fb-95f5-9758df70c18c';

async function proxyApi(context) {
  await context.route('**/api/**', async (route) => {
    const target = new URL(route.request().url());
    target.protocol = 'http:';
    target.hostname = '10.0.0.200';
    target.port = '41177';
    target.pathname = target.pathname.replace(/^\/api(?=\/|$)/, '');
    const response = await route.fetch({ url: target.href });
    await route.fulfill({ response });
  });
}

async function box(locator) {
  if (!(await locator.count())) return null;
  const b = await locator.first().boundingBox();
  return b && Object.fromEntries(Object.entries(b).map(([k, v]) => [k, Math.round(v)]));
}

const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', headless: true });
const context = await browser.newContext({
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 3,
  isMobile: true,
  hasTouch: true,
  reducedMotion: 'reduce',
});
await proxyApi(context);
const page = await context.newPage();
const evidence = { viewport: { width: 390, height: 844 }, feed: {}, video: {}, interaction: {} };

await page.goto(`${baseURL}/episodes`, { waitUntil: 'networkidle' });
await page.waitForSelector('section[aria-label="Stream results"] a');
await page.screenshot({ path: path.join(outDir, 'mobile-feed-top-viewport.png') });
evidence.feed = await page.evaluate(() => {
  const rect = (el) => el ? Object.fromEntries(['x','y','width','height','top','right','bottom','left'].map((k) => [k, Math.round(el.getBoundingClientRect()[k])])) : null;
  const cards = [...document.querySelectorAll('section[aria-label="Stream results"] > a')];
  const header = document.querySelector('header');
  const h1 = document.querySelector('h1');
  const results = document.querySelector('section[aria-label="Stream results"]');
  const filterForm = h1?.closest('section') || h1?.parentElement?.parentElement;
  const topPagination = results?.previousElementSibling;
  return {
    documentHeight: document.documentElement.scrollHeight,
    header: rect(header),
    heading: rect(h1),
    filterArea: rect(filterForm),
    topPagination: rect(topPagination),
    resultsStartY: results ? Math.round(results.getBoundingClientRect().top + scrollY) : null,
    cards: cards.slice(0, 6).map((card) => ({
      rect: rect(card),
      title: card.querySelector('h2')?.textContent?.trim(),
      image: rect(card.querySelector('img')),
      imageLoaded: card.querySelector('img')?.complete && card.querySelector('img')?.naturalWidth > 0,
      text: card.innerText,
    })),
    visibleAboveFold: cards.filter((card) => {
      const r = card.getBoundingClientRect();
      return r.top < innerHeight && r.bottom > 0;
    }).length,
  };
});

const cards = page.locator('section[aria-label="Stream results"] > a');
for (let i = 0; i < Math.min(5, await cards.count()); i++) {
  await cards.nth(i).scrollIntoViewIfNeeded();
  await page.waitForTimeout(400);
  if (i === 2) await page.screenshot({ path: path.join(outDir, 'mobile-feed-scrolled-viewport.png') });
}
evidence.feed.loadedAfterScroll = await cards.evaluateAll((nodes) => nodes.slice(0, 8).map((card) => ({
  title: card.querySelector('h2')?.textContent?.trim(),
  imageLoaded: card.querySelector('img')?.complete && card.querySelector('img')?.naturalWidth > 0,
})));

await page.goto(`${baseURL}/v/${videoId}`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('h1');
await page.waitForSelector('iframe', { timeout: 30_000 }).catch(() => {});
await page.waitForTimeout(1800);
await page.screenshot({ path: path.join(outDir, 'mobile-video-top-viewport.png') });
evidence.video = await page.evaluate(() => {
  const rect = (el) => el ? Object.fromEntries(['x','y','width','height','top','right','bottom','left'].map((k) => [k, Math.round(el.getBoundingClientRect()[k])])) : null;
  const player = document.querySelector('iframe')?.closest('.overflow-hidden') || document.querySelector('iframe');
  const transcript = document.querySelector('.transcript-shell');
  const intelligence = [...document.querySelectorAll('section,div')].find((el) => el.querySelector(':scope > h2')?.textContent?.includes('Related episodes'));
  const header = document.querySelector('.episode-masthead');
  return {
    documentHeight: document.documentElement.scrollHeight,
    header: rect(header),
    h1: rect(document.querySelector('h1')),
    player: rect(player),
    iframe: rect(document.querySelector('iframe')),
    intelligence: rect(intelligence),
    transcript: rect(transcript),
    playerDocumentY: player ? Math.round(player.getBoundingClientRect().top + scrollY) : null,
    transcriptDocumentY: transcript ? Math.round(transcript.getBoundingClientRect().top + scrollY) : null,
    playerViewportShare: player ? Number((player.getBoundingClientRect().height / innerHeight).toFixed(3)) : null,
    playerScreenWidthShare: player ? Number((player.getBoundingClientRect().width / innerWidth).toFixed(3)) : null,
  };
});

const iframe = page.locator('iframe').first();
if (await iframe.count()) {
  await iframe.scrollIntoViewIfNeeded();
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(outDir, 'mobile-video-player-viewport.png') });
  evidence.video.playerAfterScroll = await box(iframe);
  evidence.video.playerScrollY = await page.evaluate(() => Math.round(scrollY));
  await page.evaluate(() => scrollBy(0, 500));
  await page.waitForTimeout(400);
  evidence.video.playerAfterAdditionalScroll = await box(iframe);
  evidence.video.playerStickyCheckScrollY = await page.evaluate(() => Math.round(scrollY));
  await page.screenshot({ path: path.join(outDir, 'mobile-video-player-scrolled-away.png') });
}

const transcript = page.locator('.transcript-shell').first();
if (await transcript.count()) {
  await transcript.scrollIntoViewIfNeeded();
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(outDir, 'mobile-video-transcript-viewport.png') });
  evidence.video.transcriptAfterScroll = await box(transcript);
  evidence.video.transcriptScrollY = await page.evaluate(() => Math.round(scrollY));
}

// Inspect sentence activation on touch and whether the player remains visible.
const sentence = page.locator('.transcript-sentence').first();
if (await sentence.count()) {
  const before = await page.evaluate(() => ({ scrollY, url: location.href }));
  await sentence.tap();
  await page.waitForTimeout(500);
  const after = await page.evaluate(() => ({ scrollY, url: location.href }));
  evidence.interaction.sentenceTap = { before, after, sentence: await box(sentence), player: await box(iframe) };
  await page.screenshot({ path: path.join(outDir, 'mobile-video-sentence-selected.png') });
}

await fs.writeFile(path.join(outDir, 'mobile-deep-dive.json'), JSON.stringify(evidence, null, 2));
console.log(JSON.stringify(evidence, null, 2));
await browser.close();
