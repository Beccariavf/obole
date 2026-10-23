"""Serveur MCP Obole (jalon 09.0) — socle, transport stdio.

Instance unique `mcp` (`MCPServer`, SDK v2) sur laquelle viennent se brancher les
outils des jalons suivants (`tools/`). Rien ici ne porte de logique métier : les
outils sont des **verbes** qui délèguent à `services/` / `engine/` / `data/`.

Transport : **stdio** par défaut (`PRD.md` §12.3). Conséquence non négociable :
**stdout est le canal du protocole** — jamais de `print()` dans cette couche. La
journalisation passe par `observability` (console sur **stderr**).

Lancement local (une IA cliente démarre ce process) :

    PYTHONPATH=src .venv/bin/python -m obole.mcp.server
"""

from __future__ import annotations

from typing import TypedDict

from mcp.server import MCPServer

from obole import __version__, config

# Nom affiché à l'IA cliente ; la version vient de la source unique du paquet
# (`obole.__version__`, lue aussi par `pyproject.toml`) — aucune duplication.
NAME = "obole"

mcp = MCPServer(NAME, version=__version__)


class OboleStatus(TypedDict):
    """Contrat de retour de l'outil de vérification (schéma de sortie de l'IA)."""

    status: str
    schema_version: int
    reg_years_default: int
    obole_version: str


def obole_status() -> OboleStatus:
    """Outil de vérification du socle MCP.

    Vérifie que la chaîne IA → serveur MCP → `config.py`/`models.py` → données
    fonctionne, et renvoie la version du paquet, la version du schéma de la base
    locale (`cache.sqlite`) et la fenêtre de régression par défaut de la méthode
    « droite d'Obole ». Aucun seuil n'est dupliqué ici : tout vient de `config`
    (la version, elle, vient de la source unique `obole.__version__`).

    Returns:
        OboleStatus: `{"status": "ok", "schema_version": int,
        "reg_years_default": int, "obole_version": str}`.
    """
    return {
        "status": "ok",
        "schema_version": config.SCHEMA_VERSION,
        "reg_years_default": config.REGRESSION_YEARS_DEFAULT,
        "obole_version": __version__,
    }


mcp.tool()(obole_status)

# Outils de lecture (jalon 09.1) : stock, ratio, recherche, indices. Un module
# par famille dans `mcp/tools/` — l'import vit en fin de module pour que `mcp`
# soit déjà défini (évite un import circulaire au chargement).
from obole.mcp.tools import register as _register_tools  # noqa: E402

_register_tools(mcp)


def main() -> None:
    """Démarre le serveur en transport stdio (bloquant)."""
    mcp.run()


if __name__ == "__main__":
    main()
