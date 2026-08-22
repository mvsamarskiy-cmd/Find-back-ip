/* Mobile-safe Stop control for private global search.
 * Keeps the shared Stop button genuinely clickable while a private search is
 * active and routes one click to the private stop handler. No secrets here.
 */
(() => {
  if (window.__nmPrivateStopMobileFix) return;
  window.__nmPrivateStopMobileFix = true;

  const stop = document.getElementById('stopBtn');
  const start = document.getElementById('startBtn');
  if (!stop || !start) return;

  function isPrivate() {
    return document.body.classList.contains('nm-private-global');
  }

  function isBusy() {
    return isPrivate() && start.disabled;
  }

  function syncStopState() {
    if (!isPrivate()) {
      stop.style.removeProperty('pointer-events');
      stop.style.removeProperty('touch-action');
      stop.style.removeProperty('position');
      stop.style.removeProperty('z-index');
      stop.removeAttribute('data-nm-private-stop-active');
      stop.removeAttribute('data-nm-stop-requested');
      return;
    }

    const requested = stop.dataset.nmStopRequested === '1';
    const active = isBusy() && !requested;
    stop.disabled = !active;
    stop.setAttribute('aria-disabled', active ? 'false' : 'true');
    stop.dataset.nmPrivateStopActive = active ? '1' : '0';
    stop.style.pointerEvents = active ? 'auto' : 'none';
    stop.style.touchAction = 'manipulation';
    stop.style.position = 'relative';
    stop.style.zIndex = '20';

    if (!isBusy()) stop.removeAttribute('data-nm-stop-requested');
  }

  stop.addEventListener('click', event => {
    if (!isBusy() || stop.dataset.nmStopRequested === '1') return;
    event.preventDefault();
    event.stopImmediatePropagation();
    stop.dataset.nmStopRequested = '1';
    stop.disabled = true;
    stop.setAttribute('aria-disabled', 'true');
    try {
      stopSearch();
    } catch (_) {
      stop.removeAttribute('data-nm-stop-requested');
      syncStopState();
    }
  }, true);

  const observer = new MutationObserver(syncStopState);
  observer.observe(document.body, { attributes: true, attributeFilter: ['class'] });
  observer.observe(start, { attributes: true, attributeFilter: ['disabled'] });
  observer.observe(stop, { attributes: true, attributeFilter: ['disabled'] });

  document.addEventListener('visibilitychange', syncStopState);
  window.addEventListener('pageshow', syncStopState);
  syncStopState();
})();
