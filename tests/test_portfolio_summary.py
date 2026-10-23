"""Résumé de performance du portefeuille (#17.1) — service + API. Sans réseau.

`data/yahoo.fetch_prices` est remplacé par une fabrique de séries déterministes :
le service ne fait donc aucun appel réseau, et les valeurs du TWR sont vérifiables.
Le cache SQLite est isolé sur une base temporaire.
"""

from __future__ import annotations

import tempfile

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from obole import config
from obole.data import portfolio as portfolio_data
from obole.models import PriceSeries


@pytest.fixture(autouse=True)
def _isolated_db():
    _orig = config.CACHE_DB
    config.CACHE_DB = tempfile.mktemp(suffix=".sqlite")
    yield
    config.CACHE_DB = _orig


_IDX = pd.bdate_range("2023-01-02", periods=520)


def _series(base: float, drift: float) -> PriceSeries:
    raw = pd.Series(base * np.exp(np.arange(len(_IDX)) * drift), index=_IDX)
    return PriceSeries(raw=raw, adjusted=raw, fetched_at=_IDX[-1].date())


@pytest.fixture
def fake_prices(monkeypatch):
    """Branche un univers de prix déterministe (aucun réseau)."""
    from obole.data import yahoo

    universe = {
        "RI.PA": _series(100.0, 0.0010),  # forte hausse
        "AI.PA": _series(100.0, -0.0008),  # baisse
        "CW8.PA": _series(400.0, 0.0005),  # benchmark
        "UNKNOWN.PA": None,
    }

    def _fetch(ticker: str) -> PriceSeries:
        ps = universe.get(ticker)
        if ps is None:
            raise yahoo.TickerNotFound(ticker)
        return ps

    monkeypatch.setattr(yahoo, "fetch_prices", _fetch)
    return universe


@pytest.fixture
def client():
    from obole.api.app import app

    return TestClient(app)


def _account(name="PEA") -> int:
    return portfolio_data.create_account(name)


class TestBenchmarksRoute:
    def test_returns_curated_list_from_config(self, client):
        data = client.get("/api/portfolio/benchmarks").json()
        assert data["benchmarks"] == config.PORTFOLIO_BENCHMARKS
        assert data["default"] == config.PORTFOLIO_BENCHMARK_DEFAULT
        assert data["periods"] == list(config.PORTFOLIO_PERIODS)
        assert data["top_n"] == config.PORTFOLIO_TOP_N

    def test_all_benchmarks_are_eur_etf_tickers(self, client):
        for b in client.get("/api/portfolio/benchmarks").json()["benchmarks"]:
            assert b["ticker"].endswith((".PA", ".AS", ".DE", ".MI"))


class TestSummaryService:
    def test_empty_portfolio_is_well_formed(self, fake_prices):
        from obole.services import portfolio as svc

        s = svc.summary(None, "CW8.PA", "1a")
        assert s["dates"] == []
        assert s["portfolio"] == []
        assert s["kpis"]["total_value"] == 0.0
        assert s["kpis"]["total_return"] is None
        assert s["top"] == [] and s["flop"] == []

    def test_twr_aligns_with_price_and_benchmark(self, fake_prices):
        from obole.services import portfolio as svc

        acc = _account()
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2023-01-02", 10, 100.0)
        s = svc.summary(None, "CW8.PA", "max")
        assert s["dates"][0] == "2023-01-02"
        assert len(s["portfolio"]) == len(s["dates"]) == len(s["benchmark_curve"])
        # Portefeuille (RI.PA +100 %/an) bat le benchmark (CW8 +50 %/an).
        assert s["kpis"]["period_return_pct"] > s["kpis"]["benchmark_period_pct"]

    def test_dividends_counted_in_return_and_kpi(self, fake_prices):
        from obole.services import portfolio as svc

        acc = _account()
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2023-01-02", 10, 100.0)
        portfolio_data.add_dividend(acc, "RI.PA", "2023-06-01", 42.0)
        s = svc.summary(None, "CW8.PA", "max")
        assert s["kpis"]["dividends"] == 42.0
        assert s["kpis"]["dividend_yield_pct"] == pytest.approx(4.2)
        # La valeur inclut la trésorerie du dividende.
        assert s["kpis"]["total_value"] > 1000.0

    def test_proposed_dividend_excluded_from_summary(self, fake_prices):
        """Non-régression (#17.5) : une PROPOSITION n'est pas un revenu encaissé.

        Régression corrigée : `summary()` sommait les montants sans filtrer le
        statut, et `daily_values` encaissait la proposition — le KPI Dividendes et
        la courbe TWR comptaient un euro jamais versé.
        """
        from obole.services import portfolio as svc

        acc = _account()
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2023-01-02", 10, 100.0)
        portfolio_data.add_dividend(acc, "RI.PA", "2023-06-01", 42.0, "confirmed", "manual")
        portfolio_data.add_dividend(acc, "RI.PA", "2023-09-01", 99.0, "proposed", "yahoo")
        s = svc.summary(acc, "CW8.PA", "max")
        # Seul le confirmé entre dans le KPI et dans la trésorerie.
        assert s["kpis"]["dividends"] == 42.0
        # Le solde du compte (dividendes nets de frais) suit la même règle.
        assert s["account"]["balance"] == pytest.approx(42.0)

    def test_top_and_flop_rank_positions(self, fake_prices):
        from obole.services import portfolio as svc

        acc = _account()
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2023-01-02", 10, 100.0)
        portfolio_data.add_transaction(acc, "AI.PA", "buy", "2023-01-02", 10, 100.0)
        s = svc.summary(None, "CW8.PA", "max")
        assert [r["ticker"] for r in s["top"]] == ["RI.PA", "AI.PA"]
        assert [r["ticker"] for r in s["flop"]] == ["AI.PA", "RI.PA"]
        assert s["top"][0]["perf"] > 0 > s["flop"][0]["perf"]

    def test_accounts_breakdown(self, fake_prices):
        from obole.services import portfolio as svc

        pea = _account("PEA")
        cto = _account("CTO")
        portfolio_data.add_transaction(pea, "RI.PA", "buy", "2023-01-02", 10, 100.0)
        portfolio_data.add_transaction(cto, "CW8.PA", "buy", "2023-01-02", 2, 400.0)
        s = svc.summary(None, "CW8.PA", "max")
        names = [a["name"] for a in s["accounts"]]
        assert set(names) == {"PEA", "CTO"}
        assert all(a["value"] > 0 for a in s["accounts"])

    def test_account_filter_restricts_scope(self, fake_prices):
        from obole.services import portfolio as svc

        pea = _account("PEA")
        cto = _account("CTO")
        portfolio_data.add_transaction(pea, "RI.PA", "buy", "2023-01-02", 10, 100.0)
        portfolio_data.add_transaction(cto, "CW8.PA", "buy", "2023-01-02", 2, 400.0)
        s = svc.summary(pea, "CW8.PA", "max")
        assert [r["ticker"] for r in s["top"]] == ["RI.PA"]
        assert [a["name"] for a in s["accounts"]] == ["PEA"]

    def test_holdings_breakdown_by_ticker(self, fake_prices):
        """Répartition par TITRE (donut « Répartition des titres »)."""
        from obole.services import portfolio as svc

        acc = _account()
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2023-01-02", 10, 100.0)
        portfolio_data.add_transaction(acc, "AI.PA", "buy", "2023-01-02", 5, 100.0)
        s = svc.summary(None, "CW8.PA", "max")
        tickers = [h["ticker"] for h in s["holdings"]]
        # RI.PA monte (+100 %/an), AI.PA baisse : RI pèse plus lourd -> tri décroissant.
        assert tickers == ["RI.PA", "AI.PA"]
        assert all(h["value"] > 0 for h in s["holdings"])

    def test_holdings_respects_account_filter(self, fake_prices):
        from obole.services import portfolio as svc

        pea = _account("PEA")
        cto = _account("CTO")
        portfolio_data.add_transaction(pea, "RI.PA", "buy", "2023-01-02", 10, 100.0)
        portfolio_data.add_transaction(cto, "AI.PA", "buy", "2023-01-02", 10, 100.0)
        assert [h["ticker"] for h in svc.summary(pea, "CW8.PA", "max")["holdings"]] == ["RI.PA"]

    def test_empty_summary_has_holdings_key(self, fake_prices):
        from obole.services import portfolio as svc

        assert svc.summary(None, "CW8.PA", "1a")["holdings"] == []

    def test_unknown_benchmark_raises(self, fake_prices):
        from obole.services import portfolio as svc

        acc = _account()
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2023-01-02", 10, 100.0)
        with pytest.raises(ValueError, match="Benchmark introuvable"):
            svc.summary(None, "UNKNOWN.PA", "1a")

    def test_unknown_period_raises(self, fake_prices):
        from obole.services import portfolio as svc

        acc = _account()
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2023-01-02", 10, 100.0)
        with pytest.raises(ValueError, match="Période inconnue"):
            svc.summary(None, "CW8.PA", "42a")

    def test_missing_ticker_is_a_warning_not_a_crash(self, fake_prices):
        from obole.services import portfolio as svc

        acc = _account()
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2023-01-02", 10, 100.0)
        portfolio_data.add_transaction(acc, "UNKNOWN.PA", "buy", "2023-01-02", 5, 10.0)
        s = svc.summary(None, "CW8.PA", "max")
        assert s["warnings"]
        assert all(r["ticker"] != "UNKNOWN.PA" for r in s["top"])

    def test_account_meta_has_fees_taxes_balance(self, fake_prices):
        from obole.services import portfolio as svc

        acc = _account("PEA")
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2023-01-02", 10, 100.0, fees=4.56)
        portfolio_data.add_dividend(acc, "RI.PA", "2023-06-01", 42.0)
        s = svc.summary(acc, "CW8.PA", "max")
        acc_meta = s["account"]
        assert acc_meta["name"] == "PEA"
        assert acc_meta["since"] == "2023-01-02"
        assert acc_meta["fees"] == 4.56
        assert acc_meta["taxes"] == 0.0
        # Solde = dividendes perçus − frais payés.
        assert acc_meta["balance"] == pytest.approx(42.0 - 4.56)

    def test_account_meta_none_in_consolidated_view(self, fake_prices):
        from obole.services import portfolio as svc

        acc = _account("PEA")
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2023-01-02", 10, 100.0)
        assert svc.summary(None, "CW8.PA", "max")["account"] is None

    def test_top_rows_carry_name_and_gain(self, fake_prices):
        from obole.services import portfolio as svc

        acc = _account("PEA")
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2023-01-02", 10, 100.0)
        (row,) = svc.summary(acc, "CW8.PA", "max")["top"]
        assert row["ticker"] == "RI.PA"
        assert "name" in row  # peut être None si l'identité est indisponible
        assert row["market_value"] is not None
        assert row["gain"] is not None

    def test_summary_never_hits_network_for_names(self, fake_prices, monkeypatch):
        """Les noms Top/Flop sont résolus en cache seul : aucun `info` yfinance.

        Régression : `_attach_names` appelait `fetch_identity` (réseau, 0,5-2 s
        par ligne), ce qui bloquait le premier rendu du Résumé sur ~10 requêtes.
        """
        from obole.data import yahoo
        from obole.services import portfolio as svc

        def _boom(*_a, **_k):
            raise AssertionError("Le Résumé ne doit pas déclencher d'appel réseau `info`")

        monkeypatch.setattr(yahoo, "fetch_identity", _boom)
        acc = _account("PEA")
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2023-01-02", 10, 100.0)
        s = svc.summary(acc, "CW8.PA", "max")
        assert s["top"][0]["name"] is None  # cache vide -> repli sur le ticker

    def test_resolve_names_is_lazy_and_tolerant(self, monkeypatch):
        """`resolve_names` tolère le réseau (appel hors chemin critique).

        Il rend un dict ticker -> nom, ignore les doublons/vides, et met None
        pour un ticker en échec (le front garde alors l'affichage du ticker).
        """
        from obole.data import yahoo
        from obole.models import Identity
        from obole.services import portfolio as svc

        def _ident(ticker, _lp):
            if ticker == "BOOM.PA":
                raise RuntimeError("réseau")
            return Identity(ticker=ticker, name=f"Société {ticker}")

        monkeypatch.setattr(yahoo, "fetch_identity", _ident)
        out = svc.resolve_names(["", "ri.pa", "RI.PA", "BOOM.PA"])
        assert out == {"RI.PA": "Société RI.PA", "BOOM.PA": None}

    def test_resolve_names_is_capped(self, monkeypatch):
        """La liste est bornée : une liste forgée ne bloque pas la requête."""
        from obole import config
        from obole.data import yahoo
        from obole.models import Identity
        from obole.services import portfolio as svc

        calls = []

        def _ident(ticker, _lp):
            calls.append(ticker)
            return Identity(ticker=ticker, name=f"Société {ticker}")

        monkeypatch.setattr(yahoo, "fetch_identity", _ident)
        many = [f"T{i}.PA" for i in range(config.PORTFOLIO_NAMES_MAX + 10)]
        out = svc.resolve_names(many)
        assert len(out) == config.PORTFOLIO_NAMES_MAX
        assert len(calls) == config.PORTFOLIO_NAMES_MAX


class TestNamesRoute:
    def test_names_endpoint(self, client, monkeypatch):
        from obole.data import yahoo
        from obole.models import Identity

        monkeypatch.setattr(
            yahoo,
            "fetch_identity",
            lambda t, _lp: Identity(ticker=t, name=f"Société {t}"),
        )
        r = client.get("/api/portfolio/names", params={"tickers": "ri.pa, ai.pa"})
        assert r.status_code == 200
        assert r.json()["names"] == {"RI.PA": "Société RI.PA", "AI.PA": "Société AI.PA"}

    def test_names_endpoint_empty(self, client):
        r = client.get("/api/portfolio/names")
        assert r.status_code == 200
        assert r.json() == {"names": {}}


class TestSummaryRoute:
    def test_200_nominal(self, client, fake_prices):
        acc = _account()
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2023-01-02", 10, 100.0)
        r = client.get("/api/portfolio/summary?benchmark=CW8.PA&period=1a")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["benchmark"]["ticker"] == "CW8.PA"
        assert set(body["kpis"]) >= {"total_value", "invested", "total_return", "dividends"}
        assert "portfolio" in body and "benchmark_curve" in body
        # Répartition par titres servie par la route (le sérialiseur whitelist les clés).
        assert "holdings" in body
        assert [h["ticker"] for h in body["holdings"]] == ["RI.PA"]

    def test_422_on_unknown_period(self, client, fake_prices):
        acc = _account()
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2023-01-02", 10, 100.0)
        r = client.get("/api/portfolio/summary?period=zzz")
        assert r.status_code == 422

    def test_422_on_unknown_benchmark(self, client, fake_prices):
        acc = _account()
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2023-01-02", 10, 100.0)
        r = client.get("/api/portfolio/summary?benchmark=NOPE.PA")
        assert r.status_code == 422

    def test_defaults_when_params_absent(self, client, fake_prices):
        r = client.get("/api/portfolio/summary")
        assert r.status_code == 200
        assert r.json()["period"] == config.PORTFOLIO_PERIOD_DEFAULT


class TestBenchmarkSetting:
    def test_default_is_config_value(self):
        from obole.data import cache

        assert cache.get_settings()["portfolio_benchmark"] == config.PORTFOLIO_BENCHMARK_DEFAULT

    def test_roundtrip_persists(self):
        from obole.data import cache

        cache.set_settings({"portfolio_benchmark": "ESE.PA"})
        assert cache.get_settings()["portfolio_benchmark"] == "ESE.PA"

    def test_rejects_overlong_value(self):
        from obole.data import cache

        with pytest.raises(ValueError, match="hors bornes"):
            cache.set_settings({"portfolio_benchmark": "X" * 50})

    def test_rejects_empty_value(self):
        from obole.data import cache

        with pytest.raises(ValueError, match="hors bornes"):
            cache.set_settings({"portfolio_benchmark": ""})

    def test_settings_route_exposes_benchmark(self, client):
        data = client.get("/api/settings").json()
        assert data["values"]["portfolio_benchmark"] == config.PORTFOLIO_BENCHMARK_DEFAULT
        r = client.put("/api/settings", json={"values": {"portfolio_benchmark": "MSE.PA"}})
        assert r.status_code == 200
        assert r.json()["values"]["portfolio_benchmark"] == "MSE.PA"


class TestPeriodSetting:
    """La période du portefeuille est mémorisée comme le benchmark (#17.1)."""

    def test_default_is_config_value(self):
        from obole.data import cache

        assert cache.get_settings()["portfolio_period"] == config.PORTFOLIO_PERIOD_DEFAULT

    def test_roundtrip_persists(self):
        from obole.data import cache

        cache.set_settings({"portfolio_period": "5a"})
        assert cache.get_settings()["portfolio_period"] == "5a"

    def test_rejects_value_outside_closed_list(self):
        from obole.data import cache

        with pytest.raises(ValueError, match="hors bornes"):
            cache.set_settings({"portfolio_period": "42a"})

    def test_settings_route_exposes_period(self, client):
        data = client.get("/api/settings").json()
        assert data["values"]["portfolio_period"] == config.PORTFOLIO_PERIOD_DEFAULT
        r = client.put("/api/settings", json={"values": {"portfolio_period": "3a"}})
        assert r.status_code == 200
        assert r.json()["values"]["portfolio_period"] == "3a"


class TestPerformanceRoute:
    def _seed(self):
        acc = _account()
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2023-01-02", 10, 100.0)
        portfolio_data.add_transaction(acc, "AI.PA", "buy", "2023-01-02", 10, 100.0)
        return acc

    def _patch_analyze(self, monkeypatch):
        """Analyse RÉELLE : on ne mocke que la couche `data/yahoo` (identité + comptes).

        `services.analysis.analyze` s'exécute donc vraiment (contrat complet :
        Indicators, summary…) — c'est le garde-fou qui aurait attrapé le 500
        (`perf_passe`) que le mock de `analyze` masquait.
        """
        from obole.data import yahoo
        from obole.models import CompanyKind, Identity

        monkeypatch.setattr(
            yahoo,
            "fetch_identity",
            lambda t, _lp: Identity(
                ticker=t.upper(), name=f"Société {t}", kind=CompanyKind.INDUSTRIAL
            ),
        )
        monkeypatch.setattr(yahoo, "fetch_fundamentals", lambda t, kind: None)
        # L'analyse lit aussi `analyze` via le module services.analysis : on laisse
        # passer (aucun patch), seuls les fetch réseau sont neutralisés.
        return None

    def test_200_nominal(self, client, fake_prices, monkeypatch):
        self._seed()
        self._patch_analyze(monkeypatch)
        r = client.get("/api/portfolio/performance?benchmark=CW8.PA&period=max")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["benchmark"]["ticker"] == "CW8.PA"
        assert body["monthly"]["months"] == config.PORTFOLIO_MONTHS
        assert "stat_groups" in body and "stats" in body
        assert {row["ticker"] for row in body["table"]} == {"RI.PA", "AI.PA"}
        assert set(body["risk_adjusted"]["portfolio"]) == {"sharpe", "sortino"}

    def test_422_on_unknown_benchmark(self, client, fake_prices):
        self._seed()
        r = client.get("/api/portfolio/performance?benchmark=NOPE.PA")
        assert r.status_code == 422

    def test_422_on_unknown_period(self, client, fake_prices):
        self._seed()
        r = client.get("/api/portfolio/performance?period=zzz")
        assert r.status_code == 422

    def test_empty_portfolio_structure(self, client, fake_prices):
        r = client.get("/api/portfolio/performance?benchmark=CW8.PA")
        assert r.status_code == 200
        body = r.json()
        assert body["table"] == []
        assert body["monthly"]["portfolio"]["rows"] == []

    def test_meta_exposes_stat_groups(self, client):
        data = client.get("/api/meta").json()
        assert data["portfolio_stat_groups"] == config.PORTFOLIO_STAT_GROUPS
        assert data["portfolio_months"] == config.PORTFOLIO_MONTHS
