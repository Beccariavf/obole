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
trades et le drawdown. Depuis #32, il expose le marché pendant les séances in et
out (plus le rendement réel de la stratégie, en pied).

La lecture du score obéit à la même règle : le percentile et les rendements
conditionnels portent sur l'HISTORIQUE COMPLET du titre, pas sur la plage
affichée par le graphe. Ils sont donc calculés ici, une fois par jour et par
référence, dans le payload déjà mis en cache — le front ne recalcule rien.
"""

from __future__ import annotations

import datetime as _dt

import pandas as pd

from obole import config
from obole.data import cache, yahoo
from obole.engine import clara_vallis as cv
from obole.engine import momentum_backtest as backtest_engine
from obole.engine import momentum_stats as stats
from obole.services import indices as indices_service
from obole.services.values import to_values

_KIND_PREFIX = "momentum"


def _cache_kind() -> str:
    """La fenêtre et la forme du payload font partie de la clé.

    Le suffixe `lecture` date l'ajout du bloc de lecture — percentile ET
    rendement conditionnel, livrés d'un seul tenant : un payload calculé avant
    ce déploiement ne porte ni l'un ni l'autre, et le servir laisserait la fiche
    muette jusqu'à l'expiration du TTL (24 h). Il change quand la FORME du bloc
    change (un champ ajouté ou retiré), pas à chaque retouche de son calcul.
    """
    return f"{_KIND_PREFIX}:{config.MOMENTUM_WINDOW}:lecture"


def _history_start(scores: pd.Series) -> str | None:
    """Première date où le score est calculable, en ISO ; `None` si aucune."""
    known = scores.dropna()
    if known.empty:
        return None
    return known.index[0].strftime("%Y-%m-%d")


def _conditional_block(
    prices: pd.Series,
    scores: pd.Series,
    low: float,
    high: float,
    horizon: int,
) -> dict:
    """Rendement conditionnel d'une série, prêt pour le front.

    L'horizon voyage AVEC les chiffres : le front écrit « 252 séances » sans
    recopier la constante, et la note reste vraie si le réglage change. La
    prudence est tranchée ICI : `thin` dit qu'une zone compte trop peu
    d'épisodes indépendants pour être lue, exactement comme `short_history` le
    fait pour le score — le front ne décide d'aucun seuil.
    """
    block = stats.conditional_forward_returns(prices, scores, low, high, horizon)
    block["horizon"] = horizon
    min_episodes = config.MOMENTUM_CONDITIONAL_MIN_EPISODES
    for zone in (block["zones"]["bas"], block["zones"]["neutre"], block["zones"]["haut"]):
        if zone is not None:
            zone["thin"] = zone["episodes"] < min_episodes
    baseline = block["baseline"]
    if baseline is not None:
        baseline["thin"] = baseline["episodes"] < min_episodes
    return block


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
    score_adj = cv.satisfaction_score(adjusted, window) if adjusted is not None else None
    min_points = config.MOMENTUM_PERCENTILE_MIN_POINTS
    low = config.MOMENTUM_SATISFACTION_LOW
    high = config.MOMENTUM_SATISFACTION_HIGH
    horizon = config.MOMENTUM_FORWARD_SESSIONS
    history_start = _history_start(raw_series)
    # L'ajusté peut commencer ailleurs (ou manquer) : la ligne de rang affiche
    # la date de la série qu'elle lit, jamais celle de l'autre.
    history_start_adj = _history_start(adj_series) if adj_series is not None else None
    tail = raw_series.index[-window:]
    payload = {
        "score_raw": score_raw.value,
        "score_adj": score_adj.value if score_adj is not None else None,
        # Rang du score dans TOUT l'historique du titre, pas dans la plage
        # affichée par le graphe. Un indice n'a pas de série ajustée : son rang
        # ajusté n'existe pas (le front n'affiche qu'une série à la fois).
        "percentile_raw": stats.score_percentile(raw_series, score_raw.value, min_points),
        "percentile_adj": (
            stats.score_percentile(adj_series, score_adj.value, min_points)
            if adj_series is not None and score_adj is not None
            else None
        ),
        # Première date où le score est calculable : la ligne de rang dit
        # depuis quand le titre a un historique comparable, série par série.
        "history_start": history_start,
        "history_start_adj": history_start_adj,
        # Ce qui a suivi chaque zone de score, sur tout l'historique du titre.
        # Même règle que le rang : un indice n'a pas de série ajustée, donc pas
        # de rendement conditionnel ajusté.
        "conditional_raw": _conditional_block(raw, raw_series, low, high, horizon),
        "conditional_adj": (
            _conditional_block(adjusted, adj_series, low, high, horizon)
            if adjusted is not None and adj_series is not None
            else None
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
    "sessions_pct",
)


def _measures(block: dict) -> dict:
    """Contrat public d'une colonne : les sept mesures, rien de plus.

    Le moteur garde `equity` (et, pour la stratégie, ses positions) à
    l'intérieur : la route ne les sérialise jamais (~300 Ko sur MAX).
    """
    return {key: block[key] for key in _MEASURES}


def _public_result(result: dict) -> dict:
    """Réduit le résultat du moteur au contrat public du backtest.

    `{buy_hold, in, out, window, trades, strategy_cagr_pct}` : le marché pendant
    les séances in et out, plus le rendement réel de la stratégie (cash compris)
    livré une seule fois, hors des colonnes — il ne doit pas redevenir une
    comparaison. Ni `strategy`, ni `equity`, ni `positions` ne sortent d'ici.
    """
    return {
        "buy_hold": _measures(result["buy_hold"]),
        "in": _measures(result["in"]),
        "out": _measures(result["out"]),
        "window": result["window"],
        "trades": result["trades"],
        "strategy_cagr_pct": result["strategy_cagr_pct"],
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
