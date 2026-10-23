"""Tests du moteur d'indice personnalisé (panier equal-weight chaîné).

Sans réseau : séries synthétiques, fonctions pures.
"""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from tests.test_analysis import _fake_identity

from obole.engine import basket
from obole.engine.regression import fit_log_regression
from obole.models import PriceSeries
from obole.services.analysis import analyze_basket


def _geo_series(
    daily_growth: float, length: int = 3000, seed: int = 0, start: str = "2000-01-03"
) -> pd.Series:
    """Série géométrique sans bruit : pente quotidienne exacte `daily_growth`."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=length, freq="B")
    return pd.Series(100.0 * np.exp(np.cumsum(rng.normal(daily_growth, 0.0, length))), index=idx)


def _ps(s: pd.Series) -> PriceSeries:
    """Enveloppe une série dans un PriceSeries (raw = adj = série donnée)."""
    return PriceSeries(raw=s, adjusted=s, fetched_at=pd.Timestamp("today").date())


class TestAlignedFrame:
    def test_union_of_dates_preserves_longest_history(self):
        a = _geo_series(0.0005, length=4000)  # 2000 -> ~2015
        b = _geo_series(0.0010, length=800, start="2012-01-03")  # inclus dans A

        frame = basket.aligned_frame({"A": a, "B": b})

        assert list(frame.columns) == ["A", "B"]
        assert frame.shape[0] == 4000  # l'union garde tout l'historique de A
        assert frame["A"].notna().all()
        # B débute plus tard : NaN au début, puis complète.
        assert frame["B"].iloc[0] != frame["B"].iloc[0]  # NaN != NaN -> premier point NaN
        assert frame["B"].notna().sum() == 800

    def test_alignment_across_timezones(self):
        idx_a = pd.date_range("2010-01-04", periods=500, freq="B", tz="Europe/Paris")
        idx_b = pd.date_range("2010-01-04", periods=500, freq="B")
        a = pd.Series(100.0 + np.arange(500), index=idx_a)
        b = pd.Series(100.0 + np.arange(500), index=idx_b)

        frame = basket.aligned_frame({"A": a, "B": b})

        assert frame.notna().all().all()
        assert len(frame) == 500

    def test_less_than_two_members_raises(self):
        with pytest.raises(ValueError, match="au moins 2 membres"):
            basket.aligned_frame({"A": _geo_series(0.0005)})

    def test_empty_member_raises(self):
        empty = pd.Series(dtype=float)
        with pytest.raises(ValueError, match="Pas de prix exploitables"):
            basket.aligned_frame({"A": _geo_series(0.0005), "B": empty})


class TestBuildSeries:
    def test_equal_weight_mean_of_member_slopes(self):
        a = _geo_series(0.0005)
        b = _geo_series(0.0010)

        frame = basket.aligned_frame({"A": a, "B": b})
        series = basket.build_series(frame)

        reg_a = fit_log_regression(a)
        reg_b = fit_log_regression(b)
        reg_basket = fit_log_regression(series)
        # La pente de l'indice vaut la moyenne des pentes des membres (equal-weight).
        expected = (reg_a.b + reg_b.b) / 2
        assert reg_basket.b == pytest.approx(expected, rel=1e-3)
        assert series.iloc[0] == pytest.approx(100.0)

    def test_single_member_dominates_early_history(self):
        # B ne commence qu'en 2012 : au début l'indice suit A seul (renormalisé),
        # puis la moyenne des deux. Aucun NaN, historique complet conservé.
        a = _geo_series(0.0005, length=4000)
        b = _geo_series(0.0010, length=800, start="2012-01-03")

        frame = basket.aligned_frame({"A": a, "B": b})
        series = basket.build_series(frame)

        assert len(series) == 4000
        assert series.isna().sum() == 0
        full = basket.full_coverage_years(frame)
        assert full < basket.span_years(series) - 10  # fenêtre complète < historique total

    def test_gaps_in_member_are_skipped_not_propagated(self):
        a = _geo_series(0.0005, length=500)
        b = _geo_series(0.0010, length=500)
        b = b.drop(b.index[100:110])  # B ne cote pas pendant 10 jours

        frame = basket.aligned_frame({"A": a, "B": b})
        series = basket.build_series(frame)

        assert len(series) == 500
        assert series.isna().sum() == 0

    def test_short_history_raises(self):
        a = _geo_series(0.0005, length=20)
        b = _geo_series(0.0010, length=20)

        frame = basket.aligned_frame({"A": a, "B": b})
        with pytest.raises(ValueError, match="trop court"):
            basket.build_series(frame)

    def test_analyze_basket_rebuilds_when_cache_empty(self):
        # cache.get = None force le recalcul (première ouverture d'un indice neuf).
        a = _geo_series(0.0005)
        b = _geo_series(0.0010)
        with (
            patch("obole.services.analysis.cache.get", return_value=None),
            patch("obole.services.analysis.cache.put"),
        ):
            analysis, series = analyze_basket(1, "CAC Tech", "France", {"A": _ps(a), "B": _ps(b)})

        assert isinstance(series, pd.Series)
        assert analysis.regression.n_points > 30


class TestAnalyzeBasket:
    def test_returns_basket_analysis(self):
        a = _geo_series(0.0005)
        b = _geo_series(0.0010)

        with (
            patch("obole.services.analysis.yahoo.fetch_identity", side_effect=_fake_identity),
            patch("obole.services.analysis.cache.get", return_value=None),
            patch("obole.services.analysis.cache.put"),
        ):
            analysis, series = analyze_basket(7, "CAC Tech", "France", {"A": _ps(a), "B": _ps(b)})

        assert analysis.index_id == 7
        assert analysis.name == "CAC Tech"
        assert analysis.category == "France"
        assert len(analysis.members) == 2
        assert analysis.members[0]["ticker"] == "A"
        # Stats « coup d'œil » du membre : position σ, pente, tendance.
        assert set(analysis.members[0]) == {"ticker", "name", "distance_sigma", "pente", "trend"}
        assert analysis.members[0]["pente"].value is not None
        assert analysis.indicators.distance_sigma.value is not None
        assert analysis.indicators.perf_passee.label is not None
        assert analysis.indicators.quality.value is None  # pas de fondamentaux
        # La tendance MM est désormais calculée sur la série synthétique.
        assert analysis.indicators.trend.label is not None
        assert isinstance(series, pd.Series)

    def test_short_history_warning(self):
        a = _geo_series(0.0005, length=100)
        b = _geo_series(0.0010, length=100)

        with (
            patch("obole.services.analysis.yahoo.fetch_identity", side_effect=_fake_identity),
            patch("obole.services.analysis.cache.get", return_value=None),
            patch("obole.services.analysis.cache.put"),
        ):
            analysis, _ = analyze_basket(8, "Jeune", "France", {"A": _ps(a), "B": _ps(b)})

        assert any("Historique" in w for w in analysis.warnings)
