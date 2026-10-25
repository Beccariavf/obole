"""Tests de l'API FastAPI — avec TestClient, sans réseau.

Mocke les appels à analyze / analyze_ratio / yahoo.search / yahoo.refresh.
"""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from tests.test_analysis import _fake_identity, _make_prices

from obole.api.app import app
from obole.data.yahoo import TickerNotFound
from obole.models import (
    CompanyKind,
    Indicators,
    RatioAnalysis,
    RegressionResult,
    ScoredValue,
    StockAnalysis,
)
from obole.services.serialize import chart_payload


def _fake_analysis(ticker: str, prices=None) -> StockAnalysis:
    """Construit un StockAnalysis factice minimal."""
    reg = RegressionResult(
        a=1.0,
        b=0.05,
        sigma=0.25,
        t_now=20.0,
        fitted_now=50.0,
        start=pd.Timestamp("2000-01-01").date(),
        end=pd.Timestamp("2025-01-01").date(),
        n_points=1000,
    )
    return StockAnalysis(
        identity=_fake_identity(ticker, 50.0),
        indicators=Indicators(
            distance_sigma=ScoredValue(-1.5, "Décotée", True),
            perf_passee=ScoredValue(5.0, "Moyen", True),
            ecart_type=ScoredValue(25.0, "Moyen", True),
            potential_5y=ScoredValue(8.0, "Moyen", True),
            potential_10y=ScoredValue(6.0, "Moyen", True),
            trend=ScoredValue(None, "Haussière", True),
            quality=ScoredValue(65, "Bon", True),
        ),
        regression_raw=reg,
        regression_adj=reg,
        fundamentals=None,
        warnings=["Comptes indisponibles (yfinance)"],
    )


def _fake_ratio_analysis(a, b, pa, pb):
    from obole.engine import ratio as ratio_mod

    sa, sb = ratio_mod.aligned_pair(pa.adjusted, pb.adjusted)
    series = sa / sb
    reg = RegressionResult(
        a=0.0,
        b=0.02,
        sigma=0.15,
        t_now=15.0,
        fitted_now=1.0,
        start=pd.Timestamp("2010-01-01").date(),
        end=pd.Timestamp("2025-01-01").date(),
        n_points=500,
    )
    analysis = RatioAnalysis(
        ticker_a=a.upper(),
        ticker_b=b.upper(),
        label="A / B",
        last_ratio=float(series.iloc[-1]),
        indicators=Indicators(
            distance_sigma=ScoredValue(-0.5, "Légèrement sous-cotée", True),
            perf_passee=ScoredValue(3.0, "Médiocre", False),
            ecart_type=ScoredValue(20.0, "Faible", True),
            potential_5y=ScoredValue(4.0, "Médiocre", False),
            potential_10y=ScoredValue(3.0, "Médiocre", False),
            trend=ScoredValue(None, None, None),
            quality=ScoredValue(None, None, None),
        ),
        regression=reg,
    )
    return analysis, series, sa, sb


@pytest.fixture
def client():
    return TestClient(app)


class TestGetStock:
    def test_200(self, client):
        prices = _make_prices()
        with (
            patch("obole.services.analysis.yahoo.fetch_prices", return_value=prices),
            patch("obole.services.analysis.yahoo.fetch_identity", side_effect=_fake_identity),
            patch("obole.services.analysis.yahoo.fetch_fundamentals", return_value=None),
        ):
            resp = client.get("/api/stock/FAKE")

        assert resp.status_code == 200
        data = resp.json()
        assert data["kind_payload"] == "stock"
        assert data["identity"]["ticker"] == "FAKE"
        assert data["identity"]["name"] == "Fake Corp"
        assert "distance_sigma" in data["indicators"]
        assert "chart" in data
        # MM précalculées serveur sur la série pleine résolution : les 4 jeux de
        # champs (raw/adj × court/long) doivent être présents.
        chart = data["chart"]
        for f in ("ma_short_raw", "ma_long_raw", "ma_short_adj", "ma_long_adj"):
            assert f in chart
            assert len(chart[f]) == len(chart["dates"])
        # Fenêtre de 200 jours couverte par 3000 points quotidiens → dernier point non NaN.
        assert chart["ma_long_raw"][-1] is not None
        assert "warnings" in data
        assert data["fundamentals"] is None
        # Synthèse fondamentale : la grille est toujours présente (8 cartes), même
        # sans comptes — les valeurs absentes sont None (le front affiche « -- »).
        assert len(data["summary"]) == 8
        cards = {c["id"]: c for c in data["summary"]}
        assert set(cards) == {
            "profil",
            "marche",
            "valorisation",
            "dividende",
            "croissance",
            "marges",
            "rentabilite",
            "sante",
        }
        # Carte matrice Croissance : deux lignes (CA/EPS) alignées sur les colonnes.
        growth = cards["croissance"]
        assert growth["columns"] == ["1A", "5A", "10A", "Futur"]
        assert [r["key"] for r in growth["rows"]] == ["ca", "eps"]
        per = next(r for r in cards["valorisation"]["rows"] if r["key"] == "per")
        assert per["value"] is None
        assert per["unit"] == "num"
        # Identité étendue : les champs marché sont sérialisés (None si absents).
        for field in ("industry", "website", "beta", "week52_low", "avg_volume"):
            assert field in data["identity"]

    def test_chart_payload_ma_full_resolution(self):
        """La MA longue doit refléter 200 jours de bourse, pas 200 points décimés."""
        from obole.config import TREND_MA_LONG
        from obole.services.serialize import _downsample

        prices = _make_prices(length=3000)  # 3000 pts quotidiens > 1200 de décimation
        payload = chart_payload(prices)
        n_down = len(payload["dates"])
        assert n_down < 3000  # décimation active
        # MA calculée sur la série PLEINE résolution, réindexée sur les dates décimées.
        raw_down = _downsample(prices.raw)
        expected = prices.raw.rolling(TREND_MA_LONG).mean().reindex(raw_down.index)
        got = payload["ma_long_raw"]
        assert len(expected) == len(got)
        # Comparaison sur les points non-NaN (la fenêtre 200 couvre le début de série).
        for exp, g in zip(expected.to_numpy(), got, strict=True):
            if exp is not None and pd.notna(exp):
                assert g is not None and abs(g - round(float(exp), 4)) < 1e-4

    def test_chart_payload_keeps_the_last_point(self):
        """La décimation conserve le dernier cours (marqueur et KPI live)."""
        from obole.services.serialize import _downsample

        prices = _make_prices(length=3000)
        down = _downsample(prices.raw)
        assert down.index[0] == prices.raw.index[0]
        assert down.index[-1] == prices.raw.index[-1]

        payload = chart_payload(prices)
        assert payload["dates"][-1] == prices.raw.index[-1].strftime("%Y-%m-%d")
        assert payload["price_raw"][-1] == round(float(prices.raw.iloc[-1]), 4)
        assert payload["price_adj"][-1] == round(float(prices.adjusted.iloc[-1]), 4)

    def test_downsample_does_not_duplicate_last_point(self):
        """Quand le dernier point tombe déjà sur le pas, on ne l'ajoute pas deux fois."""
        from obole.services.serialize import _downsample

        prices = _make_prices(length=2401)  # pas = 2, dernier index 2400 = déjà inclus
        down = _downsample(prices.raw, max_points=1200)
        assert len(down) == 1201
        assert down.index[-1] == prices.raw.index[-1]
        assert down.index.is_unique

    def test_chart_payload_dividend_yield_aligned(self):
        """Les rendements continus sont décimés sur le MÊME index que le cours."""
        from obole.models import Fundamentals

        prices = _make_prices(length=3000)
        fund = Fundamentals(
            table=pd.DataFrame(),
            kind=CompanyKind.INDUSTRIAL,
            available_years=0,
            fetched_at=pd.Timestamp("today").date(),
        )
        # Séries dérivées du cours, en pleine résolution (comme les MA).
        fund.dividend_yield = pd.Series(3.0, index=prices.raw.index)
        fund.shareholder_yield = pd.Series(5.0, index=prices.raw.index)
        payload = chart_payload(prices, fund)
        n = len(payload["dates"])
        assert len(payload["div_yield"]) == n
        assert len(payload["sh_yield"]) == n

    def test_chart_payload_no_dividend_series_without_fundamentals(self):
        prices = _make_prices(length=3000)
        payload = chart_payload(prices)
        assert "div_yield" not in payload
        assert "sh_yield" not in payload

    def test_404_on_unknown_ticker(self, client):
        with patch(
            "obole.services.analysis.yahoo.fetch_prices", side_effect=TickerNotFound("UNKNOWN")
        ):
            resp = client.get("/api/stock/UNKNOWN")

        assert resp.status_code == 404
        assert "introuvable" in resp.json()["detail"].lower()

    def test_422_on_short_history(self, client):
        prices = _make_prices(length=20)
        with patch("obole.services.analysis.yahoo.fetch_prices", return_value=prices):
            resp = client.get("/api/stock/TOOSHORT")

        assert resp.status_code == 422


class TestGetRatio:
    def test_200(self, client):
        pa = _make_prices(seed=1)
        pb = _make_prices(seed=2)

        with (
            patch("obole.services.analysis.yahoo.fetch_prices", side_effect=[pa, pb]),
            patch(
                "obole.services.analysis.yahoo.fetch_identity",
                return_value=_fake_identity("A", None),
            ),
        ):
            resp = client.get("/api/ratio?a=A&b=B")

        assert resp.status_code == 200
        data = resp.json()
        assert data["kind_payload"] == "ratio"
        assert data["identity"]["ticker"] == "A / B"
        assert "distance_sigma" in data["indicators"]
        assert "beta" in data["indicators"]

    def test_404_on_unknown(self, client):
        with patch(
            "obole.services.analysis.yahoo.fetch_prices", side_effect=TickerNotFound("UNKNOWN")
        ):
            resp = client.get("/api/ratio?a=UNKNOWN&b=B")

        assert resp.status_code == 404


class TestSearch:
    def test_200_empty_query(self, client):
        resp = client.get("/api/search")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_200_short_query(self, client):
        resp = client.get("/api/search?q=a")
        assert resp.status_code == 200
        assert resp.json() == []


class TestRefresh:
    def test_200(self, client):
        with patch("obole.data.yahoo.refresh") as mock_refresh:
            resp = client.post("/api/refresh/FAKE")

        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        mock_refresh.assert_called_once_with("FAKE")


class TestManualTemplate:
    """La route template sert un CSV exhaustif (toutes les métriques du tableau)."""

    def test_template_covers_all_table_metrics(self, client):
        from obole.models import Fundamentals

        prices = _make_prices(length=400)
        table = pd.DataFrame(
            {
                2025: [100.0, 20.0, 10.0],
                2024: [90.0, 18.0, 9.0],
            },
            index=["Chiffre d'affaires", "Marge opérationnelle", "ROE"],
        )
        fund = Fundamentals(
            table=table,
            kind=CompanyKind.INDUSTRIAL,
            available_years=2,
            fetched_at=pd.Timestamp("today").date(),
        )
        with (
            patch("obole.data.yahoo.fetch_prices", return_value=prices),
            patch("obole.data.yahoo.fetch_identity", return_value=_fake_identity("FAKE", 50.0)),
            patch("obole.data.yahoo.fetch_fundamentals", return_value=fund),
        ):
            resp = client.get("/api/manual/FAKE/template")

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        header = resp.text.splitlines()[0].split(",")
        assert header[0] == "year"
        # Toutes les colonnes du tableau réel sont présentes (source + dérivé).
        for metric in table.index:
            assert metric in header
        # Les métriques de la taxonomie sans donnée restent absentes du template
        # (colonnes = tableau réel), mais la clé source reste reconnue à l'import.
        assert "Chiffre d'affaires" in header

    def test_template_404_on_unknown_ticker(self, client):
        with patch("obole.data.yahoo.fetch_prices", side_effect=TickerNotFound("nope")):
            resp = client.get("/api/manual/INCONNU/template")
        assert resp.status_code == 404


class TestScreenerPing:
    def test_200(self, client):
        resp = client.get("/api/screener/ping")

        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "service": "screener"}


class TestMeta:
    """#06 : /api/meta expose les seuils de config.py (source unique du front)."""

    def test_200_serves_all_thresholds(self, client):
        from obole import config

        resp = client.get("/api/meta")
        assert resp.status_code == 200
        data = resp.json()
        assert data["labels"]["distance"] == [list(e) for e in config.DISTANCE_SIGMA_LABELS]
        assert data["labels"]["ecart"] == [list(e) for e in config.ECART_TYPE_LABELS]
        assert data["ratio_thresholds"]["PER"] == list(config.RATIO_THRESHOLDS["PER"])
        assert data["label_polarity"]["ecart"] == list(config.LABEL_POLARITY["ecart"])
        assert data["reg_years_default"] == config.REGRESSION_YEARS_DEFAULT
        assert data["reg_years_financial"] == config.REGRESSION_YEARS_FINANCIAL
        assert data["beta_min_points"] == config.BETA_MIN_POINTS

    def test_quant_groups_from_config(self, client):
        """La taxonomie des cartes du Quantitatif vient de config.py (source unique)."""
        from obole import config

        data = client.get("/api/meta").json()
        assert data["quant_groups"] == config.QUANT_GROUPS
        # Une métrique par graphe : aucun type « combo »/« multi » dans la taxonomie.
        # `peg` (bandeau de chiffres) a été retiré avec la section Valorisation #20 :
        # aucun producteur de ce type ne subsiste côté config ni côté front.
        types = {c["type"] for g in data["quant_groups"] for c in g["cards"]}
        assert types <= {"line", "bars", "shares", "cagr"}

    def test_dividend_groups_from_config(self, client):
        """La taxonomie de la section Dividende vient de config.py (source unique)."""
        from obole import config

        data = client.get("/api/meta").json()
        assert data["dividend_groups"] == config.DIVIDEND_GROUPS
        assert data["dividend_colors"] == {k: list(v) for k, v in config.DIVIDEND_COLORS.items()}
        types = {c["type"] for g in data["dividend_groups"] for c in g["cards"]}
        assert types <= {"kpi", "yield", "divbars", "divgrowth", "lines", "stacked"}
        # Les unités du dividende sont fusionnées dans `metric_units` (source unique).
        assert data["metric_units"]["Earnings Payout Ratio"] == "pct"
        assert data["metric_units"]["Rachats d'actions"] == "money"

    def test_dividend_cagr_horizons_from_config(self, client):
        """Horizons de CAGR du dividende : source unique config.py."""
        from obole import config

        data = client.get("/api/meta").json()
        assert data["dividend_cagr_horizons"] == list(config.DIVIDEND_CAGR_HORIZONS)

    def test_fundamental_metrics_from_config(self, client):
        """Taxonomie des comptes (CSV) : source unique config.py (union des schémas)."""
        from obole import config

        data = client.get("/api/meta").json()
        assert data["fundamental_metrics"] == [
            {"name": n, "role": r} for n, r in config.FUNDAMENTAL_METRICS_ALL
        ]
        roles = {m["role"] for m in data["fundamental_metrics"]}
        assert roles == {"source", "derived"}
        # Les 7 métriques cœur historiques restent des postes source.
        sources = {m["name"] for m in data["fundamental_metrics"] if m["role"] == "source"}
        assert "Chiffre d'affaires" in sources
        assert "Dette nette" in sources
        # L'union couvre aussi le schéma financier (template d'une banque).
        assert "Total de l'actif" in sources
        assert "Actif net" in sources

    def test_valuation_from_config(self, client):
        """Section Valorisation : taxonomie, horizon, grille et couleur depuis config."""
        from obole import config

        data = client.get("/api/meta").json()
        assert data["valuation_metrics"] == config.VALUATION_METRICS
        assert data["valuation_groups"] == config.VALUATION_GROUPS
        assert data["valuation_horizon_years"] == config.VALUATION_HORIZON_YEARS
        assert data["valuation_target_default"] == config.VALUATION_TARGET_YIELD_DEFAULT
        assert data["valuation_periods"] == list(config.VALUATION_PERIODS)
        assert data["valuation_matrix"]["rows"] == config.VALUATION_MATRIX_ROWS
        assert data["valuation_color_ratios"] == list(config.VALUATION_COLOR_RATIOS)
        # Les courbes de la partie 2 sont continues (jamais de barres).
        types = {c["type"] for g in data["valuation_groups"] for c in g["cards"]}
        assert types == {"vline"}

    def test_dividend_stats_from_engine(self, client):
        """Les stats du dividende (régularité, fréquence, CAGR) viennent de l'engine."""
        from obole.engine import dividends as d

        # La fréquence et les stats sont calculées par engine/dividends (pur) et
        # exposées dans `dividend.stats` : source unique, pas de recalcul JS.
        assert d.frequency({"2024-06-15": 1.0, "2024-12-15": 1.0}) == "Semestriel"
        stats = d.summary({"2024-06-15": 1.0}, {2020: 1.0, 2021: 1.1, 2022: 1.2})
        assert set(stats) == {
            "increase_years",
            "no_cut_years",
            "cagr",
            "frequency",
            "perf_pct",
            "growth",
        }


class TestSummaryMeta:
    """Seuils de la synthèse « Résumé » : /api/summary-meta (source unique config.py)."""

    def test_200_serves_summary_thresholds(self, client):
        from obole import config

        resp = client.get("/api/summary-meta")
        assert resp.status_code == 200
        data = resp.json()
        assert data["market_cap_labels"] == [list(e) for e in config.MARKET_CAP_LABELS]
        assert data["altman_zones"] == [list(e) for e in config.ALTMAN_ZONES]
        assert data["piotroski_zones"] == [list(e) for e in config.PIOTROSKI_ZONES]
        assert data["summary_colors"]["net_debt_ebitda"] == list(
            config.SUMMARY_COLORS["net_debt_ebitda"]
        )


class TestValuationSettings:
    """Paramètres de la calculatrice de prix juste (#20) — persistés par ticker."""

    @pytest.fixture(autouse=True)
    def _isolated_db(self, tmp_path, monkeypatch):
        from obole import config as cfg

        monkeypatch.setattr(cfg, "CACHE_DB", tmp_path / "cache.sqlite")

    def test_get_unknown_returns_null(self, client):
        resp = client.get("/api/valuation/RI.PA")
        assert resp.status_code == 200
        assert resp.json() == {"saved": None}

    def test_put_then_get_roundtrip(self, client):
        body = {
            "metric": "eps",
            "period": 10,
            "growth": 5.51,
            "multiple": 10.04,
            "target_yield": 12,
            "dividend_yield": 7.97,
            "include_dividends": True,
            "fair_price": 64.76,
        }
        resp = client.put("/api/valuation/RI.PA", json=body)
        assert resp.status_code == 200
        saved = resp.json()["saved"]
        assert saved["metric"] == "eps"
        assert saved["fair_price"] == pytest.approx(64.76)

        got = client.get("/api/valuation/RI.PA").json()["saved"]
        assert got["period"] == 10
        assert got["include_dividends"] is True

    def test_put_invalid_metric_422(self, client):
        resp = client.put(
            "/api/valuation/RI.PA",
            json={
                "metric": "nope",
                "period": 10,
                "growth": 1,
                "multiple": 1,
                "target_yield": 12,
                "dividend_yield": 0,
                "fair_price": 1,
            },
        )
        assert resp.status_code == 422

    def test_put_missing_numeric_422(self, client):
        resp = client.put(
            "/api/valuation/RI.PA",
            json={"metric": "eps", "period": 10, "growth": 1, "multiple": 1},
        )
        assert resp.status_code == 422

    def test_put_null_fair_price_accepted(self, client):
        """Un prix juste non calculable (null) ne doit PAS bloquer l'enregistrement."""
        resp = client.put(
            "/api/valuation/RI.PA",
            json={
                "metric": "eps",
                "period": 10,
                "growth": 1,
                "multiple": 1,
                "target_yield": 12,
                "dividend_yield": 0,
                "fair_price": None,
            },
        )
        assert resp.status_code == 200
        saved = resp.json()["saved"]
        assert saved["fair_price"] is None
        assert saved["metric"] == "eps"

    def test_put_net_debt_per_share_optional(self, client):
        """`net_debt_per_share` (bridge EV) est optionnel : absent -> None persisté."""
        resp = client.put(
            "/api/valuation/RI.PA",
            json={
                "metric": "ebitda",
                "period": 10,
                "growth": 1,
                "multiple": 8,
                "target_yield": 12,
                "dividend_yield": 0,
                "fair_price": 100,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["saved"]["net_debt_per_share"] is None

    def test_put_non_numeric_fair_price_422(self, client):
        resp = client.put(
            "/api/valuation/RI.PA",
            json={
                "metric": "eps",
                "period": 10,
                "growth": 1,
                "multiple": 1,
                "target_yield": 12,
                "dividend_yield": 0,
                "fair_price": "abc",
            },
        )
        assert resp.status_code == 422

    def test_delete_clears(self, client):
        body = {
            "metric": "eps",
            "period": 10,
            "growth": 1,
            "multiple": 1,
            "target_yield": 12,
            "dividend_yield": 0,
            "fair_price": 1,
        }
        client.put("/api/valuation/RI.PA", json=body)
        assert client.delete("/api/valuation/RI.PA").json()["status"] == "cleared"
        assert client.get("/api/valuation/RI.PA").json() == {"saved": None}
