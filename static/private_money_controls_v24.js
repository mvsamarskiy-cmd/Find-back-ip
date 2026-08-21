/* Money / Material Opportunity private-mode controls v2.4.
 * Enhances the existing private search UI without replacing its proven search controller.
 */
(() => {
  if (window.__nmPrivateMoneyControlsV24) return;
  window.__nmPrivateMoneyControlsV24 = true;

  const FAMILY_LABELS = {
    funding: 'Фінансування / гранти',
    capital: 'Капітал / інвестори',
    finance: 'Кредити / фінансові інструменти',
    savings: 'Економія / компенсації / пільги',
    revenue: 'Доходи / контракти / тендери',
    assets: 'Активи / ліквідації / аукціони',
    local: 'Локальні пропозиції / classifieds',
    markets: 'Ринкові можливості / цінові розриви',
    off_market: 'Off-market / маловидимі публічні можливості',
    other: 'Інші матеріальні можливості',
  };

  const TYPE_LABELS = {
    grant: 'Гранти', subsidy: 'Субсидії / дотації', public_aid: 'Державна допомога',
    eu_fund: 'Фонди ЄС', regional_fund: 'Регіональні фонди', competition: 'Конкурси',
    prize: 'Грошові призи', challenge: 'Challenges', bounty: 'Bounties / винагороди',
    accelerator: 'Акселератори', incubator: 'Інкубатори', scholarship: 'Стипендії',
    fellowship: 'Fellowships', research_funding: 'Фінансування досліджень',
    corporate_open_call: 'Corporate open calls', paid_open_call: 'Оплачувані open calls',
    vc: 'Venture Capital', angel: 'Бізнес-ангели', equity_program: 'Equity / investment programs',
    crowdfunding: 'Краудфандинг', preferential_loan: 'Пільгові кредити', guarantee: 'Гарантії / поруки',
    leasing: 'Лізинг', factoring: 'Факторинг', equipment_financing: 'Фінансування обладнання',
    tax_relief: 'Податкові пільги', reimbursement: 'Компенсації / відшкодування',
    employment_incentive: 'Підтримка працевлаштування', training_support: 'Фінансування навчання',
    export_support: 'Підтримка експорту', innovation_voucher: 'Інноваційні ваучери',
    green_energy_support: 'Енергетична / green support', procurement: 'Закупівлі / тендери',
    job_contract: 'Робота / контракти', subcontract: 'Субпідряд', supplier_demand: 'Пошук постачальників',
    business_for_sale: 'Бізнеси на продаж', asset_sale: 'Продаж активів', liquidation: 'Ліквідаційні активи',
    real_estate_opportunity: 'Нерухомість / distressed real estate', public_auction: 'Публічні аукціони',
    classified_offer: 'Оголошення / classified offers', wholesale_closeout: 'Оптові залишки / closeouts',
    import_export_gap: 'Import / export gaps', market_dislocation: 'Ринкові аномалії / price gaps',
    off_market_public: 'Публічні off-market можливості', other_monetizable_signal: 'Інші монетизовані сигнали',
  };

  const TYPE_FAMILY = {
    grant:'funding', subsidy:'funding', public_aid:'funding', eu_fund:'funding', regional_fund:'funding',
    competition:'funding', prize:'funding', challenge:'funding', bounty:'funding', scholarship:'funding',
    fellowship:'funding', research_funding:'funding', corporate_open_call:'funding',
    accelerator:'capital', incubator:'capital', vc:'capital', angel:'capital', equity_program:'capital', crowdfunding:'capital',
    preferential_loan:'finance', guarantee:'finance', leasing:'finance', factoring:'finance', equipment_financing:'finance',
    tax_relief:'savings', reimbursement:'savings', employment_incentive:'savings', training_support:'savings',
    export_support:'savings', innovation_voucher:'savings', green_energy_support:'savings',
    paid_open_call:'revenue', procurement:'revenue', job_contract:'revenue', subcontract:'revenue', supplier_demand:'revenue',
    business_for_sale:'assets', asset_sale:'assets', liquidation:'assets', real_estate_opportunity:'assets', public_auction:'assets',
    classified_offer:'local', wholesale_closeout:'local', import_export_gap:'markets', market_dislocation:'markets',
    off_market_public:'off_market', other_monetizable_signal:'other',
  };

  let capability = null;
  let renderingCategory = false;
  let lastPayload = null;

  function node(tag, cls, text) {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (text !== undefined) el.textContent = String(text);
    return el;
  }

  function addStyle() {
    if (document.getElementById('nmPrivateMoneyControlsV24Style')) return;
    const style = document.createElement('style');
    style.id = 'nmPrivateMoneyControlsV24Style';
    style.textContent = `
      body.nm-private-global #nmPrivateGlobalPanel.nmm-primary-results{display:block!important;width:100%;min-height:48vh;margin:10px 0 14px;padding:0;scroll-margin-top:10px}
      body.nm-private-global #nmPrivateResults{min-height:280px}
      body.nm-private-global #nmPrivateGlobalPanel .nmpg-toolbar{display:flex;gap:8px;flex-wrap:wrap;align-items:stretch}
      body.nm-private-global #nmPrivateGlobalPanel .nmpg-toolbar select{flex:1 1 230px;min-width:0}
      .nmm-main-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:10px}
      .nmm-main-title{font-size:20px;font-weight:900;line-height:1.2}
      .nmm-main-sub{margin-top:4px;color:var(--muted);font-size:11px;line-height:1.4}
      .nmm-main-count{white-space:nowrap;border:1px solid var(--line);border-radius:999px;padding:6px 9px;font-size:11px;color:var(--muted)}
      .nmm-transport{display:flex;gap:7px;flex-wrap:wrap;margin:0 0 12px}
      .nmm-transport-chip{border:1px solid var(--line);border-radius:999px;padding:5px 8px;font-size:11px;color:var(--muted)}
      .nmm-transport-chip.on{border-color:var(--ok);color:var(--ok)}
      .nmm-transport-chip.warn{border-color:#a9823f;color:#dcb869}
      body.nm-private-global .composer{position:sticky;bottom:8px;z-index:25}
      @media(max-width:640px){body.nm-private-global #nmPrivateGlobalPanel.nmm-primary-results{min-height:56vh}.nmm-main-head{align-items:center}.nmm-main-title{font-size:18px}}
    `;
    document.head.appendChild(style);
  }

  function taxonomyFromDiagnostics(payload) {
    const universal = payload?.universal_search || payload?.search || {};
    const money = universal?.money_opportunity || {};
    const taxonomy = money?.taxonomy || {};
    return {
      families: Array.isArray(taxonomy.families) ? taxonomy.families : Object.keys(FAMILY_LABELS),
      types: Array.isArray(taxonomy.types) ? taxonomy.types : Object.keys(TYPE_LABELS),
      transport: universal?.opportunity_transport || {},
      directVerification: money?.direct_verification || {},
      version: String(taxonomy.version || money.version || 'money-taxonomy'),
    };
  }

  async function loadCapability() {
    try {
      const response = await fetch('/api/private-mode/diagnostics', {cache: 'no-store'});
      if (!response.ok) return;
      capability = taxonomyFromDiagnostics(await response.json());
      refresh();
    } catch (_) {}
  }

  function categoryOption(value, label) {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = label;
    return option;
  }

  function populateCategory() {
    const select = document.getElementById('nmPrivateCategory');
    if (!select || !capability || renderingCategory) return;
    const requiredSentinel = 'off_market_public';
    const existing = [...select.options].map(option => option.value);
    if (existing.includes(requiredSentinel) && existing.includes('off_market') && select.dataset.nmmTaxonomyVersion === capability.version) return;

    renderingCategory = true;
    const previous = select.value || 'all';
    const fragment = document.createDocumentFragment();
    fragment.appendChild(categoryOption('all', 'Усі матеріальні можливості'));

    const familyGroup = document.createElement('optgroup');
    familyGroup.label = 'Сфери';
    for (const family of capability.families) {
      familyGroup.appendChild(categoryOption(family, FAMILY_LABELS[family] || family.replaceAll('_', ' ')));
    }
    fragment.appendChild(familyGroup);

    const typesByFamily = {};
    for (const type of capability.types) {
      const family = TYPE_FAMILY[type] || 'other';
      (typesByFamily[family] ||= []).push(type);
    }
    for (const family of capability.families) {
      const rows = typesByFamily[family] || [];
      if (!rows.length) continue;
      const group = document.createElement('optgroup');
      group.label = `↳ ${FAMILY_LABELS[family] || family}`;
      for (const type of rows) group.appendChild(categoryOption(type, TYPE_LABELS[type] || type.replaceAll('_', ' ')));
      fragment.appendChild(group);
    }

    select.replaceChildren(fragment);
    select.dataset.nmmTaxonomyVersion = capability.version;
    select.setAttribute('aria-label', 'Категорія матеріальної можливості');
    select.title = 'Сфера або конкретний тип можливості. Вибір впливає на Money search planner.';
    if ([...select.options].some(option => option.value === previous)) select.value = previous;
    else select.value = 'all';
    renderingCategory = false;
  }

  function ensureHeader(panel) {
    let head = document.getElementById('nmPrivateMainHead');
    if (!head) {
      head = node('div', 'nmm-main-head');
      head.id = 'nmPrivateMainHead';
      const copy = node('div', '');
      copy.appendChild(node('div', 'nmm-main-title', 'Результати Money / Global Search'));
      copy.appendChild(node('div', 'nmm-main-sub', 'Web + Tor retrieval · direct-source evidence · Money taxonomy'));
      head.appendChild(copy);
      const count = node('div', 'nmm-main-count', 'Готово до пошуку');
      count.id = 'nmPrivateMainCount';
      head.appendChild(count);
      panel.insertAdjacentElement('afterbegin', head);
    }
  }

  function ensureTransport(panel) {
    let bar = document.getElementById('nmPrivateTransport');
    if (!bar) {
      bar = node('div', 'nmm-transport');
      bar.id = 'nmPrivateTransport';
      const toolbar = panel.querySelector('.nmpg-toolbar');
      if (toolbar) toolbar.insertAdjacentElement('afterend', bar);
      else panel.appendChild(bar);
    }
    const transport = capability?.transport || {};
    const torOn = transport.enabled_by_default !== false;
    const onionOn = Boolean(transport.onion_service_evidence || transport.onion_location_discovery);
    const directOn = capability?.directVerification?.enabled !== false;
    bar.replaceChildren();
    const web = node('span', 'nmm-transport-chip on', 'WEB · ON'); web.id = 'nmTransportWeb'; bar.appendChild(web);
    const tor = node('span', `nmm-transport-chip ${torOn ? 'on' : 'warn'}`, `TOR · ${torOn ? 'AUTO ON' : 'OFF'}`); tor.id = 'nmTransportTor'; bar.appendChild(tor);
    const onion = node('span', `nmm-transport-chip ${onionOn ? 'on' : 'warn'}`, `ONION · ${onionOn ? 'EVIDENCE ON' : 'OFF'}`); onion.id = 'nmTransportOnion'; bar.appendChild(onion);
    const direct = node('span', `nmm-transport-chip ${directOn ? 'on' : 'warn'}`, `DIRECT VERIFY · ${directOn ? 'ON' : 'OFF'}`); direct.id = 'nmTransportDirect'; bar.appendChild(direct);
  }

  function ensurePrimaryLayout() {
    const panel = document.getElementById('nmPrivateGlobalPanel');
    const composer = document.querySelector('.composer');
    if (!panel || !composer) return;
    panel.classList.add('nmm-primary-results');
    if (panel.nextElementSibling !== composer) composer.insertAdjacentElement('beforebegin', panel);
    ensureHeader(panel);
    ensureTransport(panel);
    populateCategory();
  }

  function updateResultMeta(payload) {
    lastPayload = payload;
    const count = document.getElementById('nmPrivateMainCount');
    const records = Array.isArray(payload?.money_records) ? payload.money_records : null;
    const rows = records || (Array.isArray(payload?.results) ? payload.results : []);
    if (count) count.textContent = `${rows.length} результатів · ${payload?.provider_status || 'unknown'}`;

    const tor = document.getElementById('nmTransportTor');
    const torState = payload?.tor_retrieval;
    if (tor && torState?.attempted) {
      const ok = torState.provider_status === 'complete';
      tor.className = `nmm-transport-chip ${ok ? 'on' : 'warn'}`;
      tor.textContent = `TOR · ${String(torState.provider_status || 'attempted').toUpperCase()}`;
    }
    const panel = document.getElementById('nmPrivateGlobalPanel');
    if (panel && document.body.classList.contains('nm-private-global')) {
      requestAnimationFrame(() => panel.scrollIntoView({behavior: 'smooth', block: 'start'}));
    }
  }

  const previousFetch = window.fetch.bind(window);
  window.fetch = async function(...args) {
    const response = await previousFetch(...args);
    try {
      const request = args[0];
      const url = typeof request === 'string' ? request : String(request?.url || '');
      if (url.includes('/api/private-mode/search')) {
        response.clone().json().then(updateResultMeta).catch(() => {});
      }
    } catch (_) {}
    return response;
  };

  let refreshQueued = false;
  function refresh() {
    if (refreshQueued) return;
    refreshQueued = true;
    requestAnimationFrame(() => {
      refreshQueued = false;
      addStyle();
      if (document.body.classList.contains('nm-private-global')) ensurePrimaryLayout();
      if (lastPayload) updateResultMeta(lastPayload);
    });
  }

  const observer = new MutationObserver(() => refresh());
  observer.observe(document.documentElement, {subtree: true, childList: true, attributes: true, attributeFilter: ['class']});

  addStyle();
  loadCapability();
  refresh();
})();
