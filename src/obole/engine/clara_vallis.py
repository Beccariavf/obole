"""Moteur de la Clara Vallis : satisfaction de la foule et confiance de la droite.

Fonctions PURES (aucune I/O, aucun réseau), vectorisées numpy.

Un « maçon » entré à la séance `i` place sa bulle entre le creux et le sommet
parcourus depuis son entrée : `(cours − min) / (max − min)`. Le score de
satisfaction est la moyenne des bulles des `window` dernières entrées : près de
1, la foule est satisfaite (le cours est près des plus hauts) ; près de 0, elle
est frustrée. Le walk-forward ne lit jamais une séance postérieure à la date
évaluée — à `t`, la fenêtre est fermée à droite sur `t`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from obole import config
from obole.models import SatisfactionResult

# Dates traitées d'un coup. `sliding_window_view` garde une vue (n, window) :
# sur 9 000 séances, les tableaux temporaires pèsent ~110 Mo. Par blocs de 2 000,
# la pointe tombe à une vingtaine de mégaoctets.
_CHUNK = 2000


def _clean(prices: pd.Series) -> pd.Series:
    """Série positive, sans trou, dans l'ordre du temps."""
    s = prices.dropna()
    return s[s > 0]


def _bubble_window(window_prices: np.ndarray) -> np.ndarray:
    """Bulles de toutes les entrées d'une fenêtre fermée à droite.

    `window_prices` = `[t-window+1, t]` ; le dernier point est le cours courant.
    Pour chaque entrée `i`, le creux et le sommet sont pris sur `[i, fin]`.
    """
    last = window_prices[-1]
    suffix_min = np.minimum.accumulate(window_prices[::-1])[::-1]
    suffix_max = np.maximum.accumulate(window_prices[::-1])[::-1]
    span = suffix_max - suffix_min
    safe = np.where(span > 0, span, 1.0)
    return np.where(span > 0, (last - suffix_min) / safe, 0.5)


def bubble_position(prices) -> float:
    """Position de la bulle d'une seule entrée, dans [0, 1].

    0,5 (neutre) si la série est plate ou trop courte : un parcours sans
    amplitude ne dit rien de la satisfaction.
    """
    p = np.asarray(prices, dtype=float)
    p = p[np.isfinite(p)]
    if len(p) < 2:
        return 0.5
    lo = float(p.min())
    hi = float(p.max())
    if hi <= lo:
        return 0.5
    return float((p[-1] - lo) / (hi - lo))


def satisfaction_score(
    prices: pd.Series, window: int = config.MOMENTUM_WINDOW
) -> SatisfactionResult:
    """Satisfaction moyenne des `window` dernières entrées."""
    s = _clean(prices)
    if len(s) < 2:
        return SatisfactionResult(value=None, n_used=0, short_history=False)
    w = s.to_numpy(dtype=float)[-window:]
    return SatisfactionResult(
        value=float(np.mean(_bubble_window(w))),
        n_used=len(w),
        short_history=len(s) < window,
    )


def satisfaction_series(prices: pd.Series, window: int = config.MOMENTUM_WINDOW) -> pd.Series:
    """Score à chaque date, sur la seule fenêtre antérieure.

    `NaN` avant la `window`-ième séance. Le découpage en blocs borne la mémoire
    sans changer le résultat.
    """
    s = _clean(prices)
    out = pd.Series(np.nan, index=s.index, dtype=float)
    n = len(s)
    if n < 2:
        return out
    p = s.to_numpy(dtype=float)
    if n < window:
        out.iloc[-1] = float(np.mean(_bubble_window(p)))
        return out

    view = np.lib.stride_tricks.sliding_window_view(p, window)
    last = p[window - 1 :]
    scores = np.empty(len(view), dtype=float)
    for start in range(0, len(view), _CHUNK):
        stop = min(start + _CHUNK, len(view))
        block = view[start:stop][:, ::-1]
        suffix_min = np.minimum.accumulate(block, axis=1)
        suffix_max = np.maximum.accumulate(block, axis=1)
        span = suffix_max - suffix_min
        safe = np.where(span > 0, span, 1.0)
        bubbles = np.where(span > 0, (last[start:stop, None] - suffix_min) / safe, 0.5)
        scores[start:stop] = bubbles.mean(axis=1)
    out.iloc[window - 1 :] = scores
    return out


def regime_score(prices: pd.Series) -> float | None:
    """Confiance de la droite : `1 − R²` de ln(prix) sur le temps.

    0 = droite parfaite (monde de Markovitz), 1 = chaos (monde de Mandelbrot).
    `None` si la série est trop courte ou parfaitement plate.
    """
    s = _clean(prices)
    if len(s) < 2:
        return None
    t = np.array([(d - s.index[0]).days / 365.25 for d in s.index], dtype=float)
    y = np.log(s.to_numpy(dtype=float))
    if float(y.max() - y.min()) <= 0:
        return None
    b, a = np.polyfit(t, y, 1)
    resid = y - (a + b * t)
    ss_res = float(np.sum(resid**2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    if ss_tot <= 0:
        return None
    return float(min(1.0, max(0.0, ss_res / ss_tot)))
