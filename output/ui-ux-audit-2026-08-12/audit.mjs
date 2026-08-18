import playwright from '../../e2e/node_modules/@playwright/test/index.js';
import fs from 'node:fs/promises';
import path from 'node:path';

const { chromium } = playwright;

const outDir = new URL('./', import.meta.url).pathname;
const baseURL = 'http://10.0.0.200:5173';
const videoId = '442156c6-e43e-46fb-95f5-9758df70c18c';
const routes = [
  ['home', '/'],
  ['search-results', '/search?q=housing'],
  ['search-empty', '/search?q=xyzzynotarealarchivequery987654'],
  ['explore', '/explore'],
  ['episodes', '/episodes'],
  ['timeline', '/timeline'],
  ['topic', '/topics/housing'],
  ['video', `/v/${videoId}`],
  ['login', '/login'],
  ['saved-protected', '/saved'],
  ['not-found', '/this-route-does-not-exist'],
];
const viewports = [
  ['desktop', { width: 1440, height: 1000 }],
  ['tablet', { width: 768, height: 1024 }],
  ['mobile', { width: 390, height: 844 }],
];

function safeName(value) {
  return value.replace(/[^a-z0-9-]+/gi, '-').replace(/^-|-$/g, '').toLowerCase();
}

const browser = await chromium.launch({
  executablePath: '/usr/bin/google-chrome',
  headless: true,
  args: ['--disable-dev-shm-usage'],
});
const results = [];

async function proxyApi(context) {
  await context.route('**/api/**', async (route) => {
    const request = route.request();
    const target = new URL(request.url());
    target.protocol = 'http:';
    target.hostname = '10.0.0.200';
    target.port = '41177';
    target.pathname = target.pathname.replace(/^\/api(?=\/|$)/, '');
    try {
      const response = await route.fetch({ url: target.href });
      await route.fulfill({ response });
    } catch (error) {
      await route.abort('failed');
    }
  });
}

for (const [viewportName, viewport] of viewports) {
  const context = await browser.newContext({
    viewport,
    colorScheme: 'light',
    reducedMotion: 'reduce',
    locale: 'en-US',
  });
  await proxyApi(context);
  const page = await context.newPage();
  await page.addInitScript(() => {
    window.__auditVitals = { cls: 0, lcp: 0, longTasks: [] };
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        if (!entry.hadRecentInput) window.__auditVitals.cls += entry.value;
      }
    }).observe({ type: 'layout-shift', buffered: true });
    new PerformanceObserver((list) => {
      const entries = list.getEntries();
      if (entries.length) window.__auditVitals.lcp = entries.at(-1).startTime;
    }).observe({ type: 'largest-contentful-paint', buffered: true });
    new PerformanceObserver((list) => {
      window.__auditVitals.longTasks.push(...list.getEntries().map((e) => ({ start: e.startTime, duration: e.duration })));
    }).observe({ type: 'longtask', buffered: true });
  });

  for (const [routeName, route] of routes) {
    const consoleMessages = [];
    const failedRequests = [];
    const badResponses = [];
    const onConsole = (msg) => {
      if (['error', 'warning'].includes(msg.type())) consoleMessages.push({ type: msg.type(), text: msg.text() });
    };
    const onFailed = (request) => failedRequests.push({ url: request.url(), failure: request.failure()?.errorText });
    const onResponse = (response) => {
      if (response.status() >= 400) badResponses.push({ status: response.status(), url: response.url() });
    };
    page.on('console', onConsole);
    page.on('requestfailed', onFailed);
    page.on('response', onResponse);

    const started = Date.now();
    let navigationError = null;
    try {
      await page.goto(`${baseURL}${route}`, { waitUntil: 'networkidle', timeout: 60_000 });
    } catch (error) {
      navigationError = String(error);
    }
    await page.waitForTimeout(1200);

    const audit = await page.evaluate(() => {
      function labelFor(el) {
        const aria = el.getAttribute('aria-label')?.trim();
        if (aria) return aria;
        const labelledBy = el.getAttribute('aria-labelledby');
        if (labelledBy) return labelledBy.split(/\s+/).map((id) => document.getElementById(id)?.textContent?.trim() || '').join(' ').trim();
        if (el.id) {
          const label = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
          if (label?.textContent?.trim()) return label.textContent.trim();
        }
        if (el.closest('label')?.textContent?.trim()) return el.closest('label').textContent.trim();
        if (el instanceof HTMLInputElement && el.type === 'image' && el.alt) return el.alt;
        return '';
      }
      function accessibleName(el) {
        return labelFor(el) || el.getAttribute('title')?.trim() || el.textContent?.trim() || (el instanceof HTMLImageElement ? el.alt : '');
      }
      function luminance(rgb) {
        const match = rgb.match(/[\d.]+/g);
        if (!match || match.length < 3) return null;
        const values = match.slice(0, 3).map(Number).map((v) => {
          const c = v / 255;
          return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
        });
        return 0.2126 * values[0] + 0.7152 * values[1] + 0.0722 * values[2];
      }
      function opaqueBackground(el) {
        let node = el;
        while (node) {
          const color = getComputedStyle(node).backgroundColor;
          const parts = color.match(/[\d.]+/g)?.map(Number) || [];
          if (parts.length === 3 || (parts.length >= 4 && parts[3] > 0.95)) return color;
          node = node.parentElement;
        }
        return 'rgb(255, 255, 255)';
      }
      const interactiveSelector = 'a[href],button,input,select,textarea,[role="button"],[tabindex]:not([tabindex="-1"])';
      const interactive = [...document.querySelectorAll(interactiveSelector)].filter((el) => {
        const s = getComputedStyle(el);
        return s.display !== 'none' && s.visibility !== 'hidden' && el.getBoundingClientRect().width > 0 && el.getBoundingClientRect().height > 0;
      });
      const tapTargets = interactive.map((el) => {
        const r = el.getBoundingClientRect();
        return { tag: el.tagName, name: accessibleName(el).slice(0, 100), width: Math.round(r.width), height: Math.round(r.height) };
      }).filter((x) => x.width < 44 || x.height < 44);
      const unlabeled = interactive.filter((el) => !accessibleName(el)).map((el) => el.outerHTML.slice(0, 240));
      const ids = [...document.querySelectorAll('[id]')].map((el) => el.id);
      const duplicateIds = [...new Set(ids.filter((id, i) => ids.indexOf(id) !== i))];
      const headings = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].map((el) => ({ level: Number(el.tagName[1]), text: el.textContent?.trim().slice(0, 160) }));
      const headingSkips = headings.slice(1).filter((h, i) => h.level > headings[i].level + 1);
      const missingAlt = [...document.images].filter((img) => !img.hasAttribute('alt')).map((img) => img.src);
      const tinyText = [...document.querySelectorAll('body *')].filter((el) => {
        const r = el.getBoundingClientRect();
        const s = getComputedStyle(el);
        return el.childElementCount === 0 && el.textContent?.trim() && r.width > 0 && r.height > 0 && parseFloat(s.fontSize) < 12;
      }).slice(0, 80).map((el) => ({ text: el.textContent.trim().slice(0, 100), size: getComputedStyle(el).fontSize }));
      const contrast = [...document.querySelectorAll('body *')].filter((el) => {
        const r = el.getBoundingClientRect();
        return el.childElementCount === 0 && el.textContent?.trim() && r.width > 0 && r.height > 0;
      }).slice(0, 500).map((el) => {
        const s = getComputedStyle(el);
        const fg = luminance(s.color);
        const bg = luminance(opaqueBackground(el));
        if (fg == null || bg == null) return null;
        const ratio = (Math.max(fg, bg) + 0.05) / (Math.min(fg, bg) + 0.05);
        const large = parseFloat(s.fontSize) >= 24 || (parseFloat(s.fontSize) >= 18.66 && Number(s.fontWeight) >= 700);
        return { text: el.textContent.trim().slice(0, 100), ratio: Number(ratio.toFixed(2)), threshold: large ? 3 : 4.5, color: s.color, background: opaqueBackground(el) };
      }).filter(Boolean).filter((x) => x.ratio < x.threshold).slice(0, 80);
      const nav = performance.getEntriesByType('navigation')[0];
      return {
        url: location.href,
        title: document.title,
        bodyText: document.body.innerText.slice(0, 12_000),
        headings,
        headingSkips,
        landmarks: [...document.querySelectorAll('header,nav,main,aside,footer,[role="main"],[role="navigation"],[role="search"]')].map((el) => ({ tag: el.tagName, role: el.getAttribute('role'), label: el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') || '' })),
        interactiveCount: interactive.length,
        unlabeled,
        tapTargets,
        duplicateIds,
        missingAlt,
        tinyText,
        contrast,
        horizontalOverflow: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - innerWidth,
        scrollWidth: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
        viewport: { width: innerWidth, height: innerHeight },
        vitals: window.__auditVitals,
        navigation: nav ? { domContentLoaded: nav.domContentLoadedEventEnd, load: nav.loadEventEnd, transferSize: nav.transferSize, decodedBodySize: nav.decodedBodySize } : null,
      };
    });

    const cdp = await context.newCDPSession(page);
    const ax = await cdp.send('Accessibility.getFullAXTree');
    const axSummary = {
      nodes: ax.nodes.length,
      ignored: ax.nodes.filter((n) => n.ignored).length,
      names: ax.nodes.filter((n) => ['button', 'link', 'textbox', 'searchbox', 'heading'].includes(n.role?.value)).map((n) => ({ role: n.role?.value, name: n.name?.value || '', ignored: n.ignored })),
    };
    const fileBase = `${viewportName}-${safeName(routeName)}`;
    await page.screenshot({ path: path.join(outDir, `${fileBase}.png`), fullPage: true });
    results.push({ viewport: viewportName, routeName, route, durationMs: Date.now() - started, navigationError, ...audit, axSummary, consoleMessages, failedRequests, badResponses });
    page.off('console', onConsole);
    page.off('requestfailed', onFailed);
    page.off('response', onResponse);
  }
  await context.close();
}

// Keyboard and interaction journey in a fresh desktop context.
const journeyContext = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
await proxyApi(journeyContext);
const journeyPage = await journeyContext.newPage();
const journey = { steps: [], focusOrder: [], errors: [] };
journeyPage.on('pageerror', (error) => journey.errors.push(String(error)));
await journeyPage.goto(baseURL, { waitUntil: 'networkidle' });
for (let i = 0; i < 24; i++) {
  await journeyPage.keyboard.press('Tab');
  journey.focusOrder.push(await journeyPage.evaluate(() => {
    const el = document.activeElement;
    return { tag: el?.tagName, text: el?.textContent?.trim().slice(0, 100), aria: el?.getAttribute('aria-label'), href: el?.getAttribute('href') };
  }));
}
await journeyPage.goto(baseURL, { waitUntil: 'networkidle' });
const search = journeyPage.getByRole('searchbox', { name: /search the hasanabi archive/i });
await search.fill('housing');
await search.press('Enter');
await journeyPage.waitForLoadState('networkidle');
journey.steps.push({ name: 'home search submit', url: journeyPage.url(), h1: await journeyPage.locator('h1').first().textContent() });
const firstResultLink = journeyPage.locator('a[href*="/v/"]').first();
if (await firstResultLink.count()) {
  const href = await firstResultLink.getAttribute('href');
  await firstResultLink.click();
  await journeyPage.waitForLoadState('networkidle');
  journey.steps.push({ name: 'open first cited result', href, url: journeyPage.url(), h1: await journeyPage.locator('h1').first().textContent() });
}
await journeyPage.goto(baseURL, { waitUntil: 'networkidle' });
const themeButton = journeyPage.getByRole('button', { name: /theme|dark|light/i }).first();
if (await themeButton.count()) {
  const before = await journeyPage.evaluate(() => document.documentElement.className);
  await themeButton.click();
  const after = await journeyPage.evaluate(() => document.documentElement.className);
  journey.steps.push({ name: 'theme toggle', before, after });
}
await journeyContext.close();

const mobileContext = await browser.newContext({ viewport: { width: 390, height: 844 }, reducedMotion: 'reduce' });
await proxyApi(mobileContext);
const mobilePage = await mobileContext.newPage();
await mobilePage.goto(baseURL, { waitUntil: 'networkidle' });
const menuButton = mobilePage.getByRole('button', { name: /menu|navigation/i }).first();
if (await menuButton.count()) {
  const before = await mobilePage.locator('nav a').count();
  await menuButton.click();
  const after = await mobilePage.locator('nav a:visible').count();
  journey.steps.push({ name: 'mobile menu', before, after, expanded: await menuButton.getAttribute('aria-expanded') });
  await mobilePage.screenshot({ path: path.join(outDir, 'mobile-menu-open.png'), fullPage: true });
}
await mobileContext.close();

await fs.writeFile(path.join(outDir, 'audit-results.json'), JSON.stringify({ generatedAt: new Date().toISOString(), baseURL, results, journey }, null, 2));
await browser.close();
console.log(JSON.stringify({ pages: results.length, screenshots: results.length + 1, journey }, null, 2));
