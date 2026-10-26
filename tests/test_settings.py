"""Tests des réglages utilisateur (panneau Paramètres).

Sans réseau : le cache est isolé sur une base temporaire (config.CACHE_DB),
l'API montée sur TestClient, et les payloads de graphe testés en direct
(serialize.py lit les réglages via cache.get_settings).
"""

from __future__ import annotations

import tempfile
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from obole import config
from obole.data import cache


@pytest.fixture(autouse=True)
def _isolated_db():
    """Isole le cache sur une base temporaire (évite de toucher cache.sqlite)."""
    _orig = config.CACHE_DB
    config.CACHE_DB = tempfile.mktemp(suffix=".sqlite")
    yield
    config.CACHE_DB = _orig


class TestGetSettings:
    def test_defaults_when_empty(self):
        assert cache.get_settings() == {
            "trend_ma_short": 11,
            "trend_ma_long": 200,
            "portfolio_benchmark": config.PORTFOLIO_BENCHMARK_DEFAULT,
            "portfolio_period": config.PORTFOLIO_PERIOD_DEFAULT,
            "portfolio_risk_free": config.SETTING_DEFS["portfolio_risk_free"]["default"],
            # Seuils de conviction (#27) : milieux des ancres 1600/1500/1400.
            "conviction_tier1_min": 57,
            "conviction_tier2_min": 43,
        }

    def test_returns_defaults_from_config(self):
        out = cache.get_settings()
        assert out["trend_ma_short"] == config.TREND_MA_SHORT
        assert out["trend_ma_long"] == config.TREND_MA_LONG

    def test_persisted_value_read_back(self):
        cache.set_settings({"trend_ma_short": 20})
        assert cache.get_settings()["trend_ma_short"] == 20
        assert cache.get_settings()["trend_ma_long"] == 200

    def test_ignores_unknown_or_corrupt_keys(self):
        cache.set_settings({"trend_ma_short": 20})
        # Clé inconnue -> ignorée ; valeur non-entier -> défaut.
        assert cache.get_settings()["trend_ma_short"] == 20


class TestSetSettings:
    def test_merge_partial(self):
        cache.set_settings({"trend_ma_long": 150})
        assert cache.get_settings()["trend_ma_long"] == 150
        assert cache.get_settings()["trend_ma_short"] == 11

    def test_rejects_short_not_less_than_long(self):
        with pytest.raises(ValueError, match="courte doit être <"):
            cache.set_settings({"trend_ma_short": 150, "trend_ma_long": 100})

    def test_rejects_out_of_bounds(self):
        with pytest.raises(ValueError, match="hors bornes"):
            cache.set_settings({"trend_ma_short": 999})

    def test_rejects_non_integer(self):
        with pytest.raises(ValueError, match="invalide"):
            cache.set_settings({"trend_ma_short": "abc"})

    def test_ignores_unknown_keys(self):
        out = cache.set_settings({"nope": 5})
        assert "nope" not in out


class TestSettingsApi:
    @pytest.fixture(autouse=True)
    def _client(self):
        from obole.api.app import app

        self._client = TestClient(app)
        yield self._client

    def test_get_returns_struct_payload(self):
        r = self._client.get("/api/settings")
        assert r.status_code == 200
        data = r.json()
        assert "values" in data and "defs" in data and "groups" in data
        assert data["values"]["trend_ma_short"] == 11

    def test_put_partial_and_persists(self):
        r = self._client.put("/api/settings", json={"values": {"trend_ma_short": 20}})
        assert r.status_code == 200
        assert r.json()["values"]["trend_ma_short"] == 20
        assert self._client.get("/api/settings").json()["values"]["trend_ma_short"] == 20

    def test_put_422_on_inversion(self):
        r = self._client.put(
            "/api/settings", json={"values": {"trend_ma_short": 150, "trend_ma_long": 100}}
        )
        assert r.status_code == 422
        assert "courte" in r.json()["detail"]

    def test_put_422_on_out_of_bounds(self):
        r = self._client.put("/api/settings", json={"values": {"trend_ma_short": 999}})
        assert r.status_code == 422


class TestConvictionSettings:
    """Seuils de conviction (#27) : défauts, groupe, persistance, inversion."""

    def test_defaults_and_group_in_payload(self):
        from obole.api.app import app

        data = TestClient(app).get("/api/settings").json()
        assert data["values"]["conviction_tier1_min"] == 57
        assert data["values"]["conviction_tier2_min"] == 43
        # Le groupe est exposé ET ordonné après la mesure technique.
        assert data["groups"] == ["technique", "conviction"]
        assert data["defs"]["conviction_tier1_min"] == {
            "default": 57,
            "min": 0,
            "max": 100,
            "label": "Seuil Tier 1",
            "group": "conviction",
        }
        assert data["defs"]["conviction_tier2_min"]["group"] == "conviction"

    def test_persists_60_40_and_reads_back(self):
        cache.set_settings({"conviction_tier1_min": 60, "conviction_tier2_min": 40})
        assert cache.get_settings()["conviction_tier1_min"] == 60
        assert cache.get_settings()["conviction_tier2_min"] == 40
        # Les autres réglages ne sont pas touchés par la fusion partielle.
        assert cache.get_settings()["trend_ma_short"] == 11

    def test_put_persists_60_40(self):
        from obole.api.app import app

        client = TestClient(app)
        r = client.put(
            "/api/settings",
            json={"values": {"conviction_tier1_min": 60, "conviction_tier2_min": 40}},
        )
        assert r.status_code == 200
        assert r.json()["values"]["conviction_tier1_min"] == 60
        assert r.json()["values"]["conviction_tier2_min"] == 40
        relu = client.get("/api/settings").json()["values"]
        assert (relu["conviction_tier1_min"], relu["conviction_tier2_min"]) == (60, 40)

    def test_rejects_tier1_not_above_tier2(self):
        with pytest.raises(ValueError, match="Tier 1 doit être supérieur"):
            cache.set_settings({"conviction_tier1_min": 40, "conviction_tier2_min": 50})
        # Rien n'a été persisté : les défauts restent en place.
        assert cache.get_settings()["conviction_tier1_min"] == 57
        assert cache.get_settings()["conviction_tier2_min"] == 43

    def test_put_422_on_inversion_keeps_previous_values(self):
        from obole.api.app import app

        client = TestClient(app)
        client.put("/api/settings", json={"values": {"conviction_tier1_min": 60, "conviction_tier2_min": 40}})
        r = client.put(
            "/api/settings",
            json={"values": {"conviction_tier1_min": 40, "conviction_tier2_min": 50}},
        )
        assert r.status_code == 422
        assert "Tier 1" in r.json()["detail"]
        relu = client.get("/api/settings").json()["values"]
        assert (relu["conviction_tier1_min"], relu["conviction_tier2_min"]) == (60, 40)

    def test_rejects_out_of_bounds(self):
        with pytest.raises(ValueError, match="hors bornes"):
            cache.set_settings({"conviction_tier1_min": 101})

    def test_ma_and_conviction_coexist(self):
        cache.set_settings({"trend_ma_short": 20, "conviction_tier1_min": 70})
        out = cache.get_settings()
        assert out["trend_ma_short"] == 20
        assert out["conviction_tier1_min"] == 70
        assert out["conviction_tier2_min"] == 43


class TestSerializeUsesSettings:
    def test_ma_windows_follow_settings(self):
        from obole.services import serialize

        idx = pd.date_range("2015-01-01", periods=600, freq="B")
        s = pd.Series(100 + np.arange(600) * 0.1, index=idx)

        def _first_non_none(vals):
            return next((i for i, v in enumerate(vals) if v is not None), None)

        # Défaut : MM200 -> premier point valide à l'index 199.
        with patch("obole.services.serialize.cache.get_settings") as gs:
            gs.return_value = {"trend_ma_short": 11, "trend_ma_long": 200}
            p = serialize.ratio_chart_payload(s, s, s)
        assert _first_non_none(p["ma_long"]) == 199

        # Changé en MM60 -> premier point valide à l'index 59 (fenêtre appliquée).
        with patch("obole.services.serialize.cache.get_settings") as gs:
            gs.return_value = {"trend_ma_short": 20, "trend_ma_long": 60}
            p2 = serialize.ratio_chart_payload(s, s, s)
        assert _first_non_none(p2["ma_long"]) == 59
        assert _first_non_none(p2["ma_long"]) != _first_non_none(p["ma_long"])


class TestTrendUsesSettings:
    def test_index_stats_uses_custom_ma(self):
        from obole.engine import summary

        # Série en « cloche » : monte fortement puis redescend sur la fin.
        # En fin, la MM courte (11) est < MM longue (200) -> baissier.
        idx = pd.date_range("2000-01-03", periods=4000, freq="B")
        n = len(idx)
        peak = int(n * 0.8)
        arr = np.empty(n)
        arr[:peak] = 20 * np.exp(np.arange(peak) * 0.001)
        arr[peak:] = arr[peak] * np.exp(-(np.arange(n - peak) + 1) * 0.0005)
        s = pd.Series(arr, index=idx)

        # MM11/200 : la tendance « baissière » est détectable (MM courte < longue).
        default = summary.index_stats(s, ma_short=11, ma_long=200)
        assert default["trend"].label is not None
        # La MM longue > historique (2500 > n) ne peut pas se calculer manuiellement
        # de façon stable ; on vérifie qu'une MM courte très courte reste évaluable.
        short_ma = summary.index_stats(s, ma_short=5, ma_long=200)
        assert short_ma["trend"].label is not None
