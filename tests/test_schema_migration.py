"""Tests du versioning du schéma SQLite (#02) — sans réseau.

Le cache est isolé sur une base temporaire (config.CACHE_DB), comme
tests/test_settings.py. On vérifie la version du schéma, l'idempotence, la
préservation des données utilisateur et l'atomicité des migrations.
"""

from __future__ import annotations

import sqlite3
import tempfile

import pytest

from obole import config
from obole.data import cache


@pytest.fixture(autouse=True)
def _isolated_db():
    """Isole le cache sur une base temporaire (évite de toucher cache.sqlite)."""
    _orig = config.CACHE_DB
    config.CACHE_DB = tempfile.mktemp(suffix=".sqlite")
    yield
    config.CACHE_DB = _orig


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


class TestUserVersion:
    """J1 — lecture/écriture de `PRAGMA user_version`."""

    def test_fresh_db_reads_zero(self):
        conn = sqlite3.connect(config.CACHE_DB)
        try:
            assert cache._read_user_version(conn) == 0
        finally:
            conn.close()

    def test_write_then_read_roundtrip(self):
        conn = sqlite3.connect(config.CACHE_DB)
        try:
            cache._write_user_version(conn, 7)
            conn.commit()
            assert cache._read_user_version(conn) == 7
        finally:
            conn.close()


class TestBaseline:
    """J2 — la migration 0 -> 1 crée le schéma et pose la version cible."""

    def test_conn_sets_schema_version(self):
        conn = cache._conn()
        try:
            assert cache._read_user_version(conn) == config.SCHEMA_VERSION
        finally:
            conn.close()

    def test_conn_creates_all_user_tables(self):
        conn = cache._conn()
        try:
            assert {
                "cache",
                "manual_fundamentals",
                "custom_categories",
                "custom_indices",
                "settings",
                "events",
            } <= _table_names(conn)
        finally:
            conn.close()

    def test_migration_0_to_1_creates_schema(self):
        conn = sqlite3.connect(config.CACHE_DB)
        try:
            cache.MIGRATIONS[0](conn)
            conn.commit()
            assert "settings" in _table_names(conn)
            assert "events" in _table_names(conn)
            assert "custom_indices" in _table_names(conn)
        finally:
            conn.close()


class TestIdempotence:
    """J2 — une base déjà à jour ne déclenche aucune migration."""

    def test_second_open_runs_no_migration(self, monkeypatch):
        calls: list[int] = []
        real = cache.MIGRATIONS[0]

        def counting(conn: sqlite3.Connection) -> None:
            calls.append(1)
            real(conn)

        monkeypatch.setitem(cache.MIGRATIONS, 0, counting)

        cache._conn().close()  # base neuve : la migration 0 -> 1 s'exécute
        assert len(calls) == 1
        cache._conn().close()  # déjà à jour : rien
        assert len(calls) == 1


class TestAtomicity:
    """J2 — une migration qui échoue laisse la base strictement inchangée."""

    def _base_at(self, version: int) -> None:
        """Prépare une base à `version` (baseline appliquée puis version forcée)."""
        conn = sqlite3.connect(config.CACHE_DB)
        try:
            cache.MIGRATIONS[0](conn)
            cache._write_user_version(conn, version)
            conn.commit()
        finally:
            conn.close()

    def test_failed_migration_rolls_back(self, monkeypatch):
        self._base_at(1)  # base en v1 (le schéma v2 n'est pas encore appliqué)
        conn = sqlite3.connect(config.CACHE_DB)
        try:
            assert cache._read_user_version(conn) == 1
        finally:
            conn.close()

        def failing(c: sqlite3.Connection) -> None:
            c.execute("ALTER TABLE events ADD COLUMN boom TEXT")
            raise RuntimeError("migration cassée")

        monkeypatch.setitem(cache.MIGRATIONS, 1, failing)
        monkeypatch.setattr(config, "SCHEMA_VERSION", 2)

        with pytest.raises(RuntimeError, match="migration cassée"):
            cache._conn()

        conn = sqlite3.connect(config.CACHE_DB)
        try:
            assert cache._read_user_version(conn) == 1
            assert "boom" not in _columns(conn, "events")
        finally:
            conn.close()

    def test_missing_migration_raises(self, monkeypatch):
        self._base_at(1)
        monkeypatch.setattr(config, "SCHEMA_VERSION", 8)  # aucune migration 7 -> 8
        with pytest.raises(RuntimeError, match="Migration manquante"):
            cache._conn()


class TestUpgradePreservesData:
    """J3 — base ancienne (v0) migrée, données utilisateur intactes."""

    def test_v0_db_migrated_and_data_intact(self):
        conn = sqlite3.connect(config.CACHE_DB)
        try:
            cache.MIGRATIONS[0](conn)
            conn.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES ('trend_ma_short','20',1.0)"
            )
            conn.execute(
                "INSERT INTO events (ref, event_date, label, description, created_at)"
                " VALUES ('RI.PA','2020-01-01','Ancien',NULL,1.0)"
            )
            conn.execute(
                "INSERT INTO manual_fundamentals (ticker, year, metric, value, added_at)"
                " VALUES ('RI.PA',2020,'CA',1000.0,1.0)"
            )
            conn.commit()
            assert cache._read_user_version(conn) == 0
        finally:
            conn.close()

        conn = cache._conn()
        try:
            assert cache._read_user_version(conn) == config.SCHEMA_VERSION
            assert (
                conn.execute("SELECT value FROM settings WHERE key='trend_ma_short'").fetchone()[0]
                == "20"
            )
            assert conn.execute("SELECT label FROM events").fetchone()[0] == "Ancien"
            assert conn.execute("SELECT value FROM manual_fundamentals").fetchone()[0] == 1000.0
        finally:
            conn.close()


class TestFutureMigration:
    """J3 — le mécanisme tient au-delà de la baseline (migration 7 -> 8, hypothétique)."""

    def test_v7_to_v8_alter_preserves_data(self, monkeypatch):
        cache._conn().close()  # base migrée jusqu'à la version courante (v7)
        conn = sqlite3.connect(config.CACHE_DB)
        try:
            conn.execute(
                "INSERT INTO events (ref, event_date, label, description, created_at)"
                " VALUES ('RI.PA','2021-05-05','Résultats',NULL,2.0)"
            )
            conn.commit()
        finally:
            conn.close()

        def v7_to_v8(c: sqlite3.Connection) -> None:
            c.execute("ALTER TABLE events ADD COLUMN impact TEXT")

        monkeypatch.setitem(cache.MIGRATIONS, 7, v7_to_v8)
        monkeypatch.setattr(config, "SCHEMA_VERSION", 8)

        conn = cache._conn()
        try:
            assert cache._read_user_version(conn) == 8
            assert "impact" in _columns(conn, "events")
            assert conn.execute("SELECT label FROM events").fetchone()[0] == "Résultats"
        finally:
            conn.close()

    def test_v6_to_v7_adds_tag_column(self):
        """#17.6 — la migration 6 -> 7 ajoute `tag` sans perdre les transactions."""
        conn = sqlite3.connect(config.CACHE_DB)
        try:
            for version in range(0, 6):
                cache.MIGRATIONS[version](conn)
            conn.execute(
                "INSERT INTO portfolio_accounts (name, currency, created_at)"
                " VALUES ('PEA','EUR',1.0)"
            )
            conn.execute(
                "INSERT INTO portfolio_transactions "
                "(account_id, ticker, side, trade_date, quantity, price, fees, currency,"
                " note, created_at) VALUES (1,'RI.PA','buy','2024-01-02',10,100.0,0,'EUR',NULL,1.0)"
            )
            cache._write_user_version(conn, 6)
            conn.commit()
            assert "tag" not in _columns(conn, "portfolio_transactions")
        finally:
            conn.close()

        conn = cache._conn()
        try:
            assert cache._read_user_version(conn) == config.SCHEMA_VERSION
            assert "tag" in _columns(conn, "portfolio_transactions")
            row = conn.execute(
                "SELECT ticker, quantity, tag FROM portfolio_transactions"
            ).fetchone()
            assert (row[0], row[1], row[2]) == ("RI.PA", 10, None)
        finally:
            conn.close()

    def test_concurrent_open_on_v6_db_migrates_once(self):
        """#17.6 — deux connexions simultanées sur une base v6 convergent sans
        « duplicate column name » (l'`ALTER TABLE` n'est pas `IF NOT EXISTS` :
        la migration doit tolérer la course)."""
        import threading

        conn = sqlite3.connect(config.CACHE_DB)
        try:
            for version in range(0, 6):
                cache.MIGRATIONS[version](conn)
            cache._write_user_version(conn, 6)
            conn.commit()
        finally:
            conn.close()

        errors: list[Exception] = []

        def open_once() -> None:
            try:
                cache._conn().close()
            except Exception as exc:  # noqa: BLE001 — collecté pour l'assertion
                errors.append(exc)

        threads = [threading.Thread(target=open_once) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        conn = cache._conn()
        try:
            assert cache._read_user_version(conn) == config.SCHEMA_VERSION
            assert "tag" in _columns(conn, "portfolio_transactions")
        finally:
            conn.close()


class TestValuationSettingsMigration:
    """#20 — la migration 2 -> 3 crée la table des paramètres de valorisation."""

    def test_table_created_at_current_version(self):
        conn = cache._conn()
        try:
            assert cache._read_user_version(conn) == config.SCHEMA_VERSION
            assert "valuation_settings" in _table_names(conn)
            assert _columns(conn, "valuation_settings") == {"ticker", "payload", "updated_at"}
        finally:
            conn.close()

    def test_v2_db_gains_table_without_data_loss(self):
        # Base construite jusqu'à v2 : on insère une donnée, puis on migre.
        conn = sqlite3.connect(config.CACHE_DB)
        try:
            for version in (0, 1):
                cache.MIGRATIONS[version](conn)
            conn.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES ('trend_ma_long','150',1.0)"
            )
            cache._write_user_version(conn, 2)  # base déjà en v2
            conn.commit()
            assert cache._read_user_version(conn) == 2
        finally:
            conn.close()

        conn = cache._conn()
        try:
            assert cache._read_user_version(conn) == config.SCHEMA_VERSION
            assert "valuation_settings" in _table_names(conn)
            assert (
                conn.execute("SELECT value FROM settings WHERE key='trend_ma_long'").fetchone()[0]
                == "150"
            )
        finally:
            conn.close()


class TestValuationSettingsCache:
    """Accesseurs `get/set/clear_valuation_settings` (payload JSON opaque)."""

    def test_roundtrip_and_clear(self):
        assert cache.get_valuation_settings("RI.PA") is None
        cache.set_valuation_settings("RI.PA", {"metric": "eps", "fair_price": 64.76})
        got = cache.get_valuation_settings("ri.pa")  # insensible à la casse
        assert got == {"metric": "eps", "fair_price": 64.76}
        cache.clear_valuation_settings("RI.PA")
        assert cache.get_valuation_settings("RI.PA") is None

    def test_corrupted_payload_returns_none(self):
        cache.set_valuation_settings("RI.PA", {"metric": "eps"})
        conn = sqlite3.connect(config.CACHE_DB)
        try:
            conn.execute("UPDATE valuation_settings SET payload='not-json' WHERE ticker='RI.PA'")
            conn.commit()
        finally:
            conn.close()
        assert cache.get_valuation_settings("RI.PA") is None


class TestThesesMigration:
    """#09.3 — la migration 3 -> 4 crée la table des thèses d'entreprise."""

    def test_table_created_at_current_version(self):
        conn = cache._conn()
        try:
            assert cache._read_user_version(conn) == config.SCHEMA_VERSION
            assert "theses" in _table_names(conn)
            assert _columns(conn, "theses") == {
                "id",
                "ticker",
                "content",
                "created_at",
                "updated_at",
            }
        finally:
            conn.close()

    def test_v3_db_gains_table_without_data_loss(self):
        # Base construite jusqu'à v3 : on insère une donnée, puis on migre.
        conn = sqlite3.connect(config.CACHE_DB)
        try:
            for version in (0, 1, 2):
                cache.MIGRATIONS[version](conn)
            conn.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES ('trend_ma_short','20',1.0)"
            )
            cache._write_user_version(conn, 3)  # base déjà en v3
            conn.commit()
            assert cache._read_user_version(conn) == 3
        finally:
            conn.close()

        conn = cache._conn()
        try:
            assert cache._read_user_version(conn) == config.SCHEMA_VERSION
            assert "theses" in _table_names(conn)
            assert (
                conn.execute("SELECT value FROM settings WHERE key='trend_ma_short'").fetchone()[0]
                == "20"
            )
        finally:
            conn.close()

    def test_one_thesis_per_ticker(self):
        cache.save_thesis("RI.PA", {"pitch": "a"})
        cache.save_thesis("ri.pa", {"pitch": "b"})  # insensible à la casse -> remplace
        assert len(cache.list_theses()) == 1
        assert cache.get_thesis("RI.PA")["content"] == {"pitch": "b"}
