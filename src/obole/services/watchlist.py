"""Cas d'usage « watchlist » (#25) : tiers, références et classement par marge.

Couche `services/` : orchestration partagée API ↔ MCP. Aucune formule propre :

- le prix juste est **lu** de `valuation_settings` (jamais recalculé ici) ;
- la marge de sécurité est `engine.valuation_calc.safety_margin` ;
- la fenêtre de confiance est choisie par `services.analysis.reference_window`
  (référence persistée sinon 20 ans) et les indicateurs de fenêtre viennent de
  `services.screen.windowed_analysis` ;
- le scan parallèle (pool + budget + timeout) est `services.screener.scan_parallel`.

La séparation assumée : l'IA (MCP) peut **organiser** (appartenance, tier) mais
ne définit **jamais** la référence ni le prix juste — ce sont des jugements, et
les routes de référence/tier ne sont pas exposées comme outils d'écriture MCP.

Toute entrée est hostile par défaut : le service valide le ticker, le tier, la
date et le plafond, et lève `ValueError` (l'API -> 422, le MCP -> `ToolError`).
"""

from __future__ import annotations

import re
import time
from datetime import date

from obole import config, observability
from obole.data import cache, yahoo
from obole.engine import regression as reg
from obole.engine import valuation_calc
from obole.engine.summary import window_since
from obole.models import StockAnalysis, WatchlistRow, WatchlistRun
from obole.services import analysis as analysis_service
from obole.services import screen as screen_service
from obole.services import screener as screener_service

logger = observability.get_logger(__name__)

# Ticker Yahoo : majuscules/chiffres et les séparateurs réellement utilisés
# (RI.PA, ^FCHI, BTC-EUR, BRK-B, A=B). On refuse tout espace ou caractère de
# contrôle : l'entrée peut venir d'une URL REST ou d'une IA.
_TICKER_RE = re.compile(r"^[A-Z0-9.\-=^]{1,24}$")
_TIER_IDS = tuple(int(t["id"]) for t in config.WATCH_TIERS)


# --- Validation --------------------------------------------------------------


def normalize_ticker(raw: object) -> str:
    """Ticker nettoyé (majuscules) ou `ValueError` si vide/illisible."""
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("Ticker requis")
    ticker = raw.strip().upper()
    if not _TICKER_RE.match(ticker):
        raise ValueError(f"Ticker invalide : {raw!r}")
    return ticker


def validate_tier(value: object) -> int:
    """Tier 1, 2 ou 3 (`ValueError` sinon). Accepte l'entier et sa forme texte."""
    if isinstance(value, bool) or value is None:
        raise ValueError("Tier invalide : attendu 1, 2 ou 3")
    if isinstance(value, int):
        tier = value
    elif isinstance(value, float):
        if not value.is_integer():
            raise ValueError("Tier invalide : attendu 1, 2 ou 3")
        tier = int(value)
    elif isinstance(value, str):
        try:
            tier = int(value.strip())
        except ValueError:
            raise ValueError("Tier invalide : attendu 1, 2 ou 3") from None
    else:
        raise ValueError("Tier invalide : attendu 1, 2 ou 3")
    if tier not in _TIER_IDS:
        raise ValueError("Tier invalide : attendu 1, 2 ou 3")
    return tier


def validate_ref_start(value: object) -> str:
    """Date ISO `AAAA-MM-JJ`, pas dans le futur. Lève `ValueError` sinon."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Date de référence requise (AAAA-MM-JJ)")
    raw = value.strip()
    if len(raw) != 10 or raw[4] != "-" or raw[7] != "-":
        raise ValueError("Date de référence invalide (attendu AAAA-MM-JJ)")
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        raise ValueError("Date de référence invalide (attendu AAAA-MM-JJ)") from None
    if parsed > date.today():
        raise ValueError("La date de référence ne peut pas être dans le futur")
    return parsed.isoformat()


# --- État / appartenance -----------------------------------------------------


def list_state() -> dict:
    """Tiers (source unique config) + valeurs suivies + références par titre."""
    return {
        "tiers": [dict(t) for t in config.WATCH_TIERS],
        "items": cache.list_watch_items(),
        "refs": cache.list_ticker_refs(),
    }


def set_tier(ticker: object, tier: object) -> dict:
    """Ajoute OU déplace une valeur dans un tier. Renvoie l'item persisté."""
    key = normalize_ticker(ticker)
    clean_tier = validate_tier(tier)
    if cache.get_watch_item(key) is None and (
        cache.count_watch_items() >= config.WATCHLIST_MAX_ITEMS
    ):
        raise ValueError(f"Watchlist pleine ({config.WATCHLIST_MAX_ITEMS} valeurs maximum)")
    cache.upsert_watch_item(key, clean_tier)
    item = cache.get_watch_item(key)
    assert item is not None  # upsert juste au-dessus
    return item


def remove(ticker: object) -> bool:
    """Retire une valeur. La référence (`ticker_refs`) est CONSERVÉE."""
    return cache.delete_watch_item(normalize_ticker(ticker))


# --- Fenêtre de confiance ----------------------------------------------------


def ref_stats(raw, start: str) -> dict | None:
    """Statistiques de la droite depuis `start` (prix bruts), ou None si trop court.

    Seule implémentation de la fenêtre de confiance : la fiche (`/api/stock`) et
    le classement lisent les mêmes nombres. `line`/`trend_gap_pct` sont la valeur
    de la droite au dernier point ; `z` en est la distance en σ.
    """
    try:
        window = window_since(raw, start).dropna()
    except (TypeError, ValueError):
        # Date corrompue en base (écrite hors service) : pas de statistiques, la
        # fiche et le classement restent servis (la référence est simplement muette).
        return None
    window = window[window > 0]
    if len(window) < config.REGRESSION_MIN_POINTS:
        return None
    try:
        regression = reg.fit_log_regression(window)
    except ValueError:
        return None
    price = float(window.iloc[-1])
    line = regression.fitted_now
    return {
        "start": regression.start.isoformat(),
        "end": regression.end.isoformat(),
        "n_points": regression.n_points,
        "line": line,
        "z": reg.distance_sigma(regression, price),
        "ecart_type_pct": regression.ecart_type_size * 100,
        "trend_gap_pct": ((line - price) / line * 100) if line else None,
        "pente_pct": regression.perf_annual * 100,
    }


def get_ref(ticker: object) -> str | None:
    """Référence persistée d'un titre, ou None (fenêtre 20 ans par défaut)."""
    return cache.get_ticker_ref(normalize_ticker(ticker))


def set_ref(ticker: object, start: object) -> dict:
    """Enregistre la référence d'un titre et renvoie ses statistiques.

    La référence est refusée (422) si la fenêtre ne contient pas assez de points.
    Si les prix sont momentanément indisponibles (réseau), on enregistre quand
    même la référence et on renvoie `stats=None` : un choix de confiance ne doit
    pas être perdu pour une panne de données.
    """
    key = normalize_ticker(ticker)
    clean_start = validate_ref_start(start)
    try:
        prices = yahoo.fetch_prices(key)
    except yahoo.TickerNotFound:
        raise ValueError(f"Ticker introuvable : {key}") from None
    except Exception:  # réseau/source : dégradation, jamais de blocage
        logger.warning("Prix indisponibles pour la référence de %s", key, exc_info=True)
        cache.set_ticker_ref(key, clean_start)
        return {
            "ref": {"start": clean_start},
            "stats": None,
            "warning": "Prix indisponibles : référence enregistrée sans statistiques.",
        }
    stats = ref_stats(prices.raw, clean_start)
    if stats is None:
        raise ValueError(
            "Historique insuffisant sur cette fenêtre "
            f"({config.REGRESSION_MIN_POINTS} points minimum)"
        )
    cache.set_ticker_ref(key, clean_start)
    return {"ref": {"start": clean_start}, "stats": stats, "warning": None}


def clear_ref(ticker: object) -> None:
    """Efface la référence : le titre revient à la fenêtre 20 ans par défaut."""
    cache.clear_ticker_ref(normalize_ticker(ticker))


# --- Fiche : état de la valeur suivie ---------------------------------------


def stock_state(ticker: str, prices) -> dict:
    """Bloc `watch` du payload de fiche : tier, référence et stats de référence."""
    key = ticker.upper()
    item = cache.get_watch_item(key)
    start = cache.get_ticker_ref(key)
    return {
        "tier": None if item is None else item["tier"],
        "ref": {"start": start} if start else None,
        "ref_stats": ref_stats(prices.raw, start) if start else None,
    }


def decorate_stock_payload(payload: dict, ticker: str, prices) -> dict:
    """Ajoute `watch` au payload de fiche (partagé route REST ↔ outil MCP)."""
    payload["watch"] = stock_state(ticker, prices)
    return payload


# --- Classement --------------------------------------------------------------


def _saved_fair(saved: dict | None) -> float | None:
    """Prix juste enregistré exploitable (`> 0`), sinon None (repli)."""
    if not saved:
        return None
    raw = saved.get("fair_price")
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _saved_target(saved: dict | None) -> float | None:
    if not saved:
        return None
    raw = saved.get("target_yield")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _error_row(ticker: str, tier: int, message: str) -> WatchlistRow:
    """Ligne d'erreur : le tier est conservé, la valeur reste retirable."""
    return WatchlistRow(ticker=ticker.upper(), tier=tier, error=message)


def _row_from_analysis(
    ticker: str,
    tier: int,
    analysis: StockAnalysis,
    effective_ref: str | None,
    saved: dict | None,
) -> WatchlistRow:
    """Réduit une analyse fenêtrée à une ligne de classement (aucun calcul neuf)."""
    ident = analysis.identity
    regression = analysis.regression_raw
    price = ident.last_price
    line = regression.fitted_now if regression else None
    z = reg.distance_sigma(regression, float(price)) if regression and price else None
    trend_gap = (line - float(price)) / line * 100 if (line and price) else None

    saved_fair = _saved_fair(saved)
    fair: float | None
    source: str
    target: float | None
    if saved_fair is not None:
        fair, source, target = saved_fair, "saved", _saved_target(saved)
    else:
        fair, source, target = line, "regression", None
    margin = valuation_calc.safety_margin(fair, price)
    return WatchlistRow(
        ticker=ident.ticker,
        tier=tier,
        name=ident.name,
        sector=ident.sector,
        currency=ident.currency,
        price=price,
        fair_price=fair,
        fair_price_source=source if fair is not None else None,
        target_yield=target,
        safety_margin_pct=margin,
        margin_good=None if margin is None else margin > 0,
        ref_start=regression.start.isoformat() if regression else None,
        ref_is_default=effective_ref is None,
        ref_line=line,
        trend_gap_pct=trend_gap,
        z=z,
        ecart_type_pct=(regression.ecart_type_size * 100) if regression else None,
        pente_pct=analysis.indicators.perf_passee.value,
        pot_5y_pct=analysis.indicators.potential_5y.value,
        pot_10y_pct=analysis.indicators.potential_10y.value,
        trend_bullish=analysis.indicators.trend.good,
        warnings=list(analysis.warnings),
    )


def _sort_key(row: WatchlistRow) -> tuple:
    """Marge décroissante (absente en dernier), puis écart, tier, ticker."""
    margin = row.safety_margin_pct
    gap = row.trend_gap_pct
    return (
        row.error is not None,
        margin is None,
        -(margin or 0.0),
        gap is None,
        -(gap or 0.0),
        row.tier,
        row.ticker,
    )


def run(tier: int | None = None) -> WatchlistRun:
    """Classe les valeurs suivies (ou celles d'un tier) par marge de sécurité.

    Le scan est parallèle et borné (`scan_parallel`), et chaque ticker est isolé :
    un ticker cassé devient une `WatchlistRow.error`, jamais un crash global. La
    fenêtre de chaque ligne est sa référence persistée (ou 20 ans), choisie par
    `analysis.reference_window` — la même que le « Prix juste » du Résumé.
    """
    tier_filter = validate_tier(tier) if tier is not None else None
    items = cache.list_watch_items()
    if tier_filter is not None:
        items = [i for i in items if i["tier"] == tier_filter]
    if not items:
        return WatchlistRun(generated_at=time.time(), rows=[])

    tiers = {i["ticker"]: i["tier"] for i in items}
    saved = {i["ticker"]: cache.get_valuation_settings(i["ticker"]) for i in items}

    def _one(ticker: str) -> tuple[str, WatchlistRow]:
        try:
            prices = yahoo.fetch_prices(ticker)
            # Même sélection de fenêtre que le Résumé : une référence stockée
            # mais inexploitable retombe sur 20 ans (pas d'erreur trompeuse).
            _, effective_ref = analysis_service.reference_window(ticker, prices.raw)
            if effective_ref:
                analysis = screen_service.windowed_analysis(ticker, prices, ref_start=effective_ref)
            else:
                analysis = screen_service.windowed_analysis(
                    ticker, prices, regression_window=config.REGRESSION_YEARS_DEFAULT
                )
            return ticker, _row_from_analysis(
                ticker, tiers[ticker], analysis, effective_ref, saved.get(ticker)
            )
        # Données indisponibles : la ligne reste dans la table, en erreur.
        except (yahoo.TickerNotFound, ValueError, KeyError, IndexError) as exc:
            return ticker, _error_row(ticker, tiers[ticker], str(exc))

    results = screener_service.scan_parallel(
        [i["ticker"] for i in items],
        _one,
        timeout_result=lambda t: _error_row(t, tiers[t], "timeout"),
    )
    rows = sorted(results.values(), key=_sort_key)
    return WatchlistRun(generated_at=time.time(), rows=rows)
