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

# Les sept mesures de chaque colonne (in, out, buy & hold). `trades` ne vit plus
# dans une colonne : il sort une fois, au premier niveau.
MEASURES = {
    "cagr_pct",
    "volatility_pct",
    "sharpe",
    "sortino",
    "max_drawdown_pct",
    "calmar",
    "sessions_pct",
}
COLUMNS = ("buy_hold", "in", "out")
TOP_LEVEL = {"buy_hold", "in", "out", "window", "trades", "strategy_cagr_pct"}


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
    def test_200_carries_the_six_payload_entries(self, client, prices):
        resp = _get_stock(client, prices)
        assert resp.status_code == 200
        data = resp.json()
        # Six clés de premier niveau : trois colonnes, la fenêtre, les trades et
        # le CAGR de la stratégie. Rien de plus.
        assert set(data) == TOP_LEVEL
        for column in COLUMNS:
            assert set(data[column]) == MEASURES  # ni equity ni positions
        assert isinstance(data["trades"], int)
        assert data["trades"] >= 0
        assert "strategy_cagr_pct" in data
        assert data["window"]["sessions"] == 800
        assert data["window"]["start"] == prices.raw.index[0].strftime("%Y-%m-%d")
        assert data["window"]["end"] == prices.raw.index[-1].strftime("%Y-%m-%d")

    def test_no_equity_positions_or_strategy_leaks(self, client, prices):
        body = _get_stock(client, prices).text
        for forbidden in ('"strategy"', '"equity"', '"positions"'):
            assert forbidden not in body
        assert "strategy_cagr_pct" in body  # le seul « strategy » restant

    def test_in_and_out_shares_sum_to_hundred(self, client, prices):
        data = _get_stock(client, prices).json()
        in_pct = data["in"]["sessions_pct"]
        out_pct = data["out"]["sessions_pct"]
        assert in_pct + out_pct == pytest.approx(100.0, abs=1e-6)
        assert data["buy_hold"]["sessions_pct"] == 100.0

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
        assert set(data) == TOP_LEVEL
        for column in COLUMNS:
            assert MEASURES <= set(data[column])

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


class TestEmptyBucket:
    def test_fully_invested_window_has_an_empty_out_bucket(self, client, prices):
        """Aucune séance dehors : out à mesures nulles, part 0 %, pas d'erreur."""
        scores = pd.Series(0.9, index=prices.raw.index)
        start, end = _bounds(prices)
        with (
            patch("obole.services.momentum.yahoo.fetch_prices", return_value=prices),
            patch("obole.services.momentum.cv.satisfaction_series", return_value=scores),
        ):
            resp = client.get(
                f"/api/stock/FAKE/momentum-backtest?start={start}&end={end}&series=raw"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["in"]["sessions_pct"] == 100.0
        assert data["out"]["sessions_pct"] == 0.0
        for key in MEASURES - {"sessions_pct"}:
            assert data["out"][key] is None
        # La colonne in reste mesurable : la table a bien trois colonnes remplies.
        assert data["in"]["cagr_pct"] is not None


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
