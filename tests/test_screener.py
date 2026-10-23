"""Tests du screener — univers FR (J1). Sans réseau : yf.screen est mocké."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from obole import config
from obole.api.app import app
from obole.data import screener


def _quote(symbol: str, name: str, quote_type: str = "EQUITY", crypto: bool = False) -> dict:
    return {
        "symbol": symbol,
        "shortName": name,
        "quoteType": quote_type,
        "cryptoTradeable": crypto,
    }


def _page(quotes: list[dict], total: int | None = None) -> dict:
    return {"quotes": quotes, "total": total if total is not None else len(quotes)}


class TestTickerFromQuote:
    def test_keeps_real_equity(self):
        q = _quote("RI.PA", "Pernod Ricard")
        assert screener._ticker_from_quote(q) == "RI.PA"

    def test_rejects_warrant_quote_type(self):
        q = _quote("FOO.PA", "Foo", quote_type="WARRANT")
        assert screener._ticker_from_quote(q) is None

    def test_rejects_crypto(self):
        q = _quote("WXRP.PA", "WisdomTree Physical XRP", crypto=True)
        assert screener._ticker_from_quote(q) is None

    def test_rejects_etp_by_name(self):
        q = _quote("XRPL.PA", "CoinShares XRP ETP")
        assert screener._ticker_from_quote(q) is None

    def test_rejects_bond_by_coupon(self):
        q = _quote("VIEBC.PA", "VEOENV0%14JAN27")
        assert screener._ticker_from_quote(q) is None

    def test_rejects_numeric_symbol_warrant(self):
        q = _quote("1027P.PA", "BCP DAX 30")
        assert screener._ticker_from_quote(q) is None

    def test_keeps_real_equity_with_letter_symbol(self):
        q = _quote("AIR.PA", "Airbus")
        assert screener._ticker_from_quote(q) == "AIR.PA"


class TestFetchUniverse:
    def test_yahoo_path_returns_deduped_tickers(self):
        page = _page(
            [
                _quote("AIR.PA", "Airbus"),
                _quote("AI.PA", "Air Liquide"),
                _quote("XRPL.PA", "CoinShares XRP ETP"),  # exclu
            ]
        )
        with (
            patch("obole.data.screener.cache.get", return_value=None),
            patch("obole.data.screener._screen_page", return_value=page),
        ):
            out = screener.fetch_universe()

        assert out["source"] == "yahoo"
        assert "AIR.PA" in out["tickers"]
        assert "AI.PA" in out["tickers"]
        assert "XRPL.PA" not in out["tickers"]  # ETP exclu
        assert out["count"] == len(out["tickers"])

    def test_merges_trusted_universe(self):
        page = _page([_quote("AIR.PA", "Airbus")])
        with (
            patch("obole.data.screener.cache.get", return_value=None),
            patch("obole.data.screener._screen_page", return_value=page),
        ):
            out = screener.fetch_universe()

        # La base de confiance est toujours incluse (union), dédupliquée.
        for t in config.UNIVERSE_FR:
            assert t in out["tickers"]
        assert out["count"] == len(out["tickers"])

    def test_cache_hit_skips_network(self):
        cached = {"tickers": ["AIR.PA"], "count": 1, "source": "cache"}
        with (
            patch("obole.data.screener.cache.get", return_value=cached),
            patch("obole.data.screener._screen_page") as mock_page,
        ):
            out = screener.fetch_universe()

        assert out == cached
        mock_page.assert_not_called()

    def test_filters_bypass_cache(self):
        # Un pré-filtre (capi/secteur) ne peut pas s'appliquer à un cache chaud :
        # on re-fetch Yahoo filtré même si le cache existe.
        cached = {"tickers": ["AIR.PA"], "count": 1, "source": "cache"}
        page = _page([_quote("AIR.PA", "Airbus")])
        with (
            patch("obole.data.screener.cache.get", return_value=cached),
            patch("obole.data.screener._screen_page", return_value=page),
        ):
            out = screener.fetch_universe(min_market_cap=2_000_000_000)

        assert out["source"] == "yahoo"

    def test_filtered_call_does_not_poison_cache(self):
        # Un appel filtré (passe 1) ne doit PAS écraser le cache de l'univers
        # plein : sinon le prochain « tout » serait tronqué au sous-ensemble.
        page = _page([_quote("AIR.PA", "Airbus")])
        with (
            patch("obole.data.screener.cache.get", return_value=None),
            patch("obole.data.screener._screen_page", return_value=page),
            patch("obole.data.screener.cache.put") as mock_put,
        ):
            screener.fetch_universe(min_market_cap=2_000_000_000)

        mock_put.assert_not_called()

    def test_fallback_on_yahoo_failure(self):
        with (
            patch("obole.data.screener.cache.get", return_value=None),
            patch("obole.data.screener._screen_page", side_effect=RuntimeError("réseau KO")),
        ):
            out = screener.fetch_universe()

        assert out["source"] == "fallback"
        assert out["tickers"] == list(config.UNIVERSE_FR)

    def test_fallback_on_empty_page(self):
        # Yahoo « répond » mais sans quotes ni total (échec silencieux) : on ne
        # renvoie pas un univers vide, on bascule sur la base de confiance.
        with (
            patch("obole.data.screener.cache.get", return_value=None),
            patch("obole.data.screener._screen_page", return_value={}),
        ):
            out = screener.fetch_universe()

        assert out["source"] == "fallback"
        assert out["tickers"] == list(config.UNIVERSE_FR)

    def test_min_market_cap_passed_to_yahoo(self):
        page = _page([_quote("AIR.PA", "Airbus")])
        with (
            patch("obole.data.screener.cache.get", return_value=None),
            patch("obole.data.screener._screen_page", return_value=page) as mock_page,
        ):
            screener.fetch_universe(min_market_cap=2_000_000_000)

        # La requête construite contient le filtre capi.
        query_dict = str(mock_page.call_args.args[0].to_dict())
        assert "intradaymarketcap" in query_dict
        assert "2000000000" in query_dict

    def test_pagination_stops_at_total(self):
        pages = [
            _page([_quote("A.PA", "A")] * 2, total=4),
            _page([_quote("B.PA", "B")] * 2, total=4),
        ]
        with (
            patch("obole.data.screener.cache.get", return_value=None),
            patch("obole.data.screener._screen_page", side_effect=pages),
        ):
            out = screener.fetch_universe()

        assert "A.PA" in out["tickers"] and "B.PA" in out["tickers"]


class TestUniverseApi:
    @pytest.fixture(autouse=True)
    def _no_cache(self):
        with patch("obole.data.screener.cache.get", return_value=None):
            yield

    def test_200(self):
        with patch(
            "obole.data.screener._screen_page",
            return_value=_page([_quote("AIR.PA", "Airbus")]),
        ):
            resp = TestClient(app).get("/api/screener/universe")

        assert resp.status_code == 200
        data = resp.json()
        assert "tickers" in data and "count" in data and "source" in data
        assert "AIR.PA" in data["tickers"]
