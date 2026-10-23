"""Tests J5 — parallélisation du scan + cache SQLite concurrent-safe.

Sans réseau : `yahoo.fetch_prices` / `screen_service.screen_stock` sont mockés.
On vérifie que `_scan_universe` (services/screener.py) exécute les tickers en
parallèle (ThreadPoolExecutor borné) tout en isolant les tickers lents/cassés,
et que le cache (`data/cache.py`) supporte les écritures concurrentes
(WAL + busy_timeout).
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from obole import config
from obole.data import cache as cache_data
from obole.models import ScreenResult
from obole.services.screener import _scan_universe


def _sr_dump(ticker: str, **kw) -> dict:
    """ScreenResult -> dict, comme stocké dans le cache de scan."""
    defaults = dict(
        ticker=ticker,
        name="X",
        sector="Tech",
        market_cap=1e9,
        z=-1.0,
        pente_pct=5.0,
        ecart_type_pct=25.0,
        pot_5y_pct=8.0,
        pot_10y_pct=6.0,
        trend_bullish=True,
        roe_pct=12.0,
        per=10.0,
        p_b=1.5,
        p_fcf=9.0,
        fcf_yield_pct=9.0,
        quality_score=60,
        warnings=[],
        error=None,
    )
    defaults.update(kw)
    return ScreenResult(**defaults).__dict__


class TestParallelScan:
    """`_scan_universe` doit paralléliser tout en restant équivalent au séquentiel."""

    def test_scan_is_parallel_not_sequential(self):
        """Un `fetch_prices` qui dort doit être appelé en parallèle (durée ~ un appel)."""
        tickers = ["A.PA", "B.PA", "C.PA", "D.PA"]

        def slow_fetch(ticker):
            time.sleep(0.3)
            return object()  # prix factice : screen_stock est mocké

        started = time.time()
        with (
            patch("obole.services.screener.yahoo.fetch_prices", side_effect=slow_fetch),
            patch(
                "obole.services.screener.screen_service.screen_stock",
                side_effect=lambda t, p, w=None: ScreenResult(**_sr_dump(t)),
            ),
        ):
            out = _scan_universe(tickers, None)

        elapsed = time.time() - started
        # 4 tickers × 0.3s : séquentiel = ~1.2s ; parallèle (4 workers) < 0.6s.
        assert elapsed < 0.8
        assert set(out) == {t for t in tickers}

    def test_scan_isolates_slow_ticker_timeout(self):
        """Un ticker bloqué au-delà du budget est isolé en `error`, sans être attendu."""
        start = time.time()
        tickers = ["OK.PA", "SLOW.PA"]

        with (
            patch("obole.services.screener.config.SCREEN_FETCH_TIMEOUT", 0.05),
            patch("obole.services.screener.config.SCREEN_WORKERS", 8),
            patch(
                "obole.services.screener.yahoo.fetch_prices",
                side_effect=lambda t: time.sleep(5.0) or object(),
            ),
            patch(
                "obole.services.screener.screen_service.screen_stock",
                side_effect=lambda t, p, w=None: ScreenResult(**_sr_dump(t)),
            ),
        ):
            out = _scan_universe(tickers, None)

        elapsed = time.time() - start
        # Le scan rend la main ~au budget (0.05 × 8 = 0.4 s), sans attendre les
        # threads bloqués (sinon 5 s). Budget ≤ 0.4 s.
        assert elapsed < 1.5
        for t in ("OK.PA", "SLOW.PA"):
            assert out[t]["error"] is not None

    def test_scan_isolates_broken_ticker(self):
        """Un ticker qui lève en passe 2 est isolé en `error`, pas de crash global."""
        tickers = ["OK.PA", "BAD.PA"]

        def fetch(ticker):
            if ticker == "BAD.PA":
                raise _not_found()
            return object()

        with (
            patch("obole.services.screener.yahoo.fetch_prices", side_effect=fetch),
            patch(
                "obole.services.screener.screen_service.screen_stock",
                side_effect=lambda t, p, w=None: ScreenResult(**_sr_dump(t)),
            ),
        ):
            out = _scan_universe(tickers, None)

        assert out["BAD.PA"]["error"] is not None
        assert out["OK.PA"]["error"] is None

    def test_scan_results_match_sequential(self):
        """Parallélisme = mêmes résultats (clés + valeurs) que le séquentiel."""
        zmap = {"A.PA": -1.5, "B.PA": 0.4, "C.PA": 2.1}
        tickers = list(zmap)

        def fetch(ticker):
            return object()

        def screen(t, p, w=None):
            return ScreenResult(**_sr_dump(t, z=zmap[t], error=None))

        with (
            patch("obole.services.screener.yahoo.fetch_prices", side_effect=fetch),
            patch("obole.services.screener.screen_service.screen_stock", side_effect=screen),
        ):
            parallel = _scan_universe(tickers, None)

        # Équivalence par comparaison (peu importe l'ordre des threads).
        assert set(parallel) == set(tickers)
        for t in tickers:
            assert parallel[t]["z"] == zmap[t]
            assert parallel[t]["error"] is None


class TestCacheConcurrency:
    """`data/cache.py` doit supporter les écritures concurrentes (WAL)."""

    def test_concurrent_put_get_no_locked(self, tmp_path, monkeypatch):
        """Plusieurs threads écrivent/lisent sans `database is locked`."""
        monkeypatch.setattr(config, "CACHE_DB", tmp_path / "cache-j5.sqlite")

        def worker(i: int) -> None:
            for k in range(20):
                cache_data.put(f"T{i}-{k}", "prices", {"n": k})
                cache_data.get(f"T{i}-{k}", "prices", 10_000)

        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(worker, range(6)))

        # Après l'orage, l'entrée finale se lit correctement.
        assert cache_data.get("T0-19", "prices", 10_000) == {"n": 19}

    def test_wal_journal_mode_enabled(self, tmp_path, monkeypatch):
        """Le journal de la base est en WAL (lecture/écriture concurrentes)."""
        monkeypatch.setattr(config, "CACHE_DB", tmp_path / "cache-j5.sqlite")
        cache_data.put("X.PA", "prices", {"n": 1})
        conn = cache_data._conn()
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        assert str(mode).lower() == "wal"


def _not_found():
    from obole.data.yahoo import TickerNotFound

    return TickerNotFound("BAD.PA")
