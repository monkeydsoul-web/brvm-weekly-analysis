# -*- coding: utf-8 -*-
"""Gardes : pas de reseau, pas de /var/data, fixtures anonymes."""
import json
import os
import socket

import pytest

import paths


def test_data_dir_hors_var_data(data_dir):
    absolu = os.path.abspath(paths.DATA_DIR)
    assert absolu == os.path.abspath(data_dir)
    assert not absolu.startswith("/var/data")
    assert os.environ["BRVM_DATA_DIR"] == data_dir


def test_socket_connect_interdit():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(RuntimeError, match="appel reseau interdit"):
            sock.connect(("192.0.2.1", 9))
    finally:
        sock.close()


def test_create_connection_interdit():
    with pytest.raises(RuntimeError, match="appel reseau interdit"):
        socket.create_connection(("192.0.2.1", 9), timeout=0.2)


def test_fixtures_anonymes(fixtures_dir):
    assert fixtures_dir.parent.name == "tests"
    assert "data" != fixtures_dir.parent.name
    fichiers = sorted(p.name for p in fixtures_dir.glob("*.json"))
    assert fichiers == [
        "bna_cas.json",
        "bna_univers.json",
        "boc_lignes.json",
        "classement_prod_2026-10-03.json",
        "live_cache.json",
        "live_ranking.json",
        "ratings_emetteurs.json",
        "susp_actif.json",
        "susp_fin_passee.json",
        "susp_malforme.json",
    ]
    boc = json.loads((fixtures_dir / "boc_lignes.json").read_text(encoding="utf-8"))
    assert len(boc) == 5
    for ligne in boc.values():
        assert ligne["cours_clot"] > 0
    texte = "\n".join(p.read_text(encoding="utf-8") for p in fixtures_dir.glob("*.json"))
    assert "sk-ant" not in texte
    assert "ANTHROPIC" not in texte
    assert "/var/data" not in texte
