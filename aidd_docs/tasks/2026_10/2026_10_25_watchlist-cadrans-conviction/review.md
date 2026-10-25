# Review: watchlist cadrans, jeu de convictions et Pot. 5A de valorisation

- Rounds: 1
- Started: 2026-10-25

## Round 1 · r-9d3f

- Date: 2026-10-25
- By: Beccariavf
- Diff: `main...feat/watchlist-cadrans-conviction` (plus l'arbre de travail, `review.md` exclu)
- Axes: code, functional, relevancy
- Verdict: approve
- Score: 7/7 met, 0 unmet, 0 unverified at runtime, 0 out of the diff

### Criteria

- [x] AMUN (Tier 2) affiche Tier 2 dans le select ; filtre/compteurs/fiche cohérents ; changement vers Tier 3 — e2e « watchlist : bouton… » (valeur 2, changement 3, compteurs), vérification serveur réel, `captures/watchlist-table.png`
- [x] VIE (prix juste enregistré) : Pot. 5A = estimation valorisation ≈ 9,77 %, badge `valo` ; marge inchangée (−11,08 %) — run réel `/api/watchlist/run`, `tests/test_watchlist.py::TestRun::test_pot_5y_valorisation_with_dividend`, `captures/watchlist-cadrans.png`
- [x] AMUN/ACA (sans prix juste) : Pot. 5A droite total-return, badge `droite` — run réel (ACA 8,36 %, AMUN 4,22 %), `tests/test_watchlist.py::TestRun::test_rows_are_sorted…`
- [x] La fiche reste en vue référence brute ; le prix juste enregistré prime — e2e « référence : la fiche suit… », run fiche (0,13 σ ; Pot. 5A 3,1 %), code #25.1 inchangé
- [x] Vue cadrans : 3 colonnes, cadrans de marge, cartes complètes, bascule tableau, responsive, états vides — e2e « vue cadrans… », `web-tests/watchlist-dials.test.js`, `captures/watchlist-cadrans.png`, `watchlist-table.png`
- [x] Jeu : 12 comparaisons, résultat avec tiers suggérés, application, annulation, rejouer, moins de 2 → désactivé — `web-tests/conviction.test.js`, e2e « jeu de convictions… » (annulation, résultat, application interceptée), `captures/conviction-duel.png`, `conviction-result.png`
- [x] Tests backend (dont réseau), front, e2e Chromium + WebKit ; aucun schéma ; calibration Pernod — runs sur la tête : pytest 1266 + réseau 5, ruff/mypy, Vitest 614, Playwright 120

### Findings

- `src/obole/web/conviction-mixin.js:147` : « Appliquer les tiers » fait N appels séquentiels ; une erreur au milieu laisse les changements déjà envoyés appliqués (l'UI le signale) → une route bulk atomique ou un rollback des changements déjà faits — 🟢 minor, error-handling
- `src/obole/services/watchlist.py:267` : une valorisation enregistrée **ancienne** sans `include_dividends`/`dividend_yield` est traitée avec un dividende 0 ; la projection dérivée du prix juste peut alors ne pas correspondre au prix juste enregistré → avertir ou retomber sur la droite quand ces champs manquent — 🟢 minor, error-handling
