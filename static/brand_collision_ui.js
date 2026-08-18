/* NameMachine brand-collision screening overlay.
 *
 * Only active in the explicit "Створити бренд" workflow. Screening is staged
 * and conservative: it never labels a brand globally free.
 */
(() => {
  const baseCard = card;
  const busy = new Set();

  function modeIsBrand() {
    return String(current?.entryMode || '') === 'brand';
  }

  function riskCopy(signal) {
    const value = String(signal || 'unknown');
    if (value === 'high') return { label: 'сильний конфлікт', cls: 'high' };
    if (value === 'medium') return { label: 'потрібна перевірка', cls: 'medium' };
    if (value === 'low_observed') return { label: 'мало конфліктів у перевірених джерелах', cls: 'low' };
    if (value === 'none_observed') return { label: 'збігів не знайдено у перевірених джерелах', cls: 'low' };
    return { label: 'не завершено', cls: 'unknown' };
  }

  function count(payload, key) {
    const value = Number(payload?.counts?.[key]);
    return Number.isFinite(value) ? value : 0;
  }

  function sourceLinks(payload) {
    const links = [];
    const manualGoogle = payload?.web?.manual_search;
    if (manualGoogle) links.push(`<a target="_blank" rel="noopener" href="${esc(manualGoogle)}">Google</a>`);
    for (const source of payload?.companies?.manual_sources || []) {
      if (source?.url) links.push(`<a target="_blank" rel="noopener" href="${esc(source.url)}">${esc(source.label || source.market || 'реєстр')}</a>`);
    }
    for (const source of Object.values(payload?.trademarks?.sources || {})) {
      if (source?.url) links.push(`<a target="_blank" rel="noopener" href="${esc(source.url)}">${esc(source.label || 'trademark')}</a>`);
    }
    return links.length ? `<div class="brand-collision-links">Додатково: ${links.join(' · ')}</div>` : '';
  }

  function panel(row) {
    const payload = row?.brand_collision;
    if (!payload) {
      return `<div class="brand-collision" data-brand-collision-panel="${esc(row?.name || '')}"><button type="button" class="brand-collision-run" data-brand-collision-name="${esc(row?.name || '')}">Перевірити бренд</button><span>web · companies · trademarks</span></div>`;
    }
    const risk = riskCopy(payload.collision_signal);
    const web = payload.web || {};
    const uk = payload.companies?.uk || {};
    const trademark = payload.trademarks || {};
    const webState = web.status === 'complete'
      ? `${count(web, 'observed')} результатів · exact domain ${count(web, 'exact_domain')}`
      : 'не перевірено';
    const companyState = uk.status === 'complete'
      ? `${count(uk, 'observed')} UK · exact active ${count(uk, 'exact_active')} · similar active ${count(uk, 'similar_active')}`
      : 'автоматична перевірка не виконана';
    const trademarkState = trademark.assessment === 'manual_search_required'
      ? 'потрібна окрема перевірка реєстрів'
      : esc(trademark.risk || 'unknown');
    return `<div class="brand-collision brand-collision-${risk.cls}" data-brand-collision-panel="${esc(row?.name || '')}">
      <div class="brand-collision-head"><b>Brand collision</b><span>${esc(risk.label)}</span></div>
      <div class="brand-collision-row"><span>Web</span><strong>${esc(webState)}</strong></div>
      <div class="brand-collision-row"><span>Компанії</span><strong>${esc(companyState)}</strong></div>
      <div class="brand-collision-row"><span>Торгові марки</span><strong>${trademarkState}</strong></div>
      <div class="brand-collision-note">Це screening конфліктів, не юридичне підтвердження, що бренд «вільний».</div>
      ${sourceLinks(payload)}
      <button type="button" class="brand-collision-run" data-brand-collision-name="${esc(row?.name || '')}">Оновити перевірку</button>
    </div>`;
  }

  card = function brandCollisionCard(row, source) {
    const html = baseCard(row, source);
    if (!modeIsBrand() || row?.product_mode === 'generic_name') return html;
    return html.replace('</article>', panel(row) + '</article>');
  };

  async function run(name) {
    const key = String(name || '').toLowerCase();
    if (!key || busy.has(key)) return;
    const row = (current?.results || []).find(item => String(item?.name || '').toLowerCase() === key);
    if (!row) return;
    busy.add(key);
    const status = document.getElementById('status');
    if (status) status.textContent = `Перевіряю бренд ${row.name}: web, компанії, trademarks…`;
    document.querySelectorAll(`[data-brand-collision-name="${CSS.escape(row.name)}"]`).forEach(button => {
      button.disabled = true;
      button.textContent = 'Перевіряю…';
    });
    try {
      const response = await fetch('/api/brand-collision', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: row.name,
          context: {
            company_markets: ['PL', 'GB', 'INTL'],
            trademark_context: { territories: ['EU', 'PL', 'INTL'], nice_classes: [] },
          },
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload?.error || ('HTTP ' + response.status));
      row.brand_collision = payload;
      row.brand_collision_checked_at = new Date().toISOString();
      saveCurrent();
      render();
      if (status) {
        const risk = riskCopy(payload.collision_signal);
        status.textContent = `${row.name}: ${risk.label}. Це screening, не висновок про юридичну доступність.`;
      }
    } catch (error) {
      if (status) status.textContent = `Не вдалося перевірити ${row.name}: ${error.message || 'помилка'}`;
    } finally {
      busy.delete(key);
    }
  }

  document.addEventListener('click', event => {
    const button = event.target.closest('.brand-collision-run');
    if (!button) return;
    run(button.dataset.brandCollisionName);
  });

  const style = document.createElement('style');
  style.textContent = `
    .brand-collision{margin-top:13px;border-top:1px solid rgba(255,255,255,.08);padding-top:12px;display:grid;gap:7px;color:var(--muted);font-size:12px}
    .brand-collision>button{width:max-content;font-size:12px;padding:8px 10px}
    .brand-collision-head,.brand-collision-row{display:flex;justify-content:space-between;gap:10px;align-items:center}
    .brand-collision-head b{color:var(--text)}
    .brand-collision-head span{border:1px solid var(--line);border-radius:999px;padding:4px 7px}
    .brand-collision-row strong{color:#cdd5df;text-align:right;font-weight:600}
    .brand-collision-high .brand-collision-head span{border-color:var(--bad);color:var(--bad)}
    .brand-collision-medium .brand-collision-head span{border-color:var(--warn);color:var(--warn)}
    .brand-collision-low .brand-collision-head span{border-color:var(--ok);color:var(--ok)}
    .brand-collision-note{line-height:1.4}
    .brand-collision-links a{color:var(--text)}
    @media(max-width:640px){.brand-collision-row{align-items:flex-start}.brand-collision-row strong{max-width:65%}}
  `;
  document.head.appendChild(style);

  try { render(); } catch (_) {}
})();
