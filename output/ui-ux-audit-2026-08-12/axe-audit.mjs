import playwright from '../../e2e/node_modules/@playwright/test/index.js';
import fs from 'node:fs/promises';

const { chromium } = playwright;
const axeSource = await fs.readFile(new URL('../../frontend/node_modules/axe-core/axe.min.js', import.meta.url), 'utf8');
const outDir = new URL('./', import.meta.url).pathname;
const baseURL = 'http://10.0.0.200:5173';
const videoId = '442156c6-e43e-46fb-95f5-9758df70c18c';
const routes = [
  ['home', '/'], ['search', '/search?q=housing'], ['search-empty', '/search?q=xyzzynotarealarchivequery987654'],
  ['explore', '/explore'], ['episodes', '/episodes'], ['timeline', '/timeline'], ['topic', '/topics/housing'],
  ['video', `/v/${videoId}`], ['login', '/login'], ['saved', '/saved'], ['not-found', '/not-found-audit'],
];

async function proxyApi(context) {
  await context.route('**/api/**', async (route) => {
    const target = new URL(route.request().url());
    target.protocol = 'http:'; target.hostname = '10.0.0.200'; target.port = '41177';
    target.pathname = target.pathname.replace(/^\/api(?=\/|$)/, '');
    const response = await route.fetch({ url: target.href });
    await route.fulfill({ response });
  });
}

const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', headless: true });
const findings = [];
for (const profile of [
  { name: 'mobile-light', viewport: { width: 390, height: 844 }, colorScheme: 'light', isMobile: true, hasTouch: true },
  { name: 'mobile-dark', viewport: { width: 390, height: 844 }, colorScheme: 'dark', isMobile: true, hasTouch: true },
  { name: 'desktop-light', viewport: { width: 1440, height: 1000 }, colorScheme: 'light' },
]) {
  const context = await browser.newContext(profile);
  await proxyApi(context);
  await context.addInitScript({ content: axeSource });
  const page = await context.newPage();
  for (const [name, route] of routes) {
    await page.goto(`${baseURL}${route}`, { waitUntil: 'networkidle', timeout: 60_000 }).catch(() => {});
    await page.waitForTimeout(700);
    const report = await page.evaluate(async () => axe.run(document, {
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'] },
      resultTypes: ['violations', 'incomplete', 'passes'],
    }));
    findings.push({
      profile: profile.name, route: name, url: page.url(),
      violations: report.violations.map((v) => ({ id: v.id, impact: v.impact, description: v.description, help: v.help, helpUrl: v.helpUrl, nodes: v.nodes.map((n) => ({ impact: n.impact, target: n.target, html: n.html, failureSummary: n.failureSummary })) })),
      incomplete: report.incomplete.map((v) => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.length })),
      passes: report.passes.length,
    });
  }
  await context.close();
}
await fs.writeFile(`${outDir}/axe-results.json`, JSON.stringify({ generatedAt: new Date().toISOString(), findings }, null, 2));
console.log(JSON.stringify({
  scans: findings.length,
  violationsByRule: Object.entries(findings.flatMap((x) => x.violations).reduce((acc, v) => { acc[v.id] = (acc[v.id] || 0) + v.nodes.length; return acc; }, {})).sort((a,b) => b[1]-a[1]),
  perPage: findings.map((x) => ({ profile: x.profile, route: x.route, violations: x.violations.map((v) => `${v.id}:${v.nodes.length}`) })),
}, null, 2));
await browser.close();
