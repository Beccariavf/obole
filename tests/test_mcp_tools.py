"""Tests des outils MCP de lecture (jalons 09.1 et 09.2) — sans réseau, transport in-memory.

Deux familles :

- **Parité outil ↔ API** : un outil MCP renvoie le même payload que la route HTTP
  équivalente — en `view="full"` strictement, ou une fois la clé `chart` retirée
  en `view="summary"` (défaut). C'est l'invariant central du jalon : le MCP n'est
  qu'un autre transport au-dessus des mêmes cas d'usage (`services/`).
- **Invariants** : délégation (aucune formule dans `mcp/`), erreurs typées
  traduites en `ToolError`, entrée hostile validée.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from mcp import Client
from tests.test_analysis import _fake_identity, _make_prices

from obole.api.app import app
from obole.data.yahoo import TickerNotFound
from obole.mcp import server as mcp_server
from obole.mcp.tools import indices as indices_tools
from obole.models import ScreenResult


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def isolated_db():
    """Isole le cache sur une base temporaire (évite de toucher `cache.sqlite`).

    Fixture **module-level** : les classes qui écrivent en base (thèse,
    portefeuille, suivi) s'y rattachent via `@pytest.mark.usefixtures`, plutôt
    que de recopier le corps du `yield` dans chacune.
    """
    import tempfile

    from obole import config

    _orig = config.CACHE_DB
    config.CACHE_DB = tempfile.mktemp(suffix=".sqlite")
    yield
    config.CACHE_DB = _orig


async def _call(name: str, args: dict) -> dict | list:
    """Appelle un outil MCP et renvoie son payload décodé.

    Les outils typés (`TypedDict`) peuplent `structured_content` ; les outils qui
    renvoient un `dict` libre sérialisent leur résultat en JSON dans le contenu
    texte, et un retour `list` est encapsulé sous `{"result": [...]}` par le SDK.
    On normalise ces formes pour comparer au payload HTTP brut.
    """
    async with Client(mcp_server.mcp) as client:
        result = await client.call_tool(name, args)
    assert result.is_error is False, result.content
    if result.structured_content is not None:
        payload = result.structured_content
    else:
        payload = json.loads(result.content[0].text)
    # Un retour `list` est encapsulé sous `{"result": [...]}` par le SDK (dans les
    # deux formes) : on déballe pour comparer au payload HTTP brut.
    if isinstance(payload, dict) and set(payload) == {"result"}:
        return payload["result"]
    return payload


async def _call_error(name: str, args: dict) -> str:
    """Appelle un outil en s'attendant à une erreur, et renvoie le message."""
    async with Client(mcp_server.mcp) as client:
        result = await client.call_tool(name, args)
    assert result.is_error is True
    return result.content[0].text


# --- Parité outil ↔ API ------------------------------------------------------


def _assert_parite(tool_payload: dict, api_payload: dict, view: str) -> None:
    """Invariant de parité selon le niveau de détail demandé.

    `full` : payload STRICTEMENT identique à la route (aucune clé écartée).
    `summary` : identique, moins la série de prix `chart` — et rien d'autre.
    """
    if view == "full":
        assert "chart" in tool_payload
        assert tool_payload == api_payload
    else:
        assert "chart" not in tool_payload
        assert tool_payload == {k: v for k, v in api_payload.items() if k != "chart"}


class TestPariteAvecLApi:
    """L'outil MCP doit servir le MÊME payload que la route HTTP équivalente."""

    @pytest.mark.anyio
    @pytest.mark.parametrize("view", ["summary", "full"])
    async def test_stock_analysis_parite(self, view):
        """Action : `summary` = API sans `chart`, `full` = API intégrale."""
        from fastapi.testclient import TestClient

        prices = _make_prices()
        client = TestClient(app)
        with (
            patch("obole.services.analysis.yahoo.fetch_prices", return_value=prices),
            patch("obole.services.analysis.yahoo.fetch_identity", side_effect=_fake_identity),
            patch("obole.services.analysis.yahoo.fetch_fundamentals", return_value=None),
        ):
            api_payload = client.get("/api/stock/FAKE").json()
            tool_payload = await _call("get_stock_analysis", {"ticker": "FAKE", "view": view})

        _assert_parite(tool_payload, api_payload, view)

    @pytest.mark.anyio
    @pytest.mark.parametrize("view", ["summary", "full"])
    async def test_ratio_analysis_parite(self, view):
        """Ratio A/B : `summary` = API sans `chart`, `full` = API intégrale."""
        from fastapi.testclient import TestClient

        prices_a = _make_prices()
        prices_b = _make_prices(seed=99)

        def _prices(ticker):
            return prices_b if ticker == "OTHER" else prices_a

        client = TestClient(app)
        with (
            patch("obole.services.analysis.yahoo.fetch_prices", side_effect=_prices),
            patch("obole.services.analysis.yahoo.fetch_identity", side_effect=_fake_identity),
        ):
            api_payload = client.get("/api/ratio?a=FAKE&b=OTHER").json()
            tool_payload = await _call(
                "get_ratio_analysis", {"a": "FAKE", "b": "OTHER", "view": view}
            )

        _assert_parite(tool_payload, api_payload, view)

    @pytest.mark.anyio
    async def test_search_parite(self):
        from fastapi.testclient import TestClient

        hits = [{"symbol": "RI.PA", "name": "Pernod Ricard", "exchange": "Paris"}]
        client = TestClient(app)
        with patch("obole.data.yahoo.search", return_value=hits) as mocked:
            api_payload = client.get("/api/search?q=pernod").json()
            tool_payload = await _call("search_tickers", {"query": "pernod"})

        assert tool_payload == api_payload
        # Les deux transports passent bien par le même `data/yahoo.search`.
        assert mocked.call_count >= 1

    @pytest.mark.anyio
    @pytest.mark.parametrize("view", ["summary", "full"])
    async def test_index_analysis_parite(self, view):
        """Fiche indice : `summary` = API sans `chart`, `full` = API intégrale."""
        import time

        from fastapi.testclient import TestClient

        created = await _call("create_index_category", {"name": f"Parite {time.time_ns()}"})
        cat_id = created["id"]
        try:
            idx = await _call(
                "create_index",
                {"category_id": cat_id, "name": "Panier", "tickers": ["A.PA", "B.PA"]},
            )
            idx_id = idx["id"]

            client = TestClient(app)
            with (
                patch("obole.data.yahoo.fetch_prices", return_value=_make_prices(seed=1)),
                patch(
                    "obole.services.analysis.yahoo.fetch_identity",
                    side_effect=_fake_identity,
                ),
                patch("obole.services.analysis.cache.put", lambda *a, **k: None),
                patch("obole.services.analysis.cache.get", lambda *a, **k: None),
            ):
                api_payload = client.get(f"/api/index/{idx_id}").json()
                tool_payload = await _call("get_index_analysis", {"index_id": idx_id, "view": view})

            _assert_parite(tool_payload, api_payload, view)
        finally:
            await _call("delete_index_category", {"category_id": cat_id})


# --- Optimisation du poids des payloads (jalon lean) -------------------------


class TestPayloadLean:
    """`view="summary"` (défaut) omet la série de prix ; `full` l'inclut.

    La parité (classe précédente) prouve déjà QUELLE clé est écartée ; on mesure
    ici le GAIN de volume, qui est la raison d'être du jalon.
    """

    @pytest.mark.anyio
    async def test_gain_de_volume(self):
        """Le payload summary pèse une fraction du full (rapport, pas un plafond).

        Seuil relatif volontairement large : la taille exacte de la fixture peut
        évoluer, le rapport non (le graphe représente l'essentiel du payload).
        """
        with (
            patch("obole.services.analysis.yahoo.fetch_identity", side_effect=_fake_identity),
            patch("obole.services.analysis.yahoo.fetch_fundamentals", return_value=None),
            patch("obole.services.analysis.yahoo.fetch_prices", return_value=_make_prices()),
        ):
            summary = await _call("get_stock_analysis", {"ticker": "FAKE"})
            full = await _call("get_stock_analysis", {"ticker": "FAKE", "view": "full"})

        def _size(o: dict) -> int:
            return len(json.dumps(o, default=str, ensure_ascii=False))

        assert _size(summary) < 0.25 * _size(full)

    @pytest.mark.anyio
    async def test_view_invalide_rejetee_via_l_outil(self):
        """`view` inconnu échoue par le CHEMIN RÉEL de l'outil, pas juste le helper."""
        msg = await _call_error("get_stock_analysis", {"ticker": "FAKE", "view": "Full"})
        assert "view" in msg.lower()


# --- Invariants et entrées hostiles -----------------------------------------


class TestInvariants:
    @pytest.mark.anyio
    async def test_stock_ticker_vide_erreur(self):
        msg = await _call_error("get_stock_analysis", {"ticker": "   "})
        assert "Ticker requis" in msg

    @pytest.mark.anyio
    async def test_stock_ticker_inconnu_erreur(self):
        with patch(
            "obole.services.analysis.yahoo.fetch_prices", side_effect=TickerNotFound("NOPE")
        ):
            msg = await _call_error("get_stock_analysis", {"ticker": "NOPE"})
        assert "introuvable" in msg

    @pytest.mark.anyio
    async def test_ratio_ticker_manquant_erreur(self):
        msg = await _call_error("get_ratio_analysis", {"a": "RI.PA", "b": ""})
        assert "Deux tickers requis" in msg

    @pytest.mark.anyio
    async def test_index_inconnu_erreur(self):
        msg = await _call_error("get_index_analysis", {"index_id": 999999})
        assert "inconnu" in msg


class TestCrudIndicesViaOutil:
    """Le CRUD passe par `services/indices.py` (mêmes règles que l'API)."""

    @pytest.mark.anyio
    async def test_cycle_complet(self):
        import time

        name = f"Tool {time.time_ns()}"
        created = await _call("create_index_category", {"name": name})
        cat_id = created["id"]
        try:
            listed = await _call("list_indices", {})
            assert any(c["id"] == cat_id for c in listed)

            idx = await _call(
                "create_index",
                {"category_id": cat_id, "name": "Panier", "tickers": ["a.pa", "b.pa"]},
            )
            idx_id = idx["id"]

            # Normalisation des tickers portée par `data/` (pas par l'outil).
            listed = await _call("list_indices", {})
            cat = next(c for c in listed if c["id"] == cat_id)
            assert cat["indices"][0]["tickers"] == ["A.PA", "B.PA"]

            updated = await _call(
                "update_index",
                {
                    "index_id": idx_id,
                    "category_id": cat_id,
                    "name": "Renommé",
                    "tickers": ["C.PA", "D.PA"],
                },
            )
            assert updated["id"] == idx_id

            deleted = await _call("delete_index", {"index_id": idx_id})
            assert deleted["status"] == "deleted"
        finally:
            await _call("delete_index_category", {"category_id": cat_id})

    @pytest.mark.anyio
    async def test_moins_de_deux_membres_erreur(self):
        import time

        created = await _call("create_index_category", {"name": f"Tool {time.time_ns()}"})
        cat_id = created["id"]
        try:
            msg = await _call_error(
                "create_index",
                {"category_id": cat_id, "name": "Solo", "tickers": ["A.PA"]},
            )
            assert "2 membres" in msg
        finally:
            await _call("delete_index_category", {"category_id": cat_id})

    @pytest.mark.anyio
    async def test_tickers_non_liste_erreur(self):
        import time

        created = await _call("create_index_category", {"name": f"Tool {time.time_ns()}"})
        cat_id = created["id"]
        try:
            # Entrée hostile : `tickers` arrive en chaîne (jamais une liste). Le
            # SDK valide le schéma avant d'appeler la fonction (défense en amont).
            msg = await _call_error(
                "create_index",
                {"category_id": cat_id, "name": "X", "tickers": "A.PA,B.PA"},
            )
            assert "valid list" in msg
        finally:
            await _call("delete_index_category", {"category_id": cat_id})

    @pytest.mark.anyio
    async def test_categorie_vide_erreur(self):
        msg = await _call_error("create_index_category", {"name": "   "})
        assert "vide" in msg

    @pytest.mark.anyio
    async def test_nom_non_chaine_rejete(self):
        # `name` typé `str` : le SDK (Pydantic) rejette un entier avant la fonction.
        msg = await _call_error("create_index_category", {"name": 42})
        assert "valid string" in msg


class TestInvariantsExecution:
    def test_les_outils_delegent_aux_services(self):
        """Aucune formule dans `mcp/tools/` : les modules importent `services`."""
        import inspect

        src = inspect.getsource(indices_tools)
        assert "obole.services" in src or "services.indices" in src
        assert "obole.engine" not in src  # pas de calcul direct


# --- Screener FR (jalon 09.2) ------------------------------------------------


def _sr_dump(ticker: str, **kw) -> dict:
    """ScreenResult -> dict, comme stocké dans le cache de scan."""
    defaults = dict(
        ticker=ticker,
        name="Fake Corp",
        sector="Technology",
        market_cap=2_000_000_000,
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


def _universe(tickers: list[str]) -> dict:
    return {"tickers": tickers, "count": len(tickers), "source": "yahoo"}


class TestScreenerParite:
    """L'outil MCP renvoie le MÊME payload que `POST /api/screener/run`."""

    @pytest.mark.anyio
    async def test_parite_payload_complet(self):
        from fastapi.testclient import TestClient

        scan = {"AIR.PA": _sr_dump("AIR.PA"), "AI.PA": _sr_dump("AI.PA")}
        client = TestClient(app)
        with (
            patch("obole.services.screener.cache_data.get", return_value=None),
            patch("obole.services.screener.cache_data.put"),
            patch(
                "obole.services.screener.screener_data.fetch_universe",
                return_value=_universe(["AIR.PA", "AI.PA"]),
            ),
            patch("obole.services.screener._scan_universe", return_value=scan),
        ):
            api_payload = client.post("/api/screener/run", json={"min_market_cap": 1e9}).json()
            tool_payload = await _call("screen_french_stocks", {"min_market_cap": 1e9})

        assert tool_payload == api_payload
        assert tool_payload["tickers_count"] == 2
        # La polarité couleur (source unique config) est bien transmise à l'IA.
        assert tool_payload["rows"][0]["colors"]["z"] is not None

    @pytest.mark.anyio
    async def test_parite_avec_filtres_et_tri(self):
        from fastapi.testclient import TestClient

        scan = {
            "AIR.PA": _sr_dump("AIR.PA", z=-2.0),
            "AI.PA": _sr_dump("AI.PA", z=1.0),
        }
        body = {"filters": {"z": [-1.0, None]}, "sort_by": ["z"]}
        client = TestClient(app)
        with (
            patch("obole.services.screener.cache_data.get", return_value=None),
            patch("obole.services.screener.cache_data.put"),
            patch(
                "obole.services.screener.screener_data.fetch_universe",
                return_value=_universe(["AIR.PA", "AI.PA"]),
            ),
            patch("obole.services.screener._scan_universe", return_value=scan),
        ):
            api_payload = client.post("/api/screener/run", json=body).json()
            tool_payload = await _call("screen_french_stocks", body)

        assert tool_payload == api_payload
        assert [r["ticker"] for r in tool_payload["rows"]] == ["AI.PA"]

    @pytest.mark.anyio
    async def test_max_rows_tronque_rows_mais_garde_totaux(self):
        """`max_rows` borne les lignes ; `count`/`tickers_count` restent les totaux."""
        scan = {
            "AIR.PA": _sr_dump("AIR.PA"),
            "AI.PA": _sr_dump("AI.PA"),
            "MC.PA": _sr_dump("MC.PA"),
        }
        with (
            patch("obole.services.screener.cache_data.get", return_value=None),
            patch("obole.services.screener.cache_data.put"),
            patch(
                "obole.services.screener.screener_data.fetch_universe",
                return_value=_universe(["AIR.PA", "AI.PA", "MC.PA"]),
            ),
            patch("obole.services.screener._scan_universe", return_value=scan),
        ):
            payload = await _call("screen_french_stocks", {"min_market_cap": 1e9, "max_rows": 2})

        assert len(payload["rows"]) == 2
        assert payload["count"] == 3  # total réel, non tronqué
        assert payload["tickers_count"] == 3

    @pytest.mark.anyio
    async def test_max_rows_invalide_erreur(self):
        msg = await _call_error("screen_french_stocks", {"max_rows": 0})
        assert "max_rows" in msg

    @pytest.mark.anyio
    async def test_max_rows_absent_pas_de_troncature(self):
        """Sans `max_rows`, toutes les lignes sont renvoyées (comportement API)."""
        scan = {"AIR.PA": _sr_dump("AIR.PA"), "AI.PA": _sr_dump("AI.PA")}
        with (
            patch("obole.services.screener.cache_data.get", return_value=None),
            patch("obole.services.screener.cache_data.put"),
            patch(
                "obole.services.screener.screener_data.fetch_universe",
                return_value=_universe(["AIR.PA", "AI.PA"]),
            ),
            patch("obole.services.screener._scan_universe", return_value=scan),
        ):
            payload = await _call("screen_french_stocks", {"min_market_cap": 1e9})

        assert len(payload["rows"]) == 2


class TestScreenerCache:
    """Cache agressif : un second appel identique ne re-scanne pas (PRD §12.2)."""

    @pytest.mark.anyio
    async def test_cache_chaud_ne_rescanne_pas(self):
        cached = {"results": {"AIR.PA": _sr_dump("AIR.PA")}, "source": "yahoo"}
        with (
            patch("obole.services.screener.cache_data.get", return_value=cached),
            patch("obole.services.screener.screener_data.fetch_universe") as mock_u,
            patch("obole.services.screener._scan_universe") as mock_scan,
        ):
            payload = await _call("screen_french_stocks", {})

        assert payload["source"] == "cache"
        mock_u.assert_not_called()
        mock_scan.assert_not_called()

    @pytest.mark.anyio
    async def test_deuxieme_appel_identique_sert_le_cache(self):
        """Deux appels successifs identiques : un seul scan réseau au total."""
        scan = {"AIR.PA": _sr_dump("AIR.PA")}
        cached = {"results": scan, "source": "yahoo"}
        # 1er appel : cache froid (None) -> scan ; 2e appel : cache chaud -> servi.
        with (
            patch(
                "obole.services.screener.cache_data.get",
                side_effect=[None, cached],
            ),
            patch("obole.services.screener.cache_data.put"),
            patch(
                "obole.services.screener.screener_data.fetch_universe",
                return_value=_universe(["AIR.PA"]),
            ),
            patch(
                "obole.services.screener._scan_universe",
                return_value=scan,
            ) as mock_scan,
        ):
            first = await _call("screen_french_stocks", {})
            second = await _call("screen_french_stocks", {})

        assert first["source"] == "yahoo"
        assert second["source"] == "cache"
        mock_scan.assert_called_once()  # un seul scan réseau pour deux appels


class TestScreenerInvariants:
    @pytest.mark.anyio
    async def test_filtre_inconnu_erreur(self):
        msg = await _call_error("screen_french_stocks", {"filters": {"bogus": (0, 10)}})
        assert "Critère inconnu" in msg

    @pytest.mark.anyio
    async def test_score_non_filtrable_erreur(self):
        msg = await _call_error("screen_french_stocks", {"filters": {"score": (0, 100)}})
        assert "Critère inconnu" in msg

    @pytest.mark.anyio
    async def test_bornes_inversees_erreur(self):
        msg = await _call_error("screen_french_stocks", {"filters": {"z": (5.0, 1.0)}})
        assert "inversées" in msg

    @pytest.mark.anyio
    async def test_tri_inconnu_erreur(self):
        msg = await _call_error("screen_french_stocks", {"sort_by": ["bogus"]})
        assert "Critère inconnu" in msg

    @pytest.mark.anyio
    async def test_sens_tri_invalide_erreur(self):
        msg = await _call_error("screen_french_stocks", {"sort_by": [["z", "up"]]})
        assert "Sens invalide" in msg

    @pytest.mark.anyio
    async def test_score_keys_inconnu_ignore_pas_de_crash(self):
        """Un critère de score inconnu est ignoré (pas d'erreur) : le scan aboutit."""
        scan = {"AIR.PA": _sr_dump("AIR.PA")}
        with (
            patch("obole.services.screener.cache_data.get", return_value=None),
            patch("obole.services.screener.cache_data.put"),
            patch(
                "obole.services.screener.screener_data.fetch_universe",
                return_value=_universe(["AIR.PA"]),
            ),
            patch("obole.services.screener._scan_universe", return_value=scan),
        ):
            payload = await _call("screen_french_stocks", {"score_keys": ["bogus"]})
        assert payload["count"] == 1

    @pytest.mark.anyio
    async def test_defaut_capi_config_applique(self):
        """Sans `min_market_cap`, l'outil passe le défaut `config` (jamais de littéral)."""
        from obole import config

        with (
            patch("obole.services.screener.cache_data.get", return_value=None),
            patch("obole.services.screener.cache_data.put"),
            patch("obole.services.screener._scan_universe", return_value={}),
            patch(
                "obole.services.screener.screener_data.fetch_universe",
                return_value=_universe([]),
            ) as mock_u,
        ):
            await _call("screen_french_stocks", {})

        assert mock_u.call_args.kwargs["min_market_cap"] == config.SCREEN_DEFAULT_MIN_CAP

    @pytest.mark.anyio
    async def test_capi_negative_erreur(self):
        """`min_market_cap` négative -> ToolError (borne métier, parité API)."""
        msg = await _call_error("screen_french_stocks", {"min_market_cap": -1})
        assert "Capi invalide" in msg

    @pytest.mark.anyio
    async def test_capi_non_numerique_rejete_en_amont(self):
        """Une capi non numérique est rejetée par le schéma du SDK (Pydantic)."""
        msg = await _call_error("screen_french_stocks", {"min_market_cap": "1 mois"})
        assert "min_market_cap" in msg or "validation error" in msg

    @pytest.mark.anyio
    async def test_regression_window_negative_erreur(self):
        """`regression_window` <= 0 -> ToolError (borne métier, parité API)."""
        msg = await _call_error("screen_french_stocks", {"regression_window": -5})
        assert "Fenêtre invalide" in msg

    @pytest.mark.anyio
    async def test_null_capi_scan_univers_complet(self):
        """`min_market_cap: null` -> univers complet (None transmis au service)."""
        with (
            patch("obole.services.screener.cache_data.get", return_value=None),
            patch("obole.services.screener.cache_data.put"),
            patch("obole.services.screener._scan_universe", return_value={}),
            patch(
                "obole.services.screener.screener_data.fetch_universe",
                return_value=_universe([]),
            ) as mock_u,
        ):
            await _call("screen_french_stocks", {"min_market_cap": None})

        assert mock_u.call_args.kwargs["min_market_cap"] is None

    def test_docstring_enumere_les_criteres_depuis_la_source(self):
        """La docstring (doc de l'IA) liste les critères depuis la SOURCE UNIQUE."""
        from obole.mcp.tools import screener as screener_tool
        from obole.services import screener as screener_service

        doc = screener_tool.screen_french_stocks.__doc__
        for key in screener_service.FILTERABLE_KEYS:
            assert f"`{key}`" in doc
        for key in screener_service.SORTABLE_KEYS:
            assert f"`{key}`" in doc
        # Aucun jeton de gabarit non résolu.
        assert "<<" not in doc


# --- Thèses d'entreprise (jalon 09.3) ----------------------------------------


@pytest.mark.usefixtures("isolated_db")
class TestThesisViaOutil:
    """`write_thesis` + CRUD, via le transport in-memory du SDK."""

    @pytest.mark.anyio
    async def test_write_thesis_prompt_et_donnees(self):
        from tests.test_analysis import _fake_identity, _make_prices

        with (
            patch("obole.services.analysis.yahoo.fetch_identity", side_effect=_fake_identity),
            patch("obole.services.analysis.yahoo.fetch_fundamentals", return_value=None),
            patch("obole.services.analysis.yahoo.fetch_prices", return_value=_make_prices()),
        ):
            out = await _call("write_thesis", {"ticker": "fake"})

        assert set(out) == {"prompt", "data", "warnings"}
        assert "Fake Corp" in out["prompt"]
        assert "chart" not in out["data"]
        assert "indicators" in out["data"]

    @pytest.mark.anyio
    async def test_cycle_crud_complet(self):
        md = "## Pitch\n\nDécotée de 3,8 σ."
        saved = await _call("save_thesis", {"ticker": "ri.pa", "content": md})
        assert saved["status"] == "ok"
        assert saved["ticker"] == "RI.PA"

        listed = await _call("list_theses", {})
        assert any(t["ticker"] == "RI.PA" for t in listed)

        got = await _call("get_thesis", {"ticker": "RI.PA"})
        assert got["content"] == md

        deleted = await _call("delete_thesis", {"ticker": "RI.PA"})
        assert deleted["status"] == "deleted"

    @pytest.mark.anyio
    async def test_get_absent_erreur(self):
        msg = await _call_error("get_thesis", {"ticker": "RI.PA"})
        assert "Aucune thèse" in msg

    @pytest.mark.anyio
    async def test_delete_absent_erreur(self):
        msg = await _call_error("delete_thesis", {"ticker": "RI.PA"})
        assert "Aucune thèse" in msg

    @pytest.mark.anyio
    async def test_contenu_vide_erreur(self):
        msg = await _call_error("save_thesis", {"ticker": "RI.PA", "content": "   "})
        assert "vide" in msg

    @pytest.mark.anyio
    async def test_ticker_inconnu_erreur(self):
        from obole.data.yahoo import TickerNotFound

        with patch(
            "obole.services.analysis.yahoo.fetch_prices",
            side_effect=TickerNotFound("nope"),
        ):
            msg = await _call_error("write_thesis", {"ticker": "ZZZ.PA"})
        assert "introuvable" in msg

    def test_les_outils_delegent_aux_services(self):
        """Aucune formule dans l'outil de thèse : il importe `services`."""
        import inspect

        from obole.mcp.tools import thesis as thesis_tool

        src = inspect.getsource(thesis_tool)
        assert "obole.services" in src
        assert "obole.engine" not in src
        assert "obole.api" not in src

    def test_write_thesis_passe_par_la_projection_commune(self):
        """`services/thesis` écarte le graphe via `include_chart`, pas un `pop` local."""
        import inspect

        from obole.services import thesis as thesis_service

        src = inspect.getsource(thesis_service.write_thesis)
        assert "include_chart=False" in src
        assert 'pop("chart"' not in src
        assert "pop('chart'" not in src

    def test_pas_de_jeton_de_gabarit(self):
        from obole.mcp.tools import thesis as thesis_tool

        doc = thesis_tool.write_thesis.__doc__ or ""
        assert "<<" not in doc


# --- Portefeuille (MCP-B, fiche #17) -----------------------------------------


@pytest.mark.usefixtures("isolated_db")
class TestPortefeuilleViaOutil:
    """Comptes, transactions, dividendes, positions : via le transport in-memory.

    La parité outil ↔ API est vérifiée sur les lectures qui passent par
    `services/serialize` (positions, résumé) ; les écritures renvoient le même
    `{"status", "id"}` que la route.
    """

    @pytest.mark.anyio
    async def test_cycle_comptes(self):
        created = await _call("create_account", {"name": "PEA"})
        assert created["status"] == "ok"
        acc = created["id"]

        rows = await _call("list_accounts", {})
        assert any(a["id"] == acc and a["currency"] == "EUR" for a in rows)

        deleted = await _call("delete_account", {"account_id": acc})
        assert deleted == {"status": "deleted", "id": acc}

    @pytest.mark.anyio
    async def test_nom_de_compte_vide_erreur(self):
        msg = await _call_error("create_account", {"name": "   "})
        assert "vide" in msg

    @pytest.mark.anyio
    async def test_devise_non_supportee_erreur(self):
        msg = await _call_error("create_account", {"name": "PEA", "currency": "USD"})
        assert "Devise non supportée" in msg

    @pytest.mark.anyio
    async def test_compte_inconnu_sur_transaction_erreur(self):
        msg = await _call_error(
            "add_transaction",
            {
                "account_id": 999999,
                "ticker": "RI.PA",
                "side": "buy",
                "trade_date": "2024-01-02",
                "quantity": 10,
                "price": 100.0,
            },
        )
        assert "Compte inconnu" in msg

    @pytest.mark.anyio
    async def test_cycle_transactions(self):
        acc = (await _call("create_account", {"name": "PEA"}))["id"]
        body = {
            "account_id": acc,
            "ticker": "ri.pa",
            "side": "buy",
            "trade_date": "2024-01-02",
            "quantity": 10,
            "price": 100.0,
            "fees": 1.5,
        }
        tx = await _call("add_transaction", body)
        assert tx["status"] == "ok"
        tx_id = tx["id"]

        rows = await _call("list_transactions", {"account_id": acc})
        assert len(rows) == 1
        assert rows[0]["ticker"] == "RI.PA"
        assert rows[0]["fees"] == 1.5

        updated = await _call("update_transaction", {**body, "tx_id": tx_id, "quantity": 20})
        assert updated == {"status": "ok", "id": tx_id}
        rows = await _call("list_transactions", {"account_id": acc})
        assert rows[0]["quantity"] == 20

        deleted = await _call("delete_transaction", {"tx_id": tx_id})
        assert deleted == {"status": "deleted", "id": tx_id}
        assert await _call("list_transactions", {}) == []

    @pytest.mark.anyio
    async def test_sens_invalide_erreur(self):
        acc = (await _call("create_account", {"name": "PEA"}))["id"]
        msg = await _call_error(
            "add_transaction",
            {
                "account_id": acc,
                "ticker": "RI.PA",
                "side": "hold",
                "trade_date": "2024-01-02",
                "quantity": 10,
                "price": 100.0,
            },
        )
        assert "Sens invalide" in msg

    @pytest.mark.anyio
    async def test_date_invalide_erreur(self):
        acc = (await _call("create_account", {"name": "PEA"}))["id"]
        msg = await _call_error(
            "add_transaction",
            {
                "account_id": acc,
                "ticker": "RI.PA",
                "side": "buy",
                "trade_date": "02/01/2024",
                "quantity": 10,
                "price": 100.0,
            },
        )
        assert "Date invalide" in msg

    @pytest.mark.anyio
    async def test_quantite_non_positive_erreur(self):
        acc = (await _call("create_account", {"name": "PEA"}))["id"]
        msg = await _call_error(
            "add_transaction",
            {
                "account_id": acc,
                "ticker": "RI.PA",
                "side": "buy",
                "trade_date": "2024-01-02",
                "quantity": 0,
                "price": 100.0,
            },
        )
        assert "strictement positive" in msg

    @pytest.mark.anyio
    async def test_transaction_inconnue_erreur(self):
        msg = await _call_error("delete_transaction", {"tx_id": 999999})
        assert "Transaction inconnue" in msg

    @pytest.mark.anyio
    async def test_cycle_dividendes(self):
        acc = (await _call("create_account", {"name": "PEA"}))["id"]
        body = {
            "account_id": acc,
            "ticker": "ri.pa",
            "pay_date": "2024-07-05",
            "amount": 42.5,
        }
        div = await _call("add_dividend", body)
        assert div["status"] == "ok"
        div_id = div["id"]

        rows = await _call("list_dividends", {"account_id": acc})
        assert len(rows) == 1
        assert rows[0]["ticker"] == "RI.PA"
        assert rows[0]["status"] == "confirmed"
        assert rows[0]["source"] == "manual"

        updated = await _call(
            "update_dividend", {**body, "div_id": div_id, "amount": 50.0, "status": "proposed"}
        )
        assert updated == {"status": "ok", "id": div_id}
        rows = await _call("list_dividends", {"account_id": acc})
        assert rows[0]["amount"] == 50.0
        assert rows[0]["status"] == "proposed"

        deleted = await _call("delete_dividend", {"div_id": div_id})
        assert deleted == {"status": "deleted", "id": div_id}
        assert await _call("list_dividends", {}) == []

    @pytest.mark.anyio
    async def test_statut_dividende_invalide_erreur(self):
        acc = (await _call("create_account", {"name": "PEA"}))["id"]
        msg = await _call_error(
            "add_dividend",
            {
                "account_id": acc,
                "ticker": "RI.PA",
                "pay_date": "2024-07-05",
                "amount": 10.0,
                "status": "peut-etre",
            },
        )
        assert "Statut invalide" in msg

    @pytest.mark.anyio
    async def test_montant_negatif_erreur(self):
        acc = (await _call("create_account", {"name": "PEA"}))["id"]
        msg = await _call_error(
            "add_dividend",
            {
                "account_id": acc,
                "ticker": "RI.PA",
                "pay_date": "2024-07-05",
                "amount": -1.0,
            },
        )
        assert "négatif" in msg

    @pytest.mark.anyio
    async def test_dividende_inconnu_erreur(self):
        msg = await _call_error("delete_dividend", {"div_id": 999999})
        assert "Dividende inconnu" in msg

    @pytest.mark.anyio
    async def test_positions_parite_avec_l_api(self):
        from fastapi.testclient import TestClient

        acc = (await _call("create_account", {"name": "PEA"}))["id"]
        for qty, price in ((10, 100.0), (5, 120.0)):
            await _call(
                "add_transaction",
                {
                    "account_id": acc,
                    "ticker": "RI.PA",
                    "side": "buy",
                    "trade_date": "2024-01-02",
                    "quantity": qty,
                    "price": price,
                },
            )

        client = TestClient(app)
        api_payload = client.get("/api/portfolio/positions").json()
        tool_payload = await _call("list_positions", {})

        assert tool_payload == api_payload
        assert len(tool_payload) == 1
        row = tool_payload[0]
        assert row["ticker"] == "RI.PA"
        assert row["quantity"] == 15
        assert row["cost_basis"] == 1600.0
        assert row["realized"] == 0.0

    @pytest.mark.anyio
    async def test_positions_vides_sans_transaction(self):
        """Portefeuille vide -> liste vide, jamais une erreur."""
        assert await _call("list_positions", {}) == []

    @pytest.mark.anyio
    async def test_resume_parite_avec_l_api(self):
        import datetime as dt

        import numpy as np
        import pandas as pd
        from fastapi.testclient import TestClient

        from obole.models import PriceSeries

        idx = pd.bdate_range("2023-01-02", periods=520)

        def _series(base: float, drift: float) -> PriceSeries:
            raw = pd.Series(base * np.exp(np.arange(len(idx)) * drift), index=idx)
            return PriceSeries(raw=raw, adjusted=raw, fetched_at=idx[-1].date())

        universe = {
            "RI.PA": _series(100.0, 0.0010),
            "CW8.PA": _series(400.0, 0.0005),
        }

        def _fetch(ticker: str) -> PriceSeries:
            if ticker not in universe:
                raise TickerNotFound(ticker)
            return universe[ticker]

        acc = (await _call("create_account", {"name": "PEA"}))["id"]
        await _call(
            "add_transaction",
            {
                "account_id": acc,
                "ticker": "RI.PA",
                "side": "buy",
                "trade_date": idx[0].date().isoformat(),
                "quantity": 10,
                "price": 100.0,
            },
        )

        client = TestClient(app)
        with patch("obole.services.portfolio.yahoo.fetch_prices", side_effect=_fetch):
            api_payload = client.get("/api/portfolio/summary").json()
            tool_payload = await _call("get_portfolio_summary", {})

        assert tool_payload == api_payload
        assert tool_payload["kpis"]["total_value"] > 0
        assert isinstance(tool_payload["dates"][0], str)
        assert tool_payload["dates"][0] == idx[0].date().isoformat()
        assert dt.date.fromisoformat(tool_payload["period_start"])

    @pytest.mark.anyio
    async def test_resume_periode_inconnue_erreur(self):
        msg = await _call_error("get_portfolio_summary", {"period": "10a"})
        assert "Période inconnue" in msg

    @pytest.mark.anyio
    async def test_transaction_tag_roundtrip(self):
        acc = (await _call("create_account", {"name": "PEA"}))["id"]
        await _call(
            "add_transaction",
            {
                "account_id": acc,
                "ticker": "RI.PA",
                "side": "buy",
                "trade_date": "2024-01-02",
                "quantity": 10,
                "price": 100.0,
                "tag": "Actions dividende",
            },
        )
        rows = await _call("list_transactions", {"tag": "Actions dividende"})
        assert len(rows) == 1
        assert rows[0]["tag"] == "Actions dividende"
        assert await _call("list_portfolio_tags", {}) == ["Actions dividende"]

    @pytest.mark.anyio
    async def test_tag_trop_long_erreur(self):
        from obole import config

        acc = (await _call("create_account", {"name": "PEA"}))["id"]
        msg = await _call_error(
            "add_transaction",
            {
                "account_id": acc,
                "ticker": "RI.PA",
                "side": "buy",
                "trade_date": "2024-01-02",
                "quantity": 10,
                "price": 100.0,
                "tag": "x" * (config.PORTFOLIO_TAG_MAX + 1),
            },
        )
        assert "trop longue" in msg

    @pytest.mark.anyio
    async def test_risk_parite_avec_l_api(self):
        import numpy as np
        import pandas as pd
        from fastapi.testclient import TestClient

        from obole.models import PriceSeries

        idx = pd.bdate_range("2022-01-03", periods=520)

        def _series(base: float, drift: float, seed: int) -> PriceSeries:
            rng = np.random.default_rng(seed)
            raw = pd.Series(
                base
                * np.exp(np.arange(len(idx)) * drift + np.cumsum(rng.normal(0, 0.005, len(idx)))),
                index=idx,
            )
            return PriceSeries(raw=raw, adjusted=raw, fetched_at=idx[-1].date())

        universe = {
            "RI.PA": _series(100.0, 0.0006, 1),
            "AI.PA": _series(150.0, 0.0004, 2),
            "CW8.PA": _series(400.0, 0.0005, 3),
        }

        def _fetch(ticker: str) -> PriceSeries:
            if ticker not in universe:
                raise TickerNotFound(ticker)
            return universe[ticker]

        acc = (await _call("create_account", {"name": "PEA"}))["id"]
        for ticker, price in (("RI.PA", 100.0), ("AI.PA", 150.0)):
            await _call(
                "add_transaction",
                {
                    "account_id": acc,
                    "ticker": ticker,
                    "side": "buy",
                    "trade_date": idx[0].date().isoformat(),
                    "quantity": 10,
                    "price": price,
                },
            )

        client = TestClient(app)
        with patch("obole.services.portfolio.yahoo.fetch_prices", side_effect=_fetch):
            api_payload = client.get("/api/portfolio/risk?period=max").json()
            tool_payload = await _call("get_portfolio_risk", {"period": "max"})

        assert tool_payload == api_payload
        assert set(tool_payload["correlation"]["tickers"]) == {"RI.PA", "AI.PA"}
        assert all(v is None or v <= 0 for v in tool_payload["drawdown"])

    @pytest.mark.anyio
    async def test_correlation_test_parite_avec_l_api(self):
        import numpy as np
        import pandas as pd
        from fastapi.testclient import TestClient

        from obole.models import PriceSeries

        idx = pd.bdate_range("2022-01-03", periods=520)

        def _series(base: float, drift: float, seed: int) -> PriceSeries:
            rng = np.random.default_rng(seed)
            raw = pd.Series(
                base
                * np.exp(np.arange(len(idx)) * drift + np.cumsum(rng.normal(0, 0.005, len(idx)))),
                index=idx,
            )
            return PriceSeries(raw=raw, adjusted=raw, fetched_at=idx[-1].date())

        universe = {
            "RI.PA": _series(100.0, 0.0006, 1),
            "AI.PA": _series(150.0, 0.0004, 2),
            "CW8.PA": _series(400.0, 0.0005, 3),
            "MC.PA": _series(700.0, 0.0003, 5),
        }

        def _fetch(ticker: str) -> PriceSeries:
            if ticker not in universe:
                raise TickerNotFound(ticker)
            return universe[ticker]

        acc = (await _call("create_account", {"name": "PEA"}))["id"]
        for ticker, price in (("RI.PA", 100.0), ("AI.PA", 150.0)):
            await _call(
                "add_transaction",
                {
                    "account_id": acc,
                    "ticker": ticker,
                    "side": "buy",
                    "trade_date": idx[0].date().isoformat(),
                    "quantity": 10,
                    "price": price,
                },
            )

        client = TestClient(app)
        with patch("obole.services.portfolio.yahoo.fetch_prices", side_effect=_fetch):
            api_payload = client.get(
                "/api/portfolio/risk/correlation-test?period=max&benchmark=CW8.PA&ticker=MC.PA"
            ).json()
            tool_payload = await _call(
                "test_portfolio_correlation",
                {"period": "max", "benchmark": "CW8.PA", "ticker": "MC.PA"},
            )

        assert tool_payload == api_payload
        assert tool_payload["ticker"] == "MC.PA"
        assert len(tool_payload["row"]) == len(tool_payload["tickers"]) == 2
        assert tool_payload["delta"] == pytest.approx(
            round(tool_payload["new_avg"] - tool_payload["current_avg"], 4)
        )

    @pytest.mark.anyio
    async def test_correlation_test_ticker_vide_erreur(self):
        acc = (await _call("create_account", {"name": "PEA"}))["id"]
        await _call(
            "add_transaction",
            {
                "account_id": acc,
                "ticker": "RI.PA",
                "side": "buy",
                "trade_date": "2022-01-03",
                "quantity": 10,
                "price": 100.0,
            },
        )
        msg = await _call_error("test_portfolio_correlation", {"ticker": "  "})
        assert "vide" in msg.lower()

    @pytest.mark.anyio
    async def test_les_outils_portefeuille_delegent_aux_services(self):
        """Aucune formule ni seuil dans l'outil : il importe `services`."""
        import inspect

        from obole.mcp.tools import portfolio as portfolio_tool

        src = inspect.getsource(portfolio_tool)
        assert "obole.services" in src
        assert "obole.engine" not in src
        assert "obole.api" not in src

    def test_docstring_resume_derive_de_config(self):
        """Périodes et benchmarks du résumé viennent de la SOURCE UNIQUE."""
        from obole import config
        from obole.mcp.tools import portfolio as portfolio_tool

        doc = portfolio_tool.get_portfolio_summary.__doc__ or ""
        for period in config.PORTFOLIO_PERIODS:
            assert f"`{period}`" in doc
        for bench in config.PORTFOLIO_BENCHMARKS:
            assert f"`{bench['ticker']}`" in doc
        assert "<<" not in doc


# --- Points de contrôle suivis (#21, bande « Suivi ») ------------------------


@pytest.mark.usefixtures("isolated_db")
class TestSuiviViaOutil:
    """CRUD des points de contrôle via le transport in-memory du SDK."""

    @pytest.mark.anyio
    async def test_cycle_complet_parite_avec_l_api(self):
        from fastapi.testclient import TestClient

        added = await _call("add_checkpoint", {"ticker": "ri.pa", "label": "Marge > 28 %"})
        assert added["status"] == "ok"
        assert added["ticker"] == "RI.PA"
        cid = added["id"]

        client = TestClient(app)
        api_payload = client.get("/api/checkpoints/RI.PA").json()
        tool_payload = await _call("list_checkpoints", {"ticker": "RI.PA"})
        assert tool_payload == api_payload
        assert tool_payload[0]["done"] is False

        updated = await _call(
            "update_checkpoint",
            {"checkpoint_id": cid, "label": "Marge > 30 %", "done": True},
        )
        assert updated == {"status": "ok", "id": cid}
        rows = await _call("list_checkpoints", {"ticker": "RI.PA"})
        assert rows[0]["label"] == "Marge > 30 %"
        assert rows[0]["done"] is True

        deleted = await _call("delete_checkpoint", {"checkpoint_id": cid})
        assert deleted == {"status": "deleted", "id": cid}
        assert await _call("list_checkpoints", {"ticker": "RI.PA"}) == []

    @pytest.mark.anyio
    async def test_liste_vide_sans_point(self):
        assert await _call("list_checkpoints", {"ticker": "RI.PA"}) == []

    @pytest.mark.anyio
    async def test_ticker_vide_erreur(self):
        msg = await _call_error("list_checkpoints", {"ticker": "   "})
        assert "Ticker requis" in msg

    @pytest.mark.anyio
    async def test_libelle_vide_erreur(self):
        msg = await _call_error("add_checkpoint", {"ticker": "RI.PA", "label": "   "})
        assert "vide" in msg

    @pytest.mark.anyio
    async def test_libelle_trop_long_erreur(self):
        from obole import config

        msg = await _call_error(
            "add_checkpoint", {"ticker": "RI.PA", "label": "x" * (config.CHECKPOINT_LABEL_MAX + 1)}
        )
        assert "trop long" in msg

    @pytest.mark.anyio
    async def test_point_inconnu_erreur(self):
        msg = await _call_error(
            "update_checkpoint", {"checkpoint_id": 999999, "label": "A", "done": True}
        )
        assert "inconnu" in msg

    @pytest.mark.anyio
    async def test_suppression_inconnue_erreur(self):
        msg = await _call_error("delete_checkpoint", {"checkpoint_id": 999999})
        assert "inconnu" in msg

    @pytest.mark.anyio
    async def test_plafond_par_ticker_erreur(self):
        from obole import config

        for i in range(config.CHECKPOINT_MAX_PER_REF):
            await _call("add_checkpoint", {"ticker": "RI.PA", "label": f"Point {i}"})
        msg = await _call_error("add_checkpoint", {"ticker": "RI.PA", "label": "Trop"})
        assert "Trop de points" in msg

    @pytest.mark.anyio
    async def test_les_outils_suivi_delegent_aux_services(self):
        import inspect

        from obole.mcp.tools import checkpoints as checkpoints_tool

        src = inspect.getsource(checkpoints_tool)
        assert "obole.services" in src
        assert "obole.engine" not in src
        assert "obole.api" not in src


@pytest.mark.usefixtures("isolated_db")
class TestImportViaOutil:
    """Parité MCP ↔ service pour le staging d'import (#23).

    L'outil `propose_import` ne fait que déléguer à `services/imports` : il ne
    peut ni appliquer un brouillon (garde-fou) ni écrire une donnée métier.
    """

    @pytest.mark.anyio
    async def test_propose_renvoie_le_rapport_du_service(self):
        csv_text = "year;Chiffre d'affaires\n2015;8 500 000"
        payload = await _call(
            "propose_import",
            {"target": "fundamentals", "ref": "RI.PA", "csv_text": csv_text},
        )
        assert payload["status"] == "pending"
        assert payload["accepted"] == 1
        assert payload["delimiter"] == ";"
        assert payload["ref"] == "RI.PA"
        assert payload["draft_id"] >= 1

    @pytest.mark.anyio
    async def test_l_outil_n_ecrit_rien_en_production(self):
        from obole.data import manual

        await _call(
            "propose_import",
            {
                "target": "fundamentals",
                "ref": "RI.PA",
                "csv_text": "year,Chiffre d'affaires\n2015,10",
            },
        )
        assert manual.get_manual("RI.PA") == []

    @pytest.mark.anyio
    async def test_cible_inconnue_erreur(self):
        msg = await _call_error(
            "propose_import",
            {"target": "portfolio", "ref": "RI.PA", "csv_text": "year,CA\n2015,10"},
        )
        assert "Cible d'import inconnue" in msg

    @pytest.mark.anyio
    async def test_csv_vide_erreur(self):
        msg = await _call_error(
            "propose_import", {"target": "fundamentals", "ref": "RI.PA", "csv_text": "  "}
        )
        assert "vide" in msg

    @pytest.mark.anyio
    async def test_seul_l_outil_de_proposition_est_expose(self):
        async with Client(mcp_server.mcp) as client:
            tools = await client.list_tools()
        names = [t.name for t in tools.tools]
        assert "propose_import" in names
        assert not [n for n in names if "apply" in n]


# --- Watchlist (#25) ---------------------------------------------------------


class TestWatchlistTools:
    """Parité des outils watchlist avec les routes, et frontière de l'écriture."""

    @pytest.mark.anyio
    @pytest.mark.usefixtures("isolated_db")
    async def test_get_watchlist_parite(self):
        from fastapi.testclient import TestClient

        from obole.data import cache

        cache.upsert_watch_item("RI.PA", 2)
        cache.set_ticker_ref("RI.PA", "2012-01-04")
        tool = await _call("get_watchlist", {})
        api = TestClient(app).get("/api/watchlist").json()
        assert tool == api
        assert tool["refs"] == {"RI.PA": "2012-01-04"}

    @pytest.mark.anyio
    @pytest.mark.usefixtures("isolated_db")
    async def test_rank_watchlist_parite_full(self):
        from fastapi.testclient import TestClient

        from obole.models import WatchlistRow, WatchlistRun

        run = WatchlistRun(
            generated_at=1.0,
            rows=[
                WatchlistRow(
                    ticker="RI.PA",
                    tier=1,
                    name="Pernod",
                    price=100.0,
                    fair_price=120.0,
                    fair_price_source="saved",
                    target_yield=12.0,
                    safety_margin_pct=16.67,
                    margin_good=True,
                    ref_start="2005-01-03",
                    ref_is_default=False,
                    ref_line=110.0,
                    trend_gap_pct=9.09,
                    z=-1.2,
                    ecart_type_pct=25.0,
                    warnings=["Comptes indisponibles"],
                ),
                WatchlistRow(ticker="AI.PA", tier=2, error="Ticker introuvable"),
            ],
        )
        client = TestClient(app)
        with patch("obole.services.watchlist.run", return_value=run):
            api_payload = client.post("/api/watchlist/run", json={}).json()
            tool_payload = await _call("rank_watchlist", {"view": "full"})
        assert tool_payload == api_payload
        assert tool_payload["rows"][0]["fair_price_source"] == "saved"

    @pytest.mark.anyio
    @pytest.mark.usefixtures("isolated_db")
    async def test_rank_watchlist_summary_is_compact(self):
        from obole.models import WatchlistRow, WatchlistRun

        run = WatchlistRun(
            generated_at=1.0,
            rows=[WatchlistRow(ticker="RI.PA", tier=1, sector="Drinks", warnings=["w"])],
        )
        with patch("obole.services.watchlist.run", return_value=run):
            payload = await _call("rank_watchlist", {})
        row = payload["rows"][0]
        assert payload["count"] == 1
        # Le résumé garde la décision, écarte le bruit de contexte.
        assert "safety_margin_pct" in row
        assert "pot_5y_pct" in row
        assert "pot_5y_source" in row
        assert "sector" not in row
        assert "warnings" not in row

    @pytest.mark.anyio
    @pytest.mark.usefixtures("isolated_db")
    async def test_rank_watchlist_max_rows_and_tier(self):
        from obole.models import WatchlistRow, WatchlistRun

        run = WatchlistRun(
            generated_at=1.0,
            rows=[
                WatchlistRow(ticker="RI.PA", tier=1),
                WatchlistRow(ticker="AI.PA", tier=1),
            ],
        )
        with patch("obole.services.watchlist.run", return_value=run) as service_run:
            payload = await _call("rank_watchlist", {"tier": 1, "max_rows": 1})
        service_run.assert_called_once_with(tier=1)
        assert payload["count"] == 2
        assert len(payload["rows"]) == 1

    @pytest.mark.anyio
    async def test_rank_watchlist_erreurs(self):
        msg = await _call_error("rank_watchlist", {"tier": 9})
        assert "Tier" in msg
        msg = await _call_error("rank_watchlist", {"max_rows": 0})
        assert "max_rows" in msg
        msg = await _call_error("rank_watchlist", {"view": "Full"})
        assert "view" in msg

    @pytest.mark.anyio
    @pytest.mark.usefixtures("isolated_db")
    async def test_add_and_remove_write_the_membership(self):
        from obole.data import cache

        added = await _call("add_to_watchlist", {"ticker": "ri.pa", "tier": 2})
        assert added["status"] == "ok"
        assert added["item"]["tier"] == 2
        assert cache.get_watch_item("RI.PA")["tier"] == 2

        removed = await _call("remove_from_watchlist", {"ticker": "RI.PA"})
        assert removed == {"status": "removed", "ticker": "RI.PA"}
        assert cache.get_watch_item("RI.PA") is None
        # Idempotent : retirer une valeur absente ne lève pas.
        assert await _call("remove_from_watchlist", {"ticker": "RI.PA"}) == {
            "status": "absent",
            "ticker": "RI.PA",
        }

    @pytest.mark.anyio
    async def test_add_rejects_invalid_tier(self):
        msg = await _call_error("add_to_watchlist", {"ticker": "RI.PA", "tier": 4})
        assert "Tier" in msg
