"""
auto_scheduler.py — Scheduler automatique BRVM Dashboard
Jobs:
  - Toutes les 5min  : prix live + ranking
  - Toutes les heures: actualités RSS
  - Tous les jours 7h: price_history + actualités entreprises
  - Tous les jours 22h: rapports PDF scrape
  - Tous les dimanches 23h: analyse IA PDF batch
  - Tous les lundis 6h: bulk_analyzer sociétés manquantes
"""
import logging, os, time
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import warnings
warnings.filterwarnings('ignore')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
logger = logging.getLogger(__name__)

# ── Jobs ──────────────────────────────────────────────────────────────────

def job_live_ranking():
    """Recalcule le classement live toutes les 5min."""
    try:
        from live_ranker import compute_live_ranking
        compute_live_ranking(trigger="scheduler")
        logger.debug("Ranking recalculé")
    except Exception as e:
        logger.error(f"job_live_ranking: {e}")

def job_news_rss():
    """Scrape les flux RSS toutes les heures."""
    try:
        from company_scraper import run_company_scraper
        added = run_company_scraper()
        if added > 0:
            logger.info(f"News RSS: {added} nouveaux articles")
    except Exception as e:
        logger.error(f"job_news_rss: {e}")

def job_price_history():
    """Met à jour l'historique des prix quotidiennement."""
    try:
        from price_history_builder import append_live_prices
        n = append_live_prices()
        logger.info(f"Price history: {n} tickers mis à jour")
    except Exception as e:
        logger.error(f"job_price_history: {e}")

def job_scrape_reports():
    """Scrape les rapports PDF depuis brvm.org à 22h."""
    try:
        from reports_scraper import fetch_all_reports, save_reports_cache
        logger.info("Scraping rapports PDF...")
        reports = fetch_all_reports()
        save_reports_cache(reports)
        total = sum(len(v) for v in reports.values())
        logger.info(f"Rapports: {total} docs pour {len(reports)} sociétés")
    except Exception as e:
        logger.error(f"job_scrape_reports: {e}")

def job_ai_analysis():
    """Analyse IA des PDFs le dimanche à 23h."""
    try:
        from bulk_analyzer import run_bulk_analysis
        logger.info("Analyse IA PDF batch...")
        run_bulk_analysis(force=False)
    except Exception as e:
        logger.error(f"job_ai_analysis: {e}")

def job_market_data():
    """Met à jour les données de marché (indices BRVM)."""
    try:
        from market_data import get_market_data
        get_market_data(force_refresh=True)
        logger.debug("Market data mis à jour")
    except Exception as e:
        logger.error(f"job_market_data: {e}")

def job_macro():
    """Met à jour les données macro."""
    try:
        from app import fetch_macro_data
        fetch_macro_data()
        logger.debug("Macro mis à jour")
    except Exception as e:
        logger.error(f"job_macro: {e}")

# ── Scheduler setup ───────────────────────────────────────────────────────

_scheduler = None

def get_scheduler():
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(
            timezone='Africa/Abidjan',
            job_defaults={'coalesce': True, 'max_instances': 1, 'misfire_grace_time': 60}
        )
    return _scheduler

def start_scheduler():
    sched = get_scheduler()
    if sched.running:
        return sched
    
    # Ranking live toutes les 5min (heures de marché 9h-16h en semaine)
    sched.add_job(job_live_ranking, IntervalTrigger(minutes=5),
                  id='live_ranking', replace_existing=True,
                  name='Ranking live 5min')
    
    # News RSS toutes les heures
    sched.add_job(job_news_rss, IntervalTrigger(hours=1),
                  id='news_rss', replace_existing=True,
                  name='News RSS 1h')
    
    # Price history quotidien à 18h
    sched.add_job(job_price_history, CronTrigger(hour=18, minute=0),
                  id='price_history', replace_existing=True,
                  name='Price history 18h')
    
    # Market data toutes les 15min
    sched.add_job(job_market_data, IntervalTrigger(minutes=15),
                  id='market_data', replace_existing=True,
                  name='Market data 15min')

    # Scrape rapports PDF à 22h
    sched.add_job(job_scrape_reports, CronTrigger(hour=22, minute=0),
                  id='scrape_reports', replace_existing=True,
                  name='Scrape rapports 22h')
    
    # Analyse IA PDF dimanche à 23h
    sched.add_job(job_ai_analysis, CronTrigger(day_of_week='sun', hour=23, minute=0),
                  id='ai_analysis', replace_existing=True,
                  name='Analyse IA PDF dim 23h')

    sched.start()
    logger.info("Scheduler démarré — jobs actifs:")
    for job in sched.get_jobs():
        logger.info(f"  • {job.name} — prochain: {job.next_run_time}")
    return sched

def stop_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler arrêté")

def get_scheduler_status():
    sched = get_scheduler()
    # Vérifier aussi le scheduler de live_data
    running = sched.running if sched else False
    if not running:
        try:
            from live_data import _scheduler as live_sched
            running = live_sched is not None and live_sched.running
        except:
            pass
    jobs = []
    if sched and sched.running:
        jobs = [{'id': j.id, 'name': j.name,
                 'next_run': str(j.next_run_time)[:19] if j.next_run_time else None}
                for j in sched.get_jobs()]
    # Ajouter jobs live_data
    try:
        from live_data import _scheduler as live_sched
        if live_sched and live_sched.running:
            running = True
            for j in live_sched.get_jobs():
                jobs.append({'id': j.id, 'name': j.name,
                             'next_run': str(j.next_run_time)[:19] if j.next_run_time else None})
    except:
        pass
    return {'running': running, 'jobs': jobs}

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s')
    print("Démarrage scheduler BRVM...")
    sched = start_scheduler()
    print(f"Jobs actifs: {len(sched.get_jobs())}")
    for job in sched.get_jobs():
        print(f"  • {job.name:35} next: {job.next_run_time}")
    # Lancer les jobs de démarrage immédiatement
    print("\nLancement news RSS...")
    job_news_rss()
    print("Lancement price history...")
    job_price_history()
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        stop_scheduler()
        print("Scheduler arrêté")
