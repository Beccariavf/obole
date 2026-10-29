# Review: Fiabilité de la Clara Vallis

- Rounds: 2
- Started: 2026-10-29

## Round 1 · r-7c3e

- Date: 2026-10-29
- By: Beccariavf
- Diff: `feat/clara-vallis...feat/clara-vallis-fiabilite`
- Axes: code, functional, relevancy
- Verdict: changes-requested
- Score: 19/22 met, 1 unmet, 2 unverified at runtime, 0 out of the diff

### Criteria

- [x] **P1.1** L'échelle affiche « satisfaite » et « frustrée », plus « gaz » ni « liquide » — `src/obole/web/index.html:781` (le vocabulaire de Darcet ne survit que dans deux commentaires, `src/obole/web/momentum.js:335` et `:350`)
- [x] **P1.2** `momRange()` et `momPreset("ref")` lisent la même référence — `src/obole/web/momentum.js:85` (`_momReferenceStart`), consommée en `:103` et `:423`
- [x] **P1.3** Le chip « Réf. » est le premier de la barre et laisse le défaut à 10 ans — `src/obole/web/index.html:795` avant `:797` ; défaut `src/obole/web/momentum.js:444`
- [x] **P1.4** Avec une référence persistée, le preset place la plage sur cette date — `src/obole/web/momentum.js:423` ; `web-tests/momentum.test.js:111`
- [x] **P2.1** Au-dessus de 0,60 la stratégie est investie, sous 0,35 elle est en cash — `src/obole/engine/momentum_backtest.py:156` et `:158` ; `tests/test_momentum_backtest.py:62`
- [x] **P2.2** Entre les deux bornes, l'état précédent est conservé (aucun trade) — `src/obole/engine/momentum_backtest.py:156` à `:158` (aucune branche ne se déclenche entre les bornes) ; `tests/test_momentum_backtest.py:45`
- [x] **P2.3** Les huit mesures sont présentes pour les deux colonnes — `src/obole/engine/momentum_backtest.py:86` ; `tests/test_momentum_backtest.py:113`
- [x] **P2.4** Décaler les scores d'un jour décale les trades, jamais l'inverse — `src/obole/engine/momentum_backtest.py:153` (`aligned[t - 1]`) ; `tests/test_momentum_backtest.py:73`
- [x] **P2.5** Un aller-retour coûte environ 0,2 % et un score toujours neutre ne trade pas — `src/obole/engine/momentum_backtest.py:161` ; `tests/test_momentum_backtest.py:93` et `:127`
- [x] **P3.1** Le service renvoie les deux jeux de mesures et la fenêtre tranchée — `src/obole/services/momentum.py:137` ; `tests/test_momentum_backtest_api.py:46`
- [x] **P3.2** Les trois cas invalides répondent 422, un ticker inconnu répond 404 — `src/obole/api/app.py:205` (validation) et `:229` (404) ; `tests/test_momentum_backtest_api.py:115`
- [x] **P3.3** `api.momentumBacktest` construit l'URL avec les quatre paramètres encodés — `src/obole/web/api.js:75` ; `web-tests/momentum.test.js:218`
- [x] **P3.4** Les tests API couvrent action, indice et les quatre erreurs — `tests/test_momentum_backtest_api.py:46` à `:145`
- [x] **P4.1** Une réponse tardive ne remplace pas une réponse plus récente — `src/obole/web/momentum.js:215`, `:226`, `:229`, `:238` ; `web-tests/momentum.test.js:353`
- [x] **P4.2** Huit lignes, deux colonnes, `—` pour les mesures absentes — `src/obole/web/momentum.js:257` ; `web-tests/momentum.test.js:269` et `:294`
- [x] **P4.3** La carte annonce la série et la durée de la fenêtre — `src/obole/web/momentum.js:303` et `:317` ; `src/obole/web/index.html:823` ; `web-tests/momentum.test.js:314`
- [x] **P4.4** Le chargement et l'erreur sont visibles ; le tableau reste masqué sans données — `src/obole/web/index.html:826` et `:827`, masquage `:829` ; `src/obole/web/momentum.js:216` ; `web-tests/momentum.test.js:325` et `:342`
- [x] **P5.1** Une fenêtre courte ou un échec affiche un message, jamais un tableau vide — `src/obole/web/index.html:827` (erreur) et `:852` (fenêtre courte), tableau en `x-show` sur `momBacktestRows().length` (`:829`)
- [x] **P5.2** Le tableau a un `caption` et des en-têtes `scope="col"` — `src/obole/web/index.html:831` à `:838` (et `scope="row"` en `:842`)
- Unverified at runtime: **P5.3** À 640 px, le tableau défile sans déborder de la carte — `src/obole/web/style.css:1013` à `:1021` et `web-tests/e2e/momentum.spec.js:68` posent le décor ; un run Playwright montrerait si `.mom-table-wrap` reste dans la carte et défile
- Unverified at runtime: **P5.4** Le smoke e2e passe sur Chromium et WebKit — `web-tests/e2e/momentum.spec.js:44` ajoute le cas ; aucun run n'est enregistré près du plan, il montrerait les deux navigateurs
- [ ] **P5.5** `pytest -m "not network"`, `npm test` et `npm run test:e2e` verts — la suite e2e n'est pas verte sur cette tête (2 échecs rapportés, dont `web-tests/e2e/sections.spec.js:835`), et aucun run n'est enregistré près du plan pour prouver qu'ils sont identiques à la base

### Findings

- `src/obole/web/momentum.js:320` : pour un indice personnalisé la légende affirme « brute, dividendes non comptés » alors que la série d'un indice est chaînée en total-return (`momentum_payload(..., adjusted=None, ...)`, `src/obole/services/serialize.py:382`) et que `momSeries` y reste forcément `"raw"` (`momHasAdj()` faux, radio ajusté désactivé) → la base de calcul annoncée est fausse. Fix : brancher la légende sur `kind_payload === "basket"` (« indice total-return, dividendes réinvestis ») au lieu de `momSeries`. — 🟢 minor, fit
- `src/obole/engine/momentum_backtest.py:95` : le moteur ajoute `equity` par colonne et `positions` à une réponse que le plan borne à `{buy_hold, strategy, window}` (phase-2 §1.4 et §2.4), et les deux routes les renvoient telles quelles (`src/obole/api/app.py:227` et `:239`) alors qu'aucun client ne les lit (seuls les tests du moteur s'en servent) : ~3N valeurs JSON de plus par requête (~300 Ko sur une fenêtre MAX) ; même famille que `risk_free_pct` exposé par `/api/meta` (`src/obole/api/app.py:773`) et lu par personne. Fix : ne sérialiser que les huit mesures et `window` dans la route, garder `equity`/`positions` internes au moteur. — 🟢 minor, fit
- `src/obole/web/momentum.js:216` : `loadMomentumBacktest()` ne vide pas `momBacktest` quand la référence change ; `src/obole/web/search.js:80` remet `data` à `null` mais la carte garde les chiffres du ticker précédent pendant la requête, le message « Calcul du backtest… » s'affichant à côté de l'ancien tableau. Fix : mémoriser la référence du payload et remettre `momBacktest = null` quand `_momBacktestRef()` change (ou masquer les lignes tant que `momBacktestLoading`). — 🟢 minor, frontend
- `src/obole/api/app.py:208` : le commentaire affirme « Les dates ISO sont validées ICI (pas par le service) » alors que `src/obole/services/momentum.py:119` à `:127` les revalide — et doit le faire, le service étant appelable seul ; le commentaire ment et la règle est écrite deux fois. Fix : corriger le commentaire (validation en double, assumée) ou faire porter la validation par le seul service. — 🟢 minor, code-health
- `src/obole/web/momentum.js:295` : la table `nulls` (`{ sharpe: "sharpe", … }`) est une identité sans usage, et `return rows;` est collé à l'accolade de fermeture de la boucle (`:299`, `}    return rows;`) — aucun formateur JS ne le rattrape dans ce dépôt. Fix : itérer directement sur `Object.entries(hints)` et remettre `return rows;` sur sa propre ligne. — 🟢 minor, code-health

## Round 2 · r-a91f

- Date: 2026-10-29
- By: Beccariavf
- Diff: `feat/clara-vallis...feat/clara-vallis-fiabilite`
- Axes: code, functional, relevancy
- Verdict: approve
- Score: 22/22 met, 0 unmet, 0 unverified at runtime, 0 out of the diff

### Criteria

- [x] **P1.1** L'échelle affiche « satisfaite » et « frustrée », plus « gaz » ni « liquide » — `src/obole/web/index.html:781` (le vocabulaire de Darcet ne survit que dans deux commentaires, `src/obole/web/momentum.js:335` et `:350`)
- [x] **P1.2** `momRange()` et `momPreset("ref")` lisent la même référence — `src/obole/web/momentum.js:86` (`_momReferenceStart`), consommée en `:104` et `:440`
- [x] **P1.3** Le chip « Réf. » est le premier de la barre et laisse le défaut à 10 ans — `src/obole/web/index.html:795` avant `:797` ; défaut `src/obole/web/momentum.js:461`
- [x] **P1.4** Avec une référence persistée, le preset place la plage sur cette date — `src/obole/web/momentum.js:440` ; `web-tests/momentum.test.js:111`
- [x] **P2.1** Au-dessus de 0,60 la stratégie est investie, sous 0,35 elle est en cash — `src/obole/engine/momentum_backtest.py:156` et `:158` ; `tests/test_momentum_backtest.py:62`
- [x] **P2.2** Entre les deux bornes, l'état précédent est conservé (aucun trade) — `src/obole/engine/momentum_backtest.py:156` à `:158` (aucune branche ne se déclenche entre les bornes) ; `tests/test_momentum_backtest.py:45`
- [x] **P2.3** Les huit mesures sont présentes pour les deux colonnes — `src/obole/engine/momentum_backtest.py:86` ; `tests/test_momentum_backtest.py:113`
- [x] **P2.4** Décaler les scores d'un jour décale les trades, jamais l'inverse — `src/obole/engine/momentum_backtest.py:153` (`aligned[t - 1]`) ; `tests/test_momentum_backtest.py:73`
- [x] **P2.5** Un aller-retour coûte environ 0,2 % et un score toujours neutre ne trade pas — `src/obole/engine/momentum_backtest.py:161` ; `tests/test_momentum_backtest.py:93` et `:127`
- [x] **P3.1** Le service renvoie les deux jeux de mesures et la fenêtre tranchée — `src/obole/services/momentum.py:103` (`_MEASURES`), `:124` (`_public_result`) et `:175` ; `tests/test_momentum_backtest_api.py:54` verrouille l'égalité des clés, pas seulement l'inclusion
- [x] **P3.2** Les trois cas invalides répondent 422, un ticker inconnu répond 404 — `src/obole/api/app.py:205` (validation) et `:230` (404) ; `tests/test_momentum_backtest_api.py:121` à `:146`
- [x] **P3.3** `api.momentumBacktest` construit l'URL avec les quatre paramètres encodés — `src/obole/web/api.js:75` ; `web-tests/momentum.test.js:217`
- [x] **P3.4** Les tests API couvrent action, indice et les quatre erreurs — `tests/test_momentum_backtest_api.py:53` à `:146`
- [x] **P4.1** Une réponse tardive ne remplace pas une réponse plus récente — `src/obole/web/momentum.js:225`, `:236`, `:239`, `:248` (le jeton survit à la remise à zéro de `:208`) ; `web-tests/momentum.test.js:384`
- [x] **P4.2** Huit lignes, deux colonnes, `—` pour les mesures absentes — `src/obole/web/momentum.js:259` ; `web-tests/momentum.test.js:268` et `:293`
- [x] **P4.3** La carte annonce la série et la durée de la fenêtre — `src/obole/web/momentum.js:313` et `:328` ; `src/obole/web/index.html:823` ; `web-tests/momentum.test.js:313` et `:324`
- [x] **P4.4** Le chargement et l'erreur sont visibles ; le tableau reste masqué sans données — `src/obole/web/index.html:827` et `:828`, masquage `:830` (renforcé : `&& !momBacktestLoading`) ; `src/obole/web/momentum.js:226` ; `web-tests/momentum.test.js:335`, `:352` et `:374`
- [x] **P5.1** Une fenêtre courte ou un échec affiche un message, jamais un tableau vide — `src/obole/web/index.html:828` (erreur) et `:853` (fenêtre courte), tableau en `x-show` sur `momBacktestRows().length` (`:830`)
- [x] **P5.2** Le tableau a un `caption` et des en-têtes `scope="col"` — `src/obole/web/index.html:832` à `:839` (et `scope="row"` en `:845`)
- [x] **P5.3** À 640 px, le tableau défile sans déborder de la carte — `src/obole/web/style.css:1014` à `:1022`, cas `web-tests/e2e/momentum.spec.js:68` ; run enregistré : `run.md` §Preuves P5.3, passé sur Chromium et WebKit
- [x] **P5.4** Le smoke e2e passe sur Chromium et WebKit — `web-tests/e2e/momentum.spec.js:6` à `:86` (cinq cas) ; run enregistré : `run.md` §Preuves P5.4
- [x] **P5.5** `pytest -m "not network"`, `npm test` et `npm run test:e2e` verts — run enregistré : `run.md` commandes 1 (back-end hors réseau), 3 (vitest) et 4 (e2e, exit 0) ; cohérent avec le diff : +2 cas vitest, aucune route ni test Python ajouté, et les deux échecs e2e du round 1 ont disparu du décompte (176 + 2 = 178 passés)

### Findings

- `web-tests/momentum.test.js:380` : deux assertions sur la même ligne (`expect(comp.momBacktestLoading).toBe(false);    expect(comp.momBacktestRows()).toEqual([]);`) — le correctif du round 1 a retiré le `return` collé de `momentum.js` mais a déplacé le même défaut ici ; aucun formateur JS ne le rattrape. Fix : remettre la seconde assertion sur sa propre ligne. — 🟢 minor, code-health
