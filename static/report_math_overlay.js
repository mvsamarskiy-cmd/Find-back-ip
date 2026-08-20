/* Append the mathematical evidence appendix to the default TXT/email report.
 * Loaded after client_report_modes so verified and generation-only reports both
 * receive the same quantitative audit. Search-reliability may wrap this later.
 */
(() => {
  if (window.__nameMachineReportMathOverlay) return;
  window.__nameMachineReportMathOverlay = true;

  const baseTextBuilder = window.clientReportTxt;
  if (typeof baseTextBuilder !== 'function' || !window.nameMachineReportMath) return;

  const clean = (value, limit = 1000) => String(value ?? '').replace(/\s+/g, ' ').trim().slice(0, limit);

  function buildText() {
    const base = String(baseTextBuilder() || '').trimEnd();
    const math = window.nameMachineReportMath.text(current?.results || []);
    return base + '\n' + math;
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

  window.clientReportTxt = buildText;
  window.exportClientReportTxt = () => download(
    buildText(),
    'namemachine-client-report-' + (current?.id || 'session') + '.txt',
    'text/plain;charset=utf-8',
  );
  window.emailClientReport = () => {
    const report = buildText();
    const recipient = window.prompt('На який email підготувати звіт?');
    if (recipient === null) return;
    const email = clean(recipient, 180);
    if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      document.getElementById('status').textContent = 'Email виглядає некоректно.';
      return;
    }
    const subject = 'NameMachine — ' + clean(current?.title || 'підсумковий звіт', 90);
    const body = report.length > 12000
      ? report.slice(0, 12000) + '\n\n[Повний математичний звіт можна завантажити з NameMachine.]'
      : report;
    document.getElementById('saveMenu')?.classList.remove('open');
    window.location.href = 'mailto:' + encodeURIComponent(email) + '?subject=' + encodeURIComponent(subject) + '&body=' + encodeURIComponent(body);
  };

  window.nameMachineReportMathOverlay = { buildText, version: 'math-overlay-v1' };
})();
