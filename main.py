"""
BRVM Analyzer — Orchestrateur principal
Lance le pipeline complet: scraping → scoring → rapport PDF → commit GitHub
Usage: python main.py [--offline] [--no-github]
"""

import os
import sys
import json
import logging
import argparse
import subprocess
from datetime import datetime
from pathlib import Path

import pandas as pd

# ── Configuration (modifie selon tes préférences) ─────────────────────────────
CONFIG = {
    "reports_dir": "reports",
    "data_dir": "data",
    "logs_dir": "logs",
    "github_repo": "brvm-weekly-analysis",   # Nom du repo GitHub (créé si inexistant)
    "github_username": "",                    # ← Remplis ton username GitHub ici
    "log_level": "INFO",
    "use_cache_if_offline": True,
}
# ─────────────────────────────────────────────────────────────────────────────


def setup_logging(log_dir: str) -> logging.Logger:
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


def load_previous_scores(data_dir: str) :
    """Charge le dernier rapport pour comparer les variations de rang"""
    pattern = os.path.join(data_dir, "scores_*.json")
    import glob
    files = sorted(glob.glob(pattern))
    if not files:
        return None
    try:
        with open(files[-1]) as f:
            return pd.DataFrame(json.load(f))
    except Exception:
        return None


def save_scores(df: pd.DataFrame, data_dir: str) -> str:
    os.makedirs(data_dir, exist_ok=True)
    fname = os.path.join(data_dir, f"scores_{datetime.now().strftime('%Y%m%d')}.json")
    df.to_json(fname, orient="records", indent=2, force_ascii=False)
    return fname


def git_push(report_path: str, scores_path: str, week_label: str, logger: logging.Logger):
    """Commit et push vers GitHub"""
    try:
        # Vérifier que git est configuré
        result = subprocess.run(["git", "remote", "-v"], capture_output=True, text=True)
        if "origin" not in result.stdout:
            logger.warning("Pas de remote GitHub configuré. Configure d'abord avec: git remote add origin ...")
            return False

        subprocess.run(["git", "add", report_path, scores_path, "logs/"], check=True)
        commit_msg = f"📊 Rapport hebdomadaire BRVM — {week_label}"
        subprocess.run(["git", "commit", "-m", commit_msg], check=True)
        subprocess.run(["git", "push", "origin", "main"], check=True)
        logger.info(f"✅ Rapport pushé sur GitHub: {commit_msg}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Erreur git: {e}")
        return False


def print_summary(df: pd.DataFrame, logger: logging.Logger):
    """Affiche un résumé dans le terminal"""
    logger.info("=" * 65)
    logger.info("  🏆 CLASSEMENT BRVM — TOP 10  ")
    logger.info("=" * 65)
    for _, row in df.head(10).iterrows():
        div = f"{row['div_yield']:.1f}%" if row.get("div_yield") else " — "
        price = f"{row['price']:>8,.0f}" if row.get("price") else "    N/D "
        logger.info(
            f"  #{int(row['rank']):<2}  {row['ticker']:<6}  {row['name'][:24]:<24}  "
            f"{price} XOF  Div:{div:>6}  Score:{row['composite_adj']:>4.0f}/70"
        )
    logger.info("=" * 65)


def run_pipeline(offline: bool = False, no_github: bool = False):
    logger = setup_logging(CONFIG["logs_dir"])
    logger.info("🚀 Démarrage de l'analyse BRVM hebdomadaire")

    week_label = datetime.now().strftime("Semaine du %d %B %Y")
    os.makedirs(CONFIG["reports_dir"], exist_ok=True)
    os.makedirs(CONFIG["data_dir"], exist_ok=True)

    # ── 1. Scraping des données ───────────────────────────────────────────────
    logger.info("📡 Étape 1/4 — Récupération des cours BRVM")
    from scraper import build_stock_dataset
    cache_path = os.path.join(CONFIG["data_dir"], "prices_cache.json")
    df_raw = build_stock_dataset(use_cache=offline, cache_path=cache_path)
    logger.info(f"  ✓ {len(df_raw)} actions chargées")

    # ── 2. Calcul des scores ──────────────────────────────────────────────────
    logger.info("📊 Étape 2/4 — Calcul des scores multi-modèles")
    from valuation import compute_all_scores
    prev_df = load_previous_scores(CONFIG["data_dir"])
    df_scores = compute_all_scores(df_raw)

    # Ajouter variation de rang vs semaine précédente
    if prev_df is not None and "ticker" in prev_df.columns and "rank" in prev_df.columns:
        rank_map = dict(zip(prev_df["ticker"], prev_df["rank"]))
        df_scores["prev_rank"] = df_scores["ticker"].map(rank_map)
        df_scores["rank_change"] = df_scores["prev_rank"] - df_scores["rank"]
    else:
        df_scores["prev_rank"] = None
        df_scores["rank_change"] = 0

    scores_path = save_scores(df_scores, CONFIG["data_dir"])
    logger.info(f"  ✓ Scores sauvegardés: {scores_path}")
    print_summary(df_scores, logger)

    # ── 3. Génération du rapport PDF ─────────────────────────────────────────
    logger.info("📄 Étape 3/4 — Génération du rapport PDF")
    from report_generator import generate_report
    pdf_name = f"BRVM_Analyse_{datetime.now().strftime('%Y_%m_%d')}.pdf"
    pdf_path = os.path.join(CONFIG["reports_dir"], pdf_name)
    generate_report(df_scores, pdf_path, week_label=week_label, prev_df=prev_df)
    logger.info(f"  ✓ Rapport PDF: {pdf_path}")

    # ── 4. Push GitHub ────────────────────────────────────────────────────────
    if not no_github:
        logger.info("🐙 Étape 4/4 — Commit et push GitHub")
        success = git_push(pdf_path, scores_path, week_label, logger)
        if not success:
            logger.warning("  ⚠ Push GitHub ignoré (configure le remote d'abord)")
    else:
        logger.info("🐙 Étape 4/4 — GitHub ignoré (--no-github)")

    logger.info(f"✅ Pipeline terminé — Rapport disponible: {pdf_path}")
    return pdf_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BRVM Weekly Analyzer")
    parser.add_argument("--offline", action="store_true",
                        help="Utiliser le cache local (pas de scraping)")
    parser.add_argument("--no-github", action="store_true",
                        help="Ne pas pusher sur GitHub")
    args = parser.parse_args()
    run_pipeline(offline=args.offline, no_github=args.no_github)
