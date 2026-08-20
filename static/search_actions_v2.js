/* NameMachine search actions v2.
 *
 * - zero selected resources means generation-only instead of an error
 * - natural-language "recheck my results" verifies existing names without generating
 * - an explicit Recheck button exposes the same action
 * - repeated foreground starts are guarded synchronously
 * - Fragment marketplace offers are visible without ever becoming strict green
 */
(() => {
  if (window.__nameMachineSearchActionsV2) return;
  window.__nameMachineSearchActionsV2 = true;

  const baseStartSearch = startSearch;
  const baseRender = render;
  const baseCheckLine = checkLine;
  let foregroundBusy = false;
  let recheckBusy = false;

  const clean = (value, limit = 1000) => String(value ?? '').replace(/\s+/g, ' ').trim().slice(0, limit);

  function appendActivity(type, details = {}) {
    if (!current) return;
    if (!Array.isArray(current.activityLog)) current.activityLog = [];
    current.activityLog.push({ at: new Date().toISOString(), type, details });
    if (current.activityLog.length > 600) current.activityLog.splice(0, current.activityLog.length - 600);
  }

  function isIdentityFlow() {
    return String(current?.uiFlow || current?.entryMode || '') === 'identity';
  }

  function isRecheckIntent(prompt) {
    const text = clean(prompt, 1000).toLowerCase();
    return /(перепров|перевір\s*(їх|усі|всі|ще\s*раз)|перевірити\s*(їх|усі|всі)|з\s*(усіх|всіх)\s*результат|recheck|check\s+all\s+results)/iu.test(text);
  }

  function latestNames(limit = 250) {
    const rows = Array.isArray(current?.results) ? current.results : [];
    const ordered = [...rows].sort((a, b) => (Number(b?.received_seq) || 0) - (Number(a?.received_seq) || 0));
    const names = [];
    const seen = new Set();
    for (const row of ordered) {
      const name = clean(row?.name, 64);
      const key = name.toLowerCase();
      if (!name || seen.has(key)) continue;
      seen.add(key);
      names.push(name);
      if (names.length >= limit) break;
    }
    return names;
  }

  async function responseJson(response) {
    let payload = null;
    try { payload = await response.json(); } catch (_) { payload = null; }
    if (!response.ok) {
      const error = new Error(payload?.error || ('HTTP ' + response.status));
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  async function generateOnly() {
    if (foregroundBusy || activeController) return;
    const prompt = clean(document.getElementById('prompt')?.value || '', 1000);
    if (prompt.length < 3) {
      document.getElementById('status').textContent = 'Опиши задачу хоча б кількома словами.';
      return;
    }
    if (!current) current = emptySession();

    foregroundBusy = true;
    stopRequested = false;
    current.resources = [];
    try { write(RESOURCES_KEY, []); } catch (_) {}
    const previous = current.promptHistory?.at?.(-1)?.text || '';
    if (prompt !== previous) {
      current.promptHistory.push({ text: prompt, at: new Date().toISOString(), feedback: typeof feedbackSummary === 'function' ? feedbackSummary() : [], entry_mode: 'generic_name' });
    }
    if (current.title === 'Нова сесія') current.title = prompt.replace(/\s+/g, ' ').slice(0, 48);
    current.batchCounter = (Number(current.batchCounter) || 0) + 1;
    const batchNumber = current.batchCounter;
    const run = {
      id: 'r' + Date.now(),
      prompt,
      entry_mode: 'generic_name',
      generation_only: true,
      started: new Date().toISOString(),
      status: 'running',
      startResultCount: current.results.length,
      startBatch: batchNumber,
    };
    current.runs.push(run);
    appendActivity('generation_only_started', { prompt, reason: 'zero_selected_resources' });

    const start = document.getElementById('startBtn');
    const stop = document.getElementById('stopBtn');
    if (start) start.disabled = true;
    if (stop) stop.disabled = false;
    document.getElementById('status').textContent = '0 ресурсів вибрано — генерую назви без перевірки.';
    activeController = new AbortController();
    saveCurrent();

    try {
      const response = await fetch('/api/generic-names', {
        method: 'POST',
        signal: activeController.signal,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          brief: prompt,
          count: 20,
          preferences: typeof buildPreferences === 'function' ? buildPreferences() : {},
          generation_context: typeof adaptiveContext === 'function' ? adaptiveContext(batchNumber) : { batch_number: batchNumber },
        }),
      });
      const rows = await responseJson(response);
      const seen = new Set((current.results || []).map(row => String(row?.name || '').toLowerCase()));
      let added = 0;
      for (const raw of Array.isArray(rows) ? rows : []) {
        const key = String(raw?.name || '').toLowerCase();
        if (!key || seen.has(key)) continue;
        seen.add(key);
        current.streamCounter = (Number(current.streamCounter) || 0) + 1;
        current.results.push({
          ...raw,
          product_mode: 'generic_name',
          checked: false,
          run_id: run.id,
          batch_number: batchNumber,
          received_seq: current.streamCounter,
          received_at: new Date().toISOString(),
        });
        added += 1;
      }
      run.status = 'complete';
      run.finished = new Date().toISOString();
      run.endResultCount = current.results.length;
      run.endBatch = batchNumber;
      appendActivity('generation_only_complete', { added });
      activeTab = 'feed';
      document.getElementById('status').textContent = `Готово: ${added} нових назв. Вибери ресурси, коли захочеш їх перевірити.`;
    } catch (error) {
      if (error.name === 'AbortError' || stopRequested) {
        run.status = 'paused';
        document.getElementById('status').textContent = 'Генерацію зупинено.';
      } else {
        run.status = 'error';
        appendActivity('generation_only_error', { message: error.message || 'unknown' });
        document.getElementById('status').textContent = error.message || 'Не вдалося згенерувати назви.';
      }
    } finally {
      activeController = null;
      foregroundBusy = false;
      saveCurrent();
      render();
      if (stop) stop.disabled = true;
      if (start) {
        start.disabled = false;
        start.textContent = 'Ще варіанти';
      }
    }
  }

  async function recheckExisting({ explicit = false } = {}) {
    if (recheckBusy || foregroundBusy || activeController) return;
    const resources = typeof selectedResources === 'function' ? selectedResources() : [];
    const names = latestNames(250);
    if (!names.length) {
      document.getElementById('status').textContent = 'Ще немає назв для переперевірки.';
      return;
    }
    if (!resources.length) {
      document.getElementById('status').textContent = 'Для переперевірки вибери хоча б один ресурс.';
      return;
    }

    recheckBusy = true;
    foregroundBusy = true;
    stopRequested = false;
    activeController = new AbortController();
    current.resources = [...resources];
    try { write(RESOURCES_KEY, resources); } catch (_) {}
    const start = document.getElementById('startBtn');
    const stop = document.getElementById('stopBtn');
    if (start) start.disabled = true;
    if (stop) stop.disabled = false;
    appendActivity('recheck_existing_started', { names: names.length, resources: [...resources], explicit });
    document.getElementById('status').textContent = `Перепровіряю ${names.length} існуючих назв · нові назви не генеруються…`;

    try {
      const response = await fetch('/api/recheck', {
        method: 'POST',
        signal: activeController.signal,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ names, resources, required_resources: resources }),
      });
      const payload = await responseJson(response);
      const byName = new Map((current.results || []).map(row => [String(row?.name || '').toLowerCase(), row]));
      let updated = 0;
      for (const fresh of Array.isArray(payload?.rows) ? payload.rows : []) {
        const existing = byName.get(String(fresh?.name || '').toLowerCase());
        if (!existing) continue;
        const preserve = {
          reason: existing.reason,
          family: existing.family,
          run_id: existing.run_id,
          batch_number: existing.batch_number,
          received_seq: existing.received_seq,
          received_at: existing.received_at,
          product_mode: existing.product_mode,
          entry_mode: existing.entry_mode,
        };
        Object.assign(existing, fresh, preserve);
        existing.checked = true;
        updated += 1;
      }
      appendActivity('recheck_existing_complete', { updated, resources: [...resources] });
      saveCurrent();
      if (typeof window.nameMachineSyncAllCandidates === 'function') window.nameMachineSyncAllCandidates();
      activeTab = 'feed';
      render();
      document.getElementById('status').textContent = `Переперевірено ${updated} назв. Дивись кожен канал окремо: зелений = claimable, жовтий = не знайдено, фіолетовий = можна купити.`;
    } catch (error) {
      if (error.name === 'AbortError' || stopRequested) {
        document.getElementById('status').textContent = 'Переперевірку зупинено.';
      } else {
        appendActivity('recheck_existing_error', { message: error.message || 'unknown' });
        document.getElementById('status').textContent = error.message || 'Не вдалося переперевірити результати.';
      }
    } finally {
      activeController = null;
      recheckBusy = false;
      foregroundBusy = false;
      if (stop) stop.disabled = true;
      if (start) start.disabled = false;
      updateRecheckButton();
    }
  }

  function offerText(result) {
    const offer = result?.offer;
    if (!offer || String(offer.provider || '').toLowerCase() !== 'fragment') return '';
    const pick = [
      ['current_bid_ton', 'поточна ставка'],
      ['minimum_bid_ton', 'від'],
      ['price_ton', 'ціна'],
      ['sold_price_ton', 'продано за'],
    ].find(([key]) => offer[key] !== undefined && offer[key] !== null && offer[key] !== '');
    if (!pick) return 'Fragment';
    return `Fragment · ${pick[1]} ${pick[0] === 'current_bid_ton' ? offer.current_bid_ton : offer[pick[0]]} TON`;
  }

  checkLine = function checkLineWithMarketplace(name, key, result) {
    const html = baseCheckLine(name, key, result);
    if (key !== 'telegram') return html;
    const marketplace = offerText(result);
    if (!marketplace) return html;
    return html.replace('</div>', `<span class="nm-fragment-offer">${esc(marketplace)}</span></div>`);
  };

  function ensureRecheckButton() {
    if (document.getElementById('nmRecheckResults')) return;
    const resources = document.querySelector('.resources');
    if (!resources) return;
    const row = document.createElement('div');
    row.className = 'nm-recheck-row';
    row.innerHTML = '<button type="button" id="nmRecheckResults">↻ Перепровірити результати</button><span>Без нової генерації</span>';
    resources.insertAdjacentElement('afterend', row);
    row.querySelector('#nmRecheckResults').addEventListener('click', () => { void recheckExisting({ explicit: true }); });
  }

  function updateRecheckButton() {
    ensureRecheckButton();
    const button = document.getElementById('nmRecheckResults');
    if (!button) return;
    const hasRows = Boolean(current?.results?.length);
    const hasResources = Boolean(typeof selectedResources === 'function' && selectedResources().length);
    button.disabled = recheckBusy || !hasRows || !hasResources;
    button.textContent = recheckBusy ? 'Перепровіряю…' : '↻ Перепровірити результати';
  }

  render = function renderSearchActionsV2() {
    baseRender();
    updateRecheckButton();
  };

  startSearch = async function startSearchActionsV2() {
    if (foregroundBusy || activeController) return;
    const prompt = clean(document.getElementById('prompt')?.value || '', 1000);
    const resources = typeof selectedResources === 'function' ? selectedResources() : [];
    if (current?.results?.length && resources.length && isRecheckIntent(prompt)) {
      return recheckExisting({ explicit: false });
    }
    if (!resources.length && !isIdentityFlow()) {
      return generateOnly();
    }
    foregroundBusy = true;
    try {
      return await baseStartSearch();
    } finally {
      foregroundBusy = false;
      updateRecheckButton();
    }
  };

  if (!document.getElementById('nmSearchActionsV2Style')) {
    const style = document.createElement('style');
    style.id = 'nmSearchActionsV2Style';
    style.textContent = `
      .nm-recheck-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:10px 0 0}.nm-recheck-row span{font-size:11px;color:var(--muted)}
      #nmRecheckResults{font-size:12px;padding:8px 11px}.nm-fragment-offer{margin-left:auto;color:#c7a9ff;font-size:11px;font-weight:700;white-space:nowrap}
      @media(max-width:640px){.nm-fragment-offer{width:100%;margin-left:17px}.nm-recheck-row{justify-content:space-between}}
    `;
    document.head.appendChild(style);
  }

  ensureRecheckButton();
  updateRecheckButton();
  try { render(); } catch (_) {}
  window.nameMachineRecheckExisting = recheckExisting;
})();
