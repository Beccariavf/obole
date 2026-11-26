"""Payload `chart.risk` de la section « Risque & dynamique » (#33).

Hors réseau : les prix (titre, panier et benchmark `^FCHI`) sont synthétiques.
On vérifie l'alignement sur la grille décimée, les mesures calculées en pleine
résolution, le 12-1 sur cours bruts, et la dégradation silencieuse quand le
benchmark est indisponible.
"""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from tests.test_analysis import _fake_identity, _make_prices

from obole.data.yahoo import TickerNotFound
from obole.engine import risk
from obole.models import PriceSeries
from obole.services import analysis as analysis_service
from obole.services import serialize


def _price_series(raw: pd.Series, adj: pd.Series) -> PriceSeries:
    return PriceSeries(
        raw=raw,
        adjusted=adj,
        fetched_at=pd.Timestamp("today").date(),
    )


def _synthetic_prices(periods: int = 800) -> PriceSeries:
    """Cours synthétique : ajustée en baisse régulière, brute au momentum connu."""
    idx = pd.bdate_range("2015-01-05", periods=periods)
    adj = pd.Series(np.linspace(200.0, 100.0, periods), index=idx)
    raw = pd.Series(100.0, index=idx)
    # 12-1 attendu : P[-1-21] / P[-1-252] - 1 = 110 / 100 - 1 = +10 %.
    raw.iloc[-1 - 21] = 110.0
    raw.iloc[-1 - 252] = 100.0
    return _price_series(raw, adj)


def _synthetic_benchmark(periods: int = 900) -> PriceSeries:
    """Benchmark simulé : volatilité et 12-1 calculables, valeurs distinctes."""
    idx = pd.bdate_range("2014-01-06", periods=periods)
    adj = pd.Series(np.linspace(50.0, 65.0, periods), index=idx)
    raw = pd.Series(120.0, index=idx)
    raw.iloc[-1 - 21] = 126.0
    raw.iloc[-1 - 252] = 120.0
    return _price_series(raw, adj)


class TestRiskChartPayload:
    def test_series_are_aligned_on_the_decimated_course_grid(self):
        prices = _synthetic_prices()
        payload = serialize.chart_payload(prices, benchmark=_synthetic_benchmark())

        risk_payload = payload["risk"]
        assert set(risk_payload) == {"drawdown_pct", "vol_pct", "vol_threshold_pct", "now"}
        assert len(risk_payload["drawdown_pct"]) == len(payload["dates"])
        assert len(risk_payload["vol_pct"]) == len(payload["dates"])

    def test_full_resolution_measures_are_then_decimated(self):
        prices = _synthetic_prices()
        payload = serialize.chart_payload(prices)
        grid = serialize._downsample(prices.raw).index

        expected_dd = risk.drawdown_series(prices.adjusted).reindex(grid)
        expected_vol = risk.realized_vol_series(prices.adjusted).reindex(grid)
        got = payload["risk"]
        assert got["drawdown_pct"] == serialize._vals(expected_dd)
        assert got["vol_pct"] == serialize._vals(expected_vol)

    def test_now_scalars_and_benchmark(self):
        prices = _synthetic_prices()
        bench = _synthetic_benchmark()
        now = serialize.chart_payload(prices, benchmark=bench)["risk"]["now"]

        assert set(now) == {
            "drawdown_pct",
            "peak_date",
            "vol_pct",
            "vol_percentile",
            "bench_vol_pct",
            "mom_12_1_pct",
            "bench_mom_12_1_pct",
        }
        # Chute depuis le plus haut : 200 -> 100 = -50 %.
        assert now["drawdown_pct"] == pytest.approx(-50.0, abs=0.01)
        assert now["peak_date"] == prices.adjusted.index[0].date().isoformat()
        # 12-1 sur cours BRUTS (le brut synthétique porte +10 %).
        assert now["mom_12_1_pct"] == pytest.approx(10.0, abs=0.01)
        # Benchmark : volatilité sur l'ajustée (dernière valeur pleine résolution).
        expected_bench_vol = round(float(risk.realized_vol_series(bench.adjusted).iloc[-1]), 2)
        assert now["bench_vol_pct"] == pytest.approx(expected_bench_vol)
        assert now["bench_mom_12_1_pct"] == pytest.approx(5.0, abs=0.01)

    def test_threshold_is_the_anomaly_quantile_of_the_full_vol_series(self):
        prices = _synthetic_prices()
        payload = serialize.chart_payload(prices)
        expected = risk.quantile_threshold(risk.realized_vol_series(prices.adjusted))
        assert payload["risk"]["vol_threshold_pct"] == pytest.approx(round(expected, 2))

    def test_benchmark_unavailable_leaves_bench_fields_none(self):
        prices = _synthetic_prices()
        now = serialize.chart_payload(prices, benchmark=None)["risk"]["now"]
        assert now["bench_vol_pct"] is None
        assert now["bench_mom_12_1_pct"] is None
        # Les mesures du titre restent calculées : aucune exception.
        assert now["drawdown_pct"] is not None
        assert now["mom_12_1_pct"] is not None

    def test_short_history_yields_none_not_an_exception(self):
        idx = pd.bdate_range("2024-01-01", periods=30)
        prices = _price_series(
            pd.Series(np.linspace(100.0, 90.0, 30), index=idx),
            pd.Series(np.linspace(100.0, 90.0, 30), index=idx),
        )
        now = serialize.chart_payload(prices)["risk"]["now"]
        assert now["drawdown_pct"] == pytest.approx(-10.0, abs=0.01)
        assert now["vol_pct"] is None
        assert now["vol_percentile"] is None
        assert now["mom_12_1_pct"] is None

    def test_basket_payload_carries_its_risk_block(self):
        prices = _synthetic_prices()
        raw = pd.Series(100.0, index=prices.adjusted.index)
        # 12-1 brut connu (+20 %), distinct de la série ajustée total-return.
        raw.iloc[-1 - 21] = 120.0
        raw.iloc[-1 - 252] = 100.0
        payload = serialize.basket_chart_payload(
            prices.adjusted, benchmark=_synthetic_benchmark(), raw_series=raw
        )
        assert len(payload["risk"]["drawdown_pct"]) == len(payload["dates"])
        assert payload["risk"]["now"]["bench_vol_pct"] is not None
        assert payload["risk"]["now"]["mom_12_1_pct"] == pytest.approx(20.0, abs=0.01)

    def test_basket_momentum_uses_the_raw_chain_not_total_return(self):
        idx = pd.bdate_range("2015-01-05", periods=800)
        members = {
            "A": _price_series(
                pd.Series(np.linspace(100.0, 120.0, 800), index=idx),
                pd.Series(np.linspace(100.0, 150.0, 800), index=idx),
            ),
            "B": _price_series(
                pd.Series(np.linspace(50.0, 55.0, 800), index=idx),
                pd.Series(np.linspace(50.0, 70.0, 800), index=idx),
            ),
        }
        with (
            patch("obole.services.analysis.yahoo.fetch_identity", side_effect=_fake_identity),
            patch("obole.services.analysis.cache.get", return_value=None),
            patch("obole.services.analysis.cache.put"),
        ):
            analysis, series = analysis_service.analyze_basket(1, "Panier", "Test", members)

        assert analysis.raw_series is not None
        payload = serialize.basket_to_dict(analysis, series)
        now = payload["chart"]["risk"]["now"]
        expected_raw = round(float(risk.momentum_12_1(analysis.raw_series)), 2)
        expected_total_return = round(float(risk.momentum_12_1(series)), 2)
        assert now["mom_12_1_pct"] == pytest.approx(expected_raw)
        assert now["mom_12_1_pct"] != pytest.approx(expected_total_return)

    def test_absent_when_chart_is_excluded(self):
        prices = _make_prices()
        with (
            patch("obole.services.analysis.yahoo.fetch_prices", return_value=prices),
            patch("obole.services.analysis.yahoo.fetch_identity", side_effect=_fake_identity),
            patch("obole.services.analysis.yahoo.fetch_fundamentals", return_value=None),
        ):
            analysis, fetched = analysis_service.analyze_ticker("FAKE")
        payload = serialize.analysis_to_dict(analysis, fetched, include_chart=False)
        assert "chart" not in payload


class TestBenchmarkRead:
    def test_benchmark_is_read_once_via_the_data_layer(self):
        bench = _synthetic_benchmark()
        with patch("obole.services.analysis.yahoo.fetch_prices", return_value=bench) as mocked:
            assert analysis_service.benchmark_prices() is bench
        mocked.assert_called_once()

    def test_unavailable_benchmark_is_none(self):
        with patch(
            "obole.services.analysis.yahoo.fetch_prices",
            side_effect=TickerNotFound("^FCHI"),
        ):
            assert analysis_service.benchmark_prices() is None
