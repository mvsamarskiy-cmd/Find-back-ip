/* Private Money / Global Search report.
 * Captures only the already-returned private-search payload. It never reads or
 * exposes the private unlock secret and never re-labels discovery as verification.
 */
(() => {
  if (window.__nmPrivateMoneyReport) return;
  window.__nmPrivateMoneyReport = true;

  const baseClientReportTxt = window.clientReportTxt;
  const baseExportTxt = window.exportClientReportTxt;
  const baseExportHtml = window.exportClientReportHtml;
  const baseEmail = window.emailClientReport;
  const previousFetch = window.fetch.bind(window);
  let latest = null;

  const TYPE_LABELS = {
    grant:'грант', subsidy:'субсидія / дотація', public_aid:'державна допомога', eu_fund:'фонд ЄС',
    regional_fund:'регіональний фонд', competition:'конкурс', prize:'грошовий приз', challenge:'challenge', bounty:'винагорода / bounty',
    accelerator:'акселератор', incubator:'інкубатор', scholarship:'стипендія', fellowship:'fellowship',
    research_funding:'фінансування досліджень', corporate_open_call:'корпоративний open call', paid_open_call:'оплачуваний open call',
    vc:'венчурний капітал', angel:'бізнес-ангел', equity_program:'інвестиційна / equity програма', crowdfunding:'краудфандинг',
    preferential_loan:'пільговий кредит', guarantee:'гарантія / порука', leasing:'лізинг', factoring:'факторинг',
    equipment_financing:'фінансування обладнання', tax_relief:'податкова пільга', reimbursement:'компенсація / відшкодування',
    employment_incentive:'підтримка працевлаштування', training_support:'фінансування навчання', export_support:'підтримка експорту',
    innovation_voucher:'інноваційний ваучер', green_energy_support:'енергетична / green підтримка', procurement:'закупівля / тендер',
    job_contract:'робота / контракт', subcontract:'субпідряд', supplier_demand:'пошук постачальника', business_for_sale:'бізнес на продаж',
    asset_sale:'продаж активу', liquidation:'ліквідаційний актив', real_estate_opportunity:'можливість у нерухомості', public_auction:'публічний аукціон',
    classified_offer:'оголошення / classified offer', wholesale_closeout:'оптовий залишок / closeout', import_export_gap:'імпортно-експортна можливість',
    market_dislocation:'ринкова / цінова аномалія', off_market_public:'публічна off-market можливість', other_monetizable_signal:'інший монетизований сигнал',
  };
  const FAMILY_LABELS = {
    funding:'фінансування', capital:'капітал / інвестори', finance:'фінансові інструменти', savings:'економія / компенсації',
    revenue:'контракти / виручка', assets:'активи', local:'локальні пропозиції', markets:'ринкові можливості',
    off_market:'публічні off-market можливості', other:'інші можливості',
  };
  const STATUS_LABELS = {
    open:'відкрито', open_or_upcoming:'відкрито або незабаром', upcoming:'незабаром', closed:'закрито', unknown:'невідомо',
  };
  const ELIGIBILITY_LABELS = {
    eligible_candidate:'попередньо відповідає відомим умовам', possible:'можливо підходить — бракує профільних даних',
    ineligible:'є відома умова, якій користувач не відповідає', unknown:'ще не визначено',
  };

  const clean = (value, limit = 1200) => String(value ?? '').replace(/\s+/g, ' ').trim().slice(0, limit);
  const esc = value => clean(value, 20000).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const yesNo = value => value ? 'так' : 'ні';
  const isPrivate = () => document.body.classList.contains('nm-private-global');

  function parseRequestMeta(args) {
    try {
      const init = args?.[1] || {};
      const body = typeof init.body === 'string' ? JSON.parse(init.body) : {};
      return {
        query: clean(body?.query || document.getElementById('prompt')?.value || '', 1000),
        category: clean(body?.category || document.getElementById('nmPrivateCategory')?.value || 'all', 120),
        country: clean(body?.country || document.getElementById('nmPrivateCountry')?.value || 'EU', 40),
        search_id: clean(body?.search_id || '', 120),
      };
    } catch (_) {
      return { query: clean(document.getElementById('prompt')?.value || '', 1000), category: 'all', country: 'EU', search_id: '' };
    }
  }

  function recordOf(row) { return row?.money_record || row?.moneyRecord || row?.opportunity || row || {}; }
  function rowsOf(payload) {
    if (Array.isArray(payload?.results) && payload.results.length) return payload.results;
    if (Array.isArray(payload?.money_records)) return payload.money_records.map(record => ({...record, money_record: record}));
    return [];
  }
  function statusOf(row) {
    const r = recordOf(row);
    return clean(r?.status?.value || row?.status?.value || row?.opportunity?.status?.value || 'unknown', 60) || 'unknown';
  }
  function eligibilityOf(row) {
    const r = recordOf(row);
    return clean(r?.eligibility_state || r?.eligibility?.state || row?.opportunity?.eligibility_state || row?.opportunity?.eligibility?.state || 'unknown', 80) || 'unknown';
  }
  function amountText(row) {
    const r = recordOf(row);
    const amount = r?.amount || row?.opportunity?.amount || row?.amount || {};
    if (amount?.display) return clean(amount.display, 160);
    const currency = clean(amount?.currency || '', 12);
    const min = Number(amount?.min), max = Number(amount?.max);
    const nf = new Intl.NumberFormat('uk-UA', { maximumFractionDigits: 0 });
    if (Number.isFinite(min) && Number.isFinite(max)) return `${nf.format(min)}–${nf.format(max)} ${currency}`.trim();
    if (Number.isFinite(max)) return `до ${nf.format(max)} ${currency}`.trim();
    if (Number.isFinite(min)) return `від ${nf.format(min)} ${currency}`.trim();
    return '';
  }
  function deadlineOf(row) {
    const r = recordOf(row);
    return clean(r?.deadline?.date || row?.opportunity?.deadline?.date || row?.deadline?.date || '', 80);
  }
  function observedAt(row) {
    const r = recordOf(row);
    return clean(r?.direct_verification?.observed_at || r?.verification?.checked_at || row?.opportunity?.verification?.checked_at || row?.verification?.checked_at || row?.retrieved_at || '', 100);
  }
  function sourceUrl(row) {
    const r = recordOf(row);
    return clean(row?.url || r?.url || r?.source_url || r?.direct_verification?.final_url || r?.direct_verification?.requested_url || '', 1200);
  }
  function sourceName(row) {
    const r = recordOf(row);
    return clean(row?.source_name || r?.source_name || r?.funder_or_counterparty || row?.opportunity?.funder_or_counterparty || '', 220);
  }
  function typeOf(row) {
    const r = recordOf(row);
    return clean(r?.opportunity_type || row?.category || 'other_monetizable_signal', 100);
  }
  function familyOf(row) {
    const r = recordOf(row);
    return clean(r?.family || row?.money_family_hint || '', 80);
  }
  function scoreOf(row) {
    const r = recordOf(row);
    const value = Number(r?.practical_ranking?.score ?? row?.fit?.score ?? row?.retrieval_score);
    return Number.isFinite(value) ? value : null;
  }
  function blockersOf(row) {
    const r = recordOf(row);
    const values = [...(Array.isArray(r?.blockers) ? r.blockers : []), ...(Array.isArray(row?.fit?.blockers) ? row.fit.blockers : [])];
    return [...new Set(values.map(v => clean(v, 260)).filter(Boolean))].slice(0, 12);
  }
  function actionsOf(row) {
    const r = recordOf(row);
    const values = r?.action_steps || row?.opportunity?.action_steps || row?.action_steps || [];
    return (Array.isArray(values) ? values : []).map(v => clean(typeof v === 'string' ? v : v?.text || v?.action || '', 320)).filter(Boolean).slice(0, 10);
  }
  function currentVerified(row) { return Boolean(recordOf(row)?.current_call_verified); }
  function sourceObserved(row) { return Boolean(recordOf(row)?.source_observed); }

  function ukrainianSummary(row) {
    const type = typeOf(row), family = familyOf(row), parts = [];
    parts.push(`Тип: ${TYPE_LABELS[type] || type}.`);
    if (family) parts.push(`Напрям: ${FAMILY_LABELS[family] || family}.`);
    const source = sourceName(row); if (source) parts.push(`Організатор або джерело: ${source}.`);
    const amount = amountText(row); if (amount) parts.push(`Знайдена сума: ${amount}.`);
    const deadline = deadlineOf(row); if (deadline) parts.push(`Дедлайн: ${deadline}.`);
    const eligibility = eligibilityOf(row); if (eligibility) parts.push(`Відповідність: ${ELIGIBILITY_LABELS[eligibility] || eligibility}.`);
    if (currentVerified(row)) parts.push('Сторінку прямого джерела перевірено й знайдено ознаки актуального або майбутнього набору.');
    else if (sourceObserved(row)) parts.push('Першоджерело безпосередньо переглянуте, але актуальність можливості не гарантована.');
    else parts.push('Це пошуковий кандидат; перед дією потрібно перевірити першоджерело.');
    return parts.join(' ');
  }

  function summary(payload) {
    const out = { total: 0, currentVerified: 0, sourceObserved: 0, official: 0, status: {}, eligibility: {} };
    for (const row of rowsOf(payload)) {
      out.total += 1;
      if (currentVerified(row)) out.currentVerified += 1;
      if (sourceObserved(row)) out.sourceObserved += 1;
      if (row?.official_source || recordOf(row)?.official_source) out.official += 1;
      const status = statusOf(row); out.status[status] = (out.status[status] || 0) + 1;
      const eligibility = eligibilityOf(row); out.eligibility[eligibility] = (out.eligibility[eligibility] || 0) + 1;
    }
    return out;
  }

  function snapshot() {
    if (latest) return latest;
    return {
      query: clean(document.getElementById('prompt')?.value || '', 1000),
      category: clean(document.getElementById('nmPrivateCategory')?.value || 'all', 120),
      country: clean(document.getElementById('nmPrivateCountry')?.value || 'EU', 40),
      search_id: '',
      payload: null,
      captured_at: '',
    };
  }

  function buildPrivateTxt() {
    const snap = snapshot(), payload = snap.payload || {}, rows = rowsOf(payload), sums = summary(payload);
    const lines = [
      'NameMachine — MONEY / GLOBAL SEARCH REPORT',
      '',
      `Запит: ${snap.query || '—'}`,
      `Географія: ${snap.country || 'EU'}`,
      `Категорія: ${snap.category || 'all'}`,
      `Знайдено можливостей / джерел: ${sums.total}`,
      `Статус пошуку: ${clean(payload?.provider_status || 'unknown', 80)}${payload?.stopped ? ' · зупинено користувачем' : ''}`,
      `Версія intelligence: ${clean(payload?.intelligence_version || payload?.version || '—', 120)}`,
      '',
      '1. ПІДСУМОК ДОКАЗОВОСТІ',
      `- Актуальний набір / call прямо підтверджено: ${sums.currentVerified}`,
      `- Першоджерело безпосередньо переглянуто: ${sums.sourceObserved}`,
      `- Позначено як офіційне джерело: ${sums.official}`,
      `- Статуси: ${Object.entries(sums.status).map(([k,v]) => `${STATUS_LABELS[k] || k}=${v}`).join(' · ') || '—'}`,
      `- Eligibility: ${Object.entries(sums.eligibility).map(([k,v]) => `${ELIGIBILITY_LABELS[k] || k}=${v}`).join(' · ') || '—'}`,
      '',
      '2. ЗНАЙДЕНІ МОЖЛИВОСТІ',
    ];

    if (!rows.length) lines.push('- Private search не повернув рядків для цього запиту.');
    rows.forEach((row, index) => {
      const r = recordOf(row), score = scoreOf(row), blockers = blockersOf(row), actions = actionsOf(row);
      lines.push('', `${index + 1}. ${clean(row?.title || r?.title || 'Без назви', 300)}`);
      lines.push(`- ${ukrainianSummary(row)}`);
      lines.push(`- Статус: ${STATUS_LABELS[statusOf(row)] || statusOf(row)}`);
      if (score !== null) lines.push(`- Практичний score: ${score}`);
      lines.push(`- Current call verified: ${yesNo(currentVerified(row))}`);
      lines.push(`- Source observed: ${yesNo(sourceObserved(row))}`);
      const observed = observedAt(row); if (observed) lines.push(`- Останнє пряме спостереження: ${observed}`);
      const url = sourceUrl(row); if (url) lines.push(`- Першоджерело: ${url}`);
      if (blockers.length) blockers.forEach(value => lines.push(`- ⚠ Блокер: ${value}`));
      if (actions.length) {
        lines.push('- Наступні кроки:');
        actions.forEach(value => lines.push(`  • ${value}`));
      }
      const raw = clean(row?.description || '', 700); if (raw) lines.push(`- Оригінальний фрагмент джерела: ${raw}`);
    });

    lines.push('', '3. ТРАНСПОРТ І ПОШУКОВИЙ ТУНЕЛЬ');
    const tor = payload?.tor_retrieval || {};
    lines.push(`- Web/provider status: ${clean(payload?.provider_status || 'unknown', 80)}`);
    lines.push(`- Tor attempted: ${yesNo(Boolean(tor?.attempted))}${tor?.provider_status ? ` · ${clean(tor.provider_status, 80)}` : ''}`);
    const direct = payload?.direct_verification || {};
    lines.push(`- Direct verification: ${clean(direct?.status || direct?.provider_status || (direct?.attempted ? 'attempted' : 'not reported'), 100)}`);
    const plan = Array.isArray(payload?.search_plan) ? payload.search_plan : [];
    if (plan.length) {
      lines.push('- Search plan:');
      plan.slice(0, 30).forEach((item, index) => lines.push(`  ${index + 1}) ${clean(typeof item === 'string' ? item : JSON.stringify(item), 600)}`));
    }

    lines.push('', '4. МЕЖА ДОКАЗОВОСТІ');
    lines.push(`- ${clean(payload?.truth_note || 'Discovery ≠ verification. Знайдений результат не гарантує доступності, eligibility, прибутку або права на фінансування.', 1200)}`);
    lines.push('- Official source ≠ автоматично підтверджений актуальний набір.');
    lines.push('- Source observed ≠ гарантована актуальність. Current call verified означає лише те, що система прямо побачила ознаки актуального/майбутнього набору у джерелі.');
    return lines.join('\n');
  }

  function buildPrivateHtml() {
    const text = buildPrivateTxt();
    return `<!doctype html><html lang="uk"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>NameMachine Money / Global Search Report</title><style>body{margin:0;background:#f4f5f7;color:#17191d;font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.wrap{max-width:960px;margin:auto;padding:32px 16px 64px}.hero{background:#111827;color:#fff;border-radius:20px;padding:22px 24px;margin-bottom:16px}.hero h1{margin:0;font-size:26px}.hero p{margin:6px 0 0;color:#d6dbe4}.report{white-space:pre-wrap;overflow-wrap:anywhere;background:#fff;border:1px solid #e1e4e8;border-radius:18px;padding:22px;font:13px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace}</style></head><body><main class="wrap"><header class="hero"><h1>Money / Global Search Report</h1><p>${esc(snapshot().query || 'Private search')}</p></header><div class="report">${esc(text)}</div></main></body></html>`;
  }

  function download(text, filename, type) {
    const blob = new Blob([text], {type});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    document.getElementById('saveMenu')?.classList.remove('open');
  }

  function syncMenuLabels() {
    const privateOn = isPrivate();
    const htmlButton = document.getElementById('downloadClientHtml');
    const txtButton = document.getElementById('downloadClientTxt');
    const emailButton = document.getElementById('emailClientReport');
    if (htmlButton) htmlButton.textContent = privateOn ? 'Money / Global звіт HTML' : 'Клієнтський звіт HTML';
    if (txtButton) txtButton.textContent = privateOn ? 'Money / Global звіт TXT' : 'Клієнтський звіт TXT + перевірки';
    if (emailButton) emailButton.textContent = privateOn ? 'Надіслати Money / Global звіт' : 'Надіслати на email';
  }

  window.fetch = async function(...args) {
    const request = args[0];
    const url = typeof request === 'string' ? request : String(request?.url || '');
    const meta = url.includes('/api/private-mode/search') ? parseRequestMeta(args) : null;
    const response = await previousFetch(...args);
    if (meta && response.ok) {
      response.clone().json().then(payload => {
        latest = {...meta, payload, captured_at: new Date().toISOString()};
        syncMenuLabels();
      }).catch(() => {});
    }
    return response;
  };

  window.clientReportTxt = () => isPrivate() ? buildPrivateTxt() : (typeof baseClientReportTxt === 'function' ? baseClientReportTxt() : '');
  window.exportClientReportTxt = () => isPrivate()
    ? download(buildPrivateTxt(), 'namemachine-money-global-report.txt', 'text/plain;charset=utf-8')
    : baseExportTxt?.();
  window.exportClientReportHtml = () => isPrivate()
    ? download(buildPrivateHtml(), 'namemachine-money-global-report.html', 'text/html;charset=utf-8')
    : baseExportHtml?.();
  window.emailClientReport = () => {
    if (!isPrivate()) return baseEmail?.();
    const report = buildPrivateTxt();
    const recipient = window.prompt('На який email підготувати Money / Global звіт?');
    if (recipient === null) return;
    const email = clean(recipient, 180);
    if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      const status = document.getElementById('status'); if (status) status.textContent = 'Email виглядає некоректно.';
      return;
    }
    const body = report.length > 12000 ? report.slice(0, 12000) + '\n\n[Повний звіт можна завантажити у TXT.]' : report;
    document.getElementById('saveMenu')?.classList.remove('open');
    window.location.href = 'mailto:' + encodeURIComponent(email) + '?subject=' + encodeURIComponent('NameMachine — Money / Global Search Report') + '&body=' + encodeURIComponent(body);
  };

  window.__nmPrivateMoneyReportSnapshot = () => latest;
  const observer = new MutationObserver(syncMenuLabels);
  observer.observe(document.body, {attributes:true, attributeFilter:['class']});
  syncMenuLabels();
})();
