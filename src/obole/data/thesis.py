"""Thèses d'entreprise : persistance SQLite + validation.

Une thèse est un contenu structuré (pitch, bull/bear, catalyseurs, points de
contrôle…) rédigé par une IA cliente à partir des données Obole, rattaché à un
ticker et persisté en base (table `theses`, une par ticker). Les thèses survivent
au redémarrage et sont incluses dans la sauvegarde (#03).

Cette couche ne fait que de l'I/O + validation : aucun calcul (engine), aucune
construction de prompt (services).
"""

from __future__ import annotations

import json

from obole.data import cache

# Bornes de validation (miroir du patron `data/events.py`). Le contenu est un
# JSON libre ; on borne sa taille sérialisée pour se prémunir d'une entrée
# hostile démesurée venue de l'IA (défense en profondeur).
THESIS_CONTENT_MAX = 100_000


def get_thesis(ticker: str) -> dict | None:
    """Thèse d'un ticker (avec `content`), ou None si absente."""
    return cache.get_thesis(_normalize_ticker(ticker))


def list_theses() -> list[dict]:
    """Thèses existantes (métadonnées seules, sans le contenu), triées par ticker."""
    return cache.list_theses()


def save_thesis(ticker: str, content: object) -> int:
    """Enregistre (crée ou remplace) la thèse d'un ticker. Lève ValueError si invalide.

    Une seule thèse par ticker : un nouvel enregistrement remplace le précédent.
    `content` est hostile par défaut : markdown (chaîne bornée) ou objet JSON,
    cf. `_valid_content`.
    """
    key = _normalize_ticker(ticker)
    return cache.save_thesis(key, _valid_content(content))


def delete_thesis(ticker: str) -> None:
    """Supprime la thèse d'un ticker. Lève ValueError si le ticker est vide."""
    cache.delete_thesis(_normalize_ticker(ticker))


def _normalize_ticker(ticker: object) -> str:
    """Normalise (strip, upper) et valide un ticker. Lève ValueError si vide."""
    if not isinstance(ticker, str):
        raise ValueError("Ticker requis")
    key = ticker.strip().upper()
    if not key:
        raise ValueError("Le ticker ne peut pas être vide")
    return key


def _valid_content(content: object) -> dict | str:
    """Valide le contenu d'une thèse. Lève ValueError sinon.

    Deux formes sont admises (chantier #21) :

    - **Markdown** (forme courante, écrite dans la fiche ou par l'IA) : une chaîne
      non vide, bornée à `THESIS_CONTENT_MAX` caractères ;
    - **objet JSON** (forme historique du jalon #09.3) : conservé pour la
      rétro-compatibilité des thèses déjà enregistrées et des clients MCP.
    """
    if isinstance(content, str):
        if not content.strip():
            raise ValueError("Le contenu de la thèse ne peut pas être vide")
        if len(content) > THESIS_CONTENT_MAX:
            raise ValueError(
                f"Contenu de thèse trop volumineux "
                f"({len(content)} > {THESIS_CONTENT_MAX} caractères)"
            )
        return content
    if not isinstance(content, dict):
        raise ValueError("Le contenu de la thèse doit être un texte markdown ou un objet JSON")
    if not content:
        raise ValueError("Le contenu de la thèse ne peut pas être vide")
    try:
        encoded = json.dumps(content)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Contenu de thèse non sérialisable : {exc}") from exc
    if len(encoded) > THESIS_CONTENT_MAX:
        raise ValueError(
            f"Contenu de thèse trop volumineux ({len(encoded)} > {THESIS_CONTENT_MAX} caractères)"
        )
    return content
