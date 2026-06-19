// dashboard/screener_lazy.js — charge la matrice de correlation au scroll (retry si donnees pas pretes)
(function () {
  var started = false;
  function findScroller(el) {
    el = el.parentElement;
    while (el && el !== document.documentElement) {
      var oy = getComputedStyle(el).overflowY;
      if (oy === 'auto' || oy === 'scroll') return el;
      el = el.parentElement;
    }
    return window;
  }
  function attempt(n) {
    if (typeof renderCorrelMatrix !== 'function') return;
    renderCorrelMatrix();
    if (n >= 4) return;
    setTimeout(function () {
      var el = document.getElementById('corr-matrix');
      var txt = el ? (el.innerText || '') : '';
      if (txt.indexOf('indisponible') > -1) attempt(n + 1);
    }, 3000);
  }
  function arm() {
    var anchor = document.getElementById('etape2-anchor');
    if (!anchor) return;
    var scroller = findScroller(anchor);
    var target = (scroller === window) ? window : scroller;
    function check() {
      if (started || typeof renderCorrelMatrix !== 'function') return;
      var r = anchor.getBoundingClientRect();
      if (r.top < window.innerHeight * 0.9) {
        started = true;
        target.removeEventListener('scroll', check);
        attempt(0);
      }
    }
    target.addEventListener('scroll', check, { passive: true });
    check();
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', arm);
  } else {
    arm();
  }
})();
