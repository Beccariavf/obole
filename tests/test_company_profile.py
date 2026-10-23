"""Profil société (chantier #21, J1) — sans réseau, cache isolé.

Couvre la nouvelle moitié « Société » de la section « Thèse & Société » :

- `data/yahoo` : extraction et normalisation des champs société (`officers`,
  `employees`, `address`, `summary`, agenda résultat / détachement) ;
- `services/serialize` : bloc `profile` du payload `/api/stock` + drapeau
  `has_thesis` (pastille du rail) ;
- invalidation : une `Identity` v7 en cache est considérée périmée (v8).
"""

from __future__ import annotations

import tempfile
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from tests.test_analysis import _fake_identity, _make_prices

from obole import config
from obole.data import cache, yahoo
from obole.data import thesis as thesis_data
from obole.models import CompanyKind, Identity
from obole.services import serialize


@pytest.fixture(autouse=True)
def _isolated_db():
    """Isole le cache sur une base temporaire (évite de toucher cache.sqlite)."""
    _orig = config.CACHE_DB
    config.CACHE_DB = tempfile.mktemp(suffix=".sqlite")
    yield
    config.CACHE_DB = _orig


class TestOfficers:
    """`_officers` — normalisation des dirigeants."""

    def test_parses_name_title_age(self):
        info = {
            "companyOfficers": [
                {"name": "Alexandre Ricard", "title": "CEO", "age": 53},
                {"name": "Helene de Tissot", "title": "EVP of Finance", "age": 55},
            ]
        }
        officers = yahoo._officers(info)
        assert [o.name for o in officers] == ["Alexandre Ricard", "Helene de Tissot"]
        assert officers[0].title == "CEO"
        assert officers[0].age == 53

    def test_missing_returns_empty_tuple(self):
        assert yahoo._officers({}) == ()
        assert yahoo._officers({"companyOfficers": None}) == ()
        assert yahoo._officers({"companyOfficers": "nope"}) == ()

    def test_skips_nameless_and_non_dict_entries(self):
        info = {"companyOfficers": [{"title": "sans nom"}, "x", {"name": "  "}, {"name": "Ok"}]}
        assert [o.name for o in yahoo._officers(info)] == ["Ok"]

    def test_optional_fields_stay_none(self):
        officers = yahoo._officers({"companyOfficers": [{"name": "X"}]})
        assert officers[0].title is None
        assert officers[0].age is None

    def test_non_numeric_age_dropped(self):
        officers = yahoo._officers({"companyOfficers": [{"name": "X", "age": "?"}]})
        assert officers[0].age is None


class TestSmallHelpers:
    def test_employees_int_or_none(self):
        assert yahoo._employees(16006) == 16006
        assert yahoo._employees("16006") == 16006
        assert yahoo._employees(None) is None
        assert yahoo._employees("n/a") is None

    def test_address_city_and_country(self):
        assert yahoo._address({"city": "Paris", "country": "France"}) == "Paris, France"
        assert yahoo._address({"country": "France"}) == "France"
        assert yahoo._address({}) is None


class TestEarningsDate:
    """`_earnings_date` — source principale `info`, repli `calendar`, jamais bloquant."""

    class _Ticker:
        def __init__(self, calendar=None):
            self.calendar = calendar

    def test_from_info_timestamp_not_estimated(self):
        info = {"earningsTimestamp": 1787844600, "isEarningsDateEstimate": False}
        iso, estimated = yahoo._earnings_date(self._Ticker(), info)
        assert iso is not None and iso.startswith("2026-")
        assert estimated is False

    def test_estimated_flag_is_boolean(self):
        info = {"earningsTimestamp": 1787844600, "isEarningsDateEstimate": True}
        assert yahoo._earnings_date(self._Ticker(), info)[1] is True

    def test_fallback_to_calendar(self):
        import datetime

        calendar = {"Earnings Date": [datetime.date(2026, 8, 27)]}
        iso, estimated = yahoo._earnings_date(self._Ticker(calendar), {})
        assert iso == "2026-08-27"
        assert estimated is True

    def test_no_data_returns_none_pair(self):
        assert yahoo._earnings_date(self._Ticker(), {}) == (None, None)

    def test_calendar_error_is_not_fatal(self):
        class _Boom:
            @property
            def calendar(self):
                raise RuntimeError("réseau")

        assert yahoo._earnings_date(_Boom(), {}) == (None, None)

    def test_repli_calendar_avec_un_vrai_Ticker(self):
        """Régression : le helper reçoit un `yf.Ticker`, pas une chaîne.

        Passer le ticker (str) rendait le repli mort : `ticker.calendar` levait
        `AttributeError`, avalée par le `except` — la ligne « Prochain résultat »
        disparaissait sans bruit dès qu'`info` n'avait pas d'`earningsTimestamp`.
        """
        import datetime

        class _Ticker:
            @property
            def calendar(self):
                return {"Earnings Date": [datetime.date(2026, 8, 27)]}

        iso, estimated = yahoo._earnings_date(_Ticker(), {})
        assert iso == "2026-08-27"
        assert estimated is True

    def test_une_chaine_ne_permet_pas_le_repli(self):
        """Documente la contrainte : une chaîne ne porte pas `.calendar`."""
        assert yahoo._earnings_date("RI.PA", {}) == (None, None)


class TestProfilePayload:
    """`services/serialize._profile_payload` — forme du bloc `profile`."""

    def _identity(self, **over):
        base = dict(
            ticker="RI.PA",
            name="Pernod Ricard",
            address="Paris, France",
            employees=16006,
            summary="Producteur de vins et spiritueux.",
            next_earnings="2026-08-27",
            next_earnings_estimated=False,
            ex_dividend="2026-11-25",
            kind=CompanyKind.INDUSTRIAL,
            model_version=yahoo.MODEL_VERSION,
        )
        base.update(over)
        return Identity(**base)

    def test_full_profile(self):
        ident = self._identity(
            officers=yahoo._officers({"companyOfficers": [{"name": "A", "title": "CEO"}]})
        )
        payload = serialize._profile_payload(ident)
        assert payload["employees"] == 16006
        assert payload["address"] == "Paris, France"
        assert payload["officers"] == [{"name": "A", "title": "CEO", "age": None}]
        assert payload["next_earnings"] == "2026-08-27"
        assert payload["next_earnings_estimated"] is False
        assert payload["ex_dividend"] == "2026-11-25"

    def test_empty_profile_has_all_keys_none(self):
        payload = serialize._profile_payload(Identity(ticker="X.PA"))
        assert set(payload) == {
            "officers",
            "employees",
            "address",
            "summary",
            "next_earnings",
            "next_earnings_estimated",
            "ex_dividend",
        }
        assert payload["officers"] == []
        assert payload["employees"] is None
        assert payload["summary"] is None


class TestStockPayloadProfile:
    """`/api/stock` porte le profil + `has_thesis`, sans appel réseau supplémentaire."""

    def _patches(self):
        return (
            patch("obole.services.analysis.yahoo.fetch_prices", return_value=_make_prices()),
            patch("obole.services.analysis.yahoo.fetch_identity", side_effect=_fake_identity),
            patch("obole.services.analysis.yahoo.fetch_fundamentals", return_value=None),
        )

    def test_profile_and_has_thesis_present(self):
        p1, p2, p3 = self._patches()
        with p1, p2, p3:
            from obole.services.analysis import analyze_ticker

            analysis, prices = analyze_ticker("FAKE")
        payload = serialize.analysis_to_dict(analysis, prices)
        assert "profile" in payload
        assert payload["has_thesis"] is False

    def test_has_thesis_true_when_saved(self):
        thesis_data.save_thesis("FAKE", "## Pitch\n\nDécotée.")
        assert serialize._has_thesis("FAKE") is True
        assert serialize._has_thesis("AI.PA") is False

    def test_has_thesis_is_not_fatal_without_db(self):
        with patch.object(cache, "get_thesis", side_effect=RuntimeError("base HS")):
            assert serialize._has_thesis("FAKE") is False


class TestModelVersionInvalidation:
    """Une identité v7 en cache doit être re-fetch (les champs société manquent)."""

    def test_old_identity_is_stale(self):
        old = Identity(
            ticker="RI.PA",
            industry="Beverages",
            website="https://x",
            beta=0.8,
            week52_low=90.0,
            avg_volume=1e6,
            model_version=7,
        )
        assert yahoo._fresh_cached(old, Identity, yahoo._IDENTITY_FIELDS) is None

    def test_current_identity_with_address_is_fresh(self):
        fresh = Identity(
            ticker="RI.PA",
            industry="Beverages",
            website="https://x",
            beta=0.8,
            week52_low=90.0,
            avg_volume=1e6,
            address="Paris, France",
            model_version=yahoo.MODEL_VERSION,
        )
        assert yahoo._fresh_cached(fresh, Identity, yahoo._IDENTITY_FIELDS) is fresh

    def test_identity_without_company_fields_is_fresh(self):
        """Un ETF/crypto n'a ni `industry`, ni `website`, ni `address`.

        Exiger ces champs rendait son identité INDÉFINIMENT périmée : `info` et
        `calendar` étaient rejoués (2 tentatives) à chaque ouverture de la
        Performance (mesuré #24). Seul `model_version` périme désormais.
        """
        etf = Identity(
            ticker="CEMQ.DE",
            sector=None,
            industry=None,
            website=None,
            address=None,
            model_version=yahoo.MODEL_VERSION,
        )
        assert yahoo._fresh_cached(etf, Identity, yahoo._IDENTITY_FIELDS) is etf
        assert yahoo._IDENTITY_FIELDS == ()


class TestNoNegativeCacheOnNetworkFailure:
    """Un échec réseau ne doit JAMAIS figer une absence de donnée (#24).

    Sans cette distinction, un simple blip mettait en cache une identité quasi
    vide pour 7 jours (et `fundamentals_missing` pour 6 h), sans aucun signal côté
    front : la fiche restait sans nom ni comptes jusqu'à un rafraîchissement manuel.
    """

    def test_empty_info_is_not_cached(self, monkeypatch):
        monkeypatch.setattr(yahoo, "_with_retry", lambda *_a, **_k: None)
        monkeypatch.setattr(yahoo.yf, "Ticker", lambda _t: MagicMock())

        ident = yahoo.fetch_identity("FAIL.PA", None)

        assert ident.ticker == "FAIL.PA"
        assert cache.get("FAIL.PA", "identity", config.TTL_FUNDAMENTALS) is None
        assert cache.get("FAIL.PA", "info", config.TTL_FUNDAMENTALS) is None

    def test_all_calls_failed_does_not_arm_negative_marker(self, monkeypatch):
        monkeypatch.setattr(yahoo, "_with_retry", lambda *_a, **_k: None)
        monkeypatch.setattr(yahoo.yf, "Ticker", lambda _t: MagicMock())

        assert yahoo.fetch_fundamentals("FAIL.PA", CompanyKind.INDUSTRIAL) is None
        assert cache.get("FAIL.PA", "fundamentals_missing", config.TTL_MISSING_FUNDAMENTALS) is None

    def test_answered_but_empty_arms_negative_marker(self, monkeypatch):
        """Yahoo A répondu (tableaux vides) : l'absence est réelle, mémorisable."""
        calls = iter([pd.DataFrame(), None, None])
        monkeypatch.setattr(yahoo, "_with_retry", lambda *_a, **_k: next(calls))
        monkeypatch.setattr(yahoo.yf, "Ticker", lambda _t: MagicMock())

        assert yahoo.fetch_fundamentals("EMPTY.PA", CompanyKind.INDUSTRIAL) is None
        assert (
            cache.get("EMPTY.PA", "fundamentals_missing", config.TTL_MISSING_FUNDAMENTALS) is True
        )
