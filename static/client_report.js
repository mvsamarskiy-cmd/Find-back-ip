/* NameMachine client report v5.
 *
 * This is the human-facing output. It deliberately hides verifier noise and raw
 * ledgers, but never turns not_found/unknown into confirmed availability.
 */
(() => {
  const CONFIRMED = new Set(['claimable', 'purchasable']);
  const CONFLICT = new Set(['taken', 'reserved', 'invalid']);
  const RESOURCE_ORDER = ['com', 'instagram', 'telegram', 'tiktok', 'youtube', 'facebook', 'x'];
  const FAMILY_LABELS = {
    root_blend: 'злиті / гібридні слова',
    invented_phonetic: 'вигадані милозвучні слова',
    semantic_compound: 'смислові сполучення',
    abstract: 'абстрактні короткі назви',
    evocative_metaphor: 'образні / метафоричні назви',
  };

  const clean = (value, limit = 800) => String(value ?? '').replace(/\s+/g, ' ').trim().slice(0, limit);
  const html = value => clean(value, 4000).replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));

  function statusOf(payload) {
    const status = String(payload?.status || 'unknown');
    return status === 'available' ? 'unknown' : status;
  }

  function resourcesForRow(row) {
    const availability = row?.availability && typeof row.availability === 'object' ? row.availability : {};
    return Object.keys(availability).sort((a, b) => {
      const ai = RESOURCE_ORDER.indexOf(a), bi = RESOURCE_ORDER.indexOf(b);
      if (ai !== -1 || bi !== -1) return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
      return a.localeCompare(b);
    });
  }

  function candidateState(row) {
    const explicit = String(row?.bundle_state || '');
    if (['confirmed', 'promising', 'conflict', 'unresolved'].includes(explicit)) return explicit;
    const resources = resourcesForRow(row);
    if (!resources.length) return 'unresolved';
    const statuses = resources.map(key => statusOf(row?.availability?.[key]));
    if (statuses.some(status => CONFLICT.has(status))) return 'conflict';
    if (statuses.every(status => CONFIRMED.has(status))) return 'confirmed';
    if (statuses.some(status => status === 'not_found') && !statuses.some(status => CONFLICT.has(status))) return 'promising';
    return 'unresolved';
  }

  function resourceHuman(resource, payload) {
    const status = statusOf(payload);
    const name = labels?.[resource] || resource;
    if (status === 'claimable') return `${name}: підтверджено вільне`;
    if (status === 'purchasable') return `${name}: можна купити`;
    if (CONFLICT.has(status)) return `${name}: зайняте`;
    if (status === 'not_found') return `${name}: не знайдено, потрібне фінальне підтвердження`;
    if (status === 'rate_limited') return `${name}: перевірку тимчасово обмежено`;
    return `${name}: не вдалося підтвердити`;
  }

  function feedbackFor(row) {
    if (typeof sessionFeedback === 'function') return sessionFeedback(row?.name);
    return current?.feedback?.[String(row?.name || '').toLowerCase()] || { vote: 0, comment: '' };
  }

  function isShortlisted(row) { return (current?.shortlist || []).includes(row?.name); }
  function isDirection(row) { return (current?.directionAnchors || []).includes(row?.name); }
  function isLiked(row) { return Number(feedbackFor(row)?.vote || 0) > 0; }
  function isDisliked(row) { return Number(feedbackFor(row)?.vote || 0) < 0; }
  function hasComment(row) { return Boolean(clean(feedbackFor(row)?.comment || '')); }

  function selectedWeight(row) {
    return (isLiked(row) ? 100 : 0) + (isShortlisted(row) ? 50 : 0) + (isDirection(row) ? 25 : 0) + (hasComment(row) ? 10 : 0) + (Number(row?.bundle_score) || 0) / 10;
  }

  function sortRows(rows) {
    return [...rows].sort((a, b) => selectedWeight(b) - selectedWeight(a) || (Number(b?.bundle_score) || 0) - (Number(a?.bundle_score) || 0) || (Number(b?.received_seq) || 0) - (Number(a?.received_seq) || 0));
  }

  function summary(rows) {
    const out = { total: rows.length, confirmed: 0, promising: 0, conflict: 0, unresolved: 0 };
    rows.forEach(row => { const state = candidateState(row); out[state] = (out[state] || 0) + 1; });
    return out;
  }

  function allResources(rows) {
    const seen = new Set();
    rows.forEach(row => resourcesForRow(row).forEach(key => seen.add(key)));
    return RESOURCE_ORDER.filter(key => seen.has(key)).concat([...seen].filter(key => !RESOURCE_ORDER.includes(key)).sort());
  }

  function familyInsights(rows) {
    const stats = new Map();
    for (const row of rows) {
      const family = String(row?.family || 'unknown');
      if (!stats.has(family)) stats.set(family, { liked: 0, disliked: 0, names: [] });
      const item = stats.get(family);
      if (isLiked(row)) item.liked += 1;
      if (isDisliked(row)) item.disliked += 1;
      if (isLiked(row) && item.names.length < 5) item.names.push(row.name);
    }
    return [...stats.entries()]
      .filter(([, item]) => item.liked || item.disliked)
      .sort((a, b) => (b[1].liked - b[1].disliked) - (a[1].liked - a[1].disliked) || b[1].liked - a[1].liked);
  }

  function nearbyOccupied(rows) {
    const likedFamilies = new Set(rows.filter(isLiked).map(row => row?.family).filter(Boolean));
    const direct = rows.filter(row => candidateState(row) === 'conflict' && (isLiked(row) || isShortlisted(row) || isDirection(row)));
    const similar = rows.filter(row => candidateState(row) === 'conflict' && likedFamilies.has(row?.family));
    const seen = new Set();
    return sortRows([...direct, ...similar]).filter(row => {
      const key = String(row?.name || '').toLowerCase();
      if (!key || seen.has(key)) return false;
      seen.add(key);
      return true;
    }).slice(0, 10);
  }

  function rowPlain(row) {
    const fb = feedbackFor(row);
    const marks = [];
    if (isLiked(row)) marks.push('👍');
    if (isDisliked(row)) marks.push('👎');
    if (isShortlisted(row)) marks.push('★');
    if (isDirection(row)) marks.push('↗');
    const status = resourcesForRow(row).map(key => resourceHuman(key, row?.availability?.[key] || {})).join(' · ');
    const comment = clean(fb?.comment || '');
    return `${marks.join('')}${marks.length ? ' ' : ''}${row?.name || '?'} — ${status}${comment ? ` · «${comment}»` : ''}`;
  }

  function cardHtml(row) {
    const state = candidateState(row);
    const fb = feedbackFor(row);
    const stateLabel = state === 'confirmed' ? 'Підтверджено' : state === 'promising' ? 'Перспективний' : state === 'conflict' ? 'Зайняте / конфлікт' : 'Потребує перевірки';
    const badgeClass = state === 'confirmed' ? 'ok' : state === 'promising' ? 'warn' : state === 'conflict' ? 'bad' : 'muted';
    const marks = [];
    if (isLiked(row)) marks.push('👍 Подобається');
    if (isDisliked(row)) marks.push('👎 Не подобається');
    if (isShortlisted(row)) marks.push('★ Кандидат');
    if (isDirection(row)) marks.push('↗ Напрям');
    return `<article class="candidate">
      <div class="candidate-head"><h3>${html(row?.name || '?')}</h3><span class="badge ${badgeClass}">${html(stateLabel)}</span></div>
      ${marks.length ? `<div class="marks">${html(marks.join(' · '))}</div>` : ''}
      ${fb?.comment ? `<div class="quote">“${html(fb.comment)}”</div>` : ''}
      ${row?.reason ? `<p>${html(row.reason)}</p>` : ''}
      <div class="resource-lines">${resourcesForRow(row).map(key => `<div>${html(resourceHuman(key, row?.availability?.[key] || {}))}</div>`).join('')}</div>
    </article>`;
  }

  function sectionHtml(title, subtitle, rows, emptyText = 'Немає') {
    const items = rows || [];
    return `<section><div class="section-title"><div><h2>${html(title)}</h2>${subtitle ? `<p>${html(subtitle)}</p>` : ''}</div><span>${items.length}</span></div>${items.length ? `<div class="cards">${items.map(cardHtml).join('')}</div>` : `<div class="empty">${html(emptyText)}</div>`}</section>`;
  }

  function reportModel() {
    const rows = current?.results || [];
    const totals = summary(rows);
    const selected = sortRows(rows.filter(row => isLiked(row) || isShortlisted(row) || isDirection(row) || hasComment(row))).slice(0, 20);
    const confirmed = sortRows(rows.filter(row => candidateState(row) === 'confirmed')).slice(0, 15);
    const promising = sortRows(rows.filter(row => candidateState(row) === 'promising')).slice(0, 15);
    const occupied = nearbyOccupied(rows);
    const disliked = sortRows(rows.filter(isDisliked)).slice(0, 12);
    const prompts = current?.promptHistory || [];
    const latestPrompt = clean(prompts.at(-1)?.text || document.getElementById('prompt')?.value || '', 1000);
    const resources = allResources(rows);
    const insights = familyInsights(rows);
    return { rows, totals, selected, confirmed, promising, occupied, disliked, prompts, latestPrompt, resources, insights };
  }

  function buildClientTxt() {
    const model = reportModel();
    const lines = [
      'NameMachine — ПІДСУМКОВИЙ ЗВІТ',
      '',
      `Проєкт: ${current?.title || 'Сесія пошуку'}`,
      `Що шукали: ${model.latestPrompt || 'не зафіксовано'}`,
      `Перевірено: ${model.totals.total} кандидатів`,
      `Результат: підтверджені ${model.totals.confirmed} · перспективні ${model.totals.promising} · зайняті/конфліктні ${model.totals.conflict} · невизначені ${model.totals.unresolved}`,
      `Ресурси, які перевірялися: ${model.resources.map(key => labels?.[key] || key).join(', ') || '—'}`,
      '',
      '1. ЩО ПРИВЕРНУЛО УВАГУ',
    ];
    if (!model.selected.length) lines.push('- Користувач ще не виділив кандидатів.');
    model.selected.forEach(row => lines.push('- ' + rowPlain(row)));
    lines.push('', '2. ЩО СИСТЕМА ЗРОЗУМІЛА ПРО СМАК');
    if (!model.insights.length) lines.push('- Недостатньо лайків/дизлайків для висновку.');
    model.insights.slice(0, 5).forEach(([family, item]) => lines.push(`- ${FAMILY_LABELS[family] || family}: 👍 ${item.liked} · 👎 ${item.disliked}${item.names.length ? ' · приклади: ' + item.names.join(', ') : ''}`));
    lines.push('', '3. ПІДТВЕРДЖЕНІ КАНДИДАТИ');
    if (!model.confirmed.length) lines.push('- Немає повністю підтверджених кандидатів.');
    model.confirmed.forEach(row => lines.push('- ' + rowPlain(row)));
    lines.push('', '4. ПЕРСПЕКТИВНІ КАНДИДАТИ');
    lines.push('- “Перспективний” означає, що жорсткого конфлікту не знайдено, але доступність ще не підтверджена остаточно.');
    if (!model.promising.length) lines.push('- Немає.');
    model.promising.forEach(row => lines.push('- ' + rowPlain(row)));
    lines.push('', '5. ВЛУЧНІ ЗА НАПРЯМОМ, АЛЕ ЗАЙНЯТІ');
    if (!model.occupied.length) lines.push('- Немає зафіксованих влучних зайнятих варіантів.');
    model.occupied.forEach(row => lines.push('- ' + rowPlain(row)));
    lines.push('', '6. ВІДСІЯНО КОРИСТУВАЧЕМ');
    if (!model.disliked.length) lines.push('- Немає дизлайків.');
    model.disliked.forEach(row => lines.push('- ' + rowPlain(row)));
    lines.push('', '7. ЯК ПРОДОВЖИТИ', `- Session ID: ${current?.id || '?'}`, `- Останній запит: ${model.latestPrompt || '—'}`, `- Кандидати: ${(current?.shortlist || []).join(', ') || '—'}`, `- Напрями: ${(current?.directionAnchors || []).join(', ') || '—'}`);
    lines.push('', 'Примітка: “не знайдено” не дорівнює “вільне”. Перед реєстрацією потрібна фінальна перевірка на самій платформі або авторитетним провайдером.');
    return lines.join('\n');
  }

  function buildClientHtml() {
    const model = reportModel();
    const insightHtml = model.insights.length
      ? model.insights.slice(0, 5).map(([family, item]) => `<div class="insight"><strong>${html(FAMILY_LABELS[family] || family)}</strong><span>👍 ${item.liked} · 👎 ${item.disliked}</span>${item.names.length ? `<small>${html(item.names.join(' · '))}</small>` : ''}</div>`).join('')
      : '<div class="empty">Ще недостатньо лайків і дизлайків для профілю смаку.</div>';
    const promptHistory = model.prompts.length ? model.prompts.map((entry, index) => `<li><strong>${index + 1}.</strong> ${html(entry?.text || '')}</li>`).join('') : '<li>Історія запитів відсутня.</li>';
    return `<!doctype html><html lang="uk"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>NameMachine — ${html(current?.title || 'звіт')}</title><style>
      :root{--bg:#f4f5f7;--card:#fff;--text:#17191d;--muted:#68707c;--line:#e1e4e8;--ok:#147a38;--warn:#986900;--bad:#b3261e;--accent:#111827}
      *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.wrap{max-width:920px;margin:auto;padding:42px 18px 70px}.hero{background:var(--accent);color:white;border-radius:24px;padding:28px}.hero h1{margin:0 0 8px;font-size:32px}.hero p{margin:0;color:#d7dce4}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:22px}.stat{background:rgba(255,255,255,.1);border-radius:14px;padding:14px}.stat b{display:block;font-size:26px}.stat span{font-size:12px;color:#d7dce4}section{margin-top:28px}.section-title{display:flex;align-items:flex-end;justify-content:space-between;gap:12px;margin-bottom:12px}.section-title h2{margin:0;font-size:22px}.section-title p{margin:4px 0 0;color:var(--muted)}.section-title>span{color:var(--muted)}.cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.candidate{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:17px}.candidate-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}.candidate h3{margin:0;font-size:22px}.candidate p{color:#464d57;margin:10px 0}.badge{white-space:nowrap;border-radius:999px;padding:5px 8px;font-size:11px;background:#eef0f3}.badge.ok{color:var(--ok);background:#e7f6ec}.badge.warn{color:var(--warn);background:#fff4d6}.badge.bad{color:var(--bad);background:#fdecea}.marks{font-size:12px;font-weight:700;margin-top:5px}.quote{margin:10px 0;padding:10px 12px;background:#f7f8fa;border-left:3px solid #a5abb3;border-radius:8px}.resource-lines{font-size:12px;color:var(--muted);display:grid;gap:4px}.insights{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.insight{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:14px;display:grid;gap:4px}.insight span{color:var(--muted)}.insight small{color:var(--muted)}.empty{background:var(--card);border:1px dashed var(--line);border-radius:16px;padding:18px;color:var(--muted)}.searchbox{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:18px}.searchbox ul{padding-left:20px}.footer{margin-top:32px;color:var(--muted);font-size:12px}.warning{background:#fff7df;border:1px solid #f0d88e;border-radius:14px;padding:12px 14px;color:#654d00;margin-top:14px}@media(max-width:700px){.stats{grid-template-columns:repeat(2,1fr)}.cards{grid-template-columns:1fr}.insights{grid-template-columns:1fr}.hero h1{font-size:27px}}
    </style></head><body><main class="wrap">
      <header class="hero"><h1>${html(current?.title || 'NameMachine')}</h1><p>${html(model.latestPrompt || 'Підсумок пошуку назв')}</p><div class="stats"><div class="stat"><b>${model.totals.total}</b><span>перевірено</span></div><div class="stat"><b>${model.totals.confirmed}</b><span>підтверджено</span></div><div class="stat"><b>${model.totals.promising}</b><span>перспективні</span></div><div class="stat"><b>${model.totals.conflict}</b><span>зайняті / конфліктні</span></div></div></header>
      ${sectionHtml('Що привернуло увагу', 'Лайки, коментарі, shortlist і вибрані напрями.', model.selected, 'Користувач ще не виділив кандидатів.')}
      <section><div class="section-title"><div><h2>Що система зрозуміла про смак</h2><p>Тільки з явних лайків і дизлайків, без вигаданих причин.</p></div></div><div class="insights">${insightHtml}</div></section>
      ${sectionHtml('Підтверджені кандидати', 'Тільки там, де вибрані ресурси справді підтверджено придатними.', model.confirmed, 'Повністю підтверджених кандидатів поки немає.')}
      ${sectionHtml('Перспективні кандидати', 'Жорсткого конфлікту не знайдено, але потрібне фінальне підтвердження.', model.promising, 'Перспективних кандидатів немає.')}
      ${sectionHtml('Влучні за напрямом, але зайняті', 'Корисні як орієнтир для наступної генерації, навіть якщо їх уже не можна брати.', model.occupied, 'Таких варіантів не зафіксовано.')}
      ${sectionHtml('Відсіяно користувачем', 'Назви, на які поставлено дизлайк.', model.disliked, 'Дизлайків немає.')}
      <section><div class="section-title"><div><h2>Що саме шукали</h2><p>Історія запитів цієї сесії.</p></div></div><div class="searchbox"><ul>${promptHistory}</ul><div><strong>Перевірені ресурси:</strong> ${html(model.resources.map(key => labels?.[key] || key).join(', ') || '—')}</div><div><strong>Session ID:</strong> ${html(current?.id || '?')}</div><div><strong>Shortlist:</strong> ${html((current?.shortlist || []).join(', ') || '—')}</div></div></section>
      <div class="warning">“Не знайдено” не означає “вільне”. Перед реєстрацією NameMachine має отримати фінальне підтвердження або користувач має перевірити ресурс на самій платформі.</div>
      <div class="footer">Звіт сформовано NameMachine. Технічні verifier-логи навмисно не включені в клієнтський документ.</div>
    </main></body></html>`;
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

  window.exportClientReportHtml = () => download(buildClientHtml(), 'namemachine-client-report-' + (current?.id || 'session') + '.html', 'text/html;charset=utf-8');
  window.exportClientReportTxt = () => download(buildClientTxt(), 'namemachine-client-report-' + (current?.id || 'session') + '.txt', 'text/plain;charset=utf-8');
  window.clientReportTxt = buildClientTxt;
  window.emailClientReport = () => {
    const report = buildClientTxt();
    const recipient = window.prompt('На який email підготувати звіт?');
    if (recipient === null) return;
    const email = clean(recipient, 180);
    if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      document.getElementById('status').textContent = 'Email виглядає некоректно.';
      return;
    }
    const subject = 'NameMachine — ' + clean(current?.title || 'підсумковий звіт', 90);
    const body = report.length > 12000 ? report.slice(0, 12000) + '\n\n[Повний звіт можна завантажити з NameMachine.]' : report;
    document.getElementById('saveMenu')?.classList.remove('open');
    window.location.href = 'mailto:' + encodeURIComponent(email) + '?subject=' + encodeURIComponent(subject) + '&body=' + encodeURIComponent(body);
  };
})();
