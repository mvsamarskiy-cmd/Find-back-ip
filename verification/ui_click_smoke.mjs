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

  async function centerHit(locator) {
    await locator.scrollIntoViewIfNeeded();
    const box = await locator.boundingBox();
    if (!box) return null;
    return page.evaluate(({ x, y }) => {
      const el = document.elementFromPoint(x, y);
      if (!el) return null;
      return { tag: el.tagName, id: el.id || '', cls: String(el.className || ''), text: (el.textContent || '').trim().slice(0, 80) };
    }, { x: box.x + box.width / 2, y: box.y + box.height / 2 });
  }

  async function touchHeight(locator) {
    const box = await locator.boundingBox();
    return box?.height || 0;
  }

  try {
    const response = await page.goto(base + '/', { waitUntil: 'domcontentloaded', timeout: 20_000 });
    check('root HTTP 200', response?.status() === 200, `status=${response?.status()}`);
    await page.waitForTimeout(900);

    const uiShell = await page.evaluate(() => ({
      uiV2: document.body.classList.contains('nm-ui-v2'),
      stylesheet: document.getElementById('nameMachineUiV2Styles')?.getAttribute('href') || '',
      introVisible: Boolean(document.getElementById('nameMachineIntro')?.getBoundingClientRect().height),
      introText: document.querySelector('#nameMachineIntro h1')?.textContent?.trim() || '',
      composerRight: Math.round(document.querySelector('.composer')?.getBoundingClientRect().right || 0),
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      titleSize: parseFloat(getComputedStyle(document.querySelector('#nameMachineIntro h1')).fontSize || '0'),
    }));
    check('UI v2 product shell is active', uiShell.uiV2, JSON.stringify(uiShell));
    check('UI v2 stylesheet is attached', uiShell.stylesheet.includes('/static/ui_v2.css'), uiShell.stylesheet);
    check('Product intro is visible', uiShell.introVisible && uiShell.introText.includes('Знайди назву'), uiShell.introText);
    check('Hero typography is prominent', uiShell.titleSize >= 32, `fontSize=${uiShell.titleSize}`);
    check('Composer stays inside viewport', uiShell.composerRight <= uiShell.clientWidth + 2, JSON.stringify(uiShell));
    check('UI v2 creates no document overflow', uiShell.scrollWidth <= uiShell.clientWidth + 2, JSON.stringify(uiShell));

    const start = page.locator('#startBtn');
    check('Start visible', await start.isVisible(), '');
    check('Start enabled', await start.isEnabled(), '');
    check('Start touch target >= 44px', await touchHeight(start) >= 44, `height=${await touchHeight(start)}`);
    const startHit = await centerHit(start);
    check('Start hit target is not covered', startHit?.id === 'startBtn', JSON.stringify(startHit));
    await start.click({ timeout: 5_000 });
    const emptyStatus = (await page.locator('#status').textContent()) || '';
    check('Start click handler runs', emptyStatus.includes('Опиши задачу'), emptyStatus);

    const save = page.locator('#saveBtn');
    check('Save touch target >= 36px', await touchHeight(save) >= 36, `height=${await touchHeight(save)}`);
    const saveHit = await centerHit(save);
    check('Save hit target is not covered', saveHit?.id === 'saveBtn', JSON.stringify(saveHit));
    await save.click({ timeout: 5_000 });
    check('Save menu opens', await page.locator('#saveMenu').evaluate(el => el.classList.contains('open')), '');

    const preview = page.locator('#previewClientReport');
    check('Report preview action exists', await preview.count() === 1, '');
    if (await preview.count()) {
      await preview.click({ timeout: 5_000 });
      const modal = page.locator('#clientReportPreview');
      check('Report preview opens', await modal.isVisible(), '');
      const close = page.locator('[data-report-close]');
      check('Report close touch target >= 44px', await touchHeight(close) >= 44, `height=${await touchHeight(close)}`);
      const closeHit = await centerHit(close);
      check('Report close hit target is not covered', String(closeHit?.cls || '').includes('report-preview-close'), JSON.stringify(closeHit));
      if (String(closeHit?.cls || '').includes('report-preview-close')) {
        await close.click({ timeout: 5_000 });
        check('Report close button dismisses modal', await modal.isHidden(), '');
      }
    }

    const feedTab = page.locator('.tab[data-tab="feed"]');
    const feedHit = await centerHit(feedTab);
    check('Feed tab hit target is clickable', String(feedHit?.cls || '').includes('tab'), JSON.stringify(feedHit));
    await feedTab.click({ timeout: 5_000 });
    await page.waitForTimeout(100);
    check('Feed tab activates', await feedTab.evaluate(el => el.classList.contains('active')), '');
    check('Feed view visible', await page.locator('#feedView').isVisible(), '');

    const legend = page.locator('#nameMachineTruthLegend');
    check('Truth-status legend is visible', await legend.isVisible(), '');
    const legendText = (await legend.textContent()) || '';
    check('Truth-status legend distinguishes strict and promising', legendText.includes('вільне — підтверджено') && legendText.includes('перспективне'), legendText);

    const modeButtons = page.locator('[data-entry-mode]');
    const count = await modeButtons.count();
    check('Entry mode controls loaded', count >= 4, `count=${count}`);
    if (count >= 4) {
      for (const mode of ['brand', 'identity', 'generic_name', 'other']) {
        const button = page.locator(`[data-entry-mode="${mode}"]`);
        check(`${mode} mode touch target >= 44px`, await touchHeight(button) >= 44, `height=${await touchHeight(button)}`);
        const hit = await centerHit(button);
        check(`${mode} mode hit target is clickable`, String(hit?.cls || '').includes('entry-mode'), JSON.stringify(hit));
      }
      const generic = page.locator('[data-entry-mode="generic_name"]');
      await generic.click({ timeout: 5_000 });
      check('Entry mode click activates', await generic.evaluate(el => el.classList.contains('active')), '');
    }

    const panel = page.locator('#largeSearchPanel');
    if (await panel.count()) {
      await page.evaluate(() => {
        const node = document.getElementById('largeSearchPanel');
        if (node) node.hidden = false;
      });
      await page.waitForTimeout(100);
      const dimensions = await page.evaluate(() => ({
        clientWidth: document.documentElement.clientWidth,
        scrollWidth: document.documentElement.scrollWidth,
        panelRight: Math.round(document.getElementById('largeSearchPanel')?.getBoundingClientRect().right || 0),
      }));
      check('Large-search panel stays inside viewport', dimensions.panelRight <= dimensions.clientWidth + 2, JSON.stringify(dimensions));
      check('Large-search panel does not create document overflow', dimensions.scrollWidth <= dimensions.clientWidth + 2, JSON.stringify(dimensions));
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
await run(chromium, 'chromium-desktop', {
  viewport: { width: 1440, height: 1000 },
  isMobile: false,
  hasTouch: false,
});

if (failures.length) {
  console.error('\nBUTTON SMOKE FAILED');
  for (const failure of failures) console.error('- ' + failure);
  process.exit(1);
}

console.log('BUTTON SMOKE OK');
