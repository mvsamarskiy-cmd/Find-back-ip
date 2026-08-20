import fs from 'node:fs';
import { chromium, webkit } from 'playwright';

const base = (process.env.NAMEMACHINE_TEST_URL || 'http://127.0.0.1:8080').replace(/\/$/, '');
const outPath = process.env.NAMEMACHINE_AUDIT_TXT || 'namemachine-client-journey-audit.txt';
const allResources = ['com', 'instagram', 'telegram', 'tiktok', 'youtube', 'facebook', 'x'];
const familyCycle = ['semantic_compound', 'evocative_metaphor', 'root_blend', 'invented_phonetic', 'abstract'];
const utility = { claimable: 1, purchasable: 0.82, not_found: 0.55, unknown: 0.18, rate_limited: 0.14, available: 0.18, taken: 0, reserved: 0, invalid: 0 };
const penalties = { claimable: 0, purchasable: -1.5, promising: 0, unresolved: -5, conflict: -18, unverified: 0 };
const failures = [];
const transcript = [];

function line(browser, action, detail = '') {
  const at = new Date().toISOString();
  const text = `${at} | ${browser} | ${action}${detail ? ` | ${detail}` : ''}`;
  transcript.push(text);
  console.log('[CLIENT-AUDIT] ' + text);
}

function strictState(statuses) {
  if (statuses.some(s => ['taken', 'reserved', 'invalid'].includes(s))) return 'conflict';
  if (statuses.some(s => ['unknown', 'rate_limited', 'available'].includes(s))) return 'unresolved';
  if (statuses.every(s => s === 'claimable')) return 'claimable';
  if (statuses.some(s => s === 'not_found')) return 'promising';
  if (statuses.every(s => ['claimable', 'purchasable'].includes(s)) && statuses.some(s => s === 'purchasable')) return 'purchasable';
  return 'unresolved';
}

function legacyState(state) {
  if (state === 'claimable' || state === 'purchasable') return 'confirmed';
  if (state === 'promising') return 'promising';
  if (state === 'conflict') return 'conflict';
  return 'unresolved';
}

function makeRows(resources, names, promptIndex) {
  return names.map((name, index) => {
    const availability = {};
    for (const [rIndex, resource] of resources.entries()) {
      let status = 'claimable';
      if (index === 1) status = 'not_found';
      if (index === 2 && rIndex === 0) status = 'taken';
      if (index === 3) status = 'purchasable';
      if (index === 4 && rIndex === resources.length - 1) status = 'unknown';
      if (index === 5 && rIndex % 2 === 1) status = 'not_found';
      availability[resource] = {
        status,
        source: 'client_journey_fixture',
        method: 'deterministic_ui_audit',
        confidence: status === 'unknown' ? 0.35 : 0.96,
        url: resource === 'com' ? `https://${name.toLowerCase()}.com` : `https://example.test/${resource}/${name.toLowerCase()}`,
      };
    }
    const statuses = resources.map(resource => availability[resource]?.status || 'unknown');
    const state = strictState(statuses);
    const structural = 68 + ((index * 7 + promptIndex * 3) % 27);
    const linguistic = 66 + ((index * 5 + promptIndex * 4) % 29);
    const quality = Math.min(100, 0.56 * structural + 0.44 * linguistic);
    const userFit = Math.min(100, 56 + promptIndex * 6 + index * 3);
    const adaptive = Math.min(100, 58 + promptIndex * 7 + index * 2);
    const identity = 0.45 * quality + 0.55 * adaptive;
    const opportunity = resources.length
      ? 100 * statuses.reduce((sum, status) => sum + (utility[status] ?? utility.unknown), 0) / resources.length
      : null;
    const final = opportunity === null
      ? identity
      : Math.max(0, Math.min(100, 0.72 * identity + 0.28 * opportunity + (penalties[state] ?? -5)));
    const evidenceConfidence = resources.length
      ? 100 * resources.reduce((sum, resource) => sum + Number(availability[resource]?.confidence || 0), 0) / resources.length
      : 0;
    const resolved = statuses.filter(s => !['unknown', 'rate_limited', 'available'].includes(s)).length;
    return {
      name,
      reason: `Audit fixture ${promptIndex + 1}.${index + 1}: перевіряємо поведінку клієнтського UI та математики звіту.`,
      family: familyCycle[index % familyCycle.length],
      availability,
      bundle_state: legacyState(state),
      bundle_availability_state: state,
      structural_quality_score: Number(structural.toFixed(1)),
      linguistic_quality_score: Number(linguistic.toFixed(1)),
      name_quality_score: Number(quality.toFixed(1)),
      user_fit_score: Number(userFit.toFixed(1)),
      adaptive_relevance_score: Number(adaptive.toFixed(1)),
      identity_relevance_score: Number(identity.toFixed(1)),
      availability_opportunity_score: opportunity === null ? null : Number(opportunity.toFixed(1)),
      availability_evidence_confidence_score: Number(evidenceConfidence.toFixed(1)),
      verification_coverage_score: resources.length ? Number((100 * resolved / resources.length).toFixed(1)) : 0,
      final_score: Number(final.toFixed(1)),
      ranking_model: 'final-v1',
      ranking_reason: `audit fixture · state=${state} · Q=${quality.toFixed(1)} · U=${userFit.toFixed(1)}`,
    };
  });
}

function candidateSource(row) {
  const source = { ...row };
  delete source.availability;
  delete source.bundle_state;
  delete source.bundle_availability_state;
  delete source.availability_opportunity_score;
  delete source.availability_evidence_confidence_score;
  delete source.verification_coverage_score;
  return source;
}

function streamEvents(rows, resources) {
  const totalChecks = rows.length * resources.length;
  const events = [
    { type: 'phase', phase: 'generated', label: 'Audit: кандидати сформовані', total: rows.length, total_resource_checks: totalChecks },
    { type: 'phase', phase: 'verifying', label: 'Audit: перевіряю ресурси', total: rows.length, total_resource_checks: totalChecks },
  ];
  let completedChecks = 0;
  rows.forEach((row, index) => {
    const candidateId = `${index}:${row.name.toLowerCase()}`;
    events.push({ type: 'candidate', candidate_id: candidateId, row: candidateSource(row), resources, index, total: rows.length });
    resources.forEach((resource, resourceIndex) => {
      completedChecks += 1;
      const availability = row.availability[resource];
      events.push({
        type: 'resource', candidate_id: candidateId, name: row.name, resource,
        availability,
        verification: {
          verdict: ['taken', 'reserved', 'invalid'].includes(availability.status) ? 'conflict' : availability.status === 'not_found' ? 'absence' : 'fixture',
          confidence: availability.confidence,
          provider: 'client_journey_fixture',
        },
        error: false,
        completed_resources: resourceIndex + 1,
        total_resources: resources.length,
        completed_resource_checks: completedChecks,
        total_resource_checks: totalChecks,
      });
    });
    events.push({ type: 'result', candidate_id: candidateId, row, completed: index + 1, total: rows.length });
  });
  events.push({ type: 'done', total: rows.length, completed: rows.length, delivered: rows.length, errors: 0, completed_resource_checks: totalChecks, total_resource_checks: totalChecks });
  return events;
}

const promptNames = [
  ['BreadHearth', 'CrustSun', 'FlourEmber', 'OvenRise', 'GrainGlow', 'LoafKind'],
  ['WheatMorn', 'DoughCraft', 'CrumbSun', 'BakeHaven', 'HearthLoaf', 'BreadNest'],
  ['GoldenCrust', 'FlourRise', 'OvenSeed', 'GrainHearth', 'DoughMorn', 'LoafBloom'],
  ['BreadHearthHQ', 'BreadHearthNow', 'BreadHearthClub', 'BreadHearthApp', 'BreadHearthCo', 'BreadHearthLab'],
];

const genericRows = [
  ['WarmCrust', 'semantic_compound'], ['BreadBloom', 'semantic_compound'], ['MorningLoaf', 'evocative_metaphor'],
  ['Bakena', 'root_blend'], ['Gralune', 'root_blend'], ['Evin', 'abstract'], ['Doughena', 'invented_phonetic'], ['FlourSun', 'semantic_compound'],
].map(([name, family], index) => ({
  name, family, product_mode: 'generic_name', reason: 'Audit fixture: генерація без перевірки.',
  structural_quality_score: 70 + index, linguistic_quality_score: 72 + index,
  name_quality_score: 71 + index, user_fit_score: 50 + index * 2, final_score: 61 + index,
  ranking_model: 'final-v1',
}));

async function installFixtures(page, browserName) {
  const promptMeta = new Map();
  let nextPromptIndex = 0;

  await page.route('**/api/generic-names', async route => {
    line(browserName, 'API fixture', 'generic-names -> 8 deterministic rows');
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(genericRows) });
  });

  await page.route('**/api/ai-generate-stream', async route => {
    const body = route.request().postDataJSON();
    const prompt = String(body?.brief || '');
    const resources = Array.isArray(body?.resources) ? body.resources : [];
    if (!promptMeta.has(prompt)) promptMeta.set(prompt, { index: nextPromptIndex++, calls: 0 });
    const meta = promptMeta.get(prompt);
    meta.calls += 1;
    const rows = meta.calls === 1 ? makeRows(resources, promptNames[meta.index % promptNames.length], meta.index) : [];
    const events = rows.length ? streamEvents(rows, resources) : [{ type: 'done', total: 0, completed: 0, delivered: 0, errors: 0, completed_resource_checks: 0, total_resource_checks: 0 }];
    line(browserName, 'API fixture', `stream prompt#${meta.index + 1} call=${meta.calls} resources=${resources.join(',') || 'none'} rows=${rows.length}`);
    await route.fulfill({ status: 200, contentType: 'application/x-ndjson; charset=utf-8', body: events.map(event => JSON.stringify(event)).join('\n') + '\n' });
  });

  await page.route('**/api/recheck', async route => {
    const body = route.request().postDataJSON();
    const resources = Array.isArray(body?.resources) ? body.resources : [];
    const names = Array.isArray(body?.names) ? body.names : [];
    const rows = makeRows(resources, names.slice(0, 30), 2);
    line(browserName, 'API fixture', `recheck names=${names.length} resources=${resources.join(',')}`);
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ rows }) });
  });
}

async function setResources(page, browserName, resources) {
  for (const resource of allResources) {
    await page.locator(`input[name="resource"][value="${resource}"]`).setChecked(resources.includes(resource));
  }
  const selected = await page.evaluate(() => typeof selectedResources === 'function' ? selectedResources() : []);
  line(browserName, 'RESOURCE COMBINATION', selected.length ? selected.join(' + ') : '0 resources / generation-only');
}

async function snapshot(page, browserName, label) {
  const state = await page.evaluate(() => ({
    sessionId: current?.id || null,
    title: current?.title || '',
    mode: current?.entryMode || current?.uiFlow || '',
    resources: typeof selectedResources === 'function' ? selectedResources() : [],
    results: current?.results?.length || 0,
    shortlist: current?.shortlist?.length || 0,
    directions: current?.directionAnchors?.length || 0,
    feedback: Object.values(current?.feedback || {}).filter(v => v?.vote || v?.comment).length,
    runs: (current?.runs || []).map(run => ({ id: run.id, status: run.status, prompt: run.prompt, start: run.startResultCount, end: run.endResultCount })),
    status: document.getElementById('status')?.textContent?.trim() || '',
  }));
  line(browserName, 'SNAPSHOT ' + label, JSON.stringify(state));
  return state;
}

async function clickSearchAndWait(page, browserName, label, expectGrowth = true) {
  const before = await page.evaluate(() => current?.results?.length || 0);
  await page.locator('#startBtn').click();
  await page.waitForFunction(() => !document.getElementById('startBtn')?.disabled, null, { timeout: 15_000 });
  const after = await page.evaluate(() => current?.results?.length || 0);
  const status = (await page.locator('#status').textContent() || '').trim();
  line(browserName, 'SEARCH ' + label, `results ${before}->${after}; status=${status}`);
  if (expectGrowth && after <= before) failures.push(`${browserName}: ${label} produced no new visible candidate (${before}->${after})`);
}

async function feedbackClicks(page, browserName) {
  await page.locator('[data-tab="feed"]').click();
  const actions = [
    ['like', 'BreadHearth'],
    ['dislike', 'CrustSun'],
    ['shortlist-btn', 'FlourEmber'],
    ['direction-btn', 'OvenRise'],
  ];
  for (const [cls, name] of actions) {
    const button = page.locator(`.${cls}[data-name="${name}"]`).first();
    if (!await button.count()) {
      failures.push(`${browserName}: missing feedback control ${cls} for ${name}`);
      continue;
    }
    await button.click();
    line(browserName, 'FEEDBACK CLICK', `${cls} ${name}`);
  }
  const comment = page.locator('.comment-toggle[data-name="GrainGlow"]').first();
  if (!await comment.count()) {
    failures.push(`${browserName}: missing comment control for GrainGlow`);
    return;
  }
  await comment.click();
  const box = page.locator('[data-commentbox="GrainGlow"]').first();
  await box.locator('input').fill('Подобається зв’язок із зерном, але хочу ще сильніше відчуття хліба й випічки.');
  await box.locator('.save-comment').click();
  line(browserName, 'FEEDBACK COMMENT', 'GrainGlow -> semantic bread/bakery guidance');
}

async function run(browserType, browserName, device) {
  const browser = await browserType.launch({ headless: true });
  const context = await browser.newContext(device);
  const page = await context.newPage();
  const pageErrors = [];
  const consoleErrors = [];
  page.on('pageerror', error => pageErrors.push(String(error?.stack || error)));
  page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()); });
  await installFixtures(page, browserName);

  try {
    const response = await page.goto(base + '/', { waitUntil: 'domcontentloaded', timeout: 20_000 });
    line(browserName, 'OPEN', `HTTP ${response?.status()} ${base}/`);
    await page.waitForTimeout(750);

    await page.locator('[data-nm-flow="brand"]').click();
    line(browserName, 'FLOW', 'brand');
    await setResources(page, browserName, []);
    await page.locator('#prompt').fill('Створи брендову назву для сучасної пекарні з хлібом на заквасці, ремісничою випічкою та теплим ранковим образом.');
    await clickSearchAndWait(page, browserName, 'generation-only / no resources');
    await snapshot(page, browserName, 'after generation-only');

    await setResources(page, browserName, ['com']);
    await page.locator('#prompt').fill('Хочу ще більше назв прямо пов’язаних з хлібом, скоринкою, тістом, піччю та випічкою.');
    await clickSearchAndWait(page, browserName, '.com only');
    await feedbackClicks(page, browserName);
    await snapshot(page, browserName, 'after .com + feedback');

    await setResources(page, browserName, ['instagram', 'telegram']);
    await page.locator('#prompt').fill('Тепер шукай короткі брендові назви пекарні, але щоб без пояснення було зрозуміло: bread, loaf, crust, dough, flour, oven або bake.');
    await clickSearchAndWait(page, browserName, 'Instagram + Telegram');
    await snapshot(page, browserName, 'after social pair');

    await setResources(page, browserName, ['com', 'instagram', 'telegram', 'youtube']);
    await page.locator('#prompt').fill('Знайди сильні назви для пекарні та хлібного магазину; перевага смисловим сполученням, менше абстрактних вигаданих слів.');
    await clickSearchAndWait(page, browserName, '.com + Instagram + Telegram + YouTube');
    await snapshot(page, browserName, 'after 4-resource bundle');

    await setResources(page, browserName, allResources);
    const recheck = page.locator('#nmRecheckResults');
    if (await recheck.count() && !(await recheck.isDisabled())) {
      await recheck.click();
      await page.waitForFunction(() => (document.getElementById('status')?.textContent || '').includes('Перепровірено'), null, { timeout: 15_000 });
      line(browserName, 'RECHECK', 'all 7 resources on existing results');
    } else {
      failures.push(`${browserName}: all-resource recheck button unavailable`);
    }
    await snapshot(page, browserName, 'after all-resource recheck');

    await page.locator('[data-nm-flow="identity"]').click();
    line(browserName, 'FLOW', 'identity / existing brand fixed');
    await page.locator('#existingBrandName').fill('BreadHearth');
    await setResources(page, browserName, ['telegram', 'youtube', 'x']);
    await page.locator('#prompt').fill('Для існуючого бренду BreadHearth знайди придатні цифрові ідентифікатори та нікнейми без зміни базової назви.');
    await clickSearchAndWait(page, browserName, 'identity Telegram + YouTube + X');
    await snapshot(page, browserName, 'after identity');

    for (const tab of ['feed', 'recommended', 'shortlist', 'feed']) {
      const button = page.locator(`[data-tab="${tab}"]`);
      if (await button.count() && await button.isVisible()) {
        await button.click();
        line(browserName, 'TAB CLICK', tab);
      }
    }

    const save = page.locator('#saveBtn');
    await save.click();
    line(browserName, 'SAVE MENU', 'opened');
    const preview = page.locator('#previewClientReport');
    if (await preview.count()) {
      await preview.click();
      const modal = page.locator('#clientReportPreview');
      await modal.waitFor({ state: 'visible', timeout: 5_000 });
      line(browserName, 'REPORT PREVIEW', 'opened');
      const close = page.locator('[data-report-close]').first();
      if (await close.count()) await close.click();
      line(browserName, 'REPORT PREVIEW', 'closed');
    }

    const report = await page.evaluate(() => typeof window.clientReportTxt === 'function' ? window.clientReportTxt() : 'clientReportTxt unavailable');
    transcript.push('', `===== ${browserName} FINAL CLIENT TXT =====`, report, `===== END ${browserName} FINAL CLIENT TXT =====`, '');
    line(browserName, 'CLIENT TXT', `captured ${String(report).length} chars`);

    if (pageErrors.length) failures.push(`${browserName}: page errors: ${pageErrors.join(' | ')}`);
    if (consoleErrors.length) failures.push(`${browserName}: console errors: ${consoleErrors.join(' | ')}`);
    line(browserName, 'ERROR SUMMARY', `page=${pageErrors.length}; console=${consoleErrors.length}`);
  } catch (error) {
    failures.push(`${browserName}: ${String(error?.stack || error)}`);
    line(browserName, 'CRASH', String(error?.stack || error));
  } finally {
    await browser.close();
  }
}

transcript.push('NameMachine — CLIENT JOURNEY AUDIT', `Generated: ${new Date().toISOString()}`, 'Mode: deterministic browser client simulation; availability facts are fixtures, not real platform claims.', '');

await run(chromium, 'chromium-mobile', { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
await run(webkit, 'webkit-mobile', { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
await run(chromium, 'chromium-desktop', { viewport: { width: 1440, height: 1000 }, isMobile: false, hasTouch: false });

transcript.push('', '===== AUDIT RESULT =====', failures.length ? `FAILURES: ${failures.length}` : 'PASS: all client journeys completed without browser/console errors.');
for (const failure of failures) transcript.push('- ' + failure);
const text = transcript.join('\n');
fs.writeFileSync(outPath, text, 'utf8');
console.log('\n===== CLIENT_AUDIT_TXT_BEGIN =====\n' + text + '\n===== CLIENT_AUDIT_TXT_END =====');
if (failures.length) process.exit(1);
