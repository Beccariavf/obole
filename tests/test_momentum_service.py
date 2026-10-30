"""Tests du payload momentum — sans réseau, cache SQLite isolé."""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
import pytest
from tests.test_analysis import _make_prices
from tests.test_api import _fake_analysis

from obole import config
from obole.data import cache
from obole.engine import clara_vallis as cv
from obole.models import PriceSeries
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


def _price_series(values, adjusted=None) -> PriceSeries:
    """Série de prix construite à la main (calendrier ouvré, sans réseau)."""
    idx = pd.date_range("2000-01-03", periods=len(values), freq="B")
    raw = pd.Series(np.asarray(values, dtype=float), index=idx)
    adj = raw if adjusted is None else pd.Series(np.asarray(adjusted, dtype=float), index=idx)
    return PriceSeries(raw=raw, adjusted=adj, fetched_at=pd.Timestamp("today").date())


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
    assert cache.get("INV.PA", momentum._cache_kind(), config.TTL_PRICES) is None
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


def test_cache_key_carries_the_window(temp_cache, monkeypatch):
    # Changer la fenêtre doit invalider le payload, pas le laisser périmé 24 h.
    before = momentum._cache_kind()
    monkeypatch.setattr(config, "MOMENTUM_WINDOW", 120)
    assert momentum._cache_kind() != before
    assert "120" in momentum._cache_kind()


def test_cache_key_carries_the_reading_suffix(temp_cache):
    # Un payload mis en cache avant la lecture du score n'a ni percentile ni
    # rendement conditionnel : sans suffixe, la fiche resterait muette 24 h.
    assert momentum._cache_kind().endswith(":lecture")


# --- Lecture du score : percentile et date de départ -------------------------


def test_payload_carries_percentile_and_history_start(temp_cache):
    prices = _make_prices(600)
    p = momentum.momentum_payload("LECT.PA", prices.raw, prices.adjusted, _grid(prices))

    assert isinstance(p["percentile_raw"], int)
    assert 0 <= p["percentile_raw"] <= 100
    assert isinstance(p["percentile_adj"], int)
    # Première date où le score est calculable : la fenêtre est alors pleine.
    expected = prices.raw.index[config.MOMENTUM_WINDOW - 1].strftime("%Y-%m-%d")
    assert p["history_start"] == expected
    # Chaque série porte SA date de départ : le libellé lit celle qu'il affiche.
    assert p["history_start_adj"] == expected


def test_percentile_reaches_a_hundred_at_the_history_maximum(temp_cache):
    # Longue baisse puis hausse : le score du jour est le plus haut de l'histoire.
    values = np.concatenate([np.linspace(200, 100, 550), np.linspace(100, 200, 250)])
    prices = _price_series(values)
    p = momentum.momentum_payload("MAX.PA", prices.raw, prices.adjusted, _grid(prices))

    assert p["score_raw"] > 0.99  # 249 bulles à 1, la dernière sans parcours (0,5)
    assert p["percentile_raw"] == 100


def test_percentile_adj_follows_the_adjusted_series(temp_cache):
    # Même titre, série ajustée de forme inverse : les deux rangs diffèrent.
    up = np.concatenate([np.linspace(200, 100, 550), np.linspace(100, 200, 250)])
    down = np.concatenate([np.linspace(100, 200, 550), np.linspace(200, 100, 250)])
    prices = _price_series(up, adjusted=down)
    p = momentum.momentum_payload("ADJ.PA", prices.raw, prices.adjusted, _grid(prices))

    assert p["percentile_raw"] == 100
    assert p["percentile_adj"] is not None
    assert p["percentile_adj"] < p["percentile_raw"]


def test_index_has_no_adjusted_percentile(temp_cache):
    prices = _price_series(np.linspace(100, 200, 600))
    p = momentum.momentum_payload("INDEX:7", prices.raw, None, _grid(prices))

    assert p["percentile_adj"] is None
    assert p["history_start_adj"] is None
    assert isinstance(p["percentile_raw"], int)


def test_short_history_has_no_percentile_but_keeps_its_start(temp_cache):
    # 40 séances : moins de 60 scores, le rang n'existe pas. La date de départ
    # est alors celle du seul point calculable, pas une date inventée.
    prices = _price_series(np.linspace(100, 120, 40))
    p = momentum.momentum_payload("SHORT.PA", prices.raw, prices.adjusted, _grid(prices))

    assert p["percentile_raw"] is None
    assert p["history_start"] == prices.raw.index[-1].strftime("%Y-%m-%d")


def test_percentile_ignores_the_displayed_range(temp_cache, monkeypatch):
    # Le rang porte sur tout l'historique : le rétrécir à la grille affichée
    # changerait le calcul. On vérifie ici que la grille n'entre pas dedans.
    prices = _make_prices(800)
    full = momentum.momentum_payload("RANGE.PA", prices.raw, prices.adjusted, _grid(prices))
    narrow = momentum.momentum_payload(
        "RANGE2.PA", prices.raw, prices.adjusted, _grid(prices)[-100:]
    )
    assert full["percentile_raw"] == narrow["percentile_raw"]
    assert full["history_start"] == narrow["history_start"]


def test_cold_payload_stays_fast(temp_cache):
    # Garde-fou large : mesuré autour de 40 ms pour les deux séries.
    prices = _make_prices(10_000)
    t0 = time.perf_counter()
    momentum.momentum_payload("FAST.PA", prices.raw, prices.adjusted, _grid(prices))
    assert time.perf_counter() - t0 < 0.5


# --- Lecture du score : rendement conditionnel par zone ----------------------


def _zigzag(n: int = 4000, period: int = 500) -> list[float]:
    """Cours qui monte puis descend : les trois zones de score sont visitées."""
    phases = 2.0 * np.pi * np.arange(n) / period
    return [float(v) for v in 100.0 * np.exp(0.3 * np.sin(phases))]


def test_payload_carries_conditional_returns(temp_cache):
    prices = _price_series(_zigzag())
    p = momentum.momentum_payload("COND.PA", prices.raw, prices.adjusted, _grid(prices))
    block = p["conditional_raw"]

    assert set(block) == {"zones", "baseline", "horizon"}
    assert set(block["zones"]) == {"bas", "neutre", "haut"}
    assert block["horizon"] == config.MOMENTUM_FORWARD_SESSIONS
    for zone in (*block["zones"].values(), block["baseline"]):
        assert zone is not None
        assert set(zone) == {"median_pct", "p10_pct", "p90_pct", "episodes", "thin"}
        assert zone["p10_pct"] <= zone["median_pct"] <= zone["p90_pct"]
        assert zone["episodes"] > 0
    # Le zigzag traverse tout l'intervalle de score : aucune zone vide.
    assert all(zone is not None for zone in block["zones"].values())
    assert p["conditional_adj"] is not None


def test_conditional_adj_reads_the_adjusted_series(temp_cache):
    raw = _zigzag()
    # Même forme, plus une dérive : la série ajustée ne rend pas les mêmes
    # rendements, donc le bloc ajusté ne peut pas recopier le bloc brut.
    drift = [value * (1.0005**i) for i, value in enumerate(raw)]
    prices = _price_series(raw, adjusted=drift)
    p = momentum.momentum_payload("CONDA.PA", prices.raw, prices.adjusted, _grid(prices))

    raw_median = p["conditional_raw"]["baseline"]["median_pct"]
    adj_median = p["conditional_adj"]["baseline"]["median_pct"]
    assert raw_median is not None
    assert adj_median is not None
    assert adj_median > raw_median


def test_index_has_no_adjusted_conditional(temp_cache):
    prices = _price_series(_zigzag())
    p = momentum.momentum_payload("INDEX:9", prices.raw, None, _grid(prices))

    assert p["conditional_adj"] is None
    assert p["conditional_raw"]["baseline"] is not None


def test_short_history_has_no_conditional(temp_cache):
    # 300 séances : l'horizon de 252 dépasse tout ce que le score peut couvrir.
    prices = _price_series(np.linspace(100, 120, 300))
    p = momentum.momentum_payload("SHORTC.PA", prices.raw, prices.adjusted, _grid(prices))
    block = p["conditional_raw"]

    assert block["baseline"] is None
    assert all(zone is None for zone in block["zones"].values())
    assert block["horizon"] == config.MOMENTUM_FORWARD_SESSIONS


def test_thin_zones_follow_the_config(temp_cache, monkeypatch):
    prices = _price_series(_zigzag())
    normal = momentum.momentum_payload("THIN.PA", prices.raw, prices.adjusted, _grid(prices))
    assert normal["conditional_raw"]["baseline"]["thin"] is False

    # La prudence est une décision serveur : relever le seuil la déclenche.
    monkeypatch.setattr(config, "MOMENTUM_CONDITIONAL_MIN_EPISODES", 10_000)
    tight = momentum.momentum_payload("TIGHT.PA", prices.raw, prices.adjusted, _grid(prices))
    assert tight["conditional_raw"]["baseline"]["thin"] is True
    assert tight["conditional_raw"]["zones"]["bas"]["thin"] is True


def test_conditional_ignores_the_displayed_range(temp_cache):
    prices = _price_series(_zigzag())
    full = momentum.momentum_payload("CRANGE.PA", prices.raw, prices.adjusted, _grid(prices))
    narrow = momentum.momentum_payload(
        "CRANGE2.PA", prices.raw, prices.adjusted, _grid(prices)[-100:]
    )

    assert full["conditional_raw"] == narrow["conditional_raw"]
    assert full["conditional_adj"] == narrow["conditional_adj"]
