/* Read-only journalist evidence browser for private Global Search. */
(() => {
  if (window.__nmPrivateResearchBrowser) return;
  window.__nmPrivateResearchBrowser = true;

  const EVIDENCE_PATH = '/api/private-mode/evidence';
  let activeController = null;
  let activeUrl = '';

  function isPrivate() {
    return document.body.classList.contains('nm-private-global');
  }

  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function addStyle() {
    if (document.getElementById('nmResearchEvidenceStyle')) return;
    const style = document.createElement('style');
    style.id = 'nmResearchEvidenceStyle';
    style.textContent = `
      .nmer-source{margin-top:10px;padding-top:9px;border-top:1px solid var(--line);display:grid;gap:7px}
      .nmer-source-url{display:block;max-width:100%;overflow-wrap:anywhere;white-space:normal;color:var(--muted);font-size:11px;line-height:1.45}
      .nmer-card-actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
      .nmer-btn{appearance:none;border:1px solid var(--line);background:var(--panel);color:var(--text);border-radius:10px;padding:7px 10px;font:inherit;font-size:12px;cursor:pointer}
      .nmer-btn:hover{border-color:currentColor}.nmer-btn:disabled{opacity:.5;cursor:wait}
      #nmResearchEvidenceModal{position:fixed;inset:0;z-index:10050;display:none;background:rgba(0,0,0,.68);padding:18px}
      #nmResearchEvidenceModal.open{display:flex;align-items:stretch;justify-content:center}
      .nmer-dialog{width:min(1180px,100%);height:calc(100dvh - 36px);margin:auto;background:var(--bg,#0d1014);color:var(--text);border:1px solid var(--line);border-radius:18px;display:grid;grid-template-rows:auto 1fr;overflow:hidden;box-shadow:0 24px 80px rgba(0,0,0,.45)}
      .nmer-top{display:grid;grid-template-columns:1fr auto;gap:12px;padding:15px 16px;border-bottom:1px solid var(--line);background:var(--panel)}
      .nmer-title{font-size:18px;font-weight:850;line-height:1.3;min-width:0}.nmer-title small{display:block;margin-top:5px;font-size:11px;font-weight:500;color:var(--muted);overflow-wrap:anywhere}
      .nmer-top-actions{display:flex;gap:7px;align-items:flex-start;flex-wrap:wrap;justify-content:flex-end}.nmer-close{font-size:20px;line-height:1;padding:6px 10px}
      .nmer-body{overflow:auto;padding:16px;display:grid;gap:14px;align-content:start;overscroll-behavior:contain}
      .nmer-loading,.nmer-error{border:1px dashed var(--line);border-radius:14px;padding:22px;color:var(--muted);text-align:center}.nmer-error{color:#e7868f}
      .nmer-section{border:1px solid var(--line);border-radius:15px;background:var(--panel);padding:13px;display:grid;gap:10px}.nmer-section h3{margin:0;font-size:13px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
      .nmer-meta{display:flex;flex-wrap:wrap;gap:7px}.nmer-chip{border:1px solid var(--line);border-radius:999px;padding:4px 8px;font-size:11px;color:var(--muted)}.nmer-chip.onion{color:#c9a8ff;border-color:#6f4e97}
      .nmer-kv{display:grid;grid-template-columns:150px 1fr;gap:6px 12px;font-size:12px}.nmer-kv dt{color:var(--muted)}.nmer-kv dd{margin:0;overflow-wrap:anywhere}.nmer-kv code{white-space:pre-wrap;overflow-wrap:anywhere}
      .nmer-contact-groups{display:grid;gap:10px}.nmer-contact-group{display:grid;gap:6px}.nmer-contact-label{font-size:11px;color:var(--muted);text-transform:uppercase}.nmer-contact-row{display:grid;grid-template-columns:1fr auto;gap:8px;align-items:center;border-top:1px solid var(--line);padding-top:6px;font-size:12px}.nmer-contact-row code{overflow-wrap:anywhere;white-space:normal}
      .nmer-raw{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;max-width:100%;tab-size:4}
      .nmer-links{display:grid;gap:8px}.nmer-link-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;padding-top:8px;border-top:1px solid var(--line)}.nmer-link-main{min-width:0}.nmer-link-title{font-size:12px;font-weight:700}.nmer-link-url{display:block;margin-top:3px;color:var(--muted);font-size:10px;overflow-wrap:anywhere;white-space:normal}.nmer-link-actions{display:flex;gap:6px;align-items:start;flex-wrap:wrap}
      .nmer-empty{font-size:12px;color:var(--muted)}
      @media(max-width:720px){#nmResearchEvidenceModal{padding:0}.nmer-dialog{height:100dvh;border-radius:0;border-left:0;border-right:0}.nmer-top{grid-template-columns:1fr}.nmer-top-actions{justify-content:flex-start}.nmer-kv{grid-template-columns:1fr}.nmer-link-row{grid-template-columns:1fr}.nmer-body{padding:12px}}
    `;
    document.head.appendChild(style);
  }

  function modal() {
    let root = document.getElementById('nmResearchEvidenceModal');
    if (root) return root;
    root = el('div');
    root.id = 'nmResearchEvidenceModal';
    root.setAttribute('role', 'dialog');
    root.setAttribute('aria-modal', 'true');

    const dialog = el('div', 'nmer-dialog');
    const top = el('div', 'nmer-top');
    const title = el('div', 'nmer-title', 'Source evidence');
    title.id = 'nmerTitle';
    const actions = el('div', 'nmer-top-actions');
    const open = el('a', 'nmer-btn', 'Відкрити оригінал ↗');
    open.id = 'nmerOpenOriginal';
    open.target = '_blank';
    open.rel = 'noopener noreferrer';
    const copy = el('button', 'nmer-btn', 'Копіювати URL');
    copy.type = 'button';
    copy.id = 'nmerCopyUrl';
    const close = el('button', 'nmer-btn nmer-close', '×');
    close.type = 'button';
    close.setAttribute('aria-label', 'Закрити');
    close.addEventListener('click', closeModal);
    actions.append(open, copy, close);
    top.append(title, actions);
    const body = el('div', 'nmer-body');
    body.id = 'nmerBody';
    dialog.append(top, body);
    root.appendChild(dialog);
    root.addEventListener('click', event => { if (event.target === root) closeModal(); });
    copy.addEventListener('click', () => copyText(activeUrl, copy));
    document.body.appendChild(root);
    return root;
  }

  async function copyText(value, button) {
    const text = String(value || '');
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      if (button) {
        const prior = button.textContent;
        button.textContent = 'Скопійовано';
        setTimeout(() => { button.textContent = prior; }, 900);
      }
    } catch (_) {
      const area = document.createElement('textarea');
      area.value = text;
      area.style.position = 'fixed';
      area.style.opacity = '0';
      document.body.appendChild(area);
      area.select();
      try { document.execCommand('copy'); } catch (_) {}
      area.remove();
    }
  }

  function closeModal() {
    activeController?.abort();
    activeController = null;
    const root = document.getElementById('nmResearchEvidenceModal');
    root?.classList.remove('open');
    document.body.style.overflow = '';
  }

  function setTop(url, titleText) {
    activeUrl = String(url || '');
    const title = document.getElementById('nmerTitle');
    if (title) {
      title.replaceChildren();
      title.appendChild(document.createTextNode(titleText || 'Source evidence'));
      const small = el('small', '', activeUrl);
      title.appendChild(small);
    }
    const open = document.getElementById('nmerOpenOriginal');
    if (open) {
      open.href = activeUrl || '#';
      open.style.display = /^https?:\/\//i.test(activeUrl) ? '' : 'none';
    }
  }

  function addKv(dl, key, value, code = false) {
    if (value === undefined || value === null || value === '') return;
    dl.appendChild(el('dt', '', key));
    const dd = el('dd');
    if (code) dd.appendChild(el('code', '', value)); else dd.textContent = String(value);
    dl.appendChild(dd);
  }

  function section(title) {
    const box = el('section', 'nmer-section');
    box.appendChild(el('h3', '', title));
    return box;
  }

  function renderContacts(parent, contacts) {
    const fields = [
      ['Email', 'emails'], ['Телефони', 'phones'], ['Telegram', 'telegram'],
      ['Signal', 'signal'], ['Matrix', 'matrix'], ['XMPP', 'xmpp'], ['Onion URL', 'onion_urls'],
    ];
    const any = fields.some(([, key]) => Array.isArray(contacts?.[key]) && contacts[key].length);
    if (!any) return;
    const box = section('Публічні контакти, побачені у джерелі');
    const groups = el('div', 'nmer-contact-groups');
    for (const [label, key] of fields) {
      const values = Array.isArray(contacts?.[key]) ? contacts[key] : [];
      if (!values.length) continue;
      const group = el('div', 'nmer-contact-group');
      group.appendChild(el('div', 'nmer-contact-label', label));
      for (const value of values) {
        const row = el('div', 'nmer-contact-row');
        row.appendChild(el('code', '', value));
        const copy = el('button', 'nmer-btn', 'Копіювати');
        copy.type = 'button';
        copy.addEventListener('click', () => copyText(value, copy));
        row.appendChild(copy);
        group.appendChild(row);
      }
      groups.appendChild(group);
    }
    box.appendChild(groups);
    parent.appendChild(box);
  }

  function isPreviewable(url) {
    return /^https?:\/\//i.test(String(url || ''));
  }

  function renderLinks(parent, rows) {
    const links = Array.isArray(rows) ? rows : [];
    if (!links.length) return;
    const box = section(`Вихідні посилання зі сторінки · ${links.length}`);
    const list = el('div', 'nmer-links');
    for (const item of links) {
      const url = String(item?.url || '');
      if (!url) continue;
      const row = el('div', 'nmer-link-row');
      const main = el('div', 'nmer-link-main');
      main.appendChild(el('div', 'nmer-link-title', item?.title || item?.kind || 'link'));
      main.appendChild(el('code', 'nmer-link-url', url));
      const actions = el('div', 'nmer-link-actions');
      const copy = el('button', 'nmer-btn', 'Copy');
      copy.type = 'button';
      copy.addEventListener('click', () => copyText(url, copy));
      actions.appendChild(copy);
      if (isPreviewable(url)) {
        const preview = el('button', 'nmer-btn', 'Переглянути тут');
        preview.type = 'button';
        preview.addEventListener('click', () => openEvidence(url));
        actions.appendChild(preview);
        const open = el('a', 'nmer-btn', 'Оригінал ↗');
        open.href = url;
        open.target = '_blank';
        open.rel = 'noopener noreferrer';
        actions.appendChild(open);
      }
      row.append(main, actions);
      list.appendChild(row);
    }
    box.appendChild(list);
    parent.appendChild(box);
  }

  function renderEvidence(payload) {
    const body = document.getElementById('nmerBody');
    if (!body) return;
    body.replaceChildren();
    const finalUrl = String(payload?.final_url || payload?.requested_url || activeUrl || '');
    setTop(finalUrl, payload?.title || 'Source evidence');

    const source = section('Першоджерело / provenance');
    const chips = el('div', 'nmer-meta');
    chips.appendChild(el('span', 'nmer-chip', `transport ${payload?.transport || 'tor'}`));
    if (payload?.onion_service) chips.appendChild(el('span', 'nmer-chip onion', 'ONION SERVICE'));
    if (payload?.http_status !== undefined && payload?.http_status !== null) chips.appendChild(el('span', 'nmer-chip', `HTTP ${payload.http_status}`));
    chips.appendChild(el('span', 'nmer-chip', payload?.verification?.state || 'retrieved evidence'));
    source.appendChild(chips);
    const dl = el('dl', 'nmer-kv');
    addKv(dl, 'Requested URL', payload?.requested_url, true);
    addKv(dl, 'Final URL', payload?.final_url, true);
    addKv(dl, 'Canonical', payload?.canonical, true);
    addKv(dl, 'Onion-Location', payload?.onion_location, true);
    addKv(dl, 'Observed at', payload?.observed_at);
    addKv(dl, 'Snapshot SHA-256', payload?.snapshot_sha256, true);
    addKv(dl, 'Truth semantics', payload?.truth_semantics);
    source.appendChild(dl);
    body.appendChild(source);

    if (payload?.onion_location && payload.onion_location !== finalUrl) {
      const onionBox = section('Onion counterpart');
      const url = String(payload.onion_location);
      const line = el('div', 'nmer-link-row');
      line.appendChild(el('code', 'nmer-link-url', url));
      const actions = el('div', 'nmer-link-actions');
      const preview = el('button', 'nmer-btn', 'Переглянути через Tor');
      preview.type = 'button';
      preview.addEventListener('click', () => openEvidence(url));
      const copy = el('button', 'nmer-btn', 'Copy');
      copy.type = 'button';
      copy.addEventListener('click', () => copyText(url, copy));
      const open = el('a', 'nmer-btn', 'Оригінал ↗');
      open.href = url; open.target = '_blank'; open.rel = 'noopener noreferrer';
      actions.append(preview, copy, open); line.appendChild(actions); onionBox.appendChild(line); body.appendChild(onionBox);
    }

    renderContacts(body, payload?.public_contacts || {});

    const raw = section(`Повний видимий текст · ${String(payload?.body_text || '').length} символів`);
    const pre = el('pre', 'nmer-raw', payload?.body_text || 'На сторінці не отримано видимого тексту.');
    raw.appendChild(pre);
    body.appendChild(raw);
    renderLinks(body, payload?.links);
  }

  async function openEvidence(url) {
    const target = String(url || '').trim();
    if (!isPreviewable(target)) return;
    addStyle();
    const root = modal();
    root.classList.add('open');
    document.body.style.overflow = 'hidden';
    setTop(target, 'Завантажую першоджерело…');
    const body = document.getElementById('nmerBody');
    body?.replaceChildren(el('div', 'nmer-loading', 'Tor retrieval → rendered source → evidence extraction…'));
    activeController?.abort();
    const controller = new AbortController();
    activeController = controller;
    try {
      const response = await fetch(EVIDENCE_PATH, {
        method: 'POST',
        signal: controller.signal,
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({url: target}),
      });
      let payload = null;
      try { payload = await response.json(); } catch (_) {}
      if (response.status === 404) {
        closeModal();
        return;
      }
      if (!response.ok && !payload?.provider_status) throw new Error(payload?.error || `HTTP ${response.status}`);
      if (!payload || payload.provider_status !== 'complete') {
        throw new Error(payload?.provider_status ? `Evidence retrieval: ${payload.provider_status}` : 'Evidence retrieval failed');
      }
      renderEvidence(payload);
    } catch (error) {
      if (error?.name === 'AbortError') return;
      const bodyNow = document.getElementById('nmerBody');
      bodyNow?.replaceChildren(el('div', 'nmer-error', error?.message || 'Не вдалося завантажити першоджерело.'));
    } finally {
      if (activeController === controller) activeController = null;
    }
  }

  function enhanceCards() {
    if (!isPrivate()) return;
    for (const card of document.querySelectorAll('#nmPrivateResults .nmpg-card')) {
      if (card.querySelector('.nmer-source')) continue;
      const original = card.querySelector('a.nmpg-link[href]');
      if (!original) continue;
      const url = original.getAttribute('href') || original.href || '';
      if (!isPreviewable(url)) continue;
      const source = el('div', 'nmer-source');
      source.appendChild(el('code', 'nmer-source-url', url));
      const actions = el('div', 'nmer-card-actions');
      const preview = el('button', 'nmer-btn', 'Переглянути тут');
      preview.type = 'button';
      preview.addEventListener('click', () => openEvidence(url));
      const copy = el('button', 'nmer-btn', 'Копіювати URL');
      copy.type = 'button';
      copy.addEventListener('click', () => copyText(url, copy));
      actions.append(preview, copy);
      source.appendChild(actions);
      original.insertAdjacentElement('beforebegin', source);
    }
  }

  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && document.getElementById('nmResearchEvidenceModal')?.classList.contains('open')) closeModal();
  });

  const observer = new MutationObserver(enhanceCards);
  observer.observe(document.documentElement, {subtree: true, childList: true, attributes: true, attributeFilter: ['class']});
  addStyle();
  modal();
  enhanceCards();
})();
