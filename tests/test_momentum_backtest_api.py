"""Tests API du backtest de fiabilité — TestClient, sans réseau."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from tests.test_analysis import _make_prices

from obole.api.app import app
from obole.data.yahoo import TickerNotFound
from obole.services.indices import IndexNotFound

MEASURES = {
    "cagr_pct",
    "volatility_pct",
    "sharpe",
    "sortino",
    "max_drawdown_pct",
    "calmar",
    "invested_pct",
    "trades",
}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def prices():
    return _make_prices(800)


def _bounds(prices) -> tuple[str, str]:
    return (
        prices.raw.index[0].strftime("%Y-%m-%d"),
        prices.raw.index[-1].strftime("%Y-%m-%d"),
    )


def _get_stock(client: TestClient, prices, series: str = "raw"):
    start, end = _bounds(prices)
    with patch("obole.services.momentum.yahoo.fetch_prices", return_value=prices):
        return client.get(
            f"/api/stock/FAKE/momentum-backtest?start={start}&end={end}&series={series}"
        )


class TestStockBacktest:
    def test_200_carries_both_columns(self, client, prices):
        resp = _get_stock(client, prices)
        assert resp.status_code == 200
        data = resp.json()
        for column in ("buy_hold", "strategy"):
            assert set(data[column]) == MEASURES  # ni equity ni positions
        assert set(data) == {"buy_hold", "strategy", "window"}
        assert data["window"]["sessions"] == 800
        assert data["window"]["start"] == prices.raw.index[0].strftime("%Y-%m-%d")
        assert data["window"]["end"] == prices.raw.index[-1].strftime("%Y-%m-%d")

    def test_404_on_unknown_ticker(self, client, prices):
        start, end = _bounds(prices)
        with patch(
            "obole.services.momentum.yahoo.fetch_prices", side_effect=TickerNotFound("UNKNOWN")
        ):
            resp = client.get(
                f"/api/stock/UNKNOWN/momentum-backtest?start={start}&end={end}&series=raw"
            )
        assert resp.status_code == 404
        assert "introuvable" in resp.json()["detail"].lower()

    def test_tz_aware_index_from_yfinance(self, client, prices):
        """yfinance renvoie un index tz-aware : les bornes ISO naïves doivent passer."""
        from obole.models import PriceSeries

        aware = PriceSeries(
            raw=prices.raw.copy(), adjusted=prices.adjusted.copy(), fetched_at=prices.fetched_at
        )
        aware.raw.index = aware.raw.index.tz_localize("Europe/Paris")
        aware.adjusted.index = aware.adjusted.index.tz_localize("Europe/Paris")
        resp = _get_stock(client, aware)
        assert resp.status_code == 200
        assert resp.json()["window"]["sessions"] == 800


class TestIndexBacktest:
    def test_200_uses_the_synthetic_series(self, client, prices):
        start, end = _bounds(prices)
        with (
            patch(
                "obole.services.momentum.indices_service.analyze_index",
                return_value=(None, prices.adjusted),
            ),
            patch(
                "obole.services.momentum.yahoo.fetch_prices",
                side_effect=AssertionError("aucun appel ticker pour un indice"),
            ),
        ):
            resp = client.get(f"/api/index/7/momentum-backtest?start={start}&end={end}&series=raw")
        assert resp.status_code == 200
        data = resp.json()
        assert data["window"]["sessions"] == 800
        assert MEASURES <= set(data["strategy"])

    def test_404_on_unknown_index(self, client, prices):
        start, end = _bounds(prices)
        with patch(
            "obole.services.momentum.indices_service.analyze_index",
            side_effect=IndexNotFound("Indice 999 introuvable"),
        ):
            resp = client.get(
                f"/api/index/999/momentum-backtest?start={start}&end={end}&series=raw"
            )
        assert resp.status_code == 404


class TestValidation:
    def test_reversed_dates_are_rejected(self, client, prices):
        start, end = _bounds(prices)
        resp = client.get(f"/api/stock/FAKE/momentum-backtest?start={end}&end={start}")
        assert resp.status_code == 422

    def test_unknown_series_is_rejected(self, client, prices):
        start, end = _bounds(prices)
        resp = client.get(f"/api/stock/FAKE/momentum-backtest?start={start}&end={end}&series=bogus")
        assert resp.status_code == 422

    def test_bad_iso_date_is_rejected(self, client, prices):
        _, end = _bounds(prices)
        resp = client.get(f"/api/stock/FAKE/momentum-backtest?start=2020-13-01&end={end}")
        assert resp.status_code == 422

    def test_one_session_window_is_rejected(self, client, prices):
        # Du vendredi au samedi : une seule séance dans la fenêtre.
        friday = prices.raw.index[4].strftime("%Y-%m-%d")
        saturday = (prices.raw.index[4] + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        with patch("obole.services.momentum.yahoo.fetch_prices", return_value=prices):
            resp = client.get(
                f"/api/stock/FAKE/momentum-backtest?start={friday}&end={saturday}&series=raw"
            )
        assert resp.status_code == 422
        assert "courte" in resp.json()["detail"].lower()
