"""Génère `tests/fixtures/regression_parity.json` (fixture de parité Python ↔ JS).

La fixture fige des cas (dates, prix) et les sorties attendues de
`engine.regression.fit_log_regression`. Deux tests la consomment :
- `tests/test_regression_parity_fixture.py` (Python, la source de vérité) ;
- `web-tests/regression-parity.test.js` (JS, la fonction `olsLog` du front).

Usage : `.venv/bin/python tests/fixtures/generate_regression_parity.py`

Générateur déterministe (LCG maison, pas de dépendance aléatoire) : relancer le
script doit produire un fichier identique.
"""

from __future__ import annotations

import json
import math
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from obole.engine.regression import fit_log_regression

OUT = Path(__file__).with_name("regression_parity.json")
N_POINTS = 250
START = date(2015, 1, 1)


def _lcg(seed: int):
    """Générateur pseudo-aléatoire déterministe (renvoie des flottants dans [0, 1[)."""
    state = seed

    def nxt() -> float:
        nonlocal state
        state = (1103515245 * state + 12345) % (2**31)
        return state / 2**31

    return nxt


def _dates(n: int) -> list[str]:
    return [(START + timedelta(days=i)).isoformat() for i in range(n)]


def _case(name: str, dates: list[str], prices: list[float]) -> dict:
    # Les prix sont arrondis AVANT la régression : la fixture doit décrire ce que
    # les deux implémentations consomment réellement (sinon la parité est fausse).
    arrondis = [round(p, 6) for p in prices]
    series = pd.Series(arrondis, index=pd.to_datetime(dates))
    reg = fit_log_regression(series)
    return {
        "name": name,
        "dates": dates,
        "prices": arrondis,
        "a": reg.a,
        "b": reg.b,
        "sigma": reg.sigma,
    }


def main() -> None:
    dates = _dates(N_POINTS)

    # 1. Croissance exponentielle pure : sigma ≈ 0, la droite doit être exacte.
    tendance = [100.0 * math.exp(0.05 * i / 365.25) for i in range(N_POINTS)]

    # 2. Tendance + bruit multiplicatif déterministe (cas réaliste).
    rand = _lcg(20260917)
    bruite = [80.0 * math.exp(0.03 * i / 365.25 + 0.08 * (rand() - 0.5)) for i in range(N_POINTS)]

    # 3. Marché baissier + forte volatilité (σ élevé, pente négative).
    rand = _lcg(424242)
    baissier = [
        150.0 * math.exp(-0.02 * i / 365.25 + 0.25 * (rand() - 0.5)) for i in range(N_POINTS)
    ]

    payload = {
        "description": (
            "Parité régression : sorties attendues de fit_log_regression (Python), "
            "consommées aussi par olsLog (JS). Ne pas éditer à la main — "
            "régénérer avec generate_regression_parity.py."
        ),
        "cases": [
            _case("croissance_exponentielle", dates, tendance),
            _case("tendance_bruitee", dates, bruite),
            _case("marche_baissier_volatil", dates, baissier),
        ],
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Écrit {OUT}")


if __name__ == "__main__":
    main()
