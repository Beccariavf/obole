"""Statistiques descriptives du score de satisfaction — la lecture du score.

Fonction PURE (aucune I/O, aucun réseau), numpy/pandas seulement. Le score
lui-même reste défini par `engine/clara_vallis` ; ce module ne dit que ce qu'il
vaut dans l'histoire du titre : son rang.

Rien ici n'est un signal : un percentile décrit une position dans une
distribution, pas une probabilité.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def score_percentile(
    scores: pd.Series | np.ndarray,
    value: float | None,
    min_points: int,
) -> int | None:
    """Rang de `value` dans `scores`, en pourcentage entier 0–100.

    Rang = part des scores **inférieurs ou égaux** à `value`. Le minimum de la
    série est égal à lui-même : son rang vaut `1/n` — 10 % sur dix points, 2 %
    sur soixante —, mais **0 % dès que `n ≥ 200`** (1/200 = 0,5 %, que `round`
    ramène à 0). Un score strictement inférieur au minimum rend 0 lui aussi :
    les deux se confondent, c'est assumé. **0 ne signifie donc pas « sous tout
    l'historique »**, mais « au plus bas de son histoire », ce qui est exact.
    Une valeur égale au maximum rend 100.

    Pas de plancher : relever le minimum à 1 ferait dire à un score
    rigoureusement au plus bas qu'il dépasse encore quelque chose.

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
