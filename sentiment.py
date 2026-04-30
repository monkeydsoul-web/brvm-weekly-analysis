import os as _os_fix
try:
    from dotenv import load_dotenv as _ld; _ld()
except ImportError:
    pass

"""
BRVM Sentiment Analyzer — Phase 3
Analyse les news avec l'API Claude pour produire :
  - Score de sentiment par action (-5 à +5)
  - Résumé des actualités de la semaine
  - Identification des événements clés (résultats, dividendes, fusions)
  - Ajustement du score composite
"""

import os
import json
import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

# ── Configuration API Claude ───────────────────────────────────────────────────
# Remplis ta clé API Claude dans le fichier .env ou comme variable d'environnement
# export ANTHROPIC_API_KEY="sk-ant-..."
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-20250514"
CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"


def call_claude(prompt: str, system: str = "", max_tokens: int = 1000) -> str:
    """Appelle l'API Claude et retourne le texte de réponse"""
    if not ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY non définie — analyse IA désactivée")
        return ""

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": CLAUDE_MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system

    try:
        r = requests.post(CLAUDE_API_URL, headers=headers, json=body, timeout=30)
        r.raise_for_status()
        data = r.json()
        return data["content"][0]["text"]
    except Exception as e:
        logger.error(f"Erreur API Claude: {e}")
        return ""


def analyze_ticker_news(ticker: str, name: str, news_list: list[dict]) -> dict:
    """
    Analyse les news d'une action spécifique avec Claude.
    Retourne: sentiment_score, resume, evenements_cles, impact_estimé
    """
    if not news_list:
        return {
            "ticker": ticker,
            "sentiment_score": 0,
            "sentiment_label": "Neutre",
            "resume": "Aucune actualité cette semaine.",
            "evenements_cles": [],
            "impact_score_adj": 0,
        }

    # Préparer le contexte des news
    news_text = "\n".join([
        f"- [{a['source']}] {a['title']}"
        for a in news_list[:10]  # Max 10 articles par action
    ])

    system = """Tu es un analyste financier expert de la BRVM (Bourse Régionale des Valeurs Mobilières 
d'Afrique de l'Ouest). Tu analyses les actualités financières et produis des analyses concises et précises.
Réponds UNIQUEMENT en JSON valide, sans markdown ni backticks."""

    prompt = f"""Analyse ces actualités de la semaine pour l'action {ticker} ({name}) cotée à la BRVM.

ACTUALITÉS:
{news_text}

Produis un JSON avec exactement ces champs:
{{
  "sentiment_score": <entier de -5 à +5, 0=neutre, +5=très positif, -5=très négatif>,
  "sentiment_label": "<Très positif|Positif|Légèrement positif|Neutre|Légèrement négatif|Négatif|Très négatif>",
  "resume": "<résumé en 2 phrases max des actualités les plus importantes>",
  "evenements_cles": ["<événement 1>", "<événement 2>"],
  "type_news": "<résultats|dividende|nomination|fusion|macro|autre>",
  "impact_score_adj": <ajustement du score de valorisation entre -2.0 et +2.0, float>
}}

Règles pour impact_score_adj:
- Résultats en forte hausse (+20%+) → +1.5 à +2.0
- Résultats en hausse modérée → +0.5 à +1.0
- Résultats stables → 0
- Résultats en baisse → -0.5 à -1.5
- Dividende surprise à la hausse → +1.0
- Restructuration, problèmes de gouvernance → -1.0 à -2.0
"""

    raw = call_claude(prompt, system=system, max_tokens=500)

    # Parser la réponse JSON
    try:
        # Nettoyer les backticks éventuels
        cleaned = raw.strip().strip("```json").strip("```").strip()
        result = json.loads(cleaned)
        result["ticker"] = ticker
        return result
    except Exception as e:
        logger.warning(f"Parsing JSON sentiment {ticker}: {e} — Réponse: {raw[:200]}")
        return {
            "ticker": ticker,
            "sentiment_score": 0,
            "sentiment_label": "Neutre",
            "resume": raw[:300] if raw else "Analyse non disponible.",
            "evenements_cles": [],
            "type_news": "autre",
            "impact_score_adj": 0.0,
        }


def generate_market_summary(all_news: list[dict], macro: dict) -> str:
    """Génère un résumé global du marché BRVM pour la semaine"""
    if not ANTHROPIC_API_KEY:
        return "Analyse IA non disponible (ANTHROPIC_API_KEY non configurée)."

    macro_news = [a for a in all_news if a.get("is_macro_news")]
    news_text = "\n".join([f"- {a['title']}" for a in macro_news[:15]])

    brvm_ci = macro.get("BRVM_COMPOSITE", "N/D")
    brvm_30 = macro.get("BRVM_30", "N/D")
    fcfa_usd = macro.get("FCFA_per_USD", "N/D")

    prompt = f"""En tant qu'analyste BRVM, rédige un résumé de marché pour la semaine en cours.

CONTEXTE MACRO:
- BRVM Composite: {brvm_ci}
- BRVM 30: {brvm_30}
- FCFA/USD: {fcfa_usd}

ACTUALITÉS MACRO DE LA SEMAINE:
{news_text if news_text else "Aucune actualité macro spécifique cette semaine."}

Rédige un résumé de marché en 3-4 phrases, style rapport professionnel.
Mentionne: orientation du marché, secteurs en vue, thème dominant de la semaine.
Réponds directement avec le texte, sans introduction."""

    return call_claude(prompt, max_tokens=300) or "Résumé de marché non disponible cette semaine."


def analyze_all_news(
    all_news: list[dict],
    df_scores,
    macro: dict,
) -> tuple:
    """
    Analyse le sentiment pour toutes les actions qui ont des news.
    Retourne: (df_scores enrichi, sentiment_dict, market_summary)
    """
    import pandas as pd

    # Grouper les news par ticker
    news_by_ticker = {}
    for article in all_news:
        for ticker in article.get("tickers", []):
            if ticker not in news_by_ticker:
                news_by_ticker[ticker] = []
            news_by_ticker[ticker].append(article)

    logger.info(f"Analyse sentiment: {len(news_by_ticker)} actions avec news")

    sentiment_results = {}
    tickers_in_df = df_scores["ticker"].tolist() if "ticker" in df_scores.columns else []

    # Analyser seulement les actions qui ont des news ET sont dans notre liste
    tickers_to_analyze = [t for t in news_by_ticker.keys() if t in tickers_in_df]

    for ticker in tickers_to_analyze:
        name_row = df_scores[df_scores["ticker"] == ticker]
        name = name_row["name"].values[0] if len(name_row) > 0 else ticker
        news_list = news_by_ticker[ticker]

        logger.info(f"  Analyse {ticker}: {len(news_list)} articles...")
        result = analyze_ticker_news(ticker, name, news_list)
        sentiment_results[ticker] = result

    # Appliquer les ajustements de score
    df = df_scores.copy()
    sentiment_scores = []
    sentiment_labels = []
    sentiment_resumes = []
    sentiment_adjs = []

    for _, row in df.iterrows():
        ticker = row["ticker"]
        if ticker in sentiment_results:
            sr = sentiment_results[ticker]
            sentiment_scores.append(sr.get("sentiment_score", 0))
            sentiment_labels.append(sr.get("sentiment_label", "Neutre"))
            sentiment_resumes.append(sr.get("resume", ""))
            adj = sr.get("impact_score_adj", 0.0)
            sentiment_adjs.append(adj)
        else:
            sentiment_scores.append(0)
            sentiment_labels.append("Neutre")
            sentiment_resumes.append("Aucune actualité cette semaine.")
            sentiment_adjs.append(0.0)

    df["sentiment_score"] = sentiment_scores
    df["sentiment_label"] = sentiment_labels
    df["sentiment_resume"] = sentiment_resumes
    df["sentiment_adj"] = sentiment_adjs

    # Ajuster le score composite avec le sentiment
    df["composite_adj"] = df["composite_adj"] + df["sentiment_adj"]
    df["composite_adj"] = df["composite_adj"].clip(lower=0, upper=90)

    # Regénérer le ranking
    df = df.sort_values("composite_adj", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1

    # Générer le résumé de marché
    market_summary = generate_market_summary(all_news, macro)

    return df, sentiment_results, market_summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=== TEST SENTIMENT ANALYZER ===")

    if not ANTHROPIC_API_KEY:
        print("⚠ ANTHROPIC_API_KEY non définie")
        print("Pour activer l'analyse IA:")
        print("  export ANTHROPIC_API_KEY='sk-ant-...'")
        print("Ou ajouter dans un fichier .env à la racine du projet")
    else:
        test_news = [
            {"source": "SikaFinance", "title": "SGBCI : Le bénéfice net progresse de 25% en 2025",
             "tickers": ["SGBC"]},
            {"source": "RichBourse", "title": "SGBCI annonce un dividende de 2293 FCFA par action",
             "tickers": ["SGBC"]},
        ]
        result = analyze_ticker_news("SGBC", "Société Générale CI", test_news)
        print(f"Résultat: {json.dumps(result, ensure_ascii=False, indent=2)}")
