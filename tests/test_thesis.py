"""Tests des thèses d'entreprise (#09.3) — sans réseau, cache isolé.

Couvre les trois couches du jalon :

- `data/thesis.py` : persistance SQLite + validation bornée (une par ticker) ;
- `services/thesis.py` : construction du prompt (métriques issues de l'analyse
  existante, **sans** la série de prix `chart`) + CRUD à erreurs typées ;
- intégration à la sauvegarde (#03) : une thèse survit à un export/restauration.
"""

from __future__ import annotations

import tempfile
from unittest.mock import patch

import pytest
from tests.test_analysis import _fake_identity, _make_prices

from obole import config
from obole.data import backup, cache, yahoo
from obole.data import thesis as thesis_data
from obole.services import thesis as thesis_service
from obole.services.thesis import ThesisNotFound


@pytest.fixture(autouse=True)
def _isolated_db():
    """Isole le cache sur une base temporaire (évite de toucher cache.sqlite)."""
    _orig = config.CACHE_DB
    config.CACHE_DB = tempfile.mktemp(suffix=".sqlite")
    yield
    config.CACHE_DB = _orig


def _patch_analysis():
    """Patch de l'analyse : identité factice, pas de comptes, prix synthétiques."""
    return (
        patch("obole.services.analysis.yahoo.fetch_identity", side_effect=_fake_identity),
        patch("obole.services.analysis.yahoo.fetch_fundamentals", return_value=None),
        patch("obole.services.analysis.yahoo.fetch_prices", return_value=_make_prices()),
    )


class TestDataThesis:
    """`data/thesis.py` — I/O + validation."""

    def test_roundtrip(self):
        tid = thesis_data.save_thesis("ri.pa", {"pitch": "Décotée"})
        assert isinstance(tid, int)
        got = thesis_data.get_thesis("RI.PA")
        assert got is not None
        assert got["ticker"] == "RI.PA"
        assert got["content"] == {"pitch": "Décotée"}

    def test_get_absent_returns_none(self):
        assert thesis_data.get_thesis("RI.PA") is None

    def test_one_per_ticker_upsert(self):
        thesis_data.save_thesis("RI.PA", {"v": 1})
        thesis_data.save_thesis("RI.PA", {"v": 2})
        assert len(thesis_data.list_theses()) == 1
        assert thesis_data.get_thesis("RI.PA")["content"] == {"v": 2}

    def test_delete(self):
        thesis_data.save_thesis("RI.PA", {"v": 1})
        thesis_data.delete_thesis("RI.PA")
        assert thesis_data.get_thesis("RI.PA") is None

    def test_content_must_be_dict(self):
        with pytest.raises(ValueError, match="objet JSON"):
            thesis_data.save_thesis("RI.PA", ["nope"])

    def test_empty_content_rejected(self):
        with pytest.raises(ValueError, match="vide"):
            thesis_data.save_thesis("RI.PA", {})

    def test_too_large_content_rejected(self):
        with pytest.raises(ValueError, match="volumineux"):
            thesis_data.save_thesis("RI.PA", {"x": "a" * thesis_data.THESIS_CONTENT_MAX})

    def test_empty_ticker_rejected(self):
        with pytest.raises(ValueError, match="vide"):
            thesis_data.save_thesis("   ", {"v": 1})

    def test_non_string_ticker_rejected(self):
        with pytest.raises(ValueError, match="requis"):
            thesis_data.save_thesis(42, {"v": 1})

    def test_list_excludes_content(self):
        thesis_data.save_thesis("RI.PA", {"pitch": "x"})
        row = thesis_data.list_theses()[0]
        assert "content" not in row
        assert set(row) == {"id", "ticker", "created_at", "updated_at"}

    def test_corrupted_content_treated_as_absent(self):
        thesis_data.save_thesis("RI.PA", {"v": 1})
        import sqlite3

        conn = sqlite3.connect(config.CACHE_DB)
        try:
            conn.execute("UPDATE theses SET content='not-json' WHERE ticker='RI.PA'")
            conn.commit()
        finally:
            conn.close()
        assert thesis_data.get_thesis("RI.PA") is None


class TestServiceThesis:
    """`services/thesis.py` — construction du prompt + CRUD typé."""

    def test_write_thesis_returns_prompt_data_warnings(self):
        p1, p2, p3 = _patch_analysis()
        with p1, p2, p3:
            out = thesis_service.write_thesis("fake")
        assert set(out) == {"prompt", "data", "warnings"}
        assert "Fake Corp" in out["prompt"]
        assert "Structure attendue" in out["prompt"]

    def test_write_thesis_omits_chart(self):
        p1, p2, p3 = _patch_analysis()
        with p1, p2, p3:
            out = thesis_service.write_thesis("fake")
        assert "chart" not in out["data"]
        assert "indicators" in out["data"]
        assert "identity" in out["data"]

    def test_write_thesis_tendance_label_only_rendue(self):
        """La tendance est « label-only » (value=None) : son libellé doit passer."""
        p1, p2, p3 = _patch_analysis()
        with p1, p2, p3:
            out = thesis_service.write_thesis("fake")
        indicators = out["data"]["indicators"]
        assert indicators["trend"]["value"] is None  # confirme la sémantique
        label = indicators["trend"]["label"]
        if label:
            assert f"Tendance : {label}" in out["prompt"]
        assert "Tendance : n/d" not in out["prompt"]

    def test_render_metrics_label_only(self):
        """`_labeled` rend le label même sans valeur numérique."""
        assert thesis_service._labeled({"value": None, "label": "Haussière"}) == "Haussière"
        assert thesis_service._labeled({"value": None, "label": None}) == "n/d"
        assert thesis_service._labeled(None) == "n/d"

    def test_render_metrics_dates_defensives(self):
        """Les dates de régression absentes rendent « n/d », pas « None »."""
        line = thesis_service._render_metrics(
            {"regression": {"perf_annual_raw": 5.0, "n_points": 3, "start": None, "end": None}}
        )
        assert "None" not in line

    def test_write_thesis_empty_ticker(self):
        with pytest.raises(ValueError, match="requis"):
            thesis_service.write_thesis("   ")

    def test_save_then_get_then_delete(self):
        saved = thesis_service.save_thesis("ri.pa", {"pitch": "Décotée"})
        assert saved["status"] == "ok"
        assert saved["ticker"] == "RI.PA"
        got = thesis_service.get_thesis("RI.PA")
        assert got["content"] == {"pitch": "Décotée"}
        deleted = thesis_service.delete_thesis("RI.PA")
        assert deleted["status"] == "deleted"

    def test_get_absent_raises_typed_error(self):
        with pytest.raises(ThesisNotFound):
            thesis_service.get_thesis("RI.PA")

    def test_delete_absent_raises_typed_error(self):
        with pytest.raises(ThesisNotFound):
            thesis_service.delete_thesis("RI.PA")

    def test_list_theses(self):
        thesis_service.save_thesis("RI.PA", {"v": 1})
        thesis_service.save_thesis("AI.PA", {"v": 2})
        assert [t["ticker"] for t in thesis_service.list_theses()] == ["AI.PA", "RI.PA"]


class TestThesisBackup:
    """#09.3 — les thèses sont incluses dans la sauvegarde (#03)."""

    def test_theses_in_archive(self):
        thesis_data.save_thesis("RI.PA", {"pitch": "Décotée"})
        arch = backup.build_archive()
        assert "theses" in arch["tables"]
        assert arch["tables"]["theses"][0]["ticker"] == "RI.PA"

    def test_restore_roundtrip(self):
        thesis_data.save_thesis("RI.PA", {"pitch": "Décotée"})
        thesis_data.save_thesis("AI.PA", {"pitch": "Qualité"})
        archive = backup.build_archive()

        with cache.connect() as conn:
            conn.execute("DELETE FROM theses")
            conn.commit()
        assert thesis_data.list_theses() == []

        backup.restore_archive(archive["tables"])
        theses = sorted(thesis_data.list_theses(), key=lambda t: t["ticker"])
        assert [t["ticker"] for t in theses] == ["AI.PA", "RI.PA"]
        assert thesis_data.get_thesis("RI.PA")["content"] == {"pitch": "Décotée"}

    def test_table_registry_declares_theses(self):
        declared = {t for names in backup._TABLE_SINCE.values() for t in names}
        assert "theses" in declared


class TestThesisMarkdown:
    """#21 — le contenu est désormais un document markdown (chaîne)."""

    def test_save_markdown_string(self):
        thesis_service.save_thesis("RI.PA", "## Pitch\n\nDécotée de 3,8 σ.")
        assert thesis_service.get_thesis("RI.PA")["content"] == "## Pitch\n\nDécotée de 3,8 σ."

    def test_markdown_roundtrip_preserves_content(self):
        md = "# Thèse\n\n- [ ] Résultats\n- [x] Dividende\n\n> Citation\n"
        thesis_data.save_thesis("RI.PA", md)
        assert thesis_data.get_thesis("RI.PA")["content"] == md

    def test_empty_markdown_rejected(self):
        with pytest.raises(ValueError, match="vide"):
            thesis_data.save_thesis("RI.PA", "   \n  ")

    def test_oversized_markdown_rejected(self):
        with pytest.raises(ValueError, match="volumineux"):
            thesis_data.save_thesis("RI.PA", "a" * (thesis_data.THESIS_CONTENT_MAX + 1))

    def test_json_object_still_accepted(self):
        """Rétro-compatibilité : une thèse dict du jalon #09.3 reste valide."""
        thesis_data.save_thesis("RI.PA", {"pitch": "Décotée"})
        assert thesis_data.get_thesis("RI.PA")["content"] == {"pitch": "Décotée"}

    def test_other_types_rejected(self):
        with pytest.raises(ValueError, match="markdown ou un objet JSON"):
            thesis_data.save_thesis("RI.PA", 42)


class TestThesisApi:
    """#21 — routes HTTP des thèses (mêmes cas d'usage que le MCP)."""

    @pytest.fixture(autouse=True)
    def _client(self):
        from fastapi.testclient import TestClient

        from obole.api.app import app

        self.client = TestClient(app)

    def test_list_empty(self):
        assert self.client.get("/api/theses").json() == []

    def test_put_then_get_roundtrip(self):
        put = self.client.put("/api/thesis/ri.pa", json={"content": "## Pitch\n\nDécotée."})
        assert put.status_code == 200
        assert put.json()["ticker"] == "RI.PA"
        got = self.client.get("/api/thesis/RI.PA").json()
        assert got["content"] == "## Pitch\n\nDécotée."
        assert got["created_at"] is not None and got["updated_at"] is not None

    def test_put_returns_updated_at(self):
        """Le PUT renvoie l'horodatage : sans lui, le client ne peut plus détecter
        une écriture concurrente (IA via MCP) après son premier enregistrement."""
        put = self.client.put("/api/thesis/RI.PA", json={"content": "x"}).json()
        assert put["updated_at"] is not None
        got = self.client.get("/api/thesis/RI.PA").json()
        assert put["updated_at"] == got["updated_at"]

    def test_put_updated_at_avance_a_la_reecriture(self):
        first = self.client.put("/api/thesis/RI.PA", json={"content": "v1"}).json()
        second = self.client.put("/api/thesis/RI.PA", json={"content": "v2"}).json()
        assert second["updated_at"] >= first["updated_at"]
        assert second["id"] == first["id"]

    def test_get_absent_404(self):
        assert self.client.get("/api/thesis/RI.PA").status_code == 404

    def test_put_empty_content_422(self):
        assert self.client.put("/api/thesis/RI.PA", json={"content": ""}).status_code == 422

    def test_put_missing_content_422(self):
        assert self.client.put("/api/thesis/RI.PA", json={}).status_code == 422

    def test_list_excludes_content(self):
        self.client.put("/api/thesis/RI.PA", json={"content": "x"})
        row = self.client.get("/api/theses").json()[0]
        assert "content" not in row

    def test_delete_then_404(self):
        self.client.put("/api/thesis/RI.PA", json={"content": "x"})
        assert self.client.delete("/api/thesis/RI.PA").json()["status"] == "deleted"
        assert self.client.get("/api/thesis/RI.PA").status_code == 404

    def test_delete_absent_404(self):
        assert self.client.delete("/api/thesis/RI.PA").status_code == 404

    def test_prompt_unknown_ticker_404(self):
        with patch("obole.services.thesis.analysis_service.analyze_ticker") as m:
            m.side_effect = yahoo.TickerNotFound()
            assert self.client.post("/api/thesis/NOPE/prompt").status_code == 404

    def test_prompt_returns_prompt_and_data(self):
        p1, p2, p3 = _patch_analysis()
        with p1, p2, p3:
            resp = self.client.post("/api/thesis/fake/prompt")
        assert resp.status_code == 200
        body = resp.json()
        assert body["prompt"].startswith("Tu es analyste actions long terme")
        assert "chart" not in body["data"]

    def test_prompt_empty_ticker_422(self):
        resp = self.client.post("/api/thesis/%20/prompt")
        assert resp.status_code in (404, 422)

    def test_has_thesis_reflected_in_stock_payload(self):
        self.client.put("/api/thesis/FAKE", json={"content": "## x"})
        p1, p2, p3 = _patch_analysis()
        with p1, p2, p3:
            resp = self.client.get("/api/stock/FAKE")
        assert resp.status_code == 200
        assert resp.json()["has_thesis"] is True
        assert "profile" in resp.json()
