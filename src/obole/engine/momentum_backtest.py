"""Moteur du backtest de la Clara Vallis : le marché pendant les séances in et out.

Fonction PURE (aucune I/O, aucun réseau). Il reçoit les cours et la série de
satisfaction DÉJÀ calculée (walk-forward, `engine/clara_vallis`), et rend les
mesures du marché sur les deux paniers de séances, plus le rendement réel de la
stratégie.

Règle de la stratégie (celle de Darcet) : investi quand le score de la séance
`t` **dépasse** `high`, hors marché quand il **passe sous** `low`, état conservé
entre les deux (hystérésis). Le signal de `t` ne décide QUE la position de
`t + 1` : le rendement de `t + 1` est `P[t+1] / P[t] − 1`, donc aucun regard
sur le futur. Un score absent (NaN) vaut « hors marché ».

**Deux paniers, deux lectures.** Chaque séance de rendement appartient à `in`
(la position de cette séance était investie) ou à `out` (hors marché). Les deux
paniers PARTITIONNENT la fenêtre. Chaque panier compose sa propre courbe avec
les seuls rendements du marché de ses séances : une courbe part de 1 et ne
contient que son panier. Ces courbes ne sont pas dessinées — elles servent à
mesurer le signal. Comparer le rendement total de la stratégie (investie 60 à
70 % du temps) à un buy & hold investi à 100 % compare deux expositions : la
bonne question est « le signal sépare-t-il les bons jours des mauvais ? ».

**CAGR annualisé sur les séances du panier** (`n/252`), pas sur le calendrier :
c'est le rythme du signal, pas le temps qui passe. Un panier de 1 800 séances
sur 11 ans se lit sur ~7 ans de marché. Le buy & hold suit la même règle
(`n − 1` rendements), et le CAGR de la stratégie (cash compris) aussi.

Les frais sont PAR ORDRE : `fee_pct` à l'entrée ET à la sortie, soit
`fee_pct × 2` l'aller-retour. Ils ne touchent QUE la courbe de la stratégie et
le buy & hold (frais d'entrée) : les paniers in/out mesurent le marché, pas un
portefeuille.

Les mesures de risque ne sont pas réécrites : Sharpe, Sortino et drawdown
viennent de `engine/portfolio`. Seuls CAGR, volatilité, Calmar et part des
séances sont propres à ce module.

Le résultat est un dict sérialisable ::

    {
      "buy_hold": {"cagr_pct", "volatility_pct", "sharpe", "sortino",
                   "max_drawdown_pct", "calmar", "sessions_pct", "equity"},
      "in":  {…},
      "out": {…},
      "window": {"start", "end", "sessions"},
      "trades": 27,
      "strategy_cagr_pct": 4.2,
      "strategy_equity": […],   # interne : jamais transporté
      "positions": […],         # interne : jamais transporté
    }

`equity`, `strategy_equity` et `positions` restent dans le moteur pour ses tests
(frais, hystérésis, absence de fuite) ; le service ne les sérialise jamais.

Chaque mesure vaut `None` quand elle n'est pas calculable (fenêtre trop courte,
aucune baisse, série plate, panier vide) : jamais un infini, jamais un NaN.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from obole.engine import portfolio

_TRADING_DAYS = 252


def _cagr_pct(curve: list[float], sessions: int) -> float | None:
    """CAGR géométrique (%) annualisé sur les SÉANCES, pas sur le calendrier.

    `sessions` = nombre de rendements composés dans `curve` (la courbe part de 1,
    donc elle en compte un de plus). `None` si non calculable.

    Deux rendements au minimum, comme pour Sharpe, Sortino et la volatilité : sur
    une seule séance, `** (252 / 1)` extrapolerait un mouvement d'un jour sur un
    an — un chiffre spectaculaire et vide, que le Calmar colorerait ensuite.
    """
    if sessions < 2 or len(curve) < 2:
        return None
    first, last = curve[0], curve[-1]
    if first <= 0 or last <= 0:
        return None
    return round(((last / first) ** (_TRADING_DAYS / sessions) - 1.0) * 100.0, 4)


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
    sessions: int,
    sessions_pct: float,
    risk_free_pct: float,
) -> dict[str, Any]:
    """Les sept mesures d'une colonne, calculées sur sa courbe.

    `sessions_pct` = part des séances de la fenêtre que porte CETTE colonne : 100 %
    pour le buy & hold, la part investie pour `in`, la part hors marché pour `out`
    (le nom dit la part des séances, pas un temps investi — sinon la clé
    mentirait sur la colonne `out`).

    Les dates ne sont pas transmises à `drawdown_metrics` : les courbes in/out ne
    sont pas contiguës (leurs séances sont éparpillées), donc leurs dates de pic
    et de creux n'auraient aucun sens. Seul le max drawdown — qui ne dépend que
    de la suite des valeurs — est lu.
    """
    cagr = _cagr_pct(equity, sessions)
    drawdown = portfolio.drawdown_metrics(equity)["max_drawdown_pct"]
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
        "sessions_pct": sessions_pct,
        "equity": equity,
    }


def _empty_block() -> dict[str, Any]:
    """Panier vide ou fenêtre inexploitable : mesures absentes, pas un crash."""
    return {
        "cagr_pct": None,
        "volatility_pct": None,
        "sharpe": None,
        "sortino": None,
        "max_drawdown_pct": None,
        "calmar": None,
        "sessions_pct": 0.0,
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
    """Mesure le marché pendant les séances in et out de la stratégie Clara Vallis.

    `prices` et `scores` sont indexés par date de séance ; `scores` est réaligné
    sur l'index des prix. `fee_pct` et `risk_free_pct` sont en %.
    """
    clean = prices.dropna()
    clean = clean[np.isfinite(clean.to_numpy(dtype=float)) & (clean.to_numpy(dtype=float) > 0)]
    n = len(clean)
    if n < 2:
        return {
            "buy_hold": _empty_block(),
            "in": _empty_block(),
            "out": _empty_block(),
            "window": {"start": None, "end": None, "sessions": n},
            "trades": 0,
            "strategy_cagr_pct": None,
            "strategy_equity": [],
            "positions": [],
        }

    values = clean.to_numpy(dtype=float)
    aligned = scores.reindex(clean.index).to_numpy(dtype=float)
    fee = fee_pct / 100.0
    dates = [d.strftime("%Y-%m-%d") for d in clean.index]

    # Buy & hold : entrée à t0 (frais), puis l'équité suit le cours.
    buy_equity = [(1.0 - fee) * (values[t] / values[0]) for t in range(n)]

    # Stratégie : le score de t−1 décide la position de t.
    strat_equity = [1.0]
    positions = [False]
    state = False
    trades = 0
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

    # Deux paniers : chaque rendement du marché va dans le panier de sa séance.
    # La position de `t` est celle décidée par le score de `t−1` (aucune fuite).
    in_curve = [1.0]
    out_curve = [1.0]
    for t in range(1, n):
        growth = values[t] / values[t - 1]
        curve = in_curve if positions[t] else out_curve
        curve.append(curve[-1] * growth)

    sessions = n - 1
    n_in = len(in_curve) - 1
    n_out = len(out_curve) - 1
    # La part de out est le COMPLÉMENT de celle de in : les deux somment à 100 %
    # exactement, malgré l'arrondi (elles partitionnent la fenêtre).
    in_pct = round(n_in / sessions * 100.0, 4)
    out_pct = round(100.0 - in_pct, 4)

    buy = _block(buy_equity, sessions, 100.0, risk_free_pct)
    inside = _block(in_curve, n_in, in_pct, risk_free_pct) if n_in else _empty_block()
    outside = _block(out_curve, n_out, out_pct, risk_free_pct) if n_out else _empty_block()
    return {
        "buy_hold": buy,
        "in": inside,
        "out": outside,
        "window": {"start": dates[0], "end": dates[-1], "sessions": n},
        "trades": trades,
        "strategy_cagr_pct": _cagr_pct(strat_equity, sessions),
        "strategy_equity": strat_equity,
        "positions": positions,
    }
