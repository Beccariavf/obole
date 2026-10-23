"""Mapping valeur numérique -> label calibré + polarité couleur.

Seuils définis dans config.py (calibrés sur 6 fiches Obole réelles, PRD §5).
Fonctions pures.
"""

from __future__ import annotations

from collections.abc import Sequence

from obole import config
from obole.models import ScoredValue


def _classify(value: float, thresholds: Sequence[tuple[float | None, str]]) -> str:
    """Renvoie le label de la première borne sup (exclue) non franchie.

    thresholds = [(borne_sup, label), ..., (None, label_final)].
    """
    for upper, label in thresholds:
        if upper is None or value < upper:
            return label
    return thresholds[-1][1]  # filet de sécurité


def _good(kind: str, value: float) -> bool:
    """Polarité couleur d'un label prix, depuis `config.LABEL_POLARITY`.

    sens "lt" : bon si valeur < seuil ; sens "ge" : bon si valeur >= seuil.
    """
    sens, seuil = config.LABEL_POLARITY[kind]
    return value < seuil if sens == "lt" else value >= seuil


def label_distance_sigma(z: float | None) -> ScoredValue:
    if z is None:
        return ScoredValue(None, None, None)
    label = _classify(z, config.DISTANCE_SIGMA_LABELS)
    # bleu=bien : un cours décoté est une opportunité (favorable).
    good = _good("distance", z)
    return ScoredValue(round(z, 2), label, good)


def label_ecart_type(size_pct: float | None) -> ScoredValue:
    if size_pct is None:
        return ScoredValue(None, None, None)
    label = _classify(size_pct, config.ECART_TYPE_LABELS)
    # volatilité faible = favorable (bleu) ; élevée = défavorable (rouge).
    good = _good("ecart", size_pct)
    return ScoredValue(round(size_pct, 1), label, good)


def label_perf(perf_pct: float | None) -> ScoredValue:
    if perf_pct is None:
        return ScoredValue(None, None, None)
    label = _classify(perf_pct, config.PERF_LABELS)
    good = _good("perf", perf_pct)
    return ScoredValue(round(perf_pct, 1), label, good)


def label_potential(pot_pct: float | None) -> ScoredValue:
    if pot_pct is None:
        return ScoredValue(None, None, None)
    label = _classify(pot_pct, config.POTENTIAL_LABELS)
    good = _good("potential", pot_pct)
    return ScoredValue(round(pot_pct, 1), label, good)


def label_trend(is_bullish: bool | None) -> ScoredValue:
    if is_bullish is None:
        return ScoredValue(None, None, None)
    return ScoredValue(
        value=None,
        label="Haussière" if is_bullish else "Baissière",
        good=is_bullish,
    )


def label_quality(score: float | None) -> ScoredValue:
    if score is None:
        return ScoredValue(None, None, None)
    label = _classify(score, config.QUALITY_LABELS)
    good = _good("quality", score)
    return ScoredValue(round(score), label, good)


def label_beta(beta: float | None) -> ScoredValue:
    """Bêta A~B (amplitude) : label NEUTRE (good=None). β<0 -> actifs inversés."""
    if beta is None:
        return ScoredValue(None, None, None)
    label = "Inversés" if beta < 0 else _classify(beta, config.BETA_LABELS)
    return ScoredValue(round(beta, 2), label, None)


def label_correlation(rho: float | None) -> ScoredValue:
    """Corrélation A~B (solidité du lien) : label NEUTRE (good=None).

    Classe sur |ρ| (5 niveaux) ; ρ<0 -> suffixe « (inverse) » (le lien est aussi
    fort, mais en sens opposé).
    """
    if rho is None:
        return ScoredValue(None, None, None)
    label = _classify(abs(rho), config.CORR_LABELS)
    if rho < 0:
        label += " (inverse)"
    return ScoredValue(round(rho, 2), label, None)
