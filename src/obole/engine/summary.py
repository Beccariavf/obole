"""Stats « coup d'œil » d'un indice et de ses membres (vues synthétiques).

Fonctions PURES (pas d'I/O, pas de réseau). Réutilisent regression.py + labels.py
exactement comme une fiche action : les valeurs affichées (position σ, pente,
tendance) sont donc identiques à celles des fiches classiques — symétrie totale
entre un indice, un membre et une action.

Harmonisation « 20 dernières années » : le front calcule les indicateurs d'une
fiche sur la fenêtre visible du slider, ouverte par défaut sur les 20 dernières
années (initRange, mode synchronisé). Pour que les vues d'ensemble (liste
« Mes indices », lignes membres) affichent la MÊME valeur que la fiche à
l'ouverture, la régression est faite ici sur la même fenêtre
(config.REGRESSION_YEARS_DEFAULT). La tendance MM, elle, reste sur l'historique
complet (c'est celle que la fiche continue d'afficher).

Une série trop courte ou invalide ne lève jamais : les indicateurs renvoient
ScoredValue(None, None, None) au lieu de crasher (dégradation gracieuse).
"""

from __future__ import annotations

import pandas as pd

from obole import config
from obole.engine import labels
from obole.engine import regression as reg


def regression_window(series: pd.Series, years: int = config.REGRESSION_YEARS_DEFAULT) -> pd.Series:
    """Fenêtre des N dernières années (même règle que l'initRange du front).

    Cutoff = date du dernier cours − N années calendaires ; on garde les points
    ≥ cutoff. Si l'historique est plus court que N ans, renvoie la série entière
    (le front fait la même chose).
    """
    if series.empty:
        return series
    cutoff = series.index[-1] - pd.DateOffset(years=years)
    return series[series.index >= cutoff]


def member_stats(
    raw: pd.Series,
    adj: pd.Series,
    ma_short: int = config.TREND_MA_SHORT,
    ma_long: int = config.TREND_MA_LONG,
) -> dict:
    """Stats « coup d'œil » d'un membre : position σ, pente, tendance.

    Symétriques avec la fiche à l'ouverture (fenêtre 20 ans, dividendes
    réinvestis) :
    - `distance_sigma` : z du dernier point sur la droite de régression de
      l'AJUSTÉ (fenêtre 20 ans) — la fiche s'ouvre avec la case « Dividendes
      réinvestis » cochée, la droite y est celle de cette série ;
    - `pente` : performance annualisée de la même fenêtre ;
    - `trend` : croisement MM court/long sur le brut (historique complet).
    """
    try:
        s = regression_window(adj).dropna()
        s = s[s > 0]
        regression = reg.fit_log_regression(s)
    except ValueError:
        return _empty()
    z = reg.distance_sigma(regression, float(s.iloc[-1]))
    perf = regression.perf_annual * 100
    bullish = reg.trend_is_bullish(raw, ma_short, ma_long)
    return {
        "distance_sigma": labels.label_distance_sigma(z),
        "pente": labels.label_perf(perf),
        "trend": labels.label_trend(bullish),
    }


def index_stats(
    series: pd.Series,
    ma_short: int = config.TREND_MA_SHORT,
    ma_long: int = config.TREND_MA_LONG,
) -> dict:
    """Stats « coup d'œil » d'un indice : position σ, pente, tendance.

    Régression sur la série synthétique (equal-weight chaînée), limitée à la
    fenêtre 20 ans (comme la fiche à l'ouverture) ; la position σ est le z du
    dernier point de cette fenêtre et la tendance MM reste sur toute la série.
    """
    try:
        s = regression_window(series).dropna()
        s = s[s > 0]
        regression = reg.fit_log_regression(s)
    except ValueError:
        return _empty()
    z = reg.distance_sigma(regression, float(s.iloc[-1]))
    return {
        "distance_sigma": labels.label_distance_sigma(z),
        "pente": labels.label_perf(regression.perf_annual * 100),
        "trend": labels.label_trend(reg.trend_is_bullish(series, ma_short, ma_long)),
    }


def _empty() -> dict:
    return {
        "distance_sigma": labels.label_distance_sigma(None),
        "pente": labels.label_perf(None),
        "trend": labels.label_trend(None),
    }
