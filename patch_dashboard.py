#!/usr/bin/env python3
"""
patch_dashboard.py — Ajoute les pages Candlesticks et Backtesting au dashboard
Usage : python3 patch_dashboard.py
"""
import re
from pathlib import Path

BASE  = Path(__file__).parent
HTML  = BASE / "dashboard" / "index.html"

if not HTML.exists():
    print("✗ dashboard/index.html non trouvé")
    exit(1)

content = HTML.read_text(encoding="utf-8")
original_size = len(content)

# ─── 1. Ajouter les entrées de navigation ────────────────────────────────────
# Chercher la nav existante et ajouter après "Commodités"
NAV_PATCH = """
            <a href="#" class="nav-item" data-page="candlestick" onclick="showPage('candlestick')">
              <span class="nav-icon">🕯️</span>
              <span>Bougies</span>
            </a>
            <a href="#" class="nav-item" data-page="backtesting" onclick="showPage('backtesting')">
              <span class="nav-icon">📊</span>
              <span>Backtesting</span>
            </a>"""

# Trouver l'ancre Commodités dans la nav
commodites_nav = 'data-page="commodites"'
if commodites_nav in content and "data-page=\"candlestick\"" not in content:
    # Trouver la fin du bloc <a> de Commodités
    idx = content.find(commodites_nav)
    end_a = content.find("</a>", idx) + 4
    content = content[:end_a] + NAV_PATCH + content[end_a:]
    print("✓ Liens nav ajoutés (Bougies + Backtesting)")
else:
    print("→ Liens nav déjà présents ou Commodités non trouvé")

# ─── 2. Ajouter la page Candlestick ─────────────────────────────────────────
CANDLESTICK_PAGE = """
    <!-- ═══ PAGE BOUGIES (CANDLESTICK) ════════════════════════════════════════ -->
    <div id="page-candlestick" class="page" style="display:none">
      <div class="page-header" style="display:flex;align-items:center;justify-content:space-between;margin-bottom:24px">
        <div>
          <h1 style="font-size:24px;font-weight:600;color:var(--text-primary,#e2e8f0);margin:0">Graphiques Bougies</h1>
          <p style="color:var(--text-secondary,#94a3b8);margin:4px 0 0;font-size:14px">Historique OHLC hebdomadaire — données 2016-2025</p>
        </div>
        <div style="display:flex;gap:8px;align-items:center">
          <select id="cs-ticker-select" onchange="loadCandlestick()" style="background:#1e293b;color:#e2e8f0;border:1px solid #334155;border-radius:6px;padding:8px 12px;font-size:13px">
            <option value="SGBC">SGBC</option>
            <option value="CBIBF">CBIBF</option>
            <option value="SNTS">SNTS</option>
            <option value="NSBC">NSBC</option>
            <option value="ORAC">ORAC</option>
            <option value="SIBC">SIBC</option>
            <option value="NTLC">NTLC</option>
            <option value="LNBB">LNBB</option>
            <option value="BOAB">BOAB</option>
            <option value="SMBC">SMBC</option>
          </select>
          <div style="display:flex;gap:4px">
            <button onclick="setCsPeriod('1y')" id="btn-cs-1y" style="background:#3b82f6;color:#fff;border:none;border-radius:6px;padding:8px 16px;font-size:13px;cursor:pointer">1 an</button>
            <button onclick="setCsPeriod('5y')" id="btn-cs-5y" style="background:#1e293b;color:#94a3b8;border:1px solid #334155;border-radius:6px;padding:8px 16px;font-size:13px;cursor:pointer">5 ans</button>
          </div>
        </div>
      </div>

      <!-- Carte principale SVG candlestick -->
      <div style="background:#0f172a;border-radius:12px;padding:20px;margin-bottom:20px;border:1px solid #1e293b">
        <div id="cs-chart-container" style="min-height:320px;display:flex;align-items:center;justify-content:center">
          <div id="cs-loading" style="color:#64748b;font-size:14px">Sélectionnez une action…</div>
        </div>
      </div>

      <!-- Métriques résumé -->
      <div id="cs-metrics" style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px"></div>

      <!-- Table OHLC récente -->
      <div style="background:#1e293b;border-radius:12px;padding:20px;border:1px solid #334155">
        <h3 style="color:#e2e8f0;margin:0 0 16px;font-size:14px;font-weight:500">Dernières bougies hebdomadaires</h3>
        <div style="overflow-x:auto">
          <table id="cs-ohlc-table" style="width:100%;border-collapse:collapse;font-size:13px">
            <thead>
              <tr style="border-bottom:1px solid #334155">
                <th style="padding:8px 12px;color:#64748b;text-align:left;font-weight:500">Semaine</th>
                <th style="padding:8px 12px;color:#64748b;text-align:right;font-weight:500">Ouv.</th>
                <th style="padding:8px 12px;color:#64748b;text-align:right;font-weight:500">Haut</th>
                <th style="padding:8px 12px;color:#64748b;text-align:right;font-weight:500">Bas</th>
                <th style="padding:8px 12px;color:#64748b;text-align:right;font-weight:500">Clôt.</th>
                <th style="padding:8px 12px;color:#64748b;text-align:right;font-weight:500">Var.</th>
              </tr>
            </thead>
            <tbody id="cs-ohlc-tbody">
              <tr><td colspan="6" style="padding:20px;text-align:center;color:#64748b">–</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
    <!-- ═══ FIN PAGE BOUGIES ═══════════════════════════════════════════════════ -->"""

BACKTESTING_PAGE = """
    <!-- ═══ PAGE BACKTESTING ══════════════════════════════════════════════════ -->
    <div id="page-backtesting" class="page" style="display:none">
      <div class="page-header" style="margin-bottom:24px">
        <h1 style="font-size:24px;font-weight:600;color:var(--text-primary,#e2e8f0);margin:0">Backtesting des Scores</h1>
        <p style="color:var(--text-secondary,#94a3b8);margin:4px 0 0;font-size:14px">Validation empirique : est-ce qu'un score élevé prédit réellement la surperformance ?</p>
      </div>

      <!-- Bouton de lancement -->
      <div style="margin-bottom:20px;display:flex;gap:12px;align-items:center">
        <button onclick="runBacktesting(false)" id="btn-bt-run"
          style="background:#3b82f6;color:#fff;border:none;border-radius:8px;padding:10px 24px;font-size:14px;font-weight:500;cursor:pointer">
          ▶ Lancer le backtesting
        </button>
        <button onclick="runBacktesting(true)"
          style="background:#1e293b;color:#94a3b8;border:1px solid #334155;border-radius:8px;padding:10px 16px;font-size:13px;cursor:pointer">
          ↺ Recalculer
        </button>
        <span id="bt-status" style="color:#64748b;font-size:13px"></span>
      </div>

      <!-- Résumé validation -->
      <div id="bt-validation-cards" style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:24px"></div>

      <!-- Tableau détail par ticker -->
      <div style="background:#1e293b;border-radius:12px;padding:20px;border:1px solid #334155">
        <h3 style="color:#e2e8f0;margin:0 0 16px;font-size:14px;font-weight:500">Détail par action</h3>
        <div style="overflow-x:auto">
          <table id="bt-detail-table" style="width:100%;border-collapse:collapse;font-size:13px">
            <thead>
              <tr style="border-bottom:1px solid #334155">
                <th style="padding:8px 12px;color:#64748b;text-align:left;font-weight:500">Action</th>
                <th style="padding:8px 12px;color:#64748b;text-align:center;font-weight:500">Score</th>
                <th style="padding:8px 12px;color:#64748b;text-align:right;font-weight:500">Rend. 3M</th>
                <th style="padding:8px 12px;color:#64748b;text-align:right;font-weight:500">Rend. 6M</th>
                <th style="padding:8px 12px;color:#64748b;text-align:right;font-weight:500">Rend. 12M</th>
                <th style="padding:8px 12px;color:#64748b;text-align:center;font-weight:500">% Haussier</th>
              </tr>
            </thead>
            <tbody id="bt-detail-tbody">
              <tr><td colspan="6" style="padding:20px;text-align:center;color:#64748b">Lancez le backtesting pour voir les résultats</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
    <!-- ═══ FIN PAGE BACKTESTING ═══════════════════════════════════════════════ -->"""

# Chercher où injecter les nouvelles pages (avant </main> ou avant le dernier </div> du content)
if "page-candlestick" not in content:
    # Insérer avant la fermeture du main content (avant le dernier grand </div>)
    # Stratégie : trouver page-commodites et insérer après
    marker = 'id="page-commodites"'
    if marker in content:
        # Trouver la fin du bloc commodites
        idx = content.rfind("<!-- ═══", 0, content.find(marker) + 1)
        # Chercher le prochain commentaire de fermeture après commodites
        end_marker_search = content.find("<!-- ═══ FIN PAGE", content.find(marker))
        if end_marker_search > 0:
            end_of_commodites = content.find("-->", end_marker_search) + 3
            content = content[:end_of_commodites] + "\n" + CANDLESTICK_PAGE + "\n" + BACKTESTING_PAGE + content[end_of_commodites:]
            print("✓ Pages Bougies et Backtesting insérées après Commodités")
        else:
            # Fallback : insérer avant </body>
            content = content.replace("</body>", CANDLESTICK_PAGE + "\n" + BACKTESTING_PAGE + "\n</body>")
            print("✓ Pages insérées avant </body> (fallback)")
    else:
        content = content.replace("</body>", CANDLESTICK_PAGE + "\n" + BACKTESTING_PAGE + "\n</body>")
        print("✓ Pages insérées avant </body>")
else:
    print("→ Pages déjà présentes")

# ─── 3. Ajouter le JavaScript des deux pages ─────────────────────────────────
JS_PATCH = """
  // ═══ CANDLESTICK ════════════════════════════════════════════════════════
  let _csPeriod = '1y';

  function setCsPeriod(p) {
    _csPeriod = p;
    document.getElementById('btn-cs-1y').style.background = p === '1y' ? '#3b82f6' : '#1e293b';
    document.getElementById('btn-cs-1y').style.color       = p === '1y' ? '#fff'    : '#94a3b8';
    document.getElementById('btn-cs-5y').style.background = p === '5y' ? '#3b82f6' : '#1e293b';
    document.getElementById('btn-cs-5y').style.color       = p === '5y' ? '#fff'    : '#94a3b8';
    loadCandlestick();
  }

  async function loadCandlestick() {
    const ticker = document.getElementById('cs-ticker-select').value;
    const container = document.getElementById('cs-chart-container');
    const metricsEl = document.getElementById('cs-metrics');
    const tbody = document.getElementById('cs-ohlc-tbody');
    if (!ticker) return;

    container.innerHTML = '<div style="color:#64748b;font-size:14px">Chargement…</div>';

    try {
      const resp = await fetch(`/api/candlestick/${ticker}?period=${_csPeriod}`);
      const data = await resp.json();

      if (data.error) {
        container.innerHTML = `<div style="color:#ef4444">${data.error}</div>`;
        return;
      }

      // Afficher le SVG
      container.innerHTML = data.svg || '<div style="color:#64748b">SVG non disponible</div>';

      // Métriques
      const ohlc = data.ohlc || [];
      if (ohlc.length > 0) {
        const last  = ohlc[ohlc.length - 1];
        const first = ohlc[0];
        const perf  = ((last.close - first.close) / first.close * 100).toFixed(1);
        const high52 = Math.max(...ohlc.map(c => c.high));
        const low52  = Math.min(...ohlc.map(c => c.low));
        const bullPct = (ohlc.filter(c => c.close >= c.open).length / ohlc.length * 100).toFixed(0);
        const perfColor = parseFloat(perf) >= 0 ? '#22c55e' : '#ef4444';
        const perfSign  = parseFloat(perf) >= 0 ? '+' : '';

        metricsEl.innerHTML = `
          <div style="background:#1e293b;border-radius:10px;padding:16px;border:1px solid #334155">
            <div style="color:#64748b;font-size:12px;margin-bottom:6px">Clôture actuelle</div>
            <div style="color:#e2e8f0;font-size:20px;font-weight:600">${last.close.toLocaleString()} FCFA</div>
          </div>
          <div style="background:#1e293b;border-radius:10px;padding:16px;border:1px solid #334155">
            <div style="color:#64748b;font-size:12px;margin-bottom:6px">Performance période</div>
            <div style="color:${perfColor};font-size:20px;font-weight:600">${perfSign}${perf}%</div>
          </div>
          <div style="background:#1e293b;border-radius:10px;padding:16px;border:1px solid #334155">
            <div style="color:#64748b;font-size:12px;margin-bottom:6px">Plage Haut / Bas</div>
            <div style="color:#e2e8f0;font-size:14px;font-weight:500">${high52.toLocaleString()} / ${low52.toLocaleString()}</div>
          </div>
          <div style="background:#1e293b;border-radius:10px;padding:16px;border:1px solid #334155">
            <div style="color:#64748b;font-size:12px;margin-bottom:6px">% semaines haussières</div>
            <div style="color:#22c55e;font-size:20px;font-weight:600">${bullPct}%</div>
          </div>`;

        // Table OHLC (20 dernières semaines)
        const recent = ohlc.slice(-20).reverse();
        tbody.innerHTML = recent.map(c => {
          const chg = ((c.close - c.open) / c.open * 100).toFixed(2);
          const color = parseFloat(chg) >= 0 ? '#22c55e' : '#ef4444';
          const sign  = parseFloat(chg) >= 0 ? '+' : '';
          return `<tr style="border-bottom:1px solid #1e293b">
            <td style="padding:7px 12px;color:#94a3b8">${c.date}</td>
            <td style="padding:7px 12px;color:#e2e8f0;text-align:right">${c.open.toLocaleString()}</td>
            <td style="padding:7px 12px;color:#22c55e;text-align:right">${c.high.toLocaleString()}</td>
            <td style="padding:7px 12px;color:#ef4444;text-align:right">${c.low.toLocaleString()}</td>
            <td style="padding:7px 12px;color:#e2e8f0;text-align:right;font-weight:500">${c.close.toLocaleString()}</td>
            <td style="padding:7px 12px;color:${color};text-align:right">${sign}${chg}%</td>
          </tr>`;
        }).join('');
      }

    } catch (err) {
      container.innerHTML = `<div style="color:#ef4444">Erreur: ${err.message}</div>`;
    }
  }

  // ═══ BACKTESTING ════════════════════════════════════════════════════════
  async function runBacktesting(force = false) {
    const btn    = document.getElementById('btn-bt-run');
    const status = document.getElementById('bt-status');
    const cards  = document.getElementById('bt-validation-cards');
    const tbody  = document.getElementById('bt-detail-tbody');

    btn.disabled = true;
    btn.textContent = '⏳ Calcul en cours…';
    status.textContent = 'Analyse de l\'historique…';

    try {
      const url = `/api/backtesting${force ? '?force=1' : ''}`;
      const resp = await fetch(url);
      const data = await resp.json();

      if (data.error) {
        status.textContent = 'Erreur: ' + data.error;
        return;
      }

      status.textContent = data.from_cache
        ? `(Résultats mis en cache — ${data.generated_at?.slice(0,10) || ''})`
        : `✓ Calculé sur ${data.n_tickers} actions`;

      // Cartes de validation par horizon
      const horizons = data.validation_summary || {};
      cards.innerHTML = Object.entries(horizons).map(([h, v]) => {
        const valid  = v.model_valid;
        const color  = valid ? '#22c55e' : '#f59e0b';
        const bg     = valid ? 'rgba(34,197,94,0.08)' : 'rgba(245,158,11,0.08)';
        const border = valid ? 'rgba(34,197,94,0.25)' : 'rgba(245,158,11,0.25)';
        const icon   = valid ? '✓' : '~';
        return `
          <div style="background:${bg};border-radius:12px;padding:20px;border:1px solid ${border}">
            <div style="color:${color};font-size:28px;font-weight:700;margin-bottom:4px">${icon}</div>
            <div style="color:#e2e8f0;font-size:16px;font-weight:600;margin-bottom:8px">Horizon ${h} mois</div>
            <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:4px">
              <span style="color:#64748b">Score ≥40 :</span>
              <span style="color:#22c55e;font-weight:500">+${v.high_score_avg_return?.toFixed(1) ?? '–'}%</span>
            </div>
            <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:4px">
              <span style="color:#64748b">Score &lt;40 :</span>
              <span style="color:#ef4444;font-weight:500">+${v.low_score_avg_return?.toFixed(1) ?? '–'}%</span>
            </div>
            <div style="display:flex;justify-content:space-between;font-size:13px">
              <span style="color:#64748b">Prime :</span>
              <span style="color:${color};font-weight:600">${v.premium_bps ?? '–'} bps</span>
            </div>
          </div>`;
      }).join('');

      // Tableau détail
      const tickers = Object.values(data.ticker_results || {})
        .filter(t => t.current_score > 0)
        .sort((a, b) => (b.current_score || 0) - (a.current_score || 0));

      if (tickers.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="padding:20px;text-align:center;color:#64748b">Aucune donnée disponible</td></tr>';
        return;
      }

      tbody.innerHTML = tickers.map(t => {
        const h3  = t.horizons?.[3]  || {};
        const h6  = t.horizons?.[6]  || {};
        const h12 = t.horizons?.[12] || {};
        const score = t.current_score || 0;
        const scoreBg = score >= 45 ? 'rgba(34,197,94,0.15)' : score >= 35 ? 'rgba(245,158,11,0.15)' : 'rgba(239,68,68,0.15)';
        const scoreColor = score >= 45 ? '#22c55e' : score >= 35 ? '#f59e0b' : '#ef4444';

        function retCell(h) {
          const v = h.avg_return_pct;
          if (v == null) return '<td style="padding:7px 12px;color:#475569;text-align:right">–</td>';
          const c = v >= 0 ? '#22c55e' : '#ef4444';
          return `<td style="padding:7px 12px;color:${c};text-align:right;font-weight:500">${v >= 0 ? '+' : ''}${v.toFixed(1)}%</td>`;
        }

        return `<tr style="border-bottom:1px solid #1e293b">
          <td style="padding:7px 12px;color:#e2e8f0;font-weight:500">${t.ticker}</td>
          <td style="padding:7px 12px;text-align:center">
            <span style="background:${scoreBg};color:${scoreColor};border-radius:6px;padding:2px 10px;font-size:12px;font-weight:600">${score}/80</span>
          </td>
          ${retCell(h3)}
          ${retCell(h6)}
          ${retCell(h12)}
          <td style="padding:7px 12px;color:#94a3b8;text-align:center">${h12.positive_pct?.toFixed(0) ?? '–'}%</td>
        </tr>`;
      }).join('');

    } catch (err) {
      status.textContent = 'Erreur réseau: ' + err.message;
    } finally {
      btn.disabled = false;
      btn.textContent = '▶ Lancer le backtesting';
    }
  }
  // ═══ FIN BACKTESTING / CANDLESTICK JS ═══════════════════════════════════
"""

# Injecter avant la fermeture </script> principale ou avant </body>
if "loadCandlestick" not in content:
    # Chercher le dernier </script> avant </body>
    last_script = content.rfind("</script>")
    if last_script > 0:
        content = content[:last_script] + JS_PATCH + "\n" + content[last_script:]
        print("✓ JavaScript Candlestick + Backtesting injecté")
    else:
        content = content.replace("</body>", f"<script>{JS_PATCH}</script>\n</body>")
        print("✓ JavaScript injecté dans nouveau bloc <script>")
else:
    print("→ JavaScript déjà présent")

# ─── 4. Sauvegarder ──────────────────────────────────────────────────────────
HTML.write_text(content, encoding="utf-8")
new_size = len(content)
delta = new_size - original_size

print(f"\n{'='*50}")
print(f"✓ dashboard/index.html mis à jour")
print(f"  Taille : {original_size:,} → {new_size:,} octets (+{delta:,})")
print(f"\nRedémarrez Flask et rechargez le dashboard :")
print(f"  Ctrl+C  →  source ~/.zprofile && python3 app.py")
