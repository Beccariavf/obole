"""Screener : univers d'actions + accès réseau/cache.

Seule couche qui touche le réseau et le disque pour le screener (pattern de
`data/`). Le J0 a posé le `ping()` de liaison ; le J1 ajoute `fetch_universe()`
qui récupère l'univers des actions françaises via l'API screener de Yahoo
(`yf.screen` + `EquityQuery`), avec cache agressif et dégradation gracieuse.

Cette couche ne fait QUE de l'I/O + validation : aucun calcul (engine).
"""

from __future__ import annotations

import yfinance as yf

from obole import config, observability
from obole.data import cache
from obole.data.yahoo import _with_retry

logger = observability.get_logger(__name__)


def ping() -> dict:
    """Test de liaison : prouve que la couche screener est joignable.

    Renvoie un dict simple, sans I/O. Servi par `/api/screener/ping`.
    """
    return {"ok": True, "service": "screener"}


def fetch_universe(
    min_market_cap: float | None = None,
    sectors: list[str] | None = None,
    force_refresh: bool = False,
) -> dict:
    """Univers des actions françaises (tickers .PA), depuis Yahoo + base de confiance.

    - **Cache d'abord** : clé `UNIVERSE_FR` / kind `universe`, TTL `TTL_UNIVERSE`
      (cohérent avec les prix : pas de re-screen en intra-journée).
    - **Sinon Yahoo** : `yf.screen` paginé (`SCREEN_PAGE_SIZE`) sur
      `region ∈ FR_REGIONS` + `exchange ∈ FR_EXCHANGES` (filtre région seul
      ramène du bruit : warrants, OTC). Pré-filtres optionnels `min_market_cap`
      et `sectors` passés côté Yahoo (passe 1, optionnelle).
    - **Filtre client** : ne garde que les actions (`quoteType == EQUITY`,
      non crypto) et exclut les ETP/obligations détectés par nom
      (`SCREEN_EXCLUDE_MARKERS`).
    - **Fusion** : l'union avec `config.UNIVERSE_FR` garantit que les grandes
      valeurs restent présentes même si le résultat Yahoo est incomplet/bruité.
    - **Fallback** : si Yahoo échoue, on renvoie `UNIVERSE_FR` statique
      (`source == "fallback"`) — jamais de crash. **Note** : en fallback, les
      pré-filtres (`min_market_cap`, `sectors`) ne sont PAS honorés (on renvoie
      l'univers plein). Les clients doivent traiter `source == "fallback"` comme
      un résultat non filtré.

    Renvoie `{"tickers": [...], "count": N, "source": "yahoo"|"cache"|"fallback"}`.
    """
    # Les pré-filtres (capi, secteurs) sont des passes 1 EXPLICITES : on ne peut
    # pas les appliquer à un cache existant (la liste de tickers ne porte pas les
    # capteurs/marchés) -> re-fetch Yahoo filtré, comme `force_refresh`.
    has_filters = min_market_cap is not None or bool(sectors)
    if not force_refresh and not has_filters:
        cached = cache.get("UNIVERSE_FR", "universe", config.TTL_UNIVERSE)
        if cached is not None:
            return cached

    try:
        tickers = _fetch_universe_yahoo(min_market_cap, sectors)
        source = "yahoo"
    except Exception:  # réseau KO, quota, changement d'API… -> dégradation
        logger.warning("Univers screener indisponible : repli sur l'univers local", exc_info=True)
        return {
            "tickers": list(config.UNIVERSE_FR),
            "count": len(config.UNIVERSE_FR),
            "source": "fallback",
        }

    # Fusion : la base de confiance est toujours incluse (union, ordre stable).
    merged = _union(config.UNIVERSE_FR, tickers)
    out = {"tickers": merged, "count": len(merged), "source": source}
    # Le cache ne porte que l'univers PLEIN : un sous-ensemble filtré (passe 1)
    # ne doit pas écraser le cache global, sinon le prochain « tout » serait
    # tronqué. Les appels filtrés sont re-fetched à chaque fois (passe 1
    # explicite, rare ; le scan complet aura son propre cache au J3).
    if not has_filters:
        cache.put("UNIVERSE_FR", "universe", out)
    return out


def _fetch_universe_yahoo(
    min_market_cap: float | None = None,
    sectors: list[str] | None = None,
) -> list[str]:
    """Pagination complète de l'API screener Yahoo pour l'univers FR.

    Boucle `offset` par `SCREEN_PAGE_SIZE` jusqu'à `total` (renvoyé par Yahoo).
    `size` est plafonné à 250 par Yahoo ; un lot vide stoppe la boucle
    (garde-fou si `total` est incohérent).
    """
    clauses: list = [_region_query()]
    if min_market_cap is not None:
        clauses.append(yf.EquityQuery("gte", ["intradaymarketcap", float(min_market_cap)]))
    if sectors:
        clauses.append(yf.EquityQuery("is-in", ["sector", *sectors]))

    query = clauses[0] if len(clauses) == 1 else yf.EquityQuery("and", clauses)

    tickers: list[str] = []
    offset = 0
    total: int | None = None
    while True:
        page = _screen_page(query, offset)
        # Yahoo inaccessible/échec silencieux (rate-limit, format différent…) :
        # un premier lot sans quotes NI total n'est pas un univers vide, c'est
        # une panne — on laisse fetch_universe déclencher le fallback.
        if page in ({}, None):
            raise RuntimeError("API screener Yahoo indisponible")
        quotes = page.get("quotes") or []
        if total is None:
            total = page.get("total") or 0
        for q in quotes:
            t = _ticker_from_quote(q)
            if t is not None:
                tickers.append(t)
        offset += len(quotes)
        if total is None or offset >= total or not quotes:
            break
    return _dedup(tickers)


def _region_query():
    """Requête de base : région FR + bourse Euronext Paris.

    Le filtre région seul (`eq region=fr`) ramène ~6000 titres dont beaucoup de
    warrants/OTC ; le filtre `exchange ∈ FR_EXCHANGES` restreint au marché
    principal de Paris (action principale + quelques valeurs étrangères cotées).
    """
    return yf.EquityQuery(
        "and",
        [
            yf.EquityQuery("is-in", ["region", *config.FR_REGIONS]),
            yf.EquityQuery("is-in", ["exchange", *config.FR_EXCHANGES]),
        ],
    )


def _screen_page(query, offset: int) -> dict:
    """Un lot de résultats (`size` = SCREEN_PAGE_SIZE). `_with_retry` (yahoo.py)."""

    def _fetch():
        return yf.screen(query, size=config.SCREEN_PAGE_SIZE, offset=offset)

    return _with_retry(_fetch, context=f"screen offset={offset}") or {}


def _ticker_from_quote(q: dict) -> str | None:
    """Ticker .PA si l'entrée est une vraie action, sinon None.

    Filtres : quoteType EQUITY, non crypto, symbole commençant par une lettre
    (les certificats/warrants/obligations Paris commencent par un chiffre :
    `1027P.PA`, `0093N.PA`…), nom sans marqueur ETP/obligation (l'API screener
    classe les ETP/trackers en EQUITY aussi — impossible de discriminer autrement
    côté requête, cf. PRD §6 yfinance limité).
    """
    if q.get("quoteType") != "EQUITY":
        return None
    if q.get("cryptoTradeable"):
        return None
    symbol = q.get("symbol") or ""
    if symbol and not symbol[0].isalpha():
        return None
    name = (q.get("shortName") or q.get("longName") or "").lower()
    if any(m in name for m in config.SCREEN_EXCLUDE_MARKERS):
        return None
    return symbol or None


def _union(base: list[str], extra: list[str]) -> list[str]:
    """Union ordonnée (base d'abord, puis extra) sans doublon."""
    seen: set[str] = set()
    out: list[str] = []
    for t in [*base, *extra]:
        t = (t or "").strip().upper()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _dedup(tickers: list[str]) -> list[str]:
    """Dédoublonne en conservant l'ordre."""
    return _union([], tickers)
