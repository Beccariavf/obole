# Review: watchlist total-return + prix juste à 12 %

- Rounds: 1
- Started: 2026-10-25

## Round 1 · r-c4a8

- Date: 2026-10-25
- By: Beccariavf
- Diff: `main...feat/watchlist-total-return` (plus l'arbre de travail, `review.md` exclu)
- Axes: code, functional, relevancy
- Verdict: approve
- Score: 5/5 met, 0 unmet, 0 unverified at runtime, 0 out of the diff

### Criteria

- [x] ACA (ref 2016-10-25) en watchlist : z/σ/Pot. 5A total-return, prix juste 12 % et marge calculée contre ce prix, source « droite » + « objectif 12 %/an » — `services/watchlist.py` (row), `tests/test_watchlist.py::TestRun::test_row_is_total_return_with_12pct_fallback`, run réel (z 0,42 σ ; σ 23,51 % ; Pot. 5A 8,36 % ; prix juste 12,65 ; marge −17,94 %), `captures/watchlist-apres.png`
- [x] Fiche ACA inchangée en vue brute — `web/search.js`/`web/charts.js` #25.1 inchangés pour la fiche, `watch.ref_stats` toujours brut, run fiche (0,13 σ ; Pot. 5A 3,1 % — valeurs rafraîchies, comportement brut) et e2e « référence : la fiche suit… »
- [x] VIE (prix juste enregistré) : marge et objectif enregistrés conservés, z/σ/Pot. 5A total-return — run réel (28,89 ; CALC ; −11,08 % ; z 0,06 σ ; Pot. 5A 10,0 %), `test_rows_are_sorted_by_margin_with_saved_price`
- [x] Légende/tableau à jour, plus de « marge = écart » — `web/index.html` (légende total-return + 12 %), `web/watchlist.js::watchRowTitle`, test Vitest du titre, e2e (badge, objectif, label σ, couverture)
- [x] Tests backend (row total-return, prix 12 %, tri), front, e2e ; calibration inchangée — runs sur la tête : pytest 1257 + réseau 5, ruff/mypy, Vitest 601, Playwright 116 (Chromium + WebKit)

### Findings

- `src/obole/services/watchlist.py:278` : le paramètre `prices` du row builder n'est pas typé, alors que le reste du contrat l'est → annoter `prices: PriceSeries` (import `obole.models`) — 🟢 minor, code-health
- `src/obole/services/watchlist.py:293` : si le fit ajusté de la fenêtre échoue, `_recompute_window` laisse la régression ajustée **pleine histoire** dans `analysis.regression_adj` ; la ligne utiliserait alors silencieusement une autre fenêtre (le `ref_start` le trahirait) → détecter l'écart avec la fenêtre effective (ou avertir dans `warnings`) — 🟢 minor, error-handling
