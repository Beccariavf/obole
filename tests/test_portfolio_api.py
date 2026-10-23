"""Portefeuille — routes API (#17.0). Sans réseau.

Frontière fine : validation HTTP + sérialisation. 422 sur entrée invalide,
404 sur identifiant inconnu. Le cache est isolé sur une base temporaire.
"""

from __future__ import annotations

import tempfile

import pytest
from fastapi.testclient import TestClient

from obole import config


@pytest.fixture(autouse=True)
def _isolated_db():
    _orig = config.CACHE_DB
    config.CACHE_DB = tempfile.mktemp(suffix=".sqlite")
    yield
    config.CACHE_DB = _orig


@pytest.fixture
def client():
    from obole.api.app import app

    return TestClient(app)


def _account(client, name="PEA") -> int:
    r = client.post("/api/portfolio/accounts", json={"name": name})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _tx(client, account_id, **over):
    body = {
        "account_id": account_id,
        "ticker": "RI.PA",
        "side": "buy",
        "trade_date": "2024-01-02",
        "quantity": 10,
        "price": 100.0,
    }
    body.update(over)
    return client.post("/api/portfolio/transactions", json=body)


class TestAccountsRoutes:
    def test_create_and_list(self, client):
        acc = _account(client)
        rows = client.get("/api/portfolio/accounts").json()
        assert rows[0]["id"] == acc and rows[0]["currency"] == "EUR"

    def test_empty_name_422(self, client):
        r = client.post("/api/portfolio/accounts", json={"name": "  "})
        assert r.status_code == 422

    def test_delete_unknown_404(self, client):
        assert client.delete("/api/portfolio/accounts/999").status_code == 404

    def test_delete_known_ok(self, client):
        acc = _account(client)
        assert client.delete(f"/api/portfolio/accounts/{acc}").status_code == 200


class TestTransactionsRoutes:
    def test_create_returns_id(self, client):
        acc = _account(client)
        r = _tx(client, acc)
        assert r.status_code == 200
        assert isinstance(r.json()["id"], int)

    def test_list_filters_by_account(self, client):
        a = _account(client, "PEA")
        b = _account(client, "CTO")
        _tx(client, a)
        _tx(client, b, ticker="AI.PA")
        assert len(client.get(f"/api/portfolio/transactions?account_id={a}").json()) == 1
        assert len(client.get("/api/portfolio/transactions").json()) == 2

    @pytest.mark.parametrize(
        "over",
        [
            {"trade_date": "02/01/2024"},
            {"quantity": 0},
            {"quantity": -1},
            {"price": -5},
            {"side": "hold"},
            {"ticker": " "},
        ],
    )
    def test_invalid_entries_422(self, client, over):
        acc = _account(client)
        assert _tx(client, acc, **over).status_code == 422

    def test_unknown_account_422(self, client):
        assert _tx(client, 999).status_code == 422

    def test_update_and_delete(self, client):
        acc = _account(client)
        tx_id = _tx(client, acc).json()["id"]
        r = client.put(
            f"/api/portfolio/transactions/{tx_id}",
            json={
                "account_id": acc,
                "ticker": "RI.PA",
                "side": "buy",
                "trade_date": "2024-01-05",
                "quantity": 12,
                "price": 101.0,
            },
        )
        assert r.status_code == 200
        assert (
            client.get(f"/api/portfolio/transactions?account_id={acc}").json()[0]["quantity"] == 12
        )
        assert client.delete(f"/api/portfolio/transactions/{tx_id}").status_code == 200
        assert client.delete(f"/api/portfolio/transactions/{tx_id}").status_code == 404


class TestDividendsRoutes:
    def test_create_and_list(self, client):
        acc = _account(client)
        r = client.post(
            "/api/portfolio/dividends",
            json={"account_id": acc, "ticker": "RI.PA", "pay_date": "2024-06-15", "amount": 42.0},
        )
        assert r.status_code == 200
        rows = client.get(f"/api/portfolio/dividends?account_id={acc}").json()
        assert rows[0]["amount"] == 42.0

    @pytest.mark.parametrize(
        "over",
        [
            {"pay_date": "15/06/2024"},
            {"amount": -1},
            {"status": "maybe"},
        ],
    )
    def test_invalid_entries_422(self, client, over):
        acc = _account(client)
        body = {"account_id": acc, "ticker": "RI.PA", "pay_date": "2024-06-15", "amount": 42.0}
        body.update(over)
        assert client.post("/api/portfolio/dividends", json=body).status_code == 422

    def test_update_unknown_404(self, client):
        acc = _account(client)
        r = client.put(
            "/api/portfolio/dividends/999",
            json={"account_id": acc, "ticker": "RI.PA", "pay_date": "2024-06-15", "amount": 1.0},
        )
        assert r.status_code == 404


class TestPositionsRoute:
    def test_positions_weighted(self, client):
        acc = _account(client)
        _tx(client, acc, quantity=10, price=100.0)
        _tx(client, acc, quantity=10, price=120.0)
        (row,) = client.get(f"/api/portfolio/positions?account_id={acc}").json()
        assert row["ticker"] == "RI.PA"
        assert row["quantity"] == 20
        assert row["pru"] == 110.0

    def test_positions_consolidated(self, client):
        a = _account(client, "PEA")
        b = _account(client, "CTO")
        _tx(client, a, quantity=10, price=100.0)
        _tx(client, b, quantity=10, price=120.0)
        (row,) = client.get("/api/portfolio/positions").json()
        assert row["quantity"] == 20
        assert row["pru"] == 110.0

    def test_empty_account(self, client):
        acc = _account(client)
        assert client.get(f"/api/portfolio/positions?account_id={acc}").json() == []

    def test_sold_position_omitted(self, client):
        acc = _account(client)
        _tx(client, acc, quantity=10, price=100.0)
        _tx(client, acc, side="sell", quantity=10, price=120.0)
        assert client.get(f"/api/portfolio/positions?account_id={acc}").json() == []


class TestTagsRoutes:
    """#17.6 — étiquettes : écriture, filtre, liste, étiquetage d'une position."""

    def test_transaction_tag_roundtrip(self, client):
        acc = _account(client)
        _tx(client, acc, tag="Actions dividende")
        (row,) = client.get(f"/api/portfolio/transactions?account_id={acc}").json()
        assert row["tag"] == "Actions dividende"

    def test_tag_too_long_422(self, client):
        acc = _account(client)
        assert _tx(client, acc, tag="x" * (config.PORTFOLIO_TAG_MAX + 1)).status_code == 422

    def test_list_tags(self, client):
        acc = _account(client)
        _tx(client, acc, ticker="RI.PA", tag="Croissance")
        _tx(client, acc, ticker="AI.PA", tag="dividende")
        _tx(client, acc, ticker="OR.PA")
        assert client.get("/api/portfolio/tags").json() == {"tags": ["Croissance", "dividende"]}

    def test_list_tags_scoped_by_account(self, client):
        a = _account(client, "PEA")
        b = _account(client, "CTO")
        _tx(client, a, ticker="RI.PA", tag="Div")
        _tx(client, b, ticker="OR.PA", tag="Croissance")
        assert client.get(f"/api/portfolio/tags?account_id={a}").json() == {"tags": ["Div"]}
        assert client.get(f"/api/portfolio/tags?account_id={b}").json() == {"tags": ["Croissance"]}
        assert client.get("/api/portfolio/tags").json() == {"tags": ["Croissance", "Div"]}

    def test_filter_transactions_by_tag(self, client):
        a = _account(client, "PEA")
        b = _account(client, "CTO")
        _tx(client, a, ticker="RI.PA", tag="Div")
        _tx(client, b, ticker="OR.PA", tag="Div")
        _tx(client, a, ticker="AI.PA")
        url = "/api/portfolio/transactions?tag=Div"
        assert len(client.get(url).json()) == 2
        assert len(client.get(f"{url}&account_id={a}").json()) == 1

    def test_positions_expose_tags(self, client):
        acc = _account(client)
        _tx(client, acc, quantity=10, price=100.0, tag="Actions dividende")
        (row,) = client.get(f"/api/portfolio/positions?account_id={acc}").json()
        assert row["tags"] == ["Actions dividende"]

    def test_positions_filtered_by_tag(self, client):
        acc = _account(client)
        _tx(client, acc, ticker="RI.PA", tag="Div")
        _tx(client, acc, ticker="AI.PA")
        rows = client.get(f"/api/portfolio/positions?account_id={acc}&tag=Div").json()
        assert [r["ticker"] for r in rows] == ["RI.PA"]

    def test_set_position_tag_endpoint(self, client):
        acc = _account(client)
        _tx(client, acc, quantity=10, price=100.0)
        _tx(client, acc, quantity=10, price=120.0)
        r = client.post(
            "/api/portfolio/positions/tag",
            json={"account_id": acc, "ticker": "RI.PA", "tag": "Actions dividende"},
        )
        assert r.status_code == 200
        assert r.json() == {"status": "ok", "updated": 2}
        (row,) = client.get(f"/api/portfolio/positions?account_id={acc}").json()
        assert row["tags"] == ["Actions dividende"]

    def test_set_position_tag_clear(self, client):
        acc = _account(client)
        _tx(client, acc, tag="Div")
        client.post(
            "/api/portfolio/positions/tag",
            json={"account_id": acc, "ticker": "RI.PA", "tag": None},
        )
        assert client.get("/api/portfolio/tags").json() == {"tags": []}

    def test_set_position_tag_empty_ticker_422(self, client):
        acc = _account(client)
        r = client.post(
            "/api/portfolio/positions/tag",
            json={"account_id": acc, "ticker": "  ", "tag": "Div"},
        )
        assert r.status_code == 422


class TestSummaryTagScope:
    """#17.6 — le résumé accepte une étiquette (portée portefeuille virtuel)."""

    def test_summary_unknown_period_still_422(self, client):
        _account(client)
        assert client.get("/api/portfolio/summary?period=10a").status_code == 422

    def test_summary_accepts_tag_parameter(self, client):
        # Sans transaction, le résumé est vide mais la requête ne doit pas échouer
        # sur le paramètre `tag` (routage + validation).
        acc = _account(client)
        r = client.get(f"/api/portfolio/summary?account_id={acc}&tag=Div")
        assert r.status_code == 200


class TestRiskRoute:
    """#17.3 — route de risque : portée compte/étiquette, structure du payload."""

    def test_risk_empty_portfolio(self, client):
        acc = _account(client)
        payload = client.get(f"/api/portfolio/risk?account_id={acc}").json()
        assert payload["dates"] == []
        assert payload["correlation"] == {"tickers": [], "matrix": [], "excluded": []}
        assert payload["corr_avg"] is None
        assert payload["metrics"]["max_drawdown_pct"] == 0.0

    def test_risk_unknown_period_422(self, client):
        acc = _account(client)
        _tx(client, acc)
        assert client.get(f"/api/portfolio/risk?account_id={acc}&period=10a").status_code == 422

    def test_risk_accepts_tag_parameter(self, client):
        acc = _account(client)
        r = client.get(f"/api/portfolio/risk?account_id={acc}&tag=Div")
        assert r.status_code == 200


class TestCorrelationTestRoute:
    """#17.3 — route du test de corrélation : validation + structure du payload."""

    def test_empty_ticker_422(self, client):
        acc = _account(client)
        _tx(client, acc)
        r = client.get(f"/api/portfolio/risk/correlation-test?account_id={acc}&ticker=")
        assert r.status_code == 422

    def test_empty_portfolio_422(self, client):
        acc = _account(client)
        r = client.get(f"/api/portfolio/risk/correlation-test?account_id={acc}&ticker=MC.PA")
        assert r.status_code == 422

    def test_unknown_period_422(self, client):
        acc = _account(client)
        _tx(client, acc)
        r = client.get(
            f"/api/portfolio/risk/correlation-test?account_id={acc}&period=10a&ticker=MC.PA"
        )
        assert r.status_code == 422

    def test_payload_shape(self, client, monkeypatch):
        import numpy as np
        import pandas as pd

        from obole.data.yahoo import TickerNotFound
        from obole.models import PriceSeries

        def _series(seed, base=100.0):
            idx = pd.bdate_range("2022-01-03", periods=520)
            rng = np.random.default_rng(seed)
            raw = pd.Series(base * np.exp(np.cumsum(rng.normal(0, 0.01, len(idx)))), index=idx)
            return PriceSeries(raw=raw, adjusted=raw, fetched_at=idx[-1].date())

        universe = {
            "RI.PA": _series(1),
            "AI.PA": _series(2, 150.0),
            "CW8.PA": _series(3, 400.0),
            "MC.PA": _series(4, 700.0),
        }

        def _fetch(ticker):
            if ticker not in universe:
                raise TickerNotFound(ticker)
            return universe[ticker]

        monkeypatch.setattr("obole.services.portfolio.yahoo.fetch_prices", _fetch)
        acc = _account(client)
        assert _tx(client, acc, ticker="RI.PA", trade_date="2022-01-03").status_code == 200
        assert (
            _tx(client, acc, ticker="AI.PA", price=150.0, trade_date="2022-01-03").status_code
            == 200
        )
        r = client.get(
            f"/api/portfolio/risk/correlation-test?account_id={acc}&benchmark=CW8.PA&ticker=MC.PA"
        )
        assert r.status_code == 200, r.text
        payload = r.json()
        assert payload["ticker"] == "MC.PA"
        assert len(payload["row"]) == len(payload["tickers"]) == 2
        assert payload["current_avg"] is not None and payload["new_avg"] is not None
        assert payload["delta"] == pytest.approx(
            round(payload["new_avg"] - payload["current_avg"], 4)
        )

    def test_unknown_ticker_422(self, client, monkeypatch):
        from obole.data.yahoo import TickerNotFound

        def _fetch(ticker):
            raise TickerNotFound(ticker)

        monkeypatch.setattr("obole.services.portfolio.yahoo.fetch_prices", _fetch)
        acc = _account(client)
        _tx(client, acc)
        r = client.get(f"/api/portfolio/risk/correlation-test?account_id={acc}&ticker=ZZZ.PA")
        assert r.status_code == 422
