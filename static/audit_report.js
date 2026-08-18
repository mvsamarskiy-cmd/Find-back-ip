/* NameMachine audit report v3.
 *
 * This layer deliberately does not change generation or verification semantics.
 * It turns the session into an auditable experiment log: every background job is
 * fetched live at export time, user feedback is correlated with worker snapshots,
 * and historical candidates keep the resource evidence that existed when they
 * were checked instead of being reinterpreted through today's checkboxes.
 */
(() => {
  const PROCESS_EVENT_TYPES = new Set([
    'feedback_change', 'comment_change', 'shortlist_change', 'direction_change',
    'resource_change', 'prompt_change', 'job_started', 'job_progress',
    'worker_feedback_applied', 'candidate_batch', 'cancel_requested',
    'job_poll_error', 'job_start_error', 'cancel_error',
    'foreground_start_clicked', 'foreground_stop_clicked', 'large_target_change',
  ]);
  const FEEDBACK_EVENT_TYPES = new Set([
    'feedback_change', 'comment_change', 'shortlist_change', 'direction_change',
  ]);
  const CONFLICT = new Set(['taken', 'reserved', 'invalid']);
  const CONFIRMED = new Set(['claimable', 'purchasable']);
  const PROMISING = new Set(['not_found']);
  const RESOURCE_ORDER = ['com', 'instagram', 'telegram', 'tiktok', 'youtube', 'facebook', 'x'];
  let cachedJobs = [];

  function isoNow() { return new Date().toISOString(); }

  function formatDuration(ms) {
    if (!Number.isFinite(Number(ms))) return '?';
    const total = Math.max(0, Math.floor(Number(ms) / 1000));
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const seconds = total % 60;
    return (hours ? String(hours).padStart(2, '0') + ':' : '') +
      String(minutes).padStart(2, '0') + ':' + String(seconds).padStart(2, '0');
  }

  function elapsedBetween(start, end) {
    const a = Date.parse(start || '');
    const b = Date.parse(end || '');
    return Number.isFinite(a) && Number.isFinite(b) ? formatDuration(b - a) : '?';
  }

  function statusOf(payload) {
    const value = String(payload?.status || 'unknown');
    return value === 'available' ? 'unknown' : value;
  }

  function resourcesForRow(row) {
    const availability = row?.availability && typeof row.availability === 'object' ? row.availability : {};
    const keys = Object.keys(availability);
    return [...keys].sort((a, b) => {
      const ai = RESOURCE_ORDER.indexOf(a), bi = RESOURCE_ORDER.indexOf(b);
      if (ai !== -1 || bi !== -1) return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
      return a.localeCompare(b);
    });
  }

  function classifyRow(row, requiredResources = null) {
    const explicit = String(row?.bundle_state || '');
    if (['confirmed', 'promising', 'conflict', 'unresolved'].includes(explicit)) return explicit;
    const resources = Array.isArray(requiredResources) && requiredResources.length
      ? requiredResources
      : resourcesForRow(row);
    if (!resources.length) return 'unresolved';
    const statuses = resources.map(key => statusOf(row?.availability?.[key]));
    if (statuses.some(value => CONFLICT.has(value))) return 'conflict';
    if (statuses.every(value => CONFIRMED.has(value))) return 'confirmed';
    if (statuses.every(value => CONFIRMED.has(value) || PROMISING.has(value)) && statuses.some(value => PROMISING.has(value))) return 'promising';
    return 'unresolved';
  }

  function summarizeRows(rows, requiredResources = null) {
    const summary = { total: 0, confirmed: 0, promising: 0, conflict: 0, unresolved: 0 };
    for (const row of rows || []) {
      summary.total += 1;
      const state = classifyRow(row, requiredResources);
      summary[state] = (summary[state] || 0) + 1;
    }
    summary.collision_rate = summary.total ? Math.round(summary.conflict / summary.total * 1000) / 10 : 0;
    return summary;
  }

  function rowsForRun(runId) {
    if (!runId) return [];
    return (current?.results || []).filter(row => row?.run_id === runId);
  }

  function batchSummaries(rows, requiredResources) {
    const groups = new Map();
    for (const row of rows || []) {
      const key = Number(row?.batch_number) || 0;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(row);
    }
    return [...groups.entries()].sort((a, b) => a[0] - b[0]).map(([batch, batchRows]) => {
      const summary = summarizeRows(batchRows, requiredResources);
      const times = batchRows.map(row => Date.parse(row?.received_at || '')).filter(Number.isFinite).sort((a, b) => a - b);
      return {
        batch,
        rows: batchRows,
        summary,
        first_at: times.length ? new Date(times[0]).toISOString() : null,
        last_at: times.length ? new Date(times[times.length - 1]).toISOString() : null,
      };
    });
  }

  function resourceStatusAggregate(rows) {
    const result = {};
    for (const row of rows || []) {
      for (const resource of resourcesForRow(row)) {
        if (!result[resource]) result[resource] = {};
        const status = statusOf(row?.availability?.[resource]);
        result[resource][status] = (result[resource][status] || 0) + 1;
      }
    }
    return result;
  }

  function cleanText(value, limit = 500) {
    return String(value ?? '').replace(/\s+/g, ' ').trim().slice(0, limit);
  }

  function feedbackLabel(value) {
    const vote = Number(value?.vote || 0);
    return vote > 0 ? 'LIKE' : vote < 0 ? 'DISLIKE' : 'NO VOTE';
  }

  function activityLog() {
    return Array.isArray(current?.activityLog) ? current.activityLog : [];
  }

  function eventDetails(event) {
    const d = event?.details || {};
    switch (event?.type) {
      case 'feedback_change': return `${d.name || '?'} → ${Number(d.vote) > 0 ? 'LIKE' : Number(d.vote) < 0 ? 'DISLIKE' : 'VOTE CLEARED'}${d.comment ? ' · ' + cleanText(d.comment, 180) : ''}`;
      case 'comment_change': return `${d.name || '?'} · comment=${cleanText(d.comment, 220) || 'cleared'} · vote=${Number(d.vote) || 0}`;
      case 'shortlist_change': return `${d.name || '?'} · shortlist=${Boolean(d.selected)}`;
      case 'direction_change': return `${d.name || '?'} · direction=${Boolean(d.selected)}`;
      case 'resource_change': return `resources=${(d.resources || []).join(', ') || 'none'} · effect=${d.effect || '?'}`;
      case 'prompt_change': return `prompt=${cleanText(d.prompt, 260)} · effect=${d.effect || '?'}`;
      case 'job_started': return `job=${d.id || '?'} target=${d.target || '?'} resources=${(d.resources || []).join(', ')} prompt=${cleanText(d.prompt, 260)}`;
      case 'job_progress': return `state=${d.state || '?'} ${d.delivered || 0}/${d.target || 0} batches=${d.attempted_batches || 0}/${d.max_batches || '?'} reason=${d.stop_reason || '—'}`;
      case 'worker_feedback_applied': return `batch=${d.applied_batch || '?'} signals=${d.feedback_count || 0} likes=${d.liked_count || 0} dislikes=${d.disliked_count || 0} conflicts_learned=${d.conflict_examples || 0} opportunities_learned=${d.opportunity_examples || 0}`;
      case 'candidate_batch': return `+${d.added || 0} names · green=${d.green || 0} promising=${d.promising || 0} conflicts=${d.conflicts || 0} · ${Array.isArray(d.names) ? d.names.slice(0, 8).join(', ') : ''}`;
      case 'foreground_start_clicked': return `prompt=${cleanText(d.prompt, 220)} · resources=${(d.resources || []).join(', ')} · results_before=${d.results_before || 0}`;
      case 'foreground_stop_clicked': return `results_at_click=${d.results_at_click || 0}`;
      case 'large_target_change': return `target=${d.target || '?'}`;
      default: return cleanText(JSON.stringify(d || {}), 500);
    }
  }

  function eventElapsed(event, baseAt) {
    const a = Date.parse(baseAt || '');
    const b = Date.parse(event?.at || '');
    return Number.isFinite(a) && Number.isFinite(b) ? formatDuration(b - a) : '?';
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

  function jobMap(jobs) { return new Map((jobs || []).map(job => [job.id, job])); }

  function firstWorkerAckAfter(event, activity) {
    const eventAt = Date.parse(event?.at || '');
    if (!Number.isFinite(eventAt)) return null;
    return (activity || []).find(candidate => {
      if (candidate?.type !== 'worker_feedback_applied') return false;
      if (event.job_id && candidate.job_id && event.job_id !== candidate.job_id) return false;
      const at = Date.parse(candidate?.at || '');
      return Number.isFinite(at) && at >= eventAt;
    }) || null;
  }

  function firstRowsAfter(rows, timestamp, limit = 8) {
    const pivot = Date.parse(timestamp || '');
    if (!Number.isFinite(pivot)) return [];
    return [...(rows || [])]
      .filter(row => {
        const at = Date.parse(row?.received_at || '');
        return Number.isFinite(at) && at >= pivot;
      })
      .sort((a, b) => Date.parse(a.received_at || '') - Date.parse(b.received_at || ''))
      .slice(0, limit);
  }

  function rowsBefore(rows, timestamp, limit = 20) {
    const pivot = Date.parse(timestamp || '');
    if (!Number.isFinite(pivot)) return [];
    return [...(rows || [])]
      .filter(row => {
        const at = Date.parse(row?.received_at || '');
        return Number.isFinite(at) && at < pivot;
      })
      .sort((a, b) => Date.parse(b.received_at || '') - Date.parse(a.received_at || ''))
      .slice(0, limit)
      .reverse();
  }

  function resourceLine(resource, payload) {
    const confidence = payload?.confidence == null ? '?' : payload.confidence;
    const ui = typeof uiState === 'function' ? uiState(payload).label : statusOf(payload);
    return `    ${labels?.[resource] || resource}: ui=${ui} raw=${statusOf(payload)} source=${payload?.source || '?'} method=${payload?.method || '?'} confidence=${confidence} detail=${cleanText(payload?.detail || '', 300)}`;
  }

  function candidateLine(row) {
    const fb = typeof sessionFeedback === 'function' ? sessionFeedback(row?.name) : { vote: 0, comment: '' };
    const parts = [
      `- ${row?.name || '?'}`,
      `run=${row?.run_id || '?'}`,
      `seq=${row?.received_seq || '?'}`,
      `batch=${row?.batch_number || '?'}`,
      `family=${row?.family || '?'}`,
      `bundle=${row?.bundle_state || classifyRow(row)}`,
      `score=${Number.isFinite(Number(row?.bundle_score)) ? Number(row.bundle_score) : 0}`,
      `received=${row?.received_at || '?'}`,
    ];
    if (fb?.vote || fb?.comment) parts.push(`feedback=${feedbackLabel(fb)}${fb.comment ? ':' + cleanText(fb.comment, 220) : ''}`);
    if (row?.reason) parts.push(`reason=${cleanText(row.reason, 280)}`);
    return parts.join(' | ');
  }

  function appendJob(lines, job, index) {
    const required = Array.isArray(job?.required_resources) && job.required_resources.length ? job.required_resources : job?.resources || [];
    const rows = rowsForRun(job?.run_id);
    const summary = summarizeRows(rows, required);
    const batches = batchSummaries(rows, required);
    const firstAt = rows.map(row => row?.received_at).filter(Boolean).sort()[0] || null;
    const lastAt = rows.map(row => row?.received_at).filter(Boolean).sort().slice(-1)[0] || null;
    const started = job?.started_at || job?.created_at || null;
    const ended = job?.finished_at || (['completed', 'cancelled', 'failed'].includes(job?.state) ? job?.updated_at : null);
    const runtime = job?.preferences?._runtime || {};
    lines.push(
      `JOB ${index + 1}`,
      `- id: ${job?.id || '?'}`,
      `- run_id: ${job?.run_id || '?'}`,
      `- state: ${job?.state || 'unknown'}`,
      `- prompt: ${cleanText(job?.prompt || '', 600)}`,
      `- resources: ${(job?.resources || []).map(key => labels?.[key] || key).join(', ') || 'none'}`,
      `- required_resources: ${required.map(key => labels?.[key] || key).join(', ') || 'none'}`,
      `- target/delivered: ${job?.target_count || 0}/${job?.delivered_count || 0}`,
      `- attempted/max batches: ${job?.attempted_batches || 0}/${job?.max_batches || '?'}`,
      `- created: ${job?.created_at || '?'}`,
      `- started: ${started || '?'}`,
      `- finished: ${ended || 'still running / not recorded'}`,
      `- duration: ${started ? elapsedBetween(started, ended || isoNow()) : '?'}`,
      `- stop_reason: ${job?.stop_reason || '—'}`,
      `- error: ${job?.error_type || '—'}${job?.error_message ? ' · ' + cleanText(job.error_message, 300) : ''}`,
      `- actual rows in local ledger: ${rows.length}`,
      `- confirmed/promising/conflict/unresolved: ${summary.confirmed}/${summary.promising}/${summary.conflict}/${summary.unresolved}`,
      `- hard-collision rate: ${summary.collision_rate}%`,
      `- first candidate: ${firstAt || '—'}${started && firstAt ? ' · T+' + elapsedBetween(started, firstAt) : ''}`,
      `- last candidate: ${lastAt || '—'}${started && lastAt ? ' · T+' + elapsedBetween(started, lastAt) : ''}`,
      `- latest worker feedback snapshot: batch=${runtime.applied_batch || '?'} applied_at=${runtime.applied_at || '—'} signals=${runtime.feedback_count || 0} likes=${runtime.liked_count || 0} dislikes=${runtime.disliked_count || 0} conflicts_learned=${runtime.conflict_examples || 0} opportunities_learned=${runtime.opportunity_examples || 0}`,
    );
    lines.push('  BATCHES');
    if (!batches.length) lines.push('  - no candidate batches recorded locally');
    for (const batch of batches) {
      lines.push(`  - batch ${batch.batch}: n=${batch.summary.total} confirmed=${batch.summary.confirmed} promising=${batch.summary.promising} conflict=${batch.summary.conflict} unresolved=${batch.summary.unresolved} collision=${batch.summary.collision_rate}% first=${batch.first_at || '?'} last=${batch.last_at || '?'}`);
      lines.push(`    names: ${batch.rows.map(row => row.name).filter(Boolean).join(', ')}`);
    }
    lines.push('');
  }

  function appendFeedbackImpact(lines, jobs) {
    const activity = activityLog();
    const jobsById = jobMap(jobs);
    const feedbackEvents = activity.filter(event => FEEDBACK_EVENT_TYPES.has(event?.type));
    lines.push('FEEDBACK IMPACT AUDIT');
    lines.push('Meaning: ACK proves that the worker read the change. Candidate differences after ACK are observations, not proof that the feedback caused a particular name.');
    if (!feedbackEvents.length) {
      lines.push('- no process-affecting feedback events recorded');
      lines.push('');
      return;
    }
    feedbackEvents.forEach((event, index) => {
      const ack = firstWorkerAckAfter(event, activity);
      const job = event.job_id ? jobsById.get(event.job_id) : null;
      const runRows = job ? rowsForRun(job.run_id) : (current?.results || []);
      const before = rowsBefore(runRows, event.at, 20);
      const beforeSummary = summarizeRows(before, job?.required_resources || job?.resources || null);
      lines.push(`CHANGE ${index + 1}: ${event.at || '?'} | ${event.type} | ${eventDetails(event)}`);
      if (!ack) {
        lines.push('- worker reaction: NOT ACKNOWLEDGED YET in the recorded timeline');
      } else {
        const delay = elapsedBetween(event.at, ack.at);
        const afterRows = firstRowsAfter(runRows, ack.at, 20);
        const afterSummary = summarizeRows(afterRows, job?.required_resources || job?.resources || null);
        lines.push(`- worker reaction: ACK at ${ack.at || '?'} · delay=${delay} · applied_batch=${ack.details?.applied_batch || '?'} · signals=${ack.details?.feedback_count || 0}`);
        lines.push(`- 20 candidates before change: n=${beforeSummary.total} conflict=${beforeSummary.conflict} promising=${beforeSummary.promising} confirmed=${beforeSummary.confirmed} collision=${beforeSummary.collision_rate}%`);
        lines.push(`- first candidates after ACK: n=${afterSummary.total} conflict=${afterSummary.conflict} promising=${afterSummary.promising} confirmed=${afterSummary.confirmed} collision=${afterSummary.collision_rate}%`);
        lines.push(`- names after ACK: ${afterRows.length ? afterRows.slice(0, 8).map(row => row.name).join(', ') : 'none recorded yet'}`);
      }
    });
    lines.push('');
  }

  function appendForegroundRuns(lines) {
    const runs = Array.isArray(current?.runs) ? current.runs : [];
    const foreground = runs.filter(run => !run?.background_job_id);
    const backgroundMirrors = runs.filter(run => run?.background_job_id);
    lines.push('FOREGROUND RUNS');
    if (!foreground.length) lines.push('- none');
    foreground.forEach((run, index) => {
      const rows = rowsForRun(run?.id);
      const summary = summarizeRows(rows);
      const metadataDelta = Math.max(0, Number(run?.endResultCount ?? current?.results?.length ?? 0) - Number(run?.startResultCount || 0));
      const flags = [];
      if (String(run?.status) === 'running' && !run?.finished) flags.push('UNFINISHED_METADATA');
      if (!rows.length && metadataDelta === 0) flags.push('NO_NEW_CANDIDATES');
      lines.push(`- RUN ${index + 1} | id=${run?.id || '?'} | recorded_status=${run?.status || 'unknown'} | started=${run?.started || '?'} | finished=${run?.finished || 'not recorded'} | duration=${run?.started ? elapsedBetween(run.started, run.finished || isoNow()) : '?'} | batches=${run?.startBatch || '?'}-${run?.endBatch || '?'} | metadata_results=${run?.startResultCount || 0}-${run?.endResultCount ?? current?.results?.length ?? 0} | actual_rows=${rows.length} | confirmed=${summary.confirmed} promising=${summary.promising} conflict=${summary.conflict} unresolved=${summary.unresolved}${flags.length ? ' | FLAGS=' + flags.join(',') : ''}`);
    });
    lines.push('', 'BACKGROUND RUN MIRRORS IN SESSION METADATA');
    if (!backgroundMirrors.length) lines.push('- none');
    backgroundMirrors.forEach(run => {
      lines.push(`- run_id=${run?.id || '?'} | job_id=${run?.background_job_id || '?'} | status=${run?.status || '?'} | target=${run?.targetCount || '?'} | delivered=${run?.deliveredCount || '?'} | stopReason=${run?.stopReason || '—'}`);
    });
    lines.push('');
  }

  function buildReport(jobs = cachedJobs) {
    const generatedAt = isoNow();
    const allRows = current?.results || [];
    const allSummary = summarizeRows(allRows);
    const sessionStarted = current?.created || null;
    const currentResources = typeof selectedResources === 'function' ? selectedResources() : (current?.resources || []);
    const lines = [
      'NameMachine LIVE AUDIT REPORT v3',
      '',
      `Назва: ${current?.title || 'Нова сесія'}`,
      `Session ID: ${current?.id || '?'}`,
      `Server session ID: ${current?.serverSession?.id || 'not connected'}`,
      `Створено: ${sessionStarted || '?'}`,
      `Звіт сформовано: ${generatedAt}`,
      `Тривалість сесії до звіту: ${sessionStarted ? elapsedBetween(sessionStarted, generatedAt) : '?'}`,
      '',
      'EXECUTIVE SUMMARY',
      `- candidates in ledger: ${allSummary.total}`,
      `- confirmed: ${allSummary.confirmed}`,
      `- promising: ${allSummary.promising}`,
      `- hard conflicts: ${allSummary.conflict}`,
      `- unresolved: ${allSummary.unresolved}`,
      `- overall hard-collision rate: ${allSummary.collision_rate}%`,
      `- current selected resources: ${currentResources.map(key => labels?.[key] || key).join(', ') || 'none'}`,
      `- current prompt: ${cleanText(document.getElementById('prompt')?.value || '', 700)}`,
      `- background jobs fetched live: ${(jobs || []).length}`,
      '',
      'IMPORTANT CONTEXT',
      '- Current checkboxes describe the current UI state only. Historical candidates below are reported using the evidence actually stored on each candidate, so changing from all resources to Telegram does not erase the old .com/Instagram/etc. evidence.',
      '- UNKNOWN and NOT_FOUND remain unresolved/promising evidence; this report never upgrades them to verified availability.',
      '',
      'PROMPT HISTORY',
    ];

    const prompts = current?.promptHistory || [];
    if (!prompts.length) lines.push('- none');
    prompts.forEach((entry, index) => lines.push(`${index + 1}. ${entry?.text || ''} | at=${entry?.at || '?'}`));
    lines.push('');

    lines.push('BACKGROUND JOBS — LIVE SERVER STATE');
    if (!(jobs || []).length) lines.push('- none fetched (no server session, request failed, or no background jobs yet)', '');
    (jobs || []).forEach((job, index) => appendJob(lines, job, index));

    appendFeedbackImpact(lines, jobs || []);

    lines.push('FINAL USER FEEDBACK STATE');
    const feedbackEntries = Object.entries(current?.feedback || {}).filter(([, value]) => value?.vote || value?.comment);
    if (!feedbackEntries.length) lines.push('- none');
    feedbackEntries.forEach(([name, value]) => lines.push(`- ${name}: ${feedbackLabel(value)}${value?.comment ? ' · ' + cleanText(value.comment, 300) : ''}`));
    lines.push('');

    lines.push('RESOURCE STATUS AGGREGATE');
    const aggregate = resourceStatusAggregate(allRows);
    if (!Object.keys(aggregate).length) lines.push('- none');
    RESOURCE_ORDER.filter(key => aggregate[key]).forEach(resource => {
      const counts = aggregate[resource];
      const ordered = Object.keys(counts).sort().map(status => `${status}=${counts[status]}`).join(' ');
      lines.push(`- ${labels?.[resource] || resource}: ${ordered}`);
    });
    Object.keys(aggregate).filter(key => !RESOURCE_ORDER.includes(key)).sort().forEach(resource => {
      const counts = aggregate[resource];
      lines.push(`- ${resource}: ${Object.keys(counts).sort().map(status => `${status}=${counts[status]}`).join(' ')}`);
    });
    lines.push('');

    lines.push('ACTION / REACTION TIMELINE');
    const activity = activityLog().filter(event => PROCESS_EVENT_TYPES.has(event?.type));
    const baseAt = sessionStarted || activity[0]?.at || generatedAt;
    if (!activity.length) lines.push('- no live process events recorded');
    activity.forEach((event, index) => {
      lines.push(`${index + 1}. +${eventElapsed(event, baseAt)} | ${event?.at || '?'} | ${event?.type || '?'} | job=${event?.job_id || '—'} | ${eventDetails(event)}`);
    });
    lines.push('');

    appendForegroundRuns(lines);

    lines.push('CANDIDATE LEDGER — NEWEST FIRST');
    const orderedRows = [...allRows].sort((a, b) => (Number(b?.received_seq) || 0) - (Number(a?.received_seq) || 0));
    if (!orderedRows.length) lines.push('- none');
    orderedRows.forEach(row => {
      lines.push(candidateLine(row));
      const resources = resourcesForRow(row);
      if (!resources.length) lines.push('    evidence: none stored');
      resources.forEach(resource => lines.push(resourceLine(resource, row?.availability?.[resource] || {})));
    });

    lines.push('', 'REPORT INTERPRETATION');
    lines.push('- A worker ACK means the feedback snapshot was consumed before a later generation batch. It does not prove that any specific later name was caused by that feedback.');
    lines.push('- A foreground run marked running without a finish timestamp is reported as unfinished metadata, not asserted to still be executing.');
    lines.push('- Background jobs are fetched live from PostgreSQL-backed job state at export time; foreground browser runs and background jobs are intentionally separated.');
    return lines.join('\n');
  }

  function recordExtraControls() {
    document.getElementById('startBtn')?.addEventListener('click', () => {
      setTimeout(() => {
        if (!current) return;
        if (!Array.isArray(current.activityLog)) current.activityLog = [];
        current.activityLog.push({
          at: isoNow(), type: 'foreground_start_clicked', job_id: current?.backgroundSearch?.id || null,
          details: {
            prompt: document.getElementById('prompt')?.value?.trim() || '',
            resources: typeof selectedResources === 'function' ? selectedResources() : [],
            results_before: current?.results?.length || 0,
          },
        });
        write(SESSION_KEY, current);
      }, 0);
    });
    document.getElementById('stopBtn')?.addEventListener('click', () => {
      if (!current) return;
      if (!Array.isArray(current.activityLog)) current.activityLog = [];
      current.activityLog.push({ at: isoNow(), type: 'foreground_stop_clicked', job_id: current?.backgroundSearch?.id || null, details: { results_at_click: current?.results?.length || 0 } });
      write(SESSION_KEY, current);
    });
    document.addEventListener('change', event => {
      if (event.target?.id !== 'largeSearchTarget' || !current) return;
      if (!Array.isArray(current.activityLog)) current.activityLog = [];
      current.activityLog.push({ at: isoNow(), type: 'large_target_change', job_id: current?.backgroundSearch?.id || null, details: { target: Number(event.target.value) || null } });
      write(SESSION_KEY, current);
    });
  }

  window.sessionTxt = () => buildReport(cachedJobs);
  window.exportTxt = async function exportCompleteAuditTxt() {
    const jobs = await fetchJobsForReport();
    const report = buildReport(jobs);
    const blob = new Blob([report], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'namemachine-live-audit-v3-' + (current?.id || 'session') + '.txt';
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    document.getElementById('saveMenu')?.classList.remove('open');
  };

  recordExtraControls();
  void fetchJobsForReport();
})();
