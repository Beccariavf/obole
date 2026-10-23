"""Outil MCP `search_tickers` — autocomplétion nom → ticker.

Délègue à `data/yahoo.search` (seule couche qui touche le réseau) : mêmes
résultats que la route `GET /api/search?q=`.
"""

from __future__ import annotations

from obole.data import yahoo


def search_tickers(query: str) -> list[dict]:
    """Recherche des symboles boursiers à partir d'un nom ou d'un fragment.

    Sert à résoudre le ticker Yahoo d'une entreprise avant de demander son
    analyse (`get_stock_analysis`). Les résultats sont filtrés sur les actions
    (ETF, fonds et indices sont écartés) et mis en cache brièvement.

    Args:
        query: nom ou début de nom/ticker (au moins 2 caractères, ex. `"pernod"`).

    Returns:
        Liste de suggestions `{"symbol", "name", "exchange"}` (vide si la requête
        est trop courte). Identique à `GET /api/search?q=`.
    """
    return yahoo.search((query or "").strip())


def register(server) -> None:
    """Enregistre l'outil sur le serveur MCP."""
    server.tool()(search_tickers)
