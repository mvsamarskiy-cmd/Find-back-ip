/* Private Money report run identity and stale-payload guard.
 * Adds auditable execution metadata to exported private reports and refuses to
 * present a previous in-memory payload as the result of a new/not-yet-run search.
 * No unlock secret or private credential is read or exposed here.
 */
(() => {
  if (window.__nmPrivateReportRunIdentityInstalled) return;
  window.__nmPrivateReportRunIdentityInstalled = true;

  const previousFetch = window.fetch.bind(window);
  const baseClientReportTxt = window.clientReportTxt;
  const baseExportTxt = window.exportClientReportTxt;
  const baseExportHtml = window.exportClientReportHtml;
  const baseEmail = window.emailClientReport;

  let run = null;
  let release = { release: 'unknown', git_commit: 'unknown', observed_at: '' };

  const clean = (value, limit = 1200) => String(value ?? '').replace(/\s+/g, ' ').trim().slice(0, limit);
  const isPrivate = () => document.body.classList.contains('nm-private-global');
  const currentPrompt = () => clean(document.getElementById('prompt')?.value || '', 1000);
  const nowIso = () => new Date().toISOString();

  function parseSearchMeta(args) {
    try {
      const init = args?.[1] || {};
      const body = typeof init.body === 'string' ? JSON.parse(init.body) : {};
      return {
        query: clean(body?.query || currentPrompt(), 1000),
        country: clean(body?.country || document.getElementById('nmPrivateCountry')?.value || 'EU', 40),
        category: clean(body?.category || document.getElementById('nmPrivateCategory')?.value || 'all', 120),
        search_id: clean(body?.search_id || '', 120),
      };
    } catch (_) {
      return { query: currentPrompt(), country: 'EU', category: 'all', search_id: '' };
    }
  }

  function identityLines(reportGeneratedAt) {
    const prompt = currentPrompt();
    const lines = [
      '0. ІДЕНТИЧНІСТЬ ЗАПУСКУ',
      `- Search ID: ${run?.search_id || '—'}`,
      `- Запит відправлено: ${run?.requested_at || '—'}`,
      `- Відповідь отримано: ${run?.completed_at || '—'}`,
      `- Звіт сформовано: ${reportGeneratedAt}`,
      `- Стан run: ${run?.status || 'no_search_in_this_page'}`,
      `- HTTP status: ${run?.http_status ?? '—'}`,
      `- Release: ${release.release || 'unknown'}`,
      `- Git commit: ${release.git_commit || 'unknown'}`,
      `- Version observed at: ${release.observed_at || '—'}`,
    ];
    if (run?.query && prompt && run.query !== prompt) {
      lines.push(`- ⚠ Поточне поле запиту відрізняється від цього run. Run query: ${run.query}`);
      lines.push(`- ⚠ Поточний текст у полі: ${prompt}`);
    }
    return lines;
  }

  function unavailableReport(reportGeneratedAt) {
    const lines = [
      'NameMachine — MONEY / GLOBAL SEARCH REPORT',
      '',
      ...identityLines(reportGeneratedAt),
      '',
      '⚠ ЗВІТ НЕ МІСТИТЬ ЗАВЕРШЕНОГО НОВОГО PRIVATE SEARCH',
    ];
    if (!run) {
      lines.push('- Після завантаження цієї сторінки в цій вкладці новий POST /api/private-mode/search не зафіксовано.');
      lines.push('- Старий in-memory payload навмисно не видається за новий результат. Запусти новий пошук і дочекайся відповіді.');
    } else if (run.status === 'running') {
      lines.push('- Поточний private search ще виконується. Старий payload навмисно не експортується.');
    } else {
      lines.push(`- Поточний private search не завершився валідною відповіддю: ${run.error || run.status || 'unknown'}.`);
      lines.push('- Попередній payload навмисно не використовується як результат цього run.');
    }
    return lines.join('\n');
  }

  function annotatedPrivateText() {
    const generatedAt = nowIso();
    if (!run || run.status !== 'completed') return unavailableReport(generatedAt);

    const base = typeof baseClientReportTxt === 'function' ? String(baseClientReportTxt() || '') : '';
    const identity = identityLines(generatedAt).join('\n');
    const title = 'NameMachine — MONEY / GLOBAL SEARCH REPORT';
    if (base.startsWith(title)) {
      return `${title}\n\n${identity}\n\n${base.slice(title.length).replace(/^\s+/, '')}`;
    }
    return `${title}\n\n${identity}\n\n${base}`.trim();
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

  function htmlEscape(value) {
    return String(value ?? '').replace(/[&<>"']/g, ch => ({
      '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'
    }[ch]));
  }

  function exportPrivateHtml() {
    const text = annotatedPrivateText();
    const html = `<!doctype html><html lang="uk"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>NameMachine Money / Global Search Report</title><style>body{margin:0;background:#f4f5f7;color:#17191d;font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.wrap{max-width:960px;margin:auto;padding:32px 16px 64px}.hero{background:#111827;color:#fff;border-radius:20px;padding:22px 24px;margin-bottom:16px}.hero h1{margin:0;font-size:26px}.report{white-space:pre-wrap;overflow-wrap:anywhere;background:#fff;border:1px solid #e1e4e8;border-radius:18px;padding:22px;font:13px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace}</style></head><body><main class="wrap"><header class="hero"><h1>Money / Global Search Report</h1></header><div class="report">${htmlEscape(text)}</div></main></body></html>`;
    download(html, 'namemachine-money-global-report.html', 'text/html;charset=utf-8');
  }

  window.fetch = async function(...args) {
    const request = args[0];
    const url = typeof request === 'string' ? request : String(request?.url || '');
    const meta = url.includes('/api/private-mode/search') ? parseSearchMeta(args) : null;

    if (meta) {
      run = {
        ...meta,
        requested_at: nowIso(),
        completed_at: '',
        status: 'running',
        http_status: null,
        error: '',
      };
    }

    try {
      const response = await previousFetch(...args);
      if (meta) {
        run.http_status = response.status;
        run.completed_at = nowIso();
        if (response.ok) {
          // Do not clone+parse the large private payload here. The main search UI
          // owns JSON validation/parsing; this layer records transport identity only.
          // Re-parsing a 300KB+ response on mobile Safari was pure duplicate work.
          run.status = 'completed';
        } else {
          run.status = 'http_error';
          run.error = `HTTP ${response.status}`;
        }
      }
      return response;
    } catch (error) {
      if (meta) {
        run.status = 'network_error';
        run.completed_at = nowIso();
        run.error = clean(error?.name || error?.message || 'network_error', 160);
      }
      throw error;
    }
  };

  window.clientReportTxt = () => isPrivate()
    ? annotatedPrivateText()
    : (typeof baseClientReportTxt === 'function' ? baseClientReportTxt() : '');

  window.exportClientReportTxt = () => isPrivate()
    ? download(annotatedPrivateText(), 'namemachine-money-global-report.txt', 'text/plain;charset=utf-8')
    : baseExportTxt?.();

  window.exportClientReportHtml = () => isPrivate()
    ? exportPrivateHtml()
    : baseExportHtml?.();

  window.emailClientReport = () => {
    if (!isPrivate()) return baseEmail?.();
    const report = annotatedPrivateText();
    const recipient = window.prompt('На який email підготувати Money / Global звіт?');
    if (recipient === null) return;
    const email = clean(recipient, 180);
    if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      const status = document.getElementById('status');
      if (status) status.textContent = 'Email виглядає некоректно.';
      return;
    }
    const body = report.length > 12000 ? report.slice(0, 12000) + '\n\n[Повний звіт можна завантажити у TXT.]' : report;
    document.getElementById('saveMenu')?.classList.remove('open');
    window.location.href = 'mailto:' + encodeURIComponent(email) + '?subject=' + encodeURIComponent('NameMachine — Money / Global Search Report') + '&body=' + encodeURIComponent(body);
  };

  previousFetch('/api/version', { cache: 'no-store' })
    .then(response => response.ok ? response.json() : null)
    .then(payload => {
      if (!payload || typeof payload !== 'object') return;
      release = {
        release: clean(payload.release || 'unknown', 160),
        git_commit: clean(payload.git_commit || 'unknown', 160),
        observed_at: nowIso(),
      };
    })
    .catch(() => {});

  window.__nmPrivateReportRunIdentity = () => ({
    run: run ? { ...run } : null,
    release: { ...release },
  });
})();
