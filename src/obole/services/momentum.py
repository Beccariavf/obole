"""Payload « momentum » (Clara Vallis) : séries de satisfaction prêtes à tracer.

Le calcul vit dans `engine/clara_vallis` (pur) ; ce module l'orchestre, l'aligne
sur la grille du graphe (`chart.dates`) et le cache par référence — un ticker,
ou `INDEX:<id>` pour un indice personnalisé.

Les séries sont calculées en PLEINE résolution puis réindexées sur la grille
décimée : un walk-forward calculé sur la série déjà décimée ne couvrirait pas
250 séances réelles (même piège que les moyennes mobiles, cf. `chart_payload`).

Le backtest de fiabilité (#31) suit la même règle : la satisfaction est calculée
sur la série PLEINE, puis la fenêtre demandée est tranchée et passée au moteur.
Un backtest sur la grille décimée raterait des croisements et fausserait les
trades et le drawdown.
"""

from __future__ import annotations

import datetime as _dt

import pandas as pd

from obole import config
from obole.data import cache, yahoo
from obole.engine import clara_vallis as cv
from obole.engine import momentum_backtest as backtest_engine
from obole.services import indices as indices_service
from obole.services.values import to_values

_KIND_PREFIX = "momentum"


def _cache_kind() -> str:
    """La fenêtre fait partie de la clé : la changer invalide le payload."""
    return f"{_KIND_PREFIX}:{config.MOMENTUM_WINDOW}"


def momentum_payload(
    ref: str,
    raw: pd.Series,
    adjusted: pd.Series | None,
    grid: pd.DatetimeIndex,
) -> dict:
    """Bloc `momentum` d'une fiche, aligné sur la grille `grid` du graphe.

    `ref` sert de clé de cache (`RI.PA`, `INDEX:7`). Le walk-forward est calculé
    une fois par jour et par référence ; `cache.invalidate(ref)` le purge avec
    les prix.
    """
    cached = cache.get(ref, _cache_kind(), config.TTL_PRICES)
    if cached is not None:
        return cached

    window = config.MOMENTUM_WINDOW
    raw_series = cv.satisfaction_series(raw, window)
    adj_series = cv.satisfaction_series(adjusted, window) if adjusted is not None else None

    score_raw = cv.satisfaction_score(raw, window)
    tail = raw_series.index[-window:]
    payload = {
        "score_raw": score_raw.value,
        "score_adj": (
            cv.satisfaction_score(adjusted, window).value if adjusted is not None else None
        ),
        "n_used": score_raw.n_used,
        "short_history": score_raw.short_history,
        "raw": to_values(raw_series.reindex(grid)),
        "adj": to_values(adj_series.reindex(grid)) if adj_series is not None else None,
        "year": {
            "dates": [d.strftime("%Y-%m-%d") for d in tail],
            "raw": to_values(raw_series.reindex(tail)),
            "adj": to_values(adj_series.reindex(tail)) if adj_series is not None else None,
        },
    }
    cache.put(ref, _cache_kind(), payload)
    return payload


def _full_series(kind: str, ref: str | int, series: str) -> pd.Series:
    """Série pleine résolution d'une référence, dans la base choisie.

    `stock` : brut (Close) ou ajusté (Adj Close) ; `basket` : la série chaînée
    de l'indice est déjà en total-return, `raw` et `adj` désignent la même.
    """
    if kind == "stock":
        prices = yahoo.fetch_prices(str(ref))
        full = prices.raw if series == "raw" else prices.adjusted
    elif kind == "basket":
        _, full = indices_service.analyze_index(int(ref))
    else:
        raise ValueError(f"Référence inconnue : {kind}")
    clean = full.dropna()
    clean = clean[clean > 0]
    # yfinance renvoie un index tz-aware (Europe/Paris) : les bornes ISO de la
    # requête sont naïves. On normalise ici, sinon pandas refuse la comparaison
    # (les fixtures de test, naïves, ne le verraient jamais).
    if isinstance(clean.index, pd.DatetimeIndex) and clean.index.tz is not None:
        clean = clean.copy()
        clean.index = clean.index.tz_localize(None)
    return clean


_MEASURES = (
    "cagr_pct",
    "volatility_pct",
    "sharpe",
    "sortino",
    "max_drawdown_pct",
    "calmar",
    "invested_pct",
    "trades",
)


def _measures(block: dict) -> dict:
    """Contrat public d'une colonne : les huit mesures, rien de plus.

    Le moteur garde `equity` et `positions` pour ses tests (frais, hystérésis,
    absence de fuite) ; la route ne les sérialise jamais (~300 Ko sur MAX).
    """
    return {key: block[key] for key in _MEASURES}


def _public_result(result: dict) -> dict:
    """Réduit le résultat du moteur au contrat `{buy_hold, strategy, window}`."""
    return {
        "buy_hold": _measures(result["buy_hold"]),
        "strategy": _measures(result["strategy"]),
        "window": result["window"],
    }


def momentum_backtest(
    kind: str,
    ref: str | int,
    start: str,
    end: str,
    series: str = "raw",
) -> dict:
    """Backtest de fiabilité sur la fenêtre `[start, end]` (dates ISO).

    `kind` vaut `stock` (ticker) ou `basket` (identifiant d'indice). Le score de
    satisfaction est calculé sur la série PLEINE, puis la fenêtre est tranchée :
    un backtest sur la grille décimée du graphe raterait des croisements.
    Lève `ValueError` pour une date illisible, une fenêtre inversée ou une
    fenêtre de moins de deux séances ; `TickerNotFound` / `IndexNotFound`
    remontent telles quelles pour que les routes les traduisent en 404.
    """
    if series not in {"raw", "adj"}:
        raise ValueError("series doit valoir 'raw' ou 'adj'")
    try:
        start_day = _dt.date.fromisoformat(start)
        end_day = _dt.date.fromisoformat(end)
    except (TypeError, ValueError):
        raise ValueError("dates ISO requises (AAAA-MM-JJ)") from None
    if start_day >= end_day:
        raise ValueError("start doit précéder end")

    full = _full_series(kind, ref, series)
    window = full.loc[pd.Timestamp(start_day) : pd.Timestamp(end_day)]
    if len(window) < 2:
        raise ValueError("Fenêtre trop courte : moins de deux séances")

    # Coût à froid mesuré à ~35 ms sur 30 ans (satisfaction + backtest), donc
    # sous le seuil de 100 ms du plan : pas de cache de la série pleine.
    scores = cv.satisfaction_series(full, config.MOMENTUM_WINDOW)
    result = backtest_engine.backtest(
        window,
        scores.reindex(window.index),
        config.MOMENTUM_SATISFACTION_LOW,
        config.MOMENTUM_SATISFACTION_HIGH,
        config.MOMENTUM_FEE_PCT,
        config.MOMENTUM_RISK_FREE_PCT,
    )
    return _public_result(result)
