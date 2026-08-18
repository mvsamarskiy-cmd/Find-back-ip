/* Report/share controls loaded after audit_report.js. */
(() => {
  const menu = document.getElementById('saveMenu');
  if (menu) {
    menu.innerHTML = `
      <button type="button" id="downloadReadableReport">Звіт TXT</button>
      <button type="button" id="downloadTechnicalAudit">Технічний аудит TXT</button>
      <button type="button" id="emailReadableReport">Надіслати на email</button>
    `;
    menu.querySelector('#downloadReadableReport')?.addEventListener('click', () => { void window.exportTxt?.(); });
    menu.querySelector('#downloadTechnicalAudit')?.addEventListener('click', () => { void window.exportTechnicalAudit?.(); });
    menu.querySelector('#emailReadableReport')?.addEventListener('click', () => { void window.emailReport?.(); });
  }

  const note = document.querySelector('.session-note');
  if (note) {
    note.textContent = 'Сесія лишається доступною в браузері; коли серверна сесія активна, background search і результати також зберігаються на сервері. У меню «Зберегти» є короткий читабельний звіт, окремий повний технічний аудит і підготовка звіту до відправки через поштовий застосунок пристрою.';
  }
})();
