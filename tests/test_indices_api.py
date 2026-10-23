"""Tests API des indices personnalisés — TestClient, sans réseau.

Les définitions sont persistées dans le vrai cache.sqlite (pattern test_manual) :
chaque test crée une catégorie au nom unique et la supprime en teardown.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from tests.test_analysis import _fake_identity, _make_prices

from obole.api.app import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def category(client):
    name = f"Cat {time.time_ns()}"
    resp = client.post("/api/indices/categories", json={"name": name})
    assert resp.status_code == 200
    cat_id = resp.json()["id"]
    yield cat_id
    client.delete(f"/api/indices/categories/{cat_id}")


def _create_index(client, category_id, name="CAC Tech", tickers=("A.PA", "B.PA")):
    resp = client.post(
        "/api/indices",
        json={"category_id": category_id, "name": name, "tickers": list(tickers)},
    )
    assert resp.status_code == 200
    return resp.json()["id"]


@pytest.fixture
def hermetic_cache(monkeypatch):
    """Aucune série synthétique de test ne persiste dans le vrai cache.

    La série chaînée est recalculée à chaque appel (cache.get -> None) et ne
    transite jamais vers le disque (cache.put no-op) : la base réelle reste
    propre, sinon les clés `INDEX:*` seraient polluées par des séries factices.
    """
    monkeypatch.setattr("obole.services.analysis.cache.put", lambda *a, **k: None)
    monkeypatch.setattr("obole.services.analysis.cache.get", lambda *a, **k: None)


class TestIndicesCrud:
    def test_create_category_and_list(self, client, category):
        resp = client.get("/api/indices")
        assert resp.status_code == 200
        cats = resp.json()
        assert any(c["id"] == category for c in cats)

    def test_empty_category_name_422(self, client):
        resp = client.post("/api/indices/categories", json={"name": "  "})
        assert resp.status_code == 422

    def test_duplicate_category_422(self, client):
        name = f"Dup {time.time_ns()}"
        assert client.post("/api/indices/categories", json={"name": name}).status_code == 200
        resp = client.post("/api/indices/categories", json={"name": name})
        assert resp.status_code == 422
        assert "déjà existante" in resp.json()["detail"]
        # Nettoyage : ne pas laisser de catégorie de test dans la base réelle.
        cat_id = next(c["id"] for c in client.get("/api/indices").json() if c["name"] == name)
        assert client.delete(f"/api/indices/categories/{cat_id}").status_code == 200

    def test_create_index_and_list_members(self, client, category):
        idx_id = _create_index(client, category)
        resp = client.get("/api/indices")
        cat = next(c for c in resp.json() if c["id"] == category)
        assert [i["id"] for i in cat["indices"]] == [idx_id]
        assert cat["indices"][0]["tickers"] == ["A.PA", "B.PA"]

    def test_create_index_requires_two_members(self, client, category):
        resp = client.post(
            "/api/indices", json={"category_id": category, "name": "Solo", "tickers": ["A.PA"]}
        )
        assert resp.status_code == 422
        assert "2 membres" in resp.json()["detail"]

    def test_create_index_unknown_category_422(self, client):
        resp = client.post(
            "/api/indices",
            json={"category_id": 999999, "name": "X", "tickers": ["A.PA", "B.PA"]},
        )
        assert resp.status_code == 422

    def test_put_index_updates(self, client, category):
        idx_id = _create_index(client, category)
        resp = client.put(
            f"/api/indices/{idx_id}",
            json={"category_id": category, "name": "Renommé", "tickers": ["C.PA", "D.PA"]},
        )
        assert resp.status_code == 200
        cat = next(c for c in client.get("/api/indices").json() if c["id"] == category)
        ix = next(i for i in cat["indices"] if i["id"] == idx_id)
        assert ix["name"] == "Renommé"
        assert ix["tickers"] == ["C.PA", "D.PA"]

    def test_delete_index(self, client, category):
        idx_id = _create_index(client, category)
        resp = client.delete(f"/api/indices/{idx_id}")
        assert resp.status_code == 200
        cat = next(c for c in client.get("/api/indices").json() if c["id"] == category)
        assert cat["indices"] == []

    def test_delete_category_cascades(self, client):
        name = f"Cat {time.time_ns()}"
        cat_id = client.post("/api/indices/categories", json={"name": name}).json()["id"]
        idx_id = _create_index(client, cat_id)
        resp = client.delete(f"/api/indices/categories/{cat_id}")
        assert resp.status_code == 200
        # l'indice n'est plus listable (cascade) ni analysable
        assert client.get(f"/api/index/{idx_id}").status_code == 404

    def test_delete_unknown_404(self, client):
        assert client.delete("/api/indices/999999").status_code == 404
        assert client.delete("/api/indices/categories/999999").status_code == 404


class TestBasketAnalysis:
    def test_get_index_200(self, client, category, hermetic_cache):
        idx_id = _create_index(client, category, tickers=("A.PA", "B.PA"))

        with (
            patch("obole.data.yahoo.fetch_prices", return_value=_make_prices(seed=1)),
            patch("obole.services.analysis.yahoo.fetch_identity", side_effect=_fake_identity),
        ):
            resp = client.get(f"/api/index/{idx_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["kind_payload"] == "basket"
        assert data["identity"]["name"] == "CAC Tech"
        assert data["identity"]["category"].startswith("Cat")
        assert data["identity"]["index_id"] == idx_id
        assert len(data["identity"]["members"]) == 2
        m = data["identity"]["members"][0]
        assert m["ticker"] == "A.PA"
        # Stats « coup d'œil » du membre sérialisées (position σ, pente, tendance).
        assert set(m) == {"ticker", "name", "distance_sigma", "pente", "trend"}
        assert m["distance_sigma"]["value"] is not None
        assert m["pente"]["label"] is not None
        assert m["trend"]["label"] is not None
        assert "distance_sigma" in data["indicators"]
        assert data["indicators"]["trend"]["label"] is not None  # 5A — tendance calculée
        assert data["chart"]["price_raw"] == data["chart"]["price_adj"]
        assert data["fundamentals"] is None
        assert "regression" in data

    def test_404_unknown_index(self, client):
        resp = client.get("/api/index/999999")
        assert resp.status_code == 404

    def test_422_unknown_member_ticker(self, client, category):
        idx_id = _create_index(client, category, tickers=("A.PA", "B.PA"))
        from obole.data.yahoo import TickerNotFound

        with patch("obole.data.yahoo.fetch_prices", side_effect=TickerNotFound("A.PA")):
            resp = client.get(f"/api/index/{idx_id}")
        assert resp.status_code == 404

    def test_refresh_index_purges_members(self, client, category):
        idx_id = _create_index(client, category, tickers=("A.PA", "B.PA"))
        with patch("obole.data.yahoo.refresh") as mock_refresh:
            resp = client.post(f"/api/index/{idx_id}/refresh")
        assert resp.status_code == 200
        assert mock_refresh.call_count == 2  # un purge par membre

    def test_refresh_unknown_index_404(self, client):
        resp = client.post("/api/index/999999/refresh")
        assert resp.status_code == 404


class TestIndicesSummary:
    """Résumé « Mes indices » : stats à la volée + refresh scopé par catégorie."""

    def test_get_summary_returns_stats(self, client, category, hermetic_cache):
        idx_id = _create_index(client, category)

        with (
            patch("obole.data.yahoo.fetch_prices", return_value=_make_prices(seed=2)),
        ):
            resp = client.get("/api/indices/summary")

        assert resp.status_code == 200
        entry = next(e for e in resp.json() if e["index_id"] == idx_id)
        assert entry["error"] is None
        st = entry["stats"]
        assert set(st) == {"distance_sigma", "pente", "trend"}
        assert st["distance_sigma"]["value"] is not None
        assert st["distance_sigma"]["label"] is not None
        assert st["pente"]["value"] is not None
        assert st["trend"]["label"] is not None

    def test_summary_shape_on_real_db(self, client, hermetic_cache):
        # La base SQLite persiste entre les sessions : des indices peuvent déjà
        # exister. On vérifie la forme de la réponse, pas le contenu exhaustif.
        with (
            patch("obole.data.yahoo.fetch_prices", return_value=_make_prices(seed=2)),
        ):
            resp = client.get("/api/indices/summary")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        for e in resp.json():
            assert set(e) == {"index_id", "error", "stats"}

    def test_refresh_scoped_to_category(self, client, category, hermetic_cache):
        idx_cat1 = _create_index(client, category, name="Groupe A")
        other_name = f"Cat {time.time_ns()}"
        other_id = client.post("/api/indices/categories", json={"name": other_name}).json()["id"]
        try:
            idx_cat2 = _create_index(client, other_id, name="Groupe B")
            with (
                patch("obole.data.yahoo.refresh") as mock_refresh,
                patch("obole.data.yahoo.fetch_prices", return_value=_make_prices(seed=3)),
            ):
                resp = client.post("/api/indices/summary/refresh", json={"category_id": category})

            assert resp.status_code == 200
            entries = resp.json()
            # Seuls les membres du périmètre (catégorie 1) sont purgés : 2 membres.
            assert mock_refresh.call_count == 2
            # Et seuls les indices de la catégorie 1 sont recalculés.
            assert [e["index_id"] for e in entries] == [idx_cat1]
            assert idx_cat2 not in [e["index_id"] for e in entries]
        finally:
            client.delete(f"/api/indices/categories/{other_id}")

    def test_refresh_all_categories(self, client, category, hermetic_cache):
        idx_id = _create_index(client, category, name="Groupe A")
        with (
            patch("obole.data.yahoo.refresh") as mock_refresh,
            patch("obole.data.yahoo.fetch_prices", return_value=_make_prices(seed=4)),
        ):
            resp = client.post("/api/indices/summary/refresh")
        assert resp.status_code == 200
        entries = {e["index_id"]: e for e in resp.json()}
        assert idx_id in entries
        assert entries[idx_id]["error"] is None
        assert entries[idx_id]["stats"]["pente"]["value"] is not None
        # purge au moins les membres de l'indice créé (2) — la base réelle peut
        # contenir d'autres indices persistés d'une session précédente.
        assert mock_refresh.call_count >= 2

    def test_member_error_isolated(self, client, category, hermetic_cache):
        from obole.data.yahoo import TickerNotFound

        idx_ok = _create_index(client, category, name="Ok", tickers=("A.PA", "B.PA"))
        idx_bad = _create_index(client, category, name="Bad", tickers=("X.PA", "Y.PA"))

        def _fake_prices(ticker):
            if ticker == "X.PA":
                raise TickerNotFound("X.PA")
            return _make_prices(seed=5)

        with (
            patch("obole.data.yahoo.fetch_prices", side_effect=_fake_prices),
        ):
            resp = client.get("/api/indices/summary")

        assert resp.status_code == 200
        entries = {e["index_id"]: e for e in resp.json()}
        assert entries[idx_ok]["error"] is None
        assert entries[idx_ok]["stats"]["pente"]["value"] is not None
        # L'indice dont un membre est introuvable est isolé : stats None + erreur.
        assert entries[idx_bad]["stats"] is None
        assert entries[idx_bad]["error"] == "X.PA"  # TickerNotFound -> str = ticker
