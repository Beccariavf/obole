"""Outils MCP de la watchlist (#25) — lecture + organisation, jamais le jugement.

Délègue à `services/watchlist.py` (le même cas d'usage que les routes REST) et
sérialise via `services/serialize` : l'IA voit exactement ce que l'utilisateur
voit, et les payloads restent alignés (parité vérifiée par test).

**Frontière actée.** L'IA peut **organiser** : lire la liste et le classement,
ajouter/déplacer une valeur dans un tier, la retirer. Elle ne peut **pas**
définir la fenêtre de confiance (`ticker_refs`) ni le prix juste/objectif de
rendement (`valuation_settings`) : ce sont des jugements humains, réservés à la
fiche (barre de période et calculatrice). Aucun outil de ce module ne les
expose — c'est volontaire, et le mode `--read-only` masque en plus les deux
écritures d'appartenance.

Les écritures sont déclarées dans `WRITE_TOOLS` : elles sont absentes de la
surface en lecture seule et déclenchent un snapshot de la base avant exécution
(`_SnapshotServer`). Aucun outil n'appelle le réseau pour ajouter/retirer ; seul
le classement lit les prix (cache 1 jour) et peut donc être long à froid.
"""

from __future__ import annotations

from typing import Literal

from mcp.server.mcpserver.exceptions import ToolError

from obole.mcp.tools._shared import validate_view
from obole.services import screener as screener_service
from obole.services import serialize
from obole.services import watchlist as watchlist_service


def get_watchlist() -> dict:
    """État de la watchlist : tiers, valeurs suivies et fenêtres de confiance.

    Appel **instantané** (aucun réseau, aucune analyse) : c'est le préalable à
    `rank_watchlist`. Les tiers sont fixes (1, 2, 3) ; leur libellé et leur aide
    (`hint`) viennent de `config.py`. Une valeur appartient à **un seul** tier.

    `refs` associe à chaque ticker la **date de départ de sa fenêtre de
    confiance** (choisie par l'utilisateur) ; son absence signifie « fenêtre
    20 ans par défaut ». Cette référence est un jugement humain : elle se lit,
    elle ne s'écrit pas par l'IA.

    Returns:
        `{"tiers": [{"id", "label", "hint"}], "items": [{"ticker", "tier",
        "added_at"}], "refs": {ticker: "AAAA-MM-JJ"}}`. Identique à
        `GET /api/watchlist`.
    """
    return serialize.watchlist_state_to_dict(watchlist_service.list_state())


def rank_watchlist(
    tier: int | None = None,
    max_rows: int | None = None,
    view: Literal["summary", "full"] = "summary",
) -> dict:
    """Classe les valeurs suivies par **marge de sécurité**.

    Deux lectures, volontairement distinctes :

    - `safety_margin_pct` = (prix juste − cours) / prix juste. Le prix juste est
      celui **enregistré** par l'utilisateur dans la calculatrice
      (`fair_price_source="saved"`, avec son `target_yield`) ; à défaut, c'est la
      **droite de référence** (`fair_price_source="regression"`), et dans ce cas
      la marge coïncide avec `trend_gap_pct` par construction — le badge de
      source et `fair_price_source` doivent être cités pour ne pas tromper.
    - `trend_gap_pct` = (droite − cours) / droite, et `z` = distance en σ à cette
      droite. `z` est la lecture ajustée au risque (comparable entre sociétés) ;
      le pourcentage est l'écart brut. Les deux sont calculés sur les **prix
      bruts** (`raw`) et sur la fenêtre de confiance du titre (`ref_start`, sinon
      20 ans ; `ref_is_default=true`).

    `margin_good` porte la polarité (True = marge positive), `error` isole un
    ticker indisponible. Les lignes sont triées par marge décroissante, les
    valeurs absentes puis les erreurs en dernier.

    Args:
        tier: ne classe qu'un tier (1, 2 ou 3) ; `null` = toute la watchlist.
        max_rows: borne le nombre de lignes renvoyées (> 0) ; `null` = toutes.
            `count` reste le total réel, même si `rows` est tronqué.
        view: `"summary"` (défaut) = champs de décision, payload compact pour le
            contexte ; `"full"` = ligne complète (secteur, potentiels, warnings),
            strictement identique à `POST /api/watchlist/run`.

    Returns:
        `{"generated_at": float, "count": int, "rows": [dict]}`.

    Raises:
        ToolError: tier invalide, `max_rows` <= 0, ou `view` inconnu.

    Note:
        À froid, le classement analyse N tickers (yfinance) : plusieurs dizaines
        de secondes possibles. Appeler `get_watchlist` d'abord pour ne scanner
        que ce qui est utile (`tier`, `max_rows`, `view="summary"`).
    """
    try:
        clean_tier = None if tier is None else watchlist_service.validate_tier(tier)
        clean_max_rows = screener_service.validate_max_rows(max_rows)
    except ValueError as exc:
        raise ToolError(str(exc)) from None
    clean_view = validate_view(view)
    run = watchlist_service.run(tier=clean_tier)
    return serialize.watchlist_run_to_dict(run, view=clean_view, max_rows=clean_max_rows)


def add_to_watchlist(ticker: str, tier: int) -> dict:
    """Ajoute une valeur à un tier, ou la DÉPLACE si elle est déjà suivie.

    Geste d'**organisation**, pas de jugement : le tier est une conviction de
    l'utilisateur. `tier` est donc **obligatoire** ; si l'utilisateur ne l'a pas
    dit, demandez-le plutôt que d'inventer. N'appelle pas le réseau : un ticker
    inconnu sera signalé en erreur au prochain `rank_watchlist`. La fenêtre de
    confiance existante du titre est conservée.

    Args:
        ticker: symbole Yahoo (ex. `"RI.PA"`), normalisé en majuscules.
        tier: 1, 2 ou 3 (voir `get_watchlist` pour les libellés).

    Returns:
        `{"status": "ok", "item": {"ticker", "tier", "added_at"}}`.

    Raises:
        ToolError: ticker invalide, tier invalide, ou watchlist pleine.
    """
    try:
        item = watchlist_service.set_tier(ticker, tier)
    except ValueError as exc:
        raise ToolError(str(exc)) from None
    return {"status": "ok", "item": item}


def remove_from_watchlist(ticker: str) -> dict:
    """Retire une valeur de la watchlist. La référence de confiance est CONSERVÉE.

    Geste demandé explicitement par l'utilisateur (ne pas retirer de sa propre
    initiative). La valeur disparaît du classement mais sa fenêtre de confiance
    (`ticker_refs`) reste : le « Prix juste » du Résumé continue de l'utiliser.

    Args:
        ticker: symbole Yahoo (ex. `"RI.PA"`).

    Returns:
        `{"status": "removed" | "absent", "ticker": str}` — `absent` si la valeur
        n'était pas suivie (idempotent).

    Raises:
        ToolError: ticker invalide.
    """
    try:
        key = watchlist_service.normalize_ticker(ticker)
        removed = watchlist_service.remove(key)
    except ValueError as exc:
        raise ToolError(str(exc)) from None
    return {"status": "removed" if removed else "absent", "ticker": key}


def register(server) -> None:
    """Enregistre les quatre outils watchlist sur le serveur MCP."""
    server.tool()(get_watchlist)
    server.tool()(rank_watchlist)
    server.tool()(add_to_watchlist)
    server.tool()(remove_from_watchlist)
