"""Watchlist (#25) — persistance et cas d'usage, sans réseau.

Le cache est isolé sur une base temporaire (même patron que test_settings.py et
test_schema_migration.py). Ce fichier couvre d'abord le SQL confiné de
`data/cache.py` (items + références), puis le service de classement.
"""

from __future__ import annotations

import sqlite3
import tempfile

import pytest

from obole import config
from obole.data import backup, cache


@pytest.fixture(autouse=True)
def _isolated_db():
    """Isole le cache sur une base temporaire (évite de toucher cache.sqlite)."""
    _orig = config.CACHE_DB
    config.CACHE_DB = tempfile.mktemp(suffix=".sqlite")
    yield
    config.CACHE_DB = _orig


class TestWatchlistItems:
    def test_add_then_get_case_insensitive(self):
        cache.upsert_watch_item("ri.pa", 2)
        item = cache.get_watch_item("RI.PA")
        assert item is not None
        assert item["ticker"] == "RI.PA"
        assert item["tier"] == 2
        assert item["added_at"] > 0

    def test_tier_change_preserves_added_at(self):
        cache.upsert_watch_item("RI.PA", 1)
        first = cache.get_watch_item("RI.PA")["added_at"]
        cache.upsert_watch_item("RI.PA", 3)
        again = cache.get_watch_item("RI.PA")
        assert again["tier"] == 3
        assert again["added_at"] == first  # date d'entrée, pas de réécriture

    def test_list_ordered_by_tier_then_ticker(self):
        cache.upsert_watch_item("ZZ.PA", 3)
        cache.upsert_watch_item("RI.PA", 1)
        cache.upsert_watch_item("AI.PA", 1)
        cache.upsert_watch_item("BN.PA", 2)
        assert [i["ticker"] for i in cache.list_watch_items()] == [
            "AI.PA",
            "RI.PA",
            "BN.PA",
            "ZZ.PA",
        ]

    def test_delete_returns_presence(self):
        cache.upsert_watch_item("RI.PA", 1)
        assert cache.delete_watch_item("ri.pa") is True
        assert cache.delete_watch_item("RI.PA") is False
        assert cache.count_watch_items() == 0

    def test_count(self):
        cache.upsert_watch_item("RI.PA", 1)
        cache.upsert_watch_item("AI.PA", 2)
        assert cache.count_watch_items() == 2

    def test_schema_refuses_tier_out_of_range(self):
        """Le CHECK est un garde-fou de dernier recours (le service valide avant)."""
        with cache.connect() as conn:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO watchlist_items (ticker, tier, added_at) VALUES ('RI.PA',4,1.0)"
                )


class TestTickerRefs:
    def test_set_get_list_clear(self):
        assert cache.get_ticker_ref("RI.PA") is None
        cache.set_ticker_ref("ri.pa", "2012-01-04")
        assert cache.get_ticker_ref("RI.PA") == "2012-01-04"
        cache.set_ticker_ref("AI.PA", "2015-06-01")
        assert cache.list_ticker_refs() == {"AI.PA": "2015-06-01", "RI.PA": "2012-01-04"}
        cache.clear_ticker_ref("RI.PA")
        assert cache.get_ticker_ref("RI.PA") is None
        assert cache.list_ticker_refs() == {"AI.PA": "2015-06-01"}

    def test_set_replaces_existing(self):
        cache.set_ticker_ref("RI.PA", "2010-01-01")
        cache.set_ticker_ref("RI.PA", "2014-01-01")
        assert cache.get_ticker_ref("RI.PA") == "2014-01-01"

    def test_ref_is_independent_from_membership(self):
        cache.upsert_watch_item("RI.PA", 1)
        cache.set_ticker_ref("RI.PA", "2012-01-04")
        cache.delete_watch_item("RI.PA")
        assert cache.get_watch_item("RI.PA") is None
        assert cache.get_ticker_ref("RI.PA") == "2012-01-04"


class TestBackupRegistry:
    def test_tables_are_declared(self):
        assert "watchlist_items" in backup._TABLE_COLUMNS
        assert "ticker_refs" in backup._TABLE_COLUMNS
        assert {"watchlist_items", "ticker_refs"} <= set(backup._TABLE_SINCE[8])

    def test_registry_guard_passes(self):
        backup._check_table_registry()


# --- Service : validation, référence, classement -----------------------------


class TestValidation:
    def test_ticker_normalized_and_rejected(self):
        from obole.services import watchlist as wl

        assert wl.normalize_ticker(" ri.pa ") == "RI.PA"
        assert wl.normalize_ticker("^FCHI") == "^FCHI"
        for bad in ("", "   ", None, 42, "bad ticker", "A" * 25, "RI;PA"):
            with pytest.raises(ValueError):
                wl.normalize_ticker(bad)

    def test_tier_validation(self):
        from obole.services import watchlist as wl

        for good in (1, 2, 3, "2", 2.0):
            assert wl.validate_tier(good) in (1, 2, 3)
        for bad in (0, 4, -1, True, None, 2.5, "x", ""):
            with pytest.raises(ValueError):
                wl.validate_tier(bad)

    def test_ref_start_validation(self):
        from obole.services import watchlist as wl

        assert wl.validate_ref_start("2012-01-04") == "2012-01-04"
        for bad in ("", None, "2012-1-4", "20120104", "pas-une-date", "2999-01-01"):
            with pytest.raises(ValueError):
                wl.validate_ref_start(bad)


class TestRefStats:
    def _series(self, length=3000, trend=0.08):
        import numpy as np
        import pandas as pd

        idx = pd.date_range("2000-01-03", periods=length, freq="B")
        t = (idx - idx[0]).days / 365.25
        return pd.Series(np.exp(trend * t) * 100.0, index=idx)

    def test_stats_match_the_regression(self):
        from obole.engine import regression as reg
        from obole.engine.summary import window_since
        from obole.services import watchlist as wl

        raw = self._series()
        start = raw.index[1000].date().isoformat()
        stats = wl.ref_stats(raw, start)
        window = window_since(raw, start)
        expected = reg.fit_log_regression(window)
        assert stats is not None
        assert stats["n_points"] == expected.n_points
        assert stats["line"] == pytest.approx(expected.fitted_now)
        assert stats["z"] == pytest.approx(reg.distance_sigma(expected, float(window.iloc[-1])))
        assert stats["ecart_type_pct"] == pytest.approx(expected.ecart_type_size * 100)
        # Paramètres de la droite persistée : le front trace EXACTEMENT la
        # référence avec eux (#25.1), sans re-fit sur la série décimée.
        assert stats["a"] == pytest.approx(expected.a)
        assert stats["b"] == pytest.approx(expected.b)
        assert stats["sigma"] == pytest.approx(expected.sigma)

    def test_too_short_returns_none(self):
        from obole.services import watchlist as wl

        raw = self._series()
        assert wl.ref_stats(raw, raw.index[-5].date().isoformat()) is None


class TestSetRef:
    def test_valid_reference_is_saved_with_stats(self, monkeypatch):
        from tests.test_analysis import _make_prices

        from obole.services import watchlist as wl

        prices = _make_prices(length=3000)
        monkeypatch.setattr(wl.yahoo, "fetch_prices", lambda t: prices)
        start = prices.raw.index[1000].date().isoformat()
        out = wl.set_ref("ri.pa", start)
        assert out["ref"] == {"start": start}
        assert out["stats"] is not None
        assert cache.get_ticker_ref("RI.PA") == start

    def test_too_short_reference_is_refused_and_not_saved(self, monkeypatch):
        from tests.test_analysis import _make_prices

        from obole.services import watchlist as wl

        prices = _make_prices(length=3000)
        monkeypatch.setattr(wl.yahoo, "fetch_prices", lambda t: prices)
        with pytest.raises(ValueError, match="Historique insuffisant"):
            wl.set_ref("RI.PA", prices.raw.index[-5].date().isoformat())
        assert cache.get_ticker_ref("RI.PA") is None

    def test_unknown_ticker_is_refused(self, monkeypatch):
        from obole.data import yahoo
        from obole.services import watchlist as wl

        def _boom(t):
            raise yahoo.TickerNotFound("nope")

        monkeypatch.setattr(wl.yahoo, "fetch_prices", _boom)
        with pytest.raises(ValueError, match="Ticker introuvable"):
            wl.set_ref("RI.PA", "2012-01-04")
        assert cache.get_ticker_ref("RI.PA") is None

    def test_network_failure_records_the_reference_without_stats(self, monkeypatch):
        from obole.services import watchlist as wl

        def _boom(t):
            raise RuntimeError("réseau KO")

        monkeypatch.setattr(wl.yahoo, "fetch_prices", _boom)
        out = wl.set_ref("RI.PA", "2012-01-04")
        assert out["stats"] is None
        assert out["warning"]
        assert cache.get_ticker_ref("RI.PA") == "2012-01-04"

    def test_clear_ref(self):
        from obole.services import watchlist as wl

        cache.set_ticker_ref("RI.PA", "2012-01-04")
        wl.clear_ref("ri.pa")
        assert cache.get_ticker_ref("RI.PA") is None


class TestItems:
    def test_set_tier_moves_and_preserves_added_at(self):
        from obole.services import watchlist as wl

        item = wl.set_tier("ri.pa", 1)
        assert item["tier"] == 1
        moved = wl.set_tier("RI.PA", 3)
        assert moved["tier"] == 3
        assert moved["added_at"] == item["added_at"]

    def test_cap_is_enforced(self, monkeypatch):
        from obole.services import watchlist as wl

        monkeypatch.setattr(config, "WATCHLIST_MAX_ITEMS", 1)
        wl.set_tier("RI.PA", 1)
        with pytest.raises(ValueError, match="Watchlist pleine"):
            wl.set_tier("AI.PA", 1)
        # Un déplacement d'une valeur existante reste possible.
        assert wl.set_tier("RI.PA", 2)["tier"] == 2

    def test_remove_is_idempotent(self):
        from obole.services import watchlist as wl

        wl.set_tier("RI.PA", 1)
        assert wl.remove("ri.pa") is True
        assert wl.remove("RI.PA") is False

    def test_tier_change_keeps_the_reference(self):
        """La référence est un réglage par titre, indépendant de l'appartenance."""
        from obole.services import watchlist as wl

        cache.set_ticker_ref("RI.PA", "2012-01-04")
        wl.set_tier("RI.PA", 1)
        wl.set_tier("RI.PA", 3)
        assert cache.get_ticker_ref("RI.PA") == "2012-01-04"
        wl.remove("RI.PA")
        assert cache.get_ticker_ref("RI.PA") == "2012-01-04"

    def test_list_state_shape(self):
        from obole.services import watchlist as wl

        wl.set_tier("RI.PA", 2)
        cache.set_ticker_ref("RI.PA", "2012-01-04")
        state = wl.list_state()
        assert [t["id"] for t in state["tiers"]] == [1, 2, 3]
        assert state["items"][0]["ticker"] == "RI.PA"
        assert state["refs"] == {"RI.PA": "2012-01-04"}


def _fake_windowed_analysis(ticker, price, line, sigma=0.25, trend=True, slope=0.0):
    """StockAnalysis minimal dont la régression de fenêtre est contrôlée."""
    import math
    from datetime import date

    from tests.test_analysis import _fake_identity

    from obole.models import (
        Indicators,
        RegressionResult,
        ScoredValue,
        StockAnalysis,
    )

    regression = RegressionResult(
        a=math.log(line) - slope * 10.0,
        b=slope,
        sigma=sigma,
        t_now=10.0,
        fitted_now=line,
        start=date(2005, 1, 3),
        end=date(2025, 1, 2),
        n_points=1000,
    )
    return StockAnalysis(
        identity=_fake_identity(ticker, price),
        indicators=Indicators(
            distance_sigma=ScoredValue(None, None, None),
            perf_passee=ScoredValue(5.0, "Moyen", True),
            ecart_type=ScoredValue(None, None, None),
            potential_5y=ScoredValue(8.0, "Moyen", True),
            potential_10y=ScoredValue(6.0, "Moyen", True),
            trend=ScoredValue(None, "Haussière" if trend else "Baissière", trend),
            quality=ScoredValue(60, "Bon", True),
        ),
        regression_raw=regression,
        regression_adj=regression,
        fundamentals=None,
        warnings=["Comptes indisponibles (yfinance)"],
    )


class TestRun:
    def _setup(self, monkeypatch, analyses, saved=None):
        from tests.test_analysis import _make_prices

        from obole.models import PriceSeries
        from obole.services import watchlist as wl

        # Les analyses factices annoncent un dernier cours de 100 : on cale la
        # série de prix sur ce cours pour que la conversion total-return
        # (cours brut / cours ajusté) reste cohérente. L'ajusté vaut brut × 1,02.
        base = _make_prices(length=3000)
        factor = 100.0 / float(base.raw.iloc[-1])
        prices = PriceSeries(
            raw=base.raw * factor,
            adjusted=base.adjusted * factor,
            fetched_at=base.fetched_at,
        )
        monkeypatch.setattr(wl.yahoo, "fetch_prices", lambda t: prices)
        monkeypatch.setattr(
            wl.analysis_service, "reference_window", lambda ticker, raw: (raw, None)
        )

        def fake_windowed(ticker, prices, *, regression_window=None, ref_start=None):
            if ticker in analyses:
                spec = analyses[ticker]
                return _fake_windowed_analysis(ticker, *spec)
            raise ValueError("données indisponibles")

        monkeypatch.setattr(wl.screen_service, "windowed_analysis", fake_windowed)
        monkeypatch.setattr(wl.cache, "get_valuation_settings", lambda t: (saved or {}).get(t))

    def test_rows_are_sorted_by_margin_with_saved_price(self, monkeypatch):
        import math

        from obole.services import watchlist as wl

        cache.upsert_watch_item("AAA.PA", 1)
        cache.upsert_watch_item("BBB.PA", 2)
        self._setup(
            monkeypatch,
            analyses={"AAA.PA": (100.0, 120.0), "BBB.PA": (100.0, 80.0)},
            saved={"AAA.PA": {"fair_price": 120.0, "target_yield": 12.0}},
        )
        run = wl.run()
        assert [r.ticker for r in run.rows] == ["AAA.PA", "BBB.PA"]
        aaa, bbb = run.rows
        assert aaa.fair_price_source == "saved"
        assert aaa.safety_margin_pct == pytest.approx(16.666, rel=1e-3)
        assert aaa.target_yield == 12.0
        assert aaa.margin_good is True
        # z et potentiel de la ligne sont en total-return (cours ajusté 102).
        assert aaa.z == pytest.approx(math.log(102 / 120) / 0.25)
        # Prix juste enregistré -> Pot. 5A de la valorisation, pas de la droite.
        assert aaa.pot_5y_pct == pytest.approx(((120 * 1.12**5 / 100) ** (1 / 5) - 1) * 100)
        assert aaa.pot_5y_source == "valuation"
        # Repli : prix juste = droite projetée 5 ans / 1,12^5, en unités brutes ;
        # la marge n'est plus l'écart à la droite.
        assert bbb.fair_price_source == "regression"
        fair = (80 / 1.12**5) * 100 / 102
        assert bbb.fair_price == pytest.approx(fair)
        assert bbb.safety_margin_pct == pytest.approx((fair - 100) / fair * 100)
        assert bbb.safety_margin_pct != pytest.approx(bbb.trend_gap_pct)
        assert bbb.target_yield == 12.0
        assert bbb.z == pytest.approx(math.log(102 / 80) / 0.25)
        assert bbb.pot_5y_pct == pytest.approx(((80 / 102) ** (1 / 5) - 1) * 100)
        assert bbb.pot_5y_source == "regression"
        assert bbb.margin_good is False
        assert bbb.ref_is_default is True

    def test_row_is_total_return_with_12pct_fallback(self, monkeypatch):
        """Prix juste = prix d'entrée 12 %/an jusqu'à la droite à 5 ans."""
        import math

        from obole.services import watchlist as wl

        cache.upsert_watch_item("AAA.PA", 1)
        self._setup(monkeypatch, analyses={"AAA.PA": (100.0, 120.0)})
        row = wl.run().rows[0]
        assert row.price == 100.0
        assert row.z == pytest.approx(math.log(102 / 120) / 0.25)
        assert row.ecart_type_pct == pytest.approx((math.exp(0.25) - 1) * 100)
        assert row.pente_pct == pytest.approx(0.0)
        assert row.pot_5y_pct == pytest.approx(((120 / 102) ** (1 / 5) - 1) * 100)
        assert row.pot_5y_source == "regression"
        assert row.pot_10y_source == "regression"
        assert row.target_yield == 12.0
        assert row.fair_price_source == "regression"
        fair = (120 / 1.12**5) * 100 / 102
        assert row.fair_price == pytest.approx(fair)
        assert row.safety_margin_pct == pytest.approx((fair - 100) / fair * 100)
        assert row.ref_line == pytest.approx(120 * 100 / 102)
        assert row.trend_gap_pct == pytest.approx((120 - 102) / 120 * 100)

    def test_error_row_keeps_tier_and_goes_last(self, monkeypatch):
        from obole.services import watchlist as wl

        cache.upsert_watch_item("OK.PA", 1)
        cache.upsert_watch_item("BAD.PA", 3)
        self._setup(monkeypatch, analyses={"OK.PA": (100.0, 90.0)})
        run = wl.run()
        assert [r.ticker for r in run.rows] == ["OK.PA", "BAD.PA"]
        assert run.rows[1].error
        assert run.rows[1].tier == 3

    def test_tier_filter_and_empty(self, monkeypatch):
        from obole.services import watchlist as wl

        cache.upsert_watch_item("AAA.PA", 1)
        cache.upsert_watch_item("BBB.PA", 2)
        self._setup(
            monkeypatch,
            analyses={"AAA.PA": (100.0, 90.0), "BBB.PA": (100.0, 90.0)},
        )
        assert [r.ticker for r in wl.run(tier=1).rows] == ["AAA.PA"]
        assert wl.run(tier=3).rows == []
        with pytest.raises(ValueError):
            wl.run(tier=4)

    def test_pot_5y_valorisation_with_dividend(self, monkeypatch):
        """Le Pot. 5A dérivé du prix juste inclut le dividende enregistré."""
        from obole.services import watchlist as wl

        cache.upsert_watch_item("AAA.PA", 1)
        self._setup(
            monkeypatch,
            analyses={"AAA.PA": (100.0, 120.0)},
            saved={
                "AAA.PA": {
                    "fair_price": 120.0,
                    "target_yield": 12.0,
                    "dividend_yield": 5.0,
                    "include_dividends": True,
                }
            },
        )
        row = wl.run().rows[0]
        expected = ((120 * 1.07**5 / 100) ** (1 / 5) - 1) * 100 + 5
        assert row.pot_5y_pct == pytest.approx(expected)
        assert row.pot_5y_source == "valuation"

    def test_pot_5y_saved_without_target_falls_back(self, monkeypatch):
        """Une valorisation sans cible exploitable retombe sur la droite, avec warning."""
        from obole.services import watchlist as wl

        cache.upsert_watch_item("AAA.PA", 1)
        self._setup(
            monkeypatch,
            analyses={"AAA.PA": (100.0, 120.0)},
            saved={"AAA.PA": {"fair_price": 120.0}},
        )
        row = wl.run().rows[0]
        assert row.pot_5y_source == "regression"
        assert any("Valorisation enregistrée" in w for w in row.warnings)

    def test_pente_is_the_reference_slope(self, monkeypatch):
        """La pente de la ligne est celle de la droite total-return."""
        import math

        from obole.services import watchlist as wl

        cache.upsert_watch_item("AAA.PA", 1)
        self._setup(
            monkeypatch,
            # (prix, ligne, sigma, tendance, pente log)
            analyses={"AAA.PA": (100.0, 90.0, 0.25, True, 0.03)},
        )
        row = wl.run().rows[0]
        assert row.pente_pct == pytest.approx((math.exp(0.03) - 1) * 100)
        # La perf ajustée du payload (5.0) n'est PAS utilisée pour la pente.
        assert row.pente_pct != pytest.approx(5.0)

    def test_window_is_passed_from_reference(self, monkeypatch):
        """Une référence persistée est utilisée (ref_start), sinon 20 ans."""
        from tests.test_analysis import _make_prices

        from obole.services import watchlist as wl

        cache.upsert_watch_item("AAA.PA", 1)
        cache.set_ticker_ref("AAA.PA", "2005-01-03")
        prices = _make_prices(length=3000)
        monkeypatch.setattr(wl.yahoo, "fetch_prices", lambda t: prices)
        monkeypatch.setattr(
            wl.analysis_service,
            "reference_window",
            lambda ticker, raw: (raw, "2005-01-03"),
        )
        seen: dict = {}

        def fake_windowed(ticker, prices, *, regression_window=None, ref_start=None):
            seen["ref"] = ref_start
            seen["years"] = regression_window
            return _fake_windowed_analysis(ticker, 100.0, 90.0)

        monkeypatch.setattr(wl.screen_service, "windowed_analysis", fake_windowed)
        monkeypatch.setattr(wl.cache, "get_valuation_settings", lambda t: None)
        row = wl.run().rows[0]
        assert seen == {"ref": "2005-01-03", "years": None}
        assert row.ref_is_default is False


class TestStockState:
    def test_state_and_decoration(self):
        from tests.test_analysis import _make_prices

        from obole.services import watchlist as wl

        cache.upsert_watch_item("RI.PA", 2)
        cache.set_ticker_ref("RI.PA", "2005-01-03")
        prices = _make_prices(length=3000)
        state = wl.stock_state("ri.pa", prices)
        assert state["tier"] == 2
        assert state["ref"] == {"start": "2005-01-03"}
        assert state["ref_stats"] is not None
        assert {"a", "b", "sigma", "line", "z"} <= set(state["ref_stats"])
        payload = wl.decorate_stock_payload({"kind_payload": "stock"}, "RI.PA", prices)
        assert payload["watch"]["tier"] == 2

    def test_corrupted_reference_is_muted_not_crashing(self):
        """Une date illisible en base ne casse ni la fiche ni le classement."""
        from tests.test_analysis import _make_prices

        from obole.services import watchlist as wl

        cache.set_ticker_ref("RI.PA", "pas-une-date")
        state = wl.stock_state("RI.PA", _make_prices(length=3000))
        assert state["ref"] == {"start": "pas-une-date"}
        assert state["ref_stats"] is None
