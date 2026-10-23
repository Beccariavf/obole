"""Génère la fixture de parité de la calculatrice de prix juste (#20).

Sorties attendues de `engine/valuation_calc.py` (référence Python). Le miroir JS
(`web/valorisation.js`) est testé sur la MÊME fixture par
`web-tests/valorisation-parity.test.js` : si l'un des deux côtés dérive, un des
deux tests casse — garde-fou contre la divergence silencieuse.

Usage : PYTHONPATH=src .venv/bin/python tests/fixtures/generate_valuation_parity.py
"""

from __future__ import annotations

import json
from pathlib import Path

from obole.engine import valuation_calc as vc

OUT = Path(__file__).parent / "valuation_parity.json"


def _case(
    name: str, metric, price, growth, multiple, horizon, dividend=0.0, net_debt_ps=None, target=12.0
) -> dict:
    return {
        "name": name,
        "metric": metric,
        "price": price,
        "growth": growth,
        "multiple": multiple,
        "horizon": horizon,
        "dividend": dividend,
        "net_debt_per_share": net_debt_ps,
        "target": target,
        "fair_price": vc.fair_price(metric, multiple, net_debt_ps),
        "safety_margin": vc.safety_margin(vc.fair_price(metric, multiple, net_debt_ps), price),
        "estimated_return": vc.estimated_return(
            metric, price, growth, multiple, horizon, dividend, net_debt_ps
        ),
        "target_entry_price": vc.target_entry_price(
            metric, growth, multiple, horizon, target, dividend, net_debt_ps
        ),
    }


CASES = [
    # Référence Baggr (matrice reconstituée au 0,01 pt).
    _case("baggr_cell_5.5_8.8", 1.0, 1.0, 5.5, 8.8 / 11.359, 5, 8.2),
    _case("baggr_cell_2.0_1.8", 1.0, 1.0, 2.0, 1.8 / 11.359, 5, 8.2),
    _case("baggr_cell_9.0_15.8", 1.0, 1.0, 9.0, 15.8 / 11.359, 5, 8.2),
    # Cas d'usage réaliste (RI.PA-like).
    _case("realiste_dividendes", 6.45, 58.54, 5.51, 10.04, 5, 7.97),
    _case("realiste_sans_dividendes", 6.45, 58.54, 5.51, 10.04, 5, 0.0),
    _case("croissance_negative", 4.0, 100.0, -3.0, 8.0, 5, 4.0),
    # Multiple d'entreprise (EV/EBITDA) : bridge dette nette par action.
    _case("entreprise_bridge", 10.43, 58.54, 4.0, 11.64, 5, 7.97, 40.6),
    # Cas limites.
    _case("horizon_nul", 5.0, 100.0, 5.0, 20.0, 0),
    _case("cours_nul", 5.0, 0.0, 5.0, 20.0, 5),
    _case("metrique_nulle", 0.0, 100.0, 5.0, 20.0, 5),
    _case("multiple_negatif", 5.0, 100.0, 5.0, -1.0, 5),
]


def _matrix_case(
    name: str,
    metric,
    price,
    growth,
    multiple,
    rows,
    cols,
    gstep,
    mstep,
    horizon,
    dividend=0.0,
    net_debt_ps=None,
    target=12.0,
    ratios=(0.5, 1.0),
) -> dict:
    """Cas de la GRILLE de la matrice + buckets de couleur (miroir JS testé).

    Le front calcule la matrice en direct (matrixGrid/colorBucket) : on verrouille
    la parité des trois fonctions par la même fixture que le reste.
    """
    growths, multiples = vc.matrix_grid(growth, multiple, rows, cols, gstep, mstep)
    matrix = vc.return_matrix(metric, price, growths, multiples, horizon, dividend, net_debt_ps)
    buckets = [[vc.color_bucket(v, target, ratios) for v in row] for row in matrix]
    return {
        "name": name,
        "metric": metric,
        "price": price,
        "growth": growth,
        "multiple": multiple,
        "rows": rows,
        "cols": cols,
        "growth_step": gstep,
        "multiple_step": mstep,
        "horizon": horizon,
        "dividend": dividend,
        "net_debt_per_share": net_debt_ps,
        "target": target,
        "color_ratios": list(ratios),
        "growths": growths,
        "multiples": multiples,
        "matrix": matrix,
        "buckets": buckets,
    }


MATRIX_CASES = [
    _matrix_case("grid_3x3", 5.0, 100.0, 5.0, 10.0, 3, 3, 1.0, 1.0, 5, 4.0),
    _matrix_case("grid_15x15_baggr", 1.0, 1.0, 5.5, 11.359, 15, 15, 0.5, 1.0, 5, 8.2),
    _matrix_case("grid_bridge", 10.43, 58.54, 4.0, 11.64, 3, 3, 0.5, 1.0, 5, 7.97, 40.6),
    _matrix_case("grid_cible_nulle", 5.0, 100.0, 5.0, 10.0, 2, 2, 1.0, 1.0, 5, 0.0, None, 0.0),
]


def main() -> None:
    payload = {
        "description": (
            "Parité calculatrice de prix juste : sorties attendues de "
            "engine/valuation_calc.py, consommées aussi par web/valorisation.js. "
            "Ne pas éditer à la main — régénérer avec generate_valuation_parity.py. "
            "NB : `fair_price` = valeur MÉDIANE (métrique × multiple médian) ; "
            "`target_entry_price` = prix d'ENTRÉE atteignant la cible (KPI de tête)."
        ),
        "cases": CASES,
        "matrix_cases": MATRIX_CASES,
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(CASES)} cas + {len(MATRIX_CASES)} grilles écrits dans {OUT}")


if __name__ == "__main__":
    main()
