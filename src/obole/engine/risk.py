"""Moteur pur du risque et de la dynamique (#33).

Fonctions **100 % pures** (`numpy`/`pandas`, aucune I/O, aucun réseau) : elles
reçoivent des séries de prix déjà extraites par `data/` et produisent les
mesures de la section « Risque & dynamique ». Aucun seuil en dur : les fenêtres,
le quantile d'anomalie et le minimum d'observations viennent de `config.py`.

Invariants :

- toute série est **nettoyée** avant calcul (NaN, valeurs ≤ 0, doublons d'index) ;
- une valeur non calculable vaut `None` (jamais un 0 trompeur, jamais d'infini) ;
- les rendements et écarts sont rendus en **points de pourcentage**, pas en
  fraction ;
- le momentum 12-1 se compte en **séances** (positions), jamais en calendrier.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from obole import config

# Convention financière : 252 séances par an, racine du temps pour annualiser.
_TRADING_DAYS_PER_YEAR = 252


def clean_prices(prices: pd.Series) -> pd.Series:
    """Série de cours exploitable : sans NaN ni valeur ≤ 0, index unique et trié.

    Un **doublon d'index** garde la dernière valeur (la lecture la plus récente
    de la même séance) : c'est celle que le flux de données a effectivement
    retenue. Un cours nul ou négatif est écarté — il n'a pas de logarithme ni de
    sens économique.
    """
    s = prices.dropna()
    s = s[s > 0]
    s = s[~s.index.duplicated(keep="last")]
    return s.sort_index()


def drawdown_series(prices: pd.Series) -> pd.Series:
    """Chute depuis le plus-haut cumulé (%), sur la série nettoyée.

    `P_t / max(P_0..P_t) − 1`, en % : 0 au plus haut, négatif en dessous. L'index
    est celui de la série nettoyée (une séance écartée ne laisse pas de trou).
    """
    s = clean_prices(prices)
    if s.empty:
        return pd.Series(dtype=float)
    peak = s.cummax()
    return (s / peak - 1.0) * 100.0


def peak_date(prices: pd.Series) -> pd.Timestamp | None:
    """Date du plus-haut courant (le dernier plus haut atteint).

    À égalité, c'est la séance la plus **récente** au maximum qui est retenue :
    c'est le dernier moment où le cours a touché son sommet. `None` si la série
    nettoyée est vide ou si l'index n'est pas convertible en date.
    """
    s = clean_prices(prices)
    if s.empty or pd.api.types.is_numeric_dtype(s.index):
        # Un index numérique est une position, pas une date : ne pas fabriquer
        # un 1970 trompeur (l'absence se dit `None`).
        return None
    highest = s.max()
    stamp = s.index[s == highest][-1]
    try:
        return pd.Timestamp(stamp)
    except (ValueError, TypeError):
        return None


def realized_vol_series(prices: pd.Series, window: int = config.RISK_VOL_WINDOW) -> pd.Series:
    """Volatilité réalisée glissante, annualisée (%), sur `window` séances.

    Écart-type (`ddof=1`) des rendements **log** quotidiens sur `window` séances,
    × √252, en %. La série est `NaN` tant que la fenêtre n'est pas pleine : la
    première valeur sort à la `window`-ième séance de rendement.
    """
    s = clean_prices(prices)
    if s.empty:
        return pd.Series(dtype=float)
    log_returns = np.log(s).diff()
    vol = log_returns.rolling(window=window, min_periods=window).std(ddof=1)
    return vol * math.sqrt(_TRADING_DAYS_PER_YEAR) * 100.0


def percentile_of_last(
    series: pd.Series, min_points: int = config.RISK_VOL_MIN_POINTS
) -> float | None:
    """Centile (0–100) de la dernière valeur parmi les valeurs antérieures.

    Part des valeurs non-NaN **strictement antérieures** à la dernière qui lui
    sont inférieures, arrondie à 1 décimale. `None` si la série compte moins de
    `min_points` valeurs non-NaN : sous ce seuil, un centile n'a pas de sens.
    """
    values = series.dropna()
    if len(values) < min_points:
        return None
    last = float(values.iloc[-1])
    prior = values.iloc[:-1]
    if prior.empty:
        return None
    share = float((prior < last).sum()) / len(prior) * 100.0
    return round(share, 1)


def quantile_threshold(
    series: pd.Series,
    pctile: float = config.RISK_VOL_ANOMALY_PCTILE,
    min_points: int = config.RISK_VOL_MIN_POINTS,
) -> float | None:
    """Seuil d'anomalie : quantile `pctile/100` des valeurs non-NaN.

    `None` si la série compte moins de `min_points` valeurs : un seuil tiré de
    trop peu de points serait arbitraire.
    """
    values = series.dropna()
    if len(values) < min_points:
        return None
    return float(values.quantile(pctile / 100.0))


def momentum_12_1(
    prices: pd.Series,
    lookback: int = config.RISK_MOM_LOOKBACK,
    skip: int = config.RISK_MOM_SKIP,
) -> float | None:
    """Momentum 12-1 (%), compté en séances : `P[-1-skip] / P[-1-lookback] − 1`.

    On saute les `skip` dernières séances (retournement de court terme) pour ne
    garder que la tendance de fond. `None` si la série nettoyée a moins de
    `lookback + 1` points : sans la séance de départ, le ratio n'existe pas.
    """
    s = clean_prices(prices)
    # Les deux positions doivent exister : un `skip` plus grand que le lookback
    # (ou que la série) rend le ratio indéfini, jamais une exception.
    if lookback < 0 or skip < 0 or len(s) <= max(lookback, skip):
        return None
    start = float(s.iloc[-1 - lookback])
    end = float(s.iloc[-1 - skip])
    if start <= 0:
        return None
    return (end / start - 1.0) * 100.0


def risk_snapshot(prices_adj: pd.Series, prices_raw: pd.Series) -> dict:
    """Instantané de risque d'un titre, chute et vol sur l'ajustée, 12-1 sur la brute.

    `prices_adj` (dividendes réinvestis) porte la chute et la volatilité — c'est
    la série de performance ; `prices_raw` (cours brut) porte le momentum 12-1 —
    c'est la série de valorisation. Valeurs arrondies à 2 décimales ; tout
    indicateur non calculable vaut `None`.
    """
    drawdown = drawdown_series(prices_adj)
    drawdown_pct = None if drawdown.empty else _round_or_none(float(drawdown.iloc[-1]))

    peak = peak_date(prices_adj)
    peak_iso = None if peak is None else peak.date().isoformat()

    vol = realized_vol_series(prices_adj)
    vol_pct = None
    if not vol.empty:
        last_vol = vol.iloc[-1]
        if pd.notna(last_vol):
            vol_pct = _round_or_none(float(last_vol))

    return {
        "drawdown_pct": drawdown_pct,
        "peak_date": peak_iso,
        "vol_pct": vol_pct,
        "vol_percentile": percentile_of_last(vol),
        "vol_threshold_pct": _round_or_none(quantile_threshold(vol)),
        "mom_12_1_pct": _round_or_none(momentum_12_1(prices_raw)),
    }


def _round_or_none(value: float | None, digits: int = 2) -> float | None:
    """Arrondit une valeur, en préservant l'absence (`None`)."""
    return None if value is None else round(value, digits)
