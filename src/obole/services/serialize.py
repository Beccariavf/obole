"""Sérialisation des analyses (`StockAnalysis`, ratio, panier…) -> dict JSON.

Module de **présentation partagé** : il transforme les objets métier en payload JSON
consommé par le front via l'API HTTP **et** par les outils MCP (`services/` est le
point d'entrée commun, cf. `web → api → services → engine → data`). Aucune logique
métier ici : pas de formule, pas de seuil, pas d'appel réseau.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING

import pandas as pd

from obole import config
from obole.data import cache
from obole.data import events as events_data
from obole.models import (
    BasketAnalysis,
    CompanyKind,
    PriceSeries,
    RatioAnalysis,
    ScoredValue,
    ScreenResult,
    StockAnalysis,
    SummaryCard,
)
from obole.services.momentum import momentum_payload
from obole.services.values import to_values as _vals

if TYPE_CHECKING:
    from obole.models import WatchlistRun
    from obole.services.screener import ScreenRun


def _scored(sv: ScoredValue) -> dict:
    return {"value": sv.value, "label": sv.label, "good": sv.good}


def _profile_payload(ident) -> dict:
    """Profil société (section Thèse & Société) : données société + agenda.

    Séparation volontaire des faits stables (`officers`, `employees`, `address`,
    `summary`) et de l'agenda (dates relatives au temps). Tous les champs
    Optionnels restent présents (valeur None) : le front décide d'omettre la ligne,
    jamais de crash sur un champ vide. Accès défensif (`getattr`) : un objet
    d'identité ancien ou factice ne doit pas faire échouer la fiche.
    """
    officers = getattr(ident, "officers", ()) or ()
    return {
        "officers": [{"name": o.name, "title": o.title, "age": o.age} for o in officers],
        "employees": getattr(ident, "employees", None),
        "address": getattr(ident, "address", None),
        "summary": getattr(ident, "summary", None),
        "next_earnings": getattr(ident, "next_earnings", None),
        "next_earnings_estimated": getattr(ident, "next_earnings_estimated", None),
        "ex_dividend": getattr(ident, "ex_dividend", None),
    }


def _has_thesis(ticker: str) -> bool:
    """Existence d'une thèse pour ce ticker (pastille du rail), sans lire le contenu.

    Lecture best-effort : une base illisible ne doit jamais empêcher l'affichage
    de la fiche (le bandeau de rail est un confort, pas une donnée de la méthode).
    """
    try:
        return cache.get_thesis(ticker) is not None
    except Exception:  # noqa: BLE001 — confort d'affichage, jamais bloquant
        return False


def _summary_card(card: SummaryCard) -> dict:
    """Carte de synthèse -> dict JSON (aucune logique métier, simple sérialisation).

    Une carte MATRICE (`columns` non vide, ex. Croissance) porte ses valeurs par
    ligne dans `cells`/`cell_good` ; une carte « libellé → valeur » classique les
    laisse vides. Les deux formes coexistent dans le même payload.
    """
    return {
        "id": card.id,
        "title": card.title,
        "columns": card.columns,
        "rows": [
            {
                "key": r.key,
                "label": r.label,
                "value": r.value,
                "unit": r.unit,
                "text": r.text,
                "good": r.good,
                "note": r.note,
                "cells": r.cells,
                "cell_good": r.cell_good,
            }
            for r in card.rows
        ],
    }


def _polarity(sens: str, seuil: float | None, value: float | None) -> str | None:
    """Polarité d'une cellule selon `config.SCREEN_COLORS` : "good"/"bad"/None.

    `seuil` None → jamais favorable (valeur de référence absente). La valeur manquante
    (None) est neutre. C'est la SEULE source de vérité des couleurs du tableau (le
    front ne duplique aucun seuil). Un booléen (tendance) est bon uniquement s'il est
    True (haussière) : on ne le compare pas numériquement (False >= 0 serait True,
    ce qui colorerait à tort la tendance baissière).
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return "good" if value else "bad"
    if seuil is None:
        return None
    if sens == "ge":
        return "good" if value >= seuil else "bad"
    if sens == "le":
        return "good" if value <= seuil else "bad"
    if sens == "le_pos":
        return "good" if 0 < value <= seuil else "bad"
    return None


def _moving_average(series: pd.Series, window: int) -> pd.Series:
    """Moyenne mobile simple sur une fenêtre glissante de `window` points quotidiens."""
    return series.rolling(window).mean()


def _downsample(series: pd.Series, max_points: int = 1200) -> pd.Series:
    """Réduit le nombre de points pour un tracé léger (sobriété + perf front).

    Le **dernier point est toujours conservé** : sans lui, le graphe et les
    indicateurs live s'arrêtaient quelques séances avant le dernier cours (le
    marqueur « prix · σ » contredisait l'en-tête, et les KPI live divergeaient
    des valeurs serveur). Le premier point l'est déjà (`iloc[::step]`).
    """
    if len(series) <= max_points:
        return series
    step = len(series) // max_points
    out = series.iloc[::step]
    if len(out) and out.index[-1] != series.index[-1]:
        out = pd.concat([out, series.iloc[[-1]]])
    return out


def chart_payload(prices: PriceSeries, fundamentals=None) -> dict:
    """Séries brutes (cours + cours dividendes réinvestis) alignées sur les dates.

    La régression et les bandes ±σ sont (re)calculées CÔTÉ CLIENT en JS (cela évite
    un aller-retour réseau à chaque déplacement du curseur). Les moyennes mobiles
    (MM11/MM200) sont, elles, PRÉCALCULÉES serveur sur la série pleine résolution,
    PUIS décimées comme le cours : calculées côté client sur la série déjà décimée,
    une fenêtre de 200 points ne couvrait pas 200 jours de bourse réels.

    Les rendements continus (`div_yield`/`sh_yield`, depuis `fundamentals`) suivent
    le MÊME principe : dérivés du cours en pleine résolution, décimés avec le même
    pas -> alignés 1:1 sur `dates`. Le front n'en garde que la stat de fenêtre.
    """
    raw = _downsample(prices.raw)
    adj = prices.adjusted.reindex(raw.index)
    settings = cache.get_settings()
    ma_short_raw = _moving_average(prices.raw, settings["trend_ma_short"])
    ma_long_raw = _moving_average(prices.raw, settings["trend_ma_long"])
    ma_short_adj = _moving_average(prices.adjusted, settings["trend_ma_short"])
    ma_long_adj = _moving_average(prices.adjusted, settings["trend_ma_long"])
    dates = [d.strftime("%Y-%m-%d") for d in raw.index]
    out = {
        "dates": dates,
        "price_raw": _vals(raw),
        "price_adj": _vals(adj),
        "ma_short_raw": _vals(ma_short_raw.reindex(raw.index)),
        "ma_long_raw": _vals(ma_long_raw.reindex(raw.index)),
        "ma_short_adj": _vals(ma_short_adj.reindex(raw.index)),
        "ma_long_adj": _vals(ma_long_adj.reindex(raw.index)),
    }
    # Rendements continus : décimés sur le MÊME index que le cours (alignement).
    if fundamentals is not None:
        for key, series in (
            ("div_yield", fundamentals.dividend_yield),
            ("sh_yield", fundamentals.shareholder_yield),
        ):
            if series is not None and len(series):
                out[key] = _vals(series.reindex(raw.index))
        # Séries CONTINUES de la section Valorisation (multiples, métrique/action) :
        # même patron (pleine résolution -> décimation -> alignement 1:1 sur dates).
        for key, series in (fundamentals.valuation_series or {}).items():
            if series is not None and len(series):
                out[key] = _vals(series.reindex(raw.index))
    return out


def security_chart_payload(prices: PriceSeries) -> dict:
    """Chart ALLÉGÉ pour la modale de détail d'un titre (Performance, #17.4).

    Le graphe de détail ne trace que la performance cumulée du titre (rebased à
    0 %) : seuls `dates` et `price_adj` (dividendes réinvestis) sont nécessaires.
    On évite donc le calcul inutile des moyennes mobiles et des séries brutes de
    `chart_payload` — la grille de dates reste identique (décimation sur l'index
    brut, puis `price_adj` réindexé dessus, donc le même index que
    `benchmark_curve`, alignée sur ces dates).
    """
    raw = _downsample(prices.raw)
    adj = prices.adjusted.reindex(raw.index)
    return {
        "dates": [d.strftime("%Y-%m-%d") for d in raw.index],
        "price_adj": _vals(adj),
    }


def ratio_chart_payload(series: pd.Series, sa: pd.Series, sb: pd.Series) -> dict:
    """Série d'un ratio pour le tracé. Même format que chart_payload (raw=adj=ratio).

    Le front réutilise drawChart tel quel : il lit price_raw/price_adj — on pointe
    les deux sur la série du ratio (pas de dividendes à distinguer ici).

    `series_a`/`series_b` = A et B alignés, réindexés sur le MÊME index que le
    ratio downsamplé : le front calcule le β (rendements de A vs B) en live sur
    la fenêtre du slider. Les trois séries partagent donc les mêmes dates.
    """
    s = _downsample(series)
    settings = cache.get_settings()
    ma_short = _moving_average(series, settings["trend_ma_short"])
    ma_long = _moving_average(series, settings["trend_ma_long"])
    dates = [d.strftime("%Y-%m-%d") for d in s.index]
    vals = _vals(s)
    return {
        "dates": dates,
        "price_raw": vals,
        "price_adj": vals,
        "ma_short": _vals(ma_short.reindex(s.index)),
        "ma_long": _vals(ma_long.reindex(s.index)),
        "series_a": _vals(sa.reindex(s.index)),
        "series_b": _vals(sb.reindex(s.index)),
    }


def ratio_to_dict(
    analysis: RatioAnalysis,
    series: pd.Series,
    sa: pd.Series,
    sb: pd.Series,
    include_chart: bool = True,
) -> dict:
    """Payload d'une fiche ratio.

    `include_chart=False` écarte la série de prix (le graphe) : utile aux consommateurs
    qui ne tracent rien (outils MCP), où elle représente l'essentiel du poids. Le dict
    `chart` n'est alors PAS construit (aucun calcul de moyennes mobiles inutile).
    """
    out = {
        "kind_payload": "ratio",  # le front distingue fiche ratio vs action
        "identity": {
            "name": analysis.label,
            "ticker": f"{analysis.ticker_a} / {analysis.ticker_b}",
            "ticker_a": analysis.ticker_a,
            "ticker_b": analysis.ticker_b,
            "last_price": round(analysis.last_ratio, 4),
            "currency": "",  # un ratio est sans dimension
            "kind": "ratio",
        },
        "indicators": {
            "distance_sigma": _scored(analysis.indicators.distance_sigma),
            "perf_passee": _scored(analysis.indicators.perf_passee),
            "ecart_type": _scored(analysis.indicators.ecart_type),
            "potential_5y": _scored(analysis.indicators.potential_5y),
            "potential_10y": _scored(analysis.indicators.potential_10y),
            "trend": _scored(analysis.indicators.trend),
            "quality": _scored(analysis.indicators.quality),
            "beta": _scored(analysis.indicators.beta),  # β A~B (amplitude, live front)
            "correlation": _scored(analysis.indicators.correlation),  # ρ A~B (live front)
        },
        "regression": {
            "perf_annual_raw": round(analysis.regression.perf_annual * 100, 2),
            "start": analysis.regression.start.isoformat(),
            "end": analysis.regression.end.isoformat(),
            "n_points": analysis.regression.n_points,
        },
        "events": _events_payload("ratio", f"{analysis.ticker_a}/{analysis.ticker_b}"),
        "fundamentals": None,  # un ratio n'a pas de comptes
        "warnings": analysis.warnings,
    }
    if include_chart:
        out["chart"] = ratio_chart_payload(series, sa, sb)
    return out


def summarize_index_to_dict(entry: dict) -> dict:
    """Stat « coup d'œil » d'un indice pour la liste « Mes indices ».

    `entry` = sortie de services/analysis.summarize_index : {index_id, stats, error}.
    `stats` vaut None si l'indice est en erreur (membre indisponible…) : le front
    affiche un tiret et le détail de l'erreur.
    """
    stats = entry["stats"]
    return {
        "index_id": entry["index_id"],
        "error": entry["error"],
        "stats": None
        if stats is None
        else {
            "distance_sigma": _scored(stats["distance_sigma"]),
            "pente": _scored(stats["pente"]),
            "trend": _scored(stats["trend"]),
        },
    }


def basket_chart_payload(series: pd.Series) -> dict:
    """Série d'un indice personnalisé pour le tracé (raw = adj = série de l'indice).

    Même format que chart_payload : le front réutilise drawChart tel quel. Pas de
    series_a/series_b : un indice n'a pas de β (pas d'actif de référence).
    """
    s = _downsample(series)
    settings = cache.get_settings()
    ma_short = _moving_average(series, settings["trend_ma_short"])
    ma_long = _moving_average(series, settings["trend_ma_long"])
    dates = [d.strftime("%Y-%m-%d") for d in s.index]
    vals = _vals(s)
    return {
        "dates": dates,
        "price_raw": vals,
        "price_adj": vals,
        "ma_short": _vals(ma_short.reindex(s.index)),
        "ma_long": _vals(ma_long.reindex(s.index)),
    }


def basket_to_dict(analysis: BasketAnalysis, series: pd.Series, include_chart: bool = True) -> dict:
    """Payload d'une fiche indice personnalisé.

    `include_chart=False` écarte la série de prix (le graphe) : le dict `chart` n'est
    PAS construit (aucun calcul de moyennes mobiles inutile) — utile aux outils MCP
    qui ne tracent rien.
    """
    out: dict[str, object] = {
        "kind_payload": "basket",  # le front distingue fiche indice vs action/ratio
        "identity": {
            "name": analysis.name,
            "ticker": f"Indice #{analysis.index_id}",
            "category": analysis.category,
            "index_id": analysis.index_id,
            "members": [
                {
                    "ticker": m["ticker"],
                    "name": m["name"],
                    "distance_sigma": _scored(m["distance_sigma"]),
                    "pente": _scored(m["pente"]),
                    "trend": _scored(m["trend"]),
                }
                for m in analysis.members
            ],
            "last_price": round(analysis.last_value, 4),
            "currency": "",  # un indice synthétique est sans dimension
            "kind": "basket",
        },
        "indicators": {
            "distance_sigma": _scored(analysis.indicators.distance_sigma),
            "perf_passee": _scored(analysis.indicators.perf_passee),
            "ecart_type": _scored(analysis.indicators.ecart_type),
            "potential_5y": _scored(analysis.indicators.potential_5y),
            "potential_10y": _scored(analysis.indicators.potential_10y),
            "trend": _scored(analysis.indicators.trend),
            "quality": _scored(analysis.indicators.quality),
        },
        "regression": {
            "perf_annual_raw": round(analysis.regression.perf_annual * 100, 2),
            "start": analysis.regression.start.isoformat(),
            "end": analysis.regression.end.isoformat(),
            "n_points": analysis.regression.n_points,
        },
        "events": _events_payload("index", analysis.index_id),
        "fundamentals": None,  # un indice n'a pas de comptes
        "warnings": analysis.warnings,
    }
    if include_chart:
        chart = basket_chart_payload(series)
        # Un indice synthétique est déjà en total-return : `raw == adj`, pas de
        # bascule possible côté front.
        chart["momentum"] = momentum_payload(
            f"INDEX:{analysis.index_id}", series, None, _downsample(series).index
        )
        out["chart"] = chart
    return out


def _metrics_dict(table: pd.DataFrame) -> dict:
    """Lignes d'un tableau (comptes ou valorisation) -> dict {nom: [valeurs arrondies]}."""
    out = {}
    for name, row in table.iterrows():
        out[name] = [None if pd.isna(v) else round(float(v), 2) for v in row.to_numpy()]
    return out


def _dividend_payload(fundamentals) -> dict | None:
    """Sous-ensemble du dividende consommé par le front (pas le dict brut).

    Le dict interne (`data/yahoo._build_dividend`) porte des clés de travail
    (`events`, `payout_history`, `buyback_history`, `dividend_paid_history`) qui
    servent au serveur mais ne sont PAS lues par le front — les séries dérivées
    passent déjà par `dividend_series`. On ne sérialise que ce qui est affiché :
    instantanés (yield, payout), disponibilité des rachats, dividende par action,
    dernier paiement et stats précalculées.
    """
    div = fundamentals.dividend if fundamentals else None
    if not div:
        return None
    keys = (
        "yield_pct",
        "payout_pct",
        "buybacks_available",
        "per_share",
        "last_payment_value",
        "last_payment_date",
        "stats",
    )
    return {k: div.get(k) for k in keys}


def _dividend_series_payload(fundamentals) -> dict | None:
    """Séries annuelles de la section Dividende (payout ratios, montants).

    Renvoie {years: [...], metrics: {nom: [valeurs alignées]}} ou None. Les années
    sont l'union des exercices de toutes les séries (tri croissant) ; une métrique
    absente pour une année vaut None. Le front trace ces séries telles quelles
    (aucun seuil, aucun calcul métier côté client).
    """
    div = fundamentals.dividend if fundamentals else None
    if not div:
        return None
    ph = div.get("payout_history") or {}
    series: dict[str, dict[int, float]] = {}
    mapping = {
        "Earnings Payout Ratio": ph.get("earnings_payout"),
        "FCF Payout Ratio": ph.get("fcf_payout"),
        "Earnings Shareholder Payout Ratio": ph.get("earnings_shareholder_payout"),
        "FCF Shareholder Payout Ratio": ph.get("fcf_shareholder_payout"),
        "Dividendes versés": div.get("dividend_paid_history"),
        "Rachats d'actions": div.get("buyback_history"),
    }
    for name, by_year in mapping.items():
        if by_year:
            series[name] = {int(y): float(v) for y, v in by_year.items()}
    if not series:
        return None
    years = sorted({y for s in series.values() for y in s})
    return {
        "years": years,
        "metrics": {name: [s.get(y) for y in years] for name, s in series.items()},
    }


def _manual_entries(ticker: str) -> list[dict]:
    """Entrées manuelles `[{year, metric}]` du ticker analysé.

    Le front en a besoin pour compter les écrasements EXACTEMENT comme le serveur
    (`metric in existing[year]`). On ne transporte que la paire (année, métrique),
    pas les valeurs : c'est un repère de comparaison, pas une donnée à afficher.
    """
    from obole.data import manual as manual_data

    return [{"year": e["year"], "metric": e["metric"]} for e in manual_data.get_manual(ticker)]


def fundamentals_payload(analysis: StockAnalysis) -> dict | None:
    f = analysis.fundamentals
    if f is None or f.table.empty:
        return None
    payload = {
        "kind": f.kind.value,
        "years": list(f.table.columns),
        "available_years": f.available_years,
        "metrics": _metrics_dict(f.table),
        "growth": f.growth,
        "dividend": _dividend_payload(f),
        "dividend_series": _dividend_series_payload(f),
        "valuation": None,
        "valuation_calc": f.valuation_calc,
        "manual_years": f.manual_years,
        # Entrées manuelles (année × métrique) : permet au front de compter un
        # « écrasement » EXACTEMENT comme le serveur (`metric in existing[year]`),
        # au lieu d'approximer sur les seules années. Léger (quelques dizaines).
        "manual_entries": _manual_entries(analysis.identity.ticker),
    }
    if f.valuation is not None and not f.valuation.empty:
        payload["valuation"] = {
            "years": [int(c) for c in f.valuation.columns],
            "metrics": _metrics_dict(f.valuation),
        }
    return payload


def screen_row_to_dict(row: ScreenResult) -> dict:
    """Ligne de résultat du screener -> dict JSON + polarité par cellule.

    La polarité des cellules colorées (`colors`) est dérivée de `config.SCREEN_COLORS`
    (seule source, seuils déjà calibrés) : le front ne calcule aucun seuil. Un ticker
    en `error` est neutre (pas de couleur) mais reste triable en fin de liste.
    """
    err = row.error is not None
    return {
        "ticker": row.ticker,
        "name": row.name,
        "sector": row.sector,
        "market_cap": row.market_cap,
        "kind": row.kind.value if isinstance(row.kind, CompanyKind) else row.kind,
        "z": row.z,
        "pente_pct": row.pente_pct,
        "ecart_type_pct": row.ecart_type_pct,
        "pot_5y_pct": row.pot_5y_pct,
        "pot_10y_pct": row.pot_10y_pct,
        "trend_bullish": row.trend_bullish,
        "roe_pct": row.roe_pct,
        "per": row.per,
        "p_b": row.p_b,
        "p_fcf": row.p_fcf,
        "fcf_yield_pct": row.fcf_yield_pct,
        "quality_score": row.quality_score,
        # Score composite (#14) : classement par compromis. Volontairement SANS
        # couleur (pas dans SCREEN_COLORS) : c'est un rang relatif, pas un seuil.
        "score": row.score,
        "warnings": row.warnings,
        "error": row.error,
        # Couleur (bleu=bon/rouge=mauvais) par critère, depuis config.SCREEN_COLORS.
        "colors": {
            key: None if err else _polarity(sens, seuil, getattr(row, key, None))
            for key, (sens, seuil) in config.SCREEN_COLORS.items()
        },
    }


def screen_run_to_dict(run: ScreenRun, max_rows: int | None = None) -> dict:
    """Résultat d'un scan screener -> payload JSON (partagé API ↔ MCP).

    Compose le `ScreenRun` (dataclass de `services/screener`) en dict : `count` =
    nombre de lignes filtrées+triées, `tickers_count` = taille du scan brut (avant
    filtre). Chaque ligne passe par `screen_row_to_dict` (polarité par cellule).
    C'est la SEULE composition de ce payload : l'API et l'outil MCP la partagent,
    ce qui garantit la parité de leur réponse.

    `max_rows` borne le nombre de lignes RENDUES (`rows`) sans changer `count` ni
    `tickers_count`, qui restent les totaux réels : un consommateur qui compte les
    lignes doit lire `count`, pas `len(rows)`. La troncature vit ici (et non dans
    une couche de transport) pour rester une règle unique, partagée API ↔ MCP.
    """
    rows = run.rows if max_rows is None else run.rows[:max_rows]
    return {
        "source": run.source,
        "count": len(run.rows),
        "tickers_count": run.tickers_count,
        "rows": [screen_row_to_dict(r) for r in rows],
    }


# --- Watchlist (#25) ---------------------------------------------------------

# Champs renvoyés par `view="summary"` (outil MCP) : la décision, sans le bruit
# (secteur, potentiels, avertissements). `view="full"` renvoie la ligne complète
# et reste STRICTEMENT identique à `POST /api/watchlist/run`.
_WATCH_SUMMARY_FIELDS = (
    "ticker",
    "tier",
    "name",
    "price",
    "fair_price",
    "fair_price_source",
    "target_yield",
    "safety_margin_pct",
    "margin_good",
    "ref_start",
    "ref_is_default",
    "ref_line",
    "trend_gap_pct",
    "z",
    "ecart_type_pct",
    "pot_5y_pct",
    "pot_10y_pct",
    "pot_5y_source",
    "pot_10y_source",
    "error",
)


def watchlist_state_to_dict(state: dict) -> dict:
    """État de la watchlist -> payload JSON (partagé API ↔ MCP).

    `tiers` vient de `config.WATCH_TIERS`, `items` de la table, `refs` est le
    dictionnaire `{ticker: date}` des fenêtres de confiance. Aucune valeur n'est
    recalculée ici : le service a déjà tout lu.
    """
    return {
        "tiers": [dict(t) for t in state.get("tiers", [])],
        "items": [dict(i) for i in state.get("items", [])],
        "refs": dict(state.get("refs", {})),
    }


def watchlist_run_to_dict(
    run: WatchlistRun, *, view: str = "full", max_rows: int | None = None
) -> dict:
    """Classement watchlist -> payload JSON (partagé API ↔ MCP).

    `count` = nombre total de lignes (avant `max_rows`) ; `rows` peut être tronqué.
    `view="summary"` réduit chaque ligne aux champs de décision ; `view="full"`
    conserve la ligne complète (parité stricte avec la route REST).
    """
    if view not in ("full", "summary"):
        raise ValueError(f"view invalide : {view!r} (attendu : full ou summary)")
    rows = run.rows if max_rows is None else run.rows[:max_rows]
    payload = [asdict(r) for r in rows]
    if view == "summary":
        payload = [{k: row[k] for k in _WATCH_SUMMARY_FIELDS} for row in payload]
    return {"generated_at": run.generated_at, "count": len(run.rows), "rows": payload}


# --- Portefeuille (#17) ------------------------------------------------------


def portfolio_position_to_dict(position: dict) -> dict:
    """Position recalculée -> dict JSON (arrondis d'affichage, aucune logique métier).

    La quantité reste telle quelle (fractionnaire possible) ; le PRU et le coût
    sont arrondis à 4 décimales (précision suffisante, évite les flottants bruyants).
    `tags` (#17.6) = étiquettes distinctes de la position (portefeuille virtuel) ;
    une position sans étiquette porte une liste vide (jamais null).
    """
    pru = position.get("pru")
    cost = position.get("cost_basis")
    return {
        "ticker": position["ticker"],
        "quantity": round(float(position["quantity"]), 6),
        "pru": None if pru is None else round(float(pru), 4),
        "cost_basis": None if cost is None else round(float(cost), 4),
        "realized": round(float(position.get("realized") or 0.0), 4),
        "tags": list(position.get("tags") or []),
    }


def portfolio_positions_to_list(positions: list[dict]) -> list[dict]:
    """Liste de positions -> liste JSON, triée par poids décroissant de coût."""
    rows = [portfolio_position_to_dict(p) for p in positions]
    rows.sort(key=lambda r: r["cost_basis"] or 0.0, reverse=True)
    return rows


def portfolio_summary_to_dict(summary: dict) -> dict:
    """Résumé de performance (#17.1) -> dict JSON.

    Aucune logique métier ici : les arrondis sont faits par `services/portfolio`,
    cette fonction garantit seulement la forme du payload (listes, scalaires
    nullables) et l'ordre de lecture des cartes Top/Flop.
    """
    return {
        "dates": list(summary.get("dates") or []),
        "period": summary.get("period"),
        "period_start": summary.get("period_start"),
        "benchmark": summary.get("benchmark"),
        "portfolio": list(summary.get("portfolio") or []),
        "benchmark_curve": list(summary.get("benchmark_curve") or []),
        "kpis": summary.get("kpis") or {},
        "accounts": list(summary.get("accounts") or []),
        "holdings": list(summary.get("holdings") or []),
        "account": summary.get("account"),
        "top": list(summary.get("top") or []),
        "flop": list(summary.get("flop") or []),
        "warnings": list(summary.get("warnings") or []),
    }


def portfolio_risk_to_dict(risk: dict) -> dict:
    """Risque du portefeuille (#17.3) -> dict JSON.

    Aucune logique métier : garantit la forme du payload (listes, scalaires
    nullables) consommée par le front et par l'outil MCP `get_portfolio_risk`.
    """
    corr = risk.get("correlation") or {}
    return {
        "dates": list(risk.get("dates") or []),
        "period": risk.get("period"),
        "period_start": risk.get("period_start"),
        "benchmark": risk.get("benchmark"),
        "drawdown": list(risk.get("drawdown") or []),
        "benchmark_drawdown": list(risk.get("benchmark_drawdown") or []),
        "metrics": risk.get("metrics") or {},
        "benchmark_metrics": risk.get("benchmark_metrics") or {},
        "months": list(risk.get("months") or []),
        "corr_avg": risk.get("corr_avg"),
        "correlation": {
            "tickers": list(corr.get("tickers") or []),
            "matrix": [list(row) for row in (corr.get("matrix") or [])],
            "excluded": list(corr.get("excluded") or []),
        },
        "warnings": list(risk.get("warnings") or []),
    }


def portfolio_performance_to_dict(perf: dict) -> dict:
    """Performance du portefeuille (#17.4) -> dict JSON.

    Aucune logique métier : garantit la forme du payload (listes, scalaires
    nullables) consommée par le front. `stats` est un dict {clé: {value, good}} ;
    `stat_groups` porte la taxonomie (source unique config.py) ; `monthly` porte
    les tableaux portefeuille + benchmark.
    """
    monthly = perf.get("monthly") or {}
    risk = perf.get("risk_adjusted") or {}
    contrib = perf.get("contributions") or {}
    return {
        "period": perf.get("period"),
        "period_start": perf.get("period_start"),
        "benchmark": perf.get("benchmark"),
        "stat_groups": list(perf.get("stat_groups") or []),
        "stats": dict(perf.get("stats") or {}),
        "monthly": {
            "portfolio": _monthly_table(monthly.get("portfolio")),
            "benchmark": _monthly_table(monthly.get("benchmark")),
            "months": monthly.get("months"),
        },
        "contributions": {
            "items": list(contrib.get("items") or []),
            "total_pct": contrib.get("total_pct"),
        },
        "risk_adjusted": {
            "risk_free_pct": risk.get("risk_free_pct"),
            "periods": list(risk.get("periods") or []),
            "by_period": {
                k: {
                    "portfolio": dict(v.get("portfolio") or {}),
                    "benchmark": dict(v.get("benchmark") or {}),
                }
                for k, v in (risk.get("by_period") or {}).items()
            },
            "portfolio": dict(risk.get("portfolio") or {}),
            "benchmark": dict(risk.get("benchmark") or {}),
        },
        "retrospective": list(perf.get("retrospective") or []),
        "table": list(perf.get("table") or []),
        "warnings": list(perf.get("warnings") or []),
    }


def _monthly_table(table: dict | None) -> dict:
    """Forme normalisée d'un tableau mensuel (années + lignes), jamais None."""
    table = table or {}
    return {"years": list(table.get("years") or []), "rows": list(table.get("rows") or [])}


def security_detail_to_dict(detail: dict) -> dict:
    """Détail d'un titre (modale Performance) -> dict JSON.

    `chart` (dates + série ajustée du titre) et `benchmark_curve` (alignée sur
    les dates du chart) sont garantis présents et de même longueur — condition
    d'un rebasage commun à 0 % côté front.
    """
    chart = detail.get("chart") or {}
    return {
        "ticker": detail.get("ticker"),
        "benchmark": detail.get("benchmark"),
        "chart": chart,
        "benchmark_curve": list(detail.get("benchmark_curve") or []),
    }


def portfolio_correlation_test_to_dict(result: dict) -> dict:
    """Test de corrélation (#17.3) -> dict JSON.

    Aucune logique métier : garantit la forme du payload consommée par le front et
    par l'outil MCP `test_portfolio_correlation`. `row` est aligné sur `tickers`
    (colonnes de la matrice), `None` = historique commun insuffisant.
    """
    return {
        "ticker": result.get("ticker"),
        "tickers": list(result.get("tickers") or []),
        "row": list(result.get("row") or []),
        "obs": result.get("obs") or 0,
        "current_avg": result.get("current_avg"),
        "new_avg": result.get("new_avg"),
        "delta": result.get("delta"),
        "warning": result.get("warning"),
    }


def portfolio_dividend_page_to_dict(page: dict) -> dict:
    """Page Dividende du portefeuille (#17.5) -> dict JSON.

    Aucune logique métier : garantit la forme du payload (listes, scalaires
    nullables) consommée par le front. `income` porte le revenu par année / mois
    / payeur, `stats` les KPI agrégés (`{clé: {value, good}}`), `stat_groups` la
    taxonomie (source unique `config.py`), `lines` le tableau par titre.
    """
    income = page.get("income") or {}
    concentration = page.get("concentration") or {}
    return {
        "income": {
            "years": list(income.get("years") or []),
            "rows": list(income.get("rows") or []),
            "by_company": list(income.get("by_company") or []),
            "total_confirmed": income.get("total_confirmed"),
            "total_proposed": income.get("total_proposed"),
            "last_year": income.get("last_year"),
        },
        "stat_groups": list(page.get("stat_groups") or []),
        "stats": dict(page.get("stats") or {}),
        "concentration": {
            "n_eff": concentration.get("n_eff"),
            "top_n_pct": concentration.get("top_n_pct"),
            "top_n": concentration.get("top_n"),
            "first_pct": concentration.get("first_pct"),
            "first_ticker": concentration.get("first_ticker"),
            "payers": concentration.get("payers") or 0,
        },
        "lines": list(page.get("lines") or []),
        "warnings": list(page.get("warnings") or []),
    }


def _events_payload(kind: str, ref: str | int) -> list[dict]:
    """Événements annotés du graphe (date/label/description), lus depuis le cache."""
    try:
        return events_data.list_events(kind, str(ref))
    except ValueError:
        return []


def analysis_to_dict(
    analysis: StockAnalysis, prices: PriceSeries, include_chart: bool = True
) -> dict:
    """Payload d'une fiche action.

    `include_chart=False` écarte la série de prix (le graphe) — qui pèse ~90 % du
    payload — pour les consommateurs qui ne tracent rien (outils MCP, prompt de
    thèse). Le dict `chart` n'est alors PAS construit (aucun calcul inutile).
    """
    ind = analysis.indicators
    ident = analysis.identity
    out: dict[str, object] = {
        "kind_payload": "stock",  # le front distingue fiche action vs ratio
        "identity": {
            "ticker": ident.ticker,
            "name": ident.name,
            "isin": ident.isin,
            "country": ident.country,
            "sector": ident.sector,
            "industry": ident.industry,
            "website": ident.website,
            "currency": ident.currency,
            "market_cap": ident.market_cap,
            "last_price": ident.last_price,
            "beta": ident.beta,
            "week52_low": ident.week52_low,
            "week52_high": ident.week52_high,
            "volume": ident.volume,
            "avg_volume": ident.avg_volume,
            "kind": ident.kind.value,
        },
        "indicators": {
            "distance_sigma": _scored(ind.distance_sigma),
            "perf_passee": _scored(ind.perf_passee),
            "ecart_type": _scored(ind.ecart_type),
            "potential_5y": _scored(ind.potential_5y),
            "potential_10y": _scored(ind.potential_10y),
            "trend": _scored(ind.trend),
            "quality": _scored(ind.quality),
        },
        "regression": {
            "perf_annual_raw": round(analysis.regression_raw.perf_annual * 100, 2),
            "start": analysis.regression_raw.start.isoformat(),
            "end": analysis.regression_raw.end.isoformat(),
            "n_points": analysis.regression_raw.n_points,
        },
        "events": _events_payload("stock", ident.ticker),
        "fundamentals": fundamentals_payload(analysis),
        "summary": [_summary_card(c) for c in analysis.summary],
        "profile": _profile_payload(ident),
        "has_thesis": _has_thesis(ident.ticker),
        "warnings": analysis.warnings,
    }
    if include_chart:
        chart = chart_payload(prices, analysis.fundamentals)
        # Momentum (Clara Vallis) : séries alignées sur la grille du graphe.
        # La grille est recalculée depuis les prix, jamais lue du dict `chart` :
        # le tracé et le momentum partagent la même décimation déterministe.
        # Absent quand `include_chart=False` (MCP, prompt de thèse) : rien à
        # tracer, donc rien à calculer.
        chart["momentum"] = momentum_payload(
            ident.ticker, prices.raw, prices.adjusted, _downsample(prices.raw).index
        )
        out["chart"] = chart
    return out
