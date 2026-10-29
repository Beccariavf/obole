"""Coût du walk-forward Clara Vallis — mesure hors ligne, sans réseau.

Mesures du 2026-10-29 (Mac local, numpy vectorisé, blocs de 2 000 dates) :

    2 500 séances    ~6 ms
    5 000 séances   ~11 ms
    8 000 séances   ~18 ms
   12 000 séances   ~25 ms

Le découpage en blocs borne la mémoire : une vue (9 000, 250) garde ~110 Mo de
pointe, un bloc n'en garde qu'une vingtaine. Relancer ce script après un
changement du moteur pour vérifier que le coût reste linéaire.
"""

import time

import numpy as np
import pandas as pd

from obole.engine import clara_vallis as cv


def _random_walk(n: int, seed: int = 0) -> pd.Series:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("1995-01-02", periods=n, freq="B")
    return pd.Series(50 * np.exp(np.cumsum(rng.normal(0, 0.01, n))), index=idx)


def main() -> None:
    for n in (2500, 5000, 8000, 12000):
        s = _random_walk(n)
        t0 = time.perf_counter()
        out = cv.satisfaction_series(s)
        ms = (time.perf_counter() - t0) * 1000
        print(f"{n:6d} séances  {ms:7.2f} ms  score={out.iloc[-1]:.3f}")


if __name__ == "__main__":
    main()
