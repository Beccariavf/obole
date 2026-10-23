# #14 — Score composite du screener (classement par compromis)

> **Statut :** fait · **Priorité :** 🔵 Q3 · **Impact Pernod :** 🟠
> **Branche (mergée) :** `feat/screener-score` · **Taille :** 1 session
> **Fiche parente :** `chantiers/13-screener-ux.md` (l'UX du screener ; ici, le classement)

---

## 1. Contexte

Le screener permet de cliquer **2 en-têtes** pour un tri chaîné (`toggleSortHeader`, plafonné à
2 critères). Mais `engine/screen.py::_apply_sort` applique un tri **lexicographique** : le 2ᵉ
critère ne départage que les **égalités strictes** du 1ᵉʳ.

Preuve (5 valeurs, `sort_by=[ROE desc, P/FCF asc]`) :

| ticker | ROE | P/FCF | rang obtenu |
|---|---|---|---|
| A | 20 | 20 | 1ᵉʳ |
| B | 19 | 5 | 2ᵉ |
| C | 18 | 3 | 3ᵉ |

Aucune égalité de ROE → le P/FCF n'est **jamais** consulté. D'où le constat utilisateur : « j'ai
l'impression que le deuxième ne fait pas effet ». C'est intrinsèque au tri en cascade sur des
valeurs continues.

Ce que l'utilisateur veut — « celle qui a le meilleur **ROE/P-FCF** » — n'est pas une cascade
mais un **score composite** : un classement par compromis où tous les critères agissent
simultanément.

## 2. Objectif

Offrir un classement qui remonte les valeurs bonnes sur **l'ensemble** des critères choisis, et
non celles qui écrasent un seul critère. Sur « ROE % ▼ + P/FCF ▲ », le 1ᵉʳ résultat doit être
une valeur à la fois rentable **et** bon marché.

## 3. Non-objectifs

- Pas de pondération réglable par sliders (écarté au cadrage : option 2b).
- Pas de ratio explicite ROE/P-FCF (écarté : option 3, cas particulier du score).
- Pas de persistance du score ni de recalcul côté client (il dépend du jeu filtré).
- Pas de filtre sur le score (ce n'est pas une donnée de marché).
- Le tri en cascade n'est **pas** supprimé : il reste disponible (bascule).

## 4. Exigences

- 4.1 `engine/screen.py::composite_score(screens, keys)` : **pur**, percentile 0-100 par
  critère (100 = meilleur), moyenne à poids égaux.
- 4.2 Le sens de chaque critère vient de `SCREEN_SORT_DESC` (source unique) — aucun seuil
  nouveau, `SCREEN_COLORS` inchangé.
- 4.3 Renvoie `{}` s'il y a moins de 2 critères exploitables.
- 4.4 Une ligne en `error` ou privée d'un critère actif est **exclue** du score (`score = None`),
  donc renvoyée en fin de liste.
- 4.5 `score` est calculé sur les lignes **filtrées** (avant tri) et posé sur chacune.
- 4.6 `score` est exposé par l'API (`screen_row_to_dict`) et **neutre** (absent de `colors`).
- 4.7 Le front envoie `score_keys` (critères du tri actif) ; en mode « Compromis » (défaut dès
  2 critères) il trie sur `score`, sinon il conserve la cascade.

## 5. Critères d'acceptation

- [x] `composite_score` pur, percentile 0-100, poids égaux
- [x] Sens lu dans `SCREEN_SORT_DESC` ; `SCREEN_COLORS` inchangé
- [x] `{}` si < 2 critères exploitables
- [x] Ligne en `error` ou critère manquant → `score = None`, en fin de liste
- [x] Score calculé sur le jeu filtré, avant tri
- [x] `score` exposé par l'API, neutre (absent de `colors`)
- [x] `score_keys` accepté par `POST /api/screener/run` (clé inconnue ignorée, pas de 422)
- [x] Front : colonne « Score » + bascule Compromis / Cascade
- [x] Tests purs dédiés (`tests/test_screen_score.py`) ; suite hors réseau verte
  (`pytest -m "not network" -q`)
- [x] E2E : 2 critères → score, B (compromis) devant A (1ᵉʳ en ROE) et D (1ᵉʳ en P/FCF)
- [x] En mode Compromis, l'affichage du tri reflète le classement réel (pas la cascade)
- [x] `score` triable mais **non filtrable** (`FILTERABLE_KEYS`, 422 explicite)
- [x] Colonne Score masquée quand elle serait vide (< 2 critères / mode cascade)

## 6. Invariants préservés

- La calibration Pernod (`z = −3.81`, ±0.15) reste verte : `fit_log_regression` intouché.
- Aucun seuil métier nouveau : le score est un **rang relatif**, pas un seuil.
- Le tri en cascade reste disponible (bascule) — aucun comportement supprimé.
- `config.py` inchangé.

## 7. Jalons

- **J1** — Tests TDD du score (16 cas) + `composite_score`.
- **J2** — `score` dans `ScreenResult` / `SORTABLE_KEYS` / API.
- **J3** — Front : `score_keys`, bascule, colonne Score.
- **J4** — E2E + fiche.

## 8. Note de reprise

**Fait** (branche `feat/screener-score`).

Livré :

- `engine/screen.py` : `composite_score()` (pure), `SCORE_KEY`, `score` dans `SORTABLE_KEYS`,
  `filter_and_sort(..., score_keys=)`.
- `models.py` : champ `score` sur `ScreenResult`.
- `api/serialize.py` : `score` exposé (volontairement **hors** `colors`).
- `api/app.py` : `_validate_score_keys()` (clé inconnue ignorée, jamais de 422).
- `web/app.js` : `screenerMode`, `_scoreKeys()`, `screenerScoreActive()`, `setScreenerMode()`,
  colonne Score dans `_screenCols()`, envoi de `score_keys`.
- `web/index.html` + `style.css` : bascule `.screen-mode-toggle`, cellule `.cell-score`.
- `tests/test_screen_score.py` ; E2E enrichi.

**Décisions** :

- Percentile par **rang** (`method="min"`) plutôt que min-max : insensible aux valeurs extrêmes.
- Égalités → même rang donc même score (pas d'arbitraire).
- Score **relatif au jeu filtré** (standard Stockopedia/Stock Rover) : assumé et documenté.

**Pièges rencontrés** :

1. Ordre de déclaration `SCORE_KEY` avant `SORTABLE_KEYS` (NameError).
2. Sens du rang inversé (`reverse=not descending` au lieu de `reverse=descending`) — attrapé
   par le test `test_percentile_direction_follows_sort_desc`.
3. **Propriété mathématique** : sur des rangs parfaitement anti-corrélés (3 valeurs), la moyenne
   des percentiles est **constante** (50 partout) — le compromis n'émerge pas. Les fixtures
   doivent rompre la symétrie (4 valeurs, dont une dominée sur les deux critères). Documenté
   dans le test `test_compromise_beats_both_extremes`.

**Vérifié** : contrat API réel (B=66.7 en tête, `score` absent de `colors`) ; navigateur
(`score_keys=["roe_pct","p_fcf"]`, `sort_by=[["score","desc"],…]`, bascule → cascade) ;
suite hors réseau verte ; E2E Chromium+WebKit verts ; aucune erreur JS console.

**Correctifs de revue (6 findings)** :

1. **Tri affiché ≠ tri réel** : en mode Compromis, `screenerSortLabel()` affiche désormais
   « Compromis sur ROE % · P/FCF » et `screenerSortRank()` renvoie `null` → plus de badges de
   rang cascade mensongers (`screenerSortIsCascade()`).
2. **En-tête « Score » cliquable = impasse** : rendu non cliquable (le geste est la bascule
   Compromis/Cascade), avec un `title` explicatif.
3. **`score` filtrable malgré la doc** : nouvelle constante `FILTERABLE_KEYS` (= `SORTABLE_KEYS`
   moins `score`) utilisée par `_validate_filters` → `filters: {"score": …}` renvoie 422.
   Tests : `test_score_is_not_filterable`, `test_score_filter_422`.
4. **Doublon dans `SORTABLE_KEYS`** : `DEFAULT_SORT_ORDER[SCORE_KEY] = True` suffit →
   `SORTABLE_KEYS = tuple(DEFAULT_SORT_ORDER.keys())`. Test `test_sortable_keys_has_no_duplicate`.
5. **Docstring « pure » contredite** : `filter_and_sort` documente explicitement qu'elle **mute**
   les `ScreenResult` (elle y écrit `score`) ; `composite_score` reste pure.
6. **Colonne Score toujours visible** : masquée hors mode compromis ≥ 2 critères
   (`screenerScoreColumnVisible()`) ; branche morte retirée de `_cellDisplay`.

**Total final** : suite hors réseau verte, E2E verts, ruff/mypy/`node --check` verts.
