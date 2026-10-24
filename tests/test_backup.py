"""Sauvegarde / restauration des données utilisateur (#03) — sans réseau.

Les 5 tables saisies à la main ou paramétrées par l'utilisateur sont exportables
en JSON lisible et restaurables transactionnellement. Le cache technique (table
`cache`, blobs picklés) est volontairement exclu : il est jetable.

Le cache est isolé sur une base temporaire (config.CACHE_DB), comme
tests/test_settings.py et tests/test_events.py.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile

import pytest
from fastapi.testclient import TestClient

from obole import config
from obole.data import backup, cache


@pytest.fixture(autouse=True)
def _isolated_db():
    """Isole le cache sur une base temporaire (évite de toucher cache.sqlite)."""
    _orig = config.CACHE_DB
    config.CACHE_DB = tempfile.mktemp(suffix=".sqlite")
    yield
    config.CACHE_DB = _orig


@pytest.fixture
def client():
    from obole.api.app import app

    return TestClient(app)


def _populate() -> None:
    """Remplit les 5 tables utilisateur + les caches (prix, comptes, panier)."""
    cache.put_manual("RI.PA", [{"year": 2020, "metric": "Chiffre d'affaires", "value": 1000.0}])
    cache.set_settings({"trend_ma_short": 20})
    cat = cache.create_category("Boissons")
    cache.create_index(cat, "Spiritueux", ["RI.PA", "AI.PA"])
    cache.add_event("RI.PA", "2020-01-01", "Résultats", "Bonne année")
    cache.put("RI.PA", "prices", {"fake": "prices"})
    cache.put("RI.PA", "fundamentals", {"fake": "fundamentals"})
    cache.put("RI.PA", "fundamentals_missing", True)
    cache.put("INDEX:1", "basket", {"fake": "basket"})


def _cache_kinds() -> set[tuple[str, str]]:
    with cache.connect() as conn:
        return {(r[0], r[1]) for r in conn.execute("SELECT ticker, kind FROM cache").fetchall()}


def _snapshot() -> dict[str, list[tuple]]:
    """Photo complète des 5 tables utilisateur (toutes colonnes, ordre stable)."""
    with cache.connect() as conn:
        out: dict[str, list[tuple]] = {}
        for name, cols in backup._TABLE_COLUMNS.items():
            rows = conn.execute(
                f"SELECT {', '.join(cols)} FROM {name} ORDER BY {', '.join(cols)}"
            ).fetchall()
            out[name] = [tuple(r) for r in rows]
        return out


def _cache_count() -> int:
    with cache.connect() as conn:
        return conn.execute("SELECT count(*) FROM cache").fetchone()[0]


class TestBuildArchive:
    """J1 — structure et en-tête de l'archive."""

    def test_header_and_tables(self):
        _populate()
        arch = backup.build_archive()
        assert arch["format"] == "obole-backup"
        assert arch["format_version"] == backup.FORMAT_VERSION
        assert arch["schema_version"] == config.SCHEMA_VERSION
        assert isinstance(arch["created_at"], str) and arch["created_at"]
        assert set(arch["tables"]) == set(backup._TABLE_COLUMNS)

    def test_contains_user_rows(self):
        _populate()
        tables = backup.build_archive()["tables"]
        assert len(tables["manual_fundamentals"]) == 1
        assert tables["settings"][0]["key"] == "trend_ma_short"
        assert len(tables["custom_categories"]) == 1
        assert len(tables["custom_indices"]) == 1
        assert len(tables["events"]) == 1

    def test_never_includes_price_cache(self):
        _populate()
        tables = backup.build_archive()["tables"]
        assert "cache" not in tables
        assert "cache" not in backup._TABLE_COLUMNS


class TestBackupRoute:
    """J1 — GET /api/backup."""

    def test_returns_valid_json_with_attachment(self, client):
        _populate()
        r = client.get("/api/backup")
        assert r.status_code == 200
        assert "attachment" in r.headers["content-disposition"]
        assert r.headers["content-disposition"].endswith('.json"')
        data = r.json()
        assert data["format"] == "obole-backup"
        assert set(data["tables"]) == set(backup._TABLE_COLUMNS)


class TestRoundTrip:
    """J2 — aller-retour fidèle."""

    def test_restore_identical_to_source(self, client):
        _populate()
        before = _snapshot()
        archive = client.get("/api/backup").json()

        # Vide toutes les tables utilisateur, puis restaure.
        with cache.connect() as conn:
            for name in backup._TABLE_COLUMNS:
                conn.execute(f"DELETE FROM {name}")
            conn.commit()
        assert _snapshot()["events"] == []

        r = client.post(
            "/api/restore",
            files={"file": ("backup.json", json.dumps(archive), "application/json")},
        )
        assert r.status_code == 200
        assert _snapshot() == before

    def test_restore_into_empty_db(self, client):
        _populate()
        source = client.get("/api/backup").json()

        # Nouvelle base vierge (aucune donnée) : on change CACHE_DB.
        config.CACHE_DB = tempfile.mktemp(suffix=".sqlite")
        r = client.post(
            "/api/restore",
            files={"file": ("backup.json", json.dumps(source), "application/json")},
        )
        assert r.status_code == 200
        restored = client.get("/api/backup").json()
        assert restored["tables"] == source["tables"]

    def test_preserves_ids_and_timestamps(self, client):
        _populate()
        source = client.get("/api/backup").json()
        ev_id = source["tables"]["events"][0]["id"]
        ix_id = source["tables"]["custom_indices"][0]["id"]

        client.post(
            "/api/restore",
            files={"file": ("b.json", json.dumps(source), "application/json")},
        )
        after = client.get("/api/backup").json()
        assert after["tables"]["events"][0]["id"] == ev_id
        assert after["tables"]["custom_indices"][0]["id"] == ix_id
        assert (
            after["tables"]["events"][0]["created_at"]
            == source["tables"]["events"][0]["created_at"]
        )


class TestValidation:
    """J2 — rejets stricts : 422 ET base inchangée."""

    @pytest.fixture(autouse=True)
    def _base(self):
        _populate()
        self.before = _snapshot()

    def _post(self, client, payload):
        body = payload if isinstance(payload, str) else json.dumps(payload)
        r = client.post("/api/restore", files={"file": ("b.json", body, "application/json")})
        assert r.status_code == 422, r.text
        assert _snapshot() == self.before, "la base doit être inchangée après un rejet"
        return r

    def _valid(self) -> dict:
        return backup.build_archive()

    def test_invalid_json(self, client):
        self._post(client, "{ pas du json")

    def test_unknown_format(self, client):
        a = self._valid()
        a["format"] = "autre-outil"
        self._post(client, a)

    def test_format_version_too_recent(self, client):
        a = self._valid()
        a["format_version"] = backup.FORMAT_VERSION + 1
        self._post(client, a)

    def test_schema_version_too_recent(self, client):
        a = self._valid()
        a["schema_version"] = config.SCHEMA_VERSION + 1
        self._post(client, a)

    def test_missing_table(self, client):
        a = self._valid()
        del a["tables"]["events"]
        self._post(client, a)

    def test_unknown_table(self, client):
        a = self._valid()
        a["tables"]["cache"] = []
        self._post(client, a)

    def test_row_not_conforming(self, client):
        a = self._valid()
        a["tables"]["settings"] = [{"key": "trend_ma_short"}]  # colonnes manquantes
        self._post(client, a)

    def test_row_wrong_type(self, client):
        a = self._valid()
        a["tables"]["settings"] = [{"key": "x", "value": 12, "updated_at": 1.0}]
        self._post(client, a)

    def test_row_not_an_object(self, client):
        a = self._valid()
        a["tables"]["events"] = ["nope"]
        self._post(client, a)

    def test_orphan_index_category(self, client):
        a = self._valid()
        a["tables"]["custom_categories"] = []
        self._post(client, a)


class TestAtomicity:
    """J2 — rollback intégral si l'insertion échoue."""

    def test_rollback_on_constraint_violation(self, client):
        _populate()
        before = _snapshot()
        archive = backup.build_archive()
        # Deux lignes de même clé primaire : passe la validation structurelle,
        # mais viole la contrainte UNIQUE au moment de l'INSERT.
        archive["tables"]["settings"] = [
            {"key": "trend_ma_short", "value": "20", "updated_at": 1.0},
            {"key": "trend_ma_short", "value": "30", "updated_at": 2.0},
        ]
        r = client.post(
            "/api/restore",
            files={"file": ("b.json", json.dumps(archive), "application/json")},
        )
        assert r.status_code == 422, r.text
        assert _snapshot() == before, "les tables doivent être restaurées à l'identique"


class TestSequenceIntegrity:
    """J2 — pas de collision de PK après restauration."""

    def test_new_rows_get_fresh_ids(self, client):
        _populate()
        archive = backup.build_archive()
        max_event = max(e["id"] for e in archive["tables"]["events"])
        max_index = max(i["id"] for i in archive["tables"]["custom_indices"])
        cat_id = archive["tables"]["custom_categories"][0]["id"]

        client.post(
            "/api/restore",
            files={"file": ("b.json", json.dumps(archive), "application/json")},
        )
        # Nouvelles insertions : les id doivent être strictement supérieurs.
        new_ev = cache.add_event("AI.PA", "2021-01-01", "Nouveau", None)
        new_ix = cache.create_index(cat_id, "Nouveau", ["AI.PA"])
        assert new_ev > max_event
        assert new_ix > max_index


class TestSchemaCoupling:
    """`_TABLE_COLUMNS` doit rester aligné sur le DDL réel de `cache.py`."""

    def test_columns_match_database_schema(self):
        """Garde-fou de dérive : une migration qui change une table doit casser ici.

        `build_archive` sélectionne une liste de colonnes explicite et la
        restauration l'utilise pour l'INSERT. Si le schéma évolue sans mettre à
        jour `_TABLE_COLUMNS`, les sauvegardes deviennent silencieusement
        incomplètes — ce test transforme la dérive en échec bruyant.
        """
        with cache.connect() as conn:
            for name, columns in backup._TABLE_COLUMNS.items():
                actual = {r[1] for r in conn.execute(f"PRAGMA table_info({name})")}
                assert set(columns) == actual, f"{name} : schéma et _TABLE_COLUMNS divergent"

    def test_foreign_key_parent_before_child(self):
        """L'ordre d'insertion doit placer `custom_categories` avant `custom_indices`."""
        names = list(backup._TABLE_COLUMNS)
        assert names.index("custom_categories") < names.index("custom_indices")


class TestDerivedCacheInvalidation:
    """La restauration purge les caches dérivés des données utilisateur."""

    def test_purges_fundamentals_and_baskets(self, client):
        _populate()
        before = _cache_kinds()
        assert ("RI.PA", "fundamentals") in before
        assert ("RI.PA", "fundamentals_missing") in before
        assert ("INDEX:1", "basket") in before

        client.post(
            "/api/restore",
            files={"file": ("b.json", json.dumps(backup.build_archive()), "application/json")},
        )
        after = _cache_kinds()
        # Caches dérivés purgés : les comptes fusionnent les données manuelles,
        # les paniers dépendent des définitions d'indices, et le marqueur négatif
        # masquerait des comptes restaurés.
        assert ("RI.PA", "fundamentals") not in after
        assert ("RI.PA", "fundamentals_missing") not in after
        assert ("INDEX:1", "basket") not in after
        # Les prix ne dépendent pas des données utilisateur : conservés.
        assert ("RI.PA", "prices") in after


class TestTickersValidation:
    """`custom_indices.tickers` doit être du JSON valide (liste de tickers)."""

    def _post(self, client, payload):
        r = client.post(
            "/api/restore",
            files={"file": ("b.json", json.dumps(payload), "application/json")},
        )
        assert r.status_code == 422, r.text
        return r

    def test_non_json_tickers_rejected(self, client):
        _populate()
        archive = backup.build_archive()
        archive["tables"]["custom_indices"][0]["tickers"] = "RI.PA"
        self._post(client, archive)

    def test_non_list_tickers_rejected(self, client):
        _populate()
        archive = backup.build_archive()
        archive["tables"]["custom_indices"][0]["tickers"] = '{"a": 1}'
        self._post(client, archive)

    def test_non_string_items_rejected(self, client):
        _populate()
        archive = backup.build_archive()
        archive["tables"]["custom_indices"][0]["tickers"] = "[1, 2]"
        self._post(client, archive)

    def test_valid_tickers_accepted(self, client):
        _populate()
        r = client.post(
            "/api/restore",
            files={"file": ("b.json", json.dumps(backup.build_archive()), "application/json")},
        )
        assert r.status_code == 200


class TestPublicConnection:
    """`cache.connect()` expose l'accès brut aux modules frères de `data/`."""

    def test_connect_yields_usable_connection_and_closes(self):
        with cache.connect() as conn:
            assert conn.execute("SELECT 1").fetchone()[0] == 1
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")  # fermée en sortie de contexte


class TestPurgeCache:
    """J3 — purge isolée du cache technique."""

    def test_purge_empties_cache_only(self, client):
        _populate()
        before = _snapshot()
        assert _cache_count() >= 1

        r = client.post("/api/cache/purge")
        assert r.status_code == 200
        assert r.json()["removed"] >= 1
        assert _cache_count() == 0
        assert _snapshot() == before, "les 5 tables utilisateur doivent être intactes"

    def test_purge_via_module(self):
        _populate()
        before = _snapshot()
        removed = backup.purge_cache()
        assert removed >= 1
        assert _cache_count() == 0
        assert _snapshot() == before

    def test_purge_empties_whole_cache(self):
        """Le geste vide TOUT le cache (pas seulement les prix) — nommage aligné."""
        _populate()
        assert _cache_kinds() == {
            ("RI.PA", "prices"),
            ("RI.PA", "fundamentals"),
            ("RI.PA", "fundamentals_missing"),
            ("INDEX:1", "basket"),
        }
        backup.purge_cache()
        assert _cache_kinds() == set()


class TestOlderArchive:
    """Une archive d'un schéma antérieur reste restaurable (#25 : v7 -> v8)."""

    def test_v7_archive_without_watchlist_tables_is_accepted(self, client):
        _populate()
        cache.upsert_watch_item("RI.PA", 1)
        cache.set_ticker_ref("RI.PA", "2012-01-04")
        archive = backup.build_archive()

        # Archive d'avant #25 : version 7, sans les deux nouvelles tables.
        archive["schema_version"] = 7
        del archive["tables"]["watchlist_items"]
        del archive["tables"]["ticker_refs"]

        r = client.post(
            "/api/restore",
            files={"file": ("b.json", json.dumps(archive), "application/json")},
        )
        assert r.status_code == 200, r.text
        # Les tables absentes de l'archive sont restaurées vides, sans erreur.
        assert cache.list_watch_items() == []
        assert cache.list_ticker_refs() == {}
