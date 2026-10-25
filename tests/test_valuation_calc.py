"""Tests de la calculatrice de prix juste (`engine/valuation_calc.py`).

Le moteur est la RÉFÉRENCE du modèle : ces tests verrouillent la formule
reconstituée sur la matrice Baggr (fit au 0,01 pt) et les cas limites (jamais
d'infini, jamais de valeur trompeuse). Le miroir JS est vérifié par un test de
parité côté front (`web-tests/valorisation.test.js`).
"""

from __future__ import annotations

import pandas as pd
import pytest

from obole.engine import valuation_calc as vc


def test_fair_price_nominal():
    assert vc.fair_price(6.45, 10.29) == pytest.approx(66.3705, abs=1e-4)


@pytest.mark.parametrize(
    "metric,multiple",
    [(None, 10.0), (6.0, None), (-1.0, 10.0), (6.0, 0.0), (6.0, -2.0)],
)
def test_fair_price_invalide(metric, multiple):
    assert vc.fair_price(metric, multiple) is None


def test_safety_margin():
    # Prix juste au-dessus du cours -> marge positive.
    assert vc.safety_margin(100.0, 80.0) == pytest.approx(20.0)
    # Cours au-dessus du prix juste -> marge négative.
    assert vc.safety_margin(100.0, 120.0) == pytest.approx(-20.0)


@pytest.mark.parametrize("fair,price", [(None, 80.0), (100.0, None), (0.0, 80.0)])
def test_safety_margin_invalide(fair, price):
    assert vc.safety_margin(fair, price) is None


def test_estimated_return_reproduit_la_matrice_baggr():
    """Rétro-ingénierie validée : m0=11,359, D=8,2 % (fit 0,01 pt sur 45 cellules)."""
    # Cellule (croissance 5,5 % / multiple 8,8) -> 8,45 % chez Baggr.
    r = vc.estimated_return(1.0, 1.0, 5.5, 8.8 / 11.359, 5, 8.2)
    assert r == pytest.approx(8.45, abs=0.02)
    # Cellule (2,0 % / 1,8) -> −21,26 %.
    r2 = vc.estimated_return(1.0, 1.0, 2.0, 1.8 / 11.359, 5, 8.2)
    assert r2 == pytest.approx(-21.26, abs=0.03)
    # Cellule (9,0 % / 15,8) -> 24,63 %.
    r3 = vc.estimated_return(1.0, 1.0, 9.0, 15.8 / 11.359, 5, 8.2)
    assert r3 == pytest.approx(24.63, abs=0.02)


def test_dividende_additif_et_exclu():
    base = vc.estimated_return(5.0, 100.0, 5.0, 20.0, 5, 0.0)
    with_div = vc.estimated_return(5.0, 100.0, 5.0, 20.0, 5, 8.0)
    assert with_div - base == pytest.approx(8.0)


@pytest.mark.parametrize(
    "metric,price,growth,multiple,horizon",
    [
        (5.0, 100.0, 5.0, 20.0, 0),  # horizon nul
        (5.0, 0.0, 5.0, 20.0, 5),  # cours nul
        (0.0, 100.0, 5.0, 20.0, 5),  # métrique nulle
        (5.0, 100.0, 5.0, -1.0, 5),  # multiple négatif
        (None, 100.0, 5.0, 20.0, 5),  # métrique absente
    ],
)
def test_estimated_return_invalide(metric, price, growth, multiple, horizon):
    assert vc.estimated_return(metric, price, growth, multiple, horizon) is None


def test_projected_value():
    # 5 × 1,05^5 × 20 = 127,63
    assert vc.projected_value(5.0, 5.0, 20.0, 5) == pytest.approx(127.628, abs=0.01)
    assert vc.projected_value(None, 5.0, 20.0, 5) is None


def test_target_entry_price_est_inverse_de_estimated_return():
    # Le prix d'entrée doit produire EXACTEMENT le rendement cible quand on le
    # repasse dans estimated_return (aller-retour).
    metric, growth, multiple, horizon, target, div = 5.0, 5.0, 20.0, 5, 12.0, 4.0
    entry = vc.target_entry_price(metric, growth, multiple, horizon, target, div)
    assert entry is not None
    back = vc.estimated_return(metric, entry, growth, multiple, horizon, div)
    assert back == pytest.approx(target, abs=1e-9)


def test_estimated_return_from_fair_est_inverse_de_target_entry_price():
    # Le prix juste enregistré encode la valeur projetée : au cours actuel, le
    # rendement dérivé doit être celui de la calculatrice (#26).
    metric, growth, multiple, horizon, target, div = 5.0, 5.0, 20.0, 5, 12.0, 4.0
    fair = vc.target_entry_price(metric, growth, multiple, horizon, target, div)
    assert fair is not None
    for price in (fair * 0.8, fair, fair * 1.2):
        expected = vc.estimated_return(metric, price, growth, multiple, horizon, div)
        assert vc.estimated_return_from_fair(fair, price, target, horizon, div) == pytest.approx(
            expected, abs=1e-9
        )
    # Au prix juste, le rendement est exactement la cible.
    assert vc.estimated_return_from_fair(fair, fair, target, horizon, div) == pytest.approx(target)


@pytest.mark.parametrize(
    "fair,price,target,horizon,div",
    [
        (None, 100.0, 12.0, 5, 0.0),
        (0.0, 100.0, 12.0, 5, 0.0),
        (100.0, None, 12.0, 5, 0.0),
        (100.0, 0.0, 12.0, 5, 0.0),
        (100.0, 100.0, 12.0, 0, 0.0),
        (100.0, 100.0, 100.0, 5, 200.0),
    ],
)
def test_estimated_return_from_fair_invalide(fair, price, target, horizon, div):
    assert vc.estimated_return_from_fair(fair, price, target, horizon, div) is None


def test_target_entry_price_nominal():
    # Valeur projetée = 5 × 1,02^5 × 1,3 = 7,228 ; cible 12 %, div 8,9 % →
    # net = 3,1 % → 7,228 / 1,031^5 = 6,20.
    entry = vc.target_entry_price(94.2788, 2.0, 1.3, 5, 12.0, 8.9)
    assert entry == pytest.approx(116.16, abs=0.05)


@pytest.mark.parametrize(
    "metric,growth,multiple,horizon,target,div,bridge",
    [
        (None, 5.0, 20.0, 5, 12.0, 0.0, None),  # métrique absente
        (5.0, 5.0, None, 5, 12.0, 0.0, None),  # multiple absent
        (0.0, 5.0, 20.0, 5, 12.0, 0.0, None),  # métrique nulle
        (5.0, 5.0, -1.0, 5, 12.0, 0.0, None),  # multiple négatif
        (5.0, 5.0, 20.0, 0, 12.0, 0.0, None),  # horizon nul
        (5.0, 5.0, 20.0, 5, -50.0, 60.0, None),  # cible nette ≤ −100 %
    ],
)
def test_target_entry_price_invalide(metric, growth, multiple, horizon, target, div, bridge):
    assert vc.target_entry_price(metric, growth, multiple, horizon, target, div, bridge) is None


def test_target_entry_price_avec_bridge():
    # Multiple d'entreprise : la dette nette/action est retranchée de la valeur.
    entry_sans = vc.target_entry_price(10.0, 4.0, 12.0, 5, 12.0, 0.0, None)
    entry_avec = vc.target_entry_price(10.0, 4.0, 12.0, 5, 12.0, 0.0, 40.0)
    assert entry_avec is not None and entry_sans is not None
    # Le bridge réduit la valeur projetée -> prix d'entrée plus bas.
    assert entry_avec < entry_sans


def test_matrix_grid_centree():
    growths, multiples = vc.matrix_grid(5.0, 10.0, 15, 15, 0.5, 1.0)
    assert len(growths) == 15
    assert len(multiples) == 15
    assert growths[7] == pytest.approx(5.0)  # centre = index n//2
    assert multiples[7] == pytest.approx(10.0)
    assert growths[0] == pytest.approx(5.0 - 7 * 0.5)


def test_return_matrix_coherente():
    growths, multiples = vc.matrix_grid(5.0, 10.0, 3, 3, 1.0, 1.0)
    matrix = vc.return_matrix(5.0, 100.0, growths, multiples, 5, 0.0)
    assert len(matrix) == 3
    assert all(len(row) == 3 for row in matrix)
    # Le rendement croît avec le multiple (même croissance).
    assert matrix[1][0] < matrix[1][1] < matrix[1][2]


def test_return_matrix_avec_base_invalide():
    growths, multiples = vc.matrix_grid(5.0, 10.0, 2, 2, 1.0, 1.0)
    matrix = vc.return_matrix(None, 100.0, growths, multiples, 5, 0.0)
    assert all(cell is None for row in matrix for cell in row)


def test_color_bucket_ancre_sur_la_cible():
    ratios = (0.5, 1.0)
    assert vc.color_bucket(-1.0, 12.0, ratios) == 0  # rouge (négatif)
    assert vc.color_bucket(3.0, 12.0, ratios) == 1  # brun (< 6)
    assert vc.color_bucket(9.0, 12.0, ratios) == 2  # jaune (< 12)
    assert vc.color_bucket(12.0, 12.0, ratios) == 3  # vert (>= cible)
    assert vc.color_bucket(20.0, 12.0, ratios) == 3


def test_color_bucket_cible_nulle_ou_valeur_absente():
    assert vc.color_bucket(5.0, 0.0, (0.5, 1.0)) is None
    assert vc.color_bucket(None, 12.0, (0.5, 1.0)) is None


def test_median_multiple():
    row = pd.Series({2024: 12.0, 2023: 10.0, 2022: 8.0, 2021: None, 2020: 6.0})
    # Médiane sur les 3 dernières années disponibles -> median(12, 10, 8) = 10.
    assert vc.median_multiple(row, 3) == pytest.approx(10.0)
    assert vc.median_multiple(pd.Series(dtype=float), 5) is None
    assert vc.median_multiple(None, 5) is None


def test_step_series_forward_fill():
    dates = pd.DatetimeIndex(["2019-06-01", "2021-06-01", "2023-06-01"])
    s = vc.step_series(dates, {2020: 10.0, 2022: 12.0})
    # Avant le premier exercice -> None ; ensuite, report du dernier connu.
    assert s.iloc[0] is None or pd.isna(s.iloc[0])
    assert s.iloc[1] == pytest.approx(10.0)
    assert s.iloc[2] == pytest.approx(12.0)


def test_price_over_step():
    dates = pd.DatetimeIndex(["2021-06-01", "2022-06-01"])
    prices = pd.Series([100.0, 120.0], index=dates)
    s = vc.price_over_step(dates, prices, {2020: 10.0})
    assert s.iloc[0] == pytest.approx(10.0)
    assert s.iloc[1] == pytest.approx(12.0)


def test_price_over_step_denominateur_invalide():
    dates = pd.DatetimeIndex(["2021-06-01"])
    prices = pd.Series([100.0], index=dates)
    # Aucun exercice connu -> None (jamais d'infini).
    s = vc.price_over_step(dates, prices, {})
    assert pd.isna(s.iloc[0])


def test_enterprise_multiple_series():
    dates = pd.DatetimeIndex(["2021-06-01"])
    prices = pd.Series([100.0], index=dates)
    s = vc.enterprise_multiple_series(dates, prices, {2020: 10.0}, {2020: 50.0}, {2020: 200.0})
    # (100 × 10 + 200) / 50 = 24
    assert s.iloc[0] == pytest.approx(24.0)
    # EBITDA absent -> None.
    s2 = vc.enterprise_multiple_series(dates, prices, {2020: 10.0}, {}, {2020: 200.0})
    assert pd.isna(s2.iloc[0])


def test_module_pur_sans_io():
    """Invariant de couche : `engine/` n'importe ni `data/` ni `services/`."""
    import inspect

    import obole.engine.valuation_calc as mod

    source = inspect.getsource(mod)
    assert "import obole.data" not in source
    assert "import obole.services" not in source
    assert "from obole.data" not in source
    assert "from obole.services" not in source
