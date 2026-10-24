"""Retry des écritures SQLite sur un verrou temporaire (chantier #11).

Le screener écrit depuis plusieurs threads et l'IA peut écrire en parallèle :
un verrou SQLite transitoire ne doit pas faire échouer une analyse. Ces tests
neutralisent le back-off réel pour rester déterministes et rapides.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from obole import config
from obole.data import cache


def _base_avec_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Base jetable, schéma créé, retry court : conditions du test."""
    db = tmp_path / "cache.sqlite"
    monkeypatch.setattr(config, "CACHE_DB", db)
    monkeypatch.setattr(config, "SQLITE_BUSY_TIMEOUT", 20)
    monkeypatch.setattr(config, "SQLITE_WRITE_RETRIES", 3)
    cache.put("BASE", "kind", {"v": 1})  # déclenche les migrations une fois
    return db


def _verrouiller(db: Path) -> sqlite3.Connection:
    """Ouvre une connexion qui tient le verrou d'écriture SQLite."""
    blocker = sqlite3.connect(db, timeout=0)
    blocker.execute("PRAGMA journal_mode=WAL")
    blocker.execute("BEGIN IMMEDIATE")
    return blocker


def test_verrou_temporaire_est_rejoue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Le premier back-off relâche le verrou, la seconde tentative réussit."""
    db = _base_avec_schema(tmp_path, monkeypatch)
    blocker = _verrouiller(db)
    relache = {"fait": False}

    def backoff(attempt: int) -> None:
        if not relache["fait"]:
            blocker.rollback()
            relache["fait"] = True

    monkeypatch.setattr(cache, "_backoff", backoff)
    try:
        cache.put("RI.PA", "analyse", {"x": 1})
    finally:
        blocker.close()

    assert relache["fait"] is True
    assert cache.get("RI.PA", "analyse", 3600) == {"x": 1}


def test_verrou_permanent_remonte_apres_n_tentatives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un verrou qui ne se libère jamais remonte, sans boucle infinie."""
    db = _base_avec_schema(tmp_path, monkeypatch)
    blocker = _verrouiller(db)
    backoffs: list[int] = []
    monkeypatch.setattr(cache, "_backoff", lambda attempt: backoffs.append(attempt))
    try:
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            cache.put("RI.PA", "analyse", {"x": 1})
    finally:
        blocker.rollback()
        blocker.close()

    assert backoffs == list(range(1, config.SQLITE_WRITE_RETRIES))
    assert cache.get("RI.PA", "analyse", 3600) is None


def test_autre_erreur_ne_retente_pas(monkeypatch: pytest.MonkeyPatch) -> None:
    """Seul `database is locked` est rejoué : une autre erreur remonte aussitôt."""
    backoffs: list[int] = []
    monkeypatch.setattr(cache, "_backoff", lambda attempt: backoffs.append(attempt))

    def autre_erreur() -> None:
        raise sqlite3.OperationalError("no such table: absente")

    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        cache._retry_locked(autre_erreur)
    assert backoffs == []
