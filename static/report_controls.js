/* Client report/share controls loaded after client_report.js. */
(() => {
  const menu = document.getElementById('saveMenu');
  if (menu) {
    menu.innerHTML = `
      <button type="button" id="downloadClientHtml">Клієнтський звіт HTML</button>
      <button type="button" id="downloadClientTxt">Клієнтський звіт TXT + перевірки</button>
      <button type="button" id="emailClientReport">Надіслати на email</button>
    `;
    menu.querySelector('#downloadClientHtml')?.addEventListener('click', () => { void window.exportClientReportHtml?.(); });
    menu.querySelector('#downloadClientTxt')?.addEventListener('click', () => { void window.exportClientReportTxt?.(); });
    menu.querySelector('#emailClientReport')?.addEventListener('click', () => { void window.emailClientReport?.(); });
  }

  const note = document.querySelector('.session-note');
  if (note) {
    note.textContent = 'Робоча сесія зберігає результати, shortlist і фідбек для продовження пошуку. TXT-звіт містить прямі лінки, Browser Eye факти та хронологію, щоб кожен результат можна було перепровірити.';
  }

  // search_reliability_overlay.js is loaded explicitly once by telegram_bootstrap.
  // Do not inject a second copy here: two independent wrappers duplicate sections
  // 8–10 in the TXT report.
})();
