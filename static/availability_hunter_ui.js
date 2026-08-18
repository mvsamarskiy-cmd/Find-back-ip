/* Availability Hunter search-mode UI.
 *
 * Procedural mode exposes the real root/strategy being explored. Turbo mode
 * deliberately hides non-claimable mass from the primary feed while keeping all
 * verifier rows durable for audit and learning.
 */
(() => {
  const POLL_MS = 2200;
  let installed = false;
  let pollTimer = null;
  let startBusy = false;

  const creds = () => current?.serverSession || null;
  const authHeaders = () => {
    const token = creds()?.token;
    return token ? { 'X-NameMachine-Session-Token': token } : {};
  };

  function appendActivity(type, details) {
    if (!current) return;
    if (!Array.isArray(current.activityLog)) current.activityLog = [];
    current.activityLog.push({
      at: new Date().toISOString(),
      type,
      job_id: current?.backgroundSearch?.id || null,
      details: details || {},
    });
    if (current.activityLog.length > 600) current.activityLog.splice(0, current.activityLog.length - 600);
    current.updated = new Date().toISOString();
    try { write(SESSION_KEY, current); } catch (_) {}
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: {
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...authHeaders(),
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

  function selectedStrategy(panel) {
    const value = String(panel?.querySelector('#hunterSearchStrategy')?.value || 'procedural');
    return value === 'turbo' ? 'turbo' : 'procedural';
  }

  function updateModeHint(panel) {
    const mode = selectedStrategy(panel);
    const focus = panel?.querySelector('#proceduralFocusStatus');
    if (!focus || current?.backgroundSearch?.id) return;
    focus.textContent = mode === 'turbo'
      ? 'Turbo: показуватиму насамперед тільки підтверджено вільні результати.'
      : 'Процедурно: один корінь за раз, доки його стратегії не вичерпано.';
  }

  function ensureHunterControls() {
    const panel = document.getElementById('largeSearchPanel');
    if (!panel) return null;
    if (panel.dataset.hunterInstalled === '1') return panel;
    panel.dataset.hunterInstalled = '1';

    const heading = panel.querySelector('strong');
    if (heading) heading.textContent = 'Пошук вільних';

    const strategy = document.createElement('select');
    strategy.id = 'hunterSearchStrategy';
    strategy.setAttribute('aria-label', 'Режим пошуку');
    strategy.innerHTML = `
      <option value="procedural" selected>Процедурно</option>
      <option value="turbo">Turbo</option>`;
    heading?.insertAdjacentElement('afterend', strategy);

    const budget = panel.querySelector('#largeSearchTarget');
    if (budget) {
      budget.setAttribute('aria-label', 'Максимум перевірок');
      const label = document.createElement('span');
      label.className = 'hunter-label';
      label.textContent = 'бюджет';
      budget.insertAdjacentElement('beforebegin', label);
    }

    const target = document.createElement('select');
    target.id = 'hunterTargetMatches';
    target.setAttribute('aria-label', 'Скільки підтверджено вільних знайти');
    target.innerHTML = [1, 3, 5, 10]
      .map(value => `<option value="${value}"${value === 3 ? ' selected' : ''}>${value} вільних</option>`)
      .join('');
    budget?.insertAdjacentElement('afterend', target);

    const start = panel.querySelector('#largeSearchStart');
    if (start) start.textContent = 'Знайти';

    const goal = document.createElement('span');
    goal.id = 'hunterGoalStatus';
    goal.className = 'hunter-goal-status';
    goal.textContent = 'Ціль: 3 підтверджено вільних.';
    const status = panel.querySelector('#largeSearchStatus');
    status?.insertAdjacentElement('afterend', goal);

    const focus = document.createElement('span');
    focus.id = 'proceduralFocusStatus';
    focus.className = 'procedural-focus-status';
    focus.textContent = 'Процедурно: один корінь за раз, доки його стратегії не вичерпано.';
    goal.insertAdjacentElement('afterend', focus);

    if (!document.getElementById('availabilityHunterStyle')) {
      const style = document.createElement('style');
      style.id = 'availabilityHunterStyle';
      style.textContent = `
        .hunter-label{font-size:11px;color:var(--muted)}
        #hunterTargetMatches,#hunterSearchStrategy{background:var(--panel2);color:var(--text);border:1px solid var(--line);border-radius:10px;padding:8px 9px;font:inherit}
        .hunter-goal-status,.procedural-focus-status{width:100%;font-size:12px;color:var(--muted)}
        .hunter-goal-status strong{color:var(--ok)}
        .procedural-focus-status b{color:var(--text)}
      `;
      document.head.appendChild(style);
    }

    target.addEventListener('change', () => {
      if (!current?.backgroundSearch?.id) {
        goal.textContent = `Ціль: ${Number(target.value) || 3} підтверджено вільних.`;
      }
    });
    strategy.addEventListener('change', () => updateModeHint(panel));

    start?.addEventListener('click', event => {
      event.preventDefault();
      event.stopImmediatePropagation();
      void startHunterSearch(panel);
    }, true);

    return panel;
  }

  async function startHunterSearch(panel) {
    if (startBusy) return;
    const session = creds();
    const prompt = document.getElementById('prompt')?.value?.trim() || '';
    const resources = typeof selectedResources === 'function' ? selectedResources() : [];
    const start = panel?.querySelector('#largeSearchStart');
    const goal = panel?.querySelector('#hunterGoalStatus');
    const focus = panel?.querySelector('#proceduralFocusStatus');
    const strategy = selectedStrategy(panel);
    const targetMatches = Math.max(1, Number(panel?.querySelector('#hunterTargetMatches')?.value) || 3);
    const maxChecks = Math.max(targetMatches, Number(panel?.querySelector('#largeSearchTarget')?.value) || 500);

    if (!session?.id || !session?.token) {
      document.getElementById('status').textContent = 'Серверна сесія ще не готова.';
      return;
    }
    if (prompt.length < 3 || !resources.length) {
      document.getElementById('status').textContent = prompt.length < 3
        ? 'Опиши задачу хоча б кількома словами.'
        : 'Обери хоча б один ресурс.';
      return;
    }

    startBusy = true;
    if (start) start.disabled = true;
    if (goal) goal.textContent = `Запускаю: знайти ${targetMatches} вільних, максимум ${maxChecks} перевірок…`;
    if (focus) {
      focus.textContent = strategy === 'turbo'
        ? 'Turbo: запускаю широке паралельне дослідження naming-простору…'
        : 'Будую послідовний план коренів…';
    }
    try {
      const payload = await api('/api/sessions/' + encodeURIComponent(session.id) + '/search-jobs', {
        method: 'POST',
        body: JSON.stringify({
          brief: prompt,
          resources,
          required_resources: resources,
          preferences: typeof buildPreferences === 'function' ? buildPreferences() : {},
          search_context: {
            mode: 'new_brand',
            brand_name: '',
            guidance: current?.directionAnchors?.length
              ? 'Орієнтуйся на: ' + current.directionAnchors.slice(-5).join(', ')
              : '',
          },
          brand_dna: null,
          generation_context: typeof adaptiveContext === 'function'
            ? adaptiveContext((Number(current?.batchCounter) || 0) + 1)
            : {},
          target_count: maxChecks,
          target_matches: targetMatches,
          max_checks: maxChecks,
          search_strategy: strategy,
          batch_size: 20,
        }),
      });
      const job = payload?.job || null;
      if (!job) throw new Error('Сервер не повернув search job');
      current.backgroundSearch = {
        id: job.id,
        run_id: job.run_id,
        target_count: maxChecks,
        target_matches: targetMatches,
        search_strategy: strategy,
        started_at: new Date().toISOString(),
      };
      current.updated = new Date().toISOString();
      try { write(SESSION_KEY, current); } catch (_) {}
      appendActivity('availability_hunter_started', {
        target_matches: targetMatches,
        max_checks: maxChecks,
        search_strategy: strategy,
        resources: [...resources],
        prompt,
      });
      if (goal) goal.textContent = `Ціль: ${targetMatches} вільних · бюджет ${maxChecks} перевірок.`;
      document.getElementById('status').textContent = strategy === 'turbo'
        ? `Turbo запущено: шукаю ${targetMatches} підтверджено вільних.`
        : `Процедурний пошук запущено: ціль ${targetMatches} підтверджено вільних.`;
      try { render(); } catch (_) {}
      schedulePoll(250);
    } catch (error) {
      appendActivity('availability_hunter_start_error', { message: error.message || 'unknown' });
      if (goal) goal.textContent = error.message || 'Не вдалося запустити пошук.';
      if (start) start.disabled = false;
    } finally {
      startBusy = false;
    }
  }

  async function pollHunterProgress() {
    const panel = ensureHunterControls();
    const session = creds();
    const goal = panel?.querySelector('#hunterGoalStatus');
    const focus = panel?.querySelector('#proceduralFocusStatus');
    if (!panel || !session?.id || !session?.token) return;
    try {
      const payload = await api('/api/sessions/' + encodeURIComponent(session.id) + '/search-jobs?limit=5');
      const jobs = Array.isArray(payload?.jobs) ? payload.jobs : [];
      const jobId = current?.backgroundSearch?.id;
      const job = jobs.find(item => item?.id === jobId) || jobs.find(item => item?.search_context?.availability_hunter?.enabled);
      if (!job) return;
      const config = job.search_context?.availability_hunter || {};
      const strategy = String(job.search_context?.search_strategy || (job.search_context?.procedural_search?.enabled ? 'procedural' : 'adaptive'));
      const runtime = job.preferences?._hunter_runtime || {};
      const plan = job.preferences?._procedural_runtime || {};
      const matches = Number(runtime.matches) || 0;
      const targetMatches = Number(runtime.target_matches || config.target_matches) || 0;
      const checked = Number(runtime.checked ?? job.delivered_count) || 0;
      const maxChecks = Number(runtime.max_checks || config.max_checks || job.target_count) || 0;
      const done = ['completed', 'cancelled', 'failed'].includes(job.state);

      if (!current.backgroundSearch || current.backgroundSearch.id !== job.id || current.backgroundSearch.search_strategy !== strategy) {
        current.backgroundSearch = {
          ...(current.backgroundSearch || {}),
          id: job.id,
          run_id: job.run_id,
          target_count: maxChecks,
          target_matches: targetMatches,
          search_strategy: strategy,
          started_at: job.started_at || job.created_at || current?.backgroundSearch?.started_at || '',
        };
        try { write(SESSION_KEY, current); } catch (_) {}
        try { render(); } catch (_) {}
      }

      const selector = panel.querySelector('#hunterSearchStrategy');
      if (selector && ['procedural', 'turbo'].includes(strategy)) selector.value = strategy;
      if (goal) {
        goal.innerHTML = `<strong>${matches}/${targetMatches}</strong> вільних · перевірено ${checked}/${maxChecks}` +
          (done && job.stop_reason ? ` · ${job.stop_reason}` : '');
      }
      if (focus) {
        if (strategy === 'turbo') {
          focus.textContent = `Turbo · широке дослідження · ${matches} підтверджено вільних знайдено`;
        } else if (plan.exhausted) {
          focus.textContent = 'Процедурний простір поточного плану вичерпано.';
        } else if (plan.current_root) {
          focus.innerHTML = `Шукаю корінь <b>${plan.current_root}</b> · ${plan.current_strategy || '—'} · ` +
            `${Number(plan.strategy_checked) || 0} перевірок у цьому кроці`;
        } else {
          focus.textContent = 'Будую послідовний план коренів…';
        }
      }
      const start = panel.querySelector('#largeSearchStart');
      if (start && done) start.disabled = false;
      if (!done) schedulePoll(POLL_MS);
    } catch (_) {
      schedulePoll(POLL_MS * 2);
    }
  }

  function schedulePoll(delay = POLL_MS) {
    clearTimeout(pollTimer);
    pollTimer = setTimeout(() => { void pollHunterProgress(); }, delay);
  }

  function install() {
    if (installed) return;
    const panel = ensureHunterControls();
    if (!panel) {
      setTimeout(install, 300);
      return;
    }
    installed = true;
    schedulePoll(600);
  }

  install();
})();
