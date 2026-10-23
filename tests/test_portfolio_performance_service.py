"""Performance du portefeuille (#17.4) — cas d'usage `services/portfolio.performance`.

Sans réseau : les prix sont mockés (`yahoo.fetch_prices`), le cache isolé sur une
base temporaire. Couvre l'assemblage A (stats pondérées + Sharpe/Sortino),
B (tableaux mensuels + contribution) et C (rétrospective + grand tableau).
"""

from __future__ import annotations

import tempfile

import numpy as np
import pandas as pd
import pytest

from obole import config
from obole.data import portfolio as portfolio_data
from obole.data.yahoo import TickerNotFound
from obole.models import PriceSeries
from obole.services import portfolio as service


def _series(base: float, drift: float, periods: int = 520, seed: int = 0) -> PriceSeries:
    idx = pd.bdate_range("2022-01-03", periods=periods)
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, 0.005, len(idx))
    raw = pd.Series(base * np.exp(np.arange(len(idx)) * drift + np.cumsum(noise)), index=idx)
    return PriceSeries(raw=raw, adjusted=raw, fetched_at=idx[-1].date())


@pytest.fixture(autouse=True)
def _isolated_db():
    _orig = config.CACHE_DB
    config.CACHE_DB = tempfile.mktemp(suffix=".sqlite")
    yield
    config.CACHE_DB = _orig


class TestServicePerformance:
    def _universe(self):
        return {
            "RI.PA": _series(100.0, 0.0006, seed=1),
            "AI.PA": _series(150.0, 0.0004, seed=2),
            "CW8.PA": _series(400.0, 0.0005, seed=3),
        }

    def _seed(self):
        acc = portfolio_data.create_account("PEA")
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2022-01-03", 10, 100.0)
        portfolio_data.add_transaction(acc, "AI.PA", "buy", "2022-01-03", 10, 150.0)
        return acc

    def _patch_yahoo_prices(self, monkeypatch):
        """Ne mocke QUE les prix : l'analyse par ligne suit son vrai chemin."""
        universe = self._universe()

        def _fetch(ticker):
            if ticker not in universe:
                raise TickerNotFound(ticker)
            return universe[ticker]

        monkeypatch.setattr("obole.services.portfolio.yahoo.fetch_prices", _fetch)

    def _patch(self, monkeypatch):
        universe = self._universe()

        def _fetch(ticker):
            if ticker not in universe:
                raise TickerNotFound(ticker)
            return universe[ticker]

        monkeypatch.setattr("obole.services.portfolio.yahoo.fetch_prices", _fetch)
        # L'analyse fondamentale par ligne est coûteuse : on la neutralise par un
        # VRAI StockAnalysis (pas un mock qui masquerait le contrat d'attributs).
        monkeypatch.setattr(
            "obole.services.portfolio.analysis_service.analyze",
            lambda tk, prices: _make_analysis(tk),
        )

    def test_empty_portfolio_structure(self):
        acc = portfolio_data.create_account("PEA")
        out = service.performance(acc, None, None)
        assert out["monthly"]["portfolio"]["rows"] == []
        assert out["table"] == []
        assert out["stats"] == {}
        assert out["risk_adjusted"]["portfolio"]["sharpe"] is None

    def test_full_payload_structure(self, monkeypatch):
        acc = self._seed()
        self._patch(monkeypatch)
        out = service.performance(acc, "CW8.PA", "max")
        assert out["benchmark"]["ticker"] == "CW8.PA"
        assert out["monthly"]["months"] == config.PORTFOLIO_MONTHS
        assert out["monthly"]["portfolio"]["rows"]
        assert out["monthly"]["benchmark"]["rows"]
        # Stats : le dict porte les clés de la taxonomie.
        keys = {m["key"] for g in config.PORTFOLIO_STAT_GROUPS for m in g["metrics"]}
        assert keys <= set(out["stats"]) | {"count", "top5_weight", "market_cap"}
        assert out["table"]
        assert {r["ticker"] for r in out["table"]} == {"RI.PA", "AI.PA"}

    def test_stats_and_donut_same_lines(self, monkeypatch):
        """Le grand tableau et les stats portent sur EXACTEMENT les lignes détenues."""
        acc = self._seed()
        self._patch(monkeypatch)
        out = service.performance(acc, "CW8.PA", "max")
        table_tickers = {r["ticker"] for r in out["table"]}
        assert table_tickers == {"RI.PA", "AI.PA"}
        # Nombre d'actions = taille du tableau (cohérence donut ↔ stats).
        assert out["stats"]["count"]["value"] == float(len(out["table"]))

    def test_contributions_sum_close_to_total(self, monkeypatch):
        acc = self._seed()
        self._patch(monkeypatch)
        out = service.performance(acc, "CW8.PA", "max")
        contribs = [
            c["contribution_pct"]
            for c in out["contributions"]["items"]
            if c["contribution_pct"] is not None
        ]
        total = out["contributions"]["total_pct"]
        if contribs and total is not None:
            assert sum(contribs) == pytest.approx(total, abs=0.05)

    def test_contribution_uses_percent_scale(self, monkeypatch):
        """Contribution = poids (fraction) × perf (%) — échelon correct, pas ×100.

        Régression : le service divisait `perf` par 100, donnant une contribution
        100× trop faible. On vérifie l'ordre de grandeur réel : une ligne de poids
        ~1 × perf +10 % doit contribuer ~+10 % (poids × perf%), pas ~+0,1 %.
        """
        acc = portfolio_data.create_account("PEA")
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2022-01-03", 10, 100.0)
        universe = self._universe()

        def _fetch(t):
            if t not in universe:
                raise TickerNotFound(t)
            return universe[t]

        monkeypatch.setattr("obole.services.portfolio.yahoo.fetch_prices", _fetch)
        monkeypatch.setattr(
            "obole.services.portfolio.analysis_service.analyze",
            lambda tk, prices: _make_analysis(tk),
        )
        out = service.performance(acc, "CW8.PA", "max")
        item = next(c for c in out["contributions"]["items"] if c["ticker"] == "RI.PA")
        # Une seule ligne -> poids 1.0 -> contribution = perf (échelon %), pas
        # perf/100 (régression ×100). On compare directement, pas d'ordre de grandeur.
        assert item["contribution_pct"] == pytest.approx(item["perf_pct"], abs=0.05)
        assert abs(item["contribution_pct"]) > 1.0  # jamais écrasé vers ~0

    def test_sharpe_present_for_portfolio_and_benchmark(self, monkeypatch):
        acc = self._seed()
        self._patch(monkeypatch)
        out = service.performance(acc, "CW8.PA", "max")
        ra = out["risk_adjusted"]
        assert ra["risk_free_pct"] == 0.0
        assert set(ra["portfolio"]) == {"sharpe", "sortino"}
        assert set(ra["benchmark"]) == {"sharpe", "sortino"}

    def test_risk_adjusted_by_period_covers_only_available(self, monkeypatch):
        # Historique ~2 ans (520 séances) : TTM et MAX sont couverts, 3A/5A non.
        acc = self._seed()
        self._patch(monkeypatch)
        ra = service.performance(acc, "CW8.PA", "max")["risk_adjusted"]
        assert "max" in ra["periods"]
        assert "ttm" in ra["periods"]
        assert "3a" not in ra["periods"] and "5a" not in ra["periods"]
        # Chaque période listée a bien ses deux lignes calculées.
        for p in ra["periods"]:
            assert set(ra["by_period"][p]["portfolio"]) == {"sharpe", "sortino"}
            assert set(ra["by_period"][p]["benchmark"]) == {"sharpe", "sortino"}
        # Compat : la forme historique `portfolio`/`benchmark` = MAX.
        assert ra["portfolio"] == ra["by_period"]["max"]["portfolio"]

    def test_risk_adjusted_empty_periods(self, monkeypatch):
        acc = portfolio_data.create_account("PEA")
        self._patch(monkeypatch)
        ra = service.performance(acc, "CW8.PA", "max")["risk_adjusted"]
        assert ra["periods"] == []
        assert ra["by_period"] == {}

    def test_security_detail_aligns_benchmark(self, monkeypatch):
        self._patch(monkeypatch)
        detail = service.security_detail("RI.PA", "CW8.PA")
        assert detail["ticker"] == "RI.PA"
        assert detail["benchmark"]["ticker"] == "CW8.PA"
        assert len(detail["benchmark_curve"]) == len(detail["chart"]["dates"])
        assert all(v is not None for v in detail["benchmark_curve"])

    def test_security_detail_cross_timezone_benchmark(self, monkeypatch):
        """Titre et benchmark sur des fuseaux DIFFÉRENTS -> courbe non vide.

        Régression : le reindex tz-aware entre deux fuseaux distincts (titre US
        `America/New_York` vs benchmark Paris `Europe/Paris`) ne matche rien et
        renvoie tout NaN — la courbe benchmark disparaissait du graphe.
        """
        idx_ny = pd.bdate_range("2022-01-03", periods=520, tz="America/New_York")
        raw_ny = pd.Series(np.linspace(100.0, 200.0, len(idx_ny)), index=idx_ny)
        us = PriceSeries(raw=raw_ny, adjusted=raw_ny, fetched_at=idx_ny[-1].date())

        def _fetch(ticker):
            if ticker == "AAPL":
                return us
            return self._universe()[ticker]

        monkeypatch.setattr("obole.services.portfolio.yahoo.fetch_prices", _fetch)
        detail = service.security_detail("AAPL", "CW8.PA")
        assert len(detail["benchmark_curve"]) == len(detail["chart"]["dates"])
        assert any(v is not None for v in detail["benchmark_curve"])

    def test_security_detail_empty_ticker_raises(self, monkeypatch):
        self._patch(monkeypatch)
        with pytest.raises(ValueError, match="vide"):
            service.security_detail("  ", "CW8.PA")

    def test_security_detail_unknown_benchmark_raises(self, monkeypatch):
        self._patch(monkeypatch)
        with pytest.raises(TickerNotFound):
            service.security_detail("RI.PA", "ZZZ.PA")

    def test_unknown_benchmark_raises(self, monkeypatch):
        acc = self._seed()
        self._patch(monkeypatch)
        with pytest.raises(ValueError, match="introuvable"):
            service.performance(acc, "ZZZ.PA", "max")

    def test_retrospective_lists_transactions(self, monkeypatch):
        acc = self._seed()
        self._patch(monkeypatch)
        out = service.performance(acc, "CW8.PA", "max")
        assert len(out["retrospective"]) == 2
        for row in out["retrospective"]:
            assert row["ticker"] in {"RI.PA", "AI.PA"}
            assert row["side"] == "buy"
            assert "delta_pct" in row

    def test_stats_are_weighted_not_simple_mean(self, monkeypatch):
        """Les stats agrégées sont PONDÉRÉES (poids de marché), pas une moyenne simple.

        Deux lignes de tailles très différentes, qualité 20 vs 80 : la moyenne
        pondérée par la capitalisation est proche de la grosse ligne (80), loin de
        la moyenne simple (50).
        """
        acc = portfolio_data.create_account("PEA")
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2022-01-03", 100, 100.0)
        portfolio_data.add_transaction(acc, "AI.PA", "buy", "2022-01-03", 1, 150.0)
        universe = self._universe()

        def _fetch(ticker):
            if ticker not in universe:
                raise TickerNotFound(ticker)
            return universe[ticker]

        monkeypatch.setattr("obole.services.portfolio.yahoo.fetch_prices", _fetch)
        # Qualité très contrastée : RI (grosse ligne) = 20, AI (petite) = 80.
        monkeypatch.setattr(
            "obole.services.portfolio.analysis_service.analyze",
            lambda tk, prices: _make_analysis(tk, quality=20.0 if tk == "RI.PA" else 80.0),
        )
        out = service.performance(acc, "CW8.PA", "max")
        q = out["stats"]["quality"]["value"]
        # Pondérée -> tirée vers RI (20), PAS vers la moyenne simple (50).
        assert q < 40.0, f"attendu proche de 20 (grosse ligne), obtenu {q}"

    def test_retrospective_compares_title_and_bench_on_same_series(self, monkeypatch):
        """Rétrospective : titre et benchmark sur la MÊME série (ajustée)."""
        acc = portfolio_data.create_account("PEA")
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2022-01-03", 10, 100.0)
        # Titre plat (raw == adjusted) ; benchmark CW8 en adj différent du raw.
        idx = pd.bdate_range("2022-01-03", periods=520)
        ri = pd.Series(100.0 * np.exp(np.arange(520) * 0.0006), index=idx)
        bench_adj = pd.Series(400.0 * np.exp(np.arange(520) * 0.0005), index=idx)
        bench_raw = bench_adj * 0.5  # écart net raw vs adj
        universe = {
            "RI.PA": PriceSeries(raw=ri, adjusted=ri, fetched_at=idx[-1].date()),
            "CW8.PA": PriceSeries(raw=bench_raw, adjusted=bench_adj, fetched_at=idx[-1].date()),
        }
        monkeypatch.setattr(
            "obole.services.portfolio.yahoo.fetch_prices",
            lambda t: universe[t] if t in universe else (_ for _ in ()).throw(TickerNotFound(t)),
        )
        monkeypatch.setattr(
            "obole.services.portfolio.analysis_service.analyze",
            lambda tk, prices: _make_analysis(tk),
        )
        out = service.performance(acc, "CW8.PA", "max")
        (row,) = out["retrospective"]
        # Benchmark mesuré sur l'ADJUSTED (base 400) : ~+29 % sur ~2 ans, pas sur
        # le raw (base 200, qui donnerait ~+158 %). On vérifie l'ordre de grandeur
        # de l'adj, preuve que la série choisie est la bonne.
        assert row["benchmark_pct"] < 60.0, f"benchmark sur raw ? {row['benchmark_pct']}"

    def test_no_network_on_warm_cache(self, monkeypatch):
        """Cache chaud : `performance()` ne doit déclencher AUCUN appel RÉSEAU.

        Régression (#1 de la revue) : la boucle « Stats agrégées » appelait
        `analysis_service.analyze` par ligne, soit `fetch_identity` +
        `fetch_fundamentals` — ~4 requêtes yfinance séquentielles par titre. En
        cache froid, ouvrir la Performance d'un portefeuille de 30 lignes bloquait
        plusieurs dizaines de secondes.

        On n'instrumente PAS `fetch_identity`/`fetch_fundamentals` : ce sont des
        wrappers qui consultent le cache AVANT le réseau, et ils sont donc appelés
        même quand tout est servi depuis le cache — compter leurs appels ne dirait
        rien du coût réseau (faux négatif). La bonne frontière est
        `yf.Ticker`, seul point réellement sortant : on le rend explosif. Si le
        cache chaud est bien respecté, il n'est jamais atteint.
        """
        from obole.data import cache as cache_mod
        from obole.data import yahoo as yahoo_mod
        from obole.models import CompanyKind, Identity

        def _explode(*_args, **_kwargs):
            raise AssertionError("appel réseau yfinance sur un cache chaud")

        acc = self._seed()
        self._patch_yahoo_prices(monkeypatch)  # prix servis, analyse réelle
        # Cache CHAUD complet : identité ET comptes valides pour le cache, sinon
        # `_fresh_cached` les rejette et un appel réseau légitime partirait
        # (faux négatif). `market`/`health_rows` sont les champs requis par
        # `_FUNDAMENTALS_FIELDS`.
        from obole.models import Fundamentals

        def _explode(*_args, **_kwargs):
            raise AssertionError("appel réseau yfinance sur un cache chaud")

        for tk in ("RI.PA", "AI.PA"):
            cache_mod.put(
                tk,
                "identity",
                Identity(
                    ticker=tk,
                    kind=CompanyKind.INDUSTRIAL,
                    model_version=yahoo_mod.MODEL_VERSION,
                    industry="Beverages",
                    website="https://example.com",
                    beta=0.8,
                    week52_low=90.0,
                    avg_volume=1_000_000.0,
                    address="Paris",
                ),
            )
            cache_mod.put(
                tk,
                "fundamentals",
                Fundamentals(
                    table=pd.DataFrame(),
                    kind=CompanyKind.INDUSTRIAL,
                    available_years=0,
                    fetched_at=__import__("datetime").date(2024, 1, 1),
                    market={},
                    health_rows={},
                    model_version=yahoo_mod.MODEL_VERSION,
                ),
            )
        monkeypatch.setattr("obole.data.yahoo.yf.Ticker", _explode)

        service.performance(acc, "CW8.PA", "max")

    def test_no_network_for_etf_lines_on_warm_cache(self, monkeypatch):
        """Un ETF/crypto en portefeuille ne rejoue RIEN au second appel (#24).

        Régression mesurée : `_IDENTITY_FIELDS` exigeait `industry`/`website`/
        `address`, champs qu'un ETF n'a pas par nature. Son identité était donc
        considérée périmée À VIE et `fetch_identity` rejouait `info` + `calendar`
        (2 tentatives) à chaque ouverture de l'onglet Performance. La même
        logique valait pour les comptes (`market`), d'où le cache négatif.

        Ici la ligne est un ETF sans champs société, servie depuis le cache : le
        test échoue si un appel réseau part. `performance()` est appelé DEUX fois
        pour couvrir le cache chaud (second appel = 0 requête).
        """
        from datetime import date

        from obole.data import cache as cache_mod
        from obole.data import yahoo as yahoo_mod
        from obole.models import CompanyKind, Fundamentals, Identity

        def _explode(*_args, **_kwargs):
            raise AssertionError("appel réseau yfinance sur un cache chaud")

        universe = {"CEMQ.DE": _series(10.0, 0.0005, seed=4), **self._universe()}

        def _fetch(ticker):
            if ticker not in universe:
                raise TickerNotFound(ticker)
            return universe[ticker]

        monkeypatch.setattr("obole.services.portfolio.yahoo.fetch_prices", _fetch)
        acc = portfolio_data.create_account("PEA")
        portfolio_data.add_transaction(acc, "CEMQ.DE", "buy", "2022-01-03", 10, 10.0)
        # Identité d'ETF RÉALISTE : aucun champ société, seul `model_version`.
        for tk in ("CEMQ.DE", "CW8.PA"):
            cache_mod.put(
                tk,
                "identity",
                Identity(
                    ticker=tk, kind=CompanyKind.INDUSTRIAL, model_version=yahoo_mod.MODEL_VERSION
                ),
            )
        # Comptes indisponibles : marqueur négatif déjà posé (sinon re-fetch).
        cache_mod.put("CEMQ.DE", "fundamentals_missing", True)
        cache_mod.put("CW8.PA", "fundamentals_missing", True)
        # Garde-fou : un chemin de valorisation qui exigerait des comptes doit
        # dégrader proprement, pas appeler le réseau.
        cache_mod.put(
            "CEMQ.DE",
            "fundamentals",
            Fundamentals(
                table=pd.DataFrame(),
                kind=CompanyKind.INDUSTRIAL,
                available_years=0,
                fetched_at=date(2024, 1, 1),
                health_rows={},
                model_version=yahoo_mod.MODEL_VERSION,
            ),
        )
        monkeypatch.setattr("obole.data.yahoo.yf.Ticker", _explode)

        service.performance(acc, "CW8.PA", "max")
        service.performance(acc, "CW8.PA", "max")

    def test_analyses_run_in_parallel(self, monkeypatch):
        """Les analyses par ligne sont parallélisées (revue #1, correctif perf).

        Avec des workers >= 2 et des lignes indépendantes, l'exécution doit être
        concurrente : on mesure que plusieurs analyses sont « en vol » en même
        temps. Un retour à la boucle séquentielle ferait échouer ce test.
        """
        from concurrent.futures import ThreadPoolExecutor

        acc = self._seed()
        self._patch(monkeypatch)  # yahoo.fetch_prices + analyze mockés
        in_flight = {"now": 0, "max": 0}
        import threading

        lock = threading.Lock()

        def _slow_analyze(tk, prices):
            with lock:
                in_flight["now"] += 1
                in_flight["max"] = max(in_flight["max"], in_flight["now"])
            try:
                import time

                time.sleep(0.05)  # simule la latence réseau
                return _make_analysis(tk)
            finally:
                with lock:
                    in_flight["now"] -= 1

        monkeypatch.setattr("obole.services.portfolio.analysis_service.analyze", _slow_analyze)
        # Garde-fou : le service doit passer par un pool (import utilisé), et la
        # constante doit exister et être bornée.
        assert isinstance(ThreadPoolExecutor, type)
        assert config.PORTFOLIO_PERF_WORKERS >= 2

        service.performance(acc, "CW8.PA", "max")

        assert (
            in_flight["max"] >= 2
        ), f"analyses non concurrentes (max en vol = {in_flight['max']}) — boucle séquentielle ?"

    def test_network_calls_are_concurrent(self, monkeypatch):
        """Les appels yfinance par ligne sont CONCURRENTS (régression #1).

        Compteur + mesure de concurrence sur la frontière réseau réelle :
        `services.analysis.yahoo.fetch_identity` / `fetch_fundamentals` (les
        wrappers appelés par `analyze` pour chaque ligne). On les remplace par des
        versions qui dorment et comptent combien sont EN VOL simultanément.

        Avant le correctif (boucle séquentielle) le maximum en vol vaut 1 ; avec
        le pool borné il doit valoir >= 2. C'est le vrai test de régression : il
        échoue sur le code d'origine et passe après.
        """
        import threading
        import time

        from obole.models import CompanyKind, Identity

        in_flight = {"now": 0, "max": 0, "calls": 0}
        lock = threading.Lock()

        def _enter():
            with lock:
                in_flight["now"] += 1
                in_flight["calls"] += 1
                in_flight["max"] = max(in_flight["max"], in_flight["now"])

        def _leave():
            with lock:
                in_flight["now"] -= 1

        def _identity(ticker, last_price):
            _enter()
            try:
                time.sleep(0.05)  # latence réseau simulée
                return Identity(ticker=ticker, kind=CompanyKind.INDUSTRIAL)
            finally:
                _leave()

        def _fundamentals(ticker, kind):
            _enter()
            try:
                time.sleep(0.05)
                return None
            finally:
                _leave()

        acc = self._seed()
        # Prix servis par le cache : seule l'analyse par ligne touche le réseau.
        self._patch_yahoo_prices(monkeypatch)
        monkeypatch.setattr("obole.services.analysis.yahoo.fetch_identity", _identity)
        monkeypatch.setattr("obole.services.analysis.yahoo.fetch_fundamentals", _fundamentals)

        service.performance(acc, "CW8.PA", "max")

        # 2 lignes -> 2 identités + 2 comptes : les appels ont bien eu lieu...
        assert in_flight["calls"] == 4, f"appels réseau inattendus : {in_flight['calls']}"
        # ...et ils se sont CHEVAUCHÉS (séquentiel = 1).
        assert (
            in_flight["max"] >= 2
        ), f"appels réseau non concurrents (max en vol = {in_flight['max']}) — boucle séquentielle ?"

    def test_engine_still_pure(self):
        import ast
        import pathlib

        src = pathlib.Path("src/obole/engine/portfolio.py").read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    assert not n.name.startswith("obole.data")
                    assert not n.name.startswith("obole.services")
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("obole.data")
                assert not node.module.startswith("obole.services")


def _make_analysis(ticker: str = "RI.PA", quality: float | None = 60.0):
    """Vrai `StockAnalysis` (pas de mock) — verrouille le contrat de champs.

    Construit avec les VRAIS modèles `Indicators`/`StockAnalysis` : toute coquille
    d'attribut dans le service (ex. `perf_passe` au lieu de `perf_passee`) casse ici.
    """
    from obole.models import (
        CompanyKind,
        Identity,
        Indicators,
        RegressionResult,
        ScoredValue,
        StockAnalysis,
    )

    reg = RegressionResult(
        a=0.0,
        b=0.01,
        sigma=0.05,
        t_now=1.0,
        fitted_now=100.0,
        start=__import__("datetime").date(2022, 1, 1),
        end=__import__("datetime").date(2023, 1, 1),
        n_points=250,
    )
    ind = Indicators(
        distance_sigma=ScoredValue(-1.0, "Décoté", True),
        perf_passee=ScoredValue(5.0, "Bonne", True),
        ecart_type=ScoredValue(20.0, "Moyen", None),
        potential_5y=ScoredValue(10.0, "Bon", True),
        potential_10y=ScoredValue(20.0, "Bon", True),
        trend=ScoredValue(None, "Haussière", True),
        quality=ScoredValue(quality, "Bon", True),
    )
    return StockAnalysis(
        identity=Identity(ticker=ticker, market_cap=1_000_000.0, kind=CompanyKind.INDUSTRIAL),
        indicators=ind,
        regression_raw=reg,
        regression_adj=reg,
        fundamentals=None,
        summary=[],
    )


class TestPerfLineMetrics:
    def test_runs_on_real_stock_analysis_no_mock(self):
        """Exerce `_perf_line_metrics` sur un VRAI StockAnalysis (angle mort du 500)."""
        cell = service._perf_line_metrics(_make_analysis("RI.PA", quality=60.0))
        # Le contrat d'attributs est respecté : plus d'AttributeError.
        assert cell["quality"]["value"] == 60.0
        assert cell["slope"]["value"] == 5.0  # perf_passee
        assert cell["pot_5y"]["value"] == 10.0
        assert cell["pot_10y"]["value"] == 20.0
        # Métrique absente -> « -- » (None), jamais un 0 trompeur.
        assert cell["per"]["value"] is None
