# Phase 1 — Backend

## Scope

- `services/watchlist.py::_row_from_analysis` : régression ajustée, prix juste 12 %,
  conversion brute, `Pot. 5A/10A` ajustés.
- `services/watchlist.py::run` : passer `prices` au row builder.
- Tests `test_watchlist.py` : ligne total-return, prix 12 %, marge, tri, saved prioritaire.

## Acceptance

- [ ] `z`, `σ`, pente, écart et Pot. 5A/10A sont calculés sur `regression_adj`.
- [ ] Sans prix juste : fair = `droite_H / 1,12^5` converti en unités brutes ; cible 12.
- [ ] Avec prix juste enregistré : fair et cible enregistrés priment.
- [ ] Tests backend + réseau + ruff + mypy verts.
