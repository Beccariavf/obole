"""Cas d'usage « indices personnalisés » : CRUD + analyse d'un panier.

Couche `services/` : elle assemble `data/` (persistance des définitions) et
`engine/` (séries chaînées) sans dupliquer la logique. C'est le point d'entrée
**partagé API ↔ MCP** du domaine indices : `api/app.py` et la couche `mcp/`
consomment les mêmes fonctions, donc la même validation (le MCP ne peut pas
importer `api/`).

Les erreurs sont **typées** pour que chaque transport les traduise dans son
vocabulaire (`api/` : HTTP 404/422 ; `mcp/` : erreur d'outil) :

- `IndexNotFound` -> ressource absente (indice, catégorie, ticker) -> 404 ;
- `ValueError` -> entrée invalide (nom vide, < 2 membres…) -> 422.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from obole.data import cache, indices, yahoo

if TYPE_CHECKING:
    import pandas as pd

    from obole.models import BasketAnalysis


class IndexNotFound(Exception):
    """Ressource d'indice absente (indice, catégorie ou ticker membre)."""


def list_indices() -> list[dict]:
    """Catégories + indices personnalisés (définitions, aucun calcul)."""
    return indices.list_indices()


def get_index(index_id: int) -> dict:
    """Définition d'un indice (avec sa catégorie). Lève IndexNotFound si absent."""
    definition = indices.get_index(index_id)
    if definition is None:
        raise IndexNotFound(f"Indice inconnu : {index_id}")
    return definition


def flat_definitions() -> list[dict]:
    """Définitions aplaties (indice -> {id, name, tickers, category_id})."""
    out: list[dict] = []
    for cat in indices.list_indices():
        for ix in cat["indices"]:
            ix = dict(ix)
            ix["category_id"] = cat["id"]
            out.append(ix)
    return out


def create_category(name: object) -> int:
    """Crée une catégorie. Lève ValueError si le nom est vide ou déjà pris.

    `name` est **hostile par défaut** (vient de l'IA ou d'un corps HTTP libre) :
    on exige une chaîne avant de la confier à `data/`, qui rejette déjà le vide
    et les doublons (`ValueError`).
    """
    if not isinstance(name, str):
        raise ValueError("Nom de catégorie requis")
    return indices.create_category(name)


def delete_category(category_id: object) -> None:
    """Supprime une catégorie et ses indices. Lève IndexNotFound si inconnue."""
    cid = _as_int(category_id, "category_id")
    if not cache.category_exists(cid):
        raise IndexNotFound(f"Catégorie inconnue : {cid}")
    indices.delete_category(cid)


def create_index(category_id: object, name: object, tickers: object) -> int:
    """Crée un indice. Lève ValueError si invalide (nom, membres, catégorie)."""
    cid = _as_int(category_id, "category_id")
    if not isinstance(name, str):
        raise ValueError("Nom d'indice requis")
    return indices.create_index(cid, name, _as_tickers(tickers))


def update_index(index_id: object, category_id: object, name: object, tickers: object) -> None:
    """Remplace la définition complète d'un indice. Lève IndexNotFound/ValueError."""
    iid = _as_int(index_id, "index_id")
    cid = _as_int(category_id, "category_id")
    if not isinstance(name, str):
        raise ValueError("Nom d'indice requis")
    if indices.get_index(iid) is None:
        raise IndexNotFound(f"Indice inconnu : {iid}")
    # `data/` valide les membres et l'existence de la catégorie (ValueError -> 422).
    indices.update_index(iid, cid, name, _as_tickers(tickers))


def delete_index(index_id: object) -> None:
    """Supprime un indice. Lève IndexNotFound si inconnu."""
    iid = _as_int(index_id, "index_id")
    if indices.get_index(iid) is None:
        raise IndexNotFound(f"Indice inconnu : {iid}")
    indices.delete_index(iid)


def purge_index_series(index_id: int) -> None:
    """Purge UNIQUEMENT la série chaînée cachée d'un indice (pas ses membres).

    Utilisé par le refresh du résumé : la boucle appelante dédoublonne elle-même
    les membres partagés par plusieurs indices (un seul appel réseau par ticker).
    """
    indices.refresh_index(index_id)


def refresh_index(index_id: int) -> dict:
    """Refresh d'un indice : purge les prix de ses membres ET sa série cachée.

    Lève IndexNotFound si l'indice est inconnu. Renvoie `{"index_id": int}` :
    la forme de la réponse (statut, statut HTTP…) appartient au transport, qui
    l'enrichit.
    """
    definition = get_index(index_id)
    indices.refresh_index(index_id)
    for ticker in definition["tickers"]:
        yahoo.refresh(ticker)
    return {"index_id": index_id}


def analyze_index(index_id: int) -> tuple[BasketAnalysis, pd.Series]:
    """Analyse complète d'un indice (définition + prix membres + panier chaîné).

    Lève IndexNotFound si l'indice est inconnu. Les erreurs de données (membre
    introuvable, panier trop court) remontent en `yahoo.TickerNotFound` /
    `ValueError`, comme les autres cas d'usage d'analyse.

    Import paresseux de `services.analysis` : `analysis` ne dépend pas de ce
    module, mais on évite un import croisé à l'initialisation.
    """
    from obole.services import analysis

    definition = get_index(index_id)
    return analysis.analyze_index(index_id, definition)


def _as_int(value: object, what: str) -> int:
    """Coerce en entier (entrée hostile : `None`, str, float…). ValueError sinon."""
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{what} requis")
    if isinstance(value, int | str):
        try:
            return int(value)
        except ValueError:
            raise ValueError(f"{what} invalide : {value!r}") from None
    raise ValueError(f"{what} invalide : {value!r}")


def _as_tickers(tickers: object) -> list[str]:
    """Coerce en liste de chaînes (la validation métier reste dans `data/`)."""
    if not isinstance(tickers, list):
        raise ValueError("tickers doit être une liste")
    out: list[str] = []
    for t in tickers:
        if not isinstance(t, str):
            raise ValueError("chaque ticker doit être une chaîne")
        out.append(t)
    return out
