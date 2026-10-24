# #18 — Fiche entreprise : section Quantitatif, comparateur & lisibilité

> **Statut :** **fait** · **Priorité :** 🟡 Q2 (cas (c) évolutivité) · **Impact Pernod :** 🟠
> **Branche (historique) :** `feat/quantitatif-fiche` · **Taille :** ~1 session
> **Fiche parente :** #16 (refonte fiche) — étape 3 « Quantitatif », jamais raffinée.
> **Maquette :** `amélioration/prototypes/quantitatif.html` (hors dépôt, gitignoré) — hiérarchie,
> pastilles de dernière valeur, puce « N ans », état vide, comparateur base 100 validés avant code.

---

## 1. Contexte

La section **Quantitatif** est la seule étape de la refonte #16 dont le contenu n'a pas été
revu. Elle empilait des cartes **combo** (`charts.js::fundamentalGroups`) — CA **+ marge nette**,
Bénéfice net **+ BNPA** — où un flux et un ratio partagent un axe à deux échelles, peu lisible.

Deux problèmes structurels observés :

- **Axe trompeur.** Les mini-charts utilisaient un axe `type: "category"` : une métrique à
  4 ans (Agilité Pernod, `Chiffre d'affaires` non) était **étirée sur toute la largeur** de la
  carte, donc lue comme couvrant autant de temps qu'une série de 17 ans. Confirmé sur les
  données RI.PA : `Agilité = [null×13, 120, 150]` (2 valeurs) sur 17 colonnes d'années.
- **Métriques calculées mais non tracées.** `data/fundamentals.build_table` produisait déjà
  des postes jamais montrés (Résultat opérationnel, EBITDA, Capitaux propres, BFR), et yfinance
  expose d'autres postes exploitables (ROIC, actions en circulation, trésorerie/dette, CAPEX, SBC).

## 2. Objectif

Rendre la section Quantitatif **honnête et dense** : une lecture « où en est-on » immédiate
(pastilles de dernière valeur), un axe temporel proportionnel aux données réelles, des cartes
pilotées par une source unique, et un **comparateur** multi-métriques en bas de section.

## 3. Non-objectifs

- Pas de **ROIC vs WACC** (WACC non calculable via yfinance), ni segments/géographie, ni AUM.
- Pas de **TTM / Prévisions** (yfinance ne fournit pas de prévisions fiables hors consensus 1 an,
  déjà en Synthèse).
- Pas de refonte des autres sections (Dividende, Valorisation, Résumé) : hors périmètre.
- Pas de changement de la **formule de régression** (invariant métier).

## 4. Exigences

- 4.1 **Taxonomie unique** : les cartes du Quantitatif vivent dans `config.QUANT_GROUPS`,
  servies au front par `/api/meta` (`quant_groups`). Le front ne décide plus quoi afficher.
- 4.2 **Un flux = un graphe** ; les ratios d'une même famille (marges ; rentabilités dont ROIC)
  partagent un graphe multi-lignes.
- 4.3 **Axe honnête** : échelle temporelle proportionnelle au nombre de données réellement
  disponibles (`metricSeries` filtre les années vides ; axe numérique `xRange`).
- 4.4 **Puce de couverture** « N ans disponibles » sur chaque carte à axe temporel.
- 4.5 **Pastilles** de dernière valeur sous chaque graphe, formatées selon l'unité
  (% / × / montant) et colorées par polarité.
- 4.6 **Comparateur** en bas de la section : 2-3 métriques, rebasées à 100.
- 4.7 Nouvelles métriques tracées : ROIC, Actions en circulation, Trésorerie/Dette brute,
  CAPEX, SBC, Liquidité, Couverture des intérêts. Le **Free Cash Flow** est tracé dans la carte
  « Génération de cash » (OCF vs FCF), **sans carte dédiée** (évite le doublon).
- 4.8 **État vide explicite** : une carte dont la série compte moins de 2 points affiche
  « Pas assez de données… », jamais un cadre de graphe nu.

## 5. Critères d'acceptation

- [x] Taxonomie `config.QUANT_GROUPS` = source unique, exposée par `/api/meta` (`quant_groups`),
      verrouillée par un test de parité front (`labels-parity.test.js`) et un test API.
- [x] Fin des combos flux+ratio ; marges et rentabilités (ROE/ROA/ROCE/ROIC) en multi-lignes.
- [x] Axe proportionnel aux données réelles (`metricSeries` sans trous + `xRange` numérique) ;
      puce « N ans » ; **état vide explicite** si < 2 points (`cardEmpty`) ; test front sur
      l'Agilité Pernod (2 ans ≠ 4 ans) + test de l'état vide.
- [x] Pastilles de dernière valeur (% / × / montant), colorées par polarité.
- [x] Comparateur 2-3 métriques en bas du Quantitatif, base 100.
- [x] Structure financière refondue : Levier, Gearing, Liquidité, **Couverture des intérêts**,
      Cash & dette, Capitaux propres, Actions en circulation.
- [x] Maquette statique validée avant code (`amélioration/prototypes/quantitatif.html`).
- [x] Nouvelles métriques backend testées (ROIC, Liquidité, Trésorerie, Dette brute, Actions,
      CAPEX, SBC, Couverture des intérêts) ; garde-fou `abs(CAPEX)`, `abs(Intérêts)`.
- [x] Invariants verts : `config.py` source unique (0 seuil littéral JS), `app.js` < 500 l.,
      0 `fetch` hors `api.js`, parité régression, calibration Pernod (`pytest -m network`).
- [x] Tests : engine (`test_fundamentals.py`), API (`test_api.py`), front
      (`web-tests/quantitatif.test.js`, 19 tests), e2e (`e2e/quantitatif.spec.js`).

## 6. Invariants préservés

- La calibration Pernod (`z = −3.81`, ±0.15) reste verte (`pytest -m network`).
- La régression reste calculée aux trois endroits (serveur, `drawChart`, `computeLive`).
- `config.py` reste la seule source des seuils et de la taxonomie des cartes.
- `app.js` reste le composant seul, < 500 lignes ; aucun `fetch` hors `api.js`.

## 7. Jalons

- **J1** — Backend : nouvelles métriques (`data/fundamentals.py`) + taxonomie (`config.py`) + route.
- **J2** — Front : `charts.js` (axe honnête, multi-lignes, pastilles, comparateur) + template + CSS.
- **J3** — Tests (engine, API, front, e2e) + vérification outillée.

## 8. Note de reprise

**Fait.** Taxonomie `config.QUANT_GROUPS` (3 groupes) servie par `/api/meta` ; `charts.js` réécrit
(`drawLines`/`drawBars`/`drawShares`, `metricSeries` sans trous, `xRange` par carte, `cardPills`,
`cardEmpty`, `compareKeys`/`toggleCompare`/`drawCompare`) ; template (`card-span`, `.card-pills`,
état vide, comparateur) ; CSS (`.card-pills`, `.compare-chip`, `.card-span`). Métriques ajoutées
dans `build_table` : ROIC, Liquidité, Trésorerie, Dette brute, Actions en circulation, CAPEX, SBC,
Couverture des intérêts + seuils `RATIO_THRESHOLDS`. Tests : 19 front, 5 engine, 1 API, 2 e2e.
Maquette validée : `amélioration/prototypes/quantitatif.html` (hors dépôt).

**Décisions.** Axe **par carte** (largeur ∝ données réelles) plutôt qu'axe partagé : une carte de
4 ans couvre 4 ans, une de 17 ans couvre 17 ans. L'unité d'affichage (`pct` / `mult` / `money`)
vit dans `config.METRIC_UNITS` (source unique servie par `/api/meta`), pas dans le JS. Le Free
Cash Flow est tracé dans « Génération de cash » (OCF vs FCF), sans carte dédiée (évite le doublon).

**Correctifs post-revue (12 constats).** Info-bulles alignées sur tous les titres réels
(`infoText`, test de couverture ajouté) ; suffixe d'axe via `metricUnit` ; options du comparateur
dérivées de `QUANT_GROUPS` ; 1er tracé via `$nextTick` ; hauteur 260 ; plafond 3 explicite
(`COMPARE_MAX`, chips désactivées + hint) ; lignes de seuil seulement sur carte mono-métrique ;
fill d'aire seulement en mono-série ; commentaire `QUANT_GROUPS` corrigé ; doc #17 retirée de
cette branche (appartient à `feat/portefeuille`).

**Pièges.** (1) Le parser JS `parsePyQuantGroups` doit tolérer les espaces internes et virgules
finales produites par `ruff format` sur les objets multilignes. (2) Un cache comptes 7 j peut
servir une table sans les nouvelles métriques : `POST /api/refresh/<ticker>` pour tester.

**Prochaine action.** Aucune — chantier clos.
