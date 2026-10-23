"""Tests purs de la section Dividende (engine/dividends.py, sans réseau)."""

from __future__ import annotations

import pandas as pd
import pytest

from obole.engine import dividends as d


def _idx(start: str, end: str, freq: str = "D") -> pd.DatetimeIndex:
    return pd.date_range(start, end, freq=freq)


class TestFrequency:
    def test_semestrial(self):
        events = {"2024-06-15": 1.0, "2024-12-15": 1.0, "2025-06-15": 1.2, "2025-12-15": 1.2}
        assert d.frequency(events) == "Semestriel"

    def test_quarterly(self):
        events = {
            "2025-03-31": 0.5,
            "2025-06-30": 0.5,
            "2025-09-30": 0.5,
            "2025-12-31": 0.5,
        }
        assert d.frequency(events) == "Trimestriel"

    def test_annual(self):
        events = {"2025-06-15": 1.0}
        assert d.frequency(events) == "Annuel"

    def test_none_when_empty(self):
        assert d.frequency({}) is None


class TestIncreaseAndNoCut:
    def test_consecutive_increases(self):
        by_year = {2022: 1.0, 2023: 1.1, 2024: 1.2, 2025: 1.3}
        assert d.increase_years(by_year) == 3
        assert d.no_cut_years(by_year) == 3

    def test_cut_interrupts(self):
        by_year = {2022: 1.0, 2023: 1.2, 2024: 1.0, 2025: 1.1}
        assert d.increase_years(by_year) == 1

    def test_stable_counts_as_no_cut_not_increase(self):
        """« Augmentation » = hausse STRICTE ; « sans baisse » = hausse OU stabilité."""
        by_year = {2023: 1.0, 2024: 1.0, 2025: 1.0}
        assert d.increase_years(by_year) == 0
        assert d.no_cut_years(by_year) == 2

    def test_increase_and_no_cut_differ_on_plateau(self):
        by_year = {2020: 1.0, 2021: 1.1, 2022: 1.1, 2023: 1.2}
        assert d.increase_years(by_year) == 1  # seul 2022->2023 est strictement croissant
        assert d.no_cut_years(by_year) == 3

    def test_none_when_empty(self):
        assert d.increase_years({}) is None
        assert d.no_cut_years({}) is None


class TestCagr:
    def test_five_years(self):
        import pytest

        by_year = {2020: 1.0, 2021: 1.1, 2022: 1.2, 2023: 1.3, 2024: 1.4, 2025: 1.5}
        assert d.cagr(by_year, 5) == pytest.approx(8.447, abs=0.01)

    def test_too_short(self):
        assert d.cagr({2024: 1.0, 2025: 1.1}, 5) is None

    def test_negative_base_is_none(self):
        assert (
            d.cagr({2020: -1.0, 2021: 1.0, 2022: 1.0, 2023: 1.0, 2024: 1.0, 2025: 1.0}, 5) is None
        )


class TestGrowthSeries:
    def test_yoy(self):
        out = d.growth_series({2023: 1.0, 2024: 1.1, 2025: 0.55})
        assert out[2023] is None  # pas d'année précédente
        assert round(out[2024], 4) == 10.0
        assert round(out[2025], 4) == -50.0


class TestRollingYield:
    def test_aligned_on_prices_index(self):
        idx = _idx("2024-01-01", "2025-12-31", "ME")
        prices = pd.Series(100.0, index=idx)
        events = {"2024-06-15": 1.0, "2024-12-15": 1.0, "2025-06-15": 1.2, "2025-12-15": 1.2}
        s = d.rolling_yield_series(idx, prices, events)
        assert len(s) == len(idx)
        assert list(s.index) == list(idx)
        # dernier point : 12 mois glissants = 1.2 + 1.2 = 2.4 -> 2.4 %
        assert round(s.iloc[-1], 3) == 2.4

    def test_tz_aware_prices(self):
        idx = pd.date_range("2024-01-01", "2025-12-31", freq="ME", tz="Europe/Paris")
        prices = pd.Series(100.0, index=idx)
        events = {"2024-06-15": 1.0, "2024-12-15": 1.0}
        s = d.rolling_yield_series(idx, prices, events)
        assert len(s) == len(idx)
        assert s.iloc[-1] is not None

    def test_zero_price_is_none(self):
        idx = _idx("2025-01-01", "2025-12-31", "ME")
        prices = pd.Series([0.0] * len(idx), index=idx)
        s = d.rolling_yield_series(idx, prices, {"2025-06-15": 1.0})
        assert pd.isna(s.iloc[-1])

    def test_extra_by_year_staircase(self):
        idx = _idx("2024-01-01", "2025-12-31", "ME")
        prices = pd.Series(100.0, index=idx)
        events = {"2024-06-15": 1.0, "2024-12-15": 1.0, "2025-06-15": 1.0, "2025-12-15": 1.0}
        s = d.rolling_yield_series(idx, prices, events, extra_by_year={2025: 2.0})
        # fin 2025 : 2.0 de dividendes + 2.0 de rachats = 4 % ; fin 2024 : 2 % (pas de rachat)
        assert round(s.iloc[-1], 3) == 4.0
        dec2024 = idx.get_loc(pd.Timestamp("2024-12-31"))
        assert round(s.iloc[dec2024], 3) == 2.0

    def test_no_events_returns_empty(self):
        idx = _idx("2025-01-01", "2025-12-31", "ME")
        prices = pd.Series(100.0, index=idx)
        s = d.rolling_yield_series(idx, prices, {})
        assert s.dropna().empty


class TestBuybacksPerShare:
    """Rachats TOTAUX (cash-flow) ramenés par action — sinon rendement aberrant."""

    def test_divides_total_by_shares(self):
        # 230 800 000 € de rachats / 635 000 000 actions = 0,3635 €/action.
        out = d.buybacks_per_share({2024: 230_800_000.0}, {2024: 635_000_000.0})
        assert out[2024] == pytest.approx(0.3635, abs=1e-4)

    def test_closest_year_fallback(self):
        # Exercice 2023 absent des comptes -> repli sur 2024 (le plus proche).
        out = d.buybacks_per_share({2023: 1_000_000.0}, {2024: 500_000.0})
        assert out[2023] == pytest.approx(2.0)

    def test_missing_shares_returns_empty(self):
        assert d.buybacks_per_share({2024: 1_000_000.0}, None) == {}
        assert d.buybacks_per_share({2024: 1_000_000.0}, {}) == {}

    def test_zero_shares_ignored(self):
        # Actions nulles -> exercice ignoré (jamais d'infini).
        assert d.buybacks_per_share({2024: 1_000_000.0}, {2024: 0.0}) == {}

    def test_no_buybacks_returns_empty(self):
        assert d.buybacks_per_share(None, {2024: 1_000_000.0}) == {}
        assert d.buybacks_per_share({}, {2024: 1_000_000.0}) == {}


class TestShareholderYieldMagnitude:
    """Garde-fou de magnitude : un rendement actionnaire reste de l'ordre de
    quelques % (jamais des milliards, symptôme d'un total non divisé par action)."""

    def test_shareholder_yield_is_few_percent(self):
        idx = _idx("2024-01-01", "2025-12-31", "ME")
        prices = pd.Series(150.0, index=idx)
        events = {"2024-06-15": 3.0, "2024-12-15": 3.0, "2025-06-15": 3.0, "2025-12-15": 3.0}
        # Rachats : 230,8 M€ / 635 M actions = 0,3635 €/action (déjà par action).
        extra = d.buybacks_per_share({2025: 230_800_000.0}, {2025: 635_000_000.0})
        s = d.rolling_yield_series(idx, prices, events, extra_by_year=extra)
        # 6 € de dividendes + 0,36 € de rachats sur 150 € -> ~4,2 %.
        assert s.iloc[-1] == pytest.approx(4.24, abs=0.1)
        assert s.max() < 100  # jamais de valeur aberrante


class TestSummary:
    """`summary` = agrégat consommé par l'API (source unique des KPI dividende)."""

    def test_returns_all_keys(self):
        out = d.summary({"2024-06-15": 1.0}, {2020: 1.0, 2021: 1.1})
        assert set(out) == {
            "increase_years",
            "no_cut_years",
            "cagr",
            "frequency",
            "perf_pct",
            "growth",
        }

    def test_excludes_current_year_from_regularity(self):
        # 2026 (année en cours) est incomplète -> écartée des stats de régularité.
        current = pd.Timestamp.today().year
        per_share = {2023: 1.0, 2024: 1.1, 2025: 1.2, current: 0.4}
        out = d.summary({}, per_share)
        # Sans l'année partielle, la série est croissante sur 2 ans.
        assert out["increase_years"] == 2
        assert out["no_cut_years"] == 2

    def test_growth_excludes_current_partial_year(self):
        """La croissance YoY ne doit pas inclure l'année en cours (partielle).

        Sinon la dernière barre montre une fausse chute (ex. payeur trimestriel
        à −50 % en milieu d'année). Même exclusion que la régularité.
        """
        current = pd.Timestamp.today().year
        per_share = {2023: 1.0, 2024: 1.1, 2025: 1.2, current: 0.4}
        out = d.summary({}, per_share)
        # L'année en cours est absente de la série de croissance.
        assert current not in out["growth"]
        assert out["growth"][2024] == pytest.approx(10.0)

    def test_cagr_uses_config_horizons(self):
        from obole import config

        per_share = {y: 1.0 + 0.1 * (y - 2015) for y in range(2015, 2025)}
        out = d.summary({}, per_share)
        assert set(out["cagr"]) == set(config.DIVIDEND_CAGR_HORIZONS)

    def test_frequency_and_growth(self):
        out = d.summary(
            {"2024-06-15": 1.0, "2024-12-15": 1.0},
            {2023: 1.0, 2024: 1.1},
        )
        assert out["frequency"] == "Semestriel"
        assert out["growth"][2024] == pytest.approx(10.0)

    def test_perf_pct(self):
        out = d.summary({}, {2020: 1.0, 2024: 1.5})
        assert out["perf_pct"] == pytest.approx(50.0)
