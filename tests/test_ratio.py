"""Tests purs de la construction de ratio — déterministes, sans réseau."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from obole.engine import ratio
from obole.engine import regression as reg


def _series(start: str, n: int, base: float, growth: float) -> pd.Series:
    """Série quotidienne croissant géométriquement (pour ratios prévisibles)."""
    idx = pd.date_range(start, periods=n, freq="B")
    t = np.arange(n)
    return pd.Series(base * (1 + growth) ** t, index=idx)


def test_ratio_aligns_on_common_dates():
    # A couvre 2000->~2008, B couvre ~2003->~2011 : recouvrement au milieu.
    a = _series("2000-01-03", 2000, 10.0, 0.0005)
    b = _series("2003-06-02", 2000, 20.0, 0.0003)
    r = ratio.build_ratio(a, b)
    assert r.index[0] >= b.index[0]  # borné par le plus jeune au démarrage
    assert r.index[-1] <= a.index[-1]  # borné par le plus vieux à la fin
    # valeur = A/B à une date commune
    d = r.index[0]
    assert r.loc[d] == pytest.approx(a.loc[d] / b.loc[d])


def test_ratio_feeds_regression():
    a = _series("2000-01-03", 8000, 10.0, 0.0004)
    b = _series("2000-01-03", 8000, 10.0, 0.0002)  # A surperforme B -> ratio croissant
    r = ratio.build_ratio(a, b)
    result = reg.fit_log_regression(r)
    assert result.b > 0  # ratio tendanciellement haussier


def test_ratio_raises_on_short_common_history():
    a = _series("2000-01-03", 500, 10.0, 0.001)
    b = _series("2024-12-01", 10, 20.0, 0.001)  # quasi aucun recouvrement
    with pytest.raises(ValueError):
        ratio.build_ratio(a, b)


def test_ratio_raises_on_nonpositive_denominator():
    idx = pd.date_range("2000-01-03", periods=40, freq="B")
    a = pd.Series(np.linspace(10, 20, 40), index=idx)
    b = pd.Series(np.linspace(1, -1, 40), index=idx)  # passe par 0/négatif
    with pytest.raises(ValueError):
        ratio.build_ratio(a, b)


def test_common_years():
    # ~10 ans calendaires d'historique (jours ouvrés -> on couvre l'amplitude réelle).
    a = _series("2000-01-03", 252 * 10, 10.0, 0.0)
    b = _series("2000-01-03", 252 * 10, 10.0, 0.0)
    r = ratio.build_ratio(a, b)
    assert ratio.common_years(r) == pytest.approx(9.65, abs=0.3)


# --- Bêta A~B ----------------------------------------------------------------


def _price_from_returns(returns: np.ndarray, start: str, base: float = 100.0) -> pd.Series:
    """Reconstruit une série de prix à partir de rendements log quotidiens."""
    idx = pd.date_range(start, periods=len(returns) + 1, freq="B")
    prices = base * np.exp(np.concatenate([[0.0], np.cumsum(returns)]))
    return pd.Series(prices, index=idx)


def test_beta_recovers_slope_of_two():
    # A = 2·B (rendements) : β(A~B) doit valoir ~2.
    rng = np.random.default_rng(0)
    rb = rng.normal(0, 0.01, 500)
    ra = 2.0 * rb
    a = _price_from_returns(ra, "2000-01-03")
    b = _price_from_returns(rb, "2000-01-03")
    sa, sb = ratio.aligned_pair(a, b)
    assert ratio.beta(sa, sb) == pytest.approx(2.0, abs=0.05)


def test_beta_near_zero_when_independent():
    rng = np.random.default_rng(1)
    a = _price_from_returns(rng.normal(0, 0.01, 2000), "2000-01-03")
    b = _price_from_returns(rng.normal(0, 0.01, 2000), "2000-01-03")
    sa, sb = ratio.aligned_pair(a, b)
    assert ratio.beta(sa, sb) == pytest.approx(0.0, abs=0.1)


def test_beta_negative_when_inverse():
    rng = np.random.default_rng(2)
    rb = rng.normal(0, 0.01, 500)
    a = _price_from_returns(-rb, "2000-01-03")  # A = -B
    b = _price_from_returns(rb, "2000-01-03")
    sa, sb = ratio.aligned_pair(a, b)
    assert ratio.beta(sa, sb) == pytest.approx(-1.0, abs=0.05)


def test_beta_none_when_too_few_points():
    # 10 rendements < BETA_MIN_POINTS (20) -> None. On borne aligned_pair au minimum
    # commun (MIN_COMMON_POINTS=30 dates), mais on tronque pour tester le garde-fou β.
    rng = np.random.default_rng(3)
    a = _price_from_returns(rng.normal(0, 0.01, 40), "2000-01-03")
    b = _price_from_returns(rng.normal(0, 0.01, 40), "2000-01-03")
    sa, sb = ratio.aligned_pair(a, b)
    assert ratio.beta(sa.iloc[:10], sb.iloc[:10]) is None


# --- Corrélation A~B (solidité du lien, distincte du β) ----------------------


def test_correlation_is_one_when_amplitude_differs():
    # A = 2·B : β=2 (amplitude) MAIS ρ=1 (parfaitement corrélés). C'est LA différence
    # clé entre les deux mesures — un β élevé n'empêche pas une corrélation parfaite.
    rng = np.random.default_rng(0)
    rb = rng.normal(0, 0.01, 500)
    a = _price_from_returns(2.0 * rb, "2000-01-03")
    b = _price_from_returns(rb, "2000-01-03")
    sa, sb = ratio.aligned_pair(a, b)
    assert ratio.beta(sa, sb) == pytest.approx(2.0, abs=0.05)
    assert ratio.correlation(sa, sb) == pytest.approx(1.0, abs=0.01)


def test_correlation_near_zero_when_independent():
    rng = np.random.default_rng(1)
    a = _price_from_returns(rng.normal(0, 0.01, 2000), "2000-01-03")
    b = _price_from_returns(rng.normal(0, 0.01, 2000), "2000-01-03")
    sa, sb = ratio.aligned_pair(a, b)
    assert ratio.correlation(sa, sb) == pytest.approx(0.0, abs=0.1)


def test_correlation_negative_when_inverse():
    rng = np.random.default_rng(2)
    rb = rng.normal(0, 0.01, 500)
    a = _price_from_returns(-rb, "2000-01-03")
    b = _price_from_returns(rb, "2000-01-03")
    sa, sb = ratio.aligned_pair(a, b)
    assert ratio.correlation(sa, sb) == pytest.approx(-1.0, abs=0.01)


def test_correlation_bounded_and_none_when_too_few_points():
    rng = np.random.default_rng(4)
    a = _price_from_returns(rng.normal(0, 0.01, 400), "2000-01-03")
    b = _price_from_returns(rng.normal(0, 0.01, 400), "2000-01-03")
    sa, sb = ratio.aligned_pair(a, b)
    rho = ratio.correlation(sa, sb)
    assert -1.0 <= rho <= 1.0
    assert ratio.correlation(sa.iloc[:10], sb.iloc[:10]) is None
