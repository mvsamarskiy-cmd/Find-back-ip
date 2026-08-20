/* Mode-aware client-report overlay.
 *
 * A session is generation-only only when it contains no availability evidence.
 * If ideas were later rechecked, the verification report wins so the document
 * never claims that no resources were checked when provider facts are present.
 */
(() => {
  const baseHtml = window.exportClientReportHtml;
  const baseTxt = window.exportClientReportTxt;
  const baseTextBuilder = window.clientReportTxt;
  const baseEmail = window.emailClientReport;

  const clean = (value, limit = 1000) => String(value ?? '').replace(/\s+/g, ' ').trim().slice(0, limit);
  const escapeHtml = value => clean(value, 4000).replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));

  function hasAvailabilityEvidence() {
    return (current?.results || []).some(row =>
      row?.availability && typeof row.availability === 'object' && Object.keys(row.availability).length > 0
    );
  }

  function isGenericSession() {
    if (hasAvailabilityEvidence()) return false;
    return String(current?.entryMode || '') === 'generic_name' ||
      (current?.results || []).some(row => row?.product_mode === 'generic_name');
  }

  function genericRows() {
    return [...(current?.results || [])]
      .filter(row => row?.product_mode === 'generic_name')
      .sort((a, b) => (Number(b?.received_seq) || 0) - (Number(a?.received_seq) || 0));
  }

  function feedback(row) {
    return typeof sessionFeedback === 'function'
      ? sessionFeedback(row?.name)
      : (current?.feedback?.[String(row?.name || '').toLowerCase()] || { vote: 0, comment: '' });
  }

  function selected(row) {
    const fb = feedback(row);
    return Number(fb?.vote || 0) > 0 ||
      (current?.shortlist || []).includes(row?.name) ||
      (current?.directionAnchors || []).includes(row?.name) ||
      Boolean(clean(fb?.comment || ''));
  }

  function disliked(row) { return Number(feedback(row)?.vote || 0) < 0; }

  function latestPrompt() {
    const generic = [...(current?.promptHistory || [])].reverse().find(item => item?.entry_mode === 'generic_name');
    return clean(generic?.text || document.getElementById('prompt')?.value || '', 1000);
  }

  function rowText(row) {
    const fb = feedback(row);
    const marks = [];
    if (Number(fb?.vote || 0) > 0) marks.push('👍');
    if (Number(fb?.vote || 0) < 0) marks.push('👎');
    if ((current?.shortlist || []).includes(row?.name)) marks.push('★');
    if ((current?.directionAnchors || []).includes(row?.name)) marks.push('↗');
    return `${marks.join('')}${marks.length ? ' ' : ''}${row?.name || '?'}${row?.reason ? ' — ' + clean(row.reason, 500) : ''}${fb?.comment ? ` · «${clean(fb.comment, 300)}»` : ''}`;
  }

  function genericText() {
    const rows = genericRows();
    const chosen = rows.filter(selected);
    const rejected = rows.filter(disliked);
    const lines = [
      'NameMachine — ЗВІТ ГЕНЕРАЦІЇ НАЗВ',
      '',
      `Проєкт: ${current?.title || 'Сесія генерації'}`,
      'Режим: Придумати назву',
      `Задача: ${latestPrompt() || 'не зафіксовано'}`,
      `Згенеровано: ${rows.length}`,
      `Виділено користувачем: ${chosen.length}`,
      `Відсіяно дизлайком: ${rejected.length}`,
      '',
      '1. ВИБРАНІ / ЦІКАВІ ІДЕЇ',
    ];
    if (!chosen.length) lines.push('- Поки нічого не виділено.');
    chosen.forEach(row => lines.push('- ' + rowText(row)));
    lines.push('', '2. УСІ ЗГЕНЕРОВАНІ НАЗВИ');
    if (!rows.length) lines.push('- Немає.');
    rows.forEach(row => lines.push('- ' + rowText(row)));
    lines.push('', '3. ВІДСІЯНО КОРИСТУВАЧЕМ');
    if (!rejected.length) lines.push('- Немає дизлайків.');
    rejected.forEach(row => lines.push('- ' + rowText(row)));
    lines.push('', '4. ДЛЯ ПРОДОВЖЕННЯ', `- Session ID: ${current?.id || '?'}`, `- Shortlist: ${(current?.shortlist || []).join(', ') || '—'}`, `- Напрями: ${(current?.directionAnchors || []).join(', ') || '—'}`);
    lines.push('', 'Примітка: у цьому запуску ресурси не перевірялися. Вибери хоча б один канал і натисни «Перепровірити результати», щоб отримати фактичні статуси.');
    return lines.join('\n');
  }

  function genericHtml() {
    const rows = genericRows();
    const chosen = rows.filter(selected);
    const rejected = rows.filter(disliked);
    const cards = items => items.length
      ? items.map(row => {
          const fb = feedback(row);
          const marks = [];
          if (Number(fb?.vote || 0) > 0) marks.push('👍 Подобається');
          if ((current?.shortlist || []).includes(row?.name)) marks.push('★ Кандидат');
          if ((current?.directionAnchors || []).includes(row?.name)) marks.push('↗ Напрям');
          return `<article><div class="head"><h3>${escapeHtml(row?.name || '?')}</h3><span>ідея</span></div>${marks.length ? `<b>${escapeHtml(marks.join(' · '))}</b>` : ''}${row?.reason ? `<p>${escapeHtml(row.reason)}</p>` : ''}${fb?.comment ? `<blockquote>${escapeHtml(fb.comment)}</blockquote>` : ''}</article>`;
        }).join('')
      : '<div class="empty">Немає</div>';
    return `<!doctype html><html lang="uk"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>NameMachine — ${escapeHtml(current?.title || 'генерація назв')}</title><style>body{margin:0;background:#f5f6f8;color:#17191d;font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.wrap{max-width:900px;margin:auto;padding:36px 18px 70px}.hero{background:#111827;color:white;border-radius:22px;padding:26px}.hero h1{margin:0 0 8px}.hero p{margin:0;color:#d4d9e1}.stats{display:flex;gap:10px;flex-wrap:wrap;margin-top:18px}.stat{background:#ffffff18;border-radius:12px;padding:10px 14px}.stat b{font-size:22px;display:block}section{margin-top:28px}.cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}article,.empty,.note{background:white;border:1px solid #e1e4e8;border-radius:16px;padding:16px}.head{display:flex;justify-content:space-between;gap:10px}.head h3{margin:0;font-size:22px}.head span{font-size:11px;background:#eef0f3;border-radius:999px;padding:5px 8px;height:max-content}article p{color:#49505a}blockquote{margin:10px 0 0;padding:9px 11px;background:#f6f7f9;border-left:3px solid #a8afb9}.note{margin-top:28px;color:#5d6570}@media(max-width:680px){.cards{grid-template-columns:1fr}}</style></head><body><main class="wrap"><header class="hero"><h1>${escapeHtml(current?.title || 'NameMachine')}</h1><p>${escapeHtml(latestPrompt())}</p><div class="stats"><div class="stat"><b>${rows.length}</b>згенеровано</div><div class="stat"><b>${chosen.length}</b>виділено</div><div class="stat"><b>${rejected.length}</b>відсіяно</div></div></header><section><h2>Вибрані / цікаві ідеї</h2><div class="cards">${cards(chosen)}</div></section><section><h2>Усі згенеровані назви</h2><div class="cards">${cards(rows)}</div></section><section><h2>Відсіяно користувачем</h2><div class="cards">${cards(rejected)}</div></section><div class="note"><strong>Важливо:</strong> у цьому запуску ресурси не перевірялися. Вибери канали й запусти переперевірку, якщо потрібні фактичні статуси.</div></main></body></html>`;
  }

  function download(text, filename, type) {
    const blob = new Blob([text], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    document.getElementById('saveMenu')?.classList.remove('open');
  }

  window.clientReportTxt = () => isGenericSession() ? genericText() : baseTextBuilder();
  window.exportClientReportTxt = () => isGenericSession()
    ? download(genericText(), 'namemachine-name-ideas-' + (current?.id || 'session') + '.txt', 'text/plain;charset=utf-8')
    : baseTxt();
  window.exportClientReportHtml = () => isGenericSession()
    ? download(genericHtml(), 'namemachine-name-ideas-' + (current?.id || 'session') + '.html', 'text/html;charset=utf-8')
    : baseHtml();
  window.emailClientReport = () => {
    if (!isGenericSession()) return baseEmail();
    const report = genericText();
    const recipient = window.prompt('На який email підготувати звіт?');
    if (recipient === null) return;
    const email = clean(recipient, 180);
    if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      document.getElementById('status').textContent = 'Email виглядає некоректно.';
      return;
    }
    const subject = 'NameMachine — ' + clean(current?.title || 'ідеї назв', 90);
    const body = report.length > 12000 ? report.slice(0, 12000) + '\n\n[Повний звіт можна завантажити з NameMachine.]' : report;
    document.getElementById('saveMenu')?.classList.remove('open');
    window.location.href = 'mailto:' + encodeURIComponent(email) + '?subject=' + encodeURIComponent(subject) + '&body=' + encodeURIComponent(body);
  };
})();
