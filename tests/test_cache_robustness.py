"""Robustesse du cache face à un blob illisible — sans réseau.

Un blob picklé peut référencer une classe qui n'existe plus (renommage du
paquet, version de modèle changée) : `pickle.loads` lève alors
`ModuleNotFoundError` / `AttributeError` / `UnpicklingError`. Le cache doit se
comporter comme un **miss** (et purger l'entrée), jamais faire échouer l'appel :
le cache est une optimisation, pas une dépendance.
"""

from __future__ import annotations

import time

import pytest

from obole import config
from obole.data import cache


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DB", tmp_path / "cache.sqlite")
    yield


def _put_raw(ticker: str, kind: str, payload: bytes) -> None:
    with cache.connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO cache (ticker, kind, payload, fetched_at) VALUES (?,?,?,?)",
            (ticker, kind, payload, time.time()),
        )
        conn.commit()


def test_unreadable_payload_is_a_cache_miss():
    _put_raw("TST", "identity", b"\x80\x04cobole.models\nStockIdentity\n.")
    assert cache.get("TST", "identity", ttl=10_000) is None


def test_unreadable_payload_is_purged():
    _put_raw("TST", "identity", b"pas du tout un pickle")
    assert cache.get("TST", "identity", ttl=10_000) is None
    assert cache.get("TST", "identity", ttl=10_000) is None


def test_readable_payload_roundtrip():
    cache.put("TST", "identity", {"name": "Test SA"})
    assert cache.get("TST", "identity", ttl=10_000) == {"name": "Test SA"}
