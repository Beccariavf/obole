# Review: Fiabilité, seconde lecture — in contre out

- Rounds: 2
- Started: 2026-10-29

## Round 1 · r-4b17

- Date: 2026-10-29
- By: Beccariavf
- Diff: `main...feat/momentum-in-out`
- Axes: code, functional, relevancy
- Verdict: changes-requested
- Score: 17/17 met, 0 unmet, 0 unverified at runtime, 0 out of the diff

### Criteria

- [x] **P1.1** In et out partitionnent les séances de rendement, sans trou ni doublon — `src/obole/engine/momentum_backtest.py:201-208` (chaque `t` de 1 à n−1 alimente exactement une courbe) et `:210-216` (`out_pct = 100 − in_pct`) ; `tests/test_momentum_backtest.py:171`
- [x] **P1.2** La courbe in ne contient que les rendements des séances in — `src/obole/engine/momentum_backtest.py:205-208` ; `tests/test_momentum_backtest.py:190` (recompose les deux courbes depuis `positions`)
- [x] **P1.3** Le CAGR d'un panier est annualisé sur ses propres séances — `src/obole/engine/momentum_backtest.py:71-82` (`_TRADING_DAYS / sessions`), appelé avec `n_in`/`n_out` en `:219-220` ; `tests/test_momentum_backtest.py:204` (1,001^252, pas le calendrier)
- [x] **P1.4** `trades` et `strategy_cagr_pct` sortent une fois, en premier niveau — `src/obole/engine/momentum_backtest.py:226-227` ; `src/obole/services/momentum.py:124-136` ; `tests/test_momentum_backtest.py:116`
- [x] **P1.5** Un panier vide donne des mesures nulles et une part de 0 %, sans crash — `src/obole/engine/momentum_backtest.py:130-141` et `:219-220` ; `tests/test_momentum_backtest.py:222` ; `tests/test_momentum_backtest_api.py:145`
- [x] **P2.1** La réponse porte exactement six clés de premier niveau — `src/obole/services/momentum.py:124-136`, mesures bornées par `_MEASURES` en `:104-113` ; `tests/test_momentum_backtest_api.py:28` et `:57-63` (`set(data) == TOP_LEVEL`)
- [x] **P2.2** Les trois colonnes portent les sept mêmes mesures — `src/obole/services/momentum.py:104-113` et `:133-135` ; `tests/test_momentum_backtest_api.py:64-65` (égalité de `set(...)`, pas inclusion)
- [x] **P2.3** Les paramètres et les erreurs de la route sont inchangés — `src/obole/api/app.py:224-252` : le diff ne touche que les docstrings, `_validate_backtest_window` et les 404/422 sont intacts ; `tests/test_momentum_backtest_api.py:166-191`
- [x] **P2.4** Un panier vide renvoie des mesures nulles, jamais une erreur — `src/obole/engine/momentum_backtest.py:219-220` ; `tests/test_momentum_backtest_api.py:145-163` (200, `out` nul, part 0 %)
- [x] **P3.1** Sept lignes, trois cellules, libellés français — `src/obole/web/momentum.js:290-316` (sept `specs`) et `:317-328` (trois colonnes, un `good` par cellule) ; `src/obole/web/index.html:837-851` ; `web-tests/momentum.test.js:281`
- [x] **P3.2** Un CAGR positif en out est coloré rouge ; le même en in est bleu — `src/obole/web/momentum.js:268-271` et `:325` ; `src/obole/web/style.css:1013-1014` (`bad` = `--bad` #DC2626, `good` = `--accent` #2563EB) ; `web-tests/momentum.test.js:306` ; run enregistré pour les classes : `run.md:79-80`
- [x] **P3.3** Le pied affiche les trades, le CAGR de la stratégie et la légende (drawdown conditionnel) — `src/obole/web/momentum.js:344-371` ; `src/obole/web/index.html:855-857` ; `web-tests/momentum.test.js:366`
- [x] **P3.4** À 640 px, le tableau défile sans déborder de la carte — `src/obole/web/style.css:1028-1036` ; `web-tests/e2e/momentum.spec.js:128-144` ; run enregistré : `run.md:60` (2 passed, Chromium + WebKit) et `run.md:80`
- [x] **P4.1** Le smoke e2e voit trois colonnes et le pied des trades, sur Chromium et WebKit — `web-tests/e2e/momentum.spec.js:44-84` ; run enregistré : `run.md:80` (180 passed, deux projets Playwright)
- [x] **P4.2** Un `out` positif est rouge, un `in` positif est bleu (classes vérifiées) — `web-tests/e2e/momentum.spec.js:86-126` ; run enregistré : `run.md:79-80`
- [x] **P4.3** Le `caption` et les `scope` sont présents ; l'information ne dépend pas de la couleur — `src/obole/web/index.html:832-841` (`caption` + quatre `scope="col"`) et `:855-857` (le pied nomme les trades en clair) ; `web-tests/e2e/momentum.spec.js:66-83`
- [x] **P4.4** Le PRD ne parle plus de la comparaison stratégie/buy & hold — `PRD.md:360-377` (§5.12 lit le marché pendant les séances in et out, buy & hold en repère de période ; plus aucune occurrence de la comparaison)

### Findings

- `aidd_docs/tasks/2026_10/2026_10_29_momentum-in-out/run.md:36` : le commit de phase 1 (`feat(momentum): mesurer le marché pendant les séances in et out`) est rouge. Le moteur y supprime déjà `strategy` (et `trades` des blocs) alors que `services/momentum.py` lit encore `result["strategy"]` et garde `trades` dans `_MEASURES` (`src/obole/services/momentum.py:111` à cet état) : toute réponse 200 du backtest lève `KeyError`, les trois tests de `tests/test_momentum_backtest_api.py` qui lisent une réponse 200 échouent, et le front de l'époque (`data.strategy`) casse l'e2e. Le run ne l'a pas vu parce que la phase 1 n'a lancé que son propre fichier de test (`run.md:36`), et l'écart n'est consigné nulle part (le corps du commit décrit même un état que ce commit n'a pas). Or `aidd_docs/memory/vcs.md:41` interdit qu'un commit rouge parte sur `main` et le merge est `--no-ff` : il y arriverait tel quel, avec un point d'historique où les deux routes du backtest répondent 500. Le correctif vaut le coup : la branche n'est pas poussée et aucun document ne cite de SHA, donc replier le commit de phase 1 dans celui de phase 2 (`git rebase -i`, moteur et transport ne portant qu'un seul changement de contrat), et lancer la suite complète à chaque phase plutôt que le seul fichier de la phase. — 🟡 major, conform
- `src/obole/web/momentum.js:274` : le commentaire affirme que « le `good` du serveur pilote la couleur » alors qu'aucun `good` n'est transporté (le service ne livre que les sept nombres, `src/obole/services/momentum.py:104-113`) : c'est `_momBacktestGood` (`:268`) qui le calcule ici, et le CSS ne fait que rendre la classe. Fix : dire que la polarité est calculée par `_momBacktestGood` et que `momCellClass` n'en rend que la classe. — 🟢 minor, code-health
- `src/obole/engine/momentum_backtest.py:125` : `invested_pct` porte la « part des séances » des trois colonnes, mais vaut sur `out` la part des séances HORS marché (36 % sur la fenêtre de référence, `run.md:94`) : la clé dit le contraire de ce qu'elle mesure, dans la table même dont l'objet est de ne pas mentir sur ce qu'elle mesure. Fix : renommer `sessions_pct` dans le moteur, `_MEASURES` (`src/obole/services/momentum.py:111`), le front (`src/obole/web/momentum.js:312`) et les tests — le contrat n'a qu'un client. — 🟢 minor, rot
- `src/obole/web/momentum.js:270` : la règle « un zéro est neutre » n'est couverte par aucun test (ni `web-tests/momentum.test.js`, ni l'e2e) et, l'affichage arrondissant à deux décimales (`:258-262`), un CAGR de 0,0004 s'affiche « 0,00 % » tout en portant la classe `good`/`bad` : neutre à la lecture, coloré à l'écran. Fix : ajouter un cas `good === null` pour `0` (et `-0`) et décider la couleur sur la valeur arrondie affichée. — 🟢 minor, frontend
- `aidd_docs/tasks/2026_10/2026_10_29_momentum-in-out/phase-2.md:37` : le Test Scope dit « exactly the five top-level keys » et le test le répète (`tests/test_momentum_backtest_api.py:57`, `test_200_carries_the_five_payload_entries`) alors que le contrat livré et l'acceptation de la même phase comptent six clés ; `phase-3.md:92` annonce de même « `—` dans ses trois cellules » pour un panier vide, alors que la part des séances vaut 0,00 % (mesuré, `web-tests/momentum.test.js:345`) — deux traces écrites qui contredisent le comportement livré. Fix : corriger les deux phrases (six clés ; six tirets et part à 0 %). — 🟢 minor, rot
- `src/obole/engine/momentum_backtest.py:77` : `sessions <= 0` laisse passer un panier d'UNE séance, dont le CAGR est extrapolé par `** 252` (et le Calmar avec) — +0,1 % sur une séance donne +28,6 %/an, affiché et coloré, alors que Sharpe, Sortino et volatilité rendent déjà `None` sous deux rendements (`src/obole/engine/portfolio.py:599-601`). L'état est atteignable depuis le front, qui n'exige que `i1 - i0 >= 1` (`src/obole/web/momentum.js:224`). L'extrapolation existait déjà sur la durée calendaire, mais le passage à `n/252` ne la traite toujours pas. Fix : exiger deux rendements comme `engine/portfolio` (`sessions < 2 → None`) et le dire dans la docstring. — 🟢 minor, backend

## Round 2 · r-9d2b

- Date: 2026-10-29
- By: Beccariavf
- Diff: `main...feat/momentum-in-out`
- Axes: code, functional, relevancy
- Verdict: approve
- Score: 17/17 met, 0 unmet, 0 unverified at runtime, 0 out of the diff

### Criteria

- [x] **P1.1** In et out partitionnent les séances de rendement, sans trou ni doublon — `src/obole/engine/momentum_backtest.py:210-218` (chaque `t` de 1 à n−1 va dans une seule courbe) et `:220-225` (`out_pct = round(100 − in_pct, 4)`) ; `tests/test_momentum_backtest.py:171`
- [x] **P1.2** La courbe in ne contient que les rendements des séances in — `src/obole/engine/momentum_backtest.py:212-218` ; `tests/test_momentum_backtest.py:190` (recompose les deux courbes depuis `positions`)
- [x] **P1.3** Le CAGR d'un panier est annualisé sur ses propres séances — `src/obole/engine/momentum_backtest.py:71-86` (`_TRADING_DAYS / sessions`, garde `sessions < 2` en `:81`), appelé avec `n_in`/`n_out` en `:228-229` ; `tests/test_momentum_backtest.py:204` et `:222`
- [x] **P1.4** `trades` et `strategy_cagr_pct` sortent une fois, en premier niveau — `src/obole/engine/momentum_backtest.py:235-236` ; `src/obole/services/momentum.py:124-139` ; `tests/test_momentum_backtest.py:116`
- [x] **P1.5** Un panier vide donne des mesures nulles et une part de 0 %, sans crash — `src/obole/engine/momentum_backtest.py:139-150` et `:228-229` ; `tests/test_momentum_backtest.py:238` ; `tests/test_momentum_backtest_api.py:145`
- [x] **P2.1** La réponse porte exactement six clés de premier niveau — `src/obole/services/momentum.py:124-139`, mesures bornées par `_MEASURES` en `:104-113` ; `tests/test_momentum_backtest_api.py:28` et `:57-63` (`set(data) == TOP_LEVEL`)
- [x] **P2.2** Les trois colonnes portent les sept mêmes mesures — `src/obole/services/momentum.py:104-113` et `:133-135` ; `tests/test_momentum_backtest_api.py:64-65` (égalité de `set(...)`, pas inclusion)
- [x] **P2.3** Les paramètres et les erreurs de la route sont inchangés — `src/obole/api/app.py:224-252` : le diff ne touche que les docstrings, `_validate_backtest_window` et les 404/422 sont intacts ; `tests/test_momentum_backtest_api.py:166-191`
- [x] **P2.4** Un panier vide renvoie des mesures nulles, jamais une erreur — `src/obole/engine/momentum_backtest.py:228-229` ; `tests/test_momentum_backtest_api.py:144-163` (200, `out` nul, part 0 %)
- [x] **P3.1** Sept lignes, trois cellules, libellés français — `src/obole/web/momentum.js:303-329` (sept `specs`) et `:330-341` (trois colonnes, un `good` par cellule) ; `src/obole/web/index.html:837-851` ; `web-tests/momentum.test.js:281`
- [x] **P3.2** Un CAGR positif en out est coloré rouge ; le même en in est bleu — `src/obole/web/momentum.js:269-272` (`_momBacktestGood`, inversion sur `out`), `:280-284` (`_momShown`, valeur affichée) et `:338` ; `src/obole/web/style.css:1013-1014` (`bad` = `--bad` #DC2626, `good` = `--accent` #2563EB) ; `web-tests/momentum.test.js:306` ; run enregistré pour les classes : `run.md:53`
- [x] **P3.3** Le pied affiche les trades, le CAGR de la stratégie et la légende (drawdown conditionnel) — `src/obole/web/momentum.js:357-384` ; `src/obole/web/index.html:855-857` ; `web-tests/momentum.test.js:391`
- [x] **P3.4** À 640 px, le tableau défile sans déborder de la carte — `src/obole/web/style.css:1028-1036` ; `web-tests/e2e/momentum.spec.js:128-144` ; run enregistré : `run.md:53` (180 passed, deux projets) et `run.md:58` (rejouée sur la tête finale)
- [x] **P4.1** Le smoke e2e voit trois colonnes et le pied des trades, sur Chromium et WebKit — `web-tests/e2e/momentum.spec.js:44-84` ; run enregistré : `run.md:53` (180 passed = 90 cas × 2 projets)
- [x] **P4.2** Un `out` positif est rouge, un `in` positif est bleu (classes vérifiées) — `web-tests/e2e/momentum.spec.js:86-126` ; run enregistré : `run.md:53`
- [x] **P4.3** Le `caption` et les `scope` sont présents ; l'information ne dépend pas de la couleur — `src/obole/web/index.html:832-841` (`caption` + quatre `scope="col"`) et `:855-857` (le pied nomme les trades en clair) ; `web-tests/e2e/momentum.spec.js:66-83`
- [x] **P4.4** Le PRD ne parle plus de la comparaison stratégie/buy & hold — `PRD.md:360-377` (§5.12 lit le marché pendant les séances in et out, buy & hold en repère de période ; plus aucune occurrence de la comparaison)

### Findings

- `aidd_docs/tasks/2026_10/2026_10_29_momentum-in-out/run.md:46-58` : la section « commit par commit » conclut « Chaque commit de la branche passe la porte complète » et « Aucun commit de la branche n'a de suite rouge », mais sa table ne montre que les trois commits qui suivent la spécification : `git log main..HEAD` en compte quatre, le commit de spécification (docs seules, qui crée la fiche et le plan) n'y figure ni comme ligne ni comme exclusion. Il est vert par construction — rien dans la suite ne lit le dossier de tâche — mais la vérification est exhaustive en fait, pas dans ce qu'elle montre. Fix : ajouter sa ligne (« docs seules, suite identique au point de départ ») ou écrire « les trois commits qui suivent la spécification ». — 🟢 minor, rot
- `src/obole/web/momentum.js:280-284` : `_momShown` rejoue à la main l'arrondi à deux décimales que `_momNum` (`:258-262`) confie à `Intl` : deux arrondis pour un même chiffre, dont l'un décide la couleur. Ils s'accordent aujourd'hui (vérifié sur 0,0004 ; 0,006 ; −0,005, et le voisinage de zéro où le signe peut basculer), mais changer la précision ou la locale de `_momNum` ferait décrocher la couleur sans rien casser de visible. Fix : calculer la valeur affichée une seule fois (`_momShown`) et formater à partir d'elle (`_momNum(shown)`), ou dériver `good` de la chaîne affichée. — 🟢 minor, rot
