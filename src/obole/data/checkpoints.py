"""Points de contrôle suivis (bande « Suivi » de la fiche action, #21).

Une liste de choses à cocher POSSÉDÉE par l'utilisateur, rattachée à un ticker.
Elle est **indépendante** du document markdown de la thèse : les deux peuvent
porter des éléments différents (les points de contrôle d'un document rédigé ne
sont pas forcément ceux qu'on suit au quotidien).

Clé de rattachement : ticker d'action (majuscules). Persistés en SQLite (table
`checkpoints`), ils survivent au refresh et aux redémarrages — pattern des
événements et des indices personnalisés.

Cette couche ne fait que de l'I/O + validation : aucun calcul (engine).
"""

from __future__ import annotations

from obole import config
from obole.data import cache


def list_checkpoints(ticker: str) -> list[dict]:
    """Points de contrôle d'un ticker, dans l'ordre de création (liste vide si aucun)."""
    return cache.list_checkpoints(_normalize_ref(ticker))


def get_checkpoint(checkpoint_id: int) -> dict | None:
    """Un point de contrôle par id. None si absent."""
    return cache.get_checkpoint(checkpoint_id)


def add_checkpoint(ticker: str, label: object) -> int:
    """Crée un point de contrôle. Lève ValueError si invalide (API -> 422).

    Le cap `CHECKPOINT_MAX_PER_REF` borne la liste par ticker : une entrée hostile
    ne doit pas permettre de faire croître la base sans limite.
    """
    ref = _normalize_ref(ticker)
    if cache.count_checkpoints(ref) >= config.CHECKPOINT_MAX_PER_REF:
        raise ValueError(
            f"Trop de points de contrôle pour {ref} " f"(maximum {config.CHECKPOINT_MAX_PER_REF})"
        )
    return cache.add_checkpoint(ref, _valid_label(label))


def update_checkpoint(checkpoint_id: int, label: object, done: object) -> None:
    """Modifie un point de contrôle (libellé et/ou état). Lève ValueError si invalide.

    L'existence est vérifiée par l'appelant (route -> 404) : pas de re-lookup ici.
    """
    cache.update_checkpoint(checkpoint_id, _valid_label(label), _valid_done(done))


def delete_checkpoint(checkpoint_id: int) -> None:
    """Supprime un point de contrôle. Lève ValueError si inconnu (API -> 404)."""
    if cache.get_checkpoint(checkpoint_id) is None:
        raise ValueError(f"Point de contrôle inconnu : {checkpoint_id}")
    cache.delete_checkpoint(checkpoint_id)


def _normalize_ref(ticker: object) -> str:
    """Normalise (strip, upper) et valide un ticker. Lève ValueError si vide."""
    if not isinstance(ticker, str):
        raise ValueError("Ticker requis")
    ref = ticker.strip().upper()
    if not ref:
        raise ValueError("Le ticker ne peut pas être vide")
    return ref


def _valid_label(label: object) -> str:
    """Libellé : chaîne non vide, bornée à `CHECKPOINT_LABEL_MAX` caractères."""
    if not isinstance(label, str):
        raise ValueError("Le libellé du point de contrôle est requis")
    label = label.strip()
    if not label:
        raise ValueError("Le libellé du point de contrôle ne peut pas être vide")
    if len(label) > config.CHECKPOINT_LABEL_MAX:
        raise ValueError(
            f"Libellé trop long ({len(label)} > {config.CHECKPOINT_LABEL_MAX} caractères)"
        )
    return label


def _valid_done(done: object) -> bool:
    """État coché : booléen strict (jamais une chaîne « false », qui serait vraie)."""
    if isinstance(done, bool):
        return done
    if done is None:
        return False
    raise ValueError("L'état d'un point de contrôle doit être un booléen")
