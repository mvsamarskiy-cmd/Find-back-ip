import { chromium, webkit } from 'playwright';

const base = (process.env.NAMEMACHINE_TEST_URL || 'http://127.0.0.1:8080').replace(/\/$/, '');
const failures = [];

function bounded(label, promise, ms = 8_000) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(`${label} timed out after ${ms}ms`)), ms);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

async function run(browserType, name) {
  console.log(`[${name}] launch`);
  const browser = await bounded(`${name} launch`, browserType.launch({ headless: true }), 15_000);
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });
  const page = await context.newPage();
  page.setDefaultTimeout(5_000);
  page.setDefaultNavigationTimeout(12_000);
  try {
    console.log(`[${name}] goto`);
    const response = await bounded(
      `${name} goto`,
      page.goto(base + '/', { waitUntil: 'domcontentloaded', timeout: 12_000 }),
      14_000,
    );
    if (response?.status() !== 200) failures.push(`${name}: root status ${response?.status()}`);
    await page.waitForTimeout(500);

    console.log(`[${name}] activate private layout`);
    await bounded(`${name} activate private layout`, page.evaluate(() => {
      document.body.classList.add('nm-private-global');
      const results = document.getElementById('nmPrivateResults');
      if (results) {
        const filler = document.createElement('div');
        filler.id = 'nmPageScrollSmokeFiller';
        filler.style.height = '1800px';
        filler.style.pointerEvents = 'none';
        results.appendChild(filler);
      }
    }), 6_000);
    await page.waitForTimeout(250);

    console.log(`[${name}] inspect layout`);
    const layout = await bounded(`${name} inspect layout`, page.evaluate(() => {
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
    }), 6_000);

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
    const downCount = await bounded(`${name} count scroll buttons`, down.count(), 3_000);
    if (downCount) {
      console.log(`[${name}] click down`);
      await bounded(`${name} click down`, down.click({ timeout: 4_000 }), 5_000);
      await page.waitForTimeout(700);
      const downY = await bounded(`${name} read down scroll`, page.evaluate(() => window.scrollY), 4_000);
      if (!(downY > 200)) failures.push(`${name}: page Down button did not scroll document (${downY})`);

      console.log(`[${name}] click up`);
      await bounded(`${name} click up`, up.click({ timeout: 4_000 }), 5_000);
      await page.waitForTimeout(700);
      const upY = await bounded(`${name} read up scroll`, page.evaluate(() => window.scrollY), 4_000);
      if (!(upY < 20)) failures.push(`${name}: page Up button did not return to top (${upY})`);
    } else {
      failures.push(`${name}: page scroll buttons missing`);
    }

    console.log(JSON.stringify({ browser: name, layout }, null, 2));
  } catch (error) {
    failures.push(`${name}: ${String(error?.stack || error)}`);
  } finally {
    console.log(`[${name}] close`);
    await bounded(`${name} browser close`, browser.close(), 8_000).catch(error => {
      failures.push(`${name}: ${String(error?.message || error)}`);
    });
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
