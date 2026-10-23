"""Service des assets : versionnage par hash + politique de cache (sans réseau).

Vérifie aussi que le front ne dépend plus d'aucun CDN (C14) : les URLs
versionnées doivent pointer vers des fichiers présents dans `web/`.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from obole.api.app import WEB_DIR, app

ASSET_URL = re.compile(r"/static/[A-Za-z0-9._/-]+")


@pytest.fixture
def client():
    return TestClient(app)


def test_index_versionne_les_urls_d_assets(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-cache"

    urls = ASSET_URL.findall(resp.text)
    assert urls, "index.html doit référencer au moins un asset"
    for url in urls:
        assert f"{url}?v=" in resp.text, f"{url} doit être versionné"


def test_le_hash_correspond_au_contenu(client):
    """« Changement d'asset => nouvelle URL » : le hash suit le contenu."""
    resp = client.get("/")
    for url in ASSET_URL.findall(resp.text):
        version = re.search(re.escape(url) + r"\?v=([0-9a-f]+)", resp.text).group(1)
        content = (WEB_DIR / url.removeprefix("/static/")).read_bytes()
        assert version == hashlib.sha256(content).hexdigest()[:10]


def test_asset_versionne_est_immutable(client):
    resp = client.get("/static/app.js?v=deadbeef")
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_asset_non_versionne_revalide(client):
    resp = client.get("/static/app.js")
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-cache"
    assert "etag" in resp.headers


def test_plus_aucune_dependance_cdn(client):
    """C14 : le front est servi 100 % en local (fonctionne hors ligne)."""
    html = client.get("/").text
    assert "cdn.plot.ly" not in html
    assert "cdn.jsdelivr.net" not in html
    assert "rsms.me" not in html

    for name in ("plotly-2.35.2.min.js", "alpine-3.14.1.min.js"):
        assert (WEB_DIR / "vendor" / name).is_file()
    assert (WEB_DIR / "vendor" / "inter" / "InterVariable.woff2").is_file()


def test_les_assets_vendorises_sont_servis(client):
    resp = client.get("/static/vendor/alpine-3.14.1.min.js")
    assert resp.status_code == 200
    assert "Alpine" in resp.text

    css = client.get("/static/vendor/inter/inter.css")
    assert css.status_code == 200
    assert "/static/vendor/inter/InterVariable.woff2" in css.text

    font = client.get("/static/vendor/inter/InterVariable.woff2")
    assert font.status_code == 200
    assert font.headers["content-type"] == "font/woff2"


def test_aucun_asset_reference_ne_manque(client):
    """Aucune URL versionnée ne doit pointer vers un fichier absent (v=0)."""
    resp = client.get("/")
    # Le placeholder d'asset manquant est EXACTEMENT « v=0 » (pas un hash
    # commençant par 0) : on cible donc le guillemet qui suit.
    assert '?v=0"' not in resp.text
    for url in ASSET_URL.findall(resp.text):
        path = WEB_DIR / url.removeprefix("/static/")
        assert path.is_file(), f"asset manquant : {Path(url)}"
