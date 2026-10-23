"""Images de thèse (#21, J7) — stockage, validation stricte, anti-traversée.

L'upload est une **frontière d'entrée hostile** : rien du client n'est cru
(rôle du type MIME, nom de fichier, extension). Le nom du fichier écrit est
régénéré depuis le contenu, donc une traversée de chemin est impossible par
construction — et non par filtrage d'une chaîne.
"""

from __future__ import annotations

import struct
import zlib

import pytest
from fastapi.testclient import TestClient

from obole import config
from obole.data import thesis_assets
from obole.data.thesis_assets import InvalidImage, media_type, path_for, save_image


@pytest.fixture(autouse=True)
def _isolated_assets(tmp_path, monkeypatch):
    """Dossier d'images temporaire : aucun test n'écrit dans le dépôt."""
    monkeypatch.setattr(config, "THESIS_ASSETS_DIR", tmp_path / "assets")


def _png(width: int = 2, height: int = 2) -> bytes:
    """PNG minimal valide (signature + IHDR), suffisant pour la validation."""

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IEND", b"")


class TestSaveImage:
    def test_png_accepted(self):
        out = save_image(_png(), "image/png")
        assert out["mime"] == "image/png"
        assert out["bytes"] == len(_png())
        assert out["url"].startswith("/api/thesis/assets/")
        assert out["url"].endswith(".png")

    def test_filename_is_content_hash_not_client_name(self):
        """Le nom vient du contenu : aucune composante client ne survit."""
        out = save_image(_png(), "image/png")
        name = out["url"].rsplit("/", 1)[-1]
        assert ".." not in name
        assert "/" not in name
        assert len(name.split(".")[0]) == 32

    def test_same_content_same_file(self):
        first = save_image(_png(), "image/png")
        second = save_image(_png(), "image/png")
        assert first["url"] == second["url"]

    def test_unknown_mime_rejected(self):
        with pytest.raises(InvalidImage, match="non autorisé"):
            save_image(_png(), "image/svg+xml")

    def test_missing_mime_rejected(self):
        with pytest.raises(InvalidImage, match="non autorisé"):
            save_image(_png(), "")

    def test_signature_mismatch_rejected(self):
        """Un exécutable renommé n'entre pas : les magic bytes font foi."""
        with pytest.raises(InvalidImage, match="ne correspond pas"):
            save_image(b"MZ\x90\x00executable", "image/png")

    def test_empty_payload_rejected(self):
        with pytest.raises(InvalidImage, match="vide"):
            save_image(b"", "image/png")

    def test_oversized_rejected(self):
        big = _png() + b"\x00" * (thesis_assets.IMAGE_MAX_BYTES + 1)
        with pytest.raises(InvalidImage, match="volumineuse"):
            save_image(big, "image/png")

    def test_jpeg_and_gif_signatures(self):
        assert save_image(b"\xff\xd8\xff\xe0rest", "image/jpeg")["url"].endswith(".jpg")
        assert save_image(b"GIF89a\x01\x00", "image/gif")["url"].endswith(".gif")

    def test_webp_needs_second_marker(self):
        assert save_image(b"RIFF\x00\x00\x00\x00WEBPxx", "image/webp")["url"].endswith(".webp")
        with pytest.raises(InvalidImage, match="WebP invalide"):
            save_image(b"RIFF\x00\x00\x00\x00NOPE", "image/webp")


class TestPathFor:
    def test_valid_name_resolves(self):
        out = save_image(_png(), "image/png")
        name = out["url"].rsplit("/", 1)[-1]
        assert path_for(name).name == name

    def test_traversal_rejected(self):
        for evil in ("../../etc/passwd", "..%2Fpasswd", "a/b.png", "..\\x.png", "..", "."):
            with pytest.raises(InvalidImage):
                path_for(evil)

    def test_absolute_path_rejected(self):
        with pytest.raises(InvalidImage):
            path_for("/etc/passwd")

    def test_unknown_file_rejected(self):
        with pytest.raises(InvalidImage, match="introuvable"):
            path_for("deadbeef.png")

    def test_empty_name_rejected(self):
        with pytest.raises(InvalidImage, match="requis"):
            path_for("")

    def test_no_residue_after_failed_traversal(self):
        with pytest.raises(InvalidImage):
            path_for("../secret.png")
        assert not (config.THESIS_ASSETS_DIR.parent / "secret.png").exists()


class TestMediaType:
    def test_known_extensions(self):
        assert media_type("x.png") == "image/png"
        assert media_type("x.JPG") == "image/jpeg"
        assert media_type("x.webp") == "image/webp"

    def test_unknown_falls_back(self):
        assert media_type("x.bin") == "application/octet-stream"


class TestApiAssets:
    @pytest.fixture(autouse=True)
    def _client(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "THESIS_ASSETS_DIR", tmp_path / "assets")
        from obole.api.app import app

        self.client = TestClient(app)

    def test_upload_then_serve(self):
        resp = self.client.post(
            "/api/thesis/assets",
            files={"file": ("shot.png", _png(), "image/png")},
        )
        assert resp.status_code == 200
        url = resp.json()["url"]
        served = self.client.get(url)
        assert served.status_code == 200
        assert served.headers["content-type"] == "image/png"
        assert served.content.startswith(b"\x89PNG")

    def test_upload_rejects_non_image(self):
        resp = self.client.post(
            "/api/thesis/assets",
            files={"file": ("evil.png", b"MZ\x90\x00", "image/png")},
        )
        assert resp.status_code == 422

    def test_upload_rejects_unauthorized_type(self):
        resp = self.client.post(
            "/api/thesis/assets",
            files={"file": ("x.svg", b"<svg/>", "image/svg+xml")},
        )
        assert resp.status_code == 422

    def test_traversal_route_rejected(self):
        # Encodage d'une traversée dans le CHEMIN de la route : Starlette ne
        # route pas `..` vers ce endpoint, et le service refuse de toute façon.
        with pytest.raises(InvalidImage):
            path_for("..%2F..%2Fetc%2Fpasswd")

    def test_unknown_asset_422(self):
        assert self.client.get("/api/thesis/assets/deadbeef.png").status_code == 422
