# Run — Fiabilité de la Clara Vallis

- **Date :** 2026-10-29
- **Branche :** `feat/clara-vallis-fiabilite`
- **Portée :** cinq phases du plan, puis correctifs de la revue round 1.

## Commandes et résultats exacts

| # | Commande | Résultat |
| - | -------- | -------- |
| 1 | `.venv/bin/python -m pytest -m "not network" -p no:cov -p no:flask -p no:mock -q` | `1324 passed, 1 skipped, 5 deselected, 1 warning in 15.33s` |
| 2 | `.venv/bin/python -m pytest tests/test_calibration_network.py -p no:cov -q` | `5 passed in 1.26s` |
| 3 | `cd web-tests && npm test` | `Test Files 29 passed (29)` · `Tests 711 passed (711)` |
| 4 | `cd web-tests && npm run test:e2e` | `178 passed (3.2m)` — exit 0, Chromium + WebKit |
| 5 | `.venv/bin/ruff check .` | `All checks passed!` |

### Preuves des critères P5.3 à P5.5

- **P5.3 — défilement à 640 px :** `web-tests/e2e/momentum.spec.js` (test « fiabilité : le tableau
  défile dans sa carte sous 640 px ») vérifie que `.mom-table-wrap` défile (`scrollWidth >
  clientWidth`) et reste dans la carte. Passé sur Chromium **et** WebKit dans le run complet.
- **P5.4 — smoke Chromium + WebKit :** les cinq tests de `web-tests/e2e/momentum.spec.js`
  (dont les deux nouveaux cas fiabilité) passent sur les deux moteurs.
- **P5.5 — trois suites vertes :** backend hors réseau (ligne 1), vitest (ligne 3) et e2e
  (ligne 4). La calibration Pernod (ligne 2) reste verte.

## Note sur le correctif de test e2e

`web-tests/e2e/sections.spec.js` (test « les graphes d'une vue se remettent à l'échelle à
l'entrée ») échouait sur la base e2e vide : aucun portefeuille n'y est seedé, donc
`#pf-summary-plot` n'avait pas de courbe à tracer. Le test mocke désormais
`**/api/portfolio/summary**` avec un résumé minimal non vide (dates + `portfolio` +
`benchmark_curve`), sans changer son intention (le redimensionnement du graphe à l'entrée).
Correctif **de test uniquement**, pré-existant à ce chantier.

## Hors porte (constat, non bloquant)

`mypy src/obole/engine src/obole/services src/obole/mcp src/obole/models.py` conserve cinq
erreurs pré-existantes dans `src/obole/services/serialize.py` (assignations de dicts de
payload), reproduites sur la base du chantier ; hors périmètre et non élargies ici.
