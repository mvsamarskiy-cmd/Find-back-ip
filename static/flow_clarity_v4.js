/* NameMachine flow clarity v4.
 *
 * Product contract:
 * - Create name + 0 resources => generation only.
 * - Create name + resources => generation + verification.
 * - Verify existing name => requires an existing name and at least one resource.
 * - Deep/Turbo availability search is only shown when there is something to verify.
 * - Turbo defaults to opportunity search, while strict-green remains an explicit option.
 */
(() => {
  if (window.__nameMachineFlowClarityV4) return;
  window.__nameMachineFlowClarityV4 = true;

  let scheduled = false;

  function flow() {
    const explicit = String(current?.uiFlow || '');
    if (explicit === 'identity') return 'identity';
    if (explicit === 'brand') return 'brand';
    return String(current?.entryMode || '') === 'identity' ? 'identity' : 'brand';
  }

  function selectedCount() {
    return document.querySelectorAll('.resources input[name="resource"]:checked').length;
  }

  function setText(node, value) {
    if (node && node.textContent !== value) node.textContent = value;
  }

  function syncResourceCopy(count, currentFlow) {
    const head = document.getElementById('nmResourcesHead');
    if (!head) return;
    let copy = `${count} вибрано`;
    if (count === 0 && currentFlow === 'brand') copy = '0 вибрано · лише генерація';
    if (count === 0 && currentFlow === 'identity') copy = '0 вибрано · вибери канал';
    const nextHtml = `<b>Перевіряти</b><span>${copy}</span>`;
    if (head.innerHTML !== nextHtml) head.innerHTML = nextHtml;
  }

  function syncFlowCards(count, currentFlow) {
    const brand = document.querySelector('[data-nm-flow="brand"]');
    const identity = document.querySelector('[data-nm-flow="identity"]');
    const brandHint = brand?.querySelector('span:last-child');
    const identityHint = identity?.querySelector('span:last-child');
    setText(
      brandHint,
      count ? 'генерація + перевірка вибраних каналів' : 'без каналів — просто генеруємо назви',
    );
    setText(identityHint, 'готова назва + перевірка вибраних каналів');

    const extra = document.querySelector('#nmFlowPicker .nm-flow-extra > span');
    let copy = '';
    if (currentFlow === 'identity') {
      copy = count
        ? `Перевіримо готову назву у ${count} вибраних каналах.`
        : 'Для перевірки готової назви вибери хоча б один канал.';
    } else {
      copy = count
        ? `Згенеруємо назви й перевіримо їх у ${count} вибраних каналах.`
        : 'Нічого не вибрано — NameMachine просто генеруватиме назви без перевірки.';
    }
    setText(extra, copy);
  }

  function syncDeepSearch(count, currentFlow) {
    const deep = document.querySelector('.nm-deep-search');
    if (!deep) return;
    const ideaOnly = Boolean(current?.uiIdeaOnly);
    const available = currentFlow === 'brand' && count > 0 && !ideaOnly;
    deep.hidden = !available;
    deep.setAttribute('aria-hidden', available ? 'false' : 'true');
    if (!available) deep.open = false;
  }

  function setHunterDefaults() {
    if (current?.backgroundSearch?.id) return;
    const strategy = document.getElementById('hunterSearchStrategy');
    const policy = document.getElementById('hunterMatchPolicy');
    if (!strategy || !policy) return;

    if (!strategy.dataset.nmUserTouched && strategy.value !== 'turbo') {
      strategy.value = 'turbo';
      strategy.dispatchEvent(new Event('change', { bubbles: true }));
    }
    if (!policy.dataset.nmUserTouched && policy.value !== 'any_opportunity') {
      policy.value = 'any_opportunity';
      policy.dispatchEvent(new Event('change', { bubbles: true }));
    }
  }

  function installTouchTracking() {
    const strategy = document.getElementById('hunterSearchStrategy');
    const policy = document.getElementById('hunterMatchPolicy');
    if (strategy && !strategy.dataset.nmTouchListener) {
      strategy.dataset.nmTouchListener = '1';
      strategy.addEventListener('change', event => {
        if (event.isTrusted) strategy.dataset.nmUserTouched = '1';
      });
    }
    if (policy && !policy.dataset.nmTouchListener) {
      policy.dataset.nmTouchListener = '1';
      policy.addEventListener('change', event => {
        if (event.isTrusted) policy.dataset.nmUserTouched = '1';
      });
    }
  }

  function sync() {
    scheduled = false;
    const currentFlow = flow();
    const count = selectedCount();
    syncResourceCopy(count, currentFlow);
    syncFlowCards(count, currentFlow);
    syncDeepSearch(count, currentFlow);
    installTouchTracking();
    if (currentFlow === 'brand' && count > 0) setHunterDefaults();
  }

  function scheduleSync() {
    if (scheduled) return;
    scheduled = true;
    setTimeout(sync, 0);
  }

  document.addEventListener('change', event => {
    if (event.target?.matches?.('.resources input[name="resource"], #nmIdeaOnly, #hunterSearchStrategy, #hunterMatchPolicy')) {
      scheduleSync();
    }
  }, true);

  document.addEventListener('click', event => {
    if (event.target?.closest?.('[data-nm-flow]')) scheduleSync();
  }, true);

  // Child-list changes are enough to notice dynamically installed result/search
  // widgets. sync() itself is idempotent, so it never creates an observer loop.
  const observer = new MutationObserver(scheduleSync);
  observer.observe(document.documentElement, { childList: true, subtree: true });

  scheduleSync();
  window.nameMachineFlowClarityV4 = { sync, version: 'flow-clarity-v4' };
})();
