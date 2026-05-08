"""
scheduler_patch.py — Nouvelles tâches à ajouter dans app.py (start_scheduler)
Ajoute 3 jobs APScheduler aux tâches existantes :
  1. Nuit (22h) — scrape rapports + détection nouveaux PDFs
  2. Dimanche (23h) — analyse IA batch des PDFs
  3. Après chaque analyse — recalcul scores enrichis
"""

# ── ROUTES À AJOUTER dans app.py ─────────────────────────────────────────────

ROUTES_TO_ADD = '''
@app.route("/api/analyses/summary")
def api_analyses_summary():
    """Résumé des analyses PDF pour toutes les sociétés."""
    try:
        import json, os
        path = os.path.join("data", "analyses_summary.json")
        if not os.path.exists(path):
            return jsonify({"error": "Aucune analyse disponible", "total": 0})
        with open(path, encoding="utf-8") as f:
            summary = json.load(f)
        # Retourner version allégée pour le dashboard
        light = {}
        for ticker, d in summary.items():
            light[ticker] = {
                "verdict":     d.get("verdict_investisseur"),
                "resume":      d.get("resume", "")[:200],
                "year":        d.get("year"),
                "analyzed_at": d.get("analyzed_at"),
                "ca":          ((d.get("kpis") or {}).get("chiffre_affaires") or {}).get("valeur"),
                "rn":          ((d.get("kpis") or {}).get("resultat_net") or {}).get("valeur"),
                "roe":         ((d.get("kpis") or {}).get("roe") or {}).get("valeur"),
                "div":         ((d.get("kpis") or {}).get("dividende_par_action") or {}).get("valeur"),
                "ebitda":      ((d.get("kpis") or {}).get("ebitda") or {}).get("valeur"),
                "points_cles": d.get("points_cles", [])[:3],
                "perspectives":d.get("perspectives", "")[:300],
            }
        return jsonify({"total": len(light), "analyses": light})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/analyses/run", methods=["POST"])
def api_analyses_run():
    """Lance une analyse IA batch en arrière-plan."""
    data   = request.get_json() or {}
    tickers = data.get("tickers")  # None = tous
    force   = data.get("force", False)

    def run():
        try:
            from bulk_analyzer import run_bulk_analysis
            from score_enricher import build_enriched_scores
            run_bulk_analysis(tickers, force=force)
            build_enriched_scores()
            logger.info("Batch analyses terminé")
        except Exception as e:
            logger.error(f"Batch analyses erreur: {e}")

    import threading
    threading.Thread(target=run, daemon=True).start()
    n = len(tickers) if tickers else 47
    return jsonify({"status": "started", "message": f"Analyse IA lancée pour {n} sociétés (~{n*30}s)"})
'''

# ── PATCH start_scheduler() dans app.py ───────────────────────────────────────

SCHEDULER_JOBS = '''
        # Job nuit — scrape nouveaux rapports (22h)
        def job_scrape_reports():
            try:
                from reports_scraper import fetch_all_reports, save_reports_cache
                logger.info("Scheduler: scrape rapports nuit")
                all_r = fetch_all_reports(delay=1.0)
                save_reports_cache(all_r)
                logger.info(f"Scheduler: {sum(len(v) for v in all_r.values())} rapports cached")
            except Exception as e:
                logger.error(f"Scheduler scrape_reports: {e}")

        scheduler.add_job(
            job_scrape_reports, "cron", hour=22, minute=0,
            id="scrape_reports", replace_existing=True
        )

        # Job hebdo — analyse IA PDF (dimanche 23h)
        def job_analyze_pdfs():
            try:
                from bulk_analyzer  import run_bulk_analysis
                from score_enricher import build_enriched_scores
                logger.info("Scheduler: analyse IA hebdo")
                run_bulk_analysis(force=False)
                build_enriched_scores()
                logger.info("Scheduler: analyse IA terminée")
            except Exception as e:
                logger.error(f"Scheduler analyze_pdfs: {e}")

        scheduler.add_job(
            job_analyze_pdfs, "cron", day_of_week="sun", hour=23, minute=0,
            id="analyze_pdfs", replace_existing=True
        )
'''


def apply_patch():
    """Applique le patch sur app.py."""
    with open("app.py", "r") as f:
        content = f.read()

    # Ajouter les routes
    if "api/analyses/summary" not in content:
        content = content.replace(
            'if __name__ == "__main__":',
            ROUTES_TO_ADD + '\nif __name__ == "__main__":'
        )
        print("Routes analyses ajoutées")

    # Ajouter les jobs scheduler
    if "job_scrape_reports" not in content:
        # Trouver la fin du bloc try du start_scheduler
        marker = '        scheduler.add_job(job, "interval", minutes=5'
        content = content.replace(marker, SCHEDULER_JOBS + "\n" + marker)
        print("Jobs scheduler ajoutés")

    with open("app.py", "w") as f:
        f.write(content)

    print("app.py patché")


if __name__ == "__main__":
    apply_patch()
