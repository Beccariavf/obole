"""Calendrier du portefeuille : l'axe temps est un axe de SÉANCES (#24).

Trois familles de vérifications :

- **unité** : `services.portfolio._trading_index` normalise des index tz-aware
  (chaque place a son fuseau) en jours calendaires, ignore les séries 24/7 et
  ne conserve que les jours de semaine ;
- **non-régression du bug** : un périmètre mêlant une place européenne
  (`Europe/Paris`) et un actif coté 24/7 (`UTC`) produisait deux points par
  date (`13T00:00Z` et `13T22:00Z` -> deux fois « 2025-05-13 »), d'où des dents
  de scie dans la courbe TWR et un décalage d'un jour sur les cours européens ;
- **services** : `summary`, `risk` et `performance` partagent le même axe (même
  nombre de points, dates croissantes, aucun week-end).
"""

from __future__ import annotations

import tempfile

import numpy as np
import pandas as pd
import pytest

from obole import config
from obole.data import portfolio as portfolio_data
from obole.models import PriceSeries
from obole.services import portfolio as svc


@pytest.fixture(autouse=True)
def _isolated_db():
    _orig = config.CACHE_DB
    config.CACHE_DB = tempfile.mktemp(suffix=".sqlite")
    yield
    config.CACHE_DB = _orig


def _paris_index() -> pd.DatetimeIndex:
    """Séances d'une place européenne : jours ouvrés, barres à 00:00 Paris."""
    days = pd.bdate_range("2025-05-13", periods=40)
    return days.tz_localize("Europe/Paris")


def _utc_index() -> pd.DatetimeIndex:
    """Actif coté 24/7 : toutes les dates, barres à 00:00 UTC (fuseau distinct)."""
    days = pd.date_range("2025-05-13", periods=56, freq="D")
    return days.tz_localize("UTC")


def _ps(index: pd.DatetimeIndex, base: float = 100.0) -> PriceSeries:
    values = pd.Series(base * np.exp(np.arange(len(index)) * 0.001), index=index)
    return PriceSeries(raw=values, adjusted=values, fetched_at=index[-1].date())


@pytest.fixture
def mixed_prices(monkeypatch):
    """Univers mêlant fuseaux : Paris (actions + benchmark) et UTC 24/7 (crypto)."""
    from obole.data import yahoo

    universe = {
        "RI.PA": _ps(_paris_index(), 100.0),
        "AI.PA": _ps(_paris_index(), 50.0),
        "CW8.PA": _ps(_paris_index(), 400.0),
        "BTC-EUR": _ps(_utc_index(), 30000.0),
    }

    def _fetch(ticker: str) -> PriceSeries:
        ps = universe.get(ticker)
        if ps is None:
            raise yahoo.TickerNotFound(ticker)
        return ps

    monkeypatch.setattr(yahoo, "fetch_prices", _fetch)
    monkeypatch.setattr(yahoo, "fetch_identity_cached", lambda _t: None)
    return universe


# --- Unité : le helper de calendrier ----------------------------------------


class TestTradingIndex:
    def test_deduplicates_tz_shifted_bars(self, mixed_prices):
        """13T00:00Z et 13T22:00Z (barre Paris) tombent le même jour : un seul point."""
        idx = svc._trading_index(mixed_prices, "CW8.PA", "2025-05-13")
        dates = [d.date().isoformat() for d in idx]
        assert len(dates) == len(set(dates))

    def test_is_strictly_monotonic(self, mixed_prices):
        idx = svc._trading_index(mixed_prices, "CW8.PA", "2025-05-13")
        assert list(idx) == sorted(idx)

    def test_excludes_weekends(self, mixed_prices):
        """Un actif 24/7 apporte des samedis/dimanches : ils sont écartés."""
        idx = svc._trading_index(mixed_prices, "CW8.PA", "2025-05-13")
        assert not any(d.weekday() >= 5 for d in idx)

    def test_keeps_a_real_session_missing_from_benchmark(self, monkeypatch):
        """Une séance ouvrée absente du benchmark est conservée (jour férié local)."""
        from obole.data import yahoo

        paris = _paris_index()
        # Action qui cote un jour ouvré de plus que le benchmark.
        extra = paris[-1] + pd.Timedelta(days=1)
        widened = paris.append(pd.DatetimeIndex([extra]))
        universe = {"CW8.PA": _ps(paris, 400.0), "RI.PA": _ps(widened, 100.0)}
        monkeypatch.setattr(
            yahoo,
            "fetch_prices",
            lambda t: universe[t],
        )
        idx = svc._trading_index(universe, "CW8.PA", "2025-05-13")
        assert extra.date() in {d.date() for d in idx}

    def test_start_bound_is_inclusive(self, mixed_prices):
        idx = svc._trading_index(mixed_prices, "CW8.PA", "2025-05-20")
        assert idx[0].date().isoformat() >= "2025-05-20"

    def test_empty_portfolio_returns_benchmark_sessions(self, monkeypatch):
        from obole.data import yahoo

        paris = _paris_index()
        monkeypatch.setattr(yahoo, "fetch_prices", lambda t: _ps(paris, 400.0))
        idx = svc._trading_index({"CW8.PA": _ps(paris, 400.0)}, "CW8.PA", "2025-05-13")
        assert len(idx) == len(paris)

    def test_single_stray_weekend_bar_does_not_discard_a_stock(self, monkeypatch):
        """Une bARRE parasite le samedi ne suffit pas à classer une action « 24/7 ».

        L'ancien critère (« au moins un week-end ») écartait alors TOUT le titre du
        calendrier, silencieusement : il perdait ses séances propres (jours fériés
        locaux absents du benchmark).
        """
        from obole.data import yahoo

        paris = _paris_index()
        stray = pd.DatetimeIndex([paris[0] + pd.Timedelta(days=4)])  # un samedi
        widened = paris.append(stray).sort_values()
        assert widened.weekday.tolist().count(5) == 1  # bien un samedi isolé
        universe = {"CW8.PA": _ps(paris, 400.0), "RI.PA": _ps(widened, 100.0)}
        monkeypatch.setattr(yahoo, "fetch_prices", lambda t: universe[t])

        assert svc._is_round_the_clock(widened) is False
        # La séance propre du titre est conservée : aucune perte de points.
        idx = svc._trading_index(universe, "CW8.PA", "2025-05-13")
        assert len(idx) == len(paris)

    def test_round_the_clock_detected_when_weekends_covered(self):
        """Un actif qui cote tous les week-ends de la période est écarté."""
        days = pd.date_range("2025-05-13", periods=56, freq="D")
        assert svc._is_round_the_clock(pd.DatetimeIndex(days)) is True


# --- Services : les trois sections partagent le même axe --------------------


class TestServicesShareCalendar:
    def _seed(self) -> int:
        acc = portfolio_data.create_account("PEA")
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2025-05-13", 10, 100.0)
        portfolio_data.add_transaction(acc, "BTC-EUR", "buy", "2025-05-20", 0.01, 30000.0)
        return acc

    def test_summary_dates_are_unique_and_monotonic(self, mixed_prices):
        self._seed()
        s = svc.summary(None, "CW8.PA", "max")
        assert len(s["dates"]) == len(set(s["dates"]))
        assert s["dates"] == sorted(s["dates"])

    def test_summary_has_no_weekends(self, mixed_prices):
        self._seed()
        s = svc.summary(None, "CW8.PA", "max")
        assert not any(pd.Timestamp(d).weekday() >= 5 for d in s["dates"])

    def test_risk_uses_same_calendar(self, mixed_prices):
        self._seed()
        s = svc.summary(None, "CW8.PA", "max")
        r = svc.risk(None, "CW8.PA", "max")
        assert r["dates"] == s["dates"]

    def test_performance_uses_same_calendar(self, mixed_prices):
        self._seed()
        s = svc.summary(None, "CW8.PA", "max")
        p = svc.performance(None, "CW8.PA", "max")
        assert len(p["monthly"]["portfolio"]["rows"]) >= 1
        # Le contexte partagé garantit un axe identique : la fenêtre débute le
        # même jour que le Résumé.
        assert p["period_start"] == s["dates"][0]

    def test_single_benchmark_plus_crypto_yields_one_point_per_session(self):
        """Jouet minimal [CW8.PA, BTC-EUR] : un point par SÉANCE, jamais plus.

        L'axe doit valoir exactement le calendrier du benchmark : la crypto cote
        le week-end, elle ne doit donc ajouter AUCUN point. Une date dupliquée
        trahit deux barres du même jour (fuseaux différents) ; un week-end trahit
        l'actif 24/7 laissé dans le calendrier.
        """
        import pandas as pd

        from obole.data import yahoo

        paris = pd.bdate_range("2025-05-13", periods=40).tz_localize("Europe/Paris")
        universe = {"CW8.PA": _ps(paris, 400.0), "BTC-EUR": _ps(_utc_index(), 30000.0)}
        yahoo_orig = yahoo.fetch_prices
        yahoo.fetch_prices = lambda t: universe[t]
        try:
            acc = portfolio_data.create_account("Jouet")
            portfolio_data.add_transaction(acc, "CW8.PA", "buy", "2025-05-13", 1, 400.0)
            portfolio_data.add_transaction(acc, "BTC-EUR", "buy", "2025-05-20", 0.01, 30000.0)
            s = svc.summary(None, "CW8.PA", "max")
        finally:
            yahoo.fetch_prices = yahoo_orig

        dates = s["dates"]
        assert len(dates) == len(set(dates))
        assert dates == sorted(dates)
        assert not any(pd.Timestamp(d).weekday() >= 5 for d in dates)
        expected = [d.date().isoformat() for d in paris if d.date().isoformat() >= "2025-05-13"]
        assert dates == expected

    def test_series_lengths_match_dates(self, mixed_prices):
        self._seed()
        s = svc.summary(None, "CW8.PA", "max")
        assert len(s["portfolio"]) == len(s["dates"])
        assert len(s["benchmark_curve"]) == len(s["dates"])
        r = svc.risk(None, "CW8.PA", "max")
        assert len(r["drawdown"]) == len(r["dates"])
        assert len(r["benchmark_drawdown"]) == len(r["dates"])


# --- Contexte unique (#24) : les 3 sections partagent le même contexte -------


class TestSharedContext:
    def _seed(self) -> int:
        acc = portfolio_data.create_account("PEA")
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2025-05-13", 10, 100.0)
        return acc

    def test_context_is_the_single_source(self, mixed_prices):
        """`summary`/`risk`/`performance` consomment `_portfolio_context`."""
        self._seed()
        ctx = svc._portfolio_context(None, "CW8.PA", "max", None)
        s = svc.summary(None, "CW8.PA", "max")
        r = svc.risk(None, "CW8.PA", "max")
        p = svc.performance(None, "CW8.PA", "max")
        # Le contexte porte l'axe unique : les trois sections en dérivent.
        assert s["dates"] == ctx["dates"]
        assert r["dates"] == ctx["dates"][ctx["start_idx"] :]
        assert p["period_start"] == ctx["dates"][0]

    def test_context_has_no_duplicated_index(self, mixed_prices):
        """Le contexte lui-même n'a ni doublon ni week-end (régression #24)."""
        self._seed()
        ctx = svc._portfolio_context(None, "CW8.PA", "max", None)
        assert len(ctx["dates"]) == len(set(ctx["dates"]))
        assert not any(pd.Timestamp(d).weekday() >= 5 for d in ctx["dates"])
