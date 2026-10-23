"""Images de thèse : stockage disque + validation stricte.

Les images insérées dans une thèse vivent dans un dossier dédié
(`config.THESIS_ASSETS_DIR`), séparé du code et du front. Rien n'y entre sans
passer par `save_image`, qui applique une **défense en profondeur** :

1. type MIME dans une liste blanche fermée (pas d'extension devinée) ;
2. taille bornée avant écriture (jamais d'écriture d'un flux démesuré) ;
3. signature binaire vérifiée (magic bytes) — le MIME déclaré par le client
   n'est PAS cru sur parole ;
4. nom de fichier **entièrement régénéré** depuis un hash du contenu : aucune
   composante du nom client ne survit (fin du path traversal par construction) ;
5. écriture atomique (fichier temporaire puis renommage).

Cette couche est de l'I/O : elle ne connaît ni l'API ni le front.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from obole import config

# Types acceptés : (MIME, extension, signatures binaires de tête).
_IMAGE_TYPES: dict[str, tuple[str, tuple[bytes, ...]]] = {
    "image/png": (".png", (b"\x89PNG\r\n\x1a\n",)),
    "image/jpeg": (".jpg", (b"\xff\xd8\xff",)),
    "image/gif": (".gif", (b"GIF87a", b"GIF89a")),
    "image/webp": (".webp", (b"RIFF",)),
}

IMAGE_MAX_BYTES = 5 * 1024 * 1024


class InvalidImage(ValueError):
    """Image refusée (type, taille ou contenu non conforme)."""


def assets_dir() -> Path:
    """Dossier des images de thèse (créé à la demande)."""
    path = Path(config.THESIS_ASSETS_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _extension(mime: str, data: bytes) -> str:
    """Extension sûre pour un (MIME, contenu). Lève `InvalidImage` sinon.

    Les magic bytes sont vérifiés : un fichier `.png` qui n'en est pas un est
    refusé, et un exécutable renommé ne peut pas se glisser dans le dossier.
    """
    if mime not in _IMAGE_TYPES:
        raise InvalidImage(f"Type d'image non autorisé : {mime!r}")
    ext, signatures = _IMAGE_TYPES[mime]
    if not any(data.startswith(sig) for sig in signatures):
        raise InvalidImage("Le contenu ne correspond pas au type annoncé")
    # WebP : RIFF....WEBP — on contrôle le second marqueur.
    if mime == "image/webp" and data[8:12] != b"WEBP":
        raise InvalidImage("WebP invalide")
    return ext


def save_image(data: bytes, mime: str) -> dict:
    """Enregistre une image et renvoie `{"url": str, "bytes": int, "mime": str}`.

    Le nom de fichier est un hash du contenu : deux envois identiques
    réutilisent le même fichier, et aucun nom fourni par le client n'est utilisé.
    Lève `InvalidImage` si le type, la taille ou la signature ne conviennent pas.
    """
    if not isinstance(data, (bytes, bytearray)) or not data:  # noqa: UP038
        raise InvalidImage("Image vide")
    if len(data) > IMAGE_MAX_BYTES:
        raise InvalidImage(f"Image trop volumineuse ({len(data)} > {IMAGE_MAX_BYTES} octets)")
    payload = bytes(data)
    extension = _extension(mime, payload)
    digest = hashlib.sha256(payload).hexdigest()[:32]
    target = assets_dir() / f"{digest}{extension}"
    if not target.exists():
        # Écriture atomique : un lecteur concurrent ne voit jamais un fichier
        # partiel, et un échec ne laisse pas de résidu.
        tmp = target.with_suffix(f"{extension}.tmp")
        tmp.write_bytes(payload)
        tmp.replace(target)
    return {
        "url": f"/api/thesis/assets/{target.name}",
        "bytes": len(payload),
        "mime": mime,
    }


def path_for(filename: str) -> Path:
    """Chemin absolu d'une image servie, ou lève `InvalidImage`.

    Le nom demandé est réduit à sa composante finale et comparé à la liste des
    fichiers du dossier : une traversée (`../../etc/passwd`) ne peut pas
    désigner un fichier hors du dossier, même par encodage ou par lien.
    """
    if not isinstance(filename, str) or not filename:
        raise InvalidImage("Nom de fichier requis")
    name = Path(filename).name
    if name != filename or name in {".", ".."} or "/" in filename or "\\" in filename:
        raise InvalidImage("Nom de fichier invalide")
    candidate = (assets_dir() / name).resolve()
    root = assets_dir().resolve()
    if root not in candidate.parents:
        raise InvalidImage("Chemin hors du dossier des images")
    if not candidate.is_file():
        raise InvalidImage("Image introuvable")
    return candidate


def media_type(filename: str) -> str:
    """Type MIME déduit de l'extension (liste blanche, défaut octet-stream)."""
    suffix = Path(filename).suffix.lower()
    for mime, (ext, _sig) in _IMAGE_TYPES.items():
        if ext == suffix:
            return mime
    return "application/octet-stream"
