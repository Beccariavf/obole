"""Indices personnalisés : définitions persistées + validation.

Les définitions (catégories, noms, membres) vivent dans des tables SQLite
dédiées et survivent au refresh et aux redémarrages (pattern des données
manuelles). La série chaînée calculée, elle, est mise en cache (TTL prix) et
purge systématiquement quand la définition change.

Cette couche ne fait que de l'I/O + validation : aucun calcul (engine).
"""

from __future__ import annotations

import sqlite3

from obole.data import cache


def list_indices() -> list[dict]:
    """Catégories + indices (définitions). Ordre : catégorie, puis nom."""
    return cache.list_indices_by_category()


def get_index(index_id: int) -> dict | None:
    """Définition d'un indice (avec sa catégorie). None si absent."""
    return cache.get_index_definition(index_id)


def create_category(name: str) -> int:
    """Crée une catégorie. Lève ValueError si le nom est vide ou déjà pris."""
    name = _require(name, "nom de catégorie")
    try:
        return cache.create_category(name)
    except sqlite3.IntegrityError:
        raise ValueError(f"Catégorie déjà existante : {name}") from None


def delete_category(category_id: int) -> None:
    """Supprime une catégorie et ses indices. Lève ValueError si inconnue."""
    if not cache.category_exists(category_id):
        raise ValueError(f"Catégorie inconnue : {category_id}")
    cache.delete_category(category_id)


def refresh_index(index_id: int) -> bool:
    """Purge la série cachée d'un indice (après refresh de ses membres).

    Renvoie False si l'indice n'existe pas (appelant -> 404).
    """
    if cache.get_index_definition(index_id) is None:
        return False
    cache.invalidate(f"INDEX:{index_id}")
    return True


def create_index(category_id: int, name: str, tickers: list[str]) -> int:
    """Crée un indice dans une catégorie. Lève ValueError si invalide."""
    name = _require(name, "nom d'indice")
    tickers = _clean_tickers(tickers)
    if not cache.category_exists(category_id):
        raise ValueError(f"Catégorie inconnue : {category_id}")
    return cache.create_index(category_id, name, tickers)


def update_index(index_id: int, category_id: int, name: str, tickers: list[str]) -> None:
    """Remplace la définition complète d'un indice. Lève ValueError si invalide."""
    name = _require(name, "nom d'indice")
    tickers = _clean_tickers(tickers)
    if cache.get_index_definition(index_id) is None:
        raise ValueError(f"Indice inconnu : {index_id}")
    if not cache.category_exists(category_id):
        raise ValueError(f"Catégorie inconnue : {category_id}")
    cache.update_index(index_id, category_id, name, tickers)


def delete_index(index_id: int) -> None:
    """Supprime un indice. Lève ValueError si inconnu."""
    if cache.get_index_definition(index_id) is None:
        raise ValueError(f"Indice inconnu : {index_id}")
    cache.delete_index(index_id)


def _clean_tickers(tickers: list[str]) -> list[str]:
    """Normalise (upper, strip) et dédoublonne en conservant l'ordre."""
    seen: set[str] = set()
    out: list[str] = []
    for t in tickers:
        t = (t or "").strip().upper()
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    if len(out) < 2:
        raise ValueError("Un indice nécessite au moins 2 membres")
    return out


def _require(value: str, what: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ValueError(f"Le {what} ne peut pas être vide")
    return value
