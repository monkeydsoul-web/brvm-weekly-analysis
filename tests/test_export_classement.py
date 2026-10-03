# -*- coding: utf-8 -*-
"""CSV du Classement : note v10fmt, conseil identique à l'écran."""
import csv
import io
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import features
import live_ranker

ROOT = Path(__file__).resolve().parents[1]
PHRASE_SUSPENDUE = "Cotation suspendue depuis le 16/09/2026"


def _ligne(**kwargs):
    base = {
        "ticker": "XXXX",
        "name": "Nom",
        "sector": "Secteur",
        "price": 1000.0,
        "change_pct": 0.0,
        "note10": 5.0,
        "composite_adj": 40.0,
        "conseil_libelle": "Prudence",
        "prix_cible": 1200,
        "libelle_valeur": "Décote modérée",
        "div_yield": 1.5,
    }
    base.update(kwargs)
    return base


@pytest.fixture
def classement(tmp_path, monkeypatch):
    chemin = tmp_path / "live_ranking.json"
    monkeypatch.setattr(live_ranker, "RANKING_PATH", str(chemin))
    monkeypatch.setattr(features, "DATA_DIR", str(tmp_path))
    lignes = [
        _ligne(
            ticker="UNLC", name="Unilever CI", sector="Consommation",
            price=50900.0, change_pct=-1.2, note10=4.1, composite_adj=32.8,
            conseil_libelle=None, prix_cible=930, libelle_valeur="incertain",
            div_yield=0.0,
        ),
        _ligne(
            ticker="SMBC", name="SMB CI", sector="Industriel",
            price=16450.0, change_pct=0.24, note10=8.4, composite_adj=67.0,
            conseil_libelle="Intéressant", prix_cible=25440,
            libelle_valeur="Forte décote", div_yield=4.28,
        ),
        _ligne(
            ticker="SICC", name="SICOR", sector="Industrie",
            price=8400.0, change_pct=0.0, note10=6.1, composite_adj=48.8,
            conseil_libelle=None, statut="suspendu", statut_depuis="2026-09-16",
            prix_cible=856, libelle_valeur="incertain",
        ),
        _ligne(
            ticker="HUIT", name="Pile", sector="Test",
            price=1000.0, change_pct=0.0, note10=8.0, composite_adj=64.0,
            conseil_libelle="Prudence",
        ),
    ]
    payload = {"updated_at": "2026-10-02T18:00:00+00:00", "ranking": lignes}
    chemin.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return chemin, payload


def _lire_csv(texte):
    return list(csv.reader(io.StringIO(texte)))


def test_csv_reprend_la_note_dix_et_le_prix_cible(classement):
    chemin, payload = classement
    avant = chemin.read_bytes()
    texte = features.export_csv()
    assert chemin.read_bytes() == avant
    assert not texte.startswith("\ufeff")
    assert "\r" not in texte
    lignes = _lire_csv(texte)
    assert lignes[0] == [
        "ticker", "nom", "secteur", "cours", "variation",
        "note /10", "conseil", "prix cible", "rendement",
    ]
    assert lignes[1] == [
        "UNLC", "Unilever CI", "Consommation", "50900", "-1.2", "4.1", "—", "930", "0",
    ]
    assert lignes[2] == [
        "SMBC", "SMB CI", "Industriel", "16450", "0.24", "8.4", "Intéressant", "25440", "4.28",
    ]
    assert lignes[3] == [
        "SICC", "SICOR", "Industrie", "8400", "0", "6.1", PHRASE_SUSPENDUE, "856", "1.5",
    ]
    assert lignes[4] == [
        "HUIT", "Pile", "Test", "1000", "0", "8.0", "Prudence", "1200", "1.5",
    ]
    assert lignes[4][5] == "8.0"
    assert "67" not in texte
    assert "930" in texte
    assert "856" in texte
    assert payload["ranking"][0]["prix_cible"] == 930
    assert payload["ranking"][1]["note10"] == 8.4
    assert payload["ranking"][1]["composite_adj"] == 67.0


def test_route_csv_alignee_sur_live_ranking(classement):
    import app as application
    client = application.app.test_client()
    api = client.get("/api/live-ranking").get_json()
    csv_texte = client.get("/api/export/csv").get_data(as_text=True)
    corps = _lire_csv(csv_texte)
    assert len(corps) == 1 + len(api["ranking"])
    for ligne_csv, ligne_api in zip(corps[1:], api["ranking"]):
        assert ligne_csv[0] == ligne_api["ticker"]
        assert ligne_csv[5] == features._note_v10fmt(ligne_api)
        assert ligne_csv[5] != features._texte_valeur_api(ligne_api["composite_adj"])
        assert ligne_csv[6] == features._conseil_comme_classement(ligne_api)
    assert api["ranking"][0]["prix_cible"] == 930
    assert corps[1][7] == "930"


def _entre(texte, debut, fin):
    i = texte.index(debut)
    j = texte.index(fin, i)
    return texte[i:j]


def _libelles_classement(lignes):
    """note10txt et conseilAffiche, lus dans le JavaScript du Classement."""
    core = (ROOT / "dashboard" / "js" / "core.js").read_text(encoding="utf-8")
    notes = _entre(core, "function v10fmt", "function triCommeClassement")
    avis = _entre(core, "function conseilAffiche", "function couleurPrincipale")
    script = notes + "\n" + avis + """
function libelle(row) {
  var a = conseilAffiche(row);
  if (!a) return '\\u2014';
  if (a.suspendu) return a.texte;
  return a.libelle;
}
var rows = """ + json.dumps(lignes) + """;
var out = rows.map(function(row) {
  return {
    ticker: row.ticker,
    note: note10txt(row).replace(',', '.'),
    v10: v10fmt(row.composite_adj),
    conseil: libelle(row)
  };
});
process.stdout.write(JSON.stringify(out));
"""
    resultat = subprocess.run(
        ["node", "-e", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert resultat.returncode == 0, resultat.stderr or resultat.stdout
    return json.loads(resultat.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
def test_csv_prod_identique_au_classement(tmp_path, monkeypatch):
    """47 lignes de production : note v10fmt et conseil du Classement."""
    brut = json.loads(
        (ROOT / "tests" / "fixtures" / "classement_prod_2026-10-03.json").read_text(encoding="utf-8")
    )
    lignes = brut["ranking"]
    assert len(lignes) == 47
    assert "BBGC" in brut["absents_du_classement"]
    assert all(ligne["ticker"] != "BBGC" for ligne in lignes)
    par = {ligne["ticker"]: ligne for ligne in lignes}
    assert par["SICC"]["statut"] == "suspendu"
    assert par["SEMC"]["statut"] == "suspendu"
    assert par["SICC"]["statut_depuis"].startswith("2026-09-16")
    assert par["SEMC"]["statut_depuis"].startswith("2026-09-16")

    chemin = tmp_path / "live_ranking.json"
    chemin.write_text(json.dumps(brut, ensure_ascii=False), encoding="utf-8")
    avant = chemin.read_bytes()
    monkeypatch.setattr(live_ranker, "RANKING_PATH", str(chemin))
    monkeypatch.setattr(features, "DATA_DIR", str(tmp_path))
    corps = _lire_csv(features.export_csv())
    assert chemin.read_bytes() == avant
    assert len(corps) == 48
    assert [ligne[0] for ligne in corps[1:]] == [ligne["ticker"] for ligne in lignes]
    assert "BBGC" not in [ligne[0] for ligne in corps]

    ecran = {ligne["ticker"]: ligne for ligne in _libelles_classement(lignes)}
    for csv_ligne, source in zip(corps[1:], lignes):
        vu = ecran[source["ticker"]]
        assert csv_ligne[5] == vu["note"] == vu["v10"]
        assert csv_ligne[6] == vu["conseil"]
    assert ecran["SICC"]["conseil"] == PHRASE_SUSPENDUE
    assert ecran["SEMC"]["conseil"] == PHRASE_SUSPENDUE
    assert corps[1 + [l["ticker"] for l in lignes].index("SICC")][6] == PHRASE_SUSPENDUE
    assert corps[1 + [l["ticker"] for l in lignes].index("SEMC")][6] == PHRASE_SUSPENDUE
