// ── data_confidence.js — Indicateurs de fiabilité des données financières ──
// Lit div_confidence / div_flag / div_is_exceptional depuis window.scores[ticker]
// et fournit des badges HTML réutilisables dans toutes les vues.

// ─── Helpers ────────────────────────────────────────────────────────────────

function _divConf(sc) {
  // sc = entrée scores pour un ticker (objet depuis window.scores)
  return (sc && sc.div_confidence) || 'inconnue';
}

/**
 * Badge compact de confiance dividende.
 * Retourne une string HTML (<span>) à insérer inline.
 * @param {object} sc   - entrée scores du ticker
 * @param {object} opts - { short: bool } — court = juste l'icône, long = icône+texte
 */
function getDivConfidenceBadge(sc, opts) {
  if (!sc) return '';
  opts = opts || {};
  const conf  = _divConf(sc);
  const flag  = sc.div_flag || '';
  const excV  = sc.div_exceptional_value || 0;
  const src   = sc.div_source_detail || sc.div_source_used || '';
  const ecart = sc.div_ecart_boc_pdf != null ? Math.round(sc.div_ecart_boc_pdf) + '%' : null;

  let icon, color, title, label;

  if (flag === 'exceptionnel_non_recurrent') {
    icon  = '🔶';
    color = 'var(--amber)';
    label = opts.short ? '' : ' Exceptionnel';
    title = `Dividende exceptionnel non récurrent (${excV.toLocaleString('fr-FR')} XOF brut) · issu d'une opération ponctuelle (cession d'actifs, HAO) · exclu du rendement courant et du simulateur`;
  } else if (conf === 'haute') {
    icon  = '✓';
    color = 'var(--green)';
    label = '';
    title = `Données validées multi-source · ${src}`;
    if (opts.hideHaute) return ''; // confiance haute = badge optionnel
  } else if (conf === 'moyenne') {
    icon  = '~';
    color = 'var(--amber)';
    label = opts.short ? '' : ' À vérifier';
    title = `Source unique ou divergence modérée · ${src}${ecart ? ' · écart BOC/PDF ' + ecart : ''}`;
  } else if (conf === 'faible') {
    icon  = '⚠';
    color = '#f97316';
    label = opts.short ? '' : ' À vérifier';
    title = `Sources divergentes (>${(sc.div_ecart_boc_pdf || 30).toFixed(0)}% d'écart) · BOC retenu · ${src}`;
  } else {
    icon  = '?';
    color = 'var(--t3)';
    label = '';
    title = 'Aucune source vérifiable disponible';
  }

  const style = `display:inline-flex;align-items:center;gap:2px;font-size:10px;color:${color};`
    + `background:${color}18;border-radius:3px;padding:1px 4px;cursor:help;white-space:nowrap;vertical-align:middle;margin-left:3px`;

  return `<span class="tt div-conf-badge" style="${style}" data-tt="${title}">${icon}${label}</span>`;
}

/**
 * Rendu du rendement dividende avec badge de confiance.
 * Retourne HTML complet : "7.3% <badge>"
 * @param {object} sc      - entrée scores du ticker
 * @param {object} opts    - { hideHaute, short, zeroLabel }
 */
function getDivYieldHtml(sc, opts) {
  if (!sc) return '—';
  opts = opts || {};
  const flag = sc.div_flag || '';
  const dy   = sc.div_yield || 0;
  const excV = sc.div_exceptional_value || 0;

  // Valeur affichée : pour l'exceptionnel, on montre le brut barré + 🔶, pas le 0%
  let yText;
  if (flag === 'exceptionnel_non_recurrent' && excV > 0) {
    const excYield = sc.price > 0 ? (excV / sc.price * 100).toFixed(1) : '?';
    yText = `<span style="text-decoration:line-through;color:var(--t3)">${excYield}%</span>`;
  } else if (dy > 0) {
    yText = dy.toFixed(1) + '%';
  } else {
    yText = opts.zeroLabel || '—';
  }

  const badge = getDivConfidenceBadge(sc, opts);
  return `${yText}${badge}`;
}

/**
 * Filtre la liste des scores pour exclure les dividendes exceptionnels
 * des calculs récurrents (simulateur, Top rendements, scoring DDM).
 * @param {Array} scoresList
 * @returns {Array} tickers avec div_yield > 0 ET non exceptionnels
 */
function getRecurringDivStocks(scoresList) {
  if (!Array.isArray(scoresList)) return [];
  return scoresList.filter(x =>
    (x.div_yield || 0) > 0 &&
    !x.div_is_exceptional &&
    x.div_flag !== 'exceptionnel_non_recurrent'
  );
}

/**
 * Tooltip de source dividende pour la fiche société.
 * Retourne une string descriptive longue.
 */
function getDivSourceTooltip(sc) {
  if (!sc) return '';
  const flag  = sc.div_flag || '';
  const conf  = _divConf(sc);
  const src   = sc.div_source_detail || '';
  const excV  = sc.div_exceptional_value || 0;

  if (flag === 'exceptionnel_non_recurrent') {
    return `Dividende exceptionnel non récurrent · Valeur brute : ${excV.toLocaleString('fr-FR')} XOF`
      + ` · Non inclus dans les calculs de revenu passif récurrent (DDM, simulateur, portefeuille)`
      + (src ? ` · Source : ${src}` : '');
  }
  const confLabel = conf === 'haute' ? 'Validé multi-source' : conf === 'moyenne' ? 'Source modérément fiable' : 'À vérifier';
  return `${confLabel} · ${src}`;
}

// ─── Patch renderDiv : exclut exceptionnels, ajoute badges ──────────────────

// Surcharge légère de renderDiv existante (appelée après le chargement)
// IMPORTANT : ne remplace pas renderDiv, étend seulement _divData post-fetch
// Les fonctions de rendu appellent getRecurringDivStocks() directement.

// ─── Export global ──────────────────────────────────────────────────────────
window.getDivConfidenceBadge = getDivConfidenceBadge;
window.getDivYieldHtml       = getDivYieldHtml;
window.getRecurringDivStocks = getRecurringDivStocks;
window.getDivSourceTooltip   = getDivSourceTooltip;
