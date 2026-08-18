/* Incremental NameMachine search client.
 *
 * Loaded after the historical inline UI. It intentionally overrides only the
 * search execution and feed ordering while reusing the existing session,
 * feedback, rendering helpers, and controls.
 */
(() => {
  const rankByQuality = sortedResults;

  function newestFirst(rows) {
    return [...rows].sort((a, b) => {
      const aSeq = Number(a?.received_seq) || 0;
      const bSeq = Number(b?.received_seq) || 0;
      if (aSeq !== bSeq) return bSeq - aSeq;
      const aAt = String(a?.received_at || '');
      const bAt = String(b?.received_at || '');
      if (aAt !== bAt) return bAt.localeCompare(aAt);
      return String(a?.name || '').localeCompare(String(b?.name || ''));
    });
  }

  render = function renderStreamingFeed() {
    if (!current) current = emptySession();
    const rec = rankByQuality(current.results.filter(allGreen));
    const feed = newestFirst(current.results);
    const short = rankByQuality(current.results.filter(r => current.shortlist.includes(r.name)));
    document.getElementById('recommendedCount').textContent = rec.length;
    document.getElementById('feedCount').textContent = feed.length;
    document.getElementById('shortlistCount').textContent = short.length;
    document.getElementById('recommendedGrid').innerHTML = rec.length
      ? rec.map(r => card(r, 'recommended')).join('')
      : '<div class="empty">Повністю зелених результатів ще немає.</div>';
    document.getElementById('feedGrid').innerHTML = feed.length
      ? feed.map(r => card(r, 'feed')).join('')
      : '<div class="empty">Тут з’являтиметься весь перевірений пошук.</div>';
    document.getElementById('shortlistGrid').innerHTML = short.length
      ? short.map(r => card(r, 'shortlist')).join('')
      : '<div class="empty">Додай сюди назви, до яких хочеш повернутися пізніше.</div>';
    document.getElementById('sessionTitle').textContent = current.title || 'Нова сесія';
    switchTab(activeTab);
  };

  function entryMode() {
    return typeof window.nameMachineEntryMode === 'function'
      ? window.nameMachineEntryMode()
      : (current?.entryMode || 'other');
  }

  function searchContext(prompt) {
    if (typeof window.nameMachineSearchContext === 'function') {
      return window.nameMachineSearchContext(prompt);
    }
    return {
      mode: 'new_brand',
      brand_name: '',
      guidance: current.directionAnchors.length
        ? 'Орієнтуйся на: ' + current.directionAnchors.slice(-5).join(', ')
        : '',
    };
  }

  function mergeStreamingRow(row, runId, batchNumber, productMode) {
    const key = String(row?.name || '').toLowerCase();
    if (!key) return 0;
    const exists = current.results.some(item => String(item?.name || '').toLowerCase() === key);
    if (exists) return 0;
    current.streamCounter = (Number(current.streamCounter) || 0) + 1;
    current.results.push({
      ...row,
      checked: true,
      product_mode: productMode,
      run_id: runId,
      batch_number: batchNumber,
      received_seq: current.streamCounter,
      received_at: new Date().toISOString(),
    });
    return 1;
  }

  async function responseError(response) {
    try {
      const payload = await response.json();
      return new Error(payload?.error || ('HTTP ' + response.status));
    } catch (_) {
      return new Error('Сервер повернув некоректну відповідь.');
    }
  }

  async function consumeNdjson(response, onEvent) {
    if (!response.ok) throw await responseError(response);

    if (!response.body || typeof response.body.getReader !== 'function') {
      const text = await response.text();
      for (const line of text.split('\n')) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        onEvent(JSON.parse(trimmed));
      }
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
        let newline;
        while ((newline = buffer.indexOf('\n')) >= 0) {
          const line = buffer.slice(0, newline).trim();
          buffer = buffer.slice(newline + 1);
          if (!line) continue;
          onEvent(JSON.parse(line));
        }
      }
      buffer += decoder.decode();
      if (buffer.trim()) onEvent(JSON.parse(buffer.trim()));
    } finally {
      reader.releaseLock();
    }
  }

  async function runStreamingBatch(prompt, resources, run, batchNumber, batchLabel, batchCount) {
    activeController = new AbortController();
    const context = searchContext(prompt);
    const response = await fetch('/api/ai-generate-stream', {
      method: 'POST',
      signal: activeController.signal,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        brief: prompt,
        count: batchCount,
        preferences: buildPreferences(),
        search_context: context,
        brand_dna: null,
        resources,
        required_resources: resources,
        generation_context: adaptiveContext(batchNumber),
      }),
    });

    let delivered = 0;
    let serverDone = false;
    try {
      await consumeNdjson(response, event => {
        if (!event || typeof event !== 'object') return;
        if (event.type === 'phase') {
          document.getElementById('status').textContent =
            'Перевіряю · партія ' + batchLabel + ' · кандидатів ' + (event.total || batchCount);
          return;
        }
        if (event.type === 'result' && event.row) {
          const added = mergeStreamingRow(event.row, run.id, batchNumber, run.entry_mode || entryMode());
          if (added) {
            delivered += added;
            saveCurrent();
            render();
          }
          document.getElementById('status').textContent =
            'Перевірено ' + (event.completed || delivered) + '/' + (event.total || batchCount) +
            ' · у стрічці ' + current.results.length;
          return;
        }
        if (event.type === 'candidate_error') {
          document.getElementById('status').textContent =
            'Перевірено ' + (event.completed || 0) + '/' + (event.total || batchCount) +
            ' · один кандидат не підтверджено';
          return;
        }
        if (event.type === 'done') serverDone = true;
      });
    } finally {
      activeController = null;
    }
    return { delivered, serverDone };
  }

  startSearch = async function startStreamingSearch() {
    if (activeController) return;
    const prompt = document.getElementById('prompt').value.trim();
    const resources = selectedResources();
    const mode = entryMode();
    if (prompt.length < 3) {
      document.getElementById('status').textContent = 'Опиши задачу хоча б кількома словами.';
      return;
    }
    if (!resources.length) {
      document.getElementById('status').textContent = 'Обери хоча б один ресурс.';
      return;
    }
    // Validate mode-specific fields before creating a run.
    try { searchContext(prompt); } catch (error) {
      document.getElementById('status').textContent = error.message || 'Уточни задачу.';
      return;
    }

    if (!current) current = emptySession();
    current.entryMode = mode;
    current.resources = resources;
    write(RESOURCES_KEY, resources);
    const previousPrompt = current.promptHistory.at(-1)?.text || '';
    if (prompt !== previousPrompt) {
      current.promptHistory.push({
        text: prompt,
        at: new Date().toISOString(),
        feedback: feedbackSummary(),
        entry_mode: mode,
      });
    }
    if (current.title === 'Нова сесія') current.title = prompt.replace(/\s+/g, ' ').slice(0, 48);

    stopRequested = false;
    document.getElementById('stopBtn').disabled = false;
    document.getElementById('startBtn').disabled = true;
    const run = {
      id: 'r' + Date.now(),
      prompt,
      entry_mode: mode,
      started: new Date().toISOString(),
      status: 'running',
      startResultCount: current.results.length,
      startBatch: (Number(current.batchCounter) || 0) + 1,
    };
    current.runs.push(run);
    saveCurrent();
    render();

    let stopReason = 'batch_limit';
    try {
      for (
        let batch = 1;
        batch <= MAX_BATCHES && current.results.length - run.startResultCount < MAX_EXTERNAL_CHECKS;
        batch++
      ) {
        if (stopRequested) {
          stopReason = 'user_stop';
          break;
        }

        const batchCount = Math.min(
          BATCH_SIZE,
          MAX_EXTERNAL_CHECKS - (current.results.length - run.startResultCount),
        );
        current.batchCounter = (Number(current.batchCounter) || 0) + 1;
        const globalBatch = current.batchCounter;
        document.getElementById('status').textContent =
          'Генерую · партія ' + batch + '/' + MAX_BATCHES + ' · цикл ' + globalBatch;

        const outcome = await runStreamingBatch(
          prompt,
          resources,
          run,
          globalBatch,
          batch + '/' + MAX_BATCHES,
          batchCount,
        );

        if (stopRequested) {
          stopReason = 'user_stop';
          break;
        }
        if (!outcome.delivered && outcome.serverDone) {
          stopReason = 'empty';
          break;
        }
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
      if (error.name === 'AbortError' || stopRequested) {
        run.status = 'paused';
        document.getElementById('status').textContent = 'Пошук на паузі. Часткові результати збережено.';
      } else {
        run.status = 'error';
        document.getElementById('status').textContent =
          (current.results.length ? 'Пошук зупинено, часткові результати збережено. ' : '') +
          (error.message || 'Помилка потокової перевірки.');
      }
    } finally {
      activeController = null;
      saveCurrent();
      render();
      document.getElementById('stopBtn').disabled = true;
      document.getElementById('startBtn').disabled = false;
      document.getElementById('startBtn').textContent = current.results.length ? 'Continue' : 'Start';
    }
  };
})();
