/* Private Money/Global Search page-scroll fix.
 *
 * v2.4 intentionally promoted the result panel and made the composer sticky.
 * On iOS that combination lets the composer cover result cards and traps swipe
 * gestures inside the nested result viewport. This overlay keeps the existing
 * search/controller semantics but restores one normal document scroll surface.
 */
(() => {
  if (window.__nmPrivateResultsPageScrollFix) return;
  window.__nmPrivateResultsPageScrollFix = true;

  function installStyle() {
    if (document.getElementById('nmPrivateResultsPageScrollFixStyle')) return;
    const style = document.createElement('style');
    style.id = 'nmPrivateResultsPageScrollFixStyle';
    style.textContent = `
      body.nm-private-global,
      body.nm-private-global html {
        overflow-y:auto!important;
        height:auto!important;
        overscroll-behavior-y:auto!important;
      }
      body.nm-private-global .shell {
        display:flex!important;
        flex-direction:column!important;
        min-height:100vh;
        overflow:visible!important;
        touch-action:pan-y!important;
      }
      body.nm-private-global .topbar { order:0; }
      body.nm-private-global .composer {
        order:1;
        position:relative!important;
        inset:auto!important;
        bottom:auto!important;
        top:auto!important;
        z-index:auto!important;
        margin-bottom:0!important;
        touch-action:pan-y!important;
      }
      body.nm-private-global #nmPrivateGlobalPanel {
        order:2;
        position:relative!important;
        z-index:auto!important;
        clear:both;
        width:100%;
        margin-top:20px!important;
        scroll-margin-top:16px!important;
        overflow:visible!important;
        touch-action:pan-y!important;
      }
      body.nm-private-global #nmPrivateGlobalPanel .nmpg-toolbar {
        position:static!important;
        top:auto!important;
        z-index:auto!important;
      }
      body.nm-private-global #nmPrivateViewport.nmpg-viewport {
        max-height:none!important;
        min-height:0!important;
        height:auto!important;
        overflow:visible!important;
        overflow-y:visible!important;
        overscroll-behavior:auto!important;
        scrollbar-gutter:auto!important;
        -webkit-overflow-scrolling:auto!important;
        touch-action:pan-y!important;
      }
      @media(max-width:640px) {
        body.nm-private-global #nmPrivateGlobalPanel { margin-top:16px!important; }
        body.nm-private-global #nmPrivateViewport.nmpg-viewport { max-height:none!important; }
      }
    `;
    document.head.appendChild(style);
  }

  function scrollingElement() {
    return document.scrollingElement || document.documentElement || document.body;
  }

  function pageScroll(top) {
    const target = scrollingElement();
    const value = Math.max(0, Number(top) || 0);
    try {
      window.scrollTo({ top: value, behavior: 'smooth' });
    } catch (_) {
      target.scrollTop = value;
      window.scrollTo(0, value);
    }
  }

  function installPageButtons() {
    const up = document.getElementById('nmScrollUp');
    const down = document.getElementById('nmScrollDown');

    if (up && up.dataset.nmPageScrollFix !== '1') {
      up.dataset.nmPageScrollFix = '1';
      up.title = 'До верху сторінки';
      up.addEventListener('click', event => {
        event.preventDefault();
        event.stopImmediatePropagation();
        pageScroll(0);
      }, true);
    }

    if (down && down.dataset.nmPageScrollFix !== '1') {
      down.dataset.nmPageScrollFix = '1';
      down.title = 'До низу сторінки';
      down.addEventListener('click', event => {
        event.preventDefault();
        event.stopImmediatePropagation();
        const target = scrollingElement();
        pageScroll(Math.max(target.scrollHeight, document.body?.scrollHeight || 0));
      }, true);
    }
  }

  function refresh() {
    installStyle();
    installPageButtons();
  }

  let queued = false;
  const observer = new MutationObserver(() => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      refresh();
    });
  });
  observer.observe(document.documentElement, {
    subtree: true,
    childList: true,
    attributes: true,
    attributeFilter: ['class'],
  });

  window.addEventListener('pageshow', refresh);
  window.addEventListener('resize', refresh);
  refresh();
})();
