# Review: Lecture du score Momentum — percentile et rendement conditionnel

- Rounds: 2
- Started: 2026-10-30

## Round 1 · r-4b7d

- Date: 2026-10-30
- By: Beccariavf
- Diff: `main...HEAD`
- Axes: code, functional, relevancy
- Verdict: changes-requested
- Score: 4/10 met, 0 unmet, 6 unverified at runtime, 0 out of the diff

### Criteria

- [x] P1·1 — un score égal au maximum rend 100, un score inférieur au minimum rend 0, moins de 60 points rend `None` — `tests/test_momentum_stats.py:29-45`
- [x] P1·2 — le payload d'une action porte `percentile_raw`, `percentile_adj`, `history_start` ; celui d'un indice porte `percentile_adj` à `None` — `tests/test_momentum_service.py:132-171`, chemin indice rejoué sur `momentum_payload(..., None, ...)`
- Unverified at runtime: P1·3 — changer la bascule brut/ajusté change le rang affiché — l'accesseur est couvert (`web-tests/momentum.test.js:535-546`), l'affichage lui-même n'est pas rejoué
- Unverified at runtime: P1·4 — la ligne apparaît sous la jauge quand le rang existe et disparaît quand il manque — balisage `src/obole/web/index.html:783-787`, e2e non rejoué
- Unverified at runtime: P1·5 — les trois suites passent sans réseau — backend et front verts dans cette relecture, e2e non rejoué
- [x] P2·1 — une série à rendement constant place la même médiane dans les trois zones, et des scores hauts suivis de hausse donnent une médiane haute supérieure — `tests/test_momentum_stats.py:94-119`
- [x] P2·2 — le payload d'une action porte `conditional_raw` et `conditional_adj` ; celui d'un indice porte `conditional_adj` à `None` — `tests/test_momentum_service.py:213-251`, chemin indice rejoué
- Unverified at runtime: P2·3 — la ligne de la zone courante est distinguée et suit le score courant — `web-tests/momentum.test.js:628-649`, e2e non rejoué
- Unverified at runtime: P2·4 — la carte est entre la jauge et le graphe et disparaît sans fenêtre complète — ordre statique vérifié dans `src/obole/web/index.html:789-822`, disparition = runtime
- Unverified at runtime: P2·5 — les suites backend, front et e2e passent sans réseau — backend et front verts ici, e2e non rejoué

### Findings

- `src/obole/engine/momentum_stats.py:33-34` : la docstring affirme que le minimum « garde son rang 1/n … et non 0 » ; à n ≥ 200 le rang rendu vaut 0 (mesuré : 199 points → 1, 200 → 0, 600 → 0, 4750 → 0), donc « égal au minimum » et « strictement sous le minimum » deviennent indiscernables, et `test_minimum_keeps_its_one_over_n_rank` ne l'atteste que pour n ≤ 60 → soit plancher `max(1, round(rank))` quand `value >= sample.min()` (le 0 restant réservé au « sous tout l'historique »), soit réécrire la docstring et le commentaire du test pour énoncer le plancher réel ; trancher explicitement, la formulation actuelle a déjà induit une relecture en erreur — 🟡 major, code-health
- `src/obole/engine/momentum_stats.py:91` : la docstring promet d'ignorer les fenêtres à « trou dans la série » ; `clean = prices.dropna()` (`:110`) supprime le trou et la fenêtre est conservée en pontant l'horizon (mesuré : p90 9,49 % avec un trou de 5 séances contre 4,96 % sans) → soit écarter les fenêtres dont l'index n'est pas continu sur `horizon` séances, soit reformuler en « un trou interne est ponté, la série est nettoyée en amont » — 🟢 minor, code-health
- `src/obole/web/momentum.js:464` : « depuis \<année\> » vient de `history_start`, calculé sur la série BRUTE (`src/obole/services/momentum.py:127`), alors que le rang affiché peut être `percentile_adj`, calculé sur une série ajustée plus courte (mesuré : série ajustée démarrant 400 séances plus tard → « depuis 2005 » pour un rang ajusté qui ne commence qu'en 2007) → n'afficher « depuis » que si `momUsesAdj()` est faux, ou porter un `history_start_adj` dans le payload — 🟢 minor, frontend
- `src/obole/services/momentum.py:46` : la docstring érige en règle « changer le suffixe à chaque nouveau champ du bloc », or la phase 2 a ajouté `conditional_raw`/`conditional_adj` sous le même `:lecture` — sans conséquence ici (aucune entrée `momentum:*:lecture` antérieure à la phase 2 dans `cache.sqlite`, et le front masque ligne et carte sur un payload ancien) → reformuler la règle (« le suffixe date le bloc de lecture ; à incrémenter au prochain champ ajouté ») — 🟢 minor, standards
- `tests/test_momentum_stats.py:181-188` : les bornes ne sont testées que du côté bas (0,35 → neutre) ; le côté haut (0,60 → neutre, au-delà → haut) n'est pas couvert alors qu'il porte la moitié de la règle « mêmes bornes strictes que la jauge » → ajouter les deux cas, côté moteur et côté `momState` — 🟢 minor, backend
- `aidd_docs/tasks/2026_10/2026_10_30_momentum-lecture/phase-2.md:14` : la projection d'architecture n'inscrit que `MOMENTUM_FORWARD_SESSIONS`, alors que `src/obole/config.py:171` ajoute `MOMENTUM_CONDITIONAL_MIN_EPISODES` et que le `thin` qui en dépend est exigé par le Test Scope → compléter la projection et la tâche 2 pour que le lecteur retrouve l'origine du champ — 🟢 minor, fit

## Round 2 · r-e1a4

- Date: 2026-10-30
- By: Beccariavf
- Diff: `main...HEAD`, delta du round `400c8b5..8610e76`
- Axes: code, functional, relevancy
- Verdict: approve
- Score: 4/10 met, 0 unmet, 6 unverified at runtime, 0 out of the diff

### Criteria

- [x] P1·1 — un score égal au maximum rend 100, un score inférieur au minimum rend 0, moins de 60 points rend `None` — `tests/test_momentum_stats.py:22-48`
- [x] P1·2 — le payload d'une action porte `percentile_raw`, `percentile_adj`, `history_start` ; celui d'un indice porte `percentile_adj` à `None` — `tests/test_momentum_service.py:132-175`, chemin indice rejoué sur `momentum_payload(..., None, ...)`
- Unverified at runtime: P1·3 — changer la bascule brut/ajusté change le rang affiché — l'accesseur et le libellé sont couverts (`web-tests/momentum.test.js:535-570`), l'affichage lui-même n'est pas rejoué
- Unverified at runtime: P1·4 — la ligne apparaît sous la jauge quand le rang existe et disparaît quand il manque — balisage `src/obole/web/index.html:783-787`, e2e non rejoué
- Unverified at runtime: P1·5 — les trois suites passent sans réseau — backend et front verts dans cette relecture (: 1364 passed, 1 skipped ; 730 vitest), e2e non rejoué
- [x] P2·1 — une série à rendement constant place la même médiane dans les trois zones, et des scores hauts suivis de hausse donnent une médiane haute supérieure — `tests/test_momentum_stats.py:107-134`
- [x] P2·2 — le payload d'une action porte `conditional_raw` et `conditional_adj` ; celui d'un indice porte `conditional_adj` à `None` — `tests/test_momentum_service.py:216-281`, chemin indice rejoué
- Unverified at runtime: P2·3 — la ligne de la zone courante est distinguée et suit le score courant — `web-tests/momentum.test.js:651-673`, e2e non rejoué
- Unverified at runtime: P2·4 — la carte est entre la jauge et le graphe et disparaît sans fenêtre complète — ordre statique vérifié dans `src/obole/web/index.html:789-822`, disparition = runtime
- Unverified at runtime: P2·5 — les suites backend, front et e2e passent sans réseau — idem P1·5

### Findings

- `src/obole/services/momentum.py:46-47` : la docstring se donne pour règle qu'« un champ ajouté ou retiré » change le suffixe de cache, alors que ce commit même ajoute `history_start_adj` (`:133`) sans bumper `_cache_kind()` (`:50`) → soit incrémenter le suffixe (`:lecture2`, plus la ligne de `tests/test_momentum_service.py:123`), soit écrire la règle réellement appliquée ; la conséquence d'affichage est acceptée en l'état (payload resté en cache : rang ajusté sans année, ≤ 24 h, jamais une année fausse) — 🟢 minor, standards
- `aidd_docs/tasks/2026_10/2026_10_30_momentum-lecture/phase-1.md:18` : la projection et la tâche 2.3 (`:92`) ne connaissent que `history_start`, alors que le payload porte désormais aussi `history_start_adj` (`src/obole/services/momentum.py:133`) → ajouter la clé aux deux, comme la phase 2 l'a fait pour `thin` — 🟢 minor, fit
