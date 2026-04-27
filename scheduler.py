"""
Planificateur hebdomadaire — Lance l'analyse chaque vendredi à 20h00
Usage: python scheduler.py
       (laisser tourner en arrière-plan)

Ou utiliser le cron (voir README.md pour les instructions)
"""

import schedule
import time
import logging
import subprocess
import sys
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("scheduler")


def run_weekly_analysis():
    logger.info(f"⏰ Déclenchement automatique — {datetime.now().strftime('%A %d/%m/%Y %H:%M')}")
    try:
        result = subprocess.run(
            [sys.executable, "main.py"],
            cwd=__file__.replace("scheduler.py", ""),
            capture_output=False,
            timeout=600,  # 10 minutes max
        )
        if result.returncode == 0:
            logger.info("✅ Analyse hebdomadaire terminée avec succès")
        else:
            logger.error(f"❌ Erreur pipeline (code {result.returncode})")
    except subprocess.TimeoutExpired:
        logger.error("❌ Timeout — analyse interrompue après 10 minutes")
    except Exception as e:
        logger.error(f"❌ Exception inattendue: {e}")


def main():
    logger.info("🟢 Planificateur BRVM démarré")
    logger.info("   Prochaine analyse: chaque vendredi à 20:00")
    logger.info("   Pour arrêter: Ctrl+C")

    # Planifier chaque vendredi à 20:00
    schedule.every().friday.at("20:00").do(run_weekly_analysis)

    # Pour tester: lancer immédiatement (décommenter la ligne suivante)
    # run_weekly_analysis()

    while True:
        schedule.run_pending()
        next_run = schedule.next_run()
        if next_run:
            remaining = next_run - datetime.now()
            hours = int(remaining.total_seconds() // 3600)
            mins = int((remaining.total_seconds() % 3600) // 60)
            logger.debug(f"Prochain lancement dans {hours}h{mins:02d}m")
        time.sleep(60)  # Vérifier chaque minute


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("🔴 Planificateur arrêté")
