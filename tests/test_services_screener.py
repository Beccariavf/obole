"""Tests du cas d'usage screener (`services/screener.py::run_screen`).

Sans réseau : `screener_data.fetch_universe`, `yahoo.fetch_prices`, le cache et
`screen_service.screen_stock` sont mockés. On vérifie que le service porte bien
l'orchestration (passe 1 + passe 2 + cache + filtre/tri), que la clé de cache est
inchangée (cache chaud exploité), et que le budget timeout reste global.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from obole.data.yahoo import TickerNotFound
from obole.models import ScreenResult
from obole.services import screener as screener_service


def _sr_dump(ticker: str, **kw) -> dict:
    defaults = dict(
        ticker=ticker,
        name="Fake Corp",
        sector="Technology",
        market_cap=2_000_000_000,
        z=-1.0,
        pente_pct=5.0,
        ecart_type_pct=25.0,
        pot_5y_pct=8.0,
        pot_10y_pct=6.0,
        trend_bullish=True,
        roe_pct=12.0,
        per=10.0,
        p_b=1.5,
        p_fcf=9.0,
        fcf_yield_pct=9.0,
        quality_score=60,
        warnings=[],
        error=None,
    )
    defaults.update(kw)
    return ScreenResult(**defaults).__dict__


def _universe(tickers: list[str]) -> dict:
    return {"tickers": tickers, "count": len(tickers), "source": "yahoo"}


def test_run_screen_scans_and_returns_rows():
    """Passe 1 + passe 2 -> ScreenRun (rows, source, tickers_count)."""
    with (
        patch(
            "obole.services.screener.screener_data.fetch_universe",
            return_value=_universe(["AIR.PA", "AI.PA"]),
        ),
        patch(
            "obole.services.screener._scan_universe",
            return_value={"AIR.PA": _sr_dump("AIR.PA"), "AI.PA": _sr_dump("AI.PA")},
        ),
        patch("obole.services.screener.cache_data.get", return_value=None),
        patch("obole.services.screener.cache_data.put"),
    ):
        run = screener_service.run_screen(
            min_market_cap=1e9,
            sectors=None,
            regression_window=None,
        )

    assert run.source == "yahoo"
    assert run.tickers_count == 2
    assert {r.ticker for r in run.rows} == {"AIR.PA", "AI.PA"}


def test_run_screen_cache_hit_skips_network():
    """Cache de scan chaud -> aucune passe 1/2, source 'cache'."""
    cached = {"results": {"AIR.PA": _sr_dump("AIR.PA")}, "source": "yahoo"}
    with (
        patch("obole.services.screener.cache_data.get", return_value=cached),
        patch("obole.services.screener.screener_data.fetch_universe") as mock_u,
        patch("obole.services.screener._scan_universe") as mock_scan,
    ):
        run = screener_service.run_screen(
            min_market_cap=1e9,
            sectors=None,
            regression_window=None,
        )

    assert run.source == "cache"
    mock_u.assert_not_called()
    mock_scan.assert_not_called()


def test_cache_key_is_stable():
    """La clé de cache est inchangée (un cache chaud reste exploité)."""
    with (
        patch("obole.services.screener.cache_data.get", return_value=None) as mock_get,
        patch("obole.services.screener.cache_data.put"),
        patch(
            "obole.services.screener.screener_data.fetch_universe",
            return_value=_universe([]),
        ),
        patch("obole.services.screener._scan_universe", return_value={}),
    ):
        screener_service.run_screen(
            min_market_cap=1e9,
            sectors=["Technology"],
            regression_window=15,
        )

    assert mock_get.call_args.args[0] == "SCREEN:1000000000.0:Technology:15"


def test_run_screen_applies_filters_and_sort():
    """Filtre + tri sont délégués au moteur pur (via le service)."""
    with (
        patch(
            "obole.services.screener.screener_data.fetch_universe",
            return_value=_universe(["AIR.PA", "AI.PA"]),
        ),
        patch(
            "obole.services.screener._scan_universe",
            return_value={
                "AIR.PA": _sr_dump("AIR.PA", z=-2.0),
                "AI.PA": _sr_dump("AI.PA", z=1.0),
            },
        ),
        patch("obole.services.screener.cache_data.get", return_value=None),
        patch("obole.services.screener.cache_data.put"),
    ):
        run = screener_service.run_screen(
            min_market_cap=1e9,
            sectors=None,
            regression_window=None,
            filters={"z": (-1.0, None)},
            sort_by=["z"],
        )

    assert [r.ticker for r in run.rows] == ["AI.PA"]


def test_run_screen_isolates_broken_ticker():
    """Un ticker cassé est isolé en `error`, jamais de crash global."""
    with (
        patch(
            "obole.services.screener.screener_data.fetch_universe",
            return_value=_universe(["AIR.PA", "BAD.PA"]),
        ),
        patch(
            "obole.services.screener.yahoo.fetch_prices",
            side_effect=[object(), TickerNotFound("BAD.PA")],
        ),
        patch(
            "obole.services.screener.screen_service.screen_stock",
            return_value=ScreenResult(**_sr_dump("AIR.PA")),
        ),
        patch("obole.services.screener.cache_data.get", return_value=None),
        patch("obole.services.screener.cache_data.put"),
    ):
        run = screener_service.run_screen(
            min_market_cap=1e9,
            sectors=None,
            regression_window=None,
        )

    rows = {r.ticker: r for r in run.rows}
    assert rows["AIR.PA"].error is None
    assert rows["BAD.PA"].error is not None


# --- Validation des filtres/tri/score (règle partagée API ↔ MCP) -------------


class TestValidateFilters:
    """`validate_filters` : borne la validation métier, lève ValueError."""

    def test_none_returns_none(self):
        assert screener_service.validate_filters(None) is None

    def test_valid_numeric_bounds(self):
        out = screener_service.validate_filters({"z": (-2.0, None), "roe_pct": (10.0, 20.0)})
        assert out == {"z": (-2.0, None), "roe_pct": (10.0, 20.0)}

    def test_accepts_list_or_tuple(self):
        assert screener_service.validate_filters({"z": [-2.0, 0.0]}) == {"z": (-2.0, 0.0)}

    def test_not_a_dict_raises(self):
        with pytest.raises(ValueError, match="objet"):
            screener_service.validate_filters(["z"])

    def test_unknown_key_raises(self):
        with pytest.raises(ValueError, match="Critère inconnu"):
            screener_service.validate_filters({"bogus": (0, 10)})

    def test_score_is_not_filterable(self):
        with pytest.raises(ValueError, match="Critère inconnu"):
            screener_service.validate_filters({"score": (0, 100)})

    def test_malformed_bounds_raise(self):
        with pytest.raises(ValueError, match="min, max"):
            screener_service.validate_filters({"z": "high"})
        with pytest.raises(ValueError, match="min, max"):
            screener_service.validate_filters({"z": [1]})

    def test_non_numeric_bound_raises(self):
        with pytest.raises(ValueError, match="Borne invalide"):
            screener_service.validate_filters({"z": ("a", None)})

    def test_inverted_bounds_raise(self):
        with pytest.raises(ValueError, match="inversées"):
            screener_service.validate_filters({"z": (5.0, 1.0)})

    def test_one_sided_bounds_ok(self):
        assert screener_service.validate_filters({"z": (None, 0.0)}) == {"z": (None, 0.0)}


class TestValidateSortBy:
    def test_none_returns_none(self):
        assert screener_service.validate_sort_by(None) is None

    def test_key_only(self):
        assert screener_service.validate_sort_by(["z"]) == ["z"]

    def test_key_with_direction(self):
        assert screener_service.validate_sort_by([["pente_pct", "desc"]]) == [("pente_pct", "desc")]

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="liste non vide"):
            screener_service.validate_sort_by([])

    def test_not_a_list_raises(self):
        with pytest.raises(ValueError, match="liste non vide"):
            screener_service.validate_sort_by("z")

    def test_unknown_key_raises(self):
        with pytest.raises(ValueError, match="Critère inconnu"):
            screener_service.validate_sort_by(["bogus"])

    def test_invalid_direction_raises(self):
        with pytest.raises(ValueError, match="Sens invalide"):
            screener_service.validate_sort_by([["z", "up"]])

    def test_malformed_spec_raises(self):
        with pytest.raises(ValueError, match="invalide"):
            screener_service.validate_sort_by([123])


class TestValidateScoreKeys:
    def test_falsy_returns_none(self):
        assert screener_service.validate_score_keys(None) is None
        assert screener_service.validate_score_keys([]) is None

    def test_unknown_keys_ignored(self):
        assert screener_service.validate_score_keys(["z", "bogus"]) == ["z"]

    def test_non_list_returns_none(self):
        assert screener_service.validate_score_keys("z") is None


class TestValidateMaxRows:
    """`max_rows` : borne de volume partagée API ↔ MCP (jalon lean)."""

    def test_none_pas_de_borne(self):
        assert screener_service.validate_max_rows(None) is None

    def test_entier_positif_accepte(self):
        assert screener_service.validate_max_rows(10) == 10

    @pytest.mark.parametrize("bad", [0, -3, 1.5, "10", True])
    def test_valeurs_invalides_rejetees(self, bad):
        with pytest.raises(ValueError, match="max_rows"):
            screener_service.validate_max_rows(bad)


class TestValidateBounds:
    """Bornage des pré-filtres (règle partagée API ↔ MCP, borne métier)."""

    def test_capi_falsy_returns_none(self):
        for v in (None, "", 0, "0"):
            assert screener_service.validate_min_market_cap(v) is None

    def test_capi_positive_ok(self):
        assert screener_service.validate_min_market_cap(1e9) == 1e9
        assert screener_service.validate_min_market_cap("10000") == 10000.0

    def test_capi_negative_raises(self):
        with pytest.raises(ValueError, match="Capi invalide"):
            screener_service.validate_min_market_cap(-1)

    def test_capi_non_numeric_raises(self):
        with pytest.raises(ValueError, match="Capi invalide"):
            screener_service.validate_min_market_cap("1 mois")

    def test_window_falsy_returns_none(self):
        for v in (None, "", 0, "0"):
            assert screener_service.validate_regression_window(v) is None

    def test_window_positive_ok(self):
        assert screener_service.validate_regression_window(20) == 20.0
        assert screener_service.validate_regression_window("15") == 15.0

    def test_window_non_positive_raises(self):
        with pytest.raises(ValueError, match="Fenêtre invalide"):
            screener_service.validate_regression_window(-3)

    def test_window_non_numeric_raises(self):
        with pytest.raises(ValueError, match="Fenêtre invalide"):
            screener_service.validate_regression_window("n/a")
