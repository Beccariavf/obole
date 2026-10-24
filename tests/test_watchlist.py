"""Watchlist (#25) — persistance et cas d'usage, sans réseau.

Le cache est isolé sur une base temporaire (même patron que test_settings.py et
test_schema_migration.py). Ce fichier couvre d'abord le SQL confiné de
`data/cache.py` (items + références), puis le service de classement.
"""

from __future__ import annotations

import sqlite3
import tempfile

import pytest

from obole import config
from obole.data import backup, cache


@pytest.fixture(autouse=True)
def _isolated_db():
    """Isole le cache sur une base temporaire (évite de toucher cache.sqlite)."""
    _orig = config.CACHE_DB
    config.CACHE_DB = tempfile.mktemp(suffix=".sqlite")
    yield
    config.CACHE_DB = _orig


class TestWatchlistItems:
    def test_add_then_get_case_insensitive(self):
        cache.upsert_watch_item("ri.pa", 2)
        item = cache.get_watch_item("RI.PA")
        assert item is not None
        assert item["ticker"] == "RI.PA"
        assert item["tier"] == 2
        assert item["added_at"] > 0

    def test_tier_change_preserves_added_at(self):
        cache.upsert_watch_item("RI.PA", 1)
        first = cache.get_watch_item("RI.PA")["added_at"]
        cache.upsert_watch_item("RI.PA", 3)
        again = cache.get_watch_item("RI.PA")
        assert again["tier"] == 3
        assert again["added_at"] == first  # date d'entrée, pas de réécriture

    def test_list_ordered_by_tier_then_ticker(self):
        cache.upsert_watch_item("ZZ.PA", 3)
        cache.upsert_watch_item("RI.PA", 1)
        cache.upsert_watch_item("AI.PA", 1)
        cache.upsert_watch_item("BN.PA", 2)
        assert [i["ticker"] for i in cache.list_watch_items()] == [
            "AI.PA",
            "RI.PA",
            "BN.PA",
            "ZZ.PA",
        ]

    def test_delete_returns_presence(self):
        cache.upsert_watch_item("RI.PA", 1)
        assert cache.delete_watch_item("ri.pa") is True
        assert cache.delete_watch_item("RI.PA") is False
        assert cache.count_watch_items() == 0

    def test_count(self):
        cache.upsert_watch_item("RI.PA", 1)
        cache.upsert_watch_item("AI.PA", 2)
        assert cache.count_watch_items() == 2

    def test_schema_refuses_tier_out_of_range(self):
        """Le CHECK est un garde-fou de dernier recours (le service valide avant)."""
        with cache.connect() as conn:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO watchlist_items (ticker, tier, added_at) VALUES ('RI.PA',4,1.0)"
                )


class TestTickerRefs:
    def test_set_get_list_clear(self):
        assert cache.get_ticker_ref("RI.PA") is None
        cache.set_ticker_ref("ri.pa", "2012-01-04")
        assert cache.get_ticker_ref("RI.PA") == "2012-01-04"
        cache.set_ticker_ref("AI.PA", "2015-06-01")
        assert cache.list_ticker_refs() == {"AI.PA": "2015-06-01", "RI.PA": "2012-01-04"}
        cache.clear_ticker_ref("RI.PA")
        assert cache.get_ticker_ref("RI.PA") is None
        assert cache.list_ticker_refs() == {"AI.PA": "2015-06-01"}

    def test_set_replaces_existing(self):
        cache.set_ticker_ref("RI.PA", "2010-01-01")
        cache.set_ticker_ref("RI.PA", "2014-01-01")
        assert cache.get_ticker_ref("RI.PA") == "2014-01-01"

    def test_ref_is_independent_from_membership(self):
        cache.upsert_watch_item("RI.PA", 1)
        cache.set_ticker_ref("RI.PA", "2012-01-04")
        cache.delete_watch_item("RI.PA")
        assert cache.get_watch_item("RI.PA") is None
        assert cache.get_ticker_ref("RI.PA") == "2012-01-04"


class TestBackupRegistry:
    def test_tables_are_declared(self):
        assert "watchlist_items" in backup._TABLE_COLUMNS
        assert "ticker_refs" in backup._TABLE_COLUMNS
        assert {"watchlist_items", "ticker_refs"} <= set(backup._TABLE_SINCE[8])

    def test_registry_guard_passes(self):
        backup._check_table_registry()
