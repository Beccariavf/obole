"""Cœur mathématique : la « droite d'Obole ».

Fonctions PURES (pas d'I/O, pas de réseau). Vectorisé numpy.
Calibré sur Pernod Ricard : z = −3.81 (exact), potentiels 32.5 % / 19.0 %.
Voir PRD §5.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from obole import config
from obole.models import RegressionResult


def _years_axis(index: pd.DatetimeIndex) -> np.ndarray:
    """Convertit un index de dates en années écoulées depuis le premier point."""
    t0 = index[0]
    return np.array([(d - t0).days / 365.25 for d in index], dtype=float)


def fit_log_regression(prices: pd.Series) -> RegressionResult:
    """Régression OLS de ln(P) sur le temps (années).

    ln(P_t) ≈ a + b·t. La pente b est la performance continue annualisée.
    sigma = écart-type (ddof=1) des résidus en unités log.
    """
    s = prices.dropna()
    s = s[s > 0]
    if len(s) < config.REGRESSION_MIN_POINTS:
        raise ValueError(f"Série trop courte pour une régression fiable ({len(s)} points)")

    t = _years_axis(s.index)
    y = np.log(s.to_numpy())
    b, a = np.polyfit(t, y, 1)  # numpy renvoie [pente, intercept]
    resid = y - (a + b * t)
    sigma = float(resid.std(ddof=1))

    t_now = float(t[-1])
    return RegressionResult(
        a=float(a),
        b=float(b),
        sigma=sigma,
        t_now=t_now,
        fitted_now=float(math.exp(a + b * t_now)),
        start=s.index[0].date(),
        end=s.index[-1].date(),
        n_points=len(s),
    )


def distance_sigma(reg: RegressionResult, current_price: float) -> float:
    """Distance en écart-type (z) du cours actuel à la droite.

    z = (ln(P) − droite) / sigma. Négatif = décoté, positif = surcoté.
    """
    resid_now = math.log(current_price) - (reg.a + reg.b * reg.t_now)
    return resid_now / reg.sigma


def annualized_potential(reg: RegressionResult, current_price: float, horizon_years: int) -> float:
    """Potentiel annualisé si le cours rejoint la droite à l'horizon H.

    Cible = point sur la droite à t_now + H (z=0). Retour annualisé.
    """
    target = math.exp(reg.a + reg.b * (reg.t_now + horizon_years))
    return (target / current_price) ** (1 / horizon_years) - 1


def regression_bands(reg: RegressionResult, index: pd.DatetimeIndex, ks=(1, 2)) -> dict:
    """Calcule la droite et les bandes ±k·sigma pour le tracé, sur un index donné.

    Renvoie {'line': Series, '+1': Series, '-1': Series, ...} en échelle prix.
    """
    t0 = reg.start
    t = np.array([(d.date() - t0).days / 365.25 for d in index], dtype=float)
    line = np.exp(reg.a + reg.b * t)
    out = {"line": pd.Series(line, index=index)}
    for k in ks:
        out[f"+{k}"] = pd.Series(np.exp(reg.a + reg.b * t + k * reg.sigma), index=index)
        out[f"-{k}"] = pd.Series(np.exp(reg.a + reg.b * t - k * reg.sigma), index=index)
    return out


def trend_is_bullish(prices: pd.Series, ma_short: int, ma_long: int) -> bool | None:
    """Tendance boursière : Haussière si MM(short) > MM(long), sinon Baissière.

    Renvoie None si pas assez d'historique pour la MM longue.
    """
    s = prices.dropna()
    if len(s) < ma_long:
        return None
    short = s.rolling(ma_short).mean().iloc[-1]
    long = s.rolling(ma_long).mean().iloc[-1]
    if pd.isna(short) or pd.isna(long):
        return None
    return bool(short > long)
