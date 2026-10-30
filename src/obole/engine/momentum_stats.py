"""Statistiques descriptives du score de satisfaction — la lecture du score.

Fonctions PURES (aucune I/O, aucun réseau), numpy/pandas seulement. Le score
lui-même reste défini par `engine/clara_vallis` ; ce module ne dit que ce qu'il
vaut dans l'histoire du titre : son rang (percentile), puis le rendement qui a
suivi les mêmes zones de score.

Rien ici n'est un signal : ce sont des statistiques de l'échantillon passé.
Un percentile décrit une position dans une distribution, pas une probabilité ;
un rendement conditionnel décrit ce qui s'est produit, pas ce qui va suivre.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Un bloc de statistiques par zone : `None` quand la zone n'a aucune fenêtre
# complète (historique plus court que l'horizon, ou zone jamais atteinte).
Block = dict[str, float | int] | None


def score_percentile(
    scores: pd.Series | np.ndarray,
    value: float | None,
    min_points: int,
) -> int | None:
    """Rang de `value` dans `scores`, en pourcentage entier 0–100.

    Rang = part des scores **inférieurs ou égaux** à `value`. Deux bornes à ne
    pas confondre :

    - le minimum de la série garde son rang `1/n` (le score est égal à lui-même),
      et non 0 ;
    - une valeur **strictement inférieure** au minimum rend 0, une valeur égale
      au maximum rend 100.

    Les NaN sont ignorés. `None` si la série utile compte moins de `min_points`
    points ou si `value` est absente : un rang sur trois points ne veut rien
    dire, et un rang sans score n'existe pas.
    """
    sample = np.asarray(scores, dtype=float).ravel()
    sample = sample[np.isfinite(sample)]
    if value is None or not np.isfinite(float(value)) or sample.size < min_points:
        return None
    rank = 100.0 * float(np.count_nonzero(sample <= float(value))) / float(sample.size)
    return int(min(100, max(0, round(rank))))


def _independent_episodes(starts: np.ndarray, horizon: int) -> int:
    """Fenêtres retenues quand deux démarrages sont espacés d'au moins `horizon`.

    Parcours glouton du plus ancien au plus récent : chaque fenêtre retenue
    écarte toutes celles qui commencent avant qu'elle ne soit terminée.
    """
    count = 0
    last: int | None = None
    for start in starts:
        position = int(start)
        if last is None or position - last >= horizon:
            count += 1
            last = position
    return count


def _block(returns: np.ndarray, starts: np.ndarray, horizon: int) -> Block:
    """Médiane, 10e et 90e centiles (en %) et épisodes indépendants d'un panier."""
    if returns.size == 0:
        return None
    return {
        "median_pct": round(float(np.median(returns)) * 100.0, 2),
        "p10_pct": round(float(np.percentile(returns, 10)) * 100.0, 2),
        "p90_pct": round(float(np.percentile(returns, 90)) * 100.0, 2),
        "episodes": _independent_episodes(starts, horizon),
    }


def conditional_forward_returns(
    prices: pd.Series,
    scores: pd.Series,
    low: float,
    high: float,
    horizon: int,
) -> dict:
    """Rendement des `horizon` séances qui ont suivi chaque zone de score.

    Pour chaque séance `t` dont le score est connu, le rendement réalisé est
    `P[t + h] / P[t] − 1`. La séance est rangée dans la zone de son score, avec
    les MÊMES bornes que la jauge : sous `low` la zone basse, au-dessus de `high`
    la zone haute, sinon la zone neutre. Les fenêtres sans cotation complète
    (trou dans la série, horizon qui dépasse la fin) sont ignorées.

    **Les fenêtres se chevauchent.** Sur un horizon d'un an, deux séances
    voisines partagent 251 des 252 séances qui suivent : toutes les fenêtres
    participent aux centiles, qui décrivent donc la dispersion des fenêtres
    réelles, pas celle d'un échantillon d'observations indépendantes. C'est
    pourquoi `episodes` est compté À PART : une fenêtre n'y compte que si elle
    démarre au moins `horizon` séances après la précédente retenue.

    Rend, par zone (`bas`, `neutre`, `haut`) et pour le repère global
    (`baseline`), un bloc `{median_pct, p10_pct, p90_pct, episodes}` — les
    centiles en pourcentage — ou `None` pour une zone sans fenêtre complète.

    Lève `ValueError` si `horizon` vaut moins d'une séance.
    """
    if horizon < 1:
        raise ValueError("horizon doit valoir au moins une séance")

    empty = {"zones": {"bas": None, "neutre": None, "haut": None}, "baseline": None}
    clean = prices.dropna()
    clean = clean[clean > 0]
    if len(clean) <= horizon:
        return empty

    values = clean.to_numpy(dtype=float)
    aligned = scores.reindex(clean.index).to_numpy(dtype=float)
    forward = values[horizon:] / values[:-horizon] - 1.0
    past_score = aligned[:-horizon]
    usable = np.isfinite(forward) & np.isfinite(past_score)
    starts = np.flatnonzero(usable)
    if starts.size == 0:
        return empty

    zone_of = past_score[starts]
    lower = zone_of < low
    upper = zone_of > high
    middle = ~lower & ~upper
    return {
        "zones": {
            "bas": _block(forward[starts[lower]], starts[lower], horizon),
            "neutre": _block(forward[starts[middle]], starts[middle], horizon),
            "haut": _block(forward[starts[upper]], starts[upper], horizon),
        },
        "baseline": _block(forward[starts], starts, horizon),
    }
