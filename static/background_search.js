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
  const ACTIVITY_LIMIT = 600;
  const activeStates = new Set(['pending', 'running', 'cancel_requested']);
  let capability = null;
  let activeJob = null;
  let capabilityTimer = null;
  let jobTimer = null;
  let polling = false;
  let knownSessionId = null;
  let candidateCursor = 0;
  let lastJobEventKey = '';
  let lastRuntimeAppliedAt = '';
  let promptAuditTimer = null;

  const credentials = () => current?.serverSession || null;
  const headers = () => {
    const token = credentials()?.token;
    return token ? { 'X-NameMachine-Session-Token': token } : {};
  };

  function maxLocalSeq() {
    return Math.max(0, ...(current?.results || []).map(row => Number(row?.received_seq) || 0));
  }

  function ensureActivityLog() {
    if (!current) return [];
    if (!Array.isArray(current.activityLog)) current.activityLog = [];
    return current.activityLog;
  }

  function recordActivity(type, details = {}) {
    if (!current) return;
    const log = ensureActivityLog();
    log.push({
      at: new Date().toISOString(),
      type,
      job_id: activeJob?.id || current?.backgroundSearch?.id || null,
      details,
    });
    if (log.length > ACTIVITY_LIMIT) log.splice(0, log.length - ACTIVITY_LIMIT);
    current.updated = new Date().toISOString();
    write(SESSION_KEY, current);
  }

  function formatDuration(ms) {
    const total = Math.max(0, Math.floor(Number(ms || 0) / 1000));
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const seconds = total % 60;
    return (hours ? String(hours).padStart(2, '0') + ':' : '') +
      String(minutes).padStart(2, '0') + ':' + String(seconds).padStart(2, '0');
  }

  function jobElapsedMs(job = activeJob) {
    if (!job) return 0;
    const started = Date.parse(job.started_at || job.created_at || current?.backgroundSearch?.started_at || '');
    if (!Number.isFinite(started)) return 0;
    const finished = Date.parse(job.finished_at || '');
    return (Number.isFinite(finished) ? finished : Date.now()) - started;
  }

  function jobRows(job = activeJob) {
    const rows = Array.isArray(current?.results) ? current.results : [];
    if (!job?.run_id) return rows;
    return rows.filter(row => row?.run_id === job.run_id);
  }

  function liveCounts(job = activeJob) {
    const rows = jobRows(job);
    const counts = { total: rows.length, green: 0, promising: 0, conflict: 0, unresolved: 0 };
    for (const row of rows) {
      if (allGreen(row)) counts.green += 1;
      else if (row?.bundle_state === 'promising') counts.promising += 1;
      else if (hasConflict(row) || row?.bundle_state === 'conflict') counts.conflict += 1;
      else counts.unresolved += 1;
    }
    return counts;
  }

  function latestUserFeedbackEvent() {
    const log = ensureActivityLog();
    for (let index = log.length - 1; index >= 0; index -= 1) {
      if (['feedback_change', 'comment_change', 'shortlist_change', 'direction_change'].includes(log[index]?.type)) {
        return log[index];
      }
    }
    return null;
  }

  function workerRuntime(job = activeJob) {
    const preferences = job?.preferences;
    return preferences && typeof preferences === 'object' && preferences._runtime && typeof preferences._runtime === 'object'
      ? preferences._runtime
      : null;
  }

  function feedbackReactionText(job = activeJob) {
    const event = latestUserFeedbackEvent();
    if (!event) return 'Фідбек: змін під час цього сеансу ще не було.';
    const runtime = workerRuntime(job);
    if (!runtime?.applied_at) return 'Фідбек: зміну записано, worker ще не підтвердив читання.';
    const eventAt = Date.parse(event.at || '');
    const appliedAt = Date.parse(runtime.applied_at || '');
    if (Number.isFinite(eventAt) && Number.isFinite(appliedAt) && appliedAt >= eventAt) {
      return `Фідбек: worker зчитав зміни · партія ${runtime.applied_batch || '?'} · ${runtime.feedback_count || 0} сигналів.`;
    }
    return 'Фідбек: зміна новіша за останній snapshot worker; очікує наступну партію.';
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
      .large-search-telemetry{display:grid;grid-template-columns:repeat(5,minmax(0,auto));gap:7px 12px;width:100%;padding:10px 12px;background:var(--panel2);border:1px solid var(--line);border-radius:12px}
      .large-search-telemetry b{color:var(--text)}
      .large-search-telemetry .telemetry-wide{grid-column:1/-1;white-space:normal;overflow-wrap:anywhere}
      .telemetry-green{color:var(--ok)}.telemetry-warn{color:var(--warn)}.telemetry-bad{color:var(--bad)}
      @media(max-width:640px){.large-search{display:grid;grid-template-columns:auto 1fr auto}.large-search-status{grid-column:1/-1;margin-left:0}.large-search-telemetry{grid-column:1/-1;grid-template-columns:repeat(2,minmax(0,1fr))}.large-search-telemetry .telemetry-wide{grid-column:1/-1}}
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
      <span id="largeSearchStatus" class="large-search-status">Працює у фоні навіть після закриття сторінки.</span>
      <div id="largeSearchTelemetry" class="large-search-telemetry" hidden>
        <span>⏱ <b id="largeSearchClock">00:00</b></span>
        <span>Партія <b id="largeSearchBatch">—</b></span>
        <span class="telemetry-green">Зелені <b id="largeSearchGreen">0</b></span>
        <span class="telemetry-warn">Перспективні <b id="largeSearchPromising">0</b></span>
        <span class="telemetry-bad">Конфлікти <b id="largeSearchConflicts">0</b></span>
        <span id="largeSearchLatest" class="telemetry-wide">Нові назви ще не надійшли.</span>
        <span id="largeSearchFeedback" class="telemetry-wide">Фідбек: очікую дані.</span>
      </div>`;
    runbar.insertAdjacentElement('afterend', panel);
    panel.querySelector('#largeSearchStart').addEventListener('click', () => { void startLargeSearch(); });
    panel.querySelector('#largeSearchCancel').addEventListener('click', () => { void cancelLargeSearch(); });
    return panel;
  }

  function updateTelemetry() {
    const panel = ensurePanel();
    const telemetry = panel?.querySelector('#largeSearchTelemetry');
    if (!telemetry) return;
    telemetry.hidden = !activeJob;
    if (!activeJob) return;
    const counts = liveCounts();
    const rows = jobRows();
    const latestNames = [...rows]
      .sort((a, b) => (Number(b?.received_seq) || 0) - (Number(a?.received_seq) || 0))
      .slice(0, 5)
      .map(row => row.name)
      .filter(Boolean);
    const runtime = workerRuntime();
    panel.querySelector('#largeSearchClock').textContent = formatDuration(jobElapsedMs());
    panel.querySelector('#largeSearchBatch').textContent = String(activeJob.attempted_batches || runtime?.applied_batch || '—');
    panel.querySelector('#largeSearchGreen').textContent = String(counts.green);
    panel.querySelector('#largeSearchPromising').textContent = String(counts.promising);
    panel.querySelector('#largeSearchConflicts').textContent = String(counts.conflict);
    panel.querySelector('#largeSearchLatest').textContent = latestNames.length
      ? 'Останні: ' + latestNames.join(' · ')
      : 'Нові назви ще не надійшли.';
    panel.querySelector('#largeSearchFeedback').textContent = feedbackReactionText();
  }

  function noteJobTransition() {
    if (!activeJob) return;
    const key = [activeJob.state, activeJob.delivered_count, activeJob.attempted_batches, activeJob.stop_reason].join('|');
    if (key !== lastJobEventKey) {
      lastJobEventKey = key;
      recordActivity('job_progress', {
        state: activeJob.state,
        delivered: Number(activeJob.delivered_count) || 0,
        target: Number(activeJob.target_count) || 0,
        attempted_batches: Number(activeJob.attempted_batches) || 0,
        max_batches: Number(activeJob.max_batches) || 0,
        stop_reason: activeJob.stop_reason || '',
        error_type: activeJob.error_type || '',
        error_message: activeJob.error_message || '',
      });
    }
    const runtime = workerRuntime();
    if (runtime?.applied_at && runtime.applied_at !== lastRuntimeAppliedAt) {
      lastRuntimeAppliedAt = runtime.applied_at;
      recordActivity('worker_feedback_applied', { ...runtime });
    }
  }

  function setPanelState() {
    const panel = ensurePanel();
    if (!panel) return;
    const creds = credentials();
    const hasActive = Boolean(activeJob && activeStates.has(activeJob.state));
    panel.hidden = !(activeJob || (capability?.ready && creds?.id && creds?.token));
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
      const reason = activeJob.stop_reason ? ` · причина: ${activeJob.stop_reason}` : '';
      status.textContent = `Фоновий пошук: ${stateText} · ${delivered}/${total}${reason}`;
      noteJobTransition();
    } else {
      status.textContent = 'Працює у фоні навіть після закриття сторінки.';
    }
    updateTelemetry();
  }

  function resetForSessionIfNeeded() {
    const id = credentials()?.id || null;
    if (id === knownSessionId) return;
    knownSessionId = id;
    activeJob = null;
    candidateCursor = maxLocalSeq();
    lastJobEventKey = '';
    lastRuntimeAppliedAt = '';
    if (jobTimer) clearTimeout(jobTimer);
    jobTimer = null;
  }

  function mergeCandidateRows(rows) {
    if (!Array.isArray(rows) || !rows.length) return 0;
    const byName = new Map((current?.results || []).map(row => [String(row?.name || '').toLowerCase(), row]));
    let changed = 0;
    const addedNames = [];
    for (const incoming of rows) {
      if (!incoming || typeof incoming !== 'object') continue;
      const key = String(incoming.name || '').toLowerCase();
      if (!key) continue;
      const existing = byName.get(key);
      if (!existing) {
        current.results.push(incoming);
        byName.set(key, incoming);
        changed += 1;
        addedNames.push(incoming.name);
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
      if (addedNames.length) {
        const counts = liveCounts();
        recordActivity('candidate_batch', {
          added: addedNames.length,
          names: addedNames,
          green: counts.green,
          promising: counts.promising,
          conflicts: counts.conflict,
        });
      }
      updateTelemetry();
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
    activeJob = jobs.find(job => activeStates.has(job?.state)) || jobs[0] || null;
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
      recordActivity('job_poll_error', { message: error.message || 'unknown', status: error.status || null });
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
      current.backgroundSearch = activeJob ? {
        id: activeJob.id,
        run_id: activeJob.run_id,
        target_count: target,
        started_at: new Date().toISOString(),
      } : null;
      current.updated = new Date().toISOString();
      write(SESSION_KEY, current);
      recordActivity('job_started', {
        id: activeJob?.id || null,
        run_id: activeJob?.run_id || null,
        target,
        resources: [...resources],
        prompt,
      });
      setPanelState();
      document.getElementById('status').textContent = `Великий пошук запущено: ціль ${target}. Можна закрити сторінку.`;
      void pollJob();
    } catch (error) {
      recordActivity('job_start_error', { message: error.message || 'unknown' });
      document.getElementById('status').textContent = error.message || 'Не вдалося запустити великий пошук.';
      setPanelState();
    }
  }

  async function cancelLargeSearch() {
    const creds = credentials();
    if (!creds?.id || !activeJob?.id) return;
    try {
      recordActivity('cancel_requested', { delivered: activeJob.delivered_count || 0 });
      const payload = await api(
        '/api/sessions/' + encodeURIComponent(creds.id) + '/search-jobs/' + encodeURIComponent(activeJob.id) + '/cancel',
        { method: 'POST' },
      );
      activeJob = payload?.job || activeJob;
      setPanelState();
      void pollJob();
    } catch (error) {
      recordActivity('cancel_error', { message: error.message || 'unknown' });
      document.getElementById('status').textContent = error.message || 'Не вдалося зупинити великий пошук.';
    }
  }

  function auditUserActions() {
    document.addEventListener('click', event => {
      const button = event.target?.closest?.('button[data-name]');
      if (!button) return;
      const name = button.dataset.name || '';
      const classes = button.classList;
      if (!(classes.contains('like') || classes.contains('dislike') || classes.contains('save-comment') ||
        classes.contains('shortlist-btn') || classes.contains('direction-btn'))) return;
      setTimeout(() => {
        if (classes.contains('like') || classes.contains('dislike')) {
          const fb = sessionFeedback(name);
          recordActivity('feedback_change', { name, vote: fb.vote || 0, comment: fb.comment || '', effect: 'next_background_batch' });
        } else if (classes.contains('save-comment')) {
          const fb = sessionFeedback(name);
          recordActivity('comment_change', { name, vote: fb.vote || 0, comment: fb.comment || '', effect: 'next_background_batch' });
        } else if (classes.contains('shortlist-btn')) {
          recordActivity('shortlist_change', { name, selected: current.shortlist.includes(name), effect: 'next_background_batch' });
        } else if (classes.contains('direction-btn')) {
          recordActivity('direction_change', { name, selected: current.directionAnchors.includes(name), effect: 'next_background_batch' });
        }
        updateTelemetry();
      }, 0);
    });

    document.querySelectorAll('input[name="resource"]').forEach(input => {
      input.addEventListener('change', () => {
        recordActivity('resource_change', {
          resources: selectedResources(),
          effect: activeJob && activeStates.has(activeJob.state) ? 'next_run' : 'immediate_next_start',
        });
      });
    });

    const prompt = document.getElementById('prompt');
    prompt?.addEventListener('input', () => {
      clearTimeout(promptAuditTimer);
      promptAuditTimer = setTimeout(() => {
        recordActivity('prompt_change', {
          prompt: prompt.value.trim().slice(0, 500),
          effect: activeJob && activeStates.has(activeJob.state) ? 'next_run' : 'immediate_next_start',
        });
      }, 900);
    });
  }

  function rawStatus(row, resource) {
    const payload = row?.availability?.[resource];
    return String(payload?.status || 'unknown');
  }

  function reportLineForCandidate(row) {
    const feedback = sessionFeedback(row.name);
    const parts = [
      `- ${row.name}`,
      `seq=${row.received_seq || '?'}`,
      `batch=${row.batch_number || '?'}`,
      `bundle=${row.bundle_state || 'unknown'}`,
      `score=${Number.isFinite(Number(row.bundle_score)) ? Number(row.bundle_score) : 0}`,
      `received=${row.received_at || '?'}`,
    ];
    if (feedback.vote || feedback.comment) {
      parts.push(`feedback=${feedback.vote === 1 ? 'LIKE' : feedback.vote === -1 ? 'DISLIKE' : 'NO VOTE'}${feedback.comment ? ':' + feedback.comment : ''}`);
    }
    return parts.join(' | ');
  }

  function extendedSessionTxt() {
    const lines = [
      'NameMachine LIVE AUDIT REPORT',
      '',
      `Назва: ${current?.title || 'Нова сесія'}`,
      `Session ID: ${current?.id || '?'}`,
      `Створено: ${current?.created || '?'}`,
      `Звіт сформовано: ${new Date().toISOString()}`,
      '',
      'SEARCH STATE',
    ];

    if (activeJob) {
      const counts = liveCounts(activeJob);
      const runtime = workerRuntime(activeJob) || {};
      lines.push(
        `- Background job: ${activeJob.id}`,
        `- Run ID: ${activeJob.run_id || '?'}`,
        `- State: ${activeJob.state || 'unknown'}`,
        `- Progress: ${activeJob.delivered_count || 0}/${activeJob.target_count || 0}`,
        `- Batches: ${activeJob.attempted_batches || 0}/${activeJob.max_batches || '?'}`,
        `- Stop reason: ${activeJob.stop_reason || '—'}`,
        `- Error: ${activeJob.error_type || '—'}${activeJob.error_message ? ' · ' + activeJob.error_message : ''}`,
        `- Elapsed: ${formatDuration(jobElapsedMs(activeJob))}`,
        `- Green: ${counts.green}`,
        `- Promising: ${counts.promising}`,
        `- Conflicts: ${counts.conflict}`,
        `- Unresolved: ${counts.unresolved}`,
        `- Worker feedback snapshot: batch=${runtime.applied_batch || '?'} applied_at=${runtime.applied_at || '—'} signals=${runtime.feedback_count || 0} conflicts_learned=${runtime.conflict_examples || 0} opportunities_learned=${runtime.opportunity_examples || 0}`,
      );
    } else {
      lines.push('- Background job: no job discovered in this browser state.');
    }

    lines.push('', 'PROMPT HISTORY');
    (current?.promptHistory || []).forEach((entry, index) => {
      lines.push(`${index + 1}. ${entry.text || ''} | at=${entry.at || '?'}`);
    });

    lines.push('', 'RESOURCES', (current?.resources || []).map(key => labels[key] || key).join(', '));
    lines.push('', 'USER FEEDBACK');
    const feedbackEntries = Object.entries(current?.feedback || {}).filter(([, value]) => value?.vote || value?.comment);
    if (!feedbackEntries.length) lines.push('- none');
    for (const [name, value] of feedbackEntries) {
      lines.push(`- ${name}: ${value.vote === 1 ? 'LIKE' : value.vote === -1 ? 'DISLIKE' : 'NO VOTE'}${value.comment ? ' · ' + value.comment : ''}`);
    }

    lines.push('', 'ACTION / REACTION TIMELINE');
    const activity = ensureActivityLog();
    if (!activity.length) lines.push('- no recorded live events');
    const baseAt = Date.parse(activeJob?.started_at || activeJob?.created_at || current?.backgroundSearch?.started_at || current?.created || '');
    for (const event of activity) {
      const eventAt = Date.parse(event.at || '');
      const elapsed = Number.isFinite(baseAt) && Number.isFinite(eventAt) ? formatDuration(eventAt - baseAt) : '?';
      lines.push(`- +${elapsed} | ${event.at || '?'} | ${event.type} | ${JSON.stringify(event.details || {})}`);
    }

    lines.push('', 'CANDIDATE LEDGER');
    const ordered = [...(current?.results || [])].sort((a, b) => (Number(b?.received_seq) || 0) - (Number(a?.received_seq) || 0));
    if (!ordered.length) lines.push('- none');
    for (const row of ordered) {
      lines.push(reportLineForCandidate(row));
      for (const resource of current?.resources || []) {
        const payload = row?.availability?.[resource] || {};
        const confidence = payload.confidence == null ? '?' : payload.confidence;
        lines.push(
          `    ${labels[resource] || resource}: ui=${uiState(payload).label} raw=${rawStatus(row, resource)} source=${payload.source || '?'} method=${payload.method || '?'} confidence=${confidence} detail=${String(payload.detail || '').replace(/\s+/g, ' ').slice(0, 240)}`,
        );
      }
    }

    lines.push('', 'LEGACY FOREGROUND RUNS');
    (current?.runs || []).forEach((run, index) => {
      lines.push(
        `- RUN ${index + 1} | id=${run.id || '?'} | ${run.status || 'unknown'} | batches ${run.startBatch || '?'}-${run.endBatch || '?'} | results ${run.startResultCount || 0}-${run.endResultCount ?? current.results.length}`,
      );
    });
    lines.push('', 'NOTE', 'Foreground runs and background jobs are reported separately. A legacy 5-batch / 100-result foreground run is not evidence that a 500-result background job stopped.');
    return lines.join('\n');
  }

  window.sessionTxt = extendedSessionTxt;
  window.exportTxt = function exportLiveAuditTxt() {
    const blob = new Blob([extendedSessionTxt()], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'namemachine-live-audit-' + (current?.id || 'session') + '.txt';
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    document.getElementById('saveMenu')?.classList.remove('open');
    recordActivity('report_exported', { candidates: current?.results?.length || 0 });
  };

  candidateCursor = maxLocalSeq();
  ensurePanel();
  auditUserActions();
  setInterval(updateTelemetry, 1000);
  void refreshCapability();
})();
