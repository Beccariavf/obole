"""Service des assets du front : versionnage par hash + politique de cache.

Pas de build côté front : le versionnage se fait au runtime, en suffixant les
URLs de `index.html` par un hash court du contenu du fichier. Un asset modifié
change donc d'URL, ce qui autorise un cache « immuable » (1 an) côté navigateur
sans risque de servir une version périmée. Les URLs non versionnées (appelées
directement, ou référencées depuis un CSS) restent en revalidation (`no-cache`),
sécurisée par l'ETag de `StaticFiles`.
"""

from __future__ import annotations

import hashlib
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

# URL d'asset référencée dans index.html : /static/<chemin> suivi d'un guillemet.
_ASSET_URL = re.compile(r"(/static/[A-Za-z0-9._/-]+?)([\"'])")

IMMUTABLE_CACHE = "public, max-age=31536000, immutable"
REVALIDATE_CACHE = "no-cache"


@lru_cache(maxsize=128)
def _content_hash(path: Path) -> str:
    """Hash court (10 hex) du contenu d'un asset. Mis en cache : les fichiers
    ne changent pas pendant la vie du process (pas de reload)."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:10]


def _stamp(url: str, web_dir: Path) -> str:
    target = web_dir / url.removeprefix("/static/")
    version = _content_hash(target) if target.is_file() else "0"
    return f"{url}?v={version}"


@lru_cache(maxsize=8)
def _render_index_html(web_dir_str: str) -> str:
    web_dir = Path(web_dir_str)
    html = (web_dir / "index.html").read_text(encoding="utf-8")
    return _ASSET_URL.sub(lambda m: _stamp(m.group(1), web_dir) + m.group(2), html)


def render_index(web_dir: Path) -> HTMLResponse:
    """`index.html` avec les URLs d'assets suffixées de leur hash de contenu."""
    return HTMLResponse(
        _render_index_html(str(web_dir)),
        headers={"Cache-Control": REVALIDATE_CACHE},
    )


class VersionedStaticFiles(StaticFiles):
    """`StaticFiles` + `Cache-Control` selon que l'URL est versionnée ou non."""

    async def get_response(self, path: str, scope: dict[str, Any]) -> Response:
        response = await super().get_response(path, scope)
        query = (scope.get("query_string") or b"").decode()
        response.headers["Cache-Control"] = IMMUTABLE_CACHE if "v=" in query else REVALIDATE_CACHE
        return response
