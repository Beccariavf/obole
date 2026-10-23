# #19 — Fiche entreprise : section Dividende

> **Statut :** fait · **Priorité :** 🟡 Q2 (important, non urgent — cas (c) évolutivité)
> **Impact Pernod :** 🟠 · **Branche :** `feat/dividende-fiche` · **Taille :** ~1 session
> **Fiche parente :** #16 (refonte fiche) — étape 4 « Dividende ».
> **Précédent :** #18 (Quantitatif, même patron de taxonomie).

---

## 1. Contexte

La section Dividende était réduite à une carte KPI (rendement / payout) et deux
graphes secondaires (dividende par action, rachats), produits en dur dans
`charts.js::fundamentalGroups`. La maquette cible (captures Obole) demande une
section dense : métriques clés, **rendements continus** (Dividend Yield,
Shareholder Yield), dividende par action + croissance, payout ratios (résultat et
FCF), shareholder payout ratios et retour à l'actionnaire (dividendes + rachats).

Deux questions ouvertes ont été tranchées :

- **Courbes continues** : elles suivent le patron déjà en place pour les moyennes
  mobiles — **calculées serveur en pleine résolution, puis décimées avec le même
  pas que le cours**, donc alignées 1:1 sur `chart.dates`. Le front ne recalcule
  que la **stat de fenêtre** (High / Médiane / Low), comme `computeLive`.
- **Zoom plein écran** : inexistant auparavant (seuls le héro et le comparateur
  étaient interactifs). Ajouté comme composant réutilisable.

## 2. Objectif

Une section Dividende **honnête et dense** : lecture immédiate « où en est-on »
(métriques clés), rendement continu sur la période affichée, séries longues du
dividende par action, ratios de distribution sur les exercices disponibles, et
zoom plein écran d'un graphique (sans requête réseau).

## 3. Non-objectifs

- Pas de **prochain paiement** ni de **statut** : yfinance Europe ne fournit aucun
  calendrier fiable (seule une date ex-div approximative) -> « — » assumé.
- Pas de payout ratios au-delà de ~5 ans : les comptes yfinance sont plafonnés.
- Pas de fiscalité (brut/net) ni de simulation de réinvestissement.
- Pas de modification de la formule de régression (invariant métier).

## 4. Exigences

- 4.1 **Taxonomie unique** `config.DIVIDEND_GROUPS` (calquée sur `QUANT_GROUPS`),
  servie par `/api/meta` (`dividend_groups`, `dividend_colors`, `metric_units`).
- 4.2 **Rendements continus** : `dividend_yield` = DPA roulant 12 M / cours,
  `shareholder_yield` = (dividendes + rachats **par action**) / cours — **toujours
  affiché** (même sans rachats, la courbe se confond avec Dividend Yield).
  Calculés par `engine/dividends.rolling_yield_series` (pur), orchestrés par
  `services/analysis` (qui ramène les rachats TOTAUX en par-action via les actions
  en circulation), sérialisés dans le payload `chart` (décimation alignée).
- 4.3 **Métriques clés** : Yield TTM, Payout TTM, années d'augmentation, années
  sans baisse, CAGR 5A/10A, fréquence (déduite du rythme des versements), dernier
  paiement. « Prochain paiement » = « — ».
- 4.4 **Dividende / Action** (barres) + **Croissance / Action** (barres %), pastilles
  Perf / CAGR.
- 4.5 **Payout Ratios** et **Shareholder Payout Ratios** en multi-lignes (~5 ans).
- 4.6 **Shareholder Returns** : barres empilées dividendes (bleu) + rachats (teal) —
  jamais de rouge.
- 4.7 **Zoom plein écran** : clic sur l'icône ⤢ d'une carte -> modale, sélecteur
  YTD/1A/3A/5A/MAX **positionnant un curseur à deux poignées** identique au héro et
  partageant `rangeStart`/`rangeEnd` (source unique), focus trap + fermeture
  Échap/clic extérieur, **zéro requête réseau**. Déplacer une poignée redessine la
  modale ET le héro ; pour les cartes à axe d'années, la plage de dates est traduite
  en bornes d'années.
- 4.8 La série de dividende par action est une **série longue** (~20-40 ans) ;
  l'année civile en cours est écartée des stats de régularité ET de croissance
  (versements partiels → fausse baisse sinon).
- 4.9 **Shareholder Yield conditionnel** : affiché seulement si le titre a des
  rachats (`buybacks_available`) — sans rachats, la courbe se confondrait
  exactement avec Dividend Yield (doublon inutile).
- 4.10 **Badge de fiabilité** signalant les manques de la source (rachats absents,
  historique de payout court).
- 4.11 **Fenêtre par défaut** des séries longues : 10 ans si l'historique le permet,
  sinon 5, sinon tout (`DIVIDEND_DEFAULT_WINDOW_YEARS`/`_MIN_` en config). Le zoom
  sert à explorer plus loin. Appliquée aux courbes de rendement ET aux barres longues.
- 4.12 **Standard de hauteur** dans `config.py` (`CHART_HEIGHT_*`, servis par
  `/api/meta`) : héro 440, mini 200, héro Dividende 300, modale 420. CSS et layout
  Plotly coïncident (variables CSS alignées, aucune valeur littérale JS).
- 4.13 **Garde-fous rachats** : actions manquantes ou nulles -> composante rachat = 0
  (jamais d'infini, jamais de milliards de %) ; repli sur `info["sharesOutstanding"]`
  quand la ligne « Actions en circulation » manque du tableau.

## 5. Critères d'acceptation

- [x] Branche `feat/dividende-fiche`.
- [x] Taxonomie `config.DIVIDEND_GROUPS` = source unique (via `/api/meta`), testée
      côté API (`test_api.py`) et front (parité `labels-parity.test.js`).
- [x] `engine/dividends.py` **pur** (zéro I/O, aucun import `data/`/`services/`).
- [x] Rendements continus calculés serveur, décimés avec le même pas que le cours :
      test d'alignement (`test_api.py`, `test_analysis.py`).
- [x] `MODEL_VERSION` 2 -> 3 -> 4 -> 5 -> 6 (re-fetch des comptes en cache).
- [x] Métriques clés, fréquence déduite, CAGR, dernier paiement ; prochain = « — ».
- [x] Dividende/Action + Croissance + Payout Ratios + Shareholder Returns rendus.
- [x] Badge de fiabilité (rachats absents, historique court).
- [x] **Shareholder Yield conditionnel** : affiché seulement si des rachats existent
      (`buybacks_available`) ; rachats TOTAUX ramenés par action
      (`services/analysis`, `engine/dividends.buybacks_per_share`), garde-fous
      actions manquantes/nulles + repli `info["sharesOutstanding"]`. Tests engine +
      API (magnitude ~quelques %, pas 10⁹).
- [x] **Fenêtre par défaut** 10/5 ans (`DIVIDEND_DEFAULT_WINDOW_YEARS` en config,
      servie par `/api/meta`) appliquée aux courbes de rendement et aux barres longues.
- [x] **Standard de hauteur** dans `config.py` (`CHART_HEIGHT_*` -> `/api/meta`) :
      CSS (variables `--chart-h-*`) et layout Plotly coïncident ; héro 440, mini 200,
      héro Dividende 300, modale 420.
- [x] **Layout « option A »** : grille adaptative (comme le Quantitatif), Dividend
      Yield en pleine largeur (héro de section, 300 px), toutes les autres cartes en
      colonne simple (200 px). Le caractère « wide » vient de la taxonomie config
      (`wide: True`), pas d'un type.
- [x] Zoom plein écran (modale `.modal-detail`), **curseur à deux poignées SOUS le
      graphe**, partagé avec le héro (`rangeStart`/`rangeEnd`), presets
      `YTD/1A/5A/10A/MAX` = raccourcis de positionnement, déplacement d'une poignée
      -> redessine modale + héro, axe années traduit de la plage de dates, focus
      trap, fermeture Échap/clic extérieur, testé e2e.
- [x] Aucun seuil littéral JS : fréquence, CAGR, unités, couleurs, fenêtre par défaut
      et hauteurs depuis `config.py`.
- [x] Calibration Pernod (`z = −3.77`, ±0.15 de −3.81) verte — `pytest -m network`.
- [x] `app.js` < 500 l. (196), 0 `fetch` hors `api.js`, aucune dépendance nouvelle.
- [x] Tests : `tests/test_dividends.py` (33), `tests/test_analysis.py` (+4),
      `tests/test_fundamentals.py` (+2), `web-tests/dividende.test.js` (30),
      `web-tests/e2e/dividende.spec.js` (6).
- [x] Suite hors réseau verte (514 tests) ; vitest (166) ; e2e Chromium+WebKit (44) verts.

## 6. Invariants préservés

- Calibration Pernod (`z = −3.81`, ±0.15) inchangée.
- La régression reste calculée aux trois endroits (serveur, `drawChart`, `computeLive`).
- `config.py` reste la seule source des seuils et des taxonomies.
- `engine/` reste pur (aucun import `data/`/`services/`).
- Les 3 points d'entrée (recherche, screener, indice) ouvrent la fiche normalement.

## 7. Jalons

- **J1** — Backend : `engine/dividends.py`, `data/yahoo._build_dividend` enrichi,
  modèle, orchestration, sérialisation, taxonomie `config.py`, route `/api/meta`.
- **J2** — Front : `web/dividend.js`, `thresholds.js`, template générique, CSS.
- **J3** — Zoom plein écran (modale, zéro requête).
- **J4** — Tests (engine, API, front, e2e) + vérification outillée.

## 8. Note de reprise

**Fait.** Section Dividende complète, pilotée par `config.DIVIDEND_GROUPS` (4 groupes :
Rendement, Dividende par action, Payout, Retour à l'actionnaire).

- **Backend.** `engine/dividends.py` (nouveau, **100 % pur**) : `annual_by_year`,
  `frequency`, `increase_years` (hausse STRICTE), `no_cut_years` (hausse ou stabilité),
  `cagr`, `growth_series`, `rolling_yield_series`, `stats`, et `summary` (agrégat
  consommé par l'API). `data/yahoo._build_dividend` expose désormais `events`
  (versements bruts datés), `payout_history` (4 ratios par exercice),
  `dividend_paid_history`, `last_payment_value/date`. `services/analysis` ajoute
  `dividend["stats"]` (régularité, CAGR, fréquence, croissance) et calcule les deux
  séries de rendement continu ; `api/serialize` les décime sur le même index que le
  cours (`chart.div_yield` / `chart.sh_yield`) et expose `fundamentals.dividend_series`.
  `engine/summary_fundamentals._increase_years` **délègue** à `engine.dividends`
  (source unique, fin de la duplication).
- **Front.** `web/dividend.js` (nouveau mixin) : `dividendGroups`, `dividendKeyMetrics`,
  `drawYieldCard` (axe date), `drawDividendHist/Growth/Lines/Stacked`, pastilles,
  état vide, badge de fiabilité (`dividendWarnings`). `charts.js` : routage générique
  (`isChartCard`, `cardPillsOf`, `cardSpanOf`, `cardEmptyOf`) + zoom (`openChartDetail`,
  `detailPreset`, `detailKeydown` focus trap). Template unifié dans `index.html` ;
  CSS `.expand-btn`, `.period-chip`, `.modal-detail`, `.reliability-badge`.

**Décisions.** (1) Rendements continus = patron des moyennes mobiles : serveur
pleine résolution, décimation alignée, stat de fenêtre côté client. (2) « Prochain
paiement » : ligne « — » assumée (non fourni), **sans** champ sérialisé mort.
(3) **Shareholder Yield conditionnel** : affiché seulement si le titre a des rachats
(`buybacks_available`) — sinon la courbe se confondrait exactement avec Dividend
Yield (doublon). Les rachats TOTAUX (cash-flow) sont ramenés par action dans
`services/analysis` (`engine/dividends.buybacks_per_share`, exercice connu le plus
proche, actions nulles ignorées, repli `info["sharesOutstanding"]`) — sans quoi le
rendement actionnaire explosait (bug AI.PA : 1,25 milliard de %). (4) Les stats de
dividende (régularité, CAGR, fréquence, croissance) sont **calculées serveur**
(`dividend.stats`) et affichées telles quelles. (5) L'année civile en cours est
écartée des stats de régularité. (6) Le zoom est une modale dédiée
(`.modal-detail`) avec **curseur à deux poignées identique au héro placé SOUS le
graphe** (plage partagée `rangeStart`/`rangeEnd`, option A) : les presets
`YTD/1A/5A/10A/MAX` positionnent le curseur, bouger une poignée redessine modale +
héro, et pour les cartes à axe d'années la plage de dates est traduite en bornes
d'années. (7) « Augmentation » = hausse stricte ; « sans baisse » = hausse ou
stabilité. (8) **Fenêtre par défaut 10/5 ans** (`DIVIDEND_DEFAULT_WINDOW_YEARS`/
`_MIN_`) : les séries longues n'affichent plus 20 ans d'emblée, le zoom sert à
explorer. (9) **Layout « option A »** : grille adaptative (auto-fit, comme le
Quantitatif), Dividend Yield en pleine largeur (héro de section 300 px), le reste en
colonne simple (200 px). Le caractère « wide » est **piloté par la taxonomie**
(`config.DIVIDEND_GROUPS` porte `wide: True` sur la carte) — le front ne décide plus
quoi mettre en avant. (10) **Standard de hauteur unique** (`config.CHART_HEIGHT_*`
-> `/api/meta`) : CSS (variables `--chart-h-*`) et Plotly partagent les mêmes
valeurs (`mini_wide` retiré). (11) **`buybacks_available`** = rachat présent sur
N'IMPORTE quel exercice de l'historique (et non seulement le plus récent) ; corrige
Amundi, dont les rachats 2021/2022 étaient masqués par le test sur la colonne
courante.

**Pièges.** (1) `index.html` est `lru_cache` : redémarrer le serveur après modif.
(2) Le fuseau du cours (tz-aware) diffère des dates ISO parsées (naïves) :
`rolling_yield_series` normalise tout en naïf. (3) `_annual_amounts` reçoit tantôt
un index Timestamp (comptes bruts) tantôt un index année int (tableau normalisé) ;
`_shares_by_year` tolère les deux (`getattr(y, "year", y)`). (4) `data/` ne peut pas
importer `engine/` (règle des couches) : les stats sont assemblées par
`services/analysis`, pas par `data/yahoo`. (5) Le tableau normalisé a des colonnes
en **années int** (pas Timestamp) — ne pas supposer un `pd.Timestamp`.
(6) `shareholder_payout` évalue `buybacks_available` AVANT le court-circuit sur
« Cash Dividends Paid » : Amundi n'a pas cette ligne, mais a bien des rachats —
l'ordre des tests compte. (7) **Tout changement de `_build_dividend` /
`shareholder_payout` exige un bump de `MODEL_VERSION`** : le cache (TTL 7 j) sert
l'ancien objet tant que la version ne change pas.

**Amundi (constat).** yfinance ne fournit `Repurchase Of Capital Stock` que pour
2021 (−558,5 M€) et 2022 (−859,5 M€) ; 2023-2025 sont `NaN`, et la ligne
« Cash Dividends Paid » est absente. Le programme de rachat de 500 M€ d'Amundi a été
lancé en **février 2026** (hors exercices annuels disponibles). Avec le correctif,
`buybacks_available=True` et le Shareholder Yield réapparaît (composante rachat
calculée via le repli `sharesOutstanding` = 201,2 M actions). Le pic du rendement
roulant (~21 % en mai 2023) vient de la fenêtre 12 mois capturant deux versements
exceptionnels + une année de rachats — comportement de la méthode roulante, pas un
artefact du correctif.

**Prochaine action.** Rien — chantier prêt à fusionner (CI verte).

## 9. Revue de code (correctifs)

- **Zoom ancré sur la fenêtre de la carte** : `openChartDetail` amorce la plage
  partagée sur `defaultDateRange` (10/5 ans) pour une carte Dividende — la modale
  s'ouvre sur ce que la carte montrait (fin du saut 20 ans), puis reste partagée
  avec le héro. Test front ajouté.
- **Payload `dividend` trimé** : `serialize._dividend_payload` ne sérialise plus que
  les clés consommées par le front (`yield_pct`, `payout_pct`, `buybacks_available`,
  `per_share`, `last_payment_*`, `stats`) — fin de la redondance avec
  `dividend_series` sur le fil (`events`, `payout_history`, `buyback_history`,
  `dividend_paid_history` retirés du JSON).
- **Date de dernier paiement** : plus de repli sur `exDividendDate` (date de
  détachement ≠ date de paiement) — seul `lastDividendDate` est utilisé.
- **Source unique `NON_CHART_TYPES`** exportée par `charts.js`, importée par
  `sections.js` (fin de la double déclaration).
- **Code mort retiré** : `engine/dividends.annual_by_year` et `stats` (aucun
  appelant hors tests).
- **Commentaires alignés** : `drawYieldCard` (fenêtre par défaut, pas « héro »),
  `data/yahoo` (prochain paiement = ligne « — » assumée côté front).
- **Fixtures de tests** : `quantitatif.test.js` mis à jour vers la taxonomie
  courante (`divbars`, `stacked`, `kpi`) ; doc `MODEL_VERSION` corrigée.

## 10. Itération UX (option A + Amundi)

- **Grille « option A »** : la section Dividende suit la grille adaptative du
  Quantitatif (2 colonnes). Dividend Yield est la SEULE carte en pleine largeur
  (héro 300 px), le reste en mini 200 px. Le marqueur vient de `config.py`
  (`"wide": True`) et `isWideCard` lit simplement `c.wide`.
- **Hauteurs** : `CHART_HEIGHT_DIVIDEND_HERO = 300` remplace `CHART_HEIGHT_MINI_WIDE`
  (220). Variables CSS `--chart-h-*` et `/api/meta` alignés ; tests de parité mis à jour.
- **Shareholder Yield conditionnel** : masqué sans rachats (badge de fiabilité à la
  place). Inversé par rapport à l'itération précédente, sur demande produit.
- **Presets de zoom** : `YTD / 1A / 5A / 10A / MAX` (3A retiré, 10A ajouté).
- **Curseur sous le graphe** : le dual-slider de la modale est déplacé sous le tracé
  (lecture : courbe d'abord, réglage ensuite) ; e2e vérifie la position verticale.
- **Amundi** : `buybacks_available` corrigé (tout l'historique) + repli
  `info["sharesOutstanding"]` dans `_shares_by_year` ; `MODEL_VERSION` 4 -> 6.
- **Tests** : `web-tests/dividende.test.js` (30), `e2e/dividende.spec.js` (6),
  `test_fundamentals.py` (+2, rachats non récents), `test_analysis.py` (+1, repli
  sharesOutstanding), parité CSS/`/api/meta`.
