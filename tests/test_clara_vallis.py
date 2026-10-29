"""Tests purs du moteur Clara Vallis — déterministes, sans réseau."""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
import pytest

from obole.engine import clara_vallis as cv


def _series(values, start: str = "2020-01-02", freq: str = "B") -> pd.Series:
    idx = pd.date_range(start, periods=len(values), freq=freq)
    return pd.Series(np.asarray(values, dtype=float), index=idx)


def test_rising_series_scores_one():
    # Chaque entrée voit son creux à son entrée et son sommet au dernier cours.
    # L'entrée du jour n'a aucun parcours : elle compte pour 0,5 (neutre), d'où
    # 249 × 1 + 0,5 sur 250 ≈ 0,998.
    s = _series(np.linspace(100, 200, 300))
    assert cv.satisfaction_score(s).value > 0.99


def test_falling_series_scores_zero():
    s = _series(np.linspace(200, 100, 300))
    assert cv.satisfaction_score(s).value < 0.01


def test_flat_series_scores_half():
    s = _series([100.0] * 300)
    assert cv.satisfaction_score(s).value == pytest.approx(0.5)


def test_v_shape_between_zero_and_one():
    values = np.concatenate(
        [np.linspace(120, 80, 100), np.linspace(80, 200, 100), np.linspace(200, 120, 100)]
    )
    score = cv.satisfaction_score(_series(values)).value
    assert score is not None
    assert 0.0 < score < 1.0


def test_short_history_is_flagged():
    s = _series(np.linspace(100, 120, 40))
    r = cv.satisfaction_score(s)
    assert r.short_history is True
    assert r.n_used == 40
    assert r.value is not None


def test_too_short_series_has_no_score():
    r = cv.satisfaction_score(_series([100.0]))
    assert r.value is None
    assert r.n_used == 0


def test_series_is_nan_before_window():
    s = _series(np.linspace(100, 200, 300))
    out = cv.satisfaction_series(s, window=250)
    assert out.iloc[:249].isna().all()
    assert out.iloc[249:].notna().all()


def test_no_lookahead():
    # Ajouter une séance future ne doit changer AUCUNE valeur passée.
    rng = np.random.default_rng(7)
    values = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 300)))
    before = cv.satisfaction_series(_series(values), window=250)
    extended = _series(np.append(values, values[-1] * 1.05))
    after = cv.satisfaction_series(extended, window=250)
    assert np.allclose(before.iloc[-50:].to_numpy(), after.iloc[-51:-1].to_numpy())


def test_regime_perfect_line_is_zero():
    # Index calendaire : le temps de la régression est en jours, pas en séances.
    s = _series(100 * np.exp(0.0003 * np.arange(300)), freq="D")
    assert cv.regime_score(s) == pytest.approx(0.0, abs=1e-6)


def test_regime_noise_is_high():
    # Bruit blanc autour d'un niveau plat : aucune tendance, R² ≈ 0.
    rng = np.random.default_rng(3)
    s = _series(100 * np.exp(rng.normal(0, 0.1, 300)))
    score = cv.regime_score(s)
    assert score is not None
    assert score > 0.9


def test_long_series_stays_fast():
    # Garde-fou anti-régression : une boucle Python par entrée prendrait des
    # secondes, la version vectorisée quelques dizaines de millisecondes.
    rng = np.random.default_rng(11)
    s = _series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 10_000))))
    t0 = time.perf_counter()
    out = cv.satisfaction_series(s, window=250)
    assert time.perf_counter() - t0 < 1.0
    assert out.notna().sum() == 10_000 - 249
