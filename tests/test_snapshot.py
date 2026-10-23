"""Copie de sécurité automatique avant une écriture pilotée par l'IA — sans réseau.

Le MCP peut écrire dans la base (transactions, thèses, indices…). Une IA qui
hallucine ne doit pas pouvoir détruire des données sans filet : avant chaque
outil d'écriture, la base est copiée à côté d'elle-même (`cache.sqlite.bak`).

Le snapshot est **best-effort** : un échec (disque plein, permissions) ne doit
pas rendre le serveur MCP inutilisable — il est journalisé, l'écriture a lieu.
"""

from __future__ import annotations

import sqlite3

import pytest

from obole import config
from obole.data import backup, cache


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DB", tmp_path / "cache.sqlite")
    with cache.connect():
        pass
    yield


def test_snapshot_creates_backup_file():
    backup.snapshot_before_write()
    assert config.CACHE_DB.with_suffix(".sqlite.bak").exists()


def test_snapshot_captures_user_rows():
    with cache.connect() as conn:
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", ("TREND_MA_SHORT", "42"))
        conn.commit()

    backup.snapshot_before_write()

    with sqlite3.connect(config.CACHE_DB.with_suffix(".sqlite.bak")) as conn:
        row = conn.execute("SELECT value FROM settings WHERE key='TREND_MA_SHORT'").fetchone()
    assert row is not None and row[0] == "42"


def test_snapshot_is_idempotent():
    backup.snapshot_before_write()
    backup.snapshot_before_write()
    assert config.CACHE_DB.with_suffix(".sqlite.bak").exists()


def test_snapshot_never_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DB", tmp_path / "absent" / "missing.sqlite")
    backup.snapshot_before_write()


def test_snapshot_path_is_next_to_db():
    path = backup.snapshot_path()
    assert path.parent == config.CACHE_DB.parent
    assert path.name == "cache.sqlite.bak"
