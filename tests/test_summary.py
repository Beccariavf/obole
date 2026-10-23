"""Tests des stats « coup d'œil » (engine/summary.py) — pures, sans réseau.

Symétrie avec les fiches : les valeurs (position σ, pente) sont celles de la
fenêtre « 20 dernières années » (défaut d'ouverture d'une fiche côté front) ;
la tendance reste sur l'historique complet, comme sur une fiche.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from tests.test_analysis import _make_prices

from obole.engine import regression as reg
from obole.engine.summary import index_stats, member_stats, regression_window


class TestMemberStats:
    def test_full_stats(self):
        prices = _make_prices()
        st = member_stats(prices.raw, prices.adjusted)

        assert set(st) == {"distance_sigma", "pente", "trend"}
        assert st["distance_sigma"].value is not None
        assert st["distance_sigma"].label is not None
        assert st["distance_sigma"].good is not None  # z fenêtre 20 ans (ajusté)
        assert st["pente"].value is not None
        assert st["pente"].label is not None
        assert st["trend"].label in ("Haussière", "Baissière")

    def test_short_history_degrades_to_none(self):
        prices = _make_prices(length=20)  # en deçà du minimum de régression
        st = member_stats(prices.raw, prices.adjusted)

        assert st["distance_sigma"].value is None
        assert st["distance_sigma"].label is None
        assert st["pente"].value is None
        assert st["trend"].value is None

    def test_empty_series_degrades_to_none(self):
        empty = pd.Series(dtype=float)
        st = member_stats(empty, empty)

        assert st["distance_sigma"].value is None
        assert st["pente"].value is None
        assert st["trend"].value is None

    def test_pente_matches_window_regression(self):
        prices = _make_prices(seed=7)
        st = member_stats(prices.raw, prices.adjusted)

        assert st["pente"].value == round(_window_perf(prices.adjusted), 1)

    def test_distance_follows_adjusted_window_not_full_history(self):
        raw, adj = _long_pair()
        st = member_stats(raw, adj)

        # La fiche s'ouvre sur les 20 dernières années, dividendes réinvestis :
        # le membre doit montrer le z de la fenêtre 20 ans de l'AJUSTÉ.
        assert st["distance_sigma"].value == round(_window_z(adj), 2)
        # … pas celui de l'historique complet, ni celui de la fenêtre du BRUT.
        assert st["distance_sigma"].value != round(_full_z(adj), 2)
        assert st["distance_sigma"].value != round(_window_z(raw), 2)


class TestIndexStats:
    def test_full_stats(self):
        prices = _make_prices()
        st = index_stats(prices.adjusted)  # une série quelconque suffit

        assert set(st) == {"distance_sigma", "pente", "trend"}
        assert st["distance_sigma"].value is not None
        assert st["distance_sigma"].label is not None
        assert st["distance_sigma"].good is not None  # z du dernier point (fenêtre 20 ans)
        assert st["pente"].value is not None
        assert st["pente"].label is not None
        assert st["trend"].label in ("Haussière", "Baissière")

    def test_short_history_degrades_to_none(self):
        prices = _make_prices(length=20)
        st = index_stats(prices.adjusted)

        assert st["distance_sigma"].value is None
        assert st["pente"].value is None
        assert st["trend"].value is None

    def test_empty_series_degrades_to_none(self):
        st = index_stats(pd.Series(dtype=float))

        assert st["distance_sigma"].value is None
        assert st["pente"].value is None
        assert st["trend"].value is None

    def test_stats_match_window_regression(self):
        prices = _make_prices(seed=11)
        st = index_stats(prices.adjusted)

        assert st["distance_sigma"].value == round(_window_z(prices.adjusted), 2)
        assert st["pente"].value == round(_window_perf(prices.adjusted), 1)

    def test_window_is_last_20_years_not_full_history(self):
        raw, _ = _long_pair()
        st = index_stats(raw)

        assert st["distance_sigma"].value == round(_window_z(raw), 2)
        # La tendance antérieure à la fenêtre (forte hausse ici) ne doit plus
        # influencer la position σ.
        assert st["distance_sigma"].value != round(_full_z(raw), 2)


def _window_z(series: pd.Series) -> float:
    s = regression_window(series).dropna()
    r = reg.fit_log_regression(regression_window(series))
    return reg.distance_sigma(r, float(s.iloc[-1]))


def _window_perf(series: pd.Series) -> float:
    return reg.fit_log_regression(regression_window(series)).perf_annual * 100


def _full_z(series: pd.Series) -> float:
    r = reg.fit_log_regression(series)
    return reg.distance_sigma(r, float(series.dropna().iloc[-1]))


def _long_pair() -> tuple[pd.Series, pd.Series]:
    """~31 ans de jours ouvrés, tendances brut/ajusté divergentes.

    brut : forte hausse ~11 ans puis quasi-plateau ~20 ans — la fenêtre 20 ans
    (plateau) a donc une position σ bien différente de l'historique complet
    (pente forte). ajusté : hausse sur les 20 dernières années puis plateau
    final — sa fenêtre (et son z) diffère aussi bien du brut que de l'ajusté
    complet. Bruit gaussien déterministe (seed fixe) : σ non nul, reproductible.
    """
    idx = pd.date_range("1995-01-02", periods=8000, freq="B")
    years = np.array([(d - idx[0]).days / 365.25 for d in idx])
    noise = np.cumsum(np.random.default_rng(11).normal(0, 0.004, len(idx)))
    raw_ln = 0.18 * np.minimum(years, 11.0) + 0.01 * np.maximum(years - 11.0, 0.0) + noise
    adj_ln = 0.10 * np.maximum(years - 11.0, 0.0) - 0.06 * np.maximum(years - 26.0, 0.0) + noise
    return (
        pd.Series(np.exp(raw_ln), index=idx),
        pd.Series(np.exp(adj_ln), index=idx),
    )
