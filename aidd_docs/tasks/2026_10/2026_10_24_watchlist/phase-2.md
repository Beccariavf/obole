# Phase 2 — Fenêtrage + Résumé aligné

## Scope

- `engine/regression.py` : `REGRESSION_MIN_POINTS` au lieu du littéral 30.
- `engine/summary.py` : `window_since(series, start)`.
- `services/analysis.py` : `reference_window(ticker, raw)` ; `_fair_price` basé sur cette fenêtre ;
  le prix juste enregistré reste prioritaire ; note de carte.
- `engine/summary_fundamentals.py` : `build_summary(..., fair_price_note=None)` (remplace
  `fair_price_saved`).
- `services/screen.py` : `windowed_analysis` (ref_start prioritaire), `screen_stock` mince appelant.
- `services/screener.py` : `scan_parallel` extrait de `_scan_universe`.
- Tests : analysis/summary/screen/screener + `pytest -m network`.

## Acceptance

- [ ] Sans référence, le « Prix juste » est la droite 20 ans (comportement inchangé).
- [ ] Avec une référence, il est la droite de référence, note « prix bruts, depuis AAAA ».
- [ ] Avec un prix juste enregistré, il gagne sur la référence.
- [ ] `windowed_analysis(ref_start=...)` tranche raw/adj et recalcule z/σ/potentiels.
- [ ] `scan_parallel` conserve budget/timeout du screener.
- [ ] `pytest -m network` vert (Pernod inchangé) ; `mypy` vert.
