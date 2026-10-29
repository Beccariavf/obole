"""Moteur du backtest de la Clara Vallis : buy & hold contre la stratégie.

Fonction PURE (aucune I/O, aucun réseau). Il reçoit les cours et la série de
satisfaction DÉJÀ calculée (walk-forward, `engine/clara_vallis`), et rend les
deux courbes d'équité avec leurs mesures de risque.

Règle de la stratégie (celle de Darcet) : investi quand le score de la séance
`t` **dépasse** `high`, hors marché quand il **passe sous** `low`, état conservé
entre les deux (hystérésis). Le signal de `t` ne décide QUE la position de
`t + 1` : le rendement de `t + 1` est `P[t+1] / P[t] − 1`, donc aucun regard
sur le futur. Un score absent (NaN) vaut « hors marché ».

Les frais sont PAR ORDRE : `fee_pct` à l'entrée ET à la sortie, soit
`fee_pct × 2` l'aller-retour.

Les mesures de risque ne sont pas réécrites : Sharpe, Sortino et drawdown
viennent de `engine/portfolio`. Seuls CAGR, volatilité, Calmar, temps investi
et nombre de trades sont propres à ce module.

Le résultat est un dict sérialisable ::

    {
      "buy_hold": {"cagr_pct", "volatility_pct", "sharpe", "sortino",
                   "max_drawdown_pct", "calmar", "invested_pct", "trades",
                   "equity"},
      "strategy": {…, "positions"},
      "window": {"start", "end", "sessions"},
    }

Chaque mesure vaut `None` quand elle n'est pas calculable (fenêtre trop
courte, aucune baisse, série plate) : jamais un infini, jamais un NaN.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from obole.engine import portfolio

_TRADING_DAYS = 252


def _cagr_pct(equity: list[float], days: int) -> float | None:
    """CAGR géométrique (%) sur la durée calendaire. `None` si non calculable."""
    if len(equity) < 2 or days <= 0:
        return None
    first, last = equity[0], equity[-1]
    if first <= 0 or last <= 0:
        return None
    return round(((last / first) ** (365.25 / days) - 1.0) * 100.0, 4)


def _volatility_pct(equity: list[float]) -> float | None:
    """Volatilité annualisée (%) des rendements quotidiens de l'équité.

    Une équité plate (cash, aucun trade) donne 0,0 % : ce n'est pas une mesure
    absente, c'est une absence de mouvement. Sharpe, lui, vaut `None` (division
    par zéro).
    """
    rets = portfolio.periodic_returns(equity)
    if len(rets) < 2:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return round(math.sqrt(var) * math.sqrt(_TRADING_DAYS) * 100.0, 4)


def _block(
    equity: list[float],
    days: int,
    dates: list[str],
    invested_pct: float,
    trades: int,
    risk_free_pct: float,
) -> dict[str, Any]:
    """Les huit mesures d'une colonne, calculées sur son équité."""
    cagr = _cagr_pct(equity, days)
    drawdown = portfolio.drawdown_metrics(equity, dates)["max_drawdown_pct"]
    calmar = None
    if cagr is not None and drawdown:
        calmar = round(cagr / abs(drawdown), 4)
    return {
        "cagr_pct": cagr,
        "volatility_pct": _volatility_pct(equity),
        "sharpe": portfolio.sharpe_ratio(equity, risk_free_pct=risk_free_pct),
        "sortino": portfolio.sortino_ratio(equity, risk_free_pct=risk_free_pct),
        "max_drawdown_pct": drawdown,
        "calmar": calmar,
        "invested_pct": invested_pct,
        "trades": trades,
        "equity": equity,
    }


def _empty_block() -> dict[str, Any]:
    """Fenêtre inexploitable : les huit mesures absentes, pas un crash."""
    return {
        "cagr_pct": None,
        "volatility_pct": None,
        "sharpe": None,
        "sortino": None,
        "max_drawdown_pct": None,
        "calmar": None,
        "invested_pct": 0.0,
        "trades": 0,
        "equity": [],
    }


def backtest(
    prices: pd.Series,
    scores: pd.Series,
    low: float,
    high: float,
    fee_pct: float,
    risk_free_pct: float,
) -> dict[str, Any]:
    """Compare buy & hold et la stratégie Clara Vallis sur `prices`.

    `prices` et `scores` sont indexés par date de séance ; `scores` est réaligné
    sur l'index des prix. `fee_pct` et `risk_free_pct` sont en %.
    """
    clean = prices.dropna()
    clean = clean[np.isfinite(clean.to_numpy(dtype=float)) & (clean.to_numpy(dtype=float) > 0)]
    n = len(clean)
    if n < 2:
        return {
            "buy_hold": _empty_block(),
            "strategy": {**_empty_block(), "positions": []},
            "window": {"start": None, "end": None, "sessions": n},
        }

    values = clean.to_numpy(dtype=float)
    aligned = scores.reindex(clean.index).to_numpy(dtype=float)
    fee = fee_pct / 100.0
    dates = [d.strftime("%Y-%m-%d") for d in clean.index]
    days = int((clean.index[-1] - clean.index[0]).days)

    # Buy & hold : entrée à t0 (frais), puis l'équité suit le cours.
    buy_equity = [(1.0 - fee) * (values[t] / values[0]) for t in range(n)]

    # Stratégie : le score de t−1 décide la position de t.
    strat_equity = [1.0]
    positions = [False]
    state = False
    trades = 0
    invested_days = 0
    for t in range(1, n):
        score = aligned[t - 1]
        if np.isnan(score):
            state = False  # score absent : hors marché
        elif score > high:
            state = True
        elif score < low:
            state = False  # entre les bornes : l'état précédent est conservé
        if state != positions[-1]:
            strat_equity[-1] *= 1.0 - fee  # frais PAR ORDRE, à l'entrée comme à la sortie
            if state:
                trades += 1
        equity = strat_equity[-1] * (values[t] / values[t - 1]) if state else strat_equity[-1]
        strat_equity.append(equity)
        positions.append(state)
        if state:
            invested_days += 1

    sessions = n - 1
    buy = _block(buy_equity, days, dates, 100.0, 1, risk_free_pct)
    strat = _block(
        strat_equity, days, dates, round(invested_days / sessions * 100.0, 4), trades, risk_free_pct
    )
    strat["positions"] = positions
    return {
        "buy_hold": buy,
        "strategy": strat,
        "window": {"start": dates[0], "end": dates[-1], "sessions": n},
    }
