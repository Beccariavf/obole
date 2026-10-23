"""Cas d'usage « import piloté » (#23) — staging, validation humaine.

Un CSV venu de l'extérieur (produit par une IA, ou collé par l'utilisateur) est
**proposé**, jamais appliqué d'emblée. Le flux est :

    propose_import(...)  -> parse (data/manual) -> BROUILLON `pending`
    apply_draft(...)     -> écriture métier     (route REST / UI uniquement)

Le garde-fou est structurel : **aucun outil MCP n'expose `apply_draft`**. Une IA
peut préparer un import propre (elle corrige un format cassé), mais c'est
l'utilisateur qui le valide depuis Obole. Un brouillon `pending` n'a donc aucun
effet métier, et un import massif par erreur se jette d'un geste.

Point d'entrée **partagé API ↔ MCP** : les deux transports consomment les mêmes
cas d'usage (`mcp/` n'importe pas `api/`). Erreurs typées (`ImportError_` ->
404/422 côté API, `ToolError` côté MCP).
"""

from __future__ import annotations

import time

from obole import config
from obole.data import cache, yahoo
from obole.data import manual as manual_data
from obole.models import ImportDraft, ImportReport

# Cibles d'import supportées. Une seule aujourd'hui (comptes financiers, le CSV
# #22) : le portefeuille (transactions/dividendes d'un export courtier) est un
# chantier distinct (détection de doublons propre).
TARGET_FUNDAMENTALS = config.IMPORT_TARGET_FUNDAMENTALS
TARGETS = (TARGET_FUNDAMENTALS,)

# Statuts d'un brouillon (cf. `data/cache.mark_import_draft`).
STATUS_PENDING = "pending"
STATUS_APPLIED = "applied"
STATUS_REJECTED = "rejected"

# Clés du résumé du rapport joint à chaque brouillon listé (affichage UI).
_SUMMARY_KEYS = ("accepted", "overridden", "rejected_total", "delimiter")


class ImportDraftNotFound(Exception):
    """Brouillon d'import absent (ou déjà appliqué/rejeté)."""


def propose_import(target: object, ref: object, csv_text: object) -> dict:
    """Parse un CSV et crée un BROUILLON en attente de validation humaine.

    N'écrit **aucune** donnée métier : la seule écriture est le brouillon
    lui-même. Renvoie `{draft_id, summary, rejected, ...}` pour que l'appelant
    (IA ou UI) puisse rendre compte avant toute application.

    Args:
        target: cible de l'import (`"fundamentals"` aujourd'hui).
        ref: clé de la cible (ticker Yahoo, ex. `"RI.PA"`).
        csv_text: contenu CSV brut (jamais un chemin : aucun accès disque).

    Returns:
        `{"draft_id": int, "target": str, "ref": str, "accepted": int,
        "overridden": int, "rejected_total": int, "rejected": [...],
        "unknown_columns": [...], "derived_columns": [...], "delimiter": str,
        "status": "pending"}`.

    Raises:
        ValueError: cible inconnue, ticker vide, texte vide ou trop volumineux,
            ou plus de `IMPORT_MAX_ENTRIES` valeurs (l'entrée vient de l'IA).
    """
    target_key = _validate_target(target)
    ref_key = _validate_ref(ref)
    text = _validate_text(csv_text)

    _purge_expired()
    if cache.count_import_drafts(STATUS_PENDING) >= config.IMPORT_MAX_DRAFTS:
        raise ValueError(
            f"Trop de brouillons d'import en attente (maximum {config.IMPORT_MAX_DRAFTS}) : "
            "valide ou supprime-en avant d'en créer un nouveau"
        )

    report = _parse(target_key, ref_key, text)
    if report.accepted == 0:
        raise ValueError(
            "Aucune entrée valide dans le CSV (vérifie l'en-tête 'year' et les noms de colonnes)"
        )
    if report.accepted > config.IMPORT_MAX_ENTRIES:
        raise ValueError(
            f"Import trop volumineux ({report.accepted} valeurs, "
            f"maximum {config.IMPORT_MAX_ENTRIES})"
        )

    draft_id = cache.add_import_draft(target_key, ref_key, report.to_dict(), STATUS_PENDING)
    return {
        "draft_id": draft_id,
        "target": target_key,
        "ref": ref_key,
        "status": STATUS_PENDING,
        **report.to_dict(),
    }


def list_drafts(status: str = STATUS_PENDING) -> list[dict]:
    """Brouillons d'un statut (du plus récent au plus ancien), avec le résumé du rapport.

    On joint le résumé du brouillon (`accepted`, `overridden`, `rejected_total`…)
    pour que l'UI affiche « N valeur(s) à importer » sans ouvrir chaque détail.
    """
    out = []
    for draft in cache.list_import_drafts(status):
        payload = cache.get_import_draft(draft["id"])
        summary = (payload or {}).get("payload", {})
        out.append({**draft, **{k: summary.get(k) for k in _SUMMARY_KEYS if k in summary}})
    return out


def get_draft(draft_id: object) -> dict:
    """Brouillon complet (rapport inclus). Lève `ImportDraftNotFound` si absent."""
    draft = cache.get_import_draft(_validate_id(draft_id))
    if draft is None:
        raise ImportDraftNotFound(f"Brouillon d'import inconnu : {draft_id}")
    return _to_dict(draft)


def discard_draft(draft_id: object) -> dict:
    """Rejette un brouillon : il ne sera **jamais** appliqué.

    Le statut passe `rejected` et la ligne est **conservée** (audit du rejet) —
    c'est la trace de ce qui a été écarté, sans effet sur les données métier.

    Lève `ImportDraftNotFound` si absent ou déjà traité (appliqué/rejeté).
    """
    draft_id_int = _validate_id(draft_id)
    draft = cache.get_import_draft(draft_id_int)
    if draft is None or draft["status"] != STATUS_PENDING:
        raise ImportDraftNotFound(f"Brouillon d'import inconnu ou déjà traité : {draft_id}")
    cache.mark_import_draft(draft_id_int, STATUS_REJECTED)
    return {"status": "rejected", "draft_id": draft_id_int}


def apply_draft(draft_id: object) -> dict:
    """Applique un brouillon : seule écriture métier du flux (validation humaine).

    ⚠️ **N'est appelée que par la route REST** (action de l'utilisateur) : aucun
    outil MCP ne l'expose, sinon l'IA contournerait la validation.

    L'écriture des données manuelles ET le passage du brouillon à `applied` sont
    faits dans **une seule transaction** (`cache.apply_import_draft`) : jamais
    d'état où les données sont écrites mais le brouillon encore `pending`, ce qui
    permettrait une double application. Le brouillon est ensuite **conservé**
    (trace d'audit) et observable via `list_drafts("applied")`.

    Lève `ImportDraftNotFound` si le brouillon est absent ou déjà traité.
    """
    draft_id_int = _validate_id(draft_id)
    draft = cache.get_import_draft(draft_id_int)
    if draft is None or draft["status"] != STATUS_PENDING:
        raise ImportDraftNotFound(f"Brouillon d'import inconnu ou déjà traité : {draft_id}")

    target = draft["target"]
    if target != TARGET_FUNDAMENTALS:
        raise ValueError(f"Cible d'import non supportée : {target}")
    ref = draft["ref"]
    entries = draft["payload"].get("entries", [])

    # Écriture métier + statut `applied` : atomique (tout ou rien).
    written = cache.apply_import_draft(draft_id_int, ref, entries)
    # Purge du cache APRÈS le commit : effet de bord réseau, hors transaction —
    # un échec ici ne doit pas annuler un import déjà validé.
    yahoo.refresh(ref)
    return {
        "status": "applied",
        "draft_id": draft_id_int,
        "target": target,
        "ref": ref,
        "entries": written,
    }


def _parse(target: str, ref: str, text: str) -> ImportReport:
    """Dispatch du parsing par cible (une seule implémentation aujourd'hui)."""
    if target == TARGET_FUNDAMENTALS:
        return manual_data.import_csv(ref, text)
    raise ValueError(f"Cible d'import non supportée : {target}")


def _purge_expired(now: float | None = None) -> int:
    """Supprime les brouillons `pending` plus vieux que `IMPORT_DRAFT_TTL_DAYS`.

    Évite qu'un brouillon oublié s'accumule indéfiniment. Renvoie le nombre purgé.
    """
    current = time.time() if now is None else now
    cutoff = current - config.IMPORT_DRAFT_TTL_DAYS * 86400
    stale = cache.list_import_draft_ids_before(cutoff, STATUS_PENDING)
    for draft_id in stale:
        cache.delete_import_draft(draft_id)
    return len(stale)


def _to_dict(draft: dict) -> dict:
    """Normalise un enregistrement `cache` en `ImportDraft` sérialisable."""
    model = ImportDraft(
        id=draft["id"],
        target=draft["target"],
        ref=draft["ref"],
        payload=draft["payload"],
        status=draft["status"],
        created_at=draft["created_at"],
        applied_at=draft["applied_at"],
    )
    return {
        "id": model.id,
        "target": model.target,
        "ref": model.ref,
        "status": model.status,
        "created_at": model.created_at,
        "applied_at": model.applied_at,
        **model.payload,
    }


def _validate_target(target: object) -> str:
    if not isinstance(target, str) or target not in TARGETS:
        raise ValueError(f"Cible d'import inconnue : {target!r} (attendu : {', '.join(TARGETS)})")
    return target


def _validate_ref(ref: object) -> str:
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError("Ticker requis")
    return ref.strip().upper()


def _validate_text(text: object) -> str:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Contenu CSV vide")
    if len(text.encode("utf-8")) > config.IMPORT_MAX_CSV_BYTES:
        raise ValueError(
            f"Contenu CSV trop volumineux (maximum {config.IMPORT_MAX_CSV_BYTES} octets)"
        )
    return text


def _validate_id(draft_id: object) -> int:
    if isinstance(draft_id, bool) or not isinstance(draft_id, int):
        raise ValueError("Identifiant de brouillon invalide")
    return draft_id
