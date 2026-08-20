/* NameMachine UI v3 — clarity-first overlay.
 *
 * This layer intentionally leaves verification semantics and the stable R8 UI
 * cleanup untouched. It simplifies product routing and presentation only.
 */
(() => {
  const observedGrids = new WeakSet();

  function installStyles() {
    if (document.getElementById('nameMachineUiV3Styles')) return;
    const link = document.createElement('link');
    link.id = 'nameMachineUiV3Styles';
    link.rel = 'stylesheet';
    link.href = '/static/ui_v3_clarity.css?v=2';
    document.head.appendChild(link);
  }

  function updateHero() {
    const intro = document.getElementById('nameMachineIntro');
    if (intro) {
      const title = intro.querySelector('h1');
      const copy = intro.querySelector('p');
      if (title) title.textContent = 'Знайди назву, домен і нікнейми';
      if (copy) copy.textContent = 'Опиши, що тобі потрібно. Система сама генерує назви, перевіряє вибрані ресурси й показує найсильніші результати.';
    }
    const composerLabel = document.getElementById('nameMachineComposerLabel');
    if (composerLabel) composerLabel.innerHTML = '<span>Що потрібно?</span><span>Опиши задачу своїми словами</span>';
  }

  function hiddenModeButton(mode) {
    return document.querySelector(`#entryModePanel [data-entry-mode="${mode}"]`);
  }

  function currentFlow() {
    const mode = String(current?.entryMode || 'other');
    return mode === 'identity' ? 'identity' : 'brand';
  }

  function applyLegacyMode(mode) {
    const button = hiddenModeButton(mode);
    if (button) button.click();
    else if (current) current.entryMode = mode;
  }

  function migrateLegacyTrap() {
    if (!current) return;
    const mode = String(current.entryMode || 'other');
    if ((mode === 'generic_name' && current.uiIdeaOnly !== true) || mode === 'other') {
      current.uiFlow = 'brand';
      current.uiIdeaOnly = false;
      applyLegacyMode('brand');
    }
  }

  function setFlow(flow, { silent = false } = {}) {
    if (!current) return;
    const next = flow === 'identity' ? 'identity' : 'brand';
    current.uiFlow = next;
    if (next === 'identity') current.uiIdeaOnly = false;
    const legacy = current.uiIdeaOnly ? 'generic_name' : next;
    if (String(current.entryMode || '') !== legacy) applyLegacyMode(legacy);

    document.querySelectorAll('[data-nm-flow]').forEach(button => {
      button.classList.toggle('active', button.dataset.nmFlow === next);
    });
    const idea = document.getElementById('nmIdeaOnly');
    if (idea && idea.checked !== Boolean(current.uiIdeaOnly)) idea.checked = Boolean(current.uiIdeaOnly);
    const wrap = document.getElementById('existingBrandWrap');
    if (wrap) wrap.hidden = next !== 'identity';

    if (!silent) {
      try { saveCurrent(); } catch (_) {}
      const status = document.getElementById('status');
      if (status) status.textContent = next === 'identity'
        ? 'Вкажи готову назву. Перевіримо її цифрову присутність.'
        : (current.uiIdeaOnly
          ? 'Режим ідей: генеруємо без перевірки доступності.'
          : 'Створюємо назву й одразу перевіряємо вибрані ресурси.');
    }
  }

  function ensureFlowPicker() {
    const composer = document.querySelector('.composer');
    const prompt = document.getElementById('prompt');
    if (!composer || !prompt) return;
    migrateLegacyTrap();

    let picker = document.getElementById('nmFlowPicker');
    if (!picker) {
      picker = document.createElement('section');
      picker.id = 'nmFlowPicker';
      picker.className = 'nm-flow-picker';
      picker.innerHTML = `
        <div class="nm-flow-title"><span>Режим</span><small>обери одну дію</small></div>
        <div class="nm-flow-options">
          <button type="button" class="nm-flow-option" data-nm-flow="brand">
            <span class="nm-flow-icon">✦</span><strong>Створити назву</strong><span>генерація + перевірка мереж</span>
          </button>
          <button type="button" class="nm-flow-option" data-nm-flow="identity">
            <span class="nm-flow-icon">✓</span><strong>Перевірити назву</strong><span>коли назва вже є</span>
          </button>
        </div>
        <div class="nm-flow-extra">
          <span>Перевіряємо все, що вибрано нижче.</span>
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
        current.uiFlow = 'brand';
        setFlow('brand');
      });
    }

    const brandWrap = document.getElementById('existingBrandWrap');
    if (brandWrap && brandWrap.parentElement !== picker) picker.appendChild(brandWrap);
    setFlow(currentFlow(), { silent: true });
  }

  function ensureResourcesHead() {
    const resources = document.querySelector('.resources');
    if (!resources) return;
    let head = document.getElementById('nmResourcesHead');
    if (!head) {
      head = document.createElement('div');
      head.id = 'nmResourcesHead';
      head.className = 'nm-resources-head';
      resources.insertAdjacentElement('beforebegin', head);
    }
    const count = resources.querySelectorAll('input[name="resource"]:checked').length;
    const nextHtml = `<b>Перевіряти</b><span>${count} вибрано</span>`;
    if (head.innerHTML !== nextHtml) head.innerHTML = nextHtml;
    resources.querySelectorAll('input[name="resource"]').forEach(input => {
      if (input.dataset.nmClarityListener) return;
      input.dataset.nmClarityListener = '1';
      input.addEventListener('change', ensureResourcesHead);
    });
  }

  function localizeActions() {
    const start = document.getElementById('startBtn');
    const stop = document.getElementById('stopBtn');
    if (start) {
      const value = start.textContent.trim();
      const labels = { Start: 'Знайти', Continue: 'Продовжити', 'Ще назви': 'Ще варіанти' };
      if (labels[value]) start.textContent = labels[value];
    }
    if (stop?.textContent.trim() === 'Stop') stop.textContent = 'Зупинити';
  }

  function renameTabs() {
    const tabs = document.querySelector('.tabs');
    if (!tabs) return;
    const feed = tabs.querySelector('[data-tab="feed"]');
    const recommended = tabs.querySelector('[data-tab="recommended"]');
    const shortlist = tabs.querySelector('[data-tab="shortlist"]');
    if (!feed || !recommended || !shortlist) return;
    if (tabs.firstElementChild !== feed) tabs.append(feed, recommended, shortlist);

    const label = (button, name) => {
      const count = button.querySelector('.count');
      const countHtml = count ? count.outerHTML : '';
      const nextHtml = `${name} ${countHtml}`;
      if (button.innerHTML !== nextHtml) button.innerHTML = nextHtml;
    };
    label(feed, 'Результати');
    label(recommended, 'Підтверджені');
    label(shortlist, 'Збережені');

    if (Array.isArray(current?.results) && current.results.length) {
      const hasStrict = current.results.some(row => {
        try { return allGreen(row); } catch (_) { return false; }
      });
      try { if (!hasStrict && activeTab === 'recommended') switchTab('feed'); } catch (_) {}
    }
  }

  function resultCounts() {
    const rows = Array.isArray(current?.results) ? current.results : [];
    let strict = 0;
    let conflict = 0;
    let promising = 0;
    for (const row of rows) {
      let green = false;
      let bad = false;
      try { green = allGreen(row); } catch (_) {}
      try { bad = hasConflict(row); } catch (_) {}
      if (green) strict += 1;
      else if (bad) conflict += 1;
      else promising += 1;
    }
    return { strict, promising, conflict };
  }

  function ensureResultSummary() {
    const tabs = document.querySelector('.tabs');
    if (!tabs) return;
    let summary = document.getElementById('nmResultSummary');
    if (!summary) {
      summary = document.createElement('section');
      summary.id = 'nmResultSummary';
      summary.className = 'nm-result-summary';
      tabs.insertAdjacentElement('afterend', summary);
    }
    const counts = resultCounts();
    const nextHtml = `
      <div class="nm-summary-stat strict"><strong>${counts.strict}</strong><span>підтверджено вільних</span></div>
      <div class="nm-summary-stat promising"><strong>${counts.promising}</strong><span>без явного конфлікту</span></div>
      <div class="nm-summary-stat conflict"><strong>${counts.conflict}</strong><span>мають конфлікт</span></div>
      <div class="nm-summary-help">Зелений з’являється лише після авторитетного підтвердження. Жовтий означає: зайнятість не знайдена, але це ще не гарантія реєстрації.</div>`;
    if (summary.innerHTML !== nextHtml) summary.innerHTML = nextHtml;
  }

  function wrapChecks(cardNode) {
    if (!cardNode || cardNode.querySelector(':scope > .checks')) return;
    const checks = Array.from(cardNode.children).filter(node => node.classList?.contains('check'));
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
      const selected = shortlist.textContent.includes('★');
      shortlist.textContent = selected ? '★' : '☆';
      shortlist.title = selected ? 'У збережених' : 'Зберегти';
      shortlist.setAttribute('aria-label', shortlist.title);
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

  function enhanceGrid(grid) {
    if (!grid) return;
    grid.querySelectorAll('.card').forEach(cardNode => {
      wrapChecks(cardNode);
      compactActions(cardNode);
      compactBrandCollision(cardNode);
    });
  }

  function observeResultGrids() {
    ['recommendedGrid', 'feedGrid', 'shortlistGrid'].forEach(id => {
      const grid = document.getElementById(id);
      if (!grid || observedGrids.has(grid)) return;
      observedGrids.add(grid);
      enhanceGrid(grid);
      const observer = new MutationObserver(() => {
        enhanceGrid(grid);
        ensureResultSummary();
        renameTabs();
      });
      observer.observe(grid, { childList: true, subtree: true });
    });
  }

  function collapseDeepSearch() {
    const panel = document.getElementById('largeSearchPanel');
    if (!panel || panel.closest('.nm-deep-search')) return;
    const details = document.createElement('details');
    details.className = 'nm-deep-search';
    const summary = document.createElement('summary');
    summary.textContent = 'Глибокий пошук вільних';
    panel.parentNode.insertBefore(details, panel);
    details.append(summary, panel);
  }

  function installButtonLabelObserver() {
    const start = document.getElementById('startBtn');
    const stop = document.getElementById('stopBtn');
    if (!start || !stop || start.dataset.nmLabelObserver) return;
    start.dataset.nmLabelObserver = '1';
    const observer = new MutationObserver(localizeActions);
    observer.observe(start, { childList: true, characterData: true, subtree: true });
    observer.observe(stop, { childList: true, characterData: true, subtree: true });
  }

  function install() {
    document.body.classList.add('nm-ui-v3');
    installStyles();
    updateHero();
    ensureFlowPicker();
    ensureResourcesHead();
    localizeActions();
    installButtonLabelObserver();
    renameTabs();
    ensureResultSummary();
    collapseDeepSearch();
    observeResultGrids();
  }

  install();
  window.nameMachineUiV3 = { install, setFlow, version: 'ui-v3-clarity' };
})();
