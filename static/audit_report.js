/* NameMachine report v4.
 *
 * Default export is a concise, reusable session report. The full verifier ledger
 * remains available as a separate technical audit. All displayed times share one
 * clock: T+ from session creation. Email uses the device mail composer; no server
 * mail provider or hidden delivery claim is involved.
 */
(() => {
  const CONFLICT = new Set(['taken', 'reserved', 'invalid']);
  const CONFIRMED = new Set(['claimable', 'purchasable']);
  const PROMISING = new Set(['not_found']);
  const RESOURCE_ORDER = ['com', 'instagram', 'telegram', 'tiktok', 'youtube', 'facebook', 'x'];
  const FEEDBACK_TYPES = new Set(['feedback_change', 'comment_change', 'shortlist_change', 'direction_change']);
  let cachedJobs = [];

  const nowIso = () => new Date().toISOString();
  const clean = (value, limit = 600) => String(value ?? '').replace(/\s+/g, ' ').trim().slice(0, limit);
  const sessionStart = () => current?.created || null;

  function formatDuration(ms) {
    if (!Number.isFinite(Number(ms))) return '?';
    const total = Math.max(0, Math.floor(Number(ms) / 1000));
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    return (h ? String(h).padStart(2, '0') + ':' : '') + String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
  }

  function tplus(timestamp) {
    const base = Date.parse(sessionStart() || '');
    const point = Date.parse(timestamp || '');
    return Number.isFinite(base) && Number.isFinite(point) ? 'T+' + formatDuration(point - base) : 'T+?';
  }

  function sessionElapsed(end = nowIso()) {
    const base = Date.parse(sessionStart() || '');
    const point = Date.parse(end || '');
    return Number.isFinite(base) && Number.isFinite(point) ? formatDuration(point - base) : '?';
  }

  function statusOf(payload) {
    const value = String(payload?.status || 'unknown');
    return value === 'available' ? 'unknown' : value;
  }

  function resourcesForRow(row) {
    const availability = row?.availability && typeof row.availability === 'object' ? row.availability : {};
    return Object.keys(availability).sort((a, b) => {
      const ai = RESOURCE_ORDER.indexOf(a), bi = RESOURCE_ORDER.indexOf(b);
      if (ai !== -1 || bi !== -1) return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
      return a.localeCompare(b);
    });
  }

  function allHistoricalResources(rows) {
    const seen = new Set();
    for (const row of rows || []) resourcesForRow(row).forEach(key => seen.add(key));
    return RESOURCE_ORDER.filter(key => seen.has(key)).concat([...seen].filter(key => !RESOURCE_ORDER.includes(key)).sort());
  }

  function classifyRow(row, required = null) {
    const explicit = String(row?.bundle_state || '');
    if (['confirmed', 'promising', 'conflict', 'unresolved'].includes(explicit)) return explicit;
    const resources = Array.isArray(required) && required.length ? required : resourcesForRow(row);
    if (!resources.length) return 'unresolved';
    const statuses = resources.map(key => statusOf(row?.availability?.[key]));
    if (statuses.some(value => CONFLICT.has(value))) return 'conflict';
    if (statuses.every(value => CONFIRMED.has(value))) return 'confirmed';
    if (statuses.every(value => CONFIRMED.has(value) || PROMISING.has(value)) && statuses.some(value => PROMISING.has(value))) return 'promising';
    return 'unresolved';
  }

  function summarizeRows(rows, required = null) {
    const out = { total: 0, confirmed: 0, promising: 0, conflict: 0, unresolved: 0 };
    for (const row of rows || []) {
      out.total += 1;
      const state = classifyRow(row, required);
      out[state] = (out[state] || 0) + 1;
    }
    out.collision_rate = out.total ? Math.round(out.conflict / out.total * 1000) / 10 : 0;
    return out;
  }

  function rowsForRun(runId) {
    return runId ? (current?.results || []).filter(row => row?.run_id === runId) : [];
  }

  function feedbackState(name) {
    return typeof sessionFeedback === 'function' ? sessionFeedback(name) : (current?.feedback?.[String(name || '').toLowerCase()] || { vote: 0, comment: '' });
  }

  function feedbackLabel(value) {
    const vote = Number(value?.vote || 0);
    return vote > 0 ? 'LIKE' : vote < 0 ? 'DISLIKE' : 'NO VOTE';
  }

  function compactResourceState(row) {
    const parts = [];
    for (const key of resourcesForRow(row)) {
      const payload = row?.availability?.[key] || {};
      const status = statusOf(payload);
      const label = typeof uiState === 'function' ? uiState(payload).label : status;
      parts.push(`${labels?.[key] || key}=${label}`);
    }
    return parts.join(' · ') || 'evidence відсутнє';
  }

  function candidateDisplay(row) {
    const fb = feedbackState(row?.name);
    const markers = [];
    if (Number(fb?.vote) > 0) markers.push('👍');
    if (Number(fb?.vote) < 0) markers.push('👎');
    if ((current?.shortlist || []).includes(row?.name)) markers.push('★');
    if ((current?.directionAnchors || []).includes(row?.name)) markers.push('↗');
    return `${markers.length ? markers.join('') + ' ' : ''}${row?.name || '?'} — ${compactResourceState(row)}${fb?.comment ? ' · «' + clean(fb.comment, 180) + '»' : ''}`;
  }

  function activity() {
    return Array.isArray(current?.activityLog) ? current.activityLog : [];
  }

  function firstWorkerAckAfter(event) {
    const eventAt = Date.parse(event?.at || '');
    if (!Number.isFinite(eventAt)) return null;
    return activity().find(candidate => {
      if (candidate?.type !== 'worker_feedback_applied') return false;
      if (event?.job_id && candidate?.job_id && event.job_id !== candidate.job_id) return false;
      const at = Date.parse(candidate?.at || '');
      return Number.isFinite(at) && at >= eventAt;
    }) || null;
  }

  function eventDescription(event) {
    const d = event?.details || {};
    switch (event?.type) {
      case 'feedback_change': return `${Number(d.vote) > 0 ? '👍 LIKE' : Number(d.vote) < 0 ? '👎 DISLIKE' : 'vote cleared'} · ${d.name || '?'}${d.comment ? ' · «' + clean(d.comment, 160) + '»' : ''}`;
      case 'comment_change': return `коментар · ${d.name || '?'} · «${clean(d.comment, 180) || 'видалено'}»`;
      case 'shortlist_change': return `${d.selected ? '★ додано в кандидати' : '★ прибрано з кандидатів'} · ${d.name || '?'}`;
      case 'direction_change': return `${d.selected ? '↗ взято за напрям' : '↗ прибрано з напряму'} · ${d.name || '?'}`;
      case 'resource_change': return `ресурси → ${(d.resources || []).map(key => labels?.[key] || key).join(', ') || 'none'}`;
      case 'prompt_change': return `змінено запит → ${clean(d.prompt, 260)}`;
      case 'job_started': return `великий пошук запущено · target=${d.target || '?'} · ${(d.resources || []).map(key => labels?.[key] || key).join(', ')}`;
      case 'cancel_requested': return `запит на зупинку великого пошуку`;
      case 'foreground_start_clicked': return `звичайний пошук запущено`;
      case 'foreground_stop_clicked': return `звичайний пошук зупинено`;
      case 'large_target_change': return `ціль великого пошуку → ${d.target || '?'}`;
      case 'job_poll_error': return `помилка polling · ${clean(d.message || '', 180)}`;
      case 'job_start_error': return `помилка запуску · ${clean(d.message || '', 180)}`;
      default: return clean(JSON.stringify(d || {}), 300);
    }
  }

  async function fetchJobsForReport() {
    const creds = current?.serverSession;
    if (!creds?.id || !creds?.token) return [];
    try {
      const response = await fetch('/api/sessions/' + encodeURIComponent(creds.id) + '/search-jobs?limit=100', {
        headers: { 'X-NameMachine-Session-Token': creds.token },
      });
      if (!response.ok) return [];
      const payload = await response.json();
      cachedJobs = Array.isArray(payload?.jobs) ? payload.jobs : [];
      return cachedJobs;
    } catch (_) {
      return [];
    }
  }

  function resourceAggregate(rows) {
    const out = {};
    for (const row of rows || []) {
      for (const key of resourcesForRow(row)) {
        out[key] ||= {};
        const status = statusOf(row?.availability?.[key]);
        out[key][status] = (out[key][status] || 0) + 1;
      }
    }
    return out;
  }

  function feedbackCounts() {
    const entries = Object.entries(current?.feedback || {}).filter(([, value]) => value?.vote || value?.comment);
    return {
      entries,
      likes: entries.filter(([, value]) => Number(value?.vote) > 0).length,
      dislikes: entries.filter(([, value]) => Number(value?.vote) < 0).length,
      comments: entries.filter(([, value]) => clean(value?.comment || '')).length,
    };
  }

  function topRowsByState(state, limit = 20) {
    return (current?.results || [])
      .filter(row => classifyRow(row) === state)
      .sort((a, b) => (Number(b?.bundle_score) || 0) - (Number(a?.bundle_score) || 0) || (Number(b?.received_seq) || 0) - (Number(a?.received_seq) || 0))
      .slice(0, limit);
  }

  function selectedRows() {
    const wanted = new Set([
      ...(current?.shortlist || []).map(value => String(value).toLowerCase()),
      ...(current?.directionAnchors || []).map(value => String(value).toLowerCase()),
      ...Object.entries(current?.feedback || {}).filter(([, value]) => Number(value?.vote) > 0).map(([name]) => String(name).toLowerCase()),
    ]);
    return (current?.results || []).filter(row => wanted.has(String(row?.name || '').toLowerCase()));
  }

  function appendCandidateCategory(lines, title, rows, limit = 20) {
    lines.push(title);
    if (!rows.length) lines.push('- немає');
    rows.slice(0, limit).forEach(row => lines.push('- ' + candidateDisplay(row)));
    if (rows.length > limit) lines.push(`- …ще ${rows.length - limit} у технічному аудиті`);
    lines.push('');
  }

  function buildCompactReport(jobs = cachedJobs) {
    const generated = nowIso();
    const rows = current?.results || [];
    const summary = summarizeRows(rows);
    const fb = feedbackCounts();
    const prompts = current?.promptHistory || [];
    const latestPrompt = clean(prompts.at(-1)?.text || document.getElementById('prompt')?.value || '', 900);
    const currentResources = typeof selectedResources === 'function' ? selectedResources() : (current?.resources || []);
    const historicalResources = allHistoricalResources(rows);
    const totalBatches = (jobs || []).reduce((sum, job) => sum + (Number(job?.attempted_batches) || 0), 0);
    const lines = [
      'NameMachine SESSION REPORT v4',
      '',
      `Назва сесії: ${current?.title || 'Нова сесія'}`,
      `Session ID: ${current?.id || '?'}`,
      `Початок: ${current?.created || '?'}`,
      `Звіт: ${generated}`,
      `Загальний час від початку сесії: ${sessionElapsed(generated)}`,
      '',
      '1. ПІДСУМОК',
      `- Що шукали: ${latestPrompt || 'не зафіксовано'}`,
      `- Виконано: ${summary.total} кандидатів · ${(jobs || []).length} background job(s) · ${totalBatches} background batch(es)` ,
      `- Результат: підтверджені=${summary.confirmed} · перспективні=${summary.promising} · конфлікти=${summary.conflict} · невизначені=${summary.unresolved}`,
      `- Частка жорстких конфліктів: ${summary.collision_rate}%`,
      `- Фідбек: 👍 ${fb.likes} · 👎 ${fb.dislikes} · коментарів ${fb.comments} · shortlist ${(current?.shortlist || []).length} · напрямів ${(current?.directionAnchors || []).length}`,
      `- Перевірені протягом сесії ресурси: ${historicalResources.map(key => labels?.[key] || key).join(', ') || 'немає'}`,
      `- Поточні вибрані ресурси: ${currentResources.map(key => labels?.[key] || key).join(', ') || 'немає'}`,
    ];
    if (!summary.confirmed && !summary.promising) lines.push('- Підсумок пошуку: підтверджених або перспективних результатів поки не знайдено.');
    else lines.push(`- Підсумок пошуку: є ${summary.confirmed + summary.promising} кандидат(и), які варто переглянути першими.`);
    lines.push('');

    lines.push('2. ЩО ШУКАЛИ');
    if (!prompts.length) lines.push('- історія запитів відсутня');
    prompts.forEach((entry, index) => lines.push(`${index + 1}. ${tplus(entry?.at)} · ${clean(entry?.text || '', 900)}`));
    lines.push('');

    appendCandidateCategory(lines, '3. ВИБРАНЕ КОРИСТУВАЧЕМ', selectedRows(), 25);
    appendCandidateCategory(lines, '4. ПІДТВЕРДЖЕНІ РЕЗУЛЬТАТИ', topRowsByState('confirmed', 25), 25);
    appendCandidateCategory(lines, '5. ПЕРСПЕКТИВНІ РЕЗУЛЬТАТИ', topRowsByState('promising', 25), 25);

    lines.push('6. ДІЇ КОРИСТУВАЧА І РЕАКЦІЯ WORKER');
    const userEvents = activity().filter(event => FEEDBACK_TYPES.has(event?.type));
    if (!userEvents.length) lines.push('- змін фідбеку під час сесії не зафіксовано');
    userEvents.forEach(event => {
      const ack = firstWorkerAckAfter(event);
      let line = `- ${tplus(event?.at)} · ${eventDescription(event)}`;
      if (ack) line += ` · worker прочитав ${tplus(ack?.at)} (batch ${ack?.details?.applied_batch || '?'})`;
      else if (event?.job_id) line += ' · worker ACK ще не зафіксовано';
      lines.push(line);
    });
    lines.push('');

    lines.push('7. ХІД ПОШУКУ');
    if (!(jobs || []).length) lines.push('- background jobs не знайдено у live server state');
    (jobs || []).forEach((job, index) => {
      const required = Array.isArray(job?.required_resources) && job.required_resources.length ? job.required_resources : (job?.resources || []);
      const jobRows = rowsForRun(job?.run_id);
      const s = summarizeRows(jobRows, required);
      const start = job?.started_at || job?.created_at;
      const end = job?.finished_at || (['completed', 'cancelled', 'failed'].includes(job?.state) ? job?.updated_at : null);
      lines.push(`- JOB ${index + 1}: ${tplus(start)} → ${end ? tplus(end) : 'зараз'} · ${job?.state || 'unknown'} · ${job?.delivered_count || 0}/${job?.target_count || 0} · batches=${job?.attempted_batches || 0}/${job?.max_batches || '?'} · confirmed=${s.confirmed} promising=${s.promising} conflict=${s.conflict} unresolved=${s.unresolved}${job?.stop_reason ? ' · stop=' + job.stop_reason : ''}${job?.error_message ? ' · error=' + clean(job.error_message, 180) : ''}`);
    });
    lines.push('');

    lines.push('8. СТАТИСТИКА ПО РЕСУРСАХ');
    const aggregate = resourceAggregate(rows);
    if (!Object.keys(aggregate).length) lines.push('- немає збережених перевірок');
    allHistoricalResources(rows).forEach(resource => {
      const counts = aggregate[resource] || {};
      const body = Object.keys(counts).sort().map(status => `${status}=${counts[status]}`).join(' · ');
      lines.push(`- ${labels?.[resource] || resource}: ${body || 'немає'}`);
    });
    lines.push('');

    lines.push('9. ДАНІ ДЛЯ ПРОДОВЖЕННЯ РОБОТИ');
    lines.push(`- Session ID: ${current?.id || '?'}`);
    lines.push(`- Останній запит: ${latestPrompt || '—'}`);
    lines.push(`- Поточні ресурси: ${currentResources.map(key => labels?.[key] || key).join(', ') || '—'}`);
    lines.push(`- Shortlist: ${(current?.shortlist || []).join(', ') || '—'}`);
    lines.push(`- Напрями: ${(current?.directionAnchors || []).join(', ') || '—'}`);
    const liked = fb.entries.filter(([, value]) => Number(value?.vote) > 0).map(([name]) => name);
    const disliked = fb.entries.filter(([, value]) => Number(value?.vote) < 0).map(([name]) => name);
    lines.push(`- Likes: ${liked.join(', ') || '—'}`);
    lines.push(`- Dislikes: ${disliked.join(', ') || '—'}`);
    const comments = fb.entries.filter(([, value]) => clean(value?.comment || '')).map(([name, value]) => `${name}: «${clean(value.comment, 180)}»`);
    lines.push(`- Коментарі: ${comments.join(' | ') || '—'}`);
    lines.push('', 'Примітка: UNKNOWN/«не вдалося підтвердити» не означає «вільне». Повний технічний ledger з source/method/confidence доступний окремим експортом «Технічний аудит TXT».');
    return lines.join('\n');
  }

  function batchGroups(rows, required) {
    const groups = new Map();
    for (const row of rows || []) {
      const batch = Number(row?.batch_number) || 0;
      if (!groups.has(batch)) groups.set(batch, []);
      groups.get(batch).push(row);
    }
    return [...groups.entries()].sort((a, b) => a[0] - b[0]).map(([batch, batchRows]) => ({ batch, rows: batchRows, summary: summarizeRows(batchRows, required) }));
  }

  function buildTechnicalAudit(jobs = cachedJobs) {
    const lines = [buildCompactReport(jobs), '', '', '===== TECHNICAL APPENDIX =====', ''];
    lines.push('A. BACKGROUND JOBS / BATCHES');
    (jobs || []).forEach((job, index) => {
      const required = Array.isArray(job?.required_resources) && job.required_resources.length ? job.required_resources : (job?.resources || []);
      const rows = rowsForRun(job?.run_id);
      lines.push(`JOB ${index + 1} · id=${job?.id || '?'} · run=${job?.run_id || '?'} · state=${job?.state || '?'} · target=${job?.target_count || 0} · delivered=${job?.delivered_count || 0} · stop=${job?.stop_reason || '—'} · error=${clean(job?.error_message || '—', 220)}`);
      for (const group of batchGroups(rows, required)) {
        const first = group.rows.map(row => row?.received_at).filter(Boolean).sort()[0] || null;
        lines.push(`  batch ${group.batch} · ${first ? tplus(first) : 'T+?'} · n=${group.summary.total} · confirmed=${group.summary.confirmed} · promising=${group.summary.promising} · conflict=${group.summary.conflict} · unresolved=${group.summary.unresolved} · collision=${group.summary.collision_rate}%`);
        lines.push(`    names: ${group.rows.map(row => row?.name).filter(Boolean).join(', ')}`);
      }
    });
    lines.push('');

    lines.push('B. PROCESS TIMELINE');
    const processTypes = new Set(['resource_change', 'prompt_change', 'job_started', 'cancel_requested', 'foreground_start_clicked', 'foreground_stop_clicked', 'large_target_change', 'job_poll_error', 'job_start_error', 'feedback_change', 'comment_change', 'shortlist_change', 'direction_change', 'worker_feedback_applied']);
    const events = activity().filter(event => processTypes.has(event?.type));
    if (!events.length) lines.push('- none');
    events.forEach(event => {
      const details = event?.type === 'worker_feedback_applied'
        ? `worker snapshot · batch=${event?.details?.applied_batch || '?'} · signals=${event?.details?.feedback_count || 0}`
        : eventDescription(event);
      lines.push(`- ${tplus(event?.at)} · ${event?.type || '?'} · job=${event?.job_id || '—'} · ${details}`);
    });
    lines.push('');

    lines.push('C. FULL CANDIDATE LEDGER — NEWEST FIRST');
    const rows = [...(current?.results || [])].sort((a, b) => (Number(b?.received_seq) || 0) - (Number(a?.received_seq) || 0));
    if (!rows.length) lines.push('- none');
    rows.forEach(row => {
      const fb = feedbackState(row?.name);
      lines.push(`- ${row?.name || '?'} · ${tplus(row?.received_at)} · run=${row?.run_id || '?'} · seq=${row?.received_seq || '?'} · batch=${row?.batch_number || '?'} · family=${row?.family || '?'} · bundle=${row?.bundle_state || classifyRow(row)} · score=${Number(row?.bundle_score) || 0}${fb?.vote || fb?.comment ? ' · feedback=' + feedbackLabel(fb) + (fb?.comment ? ':«' + clean(fb.comment, 180) + '»' : '') : ''}`);
      for (const resource of resourcesForRow(row)) {
        const payload = row?.availability?.[resource] || {};
        lines.push(`    ${labels?.[resource] || resource}: raw=${statusOf(payload)} · source=${payload?.source || '?'} · method=${payload?.method || '?'} · confidence=${payload?.confidence == null ? '?' : payload.confidence} · detail=${clean(payload?.detail || '', 280)}`);
      }
    });
    return lines.join('\n');
  }

  function downloadText(text, filename) {
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    document.getElementById('saveMenu')?.classList.remove('open');
  }

  function reportSubject() {
    const title = clean(current?.title || 'NameMachine session', 80);
    return `NameMachine — ${title}`;
  }

  function emailBody(report) {
    const max = 12000;
    if (report.length <= max) return report;
    return report.slice(0, max) + '\n\n[Звіт скорочено для email. Повну версію завантаж через «Звіт TXT».]';
  }

  function recordExtraControls() {
    document.getElementById('startBtn')?.addEventListener('click', () => {
      setTimeout(() => {
        if (!current) return;
        current.activityLog ||= [];
        current.activityLog.push({ at: nowIso(), type: 'foreground_start_clicked', job_id: current?.backgroundSearch?.id || null, details: {} });
        write(SESSION_KEY, current);
      }, 0);
    });
    document.getElementById('stopBtn')?.addEventListener('click', () => {
      if (!current) return;
      current.activityLog ||= [];
      current.activityLog.push({ at: nowIso(), type: 'foreground_stop_clicked', job_id: current?.backgroundSearch?.id || null, details: {} });
      write(SESSION_KEY, current);
    });
    document.addEventListener('change', event => {
      if (event.target?.id !== 'largeSearchTarget' || !current) return;
      current.activityLog ||= [];
      current.activityLog.push({ at: nowIso(), type: 'large_target_change', job_id: current?.backgroundSearch?.id || null, details: { target: Number(event.target.value) || null } });
      write(SESSION_KEY, current);
    });
  }

  window.sessionTxt = () => buildCompactReport(cachedJobs);

  window.exportTxt = async function exportReadableSessionReport() {
    const jobs = await fetchJobsForReport();
    downloadText(buildCompactReport(jobs), 'namemachine-report-v4-' + (current?.id || 'session') + '.txt');
  };

  window.exportTechnicalAudit = async function exportTechnicalAudit() {
    const jobs = await fetchJobsForReport();
    downloadText(buildTechnicalAudit(jobs), 'namemachine-technical-audit-' + (current?.id || 'session') + '.txt');
  };

  window.emailReport = async function emailReport() {
    const jobs = await fetchJobsForReport();
    const report = buildCompactReport(jobs);
    const recipient = window.prompt('На який email підготувати звіт?');
    if (recipient === null) return;
    const email = clean(recipient, 180);
    if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      document.getElementById('status').textContent = 'Email виглядає некоректно.';
      return;
    }
    const href = 'mailto:' + encodeURIComponent(email) + '?subject=' + encodeURIComponent(reportSubject()) + '&body=' + encodeURIComponent(emailBody(report));
    document.getElementById('saveMenu')?.classList.remove('open');
    window.location.href = href;
  };

  recordExtraControls();
  void fetchJobsForReport();
})();
