import { chromium, webkit } from 'playwright';

const base = (process.env.NAMEMACHINE_PRODUCTION_URL || 'https://web-production-04fec.up.railway.app').replace(/\/$/, '');
const expectedStatuses = new Set(['claimable','purchasable','taken','not_found','invalid','reserved','rate_limited','unknown']);
const failures = [];
const warnings = [];
const metrics = {};

function fail(label, detail = '') { failures.push(detail ? `${label}: ${detail}` : label); }
function warn(label, detail = '') { warnings.push(detail ? `${label}: ${detail}` : label); }
function assert(label, condition, detail = '') { if (!condition) fail(label, detail); }
async function timed(label, fn) {
  const started = Date.now();
  try { return await fn(); }
  finally { metrics[label] = Date.now() - started; }
}
async function jsonFetch(path, options = {}, timeoutMs = 120000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(base + path, { ...options, signal: controller.signal });
    const text = await response.text();
    let body = null;
    try { body = JSON.parse(text); } catch (_) {}
    return { response, body, text };
  } finally { clearTimeout(timer); }
}

async function auditHttpAndBackend() {
  const health = await timed('health_ms', () => jsonFetch('/health', {}, 20000));
  assert('health HTTP 200', health.response.status === 200, `status=${health.response.status}`);
  assert('health payload', health.body?.status === 'ok', JSON.stringify(health.body));

  const version = await timed('version_ms', () => jsonFetch('/api/version', {}, 20000));
  assert('version HTTP 200', version.response.status === 200, `status=${version.response.status}`);
  assert('release marker exists', Boolean(version.body?.release), JSON.stringify(version.body));
  assert('production commit marker exists', Boolean(version.body?.git_commit) && version.body?.git_commit !== 'unknown', JSON.stringify(version.body));

  const diagnostics = await timed('diagnostics_ms', () => jsonFetch('/api/verification/diagnostics', {}, 20000));
  assert('diagnostics HTTP 200', diagnostics.response.status === 200, `status=${diagnostics.response.status}`);
  const d = diagnostics.body || {};
  assert('verification engine v2', d.verification_engine === 'v2', JSON.stringify(d.verification_engine));
  assert('strict green is claimable', d.strict_free_semantics?.green_status === 'claimable');
  assert('purchasable is not strict green', d.strict_free_semantics?.purchasable_is_green === false);
  assert('not_found is not strict green', d.strict_free_semantics?.not_found_is_green === false);
  assert('streaming enabled', d.streaming_feed?.enabled === true);
  assert('feed pagination enabled', d.large_feed_navigation?.pagination === true);
  assert('background storage configured', d.background_search?.configured === true, JSON.stringify(d.background_search));
  assert('background worker online', d.background_search?.worker_online === true, JSON.stringify(d.background_search));
  if (!d.providers?.domain?.registrar?.configured) warn('domain registrar not configured', 'RDAP can prove registration presence, but fresh .com claimability stays unconfirmed without a registrar');
  if (!d.providers?.youtube?.official_api?.configured) warn('YouTube official API not configured', 'public-web fallback is less authoritative for occupancy');
  if (!d.providers?.x?.official_api?.configured) warn('X official API not configured', 'no-key/public fallback is less authoritative for occupancy');
  if (!d.providers?.telegram?.evidence_service?.configured) warn('Telegram strict claimability service not configured', 'public evidence can detect conflicts but cannot prove a handle is freely claimable');

  const occupied = await timed('known_occupied_check_ms', () => jsonFetch('/api/check/openai?resources=com,instagram,telegram,tiktok,youtube,facebook,x&required=com,instagram,telegram,tiktok,youtube,facebook,x', {}, 60000));
  assert('known occupied check HTTP 200', occupied.response.status === 200, `status=${occupied.response.status} ${occupied.text.slice(0,300)}`);
  const availability = occupied.body?.availability || {};
  assert('all seven resources returned', Object.keys(availability).length === 7, Object.keys(availability).join(','));
  for (const key of ['com','instagram','telegram','tiktok','youtube','facebook','x']) {
    assert(`${key} result present`, Boolean(availability[key]), JSON.stringify(availability[key]));
    assert(`${key} status valid`, expectedStatuses.has(String(availability[key]?.status)), JSON.stringify(availability[key]));
    assert(`${key} has evidence timestamp`, Boolean(availability[key]?.checked_at), JSON.stringify(availability[key]));
  }
  assert('openai.com detected registered', availability.com?.status === 'taken', JSON.stringify(availability.com));
  assert('verification verdicts attached', Boolean(occupied.body?.verification) && typeof occupied.body.verification === 'object');
  assert('bundle classification attached', Boolean(occupied.body?.bundle_state), JSON.stringify({bundle_state: occupied.body?.bundle_state, bundle_score: occupied.body?.bundle_score}));

  const interpret = await timed('prompt_interpret_ms', () => jsonFetch('/api/interpret', {
    method: 'POST', headers: {'content-type': 'application/json'},
    body: JSON.stringify({prompt: 'Я блогер, мені потрібна назва каналу про гусей та інших птахів. Хочу коротко, природно і щоб гарно звучало.', resources: ['instagram','tiktok','youtube','x']}),
  }, 90000));
  assert('prompt interpretation HTTP 200', interpret.response.status === 200, `status=${interpret.response.status} ${interpret.text.slice(0,500)}`);
  assert('prompt intelligence has semantic brief', String(interpret.body?.semantic_brief || '').length >= 10, JSON.stringify(interpret.body));
  assert('prompt intelligence has naming roots', Array.isArray(interpret.body?.naming_roots) && interpret.body.naming_roots.length >= 2, JSON.stringify(interpret.body?.naming_roots));
  assert('prompt intelligence preserves selected resources', Array.isArray(interpret.body?.selected_resources) && interpret.body.selected_resources.join(',') === 'instagram,tiktok,youtube,x', JSON.stringify(interpret.body?.selected_resources));

  const generic = await timed('generic_generation_ms', () => jsonFetch('/api/generic-names', {
    method: 'POST', headers: {'content-type': 'application/json'},
    body: JSON.stringify({brief: 'Коротка назва для каналу про гусей, диких птахів, польоти та природу. Англійське звучання.', count: 6, preferences: {}, generation_context: {batch_number: 1, exclude_names: [], conflict_names: [], successful_names: []}}),
  }, 120000));
  assert('generic generation HTTP 200', generic.response.status === 200, `status=${generic.response.status} ${generic.text.slice(0,500)}`);
  assert('generic generation returns six rows', Array.isArray(generic.body) && generic.body.length === 6, `count=${Array.isArray(generic.body) ? generic.body.length : 'not-array'}`);
  if (Array.isArray(generic.body)) {
    const names = generic.body.map(row => String(row?.name || ''));
    assert('generated names are unique', new Set(names.map(n => n.toLowerCase())).size === names.length, names.join(','));
    for (const row of generic.body) {
      assert('generated name is ASCII letters', /^[A-Za-z]{3,30}$/.test(String(row?.name || '')), JSON.stringify(row));
      assert('generated row has family', typeof row?.family === 'string' && row.family.length > 0, JSON.stringify(row));
      assert('generic row is not falsely verified', row?.checked === false && row?.product_mode === 'generic_name', JSON.stringify(row));
    }
  }
  return { version: version.body, diagnostics: d };
}

async function centerHit(page, locator) {
  await locator.scrollIntoViewIfNeeded();
  const box = await locator.boundingBox();
  if (!box) return null;
  return page.evaluate(({x,y}) => {
    const el = document.elementFromPoint(x,y);
    return el ? {tag: el.tagName, id: el.id || '', cls: String(el.className || ''), text: (el.textContent || '').trim().slice(0,80)} : null;
  }, {x: box.x + box.width/2, y: box.y + box.height/2});
}

async function overflowDiagnostics(page) {
  return page.evaluate(() => {
    const width = document.documentElement.clientWidth;
    return [...document.querySelectorAll('body *')]
      .map(el => {
        const r = el.getBoundingClientRect();
        return {tag: el.tagName, id: el.id || '', cls: String(el.className || ''), left: Math.round(r.left), right: Math.round(r.right), width: Math.round(r.width), text: (el.textContent || '').trim().replace(/\s+/g,' ').slice(0,60)};
      })
      .filter(row => row.right > width + 2 || row.left < -2)
      .sort((a,b) => Math.max(b.right-width, -b.left) - Math.max(a.right-width, -a.left))
      .slice(0,12);
  });
}

async function auditBrowser(browserType, name, runLiveGeneration = false) {
  const browser = await browserType.launch({headless: true});
  const context = await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
  const page = await context.newPage();
  const pageErrors = [];
  const consoleErrors = [];
  page.on('pageerror', e => pageErrors.push(String(e?.stack || e)));
  page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });

  try {
    const response = await timed(`${name}_domcontentloaded_ms`, () => page.goto(base + '/', {waitUntil:'domcontentloaded', timeout:30000}));
    assert(`${name} root HTTP 200`, response?.status() === 200, `status=${response?.status()}`);
    await page.waitForTimeout(1200);

    const bodySize = await page.evaluate(() => ({client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth}));
    if (bodySize.scroll > bodySize.client + 2) warn(`${name} overflow elements`, JSON.stringify(await overflowDiagnostics(page)));
    assert(`${name} no horizontal overflow`, bodySize.scroll <= bodySize.client + 2, JSON.stringify(bodySize));
    assert(`${name} cache-busted ui cleanup asset`, await page.locator('script[src="/static/ui_cleanup_r8.js?v=2"]').count() === 1);

    for (const selector of ['#startBtn','#saveBtn','.tab[data-tab="feed"]','[data-entry-mode="brand"]','[data-entry-mode="identity"]','[data-entry-mode="generic_name"]','[data-entry-mode="other"]']) {
      const locator = page.locator(selector).first();
      assert(`${name} ${selector} visible`, await locator.isVisible(), '');
      if (await locator.isVisible()) {
        const box = await locator.boundingBox();
        assert(`${name} ${selector} touch height`, Boolean(box && box.height >= 36), JSON.stringify(box));
        const hit = await centerHit(page, locator);
        assert(`${name} ${selector} hit target`, Boolean(hit), JSON.stringify(hit));
      }
    }

    await page.locator('#startBtn').click({timeout:5000});
    const emptyStatus = (await page.locator('#status').textContent()) || '';
    assert(`${name} Start handler runs`, emptyStatus.includes('Опиши'), emptyStatus);

    await page.locator('#saveBtn').click({timeout:5000});
    assert(`${name} Save opens menu`, await page.locator('#saveMenu').evaluate(el => el.classList.contains('open')));
    const preview = page.locator('#previewClientReport');
    assert(`${name} report preview action exists`, await preview.count() === 1);
    if (await preview.count()) {
      await preview.click();
      assert(`${name} report preview opens`, await page.locator('#clientReportPreview').isVisible());
      const close = page.locator('[data-report-close]');
      const closeHit = await centerHit(page, close);
      const closeClickable = String(closeHit?.cls || '').includes('report-preview-close');
      assert(`${name} report close hit target`, closeClickable, JSON.stringify(closeHit));
      if (closeClickable) {
        await close.click({timeout:5000});
      } else {
        await page.keyboard.press('Escape');
      }
      assert(`${name} report preview closes`, await page.locator('#clientReportPreview').isHidden());
    }

    const feedTab = page.locator('.tab[data-tab="feed"]');
    await feedTab.click();
    assert(`${name} Feed tab activates`, await feedTab.evaluate(el => el.classList.contains('active')));
    assert(`${name} Feed view visible`, await page.locator('#feedView').isVisible());

    const generic = page.locator('[data-entry-mode="generic_name"]');
    await generic.click();
    assert(`${name} generic mode activates`, await generic.evaluate(el => el.classList.contains('active')));
    assert(`${name} generic mode hides resources`, await page.evaluate(() => getComputedStyle(document.querySelector('.resources')).display === 'none'));
    assert(`${name} generic start label`, ['Згенерувати','Ще назви'].includes((await page.locator('#startBtn').textContent()) || ''));

    const identity = page.locator('[data-entry-mode="identity"]');
    await identity.click();
    assert(`${name} identity mode activates`, await identity.evaluate(el => el.classList.contains('active')));
    assert(`${name} identity brand field visible`, await page.locator('#existingBrandName').isVisible());
    await page.locator('#prompt').fill('Потрібен нікнейм для соцмереж');
    await page.locator('#startBtn').click();
    const missingBrand = (await page.locator('#status').textContent()) || '';
    assert(`${name} identity validates brand`, missingBrand.includes('існуючу назву бренду'), missingBrand);

    const brand = page.locator('[data-entry-mode="brand"]');
    await brand.click();
    assert(`${name} brand mode activates`, await brand.evaluate(el => el.classList.contains('active')));

    if (runLiveGeneration) {
      await page.locator('#prompt').fill('Канал про гусей та інших птахів, коротка природна англійська назва');
      const checkboxes = page.locator('input[name="resource"]');
      for (let i=0;i<await checkboxes.count();i++) await checkboxes.nth(i).uncheck();
      await page.locator('input[name="resource"][value="com"]').check();
      const before = Number((await page.locator('#feedCount').textContent()) || '0');
      await timed(`${name}_first_stream_result_ms`, async () => {
        await page.locator('#startBtn').click();
        await page.waitForFunction(prev => Number(document.querySelector('#feedCount')?.textContent || 0) > prev, before, {timeout:120000});
      });
      const after = Number((await page.locator('#feedCount').textContent()) || '0');
      assert(`${name} verified UI delivered result`, after > before, `before=${before} after=${after}`);
      assert(`${name} result card rendered`, await page.locator('#feedGrid .card').count() > 0);
      await page.locator('#stopBtn').click().catch(() => {});
      await page.waitForTimeout(300);
    }

    assert(`${name} no page errors`, pageErrors.length === 0, pageErrors.join(' | '));
    assert(`${name} no console errors`, consoleErrors.length === 0, consoleErrors.join(' | '));
  } catch (error) { fail(`${name} browser audit crashed`, String(error?.stack || error)); }
  finally { await browser.close(); }
}

const backend = await auditHttpAndBackend();
await auditBrowser(chromium, 'chromium-mobile', true);
await auditBrowser(webkit, 'webkit-mobile', false);

console.log(JSON.stringify({target:base, release:backend.version?.release, git_commit:backend.version?.git_commit, metrics_ms:metrics, warnings, failures}, null, 2));
if (failures.length) process.exit(1);
