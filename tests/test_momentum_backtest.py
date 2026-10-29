"""Tests purs du backtest de fiabilité — déterministes, sans réseau."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from obole.engine import momentum_backtest as mb

FEE = 0.1  # % par ordre
LOW = 0.35
HIGH = 0.60
MEASURES = {
    "cagr_pct",
    "volatility_pct",
    "sharpe",
    "sortino",
    "max_drawdown_pct",
    "calmar",
    "invested_pct",
    "trades",
}


def _prices(values, start: str = "2020-01-02") -> pd.Series:
    idx = pd.date_range(start, periods=len(values), freq="B")
    return pd.Series(np.asarray(values, dtype=float), index=idx)


def _scores(values, prices: pd.Series) -> pd.Series:
    return pd.Series(np.asarray(values, dtype=float), index=prices.index)


def _run(prices, scores, fee=FEE):
    return mb.backtest(prices, scores, LOW, HIGH, fee, 0.0)


def _rising(n: int = 300) -> pd.Series:
    return _prices(np.linspace(100, 200, n))


def test_hysteresis_keeps_the_state_between_bounds():
    prices = _rising(8)
    scores = _scores([0.8, 0.5, 0.5, 0.3, 0.3, 0.8, 0.8, 0.5], prices)
    result = _run(prices, scores)
    assert result["strategy"]["positions"] == [
        False,
        True,
        True,  # 0,5 : au-dessus de LOW, l'état investi est conservé
        True,
        False,  # 0,3 : sous LOW, sortie
        False,
        True,
        True,
    ]
    assert result["strategy"]["trades"] == 2


def test_above_high_invests_and_below_low_goes_to_cash():
    prices = _rising(4)
    invested = _run(prices, _scores([0.9, 0.9, 0.9, 0.9], prices))
    assert invested["strategy"]["positions"] == [False, True, True, True]
    cash = _run(prices, _scores([0.1, 0.1, 0.1, 0.1], prices))
    assert cash["strategy"]["positions"] == [False, False, False, False]
    # Les bornes sont STRICTES : exactement 0,60 ne suffit pas à entrer.
    edge = _run(prices, _scores([0.60, 0.60, 0.60, 0.60], prices))
    assert edge["strategy"]["trades"] == 0


def test_signal_of_t_only_decides_t_plus_one():
    prices = _rising(12)
    scores = _scores([0.1, 0.1, 0.1, 0.1, 0.9, 0.9, 0.9, 0.9, 0.1, 0.1, 0.1, 0.1], prices)
    base = _run(prices, scores)["strategy"]
    shifted = _run(prices, scores.shift(1).fillna(0.5))["strategy"]
    first_in = base["positions"].index(True)
    assert shifted["positions"].index(True) == first_in + 1
    first_out = base["positions"].index(False, first_in)
    assert shifted["positions"].index(False, first_in + 1) == first_out + 1


def test_missing_score_is_out_of_market():
    prices = _rising(5)
    scores = _scores([0.9, np.nan, 0.9, 0.9, 0.9], prices)
    result = _run(prices, scores)
    # t=2 lit un score absent : sortie forcée, puis rentrée à t=3.
    assert result["strategy"]["positions"] == [False, True, False, True, True]
    assert result["strategy"]["trades"] == 2


def test_fees_are_paid_per_order():
    prices = _prices([100.0] * 8)  # cours plat : seule la stratégie bouge
    scores = _scores([0.9, 0.9, 0.9, 0.1, 0.1, 0.1, 0.1, 0.1], prices)
    result = _run(prices, scores)["strategy"]
    assert result["trades"] == 1
    # Un aller-retour : 0,1 % à l'entrée ET 0,1 % à la sortie.
    assert result["equity"][-1] == pytest.approx((1 - FEE / 100) ** 2, rel=1e-12)
    assert (1 - result["equity"][-1]) * 100 == pytest.approx(0.2, abs=0.001)


def test_buy_and_hold_follows_the_price():
    prices = _rising(50)
    result = _run(prices, _scores([0.5] * 50, prices))["buy_hold"]
    fee = 1 - FEE / 100
    expected = [fee * (p / prices.iloc[0]) for p in prices]
    assert result["equity"] == pytest.approx(expected, rel=1e-12)
    assert result["invested_pct"] == 100.0
    assert result["trades"] == 1


def test_all_eight_measures_on_both_columns():
    prices = _rising(300)
    scores = _scores(np.tile([0.8, 0.2], 150), prices)
    result = _run(prices, scores)
    for column in ("buy_hold", "strategy"):
        assert MEASURES <= set(result[column])
        for key in MEASURES:
            value = result[column][key]
            if value is not None:
                assert math.isfinite(value)
    assert result["window"]["sessions"] == 300
    assert result["window"]["start"] == "2020-01-02"


def test_neutral_score_never_trades_and_stays_in_cash():
    prices = _rising(30)
    result = _run(prices, _scores([0.5] * 30, prices))["strategy"]
    assert result["trades"] == 0
    assert result["positions"] == [False] * 30
    assert result["equity"] == pytest.approx([1.0] * 30)
    assert result["invested_pct"] == 0.0
    assert result["sharpe"] is None
    assert result["sortino"] is None
    assert result["calmar"] is None


def test_flat_series_has_no_sharpe():
    prices = _prices([100.0] * 60)
    result = _run(prices, _scores([0.5] * 60, prices))["buy_hold"]
    assert result["sharpe"] is None
    assert result["sortino"] is None
    assert result["volatility_pct"] == 0.0
    assert result["max_drawdown_pct"] == 0.0


def test_too_short_window_degrades_without_crashing():
    prices = _prices([100.0])
    result = _run(prices, _scores([0.5], prices))
    assert result["buy_hold"]["cagr_pct"] is None
    assert result["strategy"]["trades"] == 0
    assert result["window"]["sessions"] == 1
