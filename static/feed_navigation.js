/* Large-feed navigation layer.
 *
 * Keeps the working Feed newest-first and uses real bounded pages instead of an
 * ever-growing "show more" window. Turbo keeps every checked candidate visible
 * in Results so likes/dislikes/comments can steer the next batch; Recommended
 * remains strict-green only.
 */
(() => {
  const PAGE_SIZE = 25;
  let feedFilter = 'all';
  let feedQuery = '';
  let controlsReady = false;
  const pages = { feed: 1, recommended: 1, shortlist: 1 };

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
    // Do not hide rejected/unconfirmed rows. They are the user's training surface:
    // feedback on them is consumed by the next intent-scoped generation batch.
    return turboRunRows(rows);
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

  function totalPages(total) {
    return Math.max(1, Math.ceil(Math.max(0, Number(total) || 0) / PAGE_SIZE));
  }

  function clampPage(kind, total) {
    const max = totalPages(total);
    const requested = Math.max(1, Number(pages[kind]) || 1);
    pages[kind] = Math.min(requested, max);
    return pages[kind];
  }

  function slicePage(rows, kind) {
    const list = rows || [];
    const page = clampPage(kind, list.length);
    const start = (page - 1) * PAGE_SIZE;
    return list.slice(start, start + PAGE_SIZE);
  }

  function pageNumbers(page, max) {
    if (max <= 7) return Array.from({ length: max }, (_, index) => index + 1);
    const set = new Set([1, max, page - 1, page, page + 1]);
    const ordered = [...set].filter(value => value >= 1 && value <= max).sort((a, b) => a - b);
    const output = [];
    let previous = 0;
    for (const value of ordered) {
      if (previous && value - previous > 1) output.push('…');
      output.push(value);
      previous = value;
    }
    return output;
  }

  function paginationMarkup(kind, total) {
    const max = totalPages(total);
    const page = clampPage(kind, total);
    if (total <= PAGE_SIZE) return '';
    const numbers = pageNumbers(page, max).map(value => {
      if (value === '…') return '<span class="page-gap">…</span>';
      return `<button type="button" class="page-button${value === page ? ' active' : ''}" data-page-kind="${kind}" data-page="${value}" aria-label="Сторінка ${value}"${value === page ? ' aria-current="page"' : ''}>${value}</button>`;
    }).join('');
    return `<nav class="pagination" aria-label="Навігація сторінками">
      <button type="button" class="page-button" data-page-kind="${kind}" data-page="${page - 1}" ${page <= 1 ? 'disabled' : ''} aria-label="Попередня сторінка">←</button>
      ${numbers}
      <button type="button" class="page-button" data-page-kind="${kind}" data-page="${page + 1}" ${page >= max ? 'disabled' : ''} aria-label="Наступна сторінка">→</button>
      <span class="page-summary">${page}/${max}</span>
    </nav>`;
  }

  function injectStyle() {
    if (document.getElementById('feedNavigationStyle')) return;
    const style = document.createElement('style');
    style.id = 'feedNavigationStyle';
    style.textContent = `
      .feed-tools{display:grid;gap:10px;margin-bottom:12px;padding:12px;border:1px solid var(--line);border-radius:15px;background:var(--panel)}
      .feed-tools-top{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
      .feed-search{flex:1;min-width:180px;background:var(--panel2);color:var(--text);border:1px solid var(--line);border-radius:11px;padding:10px 12px;font:inherit}
      .feed-filter{font-size:12px;padding:8px 10px}.feed-filter.active{border-color:var(--accent);color:var(--accent)}
      .feed-tools-meta{display:flex;align-items:center;justify-content:space-between;gap:10px;color:var(--muted);font-size:12px}
      .turbo-feed-note{color:var(--ok)}
      .pagination{display:flex;align-items:center;justify-content:center;gap:6px;flex-wrap:wrap;margin:16px 0 4px;grid-column:1/-1}
      .page-button{min-width:36px;padding:8px 10px;font-size:12px}.page-button.active{background:var(--text);border-color:var(--text);color:#111;font-weight:800}.page-button:disabled{opacity:.35}
      .page-gap{color:var(--muted);padding:0 2px}.page-summary{color:var(--muted);font-size:11px;margin-left:4px}
      @media(max-width:640px){.feed-tools-top{display:grid;grid-template-columns:1fr 1fr}.feed-search{grid-column:1/-1;width:100%}.feed-tools-meta{align-items:flex-start}.pagination{gap:4px}.page-button{min-width:33px;padding:7px 8px}}
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
      <div class="feed-tools-meta"><span id="feedShown">Найновіші результати зверху.</span></div>`;
    view.insertBefore(tools, grid);

    tools.querySelectorAll('[data-feed-filter]').forEach(button => {
      button.addEventListener('click', () => {
        feedFilter = button.dataset.feedFilter || 'all';
        pages.feed = 1;
        tools.querySelectorAll('[data-feed-filter]').forEach(item => item.classList.toggle('active', item === button));
        render();
      });
    });
    const search = tools.querySelector('#feedSearch');
    search.addEventListener('input', () => {
      feedQuery = search.value || '';
      pages.feed = 1;
      render();
    });
    controlsReady = true;
  }

  function syncTurboFilters() {
    // Turbo no longer hides evidence. All category filters stay usable so the user
    // can judge rejected/unconfirmed names and feed that judgement back.
    document.querySelectorAll('[data-feed-filter]').forEach(button => { button.hidden = false; });
  }

  function pageGrid(gridId, rows, source, kind, emptyHtml) {
    const grid = document.getElementById(gridId);
    const visible = slicePage(rows, kind);
    grid.innerHTML = visible.length
      ? visible.map(row => card(row, source)).join('') + paginationMarkup(kind, rows.length)
      : emptyHtml;
    return visible.length;
  }

  function renderFeedWindow(allRows) {
    ensureControls();
    syncTurboFilters();
    const rows = primaryRows(allRows);
    const ordered = newestFirst(rows);
    const filtered = ordered.filter(matches);
    const turbo = turboContext();
    const shown = pageGrid(
      'feedGrid',
      filtered,
      'feed',
      'feed',
      '<div class="empty">За цим фільтром результатів немає.</div>',
    );

    const totals = counts(rows);
    document.querySelectorAll('[data-filter-count]').forEach(node => {
      const key = node.dataset.filterCount;
      node.textContent = String(totals[key] || 0);
    });
    const shownLabel = document.getElementById('feedShown');
    if (shownLabel) {
      const page = clampPage('feed', filtered.length);
      const start = filtered.length ? (page - 1) * PAGE_SIZE + 1 : 0;
      const end = filtered.length ? Math.min(start + shown - 1, filtered.length) : 0;
      if (turbo) {
        shownLabel.innerHTML = `<span class="turbo-feed-note">Turbo · ${totals.confirmed} підтверджено</span> · ` +
          `${totals.promising} перспективних · ${totals.conflict} конфліктів · ${totals.unresolved} невідомих` +
          (filtered.length ? ` · ${start}–${end}` : '');
      } else {
        shownLabel.textContent = filtered.length
          ? `Показано ${start}–${end} з ${filtered.length} · найновіші зверху`
          : 'Немає результатів для поточного фільтра.';
      }
    }
  }

  document.addEventListener('click', event => {
    const button = event.target.closest('[data-page-kind][data-page]');
    if (!button || button.disabled) return;
    const kind = button.dataset.pageKind;
    if (!Object.prototype.hasOwnProperty.call(pages, kind)) return;
    const next = Number(button.dataset.page);
    if (!Number.isFinite(next)) return;
    pages[kind] = Math.max(1, next);
    render();
    const target = kind === 'feed' ? document.getElementById('feedTools') : document.getElementById(kind + 'View');
    target?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });

  render = function renderPagedFeed() {
    if (!current) current = emptySession();
    const rows = Array.isArray(current.results) ? current.results : [];
    const turbo = turboContext();
    const activeRows = turbo ? turboRunRows(rows) : rows;
    const recommended = newestFirst(activeRows.filter(allGreen));
    const shortlist = newestFirst(rows.filter(row => current.shortlist.includes(row.name)));

    document.getElementById('recommendedCount').textContent = recommended.length;
    document.getElementById('feedCount').textContent = activeRows.length;
    document.getElementById('shortlistCount').textContent = shortlist.length;

    pageGrid(
      'recommendedGrid',
      recommended,
      'recommended',
      'recommended',
      turbo
        ? '<div class="empty">Turbo ще шукає перший підтверджено вільний результат.</div>'
        : '<div class="empty">Повністю зелених результатів ще немає.</div>',
    );

    renderFeedWindow(rows);

    pageGrid(
      'shortlistGrid',
      shortlist,
      'shortlist',
      'shortlist',
      '<div class="empty">Додай сюди назви, до яких хочеш повернутися пізніше.</div>',
    );
    document.getElementById('sessionTitle').textContent = current.title || 'Нова сесія';
    switchTab(activeTab);
  };

  const note = document.querySelector('.session-note');
  if (note) {
    note.textContent = 'Усі перевірені кандидати залишаються в «Результатах». Лайки, дизлайки, коментарі та напрями з поточного пошуку впливають на наступну генерацію; «Підтверджені» лишаються строго зеленими.';
  }

  window.nameMachineFeedPagination = { pageSize: PAGE_SIZE, pages };
  ensureControls();
  render();
})();
