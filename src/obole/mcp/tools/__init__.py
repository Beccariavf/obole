"""Outils MCP d'Obole — stock, ratio, recherche, indices, screener, thèse,
portefeuille, suivi, staging d'import et watchlist.

Chaque module expose des fonctions **verbe** : leur docstring EST la
documentation lue par l'IA cliente (`PRD.md` §12.3). Aucune formule ni seuil ici :
les outils délèguent à `services/` (orchestration) et `engine/` (cœur pur).
`services/serialize` est appelé pour que le payload suive celui de l'API HTTP ;
les outils de lecture écartent par défaut la série de prix (`chart`,
`view="summary"`) — la parité avec la route vaut donc pour `view="full"` (ou une
fois `chart` retiré en `summary`).

`register(server)` branche tous les outils sur l'instance `mcp` du socle
(`mcp/server.py`), qui l'appelle au chargement du module.

**Mode lecture seule.** `OBOLE_MCP_READ_ONLY=1` (ou `obole --mcp --read-only`)
n'enregistre PAS les outils listés dans `WRITE_TOOLS` : ils sont absents de la
surface proposée à l'IA, pas simplement en erreur à l'appel — une IA qui ne voit
pas l'outil ne peut pas l'inventer. En mode nominal, chaque écriture
déclenche une copie de sécurité de la base avant de s'exécuter.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from obole.data.backup import snapshot_before_write
from obole.mcp.tools import (
    checkpoints,
    imports,
    indices,
    portfolio,
    ratio,
    screener,
    search,
    stock,
    thesis,
    watchlist,
)

# Outils qui MODIFIENT les données de l'utilisateur (base locale). Toute
# addition d'un outil d'écriture doit figurer ici : c'est la seule liste qui
# sépare le mode nominal du mode lecture seule, et elle est vérifiée par test.
WRITE_TOOLS = frozenset(
    {
        # Thèse : `write_thesis` ne fait que produire un prompt (aucune écriture).
        "save_thesis",
        "delete_thesis",
        # Portefeuille
        "create_account",
        "delete_account",
        "add_transaction",
        "update_transaction",
        "delete_transaction",
        "add_dividend",
        "update_dividend",
        "delete_dividend",
        # Points de contrôle suivis
        "add_checkpoint",
        "update_checkpoint",
        "delete_checkpoint",
        # Indices personnalisés
        "create_index_category",
        "delete_index_category",
        "create_index",
        "update_index",
        "delete_index",
        # Staging d'import (`propose_import` crée un brouillon : c'est une
        # écriture, même si son application reste réservée à l'utilisateur).
        "propose_import",
        # Watchlist (#25) : organisation seulement. La référence de confiance et
        # le prix juste ne sont PAS des outils MCP (jugements humains).
        "add_to_watchlist",
        "remove_from_watchlist",
    }
)


def read_only() -> bool:
    """Le serveur MCP doit-il masquer les outils d'écriture ?

    Lit `OBOLE_MCP_READ_ONLY` au moment de l'enregistrement (et non à l'import),
    pour que le drapeau de la CLI prenne effet sur la même exécution.
    """
    return os.environ.get("OBOLE_MCP_READ_ONLY") == "1"


class _ReadOnlyServer:
    """Proxy de serveur qui n'enregistre que les outils de lecture.

    Les modules `tools/*` continuent d'appeler `server.tool()` sans savoir dans
    quel mode elles tournent : le filtrage vit ici, en un seul endroit.
    """

    def __init__(self, server: Any) -> None:
        self._server = server

    def tool(self) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            if fn.__name__ in WRITE_TOOLS:
                return fn
            self._server.tool()(fn)
            return fn

        return decorator


class _SnapshotServer:
    """Proxy de serveur qui sauvegarde la base avant chaque outil d'écriture.

    Le snapshot est **best-effort** : s'il échoue, l'écriture a quand même lieu
    (un disque plein ne doit pas rendre le MCP inutilisable) — mais l'échec est
    journalisé. Voir `data/backup.snapshot_before_write`.
    """

    def __init__(self, server: Any) -> None:
        self._server = server

    def tool(self) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            if fn.__name__ in WRITE_TOOLS:
                fn = _with_snapshot(fn)
            self._server.tool()(fn)
            return fn

        return decorator


def _with_snapshot(fn: Callable[..., Any]) -> Callable[..., Any]:
    import functools

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        snapshot_before_write()
        return fn(*args, **kwargs)

    return wrapper


def register(server) -> None:
    """Branche les outils sur le serveur MCP (un module par famille).

    Lecture : stock, ratio, search, indices, screener. Écriture pilotée : thèse,
    portefeuille (MCP-B), points de contrôle suivis et staging d'import (le
    brouillon est validé par l'utilisateur — aucun outil ne l'applique).

    En mode lecture seule, les outils de `WRITE_TOOLS` ne sont pas enregistrés ;
    sinon, chacun est précédé d'un snapshot de la base.
    """
    target = _ReadOnlyServer(server) if read_only() else _SnapshotServer(server)

    stock.register(target)
    ratio.register(target)
    search.register(target)
    indices.register(target)
    screener.register(target)
    thesis.register(target)
    portfolio.register(target)
    checkpoints.register(target)
    imports.register(target)
    watchlist.register(target)
