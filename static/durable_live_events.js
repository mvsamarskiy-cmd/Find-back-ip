/* Durable true-live candidate lifecycle consumer.
 *
 * Background workers persist candidate_generated before external verification,
 * candidate_completed after the fast verifier, and candidate_enriched after the
 * asynchronous Browser Intelligence layer. This client renders only real server
 * events; it does not fabricate names or progress animation.
 */
(() => {
  const ACTIVE_POLL_MS = 900;
  const IDLE_POLL_MS = 3000;
  const PAGE_SIZE = 100;
  let timer = null;
  let polling = false;
  let knownServerSession = null;
  let cursor = 0;
  let consecutiveErrors = 0;

  function credentials() {
    return current?.serverSession || null;
  }

  function resetSessionIfNeeded() {
    const id = credentials()?.id || null;
    if (id === knownServerSession) return;
    knownServerSession = id;
    cursor = Math.max(0, Number(current?.candidateEventCursor) || 0);
    consecutiveErrors = 0;
  }

  function findRow(name) {
    const key = String(name || '').toLowerCase();
    return (current?.results || []).find(row => String(row?.name || '').toLowerCase() === key) || null;
  }

  function applyEvent(event) {
    if (!event || typeof event !== 'object') return false;
    const eventSeq = Math.max(0, Number(event.event_seq) || 0);
    const incoming = event?.payload?.row;
    if (!incoming || typeof incoming !== 'object' || !incoming.name) return false;
    let row = findRow(incoming.name);
    if (row && eventSeq <= (Number(row.lifecycle_event_seq) || 0)) return false;

    if (!row) {
      row = { ...incoming };
      current.results.push(row);
    } else {
      Object.assign(row, incoming);
    }
    row.lifecycle_event_seq = eventSeq;
    current.streamCounter = Math.max(
      Number(current.streamCounter) || 0,
      Number(row.received_seq) || 0,
    );

    const status = document.getElementById('status');
    if (event.event_type === 'candidate_generated') {
      row.checked = false;
      row.verification_state = 'checking';
      if (status) status.textContent = `${row.name} · перевіряю вибрані ресурси…`;
    } else if (event.event_type === 'candidate_completed') {
      row.checked = true;
      row.verification_state = 'complete';
      delete row.resource_progress;
      if (status) {
        if (allGreen(row)) status.textContent = `${row.name} · 🟢 підтверджено вільне`;
        else if (hasConflict(row)) status.textContent = `${row.name} · перевірено, є конфлікт`;
        else status.textContent = `${row.name} · швидка перевірка завершена`;
      }
    } else if (event.event_type === 'candidate_enriched') {
      // Browser Intelligence is an additive post-fast layer. The candidate has
      // already completed normal verification; this event refreshes evidence,
      // bundle state and final ranking without moving it back to "checking".
      row.checked = true;
      row.verification_state = 'complete';
      delete row.resource_progress;
      if (status) {
        if (allGreen(row)) status.textContent = `${row.name} · 🟢 браузерна переперевірка завершена`;
        else if (hasConflict(row)) status.textContent = `${row.name} · браузер знайшов конфлікт`;
        else status.textContent = `${row.name} · подвійна браузерна перевірка завершена`;
      }
    }
    return true;
  }

  function persistRemoteState() {
    if (!current) return;
    current.candidateEventCursor = cursor;
    current.updated = new Date().toISOString();
    // Lifecycle events originate on the server. Keep the browser copy current
    // without echoing the same candidate back through session_sync.
    write(SESSION_KEY, current);
  }

  async function fetchPage() {
    const creds = credentials();
    if (!creds?.id || !creds?.token) return { changed: 0, hasMore: false };
    const response = await fetch(
      '/api/sessions/' + encodeURIComponent(creds.id) +
      '/candidate-events?after_seq=' + encodeURIComponent(cursor) +
      '&limit=' + PAGE_SIZE,
      { headers: { 'X-NameMachine-Session-Token': creds.token } },
    );
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      const error = new Error(payload?.error || ('HTTP ' + response.status));
      error.status = response.status;
      throw error;
    }
    const payload = await response.json();
    let changed = 0;
    for (const event of payload?.events || []) {
      if (applyEvent(event)) changed += 1;
      cursor = Math.max(cursor, Number(event?.event_seq) || 0);
    }
    cursor = Math.max(cursor, Number(payload?.next_after_seq) || 0);
    return { changed, hasMore: Boolean(payload?.has_more) };
  }

  async function poll() {
    if (polling) return;
    polling = true;
    let changed = 0;
    let sawMore = false;
    try {
      resetSessionIfNeeded();
      if (!credentials()?.id || !credentials()?.token) return;
      let loops = 0;
      do {
        const page = await fetchPage();
        changed += page.changed;
        sawMore = page.hasMore;
        loops += 1;
      } while (sawMore && loops < 10);
      consecutiveErrors = 0;
      if (changed) {
        persistRemoteState();
        render();
      } else if (current && Number(current.candidateEventCursor || 0) !== cursor) {
        persistRemoteState();
      }
    } catch (error) {
      consecutiveErrors += 1;
      // A stale/missing session should not spin aggressively. The normal session
      // sync layer may create/restore credentials later, at which point polling resumes.
      if (error?.status === 404) knownServerSession = null;
    } finally {
      polling = false;
      clearTimeout(timer);
      const hidden = document.visibilityState === 'hidden';
      const delay = hidden || consecutiveErrors ? IDLE_POLL_MS : ACTIVE_POLL_MS;
      timer = setTimeout(() => { void poll(); }, delay);
    }
  }

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      clearTimeout(timer);
      timer = setTimeout(() => { void poll(); }, 0);
    }
  });

  window.addEventListener('pageshow', () => {
    clearTimeout(timer);
    timer = setTimeout(() => { void poll(); }, 0);
  });

  void poll();
})();