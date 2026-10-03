/* LOADJS-1 — un fichier JS manquant ne doit plus vider la page.
   Deux relances (250 ms, puis 700 ms). Si le module echoue encore, la
   section concernee affiche un message et un bouton pour recharger.
   Les autres sections ne sont pas touchees.

   Jeton : le serveur ecrit window.BRVM_ASSET_V (commit Render, sinon
   empreinte des JS) dans le HTML. Chaque module est demande avec ?v=.
   Une instance qui n'a pas ce jeton repond 503 no-store : onerror relance
   la requete, qui peut atteindre la nouvelle instance. &retry=N evite
   de reutiliser une 502 mise en cache pendant la bascule.
*/
(function () {
  if (window.__BRVM_LOADER) return;
  window.__BRVM_LOADER = 1;

  var RETRIES = 2;
  var MSG = "Cette partie n'a pas pu se charger. Rechargez la page.";
  var BTN = "Recharger";

  var SECTIONS = {
    "simulator.js": "page-welcome",
    "live_score.js": "page-stock",
    "ranking.js": "rank-table-wrap",
    "stock_chart.js": "page-stock",
    "badges.js": "rank-table-wrap",
    "data_confidence.js": "rank-table-wrap",
    "compare.js": "page-rank",
    "alerts.js": "page-signals",
    "screener.js": "page-screener",
    "performance.js": "perfPageContent",
    "compare_analysis.js": "page-screener",
    "backtest.js": "page-rank",
    "markowitz.js": "page-screener",
    "previsions.js": "page-signals",
    "company-tabs.js": "page-stock",
    "news_v2.js": "page-news",
    "signaux_v2.js": "page-signals",
    "rank_v2.js": "page-rank",
    "welcome_v2.js": "page-welcome",
    "top3_podium.js": "page-rank",
    "screener_lazy.js": "page-screener",
    "js/charts_comparaison.js": "page-stock"
  };

  var SYMBOL_FILE = {
    loadRankDash: "rank_v2.js",
    loadWelcomeHero: "welcome_v2.js",
    initTop3Podium: "top3_podium.js",
    loadSignauxValoAlertes: "signaux_v2.js",
    injectEpurationSignaux: "signaux_v2.js",
    renderNewsV2: "news_v2.js",
    initScreener: "screener.js",
    runScreener: "screener.js",
    screenerReset: "screener.js",
    screenerPreset: "screener.js",
    screenerSortBy: "screener.js",
    screenerExportCSV: "screener.js",
    screenerAnalyseAI: "screener.js",
    renderPerfPage: "performance.js",
    renderPrevisionsPage: "previsions.js",
    loadPriceChart: "stock_chart.js",
    drawPriceChart: "stock_chart.js",
    fetchLiveScore: "live_score.js",
    loadLiveRank: "live_score.js",
    renderLiveRankBadge: "badges.js",
    getRankBadge: "badges.js",
    initRankHistory: "badges.js",
    saveRankHistory: "badges.js",
    renderRankCards: "ranking.js",
    startAutoRefresh: "ranking.js",
    openBacktest: "backtest.js",
    openMarkowitz: "markowitz.js",
    launchMarkowitz: "markowitz.js",
    openCompareAnalysis: "compare_analysis.js",
    loadAlertsLocal: "alerts.js",
    updateAlertBadge: "alerts.js",
    renderAlertsPanel: "alerts.js",
    renderSmartAlertsPanel: "alerts.js",
    setAlert: "alerts.js",
    showAlertModal: "alerts.js",
    checkAlertsWithPrices: "alerts.js",
    initCompanyTabs: "company-tabs.js",
    getDivConfidenceBadge: "data_confidence.js",
    getDivYieldHtml: "data_confidence.js",
    getRecurringDivStocks: "data_confidence.js",
    getDivSourceTooltip: "data_confidence.js",
    simInit: "simulator.js",
    openCompare: "compare.js",
    renderCompare: "compare.js"
  };

  var REPLAY = {
    "rank_v2.js": "rank",
    "welcome_v2.js": "welcome",
    "top3_podium.js": "rank",
    "signaux_v2.js": "signals",
    "news_v2.js": "news",
    "screener.js": "screener",
    "previsions.js": "signals"
  };

  window.BRVM_MODULES = window.BRVM_MODULES || {};
  window.BRVM_SYMBOL_FILE = SYMBOL_FILE;

  function showFailure(sectionId) {
    var host = sectionId ? document.getElementById(sectionId) : null;
    if (!host) host = document.querySelector(".main") || document.body;
    if (!host || host.querySelector("[data-brvm-fallback]")) return;
    var box = document.createElement("div");
    box.className = "card";
    box.setAttribute("data-brvm-fallback", "1");
    box.setAttribute("role", "alert");
    var p = document.createElement("p");
    p.style.margin = "0 0 10px";
    p.textContent = MSG;
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn btn-o";
    btn.textContent = BTN;
    btn.addEventListener("click", function () { window.location.reload(); });
    box.appendChild(p);
    box.appendChild(btn);
    host.insertBefore(box, host.firstChild);
  }

  function replay(file) {
    var page = REPLAY[file];
    if (!page) return;
    var loaders;
    try { loaders = pageLoaders; } catch (e) { return; }
    if (!loaders || typeof loaders[page] !== "function") return;
    var el = document.getElementById("page-" + page);
    if (!el || !el.classList.contains("on")) return;
    try { loaders[page](); } catch (e2) {}
  }

  function repriseInit(file) {
    if (document.readyState === "loading") return;
    try {
      if (file === "badges.js" && typeof initRankHistory === "function") initRankHistory();
      if (file === "screener_lazy.js" && typeof window._brvmScreenerLazyArm === "function") {
        window._brvmScreenerLazyArm();
      }
    } catch (e) {}
  }

  function loadAttempt(file, attempt) {
    var s = document.createElement("script");
    var token = window.BRVM_ASSET_V || "1";
    s.src = "/" + file + "?v=" + encodeURIComponent(token) + "&retry=" + attempt;
    s.async = false;
    s.setAttribute("data-brvm-mod", file);
    s.onload = function () {
      window.BRVM_MODULES[file] = "ok";
      replay(file);
      repriseInit(file);
    };
    s.onerror = function () {
      if (attempt < RETRIES) {
        window.setTimeout(function () { loadAttempt(file, attempt + 1); }, 700);
      } else {
        window.BRVM_MODULES[file] = "fail";
        showFailure(SECTIONS[file]);
      }
    };
    document.head.appendChild(s);
  }

  function brvmOnScriptError(file) {
    if (!file || window.BRVM_MODULES[file]) return;
    window.BRVM_MODULES[file] = "retry";
    window.setTimeout(function () { loadAttempt(file, 1); }, 250);
  }

  function brvmMissing(name) {
    var file = SYMBOL_FILE[name];
    if (!file) return;
    if (window.BRVM_MODULES[file] === "fail") showFailure(SECTIONS[file]);
  }

  window.brvmOnScriptError = brvmOnScriptError;
  window.brvmMissing = brvmMissing;
  window.brvmShowSectionFailure = showFailure;
  window.brvmCall = function (name) {
    var fn = window[name];
    if (typeof fn === "function" && !fn._brvmStub) {
      return fn.apply(null, Array.prototype.slice.call(arguments, 1));
    }
    brvmMissing(name);
  };

  window.brvmFlushPending = function () {
    var pending = window.BRVM_PENDING_ERRORS || [];
    window.BRVM_PENDING_ERRORS = [];
    var i;
    for (i = 0; i < pending.length; i++) brvmOnScriptError(pending[i]);
  };
  window.brvmFlushPending();
})();
