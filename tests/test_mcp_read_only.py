"""Mode lecture seule du serveur MCP et garde-fous d'écriture — sans réseau.

Le MCP est la surface qui permet à une IA d'**écrire** dans les données locales.
Deux garde-fous structurels :

1. `OBOLE_MCP_READ_ONLY=1` n'enregistre **pas** les outils d'écriture : ils sont
   absents de la liste, pas en erreur à l'appel (une IA ne peut pas inventer un
   outil qu'elle ne voit pas).
2. En mode nominal, chaque outil d'écriture déclenche une copie de sécurité de la
   base **avant** de s'exécuter.

Le dernier test vérifie que `WRITE_TOOLS` ne dérive pas de la réalité : tout outil
dont le nom commence par un verbe d'écriture doit y figurer.
"""

from __future__ import annotations

import importlib

import pytest
from mcp import Client
from mcp.server import MCPServer

from obole.mcp import tools as tools_pkg

WRITING_PREFIXES = (
    "add_",
    "create_",
    "update_",
    "delete_",
    "save_",
    "propose_",
    "apply_",
    "remove_",
)

TOOL_MODULES = (
    "stock",
    "ratio",
    "search",
    "indices",
    "screener",
    "thesis",
    "portfolio",
    "checkpoints",
    "imports",
    "watchlist",
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("OBOLE_MCP_READ_ONLY", raising=False)
    yield


def _fresh_server() -> MCPServer:
    server = MCPServer("obole-test", version="0.0.0")
    tools_pkg.register(server)
    return server


async def _tool_names() -> set[str]:
    async with Client(_fresh_server()) as client:
        return {t.name for t in (await client.list_tools()).tools}


def _verb_names() -> set[str]:
    """Noms des fonctions-verbes définies par les modules d'outils."""
    names: set[str] = set()
    for module_name in TOOL_MODULES:
        module = importlib.import_module(f"obole.mcp.tools.{module_name}")
        for attr in vars(module).values():
            if callable(attr) and getattr(attr, "__module__", None) == module.__name__:
                names.add(attr.__name__)
    return names


@pytest.mark.anyio
async def test_nominal_exposes_write_tools():
    names = await _tool_names()
    assert {
        "add_transaction",
        "save_thesis",
        "create_index",
        "add_to_watchlist",
        "remove_from_watchlist",
    } <= names


@pytest.mark.anyio
async def test_read_only_hides_write_tools(monkeypatch):
    monkeypatch.setenv("OBOLE_MCP_READ_ONLY", "1")
    names = await _tool_names()
    assert not (names & tools_pkg.WRITE_TOOLS)


@pytest.mark.anyio
async def test_read_only_keeps_read_tools(monkeypatch):
    monkeypatch.setenv("OBOLE_MCP_READ_ONLY", "1")
    names = await _tool_names()
    assert {
        "get_stock_analysis",
        "screen_french_stocks",
        "list_positions",
        "get_watchlist",
        "rank_watchlist",
    } <= names


def test_write_tools_covers_every_writing_verb():
    verbs = _verb_names()
    assert set(tools_pkg.WRITE_TOOLS) <= verbs
    for name in verbs:
        if name.startswith(WRITING_PREFIXES):
            assert name in tools_pkg.WRITE_TOOLS, f"{name} écrit mais n'est pas déclaré"


def test_write_tools_is_not_empty():
    assert len(tools_pkg.WRITE_TOOLS) >= 10
