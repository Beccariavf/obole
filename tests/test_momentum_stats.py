"""Tests purs des statistiques du score momentum — sans réseau."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

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


# --- Rendement conditionnel par zone de score --------------------------------


def _prices(values, start: str = "2015-01-02") -> pd.Series:
    idx = pd.date_range(start, periods=len(values), freq="B")
    return pd.Series(np.asarray(values, dtype=float), index=idx)


def _constant_growth(n: int, rate: float = 0.0004) -> pd.Series:
    return _prices(100.0 * np.exp(rate * np.arange(n)))


def _zigzag(n: int = 4000, period: int = 500, amplitude: float = 0.3) -> pd.Series:
    """Cours qui monte puis descend : les trois zones de score sont visitées."""
    phases = 2.0 * np.pi * np.arange(n) / period
    return _prices(100.0 * np.exp(amplitude * np.sin(phases)))


def _scores_for(prices: pd.Series, pattern) -> pd.Series:
    values = np.asarray(pattern, dtype=float)
    filled = np.tile(values, len(prices) // values.size + 1)[: len(prices)]
    return pd.Series(filled, index=prices.index)


def test_constant_growth_gives_the_same_median_in_every_zone():
    prices = _constant_growth(400)
    scores = _scores_for(prices, [0.10, 0.45, 0.45, 0.80, 0.50])
    result = stats.conditional_forward_returns(prices, scores, 0.35, 0.60, 21)

    medians = [result["zones"][zone]["median_pct"] for zone in ("bas", "neutre", "haut")]
    assert all(median is not None for median in medians)
    assert medians[0] == medians[1] == medians[2]
    # 21 séances à 0,04 % par séance : exp(0,0004 × 21) − 1 ≈ 0,84 %.
    assert medians[0] == pytest.approx(0.84, abs=0.02)


def test_high_scores_precede_the_better_returns():
    n, horizon = 300, 5
    returns = np.where((np.arange(n) // horizon) % 2 == 0, 0.02, -0.01)
    prices = _prices(100.0 * np.cumprod(1.0 + returns))
    following = (prices.shift(-horizon) / prices - 1.0).to_numpy()
    # Le score de la séance t est haut quand les cinq séances suivantes montent.
    scores = pd.Series(np.where(following > 0, 0.9, 0.1), index=prices.index)
    result = stats.conditional_forward_returns(prices, scores, 0.35, 0.60, horizon)

    haut = result["zones"]["haut"]["median_pct"]
    bas = result["zones"]["bas"]["median_pct"]
    assert haut > bas + 3.0  # les fenêtres hautes rapportent nettement plus
    assert bas < 0.0  # celles qui suivent un score bas perdent
    assert result["baseline"]["median_pct"] is not None


def test_no_complete_window_means_no_zone():
    prices = _prices(np.linspace(100, 110, 20))
    scores = pd.Series(0.5, index=prices.index)
    result = stats.conditional_forward_returns(prices, scores, 0.35, 0.60, 252)

    assert result["baseline"] is None
    assert all(block is None for block in result["zones"].values())


def test_episodes_count_only_independent_windows():
    n, horizon = 60, 10
    prices = _prices(np.linspace(100, 200, n))
    scores = pd.Series(0.5, index=prices.index)
    result = stats.conditional_forward_returns(prices, scores, 0.35, 0.60, horizon)

    # 50 fenêtres complètes, une retenue toutes les 10 séances → 5 épisodes.
    assert result["baseline"]["episodes"] == 5
    assert result["zones"]["neutre"]["episodes"] == 5
    # Les 50 fenêtres comptent bien dans les centiles, pas seulement les 5.
    assert result["baseline"]["median_pct"] == pytest.approx(11.98, abs=0.1)


def test_zone_never_visited_is_none():
    prices = _prices(np.linspace(100, 120, 50))
    scores = pd.Series(0.9, index=prices.index)
    result = stats.conditional_forward_returns(prices, scores, 0.35, 0.60, 10)

    assert result["zones"]["bas"] is None
    assert result["zones"]["neutre"] is None
    assert result["zones"]["haut"] is not None


def test_centiles_bracket_the_median():
    result = stats.conditional_forward_returns(
        _zigzag(), _zigzag().pipe(lambda p: _scores_for(p, [0.2, 0.5, 0.8])), 0.35, 0.60, 252
    )
    block = result["baseline"]
    assert block["p10_pct"] <= block["median_pct"] <= block["p90_pct"]
    assert block["episodes"] > 0


def test_missing_scores_are_skipped():
    n, horizon = 40, 5
    prices = _prices(np.linspace(100, 140, n))
    scores = pd.Series(np.where(np.arange(n) % 2 == 0, 0.5, np.nan), index=prices.index)
    result = stats.conditional_forward_returns(prices, scores, 0.35, 0.60, horizon)

    # Une séance sur deux est écartée : positions 0, 2, …, 34, une toutes les
    # 5 séances → 0, 6, 12, 18, 24, 30.
    assert result["baseline"]["episodes"] == 6


def test_horizon_must_cover_at_least_one_session():
    prices = _prices(np.linspace(100, 120, 50))
    scores = pd.Series(0.5, index=prices.index)
    with pytest.raises(ValueError):
        stats.conditional_forward_returns(prices, scores, 0.35, 0.60, 0)


def test_zone_bounds_match_the_gauge():
    # Bornes STRICTES : un score égal à `low` ou à `high` est neutre, comme
    # `momState` dans le front ; il faut le dépasser pour changer de zone.
    prices = _prices(np.linspace(100, 160, 40))

    def zones(score):
        scores = pd.Series(score, index=prices.index)
        return stats.conditional_forward_returns(prices, scores, 0.35, 0.60, 5)["zones"]

    assert zones(0.35)["neutre"] is not None
    assert zones(0.35)["bas"] is None
    assert zones(0.3499)["bas"] is not None
    assert zones(0.3499)["neutre"] is None
    assert zones(0.60)["neutre"] is not None
    assert zones(0.60)["haut"] is None
    assert zones(0.6001)["haut"] is not None
    assert zones(0.6001)["neutre"] is None
