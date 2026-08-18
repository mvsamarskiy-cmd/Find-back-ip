/* Client report/share controls loaded after client_report.js. */
(() => {
  const menu = document.getElementById('saveMenu');
  if (menu) {
    menu.innerHTML = `
      <button type="button" id="downloadClientHtml">Клієнтський звіт HTML</button>
      <button type="button" id="downloadClientTxt">Клієнтський звіт TXT</button>
      <button type="button" id="emailClientReport">Надіслати на email</button>
    `;
    menu.querySelector('#downloadClientHtml')?.addEventListener('click', () => { void window.exportClientReportHtml?.(); });
    menu.querySelector('#downloadClientTxt')?.addEventListener('click', () => { void window.exportClientReportTxt?.(); });
    menu.querySelector('#emailClientReport')?.addEventListener('click', () => { void window.emailClientReport?.(); });
  }

  const note = document.querySelector('.session-note');
  if (note) {
    note.textContent = 'Робоча сесія зберігає результати, shortlist і фідбек для продовження пошуку. У меню «Зберегти» клієнту доступний тільки чистий підсумковий звіт; технічна телеметрія не змішується з клієнтським документом.';
  }
})();
