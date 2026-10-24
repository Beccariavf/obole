"""Watchlist (#25) — routes REST, sans réseau.

Le cache est isolé sur une base temporaire. Les prix sont fournis par la fixture
`_make_prices` (même série synthétique que test_analysis/test_api) : aucun appel
yfinance, aucun scan réel.
"""

from __future__ import annotations

import tempfile
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from tests.test_analysis import _fake_identity, _make_prices

from obole import config
from obole.data import cache
from obole.models import WatchlistRow, WatchlistRun


@pytest.fixture(autouse=True)
def _isolated_db():
    _orig = config.CACHE_DB
    config.CACHE_DB = tempfile.mktemp(suffix=".sqlite")
    yield
    config.CACHE_DB = _orig


@pytest.fixture
def client():
    from obole.api.app import app

    return TestClient(app)


class TestStateRoutes:
    def test_empty_state(self, client):
        data = client.get("/api/watchlist").json()
        assert [t["id"] for t in data["tiers"]] == [1, 2, 3]
        assert data["items"] == []
        assert data["refs"] == {}

    def test_add_move_remove(self, client):
        r = client.put("/api/watchlist/items/ri.pa", json={"tier": 1})
        assert r.status_code == 200, r.text
        assert r.json()["item"]["ticker"] == "RI.PA"
        assert r.json()["item"]["tier"] == 1

        r = client.put("/api/watchlist/items/RI.PA", json={"tier": 3})
        assert r.status_code == 200
        assert r.json()["item"]["tier"] == 3

        assert client.get("/api/watchlist").json()["items"][0]["tier"] == 3

        r = client.delete("/api/watchlist/items/RI.PA")
        assert r.status_code == 200
        assert r.json()["removed"] is True
        assert client.delete("/api/watchlist/items/RI.PA").json()["removed"] is False

    @pytest.mark.parametrize("tier", [0, 4, "x", None, True])
    def test_invalid_tier_422(self, client, tier):
        r = client.put("/api/watchlist/items/RI.PA", json={"tier": tier})
        assert r.status_code == 422

    def test_invalid_ticker_422(self, client):
        r = client.put("/api/watchlist/items/bad%20ticker", json={"tier": 1})
        assert r.status_code == 422


class TestRefRoutes:
    def test_put_ref_saves_and_returns_stats(self, client):
        prices = _make_prices(length=3000)
        start = prices.raw.index[1000].date().isoformat()
        with patch("obole.services.watchlist.yahoo.fetch_prices", return_value=prices):
            r = client.put("/api/watchlist/ref/RI.PA", json={"start": start})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ref"] == {"start": start}
        assert body["stats"] is not None
        assert cache.get_ticker_ref("RI.PA") == start
        assert client.get("/api/watchlist").json()["refs"] == {"RI.PA": start}

    def test_put_ref_too_short_422(self, client):
        prices = _make_prices(length=3000)
        with patch("obole.services.watchlist.yahoo.fetch_prices", return_value=prices):
            r = client.put(
                "/api/watchlist/ref/RI.PA",
                json={"start": prices.raw.index[-5].date().isoformat()},
            )
        assert r.status_code == 422
        assert cache.get_ticker_ref("RI.PA") is None

    @pytest.mark.parametrize("start", ["", "2012-1-4", "2999-01-01", None, 42])
    def test_put_ref_invalid_date_422(self, client, start):
        r = client.put("/api/watchlist/ref/RI.PA", json={"start": start})
        assert r.status_code == 422

    def test_delete_ref(self, client):
        cache.set_ticker_ref("RI.PA", "2012-01-04")
        r = client.delete("/api/watchlist/ref/RI.PA")
        assert r.status_code == 200
        assert r.json() == {"ref": None}
        assert cache.get_ticker_ref("RI.PA") is None


class TestRunRoute:
    def _run(self):
        return WatchlistRun(
            generated_at=1.0,
            rows=[
                WatchlistRow(
                    ticker="RI.PA",
                    tier=1,
                    name="Pernod",
                    price=100.0,
                    fair_price=120.0,
                    fair_price_source="saved",
                    target_yield=12.0,
                    safety_margin_pct=16.67,
                    margin_good=True,
                    ref_start="2005-01-03",
                    ref_is_default=False,
                    z=-1.2,
                    ecart_type_pct=25.0,
                    trend_gap_pct=10.0,
                    warnings=[],
                ),
                WatchlistRow(ticker="AI.PA", tier=2, error="Ticker introuvable"),
            ],
        )

    def test_returns_full_rows_and_count(self, client):
        with patch("obole.services.watchlist.run", return_value=self._run()):
            r = client.post("/api/watchlist/run", json={})
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 2
        assert [row["ticker"] for row in body["rows"]] == ["RI.PA", "AI.PA"]
        assert body["rows"][0]["fair_price_source"] == "saved"
        assert "warnings" in body["rows"][0]  # view plein = ligne complète
        assert body["rows"][1]["error"] == "Ticker introuvable"

    def test_max_rows_bounds_without_changing_count(self, client):
        with patch("obole.services.watchlist.run", return_value=self._run()):
            body = client.post("/api/watchlist/run", json={"max_rows": 1}).json()
        assert body["count"] == 2
        assert len(body["rows"]) == 1

    def test_tier_filter_is_validated_and_forwarded(self, client):
        with patch("obole.services.watchlist.run", return_value=self._run()) as run:
            r = client.post("/api/watchlist/run", json={"tier": 2})
        assert r.status_code == 200
        run.assert_called_once_with(tier=2)

    def test_invalid_tier_422(self, client):
        assert client.post("/api/watchlist/run", json={"tier": 9}).status_code == 422


class TestStockPayload:
    def _get_stock(self, client):
        prices = _make_prices(length=3000)
        with (
            patch("obole.services.analysis.yahoo.fetch_prices", return_value=prices),
            patch("obole.services.analysis.yahoo.fetch_identity", side_effect=_fake_identity),
            patch("obole.services.analysis.yahoo.fetch_fundamentals", return_value=None),
        ):
            return client.get("/api/stock/FAKE"), prices

    def test_watch_block_is_added(self, client):
        cache.upsert_watch_item("FAKE", 2)
        prices = _make_prices(length=3000)
        cache.set_ticker_ref("FAKE", prices.raw.index[1000].date().isoformat())
        r, _ = self._get_stock(client)
        assert r.status_code == 200, r.text
        watch = r.json()["watch"]
        assert watch["tier"] == 2
        assert watch["ref"] == {"start": prices.raw.index[1000].date().isoformat()}
        assert watch["ref_stats"] is not None
        assert set(watch["ref_stats"]) >= {"line", "z", "ecart_type_pct", "trend_gap_pct"}

    def test_watch_block_empty_when_not_followed(self, client):
        r, _ = self._get_stock(client)
        assert r.json()["watch"] == {"tier": None, "ref": None, "ref_stats": None}


def test_meta_exposes_watch_contract(client):
    watch = client.get("/api/meta").json()["watch"]
    assert [t["id"] for t in watch["tiers"]] == [1, 2, 3]
    assert watch["min_ref_points"] == config.REGRESSION_MIN_POINTS
    assert watch["max_items"] == config.WATCHLIST_MAX_ITEMS
