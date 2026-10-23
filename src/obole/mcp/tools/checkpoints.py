"""Outils MCP des points de contrôle suivis (bande « Suivi », #21).

Délègue à `services/checkpoints.py` — le point d'entrée **partagé API ↔ MCP** du
domaine : les deux transports consomment les mêmes cas d'usage, donc la même
validation (la couche `mcp/` ne peut pas importer `api/`).

Les erreurs sont **typées** côté service et traduites en `ToolError` :

- `CheckpointNotFound` -> point inconnu (404 côté API) ;
- `ValueError` -> entrée invalide (422 côté API).

Un point de contrôle est une chose à **cocher**, possédée par l'utilisateur et
rattachée à un ticker. Elle est **indépendante** du document markdown de la thèse
(les deux peuvent porter des éléments différents), d'où un outil dédié.
"""

from __future__ import annotations

from mcp.server.mcpserver.exceptions import ToolError

from obole.services import checkpoints as checkpoints_service
from obole.services.checkpoints import CheckpointNotFound


def list_checkpoints(ticker: str) -> list[dict]:
    """Liste les points de contrôle suivis d'un ticker (ordre de création).

    Args:
        ticker: symbole boursier d'action (ex. `"RI.PA"`) — un ratio ou un indice
            n'a pas de bande « Suivi ».

    Returns:
        Liste de `{"id", "ref", "label", "done"}` (vide si aucun).
        Identique à `GET /api/checkpoints/{ticker}`.

    Raises:
        ToolError: ticker vide ou invalide.
    """
    try:
        return checkpoints_service.list_checkpoints(ticker)
    except ValueError as exc:
        raise ToolError(str(exc)) from None


def add_checkpoint(ticker: str, label: str) -> dict:
    """Crée un point de contrôle à surveiller pour un titre.

    Exemple de libellé : `"Marge brute > 28 %"` ou `"Rachats d'actions"`. Le
    nombre de points par ticker est borné (`config.CHECKPOINT_MAX_PER_REF`) et le
    libellé est borné (`config.CHECKPOINT_LABEL_MAX`).

    Args:
        ticker: symbole boursier d'action (ex. `"RI.PA"`).
        label: libellé du point (non vide, borné en longueur).

    Returns:
        `{"status": "ok", "id": int, "ticker": str}`. Identique à
        `POST /api/checkpoints/{ticker}`.

    Raises:
        ToolError: ticker ou libellé vide, libellé trop long, ou plafond atteint.
    """
    try:
        return checkpoints_service.add_checkpoint(ticker, label)
    except ValueError as exc:
        raise ToolError(str(exc)) from None


def update_checkpoint(checkpoint_id: int, label: str, done: bool) -> dict:
    """Modifie un point de contrôle : son libellé et/ou son état coché.

    L'opération remplace **les deux** champs : pour Cocher un point sans changer
    son libellé, renvoyer le libellé courant (lu via `list_checkpoints`).

    Args:
        checkpoint_id: identifiant du point (voir `list_checkpoints`).
        label: nouveau libellé (non vide, borné en longueur).
        done: état coché — booléen **strict** (jamais la chaîne `"false"`, qui
            serait interprétée comme vraie).

    Returns:
        `{"status": "ok", "id": int}`. Identique à
        `PUT /api/checkpoints/{checkpoint_id}`.

    Raises:
        ToolError: point inconnu, libellé vide ou trop long, état non booléen.
    """
    try:
        return checkpoints_service.update_checkpoint(checkpoint_id, label, done)
    except CheckpointNotFound as exc:
        raise ToolError(str(exc)) from None
    except ValueError as exc:
        raise ToolError(str(exc)) from None


def delete_checkpoint(checkpoint_id: int) -> dict:
    """Supprime un point de contrôle suivi.

    Args:
        checkpoint_id: identifiant du point (voir `list_checkpoints`).

    Returns:
        `{"status": "deleted", "id": int}`. Identique à
        `DELETE /api/checkpoints/{checkpoint_id}`.

    Raises:
        ToolError: point inconnu.
    """
    try:
        return checkpoints_service.delete_checkpoint(checkpoint_id)
    except CheckpointNotFound as exc:
        raise ToolError(str(exc)) from None
    except ValueError as exc:
        raise ToolError(str(exc)) from None


def register(server) -> None:
    """Enregistre les outils de suivi sur le serveur MCP."""
    for fn in (list_checkpoints, add_checkpoint, update_checkpoint, delete_checkpoint):
        server.tool()(fn)
