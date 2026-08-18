/* Resource-progress layer loaded after streaming.js. */
(() => {
  const baseUiState = uiState;
  const baseBadgeLabel = badgeLabel;
  let flushPending = false;

  uiState = row => String(row?.status || '') === 'checking'
    ? { cls: 'unknown', label: 'Перевіряю…' }
    : baseUiState(row);

  badgeLabel = row => {
    const resources = Array.isArray(current?.resources) ? current.resources : [];
    const checking = resources.some(k => String((row?.availability || {})[k]?.status || '') === 'checking');
    if (checking) {
      const done = Number(row?.resource_progress?.completed) || 0;
      const total = Number(row?.resource_progress?.total) || resources.length;
      return 'перевірка ' + done + '/' + total;
    }
    if (row?.checked === false) return 'перевірка перервана';
    return baseBadgeLabel(row);
  };

  function flushNow() {
    flushPending = false;
    saveCurrent();
    render();
  }

  function scheduleFlush() {
    if (flushPending) return;
    flushPending = true;
    if (typeof requestAnimationFrame === 'function') requestAnimationFrame(flushNow);
    else setTimeout(flushNow, 0);
  }

  function pendingResources(resources) {
    return Object.fromEntries(resources.map(resource => [resource, {
      status: 'checking', detail: 'Перевірка виконується.', source: 'streaming_client',
      method: 'pending', confidence: 0, occupancy: 'unknown', claimability: 'unconfirmed'
    }]));
  }

  function addCandidate(event, runId, batchNumber) {
    const row = event?.row || {};
    const key = String(row.name || '').toLowerCase();
    if (!key || current.results.some(r => String(r?.name || '').toLowerCase() === key)) return 0;
    const resources = Array.isArray(event.resources) ? event.resources : current.resources;
    current.streamCounter = (Number(current.streamCounter) || 0) + 1;
    current.results.push({
      ...row,
      availability: pendingResources(resources), verification: {}, checked: false,
      resource_progress: { completed: 0, total: resources.length },
      _stream_id: event.candidate_id, run_id: runId, batch_number: batchNumber,
      received_seq: current.streamCounter, received_at: new Date().toISOString()
    });
    return 1;
  }

  const findStreamRow = id => current.results.find(row => row?._stream_id === id);

  function applyResource(event) {
    const row = findStreamRow(event?.candidate_id);
    if (!row || !event?.resource || !event?.availability) return false;
    row.availability = { ...(row.availability || {}), [event.resource]: event.availability };
    if (event.verification) row.verification = { ...(row.verification || {}), [event.resource]: event.verification };
    row.resource_progress = {
      completed: Number(event.completed_resources) || 0,
      total: Number(event.total_resources) || current.resources.length
    };
    row.checked = false;
    return true;
  }

  function finishCandidate(event, runId, batchNumber) {
    const row = findStreamRow(event?.candidate_id);
    if (!row || !event?.row) return false;
    const keep = {
      _stream_id: row._stream_id, run_id: row.run_id || runId,
      batch_number: row.batch_number || batchNumber,
      received_seq: row.received_seq, received_at: row.received_at
    };
    Object.assign(row, event.row, keep, { checked: true });
    delete row.resource_progress;
    return true;
  }

  function interruptedRow() {
    return {
      status: 'unknown', detail: 'Перевірка перервана до отримання доказу. Можна повторити.',
      source: 'streaming_client', method: 'interrupted_stream', confidence: 0,
      occupancy: 'unknown', claimability: 'unconfirmed'
    };
  }

  function markInterrupted(runId = null) {
    let changed = false;
    for (const row of current?.results || []) {
      if (runId && row.run_id !== runId) continue;
      const availability = row.availability || {};
      let rowChanged = false;
      for (const resource of current.resources || []) {
        if (String(availability[resource]?.status || '') === 'checking') {
          availability[resource] = interruptedRow();
          rowChanged = true;
          changed = true;
        }
      }
      if (rowChanged) row.checked = false;
    }
    return changed;
  }

  async function responseError(response) {
    try {
      const payload = await response.json();
      return new Error(payload?.error || ('HTTP ' + response.status));
    } catch (_) {
      return new Error('Сервер повернув некоректну відповідь.');
    }
  }

  async function consume(response, onEvent) {
    if (!response.ok) throw await responseError(response);
    if (!response.body || typeof response.body.getReader !== 'function') {
      for (const line of (await response.text()).split('\n')) if (line.trim()) onEvent(JSON.parse(line));
      return;
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let i;
        while ((i = buffer.indexOf('\n')) >= 0) {
          const line = buffer.slice(0, i).trim();
          buffer = buffer.slice(i + 1);
          if (line) onEvent(JSON.parse(line));
        }
      }
      buffer += decoder.decode();
      if (buffer.trim()) onEvent(JSON.parse(buffer.trim()));
    } finally {
      reader.releaseLock();
    }
  }

  async function runBatch(prompt, resources, run, batchNumber, batchLabel, batchCount) {
    activeController = new AbortController();
    const response = await fetch('/api/ai-generate-stream', {
      method: 'POST', signal: activeController.signal,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        brief: prompt, count: batchCount, preferences: buildPreferences(),
        search_context: {
          mode: 'new_brand', brand_name: '',
          guidance: current.directionAnchors.length ? 'Орієнтуйся на: ' + current.directionAnchors.slice(-5).join(', ') : ''
        },
        brand_dna: null, resources, required_resources: resources,
        generation_context: adaptiveContext(batchNumber)
      })
    });

    let added = 0, finalized = 0, serverDone = false;
    try {
      await consume(response, event => {
        if (!event || typeof event !== 'object') return;
        if (event.type === 'phase') {
          document.getElementById('status').textContent = event.phase === 'generated'
            ? 'Згенеровано ' + (event.total || 0) + ' · готую перевірку · партія ' + batchLabel
            : 'Перевіряю ресурси · ' + (event.total_resource_checks || 0) + ' перевірок';
        } else if (event.type === 'candidate') {
          added += addCandidate(event, run.id, batchNumber);
          scheduleFlush();
        } else if (event.type === 'resource') {
          if (applyResource(event)) scheduleFlush();
          const platform = labels[event.resource] || event.resource || 'ресурс';
          document.getElementById('status').textContent = platform + ' · ' +
            (event.completed_resource_checks || 0) + '/' + (event.total_resource_checks || 0) +
            ' · у стрічці ' + current.results.length;
        } else if (event.type === 'result' && event.row) {
          if (finishCandidate(event, run.id, batchNumber)) finalized += 1;
          scheduleFlush();
          document.getElementById('status').textContent = 'Готово кандидатів ' +
            (event.completed || finalized) + '/' + (event.total || batchCount);
        } else if (event.type === 'done') {
          serverDone = true;
        }
      });
    } finally {
      activeController = null;
      flushNow();
    }
    return { added, finalized, serverDone };
  }

  startSearch = async function resourceProgressSearch() {
    if (activeController) return;
    const prompt = document.getElementById('prompt').value.trim();
    const resources = selectedResources();
    if (prompt.length < 3) {
      document.getElementById('status').textContent = 'Опиши задачу хоча б кількома словами.';
      return;
    }
    if (!resources.length) {
      document.getElementById('status').textContent = 'Обери хоча б один ресурс.';
      return;
    }

    if (!current) current = emptySession();
    current.resources = resources;
    write(RESOURCES_KEY, resources);
    const previousPrompt = current.promptHistory.at(-1)?.text || '';
    if (prompt !== previousPrompt) current.promptHistory.push({ text: prompt, at: new Date().toISOString(), feedback: feedbackSummary() });
    if (current.title === 'Нова сесія') current.title = prompt.replace(/\s+/g, ' ').slice(0, 48);

    stopRequested = false;
    document.getElementById('stopBtn').disabled = false;
    document.getElementById('startBtn').disabled = true;
    const run = {
      id: 'r' + Date.now(), prompt, started: new Date().toISOString(), status: 'running',
      startResultCount: current.results.length,
      startBatch: (Number(current.batchCounter) || 0) + 1
    };
    current.runs.push(run);
    flushNow();

    let stopReason = 'batch_limit';
    try {
      for (let batch = 1; batch <= MAX_BATCHES && current.results.length - run.startResultCount < MAX_EXTERNAL_CHECKS; batch++) {
        if (stopRequested) { stopReason = 'user_stop'; break; }
        const batchCount = Math.min(BATCH_SIZE, MAX_EXTERNAL_CHECKS - (current.results.length - run.startResultCount));
        current.batchCounter = (Number(current.batchCounter) || 0) + 1;
        const globalBatch = current.batchCounter;
        document.getElementById('status').textContent = 'Генерую · партія ' + batch + '/' + MAX_BATCHES + ' · цикл ' + globalBatch;
        const outcome = await runBatch(prompt, resources, run, globalBatch, batch + '/' + MAX_BATCHES, batchCount);
        if (stopRequested) { stopReason = 'user_stop'; break; }
        if (!outcome.added && outcome.serverDone) { stopReason = 'empty'; break; }
      }
      run.status = stopReason === 'user_stop' ? 'paused' : 'complete';
      run.finished = new Date().toISOString();
      run.endResultCount = current.results.length;
      run.endBatch = Number(current.batchCounter) || 0;
      document.getElementById('status').textContent = stopReason === 'user_stop'
        ? 'Пошук на паузі. Часткові результати вже збережено.'
        : 'Поточний цикл завершено. Можеш уточнити запит і продовжити.';
    } catch (error) {
      run.endResultCount = current.results.length;
      run.endBatch = Number(current.batchCounter) || 0;
      markInterrupted(run.id);
      if (error.name === 'AbortError' || stopRequested) {
        run.status = 'paused';
        document.getElementById('status').textContent = 'Пошук на паузі. Отримані перевірки збережено, незавершені позначено невідомими.';
      } else {
        run.status = 'error';
        document.getElementById('status').textContent = (current.results.length ? 'Пошук зупинено, часткові результати збережено. ' : '') + (error.message || 'Помилка потокової перевірки.');
      }
    } finally {
      activeController = null;
      flushNow();
      document.getElementById('stopBtn').disabled = true;
      document.getElementById('startBtn').disabled = false;
      document.getElementById('startBtn').textContent = current.results.length ? 'Continue' : 'Start';
    }
  };

  if (markInterrupted()) flushNow();
})();
