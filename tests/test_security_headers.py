"""Durcissement HTTP : en-têtes de sécurité et uploads bornés — sans réseau.

Obole est un serveur local sans authentification. Ces tests verrouillent les deux
défenses qui empêchent un simple incident (front injecté, corps géant) de devenir
un problème :

- en-têtes `nosniff` / `X-Frame-Options` / CSP sur toutes les réponses, avec une
  CSP stricte pour l'application (aucun CDN) ;
- refus des uploads au-delà de la limite, **avant** la lecture complète.
"""

from __future__ import annotations

import io
import json

import pytest
from starlette.testclient import TestClient

from obole import config
from obole.api.app import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DB", tmp_path / "cache.sqlite")
    return TestClient(app)


def test_nosniff_on_app_and_api(client):
    for path in ("/", "/api/meta", "/static/app.js"):
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert resp.headers["x-content-type-options"] == "nosniff", path


def test_frame_denied(client):
    assert client.get("/").headers["x-frame-options"] == "DENY"


def test_csp_forbids_external_scripts(client):
    csp = client.get("/").headers["content-security-policy"]
    assert "script-src 'self'" in csp
    assert "cdn" not in csp
    assert "frame-ancestors 'none'" in csp


def test_docs_page_allows_its_cdn(client):
    """La page de doc Swagger charge son UI depuis un CDN — exception assumée."""
    csp = client.get("/api/docs").headers["content-security-policy"]
    assert "cdn.jsdelivr.net" in csp


def test_restore_rejects_oversized_archive(client, monkeypatch):
    monkeypatch.setattr(config, "UPLOAD_MAX_RESTORE_BYTES", 1024)
    payload = json.dumps({"tables": {"x": ["a" * 4096]}}).encode()
    resp = client.post(
        "/api/restore",
        files={"file": ("backup.json", io.BytesIO(payload), "application/json")},
    )
    assert resp.status_code == 413
    assert "trop volumineux" in resp.json()["detail"]


def test_csv_upload_accepts_normal_sized_body(client):
    """Un CSV normal (sous la limite) n'est pas refusé par le plafond."""
    csv = "year;revenue\n2024;1000\n"
    resp = client.post(
        "/api/manual/RI.PA/csv",
        files={"file": ("comptes.csv", io.BytesIO(csv.encode()), "text/csv")},
    )
    assert resp.status_code != 413


def test_thesis_asset_rejects_oversized_image(client, monkeypatch):
    monkeypatch.setattr(config, "UPLOAD_MAX_ASSET_BYTES", 512)
    resp = client.post(
        "/api/thesis/assets",
        files={"file": ("big.png", io.BytesIO(b"\x89PNG" + b"0" * 2048), "image/png")},
    )
    assert resp.status_code == 413
