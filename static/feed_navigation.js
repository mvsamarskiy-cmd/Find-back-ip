/* Large-feed navigation layer.
 *
 * Loaded last. It keeps the working Feed newest-first, never alphabetizes it,
 * and renders a bounded window. Turbo mode deliberately presents only strict
 * claimable results from the active Turbo run; rejected rows remain durable in
 * session storage for audit, learning, and client reports.
 */
(() => {
  const PAGE_SIZE = 60;
  const RECOMMENDED_RENDER_LIMIT = 200;
  let feedFilter = 'all';
  let feedQuery = '';
  let visibleLimit = PAGE_SIZE;
  let controlsReady = false;

  function newestFirst(rows) {
    return [...(rows || [])].sort((a, b) => {
      const aSeq = Number(a?.received_seq) || 0;
      const bSeq = Number(b?.received_seq) || 0;
      if (aSeq !== bSeq) return bSeq - aSeq;
      const aAt = String(a?.received_at || '');
      const bAt = String(b?.received_at || '');
      if (aAt !== bAt) return aAt < bAt ? 1 : -1;
      return 0;
    });
  }

  function turboContext() {
    const bg = current?.backgroundSearch;
    if (!bg || bg.search_strategy !== 'turbo' || !bg.run_id) return null;
    return { runId: String(bg.run_id) };
  }

  function turboRunRows(rows) {
    const turbo = turboContext();
    if (!turbo) return [];
    return (rows || []).filter(row => String(row?.run_id || '') === turbo.runId);
  }

  function primaryRows(rows) {
    const turbo = turboContext();
    if (!turbo) return rows || [];
    return turboRunRows(rows).filter(allGreen);
  }

  function resourcesFor(row) {
    const selected = Array.isArray(current?.resources) ? current.resources : [];
    return selected.map(key => normalizedStatus((row?.availability || {})[key]));
  }

  function isChecking(row) {
    return row?.checked === false || resourcesFor(row).some(status => status === 'checking');
  }

  function isPromising(row) {
    return !allGreen(row) && !hasConflict(row) && !isChecking(row) && row?.bundle_state === 'promising';
  }

  function isUnresolved(row) {
    return !allGreen(row) && !hasConflict(row) && !isPromising(row);
  }

  function category(row) {
    if (allGreen(row)) return 'confirmed';
    if (hasConflict(row)) return 'conflict';
    if (isPromising(row)) return 'promising';
    return 'unresolved';
  }

  function matches(row) {
    if (feedFilter !== 'all' && category(row) !== feedFilter) return false;
    const query = feedQuery.trim().toLowerCase();
    if (!query) return true;
    return String(row?.name || '').toLowerCase().includes(query);
  }

  function counts(rows) {
    const result = { all: rows.length, confirmed: 0, promising: 0, conflict: 0, unresolved: 0 };
    for (const row of rows) result[category(row)] += 1;
    return result;
  }

  function injectStyle() {
    if (document.getElementById('feedNavigationStyle')) return;
    const style = document.createElement('style');
    style.id = 'feedNavigationStyle';
    style.textContent = `
      .feed-tools{display:grid;gap:10px;margin-bottom:12px;padding:12px;border:1px solid var(--line);border-radius:15px;background:var(--panel)}
      .feed-tools-top{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
      .feed-search{flex:1;min-width:180px;background:var(--panel2);color:var(--text);border:1px solid var(--line);border-radius:11px;padding:10px 12px;font:inherit}
      .feed-filter{font-size:12px;padding:8px 10px}
      .feed-filter.active{border-color:var(--accent);color:var(--accent)}
      .feed-tools-meta{display:flex;align-items:center;justify-content:space-between;gap:10px;color:var(--muted);font-size:12px}
      .feed-more{font-size:12px;padding:8px 10px}
      .turbo-feed-note{color:var(--ok)}
      @media(max-width:640px){.feed-tools-top{display:grid;grid-template-columns:1fr 1fr}.feed-search{grid-column:1/-1;width:100%}.feed-tools-meta{align-items:flex-start}}
    `;
    document.head.appendChild(style);
  }

  function ensureControls() {
    if (controlsReady && document.getElementById('feedTools')) return;
    const view = document.getElementById('feedView');
    const grid = document.getElementById('feedGrid');
    if (!view || !grid) return;
    injectStyle();
    const tools = document.createElement('div');
    tools.id = 'feedTools';
    tools.className = 'feed-tools';
    tools.innerHTML = `
      <div class="feed-tools-top">
        <input id="feedSearch" class="feed-search" type="search" autocomplete="off" placeholder="Знайти назву в цій сесії">
        <button type="button" class="feed-filter active" data-feed-filter="all">Усі <span data-filter-count="all">0</span></button>
        <button type="button" class="feed-filter" data-feed-filter="confirmed">Підтверджені <span data-filter-count="confirmed">0</span></button>
        <button type="button" class="feed-filter" data-feed-filter="promising">Перспективні <span data-filter-count="promising">0</span></button>
        <button type="button" class="feed-filter" data-feed-filter="conflict">Конфлікти <span data-filter-count="conflict">0</span></button>
        <button type="button" class="feed-filter" data-feed-filter="unresolved">Невідомі <span data-filter-count="unresolved">0</span></button>
      </div>
      <div class="feed-tools-meta">
        <span id="feedShown">Найновіші результати зверху.</span>
        <button id="feedMore" class="feed-more" type="button" hidden>Показати ще</button>
      </div>`;
    view.insertBefore(tools, grid);

    tools.querySelectorAll('[data-feed-filter]').forEach(button => {
      button.addEventListener('click', () => {
        feedFilter = button.dataset.feedFilter || 'all';
        visibleLimit = PAGE_SIZE;
        tools.querySelectorAll('[data-feed-filter]').forEach(item => {
          item.classList.toggle('active', item === button);
        });
        render();
      });
    });
    const search = tools.querySelector('#feedSearch');
    search.addEventListener('input', () => {
      feedQuery = search.value || '';
      visibleLimit = PAGE_SIZE;
      render();
    });
    tools.querySelector('#feedMore').addEventListener('click', () => {
      visibleLimit += PAGE_SIZE;
      render();
    });
    controlsReady = true;
  }

  function syncTurboFilters() {
    const turbo = turboContext();
    document.querySelectorAll('[data-feed-filter]').forEach(button => {
      const key = button.dataset.feedFilter;
      if (turbo && !['all', 'confirmed'].includes(key)) {
        button.hidden = true;
      } else {
        button.hidden = false;
      }
    });
    if (turbo && !['all', 'confirmed'].includes(feedFilter)) {
      feedFilter = 'all';
      document.querySelectorAll('[data-feed-filter]').forEach(button => {
        button.classList.toggle('active', button.dataset.feedFilter === 'all');
      });
    }
  }

  function renderFeedWindow(allRows) {
    ensureControls();
    syncTurboFilters();
    const rows = primaryRows(allRows);
    const ordered = newestFirst(rows);
    const filtered = ordered.filter(matches);
    const shown = filtered.slice(0, visibleLimit);
    const grid = document.getElementById('feedGrid');
    const turbo = turboContext();
    grid.innerHTML = shown.length
      ? shown.map(row => card(row, 'feed')).join('')
      : turbo
        ? '<div class="empty">Turbo ще не знайшов жодного підтверджено вільного результату. Зайняті та непідтверджені кандидати перевіряються у фоні й не засмічують цю стрічку.</div>'
        : '<div class="empty">За цим фільтром результатів немає.</div>';

    const totals = counts(rows);
    document.querySelectorAll('[data-filter-count]').forEach(node => {
      const key = node.dataset.filterCount;
      node.textContent = String(totals[key] || 0);
    });
    const shownLabel = document.getElementById('feedShown');
    if (shownLabel) {
      if (turbo) {
        const checked = turboRunRows(allRows).length;
        const rejected = Math.max(0, checked - rows.length);
        shownLabel.innerHTML = `<span class="turbo-feed-note">Turbo · ${rows.length} вільних</span> · перевірено ${checked} · відсіяно ${rejected}`;
      } else {
        shownLabel.textContent = filtered.length
          ? `Показано ${shown.length} з ${filtered.length} · найновіші зверху`
          : 'Немає результатів для поточного фільтра.';
      }
    }
    const more = document.getElementById('feedMore');
    if (more) {
      more.hidden = shown.length >= filtered.length;
      more.textContent = `Показати ще ${Math.min(PAGE_SIZE, Math.max(0, filtered.length - shown.length))}`;
    }
  }

  render = function renderLargeFeed() {
    if (!current) current = emptySession();
    const rows = Array.isArray(current.results) ? current.results : [];
    const turbo = turboContext();
    const strictCurrent = turbo ? primaryRows(rows) : null;
    const recommended = turbo ? sortedResults(strictCurrent) : sortedResults(rows.filter(allGreen));
    const shortlist = sortedResults(rows.filter(row => current.shortlist.includes(row.name)));

    document.getElementById('recommendedCount').textContent = recommended.length;
    document.getElementById('feedCount').textContent = turbo ? strictCurrent.length : rows.length;
    document.getElementById('shortlistCount').textContent = shortlist.length;

    const recVisible = recommended.slice(0, RECOMMENDED_RENDER_LIMIT);
    document.getElementById('recommendedGrid').innerHTML = recVisible.length
      ? recVisible.map(row => card(row, 'recommended')).join('') +
        (recommended.length > recVisible.length
          ? `<div class="empty">Показано перші ${recVisible.length} з ${recommended.length} підтверджених.</div>`
          : '')
      : turbo
        ? '<div class="empty">Turbo ще шукає перший підтверджено вільний результат.</div>'
        : '<div class="empty">Повністю зелених результатів ще немає.</div>';

    renderFeedWindow(rows);

    document.getElementById('shortlistGrid').innerHTML = shortlist.length
      ? shortlist.map(row => card(row, 'shortlist')).join('')
      : '<div class="empty">Додай сюди назви, до яких хочеш повернутися пізніше.</div>';
    document.getElementById('sessionTitle').textContent = current.title || 'Нова сесія';
    switchTab(activeTab);
  };

  const note = document.querySelector('.session-note');
  if (note) {
    note.textContent = 'Робоча сесія зберігається одразу в браузері. Якщо серверне сховище доступне, вона також синхронізується з ним. Stop ставить пошук на паузу; лайки, дизлайки, коментарі, кандидати й напрями не скидаються.';
  }

  ensureControls();
  render();
})();
