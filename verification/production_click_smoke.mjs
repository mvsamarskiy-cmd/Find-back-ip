import { chromium, webkit } from 'playwright';

const base = (process.env.NAMEMACHINE_PRODUCTION_URL || 'https://web-production-04fec.up.railway.app').replace(/\/$/, '');
const failures = [];

async function run(browserType, name) {
  const browser = await browserType.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });
  const page = await context.newPage();
  const consoleErrors = [];
  const pageErrors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  page.on('pageerror', error => pageErrors.push(String(error?.stack || error)));

  const report = { browser: name, consoleErrors, pageErrors, checks: [] };
  const check = (label, ok, detail = '') => {
    report.checks.push({ label, ok, detail });
    if (!ok) failures.push(`${name}: ${label}${detail ? ` — ${detail}` : ''}`);
  };

  try {
    const response = await page.goto(base + '/', { waitUntil: 'networkidle', timeout: 45_000 });
    check('root HTTP 200', response?.status() === 200, `status=${response?.status()}`);
    await page.waitForTimeout(800);

    const start = page.locator('#startBtn');
    check('Start visible', await start.isVisible(), '');
    check('Start enabled', await start.isEnabled(), '');
    if (await start.isVisible()) {
      const box = await start.boundingBox();
      if (box) {
        const obstruction = await page.evaluate(({ x, y }) => {
          const el = document.elementFromPoint(x, y);
          if (!el) return null;
          return { tag: el.tagName, id: el.id || '', cls: el.className || '', text: (el.textContent || '').trim().slice(0, 80) };
        }, { x: box.x + box.width / 2, y: box.y + box.height / 2 });
        const startHit = obstruction && (obstruction.id === 'startBtn' || String(obstruction.cls).includes('primary'));
        check('Start hit target is not covered', Boolean(startHit), JSON.stringify(obstruction));
      }
    }

    await start.click({ timeout: 5_000 });
    const emptyStatus = (await page.locator('#status').textContent()) || '';
    check('Start click handler runs', emptyStatus.includes('Опиши задачу'), emptyStatus);

    const save = page.locator('#saveBtn');
    await save.click({ timeout: 5_000 });
    check('Save menu opens', await page.locator('#saveMenu').evaluate(el => el.classList.contains('open')), '');

    const feedTab = page.locator('.tab[data-tab="feed"]');
    await feedTab.click({ timeout: 5_000 });
    check('Feed tab activates', await feedTab.evaluate(el => el.classList.contains('active')), '');
    check('Feed view visible', !(await page.locator('#feedView').getAttribute('hidden')), '');

    const modeButtons = page.locator('[data-entry-mode]');
    const count = await modeButtons.count();
    check('Entry mode controls loaded', count >= 4, `count=${count}`);
    if (count >= 4) {
      const generic = page.locator('[data-entry-mode="generic_name"]');
      await generic.click({ timeout: 5_000 });
      check('Entry mode click activates', await generic.evaluate(el => el.classList.contains('active')), '');
    }

    check('No page errors during click smoke', pageErrors.length === 0, pageErrors.join(' | '));
    check('No console errors during click smoke', consoleErrors.length === 0, consoleErrors.join(' | '));
  } catch (error) {
    failures.push(`${name}: smoke crashed — ${String(error?.stack || error)}`);
    report.crash = String(error?.stack || error);
  } finally {
    console.log(JSON.stringify(report, null, 2));
    await browser.close();
  }
}

await run(chromium, 'chromium-mobile');
await run(webkit, 'webkit-mobile');

if (failures.length) {
  console.error('\nBUTTON SMOKE FAILED');
  for (const failure of failures) console.error('- ' + failure);
  process.exit(1);
}

console.log('BUTTON SMOKE OK');
