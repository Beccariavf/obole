# Review: cohérence référence / performance 5 ans + popover

- Rounds: 1
- Started: 2026-10-25

## Round 1 · r-7a2e

- Date: 2026-10-25
- By: Beccariavf
- Diff: `main...fix/watchlist-reference-link`
- Axes: code, functional, relevancy
- Verdict: approve
- Score: 9/9 met, 0 unmet, 0 unverified at runtime, 0 out of the diff

### Criteria

- [x] ACA (ref 2016-10-25) : dividendes décochés, synchro cochée, fenêtre fixe décochée — e2e « référence : la fiche suit… » + capture `captures/aca-apres.png`
- [x] KPI = `watch.ref_stats` (z 0,15 ; σ 21,6 % ; perf 3,5 % ; Pot. 5A 2,9 %) — headless sur serveur réel (valeurs identiques à la ligne de watchlist) + e2e
- [x] Dernier point du graphe = dernier cours réel (23 oct. 2026, 14,92 €) — `tests/test_api.py::test_chart_payload_keeps_the_last_point`, headless, capture
- [x] Droite et bandes = régression persistée (a/b/sigma) — `web-tests/watchlist.test.js` (referenceRegression/computeLive), e2e, capture
- [x] Watchlist : `pente_pct` brute — `tests/test_watchlist.py::TestRun::test_pente_is_the_reference_slope` + `ref_stats` a/b/sigma
- [x] Popover lisible (items ≤ 50 px) — e2e Chromium/WebKit (44/46 px, 31 px) + `captures/ref-popover-avant.png` / `ref-popover-apres.png`
- [x] Sans référence : vue par défaut inchangée, hors dernier point désormais réel — suite e2e complète (116) et tests front/API
- [x] Tests backend (dont réseau), front, e2e — `pytest`, `pytest -m network`, `npm test`, `npm run test:e2e`
- [x] `ruff`, `mypy`, calibration Pernod inchangée, aucun schéma — runs cités

### Findings

- `src/obole/api/static_files.py:42` : `_render_index_html`/`_content_hash` sont en `lru_cache` ; un changement d'`index.html`/CSS n'est visible qu'après redémarrage du serveur (les modules JS relatifs sont relus). Pré-existant, documenté dans #25.1 §8 ; pas un défaut du diff — 🟢 minor, fit
- `src/obole/web/search.js:89` : une fiche référencée force dividendes off + synchro à **chaque** chargement (y compris refresh) ; un utilisateur qui explore le total return le perd au refresh. Décision assumée de la vue référence, documentée — 🟢 minor, frontend
- `src/obole/web/charts.js:51` : si la date de référence tombe entre deux points décimés, le libellé de période commence au premier point décimé ≥ référence, alors que la droite serveur part de `ref_stats.start` (quelques jours d'écart visuel). Sans effet sur les KPI, qui lisent les paramètres serveur — 🟢 minor, frontend
