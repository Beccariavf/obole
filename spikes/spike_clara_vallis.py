"""Calibration de la Clara Vallis — hors ligne, sur la série CAC 40 figée.

Imprime la satisfaction moyenne par fenêtre, la marge par rapport aux bornes, et
rappelle les bornes retenues. Le test `tests/test_clara_vallis_calibration.py`
verrouille le résultat ; ce spike sert à rejouer la mesure après un changement du
moteur ou pour choisir de nouvelles bornes.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from obole import config
from obole.engine import clara_vallis as cv

FIXTURE = Path(__file__).parents[1] / "tests" / "fixtures" / "cac40_daily.csv"

WINDOWS = {
    "crise 2008": ("2008-09-01", "2009-03-31"),
    "crise 2011": ("2011-07-01", "2011-10-31"),
    "crise 2020": ("2020-02-20", "2020-04-30"),
    "crise 2002": ("2002-06-01", "2002-10-31"),
    "calme 2017": ("2017-01-01", "2017-12-31"),
    "calme 2021": ("2021-01-01", "2021-12-31"),
    "calme 2023": ("2023-01-01", "2023-12-31"),
    "neutre 2015": ("2015-06-01", "2015-09-30"),
}


def main() -> None:
    df = pd.read_csv(FIXTURE, comment="#", parse_dates=["date"], index_col="date")
    series = cv.satisfaction_series(df["close"].astype(float))

    print(
        f"bornes : low={config.MOMENTUM_SATISFACTION_LOW} high={config.MOMENTUM_SATISFACTION_HIGH}"
    )
    for name, (start, end) in WINDOWS.items():
        window = series.loc[start:end].dropna()
        mean = float(window.mean())
        if "crise" in name:
            verdict = "OK" if mean < config.MOMENTUM_SATISFACTION_LOW else "DÉBORDE"
            margin = config.MOMENTUM_SATISFACTION_LOW - mean
        elif "calme" in name:
            verdict = "OK" if mean > config.MOMENTUM_SATISFACTION_HIGH else "DÉBORDE"
            margin = mean - config.MOMENTUM_SATISFACTION_HIGH
        else:
            verdict = (
                "OK"
                if config.MOMENTUM_SATISFACTION_LOW < mean < config.MOMENTUM_SATISFACTION_HIGH
                else "DÉBORDE"
            )
            margin = 0.0
        print(f"{name:12s} n={len(window):4d} moyenne={mean:.3f} marge={margin:+.3f} {verdict}")


if __name__ == "__main__":
    main()
