"""Moteur pur du risque et de la dynamique (#33).

Séries déterministes, hors réseau : nettoyage des cours, chute, plus-haut,
volatilité glissante, centile/quantile d'anomalie et momentum 12-1, puis
l'instantané agrégé. La pureté du module est verrouillée en fin de fichier.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from obole.engine import risk


def _dates(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2020-01-01", periods=n, freq="B")


class TestCleanPrices:
    def test_drops_nan_and_non_positive(self):
        idx = _dates(5)
        s = pd.Series([100.0, np.nan, 0.0, -5.0, 110.0], index=idx)
        cleaned = risk.clean_prices(s)
        assert list(cleaned) == [100.0, 110.0]
        assert list(cleaned.index) == [idx[0], idx[4]]

    def test_dedup_keeps_last_and_sorts_index(self):
        idx = pd.DatetimeIndex(["2020-01-03", "2020-01-01", "2020-01-03"])
        cleaned = risk.clean_prices(pd.Series([30.0, 10.0, 31.0], index=idx))
        assert list(cleaned) == [10.0, 31.0]
        assert cleaned.index.is_monotonic_increasing


class TestDrawdownSeries:
    def test_flat_series_is_zero(self):
        s = pd.Series([100.0] * 5, index=_dates(5))
        assert list(risk.drawdown_series(s)) == [0.0] * 5

    def test_increasing_series_is_zero_everywhere(self):
        s = pd.Series([100.0, 101.0, 105.0], index=_dates(3))
        assert list(risk.drawdown_series(s)) == [0.0, 0.0, 0.0]

    def test_known_drawdown(self):
        # Pic 100 -> creux 50 = -50 %, puis 75 = -25 %.
        s = pd.Series([100.0, 50.0, 75.0], index=_dates(3))
        dd = risk.drawdown_series(s)
        assert list(dd) == [0.0, pytest.approx(-50.0), pytest.approx(-25.0)]

    def test_index_is_the_cleaned_index(self):
        idx = _dates(5)
        s = pd.Series([100.0, np.nan, 80.0, 0.0, 90.0], index=idx)
        assert list(risk.drawdown_series(s).index) == [idx[0], idx[2], idx[4]]


class TestPeakDate:
    def test_last_time_the_peak_was_reached(self):
        idx = _dates(5)
        s = pd.Series([100.0, 120.0, 90.0, 120.0, 80.0], index=idx)
        assert risk.peak_date(s) == idx[3]

    def test_empty_series(self):
        assert risk.peak_date(pd.Series(dtype=float)) is None

    def test_numeric_index_is_not_a_date(self):
        # Une position (RangeIndex) n'est pas une date : pas de faux 1970.
        assert risk.peak_date(pd.Series([100.0, 120.0, 80.0])) is None


class TestRealizedVolSeries:
    def test_nan_until_window_is_full(self):
        s = pd.Series([100.0] * 10, index=_dates(10))
        vol = risk.realized_vol_series(s, window=5)
        # Le premier rendement est NaN : la première sortie arrive à l'indice 5.
        assert vol.iloc[:5].isna().all()
        assert vol.iloc[5] == pytest.approx(0.0)

    def test_flat_series_is_zero(self):
        vol = risk.realized_vol_series(pd.Series([100.0] * 10, index=_dates(10)), window=5)
        assert vol.dropna().eq(0.0).all()

    def test_constant_growth_is_zero(self):
        prices = 100.0 * np.power(1.01, np.arange(20))
        s = pd.Series(prices, index=_dates(20))
        vol = risk.realized_vol_series(s, window=5)
        assert float(vol.dropna().abs().max()) <= 1e-9

    def test_known_noise(self):
        rets = np.array([0.01, -0.02, 0.015, -0.005, 0.02, -0.01])
        prices = np.concatenate([[100.0], 100.0 * np.exp(np.cumsum(rets))])
        s = pd.Series(prices, index=_dates(len(prices)))
        vol = risk.realized_vol_series(s, window=len(rets))
        expected = float(np.std(rets, ddof=1)) * math.sqrt(252.0) * 100.0
        assert vol.iloc[-1] == pytest.approx(expected, rel=1e-9)


class TestPercentileOfLast:
    def test_none_below_min_points(self):
        assert risk.percentile_of_last(pd.Series([1.0, 2.0, 3.0]), min_points=4) is None

    def test_exact_on_a_small_series(self):
        # Dernière = 2,5 ; antérieures strictement plus petites : 1 et 2 -> 2/4 = 50 %.
        s = pd.Series([10.0, 1.0, 2.0, 3.0, 2.5])
        assert risk.percentile_of_last(s, min_points=1) == 50.0

    def test_highest_value_is_hundred(self):
        s = pd.Series([1.0, 2.0, 3.0, 4.0])
        assert risk.percentile_of_last(s, min_points=1) == 100.0


class TestQuantileThreshold:
    def test_none_below_min_points(self):
        assert risk.quantile_threshold(pd.Series([1.0, 2.0]), min_points=3) is None

    def test_exact_median(self):
        s = pd.Series([0.0, 10.0, 20.0, 30.0, 40.0])
        assert risk.quantile_threshold(s, pctile=50, min_points=1) == 20.0


class TestMomentum12To1:
    def test_none_on_short_history(self):
        s = pd.Series([100.0] * 200, index=_dates(200))
        assert risk.momentum_12_1(s) is None

    def test_none_when_exactly_one_point_short(self):
        s = pd.Series([100.0] * 252, index=_dates(252))
        assert risk.momentum_12_1(s) is None

    def test_exact_on_a_built_series(self):
        values = np.full(300, 100.0)
        values[-1 - 21] = 110.0  # P[-1-skip]
        s = pd.Series(values, index=_dates(300))
        assert risk.momentum_12_1(s) == pytest.approx(10.0)

    def test_none_when_skip_position_does_not_exist(self):
        # lookback satisfait mais `skip` sort de la série : None, pas d'IndexError.
        s = pd.Series([1.0] * 7, index=_dates(7))
        assert risk.momentum_12_1(s, lookback=5, skip=21) is None


class TestRiskSnapshot:
    def test_short_series_has_all_fields_and_expected_nones(self):
        idx = _dates(30)
        adj = pd.Series(np.linspace(100.0, 90.0, 30), index=idx)
        snap = risk.risk_snapshot(adj, adj.astype(float))
        assert set(snap) == {
            "drawdown_pct",
            "peak_date",
            "vol_pct",
            "vol_percentile",
            "vol_threshold_pct",
            "mom_12_1_pct",
        }
        # Chute et date du pic restent calculables sur 30 séances.
        assert snap["drawdown_pct"] == pytest.approx(-10.0, abs=0.01)
        assert snap["peak_date"] == idx[0].date().isoformat()
        # Volatilité (fenêtre 60) et momentum (252 séances) hors de portée.
        assert snap["vol_pct"] is None
        assert snap["vol_percentile"] is None
        assert snap["vol_threshold_pct"] is None
        assert snap["mom_12_1_pct"] is None


class TestEnginePurity:
    def test_no_io_imports(self):
        import inspect

        src = inspect.getsource(risk)
        assert "from obole.data" not in src
        assert "from obole.services" not in src
        assert "import obole.data" not in src
