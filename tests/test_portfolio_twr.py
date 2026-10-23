"""TWR chaîné quotidien + top/flop (#17.1) — cœur pur, sans réseau.

Vérifie les propriétés définissantes du TWR (insensibilité au montant et au
calendrier des apports, dividende inclus) et les bornes des périodes.
"""

from __future__ import annotations

import inspect

import pytest

from obole.engine import portfolio as engine


def _tx(ticker, side, date, qty, price, fees=0.0, tx_id=0):
    return {
        "id": tx_id,
        "ticker": ticker,
        "side": side,
        "trade_date": date,
        "quantity": qty,
        "price": price,
        "fees": fees,
    }


DATES = ["2024-01-01", "2024-01-02", "2024-01-03"]
PRICES = {"RI.PA": [100.0, 110.0, 121.0]}


class TestDailyValues:
    def test_buy_then_price_appreciation(self):
        values, flows = engine.daily_values(
            DATES, PRICES, [_tx("RI.PA", "buy", "2024-01-01", 10, 100.0)], []
        )
        assert values == [1000.0, 1100.0, 1210.0]
        assert flows == [1000.0, 0.0, 0.0]  # seul l'achat est un flux externe

    def test_dividend_is_internal_cash_not_a_flow(self):
        values, flows = engine.daily_values(
            DATES,
            PRICES,
            [_tx("RI.PA", "buy", "2024-01-01", 10, 100.0)],
            [{"ticker": "RI.PA", "pay_date": "2024-01-02", "amount": 50.0}],
        )
        assert values == [1000.0, 1150.0, 1260.0]  # +50 de trésorerie à J2
        assert flows == [1000.0, 0.0, 0.0]  # le dividende n'est PAS un flux

    def test_sell_is_a_withdrawal(self):
        values, flows = engine.daily_values(
            DATES,
            PRICES,
            [
                _tx("RI.PA", "buy", "2024-01-01", 10, 100.0),
                _tx("RI.PA", "sell", "2024-01-03", 4, 121.0),
            ],
            [],
        )
        # Le produit de cession est un RETRAIT externe : la valeur ne garde que
        # les 6 titres restants (6 × 121 = 726), le flux est négatif (−484).
        assert values == [1000.0, 1100.0, 726.0]
        assert flows == [1000.0, 0.0, -484.0]
        # Et le rendement du jour reste celui du cours (+10 %), pas de trou.
        assert engine.twr_series(values, flows)[2] == pytest.approx(21.0)

    def test_unknown_ticker_prices_are_skipped(self):
        values, _ = engine.daily_values(
            DATES, {}, [_tx("XX.PA", "buy", "2024-01-01", 10, 100.0)], []
        )
        assert values == [0.0, 0.0, 0.0]  # jamais de crash sans cours

    def test_unpriceable_ticker_flows_are_ignored(self):
        """Un ticker sans cours ne doit ni compter comme apport ni faire plonger
        la courbe : ses flux sont ignorés (cf. régression « achat fantôme »)."""
        tx = [
            _tx("RI.PA", "buy", "2024-01-01", 10, 100.0),
            _tx("GHOST.PA", "buy", "2024-01-01", 100, 10.0),  # 1000 € non coté
        ]
        values, flows = engine.daily_values(DATES, PRICES, tx, [])
        assert values == [1000.0, 1100.0, 1210.0]
        assert flows == [1000.0, 0.0, 0.0]  # l'achat fantôme n'est PAS un apport
        assert engine.twr_series(values, flows)[2] == pytest.approx(21.0)


class TestTwrSeries:
    def test_no_flows_is_flat_zero(self):
        assert engine.twr_series([0.0, 0.0, 0.0], [0.0, 0.0, 0.0]) == [0.0, 0.0, 0.0]

    def test_single_buy_equals_price_return(self):
        values, flows = engine.daily_values(
            DATES, PRICES, [_tx("RI.PA", "buy", "2024-01-01", 10, 100.0)], []
        )
        twr = engine.twr_series(values, flows)
        assert twr[0] == 0.0
        assert twr[1] == pytest.approx(10.0)
        assert twr[2] == pytest.approx(21.0)

    def test_insensitive_to_contribution_amount(self):
        """Doubler l'apport ne change PAS le TWR (propriété définissante)."""
        v1, f1 = engine.daily_values(
            DATES, PRICES, [_tx("RI.PA", "buy", "2024-01-01", 10, 100.0)], []
        )
        v2, f2 = engine.daily_values(
            DATES, PRICES, [_tx("RI.PA", "buy", "2024-01-01", 20, 100.0)], []
        )
        assert engine.twr_series(v1, f1) == pytest.approx(engine.twr_series(v2, f2))

    def test_insensitive_to_contribution_timing(self):
        """Un apport PLUS TARDIF au cours du jour ne change pas non plus le TWR."""
        v1, f1 = engine.daily_values(
            DATES, PRICES, [_tx("RI.PA", "buy", "2024-01-01", 10, 100.0)], []
        )
        v2, f2 = engine.daily_values(
            DATES,
            PRICES,
            [
                _tx("RI.PA", "buy", "2024-01-01", 10, 100.0),
                _tx("RI.PA", "buy", "2024-01-02", 10, 110.0),
            ],
            [],
        )
        assert engine.twr_series(v1, f1) == pytest.approx(engine.twr_series(v2, f2))

    def test_dividend_included_in_return(self):
        v, f = engine.daily_values(
            DATES,
            PRICES,
            [_tx("RI.PA", "buy", "2024-01-01", 10, 100.0)],
            [{"ticker": "RI.PA", "pay_date": "2024-01-02", "amount": 50.0}],
        )
        twr = engine.twr_series(v, f)
        assert twr[1] == pytest.approx(15.0)  # 1100 + 50 = +15 %
        assert twr[2] == pytest.approx(26.0)


class TestBenchmarkSeries:
    def test_buy_and_hold(self):
        assert engine.benchmark_series([100.0, 110.0, 121.0]) == pytest.approx([0.0, 10.0, 21.0])

    def test_none_before_first_price(self):
        series = engine.benchmark_series([None, 100.0, 90.0])
        assert series[0] is None
        assert series[1] == pytest.approx(0.0)
        assert series[2] == pytest.approx(-10.0)

    def test_aligns_with_portfolio_twr(self):
        v, f = engine.daily_values(
            DATES, PRICES, [_tx("RI.PA", "buy", "2024-01-01", 10, 100.0)], []
        )
        assert engine.benchmark_series(PRICES["RI.PA"]) == pytest.approx(engine.twr_series(v, f))


class TestPeriods:
    DATES_LONG = ["2020-12-31", "2021-06-30", "2022-06-30", "2023-06-30", "2024-03-01"]

    def test_max_starts_at_zero(self):
        assert engine.period_start_index(self.DATES_LONG, "max") == 0

    def test_ytd_starts_at_january_first(self):
        assert engine.period_start_index(self.DATES_LONG, "ytd") == 4  # 2024-03-01

    def test_years_shortcut(self):
        # 1A depuis 2024-03-01 -> 2023-03-01 -> premier index >= = 3 (2023-06-30)
        assert engine.period_start_index(self.DATES_LONG, "1a") == 3

    def test_ttm_equals_one_year(self):
        # TTM = 12 derniers mois = même fenêtre que « 1a ».
        assert engine.period_start_index(self.DATES_LONG, "ttm") == 3

    def test_window_longer_than_history(self):
        assert engine.period_start_index(self.DATES_LONG, "5a") == 0

    def test_leap_day_end_does_not_raise(self):
        # Régression : reculer l'année d'un 29/02 vers une année non bissextile
        # levait « day is out of range for month » (500 côté API). Le jour est
        # clampé au dernier jour du mois cible (2023-02-28).
        assert engine.period_start_index(["2023-01-02", "2024-02-29"], "1a") == 1
        # Historique plus long : la fenêtre reste cohérente.
        dates = ["2022-06-01", "2023-06-01", "2024-02-29"]
        assert engine.period_start_index(dates, "1a") == 1

    def test_empty_dates(self):
        assert engine.period_start_index([], "1a") == 0

    def test_period_return_chain(self):
        series = [0.0, 10.0, 21.0]
        # Rendement entre l'index 1 (10 %) et la fin (21 %) = 10 %.
        assert engine.period_return(series, 1) == pytest.approx(10.0)

    def test_period_return_missing_base(self):
        assert engine.period_return([None, None], 1) is None


class TestAnnualized:
    def test_under_one_year_is_none(self):
        assert engine.annualized_return(10.0, 100) is None

    def test_one_year_identity(self):
        assert engine.annualized_return(21.0, 366) == pytest.approx(21.0, abs=0.5)

    def test_two_years_compounds(self):
        # +21 % sur 2 ans -> ~10 %/an.
        assert engine.annualized_return(21.0, 731) == pytest.approx(10.0, abs=0.2)


class TestTopFlop:
    POSITIONS = [
        {"ticker": "A", "quantity": 1},
        {"ticker": "B", "quantity": 1},
        {"ticker": "C", "quantity": 1},
        {"ticker": "D", "quantity": 1},
    ]

    def test_orders_by_perf(self):
        perfs = {"A": 5.0, "B": -3.0, "C": 12.0, "D": 1.0}
        top, flop = engine.top_flop(self.POSITIONS, perfs, 2)
        assert [r["ticker"] for r in top] == ["C", "A"]
        assert [r["ticker"] for r in flop] == ["B", "D"]  # pire en tête

    def test_positions_without_perf_are_dropped(self):
        perfs = {"A": 5.0, "C": None}
        top, flop = engine.top_flop(self.POSITIONS, perfs, 5)
        assert [r["ticker"] for r in top] == ["A"]
        assert [r["ticker"] for r in flop] == ["A"]

    def test_n_zero_returns_empty(self):
        assert engine.top_flop(self.POSITIONS, {"A": 1.0}, 0) == ([], [])


class TestEnginePurity:
    def test_no_io_imports(self):
        src = inspect.getsource(engine)
        assert "from obole.data" not in src
        assert "from obole.services" not in src
        assert "import obole.data" not in src
