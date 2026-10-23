"""Outil MCP `screen_french_stocks` — screener d'actions françaises.

Délègue entièrement à `services/screener.py` (validation `validate_*` + cas
d'usage `run_screen`) puis sérialise via `services/serialize.screen_run_to_dict` :
le payload est **exactement** celui de la route `POST /api/screener/run` (même
validation `max_rows`, même troncature). Aucune formule ni seuil dupliqué — les
bornes de filtrage sont celles du PRD §5 (`config.py`), l'univers et le scan
viennent de `data/`.
"""

from __future__ import annotations

from mcp.server.mcpserver.exceptions import ToolError

from obole import config
from obole.services import screener as screener_service
from obole.services import serialize


def screen_french_stocks(
    min_market_cap: float | None = config.SCREEN_DEFAULT_MIN_CAP,
    sectors: list[str] | None = None,
    regression_window: float | None = None,
    filters: dict | None = None,
    sort_by: list | None = None,
    score_keys: list | None = None,
    max_rows: int | None = None,
) -> dict:
    """Scanne l'univers des actions françaises selon la méthode « droite d'Obole ».

    Exécute la même chaîne que la page Screener : passe 1 (pré-filtre Yahoo sur la
    capitalisation et les secteurs) puis passe 2 (régression par valeur -> distance
    σ, pente, écart-type, potentiels 5/10 ans, tendance, fondamentaux), avec un
    **cache agressif** : un second appel identique est servi depuis le cache SQLite
    sans refaire le moindre appel réseau. Le scan complet à froid peut durer
    plusieurs dizaines de secondes (N requêtes yfinance).

    Args:
        min_market_cap: capitalisation minimale en euros (passe 1), >= 0. Défaut
            `config.SCREEN_DEFAULT_MIN_CAP` (1 Md€, scan rapide) ; `null` =
            univers complet (aucun plancher, plus lent).
        sectors: secteurs Yahoo à retenir (`list[str]`, ex. `["Technology"]`) ;
            `null` = tous les secteurs.
        regression_window: fenêtre de régression en années pour σ/pente/
            potentiels (ex. `20`), > 0 ; `null` = historique complet de chaque valeur.
        filters: bornes par critère `{critère: [min, max]}` (min ou max `null` =
            non borné, bornes inclusives). Ex. décotées rentables :
            `{"z": [-2, null], "roe_pct": [10, null]}`. Critères filtrables :
            <<FILTERABLE_KEYS>>.
        sort_by: critères de tri chaînés, chacun une clé ou `[clé, "asc"|"desc"]`
            (ex. `["z", ["pente_pct", "desc"]]`). Sens par défaut = celui de la
            méthode (`config.SCREEN_SORT_DESC`). Critères triables (dont `score`) :
            <<SORTABLE_KEYS>>.
        score_keys: critères du score composite (`0-100`, classement par
            compromis). À fournir quand `sort_by` contient `"score"` ; au moins 2
            critères sont nécessaires pour qu'un score soit calculé.
        max_rows: plafond du nombre de lignes renvoyées (> 0), utile pour borner
            le volume d'un scan large. `null` (défaut) = toutes les lignes. `count`
            et `tickers_count` restent les TOTAUX réels, même si `rows` est tronqué.

    Returns:
        Payload du scan : `{"source": "yahoo"|"cache"|"fallback", "count": int,
        "tickers_count": int, "rows": [dict]}`. `count` = total des lignes
        filtrées+triées (avant `max_rows`), `tickers_count` = taille du scan brut.
        `rows` est déjà filtré et trié, chaque ligne portant ses valeurs et sa
        polarité couleur (`colors`). Identique à `POST /api/screener/run` (la
        route accepte le même `max_rows`).

    Raises:
        ToolError: entrée invalide (critère de filtre/tri inconnu, bornes
            malformées ou inversées, sens inconnu, `min_market_cap` négative,
            `regression_window` <= 0, `max_rows` <= 0) — l'entrée de l'IA est
            hostile par défaut.
    """
    try:
        clean_min_cap = screener_service.validate_min_market_cap(min_market_cap)
        clean_window = screener_service.validate_regression_window(regression_window)
        clean_filters = screener_service.validate_filters(filters)
        clean_sort_by = screener_service.validate_sort_by(sort_by)
        clean_score_keys = screener_service.validate_score_keys(score_keys)
        clean_max_rows = screener_service.validate_max_rows(max_rows)
    except ValueError as exc:
        raise ToolError(str(exc)) from None

    run = screener_service.run_screen(
        min_market_cap=clean_min_cap,
        sectors=sectors,
        regression_window=clean_window,
        filters=clean_filters,
        sort_by=clean_sort_by,
        score_keys=clean_score_keys,
    )
    return serialize.screen_run_to_dict(run, max_rows=clean_max_rows)


# Les critères filtrables/triables sont injectés dans la docstring depuis la
# SOURCE UNIQUE (`services.screener.FILTERABLE_KEYS`/`SORTABLE_KEYS`, elles-mêmes
# issues de `engine.screen`) : aucune énumération en dur qui pourrait dériver.
_doc = screen_french_stocks.__doc__ or ""
screen_french_stocks.__doc__ = _doc.replace(
    "<<FILTERABLE_KEYS>>", ", ".join(f"`{k}`" for k in screener_service.FILTERABLE_KEYS)
).replace("<<SORTABLE_KEYS>>", ", ".join(f"`{k}`" for k in screener_service.SORTABLE_KEYS))


def register(server) -> None:
    """Enregistre l'outil screener sur le serveur MCP."""
    server.tool()(screen_french_stocks)
