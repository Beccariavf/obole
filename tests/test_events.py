"""Tests des événements annotés des graphiques (cache + API + sérialisation).

Sans réseau : le cache est isolé sur une base temporaire (config.CACHE_DB),
l'API montée sur TestClient.
"""

from __future__ import annotations

import tempfile
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from obole import config
from obole.data import cache, events


@pytest.fixture(autouse=True)
def _isolated_db():
    """Isole le cache sur une base temporaire (évite de toucher cache.sqlite)."""
    _orig = config.CACHE_DB
    config.CACHE_DB = tempfile.mktemp(suffix=".sqlite")
    yield
    config.CACHE_DB = _orig


class TestEventKey:
    def test_stock_uppercases(self):
        assert events.event_key("stock", "ri.pa") == "RI.PA"

    def test_ratio_normalized(self):
        assert events.event_key("ratio", "cw8 / ri ") == "RATIO:CW8/RI"

    def test_index_prefixed(self):
        assert events.event_key("index", "3") == "INDEX:3"

    def test_unknown_kind_raises(self):
        with pytest.raises(ValueError, match="inconnu"):
            events.event_key("nope", "X")


class TestEventsCache:
    def test_add_and_list_sorted_by_date(self):
        cache.add_event("RI.PA", "2023-03-15", "Crise", None)
        cache.add_event("RI.PA", "2019-07-01", "OPA", "Contexte")
        out = cache.list_events("RI.PA")
        assert [e["date"] for e in out] == ["2019-07-01", "2023-03-15"]
        assert out[0]["label"] == "OPA"
        assert out[0]["description"] == "Contexte"

    def test_isolation_by_ref(self):
        cache.add_event("RI.PA", "2020-01-01", "A", None)
        assert cache.list_events("MC.PA") == []
        assert len(cache.list_events("RI.PA")) == 1

    def test_get_event_roundtrip(self):
        eid = cache.add_event("RI.PA", "2020-01-01", "A", "d")
        ev = cache.get_event(eid)
        assert ev == {
            "id": eid,
            "ref": "RI.PA",
            "date": "2020-01-01",
            "label": "A",
            "description": "d",
        }
        assert cache.get_event(99999) is None

    def test_update_event(self):
        eid = cache.add_event("RI.PA", "2020-01-01", "A", None)
        cache.update_event(eid, "2021-06-30", "B", "note")
        ev = cache.get_event(eid)
        assert (ev["date"], ev["label"], ev["description"]) == ("2021-06-30", "B", "note")

    def test_delete_event(self):
        eid = cache.add_event("RI.PA", "2020-01-01", "A", None)
        cache.delete_event(eid)
        assert cache.get_event(eid) is None
        assert cache.list_events("RI.PA") == []


class TestEventsValidation:
    def test_add_rejects_bad_date(self):
        with pytest.raises(ValueError, match="Date invalide"):
            events.add_event("stock", "RI.PA", "15/03/2023", "X")

    def test_add_rejects_empty_label(self):
        with pytest.raises(ValueError, match="vide"):
            events.add_event("stock", "RI.PA", "2023-03-15", "  ")

    def test_add_rejects_long_label(self):
        with pytest.raises(ValueError, match="trop long"):
            events.add_event("stock", "RI.PA", "2023-03-15", "x" * 61)

    def test_add_rejects_long_description(self):
        with pytest.raises(ValueError, match="trop longue"):
            events.add_event("stock", "RI.PA", "2023-03-15", "X", "d" * 301)

    def test_add_normalizes_date_and_strips(self):
        events.add_event("stock", "ri.pa", " 2023-03-05 ", "  Label ")
        ev = cache.list_events("RI.PA")[0]
        assert ev["date"] == "2023-03-05"
        assert ev["label"] == "Label"

    def test_index_key_rejects_non_numeric(self):
        with pytest.raises(ValueError, match="Identifiant d'indice invalide"):
            events.event_key("index", "abc")

    def test_delete_unknown_event_raises(self):
        with pytest.raises(ValueError, match="inconnu"):
            events.delete_event(424242)


class TestEventsApi:
    @pytest.fixture(autouse=True)
    def _client(self):
        from obole.api.app import app

        self._client = TestClient(app)
        yield self._client

    def test_post_get_delete_roundtrip(self):
        r = self._client.post(
            "/api/events/stock?ref=RI.PA",
            json={"date": "2023-03-15", "label": "Crise", "description": "Abandon dividende"},
        )
        assert r.status_code == 200
        eid = r.json()["id"]

        listed = self._client.get("/api/events/stock?ref=RI.PA").json()
        assert len(listed) == 1
        assert listed[0]["label"] == "Crise"

        r = self._client.delete(f"/api/events/{eid}")
        assert r.status_code == 200
        assert self._client.get("/api/events/stock?ref=RI.PA").json() == []

    def test_post_422_on_invalid_date(self):
        r = self._client.post(
            "/api/events/stock?ref=RI.PA", json={"date": "pas-une-date", "label": "X"}
        )
        assert r.status_code == 422
        assert "Date invalide" in r.json()["detail"]

    def test_post_422_on_empty_label(self):
        r = self._client.post(
            "/api/events/stock?ref=RI.PA", json={"date": "2023-03-15", "label": ""}
        )
        assert r.status_code == 422

    def test_put_edits_event(self):
        eid = self._client.post(
            "/api/events/stock?ref=RI.PA", json={"date": "2020-01-01", "label": "Avant"}
        ).json()["id"]
        r = self._client.put(f"/api/events/{eid}", json={"date": "2020-02-02", "label": "Après"})
        assert r.status_code == 200
        ev = self._client.get("/api/events/stock?ref=RI.PA").json()[0]
        assert (ev["date"], ev["label"]) == ("2020-02-02", "Après")

    def test_put_404_on_unknown(self):
        r = self._client.put("/api/events/424242", json={"date": "2020-01-01", "label": "X"})
        assert r.status_code == 404

    def test_delete_404_on_unknown(self):
        r = self._client.delete("/api/events/424242")
        assert r.status_code == 404

    def test_get_422_on_unknown_kind(self):
        r = self._client.get("/api/events/nope?ref=X")
        assert r.status_code == 422

    def test_get_422_on_missing_ref(self):
        r = self._client.get("/api/events/stock")
        assert r.status_code == 422
        assert "ref requis" in r.json()["detail"]

    def test_index_events_route(self):
        r = self._client.post(
            "/api/events/index?ref=3", json={"date": "2021-01-01", "label": "Création"}
        )
        assert r.status_code == 200
        listed = self._client.get("/api/events/index?ref=3").json()
        assert listed[0]["label"] == "Création"

    def test_ratio_events_route(self):
        """Le « / » du ref ratio est interdit dans le chemin (Starlette décode
        %2F avant le routage) : le ratio passe par ?a=&b=, comme /api/ratio."""
        r = self._client.post(
            "/api/events/ratio?a=CW8&b=RI", json={"date": "2020-03-16", "label": "Choc COVID"}
        )
        assert r.status_code == 200
        listed = self._client.get("/api/events/ratio?a=CW8&b=RI").json()
        assert len(listed) == 1
        assert listed[0]["label"] == "Choc COVID"
        # Le ref stocké est normalisé (upper, sans espaces) : clé RATIO:CW8/RI.
        assert cache.list_events("RATIO:CW8/RI")

    def test_ratio_422_on_missing_params(self):
        r = self._client.get("/api/events/ratio?a=CW8")
        assert r.status_code == 422
        assert "a et b requis" in r.json()["detail"]


class TestSerializeEmbedsEvents:
    def test_analysis_to_dict_includes_events(self):
        from obole.services import serialize

        cache.add_event("RI.PA", "2020-03-16", "COVID", "Chute des cours")

        idx = pd.date_range("2015-01-01", periods=300, freq="B")
        raw = pd.Series([100.0 + i for i in range(300)], index=idx)
        prices = type(
            "P",
            (),
            {"raw": raw, "adjusted": raw, "fetched_at": None},
        )()
        analysis = type(
            "A",
            (),
            {
                "identity": type(
                    "I",
                    (),
                    {
                        "ticker": "RI.PA",
                        "name": "Pernod",
                        "isin": None,
                        "country": None,
                        "sector": None,
                        "industry": None,
                        "website": None,
                        "currency": "EUR",
                        "market_cap": None,
                        "last_price": 100.0,
                        "beta": None,
                        "week52_low": None,
                        "week52_high": None,
                        "volume": None,
                        "avg_volume": None,
                        "kind": type("K", (), {"value": "industrial"})(),
                    },
                )(),
                "indicators": type(
                    "N",
                    (),
                    {
                        k: type("S", (), {"value": 0, "label": "L", "good": True})()
                        for k in (
                            "distance_sigma",
                            "perf_passee",
                            "ecart_type",
                            "potential_5y",
                            "potential_10y",
                            "trend",
                            "quality",
                        )
                    },
                )(),
                "regression_raw": type(
                    "R",
                    (),
                    {
                        "perf_annual": 0.05,
                        "start": pd.Timestamp("2015-01-01"),
                        "end": pd.Timestamp("2016-03-01"),
                        "n_points": 300,
                    },
                )(),
                "fundamentals": None,
                "warnings": [],
                "summary": [],
            },
        )()

        with (
            patch.object(serialize, "fundamentals_payload", return_value=None),
            patch.object(serialize, "chart_payload", return_value={}),
        ):
            payload = serialize.analysis_to_dict(analysis, prices)
        assert payload["events"] == [
            {
                "id": pytest.approx(cache.list_events("RI.PA")[0]["id"]),
                "date": "2020-03-16",
                "label": "COVID",
                "description": "Chute des cours",
            },
        ]

    def test_events_payload_swallows_invalid_kind(self):
        from obole.services import serialize

        assert serialize._events_payload("nope", "X") == []
