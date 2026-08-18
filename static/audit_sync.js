/* Best-effort short-lived audit telemetry sync.
 *
 * The client report never reads this store. This only mirrors operational events
 * for debugging; the server applies a seven-day TTL by default.
 */
(() => {
  const POLL_MS = 5000;
  const BATCH_SIZE = 50;
  const sent = new Set();
  let inFlight = false;
  let timer = null;

  function credentials() { return current?.serverSession || null; }

  function keyOf(event) {
    try { return JSON.stringify([event?.at || '', event?.type || '', event?.job_id || '', event?.details || {}]); }
    catch (_) { return String(event?.at || '') + '|' + String(event?.type || ''); }
  }

  function pendingEvents() {
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
    void flush();
    timer = setTimeout(pulse, POLL_MS);
  }

  window.addEventListener('pagehide', () => { void flush({ keepalive: true }); });
  timer = setTimeout(pulse, 1200);
})();
