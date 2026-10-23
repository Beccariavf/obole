"""Construction de la série d'un ratio A/B entre deux actifs.

Fonction PURE (pas d'I/O). Le ratio est une série de prix synthétique :
une fois construit, il passe dans `regression.py` exactement comme un cours.
On compare deux actifs en « total return » (séries dividendes réinvestis).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from obole import config

# En deçà, la régression du ratio n'est pas fiable (cf. fit_log_regression).
MIN_COMMON_POINTS = 30


def _to_calendar_dates(s: pd.Series) -> pd.Series:
    """Ramène un index daté au jour calendaire (tz-naïf, minuit).

    Indispensable pour aligner deux places différentes : BN.PA est en
    Europe/Paris et SPY en America/New_York — sans ça, aucun timestamp ne
    coïncide et l'historique commun serait vide.
    """
    s = s.copy()
    idx = s.index
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    s.index = idx.normalize()
    return s[~s.index.duplicated(keep="last")]


def aligned_pair(a: pd.Series, b: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Aligne A et B sur leurs dates communes et renvoie le couple (sa, sb).

    `join="inner"` : on ne garde que les dates présentes des deux côtés
    (l'historique commun est borné par le plus jeune des deux actifs).
    Lève ValueError si l'historique commun est trop court ou si B s'annule.
    Base commune de `build_ratio` (série A/B) et de `beta` (rendements A vs B).
    """
    a = _to_calendar_dates(a.dropna())
    b = _to_calendar_dates(b.dropna())
    df = pd.concat([a, b], axis=1, join="inner").dropna()
    if len(df) < MIN_COMMON_POINTS:
        raise ValueError(f"Historique commun trop court pour un ratio fiable ({len(df)} dates)")
    sa, sb = df.iloc[:, 0], df.iloc[:, 1]
    if (sb <= 0).any():
        raise ValueError("Le dénominateur du ratio contient des valeurs nulles/négatives")
    return sa, sb


def build_ratio(a: pd.Series, b: pd.Series) -> pd.Series:
    """Aligne A et B sur leurs dates communes et renvoie la série A/B."""
    sa, sb = aligned_pair(a, b)
    return sa / sb


def beta(sa: pd.Series, sb: pd.Series) -> float | None:
    """Bêta de A par rapport à B : sensibilité de A quand B bouge de 1 %.

    Régression OLS des rendements log quotidiens `r_a = α + β·r_b`, soit
    `β = cov(r_a, r_b) / var(r_b)`. Les deux séries doivent être alignées
    (cf. `aligned_pair`). Fonction PURE (pas d'I/O).

    Renvoie None si moins de `config.BETA_MIN_POINTS` rendements exploitables ou
    si B est constant (var nulle) : β non fiable -> le front l'affiche en neutre.
    """
    ra, rb = _log_returns(sa, sb)
    if ra is None or len(rb) < config.BETA_MIN_POINTS:
        return None
    var_b = float(np.var(rb))  # ddof=0 : mêmes conventions que cov ci-dessous
    if var_b == 0.0:
        return None
    cov = float(np.mean((ra - ra.mean()) * (rb - rb.mean())))
    return cov / var_b


def correlation(sa: pd.Series, sb: pd.Series) -> float | None:
    """Corrélation de Pearson entre A et B : à quel point ils bougent ensemble.

    `ρ = cov(r_a, r_b) / (σ_a · σ_b)`, sur les rendements log quotidiens (mêmes
    que `beta`). Bornée [−1, +1] : ρ≈1 très liés, ρ≈0 décorrélés, ρ<0 inverses.
    Complète `beta` (amplitude) en isolant la SOLIDITÉ du lien. Fonction PURE.

    Renvoie None si moins de `config.CORR_MIN_POINTS` rendements exploitables ou
    si une des deux séries est constante (écart-type nul).
    """
    ra, rb = _log_returns(sa, sb)
    if ra is None or len(ra) < config.CORR_MIN_POINTS:
        return None
    std_a = float(np.std(ra))
    std_b = float(np.std(rb))
    if std_a == 0.0 or std_b == 0.0:
        return None
    cov = float(np.mean((ra - ra.mean()) * (rb - rb.mean())))
    return cov / (std_a * std_b)


def _log_returns(sa: pd.Series, sb: pd.Series):
    """Rendements log quotidiens alignés de A et B (couple filtré des NaN/inf).

    Base commune de `beta` et `correlation`. Renvoie (None, None) si séries vides.
    """
    ra = np.diff(np.log(sa.to_numpy(dtype=float)))
    rb = np.diff(np.log(sb.to_numpy(dtype=float)))
    mask = np.isfinite(ra) & np.isfinite(rb)
    ra, rb = ra[mask], rb[mask]
    if len(ra) == 0:
        return None, None
    return ra, rb


def common_years(ratio: pd.Series) -> float:
    """Nombre d'années couvertes par l'historique commun (pour les warnings)."""
    if len(ratio) < 2:
        return 0.0
    return (ratio.index[-1] - ratio.index[0]).days / 365.25
