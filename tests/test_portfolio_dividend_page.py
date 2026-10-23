"""Page Dividende du portefeuille (#17.5) — cas d'usage `dividend_page`.

Sans réseau : prix mockés (`yahoo.fetch_prices`), analyse par ligne mockée sur un
VRAI `StockAnalysis` (contrat d'attributs verrouillé), base isolée temporaire.
Couvre le revenu par mois/payeur, l'exclusion des propositions, les KPI agrégés
(rendement, yield on cost, payout, shareholder yield) et la double TWR.
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


def _recent_events() -> dict[str, float]:
    """Deux versements DANS la fenêtre TTM (le DPA courant se lit sur 365 jours).

    Les dates sont relatives à aujourd'hui : une fixture figée en 2024 sortirait
    de la fenêtre au fil du temps et ferait tomber silencieusement le rendement.
    """
    today = pd.Timestamp.today().normalize()
    first = (today - pd.Timedelta(days=200)).strftime("%Y-%m-%d")
    second = (today - pd.Timedelta(days=60)).strftime("%Y-%m-%d")
    return {first: 3.5, second: 4.0}


def _make_analysis(
    ticker: str = "RI.PA",
    events: dict[str, float] | None = None,
    dividend_paid: dict[int, float] | None = None,
    net_income: float | None = None,
    buybacks_ps: dict[int, float] | None = None,
) -> object:
    """VRAI `StockAnalysis` portant un payload dividende réaliste."""
    from obole.models import (
        CompanyKind,
        Fundamentals,
        Identity,
        Indicators,
        RegressionResult,
        ScoredValue,
        StockAnalysis,
    )

    kind = CompanyKind.INDUSTRIAL

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
        quality=ScoredValue(60.0, "Bon", True),
    )
    table = None
    if net_income is not None:
        table = pd.DataFrame({pd.Timestamp("2024-12-31"): [net_income]}, index=["Bénéfice net"])
    dividend = None
    if events is not None:
        dividend = {
            "events": events,
            "per_share": {},
            "buybacks_available": buybacks_ps is not None,
            "buybacks_per_share": buybacks_ps,
            "dividend_paid_history": dividend_paid,
            "payout_history": {"earnings_payout": {2024: 45.0}},
            "stats": {"cagr": {5: 3.5, 10: 4.0}},
        }
    fundamentals = None
    if dividend:
        fundamentals = Fundamentals(
            table=table if table is not None else pd.DataFrame(),
            kind=kind,
            available_years=1,
            fetched_at=__import__("datetime").date(2024, 12, 31),
            dividend=dividend,
        )
    return StockAnalysis(
        identity=Identity(ticker=ticker, market_cap=1_000_000.0, kind=kind),
        indicators=ind,
        regression_raw=reg,
        regression_adj=reg,
        fundamentals=fundamentals,
        summary=[],
    )


class TestDividendIncomeEngine:
    def test_groups_by_year_and_month(self):
        from obole.engine import portfolio as engine

        out = engine.dividend_income(
            [
                {
                    "ticker": "RI.PA",
                    "pay_date": "2024-06-15",
                    "amount": 35.0,
                    "status": "confirmed",
                },
                {
                    "ticker": "RI.PA",
                    "pay_date": "2024-12-01",
                    "amount": 10.0,
                    "status": "confirmed",
                },
            ]
        )
        assert out["years"] == [2024]
        (row,) = out["rows"]
        assert row["months"]["6"] == 35.0
        assert row["months"]["12"] == 10.0
        assert row["months"]["1"] is None  # mois vide = None, jamais 0
        assert row["total_confirmed"] == 45.0
        assert out["total_confirmed"] == 45.0

    def test_excludes_proposed_from_confirmed(self):
        from obole.engine import portfolio as engine

        out = engine.dividend_income(
            [
                {
                    "ticker": "RI.PA",
                    "pay_date": "2024-06-15",
                    "amount": 35.0,
                    "status": "confirmed",
                },
                {"ticker": "RI.PA", "pay_date": "2024-09-15", "amount": 99.0, "status": "proposed"},
            ]
        )
        (row,) = out["rows"]
        assert row["total_confirmed"] == 35.0
        assert row["total_proposed"] == 99.0
        assert row["months"]["9"] is None  # une proposition ne devient pas un mois reçu
        assert out["total_confirmed"] == 35.0

    def test_share_pct_sums_to_100(self):
        from obole.engine import portfolio as engine

        out = engine.dividend_income(
            [
                {
                    "ticker": "RI.PA",
                    "pay_date": "2024-06-15",
                    "amount": 75.0,
                    "status": "confirmed",
                },
                {
                    "ticker": "AI.PA",
                    "pay_date": "2024-05-15",
                    "amount": 25.0,
                    "status": "confirmed",
                },
            ]
        )
        assert [c["ticker"] for c in out["by_company"]] == ["RI.PA", "AI.PA"]
        assert sum(c["share_pct"] for c in out["by_company"]) == pytest.approx(100.0)
        assert out["by_company"][0]["share_pct"] == pytest.approx(75.0)

    def test_empty_dividends(self):
        from obole.engine import portfolio as engine

        out = engine.dividend_income([])
        assert out["years"] == []
        assert out["by_company"] == []
        assert out["total_confirmed"] == 0.0


class TestIncomeConcentration:
    def test_effective_payers_count(self):
        from obole.engine import portfolio as engine

        out = engine.income_concentration({"A": 25.0, "B": 25.0, "C": 25.0, "D": 25.0}, 2)
        assert out["n_eff"] == pytest.approx(4.0)
        assert out["top_n_pct"] == pytest.approx(50.0)
        assert out["first_pct"] == pytest.approx(25.0)
        assert out["payers"] == 4

    def test_concentrated_portfolio_has_low_effective_count(self):
        from obole.engine import portfolio as engine

        out = engine.income_concentration({"A": 70.0, "B": 10.0, "C": 10.0, "D": 10.0}, 2)
        assert out["n_eff"] is not None
        assert out["n_eff"] < 2.0  # 4 payeurs mais un seul compte vraiment
        assert out["first_ticker"] == "A"

    def test_empty(self):
        from obole.engine import portfolio as engine

        out = engine.income_concentration({}, 5)
        assert out["n_eff"] is None
        assert out["payers"] == 0


class TestDividendMetrics:
    def test_yield_on_cost(self):
        from obole.engine import portfolio as engine

        # Numérateur = revenu TTM (et non les dividendes cumulés, qui gonflent
        # avec l'ancienneté de la position).
        out = engine.dividend_metrics(
            dividends_total=500.0,
            cost_basis_total=1000.0,
            ttm_income=40.0,
        )
        assert out["yield_on_cost_pct"] == pytest.approx(4.0)

    def test_yield_none_without_dps(self):
        from obole.engine import portfolio as engine

        out = engine.dividend_metrics(
            dividends_total=0.0,
            cost_basis_total=1000.0,
            ttm_income=None,
            dps_ttm_by_ticker={"RI.PA": None},
            quantity_by_ticker={"RI.PA": 10},
            market_value_by_ticker={"RI.PA": 1000.0},
        )
        assert out["yield_pct"] is None  # jamais 0

    def test_yield_aggregates_on_market_value(self):
        from obole.engine import portfolio as engine

        out = engine.dividend_metrics(
            dividends_total=0.0,
            cost_basis_total=2000.0,
            ttm_income=40.0,
            dps_ttm_by_ticker={"RI.PA": 2.0, "AI.PA": 2.0},
            quantity_by_ticker={"RI.PA": 10, "AI.PA": 10},
            market_value_by_ticker={"RI.PA": 1000.0, "AI.PA": 1000.0},
        )
        # (2×10 + 2×10) / 2000 = 2 %
        assert out["yield_pct"] == pytest.approx(2.0)
        assert out["yield_coverage_pct"] == pytest.approx(100.0)

    def test_payout_excludes_negative_earnings_and_reports_coverage(self):
        from obole.engine import portfolio as engine

        out = engine.dividend_metrics(
            dividends_total=0.0,
            cost_basis_total=2000.0,
            ttm_income=None,
            market_value_by_ticker={"A": 1000.0, "B": 1000.0},
            dividend_paid_by_ticker={"A": 100.0, "B": 100.0},
            net_income_by_ticker={"A": 200.0, "B": -50.0},
        )
        # Seule A est exploitable : 100/200 = 50 %, couverture 50 % de la valeur.
        assert out["payout_pct"] == pytest.approx(50.0)
        assert out["payout_coverage_pct"] == pytest.approx(50.0)

    def test_shareholder_yield_uses_per_share_amounts(self):
        from obole.engine import portfolio as engine

        out = engine.dividend_metrics(
            dividends_total=0.0,
            cost_basis_total=1000.0,
            ttm_income=None,
            quantity_by_ticker={"A": 10},
            market_value_by_ticker={"A": 1000.0},
            shareholder_per_share_by_ticker={"A": 4.0},  # 2 dividende + 2 rachat
        )
        # (4 × 10) / 1000 = 4 %
        assert out["shareholder_yield_pct"] == pytest.approx(4.0)

    def test_zero_weight_line_ignored(self):
        from obole.engine import portfolio as engine

        out = engine.dividend_metrics(
            dividends_total=0.0,
            cost_basis_total=0.0,
            ttm_income=None,
            dps_ttm_by_ticker={"GHOST": 5.0},
            quantity_by_ticker={"GHOST": 0.0},
            market_value_by_ticker={},
        )
        assert out["yield_pct"] is None
        assert out["yield_on_cost_pct"] is None


class TestDividendLine:
    def test_gap_and_flags(self):
        from obole.engine import portfolio as engine

        line = engine.dividend_line(
            ticker="RI.PA",
            quantity=10,
            cost_basis=1000.0,
            market_value=1200.0,
            dps_ttm=4.0,
            income_share_pct=18.0,
            capital_share_pct=12.0,
        )
        assert line["div_yield_pct"] == pytest.approx(4.0 / 120.0 * 100.0, abs=0.01)
        assert line["div_to_cost_pct"] == pytest.approx(4.0 / 100.0 * 100.0, abs=0.01)
        assert line["gap_pp"] == pytest.approx(6.0)
        assert "payout_absent" in line["flags"]

    def test_missing_cost_flagged(self):
        from obole.engine import portfolio as engine

        line = engine.dividend_line(
            ticker="X",
            quantity=10,
            cost_basis=0.0,
            market_value=None,
            dps_ttm=None,
            income_share_pct=None,
            capital_share_pct=None,
        )
        assert line["div_yield_pct"] is None
        assert line["div_to_cost_pct"] is None
        assert "cost_absent" in line["flags"]
        assert "price_absent" in line["flags"]
        assert "dps_absent" in line["flags"]


class TestTtmPerShare:
    def test_sums_last_365_days(self):
        from obole.engine import dividends as div_engine

        out = div_engine.ttm_per_share(
            {"2024-11-01": 1.0, "2025-03-01": 2.0, "2023-06-01": 9.0},
            today="2025-06-01",
        )
        assert out == pytest.approx(3.0)  # la vieille de 2023 sort de la fenêtre

    def test_none_without_events(self):
        from obole.engine import dividends as div_engine

        assert div_engine.ttm_per_share({}, today="2025-06-01") is None


class TestServiceDividendPage:
    def _universe(self):
        return {
            "RI.PA": _series(100.0, 0.0006, seed=1),
            "AI.PA": _series(150.0, 0.0004, seed=2),
        }

    def _seed(self):
        acc = portfolio_data.create_account("PEA")
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2022-01-03", 10, 100.0)
        portfolio_data.add_transaction(acc, "AI.PA", "buy", "2022-01-03", 10, 150.0)
        portfolio_data.add_dividend(acc, "RI.PA", "2024-06-15", 35.0, "confirmed", "manual")
        portfolio_data.add_dividend(acc, "RI.PA", "2024-09-15", 40.0, "confirmed", "manual")
        portfolio_data.add_dividend(acc, "RI.PA", "2025-06-15", 99.0, "proposed", "manual")
        return acc

    def _patch(self, monkeypatch):
        universe = self._universe()

        def _fetch(ticker):
            if ticker not in universe:
                raise TickerNotFound(ticker)
            return universe[ticker]

        monkeypatch.setattr("obole.services.portfolio.yahoo.fetch_prices", _fetch)
        monkeypatch.setattr(
            "obole.services.portfolio.analysis_service.analyze",
            lambda tk, prices: _make_analysis(
                tk,
                events=_recent_events(),
                dividend_paid={2024: 200.0},
                net_income=500.0,
                buybacks_ps={2024: 0.5},
            ),
        )

    def test_empty_portfolio_structure(self):
        acc = portfolio_data.create_account("PEA")
        out = service.dividend_page(acc)
        assert out["income"]["rows"] == []
        assert out["lines"] == []
        assert out["stats"] == {}
        assert out["concentration"]["n_eff"] is None

    def test_payload_structure(self, monkeypatch):
        acc = self._seed()
        self._patch(monkeypatch)
        out = service.dividend_page(acc)
        assert out["stat_groups"] == config.PORTFOLIO_DIVIDEND_GROUPS
        assert "metrics" not in out and "months" not in out  # ni doublon ni champ mort
        keys = {m["key"] for g in config.PORTFOLIO_DIVIDEND_GROUPS for m in g["metrics"]}
        assert keys <= set(out["stats"])
        assert {line["ticker"] for line in out["lines"]} == {"RI.PA", "AI.PA"}

    def test_proposed_not_in_totals(self, monkeypatch):
        acc = self._seed()
        self._patch(monkeypatch)
        out = service.dividend_page(acc)
        # 35 + 40 = 75 confirmés ; le proposé de 99 reste à part.
        assert out["income"]["total_confirmed"] == pytest.approx(75.0)
        assert out["income"]["total_proposed"] == pytest.approx(99.0)
        assert out["stats"]["total_income"]["value"] == pytest.approx(75.0)

    def test_yield_on_cost_matches_fixture(self, monkeypatch):
        acc = self._seed()
        self._patch(monkeypatch)
        out = service.dividend_page(acc)
        # Coût = 10×100 + 10×150 = 2500. La fixture attribue le MÊME DPA TTM
        # (7,50/action) aux deux lignes : (7,5×10 + 7,5×10) / 2500 = 6 %.
        assert out["stats"]["yield_on_cost_pct"]["value"] == pytest.approx(6.0)

    def test_lines_sorted_by_income_share(self, monkeypatch):
        acc = self._seed()
        self._patch(monkeypatch)
        out = service.dividend_page(acc)
        first = out["lines"][0]
        assert first["ticker"] == "RI.PA"  # seul payeur -> plus gros poids de revenu
        assert first["income_share_pct"] == pytest.approx(100.0)

    def test_concentration_present(self, monkeypatch):
        acc = self._seed()
        self._patch(monkeypatch)
        out = service.dividend_page(acc)
        assert out["concentration"]["payers"] == 1
        assert out["concentration"]["first_ticker"] == "RI.PA"

    def test_warning_when_payout_missing(self, monkeypatch):
        acc = self._seed()
        self._patch(monkeypatch)
        out = service.dividend_page(acc)
        # Les deux lignes portent un payout dans la fixture -> aucun badge payout.
        assert not any("payout absent" in w for w in out["warnings"])

    def test_warnings_capped_at_two(self, monkeypatch):
        """Jamais plus de 2 badges : au-delà, on n'en lit aucun.

        Les manques de données sont fusionnés en UN badge de couverture ; les
        rachats absents forment le second. La page n'en affiche donc jamais trois.
        """
        acc = self._seed()
        self._patch(monkeypatch)
        out = service.dividend_page(acc)
        assert len(out["warnings"]) <= 2
        if out["warnings"]:
            assert out["warnings"][0].startswith("Couverture des données") or out["warnings"][
                0
            ].startswith("Rachats")

    def test_warning_merges_missing_data_into_one_badge(self, monkeypatch):
        acc = self._seed()
        # Payout disponible sur RI mais absent sur AI (analyse en échec) : le badge
        # de couverture doit exister et rester UNIQUE.
        universe = self._universe()

        def _fetch(ticker):
            if ticker not in universe:
                raise TickerNotFound(ticker)
            return universe[ticker]

        def _analyze(ticker, prices):
            if ticker == "AI.PA":
                return _make_analysis(ticker)  # aucun payload dividende -> payout None
            return _make_analysis(
                ticker,
                events=_recent_events(),
                dividend_paid={2024: 200.0},
                net_income=500.0,
                buybacks_ps={2024: 0.5},
            )

        monkeypatch.setattr("obole.services.portfolio.yahoo.fetch_prices", _fetch)
        monkeypatch.setattr("obole.services.portfolio.analysis_service.analyze", _analyze)
        out = service.dividend_page(acc)
        coverage_badges = [w for w in out["warnings"] if w.startswith("Couverture")]
        assert len(coverage_badges) == 1
        assert "payout absent" in coverage_badges[0]
        assert len(out["warnings"]) <= 2

    def test_service_skips_failed_analysis(self, monkeypatch):
        acc = self._seed()
        universe = self._universe()

        def _fetch(ticker):
            if ticker not in universe:
                raise TickerNotFound(ticker)
            return universe[ticker]

        def _analyze(ticker, prices):
            if ticker == "AI.PA":
                raise TickerNotFound(ticker)
            return _make_analysis(
                ticker,
                events=_recent_events(),
                dividend_paid={2024: 200.0},
                net_income=500.0,
            )

        monkeypatch.setattr("obole.services.portfolio.yahoo.fetch_prices", _fetch)
        monkeypatch.setattr("obole.services.portfolio.analysis_service.analyze", _analyze)
        out = service.dividend_page(acc)
        # La ligne en échec reste au tableau (poids de capital connu) mais sans DPA.
        assert {line["ticker"] for line in out["lines"]} == {"RI.PA", "AI.PA"}
        ai = next(line for line in out["lines"] if line["ticker"] == "AI.PA")
        assert ai["div_yield_pct"] is None
        assert "dps_absent" in ai["flags"]

    def test_dividend_contribution_present(self, monkeypatch):
        acc = self._seed()
        self._patch(monkeypatch)
        out = service.dividend_page(acc)
        # La double TWR doit produire un écart (les dividendes versent un revenu).
        assert out["stats"]["dividend_contribution_pct"]["value"] is not None

    def test_contribution_exposes_both_annualized_rates(self, monkeypatch):
        """Les DEUX taux annualisés sont dans le payload, pas seulement l'écart.

        La contribution est définie comme `TWR avec dividendes − TWR sans` : sans
        les deux termes, l'écart n'est pas auditable (et le MCP ne peut pas le
        recalculer). On vérifie la cohérence arithmétique de la soustraction.
        """
        acc = self._seed()
        self._patch(monkeypatch)
        stats = service.dividend_page(acc)["stats"]
        with_div = stats["twr_with_dividends_pct"]["value"]
        without_div = stats["twr_without_dividends_pct"]["value"]
        delta = stats["dividend_contribution_pct"]["value"]
        assert with_div is not None and without_div is not None and delta is not None
        assert with_div >= without_div  # un revenu ne peut pas dégrader le TWR ici
        assert delta == pytest.approx(with_div - without_div, abs=0.02)

    def test_no_network_on_warm_cache(self, monkeypatch):
        """Cache CHAUD complet : `dividend_page` ne déclenche AUCUN appel réseau.

        On n'instrumente pas `fetch_prices`/`analyze` (ce sont des wrappers qui
        consultent le cache AVANT le réseau : compter leurs appels ne dirait rien
        du coût réel). La bonne frontière est `yf.Ticker`, seul point sortant : on
        le rend explosif. Si le cache chaud est respecté, il n'est jamais atteint —
        même patron que la Performance (#17.4).
        """
        import datetime as _dt

        from obole.data import cache as cache_mod
        from obole.data import yahoo as yahoo_mod
        from obole.models import CompanyKind, Fundamentals, Identity

        def _explode(*_args, **_kwargs):
            raise AssertionError("appel réseau yfinance sur un cache chaud")

        acc = self._seed()

        def _fetch(ticker):
            universe = self._universe()
            if ticker not in universe:
                raise TickerNotFound(ticker)
            return universe[ticker]

        monkeypatch.setattr("obole.services.portfolio.yahoo.fetch_prices", _fetch)
        # Cache CHAUD complet : identité ET comptes valides pour `_fresh_cached`,
        # sinon un appel réseau légitime partirait (faux négatif).
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
                    fetched_at=_dt.date(2024, 1, 1),
                    market={},
                    health_rows={},
                    model_version=yahoo_mod.MODEL_VERSION,
                ),
            )
        monkeypatch.setattr("obole.data.yahoo.yf.Ticker", _explode)

        # Premier ET second appel : aucun des deux ne doit atteindre le réseau.
        service.dividend_page(acc)
        service.dividend_page(acc)
