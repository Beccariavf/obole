"""Parité de la régression : la fixture décrit ce que Python DOIT produire.

Le miroir JS (`web/app.js::olsLog`) est testé sur la **même** fixture par
`web-tests/regression-parity.test.js`. Si l'un des deux côtés dérive, un des
deux tests casse — c'est le garde-fou contre la divergence silencieuse.

La fixture est générée par `tests/fixtures/generate_regression_parity.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from obole.engine.regression import fit_log_regression

FIXTURE = Path(__file__).parent / "fixtures" / "regression_parity.json"
CASES = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_python_regression_matches_fixture(case: dict) -> None:
    series = pd.Series(case["prices"], index=pd.to_datetime(case["dates"]))
    reg = fit_log_regression(series)
    # Tolérance serrée : même code que le générateur, la fixture doit être
    # exactement à jour (un changement de formule la rend périmée -> test rouge).
    assert reg.a == pytest.approx(case["a"], abs=1e-12)
    assert reg.b == pytest.approx(case["b"], abs=1e-12)
    assert reg.sigma == pytest.approx(case["sigma"], abs=1e-12)
