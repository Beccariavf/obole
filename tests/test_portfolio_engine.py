"""Cœur pur du portefeuille (#17.0) — recalcul des positions. Sans réseau."""

from __future__ import annotations

import tempfile

import pytest

from obole import config
from obole.data import portfolio as portfolio_data
from obole.engine import portfolio as engine
from obole.services import portfolio as service


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


class TestPositionsPure:
    """engine/portfolio — pur, sans I/O."""

    def test_no_transactions(self):
        assert engine.positions_from_transactions([]) == []

    def test_single_buy(self):
        (pos,) = engine.positions_from_transactions([_tx("RI.PA", "buy", "2024-01-02", 10, 100.0)])
        assert pos.ticker == "RI.PA"
        assert pos.quantity == 10
        assert pos.pru == 100.0
        assert pos.cost_basis == 1000.0
        assert pos.realized == 0.0

    def test_multiple_buys_weighted_pru(self):
        (pos,) = engine.positions_from_transactions(
            [
                _tx("RI.PA", "buy", "2024-01-02", 10, 100.0),
                _tx("RI.PA", "buy", "2024-02-02", 10, 120.0),
            ]
        )
        assert pos.quantity == 20
        assert pos.pru == 110.0  # (1000 + 1200) / 20

    def test_fees_included_in_cost(self):
        (pos,) = engine.positions_from_transactions(
            [_tx("RI.PA", "buy", "2024-01-02", 10, 100.0, fees=5.0)]
        )
        assert pos.cost_basis == 1005.0
        assert pos.pru == 100.5

    def test_partial_sell_reduces_quantity_and_realizes(self):
        (pos,) = engine.positions_from_transactions(
            [
                _tx("RI.PA", "buy", "2024-01-02", 10, 100.0),
                _tx("RI.PA", "sell", "2024-03-02", 4, 150.0),
            ]
        )
        assert pos.quantity == 6
        assert pos.pru == 100.0  # le PRU ne bouge pas sur une vente
        assert pos.realized == 4 * (150.0 - 100.0)  # 200

    def test_full_sell_is_dropped(self):
        positions = engine.positions_from_transactions(
            [
                _tx("RI.PA", "buy", "2024-01-02", 10, 100.0),
                _tx("RI.PA", "sell", "2024-03-02", 10, 120.0),
            ]
        )
        assert positions == []

    def test_sell_without_holding_is_ignored(self):
        """Long-only : une vente sans position préalable ne peut rien vendre."""
        (pos,) = engine.positions_from_transactions(
            [
                _tx("RI.PA", "sell", "2024-01-02", 5, 100.0),
                _tx("RI.PA", "buy", "2024-02-02", 10, 100.0),
            ]
        )
        assert pos.quantity == 10
        assert pos.pru == 100.0
        assert pos.realized == 0.0

    def test_chronological_order_matters(self):
        """La vente est datée AVANT le second achat : le PRU appliqué est celui
        de l'achat initial, pas du mélange."""
        (pos,) = engine.positions_from_transactions(
            [
                _tx("RI.PA", "buy", "2024-01-02", 10, 100.0),
                _tx("RI.PA", "sell", "2024-02-01", 5, 200.0),
                _tx("RI.PA", "buy", "2024-03-01", 5, 300.0),
            ]
        )
        assert pos.quantity == 10
        assert pos.realized == 5 * (200.0 - 100.0)  # vente au PRU initial (100)
        # Coût restant : 500 (initial) + 1500 (nouvel achat)
        assert pos.cost_basis == 2000.0

    def test_pru_none_when_fully_sold(self):
        pos = engine.Position(ticker="RI.PA", quantity=0.0, cost_basis=0.0, realized=100.0)
        assert pos.pru is None


class TestEnginePurity:
    """Invariant : engine/portfolio.py n'importe ni data/ ni services/."""

    def test_no_io_imports(self):
        import inspect

        src = inspect.getsource(engine)
        assert "from obole.data" not in src
        assert "from obole.services" not in src
        assert "import obole.data" not in src


class TestServicePositions:
    """services/portfolio.positions — assemblage data + engine."""

    @pytest.fixture(autouse=True)
    def _isolated_db(self):
        _orig = config.CACHE_DB
        config.CACHE_DB = tempfile.mktemp(suffix=".sqlite")
        yield
        config.CACHE_DB = _orig

    def test_empty_account(self):
        acc = portfolio_data.create_account("PEA")
        assert service.positions(acc) == []

    def test_weighted_positions_from_db(self):
        acc = portfolio_data.create_account("PEA")
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2024-01-02", 10, 100.0)
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2024-02-02", 10, 120.0)
        (row,) = service.positions(acc)
        assert row["ticker"] == "RI.PA"
        assert row["quantity"] == 20
        assert row["pru"] == 110.0

    def test_consolidated_across_accounts(self):
        pea = portfolio_data.create_account("PEA")
        cto = portfolio_data.create_account("CTO")
        portfolio_data.add_transaction(pea, "RI.PA", "buy", "2024-01-02", 10, 100.0)
        portfolio_data.add_transaction(cto, "RI.PA", "buy", "2024-01-02", 10, 120.0)
        (row,) = service.positions(None)  # vue « Tous »
        assert row["quantity"] == 20
        assert row["pru"] == 110.0

    def test_sold_position_omitted(self):
        acc = portfolio_data.create_account("PEA")
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2024-01-02", 10, 100.0)
        portfolio_data.add_transaction(acc, "RI.PA", "sell", "2024-03-02", 10, 120.0)
        assert service.positions(acc) == []
