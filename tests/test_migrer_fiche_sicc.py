# -*- coding: utf-8 -*-
"""Migration disque de la fiche SICC : SICOR, pas le câblier.

Aucune note, aucun conseil, aucun prix cible n'est recalculé.
"""
import json
import os
import re
import threading
from pathlib import Path

import pytest

import migrer_fiche_sicc

ROOT = Path(__file__).resolve().parents[1]
FICHE = json.loads((ROOT / "stories" / "sicc.json").read_text(encoding="utf-8"))
_BAK = re.compile(r"companies_stories\.json\.bak-\d{8}T\d{12}Z$")


def _histoires():
    return {
        "_meta": {
            "generated_at": "2026-05-30T17:54:09+00:00",
            "source": "generation",
        },
        "stories": {
            "ABJC": {
                "en_bref": "Erium Côte d'Ivoire, texte laissé tel quel.",
                "activites": ["Transport aérien"],
            },
            "CABC": {
                "en_bref": "Sicable fabrique des câbles.",
                "points_forts": ["Cuivre", "Câbles"],
                "conseil": "À surveiller",
                "prix_cible": 1234,
                "note10": 5.3,
            },
            "SICC": {
                "en_bref": "SICABLE est une société industrielle ivoirienne cotée à la BRVM, spécialisée dans la fabrication et la distribution de câbles.",
                "points_forts": ["Câbles"],
                "activites": ["Câbles électriques"],
            },
            "SEMC": {
                "en_bref": "Autre société, inchangée.",
                "presence": ["🇨🇮 Côte d'Ivoire", "🇸🇳 Sénégal"],
            },
        },
    }


def _ecrire(dossier, payload, brut=None):
    chemin = Path(dossier) / "companies_stories.json"
    if brut is None:
        chemin.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        chemin.write_bytes(brut)
    return chemin


def _sauvegardes(dossier):
    return sorted(Path(dossier).glob("companies_stories.json.bak-*"))


def test_migration_idempotente_sauvegarde_et_laisse_les_autres(tmp_path):
    avant = _histoires()
    chemin = _ecrire(tmp_path, avant)
    original = chemin.read_bytes()
    horodatage = chemin.stat().st_mtime_ns

    resultat = migrer_fiche_sicc.migrer_fiche_sicc(str(tmp_path))

    assert resultat["modifie"] is True
    assert resultat["raison"] == "migre"
    assert resultat["chemin"] == str(chemin)
    sauvegarde = Path(resultat["sauvegarde"])
    assert sauvegarde.is_file()
    assert _BAK.search(sauvegarde.name)
    assert sauvegarde.read_bytes() == original

    apres = json.loads(chemin.read_text(encoding="utf-8"))
    assert apres["stories"]["SICC"] == FICHE
    assert apres["stories"]["CABC"] == avant["stories"]["CABC"]
    assert apres["stories"]["ABJC"] == avant["stories"]["ABJC"]
    assert apres["stories"]["SEMC"] == avant["stories"]["SEMC"]
    assert list(apres["stories"]) == list(avant["stories"])
    assert apres["_meta"] == avant["_meta"]
    sicc = json.dumps(apres["stories"]["SICC"], ensure_ascii=False).lower()
    assert "coco" in sicc
    assert "sicable" not in sicc
    assert "câble" not in sicc and "cable" not in sicc
    assert "câble" in apres["stories"]["CABC"]["en_bref"].lower()
    assert apres["stories"]["CABC"]["conseil"] == "À surveiller"
    assert apres["stories"]["CABC"]["prix_cible"] == 1234
    assert apres["stories"]["CABC"]["note10"] == 5.3

    octets = chemin.read_bytes()
    mtime = chemin.stat().st_mtime_ns
    assert mtime != horodatage
    second = migrer_fiche_sicc.migrer_fiche_sicc(str(tmp_path))
    assert second["modifie"] is False
    assert second["raison"] == "deja_a_jour"
    assert second["sauvegarde"] is None
    assert chemin.read_bytes() == octets
    assert chemin.stat().st_mtime_ns == mtime
    assert len(_sauvegardes(tmp_path)) == 1
    assert not list(tmp_path.glob("*.json.tmp"))
    assert not list(tmp_path.glob("*.bak.tmp"))


def test_fichier_absent_ne_cree_rien(tmp_path):
    resultat = migrer_fiche_sicc.migrer_fiche_sicc(str(tmp_path))
    assert resultat["modifie"] is False
    assert resultat["raison"] == "fichier_absent"
    assert resultat["sauvegarde"] is None
    assert list(tmp_path.iterdir()) == []


def test_json_illisible_et_structure_inattendue_ne_touchent_pas(tmp_path):
    chemin = _ecrire(tmp_path, None, brut=b"{ ceci n'est pas du json")
    original = chemin.read_bytes()
    illisible = migrer_fiche_sicc.migrer_fiche_sicc(str(tmp_path))
    assert illisible["raison"] == "json_illisible"
    assert illisible["modifie"] is False
    assert chemin.read_bytes() == original
    assert _sauvegardes(tmp_path) == []

    chemin.write_text(json.dumps(["pas", "un", "objet"]), encoding="utf-8")
    brut = chemin.read_bytes()
    structure = migrer_fiche_sicc.migrer_fiche_sicc(str(tmp_path))
    assert structure["raison"] == "structure_inattendue"
    assert structure["modifie"] is False
    assert chemin.read_bytes() == brut
    assert _sauvegardes(tmp_path) == []

    chemin.write_text(json.dumps({"stories": ["liste"]}), encoding="utf-8")
    brut = chemin.read_bytes()
    sans_dict = migrer_fiche_sicc.migrer_fiche_sicc(str(tmp_path))
    assert sans_dict["raison"] == "structure_inattendue"
    assert chemin.read_bytes() == brut


def test_echec_du_remplacement_conserve_lorigine_et_la_sauvegarde(tmp_path, monkeypatch):
    avant = _histoires()
    chemin = _ecrire(tmp_path, avant)
    original = chemin.read_bytes()
    reel = os.replace

    def remplacer(src, dst):
        if os.path.basename(dst) == "companies_stories.json":
            raise OSError("disque plein")
        return reel(src, dst)

    monkeypatch.setattr(migrer_fiche_sicc.os, "replace", remplacer)
    with pytest.raises(OSError, match="disque plein"):
        migrer_fiche_sicc.migrer_fiche_sicc(str(tmp_path))

    assert chemin.read_bytes() == original
    sauvegardes = _sauvegardes(tmp_path)
    assert len(sauvegardes) == 1
    assert sauvegardes[0].read_bytes() == original
    assert not list(tmp_path.glob("*.json.tmp"))


def test_deux_appels_paralleles_une_seule_sauvegarde(tmp_path):
    _ecrire(tmp_path, _histoires())
    resultats = []
    erreurs = []

    def lancer():
        try:
            resultats.append(migrer_fiche_sicc.migrer_fiche_sicc(str(tmp_path)))
        except Exception as exc:  # pragma: no cover - le test échoue via erreurs
            erreurs.append(exc)

    fils = [threading.Thread(target=lancer) for _ in range(4)]
    for fil in fils:
        fil.start()
    for fil in fils:
        fil.join()

    assert erreurs == []
    assert sum(1 for r in resultats if r["raison"] == "migre") == 1
    assert sum(1 for r in resultats if r["raison"] == "deja_a_jour") == 3
    assert len(_sauvegardes(tmp_path)) == 1
    apres = json.loads((tmp_path / "companies_stories.json").read_text(encoding="utf-8"))
    assert apres["stories"]["SICC"] == FICHE
    assert apres["stories"]["CABC"]["en_bref"] == "Sicable fabrique des câbles."
    assert apres["stories"]["ABJC"]["en_bref"].startswith("Erium")


def test_demarrage_appelle_la_migration_et_la_route_ecrase_encore():
    import inspect
    import app

    corps = inspect.getsource(app._init_app)
    assert "migrer_fiche_sicc" in corps
    assert corps.index("BRVM_DISABLE_SCHEDULER") < corps.index("migrer_fiche_sicc")
    route = inspect.getsource(app.serve_companies_stories)
    assert 'stories["SICC"] = _histoire_sicc()' in route


def test_cli_deja_a_jour_puis_absent(tmp_path, capsys):
    _ecrire(tmp_path, {"_meta": {"generated_at": "2026-05-30T17:54:09+00:00"}, "stories": {"SICC": FICHE, "CABC": {"en_bref": "inchangée"}}})
    assert migrer_fiche_sicc.main(["--data-dir", str(tmp_path)]) == 0
    lu = json.loads(capsys.readouterr().out)
    assert lu["raison"] == "deja_a_jour"
    assert _sauvegardes(tmp_path) == []

    vide = tmp_path / "vide"
    vide.mkdir()
    assert migrer_fiche_sicc.main(["--data-dir", str(vide)]) == 1
    lu = json.loads(capsys.readouterr().out)
    assert lu["raison"] == "fichier_absent"
