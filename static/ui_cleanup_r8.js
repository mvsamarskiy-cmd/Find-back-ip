/* NameMachine UI cleanup — clarity-first UI v3.
 *
 * The stable verification/backend contracts remain unchanged. This layer fixes
 * product routing and presentation: two clear workflows, compact result cards,
 * ranked-results-first navigation, collapsed advanced tools, and mobile clarity.
 * Historical phrase retained for regression context only: AI → перевірка → докази → рейтинг.
 */
(() => {
  let bodyObserver = null;
  let searchStateObserver = null;
  let telemetryObserver = null;
  let buttonTextObserver = null;
  let reportOpen = false;
  let wrappingStart = false;

  function text(id, fallback = '—') {
    const value = document.getElementById(id)?.textContent?.trim();
    return value || fallback;
  }

  function installStyles() {
    if (!document.getElementById('nameMachineUiV2Styles')) {
      const legacy = document.createElement('link');
      legacy.id = 'nameMachineUiV2Styles';
      legacy.rel = 'stylesheet';
      legacy.href = '/static/ui_v2.css?v=1';
      document.head.appendChild(legacy);
    }
    if (!document.getElementById('nameMachineUiV3Styles')) {
      const link = document.createElement('link');
      link.id = 'nameMachineUiV3Styles';
      link.rel = 'stylesheet';
      link.href = '/static/ui_v3_clarity.css?v=1';
      document.head.appendChild(link);
    }
  }

  function ensureProductIntro() {
    const shell = document.querySelector('.shell');
    const composer = document.querySelector('.composer');
    if (!shell || !composer) return false;
    let intro = document.getElementById('nameMachineIntro');
    if (!intro) {
      intro = document.createElement('section');
      intro.id = 'nameMachineIntro';
      intro.className = 'nm-intro';
      intro.setAttribute('aria-label', 'NameMachine');
      shell.insertBefore(intro, composer);
    }
    intro.innerHTML = `
      <div class="nm-intro-kicker">AI naming & identity intelligence</div>
      <h1>Знайди назву, домен і нікнейми</h1>
      <p>Опиши, що тобі потрібно. Система сама генерує назви, перевіряє вибрані ресурси й показує найсильніші результати.</p>`;
    return true;
  }

  function ensureComposerLabel() {
    const composer = document.querySelector('.composer');
    if (!composer) return false;
    let label = document.getElementById('nameMachineComposerLabel');
    if (!label) {
      label = document.createElement('div');
      label.id = 'nameMachineComposerLabel';
      label.className = 'nm-composer-label';
      composer.insertBefore(label, composer.firstChild);
    }
    label.innerHTML = '<span>Що потрібно?</span><span>Опиши задачу своїми словами</span>';
    return true;
  }

  function ensureTruthLegend() {
    const tabs = document.querySelector('.tabs');
    if (!tabs) return false;
    let legend = document.getElementById('nameMachineTruthLegend');
    if (!legend) {
      legend = document.createElement('div');
      legend.id = 'nameMachineTruthLegend';
      legend.className = 'nm-truth-legend';
      legend.setAttribute('aria-label', 'Статуси перевірки');
      tabs.insertAdjacentElement('afterend', legend);
    }
    legend.innerHTML = `
      <span class="strict"><i></i>вільне — підтверджено</span>
      <span class="paid"><i></i>можна купити</span>
      <span class="promising"><i></i>перспективне</span>
      <span class="conflict"><i></i>зайняте</span>`;
    return true;
  }

  function flowFromSession() {
    if (current?.uiFlow === 'identity' || current?.entryMode === 'identity') return 'identity';
    return 'brand';
  }

  function ideaOnly() {
    return Boolean(current?.uiIdeaOnly);
  }

  function syncFlowToSession() {
    if (!current) return;
    const flow = flowFromSession();
    current.uiFlow = flow;
    current.entryMode = flow === 'identity' ? 'identity' : (ideaOnly() ? 'generic_name' : 'brand');
  }

  function setFlow(flow, options = {}) {
    if (!current) return;
    current.uiFlow = flow === 'identity' ? 'identity' : 'brand';
    if (current.uiFlow === 'identity') current.uiIdeaOnly = false;
    syncFlowToSession();
    document.querySelectorAll('[data-nm-flow]').forEach(button => {
      button.classList.toggle('active', button.dataset.nmFlow === current.uiFlow);
    });
    const wrap = document.getElementById('existingBrandWrap');
    if (wrap) wrap.hidden = current.uiFlow !== 'identity';
    const idea = document.getElementById('nmIdeaOnly');
    if (idea) idea.checked = Boolean(current.uiIdeaOnly);
    if (!options.silent) {
      try { saveCurrent(); } catch (_) {}
      const status = document.getElementById('status');
      if (status) {
        status.textContent = current.uiFlow === 'identity'
          ? 'Вкажи готову назву. Перевіримо її цифрову присутність і допустимі варіанти.'
          : (current.uiIdeaOnly
            ? 'Режим ідей: генеруємо без перевірки доступності.'
            : 'Створюємо нову назву й одразу перевіряємо вибрані ресурси.');
      }
    }
  }

  function migrateLegacyMode() {
    if (!current) return;
    if (!current.uiFlow) {
      current.uiFlow = current.entryMode === 'identity' ? 'identity' : 'brand';
    }
    // The old generic-name card was an easy trap: it silently disabled all
    // availability checks. v3 makes verification the default; idea-only must
    // now be an explicit advanced choice.
    if (current.entryMode === 'generic_name' && current.uiIdeaOnly !== true) {
      current.entryMode = 'brand';
      current.uiFlow = 'brand';
    }
    if (current.entryMode === 'other') {
      current.entryMode = 'brand';
      current.uiFlow = 'brand';
    }
  }

  function ensureFlowPicker() {
    const composer = document.querySelector('.composer');
    const prompt = document.getElementById('prompt');
    if (!composer || !prompt) return false;
    migrateLegacyMode();

    let picker = document.getElementById('nmFlowPicker');
    if (!picker) {
      picker = document.createElement('section');
      picker.id = 'nmFlowPicker';
      picker.className = 'nm-flow-picker';
      picker.innerHTML = `
        <div class="nm-flow-title"><span>Режим</span><small>дві зрозумілі дії</small></div>
        <div class="nm-flow-options">
          <button type="button" class="nm-flow-option" data-nm-flow="brand">
            <span class="nm-flow-icon">✦</span><strong>Створити назву</strong><span>генерація + перевірка мереж</span>
          </button>
          <button type="button" class="nm-flow-option" data-nm-flow="identity">
            <span class="nm-flow-icon">✓</span><strong>Перевірити назву</strong><span>якщо назва вже є</span>
          </button>
        </div>
        <div class="nm-flow-extra">
          <span>За замовчуванням перевіряємо все, що вибрано нижче.</span>
          <details><summary>Налаштування</summary><div class="nm-advanced-box"><label><input id="nmIdeaOnly" type="checkbox"> Лише ідеї, без перевірки</label></div></details>
        </div>`;
      composer.insertBefore(picker, prompt);
      picker.addEventListener('click', event => {
        const button = event.target.closest('[data-nm-flow]');
        if (button) setFlow(button.dataset.nmFlow);
      });
      picker.querySelector('#nmIdeaOnly')?.addEventListener('change', event => {
        if (!current) return;
        current.uiIdeaOnly = Boolean(event.target.checked);
        if (current.uiIdeaOnly) current.uiFlow = 'brand';
        setFlow(current.uiFlow || 'brand');
      });
    }

    const originalPanel = document.getElementById('entryModePanel');
    if (originalPanel) originalPanel.setAttribute('aria-hidden', 'true');
    const existingWrap = document.getElementById('existingBrandWrap');
    if (existingWrap && existingWrap.parentElement !== picker) picker.appendChild(existingWrap);
    setFlow(flowFromSession(), { silent: true });
    return true;
  }

  function ensureResourcesHead() {
    const resources = document.querySelector('.resources');
    if (!resources) return false;
    let head = document.getElementById('nmResourcesHead');
    if (!head) {
      head = document.createElement('div');
      head.id = 'nmResourcesHead';
      head.className = 'nm-resources-head';
      resources.insertAdjacentElement('beforebegin', head);
    }
    let count = 0;
    try { count = selectedResources().length; } catch (_) { count = resources.querySelectorAll('input:checked').length; }
    head.innerHTML = `<b>Перевіряти</b><span>${count} вибрано</span>`;
    return true;
  }

  function localizeButtons() {
    const start = document.getElementById('startBtn');
    const stop = document.getElementById('stopBtn');
    if (start) {
      const map = { Start: 'Знайти', Continue: 'Продовжити', 'Ще назви': 'Ще варіанти' };
      const next = map[start.textContent.trim()];
      if (next && start.textContent !== next) start.textContent = next;
    }
    if (stop && stop.textContent.trim() === 'Stop') stop.textContent = 'Зупинити';
  }

  function installStartRouter() {
    if (wrappingStart || window.__nmClarityStartWrapped) return;
    const previous = window.startSearch;
    if (typeof previous !== 'function') return;
    wrappingStart = true;
    const routed = async function clarityRoutedStartSearch() {
      syncFlowToSession();
      try { saveCurrent(); } catch (_) {}
      return previous.apply(this, arguments);
    };
    window.startSearch = routed;
    try { startSearch = routed; } catch (_) {}
    window.__nmClarityStartWrapped = true;
    wrappingStart = false;
  }

  function reorderTabs() {
    const tabs = document.querySelector('.tabs');
    if (!tabs) return false;
    const feed = tabs.querySelector('[data-tab="feed"]');
    const recommended = tabs.querySelector('[data-tab="recommended"]');
    const shortlist = tabs.querySelector('[data-tab="shortlist"]');
    if (!feed || !recommended || !shortlist) return false;
    if (tabs.firstElementChild !== feed) {
      tabs.append(feed, recommended, shortlist);
    }
    const setLabel = (button, label) => {
      const count = button.querySelector('.count');
      const countHtml = count ? count.outerHTML : '';
      const desired = `${label} ${countHtml}`;
      if (button.innerHTML !== desired) button.innerHTML = desired;
    };
    setLabel(feed, 'Результати');
    setLabel(recommended, 'Підтверджені');
    setLabel(shortlist, 'Збережені');
    if (current?.results?.length && (!current.results.some(row => {
      try { return allGreen(row); } catch (_) { return false; }
    }))) {
      try { if (activeTab === 'recommended') switchTab('feed'); } catch (_) {}
    }
    return true;
  }

  function classifyRows() {
    const rows = Array.isArray(current?.results) ? current.results : [];
    let strict = 0, conflict = 0, promising = 0;
    for (const row of rows) {
      let green = false, bad = false;
      try { green = allGreen(row); } catch (_) {}
      try { bad = hasConflict(row); } catch (_) {}
      if (green) strict += 1;
      else if (bad) conflict += 1;
      else promising += 1;
    }
    return { strict, conflict, promising, total: rows.length };
  }

  function ensureResultSummary() {
    const tabs = document.querySelector('.tabs');
    if (!tabs) return false;
    let summary = document.getElementById('nmResultSummary');
    if (!summary) {
      summary = document.createElement('section');
      summary.id = 'nmResultSummary';
      summary.className = 'nm-result-summary';
      tabs.insertAdjacentElement('afterend', summary);
    }
    const counts = classifyRows();
    summary.innerHTML = `
      <div class="nm-summary-stat strict"><strong>${counts.strict}</strong><span>підтверджено вільних</span></div>
      <div class="nm-summary-stat promising"><strong>${counts.promising}</strong><span>без явного конфлікту</span></div>
      <div class="nm-summary-stat conflict"><strong>${counts.conflict}</strong><span>мають конфлікт</span></div>
      <div class="nm-summary-help">Зелений з’являється лише після авторитетного підтвердження. Жовтий означає: зайнятість не знайдена, але це ще не гарантія реєстрації.</div>`;
    return true;
  }

  function wrapChecks(cardNode) {
    if (!cardNode || cardNode.querySelector(':scope > .checks')) return;
    const checks = Array.from(cardNode.children).filter(child => child.classList?.contains('check'));
    if (!checks.length) return;
    const wrap = document.createElement('div');
    wrap.className = 'checks';
    cardNode.insertBefore(wrap, checks[0]);
    checks.forEach(check => wrap.appendChild(check));
  }

  function compactActions(cardNode) {
    const actions = cardNode?.querySelector(':scope > .actions');
    if (!actions || actions.dataset.nmCompact === '1') return;
    actions.dataset.nmCompact = '1';
    const shortlist = actions.querySelector('.shortlist-btn');
    if (shortlist) {
      shortlist.setAttribute('aria-label', shortlist.textContent.includes('★') ? 'У збережених' : 'Зберегти');
      shortlist.title = shortlist.getAttribute('aria-label');
      shortlist.textContent = shortlist.textContent.includes('★') ? '★' : '☆';
    }
    const secondary = ['.comment-toggle', '.direction-btn', '.copy-btn']
      .map(selector => actions.querySelector(selector)).filter(Boolean);
    if (!secondary.length) return;
    const more = document.createElement('details');
    more.className = 'nm-card-more';
    const summary = document.createElement('summary');
    summary.setAttribute('aria-label', 'Ще дії');
    summary.textContent = '•••';
    const menu = document.createElement('div');
    menu.className = 'nm-card-more-menu';
    secondary.forEach(button => menu.appendChild(button));
    more.append(summary, menu);
    actions.appendChild(more);
  }

  function compactBrandCollision(cardNode) {
    const panel = cardNode?.querySelector(':scope > .brand-collision');
    if (!panel || panel.dataset.nmCompact === '1') return;
    panel.dataset.nmCompact = '1';
    const risk = panel.querySelector('.brand-collision-head span')?.textContent?.trim();
    const details = document.createElement('details');
    details.className = 'nm-brand-details';
    const summary = document.createElement('summary');
    summary.textContent = risk ? `Перевірка бренду · ${risk}` : 'Перевірка бренду';
    const body = document.createElement('div');
    body.className = 'nm-brand-details-body';
    while (panel.firstChild) body.appendChild(panel.firstChild);
    details.append(summary, body);
    panel.appendChild(details);
  }

  function enhanceCards() {
    document.querySelectorAll('.card').forEach(cardNode => {
      wrapChecks(cardNode);
      compactActions(cardNode);
      compactBrandCollision(cardNode);
    });
  }

  function wrapDeepSearch() {
    const panel = document.getElementById('largeSearchPanel');
    if (!panel || panel.closest('.nm-deep-search')) return Boolean(panel);
    const details = document.createElement('details');
    details.className = 'nm-deep-search';
    const summary = document.createElement('summary');
    summary.textContent = 'Глибокий пошук вільних';
    panel.parentNode.insertBefore(details, panel);
    details.append(summary, panel);
    return true;
  }

  function parsedChecked() {
    const status = text('largeSearchStatus', '');
    const match = status.match(/(\d+)\s*\/\s*(\d+)/);
    return match ? Number(match[1]) : null;
  }

  function updateCompactTelemetry() {
    const compact = document.getElementById('largeSearchCompact');
    const panel = document.getElementById('largeSearchPanel');
    if (!compact || !panel) return;
    const checked = parsedChecked();
    const parts = [
      `⏱ ${text('largeSearchClock', '00:00')}`,
      checked === null ? null : `перевірено ${checked}`,
      `🟢 ${text('largeSearchGreen', '0')}`,
      `перспективні ${text('largeSearchPromising', '0')}`,
      `конфлікти ${text('largeSearchConflicts', '0')}`,
    ].filter(Boolean);
    const copy = compact.querySelector('[data-compact-copy]');
    const next = parts.join(' · ');
    if (copy && copy.textContent !== next) copy.textContent = next;
  }

  function attachTelemetryCleanup() {
    const panel = document.getElementById('largeSearchPanel');
    const telemetry = document.getElementById('largeSearchTelemetry');
    if (!panel || !telemetry) return false;
    let compact = document.getElementById('largeSearchCompact');
    if (!compact) {
      compact = document.createElement('div');
      compact.id = 'largeSearchCompact';
      compact.className = 'large-search-compact';
      compact.innerHTML = '<span data-compact-copy>⏱ 00:00 · 🟢 0</span><button type="button" id="largeSearchDetailsToggle" aria-expanded="false">Деталі</button>';
      telemetry.insertAdjacentElement('beforebegin', compact);
      panel.classList.add('nm-telemetry-collapsed');
      compact.querySelector('#largeSearchDetailsToggle').addEventListener('click', () => {
        const open = panel.classList.toggle('nm-telemetry-open');
        const button = compact.querySelector('#largeSearchDetailsToggle');
        button.setAttribute('aria-expanded', String(open));
        button.textContent = open ? 'Сховати деталі' : 'Деталі';
      });
    }
    telemetryObserver?.disconnect();
    telemetryObserver = new MutationObserver(updateCompactTelemetry);
    telemetryObserver.observe(telemetry, { childList: true, subtree: true, characterData: true });
    updateCompactTelemetry();
    return true;
  }

  function ensureReportModal() {
    let modal = document.getElementById('clientReportPreview');
    if (modal) return modal;
    modal = document.createElement('div');
    modal.id = 'clientReportPreview';
    modal.className = 'report-preview';
    modal.hidden = true;
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.innerHTML = `
      <div class="report-preview-card" data-report-card>
        <header class="report-preview-head"><div><strong>Клієнтський звіт</strong><span>Попередній перегляд</span></div><button type="button" class="report-preview-close" data-report-close aria-label="Закрити">×</button></header>
        <div class="report-preview-body"><pre id="clientReportPreviewText"></pre></div>
      </div>`;
    document.body.appendChild(modal);
    modal.querySelector('[data-report-close]').addEventListener('click', closeReportPreview);
    modal.addEventListener('click', event => { if (event.target === modal) closeReportPreview(); });
    return modal;
  }

  function openReportPreview() {
    const modal = ensureReportModal();
    const builder = window.clientReportTxt;
    modal.querySelector('#clientReportPreviewText').textContent = typeof builder === 'function' ? String(builder() || '') : 'Клієнтський звіт ще не готовий для цієї сесії.';
    modal.hidden = false;
    reportOpen = true;
    document.body.classList.add('report-preview-open');
    document.getElementById('saveMenu')?.classList.remove('open');
    modal.querySelector('[data-report-close]')?.focus();
  }

  function closeReportPreview() {
    const modal = document.getElementById('clientReportPreview');
    if (!modal) return;
    modal.hidden = true;
    reportOpen = false;
    document.body.classList.remove('report-preview-open');
  }

  function installPreviewAction() {
    const menu = document.getElementById('saveMenu');
    if (!menu || document.getElementById('previewClientReport')) return Boolean(menu);
    const button = document.createElement('button');
    button.type = 'button';
    button.id = 'previewClientReport';
    button.textContent = 'Переглянути звіт';
    button.addEventListener('click', openReportPreview);
    menu.insertBefore(button, menu.firstChild);
    return true;
  }

  function updateSearchState() {
    const start = document.getElementById('startBtn');
    const stop = document.getElementById('stopBtn');
    const active = Boolean(start?.disabled && stop && !stop.disabled);
    document.body.classList.toggle('nm-search-active', active);
  }

  function installSearchStateObserver() {
    const start = document.getElementById('startBtn');
    const stop = document.getElementById('stopBtn');
    if (!start || !stop || searchStateObserver) return Boolean(start && stop);
    searchStateObserver = new MutationObserver(() => { updateSearchState(); localizeButtons(); });
    searchStateObserver.observe(start, { attributes: true, attributeFilter: ['disabled'] });
    searchStateObserver.observe(stop, { attributes: true, attributeFilter: ['disabled'] });
    buttonTextObserver = new MutationObserver(localizeButtons);
    buttonTextObserver.observe(start, { childList: true, characterData: true, subtree: true });
    buttonTextObserver.observe(stop, { childList: true, characterData: true, subtree: true });
    updateSearchState();
    localizeButtons();
    return true;
  }

  function decorateProductShell() {
    document.body.classList.add('nm-ui-v2', 'nm-ui-v3');
    installStyles();
    ensureProductIntro();
    ensureComposerLabel();
    ensureTruthLegend();
    ensureFlowPicker();
    ensureResourcesHead();
    reorderTabs();
    ensureResultSummary();
    wrapDeepSearch();
    attachTelemetryCleanup();
    installPreviewAction();
    ensureReportModal();
    installSearchStateObserver();
    installStartRouter();
    enhanceCards();

    const status = document.getElementById('status');
    if (status) { status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite'); }
    document.querySelectorAll('.resource input[name="resource"]').forEach(input => {
      const label = input.closest('.resource');
      if (!label) return;
      label.dataset.platform = input.value;
      label.title = `Перевіряти ${input.value === 'com' ? '.com' : input.value}`;
      if (!input.dataset.nmListener) {
        input.dataset.nmListener = '1';
        input.addEventListener('change', ensureResourcesHead);
      }
    });
    const sessionNote = document.querySelector('.session-note');
    if (sessionNote) sessionNote.textContent = 'Сесія, результати та відгуки зберігаються автоматично. Пошук можна зупинити й продовжити без втрати даних.';
  }

  document.addEventListener('keydown', event => { if (event.key === 'Escape' && reportOpen) closeReportPreview(); });

  const style = document.createElement('style');
  style.id = 'uiCleanupR8Style';
  style.textContent = `
    #startBtn,#stopBtn,#saveBtn{min-height:44px}
    .entry-mode-button{min-height:44px;padding:10px 12px}
    #largeSearchPanel.nm-telemetry-collapsed:not(.nm-telemetry-open) #largeSearchTelemetry{display:none!important}
    #largeSearchPanel.nm-telemetry-open #largeSearchTelemetry{display:grid!important}
    .large-search-compact{display:flex;align-items:center;justify-content:space-between;gap:10px;width:100%;min-width:0;padding:8px 9px;border:1px solid var(--line);border-radius:10px;background:var(--panel2);font-size:10px;color:var(--muted)}
    .large-search-compact button{padding:6px 8px;font-size:10px;white-space:nowrap}
    .report-preview-close{position:relative;z-index:5;width:44px;min-width:44px;height:44px;min-height:44px}
    @media(max-width:640px){#largeSearchPanel.large-search{grid-template-columns:minmax(0,1fr) minmax(0,1fr)!important;width:100%;max-width:100%;min-width:0}#largeSearchPanel.large-search>*{min-width:0;max-width:100%}#largeSearchPanel>#largeSearchStatus{grid-column:1/-1}}
  `;
  document.head.appendChild(style);

  function install() {
    decorateProductShell();
  }

  install();
  bodyObserver = new MutationObserver(() => {
    ensureFlowPicker();
    ensureResourcesHead();
    reorderTabs();
    ensureResultSummary();
    wrapDeepSearch();
    attachTelemetryCleanup();
    enhanceCards();
    localizeButtons();
  });
  bodyObserver.observe(document.body, { childList: true, subtree: true });

  window.nameMachineUiCleanup = {
    openReportPreview,
    closeReportPreview,
    updateCompactTelemetry,
    decorateProductShell,
    version: 'ui-v3-clarity',
  };
})();
