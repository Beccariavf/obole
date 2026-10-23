"""Performance du portefeuille (#17.4) — cœur PUR `engine/portfolio`. Sans réseau.

Couvre : tableau mensuel (total annuel chaîné), contributions, Sharpe/Sortino,
agrégation pondérée, rétrospective points d'entrée/sortie.
"""

from __future__ import annotations

import math

import pytest

from obole.engine import portfolio as engine


class TestMonthlyTable:
    def _perf(self, months):
        # Deux points par mois (début ET fin) : `monthly_returns` prend la
        # dernière valeur du mois précédent comme base, donc chaque mois est
        # correctement dé-cumulé (mois partiels inclus).
        dates = []
        perf = []
        cum = 1.0
        for y, m, r in months:
            dates.append(f"{y}-{m:02d}-01")
            perf.append((cum - 1.0) * 100.0)
            cum *= 1.0 + r / 100.0
            dates.append(f"{y}-{m:02d}-28")
            perf.append((cum - 1.0) * 100.0)
        return perf, dates

    def test_total_is_chained(self):
        perf, dates = self._perf([(2024, 1, 10.0), (2024, 2, -5.0), (2024, 3, 20.0)])
        table = engine.monthly_table(perf, dates)
        assert table["years"] == [2024]
        row = table["rows"][0]
        assert row["months"]["1"] == pytest.approx(10.0)
        assert row["months"]["2"] == pytest.approx(-5.0)
        # Total = chaînage exact, pas la somme.
        expected = (1.10 * 0.95 * 1.20 - 1.0) * 100.0
        assert row["total"] == pytest.approx(expected, abs=0.02)
        assert row["total"] != pytest.approx(25.0)  # pas la somme naïve

    def test_missing_month_is_none(self):
        perf, dates = self._perf([(2024, 1, 10.0), (2024, 3, 10.0)])
        row = engine.monthly_table(perf, dates)["rows"][0]
        assert row["months"]["2"] is None
        assert row["months"]["1"] is not None

    def test_partial_first_and_last_year(self):
        perf, dates = self._perf([(2023, 12, 5.0), (2024, 1, 4.0), (2025, 2, 3.0)])
        table = engine.monthly_table(perf, dates)
        assert table["years"] == [2023, 2024, 2025]
        # 2024 n'a qu'un mois renseigné -> total = ce mois.
        y2024 = next(r for r in table["rows"] if r["year"] == 2024)
        assert y2024["months"]["1"] == pytest.approx(4.0)
        assert y2024["total"] == pytest.approx(4.0)
        assert y2024["months"]["12"] is None

    def test_empty(self):
        assert engine.monthly_table([], []) == {"years": [], "rows": []}


class TestContributions:
    def test_weighted_contribution(self):
        perf = {"A": 10.0, "B": -5.0}
        weights = {"A": 0.6, "B": 0.4}
        out = engine.contributions(perf, weights)
        assert out["by_ticker"]["A"] == pytest.approx(6.0)
        assert out["by_ticker"]["B"] == pytest.approx(-2.0)
        assert out["total"] == pytest.approx(4.0)

    def test_missing_perf_is_none(self):
        out = engine.contributions({"A": None, "B": 5.0}, {"A": 0.5, "B": 0.5})
        assert out["by_ticker"]["A"] is None
        assert out["total"] == pytest.approx(2.5)

    def test_total_none_when_nothing_exploitable(self):
        # Aucune ligne exploitable -> total None (jamais un 0 trompeur).
        out = engine.contributions({"A": None, "B": None}, {"A": 0.5, "B": 0.5})
        assert out["by_ticker"] == {"A": None, "B": None}
        assert out["total"] is None


class TestSharpeSortino:
    def test_no_data(self):
        assert engine.sharpe_ratio([]) is None
        assert engine.sortino_ratio([]) is None

    def test_flat_series_zero_vol(self):
        # Série plate : volatilité nulle -> Sharpe None (pas d'infini).
        assert engine.sharpe_ratio([1.0, 1.0, 1.0, 1.0]) is None

    def test_sharpe_positive_for_rising(self):
        vals = [1.0 * math.exp(0.0005 * i) for i in range(60)]
        s = engine.sharpe_ratio(vals, risk_free_pct=0.0)
        assert s is not None and s > 0

    def test_risk_free_reduces_sharpe(self):
        vals = [1.0 * math.exp(0.0005 * i) for i in range(60)]
        s0 = engine.sharpe_ratio(vals, risk_free_pct=0.0)
        s2 = engine.sharpe_ratio(vals, risk_free_pct=2.0)
        assert s0 > s2

    def test_sortino_ignores_upside_vol(self):
        # Descente puis remontée : Sortino calculable, dénominateur = baisses.
        vals = [100.0, 98.0, 97.0, 101.0, 103.0, 104.0, 105.0]
        so = engine.sortino_ratio(vals, risk_free_pct=0.0)
        assert so is not None

    def test_sortino_none_without_losses(self):
        # Aucune baisse -> dénominateur nul -> None.
        assert engine.sortino_ratio([1.0, 2.0, 3.0, 4.0]) is None


class TestWeightedMean:
    def test_weighted_differs_from_simple(self):
        values = [10.0, 20.0]
        weights = [0.9, 0.1]
        assert engine.weighted_mean(values, weights) == pytest.approx(11.0)
        assert engine.weighted_mean(values, weights) != pytest.approx(15.0)

    def test_none_excluded_from_denominator(self):
        # A absent : la moyenne porte sur B (poids recalé sur les points connus).
        assert engine.weighted_mean([None, 20.0], [0.5, 0.5]) == pytest.approx(20.0)

    def test_all_none(self):
        assert engine.weighted_mean([None, None], [0.5, 0.5]) is None

    def test_zero_weight(self):
        assert engine.weighted_mean([10.0], [0.0]) is None


class TestAggregateStatistics:
    GROUPS = [
        {
            "id": "g",
            "title": "G",
            "metrics": [
                {"key": "roe", "label": "ROE", "unit": "pct", "higher_is_better": True},
            ],
        },
    ]

    def test_weighted_value_and_majority_good(self):
        rows = [
            {"roe": {"value": 10.0, "good": True}},
            {"roe": {"value": 30.0, "good": False}},
        ]
        out = engine.aggregate_statistics(rows, [0.8, 0.2], self.GROUPS)
        assert out["roe"]["value"] == pytest.approx(14.0)
        assert out["roe"]["good"] is True  # 80 % du poids est « good »

    def test_missing_excluded(self):
        rows = [{"roe": {"value": None, "good": None}}, {"roe": {"value": 20.0, "good": True}}]
        out = engine.aggregate_statistics(rows, [0.5, 0.5], self.GROUPS)
        assert out["roe"]["value"] == pytest.approx(20.0)
        assert out["roe"]["good"] is True


class TestEntryExitRetrospective:
    def test_buy_beats_benchmark(self):
        dates = ["2024-01-01", "2024-06-01", "2025-01-01"]
        prices = {"A": [100.0, 130.0, 150.0]}
        bench = [100.0, 105.0, 110.0]
        tx = [
            {
                "id": 1,
                "ticker": "A",
                "side": "buy",
                "trade_date": "2024-01-01",
                "quantity": 10,
                "price": 100.0,
            }
        ]
        (row,) = engine.entry_exit_retrospective(dates, tx, prices, bench)
        assert row["return_pct"] == pytest.approx(50.0)
        assert row["benchmark_pct"] == pytest.approx(10.0)
        assert row["delta_pct"] == pytest.approx(40.0)  # a battu

    def test_buy_lags_benchmark(self):
        dates = ["2024-01-01", "2025-01-01"]
        prices = {"A": [100.0, 102.0]}
        bench = [100.0, 120.0]
        tx = [
            {
                "id": 1,
                "ticker": "A",
                "side": "buy",
                "trade_date": "2024-01-01",
                "quantity": 1,
                "price": 100.0,
            }
        ]
        (row,) = engine.entry_exit_retrospective(dates, tx, prices, bench)
        assert row["delta_pct"] < 0

    def test_missing_price_series_skipped(self):
        dates = ["2024-01-01"]
        tx = [
            {
                "id": 1,
                "ticker": "Z",
                "side": "buy",
                "trade_date": "2024-01-01",
                "quantity": 1,
                "price": 1.0,
            }
        ]
        assert engine.entry_exit_retrospective(dates, tx, {}, [1.0]) == []

    def test_anchors_to_first_session_on_or_after_date(self):
        # Transaction un week-end : l'ancrage est la PREMIÈRE séance >= la date
        # (pas la séance précédente) — cohérent avec le docstring.
        dates = ["2024-01-05", "2024-01-08", "2024-01-10"]
        prices = {"A": [100.0, 110.0, 121.0]}
        bench = [100.0, 100.0, 100.0]
        tx = [
            {
                "id": 1,
                "ticker": "A",
                "side": "buy",
                "trade_date": "2024-01-06",
                "quantity": 1,
                "price": 100.0,
            }
        ]
        (row,) = engine.entry_exit_retrospective(dates, tx, prices, bench)
        # Entrée ancrée le 2024-01-08 (cours 110), sortie 121 -> +10 %.
        assert row["return_pct"] == pytest.approx(10.0)
        assert row["benchmark_pct"] == pytest.approx(0.0)
        assert row["delta_pct"] == pytest.approx(10.0)
