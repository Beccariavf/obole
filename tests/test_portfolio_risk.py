"""Risque du portefeuille (#17.3) — drawdown, corrélation, rendements mensuels.

Trois familles :

- **engine/portfolio** (pur) : `drawdown_series`, `drawdown_metrics`,
  `realized_volatility`, `monthly_returns`, `correlation_matrix`,
  `correlation_order`, `log_returns_by_ticker` — sur fixtures déterministes.
- **services/portfolio.risk** : assemblage data + engine, prix mockés.
- **invariant** : `engine/portfolio.py` reste pur.
"""

from __future__ import annotations

import tempfile

import numpy as np
import pandas as pd
import pytest

from obole import config
from obole.data import portfolio as portfolio_data
from obole.data.yahoo import TickerNotFound
from obole.engine import portfolio as engine
from obole.models import PriceSeries
from obole.services import portfolio as service

# --- Drawdown ----------------------------------------------------------------


class TestDrawdownSeries:
    def test_monotonic_increasing_is_zero(self):
        assert engine.drawdown_series([100.0, 110.0, 120.0]) == [0.0, 0.0, 0.0]

    def test_known_trough(self):
        # Pic 100 -> creux 80 = -20 %, puis remontée à 90 = -10 %.
        dd = engine.drawdown_series([100.0, 80.0, 90.0])
        assert dd[0] == 0.0
        assert dd[1] == pytest.approx(-20.0)
        assert dd[2] == pytest.approx(-10.0)

    def test_new_peak_resets(self):
        dd = engine.drawdown_series([100.0, 90.0, 120.0, 114.0])
        assert dd[2] == 0.0
        assert dd[3] == pytest.approx(-5.0)

    def test_none_preserved(self):
        assert engine.drawdown_series([100.0, None, 90.0]) == [0.0, None, pytest.approx(-10.0)]

    def test_empty(self):
        assert engine.drawdown_series([]) == []


class TestDrawdownMetrics:
    def test_max_and_current(self):
        dates = ["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-10"]
        values = [1.0, 0.8, 0.9, 0.85]
        m = engine.drawdown_metrics(values, dates)
        assert m["max_drawdown_pct"] == pytest.approx(-20.0)
        assert m["current_drawdown_pct"] == pytest.approx(-15.0)
        assert m["recovered"] is False
        assert m["peak_at"] == "2020-01-01"
        assert m["trough_at"] == "2020-01-02"

    def test_recovered_when_last_is_peak(self):
        dates = ["2020-01-01", "2020-01-02", "2020-01-03"]
        m = engine.drawdown_metrics([1.0, 0.9, 1.1], dates)
        assert m["current_drawdown_pct"] == 0.0
        assert m["recovered"] is True

    def test_longest_recovery_days(self):
        dates = ["2020-01-01", "2020-01-11", "2020-01-21", "2020-02-01"]
        # pic J0 -> creux J10 -> récupération J21 : 20 jours.
        m = engine.drawdown_metrics([1.0, 0.8, 1.0, 0.95], dates)
        assert m["longest_recovery_days"] == 20

    def test_no_dates_only_time_free_metrics(self):
        m = engine.drawdown_metrics([1.0, 0.9])
        assert m["max_drawdown_pct"] == pytest.approx(-10.0)
        assert m["longest_recovery_days"] == 0

    def test_flat_series(self):
        m = engine.drawdown_metrics([1.0, 1.0, 1.0], ["a", "b", "c"])
        assert m["max_drawdown_pct"] == 0.0
        assert m["recovered"] is True


class TestRealizedVolatility:
    def test_none_under_two_returns(self):
        assert engine.realized_volatility([1.0]) is None
        assert engine.realized_volatility([1.0, 1.0]) is None

    def test_zero_for_constant_growth(self):
        # Croissance géométrique constante : rendements log identiques -> vol 0.
        assert engine.realized_volatility([1.0, 2.0, 4.0]) == pytest.approx(0.0)

    def test_positive_for_varying_series(self):
        vol = engine.realized_volatility([1.0, 1.1, 1.0, 1.2, 1.1])
        assert vol is not None and vol > 0


# --- Rendements mensuels -----------------------------------------------------


class TestMonthlyReturns:
    def test_single_full_month(self):
        perf = [0.0, 5.0]  # cumulé : 0 % puis +5 %
        dates = ["2024-01-02", "2024-01-31"]
        months = engine.monthly_returns(perf, dates)
        assert months == [{"year": 2024, "month": 1, "pct": 5.0}]

    def test_two_months_décumulé(self):
        # Janvier +10 % (0 -> 10), février +9.09 % ((1.20/1.10 - 1) = +9.09 %)
        perf = [0.0, 10.0, 20.0]
        dates = ["2024-01-10", "2024-01-31", "2024-02-28"]
        months = engine.monthly_returns(perf, dates)
        assert months[0]["pct"] == pytest.approx(10.0)
        assert months[1]["pct"] == pytest.approx((1.20 / 1.10 - 1) * 100, abs=0.01)

    def test_none_ignored(self):
        months = engine.monthly_returns([None, 5.0], ["2024-01-31", "2024-01-31"])
        assert months[0]["pct"] == 0.0

    def test_mismatched_lengths(self):
        assert engine.monthly_returns([1.0], []) == []


# --- Corrélation -------------------------------------------------------------


def _rets(values: list[float]) -> dict[str, float]:
    return {f"2024-01-{i + 1:02d}": v for i, v in enumerate(values)}


class TestCorrelationMatrix:
    def test_diagonal_one_and_symmetry(self):
        returns = {
            "A": _rets([0.01, -0.02, 0.03, 0.01, -0.01, 0.02]),
            "B": _rets([0.02, -0.04, 0.06, 0.02, -0.02, 0.04]),
            "C": _rets([-0.01, 0.02, -0.03, 0.00, 0.01, 0.00]),
        }
        out = engine.correlation_matrix(returns, min_obs=3)
        assert out["tickers"] == ["A", "B", "C"]
        m = out["matrix"]
        for i in range(3):
            assert m[i][i] == 1.0
        assert m[0][1] == m[1][0]
        # A et B sont proportionnels : corrélation ~ 1.
        assert m[0][1] == pytest.approx(1.0, abs=1e-6)

    def test_lines_under_min_obs_excluded(self):
        returns = {
            "A": _rets([0.01, 0.02, 0.03, 0.01]),
            "B": _rets([0.02, 0.04, 0.06, 0.02]),
            "SHORT": _rets([0.01, 0.02]),
        }
        out = engine.correlation_matrix(returns, min_obs=3)
        assert out["tickers"] == ["A", "B"]
        assert out["excluded"] == [{"ticker": "SHORT", "obs": 2}]

    def test_fewer_than_two_lines(self):
        out = engine.correlation_matrix({"A": _rets([0.01, 0.02, 0.03])}, min_obs=2)
        assert out["tickers"] == ["A"]
        assert out["matrix"] == [[1.0]]

    def test_pair_under_min_common_obs_is_none(self):
        returns = {
            "A": _rets([0.01, 0.02, 0.03, 0.04]),
            "B": {"2024-01-01": 0.01, "2024-01-02": 0.02, "2024-01-05": 0.03, "2024-01-06": 0.04},
        }
        out = engine.correlation_matrix(returns, min_obs=3)
        # Aucune date commune en nombre suffisant -> None (pas un 0).
        assert out["matrix"][0][1] is None

    def test_zero_variance_is_none(self):
        returns = {"A": _rets([0.01, 0.01, 0.01]), "B": _rets([0.02, 0.03, 0.04])}
        out = engine.correlation_matrix(returns, min_obs=3)
        assert out["matrix"][0][1] is None


class TestCorrelationOrder:
    def test_non_trivial_order_groups_blocks(self):
        # A et B corrélés ; C isolé. Ordre -> A,B contigus (ou B,A).
        tickers = ["A", "B", "C"]
        matrix = [
            [1.0, 0.9, 0.0],
            [0.9, 1.0, 0.1],
            [0.0, 0.1, 1.0],
        ]
        order = engine.correlation_order(tickers, matrix)
        assert order[0] in (0, 1) and order[1] in (0, 1)
        assert order[2] == 2

    def test_two_or_fewer_identity(self):
        assert engine.correlation_order(["A", "B"], [[1.0, 0.5], [0.5, 1.0]]) == [0, 1]
        assert engine.correlation_order(["A"], [[1.0]]) == [0]


class TestLogReturnsByTicker:
    def test_aligned_and_positive_only(self):
        dates = ["2024-01-01", "2024-01-02", "2024-01-03"]
        prices = {"A": [100.0, 110.0, 0.0], "B": [50.0, None, 55.0]}
        out = engine.log_returns_by_ticker(dates, prices)
        assert set(out["A"]) == {"2024-01-02"}  # le passage par 0 est ignoré
        assert out["A"]["2024-01-02"] == pytest.approx(np.log(1.1))
        assert set(out["B"]) == set()  # trou -> aucun rendement


class TestMeanOffdiagonal:
    def test_averages_only_offdiagonal(self):
        # Diagonale (1.0) ignorée : moyenne de 0.8 et 0.2.
        m = [[1.0, 0.8], [0.4, 1.0]]
        assert engine.mean_offdiagonal(m) == pytest.approx((0.8 + 0.4) / 2)

    def test_ignores_none(self):
        m = [[1.0, 0.8, None], [0.8, 1.0, 0.2], [None, 0.2, 1.0]]
        assert engine.mean_offdiagonal(m) == pytest.approx((0.8 + 0.2) / 2)

    def test_none_when_no_pair(self):
        assert engine.mean_offdiagonal([[1.0]]) is None
        assert engine.mean_offdiagonal([]) is None
        assert engine.mean_offdiagonal([[1.0, None], [None, 1.0]]) is None


class TestCorrelationRow:
    def test_correlates_target_against_each_series(self):
        # B = +A -> corrélation 1 ; C = -A -> corrélation -1.
        a = {"d1": 0.01, "d2": -0.02, "d3": 0.03}
        b = {"d1": 0.01, "d2": -0.02, "d3": 0.03}
        c = {"d1": -0.01, "d2": 0.02, "d3": -0.03}
        out = engine.correlation_row(a, {"B": b, "C": c}, min_obs=2)
        assert out["B"] == pytest.approx(1.0)
        assert out["C"] == pytest.approx(-1.0)

    def test_preserves_key_order(self):
        a = {"d1": 0.01, "d2": -0.02, "d3": 0.03}
        out = engine.correlation_row(a, {"Z": a, "A": a}, min_obs=2)
        assert list(out) == ["Z", "A"]

    def test_none_below_min_obs(self):
        a = {"d1": 0.01, "d2": -0.02}
        out = engine.correlation_row(a, {"B": a}, min_obs=5)
        assert out["B"] is None


# --- Service (assemblage) ----------------------------------------------------


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


class TestServiceRisk:
    def _universe(self):
        return {
            "RI.PA": _series(100.0, 0.0006, seed=1),
            "AI.PA": _series(150.0, 0.0004, seed=2),
            "CW8.PA": _series(400.0, 0.0005, seed=3),
        }

    def _seed(self):
        acc = portfolio_data.create_account("PEA")
        for ticker, price in (("RI.PA", 100.0), ("AI.PA", 150.0)):
            portfolio_data.add_transaction(acc, ticker, "buy", "2022-01-03", 10, price)
        return acc

    def test_empty_portfolio(self):
        acc = portfolio_data.create_account("PEA")
        out = service.risk(acc, None, None)
        assert out["dates"] == []
        assert out["correlation"]["matrix"] == []

    def test_full_payload_structure(self, monkeypatch):
        acc = self._seed()
        universe = self._universe()

        def _fetch(ticker):
            if ticker not in universe:
                raise TickerNotFound(ticker)
            return universe[ticker]

        monkeypatch.setattr("obole.services.portfolio.yahoo.fetch_prices", _fetch)
        out = service.risk(acc, "CW8.PA", "max")
        assert len(out["drawdown"]) == len(out["dates"])
        assert all(v is None or v <= 0 for v in out["drawdown"])
        assert set(out["correlation"]["tickers"]) == {"RI.PA", "AI.PA"}
        assert len(out["correlation"]["matrix"]) == 2
        assert out["correlation"]["matrix"][0][0] == 1.0
        assert out["corr_avg"] == pytest.approx(out["correlation"]["matrix"][0][1])
        assert out["metrics"]["max_drawdown_pct"] <= 0
        assert out["benchmark"]["ticker"] == "CW8.PA"
        assert out["period"] == "max"

    def test_sold_line_excluded_from_correlation(self, monkeypatch):
        """Une ligne soldée ne figure PAS dans la matrice (#17.3, retour utilisateur).

        Elle reste dans la courbe TWR (sa performance passée est légitime) mais
        n'a rien à faire dans les corrélations, qui ne portent que sur ce qui est
        détenu aujourd'hui.
        """
        acc = portfolio_data.create_account("PEA")
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2022-01-03", 10, 100.0)
        portfolio_data.add_transaction(acc, "AI.PA", "buy", "2022-01-03", 10, 150.0)
        # AI.PA entièrement soldée plus tard.
        portfolio_data.add_transaction(acc, "AI.PA", "sell", "2024-01-03", 10, 200.0)
        universe = self._universe()

        def _fetch(ticker):
            if ticker not in universe:
                raise TickerNotFound(ticker)
            return universe[ticker]

        monkeypatch.setattr("obole.services.portfolio.yahoo.fetch_prices", _fetch)
        out = service.risk(acc, "CW8.PA", "max")
        assert out["correlation"]["tickers"] == ["RI.PA"]
        # La ligne soldée n'est pas non plus signalée comme « écartée ».
        assert [e["ticker"] for e in out["correlation"]["excluded"]] == []
        # Mais la courbe couvre bien son historique (dates non vides).
        assert out["dates"]

    def test_tag_scope_restricts_tickers(self, monkeypatch):
        acc = portfolio_data.create_account("PEA")
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2022-01-03", 10, 100.0, tag="Div")
        portfolio_data.add_transaction(acc, "AI.PA", "buy", "2022-01-03", 10, 150.0)
        universe = self._universe()

        def _fetch(ticker):
            if ticker not in universe:
                raise TickerNotFound(ticker)
            return universe[ticker]

        monkeypatch.setattr("obole.services.portfolio.yahoo.fetch_prices", _fetch)
        out = service.risk(acc, "CW8.PA", "max", tag="Div")
        assert out["correlation"]["tickers"] == ["RI.PA"]

    def test_unknown_benchmark_raises(self, monkeypatch):
        self._seed()

        def _fetch(ticker):
            raise TickerNotFound(ticker)

        monkeypatch.setattr("obole.services.portfolio.yahoo.fetch_prices", _fetch)
        with pytest.raises(ValueError, match="Benchmark introuvable"):
            service.risk(None, "ZZZ.PA", "max")

    def test_short_history_line_excluded(self, monkeypatch):
        acc = portfolio_data.create_account("PEA")
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2022-01-03", 10, 100.0)
        portfolio_data.add_transaction(acc, "AI.PA", "buy", "2022-01-03", 10, 150.0)
        universe = {
            "RI.PA": _series(100.0, 0.0006, periods=520, seed=1),
            "AI.PA": _series(150.0, 0.0004, periods=520, seed=2),
            # 10 points seulement < PORTFOLIO_CORR_MIN_OBS.
            "CW8.PA": _series(400.0, 0.0005, periods=10, seed=3),
        }

        def _fetch(ticker):
            if ticker not in universe:
                raise TickerNotFound(ticker)
            return universe[ticker]

        monkeypatch.setattr("obole.services.portfolio.yahoo.fetch_prices", _fetch)
        out = service.risk(acc, "CW8.PA", "max")
        # Le benchmark court borne la fenêtre : les lignes ont peu d'observations
        # communes -> écartées ou corrélations None, jamais de crash.
        assert out["correlation"]["tickers"] is not None


class TestServiceCorrelationTest:
    """#17.3 — impact d'un ticker candidat sur la corrélation du périmètre."""

    def _anti_correlated(self):
        """Deux séries strictement anti-corrélées (corrélation -1 exacte)."""
        idx = pd.bdate_range("2022-01-03", periods=520)
        rng = np.random.default_rng(7)
        steps = rng.normal(0, 0.01, len(idx))
        up = pd.Series(100.0 * np.exp(np.cumsum(steps)), index=idx)
        down = pd.Series(100.0 * np.exp(-np.cumsum(steps)), index=idx)
        bench = pd.Series(50.0 * np.exp(np.cumsum(steps) * 0.5), index=idx)
        return up, down, bench

    def _seed_and_patch(self, monkeypatch):
        acc = portfolio_data.create_account("PEA")
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2022-01-03", 10, 100.0)
        portfolio_data.add_transaction(acc, "AI.PA", "buy", "2022-01-03", 10, 50.0)
        up, down, bench = self._anti_correlated()
        universe = {
            "RI.PA": PriceSeries(raw=up, adjusted=up, fetched_at=up.index[-1].date()),
            "AI.PA": PriceSeries(raw=down, adjusted=down, fetched_at=down.index[-1].date()),
            "CW8.PA": PriceSeries(raw=bench, adjusted=bench, fetched_at=bench.index[-1].date()),
            # Candidat = même série que RI.PA : corrélé +1 à RI, -1 à AI.
            "CAND.PA": PriceSeries(raw=up, adjusted=up, fetched_at=up.index[-1].date()),
        }

        def _fetch(ticker):
            if ticker not in universe:
                raise TickerNotFound(ticker)
            return universe[ticker]

        monkeypatch.setattr("obole.services.portfolio.yahoo.fetch_prices", _fetch)
        return acc

    def test_impact_of_highly_correlated_candidate(self, monkeypatch):
        acc = self._seed_and_patch(monkeypatch)
        out = service.correlation_test(acc, "CW8.PA", "max", None, "CAND.PA")
        assert out["ticker"] == "CAND.PA"
        assert len(out["row"]) == len(out["tickers"]) == 2
        # Le candidat suit RI.PA (+1) et inverse AI.PA (-1).
        values = dict(zip(out["tickers"], out["row"], strict=True))
        assert values["RI.PA"] == pytest.approx(1.0, abs=1e-3)
        assert values["AI.PA"] == pytest.approx(-1.0, abs=1e-3)
        # Sans le candidat, la moyenne hors diagonale vaut -1 (deux lignes
        # strictement anti-corrélées) ; avec lui, [-1, +1, -1] -> -1/3.
        assert out["current_avg"] == pytest.approx(-1.0, abs=1e-3)
        assert out["new_avg"] == pytest.approx(-1.0 / 3.0, abs=1e-3)
        assert out["delta"] == pytest.approx(2.0 / 3.0, abs=1e-3)

    def test_current_avg_matches_risk_matrix(self, monkeypatch):
        acc = self._seed_and_patch(monkeypatch)
        risk = service.risk(acc, "CW8.PA", "max")
        expected = engine.mean_offdiagonal(risk["correlation"]["matrix"])
        out = service.correlation_test(acc, "CW8.PA", "max", None, "CAND.PA")
        assert out["current_avg"] == pytest.approx(round(expected, 4))

    def test_empty_ticker_raises(self, monkeypatch):
        acc = self._seed_and_patch(monkeypatch)
        with pytest.raises(ValueError, match="vide"):
            service.correlation_test(acc, "CW8.PA", "max", None, "   ")

    def test_unknown_ticker_raises(self, monkeypatch):
        acc = self._seed_and_patch(monkeypatch)
        with pytest.raises(ValueError, match="introuvable"):
            service.correlation_test(acc, "CW8.PA", "max", None, "ZZZ.PA")

    def test_empty_portfolio_raises(self):
        acc = portfolio_data.create_account("PEA")
        with pytest.raises(ValueError, match="Aucune transaction"):
            service.correlation_test(acc, "CW8.PA", "max", None, "CAND.PA")

    def test_already_held_raises(self, monkeypatch):
        acc = self._seed_and_patch(monkeypatch)
        with pytest.raises(ValueError, match="déjà"):
            service.correlation_test(acc, "CW8.PA", "max", None, "AI.PA")

    def test_short_history_candidate_warns(self, monkeypatch):
        acc = self._seed_and_patch(monkeypatch)
        base_fetch = service.yahoo.fetch_prices  # déjà patché par _seed_and_patch
        idx = pd.bdate_range("2024-12-01", periods=5)
        short = pd.Series(np.linspace(10.0, 11.0, 5), index=idx)

        def _fetch(ticker):
            if ticker == "SHORT.PA":
                return PriceSeries(raw=short, adjusted=short, fetched_at=idx[-1].date())
            return base_fetch(ticker)

        monkeypatch.setattr("obole.services.portfolio.yahoo.fetch_prices", _fetch)
        out = service.correlation_test(acc, "CW8.PA", "max", None, "SHORT.PA")
        assert out["obs"] < config.PORTFOLIO_CORR_MIN_OBS
        assert out["warning"] and "Historique insuffisant" in out["warning"]
        # Toutes les paires sont None -> la moyenne ne bouge pas.
        assert out["delta"] == pytest.approx(0.0)

    def test_tz_aware_series_are_aligned_not_dropped(self, monkeypatch):
        """Régression #24 : les index Yahoo sont tz-aware, l'axe du contexte est naïf.

        Un `reindex` entre un index tz-aware (`Europe/Paris`) et l'axe naïf
        (`_trading_index`) ne matche RIEN : le candidat ressortait à `obs=0` et une
        ligne de `None` (corrélations perdues), silencieusement. Les fixtures
        ci-dessus sont naïves, ce qui masquait le défaut. On seed ici des séries
        tz-aware comme les vraies (les autres méthodes de risque/corrélation
        passaient déjà par `_align`).
        """
        acc = portfolio_data.create_account("PEA")
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2022-01-03", 10, 100.0)
        portfolio_data.add_transaction(acc, "AI.PA", "buy", "2022-01-03", 10, 50.0)
        up, down, bench = self._anti_correlated()
        tz = "Europe/Paris"
        universe = {
            "RI.PA": PriceSeries(
                raw=up.tz_localize(tz), adjusted=up.tz_localize(tz), fetched_at=up.index[-1].date()
            ),
            "AI.PA": PriceSeries(
                raw=down.tz_localize(tz),
                adjusted=down.tz_localize(tz),
                fetched_at=down.index[-1].date(),
            ),
            "CW8.PA": PriceSeries(
                raw=bench.tz_localize(tz),
                adjusted=bench.tz_localize(tz),
                fetched_at=bench.index[-1].date(),
            ),
            "CAND.PA": PriceSeries(
                raw=up.tz_localize(tz), adjusted=up.tz_localize(tz), fetched_at=up.index[-1].date()
            ),
        }

        def _fetch(ticker):
            if ticker not in universe:
                raise TickerNotFound(ticker)
            return universe[ticker]

        monkeypatch.setattr("obole.services.portfolio.yahoo.fetch_prices", _fetch)
        out = service.correlation_test(acc, "CW8.PA", "max", None, "CAND.PA")
        # Alignement effectif : observations réelles et corrélations non nulles.
        assert out["obs"] > 0
        assert all(v is not None for v in out["row"])
        values = dict(zip(out["tickers"], out["row"], strict=True))
        assert values["RI.PA"] == pytest.approx(1.0, abs=1e-3)
        assert values["AI.PA"] == pytest.approx(-1.0, abs=1e-3)


class TestEnginePurity:
    def test_no_io_imports(self):
        import inspect

        src = inspect.getsource(engine)
        assert "from obole.data" not in src
        assert "from obole.services" not in src
        assert "import obole.data" not in src
