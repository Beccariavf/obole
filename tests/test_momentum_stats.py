"""Tests purs des statistiques du score momentum — sans réseau."""

from __future__ import annotations

import numpy as np
import pandas as pd

from obole.engine import momentum_stats as stats


def _scores(values) -> pd.Series:
    return pd.Series(np.asarray(values, dtype=float))


def test_percentile_is_the_share_of_scores_below_or_equal():
    # 1..100 : 50 est le 50e score, donc la moitié de la série est en dessous.
    assert stats.score_percentile(_scores(range(1, 101)), 50.0, min_points=10) == 50
    assert stats.score_percentile(_scores(range(1, 101)), 33.0, min_points=10) == 33


def test_minimum_keeps_its_one_over_n_rank():
    # Le minimum est égal à lui-même : son rang vaut 1/n, visible sur les petits
    # échantillons (10 points → 10 %). Sur 60 points, 1/60 ≈ 1,67 % → 2 %.
    # Au-delà de ~200 points il arrondit à 0 : 0 veut alors dire « au plus bas
    # de l'historique », pas « sous tout l'historique » (test dédié plus bas).
    assert stats.score_percentile(_scores(range(1, 11)), 1.0, min_points=10) == 10
    assert stats.score_percentile(_scores(range(1, 61)), 1.0, min_points=60) == 2


def test_minimum_rounds_to_zero_on_a_long_history():
    # 1/600 ≈ 0,17 % : le rang du minimum arrondit à 0, exactement comme un
    # score strictement inférieur — les deux se confondent, c'est assumé. Pas de
    # plancher : 0 dit « au plus bas de son histoire », ce qui est exact.
    scores = _scores(np.linspace(0.2, 0.8, 600))
    assert stats.score_percentile(scores, 0.2, min_points=600) == 0
    assert stats.score_percentile(scores, 0.1, min_points=600) == 0
    # Le reste de l'échelle n'est pas écrasé par ce 0 : le milieu vaut 50.
    assert stats.score_percentile(scores, float(scores.iloc[300]), min_points=600) == 50


def test_below_minimum_is_zero_and_maximum_is_a_hundred():
    scores = _scores(np.linspace(0.2, 0.8, 200))
    assert stats.score_percentile(scores, 0.1, min_points=10) == 0
    assert stats.score_percentile(scores, 0.8, min_points=10) == 100
    # Au-dessus du maximum, le rang plafonne : jamais plus de 100.
    assert stats.score_percentile(scores, 5.0, min_points=10) == 100


def test_flat_series_ranks_at_a_hundred():
    # Tous les scores valent la valeur : elle est le maximum de la série.
    assert stats.score_percentile(_scores([0.5] * 80), 0.5, min_points=10) == 100


def test_too_short_history_has_no_rank():
    assert stats.score_percentile(_scores([0.5] * 59), 0.5, min_points=60) is None
    # Exactement le minimum de points suffit.
    assert stats.score_percentile(_scores([0.5] * 60), 0.5, min_points=60) == 100


def test_missing_value_has_no_rank():
    scores = _scores([0.4, 0.6] * 40)
    assert stats.score_percentile(scores, None, min_points=10) is None
    assert stats.score_percentile(scores, float("nan"), min_points=10) is None


def test_nan_scores_are_ignored():
    # Quatre points utiles seulement : 2 est le 2e, soit 50 %.
    scores = _scores([1.0, 2.0, 3.0, 4.0, np.nan, np.nan])
    assert stats.score_percentile(scores, 2.0, min_points=4) == 50
    # Les NaN ne comptent pas dans le dénominateur : 4 points, pas 6.
    assert stats.score_percentile(scores, 4.0, min_points=4) == 100
    # Une série entièrement NaN n'a aucun rang.
    assert stats.score_percentile(_scores([np.nan] * 80), 0.5, min_points=10) is None


def test_numpy_array_is_accepted():
    # Le service peut passer un tableau : le moteur ne dépend pas de pandas.
    values = np.linspace(0.0, 1.0, 50)
    assert stats.score_percentile(values, 0.5, min_points=10) == 50
