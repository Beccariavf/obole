"""Tests du socle MCP (jalon 09.0) — sans réseau, sans stdio réel.

Le transport stdio n'est pas testable en unité ; on exerce le protocole via le
transport **in-memory** du SDK (`Client(server)`), qui liste les outils et les
appelle exactement comme le ferait une IA cliente.

Les autres tests sont **structurels** : ils lisent la source de `mcp/` pour
verrouiller les invariants de la couche (pas d'import de `api/`/`web/`, pas
d'écriture sur stdout — canal du protocole —, aucun seuil littéral).
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest
from mcp import Client

from obole import __version__, config
from obole.mcp import server as mcp_server

MCP_DIR = Path(inspect.getfile(mcp_server)).parent


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def mcp_sources() -> list[tuple[str, str]]:
    """(nom, contenu) de chaque module Python de la couche `mcp/` (récursif)."""
    return [
        (str(p.relative_to(MCP_DIR)), p.read_text(encoding="utf-8"))
        for p in sorted(MCP_DIR.rglob("*.py"))
    ]


def test_structure_du_socle():
    assert (MCP_DIR / "__init__.py").is_file()
    assert (MCP_DIR / "server.py").is_file()


@pytest.mark.anyio
async def test_liste_et_appel_de_l_outil_de_verification():
    """Le client liste les outils et appelle l'outil de vérification."""
    async with Client(mcp_server.mcp) as client:
        tools = await client.list_tools()
        assert "obole_status" in [t.name for t in tools.tools]

        result = await client.call_tool("obole_status", {})
        assert result.is_error is False
        payload = result.structured_content
        assert payload["status"] == "ok"
        assert payload["schema_version"] == config.SCHEMA_VERSION
        # La version MCP vient de la source unique du paquet (pas de littéral).
        assert payload["obole_version"] == __version__


def test_outil_verification_a_une_docstring():
    """La docstring de l'outil EST la doc de l'IA (`PRD.md` §12.3)."""
    assert inspect.getdoc(mcp_server.obole_status)


def test_aucun_import_de_api_ni_web(mcp_sources):
    """Invariant de couche : `mcp/` ne remonte jamais vers `api/` ni `web/`."""
    for name, source in mcp_sources:
        assert "obole.api" not in source, name
        assert "obole.web" not in source, name


def test_aucun_ecrit_sur_stdout(mcp_sources):
    """stdout est le canal du protocole stdio : jamais de `print` dans `mcp/`."""
    for name, source in mcp_sources:
        assert "sys.stdout" not in source, name
        assert not re.search(r"^\s*print\(", source, re.M), name


def test_aucun_seuil_litteral_module_level(mcp_sources):
    """Zéro seuil littéral : toute constante vient de `config.py`."""
    pattern = re.compile(r"^[A-Z_][A-Z0-9_]*\s*(?::[^=\n]+)?=\s*-?\d", re.M)
    for name, source in mcp_sources:
        assert not pattern.search(source), name


def test_aucun_outil_n_applique_un_import(mcp_sources):
    """Garde-fou #23 : la couche MCP ne peut JAMAIS appliquer un brouillon d'import.

    L'IA prépare un import (`propose_import`) ; la validation est un acte humain
    dans l'interface (routes REST `/api/imports/{id}/apply`). Si un outil MCP
    appelait `apply_draft`, l'IA contournerait cette revue — exactement ce que le
    chantier veut interdire. Ce test échoue à l'ajout d'un tel outil.
    """
    # 1. Statique : aucun APPEL de code (les docstrings qui l'expliquent sont
    #    légitimes, on cherche l'usage réel).
    call = re.compile(r"\.(apply_draft|apply_import)\s*\(")
    for name, source in mcp_sources:
        assert not call.search(source), f"{name} ne doit pas appeler apply_*"

    # 2. Runtime : aucun outil exposé ne porte un nom d'application.
    #    (`obole_status` est inclus : aucun outil de la liste ne doit être un
    #    « apply ».)
    import asyncio

    from mcp import Client

    async def _names() -> list[str]:
        async with Client(mcp_server.mcp) as client:
            tools = await client.list_tools()
            return [t.name for t in tools.tools]

    names = asyncio.run(_names())
    assert "propose_import" in names
    assert not [n for n in names if "apply" in n], names


def test_propose_import_est_le_seul_verbe_d_import(mcp_sources):
    """L'outil de staging existe bien, et il délègue au service partagé."""
    sources = dict(mcp_sources)
    module = sources.get("tools/imports.py")
    assert module is not None
    assert "imports_service.propose_import" in module
    # Aucun accès direct à `data/` pour écrire : c'est le service qui décide.
    assert "cache.add_import_draft" not in module
