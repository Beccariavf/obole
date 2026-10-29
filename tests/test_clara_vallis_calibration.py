"""Calibration de la Clara Vallis — série CAC 40 figée, sans réseau.

La fixture (`fixtures/cac40_daily.csv`) est commitée : le test ne dépend ni de
yfinance ni de la date du jour. Régénérer la fixture est un acte explicite
(`fixtures/generate_cac40_fixture.py`) qui doit s'accompagner d'une revue des
bornes.

Fenêtres mesurées au 2026-10-29 (moyenne de satisfaction) :

    crises  0,174 (2008-09 → 2009-03) · 0,239 (2011-07 → 2011-10)
            0,255 (2020-02 → 2020-04) · 0,174 (2002-06 → 2002-10)
    calmes  0,762 (2017) · 0,859 (2021) · 0,704 (2023)
    neutre  0,515 (2015-06 → 2015-09)
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from obole import config
from obole.engine import clara_vallis as cv

FIXTURE = Path(__file__).parent / "fixtures" / "cac40_daily.csv"

CRISES = {
    "2008-2009": ("2008-09-01", "2009-03-31"),
    "2011": ("2011-07-01", "2011-10-31"),
    "2020": ("2020-02-20", "2020-04-30"),
    "2002": ("2002-06-01", "2002-10-31"),
}
CALMS = {
    "2017": ("2017-01-01", "2017-12-31"),
    "2021": ("2021-01-01", "2021-12-31"),
    "2023": ("2023-01-01", "2023-12-31"),
}
NEUTRAL = {"2015": ("2015-06-01", "2015-09-30")}


@pytest.fixture(scope="module")
def satisfaction() -> pd.Series:
    df = pd.read_csv(FIXTURE, comment="#", parse_dates=["date"], index_col="date")
    prices = df["close"].astype(float)
    return cv.satisfaction_series(prices)


def _mean(series: pd.Series, window: tuple[str, str]) -> float:
    start, end = window
    return float(series.loc[start:end].dropna().mean())


@pytest.mark.parametrize("name,window", list(CRISES.items()))
def test_crisis_windows_are_below_low(satisfaction, name, window):
    assert _mean(satisfaction, window) < config.MOMENTUM_SATISFACTION_LOW


@pytest.mark.parametrize("name,window", list(CALMS.items()))
def test_calm_windows_are_above_high(satisfaction, name, window):
    assert _mean(satisfaction, window) > config.MOMENTUM_SATISFACTION_HIGH


def test_neutral_window_stays_between(satisfaction):
    value = _mean(satisfaction, NEUTRAL["2015"])
    assert config.MOMENTUM_SATISFACTION_LOW < value < config.MOMENTUM_SATISFACTION_HIGH


def test_fixture_is_frozen_and_long_enough():
    df = pd.read_csv(FIXTURE, comment="#", parse_dates=["date"], index_col="date")
    assert len(df) >= 6000
    assert df.index.min().year == 2000
    assert df.index.max().year == 2023
