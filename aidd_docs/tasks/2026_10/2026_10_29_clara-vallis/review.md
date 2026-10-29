# Review: La Clara Vallis — onglet Momentum

- Rounds: 2
- Started: 2026-10-29

## Round 1 · r-7c1e

- Date: 2026-10-29
- By: Beccariavf
- Diff: `main...HEAD`
- Axes: code, functional, relevancy
- Verdict: changes-requested
- Score: 26/32 met, 0 unmet, 6 unverified at runtime, 0 out of the diff

### Criteria

- [x] Série croissante ≥ 0,99, décroissante ≤ 0,01 — `tests/test_clara_vallis.py::test_rising_series_scores_one`, `::test_falling_series_scores_zero`
- [x] Série plate 0,5 ; 40 points → `short_history` — `tests/test_clara_vallis.py::test_flat_series_scores_half`, `::test_short_history_is_flagged`
- [x] `satisfaction_series` : `NaN` sur les 249 premières séances — `tests/test_clara_vallis.py::test_series_is_nan_before_window`
- [x] Ajouter une séance future ne change aucune valeur passée — `tests/test_clara_vallis.py::test_no_lookahead`
- [x] Droite log-linéaire → confiance 0,0 — `tests/test_clara_vallis.py::test_regime_perfect_line_is_zero`
- Unverified at runtime: 10 000 séances en moins d'une seconde — seule l'exécution du test de temps le montre
- [x] Payload : `raw`, `adj`, `score_raw`, `n_used`, `year` — `src/obole/services/momentum.py:28`
- [x] `raw` et `adj` de la longueur de `chart.dates` — `tests/test_momentum_service.py::test_payload_aligns_on_chart_dates`
- [x] `year.dates` finit sur la dernière séance, ≤ 250 entrées — `tests/test_momentum_service.py::test_payload_aligns_on_chart_dates`
- [x] Indice : `adj` à `None` ; ratio sans `momentum` — `tests/test_momentum_service.py::test_index_has_no_adjusted_series`, `src/obole/services/serialize.py:389`
- [x] Second appel servi par le cache, invalidation qui recalcule — `tests/test_momentum_service.py::test_second_call_is_cached`, `::test_invalidate_forces_recompute`
- Unverified at runtime: payload à froid sous 500 ms sur 10 000 séances — seule l'exécution du test de temps le montre
- [x] `MOMENTUM_SATISFACTION_LOW` strictement inférieur à `HIGH` — `src/obole/config.py:155`
- [x] `/api/meta` expose les quatre champs et `applyMeta` les lit — `web-tests/momentum-parity.test.js`
- [x] Fixture ≥ 6 000 lignes, dernière séance de 2023 — `tests/test_clara_vallis_calibration.py::test_fixture_is_frozen_and_long_enough`
- [x] Calibration dans `pytest -m "not network"`, sans réseau — `tests/test_clara_vallis_calibration.py` (aucun marqueur `network`)
- [x] Quatre crises sous la borne basse, trois calmes au-dessus, 2015 entre — `tests/test_clara_vallis_calibration.py::test_crisis_windows_are_below_low`, `::test_calm_windows_are_above_high`, `::test_neutral_window_stays_between`
- [x] Onglet après Valorisation, ouverture au clic — `src/obole/web/sections.js:51`, `setSection`
- [x] Absent sur un ratio, présent sur un indice — `src/obole/web/charts.js` (`sectionAvailable`, `kind_payload` stock/basket)
- [x] Droite log-parfaite → confiance 0,0 et z 0,0 — `web-tests/momentum.test.js::une droite log-parfaite donne une confiance nulle et un z nul`
- [x] Changer de fenêtre change les valeurs — `web-tests/momentum.test.js::la fenêtre change la pente`
- [x] Table à six colonnes et chips de fenêtre — `src/obole/web/momentum.js:134`, `index.html` (`momWindows`)
- [x] Aiguille à gauche si satisfaite, à droite si frustrée — `src/obole/web/momentum.js:171`, `web-tests/momentum.test.js::l'aiguille est à gauche pour une foule satisfaite`
- Unverified at runtime: la courbe à un an affiche les deux seuils et les zones — seul un rendu le montre
- Unverified at runtime: l'historique affiche le cours et les bandes aux changements de régime — seul un rendu le montre
- [x] Chips et double poignée ne déplacent pas le graphe du Résumé — `momStart`/`momEnd` distincts de `rangeStart`/`rangeEnd`, `src/obole/web/momentum.js:64`
- [x] Basculer brut/ajusté redessine jauge, courbe et historique — `index.html` (`@change` → `drawMomentum`)
- [x] Historique court : badge et aucun bloc cassé — `index.html` (`x-show="momData()?.short_history"`)
- [x] Jauge annoncée comme `meter` avec sa valeur — `index.html` (`role="meter"`, `aria-valuenow`)
- [x] À 900 px, les trois cartes sont empilées — `src/obole/web/style.css` (`.mom-blocks` en colonne)
- Unverified at runtime: smoke e2e vert sur Chromium et WebKit — seul un run le montre
- Unverified at runtime: `pytest`, `npm test` et `npm run test:e2e` verts — seul un run le montre

### Findings

- `src/obole/web/momentum.js:246` : la plage `momStart`/`momEnd` n'est jamais réinitialisée quand la fiche change ; sur une fiche plus courte elle se clampe en `[end-1, end]` et l'historique n'affiche plus que deux points → réinitialiser quand `_hashRef()` change, comme `applySectionsAfterLoad` le fait pour la section — 🟡 major, frontend
- `src/obole/web/index.html` : les deux radios de `momSeries` n'ont pas de `name` commun, donc le groupe n'a pas la navigation aux flèches → ajouter `name="mom-series"` — 🟢 minor, frontend
- `src/obole/web/index.html` : `aria-valuenow` reçoit le flottant brut (0.5436585620615721), bruyant à l'annonce → arrondir à deux décimales — 🟢 minor, frontend
- `src/obole/services/momentum.py:22` : `_values` duplique `serialize._vals` (même arrondi, même conversion) → extraire un helper partagé plutôt que deux copies — 🟢 minor, code-health
- `src/obole/services/momentum.py:20` : la clé de cache ignore `MOMENTUM_WINDOW` ; changer la fenêtre laisse un payload périmé jusqu'à 24 h → inclure la fenêtre dans la clé — 🟢 minor, backend
- `web-tests/e2e/screener.spec.js:259` : le correctif du sélecteur ambigu ne relève pas du chantier ; il débloque la suite mais devrait être isolé sur `main` → sortir ce commit du lot — 🟢 minor, fit
- `src/obole/web/style.css` : `#mom-year` et `#mom-history` n'ont pas de hauteur CSS alignée sur `CHART_HEIGHTS.momentum_*`, contrairement à la règle « conteneur = layout Plotly » de `design.md` → variables `--chart-h-mom-*` — 🟢 minor, conform

## Round 2 · r-b2e4

- Date: 2026-10-29
- By: Beccariavf
- Diff: `main...HEAD`
- Axes: code, functional, relevancy
- Verdict: approve
- Score: 26/32 met, 0 unmet, 6 unverified at runtime, 0 out of the diff

### Criteria

- [x] Série croissante ≥ 0,99, décroissante ≤ 0,01 — `tests/test_clara_vallis.py::test_rising_series_scores_one`, `::test_falling_series_scores_zero`
- [x] Série plate 0,5 ; 40 points → `short_history` — `tests/test_clara_vallis.py::test_flat_series_scores_half`, `::test_short_history_is_flagged`
- [x] `satisfaction_series` : `NaN` sur les 249 premières séances — `tests/test_clara_vallis.py::test_series_is_nan_before_window`
- [x] Ajouter une séance future ne change aucune valeur passée — `tests/test_clara_vallis.py::test_no_lookahead`
- [x] Droite log-linéaire → confiance 0,0 — `tests/test_clara_vallis.py::test_regime_perfect_line_is_zero`
- Unverified at runtime: 10 000 séances en moins d'une seconde — seule l'exécution du test de temps le montre
- [x] Payload : `raw`, `adj`, `score_raw`, `n_used`, `year` — `src/obole/services/momentum.py:33`
- [x] `raw` et `adj` de la longueur de `chart.dates` — `tests/test_momentum_service.py::test_payload_aligns_on_chart_dates`
- [x] `year.dates` finit sur la dernière séance, ≤ 250 entrées — `tests/test_momentum_service.py::test_payload_aligns_on_chart_dates`
- [x] Indice : `adj` à `None` ; ratio sans `momentum` — `tests/test_momentum_service.py::test_index_has_no_adjusted_series`, `src/obole/services/serialize.py:389`
- [x] Second appel servi par le cache, invalidation qui recalcule — `tests/test_momentum_service.py::test_second_call_is_cached`, `::test_invalidate_forces_recompute`
- Unverified at runtime: payload à froid sous 500 ms sur 10 000 séances — seule l'exécution du test de temps le montre
- [x] `MOMENTUM_SATISFACTION_LOW` strictement inférieur à `HIGH` — `src/obole/config.py:155`
- [x] `/api/meta` expose les quatre champs et `applyMeta` les lit — `web-tests/momentum-parity.test.js`
- [x] Fixture ≥ 6 000 lignes, dernière séance de 2023 — `tests/test_clara_vallis_calibration.py::test_fixture_is_frozen_and_long_enough`
- [x] Calibration dans `pytest -m "not network"`, sans réseau — `tests/test_clara_vallis_calibration.py` (aucun marqueur `network`)
- [x] Quatre crises sous la borne basse, trois calmes au-dessus, 2015 entre — `tests/test_clara_vallis_calibration.py::test_crisis_windows_are_below_low`, `::test_calm_windows_are_above_high`, `::test_neutral_window_stays_between`
- [x] Onglet après Valorisation, ouverture au clic — `src/obole/web/sections.js:51`, `setSection`
- [x] Absent sur un ratio, présent sur un indice — `src/obole/web/charts.js` (`sectionAvailable`, `kind_payload` stock/basket)
- [x] Droite log-parfaite → confiance 0,0 et z 0,0 — `web-tests/momentum.test.js::une droite log-parfaite donne une confiance nulle et un z nul`
- [x] Changer de fenêtre change les valeurs — `web-tests/momentum.test.js::la fenêtre change la pente`
- [x] Table à six colonnes et chips de fenêtre — `src/obole/web/momentum.js:148`, `index.html` (`momWindows`)
- [x] Aiguille à gauche si satisfaite, à droite si frustrée — `src/obole/web/momentum.js:185`, `web-tests/momentum.test.js::l'aiguille est à gauche pour une foule satisfaite`
- Unverified at runtime: la courbe à un an affiche les deux seuils et les zones — seul un rendu le montre
- Unverified at runtime: l'historique affiche le cours et les bandes aux changements de régime — seul un rendu le montre
- [x] Chips et double poignée ne déplacent pas le graphe du Résumé — `momStart`/`momEnd` distincts de `rangeStart`/`rangeEnd`, `src/obole/web/momentum.js:78`
- [x] Basculer brut/ajusté redessine jauge, courbe et historique — `index.html` (`@change` → `drawMomentum`)
- [x] Historique court : badge et aucun bloc cassé — `index.html` (`x-show="momData()?.short_history"`)
- [x] Jauge annoncée comme `meter` avec sa valeur — `index.html` (`role="meter"`, `aria-valuenow` arrondi)
- [x] À 900 px, les trois cartes sont empilées — `src/obole/web/style.css` (`.mom-blocks` en colonne)
- Unverified at runtime: smoke e2e vert sur Chromium et WebKit — seul un run le montre
- Unverified at runtime: `pytest`, `npm test` et `npm run test:e2e` verts — seul un run le montre

### Findings

- `web-tests/e2e/screener.spec.js:259` : le correctif du sélecteur ambigu ne relève pas du chantier ; il débloque la suite mais devrait être isolé sur `main` → sortir ce commit du lot — 🟢 minor, fit
