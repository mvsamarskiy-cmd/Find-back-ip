/* Universal-search UI adaptation layered over the private Global Search controller. */
(() => {
  if (window.__nmUniversalGlobalMode) return;
  window.__nmUniversalGlobalMode = true;

  const originalFetch = window.fetch.bind(window);
  const searchPath = '/api/private-mode/search';

  function isPrivate() {
    return document.body.classList.contains('nm-private-global');
  }

  function normalizePrivateCopy() {
    if (!isPrivate()) return;
    const prompt = document.getElementById('prompt');
    const status = document.getElementById('status');
    const category = document.getElementById('nmPrivateCategory');

    if (prompt) {
      prompt.placeholder = 'Пиши будь-який глобальний запит — система сама вибере пошуковий маршрут…';
    }
    if (category?.options?.length && category.options[0]?.value === 'all') {
      category.options[0].textContent = 'Авто';
    }
    if (status?.textContent === 'Opportunity Intelligence активний.') {
      status.textContent = 'Universal Search активний.';
    }
    if (status?.textContent?.includes('Шукаю → нормалізую → перевіряю джерела → рахую fit')) {
      status.textContent = 'Шукаю → визначаю намір → вибираю маршрут → перевіряю джерела…';
    }
  }

  function cleanGeneralCards() {
    if (document.body.dataset.nmIntelligenceRoute !== 'general_web') return;
    for (const card of document.querySelectorAll('#nmPrivateResults .nmpg-card')) {
      for (const badge of card.querySelectorAll('.nmpg-badge')) {
        if ((badge.textContent || '').trim() === 'STATUS ?') badge.remove();
      }
      for (const evidence of card.querySelectorAll('.nmpg-evidence')) {
        if (!(evidence.textContent || '').trim()) evidence.remove();
      }
    }
  }

  function refresh() {
    normalizePrivateCopy();
    cleanGeneralCards();
  }

  window.fetch = async (...args) => {
    const response = await originalFetch(...args);
    const target = typeof args[0] === 'string' ? args[0] : (args[0]?.url || '');
    if (String(target).includes(searchPath)) {
      response.clone().json().then(payload => {
        if (!payload || typeof payload !== 'object') return;
        if (payload.intelligence_route) {
          document.body.dataset.nmIntelligenceRoute = String(payload.intelligence_route);
        }
        if (payload.general_intent) {
          document.body.dataset.nmGeneralIntent = String(payload.general_intent);
        } else {
          delete document.body.dataset.nmGeneralIntent;
        }
        queueMicrotask(refresh);
      }).catch(() => {});
    }
    return response;
  };

  const observer = new MutationObserver(refresh);
  observer.observe(document.documentElement, {
    subtree: true,
    childList: true,
    attributes: true,
    attributeFilter: ['class'],
  });
  refresh();
})();
