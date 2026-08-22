/* Human-readable explanations for private Money / Global result cards.
 * Uses the already captured private payload; it does not issue another search or
 * parse another response body. All text is inserted via textContent.
 */
(() => {
  if (window.__nmPrivateResultExplainer) return;
  window.__nmPrivateResultExplainer = true;

  const clean = (value, limit = 600) => String(value ?? '').replace(/\s+/g, ' ').trim().slice(0, limit);

  function addStyle() {
    if (document.getElementById('nmPrivateResultExplainerStyle')) return;
    const style = document.createElement('style');
    style.id = 'nmPrivateResultExplainerStyle';
    style.textContent = `
      .nmpg-explain{display:grid;gap:8px;margin:11px 0 12px;padding:11px 12px;border:1px solid var(--line);border-radius:13px;background:rgba(255,255,255,.018)}
      .nmpg-explain-row{display:grid;grid-template-columns:minmax(108px,auto) 1fr;gap:8px;align-items:start;font-size:12px;line-height:1.5}
      .nmpg-explain-label{font-weight:800;color:var(--text)}
      .nmpg-explain-value{color:#c9d0da;overflow-wrap:anywhere}
      .nmpg-explain-warning .nmpg-explain-value{color:#e2bd7a}
      @media(max-width:520px){.nmpg-explain-row{grid-template-columns:1fr;gap:2px}.nmpg-explain{padding:10px}}
    `;
    document.head.appendChild(style);
  }

  function rowMap() {
    const snapshot = window.__nmPrivateMoneyReportSnapshot?.();
    const rows = Array.isArray(snapshot?.payload?.results) ? snapshot.payload.results : [];
    const map = new Map();
    for (const row of rows) {
      const title = clean(row?.title, 300).toLocaleLowerCase();
      if (title && !map.has(title)) map.set(title, row);
    }
    return map;
  }

  function appendLine(box, label, value, warning = false) {
    const text = clean(value, 700);
    if (!text) return;
    const line = document.createElement('div');
    line.className = 'nmpg-explain-row' + (warning ? ' nmpg-explain-warning' : '');
    const key = document.createElement('div');
    key.className = 'nmpg-explain-label';
    key.textContent = label;
    const val = document.createElement('div');
    val.className = 'nmpg-explain-value';
    val.textContent = text;
    line.append(key, val);
    box.appendChild(line);
  }

  function fallback(card) {
    const raw = clean(card.querySelector('.nmpg-original p')?.textContent, 360);
    const old = clean(card.querySelector('.nmpg-desc')?.textContent, 500);
    return {
      about: raw || old || 'Зміст джерела ще не витягнуто.',
      why: 'Система знайшла цей URL у пошуковій видачі. Якщо категорія не підтверджена самим текстом джерела, такий кандидат має бути відсіяний бекендом.',
      value: 'Конкретну суму або матеріальну вигоду з доступного фрагмента не підтверджено.',
      uncertainty: 'Перевір першоджерело, актуальність і умови перед будь-якою дією.',
    };
  }

  function explainCard(card, rows) {
    if (!(card instanceof HTMLElement)) return;
    const title = clean(card.querySelector('.nmpg-title')?.textContent, 300).toLocaleLowerCase();
    const row = rows.get(title);
    const info = row?.ui_explanation || fallback(card);

    let box = card.querySelector(':scope > .nmpg-explain');
    if (!box) {
      box = document.createElement('div');
      box.className = 'nmpg-explain';
      const desc = card.querySelector(':scope > .nmpg-desc');
      if (desc) {
        desc.hidden = true;
        desc.insertAdjacentElement('afterend', box);
      } else {
        card.querySelector('.nmpg-head')?.insertAdjacentElement('afterend', box);
      }
    }
    box.replaceChildren();
    appendLine(box, 'Про що це', info.about);
    appendLine(box, 'Чому тут', info.why);
    appendLine(box, 'Що можна отримати', info.value);
    appendLine(box, 'Що не підтверджено', info.uncertainty, true);
    card.dataset.nmExplained = '1';
  }

  let scheduled = false;
  function refresh() {
    scheduled = false;
    if (!document.body.classList.contains('nm-private-global')) return;
    const root = document.getElementById('nmPrivateResults');
    if (!root) return;
    const rows = rowMap();
    root.querySelectorAll('.nmpg-card').forEach(card => explainCard(card, rows));
  }

  function schedule() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(refresh);
  }

  addStyle();
  const observer = new MutationObserver(schedule);
  observer.observe(document.body, {childList: true, subtree: true, attributes: true, attributeFilter: ['class']});
  window.addEventListener('pageshow', schedule);
  document.addEventListener('visibilitychange', schedule);
  schedule();
})();
