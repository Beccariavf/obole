"""API FastAPI — fine couche d'orchestration. Sert le front + l'endpoint JSON."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse

from obole import config, observability
from obole.api.static_files import VersionedStaticFiles, render_index
from obole.api.uploads import read_bounded
from obole.data import backup as backup_data
from obole.data import cache as cache_data
from obole.data import events as events_data
from obole.data import health as health_data
from obole.data import manual as manual_data
from obole.data import portfolio as portfolio_data
from obole.data import screener as screener_data
from obole.data import thesis_assets, yahoo
from obole.services import checkpoints as checkpoints_service
from obole.services import imports as imports_service
from obole.services import indices as indices_service
from obole.services import portfolio as portfolio_service
from obole.services import screener as screener_service
from obole.services import thesis as thesis_service
from obole.services import watchlist as watchlist_service
from obole.services.analysis import analyze_ratio_tickers, analyze_ticker, summarize_indices
from obole.services.checkpoints import CheckpointNotFound
from obole.services.indices import IndexNotFound
from obole.services.serialize import (
    analysis_to_dict,
    basket_to_dict,
    portfolio_correlation_test_to_dict,
    portfolio_dividend_page_to_dict,
    portfolio_performance_to_dict,
    portfolio_positions_to_list,
    portfolio_risk_to_dict,
    portfolio_summary_to_dict,
    ratio_to_dict,
    screen_run_to_dict,
    security_detail_to_dict,
    summarize_index_to_dict,
    watchlist_run_to_dict,
    watchlist_state_to_dict,
)
from obole.services.thesis import ThesisNotFound

_UNSET = object()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    observability.configure_logging()
    # Pas de message « prêt » ici : il annoncerait un host/port devinés (l'app ne
    # connaît pas son bind) et s'afficherait même quand le bind échoue. C'est
    # `__main__._serve` qui l'émet, une fois le serveur réellement à l'écoute.
    yield


app = FastAPI(title="Obole", docs_url="/api/docs", lifespan=lifespan)


@app.middleware("http")
async def security_headers(request, call_next):
    """En-têtes de durcissement : front servi localement, aucun CDN.

    L'app n'a pas d'authentification et vit sur la boucle locale ; ces en-têtes
    sont une défense en profondeur, pas une barrière. La CSP autorise l'`inline`
    de style (Plotly et Alpine écrivent des attributs `style`) mais **pas**
    l'`inline` de script : tout le JS du front vient de `/static/`, versionné
    par hash de contenu.

    Seule exception : `/api/docs` charge Swagger UI depuis un CDN (comportement
    par défaut de FastAPI). La page est une aide au développement, jamais
    utilisée par le front — on lui accorde le CDN sans élargir la politique de
    l'application elle-même.
    """
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path.startswith("/api/docs"):
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https://fastapi.tiangolo.com; "
            "frame-ancestors 'none'; "
            "base-uri 'self'",
        )
        return response
    response.headers.setdefault(
        "Content-Security-Policy",
        # `script-src 'unsafe-eval'` est imposé par Alpine.js : le front n'a pas
        # de build, donc les expressions `x-text`/`x-show` sont évaluées à
        # l'exécution via `new Function()`. Sans `unsafe-eval`, Alpine ne démarre
        # pas et la page reste vide (vérifié en navigateur : `PAGEERROR … violates
        # the following Content Security Policy directive`).
        #
        # Ce que la politique conserve malgré cela : aucun script inline (tout le
        # JS vient de `/static/`), aucun CDN, aucun `frame-ancestors`. Le gain
        # réel porte sur l'injection de balises `<script>` distantes ou inline —
        # pas sur l'évaluation dynamique, intrinsèque au framework choisi.
        "default-src 'self'; "
        "script-src 'self' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'",
    )
    return response


WEB_DIR = Path(__file__).resolve().parents[1] / "web"


@app.get("/api/stock/{ticker}")
def get_stock(ticker: str) -> dict:
    """Analyse complète d'une valeur. 404 si ticker inconnu."""
    try:
        analysis, prices = analyze_ticker(ticker)
    except yahoo.TickerNotFound:
        raise HTTPException(status_code=404, detail=f"Ticker introuvable : {ticker}") from None
    except ValueError as exc:  # historique trop court, etc.
        raise HTTPException(status_code=422, detail=str(exc)) from None

    payload = analysis_to_dict(analysis, prices)
    # État watchlist (#25) ajouté ICI, jamais dans `analyze()` : c'est de l'état
    # utilisateur, pas de l'analyse (le payload MCP de la thèse reste propre).
    return watchlist_service.decorate_stock_payload(payload, analysis.identity.ticker, prices)


@app.get("/api/ratio")
def get_ratio(a: str, b: str) -> dict:
    """Analyse d'un ratio A/B entre deux actifs (ETF, indices…). 404 si inconnu."""
    try:
        analysis, series, sa, sb = analyze_ratio_tickers(a, b)
    except yahoo.TickerNotFound as exc:
        raise HTTPException(status_code=404, detail=f"Ticker introuvable : {exc}") from None
    except ValueError as exc:  # historique commun trop court, dénominateur nul…
        raise HTTPException(status_code=422, detail=str(exc)) from None

    return ratio_to_dict(analysis, series, sa, sb)


@app.get("/api/search")
def get_search(q: str = "") -> list[dict]:
    """Autocomplétion nom/ticker pour la barre de recherche."""
    return yahoo.search(q)


@app.post("/api/refresh/{ticker}")
def post_refresh(ticker: str) -> dict:
    """Refresh manuel : purge le cache du ticker."""
    yahoo.refresh(ticker)
    return {"status": "ok", "ticker": ticker.upper()}


# --- Indices personnalisés ---------------------------------------------------


@app.get("/api/indices")
def get_indices() -> list[dict]:
    """Catégories + indices personnalisés (définitions, aucun calcul)."""
    return indices_service.list_indices()


@app.get("/api/index/{index_id}")
def get_index(index_id: int) -> dict:
    """Analyse complète d'un indice personnalisé. 404 si inconnu."""
    try:
        analysis, series = indices_service.analyze_index(index_id)
    except IndexNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except yahoo.TickerNotFound as exc:
        raise HTTPException(status_code=404, detail=f"Ticker introuvable : {exc}") from None
    except ValueError as exc:  # panier trop court, membre sans prix…
        raise HTTPException(status_code=422, detail=str(exc)) from None

    return basket_to_dict(analysis, series)


@app.post("/api/index/{index_id}/refresh")
def post_index_refresh(index_id: int) -> dict:
    """Refresh d'un indice : purge les prix de ses membres ET sa série cachée."""
    try:
        indices_service.refresh_index(index_id)
    except IndexNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return {"status": "ok", "index_id": index_id}


def _flat_index_definitions() -> list[dict]:
    """Définitions aplaties (indice -> {id, name, tickers, category_id})."""
    return indices_service.flat_definitions()


@app.get("/api/indices/summary")
def get_indices_summary() -> list[dict]:
    """Stats « coup d'œil » de tous les indices (position σ, pente, tendance).

    Calcul à la volée depuis les prix cachés (TTL prix) : rapide à chaud, aucun
    purge. Chaque indice est traité indépendamment (`error` en cas d'échec).
    """
    return [summarize_index_to_dict(e) for e in summarize_indices(_flat_index_definitions())]


@app.post("/api/indices/summary/refresh")
def post_indices_summary_refresh(body: dict | None = None) -> list[dict]:
    """Recalcule les stats (position σ, pente, tendance) : purge prix membres +
    série cachée du périmètre.

    `body` facultatif : {"category_id": int} limite le refresh à une catégorie
    (bouton ↻ de catégorie) ; sans body, toutes les catégories (« Tout rafraîchir »).
    Un ticker partagé par plusieurs indices n'est purgé qu'une seule fois (un
    seul appel réseau par membre du périmètre).
    Réponse : les stats fraîches, indice par indice (`error` isolée).
    """
    category_id = None
    if body and body.get("category_id") is not None:
        category_id = int(body["category_id"])
    definitions = _flat_index_definitions()
    if category_id is not None:
        definitions = [d for d in definitions if d["category_id"] == category_id]
    for d in definitions:
        indices_service.purge_index_series(d["id"])
    for ticker in {t for d in definitions for t in d["tickers"]}:
        yahoo.refresh(ticker)
    return [summarize_index_to_dict(e) for e in summarize_indices(definitions)]


@app.post("/api/indices/categories")
def post_index_category(body: dict) -> dict:
    """Crée une catégorie d'indices : {"name": str}."""
    try:
        cat_id = indices_service.create_category(body.get("name"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return {"status": "ok", "id": cat_id}


@app.delete("/api/indices/categories/{category_id}")
def delete_index_category(category_id: int) -> dict:
    """Supprime une catégorie et ses indices."""
    try:
        indices_service.delete_category(category_id)
    except IndexNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return {"status": "deleted", "category_id": category_id}


@app.post("/api/indices")
def post_index(body: dict) -> dict:
    """Crée un indice : {"category_id": int, "name": str, "tickers": [str]}."""
    try:
        idx_id = indices_service.create_index(
            body.get("category_id"), body.get("name"), body.get("tickers") or []
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return {"status": "ok", "id": idx_id}


@app.put("/api/indices/{index_id}")
def put_index(index_id: int, body: dict) -> dict:
    """Remplace la définition complète d'un indice."""
    try:
        indices_service.update_index(
            index_id,
            body.get("category_id"),
            body.get("name"),
            body.get("tickers") or [],
        )
    except IndexNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return {"status": "ok", "id": index_id}


@app.delete("/api/indices/{index_id}")
def delete_index(index_id: int) -> dict:
    """Supprime un indice."""
    try:
        indices_service.delete_index(index_id)
    except IndexNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return {"status": "deleted", "index_id": index_id}


# --- Événements (annotations datées des graphiques) --------------------------
# Le ref d'un ratio contient un « / » (ex. CW8/RI) que Starlette décode AVANT le
# routage : un ref dans le chemin casserait la route. Il passe donc en query
# params (`?a=&b=`), même pattern que /api/ratio ; stock/index restent en chemin.


@app.get("/api/events/{kind}")
def get_events(
    kind: str, ref: str | None = None, a: str | None = None, b: str | None = None
) -> list[dict]:
    """Liste les événements annotés d'un graphe (stock / ratio / index).

    Ratio : `?a=CW8&b=RI` (le « / » du ref est interdit dans un segment de chemin).
    Stock / index : `?ref=RI.PA` / `?ref=3`.
    """
    try:
        return events_data.list_events(kind, _event_ref(kind, ref, a, b))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@app.post("/api/events/{kind}")
def post_event(
    kind: str, body: dict, ref: str | None = None, a: str | None = None, b: str | None = None
) -> dict:
    """Crée un événement : {"date": "AAAA-MM-JJ", "label": str, "description"?: str}.

    Cible du graphe : `?ref=...` (stock/index) ou `?a=...&b=...` (ratio).
    """
    try:
        event_id = events_data.add_event(
            kind,
            _event_ref(kind, ref, a, b),
            body.get("date"),
            body.get("label"),
            body.get("description"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return {"status": "ok", "id": event_id}


def _event_ref(kind: str, ref: str | None, a: str | None, b: str | None) -> str:
    """Ref cible selon le kind : ratio -> "A/B", sinon `ref` obligatoire."""
    if kind == "ratio":
        if not a or not b:
            raise ValueError("Ratio : paramètres a et b requis")
        return f"{a}/{b}"
    if not ref:
        raise ValueError(f"Paramètre ref requis pour {kind}")
    return ref


@app.put("/api/events/{event_id}")
def put_event(event_id: int, body: dict) -> dict:
    """Modifie un événement (mêmes champs que la création). 404 si inconnu."""
    if cache_data.get_event(event_id) is None:
        raise HTTPException(status_code=404, detail=f"Événement inconnu : {event_id}")
    try:
        events_data.update_event(
            event_id, body.get("date"), body.get("label"), body.get("description")
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return {"status": "ok", "id": event_id}


@app.delete("/api/events/{event_id}")
def delete_event(event_id: int) -> dict:
    """Supprime un événement."""
    try:
        events_data.delete_event(event_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return {"status": "deleted", "id": event_id}


# --- Données manuelles -------------------------------------------------------


@app.get("/api/manual/{ticker}")
def get_manual(ticker: str) -> list[dict]:
    """Liste les entrées manuelles d'un ticker."""
    return manual_data.get_manual(ticker)


@app.post("/api/manual/{ticker}")
def post_manual(ticker: str, entries: list[dict]) -> dict:
    """Ajoute/remplace des entrées manuelles (batch JSON).

    Chaque entrée: {"year": int, "metric": str, "value": float}
    """
    for e in entries:
        year = e.get("year")
        metric = e.get("metric")
        value = e.get("value")
        if (
            not isinstance(year, int)
            or not isinstance(metric, str)
            or not isinstance(value, int | float)
        ):
            raise HTTPException(status_code=400, detail="Entrée invalide : {year}/{metric}/{value}")
    manual_data.upsert_manual(ticker, entries)
    yahoo.refresh(ticker)
    return {"status": "ok", "ticker": ticker.upper(), "entries": len(entries)}


@app.get("/api/manual/{ticker}/template")
def get_manual_template(ticker: str) -> PlainTextResponse:
    """CSV template exhaustif, pré-rempli avec les données yfinance + manuelles.

    Une colonne par métrique du tableau des comptes (postes source éditables +
    ratios dérivés en lecture seule), ordonnées selon `config.FUNDAMENTAL_METRICS`.
    """
    try:
        prices = yahoo.fetch_prices(ticker)
        identity = yahoo.fetch_identity(ticker, float(prices.raw.iloc[-1]))
        fundamentals = yahoo.fetch_fundamentals(ticker, identity.kind)
    except yahoo.TickerNotFound:
        raise HTTPException(status_code=404, detail=f"Ticker introuvable : {ticker}") from None

    yf_years = []
    # Colonnes = toutes les métriques du tableau réel (source + dérivé) : le
    # template reflète exactement ce que l'app affiche (pré-rempli yfinance).
    table_metrics = list(fundamentals.table.index) if fundamentals is not None else []
    if fundamentals is not None:
        yf_years = list(fundamentals.table.columns)

    manual = manual_data.get_manual_dict(ticker)
    for y in yf_years:
        manual.setdefault(y, {})
        if fundamentals is not None and y in fundamentals.table.columns:
            for m in table_metrics:
                v = fundamentals.table.at[m, y]
                if pd.notna(v) and m not in manual[y]:
                    manual[y][m] = float(v)

    csv_content = manual_data.export_csv(
        ticker, yf_years, manual_override=manual, metrics=table_metrics
    )
    fname = f"{ticker.upper()}_comptes.csv"
    return PlainTextResponse(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.post("/api/manual/{ticker}/csv")
async def post_manual_csv(ticker: str, file: UploadFile) -> dict:
    """Import d'un CSV de données manuelles — renvoie le **rapport** d'import.

    Le parsing tolère les formats réels (délimiteur `;`/tab, nombres FR/US) et
    rapporte ce qui a été accepté, écrasé et **rejeté (avec la raison)**, au lieu
    du silence d'un `float()` qui échoue. La clé `entries` (int) est conservée
    pour la compatibilité du front.
    """
    content = await read_bounded(file, config.UPLOAD_MAX_CSV_BYTES, "Fichier CSV")
    csv_text = content.decode("utf-8-sig")
    report = manual_data.import_csv(ticker, csv_text)
    if not report.entries:
        # `detail` reste une CHAÎNE (homogénéité avec les autres routes) : le
        # motif de rejet est résumé dedans, le détail complet est dans le rapport.
        reasons = (
            ", ".join(sorted({r.reason for r in report.rejected})) or "aucune colonne reconnue"
        )
        raise HTTPException(
            status_code=400,
            detail=f"Aucune entrée valide dans le CSV ({reasons})",
        )
    manual_data.upsert_manual(ticker, report.entries)
    # Purge le cache du ticker pour que le prochain /api/stock merge les données.
    yahoo.refresh(ticker)
    # `entries` (int) = nombre de valeurs écrites (compatibilité du front) ; le
    # rapport complet (rejets, colonnes ignorées) est ajouté à côté.
    return {
        "status": "ok",
        "ticker": ticker.upper(),
        "entries": report.accepted,
        **report.summary(),
        "rejected": report.to_dict()["rejected"],
    }


# --- Import piloté (#23) -----------------------------------------------------
# Staging : une IA (via le MCP) ou un collage propose un import, l'utilisateur le
# valide ici. `apply` est une route REST uniquement — aucun outil MCP ne l'expose.


@app.get("/api/imports")
def get_imports(status: str = "pending") -> list[dict]:
    """Brouillons d'import d'un statut (métadonnées, du plus récent au plus ancien)."""
    return imports_service.list_drafts(status)


@app.post("/api/imports/propose")
def post_import_propose(body: dict) -> dict:
    """Propose un import (crée un brouillon `pending`) — miroir HTTP de l'outil MCP.

    Même cas d'usage que `propose_import` côté MCP : le collage de la modale
    passe par ici, donc **aucune** écriture métier directe — l'utilisateur valide
    ensuite via `POST /api/imports/{id}/apply`. L'entrée est hostile par défaut.
    """
    try:
        return imports_service.propose_import(
            body.get("target"), body.get("ref"), body.get("csv_text")
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@app.get("/api/imports/{draft_id}")
def get_import(draft_id: int) -> dict:
    """Brouillon d'import complet (rapport inclus)."""
    try:
        return imports_service.get_draft(draft_id)
    except imports_service.ImportDraftNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@app.post("/api/imports/{draft_id}/apply")
def post_import_apply(draft_id: int) -> dict:
    """Applique un brouillon d'import (écriture métier) — acte de l'utilisateur."""
    try:
        return imports_service.apply_draft(draft_id)
    except imports_service.ImportDraftNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@app.delete("/api/imports/{draft_id}")
def delete_import(draft_id: int) -> dict:
    """Rejette un brouillon d'import (statut `rejected`, aucun effet métier)."""
    try:
        return imports_service.discard_draft(draft_id)
    except imports_service.ImportDraftNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@app.delete("/api/manual/{ticker}/{year}")
def delete_manual_year(ticker: str, year: int) -> dict:
    """Supprime une année de données manuelles."""
    manual_data.delete_manual_year(ticker, year)
    yahoo.refresh(ticker)
    return {"status": "deleted", "ticker": ticker.upper(), "year": year}


# --- Screener -----------------------------------------------------------------


@app.get("/api/screener/ping")
def screener_ping() -> dict:
    """Test de liaison screener (J0) : la couche est joignable."""
    return screener_data.ping()


@app.get("/api/screener/universe")
def screener_universe(min_market_cap: float | None = None, sectors: str | None = None) -> dict:
    """Univers des actions françaises (J1).

    `min_market_cap` : pré-filtre optionnel côté Yahoo (passe 1).
    `sectors` : liste de secteurs séparés par des virgules (optionnel).
    Réponse : `{"tickers": [...], "count": N, "source": "yahoo"|"cache"|"fallback"}`.
    """
    sector_list = [s.strip() for s in sectors.split(",") if s.strip()] if sectors else None
    return screener_data.fetch_universe(min_market_cap=min_market_cap, sectors=sector_list)


@app.get("/api/screener/meta")
def screener_meta() -> dict:
    """Métadonnées de colonnes du screener (source unique, aucun duplicat côté front).

    Renvoie la direction de tri « bon premier » par critère (`sort_desc`) et les
    seuils de couleur (`colors`, depuis config.SCREEN_COLORS). Le front construit
    ses en-têtes, ses sens par défaut et ses couleurs À PARTIR d'ici : il n'a
    aucun seuil ni direction en dur.
    """
    return {
        "sort_desc": config.SCREEN_SORT_DESC,
        "colors": {
            key: {"sens": sens, "seuil": seuil}
            for key, (sens, seuil) in config.SCREEN_COLORS.items()
        },
    }


def _cast_window(regression_window) -> float | None:
    """Valide/coerce `regression_window` (422) — règle portée par `services/`.

    Tolère une chaîne numérique (le front peut encore envoyer tout ou rien) et un
    falsy (`""`, 0, null) traité comme absent -> None (historique complet).
    """
    try:
        return screener_service.validate_regression_window(regression_window)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


def _cast_capi(min_market_cap) -> float | None:
    """Valide/coerce `min_market_cap` (422) — règle portée par `services/`.

    Renvoie la valeur numérique ; None si absent/falsy (l'appelant veut l'univers
    complet ou le défaut serveur). 422 uniquement si non coercible ou négative.
    """
    try:
        return screener_service.validate_min_market_cap(min_market_cap)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


def _validate_filters(filters) -> dict | None:
    """Valide `filters` à la frontière HTTP (422) — règle portée par `services/`.

    La règle vit dans `services.screener.validate_filters` (partagée API ↔ MCP) ;
    ici on ne fait que traduire le `ValueError` métier en 422 HTTP.
    """
    try:
        return screener_service.validate_filters(filters)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


def _validate_sort_by(sort_by) -> list | None:
    """Valide `sort_by` à la frontière HTTP (422) — règle portée par `services/`."""
    try:
        return screener_service.validate_sort_by(sort_by)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


def _validate_score_keys(score_keys) -> list[str] | None:
    """Valide `score_keys` (#14) — règle portée par `services/` (critères inconnus ignorés)."""
    return screener_service.validate_score_keys(score_keys)


@app.post("/api/screener/run")
def screener_run(body: dict | None = None) -> dict:
    """Exécute un scan Obole sur l'univers FR (J3).

    Frontière fine : valide le body (422), délègue le cas d'usage à
    `services.screener.run_screen` (passe 1 univers + passe 2 scan parallèle +
    cache + filtre/tri), puis sérialise. Aucune formule ni orchestration ici.

    `body` (tout optionnel) :
      - `min_market_cap` (float|null) : défaut `SCREEN_DEFAULT_MIN_CAP` (1 Md€,
        scan rapide) ; null = univers complet.
      - `sectors` (list[str]|null) : pré-filtre passe 1.
      - `regression_window` (int|null) : années pour σ/pente/potentiels ; null =
        historique complet (décision J2).
      - `filters` / `sort_by` / `score_keys` : appliqués par le moteur pur
        (`engine.screen.filter_and_sort`, via le service), à la volée, servi
        depuis le cache de scan.
      - `max_rows` (int|null) : borne du nombre de lignes RENDUES ; `count` et
        `tickers_count` restent les totaux réels. null = toutes les lignes.
        Même validation que l'outil MCP (`services.screener.validate_max_rows`).

    Réponse : `{"source", "count", "tickers_count", "rows": [dict]}` où `rows`
    est filtré+trié.
    """
    body = body or {}
    min_market_cap = body.get("min_market_cap", _UNSET)
    if min_market_cap is _UNSET:
        min_market_cap = config.SCREEN_DEFAULT_MIN_CAP
    else:
        # Défaut : null explicite = univers complet (AUCUNE capi minimale) ;
        # sinon on coercit (nombre ou chaîne numérique), 422 si invalide.
        min_market_cap = _cast_capi(min_market_cap)

    run = screener_service.run_screen(
        min_market_cap=min_market_cap,
        sectors=body.get("sectors"),
        regression_window=_cast_window(body.get("regression_window")),
        filters=_validate_filters(body.get("filters")),
        sort_by=_validate_sort_by(body.get("sort_by")),
        score_keys=_validate_score_keys(body.get("score_keys")),
    )
    # `max_rows` : borne du tableau RENDU (`count`/`tickers_count` restent les
    # totaux). La validation est partagée avec le MCP (`services.screener`).
    try:
        max_rows = screener_service.validate_max_rows(body.get("max_rows"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return screen_run_to_dict(run, max_rows=max_rows)


@app.get("/api/meta")
def get_meta() -> dict:
    """Seuils calibrés exposés au front — SOURCE UNIQUE (`config.py`).

    Le front ne redéfinit plus aucun seuil : il lit ce payload au démarrage
    (`app.js::applyMeta`) et calcule ses labels/couleurs à partir d'ici. Modifier
    un seuil dans `config.py` le propage au front sans toucher au JS.

    Contenu : listes de labels (`labels`), polarité couleur (`label_polarity`),
    seuils des ratios fondamentaux (`ratio_thresholds`), fenêtres de régression
    non synchronisée (`reg_years_default`/`reg_years_financial`), seuils de
    fiabilité β/ρ (`beta_min_points`/`corr_min_points`), horizons de potentiel,
    **taxonomie des cartes du Quantitatif** (`quant_groups`), **taxonomie de la
    section Dividende** (`dividend_groups`), polarité couleur du dividende
    (`dividend_colors`) et unité d'affichage par métrique (`metric_units`,
    complétée par les unités du dividende).
    """
    return {
        "labels": {
            "distance": config.DISTANCE_SIGMA_LABELS,
            "ecart": config.ECART_TYPE_LABELS,
            "perf": config.PERF_LABELS,
            "potential": config.POTENTIAL_LABELS,
            "beta": config.BETA_LABELS,
            "corr": config.CORR_LABELS,
        },
        "label_polarity": config.LABEL_POLARITY,
        "ratio_thresholds": config.RATIO_THRESHOLDS,
        "reg_years_default": config.REGRESSION_YEARS_DEFAULT,
        "reg_years_financial": config.REGRESSION_YEARS_FINANCIAL,
        "beta_min_points": config.BETA_MIN_POINTS,
        "corr_min_points": config.CORR_MIN_POINTS,
        "potential_horizons": list(config.POTENTIAL_HORIZONS),
        # Clara Vallis (#30) : fenêtre de la foule, bornes de satisfaction
        # calibrées et fenêtres du sélecteur. Aucune valeur côté JS.
        "momentum": {
            "window": config.MOMENTUM_WINDOW,
            "low": config.MOMENTUM_SATISFACTION_LOW,
            "high": config.MOMENTUM_SATISFACTION_HIGH,
            "table_windows": list(config.MOMENTUM_TABLE_WINDOWS),
        },
        "quant_groups": config.QUANT_GROUPS,
        "dividend_groups": config.DIVIDEND_GROUPS,
        # Page Dividende du PORTEFEUILLE (#17.5) : taxonomie des tuiles KPI,
        # polarité couleur et unités — même source unique que le reste.
        "portfolio_dividend_groups": config.PORTFOLIO_DIVIDEND_GROUPS,
        "portfolio_dividend_polarity": config.PORTFOLIO_DIVIDEND_POLARITY,
        "portfolio_dividend_units": config.PORTFOLIO_DIVIDEND_METRIC_UNITS,
        # Échelle visuelle de la micro-barre « Écart » (points de %) : le front ne
        # code pas cette amplitude en dur, il lit `config.py`.
        "portfolio_dividend_gap_scale_pp": config.PORTFOLIO_DIVIDEND_GAP_SCALE_PP,
        # Stats agrégées de la Performance (#17.4) : taxonomie (ordre, libellés,
        # unités, sens) rendue par le front, source unique `config.py`.
        "portfolio_stat_groups": config.PORTFOLIO_STAT_GROUPS,
        "portfolio_months": config.PORTFOLIO_MONTHS,
        "dividend_colors": config.DIVIDEND_COLORS,
        "dividend_cagr_horizons": list(config.DIVIDEND_CAGR_HORIZONS),
        "dividend_default_window_years": config.DIVIDEND_DEFAULT_WINDOW_YEARS,
        "dividend_min_window_years": config.DIVIDEND_MIN_WINDOW_YEARS,
        "chart_heights": {
            "hero": config.CHART_HEIGHT_HERO,
            "mini": config.CHART_HEIGHT_MINI,
            "dividend_hero": config.CHART_HEIGHT_DIVIDEND_HERO,
            "valuation_hero": config.CHART_HEIGHT_VALUATION_HERO,
            "momentum_year": config.CHART_HEIGHT_MOMENTUM_YEAR,
            "momentum_history": config.CHART_HEIGHT_MOMENTUM_HISTORY,
            "portfolio_resume": config.CHART_HEIGHT_PORTFOLIO_RESUME,
            "portfolio_donut": config.CHART_HEIGHT_PORTFOLIO_DONUT,
            "portfolio_drawdown": config.CHART_HEIGHT_PORTFOLIO_DRAWDOWN,
            "portfolio_corr": config.CHART_HEIGHT_PORTFOLIO_CORR,
            "portfolio_corr_test": config.CHART_HEIGHT_PORTFOLIO_CORR_TEST,
            "portfolio_monthly": config.CHART_HEIGHT_PORTFOLIO_MONTHLY,
            "portfolio_contrib": config.CHART_HEIGHT_PORTFOLIO_CONTRIB,
            "portfolio_dividends": config.CHART_HEIGHT_PORTFOLIO_DIVIDENDS,
            "portfolio_div_conc": config.CHART_HEIGHT_PORTFOLIO_DIV_CONC,
            "portfolio_div_conc_row": config.CHART_HEIGHT_PORTFOLIO_DIV_CONC_ROW,
            "portfolio_div_conc_pad": config.CHART_HEIGHT_PORTFOLIO_DIV_CONC_PAD,
            "detail": config.CHART_HEIGHT_DETAIL,
        },
        "metric_units": {**config.METRIC_UNITS, **config.DIVIDEND_METRIC_UNITS},
        # Taxonomie des comptes (document financier CSV) : {nom, rôle}. Union des
        # deux schémas (industriel + financier) : le front lit cette liste pour
        # l'aperçu d'import — aucun nom de métrique en dur dans `web/exportcsv.js`.
        "fundamental_metrics": [{"name": n, "role": r} for n, r in config.FUNDAMENTAL_METRICS_ALL],
        "valuation_metrics": config.VALUATION_METRICS,
        "valuation_groups": config.VALUATION_GROUPS,
        "valuation_horizon_years": config.VALUATION_HORIZON_YEARS,
        "valuation_target_default": config.VALUATION_TARGET_YIELD_DEFAULT,
        "valuation_periods": list(config.VALUATION_PERIODS),
        "valuation_period_default": config.VALUATION_PERIOD_DEFAULT,
        "valuation_matrix": {
            "rows": config.VALUATION_MATRIX_ROWS,
            "cols": config.VALUATION_MATRIX_COLS,
            "growth_step": config.VALUATION_MATRIX_GROWTH_STEP,
            "multiple_step": config.VALUATION_MATRIX_MULTIPLE_STEP,
        },
        "valuation_color_ratios": list(config.VALUATION_COLOR_RATIOS),
        # Bornes des libellés de points de contrôle suivis (#21) : le champ de
        # saisie du front lit `maxlength` ici, jamais une constante en dur.
        "checkpoint_label_max": config.CHECKPOINT_LABEL_MAX,
        # Étiquettes du portefeuille (#17.6) : borne du libellé (miroir de la
        # validation de `data/portfolio`), lue par le `maxlength` du champ.
        "portfolio_tag_max": config.PORTFOLIO_TAG_MAX,
        # Risque du portefeuille (#17.3) : observations minimales par paire
        # (lignes sous ce seuil écartées de la matrice, badge explicite) et seuil
        # au-delà duquel la heatmap masque les annotations (cellules illisibles).
        "portfolio_corr_min_obs": config.PORTFOLIO_CORR_MIN_OBS,
        "portfolio_corr_annotate_max": config.PORTFOLIO_CORR_ANNOTATE_MAX,
        # Watchlist (#25) : tiers fixes, point minimal d'une fenêtre de confiance
        # et plafond de valeurs. Le front n'écrit aucun de ces nombres en dur.
        "watch": {
            "tiers": [dict(t) for t in config.WATCH_TIERS],
            "min_ref_points": config.REGRESSION_MIN_POINTS,
            "max_items": config.WATCHLIST_MAX_ITEMS,
        },
    }


@app.get("/api/summary-meta")
def get_summary_meta() -> dict:
    """Seuils de la grille de synthèse (section Résumé) — SOURCE UNIQUE config.py.

    Séparé de `/api/meta` (dont la liste de champs est verrouillée par un test de
    parité) : le front charge ce payload pour colorer les lignes de la synthèse
    sans redéfinir aucun seuil. Catégories de capitalisation, zones Altman Z et
    Piotroski, polarité couleur par ligne.
    """
    return {
        "market_cap_labels": config.MARKET_CAP_LABELS,
        "altman_zones": config.ALTMAN_ZONES,
        "piotroski_zones": config.PIOTROSKI_ZONES,
        "summary_colors": config.SUMMARY_COLORS,
    }


# --- Portefeuille (#17) ------------------------------------------------------
# Frontière fine : valide le body (422), délègue le cas d'usage à
# `services/portfolio` (point d'entrée unique, partagé avec le futur MCP-B) —
# l'API ne touche jamais `data/portfolio` en direct. `NotFoundError` (sous-classe
# de ValueError, levée par la couche data) donne un 404 distinct d'un 422.


@app.get("/api/portfolio/accounts")
def get_portfolio_accounts() -> list[dict]:
    """Comptes du portefeuille."""
    return portfolio_service.accounts()


@app.post("/api/portfolio/accounts")
def post_portfolio_account(body: dict) -> dict:
    """Crée un compte : {"name": str, "currency"?: str}."""
    try:
        account_id = portfolio_service.create_account(body.get("name"), body.get("currency"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return {"status": "ok", "id": account_id}


@app.delete("/api/portfolio/accounts/{account_id}")
def delete_portfolio_account(account_id: int) -> dict:
    """Supprime un compte et ses lignes (cascade). 404 si inconnu."""
    try:
        portfolio_service.delete_account(account_id)
    except portfolio_data.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return {"status": "deleted", "id": account_id}


@app.get("/api/portfolio/transactions")
def get_portfolio_transactions(account_id: int | None = None, tag: str | None = None) -> list[dict]:
    """Transactions, éventuellement filtrées par compte et/ou étiquette (#17.6)."""
    return portfolio_service.transactions(account_id, tag)


def _transaction_kwargs(body: dict) -> dict:
    """Extrait et nomme les champs d'une transaction depuis le body JSON.

    Les types sont volontairement laissés à la validation de `data/portfolio`
    (422) : la frontière HTTP ne duplique pas les règles métier.
    """
    return {
        "account_id": body.get("account_id"),
        "ticker": body.get("ticker"),
        "side": body.get("side"),
        "trade_date": body.get("trade_date"),
        "quantity": body.get("quantity"),
        "price": body.get("price"),
        "fees": body.get("fees", 0.0),
        "currency": body.get("currency"),
        "note": body.get("note"),
        "tag": body.get("tag"),
    }


@app.post("/api/portfolio/transactions")
def post_portfolio_transaction(body: dict) -> dict:
    """Crée une transaction. 422 si une donnée est invalide."""
    try:
        tx_id = portfolio_service.add_transaction(**_transaction_kwargs(body))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return {"status": "ok", "id": tx_id}


@app.put("/api/portfolio/transactions/{tx_id}")
def put_portfolio_transaction(tx_id: int, body: dict) -> dict:
    """Remplace une transaction. 422 si invalide, 404 si inconnue."""
    try:
        portfolio_service.update_transaction(tx_id, **_transaction_kwargs(body))
    except portfolio_data.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return {"status": "ok", "id": tx_id}


@app.delete("/api/portfolio/transactions/{tx_id}")
def delete_portfolio_transaction(tx_id: int) -> dict:
    """Supprime une transaction. 404 si inconnue."""
    try:
        portfolio_service.delete_transaction(tx_id)
    except portfolio_data.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return {"status": "deleted", "id": tx_id}


@app.get("/api/portfolio/dividends")
def get_portfolio_dividends(account_id: int | None = None) -> list[dict]:
    """Dividendes, éventuellement filtrés par compte."""
    return portfolio_service.dividends(account_id)


def _dividend_kwargs(body: dict) -> dict:
    return {
        "account_id": body.get("account_id"),
        "ticker": body.get("ticker"),
        "pay_date": body.get("pay_date"),
        "amount": body.get("amount"),
        "status": body.get("status", "confirmed"),
        "source": body.get("source", "manual"),
    }


@app.post("/api/portfolio/dividends")
def post_portfolio_dividend(body: dict) -> dict:
    """Crée un dividende. 422 si une donnée est invalide."""
    try:
        div_id = portfolio_service.add_dividend(**_dividend_kwargs(body))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return {"status": "ok", "id": div_id}


@app.put("/api/portfolio/dividends/{div_id}")
def put_portfolio_dividend(div_id: int, body: dict) -> dict:
    """Remplace un dividende. 422 si invalide, 404 si inconnu."""
    try:
        portfolio_service.update_dividend(div_id, **_dividend_kwargs(body))
    except portfolio_data.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return {"status": "ok", "id": div_id}


@app.delete("/api/portfolio/dividends/{div_id}")
def delete_portfolio_dividend(div_id: int) -> dict:
    """Supprime un dividende. 404 si inconnu."""
    try:
        portfolio_service.delete_dividend(div_id)
    except portfolio_data.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return {"status": "deleted", "id": div_id}


@app.get("/api/portfolio/positions")
def get_portfolio_positions(account_id: int | None = None, tag: str | None = None) -> list[dict]:
    """Positions recalculées (quantité, PRU, coût, réalisé, étiquettes).

    `account_id` absent = vue consolidée « Tous les comptes ». `tag` (#17.6)
    restreint aux transactions étiquetées (portefeuille virtuel). Aucune
    valorisation de marché ici (elle vit dans `/api/portfolio/summary`).
    """
    return portfolio_positions_to_list(portfolio_service.positions(account_id, tag))


@app.post("/api/portfolio/positions/tag")
def post_portfolio_position_tag(body: dict) -> dict:
    """Étiquette toutes les transactions d'un titre (#17.6). 422 si invalide.

    Body : `{"ticker": str, "tag": str | null, "account_id"?: int}`. `tag` null
    efface l'étiquette. Renvoie `{"status": "ok", "updated": n}`.
    """
    try:
        updated = portfolio_service.tag_positions(
            body.get("account_id"), body.get("ticker"), body.get("tag")
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return {"status": "ok", "updated": updated}


@app.get("/api/portfolio/tags")
def get_portfolio_tags(account_id: int | None = None) -> dict:
    """Étiquettes distinctes du portefeuille (portefeuilles virtuels, #17.6).

    `account_id` restreint la liste au compte donné : le sélecteur du front ne
    propose que des étiquettes réellement présentes dans le périmètre affiché.
    """
    return {"tags": portfolio_service.tags(account_id)}


@app.get("/api/portfolio/benchmarks")
def get_portfolio_benchmarks() -> dict:
    """Benchmarks proposés (#17.1) — SOURCE UNIQUE `config.py`.

    Le front n'a aucun ticker en dur : il lit cette liste (ETF UCITS en EUR,
    historique long) et peut aussi saisir un ticker libre. `periods`, `top_n` et
    le défaut sont exposés ici (même source unique).
    """
    return {
        "benchmarks": portfolio_service.benchmarks(),
        "default": config.PORTFOLIO_BENCHMARK_DEFAULT,
        "periods": list(config.PORTFOLIO_PERIODS),
        "period_default": config.PORTFOLIO_PERIOD_DEFAULT,
        "detail_horizons": list(config.PORTFOLIO_DETAIL_HORIZONS),
        "detail_horizon_default": config.PORTFOLIO_DETAIL_HORIZON_DEFAULT,
        "top_n": config.PORTFOLIO_TOP_N,
    }


@app.get("/api/portfolio/summary")
def get_portfolio_summary(
    account_id: int | None = None,
    benchmark: str | None = None,
    period: str | None = None,
    tag: str | None = None,
) -> dict:
    """Résumé de performance (#17.1) : TWR vs benchmark, KPI, Top/Flop.

    `account_id` et `tag` (#17.6) restreignent la portée (compte, portefeuille
    virtuel, ou les deux). 422 si la période est inconnue ou le benchmark
    introuvable sur Yahoo.
    """
    try:
        summary = portfolio_service.summary(account_id, benchmark, period, tag)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return portfolio_summary_to_dict(summary)


@app.get("/api/portfolio/risk")
def get_portfolio_risk(
    account_id: int | None = None,
    benchmark: str | None = None,
    period: str | None = None,
    tag: str | None = None,
) -> dict:
    """Risque du portefeuille (#17.3) : drawdown vs benchmark + corrélations.

    `account_id` et `tag` (#17.6) restreignent la portée (compte, portefeuille
    virtuel, ou les deux). 422 si la période est inconnue ou le benchmark
    introuvable sur Yahoo.
    """
    try:
        risk = portfolio_service.risk(account_id, benchmark, period, tag)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return portfolio_risk_to_dict(risk)


@app.get("/api/portfolio/risk/correlation-test")
def get_portfolio_correlation_test(
    ticker: str = "",
    account_id: int | None = None,
    benchmark: str | None = None,
    period: str | None = None,
    tag: str | None = None,
) -> dict:
    """Test de corrélation (#17.3) : impact d'un ticker candidat sur le périmètre.

    Corrèle le ticker candidat aux lignes détenues (même ordre que la matrice) et
    renvoie la corrélation moyenne avant/après (`current_avg`, `new_avg`) avec son
    `delta`. 422 si le ticker est vide, introuvable, déjà détenu, ou si le
    périmètre n'a aucune ligne exploitable ; 422 aussi sur période inconnue ou
    benchmark introuvable.
    """
    try:
        result = portfolio_service.correlation_test(account_id, benchmark, period, tag, ticker)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return portfolio_correlation_test_to_dict(result)


@app.get("/api/portfolio/performance")
def get_portfolio_performance(
    account_id: int | None = None,
    benchmark: str | None = None,
    period: str | None = None,
    tag: str | None = None,
) -> dict:
    """Performance du portefeuille (#17.4) : stats pondérées, mensuels, rétrospective.

    `account_id` et `tag` (#17.6) restreignent la portée (compte, portefeuille
    virtuel, ou les deux) — mêmes lignes que le donut. 422 si la période est
    inconnue ou le benchmark introuvable sur Yahoo.
    """
    try:
        perf = portfolio_service.performance(account_id, benchmark, period, tag)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return portfolio_performance_to_dict(perf)


@app.get("/api/portfolio/dividend-metrics")
def get_portfolio_dividend_metrics(
    account_id: int | None = None,
    tag: str | None = None,
) -> dict:
    """Page Dividende du portefeuille (#17.5) : revenu, KPI agrégés, pilotage.

    `account_id` et `tag` (#17.6) restreignent la portée (compte, portefeuille
    virtuel, ou les deux). Aucune période : le revenu se lit par année civile, et
    la contribution du dividende à la performance est annualisée sur tout
    l'historique de détention (une fenêtre tronquée rendrait le calcul muet).
    """
    return portfolio_dividend_page_to_dict(
        portfolio_service.dividend_page(account_id=account_id, tag=tag)
    )


@app.get("/api/portfolio/security")
def get_portfolio_security(ticker: str, benchmark: str | None = None) -> dict:
    """Détail d'un titre (modale Performance) : perf cumulée + courbe benchmark alignée.

    Sert le graphe comparatif de la fenêtre « détail par titre » : la série
    ajustée du titre et celle du benchmark partagent EXACTEMENT les mêmes dates
    (base commune rebasée à 0 % côté front).
    404 si un ticker est introuvable, 422 si le ticker est vide.
    """
    try:
        detail = portfolio_service.security_detail(ticker, benchmark)
    except yahoo.TickerNotFound as exc:
        raise HTTPException(status_code=404, detail=f"Ticker introuvable : {exc}") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return security_detail_to_dict(detail)


@app.get("/api/portfolio/names")
def get_portfolio_names(tickers: str = "") -> dict:
    """Noms de société pour une liste de tickers (complément paresseux du Résumé).

    Le Résumé renvoie d'abord les lignes Top/Flop sans bloquer sur ~10 appels
    `info` yfinance ; le front demande ensuite les noms ici. Format `tickers` :
    liste séparée par des virgules. Un ticker non résolu vaut null.
    """
    wanted = [t for t in (tickers or "").split(",") if t.strip()]
    if not wanted:
        return {"names": {}}
    return {"names": portfolio_service.resolve_names(wanted)}


# --- Contrôle de santé (#01) -------------------------------------------------


@app.get("/api/health")
def get_health() -> JSONResponse:
    """Contrôle de santé des briques : yfinance, SQLite, cache.

    200 si les briques critiques (SQLite, cache) répondent — un yfinance en
    échec donne un statut `degraded` mais laisse l'app utilisable (dégradation
    gracieuse). 503 dès qu'une brique critique est HS. Aucun appel réseau.
    """
    report = health_data.snapshot()
    status_code = 503 if report["status"] == "down" else 200
    return JSONResponse(content=report, status_code=status_code)


# --- Sauvegarde / restauration des données utilisateur (#03) ------------------


@app.get("/api/backup")
def get_backup() -> JSONResponse:
    """Archive JSON des tables utilisateur (téléchargement direct).

    Ne contient jamais le cache technique (jetable, re-fetchable). Le nom de
    fichier est daté pour distinguer les sauvegardes successives.
    """
    archive = backup_data.build_archive()
    fname = f"obole-backup-{datetime.now(UTC).date().isoformat()}.json"
    return JSONResponse(
        content=archive,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.post("/api/restore")
async def post_restore(file: UploadFile) -> dict:
    """Restaure une archive (multipart/form-data, champ « file »).

    Remplace intégralement le contenu des tables utilisateur, en une seule
    transaction : une archive invalide ou inapplicable renvoie 422 sans laisser
    la base à moitié restaurée.
    """
    raw = await read_bounded(file, config.UPLOAD_MAX_RESTORE_BYTES, "Archive de sauvegarde")
    try:
        counts = backup_data.restore_from_json(raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return {"status": "ok", "tables": counts}


@app.post("/api/cache/purge")
def post_cache_purge() -> dict:
    """Vide le cache technique (prix, comptes, métadonnées) sans toucher aux données.

    Tout le cache est re-fetchable depuis yfinance : c'est le geste sûr pour
    forcer un rechargement complet. Les tables utilisateur sont intactes.
    """
    removed = backup_data.purge_cache()
    return {"status": "purged", "removed": removed}


# --- Réglages utilisateur ----------------------------------------------------


def _settings_payload() -> dict:
    """Payload complet du panneau Paramètres (valeurs + métadonnées extensibles).

    `values` : réglages effectifs (défauts appliqués) pour les calculs ;
    `defs` : description de chaque réglage (défaut, bornes, libellé) pour générer
    l'UI dynamiquement ; `groups` : ordre d'affichage des sections.
    """
    values = cache_data.get_settings()
    defs = {
        key: {
            "default": spec["default"],
            "min": spec["min"],
            "max": spec["max"],
            "label": spec["label"],
            "group": spec["group"],
            **({"choices": list(spec["choices"])} if spec.get("choices") else {}),
        }
        for key, spec in config.SETTING_DEFS.items()
    }
    return {"values": values, "defs": defs, "groups": config.SETTING_GROUPS}


# Clés numériques REQUISES des paramètres de valorisation (validation stricte :
# tout input extérieur est hostile par défaut).
_VALUATION_NUMERIC_KEYS = (
    "growth",
    "multiple",
    "target_yield",
    "dividend_yield",
)
# Clés numériques OPTIONNELLES : absentes/vides -> `None` persisté (pas d'erreur).
_VALUATION_OPTIONAL_KEYS = (
    "net_debt_per_share",  # bridge EV -> capitaux propres (multiple d'entreprise)
    "fair_price",  # prix juste = prix d'ENTRÉE atteignant la cible, calculé côté client
)


def _validate_valuation_settings(body: dict) -> dict:
    """Valide et normalise les paramètres de la calculatrice reçus du front.

    Lève ValueError (-> 422) si un champ REQUIS manque ou n'est pas numérique.
    `include_dividends` est un booléen ; `metric`/`period` sont validés contre
    `config` (jamais de valeur arbitraire persistée).

    Le prix juste est un RÉSULTAT de la calculatrice, recalculé en direct côté
    client (`web/valorisation.js`, miroir testé de `engine/valuation_calc.py`) :
    le serveur le persiste tel quel pour la synthèse « Résumé ». Il est NULLABLE
    (une base non calculable — médiane ou métrique absente — ne doit pas bloquer
    l'enregistrement des paramètres).
    """
    if not isinstance(body, dict):
        raise ValueError("Corps de requête invalide")
    metric = body.get("metric")
    if metric not in {m["key"] for m in config.VALUATION_METRICS}:
        raise ValueError(f"Données utilisées inconnues : {metric!r}")
    period = body.get("period")
    if period not in config.VALUATION_PERIODS:
        raise ValueError(f"Période historique inconnue : {period!r}")
    out: dict = {
        "metric": metric,
        "period": period,
        "include_dividends": bool(body.get("include_dividends")),
    }
    for key in _VALUATION_NUMERIC_KEYS:
        raw = body.get(key)
        if raw is None:
            raise ValueError(f"Paramètre manquant : {key}")
        try:
            out[key] = float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Paramètre non numérique : {key}") from exc
    for key in _VALUATION_OPTIONAL_KEYS:
        raw = body.get(key)
        if raw is None:
            out[key] = None
            continue
        try:
            out[key] = float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Paramètre non numérique : {key}") from exc
    return out


@app.get("/api/settings")
def get_settings() -> dict:
    """Réglages globaux (panneau Paramètres), toujours avec les défauts appliqués.

    Les fiches (stock/ratio/indice) et le résumé des indices lisent ces valeurs
    pour calculer les moyennes mobiles et la tendance boursière.
    Réponse : `{"values": {...}, "defs": {...}, "groups": [...]}`.
    """
    return _settings_payload()


@app.put("/api/settings")
def put_settings(body: dict) -> dict:
    """Met à jour (partiel) et persiste les réglages fusionnés.

    Seules les clés connues sont acceptées ; chaque valeur est validée (bornes +
    cohérence MM courte < MM longue). Une valeur invalide renvoie 422.
    Réponse : le payload complet après fusion.
    """
    body_values = body.get("values", body) if isinstance(body, dict) else {}
    try:
        cache_data.set_settings(body_values)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return _settings_payload()


@app.get("/api/valuation/{ticker}")
def get_valuation_settings(ticker: str) -> dict:
    """Paramètres de la calculatrice de prix juste enregistrés pour un titre.

    Renvoie `{"saved": {...} | null}` : la fiche affiche le prix juste enregistré
    dans sa synthèse (le calcul lui-même est fait côté client).
    """
    return {"saved": cache_data.get_valuation_settings(ticker)}


@app.put("/api/valuation/{ticker}")
def put_valuation_settings(ticker: str, body: dict) -> dict:
    """Enregistre les paramètres de la calculatrice pour un titre.

    Le prix juste (`fair_price`, nullable) est calculé en direct côté client
    (miroir testé de `engine/valuation_calc.py`) et persisté tel quel : c'est
    cette valeur qui alimente la synthèse « Résumé ». Body invalide
    (paramètre requis manquant ou non numérique) -> 422.
    """
    try:
        payload = _validate_valuation_settings(body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    cache_data.set_valuation_settings(ticker, payload)
    return {"saved": payload}


@app.delete("/api/valuation/{ticker}")
def delete_valuation_settings(ticker: str) -> dict:
    """Efface les paramètres enregistrés (« Réinitialiser ») : le Résumé revient
    à la droite de régression."""
    cache_data.clear_valuation_settings(ticker)
    return {"status": "cleared", "ticker": ticker.upper()}


# --- Watchlist (#25) ---------------------------------------------------------
# Cas d'usage partagé avec le MCP (`services/watchlist.py`) : validation,
# classement et erreurs typées viennent de là, la route ne fait que traduire en
# HTTP (422) et sérialiser. La référence et le prix juste restent des gestes
# humains ; le MCP n'expose pas leurs écritures.


@app.get("/api/watchlist")
def get_watchlist() -> dict:
    """Tiers, valeurs suivies et références par titre (aucune analyse)."""
    return watchlist_state_to_dict(watchlist_service.list_state())


@app.put("/api/watchlist/items/{ticker}")
def put_watchlist_item(ticker: str, body: dict) -> dict:
    """Ajoute OU déplace une valeur dans un tier (upsert). 422 si tier invalide."""
    try:
        item = watchlist_service.set_tier(ticker, body.get("tier"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return {"item": item}


@app.delete("/api/watchlist/items/{ticker}")
def delete_watchlist_item(ticker: str) -> dict:
    """Retire une valeur. La référence de fenêtre est conservée."""
    try:
        removed = watchlist_service.remove(ticker)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return {"removed": removed}


@app.put("/api/watchlist/ref/{ticker}")
def put_watchlist_ref(ticker: str, body: dict) -> dict:
    """Enregistre la fenêtre de confiance (date de départ) d'un titre.

    Renvoie les statistiques de la droite de référence ; 422 si la date est
    invalide/future ou si la fenêtre ne contient pas assez de points.
    """
    try:
        return watchlist_service.set_ref(ticker, body.get("start"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@app.delete("/api/watchlist/ref/{ticker}")
def delete_watchlist_ref(ticker: str) -> dict:
    """Efface la référence : retour à la fenêtre 20 ans par défaut."""
    try:
        watchlist_service.clear_ref(ticker)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return {"ref": None}


@app.post("/api/watchlist/run")
def run_watchlist(body: dict | None = None) -> dict:
    """Classe les valeurs suivies par marge de sécurité.

    `tier` (1..3, optionnel) restreint le scan ; `max_rows` borne les lignes
    RENDUES (`count` reste le total). Le scan est synchrone et borné par le pool
    du screener ; les erreurs de ticker sont isolées dans `rows[].error`.
    """
    body = body or {}
    try:
        tier = body.get("tier")
        tier = None if tier in (None, "") else watchlist_service.validate_tier(tier)
        max_rows = screener_service.validate_max_rows(body.get("max_rows"))
        run = watchlist_service.run(tier=tier)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return watchlist_run_to_dict(run, max_rows=max_rows)


# --- Thèses d'entreprise (#21) ----------------------------------------------
# Cas d'usage partagé avec le MCP (`services/thesis.py`) : validation et erreurs
# typées viennent de là, la route ne fait que traduire en HTTP.


@app.get("/api/theses")
def get_theses() -> list[dict]:
    """Thèses enregistrées (métadonnées seules : ticker + horodatages)."""
    return thesis_service.list_theses()


@app.get("/api/thesis/{ticker}")
def get_thesis(ticker: str) -> dict:
    """Thèse d'un ticker (contenu markdown inclus). 404 si absente."""
    try:
        return thesis_service.get_thesis(ticker)
    except ThesisNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@app.put("/api/thesis/{ticker}")
def put_thesis(ticker: str, body: dict) -> dict:
    """Enregistre (crée ou remplace) la thèse d'un ticker.

    Body : `{"content": "<markdown>"}` (ou un objet JSON, forme historique).
    Contenu vide ou démesuré -> 422.
    """
    content = body.get("content") if isinstance(body, dict) else None
    try:
        return thesis_service.save_thesis(ticker, content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@app.delete("/api/thesis/{ticker}")
def delete_thesis(ticker: str) -> dict:
    """Supprime la thèse d'un ticker. 404 si absente."""
    try:
        return thesis_service.delete_thesis(ticker)
    except ThesisNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@app.post("/api/thesis/{ticker}/prompt")
def post_thesis_prompt(ticker: str) -> dict:
    """Prompt de thèse + données de l'analyse (aucun appel LLM côté serveur).

    Obole fournit le prompt et les chiffres : c'est l'IA cliente (ou l'auteur)
    qui rédige. 404 si ticker inconnu, 422 si entrée invalide.
    """
    try:
        return thesis_service.write_thesis(ticker)
    except yahoo.TickerNotFound:
        raise HTTPException(status_code=404, detail=f"Ticker introuvable : {ticker}") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@app.post("/api/thesis/assets")
async def post_thesis_asset(file: UploadFile = File(...)) -> dict:  # noqa: B008
    """Enregistre une image insérée dans une thèse et renvoie son URL.

    Type et taille sont validés, la signature binaire vérifiée, et le nom de
    fichier **régénéré** depuis le contenu (aucun composant client conservé).
    422 si le fichier est refusé.
    """
    data = await read_bounded(file, config.UPLOAD_MAX_ASSET_BYTES, "Image")
    try:
        return thesis_assets.save_image(data, file.content_type or "")
    except thesis_assets.InvalidImage as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@app.get("/api/thesis/assets/{filename}")
def get_thesis_asset(filename: str) -> FileResponse:
    """Sert une image de thèse. 404 si absente, 422 si le nom est invalide."""
    try:
        path = thesis_assets.path_for(filename)
    except thesis_assets.InvalidImage as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return FileResponse(path, media_type=thesis_assets.media_type(path.name))


# --- Points de contrôle suivis (#21, bande « Suivi ») ------------------------
# Cas d'usage partagé avec le MCP (`services/checkpoints.py`) : validation et
# erreurs typées viennent de là, la route ne fait que traduire en HTTP.
# Rattachement : ticker d'action (un ratio ou un indice n'a pas de section
# « Thèse & Société », donc pas de points de contrôle).


@app.get("/api/checkpoints/{ticker}")
def get_checkpoints(ticker: str) -> list[dict]:
    """Points de contrôle suivis d'un ticker (liste vide si aucun)."""
    try:
        return checkpoints_service.list_checkpoints(ticker)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@app.post("/api/checkpoints/{ticker}")
def post_checkpoint(ticker: str, body: dict) -> dict:
    """Crée un point de contrôle : `{"label": str}`. 422 si vide ou trop long."""
    try:
        return checkpoints_service.add_checkpoint(ticker, body.get("label"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@app.put("/api/checkpoints/{checkpoint_id}")
def put_checkpoint(checkpoint_id: int, body: dict) -> dict:
    """Modifie un point de contrôle : `{"label": str, "done": bool}`. 404 si inconnu."""
    try:
        return checkpoints_service.update_checkpoint(
            checkpoint_id, body.get("label"), body.get("done")
        )
    except CheckpointNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@app.delete("/api/checkpoints/{checkpoint_id}")
def delete_checkpoint(checkpoint_id: int) -> dict:
    """Supprime un point de contrôle. 404 s'il est inconnu."""
    try:
        return checkpoints_service.delete_checkpoint(checkpoint_id)
    except CheckpointNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@app.get("/")
def index() -> HTMLResponse:
    return render_index(WEB_DIR)


# Sert les assets statiques (css, js, vendor) du front.
app.mount("/static", VersionedStaticFiles(directory=WEB_DIR), name="static")
