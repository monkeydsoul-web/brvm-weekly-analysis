# -*- coding: utf-8 -*-
"""Filet de tests PR-02.

Aucun appel reseau, aucune ecriture sous /var/data.
BRVM_DATA_DIR est pose avant tout import applicatif.
"""
import os
import socket
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = Path(__file__).resolve().parent
for _chemin in (str(ROOT), str(TESTS)):
    if _chemin not in sys.path:
        sys.path.insert(0, _chemin)

_TEST_DATA = tempfile.mkdtemp(prefix="brvm-pr02-")
if os.path.abspath(_TEST_DATA).startswith("/var/data"):
    raise RuntimeError("le repertoire de test ne doit pas etre sous /var/data")
os.environ["BRVM_DATA_DIR"] = _TEST_DATA
# Importer app.py ne doit pas demarrer le planificateur ni ecrire un classement.
os.environ["BRVM_DISABLE_SCHEDULER"] = "1"
os.environ.pop("ANTHROPIC_API_KEY", None)

# brvm_market_data_scraper ouvre logs/brvm_market.log des l'import.
# logs/ est gitignore : le fichier n'est pas versionne.
(ROOT / "logs").mkdir(exist_ok=True)

import pytest

_REFUS = "appel reseau interdit dans les tests"


def _refuser_reseau(*_args, **_kwargs):
    raise RuntimeError(_REFUS)


@pytest.fixture(autouse=True)
def interdire_reseau_et_cle(monkeypatch):
    """Bloque les sockets et retire une eventuelle cle Anthropic."""
    monkeypatch.setattr(socket.socket, "connect", _refuser_reseau)
    monkeypatch.setattr(socket.socket, "connect_ex", _refuser_reseau)
    monkeypatch.setattr(socket, "create_connection", _refuser_reseau)
    monkeypatch.setattr(socket, "getaddrinfo", _refuser_reseau)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.fixture
def data_dir():
    return _TEST_DATA


@pytest.fixture
def fixtures_dir():
    return Path(__file__).resolve().parent / "fixtures"
