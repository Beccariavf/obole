"""Parité de la calculatrice de prix juste : la fixture décrit ce que Python DOIT produire.

Le miroir JS (`web/valorisation.js`) est testé sur la **même** fixture par
`web-tests/valorisation-parity.test.js`. Si l'un des deux côtés dérive, un des
deux tests casse — garde-fou contre la divergence silencieuse (même invariant que
la régression).

La fixture est générée par `tests/fixtures/generate_valuation_parity.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from obole.engine import valuation_calc as vc

FIXTURE = Path(__file__).parent / "fixtures" / "valuation_parity.json"
PAYLOAD = json.loads(FIXTURE.read_text(encoding="utf-8"))
CASES = PAYLOAD["cases"]
MATRIX_CASES = PAYLOAD["matrix_cases"]


def _same(actual, expected):
    if expected is None:
        return actual is None
    return actual is not None and abs(actual - expected) < 1e-9


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_python_valuation_matches_fixture(case: dict) -> None:
    fair = vc.fair_price(case["metric"], case["multiple"], case.get("net_debt_per_share"))
    assert _same(fair, case["fair_price"]), f"fair_price {case['name']}"
    margin = vc.safety_margin(fair, case["price"])
    assert _same(margin, case["safety_margin"]), f"safety_margin {case['name']}"
    ret = vc.estimated_return(
        case["metric"],
        case["price"],
        case["growth"],
        case["multiple"],
        case["horizon"],
        case["dividend"],
        case.get("net_debt_per_share"),
    )
    assert _same(ret, case["estimated_return"]), f"estimated_return {case['name']}"
    entry = vc.target_entry_price(
        case["metric"],
        case["growth"],
        case["multiple"],
        case["horizon"],
        case["target"],
        case["dividend"],
        case.get("net_debt_per_share"),
    )
    assert _same(entry, case["target_entry_price"]), f"target_entry_price {case['name']}"


@pytest.mark.parametrize("case", MATRIX_CASES, ids=[c["name"] for c in MATRIX_CASES])
def test_python_matrix_matches_fixture(case: dict) -> None:
    """Grille + rendements + buckets : le miroir JS (matrixGrid/colorBucket) doit
    reproduire ces sorties (verrouillé par web-tests/valorisation-parity.test.js)."""
    growths, multiples = vc.matrix_grid(
        case["growth"],
        case["multiple"],
        case["rows"],
        case["cols"],
        case["growth_step"],
        case["multiple_step"],
    )
    assert growths == case["growths"], f"growths {case['name']}"
    assert multiples == case["multiples"], f"multiples {case['name']}"
    matrix = vc.return_matrix(
        case["metric"],
        case["price"],
        growths,
        multiples,
        case["horizon"],
        case["dividend"],
        case.get("net_debt_per_share"),
    )
    for row, expected in zip(matrix, case["matrix"], strict=True):
        for value, exp in zip(row, expected, strict=True):
            assert _same(value, exp), f"matrix {case['name']}"
    buckets = [
        [vc.color_bucket(v, case["target"], tuple(case["color_ratios"])) for v in row]
        for row in matrix
    ]
    assert buckets == case["buckets"], f"buckets {case['name']}"
