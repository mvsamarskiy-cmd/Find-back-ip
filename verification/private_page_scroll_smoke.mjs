import { chromium, webkit } from 'playwright';

const base = (process.env.NAMEMACHINE_TEST_URL || 'http://127.0.0.1:8080').replace(/\/$/, '');
const failures = [];

async function run(browserType, name) {
  const browser = await browserType.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });
  const page = await context.newPage();
  try {
    const response = await page.goto(base + '/', { waitUntil: 'domcontentloaded', timeout: 20_000 });
    if (response?.status() !== 200) failures.push(`${name}: root status ${response?.status()}`);
    await page.waitForTimeout(800);

    await page.evaluate(() => {
      document.body.classList.add('nm-private-global');
      const results = document.getElementById('nmPrivateResults');
      if (results) {
        const filler = document.createElement('div');
        filler.id = 'nmPageScrollSmokeFiller';
        filler.style.height = '1800px';
        filler.style.pointerEvents = 'none';
        results.appendChild(filler);
      }
    });
    await page.waitForTimeout(350);

    const layout = await page.evaluate(() => {
      const composer = document.querySelector('.composer');
      const panel = document.getElementById('nmPrivateGlobalPanel');
      const viewport = document.getElementById('nmPrivateViewport');
      const toolbar = panel?.querySelector('.nmpg-toolbar');
      const cs = composer ? getComputedStyle(composer) : null;
      const ps = panel ? getComputedStyle(panel) : null;
      const vs = viewport ? getComputedStyle(viewport) : null;
      const ts = toolbar ? getComputedStyle(toolbar) : null;
      return {
        fixLoaded: Boolean(window.__nmPrivateResultsPageScrollFix),
        composerPosition: cs?.position || '',
        composerOrder: Number(cs?.order || 0),
        panelOrder: Number(ps?.order || 0),
        composerTop: composer?.getBoundingClientRect().top ?? null,
        panelTop: panel?.getBoundingClientRect().top ?? null,
        viewportOverflowY: vs?.overflowY || '',
        viewportMaxHeight: vs?.maxHeight || '',
        toolbarPosition: ts?.position || '',
        scrollHeight: (document.scrollingElement || document.documentElement).scrollHeight,
        clientHeight: document.documentElement.clientHeight,
      };
    });

    if (!layout.fixLoaded) failures.push(`${name}: page-scroll fix did not load`);
    if (layout.composerPosition === 'sticky' || layout.composerPosition === 'fixed') {
      failures.push(`${name}: composer still overlays results (${layout.composerPosition})`);
    }
    if (!(layout.composerOrder < layout.panelOrder)) {
      failures.push(`${name}: composer is not visually before results (${layout.composerOrder}/${layout.panelOrder})`);
    }
    if (!(layout.composerTop < layout.panelTop)) {
      failures.push(`${name}: result panel is not below composer (${layout.composerTop}/${layout.panelTop})`);
    }
    if (layout.viewportOverflowY !== 'visible') {
      failures.push(`${name}: nested result scrolling still active (${layout.viewportOverflowY})`);
    }
    if (layout.viewportMaxHeight !== 'none') {
      failures.push(`${name}: result viewport still height-capped (${layout.viewportMaxHeight})`);
    }
    if (layout.toolbarPosition === 'sticky' || layout.toolbarPosition === 'fixed') {
      failures.push(`${name}: result toolbar still overlays page (${layout.toolbarPosition})`);
    }
    if (!(layout.scrollHeight > layout.clientHeight + 500)) {
      failures.push(`${name}: smoke page is not document-scrollable`);
    }

    const down = page.locator('#nmScrollDown');
    const up = page.locator('#nmScrollUp');
    if (await down.count()) {
      await down.click({ timeout: 5_000 });
      await page.waitForTimeout(900);
      const downY = await page.evaluate(() => window.scrollY);
      if (!(downY > 200)) failures.push(`${name}: page Down button did not scroll document (${downY})`);

      await up.click({ timeout: 5_000 });
      await page.waitForTimeout(900);
      const upY = await page.evaluate(() => window.scrollY);
      if (!(upY < 20)) failures.push(`${name}: page Up button did not return to top (${upY})`);
    } else {
      failures.push(`${name}: page scroll buttons missing`);
    }

    console.log(JSON.stringify({ browser: name, layout }, null, 2));
  } catch (error) {
    failures.push(`${name}: ${String(error?.stack || error)}`);
  } finally {
    await browser.close();
  }
}

await run(chromium, 'chromium-mobile-page-scroll');
await run(webkit, 'webkit-mobile-page-scroll');

if (failures.length) {
  console.error('PRIVATE PAGE SCROLL SMOKE FAILED');
  failures.forEach(item => console.error('- ' + item));
  process.exit(1);
}
console.log('PRIVATE PAGE SCROLL SMOKE OK');
