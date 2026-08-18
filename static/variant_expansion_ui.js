/* NameMachine R9 visible variant expansion.
 *
 * Clean identifiers are always searched first. This overlay appears only on
 * verified-workflow candidate cards and only generates punctuation/digit/affix
 * variants after an explicit user click. Every generated shape is then checked
 * through /api/variants/check; the UI never promotes not_found to green.
 */
(() => {
  const baseCard = card;
  const MAX_CHECKS = 24;
  const CHECK_WORKERS = 4;
  const LABELS = typeof labels === 'object' ? labels : {
    com: '.com', instagram: 'Instagram', telegram: 'Telegram', tiktok: 'TikTok',
    youtube: 'YouTube', facebook: 'Facebook', x: 'X',
  };
  let grammarPromise = null;
  let activeName = '';
  let running = false;

  function modeAllowsVariants(row) {
    if (row?.product_mode === 'generic_name') return false;
    const mode = typeof window.nameMachineEntryMode === 'function'
      ? window.nameMachineEntryMode()
      : String(current?.entryMode || 'other');
    if (mode === 'generic_name') return false;
    if (row?.verification_state === 'checking' || row?.checked === false) return false;
    return true;
  }

  function injectButton(html, row) {
    if (!modeAllowsVariants(row)) return html;
    const name = String(row?.name || '').trim();
    if (!name) return html;
    const panel = `<div class="variant-expand-entry">
      <button type="button" class="variant-expand-open" data-variant-name="${esc(name)}">Розширити пошук</button>
      <span>_ · цифри · крапки / дефіси лише там, де платформа дозволяє</span>
    </div>`;
    return html.replace('</article>', panel + '</article>');
  }

  card = function variantAwareCard(row, source) {
    return injectButton(baseCard(row, source), row);
  };

  function ensureStore() {
    if (!current) return {};
    if (!current.variantExpansions || typeof current.variantExpansions !== 'object' || Array.isArray(current.variantExpansions)) {
      current.variantExpansions = {};
    }
    return current.variantExpansions;
  }

  function savedExpansion(name) {
    return ensureStore()[String(name || '').toLowerCase()] || null;
  }

  function saveExpansion(name, payload) {
    const store = ensureStore();
    store[String(name || '').toLowerCase()] = payload;
    saveCurrent();
  }

  function parseTokens(value, digitsOnly = false) {
    const output = [];
    const seen = new Set();
    for (const raw of String(value || '').split(/[\s,;]+/)) {
      let token = raw.trim().toLowerCase();
      token = digitsOnly ? token.replace(/[^0-9]/g, '') : token.replace(/[^a-z0-9]/g, '');
      token = token.slice(0, digitsOnly ? 4 : 12);
      if (!token || seen.has(token)) continue;
      seen.add(token);
      output.push(token);
      if (output.length >= 10) break;
    }
    return output;
  }

  function statusCopy(row) {
    const status = String(row?.status || row?.availability?.status || 'unknown');
    if (status === 'claimable') return { rank: 0, cls: 'free', text: '🟢 Вільний' };
    if (status === 'purchasable') return { rank: 1, cls: 'purchase', text: '🟣 Можна купити' };
    if (status === 'not_found') return { rank: 2, cls: 'likely', text: '🟡 Не знайдено · не підтверджено' };
    if (['taken', 'reserved', 'invalid'].includes(status)) return { rank: 3, cls: 'conflict', text: '🔴 Зайнятий / недоступний' };
    if (status === 'rate_limited') return { rank: 4, cls: 'unknown', text: '⏳ Тимчасово не перевірено' };
    return { rank: 4, cls: 'unknown', text: '⚪ Не підтверджено' };
  }

  function resultLink(row) {
    const url = String(row?.availability?.url || '').trim();
    if (url.startsWith('https://')) return url;
    const id = encodeURIComponent(String(row?.identifier || '').toLowerCase());
    const resource = row?.resource;
    if (resource === 'com') return `https://www.name.com/domain/search/${id}.com`;
    if (resource === 'telegram') return `https://t.me/${id}`;
    if (resource === 'instagram') return `https://www.instagram.com/${id}/`;
    if (resource === 'tiktok') return `https://www.tiktok.com/@${id}`;
    if (resource === 'youtube') return `https://www.youtube.com/@${id}`;
    if (resource === 'facebook') return `https://www.facebook.com/${id}`;
    if (resource === 'x') return `https://x.com/${id}`;
    return '';
  }

  function resultActionLabel(row) {
    if (row?.status === 'purchasable') return 'До покупки';
    if (row?.resource === 'com' && row?.status === 'claimable') return 'До реєстрації';
    return 'Відкрити';
  }

  function renderResults(rows, summary = '') {
    const container = document.getElementById('variantExpansionResults');
    const summaryNode = document.getElementById('variantExpansionSummary');
    if (!container || !summaryNode) return;
    const sorted = [...(rows || [])].sort((a, b) => {
      const sa = statusCopy(a), sb = statusCopy(b);
      return sa.rank - sb.rank || String(a.resource).localeCompare(String(b.resource)) || String(a.identifier).localeCompare(String(b.identifier));
    });
    const freeCount = sorted.filter(row => String(row.status) === 'claimable').length;
    const purchaseCount = sorted.filter(row => String(row.status) === 'purchasable').length;
    summaryNode.textContent = summary || `Перевірено ${sorted.length} · 🟢 ${freeCount} · 🟣 ${purchaseCount}`;
    if (!sorted.length) {
      container.innerHTML = '<div class="variant-empty">Варіантів ще немає.</div>';
      return;
    }
    container.innerHTML = sorted.map(row => {
      const state = statusCopy(row);
      const link = resultLink(row);
      const suffix = row.resource === 'com' ? '.com' : '';
      return `<div class="variant-result variant-${state.cls}">
        <div class="variant-result-main">
          <span class="variant-platform">${esc(LABELS[row.resource] || row.resource)}</span>
          <strong>${row.resource === 'com' ? '' : '@'}${esc(row.identifier)}${suffix}</strong>
          <span class="variant-state">${esc(state.text)}</span>
        </div>
        <div class="variant-result-actions">
          <button type="button" class="variant-copy" data-variant-copy="${esc(row.identifier)}">Копіювати</button>
          ${link ? `<a target="_blank" rel="noopener" href="${esc(link)}">${esc(resultActionLabel(row))}</a>` : ''}
        </div>
      </div>`;
    }).join('');
  }

  function ensureModal() {
    let modal = document.getElementById('variantExpansionModal');
    if (modal) return modal;
    modal = document.createElement('div');
    modal.id = 'variantExpansionModal';
    modal.className = 'variant-modal';
    modal.hidden = true;
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-labelledby', 'variantExpansionTitle');
    modal.innerHTML = `
      <div class="variant-modal-card">
        <header class="variant-modal-head">
          <div><strong id="variantExpansionTitle">Розширити пошук</strong><span>Чиста назва завжди перевіряється першою.</span></div>
          <button type="button" class="variant-modal-close" aria-label="Закрити">×</button>
        </header>
        <div class="variant-modal-body">
          <div class="variant-section"><b>Де шукати</b><div id="variantResources" class="variant-resource-list"></div></div>
          <div class="variant-section"><b>Дозволити варіації</b>
            <div class="variant-option-list">
              <label><input type="checkbox" data-variant-option="underscore"> _ underscore</label>
              <label><input type="checkbox" data-variant-option="dots"> крапки</label>
              <label><input type="checkbox" data-variant-option="hyphen"> дефіс</label>
              <label><input type="checkbox" data-variant-option="digits"> цифри</label>
              <label><input type="checkbox" data-variant-option="prefix"> префікс</label>
              <label><input type="checkbox" data-variant-option="suffix"> суфікс</label>
            </div>
            <div class="variant-fields">
              <label data-variant-field="digits">Цифри <input id="variantDigits" autocomplete="off" placeholder="напр. 24, 7"></label>
              <label data-variant-field="prefix">Префікси <input id="variantPrefixes" autocomplete="off" placeholder="напр. go, my"></label>
              <label data-variant-field="suffix">Суфікси <input id="variantSuffixes" autocomplete="off" placeholder="напр. hq, app"></label>
            </div>
            <div id="variantCompatibilityNote" class="variant-note">Опція застосовується лише до платформ, де така форма допустима.</div>
          </div>
          <div class="variant-run-row">
            <button id="variantRunButton" type="button" class="primary">Згенерувати й перевірити</button>
            <span id="variantRunStatus">Нічого не змінюємо без твого вибору.</span>
          </div>
          <div class="variant-results-head"><b>Результат</b><span id="variantExpansionSummary"></span></div>
          <div id="variantExpansionResults" class="variant-results"></div>
        </div>
      </div>`;
    document.body.appendChild(modal);

    modal.querySelector('.variant-modal-close').addEventListener('click', closeModal);
    modal.addEventListener('click', event => { if (event.target === modal) closeModal(); });
    modal.querySelector('#variantRunButton').addEventListener('click', () => { void runExpansion(); });
    modal.addEventListener('change', event => {
      if (event.target.matches('[data-variant-option]')) refreshOptionFields();
      if (event.target.matches('[data-variant-resource]')) refreshCapabilities();
    });
    modal.addEventListener('click', async event => {
      const button = event.target.closest('[data-variant-copy]');
      if (!button) return;
      try {
        await navigator.clipboard.writeText(button.dataset.variantCopy || '');
        button.textContent = 'Скопійовано';
        setTimeout(() => { button.textContent = 'Копіювати'; }, 900);
      } catch (_) {}
    });
    return modal;
  }

  function ensureStyle() {
    if (document.getElementById('variantExpansionStyle')) return;
    const style = document.createElement('style');
    style.id = 'variantExpansionStyle';
    style.textContent = `
      .variant-expand-entry{margin-top:12px;padding-top:11px;border-top:1px solid rgba(255,255,255,.07);display:flex;align-items:center;gap:9px;flex-wrap:wrap;color:var(--muted);font-size:11px}
      .variant-expand-entry button{font-size:12px;padding:8px 10px}.variant-modal[hidden]{display:none!important}.variant-modal{position:fixed;inset:0;z-index:10020;background:rgba(0,0,0,.74);display:grid;place-items:center;padding:16px}
      body.variant-modal-open{overflow:hidden}.variant-modal-card{width:min(820px,100%);max-height:92vh;overflow:hidden;background:var(--panel);border:1px solid var(--line);border-radius:20px;display:grid;grid-template-rows:auto 1fr;box-shadow:0 24px 80px rgba(0,0,0,.5)}
      .variant-modal-head{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:13px 15px;border-bottom:1px solid var(--line);background:var(--panel2)}.variant-modal-head>div{display:grid;gap:2px}.variant-modal-head strong{font-size:15px}.variant-modal-head span{font-size:11px;color:var(--muted)}
      .variant-modal-close{width:38px;height:38px;border-radius:50%;padding:0;font-size:25px;display:grid;place-items:center}.variant-modal-body{overflow:auto;padding:15px;display:grid;gap:15px}.variant-section{display:grid;gap:9px}.variant-section>b,.variant-results-head>b{font-size:12px}.variant-resource-list,.variant-option-list{display:flex;flex-wrap:wrap;gap:7px}.variant-resource-list label,.variant-option-list label{display:flex;gap:6px;align-items:center;border:1px solid var(--line);border-radius:999px;padding:7px 9px;color:var(--muted);font-size:12px}.variant-resource-list label:has(input:checked),.variant-option-list label:has(input:checked){border-color:var(--accent);color:var(--text)}.variant-resource-list label[data-unsupported="true"]{opacity:.45}.variant-resource-list input,.variant-option-list input{accent-color:var(--accent)}
      .variant-fields{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.variant-fields label{display:none;color:var(--muted);font-size:11px;gap:5px}.variant-fields label.open{display:grid}.variant-fields input{min-width:0;background:var(--panel2);border:1px solid var(--line);border-radius:10px;color:var(--text);padding:9px;font:inherit}.variant-note{font-size:11px;color:var(--muted);line-height:1.4}.variant-run-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.variant-run-row span{font-size:12px;color:var(--muted)}.variant-run-row button{font-size:12px}.variant-results-head{display:flex;justify-content:space-between;gap:10px;color:var(--muted);font-size:11px}.variant-results{display:grid;gap:7px}.variant-empty{border:1px dashed var(--line);padding:16px;border-radius:12px;color:var(--muted);font-size:12px;text-align:center}.variant-result{display:flex;justify-content:space-between;gap:10px;align-items:center;border:1px solid var(--line);border-radius:13px;padding:10px;background:var(--panel2)}.variant-result-main{display:grid;grid-template-columns:minmax(70px,auto) minmax(110px,1fr) auto;align-items:center;gap:8px;min-width:0;flex:1}.variant-platform{color:var(--muted);font-size:11px}.variant-result strong{overflow-wrap:anywhere}.variant-state{font-size:11px;text-align:right}.variant-free{border-color:rgba(101,215,122,.55)}.variant-purchase{border-color:rgba(174,116,255,.5)}.variant-likely{border-color:rgba(216,166,76,.45)}.variant-conflict{opacity:.72}.variant-result-actions{display:flex;gap:6px}.variant-result-actions button,.variant-result-actions a{font-size:11px;padding:7px 8px;border:1px solid var(--line);border-radius:9px;background:var(--panel);color:var(--text);text-decoration:none;white-space:nowrap}
      @media(max-width:640px){.variant-modal{padding:0}.variant-modal-card{height:100dvh;max-height:none;border-radius:0;border-left:0;border-right:0}.variant-fields{grid-template-columns:1fr}.variant-result{align-items:flex-start;flex-direction:column}.variant-result-main{width:100%;grid-template-columns:68px 1fr}.variant-state{grid-column:2;text-align:left}.variant-result-actions{width:100%}.variant-result-actions>*{flex:1;text-align:center}}
    `;
    document.head.appendChild(style);
  }

  async function grammar() {
    if (!grammarPromise) {
      grammarPromise = fetch('/api/variant-grammar')
        .then(async response => {
          const payload = await response.json().catch(() => ({}));
          if (!response.ok) throw new Error(payload?.error || ('HTTP ' + response.status));
          return payload;
        })
        .catch(error => {
          grammarPromise = null;
          throw error;
        });
    }
    return grammarPromise;
  }

  function selectedModalResources() {
    return [...document.querySelectorAll('[data-variant-resource]:checked')].map(input => input.value);
  }

  function refreshOptionFields() {
    for (const key of ['digits', 'prefix', 'suffix']) {
      const checked = document.querySelector(`[data-variant-option="${key}"]`)?.checked;
      document.querySelector(`[data-variant-field="${key}"]`)?.classList.toggle('open', Boolean(checked));
    }
  }

  async function refreshCapabilities() {
    const selected = selectedModalResources();
    let payload;
    try { payload = await grammar(); } catch (_) { return; }
    for (const option of ['underscore', 'dots', 'hyphen', 'digits']) {
      const input = document.querySelector(`[data-variant-option="${option}"]`);
      if (!input) continue;
      const supported = selected.some(resource => Boolean(payload?.resources?.[resource]?.supports?.[option]));
      input.disabled = !supported;
      if (!supported) input.checked = false;
      input.closest('label')?.toggleAttribute('data-disabled', !supported);
    }
    refreshOptionFields();
  }

  async function openModal(name) {
    activeName = String(name || '').trim();
    if (!activeName) return;
    ensureStyle();
    const modal = ensureModal();
    modal.querySelector('#variantExpansionTitle').textContent = `Розширити: ${activeName}`;
    const resourcesNode = modal.querySelector('#variantResources');
    const selected = Array.isArray(current?.resources) ? current.resources : [];
    resourcesNode.innerHTML = selected.map(resource => `<label><input type="checkbox" data-variant-resource value="${esc(resource)}" checked>${esc(LABELS[resource] || resource)}</label>`).join('');
    modal.querySelectorAll('[data-variant-option]').forEach(input => { input.checked = false; input.disabled = false; });
    modal.querySelector('#variantDigits').value = '';
    modal.querySelector('#variantPrefixes').value = '';
    modal.querySelector('#variantSuffixes').value = '';
    modal.querySelector('#variantRunStatus').textContent = 'Нічого не змінюємо без твого вибору.';
    refreshOptionFields();
    modal.hidden = false;
    document.body.classList.add('variant-modal-open');
    await refreshCapabilities();
    const saved = savedExpansion(activeName);
    renderResults(saved?.results || [], saved?.results?.length ? `Збережена локальна перевірка · ${saved.results.length} варіантів` : '');
  }

  function closeModal() {
    const modal = document.getElementById('variantExpansionModal');
    if (!modal || running) return;
    modal.hidden = true;
    document.body.classList.remove('variant-modal-open');
    activeName = '';
  }

  function collectOptions() {
    const enabled = key => Boolean(document.querySelector(`[data-variant-option="${key}"]`)?.checked);
    return {
      underscore: enabled('underscore'),
      dots: enabled('dots'),
      hyphen: enabled('hyphen'),
      digits: enabled('digits'),
      prefix: enabled('prefix'),
      suffix: enabled('suffix'),
      number_tokens: parseTokens(document.getElementById('variantDigits')?.value, true),
      prefixes: parseTokens(document.getElementById('variantPrefixes')?.value),
      suffixes: parseTokens(document.getElementById('variantSuffixes')?.value),
    };
  }

  async function generate(options, resources) {
    const response = await fetch('/api/variants', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stem: activeName, resources, options, per_resource_limit: 6 }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload?.error || ('HTTP ' + response.status));
    const rows = [];
    for (const resource of resources) {
      for (const row of payload?.variants?.[resource] || []) rows.push({ ...row, resource });
    }
    return rows.slice(0, MAX_CHECKS);
  }

  async function verifyOne(row) {
    try {
      const response = await fetch('/api/variants/check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resource: row.resource, identifier: row.identifier }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload?.error || ('HTTP ' + response.status));
      return { ...row, ...payload, checked_at: new Date().toISOString() };
    } catch (error) {
      return {
        ...row,
        status: 'unknown',
        strict_free: false,
        purchasable: false,
        availability: { status: 'unknown', detail: error.message || 'verification failed' },
        verification: null,
        checked_at: new Date().toISOString(),
      };
    }
  }

  async function verifyRows(rows) {
    const output = new Array(rows.length);
    let cursor = 0;
    async function worker() {
      while (cursor < rows.length) {
        const index = cursor++;
        output[index] = await verifyOne(rows[index]);
        const done = output.filter(Boolean).length;
        document.getElementById('variantRunStatus').textContent = `Перевіряю ${done}/${rows.length}…`;
        renderResults(output.filter(Boolean), `Перевіряю ${done}/${rows.length}…`);
      }
    }
    await Promise.all(Array.from({ length: Math.min(CHECK_WORKERS, rows.length) }, () => worker()));
    return output.filter(Boolean);
  }

  async function runExpansion() {
    if (running || !activeName) return;
    const resources = selectedModalResources();
    const status = document.getElementById('variantRunStatus');
    const button = document.getElementById('variantRunButton');
    if (!resources.length) {
      status.textContent = 'Обери хоча б одну платформу.';
      return;
    }
    const options = collectOptions();
    const hasMutation = ['underscore', 'dots', 'hyphen', 'digits', 'prefix', 'suffix'].some(key => options[key]);
    if (!hasMutation) {
      status.textContent = 'Обери хоча б один тип варіації.';
      return;
    }
    if (options.digits && !options.number_tokens.length) {
      status.textContent = 'Для цифр введи конкретні числа — NameMachine не вигадує 123 автоматично.';
      return;
    }
    if (options.prefix && !options.prefixes.length) {
      status.textContent = 'Введи конкретний префікс.';
      return;
    }
    if (options.suffix && !options.suffixes.length) {
      status.textContent = 'Введи конкретний суфікс.';
      return;
    }

    running = true;
    button.disabled = true;
    button.textContent = 'Працюю…';
    try {
      status.textContent = 'Будую допустимі варіанти…';
      const generated = await generate(options, resources);
      if (!generated.length) {
        renderResults([], 'Немає допустимих варіантів для вибраних правил.');
        status.textContent = 'Немає допустимих варіантів. Зміни параметри.';
        return;
      }
      status.textContent = `Згенеровано ${generated.length}. Перевіряю реально…`;
      renderResults(generated.map(row => ({ ...row, status: 'unknown' })), `Починаю перевірку ${generated.length}…`);
      const checked = await verifyRows(generated);
      saveExpansion(activeName, {
        parent_name: activeName,
        resources,
        options,
        checked_at: new Date().toISOString(),
        results: checked,
      });
      const free = checked.filter(row => row.status === 'claimable').length;
      status.textContent = free
        ? `Готово. Знайдено 🟢 ${free} підтверджено вільних варіантів.`
        : 'Готово. Підтверджено вільних варіантів у цій спробі немає.';
      renderResults(checked);
    } catch (error) {
      status.textContent = error.message || 'Не вдалося розширити пошук.';
    } finally {
      running = false;
      button.disabled = false;
      button.textContent = 'Згенерувати й перевірити';
    }
  }

  document.addEventListener('click', event => {
    const button = event.target.closest('.variant-expand-open');
    if (!button) return;
    void openModal(button.dataset.variantName);
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !document.getElementById('variantExpansionModal')?.hidden) closeModal();
  });

  ensureStyle();
  ensureModal();
  try { render(); } catch (_) {}

  window.nameMachineVariantExpansion = {
    open: openModal,
    close: closeModal,
    saved: savedExpansion,
  };
})();
