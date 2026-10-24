# Phase 3 — Classement + API

## Scope

- `models.py` : `WatchlistRow`, `WatchlistRun`.
- `services/watchlist.py` : validation, CRUD, `set_ref`/`clear_ref`, `ref_stats`, `stock_state`,
  `decorate_stock_payload`, `run(tier=None)`.
- `services/serialize.py` : `watchlist_state_to_dict`, `watchlist_run_to_dict(view, max_rows)`.
- `api/app.py` : routes watchlist, `/api/stock` décoré, `/api/meta` enrichi.
- Tests : service (formules, tri, erreurs), API (200/422, payloads).

## Acceptance

- [ ] `run()` trie par marge décroissante, nulls en dernier, puis écart, puis tier.
- [ ] Prix juste enregistré prioritaire ; repli « droite » marqué `fair_price_source`.
- [ ] Erreurs de ticker isolées, tier conservé.
- [ ] `/api/stock` porte `watch` ; `/api/meta` porte `watch`.
- [ ] Validations 422 (tier, date, plafond, points insuffisants).
