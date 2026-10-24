"""Outil MCP `get_stock_analysis` — fiche d'une valeur.

Délègue à `services/analysis.analyze_ticker` (fetch + analyse) puis sérialise via
`services/serialize.analysis_to_dict`. En `view="full"` le payload est celui de la
route `GET /api/stock/{ticker}` ; en `view="summary"` (défaut) la série de prix
(`chart`) est omise.
"""

from __future__ import annotations

from typing import Literal

from mcp.server.mcpserver.exceptions import ToolError

from obole.data import yahoo
from obole.mcp.tools._shared import chart_enabled
from obole.services import analysis as analysis_service
from obole.services import serialize
from obole.services import watchlist as watchlist_service


def get_stock_analysis(ticker: str, view: Literal["summary", "full"] = "summary") -> dict:
    """Analyse complète d'une action/ETF selon la méthode « droite d'Obole ».

    Régresse ln(cours) sur le temps puis en déduit la distance σ à la droite
    (valorisation), la performance annualisée, l'écart-type (volatilité), les
    potentiels à 5 et 10 ans, la tendance (moyennes mobiles) et les comptes.
    Utilise le cache local (aucun appel réseau si les prix sont récents).

    Args:
        ticker: symbole boursier Yahoo (ex. `"RI.PA"` pour Pernod Ricard).
        view: niveau de détail. `"summary"` (défaut) omet la série de prix du graphe
            (`chart`, ~90 % du payload) — suffisant pour raisonner sur les
            indicateurs et les comptes. `"full"` inclut la série de prix complète
            (nécessaire seulement pour tracer le graphe).

    Returns:
        Le payload de la fiche : identité, indicateurs (avec libellés et polarité),
        régression, comptes, synthèse, avertissements — et, en `view="full"`
        uniquement, les séries du graphe. Identique à `GET /api/stock/{ticker}`
        (sauf `chart` omis en `summary`). Le bloc `watch` porte le tier de la
        valeur dans la watchlist et sa fenêtre de confiance (`ref`, `ref_stats`),
        ou `null` si elle n'est pas suivie / sans référence.

    Raises:
        ToolError: ticker vide, introuvable, ou historique trop court.
    """
    ticker = (ticker or "").strip()
    if not ticker:
        raise ToolError("Ticker requis")
    try:
        analysis, prices = analysis_service.analyze_ticker(ticker)
    except yahoo.TickerNotFound:
        raise ToolError(f"Ticker introuvable : {ticker}") from None
    except ValueError as exc:
        raise ToolError(str(exc)) from None
    payload = serialize.analysis_to_dict(analysis, prices, include_chart=chart_enabled(view))
    # État watchlist (#25) : même décoration que la route `/api/stock`, pour que
    # l'IA voie le tier et la fenêtre de confiance de la valeur qu'elle analyse.
    return watchlist_service.decorate_stock_payload(payload, analysis.identity.ticker, prices)


def register(server) -> None:
    """Enregistre l'outil sur le serveur MCP."""
    server.tool()(get_stock_analysis)
