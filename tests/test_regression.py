"""Tests purs de l'engine — déterministes, sans réseau."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from obole.engine import regression as reg


def _synthetic_series(
    b_annual: float, sigma_log: float, years: int = 26, seed: int = 0
) -> pd.Series:
    """Série log-linéaire connue : ln(P) = a + b·t + bruit gaussien sigma."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2000-01-03", periods=years * 252, freq="B")
    t = np.array([(d - idx[0]).days / 365.25 for d in idx])
    b = math.log(1 + b_annual)
    a = math.log(20.0)
    noise = rng.normal(0, sigma_log, len(idx))
    return pd.Series(np.exp(a + b * t + noise), index=idx)


def test_fit_recovers_slope_and_sigma():
    s = _synthetic_series(b_annual=0.08, sigma_log=0.30)
    r = reg.fit_log_regression(s)
    # la pente annuelle simple doit retrouver ~8 %
    assert r.perf_annual == pytest.approx(0.08, abs=0.02)
    # l'écart-type (taille) doit retrouver e^0.30 - 1 ≈ 35 %
    assert r.ecart_type_size == pytest.approx(math.exp(0.30) - 1, abs=0.05)


def test_distance_sigma_zero_on_the_line():
    s = _synthetic_series(b_annual=0.08, sigma_log=0.30)
    r = reg.fit_log_regression(s)
    z = reg.distance_sigma(r, r.fitted_now)  # cours pile sur la droite -> z≈0
    assert abs(z) < 1e-9


def test_distance_sigma_sign():
    s = _synthetic_series(b_annual=0.05, sigma_log=0.20)
    r = reg.fit_log_regression(s)
    assert reg.distance_sigma(r, r.fitted_now * 0.5) < 0  # sous la droite = décoté
    assert reg.distance_sigma(r, r.fitted_now * 2.0) > 0  # au-dessus = surcoté


def test_potential_positive_when_below_line():
    s = _synthetic_series(b_annual=0.08, sigma_log=0.25)
    r = reg.fit_log_regression(s)
    # cours bien sous la droite -> potentiel de retour positif
    pot = reg.annualized_potential(r, r.fitted_now * 0.4, 5)
    assert pot > 0


def test_trend_bullish_when_short_above_long():
    idx = pd.date_range("2020-01-01", periods=300, freq="B")
    s = pd.Series(np.linspace(10, 50, 300), index=idx)  # tendance haussière nette
    assert reg.trend_is_bullish(s, 11, 200) is True
    s_down = pd.Series(np.linspace(50, 10, 300), index=idx)
    assert reg.trend_is_bullish(s_down, 11, 200) is False


def test_trend_none_when_insufficient_history():
    idx = pd.date_range("2020-01-01", periods=50, freq="B")
    s = pd.Series(np.linspace(10, 20, 50), index=idx)
    assert reg.trend_is_bullish(s, 11, 200) is None


def test_fit_raises_on_short_series():
    s = pd.Series([10, 11, 12], index=pd.date_range("2020-01-01", periods=3))
    with pytest.raises(ValueError):
        reg.fit_log_regression(s)
