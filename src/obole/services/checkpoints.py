"""Cas d'usage « points de contrôle suivis » (bande « Suivi », #21).

Couche `services/` : elle assemble `data/checkpoints` sans logique métier propre.
C'est le point d'entrée **partagé API ↔ MCP** du domaine, comme `services/thesis`
et `services/screener` : les deux transports consomment la même validation.

Les erreurs sont **typées** pour que chaque transport les traduise dans son
vocabulaire (`api/` : HTTP 404/422 ; `mcp/` : erreur d'outil) :

- `CheckpointNotFound` -> point inconnu -> 404 ;
- `ValueError` -> entrée invalide -> 422.
"""

from __future__ import annotations

from obole.data import checkpoints as checkpoints_data


class CheckpointNotFound(Exception):
    """Point de contrôle absent."""


def list_checkpoints(ticker: object) -> list[dict]:
    """Points de contrôle d'un ticker (liste vide si aucun). Lève ValueError si le ticker est vide."""
    return checkpoints_data.list_checkpoints(_ticker(ticker))


def add_checkpoint(ticker: object, label: object) -> dict:
    """Crée un point de contrôle. Lève ValueError si le ticker ou le libellé est invalide."""
    key = _ticker(ticker)
    checkpoint_id = checkpoints_data.add_checkpoint(key, label)
    return {"status": "ok", "id": checkpoint_id, "ticker": key}


def update_checkpoint(checkpoint_id: object, label: object, done: object) -> dict:
    """Modifie un point de contrôle. Lève `CheckpointNotFound` s'il est inconnu."""
    cid = _checkpoint_id(checkpoint_id)
    if checkpoints_data.get_checkpoint(cid) is None:
        raise CheckpointNotFound(f"Point de contrôle inconnu : {cid}")
    checkpoints_data.update_checkpoint(cid, label, done)
    return {"status": "ok", "id": cid}


def delete_checkpoint(checkpoint_id: object) -> dict:
    """Supprime un point de contrôle. Lève `CheckpointNotFound` s'il est inconnu."""
    cid = _checkpoint_id(checkpoint_id)
    try:
        checkpoints_data.delete_checkpoint(cid)
    except ValueError as exc:
        raise CheckpointNotFound(str(exc)) from None
    return {"status": "deleted", "id": cid}


def _ticker(ticker: object) -> str:
    if not isinstance(ticker, str) or not ticker.strip():
        raise ValueError("Ticker requis")
    return ticker.strip().upper()


def _checkpoint_id(checkpoint_id: object) -> int:
    if isinstance(checkpoint_id, bool) or not isinstance(checkpoint_id, int):
        raise ValueError("Identifiant de point de contrôle invalide")
    return checkpoint_id
