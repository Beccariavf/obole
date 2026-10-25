# Phase 1 — Backend

## Scope

- `services/serialize.py::_downsample` : ajouter le dernier point s'il manque.
- `services/watchlist.py::ref_stats` : ajouter `a`, `b`, `sigma`.
- `services/watchlist.py::_row_from_analysis` : `pente_pct` brute.
- Tests : `test_api.py` (dernier point), `test_watchlist.py` (params, pente), `test_watchlist_api.py` (payload).

## Acceptance

- [ ] `_downsample` conserve premier et dernier point, sans doublon.
- [ ] `chart_payload` : `dates[-1]` = dernier cours réel, `price_raw[-1]`/`price_adj[-1]` à jour.
- [ ] `ref_stats` : `a/b/sigma` égaux à `fit_log_regression`.
- [ ] Ligne de watchlist : pente = `regression_raw.perf_annual*100`.
- [ ] Tests backend + réseau + ruff + mypy verts.
