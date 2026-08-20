/* NameMachine R8 UI cleanup + UI v2 product shell.
 *
 * Keeps technical observability available without letting it dominate the main
 * workflow, provides a closable client-report preview, and layers a modern
 * presentation system over the stable verification DOM without changing truth
 * semantics or backend contracts.
 */
(() => {
  let telemetryObserver = null;
  let bodyObserver = null;
  let searchStateObserver = null;
  let reportOpen = false;

  function text(id, fallback = '—') {
    const value = document.getElementById(id)?.textContent?.trim();
    return value || fallback;
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
    const nextText = parts.join(' · ');
    if (copy && copy.textContent !== nextText) copy.textContent = nextText;
    if (compact.hidden !== panel.hidden) compact.hidden = panel.hidden;
  }

  function attachTelemetryCleanup() {
    const panel = document.getElementById('largeSearchPanel');
    const telemetry = document.getElementById('largeSearchTelemetry');
    if (!panel || !telemetry || document.getElementById('largeSearchCompact')) return Boolean(panel && telemetry);

    const compact = document.createElement('div');
    compact.id = 'largeSearchCompact';
    compact.className = 'large-search-compact';
    compact.innerHTML = `
      <span data-compact-copy>⏱ 00:00 · 🟢 0</span>
      <button type="button" id="largeSearchDetailsToggle" aria-expanded="false">Деталі</button>`;
    telemetry.insertAdjacentElement('beforebegin', compact);
    panel.classList.add('nm-telemetry-collapsed');

    compact.querySelector('#largeSearchDetailsToggle').addEventListener('click', () => {
      const open = panel.classList.toggle('nm-telemetry-open');
      compact.querySelector('#largeSearchDetailsToggle').setAttribute('aria-expanded', String(open));
      compact.querySelector('#largeSearchDetailsToggle').textContent = open ? 'Сховати деталі' : 'Деталі';
    });

    telemetryObserver?.disconnect();
    telemetryObserver = new MutationObserver(updateCompactTelemetry);
    // Observe only the telemetry subtree plus the panel's own hidden attribute.
    // Observing the whole panel subtree caused a self-triggering MutationObserver:
    // updateCompactTelemetry() mutates #largeSearchCompact, which is itself inside
    // #largeSearchPanel, scheduling the observer forever and starving clicks/DCL.
    telemetryObserver.observe(telemetry, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: ['hidden'],
    });
    telemetryObserver.observe(panel, {
      attributes: true,
      attributeFilter: ['hidden'],
    });
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
    modal.setAttribute('aria-labelledby', 'clientReportPreviewTitle');
    modal.innerHTML = `
      <div class="report-preview-card" data-report-card>
        <header class="report-preview-head">
          <div><strong id="clientReportPreviewTitle">Клієнтський звіт</strong><span>Попередній перегляд</span></div>
          <button type="button" class="report-preview-close" data-report-close aria-label="Закрити">×</button>
        </header>
        <div class="report-preview-body"><pre id="clientReportPreviewText"></pre></div>
      </div>`;
    document.body.appendChild(modal);

    modal.querySelector('[data-report-close]').addEventListener('click', closeReportPreview);
    modal.addEventListener('click', event => {
      if (event.target === modal) closeReportPreview();
    });
    return modal;
  }

  function openReportPreview() {
    const modal = ensureReportModal();
    const builder = window.clientReportTxt;
    const report = typeof builder === 'function'
      ? builder()
      : 'Клієнтський звіт ще не готовий для цієї сесії.';
    modal.querySelector('#clientReportPreviewText').textContent = String(report || '');
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

  function installUiV2Styles() {
    if (document.getElementById('nameMachineUiV2Styles')) return;
    const link = document.createElement('link');
    link.id = 'nameMachineUiV2Styles';
    link.rel = 'stylesheet';
    link.href = '/static/ui_v2.css?v=1';
    document.head.appendChild(link);
  }

  function ensureProductIntro() {
    const shell = document.querySelector('.shell');
    const composer = document.querySelector('.composer');
    if (!shell || !composer || document.getElementById('nameMachineIntro')) return Boolean(shell && composer);
    const intro = document.createElement('section');
    intro.id = 'nameMachineIntro';
    intro.className = 'nm-intro';
    intro.setAttribute('aria-label', 'NameMachine');
    intro.innerHTML = `
      <div class="nm-intro-kicker">AI naming & identity intelligence</div>
      <h1>Знайди назву, домен і нікнейми в одному пошуку</h1>
      <p>Опиши задачу. NameMachine генерує сильні варіанти, перевіряє цифрову присутність і поступово підсилює докази у фоні.</p>`;
    shell.insertBefore(intro, composer);
    return true;
  }

  function ensureComposerLabel() {
    const composer = document.querySelector('.composer');
    if (!composer || document.getElementById('nameMachineComposerLabel')) return Boolean(composer);
    const label = document.createElement('div');
    label.id = 'nameMachineComposerLabel';
    label.className = 'nm-composer-label';
    label.innerHTML = '<span>Пошукове завдання</span><span>AI → перевірка → докази → рейтинг</span>';
    composer.insertBefore(label, composer.firstChild);
    return true;
  }

  function ensureTruthLegend() {
    const tabs = document.querySelector('.tabs');
    if (!tabs || document.getElementById('nameMachineTruthLegend')) return Boolean(tabs);
    const legend = document.createElement('div');
    legend.id = 'nameMachineTruthLegend';
    legend.className = 'nm-truth-legend';
    legend.setAttribute('aria-label', 'Статуси перевірки');
    legend.innerHTML = `
      <span class="strict"><i></i>вільне — підтверджено</span>
      <span class="paid"><i></i>можна купити</span>
      <span class="promising"><i></i>перспективне</span>
      <span class="conflict"><i></i>зайняте</span>`;
    tabs.insertAdjacentElement('afterend', legend);
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
    searchStateObserver = new MutationObserver(updateSearchState);
    searchStateObserver.observe(start, { attributes: true, attributeFilter: ['disabled'] });
    searchStateObserver.observe(stop, { attributes: true, attributeFilter: ['disabled'] });
    updateSearchState();
    return true;
  }

  function decorateProductShell() {
    document.body.classList.add('nm-ui-v2');
    installUiV2Styles();
    ensureProductIntro();
    ensureComposerLabel();
    ensureTruthLegend();
    installSearchStateObserver();

    const status = document.getElementById('status');
    if (status) {
      status.setAttribute('role', 'status');
      status.setAttribute('aria-live', 'polite');
    }
    document.querySelectorAll('.resource input[name="resource"]').forEach(input => {
      const label = input.closest('.resource');
      if (!label) return;
      label.dataset.platform = input.value;
      label.title = `Перевіряти ${input.value === 'com' ? '.com' : input.value}`;
    });
    const sessionNote = document.querySelector('.session-note');
    if (sessionNote) {
      sessionNote.textContent = 'Сесія, результати та відгуки зберігаються автоматично. Пошук можна зупинити й продовжити без втрати вже отриманих результатів.';
    }
  }

  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && reportOpen) closeReportPreview();
  });

  const style = document.createElement('style');
  style.id = 'uiCleanupR8Style';
  style.textContent = `
    #startBtn,#stopBtn,#saveBtn{min-height:44px}
    .entry-mode-button{min-height:44px;padding:10px 12px}
    .large-search-compact{display:flex;align-items:center;justify-content:space-between;gap:10px;width:100%;min-width:0;padding:9px 11px;border:1px solid var(--line);border-radius:11px;background:var(--panel2);font-size:12px;color:var(--muted)}
    .large-search-compact [data-compact-copy]{min-width:0;overflow-wrap:anywhere}
    .large-search-compact button{padding:6px 9px;font-size:11px;white-space:nowrap;flex:0 0 auto}
    #largeSearchPanel.nm-telemetry-collapsed:not(.nm-telemetry-open) #largeSearchTelemetry{display:none!important}
    #largeSearchPanel.nm-telemetry-open #largeSearchTelemetry{display:grid!important}
    body.report-preview-open{overflow:hidden}
    .report-preview[hidden]{display:none!important}.report-preview{position:fixed;inset:0;z-index:10000;background:rgba(0,0,0,.72);display:grid;place-items:center;padding:18px}
    .report-preview-card{position:relative;z-index:1;width:min(920px,100%);height:min(88vh,900px);background:var(--panel);border:1px solid var(--line);border-radius:20px;overflow:hidden;display:grid;grid-template-rows:auto 1fr;box-shadow:0 24px 80px rgba(0,0,0,.45)}
    .report-preview-head{position:relative;z-index:2;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 14px;border-bottom:1px solid var(--line);background:var(--panel2)}
    .report-preview-head>div{display:grid;gap:2px;min-width:0}.report-preview-head strong{font-size:14px}.report-preview-head span{font-size:11px;color:var(--muted)}
    .report-preview-close{position:relative;z-index:5;flex:0 0 44px;width:44px;min-width:44px;height:44px;min-height:44px;padding:0;border-radius:50%;font-size:26px;line-height:1;display:grid;place-items:center;pointer-events:auto;touch-action:manipulation}
    .report-preview-body{overflow:auto;background:#f4f5f7;color:#17191d;padding:22px}
    .report-preview-body pre{margin:0 auto;max-width:820px;white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#fff;border:1px solid #e1e4e8;border-radius:16px;padding:20px;color:#17191d}
    @media(max-width:640px){
      .report-preview{padding:0}.report-preview-card{height:100dvh;border-radius:0;border-left:0;border-right:0}.report-preview-body{padding:12px}.report-preview-body pre{padding:15px;font-size:13px}.large-search-compact{align-items:center}
      #largeSearchPanel.large-search{grid-template-columns:minmax(0,1fr) minmax(0,1fr)!important;width:100%;max-width:100%;min-width:0}
      #largeSearchPanel.large-search>*{min-width:0;max-width:100%}
      #largeSearchPanel>strong,#largeSearchPanel>#hunterSearchStrategy,#largeSearchPanel>.hunter-label,#largeSearchPanel>#largeSearchStart,#largeSearchPanel>#largeSearchCancel,#largeSearchPanel>#largeSearchStatus,#largeSearchPanel>#hunterGoalStatus,#largeSearchPanel>#proceduralFocusStatus,#largeSearchPanel>#largeSearchCompact,#largeSearchPanel>#largeSearchTelemetry{grid-column:1/-1;width:100%}
      #largeSearchPanel>#largeSearchTarget{grid-column:1;width:100%}
      #largeSearchPanel>#hunterTargetMatches{grid-column:2;width:100%}
      #largeSearchPanel>#largeSearchStart,#largeSearchPanel>#largeSearchCancel{min-height:44px}
    }
  `;
  document.head.appendChild(style);

  function install() {
    const telemetryReady = attachTelemetryCleanup();
    const reportReady = installPreviewAction();
    decorateProductShell();
    ensureReportModal();
    if (telemetryReady && reportReady) {
      bodyObserver?.disconnect();
      bodyObserver = null;
    }
  }

  install();
  if (!document.getElementById('largeSearchCompact') || !document.getElementById('previewClientReport')) {
    bodyObserver = new MutationObserver(install);
    bodyObserver.observe(document.body, { childList: true, subtree: true });
  }

  window.nameMachineUiCleanup = {
    openReportPreview,
    closeReportPreview,
    updateCompactTelemetry,
    decorateProductShell,
    version: 'ui-v2',
  };
})();