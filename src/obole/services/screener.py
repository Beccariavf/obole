"""Cas d'usage « screener » : orchestre l'univers, le scan parallèle et le cache.

Couche `services/` : elle assemble `data/` (I/O : univers Yahoo, prix, cache) et
`engine/` (logique pure : filtre + tri + score) sans logique métier propre. Le
`api/` reste une frontière fine : validation HTTP + sérialisation, jamais de scan.

Ce module porte le cas d'usage complet `run_screen` (passe 1 pré-filtre Yahoo +
passe 2 scan parallèle + cache de scan + filtre/tri à la volée). C'est le point
d'entrée unique, partagé par l'API et le MCP.

Il porte aussi la **validation** des filtres/tri/score (`validate_*`) et le bornage
des pré-filtres (`min_market_cap >= 0`, `regression_window > 0`) : elle vit ici
pour que l'API et le MCP consomment la MÊME règle (le MCP ne peut pas importer
`api/`). Chaque transport traduit le `ValueError` dans son vocabulaire.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass

from obole import config
from obole.data import cache as cache_data
from obole.data import screener as screener_data
from obole.data import yahoo
from obole.engine import screen as screen_engine
from obole.models import ScreenResult
from obole.services import screen as screen_service

# Critères de filtre/tri : SOURCE UNIQUE `engine.screen`, ré-exportée ici pour que
# l'API valide sans importer `engine/` en direct (frontière services/).
FILTERABLE_KEYS = screen_engine.FILTERABLE_KEYS
SORTABLE_KEYS = screen_engine.SORTABLE_KEYS


def validate_min_market_cap(value: object) -> float | None:
    """Valide/coerce `min_market_cap` : nombre **>= 0** (ou str numérique), sinon `ValueError`.

    Un falsy (`None`, `""`, `0`, `"0"`) vaut « non renseigné » -> `None` (l'appelant
    décide alors du défaut serveur ou de l'univers complet). La borne de valeur
    (`>= 0`) est du **métier** : elle vit ici pour que l'API et le MCP appliquent la
    même règle (le MCP ne peut pas importer `api/`). Seule la traduction de l'erreur
    diffère selon le transport (422 HTTP / erreur d'outil).
    """
    if value in (None, "", 0, "0"):
        return None
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise ValueError(f"Capi invalide : {value}")
    try:
        val = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Capi invalide : {value}") from None
    if val < 0:
        raise ValueError(f"Capi invalide : {value}")
    return val


def validate_regression_window(value: object) -> float | None:
    """Valide/coerce `regression_window` : nombre **> 0** (ou str numérique), sinon `ValueError`.

    Un falsy (`None`, `""`, `0`, `"0"`) vaut « non renseigné » -> `None` (historique
    complet). Même frontière partagée API ↔ MCP que `validate_min_market_cap`.
    """
    if value in (None, "", 0, "0"):
        return None
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise ValueError(f"Fenêtre invalide : {value}")
    try:
        val = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Fenêtre invalide : {value}") from None
    if not (val > 0):
        raise ValueError(f"Fenêtre invalide : {value}")
    return val


def validate_filters(filters: object) -> dict | None:
    """Valide `filters` : {critère: (min, max)} sur des clés FILTRABLES connues.

    Un critère inconnu — y compris `score`, qui est un rang calculé et non une
    donnée de marché — une borne invalide ou une structure malformée lève
    `ValueError` (au lieu d'un 500 silencieux dans `engine.screen`). Chaque valeur
    est numérique ou None ; (min, max) ordonnés (min <= max si les deux présents).

    Frontière partagée API ↔ MCP : chaque transport traduit le `ValueError` dans
    son vocabulaire (422 HTTP / erreur d'outil). Entrée hostile par défaut.
    """
    if filters is None:
        return None
    if not isinstance(filters, dict):
        raise ValueError("filters doit être un objet")
    out: dict = {}
    for key, bounds in filters.items():
        if key not in FILTERABLE_KEYS:
            raise ValueError(f"Critère inconnu : {key}")
        if not isinstance(bounds, list | tuple) or len(bounds) != 2:
            raise ValueError(f"Filtre {key} attendu : [min, max]")
        lo, hi = bounds
        for v in (lo, hi):
            if v is not None and not isinstance(v, int | float):
                raise ValueError(f"Borne invalide pour {key} : {v!r}")
        if lo is not None and hi is not None and lo > hi:
            raise ValueError(f"Bornes inversées pour {key}")
        out[key] = (lo, hi)
    return out


def validate_sort_by(sort_by: object) -> list | None:
    """Valide `sort_by` : liste de critères, chacun une clé ou un (clé, sens).

    Sens accepté : "asc"/"desc" (ou la valeur par défaut si clé seule). Lève
    `ValueError` si la structure malformée ou un critère/sens inconnu (cf.
    `validate_filters` pour la frontière partagée API ↔ MCP).
    """
    if sort_by is None:
        return None
    if not isinstance(sort_by, list) or not sort_by:
        raise ValueError("sort_by doit être une liste non vide")
    out: list = []
    for spec in sort_by:
        if isinstance(spec, str):
            key, sens = spec, None
        elif isinstance(spec, list | tuple) and len(spec) == 2:
            key, sens = spec[0], spec[1]
        else:
            raise ValueError(f"Critère de tri invalide : {spec!r}")
        if key not in SORTABLE_KEYS:
            raise ValueError(f"Critère inconnu : {key}")
        if sens is not None and sens not in ("asc", "desc"):
            raise ValueError(f"Sens invalide pour {key} : {sens!r}")
        out.append((key, sens) if sens else key)
    return out


def validate_score_keys(score_keys: object) -> list[str] | None:
    """Valide `score_keys` (#14) : liste de critères du score composite.

    Un critère inconnu est **ignoré** (pas d'erreur : le score est un confort, pas
    une donnée critique — un front en retard ne doit pas casser le scan). Il faut
    au moins 2 critères exploitables pour qu'un score soit calculé.
    """
    if not score_keys:
        return None
    if not isinstance(score_keys, list):
        return None
    return [k for k in score_keys if k in SORTABLE_KEYS]


def validate_max_rows(value: object) -> int | None:
    """Valide `max_rows` : `None` (tout) ou entier **> 0**, sinon `ValueError`.

    Borne de volume d'affichage, donc même frontière partagée API ↔ MCP que les
    autres `validate_*` : la règle vit ici, seule la traduction de l'erreur
    diffère selon le transport (422 HTTP / erreur d'outil MCP). `max_rows` ne
    change NI le scan NI le filtre — il ne fait que borner le tableau rendu.
    """
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"max_rows doit être un entier > 0 ou null : {value!r}")
    return value


@dataclass
class ScreenRun:
    """Résultat d'un scan : lignes filtrées+triées, source et taille brute.

    `rows` est le tableau final (filtre + tri + score appliqués) ;
    `tickers_count` = nombre de tickers scannés AVANT filtre (le cache de scan).
    """

    rows: list[ScreenResult]
    source: str
    tickers_count: int


def run_screen(
    *,
    min_market_cap: float | None,
    sectors: list[str] | None,
    regression_window: float | None,
    filters: dict[str, tuple[float | None, float | None]] | None = None,
    sort_by: list | None = None,
    score_keys: list[str] | None = None,
) -> ScreenRun:
    """Exécute un scan Obole sur l'univers FR, avec cache de scan.

    Passe 1 (`screener_data.fetch_universe`) : pré-filtre Yahoo facultatif
    (`min_market_cap`, `sectors`) + base de confiance. Passe 2 (`_scan_universe`) :
    `yahoo.fetch_prices` + `screen_service.screen_stock` (aucune formule ici — tout
    passe par `engine/`). Un ticker cassé est isolé dans `ScreenResult.error`,
    jamais de crash global.

    Le tableau triable brut (non filtré/non trié) est mis en cache SQLite, clé
    dérivée de (min_market_cap, sectors, regression_window), TTL `TTL_UNIVERSE` :
    un changement de tri/filtre ne re-scanne pas. La clé de cache est INCHANGÉE
    depuis l'implémentation inline précédente (un cache chaud reste exploité).
    """
    cache_key = (
        f"SCREEN:{float(min_market_cap or 0)}:{','.join(sectors or [])}:{regression_window or 0}"
    )
    cached = cache_data.get(cache_key, "screen", config.TTL_UNIVERSE)
    if cached is not None:
        raw_screens: dict[str, dict] = cached["results"]
        source: str = "cache"
    else:
        universe = screener_data.fetch_universe(min_market_cap=min_market_cap, sectors=sectors)
        raw_screens = _scan_universe(universe["tickers"], regression_window)
        source = universe["source"]
        if raw_screens:
            cache_data.put(cache_key, "screen", {"results": raw_screens, "source": source})

    rows = [ScreenResult(**raw) for raw in raw_screens.values()]
    rows = screen_engine.filter_and_sort(
        rows, filters=filters, sort_by=sort_by, score_keys=score_keys
    )
    return ScreenRun(rows=rows, source=source, tickers_count=len(raw_screens))


def _scan_universe(tickers: list[str], regression_window: float | None) -> dict[str, dict]:
    """Passe 2 : réduit chaque ticker de l'univers en ScreenResult dict.

    I/O-bound (yfinance) -> exécuté en **parallèle** via un ThreadPoolExecutor
    borné (`config.SCREEN_WORKERS`). Un ticker introuvable ou une série trop
    courte est isolé via le champ `error` de screen_stock — jamais de crash
    global. Garde-fou GLOBAL : au-delà d'un budget `SCREEN_WORKERS ×
    SCREEN_FETCH_TIMEOUT`, les tickers non-aboutis sont isolés `error="timeout"`
    et le pool est arrêté sans attendre (`shutdown(wait=False)`) : les threads
    déjà lancés ne sont PAS préemptables, mais on ne bloque pas le scan sur eux.
    Les vrais bugs (TypeError…) restent visibles via `fut.result()`.
    """
    screens: dict[str, dict] = {}

    def _one(ticker: str) -> tuple[str, dict]:
        try:
            prices = yahoo.fetch_prices(ticker)
        except yahoo.TickerNotFound as exc:
            return ticker.upper(), ScreenResult(ticker=ticker.upper(), error=str(exc)).__dict__
        result = screen_service.screen_stock(ticker, prices, regression_window)
        return ticker.upper(), result.__dict__

    # Budget GLOBAL (secondes) : filet anti-scan-infini, PAS une limite par
    # ticker. `shutdown(wait=False)` évite qu'un thread en cours (réseau sans
    # timeout propre) bloque le retour ; un futur inachevé est isolé en erreur.
    budget = config.SCREEN_WORKERS * config.SCREEN_FETCH_TIMEOUT
    pool = ThreadPoolExecutor(max_workers=config.SCREEN_WORKERS)
    try:
        futures = {pool.submit(_one, t): t for t in tickers}
        done, pending = wait(futures, timeout=budget)
        for fut in done:
            key, val = fut.result()  # les vraies exceptions remontent (visibles)
            screens[key] = val
        for fut in pending:
            fut.cancel()
            ticker = futures[fut]
            screens[ticker.upper()] = ScreenResult(ticker=ticker.upper(), error="timeout").__dict__
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return screens
