"""Événements personnalisés annotés sur les graphiques (date + libellé + note).

Une ligne verticale par événement sur le graphe héro : dates importantes de
l'entreprise (OPA, crise, changement de PDG…). Persistés en SQLite (table
`events`), survivent au refresh et aux redémarrages — pattern des données
manuelles et des indices personnalisés.

Clé de rattachement : ticker (action), "A/B" (ratio) ou "INDEX:<id>" (panier).
Cette couche ne fait que de l'I/O + validation : aucun calcul (engine).
"""

from __future__ import annotations

import datetime as _dt

from obole.data import cache

# Bornes de validation (aussi appliquées côté front — miroir app.js).
LABEL_MAX = 60
DESCRIPTION_MAX = 300


def event_key(kind: str, ref: str) -> str:
    """Clé de rattachement des événements : stock|ratio -> ref, index -> INDEX:<id>."""
    kind = (kind or "").strip().lower()
    ref = (ref or "").strip()
    if kind == "index":
        try:
            return f"INDEX:{int(ref)}"
        except ValueError as exc:
            raise ValueError(f"Identifiant d'indice invalide : {ref!r}") from exc
    if kind == "ratio":
        return "RATIO:" + ref.upper().replace(" ", "")
    if kind == "stock":
        return ref.upper()
    raise ValueError(f"Type d'événement inconnu : {kind}")


def list_events(kind: str, ref: str) -> list[dict]:
    """Événements d'un graphe, triés par date croissante."""
    return cache.list_events(event_key(kind, ref))


def add_event(kind: str, ref: str, date: str, label: str, description: str | None = None) -> int:
    """Crée un événement. Lève ValueError si invalide (API -> 422)."""
    return cache.add_event(
        event_key(kind, ref),
        _valid_date(date),
        _valid_label(label),
        _valid_description(description),
    )


def update_event(event_id: int, date: str, label: str, description: str | None = None) -> None:
    """Modifie un événement. Lève ValueError si date/label invalide (API -> 422).

    L'existence est vérifiée par l'appelant (route -> 404) : pas de re-lookup ici.
    """
    cache.update_event(
        event_id, _valid_date(date), _valid_label(label), _valid_description(description)
    )


def delete_event(event_id: int) -> None:
    """Supprime un événement. Lève ValueError si inconnu (API -> 404)."""
    if cache.get_event(event_id) is None:
        raise ValueError(f"Événement inconnu : {event_id}")
    cache.delete_event(event_id)


def _valid_date(date: str) -> str:
    """Normalise et valide la date ISO (YYYY-MM-DD)."""
    date = (date or "").strip()
    try:
        return _dt.date.fromisoformat(date).isoformat()
    except ValueError as exc:
        raise ValueError(f"Date invalide : {date!r} (format attendu AAAA-MM-JJ)") from exc


def _valid_label(label: str) -> str:
    label = (label or "").strip()
    if not label:
        raise ValueError("Le libellé ne peut pas être vide")
    if len(label) > LABEL_MAX:
        raise ValueError(f"Libellé trop long ({len(label)} > {LABEL_MAX} caractères)")
    return label


def _valid_description(description: str | None) -> str | None:
    if description is None:
        return None
    description = description.strip() or None
    if description and len(description) > DESCRIPTION_MAX:
        raise ValueError(
            f"Description trop longue ({len(description)} > {DESCRIPTION_MAX} caractères)"
        )
    return description
