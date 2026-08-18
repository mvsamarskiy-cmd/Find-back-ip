/* Best-effort short-lived audit telemetry sync.
 *
 * The client report never reads this store. This only mirrors operational events
 * for debugging; both the browser copy and server copy use a seven-day TTL by
 * default. Durable candidates/feedback remain separate so the search can resume.
 */
(() => {
  const POLL_MS = 5000;
  const BATCH_SIZE = 50;
  const LOCAL_RETENTION_MS = 7 * 24 * 60 * 60 * 1000;
  const LOCAL_PRUNE_INTERVAL_MS = 60 * 60 * 1000;
  const sent = new Set();
  let inFlight = false;
  let timer = null;
  let lastLocalPruneAt = 0;

  function credentials() { return current?.serverSession || null; }

  function keyOf(event) {
    try { return JSON.stringify([event?.at || '', event?.type || '', event?.job_id || '', event?.details || {}]); }
    catch (_) { return String(event?.at || '') + '|' + String(event?.type || ''); }
  }

  function pruneLocalAudit(force = false) {
    if (!current || !Array.isArray(current.activityLog)) return 0;
    const now = Date.now();
    if (!force && now - lastLocalPruneAt < LOCAL_PRUNE_INTERVAL_MS) return 0;
    lastLocalPruneAt = now;
    const cutoff = now - LOCAL_RETENTION_MS;
    const before = current.activityLog.length;
    current.activityLog = current.activityLog.filter(event => {
      const at = Date.parse(event?.at || '');
      return Number.isFinite(at) && at > cutoff;
    });
    const removed = before - current.activityLog.length;
    if (removed) {
      current.updated = new Date().toISOString();
      write(SESSION_KEY, current);
    }
    return removed;
  }

  function pendingEvents() {
    pruneLocalAudit();
    const log = Array.isArray(current?.activityLog) ? current.activityLog : [];
    const rows = [];
    for (const event of log) {
      if (!event || typeof event !== 'object' || !event.type) continue;
      const key = keyOf(event);
      if (sent.has(key)) continue;
      rows.push({ key, event });
      if (rows.length >= BATCH_SIZE) break;
    }
    return rows;
  }

  async function flush(options = {}) {
    if (inFlight) return;
    const creds = credentials();
    if (!creds?.id || !creds?.token) return;
    const rows = pendingEvents();
    if (!rows.length) return;
    inFlight = true;
    try {
      const response = await fetch('/api/sessions/' + encodeURIComponent(creds.id) + '/audit-events/batch', {
        method: 'POST',
        keepalive: Boolean(options.keepalive),
        headers: {
          'Content-Type': 'application/json',
          'X-NameMachine-Session-Token': creds.token,
        },
        body: JSON.stringify({ events: rows.map(row => row.event) }),
      });
      if (response.ok) rows.forEach(row => sent.add(row.key));
    } catch (_) {
      // Telemetry must never interrupt search or persistence.
    } finally {
      inFlight = false;
    }
  }

  function pulse() {
    pruneLocalAudit();
    void flush();
    timer = setTimeout(pulse, POLL_MS);
  }

  window.addEventListener('pagehide', () => {
    pruneLocalAudit(true);
    void flush({ keepalive: true });
  });
  pruneLocalAudit(true);
  timer = setTimeout(pulse, 1200);
})();
