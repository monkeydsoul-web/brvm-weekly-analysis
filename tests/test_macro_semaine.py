# -*- coding: utf-8 -*-
"""Semaine de /api/macro : ISO dans la réponse, fichier inchangé."""
import json
import os
from pathlib import Path

import pytest


def _ecrire(chemin, data):
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


@pytest.fixture
def client(tmp_path, monkeypatch):
    import app as application
    monkeypatch.setattr(application, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        "news_scraper.fetch_macro_context",
        lambda: (_ for _ in ()).throw(RuntimeError("le job ne doit pas réécrire")),
    )
    yield application.app.test_client(), tmp_path


def test_semaine_iso_sans_changer_la_date_ni_le_fichier(client):
    http, dossier = client
    chemin = dossier / "macro_cache.json"
    _ecrire(str(chemin), {
        "date": "2026-10-03",
        "week": "Semaine 39/2026",
        "BRVM_30": 264.57,
        "BRVM_COMPOSITE": 546.78,
    })
    avant = chemin.read_bytes()
    corps = http.get("/api/macro").get_json()
    assert corps["date"] == "2026-10-03"
    assert corps["week"] == "Semaine 40/2026"
    assert corps["BRVM_30"] == 264.57
    assert chemin.read_bytes() == avant

    _ecrire(str(chemin), {
        "date": "2026-10-02",
        "week": "Semaine 39/2026",
        "FCFA_per_USD": 580.49,
    })
    avant = chemin.read_bytes()
    corps = http.get("/api/macro").get_json()
    assert corps["date"] == "2026-10-02"
    assert corps["week"] == "Semaine 40/2026"
    assert chemin.read_bytes() == avant


def test_sans_cle_week_la_reponse_est_le_fichier(client):
    http, dossier = client
    brut = {"date": "2026-10-03T12:00:00+00:00", "FCFA_per_EUR": 655.957}
    chemin = dossier / "macro_cache.json"
    _ecrire(str(chemin), brut)
    assert http.get("/api/macro").get_json() == brut
    assert json.loads(chemin.read_text(encoding="utf-8")) == brut


def test_ecriture_du_job_reste_en_pourcent_w():
    texte = (Path(__file__).resolve().parents[1] / "news_scraper.py").read_text(encoding="utf-8")
    assert 'strftime("Semaine %W/%Y")' in texte
