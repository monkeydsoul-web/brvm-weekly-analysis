"""
gunicorn.conf.py — HANG-1 : instrumentation de diagnostic uniquement.
Charge automatiquement par gunicorn (aucun --config/-c dans la commande Render
ni dans GUNICORN_CMD_ARGS) : voir gunicorn/app/base.py:172-178 et
gunicorn/config.py:542-547 (fallback sur ./gunicorn.conf.py).

post_worker_init tourne APRES init_signals() du worker (gunicorn/workers/base.py:118
puis 137) : enregistrer sur SIGUSR1/SIGUSR2 ecraserait des handlers deja pris par
gunicorn (USR1 = reopen logs + relais aux workers, USR2 = reexec du binaire —
gunicorn/arbiter.py:283-294). SIGURG n'est utilise ni par l'arbitre
(gunicorn/arbiter.py:43) ni par le worker (gunicorn/workers/base.py:32) : aucun
conflit.

Le hook est protege par try/except : une exception ici empecherait le worker de
demarrer (donc le site) si elle remontait.
"""
import logging

logger = logging.getLogger("gunicorn.error")


def post_worker_init(worker):
    try:
        import faulthandler
        import signal
        faulthandler.register(signal.SIGURG, all_threads=True)
        logger.info("HANG-1: faulthandler arme sur SIGURG (pid=%s)", worker.pid)
    except Exception as e:
        logger.warning("HANG-1: faulthandler non arme: %s", e)
