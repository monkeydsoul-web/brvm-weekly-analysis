"""
BRVM Analyzer v2 — Orchestrateur complet
Pipeline: Scraping (5 sources) → News → Sentiment IA → 8 scores → PDF → Alertes → GitHub
Usage: python main.py [--offline] [--no-github] [--no-ai] [--no-email]
"""

import os
import sys
import json
import logging
import argparse
import subprocess
from datetime import datetime

import pandas as pd

CONFIG = {
    "reports_dir": "reports",
    "data_dir": "data",
    "logs_dir": "logs",
    "github_username": "monkeydsoul-web",
    "log_level": "INFO",
}


def setup_logging(log_dir):
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"brvm_{datetime.now().strftime('%Y%m%d')}.log")
    logging.basicConfig(
        level=getattr(logging, CONFIG["log_level"]),
        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )
    return logging.getLogger("main")


def load_previous_scores(data_dir):
    import glob
    pattern = os.path.join(data_dir, "scores_*.json")
    files = sorted(glob.glob(pattern))
    if not files:
        return None, {}
    try:
        with open(files[-1]) as f:
            data = json.load(f)
        df = pd.DataFrame(data)
        score_map = dict(zip(df["ticker"], df.get("composite_adj", [0]*len(df))))
        return df, score_map
    except Exception:
        return None, {}


def save_scores(df, data_dir):
    os.makedirs(data_dir, exist_ok=True)
    fname = os.path.join(data_dir, f"scores_{datetime.now().strftime('%Y%m%d')}.json")
    cols = [c for c in df.columns if c != "technical_signals"]
    df[cols].to_json(fname, orient="records", indent=2, force_ascii=False)
    return fname


def git_push(files, week_label, logger):
    try:
        result = subprocess.run(["git", "remote", "-v"], capture_output=True, text=True)
        if "origin" not in result.stdout:
            logger.warning("Pas de remote GitHub configuré")
            return False
        subprocess.run(["git", "add"] + files + ["logs/"], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", f"Rapport BRVM — {week_label}"], check=True, capture_output=True)
        subprocess.run(["git", "push", "origin", "main"], check=True, capture_output=True)
        logger.info(f"GitHub: Rapport BRVM — {week_label}")
        return True
    except subprocess.CalledProcessError as e:
        logger.warning(f"Git push: {e}")
        return False


def print_summary(df, logger):
    logger.info("=" * 70)
    logger.info("  CLASSEMENT BRVM — TOP 10  ")
    logger.info("=" * 70)
    for _, row in df.head(10).iterrows():
        div = f"{row['div_yield']:.1f}%" if row.get("div_yield") else "  —  "
        price = f"{row['price']:>9,.0f}" if row.get("price") else "      N/D "
        sent = str(row.get("sentiment_label", "Neutre"))[:12]
        tech = row.get("score_technique", 0)
        logger.info(
            f"  #{int(row['rank']):<2}  {row['ticker']:<6}  {row['name'][:22]:<22}  "
            f"{price} XOF  Div:{div:>6}  "
            f"Score:{row.get('composite_adj',0):>5.0f}/80  "
            f"Tech:{tech:.0f}  {sent}"
        )
    logger.info("=" * 70)


def run_pipeline(offline=False, no_github=False, no_ai=False, no_email=False):
    logger = setup_logging(CONFIG["logs_dir"])
    logger.info("BRVM Analyzer v2 — Demarrage du pipeline complet")
    week_label = datetime.now().strftime("Semaine du %d %B %Y")
    os.makedirs(CONFIG["reports_dir"], exist_ok=True)
    os.makedirs(CONFIG["data_dir"], exist_ok=True)

    # 1. Cours
    logger.info("Etape 1/7 — Recuperation des cours BRVM")
    from scraper import build_stock_dataset
    cache_path = os.path.join(CONFIG["data_dir"], "prices_cache.json")
    df_raw = build_stock_dataset(use_cache=offline, cache_path=cache_path)
    logger.info(f"  {len(df_raw)} actions chargees")

    # 2. News et dividendes
    logger.info("Etape 2/7 — Scraping news et dividendes (5 sources)")
    all_news, confirmed_dividends = [], {}
    macro = {"FCFA_per_USD": 610.0, "EUR_USD": 1.076}
    if not offline:
        try:
            from news_scraper import fetch_all_news, fetch_confirmed_dividends, fetch_macro_context
            all_news = fetch_all_news()
            confirmed_dividends = fetch_confirmed_dividends()
            macro = fetch_macro_context()
            logger.info(f"  {len(all_news)} articles · {len(confirmed_dividends)} dividendes confirmes")
            for ticker, div_data in confirmed_dividends.items():
                mask = df_raw["ticker"] == ticker
                if mask.any() and div_data.get("dividend", 0) > 0:
                    price = df_raw.loc[mask, "price"].values[0]
                    if price and price > 0:
                        df_raw.loc[mask, "div_per_share"] = div_data["dividend"]
                        df_raw.loc[mask, "div_yield"] = round(div_data["dividend"] / price * 100, 2)
        except Exception as e:
            logger.warning(f"  News/dividendes: {e}")
    else:
        logger.info("  Mode offline — news ignorees")

    # 3. Historique prix
    logger.info("Etape 3/7 — Historique + score technique")
    history = {}
    try:
        from price_history import update_history, get_history_summary
        history = update_history(df_raw)
        s = get_history_summary(history)
        logger.info(f"  {s['total_tickers_tracked']} tickers · {s['avg_weeks_per_ticker']:.1f} semaines")
    except Exception as e:
        logger.warning(f"  Historique: {e}")

    # 4. Scores fondamentaux (7 modèles)
    logger.info("Etape 4/7 — Calcul des 7 scores fondamentaux")
    from valuation import compute_all_scores
    prev_df, prev_score_map = load_previous_scores(CONFIG["data_dir"])
    df_scores = compute_all_scores(df_raw)

    if prev_df is not None and "ticker" in prev_df.columns:
        rank_map = dict(zip(prev_df["ticker"], prev_df.get("rank", range(1, len(prev_df)+1))))
        df_scores["prev_rank"] = df_scores["ticker"].map(rank_map)
        df_scores["rank_change"] = (df_scores["prev_rank"] - df_scores["rank"]).fillna(0)
    else:
        df_scores["prev_rank"] = None
        df_scores["rank_change"] = 0

    df_scores["score_technique"] = 5.0
    df_scores["detail_technique"] = "Donnees insuffisantes"
    df_scores["sentiment_score"] = 0
    df_scores["sentiment_label"] = "Neutre"
    df_scores["sentiment_resume"] = ""
    df_scores["sentiment_adj"] = 0.0

    # 5. Score technique (8ème modèle)
    logger.info("Etape 5/7 — Score technique (8eme modele)")
    try:
        from price_history import compute_all_technical_scores
        df_scores = compute_all_technical_scores(df_scores, history)
        logger.info(f"  Score technique moyen: {df_scores['score_technique'].mean():.1f}/10")
    except Exception as e:
        logger.warning(f"  Score technique: {e}")

    # 6. Sentiment IA
    sentiment_results = {}
    market_summary = "Analyse de marche non disponible cette semaine."
    if not no_ai and all_news:
        logger.info("Etape 6/7 — Analyse de sentiment IA")
        try:
            from sentiment import analyze_all_news
            df_scores, sentiment_results, market_summary = analyze_all_news(all_news, df_scores, macro)
            n_pos = sum(1 for v in sentiment_results.values() if v.get("sentiment_score", 0) > 0)
            logger.info(f"  {len(sentiment_results)} analyses · {n_pos} positifs")
        except Exception as e:
            logger.warning(f"  Sentiment: {e}")
    else:
        logger.info("  Sentiment IA ignore")

    scores_path = save_scores(df_scores, CONFIG["data_dir"])
    print_summary(df_scores, logger)

    # 7a. PDF
    logger.info("Etape 7/7a — Generation du rapport PDF enrichi")
    from report_generator import generate_report
    pdf_name = f"BRVM_Analyse_{datetime.now().strftime('%Y_%m_%d')}.pdf"
    pdf_path = os.path.join(CONFIG["reports_dir"], pdf_name)
    try:
        generate_report(
            df_scores, pdf_path,
            week_label=week_label,
            prev_df=prev_df,
            all_news=all_news,
            market_summary=market_summary,
            macro=macro,
        )
        logger.info(f"  PDF: {pdf_path}")
    except TypeError:
        # Fallback si l'ancienne signature est utilisée
        generate_report(df_scores, pdf_path, week_label=week_label, prev_df=prev_df)
        logger.info(f"  PDF (mode compat): {pdf_path}")

    # 7b. Alertes email
    if not no_email:
        logger.info("Etape 7b — Alertes email")
        try:
            from alerter import process_all_alerts, save_default_config
            save_default_config()
            n_sent = process_all_alerts(
                df_scores, pdf_path, market_summary,
                sentiment_results, confirmed_dividends, macro,
                prev_scores=prev_score_map,
            )
            logger.info(f"  {n_sent} alerte(s) envoyee(s)")
        except Exception as e:
            logger.warning(f"  Alertes: {e}")

    # 7c. GitHub
    if not no_github:
        logger.info("Etape 7c — Push GitHub")
        git_push([pdf_path, scores_path], week_label, logger)
    else:
        logger.info("  GitHub ignore (--no-github)")

    logger.info(f"Pipeline v2 termine — {pdf_path}")
    return pdf_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BRVM Analyzer v2")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--no-github", action="store_true")
    parser.add_argument("--no-ai", action="store_true")
    parser.add_argument("--no-email", action="store_true")
    args = parser.parse_args()
    run_pipeline(
        offline=args.offline,
        no_github=args.no_github,
        no_ai=args.no_ai,
        no_email=args.no_email,
    )
