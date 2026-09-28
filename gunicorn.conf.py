"""
gunicorn.conf.py — HANG-1 + HANG-2 : instrumentation de diagnostic uniquement.
Charge automatiquement par gunicorn (aucun --config/-c dans la commande Render
ni dans GUNICORN_CMD_ARGS) : voir gunicorn/app/base.py:172-178 et
gunicorn/config.py:542-547 (fallback sur ./gunicorn.conf.py).

post_worker_init tourne APRES init_signals() du worker (gunicorn/workers/base.py:118
puis 137) : enregistrer sur SIGUSR1/SIGUSR2 ecraserait des handlers deja pris par
gunicorn (USR1 = reopen logs + relais aux workers, USR2 = reexec du binaire —
gunicorn/arbiter.py:283-294). SIGURG n'est utilise ni par l'arbitre
(gunicorn/arbiter.py:43) ni par le worker (gunicorn/workers/base.py:32) : aucun
conflit.

HANG-2 : un fil demon dans le worker sonde /api/status toutes les 10 s.
- 2 echecs consecutifs -> faulthandler.dump_traceback() immediat (motif logue),
  au plus une fois toutes les 5 min.
- A chaque tour, le minuteur C faulthandler.dump_traceback_later(40, exit=False)
  est annule puis rearme : si le fil lui-meme ne tourne plus (GIL retenu en
  continu par un appel C natif, ex. ctypes.PyDLL(...).sleep()), ce minuteur
  independant du GIL ecrit quand meme les piles ~40 s apres le dernier
  rearmement reussi. Sa sortie commence nativement par "Timeout (0:00:40)!" —
  verifie empiriquement — ce qui suffit a distinguer les deux origines dans
  les logs sans code supplementaire en prod.
- worker.alive passe a False sur SIGTERM (arbitre en deploiement,
  gunicorn/arbiter.py:576 -> handle_exit, gunicorn/workers/base.py:192),
  SIGQUIT/SIGINT (handle_quit surcharge pour gthread, gunicorn/workers/
  gthread.py:101), SIGABRT (gunicorn/workers/base.py:202) ou recyclage
  --max-requests (gunicorn/workers/gthread.py:325). Des que worker.alive est
  faux, le chien de garde arrete de sonder et annule le minuteur : pas de
  capture parasite pendant un arret normal (deploiement). Delai de grace de
  60 s apres le demarrage du fil avant la premiere sonde (le worker peut
  encore finir son propre demarrage).
- HANG2_DEBUG=1 (variable d'environnement, jamais positionnee en prod) ajoute
  une ligne de log a chaque rearmement du minuteur, pour dater precisement en
  test le dernier rearmement reussi avant un gel provoque.

Les deux hooks sont proteges par try/except : une exception ici empecherait le
worker de demarrer (donc le site) si elle remontait. Chaque iteration de la
boucle du chien de garde a son propre try/except : une erreur ponctuelle ne
doit jamais arreter silencieusement toute la surveillance pour le reste de la
vie du worker.
"""
import logging
import os
import sys
import time
import signal
import threading
import faulthandler
import urllib.request

logger = logging.getLogger("gunicorn.error")

_HANG2_DEBUG = os.environ.get("HANG2_DEBUG") == "1"
_HANG2_GRACE_S = 60
_HANG2_INTERVAL_S = 10
_HANG2_TIMEOUT_S = 5
_HANG2_FAIL_THRESHOLD = 2
_HANG2_DUMP_COOLDOWN_S = 300
_HANG2_TIMER_S = 40


def _hang2_watchdog(worker, port):
    url = "http://127.0.0.1:%s/api/status" % port
    fails = 0
    last_dump = 0.0
    time.sleep(_HANG2_GRACE_S)
    while True:
        try:
            if not worker.alive:
                try:
                    faulthandler.cancel_dump_traceback_later()
                except Exception:
                    pass
                logger.info("HANG-2: worker.alive=False, chien de garde arrete")
                return

            try:
                with urllib.request.urlopen(url, timeout=_HANG2_TIMEOUT_S) as resp:
                    ok = resp.status == 200
            except Exception:
                ok = False
            fails = 0 if ok else fails + 1

            if fails >= _HANG2_FAIL_THRESHOLD and (time.time() - last_dump) >= _HANG2_DUMP_COOLDOWN_S:
                logger.warning("HANG-2: capture (motif=2 echecs consecutifs)")
                faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
                last_dump = time.time()

            try:
                faulthandler.cancel_dump_traceback_later()
            except Exception:
                pass
            faulthandler.dump_traceback_later(_HANG2_TIMER_S, exit=False, file=sys.stderr)
            if _HANG2_DEBUG:
                logger.info("HANG-2: minuteur arme (%s s)", _HANG2_TIMER_S)
        except Exception as e:
            logger.warning("HANG-2: iteration chien de garde en erreur: %s", e)
        time.sleep(_HANG2_INTERVAL_S)


def post_worker_init(worker):
    try:
        faulthandler.register(signal.SIGURG, all_threads=True)
        logger.info("HANG-1: faulthandler arme sur SIGURG (pid=%s)", worker.pid)
    except Exception as e:
        logger.warning("HANG-1: faulthandler non arme: %s", e)

    try:
        port = worker.sockets[0].getsockname()[1]
        t = threading.Thread(target=_hang2_watchdog, args=(worker, port), daemon=True)
        t.start()
        logger.info("HANG-2: chien de garde demarre (port=%s, grace=%ss)", port, _HANG2_GRACE_S)
    except Exception as e:
        logger.warning("HANG-2: chien de garde non demarre: %s", e)
