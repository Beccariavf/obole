"""Helpers partagés des outils MCP (validation d'entrée commune).

`view` est un axe transversal aux outils de lecture (stock, ratio, indice) :
on centralise ici sa validation pour éviter qu'une valeur inconnue ne retombe
**silencieusement** sur `summary`. Le transport MCP valide déjà le `Literal`
via le schéma, mais un appel direct (test, code programmatique) le contourne :
la garde explicite garantit un échec clair dans tous les cas.
"""

from __future__ import annotations

from mcp.server.mcpserver.exceptions import ToolError

VALID_VIEWS = ("summary", "full")


def validate_view(view: str) -> str:
    """Valide `view` et le renvoie, en rejetant toute valeur inconnue.

    Lève `ToolError` si `view` n'est ni `"summary"` ni `"full"` : pas de repli
    silencieux (une IA qui demanderait `"Full"` doit être corrigée, pas servie
    sans le graphe).
    """
    if view not in VALID_VIEWS:
        raise ToolError(f"view invalide : {view!r} (attendu : summary ou full)")
    return view


def chart_enabled(view: str) -> bool:
    """Traduit `view` en `include_chart` (validation partagée via `validate_view`)."""
    return validate_view(view) == "full"
