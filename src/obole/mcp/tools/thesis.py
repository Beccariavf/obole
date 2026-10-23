"""Outils MCP de thèse d'entreprise (`write_thesis` + CRUD).

Délègue à `services/thesis.py` — qui porte la validation à source unique et des
erreurs typées (`ThesisNotFound` -> ressource absente, `ValueError` -> entrée
invalide, `yahoo.TickerNotFound` -> titre inconnu). Chaque fonction traduit ces
erreurs en `ToolError` (vocabulaire du transport MCP) : le message reste lisible
pour l'IA cliente.

Aucun appel LLM côté serveur (`PRD.md` §12.4) : `write_thesis` renvoie un prompt
structuré que l'IA cliente déroule, avec les données de l'analyse existante.
"""

from __future__ import annotations

from mcp.server.mcpserver.exceptions import ToolError

from obole.data import yahoo
from obole.services import thesis as thesis_service
from obole.services.thesis import ThesisNotFound


def write_thesis(ticker: str) -> dict:
    """Rédige le prompt de thèse d'investissement d'une action + ses données.

    Renvoie un **prompt structuré** (pitch, bull/bear, catalyseurs, points de
    contrôle) adossé aux métriques de la méthode « droite d'Obole » — distance σ
    (valorisation), performance passée, écart-type, potentiels 5/10 ans, tendance,
    qualité, ROE — et les **données complètes** de l'analyse pour que l'IA puisse
    citer les chiffres. Utilise le cache local.

    C'est à l'IA CLIENTE de rédiger la thèse à partir de ce prompt (aucun appel
    LLM côté serveur) ; la persistance se fait ensuite via `save_thesis`.

    Args:
        ticker: symbole boursier Yahoo (ex. `"RI.PA"` pour Pernod Ricard).

    Returns:
        `{"prompt": str, "data": dict, "warnings": [str]}` — le prompt markdown,
        les données de la fiche (identique à `GET /api/stock/{ticker}`, série de
        prix `chart` exclue) et les avertissements de fiabilité.

    Raises:
        ToolError: ticker vide, introuvable, ou historique trop court.
    """
    try:
        return thesis_service.write_thesis(ticker)
    except yahoo.TickerNotFound:
        raise ToolError(f"Ticker introuvable : {ticker}") from None
    except ValueError as exc:
        raise ToolError(str(exc)) from None


def save_thesis(ticker: str, content: str) -> dict:
    """Enregistre (crée ou remplace) la thèse d'un titre — une seule par ticker.

    À appeler avec le contenu rédigé par l'IA. Un nouvel enregistrement pour le
    même ticker REMPLACE le précédent. Le contenu est un **document markdown**
    (titres `#`/`##`, gras, listes, cases à cocher `- [ ]`, images, liens) :
    c'est ce markdown que la fiche affiche et dont elle dérive son sommaire.

    Args:
        ticker: symbole boursier (ex. `"RI.PA"`).
        content: thèse en markdown (non vide, taille bornée).

    Returns:
        `{"status": "ok", "ticker": str, "id": int}`.

    Raises:
        ToolError: ticker ou contenu invalide.
    """
    try:
        return thesis_service.save_thesis(ticker, content)
    except ValueError as exc:
        raise ToolError(str(exc)) from None


def list_theses() -> list[dict]:
    """Liste les thèses enregistrées (métadonnées seules, sans le contenu).

    Returns:
        Liste de `{"id", "ticker", "created_at", "updated_at"}` triée par ticker.
    """
    return thesis_service.list_theses()


def get_thesis(ticker: str) -> dict:
    """Relit la thèse enregistrée d'un titre (avec son contenu complet).

    Args:
        ticker: symbole boursier.

    Returns:
        `{"id", "ticker", "content", "created_at", "updated_at"}`.

    Raises:
        ToolError: thèse absente pour ce ticker.
    """
    try:
        return thesis_service.get_thesis(ticker)
    except ThesisNotFound as exc:
        raise ToolError(str(exc)) from None
    except ValueError as exc:
        raise ToolError(str(exc)) from None


def delete_thesis(ticker: str) -> dict:
    """Supprime la thèse enregistrée d'un titre.

    Args:
        ticker: symbole boursier.

    Returns:
        `{"status": "deleted", "ticker": str}`.

    Raises:
        ToolError: aucune thèse pour ce ticker.
    """
    try:
        thesis_service.delete_thesis(ticker)
    except ThesisNotFound as exc:
        raise ToolError(str(exc)) from None
    except ValueError as exc:
        raise ToolError(str(exc)) from None
    return {"status": "deleted", "ticker": ticker.strip().upper()}


def register(server) -> None:
    """Enregistre les outils de thèse sur le serveur MCP."""
    for fn in (write_thesis, save_thesis, list_theses, get_thesis, delete_thesis):
        server.tool()(fn)
