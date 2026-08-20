/* NameMachine search-loop reliability overlay.
 *
 * 1) Likes/dislikes/comments steer the next generation only inside the same
 *    search intent, so an older project cannot leak semantic roots into a new one.
 * 2) Every checked candidate stays visible; strict green remains strict.
 * 3) TXT reports carry direct profile URLs, observed Browser Eye identity and a
 *    compact activity timeline so a human can re-check exactly what happened.
 */
(() => {
  const RESOURCE_ORDER = ['com', 'instagram', 'telegram', 'tiktok', 'youtube', 'facebook', 'x'];
  const HARD_CONFLICT = new Set(['taken', 'reserved', 'invalid']);
  const installed = { feedback: false, searchContext: false, report: false, ui: false };

  const clean = (value, limit = 1000) => String(value ?? '').replace(/\s+/g, ' ').trim().slice(0, limit);
  const normPrompt = value => clean(value, 600).toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
  const promptTokens = value => new Set(normPrompt(value).split(/\s+/).filter(Boolean));

  function sameIntent(left, right) {
    const a = normPrompt(left), b = normPrompt(right);
    if (!a || !b) return false;
    if (a === b) return true;
    if (Math.min(a.length, b.length) < 6) return false;
    const aTokens = promptTokens(a), bTokens = promptTokens(b);
    const union = new Set([...aTokens, ...bTokens]);
    let shared = 0;
    aTokens.forEach(token => { if (bTokens.has(token)) shared += 1; });
    const overlap = union.size ? shared / union.size : 0;
    // Conservative on purpose: changing the subject starts a fresh semantic loop.
    return overlap >= 0.72;
  }

  function activePrompt() {
    return clean(document.getElementById('prompt')?.value || current?.promptHistory?.at?.(-1)?.text || '', 600);
  }

  function backgroundPromptForRun(runId, jobId = '') {
    const runKey = String(runId || '');
    const jobKey = String(jobId || '');
    if (!runKey && !jobKey) return '';
    const log = current?.activityLog || [];
    for (let index = log.length - 1; index >= 0; index -= 1) {
      const item = log[index];
      if (!['job_started', 'availability_hunter_started'].includes(item?.type)) continue;
      const details = item?.details || {};
      const runMatches = runKey && String(details.run_id || '') === runKey;
      const jobMatches = jobKey && String(item?.job_id || '') === jobKey;
      if (!runMatches && !jobMatches) continue;
      const prompt = clean(details.prompt || '', 600);
      if (prompt) return prompt;
    }
    return '';
  }

  function intentRunIds(prompt = activePrompt()) {
    const ids = new Set();
    for (const run of current?.runs || []) {
      if (run?.id && sameIntent(run?.prompt || '', prompt)) ids.add(String(run.id));
    }
    // backgroundSearch itself intentionally stores compact job metadata. Resolve
    // the originating prompt from its immutable activity event; never assume that
    // a missing old prompt means "same as what is currently in textarea".
    const bg = current?.backgroundSearch;
    const bgPrompt = bg?.run_id ? backgroundPromptForRun(bg.run_id, bg.id) : '';
    if (bg?.run_id && bgPrompt && sameIntent(bgPrompt, prompt)) ids.add(String(bg.run_id));
    return ids;
  }

  function intentRows(prompt = activePrompt()) {
    const ids = intentRunIds(prompt);
    if (!ids.size) return [];
    return (current?.results || []).filter(row => ids.has(String(row?.run_id || '')));
  }

  function intentNames(prompt = activePrompt()) {
    return new Set(intentRows(prompt).map(row => String(row?.name || '').toLowerCase()).filter(Boolean));
  }

  function intentFeedback(prompt = activePrompt()) {
    const allowed = intentNames(prompt);
    const rows = new Map(intentRows(prompt).map(row => [String(row?.name || '').toLowerCase(), row]));
    const liked = [], disliked = [], feedbackRows = [];
    for (const [name, fb] of Object.entries(current?.feedback || {})) {
      const key = String(name).toLowerCase();
      if (!allowed.has(key)) continue;
      if (Number(fb?.vote) === 1) liked.push(name);
      if (Number(fb?.vote) === -1) disliked.push(name);
      if (Number(fb?.vote) || clean(fb?.comment || '')) {
        feedbackRows.push({
          name,
          vote: Number(fb?.vote) || 0,
          comment: clean(fb?.comment || '', 300),
          family: rows.get(key)?.family || 'unknown',
        });
      }
    }
    const shortlist = (current?.shortlist || []).filter(name => allowed.has(String(name).toLowerCase()));
    const anchors = (current?.directionAnchors || []).filter(name => allowed.has(String(name).toLowerCase()));
    return { liked, disliked, feedbackRows, shortlist, anchors, rows: [...rows.values()] };
  }

  function installFeedbackScope() {
    if (installed.feedback || typeof buildPreferences !== 'function' || typeof adaptiveContext !== 'function') return;
    buildPreferences = function intentScopedPreferences() {
      const scoped = intentFeedback();
      return {
        liked: scoped.liked.slice(-20),
        disliked: scoped.disliked.slice(-20),
        reasons: {},
        feedback: scoped.feedbackRows.slice(-80),
        direction_anchors: scoped.anchors.slice(-20),
        shortlist: scoped.shortlist.slice(-20),
      };
    };
    adaptiveContext = function intentScopedAdaptiveContext(batchNumber) {
      const scoped = intentFeedback();
      const rows = scoped.rows;
      const successful = [
        ...scoped.anchors,
        ...scoped.shortlist,
        ...scoped.liked,
        ...rows.filter(row => typeof allGreen === 'function' && allGreen(row)).map(row => row.name),
      ];
      return {
        batch_number: batchNumber,
        exclude_names: rows.map(row => row.name).filter(Boolean).slice(-100),
        conflict_names: rows.filter(row => typeof hasConflict === 'function' && hasConflict(row)).map(row => row.name).slice(-40),
        successful_names: [...new Set(successful)].slice(-20),
      };
    };
    installed.feedback = true;
  }

  function installSearchContextScope() {
    if (installed.searchContext || typeof window.nameMachineSearchContext !== 'function') return;
    const base = window.nameMachineSearchContext;
    window.nameMachineSearchContext = function scopedSearchContext(prompt) {
      const value = { ...base(prompt) };
      const scoped = intentFeedback(prompt || activePrompt());
      let guidance = clean(value.guidance || '', 500);
      guidance = guidance.replace(/(?:\s*\|\s*)?Орієнтуйся на:\s*[^|]+/gi, '').trim().replace(/^\|+|\|+$/g, '').trim();
      if (scoped.anchors.length) {
        guidance = [guidance, 'Орієнтуйся на: ' + scoped.anchors.slice(-5).join(', ')].filter(Boolean).join(' | ');
      }
      value.guidance = guidance.slice(0, 500);
      return value;
    };
    installed.searchContext = true;
  }

  function requestedUrl(resource, name) {
    const n = encodeURIComponent(String(name || '').toLowerCase());
    if (resource === 'com') return `https://${n}.com`;
    if (resource === 'instagram') return `https://www.instagram.com/${n}/`;
    if (resource === 'telegram') return `https://t.me/${n}`;
    if (resource === 'tiktok') return `https://www.tiktok.com/@${n}`;
    if (resource === 'youtube') return `https://www.youtube.com/@${n}`;
    if (resource === 'facebook') return `https://www.facebook.com/${n}`;
    if (resource === 'x') return `https://x.com/${n}`;
    return '';
  }

  function statusOf(payload) {
    const status = String(payload?.status || 'unknown');
    return status === 'available' ? 'unknown' : status;
  }

  function browserLine(row, resource) {
    const meta = row?.browser_verification?.[resource];
    if (!meta || typeof meta !== 'object') return '';
    const parts = [];
    for (const [label, eye] of [['A', meta.eye_a], ['B', meta.eye_b]]) {
      if (!eye || typeof eye !== 'object') continue;
      const bits = [
        `Eye${label}=${clean(eye.signal || 'unknown', 30)}`,
        eye.observed_username ? `observed=@${clean(eye.observed_username, 80)}` : '',
        eye.username && !eye.observed_username ? `username=@${clean(eye.username, 80)}` : '',
        eye.final_url ? `final=${clean(eye.final_url, 500)}` : '',
        eye.identity_sources?.length ? `identity=${eye.identity_sources.join('+')}` : '',
      ].filter(Boolean);
      parts.push(bits.join(' '));
    }
    if (meta.search?.exact_profile_hits) parts.push(`SearchEye exact_hits=${meta.search.exact_profile_hits}`);
    return parts.join(' | ');
  }

  function candidateAudit(row) {
    const name = row?.name || '?';
    const availability = row?.availability && typeof row.availability === 'object' ? row.availability : {};
    const resources = RESOURCE_ORDER.filter(key => key in availability || (current?.resources || []).includes(key));
    const lines = [`- ${name}`];
    for (const resource of resources) {
      const payload = availability[resource] || {};
      const direct = requestedUrl(resource, name);
      const facts = [
        `${resource}: ${statusOf(payload)}`,
        `requested=${direct}`,
        payload.url && payload.url !== direct ? `provider_url=${clean(payload.url, 500)}` : '',
        payload.source ? `source=${clean(payload.source, 80)}` : '',
        payload.method ? `method=${clean(payload.method, 80)}` : '',
      ].filter(Boolean).join(' | ');
      lines.push(`    ${facts}`);
      const browser = browserLine(row, resource);
      if (browser) lines.push(`      ${browser}`);
    }
    return lines.join('\n');
  }

  function timelineLines() {
    const lines = [];
    for (const run of current?.runs || []) {
      lines.push(`- RUN ${clean(run?.id || '?', 100)} | prompt=${clean(run?.prompt || '', 300)} | status=${clean(run?.status || 'unknown', 40)} | ${clean(run?.started || '', 40)} → ${clean(run?.finished || '', 40) || '...'}`);
    }
    const activity = (current?.activityLog || []).slice(-120);
    for (const item of activity) {
      const d = item?.details || {};
      const details = [
        d.prompt ? `prompt=${clean(d.prompt, 180)}` : '',
        d.resources ? `resources=${Array.isArray(d.resources) ? d.resources.join(',') : clean(d.resources, 120)}` : '',
        d.state ? `state=${clean(d.state, 40)}` : '',
        Number.isFinite(Number(d.delivered)) ? `delivered=${Number(d.delivered)}` : '',
        Number.isFinite(Number(d.added)) ? `added=${Number(d.added)}` : '',
        d.name ? `name=${clean(d.name, 80)}` : '',
        d.vote !== undefined ? `vote=${d.vote}` : '',
        d.error_type ? `error=${clean(d.error_type, 100)}` : '',
        d.error_message ? `message=${clean(d.error_message, 220)}` : '',
        d.message && !d.error_message ? `message=${clean(d.message, 220)}` : '',
      ].filter(Boolean).join(' | ');
      lines.push(`- ${clean(item?.at || '', 40)} | ${clean(item?.type || 'event', 80)}${details ? ' | ' + details : ''}`);
    }
    return lines.length ? lines : ['- Хронологія ще не зафіксована.'];
  }

  function reliabilityAppendix() {
    const rows = [...(current?.results || [])].sort((a, b) => (Number(b?.received_seq) || 0) - (Number(a?.received_seq) || 0));
    const unresolved = rows.filter(row => {
      const availability = row?.availability || {};
      const statuses = Object.values(availability).map(statusOf);
      return statuses.length && !statuses.some(status => HARD_CONFLICT.has(status)) && !statuses.every(status => status === 'claimable');
    });
    const lines = [
      '',
      '8. ПРЯМІ ЛІНКИ ТА ФАКТИ ПЕРЕВІРКИ',
      '- requested = адреса, яку NameMachine мав перевірити.',
      '- observed/final = те, що реально прочитав Browser Eye. URL без exact identity не є доказом зайнятості.',
    ];
    rows.forEach(row => lines.push(candidateAudit(row)));
    lines.push('', '9. НЕПІДТВЕРДЖЕНІ БЕЗ ЖОРСТКОГО КОНФЛІКТУ');
    if (!unresolved.length) lines.push('- Немає.');
    unresolved.forEach(row => lines.push(`- ${row.name} — залишено у результатах для лайка/дизлайка/коментаря та наступної генерації.`));
    lines.push('', '10. ХРОНОЛОГІЯ ПОШУКУ');
    lines.push(...timelineLines());
    return lines.join('\n');
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

  function installReport() {
    if (installed.report || typeof window.clientReportTxt !== 'function') return;
    const baseBuilder = window.clientReportTxt;
    window.clientReportTxt = () => baseBuilder() + '\n' + reliabilityAppendix();
    window.exportClientReportTxt = () => download(
      window.clientReportTxt(),
      'namemachine-verification-report-' + (current?.id || 'session') + '.txt',
      'text/plain;charset=utf-8',
    );
    window.emailClientReport = () => {
      const report = window.clientReportTxt();
      const recipient = window.prompt('На який email підготувати звіт?');
      if (recipient === null) return;
      const email = clean(recipient, 180);
      if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        document.getElementById('status').textContent = 'Email виглядає некоректно.';
        return;
      }
      const subject = 'NameMachine — ' + clean(current?.title || 'підсумковий звіт', 90);
      const body = report.length > 12000 ? report.slice(0, 12000) + '\n\n[Повний TXT містить усі прямі лінки та хронологію.]' : report;
      window.location.href = 'mailto:' + encodeURIComponent(email) + '?subject=' + encodeURIComponent(subject) + '&body=' + encodeURIComponent(body);
    };
    installed.report = true;
  }

  function latestWorkerError() {
    const log = current?.activityLog || [];
    for (let index = log.length - 1; index >= 0; index -= 1) {
      const item = log[index];
      if (item?.type !== 'job_progress') continue;
      const details = item.details || {};
      if (details.error_type || details.error_message || details.stop_reason === 'worker_error') return details;
    }
    return null;
  }

  function renderWorkerError() {
    const status = document.getElementById('largeSearchStatus');
    const panel = document.getElementById('largeSearchPanel');
    if (!status || !panel) return;
    let detail = panel.querySelector('.nm-worker-error-detail');
    const error = latestWorkerError();
    const shouldShow = /worker_error|помилка/i.test(status.textContent || '') && error;
    if (!shouldShow) {
      detail?.remove();
      return;
    }
    if (!detail) {
      detail = document.createElement('div');
      detail.className = 'nm-worker-error-detail';
      detail.style.cssText = 'grid-column:1/-1;padding:10px 12px;border:1px solid rgba(255,116,108,.35);border-radius:12px;color:var(--bad);font-size:12px;line-height:1.45';
      status.insertAdjacentElement('afterend', detail);
    }
    detail.textContent = `Worker: ${error.error_type || 'error'}${error.error_message ? ' — ' + error.error_message : ''}`;
  }

  async function renderStrictCapabilityNote() {
    const panel = document.getElementById('largeSearchPanel');
    if (!panel || panel.querySelector('.nm-strict-capability-note')) return;
    try {
      const response = await fetch('/api/verification/diagnostics', { cache: 'no-store' });
      if (!response.ok) return;
      const payload = await response.json();
      const caps = payload?.verification_pipeline?.strict_claimability?.resources || {};
      const selected = typeof selectedResources === 'function' ? selectedResources() : (current?.resources || []);
      const unsupported = selected.filter(resource => caps?.[resource] && !caps[resource].can_turn_green);
      if (!unsupported.length) return;
      const note = document.createElement('div');
      note.className = 'nm-strict-capability-note';
      note.style.cssText = 'grid-column:1/-1;color:var(--muted);font-size:12px;line-height:1.45;padding:9px 11px;border:1px solid var(--line);border-radius:12px';
      note.textContent = '100% зелений статус не може бути авторитетно підтверджений для: ' + unsupported.join(', ') + '. Вони все одно проходять перевірку й залишаються у результатах як непідтверджені/перспективні для фідбеку.';
      panel.appendChild(note);
    } catch (_) {}
  }

  function installUi() {
    if (installed.ui) return;
    const observer = new MutationObserver(() => renderWorkerError());
    const panel = document.getElementById('largeSearchPanel');
    if (panel) observer.observe(panel, { subtree: true, childList: true, characterData: true, attributes: true });
    renderWorkerError();
    void renderStrictCapabilityNote();
    installed.ui = true;
  }

  function installAll() {
    installFeedbackScope();
    installSearchContextScope();
    installReport();
    installUi();
    if (!(installed.feedback && installed.searchContext && installed.report && installed.ui)) {
      setTimeout(installAll, 80);
    }
  }

  installAll();
})();
