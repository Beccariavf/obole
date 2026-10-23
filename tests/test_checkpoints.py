"""Points de contrôle suivis (#21, bande « Suivi ») — sans réseau.

Trois niveaux : la validation et l'I/O (`data/checkpoints.py`), la table et sa
migration (`data/cache.py`), puis les routes HTTP. Le cache est isolé sur une base
temporaire, comme `tests/test_events.py`.
"""

from __future__ import annotations

import sqlite3
import tempfile

import pytest
from fastapi.testclient import TestClient

from obole import config
from obole.data import cache, checkpoints


@pytest.fixture(autouse=True)
def _isolated_db():
    """Isole le cache sur une base temporaire (évite de toucher cache.sqlite)."""
    _orig = config.CACHE_DB
    config.CACHE_DB = tempfile.mktemp(suffix=".sqlite")
    yield
    config.CACHE_DB = _orig


class TestCheckpointsCache:
    """Couche `cache` : I/O pure sur la table `checkpoints`."""

    def test_add_and_list_in_creation_order(self):
        cache.add_checkpoint("RI.PA", "Marge > 28%")
        cache.add_checkpoint("RI.PA", "Rachats d'actions")
        out = cache.list_checkpoints("RI.PA")
        assert [c["label"] for c in out] == ["Marge > 28%", "Rachats d'actions"]
        assert [c["done"] for c in out] == [False, False]

    def test_isolation_by_ref(self):
        cache.add_checkpoint("RI.PA", "A")
        assert cache.list_checkpoints("MC.PA") == []

    def test_get_roundtrip(self):
        cid = cache.add_checkpoint("RI.PA", "A", done=True)
        assert cache.get_checkpoint(cid) == {
            "id": cid,
            "ref": "RI.PA",
            "label": "A",
            "done": True,
        }
        assert cache.get_checkpoint(99999) is None

    def test_update_and_count(self):
        cid = cache.add_checkpoint("RI.PA", "A")
        cache.update_checkpoint(cid, "B", True)
        assert cache.get_checkpoint(cid)["label"] == "B"
        assert cache.get_checkpoint(cid)["done"] is True
        assert cache.count_checkpoints("RI.PA") == 1

    def test_delete(self):
        cid = cache.add_checkpoint("RI.PA", "A")
        cache.delete_checkpoint(cid)
        assert cache.get_checkpoint(cid) is None


class TestCheckpointsValidation:
    """Ordre des points, bornes et normalisations."""

    def test_order_is_creation_not_completion(self):
        a = cache.add_checkpoint("RI.PA", "Premier")
        b = cache.add_checkpoint("RI.PA", "Second")
        # Cocher le premier ne doit PAS le faire passer en tête : l'ordre
        # d'affichage est celui d'écriture (sinon la liste bougerait sous le clic).
        checkpoints.update_checkpoint(a, "Premier", True)
        assert [c["id"] for c in checkpoints.list_checkpoints("RI.PA")] == [a, b]

    def test_add_rejects_empty_label(self):
        with pytest.raises(ValueError, match="vide"):
            checkpoints.add_checkpoint("RI.PA", "   ")

    def test_add_rejects_non_string_label(self):
        with pytest.raises(ValueError, match="requis"):
            checkpoints.add_checkpoint("RI.PA", None)

    def test_add_rejects_long_label(self):
        too_long = "x" * (config.CHECKPOINT_LABEL_MAX + 1)
        with pytest.raises(ValueError, match="trop long"):
            checkpoints.add_checkpoint("RI.PA", too_long)

    def test_add_accepts_label_at_the_bound(self):
        at_max = "x" * config.CHECKPOINT_LABEL_MAX
        cid = checkpoints.add_checkpoint("RI.PA", at_max)
        assert cache.get_checkpoint(cid)["label"] == at_max

    def test_add_strips_and_uppercases_ticker(self):
        checkpoints.add_checkpoint("  ri.pa ", "  Marge  ")
        row = checkpoints.list_checkpoints("RI.PA")[0]
        assert row["label"] == "Marge"

    def test_add_rejects_empty_ticker(self):
        with pytest.raises(ValueError, match="ticker"):
            checkpoints.add_checkpoint("  ", "A")

    def test_cap_per_ref(self):
        for i in range(config.CHECKPOINT_MAX_PER_REF):
            checkpoints.add_checkpoint("RI.PA", f"point {i}")
        with pytest.raises(ValueError, match="Trop de points"):
            checkpoints.add_checkpoint("RI.PA", "de trop")
        # Le cap est PAR ticker : un autre titre reste libre.
        assert checkpoints.add_checkpoint("MC.PA", "ok") > 0

    def test_update_done_must_be_bool(self):
        cid = checkpoints.add_checkpoint("RI.PA", "A")
        with pytest.raises(ValueError, match="booléen"):
            checkpoints.update_checkpoint(cid, "A", "false")
        # `None` est toléré (PUT sans état explicite) et vaut « non coché ».
        checkpoints.update_checkpoint(cid, "A", None)
        assert cache.get_checkpoint(cid)["done"] is False

    def test_delete_unknown_raises(self):
        with pytest.raises(ValueError, match="inconnu"):
            checkpoints.delete_checkpoint(424242)


class TestCheckpointsMigration:
    """#21 — la migration 4 -> 5 crée la table et son index."""

    def test_table_created_at_current_version(self):
        conn = cache._conn()
        try:
            assert cache._read_user_version(conn) == config.SCHEMA_VERSION
            assert config.SCHEMA_VERSION >= 5
            names = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            assert "checkpoints" in names
        finally:
            conn.close()

    def test_index_created(self):
        conn = cache._conn()
        try:
            indexes = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
            }
            assert "idx_checkpoints_ref" in indexes
        finally:
            conn.close()

    def test_migration_is_idempotent(self):
        cache._conn().close()
        conn = cache._conn()  # deuxième ouverture : aucune migration à rejouer
        try:
            conn.execute(cache._CHECKPOINTS_SCHEMA)
            conn.execute(cache._CREATE_CHECKPOINTS_INDEX)
        finally:
            conn.close()

    def test_v4_db_gains_table_without_data_loss(self):
        # Base construite jusqu'à v4 : on insère une donnée, puis on migre.
        conn = sqlite3.connect(config.CACHE_DB)
        try:
            for version in (0, 1, 2, 3):
                cache.MIGRATIONS[version](conn)
            conn.execute(
                "INSERT INTO events (ref, event_date, label, description, created_at)"
                " VALUES ('RI.PA','2020-01-01','Ancien',NULL,1.0)"
            )
            cache._write_user_version(conn, 4)
            conn.commit()
            assert cache._read_user_version(conn) == 4
        finally:
            conn.close()

        conn = cache._conn()
        try:
            assert cache._read_user_version(conn) == config.SCHEMA_VERSION
            names = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            assert "checkpoints" in names
            assert conn.execute("SELECT label FROM events").fetchone()[0] == "Ancien"
        finally:
            conn.close()


class TestCheckpointsApi:
    @pytest.fixture(autouse=True)
    def _client(self):
        from obole.api.app import app

        self._client = TestClient(app)
        yield self._client

    def test_get_empty_returns_empty_list_not_404(self):
        r = self._client.get("/api/checkpoints/RI.PA")
        assert r.status_code == 200
        assert r.json() == []

    def test_post_get_roundtrip(self):
        r = self._client.post("/api/checkpoints/RI.PA", json={"label": "Marge > 28%"})
        assert r.status_code == 200
        cid = r.json()["id"]

        listed = self._client.get("/api/checkpoints/RI.PA").json()
        assert len(listed) == 1
        assert listed[0] == {"id": cid, "label": "Marge > 28%", "done": False}

    def test_post_422_on_empty_label(self):
        r = self._client.post("/api/checkpoints/RI.PA", json={"label": ""})
        assert r.status_code == 422

    def test_post_422_on_long_label(self):
        r = self._client.post(
            "/api/checkpoints/RI.PA", json={"label": "x" * (config.CHECKPOINT_LABEL_MAX + 1)}
        )
        assert r.status_code == 422
        assert "trop long" in r.json()["detail"]

    def test_put_toggles_done(self):
        cid = self._client.post("/api/checkpoints/RI.PA", json={"label": "A"}).json()["id"]
        r = self._client.put(f"/api/checkpoints/{cid}", json={"label": "A", "done": True})
        assert r.status_code == 200
        assert self._client.get("/api/checkpoints/RI.PA").json()[0]["done"] is True

    def test_put_404_on_unknown(self):
        r = self._client.put("/api/checkpoints/424242", json={"label": "X", "done": False})
        assert r.status_code == 404

    def test_put_422_on_invalid_label(self):
        cid = self._client.post("/api/checkpoints/RI.PA", json={"label": "A"}).json()["id"]
        r = self._client.put(f"/api/checkpoints/{cid}", json={"label": "  ", "done": False})
        assert r.status_code == 422

    def test_delete_roundtrip(self):
        cid = self._client.post("/api/checkpoints/RI.PA", json={"label": "A"}).json()["id"]
        r = self._client.delete(f"/api/checkpoints/{cid}")
        assert r.status_code == 200
        assert self._client.get("/api/checkpoints/RI.PA").json() == []

    def test_delete_404_on_unknown(self):
        assert self._client.delete("/api/checkpoints/424242").status_code == 404
