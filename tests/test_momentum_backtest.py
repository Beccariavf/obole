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
# Les sept mesures transportées par chaque colonne (in, out, buy & hold). La
# courbe `equity` et les positions restent internes au moteur.
MEASURES = {
    "cagr_pct",
    "volatility_pct",
    "sharpe",
    "sortino",
    "max_drawdown_pct",
    "calmar",
    "sessions_pct",
}
COLUMNS = ("buy_hold", "in", "out")


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
    assert result["positions"] == [
        False,
        True,
        True,  # 0,5 : au-dessus de LOW, l'état investi est conservé
        True,
        False,  # 0,3 : sous LOW, sortie
        False,
        True,
        True,
    ]
    assert result["trades"] == 2


def test_above_high_invests_and_below_low_goes_to_cash():
    prices = _rising(4)
    invested = _run(prices, _scores([0.9, 0.9, 0.9, 0.9], prices))
    assert invested["positions"] == [False, True, True, True]
    cash = _run(prices, _scores([0.1, 0.1, 0.1, 0.1], prices))
    assert cash["positions"] == [False, False, False, False]
    # Les bornes sont STRICTES : exactement 0,60 ne suffit pas à entrer.
    edge = _run(prices, _scores([0.60, 0.60, 0.60, 0.60], prices))
    assert edge["trades"] == 0


def test_signal_of_t_only_decides_t_plus_one():
    prices = _rising(12)
    scores = _scores([0.1, 0.1, 0.1, 0.1, 0.9, 0.9, 0.9, 0.9, 0.1, 0.1, 0.1, 0.1], prices)
    base = _run(prices, scores)
    shifted = _run(prices, scores.shift(1).fillna(0.5))
    first_in = base["positions"].index(True)
    assert shifted["positions"].index(True) == first_in + 1
    first_out = base["positions"].index(False, first_in)
    assert shifted["positions"].index(False, first_in + 1) == first_out + 1


def test_missing_score_is_out_of_market():
    prices = _rising(5)
    scores = _scores([0.9, np.nan, 0.9, 0.9, 0.9], prices)
    result = _run(prices, scores)
    # t=2 lit un score absent : sortie forcée, puis rentrée à t=3.
    assert result["positions"] == [False, True, False, True, True]
    assert result["trades"] == 2


def test_fees_are_paid_per_order():
    prices = _prices([100.0] * 8)  # cours plat : seule la stratégie bouge
    scores = _scores([0.9, 0.9, 0.9, 0.1, 0.1, 0.1, 0.1, 0.1], prices)
    result = _run(prices, scores)
    assert result["trades"] == 1
    # Un aller-retour : 0,1 % à l'entrée ET 0,1 % à la sortie.
    assert result["strategy_equity"][-1] == pytest.approx((1 - FEE / 100) ** 2, rel=1e-12)
    assert (1 - result["strategy_equity"][-1]) * 100 == pytest.approx(0.2, abs=0.001)


def test_buy_and_hold_follows_the_price():
    prices = _rising(50)
    result = _run(prices, _scores([0.5] * 50, prices))
    fee = 1 - FEE / 100
    expected = [fee * (p / prices.iloc[0]) for p in prices]
    assert result["buy_hold"]["equity"] == pytest.approx(expected, rel=1e-12)
    assert result["buy_hold"]["sessions_pct"] == 100.0
    # Un score toujours neutre ne trade pas : aucune entrée dans la stratégie.
    assert result["trades"] == 0


def test_seven_measures_on_three_columns_and_trades_on_top():
    prices = _rising(300)
    scores = _scores(np.tile([0.8, 0.2], 150), prices)
    result = _run(prices, scores)
    for column in COLUMNS:
        assert MEASURES <= set(result[column])
        for key in MEASURES:
            value = result[column][key]
            if value is not None:
                assert math.isfinite(value)
    # `trades` et le CAGR de la stratégie sortent UNE fois, au premier niveau.
    assert isinstance(result["trades"], int)
    assert result["trades"] >= 1
    assert math.isfinite(result["strategy_cagr_pct"])
    for column in COLUMNS:
        assert "trades" not in result[column]
    assert result["window"]["sessions"] == 300
    assert result["window"]["start"] == "2020-01-02"


def test_neutral_score_never_trades_and_stays_in_cash():
    prices = _rising(30)
    result = _run(prices, _scores([0.5] * 30, prices))
    assert result["trades"] == 0
    assert result["positions"] == [False] * 30
    assert result["strategy_equity"] == pytest.approx([1.0] * 30)
    assert result["strategy_cagr_pct"] == pytest.approx(0.0, abs=1e-12)
    # Rien n'est investi : le panier in est vide, tout est dehors.
    assert result["in"]["sessions_pct"] == 0.0
    assert result["out"]["sessions_pct"] == 100.0


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
    assert result["trades"] == 0
    assert result["strategy_cagr_pct"] is None
    assert result["in"]["cagr_pct"] is None
    assert result["out"]["cagr_pct"] is None
    assert result["window"]["sessions"] == 1


# --- Les deux paniers in / out (#32) ----------------------------------------


def test_in_and_out_partition_the_window():
    prices = _rising(301)
    scores = _scores([0.9, 0.1, 0.1, 0.9, 0.5, 0.5] * 50 + [0.9], prices)
    result = _run(prices, scores)
    sessions = result["window"]["sessions"] - 1
    positions = result["positions"]
    n_in = sum(1 for p in positions[1:] if p)
    n_out = sessions - n_in
    # Les deux courbes comptent exactement leurs séances (+ la base 1).
    assert len(result["in"]["equity"]) == n_in + 1
    assert len(result["out"]["equity"]) == n_out + 1
    assert n_in + n_out == sessions
    # Aucun trou, aucun doublon : les parts somment à 100 % exactement.
    assert result["in"]["sessions_pct"] + result["out"]["sessions_pct"] == pytest.approx(
        100.0, abs=1e-9
    )
    assert result["in"]["sessions_pct"] == pytest.approx(n_in / sessions * 100.0, abs=1e-4)


def test_in_curve_composes_only_the_in_sessions():
    prices = _rising(40)
    scores = _scores([0.9, 0.9, 0.1, 0.1, 0.9, 0.3] * 6 + [0.9, 0.9, 0.9, 0.9], prices)
    result = _run(prices, scores)
    values = prices.to_numpy()
    expected_in = [1.0]
    expected_out = [1.0]
    for t in range(1, len(values)):
        curve = expected_in if result["positions"][t] else expected_out
        curve.append(curve[-1] * values[t] / values[t - 1])
    assert result["in"]["equity"] == pytest.approx(expected_in, rel=1e-12)
    assert result["out"]["equity"] == pytest.approx(expected_out, rel=1e-12)


def test_bucket_cagr_is_annualised_on_its_own_sessions():
    # 1 000 séances, une sur deux investie, +0,1 % par séance in (out plat).
    n = 1001
    values = [100.0]
    for t in range(1, n):
        values.append(values[-1] * (1.001 if t % 2 == 0 else 1.0))
    prices = _prices(values)
    scores = _scores([0.9 if i % 2 else 0.1 for i in range(n)], prices)
    result = _run(prices, scores)
    assert result["in"]["sessions_pct"] == pytest.approx(50.0)
    # CAGR sur les 500 séances du panier : 1,001^252 − 1, pas le calendrier.
    assert result["in"]["cagr_pct"] == pytest.approx((1.001**252 - 1.0) * 100.0, abs=1e-3)
    # Démonstration : le même panier lu sur le calendrier (~4 ans) serait ~2,5×
    # plus faible. Le chiffre ne peut donc pas venir de la durée civile.
    assert result["in"]["cagr_pct"] > 25.0
    assert result["out"]["cagr_pct"] == pytest.approx(0.0, abs=1e-12)


def test_single_session_bucket_does_not_extrapolate_a_cagr():
    """Une séance ne s'annualise pas : `** 252` inventerait un rythme."""
    prices = _rising(20)
    # Le score de t0 fait entrer à t1, puis reste sous LOW : une seule séance in.
    scores = _scores([0.9] + [0.1] * 19, prices)
    result = _run(prices, scores)
    assert len(result["in"]["equity"]) == 2  # la base 1 + un rendement
    assert result["in"]["cagr_pct"] is None
    assert result["in"]["calmar"] is None
    assert result["in"]["volatility_pct"] is None
    assert result["in"]["sessions_pct"] == pytest.approx(round(1 / 19 * 100.0, 4))
    # Même règle pour le buy & hold : deux cours, un seul rendement.
    tiny = _run(_prices([100.0, 110.0]), _scores([0.5, 0.5], _prices([100.0, 110.0])))
    assert tiny["buy_hold"]["cagr_pct"] is None


def test_empty_bucket_has_null_measures_and_zero_share():
    prices = _rising(60)
    result = _run(prices, _scores([0.9] * 60, prices))
    assert result["in"]["sessions_pct"] == 100.0
    assert result["out"]["sessions_pct"] == 0.0
    assert result["out"]["equity"] == []
    for key in MEASURES - {"sessions_pct"}:
        assert result["out"][key] is None
    # Le panier in, lui, est mesurable.
    assert result["in"]["cagr_pct"] is not None
    assert result["in"]["volatility_pct"] is not None


def test_shifting_the_scores_shifts_the_buckets():
    prices = _rising(30)
    scores = _scores([0.9, 0.9, 0.1, 0.1, 0.9] * 6, prices)
    base = _run(prices, scores)
    shifted = _run(prices, scores.shift(1).fillna(0.5))
    # Une séance de décalage : le panier de t est celui de t−1, sans fuite.
    assert shifted["positions"][1:] == base["positions"][:-1]
    base_in = len(base["in"]["equity"]) - 1
    shifted_in = len(shifted["in"]["equity"]) - 1
    assert abs(shifted_in - base_in) <= 1
