import { chromium, webkit } from 'playwright';

const base = (process.env.NAMEMACHINE_TEST_URL || 'http://127.0.0.1:8080').replace(/\/$/, '');
const failures = [];

function largePayload() {
  const filler = 'Source evidence sentence about a public cash prize competition. '.repeat(55);
  const results = Array.from({length: 60}, (_, index) => ({
    title: `Cash prize opportunity ${index + 1}`,
    description: `${filler} Candidate ${index + 1}.`,
    url: `https://example.org/prize/${index + 1}`,
    source_name: 'Example public source',
    retrieval_score: 80 - (index % 20),
    category: 'prize',
    ui_explanation: {
      about: `Публічний конкурс №${index + 1} з грошовим призом.`,
      why: 'У тексті джерела знайдено ознаки вибраного типу «prize».',
      value: 'Конкретну суму або матеріальну вигоду з цього фрагмента не підтверджено.',
      uncertainty: 'поточна доступність не підтверджена; відповідність користувачу не визначена.',
    },
    money_record: {
      opportunity_id: `call-${index + 1}`,
      opportunity_type: 'prize',
      family: 'funding',
      current_call_verified: false,
      source_observed: false,
      eligibility_state: 'unknown',
      status: {value: 'unknown'},
      practical_ranking: {score: 70},
    },
  }));
  return {
    provider_status: 'complete',
    intelligence_version: 'money-graph-search-v2.3',
    results,
    result_quality: {client_results: 60, max_client_results: 60, scope_rejected: 12},
    search_plan: ['Польша', 'Польша cash prize competition Poland'],
    truth_note: 'Discovery is not verification.',
  };
}

async function run(browserType, name) {
  const browser = await browserType.launch({headless: true});
  const context = await browser.newContext({viewport: {width: 390, height: 844}, isMobile: true, hasTouch: true});
  const page = await context.newPage();
  try {
    const root = await page.goto(base + '/', {waitUntil: 'domcontentloaded', timeout: 20_000});
    if (root?.status() !== 200) failures.push(`${name}: root status ${root?.status()}`);
    await page.waitForTimeout(500);

    const payload = largePayload();
    await page.route('**/api/private-mode/search', async route => {
      await route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify(payload)});
    });

    const elapsed = await page.evaluate(async () => {
      document.body.classList.add('nm-private-global');
      const started = performance.now();
      const response = await fetch('/api/private-mode/search', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({query: 'Польша', category: 'prize', country: 'EU', search_id: 'mobile-quality-smoke'}),
      });
      const data = await response.json();

      const root = document.getElementById('nmPrivateResults') || (() => {
        const node = document.createElement('div');
        node.id = 'nmPrivateResults';
        document.body.appendChild(node);
        return node;
      })();
      root.replaceChildren();
      const row = data.results[0];
      const card = document.createElement('article'); card.className = 'nmpg-card';
      const title = document.createElement('div'); title.className = 'nmpg-title'; title.textContent = row.title;
      const desc = document.createElement('div'); desc.className = 'nmpg-desc'; desc.textContent = 'old generic description';
      const details = document.createElement('details'); details.className = 'nmpg-original';
      const summary = document.createElement('summary'); summary.textContent = 'Оригінальний фрагмент джерела';
      const p = document.createElement('p'); p.textContent = row.description;
      details.append(summary, p); card.append(title, desc, details); root.appendChild(card);
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      return performance.now() - started;
    });

    await page.waitForTimeout(150);
    const state = await page.evaluate(() => ({
      identity: window.__nmPrivateReportRunIdentity?.() || null,
      explained: Boolean(document.querySelector('.nmpg-card .nmpg-explain')),
      text: document.querySelector('.nmpg-card .nmpg-explain')?.textContent || '',
      oldHidden: Boolean(document.querySelector('.nmpg-card .nmpg-desc')?.hidden),
    }));

    if (elapsed > 4000) failures.push(`${name}: large private payload processing took ${Math.round(elapsed)}ms`);
    if (state.identity?.run?.status !== 'completed') failures.push(`${name}: run identity not completed`);
    if (!state.explained) failures.push(`${name}: structured explanation not rendered`);
    for (const label of ['Про що це', 'Чому тут', 'Що можна отримати', 'Що не підтверджено']) {
      if (!state.text.includes(label)) failures.push(`${name}: explanation missing ${label}`);
    }
    if (!state.oldHidden) failures.push(`${name}: generic legacy description not hidden`);

    console.log(JSON.stringify({browser: name, elapsedMs: Math.round(elapsed), explained: state.explained}, null, 2));
  } catch (error) {
    failures.push(`${name}: ${String(error?.stack || error)}`);
  } finally {
    await browser.close();
  }
}

await run(chromium, 'chromium-private-mobile-quality');
await run(webkit, 'webkit-private-mobile-quality');

if (failures.length) {
  console.error('PRIVATE MOBILE RESULT QUALITY SMOKE FAILED');
  failures.forEach(item => console.error('- ' + item));
  process.exit(1);
}
console.log('PRIVATE MOBILE RESULT QUALITY SMOKE OK');
