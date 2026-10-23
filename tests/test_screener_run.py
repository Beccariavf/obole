"""Tests J3 — endpoint `POST /api/screener/run` (orchestration api).

Sans réseau : `yahoo.fetch_prices`, `screener_data.fetch_universe` et le cache
sont mockés. On vérifie l'assemblage passe 1 + passe 2 + cache + tri/filtre, et
l'isolation d'un ticker cassé (jamais de crash global). Le moteur (screen_stock /
filter_and_sort) est déjà couvert par test_screen.py.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from obole import config
from obole.api.app import app
from obole.data.yahoo import TickerNotFound
from obole.models import ScreenResult


def _client() -> TestClient:
    return TestClient(app)


def _sr_dump(ticker: str, **kw) -> dict:
    """ScreenResult -> dict, comme stocké dans le cache de scan."""
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


class TestScreenerRun:
    def test_post_returns_wellformed_rows(self):
        """Route mockée -> 200, rows bien formés et triés, source yahoo."""
        universe = _universe(["AIR.PA", "AI.PA"])
        with (
            patch("obole.services.screener.screener_data.fetch_universe", return_value=universe),
            patch("obole.services.screener._scan_universe") as scan,
            patch("obole.services.screener.cache_data.get", return_value=None),
            patch("obole.services.screener.cache_data.put"),
            patch(
                "obole.services.screener.screen_engine.filter_and_sort",
                side_effect=lambda rows, **k: rows,
            ),
        ):
            scan.return_value = {
                "AIR.PA": _sr_dump("AIR.PA"),
                "AI.PA": _sr_dump("AI.PA"),
            }
            resp = _client().post("/api/screener/run", json={})

        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] == "yahoo"
        assert data["count"] == 2
        assert data["tickers_count"] == 2
        assert {r["ticker"] for r in data["rows"]} == {"AIR.PA", "AI.PA"}
        # Un champ triable est présent et non None.
        row = data["rows"][0]
        assert row["z"] is not None
        assert row["kind"] == "industrial"
        assert row["error"] is None

    def test_default_min_cap_applied_when_absent(self):
        """`min_market_cap` absent -> défaut SCREEN_DEFAULT_MIN_CAP (1 Md€),
        et l'univers est demandé avec cette capi."""
        with (
            patch("obole.services.screener.cache_data.get", return_value=None),
            patch("obole.services.screener.cache_data.put"),
            patch("obole.services.screener._scan_universe", return_value={}),
            patch(
                "obole.services.screener.screener_data.fetch_universe", return_value=_universe([])
            ) as mock_u,
        ):
            _client().post("/api/screener/run", json={})

        assert mock_u.call_args.kwargs["min_market_cap"] == config.SCREEN_DEFAULT_MIN_CAP

    def test_null_min_cap_scans_full_universe(self):
        """`min_market_cap: null` explicite -> univers complet (aucune capi minimale)."""
        with (
            patch("obole.services.screener.cache_data.get", return_value=None),
            patch("obole.services.screener.cache_data.put"),
            patch("obole.services.screener._scan_universe", return_value={}),
            patch(
                "obole.services.screener.screener_data.fetch_universe", return_value=_universe([])
            ) as mock_u,
        ):
            _client().post("/api/screener/run", json={"min_market_cap": None})

        assert mock_u.call_args.kwargs["min_market_cap"] is None

    def test_invalid_min_cap_422(self):
        with (
            patch("obole.services.screener.cache_data.get", return_value=None),
            patch("obole.services.screener.cache_data.put"),
            patch("obole.services.screener._scan_universe"),
            patch("obole.services.screener.screener_data.fetch_universe"),
        ):
            resp = _client().post("/api/screener/run", json={"min_market_cap": "1 mois"})
        assert resp.status_code == 422

    def test_numeric_string_min_cap_accepted(self):
        """Une capi envoyée en chaîne numérique (front) est convertie, pas de 422."""
        with (
            patch("obole.services.screener.cache_data.get", return_value=None),
            patch("obole.services.screener.cache_data.put"),
            patch("obole.services.screener._scan_universe", return_value={}),
            patch(
                "obole.services.screener.screener_data.fetch_universe", return_value=_universe([])
            ) as mock_u,
        ):
            resp = _client().post("/api/screener/run", json={"min_market_cap": "10000"})
        assert resp.status_code == 200
        assert mock_u.call_args.kwargs["min_market_cap"] == 10000.0

    def test_regression_window_passed_to_screen_stock(self):
        """`regression_window` est transmis à `screen_stock` (via `_scan_universe`)."""
        universe = _universe(["AIR.PA"])
        with (
            patch("obole.services.screener.cache_data.get", return_value=None),
            patch("obole.services.screener.cache_data.put"),
            patch("obole.services.screener.screener_data.fetch_universe", return_value=universe),
            patch(
                "obole.services.screener.screen_service.screen_stock",
                return_value=ScreenResult(ticker="AIR.PA"),
            ) as screen_mock,
            patch("obole.services.screener.yahoo.fetch_prices"),
        ):
            _client().post("/api/screener/run", json={"regression_window": 15})

        assert screen_mock.call_args.args[2] == 15

    def test_invalid_regression_window_422(self):
        resp = _client().post("/api/screener/run", json={"regression_window": -3})
        assert resp.status_code == 422

    def test_ticker_not_found_isolated_no_crash(self):
        """Un TickerNotFound en passe 2 isole la ligne `error`, sans crash global."""
        universe = _universe(["AIR.PA", "BAD.PA"])
        with (
            patch("obole.services.screener.cache_data.get", return_value=None),
            patch("obole.services.screener.cache_data.put"),
            patch("obole.services.screener.screener_data.fetch_universe", return_value=universe),
            patch(
                "obole.services.screener.yahoo.fetch_prices",
                side_effect=[None, TickerNotFound("BAD.PA")],
            ),
            patch(
                "obole.services.screener.screen_service.screen_stock",
                return_value=ScreenResult(**_sr_dump("AIR.PA")),
            ),
        ):
            resp = _client().post("/api/screener/run", json={})

        assert resp.status_code == 200
        rows = {r["ticker"]: r for r in resp.json()["rows"]}
        assert rows["AIR.PA"]["error"] is None
        assert rows["BAD.PA"]["error"] is not None

    def test_cache_hit_skips_scan_and_universe(self):
        """Cache de scan chaud -> servi sans re-fetch réseau, source 'cache'."""
        cached = {
            "results": {"AIR.PA": _sr_dump("AIR.PA")},
            "source": "yahoo",
        }
        with (
            patch("obole.services.screener.cache_data.get", return_value=cached),
            patch("obole.services.screener.screener_data.fetch_universe") as mock_u,
            patch("obole.services.screener._scan_universe") as scan,
        ):
            resp = _client().post("/api/screener/run", json={"sort_by": ["z"]})

        assert resp.status_code == 200
        assert resp.json()["source"] == "cache"
        mock_u.assert_not_called()
        scan.assert_not_called()

    def test_sort_served_from_cache_no_rescan(self):
        """Un `sort_by` différent sert le même scan depuis le cache (pas de re-scan)."""
        cached = {
            "results": {"AIR.PA": _sr_dump("AIR.PA")},
            "source": "yahoo",
        }
        with (
            patch("obole.services.screener.cache_data.get", return_value=cached),
            patch("obole.services.screener._scan_universe") as scan,
        ):
            _client().post("/api/screener/run", json={"sort_by": ["pente_pct", "z"]})

        scan.assert_not_called()


class TestValidation:
    """Validation à la frontière API : filtres/tri invalides -> 422 (pas de 500)."""

    def _post(self, payload: dict) -> TestClient:
        with (
            patch("obole.services.screener.cache_data.get", return_value=None),
            patch("obole.services.screener.cache_data.put"),
        ):
            return _client().post("/api/screener/run", json=payload)

    @pytest.fixture(autouse=True)
    def _no_work(self):
        # Toute requête qui passe la validation doit pouvoir s'exécuter sans réseau.
        with (
            patch(
                "obole.services.screener.screener_data.fetch_universe", return_value=_universe([])
            ),
            patch("obole.services.screener._scan_universe", return_value={}),
        ):
            yield

    def test_unknown_filter_key_422(self):
        assert self._post({"filters": {"bogus": (0, 10)}}).status_code == 422

    def test_score_filter_422(self):
        """`score` est triable mais PAS filtrable : c'est un rang calculé, il
        dépend du jeu filtré (le filtrer serait un non-sens / résultat vide)."""
        assert self._post({"filters": {"score": (0, 100)}}).status_code == 422

    def test_malformed_filter_bounds_422(self):
        # Une structure non [min, max] au lieu d'un 500 silencieux dans engine.
        assert self._post({"filters": {"z": "high"}}).status_code == 422
        assert self._post({"filters": {"z": [1]}}).status_code == 422

    def test_numeric_filter_passes(self):
        # Bornes numériques valides -> 200 (le filtre franchit la validation).
        assert self._post({"filters": {"z": (-2.0, 0.0)}}).status_code == 200

    def test_inverted_bounds_422(self):
        assert self._post({"filters": {"z": (5.0, 1.0)}}).status_code == 422

    def test_multi_criteria_filters_pass(self):
        # E6 : plusieurs critères bornés (min/max) en un seul objet -> 200.
        # Le front envoie {critère: [min, max]} pour Capi/Pente/Écart-type/ROE…
        filters = {
            "market_cap": (1e9, None),
            "pente_pct": (4.0, None),
            "ecart_type_pct": (None, 35.0),
            "roe_pct": (10.0, None),
            "pot_5y_pct": (5.0, None),
            "per": (None, 12.0),
            "fcf_yield_pct": (8.0, None),
            "quality_score": (55.0, None),
        }
        assert self._post({"filters": filters}).status_code == 200

    def test_one_sided_bound_passes(self):
        # Une seule borne (min seul ou max seul) est valide.
        assert self._post({"filters": {"roe_pct": (10.0, None)}}).status_code == 200
        assert self._post({"filters": {"ecart_type_pct": (None, 30.0)}}).status_code == 200

    def test_unknown_sort_key_422(self):
        assert self._post({"sort_by": ["bogus"]}).status_code == 422

    def test_invalid_sort_direction_422(self):
        assert self._post({"sort_by": [("z", "up")]}).status_code == 422

    def test_empty_sort_by_422(self):
        assert self._post({"sort_by": []}).status_code == 422

    def test_valid_sort_by_passes(self):
        assert self._post({"sort_by": ["z", ("pente_pct", "desc")]}).status_code == 200


class TestScreenMetaAndPolarity:
    """J4 : /api/screener/meta (source unique) + polarité par cellule (config)."""

    def test_meta_exposes_sort_and_colors(self):
        resp = _client().get("/api/screener/meta")
        assert resp.status_code == 200
        data = resp.json()
        assert "sort_desc" in data and "colors" in data
        # Directions de tri présentes au moins pour les critères clés.
        assert data["sort_desc"]["z"] is False
        assert data["sort_desc"]["pente_pct"] is True
        assert data["sort_desc"]["per"] is False
        # Seuils de couleur : PER bon si positif <= 12.
        assert data["colors"]["per"]["sens"] == "le_pos"
        assert data["colors"]["per"]["seuil"] == 12.0

    def test_row_colors_never_good_on_negative_multiple(self):
        """Un PER négatif (société en perte) n'est JAMAIS coloré « good »."""
        from obole.models import ScreenResult
        from obole.services.serialize import screen_row_to_dict

        row = screen_row_to_dict(ScreenResult(ticker="X", per=-5.0, p_b=-1.0, p_fcf=-8.0))
        assert row["colors"]["per"] == "bad"
        assert row["colors"]["p_b"] == "bad"
        assert row["colors"]["p_fcf"] == "bad"

    def test_row_colors_good_on_reasonable_multiple(self):
        from obole.models import ScreenResult
        from obole.services.serialize import screen_row_to_dict

        row = screen_row_to_dict(
            ScreenResult(ticker="X", per=8.0, p_b=1.5, p_fcf=6.0, roe_pct=14.0, fcf_yield_pct=9.0)
        )
        assert row["colors"]["per"] == "good"
        assert row["colors"]["p_b"] == "good"
        assert row["colors"]["p_fcf"] == "good"
        assert row["colors"]["roe_pct"] == "good"
        assert row["colors"]["fcf_yield_pct"] == "good"

    def test_row_colors_neutral_on_radius(self):
        """Un critère sans valeur (None) est neutre (pas de couleur)."""
        from obole.models import ScreenResult
        from obole.services.serialize import screen_row_to_dict

        row = screen_row_to_dict(ScreenResult(ticker="X", per=None, roe_pct=None))
        assert row["colors"]["per"] is None
        assert row["colors"]["roe_pct"] is None

    def test_error_row_all_neutral(self):
        from obole.models import ScreenResult
        from obole.services.serialize import screen_row_to_dict

        row = screen_row_to_dict(ScreenResult(ticker="X", per=8.0, error="cassé"))
        assert all(c is None for c in row["colors"].values())

    def test_trend_bullish_boolean_polarity(self):
        """Tendance : True (haussière) = bon, False (baissière) = mauvais.
        (Un booléen ne doit pas être comparé numériquement : False >= 0 serait True.)"""
        from obole.models import ScreenResult
        from obole.services.serialize import screen_row_to_dict

        assert (
            screen_row_to_dict(ScreenResult(ticker="X", trend_bullish=True))["colors"][
                "trend_bullish"
            ]
            == "good"
        )
        assert (
            screen_row_to_dict(ScreenResult(ticker="X", trend_bullish=False))["colors"][
                "trend_bullish"
            ]
            == "bad"
        )
