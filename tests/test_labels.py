"""Tests des labels calibrés — chaque cas vient d'une fiche Obole réelle (PRD §5)."""

from __future__ import annotations

import pytest

from obole.engine import labels
from obole.engine.quality import quality_score
from obole.models import CompanyKind


@pytest.mark.parametrize(
    "z, expected",
    [
        (-3.81, "Décotée"),  # Pernod
        (-0.96, "Légèrement sous-cotée"),  # Renault
        (-0.17, "Légèrement sous-cotée"),  # Danone
        (1.02, "Surcotée"),  # BNP
        (1.38, "Surcotée"),  # STMicro
        (1.79, "Surcotée"),  # Total
    ],
)
def test_distance_sigma_labels(z, expected):
    assert labels.label_distance_sigma(z).label == expected


@pytest.mark.parametrize(
    "size, expected",
    [
        (15.8, "Faible"),
        (18.7, "Faible"),
        (30.1, "Moyen"),
        (41.2, "Plutôt élevée"),
        (51.0, "Plutôt élevée"),
        (80.6, "Elevée"),
    ],
)
def test_ecart_type_labels(size, expected):
    assert labels.label_ecart_type(size).label == expected


@pytest.mark.parametrize(
    "perf, expected",
    [(1.2, "Médiocre"), (3.0, "Médiocre"), (5.7, "Moyen"), (8.9, "Moyen")],
)
def test_perf_labels(perf, expected):
    assert labels.label_perf(perf).label == expected


@pytest.mark.parametrize(
    "pot, expected",
    [
        (-7.5, "Mauvais"),
        (-0.5, "Mauvais"),
        (0.4, "Médiocre"),
        (6.0, "Moyen"),
        (10.3, "Bien"),
        (20.0, "Excellent"),
        (32.6, "Excellent"),
    ],
)
def test_potential_labels(pot, expected):
    assert labels.label_potential(pot).label == expected


def test_trend_labels():
    assert labels.label_trend(True).label == "Haussière"
    assert labels.label_trend(False).label == "Baissière"
    assert labels.label_trend(None).label is None


def test_none_propagates():
    assert labels.label_distance_sigma(None).value is None
    assert labels.label_potential(None).label is None


@pytest.mark.parametrize(
    "beta, expected",
    [
        (0.1, "Très défensif"),
        (0.5, "Défensif"),
        (1.0, "Neutre"),
        (1.5, "Offensif"),
        (3.0, "Très offensif"),
        (-0.8, "Inversés"),
    ],
)
def test_beta_labels(beta, expected):
    assert labels.label_beta(beta).label == expected


def test_beta_is_neutral_and_handles_none():
    # β n'a pas de polarité bon/mauvais : good doit rester None.
    assert labels.label_beta(1.0).good is None
    assert labels.label_beta(-2.0).good is None
    sv = labels.label_beta(None)
    assert sv.value is None and sv.label is None


@pytest.mark.parametrize(
    "rho, expected",
    [
        (0.1, "Très peu corrélés"),
        (0.3, "Peu corrélés"),
        (0.5, "Moyennement corrélés"),
        (0.7, "Fortement corrélés"),
        (0.95, "Très fortement corrélés"),
        (-0.9, "Très fortement corrélés (inverse)"),
        (-0.1, "Très peu corrélés (inverse)"),
    ],
)
def test_correlation_labels(rho, expected):
    # Classement sur |ρ| ; suffixe « (inverse) » si négatif.
    assert labels.label_correlation(rho).label == expected


def test_correlation_is_neutral_and_handles_none():
    assert labels.label_correlation(0.8).good is None
    assert labels.label_correlation(-0.8).good is None
    sv = labels.label_correlation(None)
    assert sv.value is None and sv.label is None


@pytest.mark.parametrize(
    "roe_mean, roe_last, declines, eq, expected_label",
    [
        (-3.7, -52.6, 4, 17, "Médiocre"),  # Renault
        (9.8, 10.7, 4, 41, "Bon"),  # Pernod
        (11.2, 10.8, 6, 38, "Bon"),  # Danone
        (13.8, 1.0, 3, 72, "Bon"),  # STMicro (pénalisé par roe_last)
    ],
)
def test_quality_score_ranking(roe_mean, roe_last, declines, eq, expected_label):
    score = quality_score(roe_mean, roe_last, declines, eq, CompanyKind.INDUSTRIAL)
    assert labels.label_quality(score).label == expected_label


def test_quality_renault_below_pernod():
    renault = quality_score(-3.7, -52.6, 4, 17)
    pernod = quality_score(9.8, 10.7, 4, 41)
    assert renault < pernod
