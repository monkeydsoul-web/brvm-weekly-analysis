// dashboard/welcome_v2.js — Sprint 6b : Accueil hero Marché

function loadWelcomeHero() {
  var pw = document.getElementById('page-welcome');
  var pm = document.getElementById('page-marche');
  if (!pw || !pm) return;

  // Garde anti-doublon : contenu déjà fusionné, juste re-render
  if (pm.parentElement === pw) {
    if (typeof _renderMarketPage !== 'undefined') _renderMarketPage();
    return;
  }

  // Masquer le bloc 3 portes
  var hero  = pw.querySelector('.welcome-hero');
  var cards = pw.querySelector('.welcome-cards');
  if (hero)  hero.style.display = 'none';
  if (cards) cards.style.display = 'none';

  // Déplacer #page-marche dans #page-welcome
  pm.classList.remove('page');
  pm.style.display = 'block';
  pm.style.padding = '0';
  pw.appendChild(pm);

  // Masquer le bouton Retour hérité de #page-marche (sans sens sur l'Accueil)
  var backBtn = pm.querySelector('.brvm-back-btn');
  if (backBtn) backBtn.style.display = 'none';

  // Rendre
  if (typeof _renderMarketPage !== 'undefined') _renderMarketPage();
}
