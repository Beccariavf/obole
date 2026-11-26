"""Conversion d'une série pandas en liste JSON-compatible.

Utilisé par `serialize.py` (payloads) : même arrondi, même traitement des trous.
Module feuille (numpy/pandas seulement).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def to_values(series: pd.Series) -> list:
    """Liste arrondie à 4 décimales, `None` pour les trous."""
    return [
        None if (v is None or (isinstance(v, float) and np.isnan(v))) else round(float(v), 4)
        for v in series.to_numpy()
    ]
