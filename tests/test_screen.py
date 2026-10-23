"""Tests du moteur screener (J2) — pur, sans réseau.

Mock des appels réseau via services.analysis (analyse) : les prix arrivent déjà
fetchés, screen_stock ne touche jamais data/ ni api/. On teste la réduction
(screen_stock, services/screen.py), le filtre et le tri multi-colonnes
(filter_and_sort, engine/screen.py).
"""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd

from obole.engine import screen
from obole.models import CompanyKind, Identity, PriceSeries, ScreenResult
from obole.services import screen as screen_service


def _date_index(length: int) -> pd.DatetimeIndex:
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


def _sr(
    ticker: str,
    *,
    z: float | None = 0.0,
    pente: float | None = 5.0,
    ecart: float | None = 25.0,
    pot5: float | None = 8.0,
    pot10: float | None = 6.0,
    roe: float | None = 12.0,
    per: float | None = 10.0,
    p_b: float | None = 1.5,
    p_fcf: float | None = 9.0,
    fcf_yield: float | None = 9.0,
    quality: float | None = 60.0,
    market_cap: float | None = 1_000_000_000,
    error: str | None = None,
) -> ScreenResult:
    """ScreenResult de test (raccourci)."""
    return ScreenResult(
        ticker=ticker.upper(),
        name=ticker,
        z=z,
        pente_pct=pente,
        ecart_type_pct=ecart,
        pot_5y_pct=pot5,
        pot_10y_pct=pot10,
        roe_pct=roe,
        per=per,
        p_b=p_b,
        p_fcf=p_fcf,
        fcf_yield_pct=fcf_yield,
        quality_score=quality,
        market_cap=market_cap,
        error=error,
    )


class TestScreenStock:
    def test_returns_wellformed_screenresult(self):
        prices = _make_prices()
        with (
            patch("obole.services.analysis.yahoo.fetch_identity", side_effect=_fake_identity),
            patch("obole.services.analysis.yahoo.fetch_fundamentals", return_value=None),
        ):
            out = screen_service.screen_stock("FAKE", prices)

        assert isinstance(out, ScreenResult)
        assert out.ticker == "FAKE"
        assert out.name == "Fake Corp"
        assert out.error is None
        # Fondamentaux indisponibles -> None (dégradation gracieuse).
        assert out.roe_pct is None
        assert out.per is None
        assert out.z is not None

    def test_invalid_ticker_isolated_with_error(self):
        prices = _make_prices()
        with (
            patch("obole.services.screen.analyze", side_effect=ValueError("Série trop courte")),
        ):
            out = screen_service.screen_stock("FAKE", prices)

        assert out.error is not None
        assert out.ticker == "FAKE"

    def test_regression_window_bounds_sigma_and_pente(self):
        # Série contrôlée avec un régime de prix différent sur les ~10 dernières
        # années : la fenêtre 10 ans borne la régression, donc σ et pente changent
        # par rapport à l'historique complet (la fenêtre a bien été appliquée).
        idx = pd.date_range("2000-01-03", periods=7000, freq="B")
        t = (idx - idx[0]).days / 365.25
        price0 = np.exp(0.08 * t) * (1 + 0.02 * np.sin(t))
        price = np.where(t > (t[-1] - 10), np.exp(0.01 * t) * 2.2, price0)
        raw = pd.Series(price, index=idx)
        prices = PriceSeries(
            raw=raw,
            adjusted=raw * 1.02,
            fetched_at=pd.Timestamp("today").date(),
        )
        with (
            patch("obole.services.analysis.yahoo.fetch_identity", side_effect=_fake_identity),
            patch("obole.services.analysis.yahoo.fetch_fundamentals", return_value=None),
        ):
            full = screen_service.screen_stock("FAKE", prices)
            window = screen_service.screen_stock("FAKE", prices, regression_window=10)

        # Fenêtre bien plus lente que l'historique complet (0.01 vs 0.08 %/an).
        assert window.pente_pct < full.pente_pct
        # σ de la fenêtre (replati) inférieur à celui de l'historique (pente 8 %).
        assert window.ecart_type_pct < full.ecart_type_pct


class TestFilterAndSort:
    def _rows(self) -> list[ScreenResult]:
        return [
            _sr("A", z=-2.0, pente=8.0, per=8.0, quality=70, market_cap=10_000_000_000),
            _sr("B", z=-1.0, pente=4.0, per=12.0, quality=55, market_cap=2_000_000_000),
            _sr("C", z=0.5, pente=12.0, per=15.0, quality=80, market_cap=5_000_000_000),
            _sr("D", z=-3.0, pente=6.0, per=10.0, quality=60, market_cap=1_000_000_000),
        ]

    def test_filter_min_max_inclusive(self):
        rows = self._rows()
        out = screen.filter_and_sort(rows, filters={"z": (-2.5, 0.0)})
        # Borne inclusive : z=-2.0 gardé ; z=-3.0 exclu (trop bas) ; z=0.5 exclu
        # (trop haut) ; z=-1.0 gardé.
        assert {r.ticker for r in out} == {"A", "B"}

    def test_filter_multi_criteria_anded(self):
        # E6 : plusieurs critères bornés en même temps (ET logique).
        # market_cap > 1Md ET pente >= 5 ET per <= 12.
        rows = self._rows()
        out = screen.filter_and_sort(
            rows,
            filters={
                "market_cap": (1_500_000_000, None),
                "pente_pct": (5.0, None),
                "per": (None, 12.0),
            },
        )
        # A : capi 10Md ✓, pente 8 ✓, per 8 ✓ -> gardé.
        # B : capi 2Md ✓, pente 4 ✗ -> exclu.
        # C : capi 5Md ✓, pente 12 ✓, per 15 ✗ -> exclu.
        # D : capi 1Md ✗ -> exclu.
        assert [r.ticker for r in out] == ["A"]

    def test_filter_one_sided_bounds(self):
        rows = self._rows()
        # min seul (per >= 10) : D(10), B(12), C(15) gardés ; A(8) exclu.
        out = screen.filter_and_sort(rows, filters={"per": (10.0, None)})
        assert {r.ticker for r in out} == {"B", "C", "D"}

    def test_filter_on_monotonic_per(self):
        rows = self._rows()
        # per <= 10 (moins = mieux) : A(8), D(10) gardés ; B(12), C(15) exclus.
        out = screen.filter_and_sort(rows, filters={"per": (None, 10.0)})
        assert {r.ticker for r in out} == {"A", "D"}

    def test_filter_excludes_none(self):
        rows = self._rows()
        rows.append(_sr("E", roe=None, per=None))
        out = screen.filter_and_sort(rows, filters={"roe_pct": (0.0, None)})
        # E n'a pas de ROE -> exclu par le filtre.
        assert "E" not in {r.ticker for r in out}

    def test_sort_single_default_desc(self):
        rows = self._rows()
        out = screen.filter_and_sort(rows, sort_by=["quality_score"])
        # quality_score : « plus = mieux » -> décroissant : C(80), A(70), D(60), B(55).
        assert [r.ticker for r in out] == ["C", "A", "D", "B"]

    def test_sort_single_default_asc_for_multiple(self):
        rows = self._rows()
        out = screen.filter_and_sort(rows, sort_by=["per"])
        # per : « moins = mieux » -> croissant : A(8), D(10), B(12), C(15).
        assert [r.ticker for r in out] == ["A", "D", "B", "C"]

    def test_sort_override_direction(self):
        rows = self._rows()
        out = screen.filter_and_sort(rows, sort_by=[("quality_score", "asc")])
        assert [r.ticker for r in out] == ["B", "D", "A", "C"]

    def test_sort_multi_column_chained(self):
        rows = self._rows()
        # Primaire : z croissant (plus décoté en premier) ; secondaire : pente desc.
        out = screen.filter_and_sort(rows, sort_by=["z", "pente_pct"])
        # z : D(-3), A(-2), B(-1), C(0.5) ; à z égal pas de conflit ici.
        assert [r.ticker for r in out] == ["D", "A", "B", "C"]

    def test_sort_missing_values_last(self):
        rows = self._rows()
        rows.append(_sr("E", quality=None))
        rows.append(_sr("F", error="boom"))
        out = screen.filter_and_sort(rows, sort_by=["quality_score"])
        # Les valeurs triées d'abord (desc) ; E et F (None/error) rejetées en fin.
        tickers = [r.ticker for r in out]
        assert tickers[:4] == ["C", "A", "D", "B"]
        assert set(tickers[4:]) == {"E", "F"}

    def test_filter_preserves_order_when_no_sort(self):
        rows = self._rows()
        out = screen.filter_and_sort(rows, filters={"market_cap": (1_000_000_000, None)})
        assert [r.ticker for r in out] == ["A", "B", "C", "D"]
