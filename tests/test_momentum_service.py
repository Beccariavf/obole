"""Tests du payload momentum — sans réseau, cache SQLite isolé."""

from __future__ import annotations

import time

import pytest
from tests.test_analysis import _make_prices
from tests.test_api import _fake_analysis

from obole import config
from obole.data import cache
from obole.engine import clara_vallis as cv
from obole.services import momentum
from obole.services.serialize import _downsample, analysis_to_dict


@pytest.fixture
def temp_cache(monkeypatch, tmp_path):
    """Isole la base : sans ça, le test écrirait dans le cache du dépôt."""
    db = tmp_path / "cache.sqlite"
    monkeypatch.setattr(config, "CACHE_DB", db)
    return db


def _grid(prices):
    return _downsample(prices.raw).index


def _dates(prices) -> list[str]:
    return [d.strftime("%Y-%m-%d") for d in _grid(prices)]


def test_payload_aligns_on_chart_dates(temp_cache):
    prices = _make_prices(400)
    dates = _dates(prices)
    p = momentum.momentum_payload("TEST.PA", prices.raw, prices.adjusted, _grid(prices))

    assert len(p["raw"]) == len(dates)
    assert len(p["adj"]) == len(dates)
    assert p["n_used"] == config.MOMENTUM_WINDOW
    assert p["short_history"] is False
    assert len(p["year"]["dates"]) == config.MOMENTUM_WINDOW
    assert p["year"]["dates"][-1] == dates[-1]
    assert len(p["year"]["raw"]) == config.MOMENTUM_WINDOW


def test_second_call_is_cached(temp_cache, monkeypatch):
    prices = _make_prices(400)
    calls = {"n": 0}
    real = cv.satisfaction_series

    def counted(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(momentum.cv, "satisfaction_series", counted)
    momentum.momentum_payload("CACHE.PA", prices.raw, prices.adjusted, _grid(prices))
    first = calls["n"]
    momentum.momentum_payload("CACHE.PA", prices.raw, prices.adjusted, _grid(prices))
    assert calls["n"] == first  # deuxième appel servi par le cache


def test_invalidate_forces_recompute(temp_cache, monkeypatch):
    prices = _make_prices(400)
    calls = {"n": 0}
    real = cv.satisfaction_series

    def counted(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(momentum.cv, "satisfaction_series", counted)
    momentum.momentum_payload("INV.PA", prices.raw, prices.adjusted, _grid(prices))
    first = calls["n"]
    cache.invalidate("INV.PA")
    assert cache.get("INV.PA", "momentum", config.TTL_PRICES) is None
    momentum.momentum_payload("INV.PA", prices.raw, prices.adjusted, _grid(prices))
    assert calls["n"] > first  # l'invalidation a bien forcé le recalcul


def test_index_has_no_adjusted_series(temp_cache):
    prices = _make_prices(400)
    p = momentum.momentum_payload("INDEX:7", prices.raw, None, _grid(prices))
    assert p["adj"] is None
    assert p["year"]["adj"] is None
    assert p["score_adj"] is None


def test_stock_payload_carries_momentum(temp_cache):
    prices = _make_prices(400)
    payload = analysis_to_dict(_fake_analysis("FAKE", prices), prices)
    mom = payload["chart"]["momentum"]
    assert len(mom["raw"]) == len(payload["chart"]["dates"])
    assert mom["n_used"] == config.MOMENTUM_WINDOW


def test_no_chart_means_no_momentum(temp_cache):
    prices = _make_prices(400)
    payload = analysis_to_dict(_fake_analysis("FAKE", prices), prices, include_chart=False)
    assert "chart" not in payload


def test_cold_payload_stays_fast(temp_cache):
    # Garde-fou large : mesuré autour de 40 ms pour les deux séries.
    prices = _make_prices(10_000)
    t0 = time.perf_counter()
    momentum.momentum_payload("FAST.PA", prices.raw, prices.adjusted, _grid(prices))
    assert time.perf_counter() - t0 < 0.5
