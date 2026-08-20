import { chromium, webkit } from 'playwright';

const base = (process.env.NAMEMACHINE_TEST_URL || 'http://127.0.0.1:8080').replace(/\/$/, '');
const failures = [];

async function run(browserType, name, device = {}) {
  const browser = await browserType.launch({ headless: true });
  const context = await browser.newContext({
    viewport: device.viewport || { width: 390, height: 844 },
    isMobile: device.isMobile ?? true,
    hasTouch: device.hasTouch ?? true,
  });
  const page = await context.newPage();
  const pageErrors = [];
  const consoleErrors = [];
  page.on('pageerror', error => pageErrors.push(String(error?.stack || error)));
  page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });

  const report = { browser: name, pageErrors, consoleErrors, checks: [] };
  const check = (label, ok, detail = '') => {
    report.checks.push({ label, ok, detail });
    if (!ok) failures.push(`${name}: ${label}${detail ? ` — ${detail}` : ''}`);
  };

  async function touchHeight(locator) {
    const box = await locator.boundingBox();
    return box?.height || 0;
  }

  async function centerHit(locator) {
    await locator.scrollIntoViewIfNeeded();
    const box = await locator.boundingBox();
    if (!box) return null;
    return page.evaluate(({ x, y }) => {
      const el = document.elementFromPoint(x, y);
      if (!el) return null;
      return { id: el.id || '', cls: String(el.className || ''), text: (el.textContent || '').trim().slice(0, 80) };
    }, { x: box.x + box.width / 2, y: box.y + box.height / 2 });
  }

  try {
    const response = await page.goto(base + '/', { waitUntil: 'domcontentloaded', timeout: 20_000 });
    check('root HTTP 200', response?.status() === 200, `status=${response?.status()}`);
    await page.waitForTimeout(1000);

    const shell = await page.evaluate(() => ({
      uiV3: document.body.classList.contains('nm-ui-v3'),
      stylesheet: document.getElementById('nameMachineUiV3Styles')?.getAttribute('href') || '',
      intro: document.querySelector('#nameMachineIntro h1')?.textContent?.trim() || '',
      composerRight: Math.round(document.querySelector('.composer')?.getBoundingClientRect().right || 0),
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      oldModeHidden: getComputedStyle(document.getElementById('entryModePanel')).display === 'none',
    }));
    check('UI v3 clarity shell is active', shell.uiV3, JSON.stringify(shell));
    check('UI v3 stylesheet is attached', shell.stylesheet.includes('/static/ui_v3_clarity.css'), shell.stylesheet);
    check('Product intro is clear', shell.intro.includes('Знайди назву'), shell.intro);
    check('Composer stays inside viewport', shell.composerRight <= shell.clientWidth + 2, JSON.stringify(shell));
    check('No document overflow', shell.scrollWidth <= shell.clientWidth + 2, JSON.stringify(shell));
    check('Old four-mode matrix is hidden', shell.oldModeHidden, JSON.stringify(shell));

    const flows = page.locator('[data-nm-flow]');
    check('Two clear workflow controls loaded', await flows.count() === 2, `count=${await flows.count()}`);
    for (const flow of ['brand', 'identity']) {
      const button = page.locator(`[data-nm-flow="${flow}"]`);
      check(`${flow} flow visible`, await button.isVisible(), '');
      check(`${flow} touch target >= 44px`, await touchHeight(button) >= 44, `height=${await touchHeight(button)}`);
      const hit = await centerHit(button);
      check(`${flow} hit target clickable`, String(hit?.cls || '').includes('nm-flow'), JSON.stringify(hit));
    }
    await page.locator('[data-nm-flow="identity"]').click();
    check('Identity flow activates', await page.locator('[data-nm-flow="identity"]').evaluate(el => el.classList.contains('active')), '');
    check('Existing brand input appears', await page.locator('#existingBrandWrap').isVisible(), '');
    await page.locator('[data-nm-flow="brand"]').click();
    check('Brand flow activates', await page.locator('[data-nm-flow="brand"]').evaluate(el => el.classList.contains('active')), '');

    const start = page.locator('#startBtn');
    const stop = page.locator('#stopBtn');
    check('Primary action visible', await start.isVisible(), '');
    check('Primary action localized', ['Знайти', 'Продовжити', 'Ще варіанти', 'Згенерувати'].includes((await start.textContent() || '').trim()), await start.textContent());
    check('Primary touch target >= 44px', await touchHeight(start) >= 44, `height=${await touchHeight(start)}`);
    check('Stop localized', (await stop.textContent() || '').trim() === 'Зупинити', await stop.textContent());
    await start.click({ timeout: 5_000 });
    const emptyStatus = (await page.locator('#status').textContent()) || '';
    check('Primary action click handler runs', emptyStatus.includes('Опиши'), emptyStatus);

    const resourcesHead = page.locator('#nmResourcesHead');
    check('Resource selection has clear heading', await resourcesHead.isVisible(), '');
    check('Resource selection shows count', /\d+ вибрано/.test((await resourcesHead.textContent()) || ''), await resourcesHead.textContent());

    const save = page.locator('#saveBtn');
    check('Save touch target >= 36px', await touchHeight(save) >= 36, `height=${await touchHeight(save)}`);
    await save.click({ timeout: 5_000 });
    const preview = page.locator('#previewClientReport');
    check('Report preview action exists', await preview.count() === 1, '');
    if (await preview.count()) {
      await preview.click({ timeout: 5_000 });
      const modal = page.locator('#clientReportPreview');
      check('Report preview opens', await modal.isVisible(), '');
      const close = page.locator('[data-report-close]');
      check('Report close touch target >= 44px', await touchHeight(close) >= 44, `height=${await touchHeight(close)}`);
      await close.click({ timeout: 5_000 });
      check('Report closes', await modal.isHidden(), '');
    }

    const tabs = page.locator('.tabs');
    check('Result tabs visible', await tabs.isVisible(), '');
    const tabTexts = await tabs.locator('.tab').allTextContents();
    check('Results-first navigation is clear', tabTexts[0]?.includes('Результати') && tabTexts[1]?.includes('Підтверджені') && tabTexts[2]?.includes('Збережені'), JSON.stringify(tabTexts));
    const summary = page.locator('#nmResultSummary');
    check('Result truth summary visible', await summary.isVisible(), '');
    const summaryText = (await summary.textContent()) || '';
    check('Strict and non-strict states explained', summaryText.includes('підтверджено вільних') && summaryText.includes('без явного конфлікту'), summaryText);

    const deep = page.locator('.nm-deep-search');
    if (await deep.count()) {
      check('Deep search is collapsed by default', !(await deep.evaluate(el => el.open)), '');
      await deep.locator('summary').click();
      check('Deep search can be opened', await deep.evaluate(el => el.open), '');
      const dimensions = await page.evaluate(() => ({
        clientWidth: document.documentElement.clientWidth,
        scrollWidth: document.documentElement.scrollWidth,
        panelRight: Math.round(document.getElementById('largeSearchPanel')?.getBoundingClientRect().right || 0),
      }));
      check('Deep-search panel stays inside viewport', dimensions.panelRight <= dimensions.clientWidth + 2, JSON.stringify(dimensions));
      check('Deep-search panel creates no overflow', dimensions.scrollWidth <= dimensions.clientWidth + 2, JSON.stringify(dimensions));
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
await run(chromium, 'chromium-desktop', { viewport: { width: 1440, height: 1000 }, isMobile: false, hasTouch: false });

if (failures.length) {
  console.error('\nBUTTON SMOKE FAILED');
  for (const failure of failures) console.error('- ' + failure);
  process.exit(1);
}
console.log('BUTTON SMOKE OK');
