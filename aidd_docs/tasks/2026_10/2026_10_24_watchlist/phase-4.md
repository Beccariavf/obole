# Phase 4 — MCP

## Scope

- `mcp/tools/watchlist.py` : `get_watchlist`, `rank_watchlist`, `add_to_watchlist`,
  `remove_from_watchlist` ; docstrings = doc IA (deux marges, source, repli, fenêtre).
- `mcp/tools/__init__.py` : enregistrement + `WRITE_TOOLS`.
- `mcp/tools/stock.py` : `get_stock_analysis` décoré avec `watch`.
- Tests : parité API ↔ MCP, `view`/`max_rows`/`tier`, read-only, `WRITE_TOOLS`.

## Acceptance

- [ ] Parité stricte `get_watchlist` ↔ `GET /api/watchlist` et `rank_watchlist(view="full")` ↔
      `POST /api/watchlist/run`.
- [ ] `view="summary"` est un sous-ensemble ; `max_rows` tronque en gardant `count`.
- [ ] Read-only conserve les lectures et masque les deux écritures.
- [ ] Aucun outil ne touche la référence ni le prix juste.
- [ ] Aucun réseau dans les tests (services/prix monkeypatchés).
