"""Lecture bornée d'un upload HTTP (validation d'entrée hostile par défaut).

`UploadFile.read()` charge **tout** le corps en mémoire. Une route d'upload sans
authentification, ouverte sur une boucle locale, reste exposée à un corps géant
(accidentel ou non) : on plafonne donc avant la lecture complète.

La taille déclarée (`Content-Length`) est vérifiée en premier — elle est
fournie par le client, donc jamais de confiance aveugle : si elle est absente
(transfert *chunked*), on lit par tranches et on coupe dès le dépassement.
"""

from __future__ import annotations

from fastapi import HTTPException, UploadFile

CHUNK_SIZE = 64 * 1024


async def read_bounded(file: UploadFile, max_bytes: int, label: str) -> bytes:
    """Lit un upload en refusant tout corps au-delà de `max_bytes`.

    Renvoie les octets bruts ; lève `HTTPException(413)` si le corps est trop
    volumineux. Le message nomme la limite en Mo pour rester actionnable côté
    interface.
    """
    declared = getattr(file, "size", None)
    if isinstance(declared, int) and declared > max_bytes:
        raise _too_large(max_bytes, label)

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise _too_large(max_bytes, label)
        chunks.append(chunk)
    return b"".join(chunks)


def _too_large(max_bytes: int, label: str) -> HTTPException:
    limit_mb = max_bytes / (1024 * 1024)
    return HTTPException(
        status_code=413,
        detail=f"{label} trop volumineux (maximum {limit_mb:g} Mo)",
    )
