"""Tests du staging d'import (#23) — sans réseau.

Le point central du chantier : un import proposé (par l'IA via le MCP, ou par un
collage) n'écrit **rien** en production tant qu'un humain ne l'a pas appliqué.
On vérifie donc surtout ce qui NE se passe PAS : `propose_import` ne touche pas
les données manuelles, et seul `apply_draft` (route REST, jamais un outil MCP)
écrit.
"""

from __future__ import annotations

import sqlite3
import tempfile
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from obole import config
from obole.api.app import app
from obole.data import cache, manual
from obole.services import imports


@pytest.fixture(autouse=True)
def _isolated_db():
    """Isole le cache sur une base temporaire (évite de toucher cache.sqlite)."""
    _orig = config.CACHE_DB
    config.CACHE_DB = tempfile.mktemp(suffix=".sqlite")
    yield
    config.CACHE_DB = _orig


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


CSV_OK = "year;Chiffre d'affaires\n2015;8 500 000"


class TestPropose:
    """`propose_import` : parse, stage, n'écrit jamais en production."""

    def test_creates_pending_draft_without_writing(self):
        result = imports.propose_import("fundamentals", "ri.pa", CSV_OK)
        assert result["draft_id"] >= 1
        assert result["status"] == "pending"
        assert result["ref"] == "RI.PA"  # normalisé en majuscules
        assert result["accepted"] == 1
        assert result["delimiter"] == ";"
        # Garde-fou : aucune donnée métier n'a été écrite.
        assert manual.get_manual("RI.PA") == []
        assert len(imports.list_drafts()) == 1

    def test_report_is_available_in_the_draft(self):
        draft_id = imports.propose_import("fundamentals", "RI.PA", CSV_OK)["draft_id"]
        draft = imports.get_draft(draft_id)
        assert draft["accepted"] == 1
        assert draft["entries"] == [
            {"year": 2015, "metric": "Chiffre d'affaires", "value": 8_500_000.0}
        ]

    def test_rejects_unknown_target(self):
        with pytest.raises(ValueError, match="Cible d'import inconnue"):
            imports.propose_import("portfolio", "RI.PA", CSV_OK)

    def test_rejects_empty_ticker(self):
        with pytest.raises(ValueError, match="Ticker requis"):
            imports.propose_import("fundamentals", "   ", CSV_OK)

    def test_rejects_empty_text(self):
        with pytest.raises(ValueError, match="Contenu CSV vide"):
            imports.propose_import("fundamentals", "RI.PA", "   ")

    def test_rejects_csv_without_valid_entries(self):
        """Un CSV sans valeur exploitable est refusé (pas de brouillon vide)."""
        with pytest.raises(ValueError, match="Aucune entrée valide"):
            imports.propose_import("fundamentals", "RI.PA", "year,Chiffre d'affaires\nn/a,pomme")

    def test_rejects_oversized_text(self):
        huge = "year,Chiffre d'affaires\n" + "x" * (config.IMPORT_MAX_CSV_BYTES + 1)
        with pytest.raises(ValueError, match="trop volumineux"):
            imports.propose_import("fundamentals", "RI.PA", huge)

    def test_rejects_too_many_entries(self):
        rows = "\n".join(f"2015,{i}" for i in range(config.IMPORT_MAX_ENTRIES + 1))
        with pytest.raises(ValueError, match="trop volumineux"):
            imports.propose_import("fundamentals", "RI.PA", f"year,Chiffre d'affaires\n{rows}")

    def test_rejects_when_draft_cap_reached(self):
        for _ in range(config.IMPORT_MAX_DRAFTS):
            imports.propose_import("fundamentals", "RI.PA", CSV_OK)
        with pytest.raises(ValueError, match="Trop de brouillons"):
            imports.propose_import("fundamentals", "RI.PA", CSV_OK)


class TestApplyAndDiscard:
    """Seule `apply_draft` écrit ; `discard_draft` jette sans écrire."""

    def test_apply_writes_entries_and_keeps_audit_row(self):
        draft_id = imports.propose_import("fundamentals", "RI.PA", CSV_OK)["draft_id"]
        result = imports.apply_draft(draft_id)
        assert result["status"] == "applied"
        assert result["entries"] == 1
        assert manual.get_manual("RI.PA") == [
            {"year": 2015, "metric": "Chiffre d'affaires", "value": 8_500_000.0}
        ]
        # Le brouillon est CONSERVÉ en `applied` (trace d'audit), plus `pending`.
        assert imports.list_drafts("pending") == []
        applied = imports.list_drafts("applied")
        assert [d["id"] for d in applied] == [draft_id]
        assert applied[0]["applied_at"] is not None

    def test_double_apply_raises(self):
        draft_id = imports.propose_import("fundamentals", "RI.PA", CSV_OK)["draft_id"]
        imports.apply_draft(draft_id)
        with pytest.raises(imports.ImportDraftNotFound):
            imports.apply_draft(draft_id)

    def test_discard_writes_nothing_and_keeps_audit_row(self):
        draft_id = imports.propose_import("fundamentals", "RI.PA", CSV_OK)["draft_id"]
        assert imports.discard_draft(draft_id)["status"] == "rejected"
        assert manual.get_manual("RI.PA") == []
        assert imports.list_drafts("pending") == []
        # La ligne rejetée est CONSERVÉE (audit du rejet).
        assert [d["id"] for d in imports.list_drafts("rejected")] == [draft_id]

    def test_discard_unknown_raises(self):
        with pytest.raises(imports.ImportDraftNotFound):
            imports.discard_draft(999)

    def test_get_unknown_raises(self):
        with pytest.raises(imports.ImportDraftNotFound):
            imports.get_draft(999)

    def test_invalid_id_raises(self):
        with pytest.raises(ValueError):
            imports.get_draft("abc")
        with pytest.raises(ValueError):
            imports.get_draft(True)


class TestAtomicity:
    """L'écriture métier et le passage à `applied` sont atomiques (#23)."""

    def test_no_pending_left_with_data_written(self):
        """Un brouillon ne peut pas rester `pending` avec les données écrites.

        Si l'écriture des comptes et le marquage `applied` étaient séparés, un
        crash entre les deux laisserait un état incohérent (brouillon `pending`
        + données écrites -> double application au retry). On vérifie qu'après un
        apply réussi, le brouillon est `applied` ET les données présentes.
        """
        draft_id = imports.propose_import("fundamentals", "RI.PA", CSV_OK)["draft_id"]
        imports.apply_draft(draft_id)
        assert imports.list_drafts("pending") == []
        assert manual.get_manual("RI.PA") != []
        assert [d["id"] for d in imports.list_drafts("applied")] == [draft_id]

    def test_apply_is_idempotent_guarded(self):
        """Un second apply sur un brouillon déjà appliqué n'écrit pas une 2ᵉ fois."""
        draft_id = imports.propose_import("fundamentals", "RI.PA", CSV_OK)["draft_id"]
        imports.apply_draft(draft_id)
        before = manual.get_manual("RI.PA")
        with pytest.raises(imports.ImportDraftNotFound):
            imports.apply_draft(draft_id)
        assert manual.get_manual("RI.PA") == before

    def test_write_failure_leaves_draft_pending(self):
        """Si l'écriture échoue, le brouillon reste `pending` (pas de faux `applied`).

        Transaction unique : une erreur pendant l'`INSERT` fait échouer l'ensemble,
        donc le statut n'est pas avancé et l'import reste rejouable.
        """
        import sqlite3

        draft_id = imports.propose_import("fundamentals", "RI.PA", CSV_OK)["draft_id"]
        # `year` est NOT NULL : une entrée invalide fait échouer l'INSERT, donc
        # l'UPDATE de statut (même transaction) n'est pas appliqué.
        with pytest.raises(sqlite3.IntegrityError):
            cache.apply_import_draft(
                draft_id, "RI.PA", [{"year": None, "metric": "CA", "value": 1.0}]
            )
        assert imports.get_draft(draft_id)["status"] == "pending"


class TestPurge:
    """Un brouillon oublié est purgé au-delà de son TTL."""

    def test_expired_draft_is_purged(self):
        draft_id = imports.propose_import("fundamentals", "RI.PA", CSV_OK)["draft_id"]
        future = __import__("time").time() + (config.IMPORT_DRAFT_TTL_DAYS + 1) * 86400
        assert imports._purge_expired(future) == 1
        assert cache.get_import_draft(draft_id) is None

    def test_fresh_draft_is_kept(self):
        imports.propose_import("fundamentals", "RI.PA", CSV_OK)
        assert imports._purge_expired() == 0
        assert len(imports.list_drafts()) == 1


class TestImportRoutes:
    """Routes REST du staging : le seul chemin d'application est humain (UI)."""

    def test_list_is_empty_initially(self, client):
        assert client.get("/api/imports").json() == []

    def test_full_lifecycle(self, client):
        # 1. Une IA propose (ici simulé par un appel direct au service).
        draft_id = imports.propose_import("fundamentals", "RI.PA", CSV_OK)["draft_id"]

        # 2. L'UI liste et lit le brouillon.
        listing = client.get("/api/imports").json()
        assert [d["id"] for d in listing] == [draft_id]
        detail = client.get(f"/api/imports/{draft_id}").json()
        assert detail["accepted"] == 1

        # 3. L'utilisateur applique.
        with patch("obole.data.yahoo.refresh"):
            applied = client.post(f"/api/imports/{draft_id}/apply")
        assert applied.status_code == 200
        assert applied.json()["entries"] == 1
        assert manual.get_manual("RI.PA") != []

    def test_apply_unknown_is_404(self, client):
        assert client.post("/api/imports/999/apply").status_code == 404

    def test_delete_rejects_without_writing(self, client):
        draft_id = imports.propose_import("fundamentals", "RI.PA", CSV_OK)["draft_id"]
        assert client.delete(f"/api/imports/{draft_id}").status_code == 200
        assert manual.get_manual("RI.PA") == []

    def test_delete_unknown_is_404(self, client):
        assert client.delete("/api/imports/999").status_code == 404

    def test_get_unknown_is_404(self, client):
        assert client.get("/api/imports/999").status_code == 404

    def test_propose_route_creates_draft_without_writing(self, client):
        """`POST /api/imports/propose` : miroir HTTP de l'outil MCP, sans écriture."""
        resp = client.post(
            "/api/imports/propose",
            json={"target": "fundamentals", "ref": "RI.PA", "csv_text": CSV_OK},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "pending"
        assert body["accepted"] == 1
        # Aucune donnée métier n'est écrite par la proposition.
        assert manual.get_manual("RI.PA") == []
        # L'UI la retrouve immédiatement dans la liste.
        assert [d["id"] for d in client.get("/api/imports").json()] == [body["draft_id"]]

    def test_propose_route_rejects_bad_input(self, client):
        resp = client.post(
            "/api/imports/propose",
            json={"target": "portfolio", "ref": "RI.PA", "csv_text": CSV_OK},
        )
        assert resp.status_code == 422
        assert isinstance(resp.json()["detail"], str)


class TestManualCsvReport:
    """La route d'import direct renvoie désormais un RAPPORT (et non un simple compte)."""

    def test_report_fields_present(self, client):
        with patch("obole.data.yahoo.refresh"):
            resp = client.post(
                "/api/manual/RI.PA/csv",
                files={"file": ("x.csv", CSV_OK.encode("utf-8"), "text/csv")},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["entries"] == 1
        assert body["accepted"] == 1
        assert body["delimiter"] == ";"
        assert body["rejected"] == []

    def test_empty_csv_is_400_with_string_detail(self, client):
        """Le `detail` reste une CHAÎNE (homogénéité d'API), mais porte la raison."""
        resp = client.post(
            "/api/manual/RI.PA/csv",
            files={"file": ("x.csv", b"year,Chiffre d'affaires\nn/a,pomme", "text/csv")},
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert isinstance(detail, str)
        assert "Aucune entrée valide" in detail
        # La raison du rejet est résumée dans le message.
        assert "bad_year" in detail


class TestSchemaAndBackup:
    """Le schéma v8 et la sauvegarde connaissent la nouvelle table."""

    def test_schema_version_is_8(self):
        assert config.SCHEMA_VERSION == 8
        conn = cache._conn()
        try:
            tables = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        finally:
            conn.close()
        assert "import_drafts" in tables

    def test_backup_knows_import_drafts(self):
        from obole.data import backup

        assert "import_drafts" in backup._TABLE_COLUMNS

    def test_v5_db_gains_table(self):
        conn = sqlite3.connect(config.CACHE_DB)
        try:
            for version in (0, 1, 2, 3, 4):
                cache.MIGRATIONS[version](conn)
            conn.execute(
                "INSERT INTO checkpoints (ref, label, done, created_at) VALUES ('RI.PA','x',0,1.0)"
            )
            cache._write_user_version(conn, 5)
            conn.commit()
        finally:
            conn.close()
        conn = cache._conn()
        try:
            assert cache._read_user_version(conn) == config.SCHEMA_VERSION
            assert conn.execute("SELECT label FROM checkpoints").fetchone()[0] == "x"
        finally:
            conn.close()
