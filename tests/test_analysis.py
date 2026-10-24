"""Tests d'orchestration — analyse assemble data + engine correctement.

Sans réseau : mock des appels à yahoo.
"""

from __future__ import annotations

from functools import cache
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from obole.models import CompanyKind, Identity, PriceSeries, StockAnalysis
from obole.services.analysis import analyze, analyze_ratio


@cache
def _date_index(length: int) -> pd.DatetimeIndex:
    # L'index BusinessDay est identique pour un `length` donné : on le calcule
    # une seule fois (pd.date_range(freq="B") est coûteux, ~48µs/point) et on le
    # partage entre toutes les séries de test.
    return pd.date_range("2000-01-03", periods=length, freq="B")


def _make_prices(length: int = 3000, seed: int = 42) -> PriceSeries:
    rng = np.random.default_rng(seed)
    idx = _date_index(length)
    raw = pd.Series(20.0 * np.exp(np.cumsum(rng.normal(0, 0.01, length))), index=idx)
    adj = raw * 1.02
    return PriceSeries(raw=raw, adjusted=adj, fetched_at=pd.Timestamp("today").date())


def _fake_identity(ticker: str, last_price: float | None) -> Identity:
    return Identity(
        ticker=ticker.upper(),
        name="Fake Corp",
        country="FR",
        sector="Technology",
        currency="EUR",
        last_price=last_price,
        kind=CompanyKind.INDUSTRIAL,
    )


def _fake_fundamentals(ticker: str, kind: CompanyKind):
    return None


class TestAnalyze:
    def test_returns_stock_analysis_with_indicators(self):
        prices = _make_prices()
        with (
            patch("obole.services.analysis.yahoo.fetch_identity", side_effect=_fake_identity),
            patch("obole.services.analysis.yahoo.fetch_fundamentals", return_value=None),
        ):
            analysis = analyze("FAKE", prices)

        assert isinstance(analysis, StockAnalysis)
        assert analysis.identity.ticker == "FAKE"
        assert analysis.identity.name == "Fake Corp"
        assert analysis.regression_raw is not None
        assert analysis.regression_adj is not None
        assert analysis.indicators.distance_sigma.value is not None
        assert analysis.indicators.perf_passee.label is not None
        assert analysis.indicators.quality.value is None  # pas de comptes
        assert any("Comptes indisponibles" in w for w in analysis.warnings)

    def test_prices_with_short_history_raises(self):
        prices = _make_prices(length=20)
        with (
            patch("obole.services.analysis.yahoo.fetch_identity", side_effect=_fake_identity),
            patch("obole.services.analysis.yahoo.fetch_fundamentals", return_value=None),
        ):
            with pytest.raises(ValueError, match="Série trop courte"):
                analyze("FAKE", prices)

    def test_identity_kind_propagated(self):
        prices = _make_prices()

        def _fake_identity_financial(ticker, last_price):
            return Identity(
                ticker=ticker.upper(),
                name="Fake Bank",
                sector="Banks",
                kind=CompanyKind.FINANCIAL,
            )

        with patch(
            "obole.services.analysis.yahoo.fetch_identity", side_effect=_fake_identity_financial
        ):
            analysis = analyze("FAKE", prices)
        assert analysis.identity.kind is CompanyKind.FINANCIAL

    def test_fair_price_is_regression_on_20y_window(self):
        """« Prix juste » = valeur de la droite sur la fenêtre 20 ans (vue graphe)."""
        from obole.engine import regression as reg
        from obole.engine.summary import regression_window

        prices = _make_prices()  # ~12 ans d'historique < 20 ans -> série entière
        with (
            patch("obole.services.analysis.yahoo.fetch_identity", side_effect=_fake_identity),
            patch("obole.services.analysis.yahoo.fetch_fundamentals", return_value=None),
        ):
            analysis = analyze("FAKE", prices)

        window = regression_window(prices.raw)
        expected = reg.fit_log_regression(window).fitted_now
        fair = next(
            r
            for c in analysis.summary
            if c.id == "valorisation"
            for r in c.rows
            if r.key == "fair_price"
        )
        assert fair.value == pytest.approx(expected)

    def test_dividend_yield_series_computed_and_aligned(self):
        """Le rendement continu est calculé depuis prix + dividendes, aligné sur le prix."""
        from obole.models import Fundamentals

        prices = _make_prices()
        fund = Fundamentals(
            table=pd.DataFrame(),
            kind=CompanyKind.INDUSTRIAL,
            available_years=0,
            fetched_at=pd.Timestamp("today").date(),
            dividend={"events": {"2024-06-15": 1.0, "2025-06-15": 1.0}},
        )
        with (
            patch("obole.services.analysis.yahoo.fetch_identity", side_effect=_fake_identity),
            patch("obole.services.analysis.yahoo.fetch_fundamentals", return_value=fund),
        ):
            analysis = analyze("FAKE", prices)

        assert analysis.fundamentals.dividend_yield is not None
        assert analysis.fundamentals.shareholder_yield is not None
        # Alignement : même index que la série de prix.
        assert len(analysis.fundamentals.dividend_yield) == len(prices.raw)
        assert analysis.fundamentals.dividend_yield.index.equals(prices.raw.index)

    def test_shareholder_yield_buybacks_converted_per_share(self):
        """Rachats TOTAUX (cash-flow) ramenés par action : rendement de quelques %.

        Garde-fou : sans la division par les actions en circulation, le rendement
        actionnaire exploserait (milliards de %) — cf. bug AI.PA.
        """
        from obole.models import Fundamentals

        prices = _make_prices()
        table = pd.DataFrame(
            {2010: [635_000_000.0]},
            index=["Actions en circulation"],
        )
        fund = Fundamentals(
            table=table,
            kind=CompanyKind.INDUSTRIAL,
            available_years=1,
            fetched_at=pd.Timestamp("today").date(),
            dividend={
                "events": {"2010-06-15": 3.0, "2010-12-15": 3.0},
                "buyback_history": {2010: 230_800_000.0},
            },
        )
        with (
            patch("obole.services.analysis.yahoo.fetch_identity", side_effect=_fake_identity),
            patch("obole.services.analysis.yahoo.fetch_fundamentals", return_value=fund),
        ):
            analysis = analyze("FAKE", prices)

        # Rachats convertis par action (dans services/analysis, pas côté front).
        assert fund.dividend["buybacks_per_share"][2010] == pytest.approx(0.3635, abs=1e-4)
        sh = analysis.fundamentals.shareholder_yield.dropna()
        assert not sh.empty
        # Rendement actionnaire de l'ordre de quelques % (jamais 10^9).
        assert 0 < sh.iloc[-1] < 100

    def test_shares_fallback_on_info_when_table_lacks_shares(self):
        """Sans ligne « Actions en circulation », repli sur info.sharesOutstanding.

        Cas Amundi (profil financier) : le tableau n'expose pas les actions, mais
        `info` fournit `sharesOutstanding`. Sans ce repli, la composante rachat
        serait nulle et le Shareholder Yield faux.
        """
        from obole.models import Fundamentals

        prices = _make_prices()
        fund = Fundamentals(
            table=pd.DataFrame(),  # aucune ligne « Actions en circulation »
            kind=CompanyKind.FINANCIAL,
            available_years=0,
            fetched_at=pd.Timestamp("today").date(),
            dividend={
                "events": {"2010-06-15": 3.0},
                "buyback_history": {2010: 200_000_000.0},
            },
        )
        with (
            patch("obole.services.analysis.yahoo.fetch_identity", side_effect=_fake_identity),
            patch(
                "obole.services.analysis.cache.get",
                return_value={"sharesOutstanding": 200_000_000},
            ),
            patch("obole.services.analysis.yahoo.fetch_fundamentals", return_value=fund),
        ):
            analyze("FAKE", prices)

        # 200 M€ / 200 M actions = 1,00 €/action (repli info appliqué).
        assert fund.dividend["buybacks_per_share"][2010] == pytest.approx(1.0)

    def test_shareholder_yield_equals_dividend_yield_without_buybacks(self):
        """Sans rachats, le rendement actionnaire se confond avec le dividende."""
        from obole.models import Fundamentals

        prices = _make_prices()
        fund = Fundamentals(
            table=pd.DataFrame(),
            kind=CompanyKind.INDUSTRIAL,
            available_years=0,
            fetched_at=pd.Timestamp("today").date(),
            dividend={"events": {"2024-06-15": 1.0, "2025-06-15": 1.0}},
        )
        with (
            patch("obole.services.analysis.yahoo.fetch_identity", side_effect=_fake_identity),
            patch("obole.services.analysis.yahoo.fetch_fundamentals", return_value=fund),
        ):
            analysis = analyze("FAKE", prices)

        div = analysis.fundamentals.dividend_yield
        sh = analysis.fundamentals.shareholder_yield
        assert div is not None and sh is not None
        # Aucun rachat disponible -> les deux courbes coïncident (continuité voulue).
        assert sh.equals(div)


class TestAnalyzeRatio:
    def test_returns_tuple_with_ratio_analysis(self):
        pa = _make_prices()
        pb = _make_prices(seed=99)

        with patch(
            "obole.services.analysis.yahoo.fetch_identity", return_value=_fake_identity("A", None)
        ):
            result, series, sa, sb = analyze_ratio("A", "B", pa, pb)

        assert result.ticker_a == "A"
        assert result.ticker_b == "B"
        assert result.regression is not None
        assert result.indicators.distance_sigma.value is not None
        assert result.indicators.quality.value is None  # pas de qualité pour un ratio
        assert result.indicators.trend.value is None
        assert isinstance(series, pd.Series)
        assert isinstance(sa, pd.Series)
        assert isinstance(sb, pd.Series)

    def test_warning_on_short_common_history(self):
        pa = _make_prices(length=100)
        pb = _make_prices(length=100, seed=99)

        with patch(
            "obole.services.analysis.yahoo.fetch_identity", return_value=_fake_identity("A", None)
        ):
            result, *_ = analyze_ratio("A", "B", pa, pb)
        assert any("Historique commun" in w for w in result.warnings)


class TestFairPriceReference:
    """#25 — le « Prix juste » suit la fenêtre de confiance persistée du titre."""

    @pytest.fixture(autouse=True)
    def _isolated_db(self):
        import tempfile

        from obole import config

        _orig = config.CACHE_DB
        config.CACHE_DB = tempfile.mktemp(suffix=".sqlite")
        yield
        config.CACHE_DB = _orig

    def _analyze(self):
        prices = _make_prices(length=3000)  # ~12 ans d'historique (2000-01-03 -> 2011-07), < 20 ans
        with (
            patch("obole.services.analysis.yahoo.fetch_identity", side_effect=_fake_identity),
            patch("obole.services.analysis.yahoo.fetch_fundamentals", return_value=None),
        ):
            return analyze("FAKE", prices), prices

    @staticmethod
    def _fair(analysis):
        return next(
            r
            for c in analysis.summary
            if c.id == "valorisation"
            for r in c.rows
            if r.key == "fair_price"
        )

    def test_no_reference_keeps_20y_default(self):
        from obole.engine import regression as reg
        from obole.engine.summary import regression_window

        analysis, prices = self._analyze()
        expected = reg.fit_log_regression(regression_window(prices.raw)).fitted_now
        fair = self._fair(analysis)
        assert fair.value == pytest.approx(expected)
        assert fair.note is None

    def test_reference_drives_the_fair_price_and_the_note(self):
        from obole.data import cache
        from obole.engine import regression as reg
        from obole.engine.summary import window_since

        cache.set_ticker_ref("FAKE", "2005-01-03")
        analysis, prices = self._analyze()
        expected = reg.fit_log_regression(window_since(prices.raw, "2005-01-03")).fitted_now
        fair = self._fair(analysis)
        assert fair.value == pytest.approx(expected)
        assert fair.note == "Droite de référence (prix bruts, depuis 2005)"

    def test_saved_fair_price_wins_over_reference(self):
        from obole.data import cache

        cache.set_ticker_ref("FAKE", "2005-01-03")
        cache.set_valuation_settings(
            "FAKE",
            {
                "metric": "eps",
                "period": 10,
                "growth": 2.0,
                "multiple": 12.0,
                "target_yield": 12.0,
                "dividend_yield": 0.0,
                "include_dividends": True,
                "fair_price": 123.45,
                "net_debt_per_share": None,
            },
        )
        analysis, _ = self._analyze()
        fair = self._fair(analysis)
        assert fair.value == pytest.approx(123.45)
        assert fair.note == "Prix juste enregistré (calculatrice)"

    def test_negative_saved_fair_price_is_ignored(self):
        from obole.data import cache

        cache.set_valuation_settings(
            "FAKE",
            {
                "metric": "eps",
                "period": 10,
                "growth": 2.0,
                "multiple": 12.0,
                "target_yield": 12.0,
                "dividend_yield": 0.0,
                "include_dividends": True,
                "fair_price": -5.0,
                "net_debt_per_share": None,
            },
        )
        analysis, _ = self._analyze()
        assert self._fair(analysis).note is None

    def test_too_short_reference_falls_back_to_20y(self):
        from obole.data import cache
        from obole.engine import regression as reg
        from obole.engine.summary import regression_window

        prices = _make_prices(length=3000)
        cache.set_ticker_ref("FAKE", prices.raw.index[-5].date().isoformat())
        analysis, _ = self._analyze()
        expected = reg.fit_log_regression(regression_window(prices.raw)).fitted_now
        fair = self._fair(analysis)
        assert fair.value == pytest.approx(expected)
        assert fair.note is None

    def test_corrupted_reference_falls_back(self):
        from obole.data import cache

        cache.set_ticker_ref("FAKE", "pas-une-date")
        analysis, _ = self._analyze()
        assert self._fair(analysis).note is None
