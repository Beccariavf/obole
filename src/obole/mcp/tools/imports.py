"""Outil MCP `propose_import` — staging d'un import CSV (#23).

Le seul **verbe d'écriture « douce »** de la couche : il prépare un import
(comptes financiers) à partir d'un CSV brut, corrige un format cassé, et le
dépose en **brouillon** soumis à validation humaine. Il n'écrit **jamais** une
donnée métier.

Garde-fou du chantier : **aucun outil MCP d'application**. `apply_draft` vit dans
`services/imports.py` mais n'est branché que sur une route REST ; l'IA ne peut
donc pas contourner la revue de l'utilisateur. Un test structurel échoue si un
outil d'application apparaît ici.
"""

from __future__ import annotations

from mcp.server.mcpserver.exceptions import ToolError

from obole.services import imports as imports_service


def propose_import(target: str, ref: str, csv_text: str) -> dict:
    """Prépare un import CSV (comptes financiers) et le soumet à validation humaine.

    Analyse un CSV brut **sans l'appliquer** : détecte le délimiteur (virgule,
    point-virgule d'Excel FR, tabulation d'un copier-coller) et normalise les
    nombres (virgule décimale, séparateurs de milliers, parenthèses négatives,
    devise). Corrige donc un export au format approximatif, mais ne modifie rien :
    le lot est déposé en **brouillon** que l'utilisateur valide ou rejette depuis
    Obole. Aucun outil ne permet d'appliquer un brouillon — c'est volontaire.

    Args:
        target: cible de l'import. Seule valeur admise aujourd'hui :
            `"fundamentals"` (postes des comptes annuels du CSV de la fiche).
        ref: ticker Yahoo visé (ex. `"RI.PA"`).
        csv_text: contenu CSV brut (texte, jamais un chemin). En-tête `year`
            attendu, puis une colonne par poste ; les ratios calculés et les
            colonnes inconnues sont ignorés et signalés dans le rapport. Formats
            numériques acceptés : virgule décimale, séparateurs de milliers
            (espace, insécable, apostrophe), parenthèses négatives, devise. Un
            point isolé est lu comme décimal (`1.234` -> 1.234), donc un export
            dont les milliers seraient écrits au point (`8.500.000`) doit être
            reformaté (espace ou virgule décimale).

    Returns:
        `{"draft_id": int, "target": str, "ref": str, "status": "pending",
        "accepted": int, "overridden": int, "rejected_total": int,
        "rejected": [{"year", "metric", "raw", "reason"}],
        "unknown_columns": [str], "derived_columns": [str], "delimiter": str}` —
        `draft_id` sert à l'utilisateur pour valider l'import dans l'interface.

    Raises:
        ToolError: cible inconnue, ticker vide, CSV vide ou trop volumineux,
            plus de `config.IMPORT_MAX_ENTRIES` valeurs, ou plafond de brouillons
            en attente atteint.
    """
    try:
        return imports_service.propose_import(target, ref, csv_text)
    except ValueError as exc:
        raise ToolError(str(exc)) from None


def register(server) -> None:
    """Enregistre l'outil de staging d'import sur le serveur MCP."""
    server.tool()(propose_import)
