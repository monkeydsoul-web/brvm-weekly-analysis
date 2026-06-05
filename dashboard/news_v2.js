// dashboard/news_v2.js — Refonte Actualites : Google News en vedette + tableau dividendes 2026

async function renderNewsV2() {
  const page = document.getElementById('page-news');
  if (!page) return;

  // Rebind du filtre ticker vers renderNewsV2
  const sel = document.getElementById('news-ticker-filter');
  if (sel) {
    if (sel.options.length <= 1) {
      const tickers = [...new Set((window.scores || []).map(x => x.ticker).filter(Boolean))].sort();
      tickers.forEach(t => sel.add(new Option(t, t)));
    }
    sel.onchange = renderNewsV2;
  }

  // Masquer les anciennes cards, creer le conteneur V2 une seule fois
  let v2 = document.getElementById('news-v2-main');
  if (!v2) {
    page.querySelectorAll(':scope > .card').forEach(c => { c.style.display = 'none'; });
    v2 = document.createElement('div');
    v2.id = 'news-v2-main';
    const ph = page.querySelector('.ph');
    if (ph && ph.nextElementSibling) {
      page.insertBefore(v2, ph.nextElementSibling);
    } else {
      page.appendChild(v2);
    }
  }

  v2.innerHTML =
    '<div class="card" style="margin-bottom:14px">' +
    '<div class="ct" style="margin-bottom:10px">&#128225; Google News &mdash; Presse financi&egrave;re BRVM</div>' +
    '<div id="nv2-gnews-list" style="min-height:60px">Chargement...</div>' +
    '</div>' +
    '<div class="card">' +
    '<div class="ct" style="margin-bottom:10px">&#128176; Dividendes 2026</div>' +
    '<div id="nv2-div-list" style="min-height:40px">Chargement...</div>' +
    '</div>';

  await Promise.all([_nv2LoadGNews(), _nv2LoadDividends()]);
}

async function _nv2LoadGNews() {
  const el = document.getElementById('nv2-gnews-list');
  if (!el) return;
  const sel = document.getElementById('news-ticker-filter');
  const ticker = sel ? sel.value : '';
  const params = new URLSearchParams({ limit: 60 });
  if (ticker) params.set('ticker', ticker);
  try {
    const d = await fetch('/api/news?' + params).then(r => r.json());
    const items = d.data || [];
    if (!items.length) {
      el.innerHTML = '<div style="text-align:center;padding:20px;color:var(--t2);font-size:12px">Aucun article disponible.</div>';
      return;
    }
    el.innerHTML = items.map(function(a) {
      const rel = a.relevance || {};
      const score = rel.score || 0;
      const badge = score >= 80
        ? '<span style="font-size:9px;font-weight:700;padding:2px 7px;border-radius:10px;background:rgba(74,222,128,.15);color:var(--green);border:1px solid rgba(74,222,128,.3)">Tr&egrave;s pertinent</span>'
        : score >= 50
          ? '<span style="font-size:9px;font-weight:700;padding:2px 7px;border-radius:10px;background:rgba(96,165,250,.15);color:var(--blue);border:1px solid rgba(96,165,250,.3)">Pertinent</span>'
          : '';
      const ticker_badge = a.ticker
        ? '<span style="font-size:10px;font-weight:700;color:var(--accent)">' + a.ticker + '</span>'
        : '';
      const source_badge = a.source
        ? '<span style="font-size:10px;color:var(--t3)">' + a.source + '</span>'
        : '';
      const date_badge = '<span style="font-size:10px;color:var(--t3);margin-left:auto">' + (a.date || '') + '</span>';
      const titre = (a.titre || '').slice(0, 110);
      const titre_html = a.lien
        ? '<a href="' + a.lien + '" target="_blank" style="color:var(--text);text-decoration:none" onmouseover="this.style.color=\'var(--accent)\'" onmouseout="this.style.color=\'var(--text)\'">' + titre + '</a>'
        : titre;
      const resume_html = a.resume
        ? '<div style="font-size:11px;color:var(--t2);line-height:1.5">' + a.resume.slice(0, 140) + '</div>'
        : '';
      return '<div class="gnews-card">' +
        '<div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;flex-wrap:wrap">' +
        ticker_badge + badge + date_badge + source_badge +
        '</div>' +
        '<div style="font-size:12px;font-weight:600;color:var(--text);margin-bottom:3px;line-height:1.4">' + titre_html + '</div>' +
        resume_html +
        '</div>';
    }).join('');
  } catch (e) {
    el.innerHTML = '<div style="text-align:center;padding:20px;color:var(--t2);font-size:12px">Erreur de chargement.</div>';
  }
}

function _nv2ExtractTicker(item) {
  if (item.ticker && item.ticker !== 'None' && item.ticker !== null) return item.ticker;
  const contenu = item.contenu || '';
  const m = contenu.match(/symbole\s*:\s*([A-Z]{3,6})/i);
  if (m) return m[1];
  return '&mdash;';
}

async function _nv2LoadDividends() {
  const el = document.getElementById('nv2-div-list');
  if (!el) return;
  try {
    const d = await fetch('/api/announcements?type=dividendes&limit=200').then(r => r.json());
    const items = (d.data || []).filter(function(item) {
      const ref = item.date_paiement || item.date || '';
      return String(ref).startsWith('2026');
    });
    items.sort(function(a, b) {
      const da = String(a.date_paiement || a.date || '');
      const db = String(b.date_paiement || b.date || '');
      return da.localeCompare(db);
    });
    if (!items.length) {
      el.innerHTML = '<div style="text-align:center;padding:16px;color:var(--t2);font-size:12px">Aucun dividende 2026 disponible.</div>';
      return;
    }
    const withMontant = items.filter(function(x) { return x.montant_xof != null; }).length;
    const note = '<div style="font-size:10px;color:var(--t3);margin-bottom:8px">' +
      'Date de paiement 2026 &mdash; montant disponible pour ' + withMontant + '/' + items.length + ' entr&eacute;es' +
      '</div>';
    const rows = items.map(function(item) {
      const ticker = _nv2ExtractTicker(item);
      const date = item.date_paiement || item.date || '&mdash;';
      const montant = item.montant_xof != null
        ? (typeof fmtXOF === 'function' ? fmtXOF(item.montant_xof) : item.montant_xof.toLocaleString('fr-FR') + ' XOF')
        : '&mdash;';
      return '<tr>' +
        '<td style="padding:6px 4px;font-weight:600;color:var(--accent)">' + ticker + '</td>' +
        '<td style="padding:6px 4px">' + date + '</td>' +
        '<td style="padding:6px 4px;text-align:right">' + montant + '</td>' +
        '</tr>';
    }).join('');
    el.innerHTML = note +
      '<table style="width:100%;border-collapse:collapse;font-size:12px">' +
      '<thead><tr style="color:var(--t2);font-size:10px;font-weight:700;text-transform:uppercase;border-bottom:1px solid var(--border)">' +
      '<th style="text-align:left;padding:6px 4px">Soci&eacute;t&eacute;</th>' +
      '<th style="text-align:left;padding:6px 4px">Date de paiement</th>' +
      '<th style="text-align:right;padding:6px 4px">Montant</th>' +
      '</tr></thead>' +
      '<tbody>' + rows + '</tbody>' +
      '</table>';
  } catch (e) {
    el.innerHTML = '<div style="text-align:center;padding:16px;color:var(--t2);font-size:12px">Erreur de chargement.</div>';
  }
}
