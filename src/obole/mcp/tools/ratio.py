"""Outil MCP `get_ratio_analysis` — ratio A/B entre deux actifs.

Délègue à `services/analysis.analyze_ratio_tickers` (fetch des deux séries +
analyse) puis sérialise via `services/serialize.ratio_to_dict`. En `view="full"`
le payload suit la route `GET /api/ratio?a=&b=` ; en `view="summary"` (défaut) la
série de prix (`chart`) est omise.
"""

from __future__ import annotations

from typing import Literal

from mcp.server.mcpserver.exceptions import ToolError

from obole.data import yahoo
from obole.mcp.tools._shared import chart_enabled
from obole.services import analysis as analysis_service
from obole.services import serialize


def get_ratio_analysis(a: str, b: str, view: Literal["summary", "full"] = "summary") -> dict:
    """Analyse d'un ratio A / B entre deux actifs (comparaison relative long terme).

    Le ratio est construit en « total return » (dividendes réinvestis des deux
    côtés) pour comparer équitablement un actif distribuant à un capitalisant,
    puis régressé comme une valeur : distance σ, tendance, β et ρ (A relativement
    à B). Utile pour juger si A est cher/abordable face à B.

    Args:
        a: numérateur, symbole Yahoo (ex. `"CW8.PA"`).
        b: dénominateur, symbole Yahoo (ex. `"RI.PA"`).
        view: niveau de détail. `"summary"` (défaut) omet la série de prix du graphe
            (`chart`, ~99 % du payload) ; `"full"` l'inclut (nécessaire pour tracer).

    Returns:
        Le payload du ratio : identité, indicateurs (dont β et ρ), régression — et,
        en `view="full"` uniquement, les séries du graphe. Identique à
        `GET /api/ratio?a=&b=` (sauf `chart` omis en `summary`).

    Raises:
        ToolError: un symbole est vide/introuvable, ou l'historique commun est
            trop court.
    """
    a = (a or "").strip()
    b = (b or "").strip()
    if not a or not b:
        raise ToolError("Deux tickers requis (a et b)")
    try:
        analysis, series, sa, sb = analysis_service.analyze_ratio_tickers(a, b)
    except yahoo.TickerNotFound as exc:
        raise ToolError(f"Ticker introuvable : {exc}") from None
    except ValueError as exc:
        raise ToolError(str(exc)) from None
    return serialize.ratio_to_dict(analysis, series, sa, sb, include_chart=chart_enabled(view))


def register(server) -> None:
    """Enregistre l'outil sur le serveur MCP."""
    server.tool()(get_ratio_analysis)
