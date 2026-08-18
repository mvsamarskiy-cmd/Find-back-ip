/* NameMachine first-class entry workflows.
 *
 * Four explicit product modes prevent the generator/search engine from guessing
 * a fundamentally different task when the user already knows what they want.
 */
(() => {
  const MODES = {
    brand: {
      label: 'Створити бренд',
      hint: 'Створюємо нову назву бренду та перевіряємо вибрану цифрову присутність.',
      placeholder: 'Опиши бізнес, продукт, аудиторію, ринок і характер майбутнього бренду.',
      verifies: true,
    },
    identity: {
      label: 'Нікнейми / домени',
      hint: 'Назву бренду не змінюємо. Шукаємо пов’язані домени та нікнейми.',
      placeholder: 'Опиши, які цифрові ідентифікатори потрібні та які варіації допустимі.',
      verifies: true,
    },
    generic_name: {
      label: 'Придумати назву',
      hint: 'Лише генеруємо назви або нікнейми. Перевірки доменів і соцмереж не запускаються.',
      placeholder: 'Наприклад: нік для гри, ім’я для бота, назва персонажа, каналу, яхти або проєкту.',
      verifies: false,
    },
    other: {
      label: 'Інше',
      hint: 'Опиши задачу своїми словами. AI структурує її, а вибрані ресурси визначають, що перевіряти.',
      placeholder: 'Опиши своїми словами, що вже маєш і який результат хочеш отримати.',
      verifies: true,
    },
  };
  const MODE_LOCK = '[[nm-mode-lock:';
  const verifiedStartSearch = startSearch;
  const baseCard = card;
  const baseEmptySession = emptySession;
  let genericBusy = false;

  function currentMode() {
    const mode = String(current?.entryMode || 'other');
    return MODES[mode] ? mode : 'other';
  }

  window.nameMachineEntryMode = currentMode;

  emptySession = function emptySessionWithMode() {
    return { ...baseEmptySession(), entryMode: 'other', existingBrandName: '' };
  };

  function guidanceWithMode(mode) {
    const anchors = current?.directionAnchors?.length
      ? 'Орієнтуйся на: ' + current.directionAnchors.slice(-5).join(', ')
      : '';
    if (mode === 'brand') {
      return `${MODE_LOCK}new_brand]] ${anchors}`.trim();
    }
    if (mode === 'identity') {
      return `${MODE_LOCK}existing_brand_fixed]] ${anchors}`.trim();
    }
    return anchors;
  }

  window.nameMachineSearchContext = function nameMachineSearchContext() {
    const mode = currentMode();
    if (mode === 'identity') {
      const brandName = String(document.getElementById('existingBrandName')?.value || current?.existingBrandName || '').trim();
      if (brandName.length < 2) throw new Error('Вкажи існуючу назву бренду.');
      current.existingBrandName = brandName.slice(0, 80);
      return {
        mode: 'existing_brand_fixed',
        brand_name: current.existingBrandName,
        guidance: guidanceWithMode(mode),
      };
    }
    if (mode === 'brand') {
      return { mode: 'new_brand', brand_name: '', guidance: guidanceWithMode(mode) };
    }
    return {
      mode: 'new_brand',
      brand_name: '',
      guidance: guidanceWithMode(mode),
    };
  };

  function ensureModeUi() {
    if (document.getElementById('entryModePanel')) return;
    const composer = document.querySelector('.composer');
    const prompt = document.getElementById('prompt');
    if (!composer || !prompt) return;

    const panel = document.createElement('div');
    panel.id = 'entryModePanel';
    panel.className = 'entry-mode-panel';
    panel.innerHTML = `
      <div class="entry-mode-title">Що потрібно зробити?</div>
      <div class="entry-mode-options">
        ${Object.entries(MODES).map(([key, mode]) => `<button type="button" class="entry-mode-button" data-entry-mode="${key}">${mode.label}</button>`).join('')}
      </div>
      <div id="entryModeHint" class="entry-mode-hint"></div>
      <div id="existingBrandWrap" class="existing-brand-wrap" hidden>
        <label for="existingBrandName">Існуючий бренд</label>
        <input id="existingBrandName" maxlength="80" autocomplete="off" placeholder="Наприклад: Botella">
      </div>`;
    composer.insertBefore(panel, prompt);

    const style = document.createElement('style');
    style.id = 'entryModeStyle';
    style.textContent = `
      .entry-mode-panel{display:grid;gap:9px;margin-bottom:12px;padding-bottom:13px;border-bottom:1px solid var(--line)}
      .entry-mode-title{font-size:12px;color:var(--muted);font-weight:700}
      .entry-mode-options{display:flex;gap:7px;flex-wrap:wrap}
      .entry-mode-button{font-size:12px;padding:8px 10px}
      .entry-mode-button.active{border-color:var(--accent);color:var(--accent);background:rgba(224,178,79,.07)}
      .entry-mode-hint{font-size:12px;color:var(--muted);line-height:1.45}
      .existing-brand-wrap{display:grid;grid-template-columns:auto 1fr;align-items:center;gap:8px}
      .existing-brand-wrap[hidden]{display:none}
      .existing-brand-wrap label{font-size:12px;color:var(--muted)}
      .existing-brand-wrap input{min-width:0;background:var(--panel2);color:var(--text);border:1px solid var(--line);border-radius:11px;padding:9px 11px;font:inherit}
      body.nm-mode-generic_name .resources,body.nm-mode-generic_name #largeSearchPanel{display:none!important}
      body.nm-mode-generic_name .tab[data-tab="recommended"]{display:none}
      @media(max-width:640px){.entry-mode-options{display:grid;grid-template-columns:1fr 1fr}.entry-mode-button{width:100%}.existing-brand-wrap{grid-template-columns:1fr}}
    `;
    document.head.appendChild(style);

    panel.addEventListener('click', event => {
      const button = event.target.closest('[data-entry-mode]');
      if (!button) return;
      setMode(button.dataset.entryMode);
    });
    panel.querySelector('#existingBrandName').addEventListener('input', event => {
      if (!current) current = emptySession();
      current.existingBrandName = String(event.target.value || '').slice(0, 80);
      saveCurrent();
    });
  }

  function setMode(mode, options = {}) {
    if (!MODES[mode]) mode = 'other';
    if (!current) current = emptySession();
    current.entryMode = mode;
    const definition = MODES[mode];
    document.body.className = [...document.body.classList].filter(name => !name.startsWith('nm-mode-')).join(' ');
    document.body.classList.add('nm-mode-' + mode);
    document.querySelectorAll('[data-entry-mode]').forEach(button => {
      button.classList.toggle('active', button.dataset.entryMode === mode);
    });
    const hint = document.getElementById('entryModeHint');
    if (hint) hint.textContent = definition.hint;
    const brandWrap = document.getElementById('existingBrandWrap');
    if (brandWrap) brandWrap.hidden = mode !== 'identity';
    const brandInput = document.getElementById('existingBrandName');
    if (brandInput && brandInput.value !== (current.existingBrandName || '')) {
      brandInput.value = current.existingBrandName || '';
    }
    const prompt = document.getElementById('prompt');
    if (prompt) prompt.placeholder = definition.placeholder;

    if (mode === 'generic_name') {
      if (activeTab === 'recommended') switchTab('feed');
      document.getElementById('startBtn').textContent = current.results.some(row => row?.product_mode === 'generic_name') ? 'Ще назви' : 'Згенерувати';
      document.getElementById('status').textContent = 'Опиши, для чого потрібна назва. Перевірки доступності не виконуються.';
    } else {
      document.getElementById('startBtn').textContent = current.results.length ? 'Continue' : 'Start';
      if (!options.silent) document.getElementById('status').textContent = definition.hint;
    }
    if (!options.silent) saveCurrent();
    try { render(); } catch (_) {}
  }

  function genericCard(row) {
    const fb = sessionFeedback(row.name);
    const shortlisted = current.shortlist.includes(row.name);
    const anchored = current.directionAnchors.includes(row.name);
    const comment = fb.comment ? '<div class="comment">' + esc(fb.comment) + '</div>' : '';
    const direction = anchored ? '<div class="direction">↗ Використовується як напрям</div>' : '';
    return '<article class="card"><div class="card-head"><div class="name">' + esc(row.name) + '</div><div class="badge">ідея</div></div><div class="reason">' + esc(row.reason || 'Згенерована назва.') + '</div>' + direction + '<div class="actions"><button class="like ' + (fb.vote === 1 ? 'active-like' : '') + '" data-name="' + esc(row.name) + '">👍</button><button class="dislike ' + (fb.vote === -1 ? 'active-dislike' : '') + '" data-name="' + esc(row.name) + '">👎</button><button class="comment-toggle" data-name="' + esc(row.name) + '">Коментар</button><button class="direction-btn" data-name="' + esc(row.name) + '">Взяти за напрям</button><button class="shortlist-btn ' + (shortlisted ? 'active-shortlist' : '') + '" data-name="' + esc(row.name) + '">' + (shortlisted ? '★ У кандидатах' : '☆ В кандидати') + '</button><button class="copy-btn" data-name="' + esc(row.name) + '">Копіювати</button></div><div class="commentbox" data-commentbox="' + esc(row.name) + '"><input maxlength="300" value="' + esc(fb.comment || '') + '" placeholder="Що саме подобається або не подобається?"><button class="save-comment" data-name="' + esc(row.name) + '">Зберегти</button></div>' + comment + '</article>';
  }

  card = function modeAwareCard(row, source) {
    if (row?.product_mode === 'generic_name') return genericCard(row);
    return baseCard(row, source);
  };

  async function responseJson(response) {
    let payload = null;
    try { payload = await response.json(); } catch (_) { payload = null; }
    if (!response.ok) throw new Error(payload?.error || ('HTTP ' + response.status));
    return payload;
  }

  async function runGenericNaming() {
    if (genericBusy || activeController) return;
    const prompt = document.getElementById('prompt').value.trim();
    if (prompt.length < 3) {
      document.getElementById('status').textContent = 'Опиши, для чого потрібна назва.';
      return;
    }
    if (!current) current = emptySession();
    current.entryMode = 'generic_name';
    current.resources = [];
    const previousPrompt = current.promptHistory.at(-1)?.text || '';
    if (prompt !== previousPrompt) {
      current.promptHistory.push({ text: prompt, at: new Date().toISOString(), feedback: feedbackSummary(), entry_mode: 'generic_name' });
    }
    if (current.title === 'Нова сесія') current.title = prompt.replace(/\s+/g, ' ').slice(0, 48);

    const run = {
      id: 'r' + Date.now(),
      prompt,
      entry_mode: 'generic_name',
      started: new Date().toISOString(),
      status: 'running',
      startResultCount: current.results.length,
      startBatch: (Number(current.batchCounter) || 0) + 1,
    };
    current.runs.push(run);
    current.batchCounter = (Number(current.batchCounter) || 0) + 1;
    genericBusy = true;
    stopRequested = false;
    document.getElementById('startBtn').disabled = true;
    document.getElementById('stopBtn').disabled = false;
    document.getElementById('status').textContent = 'Генерую назви…';
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
          preferences: buildPreferences(),
          generation_context: adaptiveContext(current.batchCounter),
        }),
      });
      const rows = await responseJson(response);
      const seen = new Set(current.results.map(row => String(row?.name || '').toLowerCase()));
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
          batch_number: current.batchCounter,
          received_seq: current.streamCounter,
          received_at: new Date().toISOString(),
        });
      }
      run.status = 'complete';
      run.finished = new Date().toISOString();
      run.endResultCount = current.results.length;
      run.endBatch = current.batchCounter;
      activeTab = 'feed';
      document.getElementById('status').textContent = 'Назви готові. Лайки, дизлайки й коментарі вплинуть на наступну генерацію.';
    } catch (error) {
      if (error.name === 'AbortError' || stopRequested) {
        run.status = 'paused';
        document.getElementById('status').textContent = 'Генерацію зупинено.';
      } else {
        run.status = 'error';
        document.getElementById('status').textContent = error.message || 'Не вдалося згенерувати назви.';
      }
    } finally {
      activeController = null;
      genericBusy = false;
      saveCurrent();
      render();
      document.getElementById('stopBtn').disabled = true;
      document.getElementById('startBtn').disabled = false;
      document.getElementById('startBtn').textContent = 'Ще назви';
    }
  }

  startSearch = async function modeAwareStartSearch() {
    if (currentMode() === 'generic_name') return runGenericNaming();
    if (currentMode() === 'identity') {
      try { window.nameMachineSearchContext(); } catch (error) {
        document.getElementById('status').textContent = error.message;
        return;
      }
    }
    return verifiedStartSearch();
  };

  // Existing sessions predate explicit modes. Preserve their behavior as Other.
  if (!current) current = emptySession();
  if (!MODES[current.entryMode]) {
    const lastRunMode = [...(current.runs || [])].reverse().find(run => MODES[run?.entry_mode])?.entry_mode;
    current.entryMode = lastRunMode || 'other';
  }
  ensureModeUi();
  setMode(current.entryMode, { silent: true });
})();
