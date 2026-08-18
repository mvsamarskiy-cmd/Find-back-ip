/* Best-effort durable sync for R9 variant expansions.
 *
 * Resource-specific variants stay outside the main candidate bundle table. This
 * layer loads/saves them through their own session-authenticated API whenever a
 * durable server session exists. Local UI remains usable if storage is offline.
 */
(() => {
  const TOKEN_HEADER = 'X-NameMachine-Session-Token';
  const POLL_MS = 300;
  const MAX_POLLS = 200;
  const inflightLoads = new Map();
  const inflightWrites = new Map();

  function api() {
    return window.nameMachineVariantExpansion || null;
  }

  function credentials() {
    const value = current?.serverSession;
    return value?.id && value?.token ? value : null;
  }

  function pathFor(name) {
    const creds = credentials();
    if (!creds) return null;
    return '/api/sessions/' + encodeURIComponent(creds.id) +
      '/variant-expansions/' + encodeURIComponent(String(name || ''));
  }

  function localStore() {
    if (!current) return null;
    if (!current.variantExpansions || typeof current.variantExpansions !== 'object' || Array.isArray(current.variantExpansions)) {
      current.variantExpansions = {};
    }
    return current.variantExpansions;
  }

  async function loadServer(name) {
    const key = String(name || '').toLowerCase();
    const creds = credentials(), path = pathFor(name);
    if (!key || !creds || !path) return null;
    if (inflightLoads.has(key)) return inflightLoads.get(key);
    const task = (async () => {
      try {
        const response = await fetch(path, { headers: { [TOKEN_HEADER]: creds.token } });
        if (!response.ok) return null;
        const payload = await response.json().catch(() => ({}));
        const expansion = payload?.expansion;
        if (!expansion || typeof expansion !== 'object') return null;
        const store = localStore();
        if (store) {
          store[key] = expansion;
          write(SESSION_KEY, current);
        }
        return expansion;
      } catch (_) {
        return null;
      } finally {
        inflightLoads.delete(key);
      }
    })();
    inflightLoads.set(key, task);
    return task;
  }

  async function saveServer(name, expansion) {
    const key = String(name || '').toLowerCase();
    const creds = credentials(), path = pathFor(name);
    if (!key || !creds || !path || !expansion || typeof expansion !== 'object') return false;
    if (inflightWrites.has(key)) return inflightWrites.get(key);
    const task = (async () => {
      try {
        const response = await fetch(path, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json', [TOKEN_HEADER]: creds.token },
          body: JSON.stringify(expansion),
        });
        return response.ok;
      } catch (_) {
        return false;
      } finally {
        inflightWrites.delete(key);
      }
    })();
    inflightWrites.set(key, task);
    return task;
  }

  async function openWithServerState(name) {
    const control = api();
    if (!control?.open) return;
    await loadServer(name);
    await control.open(name);
  }

  function modalName() {
    const title = document.getElementById('variantExpansionTitle')?.textContent || '';
    return title.replace(/^Розширити:\s*/, '').trim();
  }

  function watchRun(name) {
    let polls = 0;
    const tick = async () => {
      polls += 1;
      const control = api();
      if (!control) return;
      if (control.running && polls < MAX_POLLS) {
        setTimeout(tick, POLL_MS);
        return;
      }
      const expansion = control.saved?.(name);
      if (expansion) await saveServer(name, expansion);
    };
    setTimeout(tick, POLL_MS);
  }

  // Capture candidate-card clicks before the base R9 listener so server state is
  // loaded first. Failure to load never blocks the local workflow.
  document.addEventListener('click', event => {
    const button = event.target.closest('.variant-expand-open');
    if (!button) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    void openWithServerState(button.dataset.variantName || '');
  }, true);

  // Do not stop the real run-button event. Merely remember the parent candidate
  // and persist its local result after the visible workflow finishes.
  document.addEventListener('click', event => {
    if (!event.target.closest('#variantRunButton')) return;
    const name = modalName();
    if (name) watchRun(name);
  }, true);

  window.nameMachineVariantSync = { load: loadServer, save: saveServer };
})();
