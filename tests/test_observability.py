"""Observabilité (#01) : journalisation, compteur d'échecs, `/api/health`.

Sans réseau : la brique yfinance du contrôle de santé ne fait AUCUN appel (elle
rapporte l'importabilité, la version et les échecs récents). Le cache est isolé
sur une base temporaire (config.CACHE_DB), comme tests/test_settings.py.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from obole import config, observability
from obole.data import cache, health, yahoo


@pytest.fixture(autouse=True)
def _isolated_db():
    """Isole le cache sur une base temporaire (évite de toucher cache.sqlite)."""
    _orig = config.CACHE_DB
    config.CACHE_DB = tempfile.mktemp(suffix=".sqlite")
    yield
    config.CACHE_DB = _orig


@pytest.fixture(autouse=True)
def _clean_state():
    """Remet le logger `obole` et le compteur d'échecs à zéro entre les tests."""
    observability.reset_stats()
    yield
    observability.reset_stats()
    logger = logging.getLogger(observability.LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


@pytest.fixture
def capture():
    """Capture les enregistrements du logger `obole` (indépendant de la propagation)."""
    logger = logging.getLogger(observability.LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    class _ListHandler(logging.Handler):
        def __init__(self) -> None:
            super().__init__()
            self.records: list[logging.LogRecord] = []

        def emit(self, record: logging.LogRecord) -> None:
            self.records.append(record)

    handler = _ListHandler()
    logger.addHandler(handler)
    yield handler
    logger.removeHandler(handler)


@pytest.fixture
def client():
    from obole.api.app import app

    return TestClient(app)


class TestConfigureLogging:
    """J1 — configuration du logging."""

    def test_default_level_is_info(self, monkeypatch):
        monkeypatch.delenv("OBOLE_LOG_LEVEL", raising=False)
        assert observability.resolve_level() == logging.INFO

    def test_level_from_environment(self, monkeypatch):
        monkeypatch.setenv("OBOLE_LOG_LEVEL", "debug")
        assert observability.resolve_level() == logging.DEBUG

    def test_invalid_level_falls_back_to_info(self, monkeypatch):
        monkeypatch.setenv("OBOLE_LOG_LEVEL", "bavard")
        assert observability.resolve_level() == logging.INFO

    def test_configure_is_idempotent(self, tmp_path):
        logger = observability.configure_logging(log_file=tmp_path / "a.log")
        observability.configure_logging(log_file=tmp_path / "b.log")
        assert len(logger.handlers) == 2  # console + fichier, une seule fois

    def test_console_goes_to_stderr(self, tmp_path, capsys):
        logger = observability.configure_logging(log_file=tmp_path / "a.log")
        logger.info("allo")
        captured = capsys.readouterr()
        assert "allo" in captured.err
        assert "allo" not in captured.out  # stdout réservé au message de démarrage

    def test_writes_to_file(self, tmp_path):
        path = tmp_path / "sub" / "obole.log"
        logger = observability.configure_logging(log_file=path)
        logger.info("marqueur-fichier")
        for handler in logger.handlers:
            handler.flush()
        assert path.exists()
        assert "marqueur-fichier" in path.read_text(encoding="utf-8")

    def test_get_logger_prefixes_under_obole(self):
        assert observability.get_logger("yahoo").name == "obole.yahoo"
        assert observability.get_logger("obole.data.yahoo").name == "obole.data.yahoo"


class TestSafeLabel:
    """Anti-injection de logs : un libellé externe ne peut pas forger une entrée."""

    def test_strips_newlines(self):
        assert "\n" not in observability.safe_label("RI.PA\nFAKE ERROR")

    def test_bounded_length(self):
        assert len(observability.safe_label("x" * 5000)) <= 120

    def test_keeps_normal_text(self):
        assert observability.safe_label("prices RI.PA") == "prices RI.PA"


class TestWithRetryLogging:
    """J2/J4 — traçage des échecs et des appels lents."""

    def test_failure_logs_warning_and_degrades(self, capture):
        def boom():
            raise RuntimeError("réseau KO")

        assert yahoo._with_retry(boom, context="prices RI.PA") is None
        warnings = [r for r in capture.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        message = warnings[0].getMessage()
        assert "prices RI.PA" in message
        assert warnings[0].exc_info is not None  # cause tracée, plus avalée

    def test_success_logs_no_warning(self, capture, monkeypatch):
        monkeypatch.setattr(config, "SLOW_CALL_MS", 10**9)
        assert yahoo._with_retry(lambda: 42, context="info RI.PA") == 42
        assert not [r for r in capture.records if r.levelno >= logging.WARNING]

    def test_context_is_optional(self, capture):
        assert yahoo._with_retry(lambda: "ok") == "ok"

    def test_slow_call_is_reported(self, capture, monkeypatch):
        monkeypatch.setattr(config, "SLOW_CALL_MS", 0)  # tout appel est « lent »
        yahoo._with_retry(lambda: 1, context="financials RI.PA")
        slow = [r for r in capture.records if "lent" in r.getMessage()]
        assert len(slow) == 1
        assert "financials RI.PA" in slow[0].getMessage()

    def test_payload_is_never_logged(self, capture):
        payload = {"secret_marker": "ne-doit-pas-apparaitre"}
        assert yahoo._with_retry(lambda: payload) == payload
        assert "ne-doit-pas-apparaitre" not in "\n".join(r.getMessage() for r in capture.records)

    def test_failed_call_records_stat(self, capture):
        assert observability.recent_failures(300) == 0
        yahoo._with_retry(lambda: (_ for _ in ()).throw(RuntimeError("x")), context="prices X")
        assert observability.recent_failures(300) == 1
        assert observability.last_failure() == "prices X"

    def test_failure_stat_expires_outside_window(self, capture):
        observability.record_failure("prices X")
        assert observability.recent_failures(0) == 0

    def test_failure_list_is_bounded(self):
        """Sans poll de /api/health, la liste ne doit pas croître sans borne."""
        for i in range(observability._MAX_FAILURES + 500):
            observability.record_failure(f"prices T{i}")
        assert len(observability._failures) == observability._MAX_FAILURES
        # On garde les plus récents.
        assert observability.last_failure() == f"prices T{observability._MAX_FAILURES + 499}"

    def test_screener_fallback_is_logged(self, capture, monkeypatch):
        from obole.data import screener

        def boom(*_args, **_kwargs):
            raise RuntimeError("quota Yahoo")

        monkeypatch.setattr(screener, "_fetch_universe_yahoo", boom)
        monkeypatch.setattr(config, "UNIVERSE_FR", ["RI.PA"])
        out = screener.fetch_universe(force_refresh=True)
        assert out["source"] == "fallback"
        assert out["tickers"] == ["RI.PA"]
        assert [r for r in capture.records if r.levelno == logging.WARNING]


class TestHealthBricks:
    """J3 — les trois briques et leur sémantique."""

    def test_snapshot_has_three_bricks(self):
        report = health.snapshot()
        assert set(report["bricks"]) == {"yfinance", "sqlite", "cache"}
        assert report["status"] in {"ok", "degraded", "down"}
        for brick in report["bricks"].values():
            assert "status" in brick

    def test_sqlite_brick_reports_schema_version(self):
        brick = health.check_sqlite()
        assert brick["status"] == "ok"
        assert brick["schema_version"] == config.SCHEMA_VERSION

    def test_cache_brick_removes_sentinel_key(self):
        assert health.check_cache()["status"] == "ok"
        with cache.connect() as conn:
            rows = conn.execute(
                "SELECT count(*) FROM cache WHERE ticker=?", (health._HEALTH_KEY.upper(),)
            ).fetchone()[0]
        assert rows == 0

    def test_yfinance_brick_ok_when_no_recent_failure(self):
        assert health.check_yfinance()["status"] == "ok"

    def test_yfinance_brick_degraded_after_failure(self):
        observability.record_failure("prices X")
        brick = health.check_yfinance()
        assert brick["status"] == "degraded"
        assert brick["recent_failures"] == 1

    def test_yfinance_brick_down_when_not_importable(self, monkeypatch):
        monkeypatch.setattr(health, "_import_yfinance", lambda: None)
        assert health.check_yfinance()["status"] == "down"

    def test_bricks_never_raise(self, monkeypatch):
        def boom():
            raise RuntimeError("interne")

        monkeypatch.setattr(health, "check_sqlite", boom)
        report = health.snapshot()
        assert report["bricks"]["sqlite"]["status"] == "down"


class TestHealthRoute:
    """J3 — codes HTTP et absence de réseau."""

    def test_ok_returns_200_with_three_bricks(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        data = r.json()
        assert set(data["bricks"]) == {"yfinance", "sqlite", "cache"}
        assert data["status"] in {"ok", "degraded"}

    def test_sqlite_down_returns_503(self, client, monkeypatch):
        monkeypatch.setattr(health, "check_sqlite", lambda: {"status": "down", "error": "X"})
        r = client.get("/api/health")
        assert r.status_code == 503
        assert r.json()["status"] == "down"

    def test_cache_down_returns_503(self, client, monkeypatch):
        monkeypatch.setattr(health, "check_cache", lambda: {"status": "down", "error": "X"})
        assert client.get("/api/health").status_code == 503

    def test_yfinance_down_returns_200_degraded(self, client, monkeypatch):
        monkeypatch.setattr(health, "check_yfinance", lambda: {"status": "down", "error": "X"})
        r = client.get("/api/health")
        assert r.status_code == 200  # dégradation gracieuse : l'app reste utilisable
        assert r.json()["status"] == "degraded"

    def test_no_network_call(self, client, monkeypatch):
        def forbidden(*_args, **_kwargs):
            raise AssertionError("le contrôle de santé ne doit pas appeler le réseau")

        import yfinance as yf

        monkeypatch.setattr(yf, "Ticker", forbidden)
        monkeypatch.setattr(yf, "download", forbidden)
        monkeypatch.setattr(yf, "Search", forbidden)
        assert client.get("/api/health").status_code == 200


class TestLogsAreIgnored:
    """Le dossier de logs ne doit pas être versionné."""

    def test_logs_dir_gitignored(self):
        root = Path(__file__).resolve().parents[1]
        if not (root / ".git").exists():
            pytest.skip("pas un dépôt git")
        result = subprocess.run(
            ["git", "check-ignore", "logs/obole.log"],
            cwd=root,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, "logs/ doit être ignoré par git"

    def test_log_paths_are_in_repo(self):
        assert config.LOG_DIR.name == "logs"
        assert config.LOG_FILE.parent == config.LOG_DIR
