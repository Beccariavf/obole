"""Tests purs de la reconstruction des multiples (engine/valuation, sans réseau)."""

from __future__ import annotations

import pandas as pd
import pytest

from obole.engine import valuation as v


def _series(values: dict[str, float]) -> pd.Series:
    """Série indexée par Timestamp de clôture (année -> valeur)."""
    return pd.Series({pd.Timestamp(f"{y}-12-31"): val for y, val in values.items()})


def _daily_price(level: float, start="2020-01-01", end="2024-12-31") -> pd.Series:
    idx = pd.date_range(start, end, freq="D")
    return pd.Series([level] * len(idx), index=idx)


def test_per_reconstruct():
    # 100 actions, prix 10 -> market cap 1000. Bénéfice 100 -> PER = 10.
    rows = {
        "shares": _series({2023: 100, 2022: 100}),
        "net_income": _series({2023: 100, 2022: 80}),
    }
    table = pd.DataFrame()  # non utilisé par build directement
    df = v.build(table, rows, _daily_price(10.0))
    assert df.loc["PER"][2023] == pytest.approx(10.0)  # 1000/100
    assert df.loc["PER"][2022] == pytest.approx(12.5)  # 1000/80


def test_ev_ebitda_and_fcf_yield():
    rows = {
        "shares": _series({2023: 100}),
        "ebitda": _series({2023: 200}),
        "net_debt": _series({2023: 500}),
        "fcf": _series({2023: 50}),
    }
    df = v.build(pd.DataFrame(), rows, _daily_price(10.0))
    # market cap 1000, EV = 1000 + 500 = 1500 ; EV/EBITDA = 1500/200 = 7.5
    assert df.loc["EV / EBITDA"][2023] == pytest.approx(7.5)
    # FCF yield = 50/1000 = 5 %
    assert df.loc["FCF yield"][2023] == pytest.approx(5.0)


def test_negative_earnings_gives_none_not_inf():
    rows = {
        "shares": _series({2023: 100}),
        "net_income": _series({2023: -50}),  # déficit -> PER sans sens
        "fcf": _series({2023: -10}),
    }
    df = v.build(pd.DataFrame(), rows, _daily_price(10.0))
    # PER absent (ligne entièrement vide retirée) ou None, jamais un nombre négatif.
    if "PER" in df.index:
        assert pd.isna(df.loc["PER"][2023])
    if "FCF yield" in df.index:
        assert pd.isna(df.loc["FCF yield"][2023])


def test_no_shares_gives_empty():
    assert v.build(pd.DataFrame(), {"net_income": _series({2023: 100})}, _daily_price(10.0)).empty


def test_price_before_ipo_skipped():
    # Clôture 2023 mais prix commence en 2024 -> aucun cours asof -> exercice ignoré.
    rows = {"shares": _series({2023: 100}), "net_income": _series({2023: 100})}
    price = _daily_price(10.0, start="2024-01-01", end="2024-12-31")
    assert v.build(pd.DataFrame(), rows, price).empty
