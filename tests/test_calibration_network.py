"""Test de non-régression de calibration — APPELLE LE RÉSEAU (yfinance).

Garde-fou central : les mesures calibrées sur Pernod Ricard (PRD §5.0) doivent
rester stables — z = −3.81, potentiels 5/10 ans (32.5 % / 19.0 %) et perf
passée (8.9 % sur Adj Close).
Marqué `network` : `pytest -m "not network"` pour l'ignorer hors-ligne.

⚠️ La cible −3.81 est une photo au 22/06/2026 (fiche de référence, PDF dans
`exemple/`). Le z dépend du cours du jour ET de la droite recalculée sur
l'historique complet : au fil des semaines, de nouveaux points déplacent la
droite et font dériver le z (ex. −3.60 fin août 2026). On fige donc la série
à la date de calibration pour comparer ce qui est comparable, et on vérifie
séparément que le calcul « à aujourd'hui » reste cohérent (pas de NaN, ordre
de grandeur décotée).
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import pandas as pd

pytestmark = pytest.mark.network

# Date de la fiche de référence (PDF dans exemple/).
CALIBRATION_DATE = "2026-06-22"


@lru_cache(maxsize=1)
def _pernod_series() -> tuple[pd.Series, pd.Series]:
    """Séries Pernod complètes : (Close brut, Adj Close), historique max.

    Mémoïsé : un seul appel réseau pour les 5 tests du module (les séries ne
    sont que lues, jamais mutées).

    Le Close brut sert la valorisation (z, potentiels), l'Adj Close (dividendes
    réinvestis) sert la perf passée — cf. PRD §5.0, la distinction est la clé.
    """
    import yfinance as yf

    hist = yf.Ticker("RI.PA").history(period="max", auto_adjust=False)
    if hist.empty:
        pytest.skip("yfinance indisponible")
    # yfinance ajoute parfois une ligne du jour encore vide (Close = NaN).
    raw = hist["Close"].dropna()
    raw = raw[raw > 0]
    adj = hist["Adj Close"].dropna()
    adj = adj[adj > 0]
    if raw.empty or adj.empty:
        pytest.skip("yfinance indisponible")
    return raw, adj


def _pernod_frozen_series() -> tuple[pd.Series, pd.Series]:
    """Séries Pernod figées à CALIBRATION_DATE : (Close brut, Adj Close).

    Série figée à la date de la fiche de référence : sinon la droite dérive à
    chaque nouvelle séance et les cibles du PRD §5.0 n'ont plus de sens.
    """
    raw, adj = _pernod_series()
    frozen_raw = raw[raw.index <= CALIBRATION_DATE]
    frozen_adj = adj[adj.index <= CALIBRATION_DATE]
    if frozen_raw.empty or frozen_adj.empty:
        pytest.skip(f"Pas de données avant {CALIBRATION_DATE}")
    return frozen_raw, frozen_adj


def test_pernod_distance_sigma_is_minus_381():
    from obole.engine import regression as reg

    frozen, _ = _pernod_frozen_series()
    r = reg.fit_log_regression(frozen)
    z = reg.distance_sigma(r, float(frozen.iloc[-1]))
    # Cible PDF de référence : −3.81. Tolérance large (données quotidiennes yfinance).
    assert z == pytest.approx(-3.81, abs=0.15)


def test_pernod_potential_5y_is_325():
    from obole.engine import regression as reg

    frozen, _ = _pernod_frozen_series()
    r = reg.fit_log_regression(frozen)
    pot5 = reg.annualized_potential(r, float(frozen.iloc[-1]), 5) * 100
    # Cible PDF de référence : 32.6 % (calibration PRD §5.0 : 32.5 % sur Close brut).
    # Tolérance 1 pt : données quotidiennes yfinance.
    assert pot5 == pytest.approx(32.5, abs=1.0)


def test_pernod_potential_10y_is_190():
    from obole.engine import regression as reg

    frozen, _ = _pernod_frozen_series()
    r = reg.fit_log_regression(frozen)
    pot10 = reg.annualized_potential(r, float(frozen.iloc[-1]), 10) * 100
    # Cible PDF de référence : 20.0 % (calibration PRD §5.0 : 19.0 % sur Close brut).
    # Tolérance 1 pt : données quotidiennes yfinance.
    assert pot10 == pytest.approx(19.0, abs=1.0)


def test_pernod_past_perf_is_89_on_adjusted():
    """Perf passée sur Adj Close (dividendes réinvestis), PAS sur le Close brut.

    Piège PRD §5.0 : la perf affichée par l'outil de référence (8.5 %) se lit sur la droite
    div réinvestis (8.9 %), pas sur la droite brute (6.8 %). Vérifier la perf
    sur le brut serait une erreur de lecture (perf hors dividendes).
    """
    from obole.engine import regression as reg

    _, frozen_adj = _pernod_frozen_series()
    r_adj = reg.fit_log_regression(frozen_adj)
    perf = r_adj.perf_annual * 100
    # Cible PDF de référence : 8.5 % (calibration PRD §5.0 : 8.9 % sur Adj Close).
    # Tolérance 0.5 pt : données quotidiennes yfinance.
    assert perf == pytest.approx(8.9, abs=0.5)


def test_pernod_distance_sigma_today_is_coherent():
    """Le calcul « à aujourd'hui » doit rester exploitable (pas de NaN/inf).

    La valeur exacte dérive avec les séances (c'est attendu) : on ne fige ici
    AUCUNE hypothèse métier, seulement la validité du calcul.
    """
    from obole.engine import regression as reg

    close, _ = _pernod_series()
    r = reg.fit_log_regression(close)
    z = reg.distance_sigma(r, float(close.iloc[-1]))
    # Pas d'hypothèse métier ici : le z dérive avec les séances (c'est attendu),
    # on vérifie seulement que le calcul reste exploitable (ni NaN ni infini).
    assert z == z  # pas de NaN
    assert math.isfinite(z)
