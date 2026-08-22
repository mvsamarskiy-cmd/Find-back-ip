import { chromium, webkit } from 'playwright';

const base = (process.env.NAMEMACHINE_TEST_URL || 'http://127.0.0.1:8080').replace(/\/$/, '');
const failures = [];

const payload = {
  provider_status: 'complete',
  intelligence_version: 'money-test-v1',
  truth_note: 'Discovery is not verification.',
  results: [{
    title: 'Test Polish microbusiness opportunity',
    description: 'Original source snippet for a zero-capital business opportunity.',
    url: 'https://example.org/opportunity-1',
    source_name: 'Example public source',
    official_source: true,
    retrieval_score: 81,
    fit: {score: 87, blockers: ['verify applicant requirements']},
    money_record: {
      opportunity_type: 'business_for_sale',
      family: 'assets',
      current_call_verified: true,
      source_observed: true,
      eligibility_state: 'possible',
      amount: {min: 0, max: 5000, currency: 'PLN'},
      deadline: {date: '2026-09-30'},
      status: {value: 'open'},
      practical_ranking: {score: 88},
      direct_verification: {observed_at: '2026-08-22T02:18:38Z'},
      blockers: ['verify applicant requirements'],
      action_steps: ['Read the source conditions', 'Confirm eligibility'],
    },
  }],
  tor_retrieval: {attempted: true, provider_status: 'complete'},
  direct_verification: {attempted: true, status: 'complete'},
  search_plan: ['exact user query', 'bounded source expansion'],
};

async function run(browserType, name) {
  const browser = await browserType.launch({headless: true});
  const context = await browser.newContext({viewport: {width: 390, height: 844}, isMobile: true, hasTouch: true});
  const page = await context.newPage();
  const reliabilityRequests = [];
  page.on('request', request => {
    if (request.url().includes('/static/search_reliability_overlay.js')) reliabilityRequests.push(request.url());
  });
  try {
    const response = await page.goto(base + '/', {waitUntil: 'domcontentloaded', timeout: 20_000});
    if (response?.status() !== 200) failures.push(`${name}: root status ${response?.status()}`);
    await page.waitForTimeout(700);

    if (reliabilityRequests.length !== 1) {
      failures.push(`${name}: reliability overlay loaded ${reliabilityRequests.length} times`);
    }

    const loaded = await page.evaluate(() => ({
      report: Boolean(window.__nmPrivateMoneyReport),
      identity: Boolean(window.__nmPrivateReportRunIdentityInstalled),
    }));
    if (!loaded.report) failures.push(`${name}: private Money report overlay did not load`);
    if (!loaded.identity) failures.push(`${name}: private report run identity guard did not load`);

    await page.evaluate(() => document.body.classList.add('nm-private-global'));
    const preSearchText = await page.evaluate(() => window.clientReportTxt?.() || '');
    if (!preSearchText.includes('no_search_in_this_page')) failures.push(`${name}: no-search report does not expose run state`);
    if (!preSearchText.includes('Старий in-memory payload навмисно не видається за новий результат')) {
      failures.push(`${name}: stale-payload guard warning missing before search`);
    }

    await page.route('**/api/private-mode/search', async route => {
      await route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify(payload)});
    });

    await page.evaluate(async () => {
      const response = await fetch('/api/private-mode/search', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          query: 'Знайди мені бізнес з 0 в Польщі',
          category: 'all',
          country: 'PL',
          search_id: 'report-smoke-1234',
        }),
      });
      await response.json();
    });
    await page.waitForTimeout(150);

    const state = await page.evaluate(() => ({
      text: window.clientReportTxt?.() || '',
      htmlLabel: document.getElementById('downloadClientHtml')?.textContent || '',
      txtLabel: document.getElementById('downloadClientTxt')?.textContent || '',
      snapshot: window.__nmPrivateMoneyReportSnapshot?.() || null,
      identity: window.__nmPrivateReportRunIdentity?.() || null,
    }));

    const required = [
      'MONEY / GLOBAL SEARCH REPORT',
      '0. ІДЕНТИЧНІСТЬ ЗАПУСКУ',
      'Search ID: report-smoke-1234',
      'Стан run: completed',
      'Git commit:',
      'Знайди мені бізнес з 0 в Польщі',
      'Знайдено можливостей / джерел: 1',
      'Test Polish microbusiness opportunity',
      'Current call verified: так',
      'Source observed: так',
      'https://example.org/opportunity-1',
      'Tor attempted: так',
      'Discovery is not verification.',
    ];
    for (const value of required) {
      if (!state.text.includes(value)) failures.push(`${name}: private report missing ${value}`);
    }
    for (const forbidden of ['ЩО СИСТЕМА ЗРОЗУМІЛА ПРО СМАК', 'ПІДТВЕРДЖЕНІ КАНДИДАТИ', 'МАТЕМАТИЧНА ОСНОВА ВИСНОВКІВ']) {
      if (state.text.includes(forbidden)) failures.push(`${name}: naming report leaked into private report: ${forbidden}`);
    }
    if (!state.htmlLabel.includes('Money / Global')) failures.push(`${name}: HTML report label is not private-mode specific`);
    if (!state.txtLabel.includes('Money / Global')) failures.push(`${name}: TXT report label is not private-mode specific`);
    if (state.snapshot?.payload?.results?.length !== 1) failures.push(`${name}: private payload snapshot was not captured`);
    if (state.identity?.run?.search_id !== 'report-smoke-1234') failures.push(`${name}: run identity did not capture search_id`);
    if (state.identity?.run?.status !== 'completed') failures.push(`${name}: run identity did not reach completed`);

    console.log(JSON.stringify({browser: name, reliabilityRequests: reliabilityRequests.length, reportLength: state.text.length}, null, 2));
  } catch (error) {
    failures.push(`${name}: ${String(error?.stack || error)}`);
  } finally {
    await browser.close();
  }
}

await run(chromium, 'chromium-private-money-report');
await run(webkit, 'webkit-private-money-report');

if (failures.length) {
  console.error('PRIVATE MONEY REPORT SMOKE FAILED');
  failures.forEach(item => console.error('- ' + item));
  process.exit(1);
}
console.log('PRIVATE MONEY REPORT SMOKE OK');
