# Run — #32 Fiabilité, seconde lecture : in contre out

- **Date :** 2026-10-29
- **Branche :** `feat/momentum-in-out` (partie de `main`, aucun push, aucun merge)
- **Plan :** `aidd_docs/tasks/2026_10/2026_10_29_momentum-in-out/plan.md`

Aucun SHA n'est consigné ici (règle `CLAUDE.md` §Workflow git) : les jalons sont décrits,
les commits sont identifiés par leur sujet.

## Découpage des commits

Le plan découpe le travail en quatre phases (ordre d'implémentation), mais **un commit ne
peut pas laisser l'application cassée**. Trois frontières du plan l'auraient fait :

- moteur seul, sans le transport → le service lit `result["strategy"]`, que le moteur ne
  rend plus : **tout 200 lève** (`KeyError`) et 3 tests API échouent ;
- transport seul, sans la carte → le front lit `b.strategy`, que la route ne rend plus :
  **le tableau est vide** et le smoke e2e échoue ;
- carte seule, sans son smoke → l'e2e vérifie encore l'ancien contrat et échoue.

Les phases 1 à 3 voyagent donc dans **un seul commit vert** (moteur, transport, lecture et
sa preuve e2e) ; la phase 4 (documentation) suit séparément, puis la clôture du plan.
Chaque commit de la branche passe la porte complète — vérifié ci-dessous, commit par commit.

## Commandes et résultats exacts (tête finale)

| Commande | Résultat |
| --- | --- |
| `.venv/bin/python -m pytest -m "not network" -p no:cov -p no:flask -p no:mock -q` | `1333 passed, 1 skipped, 5 deselected, 1 warning in 15.39s` |
| `.venv/bin/python -m pytest tests/test_calibration_network.py -p no:cov -q` | `5 passed in 0.87s` (réseau, fin de chantier) |
| `cd web-tests && npm test` | `Test Files 29 passed (29)` · `Tests 716 passed (716)` |
| `cd web-tests && npm run test:e2e` | `180 passed (3.3m)` — Chromium **et** WebKit |
| `.venv/bin/ruff check .` | `All checks passed!` |
| `.venv/bin/ruff format --check .` | `130 files already formatted` |
| `.venv/bin/mypy src/obole/engine src/obole/services src/obole/mcp src/obole/models.py` | `Found 5 errors in 1 file (checked 43 source files)` — **pré-existant**, voir ci-dessous |

### État mypy (pré-existant, hors périmètre)

Les 5 erreurs sont toutes dans `src/obole/services/serialize.py` (`:886` et suivantes,
assignation `dict` → `str | float | None`) et **existent à l'identique sur le point de
départ de la branche** : la commande a été rejouée sur l'arbre remisé, mêmes 5 erreurs,
même fichier. Aucun fichier touché par ce chantier n'ajoute d'erreur de type.

## Vérification commit par commit

Chaque commit a été validé sur son propre arbre (pas seulement la tête). La suite e2e
complète (~3,3 min) a été jouée sur le commit de code ; les deux commits suivants ne
touchent que de la documentation (aucun fichier servi par le serveur, aucun test de
navigateur concerné) et passent la porte backend + front.

| Commit (sujet) | `ruff` | `pytest` | `npm test` | `npm run test:e2e` |
| --- | --- | --- | --- | --- |
| `feat(momentum): mesurer le marché pendant les séances in et out` | ✅ | `1333 passed, 1 skipped, 5 deselected` | `716 passed` | `180 passed` |
| `docs(momentum): documenter la lecture in/out et la convention de out` | ✅ | `1333 passed, 1 skipped, 5 deselected` | `716 passed` | inchangé (docs seules) |
| `chore(momentum): clore le plan #32 et enregistrer le run` | ✅ | `1333 passed, 1 skipped, 5 deselected` | `716 passed` | inchangé (docs seules) |

Aucun commit de la branche n'a de suite rouge. La suite e2e complète a en outre été
**rejouée sur la tête finale**, après la clôture du plan : `180 passed (3.3m)`.

## Points corrigés en revue (round 1)

1. **Commit rouge de phase 1** — supprimé : moteur, transport et carte sont dans le même
   commit vert (voir §Découpage), et chaque commit restant est vérifié sur la porte
   complète.
2. **Commentaire de `momCellClass`** — il attribuait le `good` au serveur : il vient de
   `_momBacktestGood`, appelé par `momBacktestRows()`.
3. **`invested_pct` → `sessions_pct`** — dans le moteur (`_block`, `_empty_block`), la
   liste `_MEASURES` du service, le front (champ de ligne et clé de ligne) et les trois
   suites de tests. La docstring de `_block` dit maintenant que la valeur est la part des
   séances de CETTE colonne (donc la part HORS marché pour `out`).
4. **Couleur et arrondi** — la polarité se décide sur la valeur **affichée** (`_momShown`,
   deux décimales, arrondi demi vers l'extérieur comme `Intl`) : 0,0004 % s'écrit
   « 0,00 % » et reste neutre, tandis que −0,005 s'écrit « -0,01 % » et se colore. Tests
   unitaires ajoutés (positif et négatif négligeables, 0,006 % → « 0,01 % » coloré,
   frontière −0,005 → « -0,01 % » rouge).
5. **Deux phrases du plan** — `phase-2.md` dit « six top-level keys » (le contrat en a
   six) et `phase-3.md` « `—` sur ses six mesures et 0,00 % de part des séances » (la part
   vaut zéro, elle n'est pas absente).
6. **Panier d'une séance** — `_cagr_pct` exige `sessions >= 2`, comme Sharpe, Sortino et la
   volatilité : plus de `** 252` extrapolé ni de Calmar coloré sur un seul rendement. Test
   unitaire ajouté (panier in d'une séance, et buy & hold à deux cours).

## Contrôles manuels

- **Contrat de la route** (RI.PA, `2015-01-02` → `2025-10-24`, `series=adj`) : six clés
  exactement — `buy_hold`, `in`, `out` (7 mesures chacun), `window`
  (`start`/`end`/`sessions`), `trades` (27), `strategy_cagr_pct` (−0,1739). Aucune
  occurrence de `equity`, `positions` ni d'un bloc `strategy`.
- **Rendu** (Chromium 1280 px, `#RI.PA/momentum`) : trois colonnes et sept lignes, pied
  `59 trades · stratégie -1,22 %/an`, légende « … le drawdown des paniers est
  conditionnel. ». Sur la fenêtre de référence, `out` positif (8,49 %) est **rouge**, `in`
  négatif (−1,16 %) est **rouge** aussi (polarité standard), volatilité, max drawdown et
  part des séances restent neutres.
- La modification d'`index.html` impose de redémarrer le serveur local (HTML en cache)
  avant tout test navigateur — fait avant les contrôles ci-dessus.

## Lecture obtenue sur RI.PA

| Fenêtre | CAGR buy & hold | CAGR `in` | CAGR `out` | Part `in` / `out` | Trades | Stratégie |
| --- | --- | --- | --- | --- | --- | --- |
| 10 ans par défaut (brut) | −4,67 % | −2,51 % | −7,13 % | 53,85 % / 46,15 % | 23 | −1,79 %/an |
| Réf. ≈ 23,5 ans (brut) | 2,28 % | −1,16 % | 8,49 % | 63,33 % / 36,67 % | 59 | −1,22 %/an |

Sur 10 ans le signal sépare bien (`out` négatif, donc bleu) ; sur l'historique complet il
s'inverse (`out` positif à 8,49 %, donc rouge) : les meilleures séances de RI.PA sont
justement celles où la stratégie est dehors.
