"""Outils MCP des indices personnalisés (CRUD + analyse).

Délègue à `services/indices.py` — qui porte la validation à source unique et
des erreurs typées (`IndexNotFound` -> ressource absente, `ValueError` -> entrée
invalide). Chaque fonction traduit ces erreurs en `ToolError` (vocabulaire du
transport MCP) : le message reste lisible pour l'IA cliente.

Aucune formule ici : l'analyse d'un indice passe par `services/indices.analyze_index`.
"""

from __future__ import annotations

from typing import Literal

from mcp.server.mcpserver.exceptions import ToolError

from obole.data import yahoo
from obole.mcp.tools._shared import chart_enabled
from obole.services import indices as indices_service
from obole.services import serialize
from obole.services.indices import IndexNotFound


def list_indices() -> list[dict]:
    """Liste les catégories d'indices personnalisés et leurs définitions.

    Un indice est un panier « equal-weight » de tickers, chaîné en total return :
    il permet de suivre la performance d'un thème (ex. « Énergie ») comme une
    seule valeur. Cette fonction ne calcule rien (définitions seules).

    Returns:
        Liste de catégories `{"id", "name", "indices": [{"id", "name", "tickers"}]}`.
        Identique à `GET /api/indices`.
    """
    return indices_service.list_indices()


def get_index_analysis(index_id: int, view: Literal["summary", "full"] = "summary") -> dict:
    """Analyse complète d'un indice personnalisé (panier chaîné en total return).

    Comme une fiche d'action (distance σ, tendance, potentiels, régression) mais
    sur la série synthétique de l'indice, avec les stats « coup d'œil » de chaque
    membre. Utilise le cache local.

    Args:
        index_id: identifiant de l'indice (voir `list_indices`).
        view: niveau de détail. `"summary"` (défaut) omet la série de prix du graphe
            (`chart`, l'essentiel du payload) ; `"full"` l'inclut (pour tracer).

    Returns:
        Payload de la fiche indice (sauf `chart` omis en `summary`). Identique à
        `GET /api/index/{index_id}` en `view="full"`.

    Raises:
        ToolError: indice inconnu, membre introuvable, ou panier trop court.
    """
    try:
        analysis, series = indices_service.analyze_index(index_id)
    except IndexNotFound as exc:
        raise ToolError(str(exc)) from None
    except yahoo.TickerNotFound as exc:
        raise ToolError(f"Ticker introuvable : {exc}") from None
    except ValueError as exc:
        raise ToolError(str(exc)) from None
    return serialize.basket_to_dict(analysis, series, include_chart=chart_enabled(view))


def create_index_category(name: str) -> dict:
    """Crée une catégorie d'indices (regroupement thématique).

    Args:
        name: nom de la catégorie (non vide, unique).

    Returns:
        `{"status": "ok", "id": int}`. Identique à `POST /api/indices/categories`.

    Raises:
        ToolError: nom vide ou déjà utilisé.
    """
    try:
        category_id = indices_service.create_category(name)
    except ValueError as exc:
        raise ToolError(str(exc)) from None
    return {"status": "ok", "id": category_id}


def delete_index_category(category_id: int) -> dict:
    """Supprime une catégorie d'indices ET TOUS les indices qu'elle contient.

    ⚠️ **Destructif et en cascade, sans confirmation** : chaque indice de la
    catégorie est définitivement supprimé (ses membres, non — seules les
    définitions d'indices disparaissent). Pour ne supprimer qu'un indice, utiliser
    `delete_index` ; pour vider une catégorie, appeler `list_indices` d'abord et
    supprimer les indices un à un.

    Args:
        category_id: identifiant de la catégorie.

    Returns:
        `{"status": "deleted", "category_id": int}`.

    Raises:
        ToolError: catégorie inconnue.
    """
    try:
        indices_service.delete_category(category_id)
    except (IndexNotFound, ValueError) as exc:
        raise ToolError(str(exc)) from None
    return {"status": "deleted", "category_id": category_id}


def create_index(category_id: int, name: str, tickers: list[str]) -> dict:
    """Crée un indice dans une catégorie.

    Args:
        category_id: catégorie d'accueil (voir `list_indices`).
        name: nom de l'indice (non vide).
        tickers: au moins 2 symboles Yahoo (normalisés en majuscules, dédoublonnés).

    Returns:
        `{"status": "ok", "id": int}`. Identique à `POST /api/indices`.

    Raises:
        ToolError: catégorie inconnue, nom vide, ou moins de 2 membres.
    """
    try:
        index_id = indices_service.create_index(category_id, name, tickers)
    except (IndexNotFound, ValueError) as exc:
        raise ToolError(str(exc)) from None
    return {"status": "ok", "id": index_id}


def update_index(index_id: int, category_id: int, name: str, tickers: list[str]) -> dict:
    """Remplace la définition complète d'un indice (nom, catégorie, membres).

    Args:
        index_id: indice à modifier.
        category_id: nouvelle catégorie.
        name: nouveau nom (non vide).
        tickers: nouvelle liste d'au moins 2 symboles.

    Returns:
        `{"status": "ok", "id": int}`. Identique à `PUT /api/indices/{index_id}`.

    Raises:
        ToolError: indice ou catégorie inconnue, nom vide, moins de 2 membres.
    """
    try:
        indices_service.update_index(index_id, category_id, name, tickers)
    except (IndexNotFound, ValueError) as exc:
        raise ToolError(str(exc)) from None
    return {"status": "ok", "id": index_id}


def delete_index(index_id: int) -> dict:
    """Supprime un indice (la catégorie et les autres indices sont conservés).

    Args:
        index_id: indice à supprimer.

    Returns:
        `{"status": "deleted", "index_id": int}`.

    Raises:
        ToolError: indice inconnu.
    """
    try:
        indices_service.delete_index(index_id)
    except (IndexNotFound, ValueError) as exc:
        raise ToolError(str(exc)) from None
    return {"status": "deleted", "index_id": index_id}


def register(server) -> None:
    """Enregistre les outils indices sur le serveur MCP."""
    for fn in (
        list_indices,
        get_index_analysis,
        create_index_category,
        delete_index_category,
        create_index,
        update_index,
        delete_index,
    ):
        server.tool()(fn)
