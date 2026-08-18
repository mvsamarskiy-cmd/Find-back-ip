/* Durable large-search UI.
 *
 * Hidden unless both durable storage and a live background worker are present.
 * Long jobs run server-side; this client polls job metadata and pulls only new
 * candidate rows by received_seq, so closing the browser does not cancel work.
 */
(() => {
  const CAPABILITY_POLL_MS = 15000;
  const JOB_POLL_MS = 2500;
  const FEED_PAGE = 100;
  const activeStates = new Set(['pending', 'running', 'cancel_requested']);
  let capability = null;
  let activeJob = null;
  let capabilityTimer = null;
  let jobTimer = null;
  let polling = false;
  let knownSessionId = null;
  let candidateCursor = 0;

  const credentials = () => current?.serverSession || null;
  const headers = () => {
    const token = credentials()?.token;
    return token ? { 'X-NameMachine-Session-Token': token } : {};
  };

  function maxLocalSeq() {
    return Math.max(0, ...(current?.results || []).map(row => Number(row?.received_seq) || 0));
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: {
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...headers(),
        ...(options.headers || {}),
      },
    });
    let payload = null;
    try { payload = await response.json(); } catch (_) { payload = null; }
    if (!response.ok) {
      const error = new Error(payload?.error || ('HTTP ' + response.status));
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  function injectStyle() {
    if (document.getElementById('backgroundSearchStyle')) return;
    const style = document.createElement('style');
    style.id = 'backgroundSearchStyle';
    style.textContent = `
      .large-search{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:12px;padding-top:12px;border-top:1px solid var(--line);color:var(--muted);font-size:12px}
      .large-search strong{color:var(--text)}
      .large-search select{background:var(--panel2);color:var(--text);border:1px solid var(--line);border-radius:10px;padding:8px 9px;font:inherit}
      .large-search button{font-size:12px;padding:8px 10px}
      .large-search-status{margin-left:auto}
      @media(max-width:640px){.large-search{display:grid;grid-template-columns:auto 1fr auto}.large-search-status{grid-column:1/-1;margin-left:0}}
    `;
    document.head.appendChild(style);
  }

  function ensurePanel() {
    let panel = document.getElementById('largeSearchPanel');
    if (panel) return panel;
    const composer = document.querySelector('.composer');
    const runbar = composer?.querySelector('.runbar');
    if (!composer || !runbar) return null;
    injectStyle();
    panel = document.createElement('div');
    panel.id = 'largeSearchPanel';
    panel.className = 'large-search';
    panel.hidden = true;
    panel.innerHTML = `
      <strong>Великий пошук</strong>
      <select id="largeSearchTarget" aria-label="Кількість кандидатів">
        <option value="500">500</option>
        <option value="1000">1 000</option>
        <option value="5000">5 000</option>
        <option value="20000">20 000</option>
      </select>
      <button id="largeSearchStart" type="button">Запустити</button>
      <button id="largeSearchCancel" class="danger" type="button" hidden>Зупинити</button>
      <span id="largeSearchStatus" class="large-search-status">Працює у фоні навіть після закриття сторінки.</span>`;
    runbar.insertAdjacentElement('afterend', panel);
    panel.querySelector('#largeSearchStart').addEventListener('click', () => { void startLargeSearch(); });
    panel.querySelector('#largeSearchCancel').addEventListener('click', () => { void cancelLargeSearch(); });
    return panel;
  }

  function setPanelState() {
    const panel = ensurePanel();
    if (!panel) return;
    const creds = credentials();
    const hasActive = Boolean(activeJob && activeStates.has(activeJob.state));
    panel.hidden = !(hasActive || (capability?.ready && creds?.id && creds?.token));
    if (panel.hidden) return;

    const start = panel.querySelector('#largeSearchStart');
    const cancel = panel.querySelector('#largeSearchCancel');
    const target = panel.querySelector('#largeSearchTarget');
    const status = panel.querySelector('#largeSearchStatus');
    start.disabled = hasActive;
    target.disabled = hasActive;
    cancel.hidden = !hasActive;

    if (activeJob) {
      const delivered = Number(activeJob.delivered_count) || 0;
      const total = Number(activeJob.target_count) || 0;
      const stateText = activeJob.state === 'pending'
        ? 'у черзі'
        : activeJob.state === 'cancel_requested'
          ? 'зупиняю'
          : activeJob.state === 'running'
            ? 'працює'
            : activeJob.state === 'completed'
              ? 'завершено'
              : activeJob.state === 'cancelled'
                ? 'зупинено'
                : 'помилка';
      status.textContent = `Фоновий пошук: ${stateText} · ${delivered}/${total}`;
    } else {
      status.textContent = 'Працює у фоні навіть після закриття сторінки.';
    }
  }

  function resetForSessionIfNeeded() {
    const id = credentials()?.id || null;
    if (id === knownSessionId) return;
    knownSessionId = id;
    activeJob = null;
    candidateCursor = maxLocalSeq();
    if (jobTimer) clearTimeout(jobTimer);
    jobTimer = null;
  }

  function mergeCandidateRows(rows) {
    if (!Array.isArray(rows) || !rows.length) return 0;
    const byName = new Map((current?.results || []).map(row => [String(row?.name || '').toLowerCase(), row]));
    let changed = 0;
    for (const incoming of rows) {
      if (!incoming || typeof incoming !== 'object') continue;
      const key = String(incoming.name || '').toLowerCase();
      if (!key) continue;
      const existing = byName.get(key);
      if (!existing) {
        current.results.push(incoming);
        byName.set(key, incoming);
        changed += 1;
      } else if (Number(incoming.received_seq) >= Number(existing.received_seq || 0)) {
        Object.assign(existing, incoming);
        changed += 1;
      }
      candidateCursor = Math.max(candidateCursor, Number(incoming.received_seq) || 0);
      current.streamCounter = Math.max(Number(current.streamCounter) || 0, Number(incoming.received_seq) || 0);
    }
    if (changed) {
      current.updated = new Date().toISOString();
      write(SESSION_KEY, current); // remote-origin data: avoid echoing it back through durable sync
      render();
    }
    return changed;
  }

  async function pullCandidateDelta() {
    const creds = credentials();
    if (!creds?.id || !creds?.token) return 0;
    let total = 0;
    let loops = 0;
    while (loops < 10) {
      loops += 1;
      const payload = await api(
        '/api/sessions/' + encodeURIComponent(creds.id) +
        '/candidate-feed?after_seq=' + encodeURIComponent(candidateCursor) +
        '&limit=' + FEED_PAGE,
      );
      total += mergeCandidateRows(payload?.candidates || []);
      const next = Number(payload?.next_after_seq) || candidateCursor;
      candidateCursor = Math.max(candidateCursor, next);
      if (!payload?.has_more) break;
    }
    return total;
  }

  async function discoverJob() {
    const creds = credentials();
    if (!creds?.id || !creds?.token || !capability?.enabled) return;
    if (activeJob?.id) return;
    const payload = await api('/api/sessions/' + encodeURIComponent(creds.id) + '/search-jobs?limit=10');
    const jobs = Array.isArray(payload?.jobs) ? payload.jobs : [];
    activeJob = jobs.find(job => activeStates.has(job?.state)) || null;
  }

  async function pollJob() {
    if (polling) return;
    polling = true;
    try {
      resetForSessionIfNeeded();
      const creds = credentials();
      if (!creds?.id || !creds?.token || !capability?.enabled) return;
      await discoverJob();
      if (!activeJob?.id) {
        setPanelState();
        return;
      }
      const payload = await api(
        '/api/sessions/' + encodeURIComponent(creds.id) + '/search-jobs/' + encodeURIComponent(activeJob.id),
      );
      activeJob = payload?.job || activeJob;
      await pullCandidateDelta();
      setPanelState();
    } catch (error) {
      if (error.status === 404) activeJob = null;
    } finally {
      polling = false;
      if (activeJob && activeStates.has(activeJob.state)) {
        jobTimer = setTimeout(() => { void pollJob(); }, JOB_POLL_MS);
      } else {
        jobTimer = null;
      }
    }
  }

  async function refreshCapability() {
    try {
      resetForSessionIfNeeded();
      capability = await api('/api/background-search');
      setPanelState();
      if (capability?.enabled && credentials()?.id) void pollJob();
    } catch (_) {
      capability = null;
      setPanelState();
    } finally {
      clearTimeout(capabilityTimer);
      capabilityTimer = setTimeout(() => { void refreshCapability(); }, CAPABILITY_POLL_MS);
    }
  }

  async function startLargeSearch() {
    const creds = credentials();
    const prompt = document.getElementById('prompt')?.value?.trim() || '';
    const resources = selectedResources();
    if (!capability?.ready || !creds?.id || !creds?.token) {
      document.getElementById('status').textContent = 'Фоновий worker або серверне сховище ще не готові.';
      return;
    }
    if (prompt.length < 3 || !resources.length) {
      document.getElementById('status').textContent = prompt.length < 3
        ? 'Опиши задачу хоча б кількома словами.'
        : 'Обери хоча б один ресурс.';
      return;
    }
    const target = Number(document.getElementById('largeSearchTarget')?.value) || 500;
    document.getElementById('largeSearchStart').disabled = true;
    try {
      const payload = await api('/api/sessions/' + encodeURIComponent(creds.id) + '/search-jobs', {
        method: 'POST',
        body: JSON.stringify({
          brief: prompt,
          resources,
          required_resources: resources,
          preferences: buildPreferences(),
          search_context: {
            mode: 'new_brand',
            brand_name: '',
            guidance: current?.directionAnchors?.length
              ? 'Орієнтуйся на: ' + current.directionAnchors.slice(-5).join(', ')
              : '',
          },
          brand_dna: null,
          generation_context: adaptiveContext((Number(current?.batchCounter) || 0) + 1),
          target_count: target,
          batch_size: 20,
        }),
      });
      activeJob = payload?.job || null;
      current.backgroundSearch = activeJob ? { id: activeJob.id, started_at: new Date().toISOString() } : null;
      current.updated = new Date().toISOString();
      write(SESSION_KEY, current);
      setPanelState();
      document.getElementById('status').textContent = `Великий пошук запущено: ціль ${target}. Можна закрити сторінку.`;
      void pollJob();
    } catch (error) {
      document.getElementById('status').textContent = error.message || 'Не вдалося запустити великий пошук.';
      setPanelState();
    }
  }

  async function cancelLargeSearch() {
    const creds = credentials();
    if (!creds?.id || !activeJob?.id) return;
    try {
      const payload = await api(
        '/api/sessions/' + encodeURIComponent(creds.id) + '/search-jobs/' + encodeURIComponent(activeJob.id) + '/cancel',
        { method: 'POST' },
      );
      activeJob = payload?.job || activeJob;
      setPanelState();
      void pollJob();
    } catch (error) {
      document.getElementById('status').textContent = error.message || 'Не вдалося зупинити великий пошук.';
    }
  }

  candidateCursor = maxLocalSeq();
  ensurePanel();
  void refreshCapability();
})();
