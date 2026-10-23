"""Construction de la série d'un indice personnalisé (panier d'actions).

Fonctions PURES (pas d'I/O, pas de réseau). Même philosophie que `ratio.py` :
on construit une série de prix synthétique qui passe ensuite dans
`regression.py` exactement comme un cours (une fois construite, un indice
personnalisé se comporte comme un ETF).

Méthode : indice equal-weight CHAÎNÉ en total return (standard des indices
réels — CAC 40, S&P 500). Chaque jour, le rendement du panier est la moyenne
des rendements des membres cotés ce jour-là (pondération renormalisée : un
membre non coté est simplement absent ce jour, comme dans un vrai indice), puis
chaînage Indice_t = Indice_{t-1} × (1 + r̄_t). Les membres arrivent en Adj Close
(dividendes réinvestis) pour comparer équitablement avec des ETF capitalisants.
"""

from __future__ import annotations

import pandas as pd

from obole.engine import ratio as ratio_mod

# Un indice à un seul membre n'est qu'une action : autant la suivre directement.
MIN_MEMBERS = 2
# Cohérent avec fit_log_regression / ratio.py : en deçà, régression non fiable.
MIN_COMMON_POINTS = 30


def aligned_frame(members: dict[str, pd.Series]) -> pd.DataFrame:
    """Aligne tous les membres sur l'UNION de leurs dates calendaires.

    Une colonne par membre (Adj Close, dividendes réinvestis), triée par date ;
    NaN = membre non coté ce jour-là. L'union (et non l'intersection) préserve
    le maximum d'historique : un membre récent ne tronque pas les anciens.

    Lève ValueError si moins de MIN_MEMBERS membres ou si un membre n'a aucun
    prix exploitable (série vide ou non positive).
    """
    if len(members) < MIN_MEMBERS:
        raise ValueError(
            f"Un indice nécessite au moins {MIN_MEMBERS} membres ({len(members)} fournis)"
        )
    cols: dict[str, pd.Series] = {}
    for ticker, s in members.items():
        s = s.dropna()
        if s.empty:
            raise ValueError(f"Pas de prix exploitables pour {ticker.upper()}")
        s = ratio_mod._to_calendar_dates(s)
        s = s[s > 0]
        if s.empty:
            raise ValueError(f"Pas de prix exploitables pour {ticker.upper()}")
        cols[ticker.upper()] = s
    frame = pd.concat(cols, axis=1, join="outer").sort_index()
    return frame


def build_series(frame: pd.DataFrame) -> pd.Series:
    """Construit la série de l'indice (base 100) à partir du panier aligné.

    Chaînage des rendements moyens quotidiens (cf. doc module). Lève ValueError
    si l'historique exploitable est trop court pour une régression fiable.
    """
    if frame.shape[1] < MIN_MEMBERS or frame.shape[0] < 2:
        raise ValueError("Panier insuffisant pour construire un indice")
    rets = frame.pct_change(fill_method=None).iloc[1:]
    r_mean = rets.mean(axis=1, skipna=True).dropna()
    if len(r_mean) < MIN_COMMON_POINTS:
        raise ValueError(
            f"Historique du panier trop court pour un indice fiable ({len(r_mean)} dates)"
        )
    base = pd.Series([100.0], index=[frame.index[0]])
    chained = (1.0 + r_mean).cumprod() * 100.0
    return pd.concat([base, chained]).sort_index()


def span_years(series: pd.Series) -> float:
    """Années couvertes par une série (pour les warnings de fiabilité)."""
    if len(series) < 2:
        return 0.0
    return (series.index[-1] - series.index[0]).days / 365.25


def full_coverage_years(frame: pd.DataFrame) -> float:
    """Années où TOUS les membres cotent (fenêtre « panier complet »).

    En deçà de l'historique total : les membres récents n'ont pas encore
    d'historique complet — l'indice y est calculé sur un sous-ensemble.
    """
    full = frame.notna().all(axis=1)
    if not full.any():
        return 0.0
    idx = frame.index[full]
    return (idx[-1] - idx[0]).days / 365.25
