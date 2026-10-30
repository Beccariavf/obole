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
