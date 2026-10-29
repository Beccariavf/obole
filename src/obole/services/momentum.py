"""Payload « momentum » (Clara Vallis) : séries de satisfaction prêtes à tracer.

Le calcul vit dans `engine/clara_vallis` (pur) ; ce module l'orchestre, l'aligne
sur la grille du graphe (`chart.dates`) et le cache par référence — un ticker,
ou `INDEX:<id>` pour un indice personnalisé.

Les séries sont calculées en PLEINE résolution puis réindexées sur la grille
décimée : un walk-forward calculé sur la série déjà décimée ne couvrirait pas
250 séances réelles (même piège que les moyennes mobiles, cf. `chart_payload`).
"""

from __future__ import annotations

import pandas as pd

from obole import config
from obole.data import cache
from obole.engine import clara_vallis as cv

_KIND = "momentum"


def _values(series: pd.Series) -> list:
    """Liste JSON-compatible, arrondie à 4 décimales, `None` pour les trous."""
    return [None if pd.isna(v) else round(float(v), 4) for v in series.to_numpy()]


def momentum_payload(
    ref: str,
    raw: pd.Series,
    adjusted: pd.Series | None,
    grid: pd.DatetimeIndex,
) -> dict:
    """Bloc `momentum` d'une fiche, aligné sur la grille `grid` du graphe.

    `ref` sert de clé de cache (`RI.PA`, `INDEX:7`). Le walk-forward est calculé
    une fois par jour et par référence ; `cache.invalidate(ref)` le purge avec
    les prix.
    """
    cached = cache.get(ref, _KIND, config.TTL_PRICES)
    if cached is not None:
        return cached

    window = config.MOMENTUM_WINDOW
    raw_series = cv.satisfaction_series(raw, window)
    adj_series = cv.satisfaction_series(adjusted, window) if adjusted is not None else None

    score_raw = cv.satisfaction_score(raw, window)
    tail = raw_series.index[-window:]
    payload = {
        "score_raw": score_raw.value,
        "score_adj": (
            cv.satisfaction_score(adjusted, window).value if adjusted is not None else None
        ),
        "n_used": score_raw.n_used,
        "short_history": score_raw.short_history,
        "raw": _values(raw_series.reindex(grid)),
        "adj": _values(adj_series.reindex(grid)) if adj_series is not None else None,
        "year": {
            "dates": [d.strftime("%Y-%m-%d") for d in tail],
            "raw": _values(raw_series.reindex(tail)),
            "adj": _values(adj_series.reindex(tail)) if adj_series is not None else None,
        },
    }
    cache.put(ref, _KIND, payload)
    return payload
