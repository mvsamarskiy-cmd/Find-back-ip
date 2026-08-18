/* Best-effort durable session sync.
 *
 * localStorage remains the immediate working copy. If the server advertises a
 * configured database, this layer creates a capability-protected server session,
 * reconciles prior server data, and incrementally persists metadata + changed
 * candidates in bounded batches. Search never blocks on persistence.
 */
(() => {
  const baseSaveCurrent = saveCurrent;
  const candidateFingerprints = new Map();
  const candidateQueue = new Map();
  let remoteReady = false;
  let remoteDisabled = false;
  let metadataTimer = null;
  let candidateTimer = null;
  let metadataInFlight = false;
  let candidateInFlight = false;

  const credentials = () => current?.serverSession || null;
  const tokenHeaders = () => {
    const token = credentials()?.token;
    return token ? { 'X-NameMachine-Session-Token': token } : {};
  };

  function metadataPayload() {
    return {
      client_session_id: current?.id || null,
      title: current?.title || 'Нова сесія',
      prompt_history: Array.isArray(current?.promptHistory) ? current.promptHistory : [],
      resources: Array.isArray(current?.resources) ? current.resources : [],
      shortlist: Array.isArray(current?.shortlist) ? current.shortlist : [],
      direction_anchors: Array.isArray(current?.directionAnchors) ? current.directionAnchors : [],
      runs: Array.isArray(current?.runs) ? current.runs : [],
      feedback: current?.feedback && typeof current.feedback === 'object' ? current.feedback : {},
      batch_counter: Number(current?.batchCounter) || 0,
      created: current?.created || null,
      updated: current?.updated || null,
    };
  }

  function rowFingerprint(row) {
    try {
      return JSON.stringify({
        name: row?.name,
        score: row?.score,
        reason: row?.reason,
        family: row?.family,
        availability: row?.availability,
        verification: row?.verification,
        bundle_state: row?.bundle_state,
        bundle_score: row?.bundle_score,
        checked: row?.checked,
        run_id: row?.run_id,
        batch_number: row?.batch_number,
        received_seq: row?.received_seq,
        received_at: row?.received_at,
        resource_progress: row?.resource_progress,
      });
    } catch (_) {
      return String(Date.now());
    }
  }

  function queueCandidate(row, force = false) {
    const key = String(row?.name || '').toLowerCase();
    if (!key) return;
    const fingerprint = rowFingerprint(row);
    if (!force && candidateFingerprints.get(key) === fingerprint) return;
    candidateQueue.set(key, { row: { ...row }, fingerprint });
  }

  function queueChangedCandidates(forceAll = false) {
    const rows = Array.isArray(current?.results) ? current.results : [];
    if (forceAll) {
      rows.forEach(row => queueCandidate(row, true));
      return;
    }
    const activeRunId = current?.runs?.at?.(-1)?.id;
    let candidates = activeRunId ? rows.filter(row => row?.run_id === activeRunId) : [];
    if (!candidates.length) candidates = rows.slice(-120);
    candidates.forEach(row => queueCandidate(row));
  }

  async function api(path, options = {}) {
    const headers = {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...tokenHeaders(),
      ...(options.headers || {}),
    };
    const response = await fetch(path, { ...options, headers });
    let payload = null;
    try { payload = await response.json(); } catch (_) { payload = null; }
    if (!response.ok) {
      const error = new Error(payload?.error || ('HTTP ' + response.status));
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  function mergeRemote(remote) {
    if (!remote || typeof remote !== 'object') return false;
    let changed = false;
    if ((!current.title || current.title === 'Нова сесія') && remote.title) {
      current.title = remote.title;
      changed = true;
    }

    const mergeUniqueObjects = (local, incoming, keyFn) => {
      const result = Array.isArray(local) ? [...local] : [];
      const seen = new Set(result.map(keyFn));
      for (const item of Array.isArray(incoming) ? incoming : []) {
        const key = keyFn(item);
        if (!key || seen.has(key)) continue;
        seen.add(key);
        result.push(item);
        changed = true;
      }
      return result;
    };

    current.promptHistory = mergeUniqueObjects(
      current.promptHistory,
      remote.promptHistory,
      item => String(item?.at || '') + '|' + String(item?.text || ''),
    );
    current.runs = mergeUniqueObjects(current.runs, remote.runs, item => String(item?.id || ''));

    const localByName = new Map((current.results || []).map(row => [String(row?.name || '').toLowerCase(), row]));
    for (const row of Array.isArray(remote.results) ? remote.results : []) {
      const key = String(row?.name || '').toLowerCase();
      if (!key) continue;
      const local = localByName.get(key);
      if (!local) {
        current.results.push(row);
        localByName.set(key, row);
        changed = true;
      } else if (local.checked === false && row?.checked === true) {
        Object.assign(local, row);
        changed = true;
      }
    }

    current.feedback = { ...(remote.feedback || {}), ...(current.feedback || {}) };
    current.shortlist = [...new Set([...(remote.shortlist || []), ...(current.shortlist || [])])];
    current.directionAnchors = [...new Set([...(remote.directionAnchors || []), ...(current.directionAnchors || [])])];
    current.batchCounter = Math.max(Number(current.batchCounter) || 0, Number(remote.batchCounter) || 0);
    return changed;
  }

  async function createRemoteSession() {
    const created = await api('/api/sessions', {
      method: 'POST',
      body: JSON.stringify(metadataPayload()),
    });
    current.serverSession = {
      id: created.session_id,
      token: created.session_token,
      revision: Number(created.revision) || 1,
      server_updated_at: created.server_updated_at || null,
    };
    baseSaveCurrent();
    remoteReady = true;
    queueChangedCandidates(true);
    scheduleCandidateFlush(0);
  }

  async function connectExistingRemote() {
    const creds = credentials();
    if (!creds?.id || !creds?.token) return false;
    try {
      const response = await api('/api/sessions/' + encodeURIComponent(creds.id));
      if (mergeRemote(response?.session)) {
        baseSaveCurrent();
        render();
      }
      current.serverSession.revision = Number(response?.session?.revision) || Number(creds.revision) || 0;
      current.serverSession.server_updated_at = response?.session?.server_updated_at || creds.server_updated_at || null;
      baseSaveCurrent();
      remoteReady = true;
      queueChangedCandidates(true);
      scheduleCandidateFlush(0);
      scheduleMetadataSync(0);
      return true;
    } catch (error) {
      if (error.status === 404) {
        delete current.serverSession;
        baseSaveCurrent();
        return false;
      }
      throw error;
    }
  }

  async function initializeRemote() {
    try {
      const capability = await api('/api/session-storage');
      if (!capability?.enabled) {
        remoteDisabled = true;
        return;
      }
      if (await connectExistingRemote()) return;
      await createRemoteSession();
    } catch (_) {
      remoteDisabled = true;
    }
  }

  async function syncMetadata(options = {}) {
    if (!remoteReady || remoteDisabled || metadataInFlight) return;
    const creds = credentials();
    if (!creds?.id) return;
    metadataInFlight = true;
    try {
      const updated = await api('/api/sessions/' + encodeURIComponent(creds.id), {
        method: 'PUT',
        body: JSON.stringify(metadataPayload()),
        keepalive: Boolean(options.keepalive),
      });
      creds.revision = Number(updated?.revision) || Number(creds.revision) || 0;
      creds.server_updated_at = updated?.server_updated_at || creds.server_updated_at || null;
      baseSaveCurrent();
    } catch (error) {
      if (error.status === 404) remoteReady = false;
    } finally {
      metadataInFlight = false;
    }
  }

  function scheduleMetadataSync(delay = 650) {
    if (!remoteReady || remoteDisabled) return;
    clearTimeout(metadataTimer);
    metadataTimer = setTimeout(() => { void syncMetadata(); }, delay);
  }

  function takeCandidateBatch() {
    const entries = [];
    let estimatedBytes = 20;
    for (const [key, value] of candidateQueue.entries()) {
      const encoded = JSON.stringify(value.row);
      const bytes = typeof TextEncoder === 'function' ? new TextEncoder().encode(encoded).length : encoded.length * 2;
      if (entries.length && (entries.length >= 8 || estimatedBytes + bytes > 24000)) break;
      candidateQueue.delete(key);
      entries.push([key, value]);
      estimatedBytes += bytes;
    }
    return entries;
  }

  async function flushCandidates(options = {}) {
    if (!remoteReady || remoteDisabled || candidateInFlight || !candidateQueue.size) return;
    const creds = credentials();
    if (!creds?.id) return;
    const entries = takeCandidateBatch();
    if (!entries.length) return;
    candidateInFlight = true;
    try {
      const sent = entries.map(([, value]) => value.row);
      const updated = await api('/api/sessions/' + encodeURIComponent(creds.id) + '/candidates/batch', {
        method: 'POST',
        body: JSON.stringify({ candidates: sent }),
        keepalive: Boolean(options.keepalive),
      });
      creds.revision = Number(updated?.revision) || Number(creds.revision) || 0;
      creds.server_updated_at = updated?.server_updated_at || creds.server_updated_at || null;
      for (const [key, value] of entries) {
        candidateFingerprints.set(key, value.fingerprint);
        const currentRow = (current.results || []).find(row => String(row?.name || '').toLowerCase() === key);
        if (currentRow && rowFingerprint(currentRow) !== value.fingerprint) queueCandidate(currentRow, true);
      }
      baseSaveCurrent();
    } catch (error) {
      for (const [key, value] of entries) if (!candidateQueue.has(key)) candidateQueue.set(key, value);
      if (error.status === 404) remoteReady = false;
    } finally {
      candidateInFlight = false;
      if (candidateQueue.size && remoteReady) scheduleCandidateFlush(120);
    }
  }

  function scheduleCandidateFlush(delay = 500) {
    if (!remoteReady || remoteDisabled) return;
    clearTimeout(candidateTimer);
    candidateTimer = setTimeout(() => { void flushCandidates(); }, delay);
  }

  saveCurrent = function saveCurrentWithDurableMirror() {
    baseSaveCurrent();
    if (!remoteReady || remoteDisabled) return;
    queueChangedCandidates(false);
    scheduleMetadataSync();
    if (candidateQueue.size) scheduleCandidateFlush();
  };

  window.addEventListener('pagehide', () => {
    if (!remoteReady || remoteDisabled) return;
    queueChangedCandidates(false);
    void syncMetadata({ keepalive: true });
    void flushCandidates({ keepalive: true });
  });

  void initializeRemote();
})();
