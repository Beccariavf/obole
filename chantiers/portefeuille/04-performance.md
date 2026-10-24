# #17.4 — Portefeuille · Performance (stats, mensuels, points d'entrée/sortie)

> **Statut :** **fait** · **Priorité :** 🟡 Q2 · **Impact Pernod :** 🟠 (marqueurs sur le graphe héro)
> **Branche (historique) :** `feat/portefeuille-performance` · **Taille :** ~3 sessions
> **Fiche parente :** #17 · **Précédent :** `03-risque.md` · **Suivant :** `05-dividendes.md`

---

## 1. Contexte

La section `Performance` répond à « est-ce que je bats le marché, et mes achats ont-ils été
bons ? ». C'est la transposition des captures Baggr « Rendements mensuels (TWR) » + la
rétrospective des points d'entrée/sortie, élargie au retour utilisateur à une **synthèse
fondamentale pondérée** de ce que l'on détient réellement (pas une moyenne de catalogue).

**C'est le seul jalon 🟠 du chantier** : la dernière brique (points d'entrée/sortie) ajoute des
marqueurs au **graphe héro de la fiche entreprise** (`src/obole/web/charts.js::drawChart`), donc
`pytest -m network` est **obligatoire**.

## 2. Objectif

Comparer le portefeuille à un benchmark choisi, sur la durée **MAX** (par principe),
voir la **synthèse fondamentale pondérée** de ses lignes, ses **rendements mensuels** en tableau
face au benchmark, la **contribution de chaque entreprise** à la performance, puis **rejouer ses
points d'entrée/sortie** ligne par ligne pour savoir si, depuis chaque achat, on a battu le
benchmark.

## 3. Non-objectifs

- Pas de rendements glissants ni de rolling Sharpe.
- Pas de comparaison multi-benchmarks simultanée (un benchmark à la fois).
- Pas de marqueur sur le graphe **d'un ratio ou d'un indice** (action uniquement dans ce jalon).
- Pas de prévision / projection.
- Pas de rééchantillonnage des stats par ligne (une valeur par métrique, pondérée).

## 4. Périmètre élargi — 3 sous-jalons

### A — Camembert + statistiques agrégées

- Réutilise le donut « Répartition des titres » existant (pondéré par poids de marché) :
  **cohérence absolue avec le camembert** — mêmes lignes sélectionnées (compte ou étiquette),
  mêmes poids.
- Panneau de stats **pondéré par poids de portefeuille** (agrégation pondérée, pas moyenne
  simple), par grandes catégories (taxonomie `config.PORTFOLIO_STAT_GROUPS`, source unique) :
  - **Général** : nombre d'actions, poids du top 5, capitalisation, note Q moyenne ;
  - **Marges** : brute, opérationnelle, nette ;
  - **Retours sur capitaux** : ROE, ROCE, ROIC ;
  - **Santé** : dette nette/EBITDA, Piotroski, Altman Z, Agilité (FCF/CAPEX) ;
  - **Croissance** : pente de régression 20 ans, potentiel 5A, potentiel 10A ;
  - **Valorisation** : P/E, P/FCF, P/B ;
  - **Rendement ajusté au risque** : Sharpe + Sortino, portefeuille face au benchmark.
- **Ratios ajustés au risque** : Sharpe = rendement/volatilité, taux sans risque = 0 % par défaut
  (`config.PORTFOLIO_RISK_FREE_DEFAULT`), **réglable en Paramètres** (persisté, comme le
  benchmark — réglage `portfolio_risk_free`, groupe « Mesure technique »).

### B — Rendements mensuels + performance par entreprise

- Tableau mensuel : lignes = années, colonnes = 12 mois + total annuel ; portefeuille en ligne
  principale, benchmark en sous-ligne (chaînage TWR cohérent avec le Résumé).
- Répartition de la performance par entreprise : performance brute **ET** contribution
  (poids × perf) à la performance totale du portefeuille.

### C — Grand tableau cliquable + détail par point d'achat + marqueurs fiche

- Grand tableau de toutes les lignes sélectionnées ; clic ligne → fenêtre de détail.
- Détail : graphe dédié compact (hauteur ~300 px, style mini-chart) traçant la **performance
  cumulée** du titre face au benchmark (rebasée à 0 % au début de la fenêtre), avec un
  **sélecteur d'horizon TTM/3A/5A/10A/MAX** (défaut 5A).
- Sélecteur d'achats/ventes au-dessus : cocher un point d'entrée → le graphe ne montre qu'à
  partir de ce point et compare au benchmark (sélectionnable).
- Extension fiche entreprise (graphe héro) : case « transactions » **séparée des événements** →
  marqueurs triangle plein vers le haut = achat (bleu), vers le bas = vente (rouge), niveau =
  cours du jour, infobulle (date · quantité · prix). Marqueurs **masqués par défaut**, alimentés
  par le **portefeuille** (pas la table `events`), et **n'entrent pas** dans le calcul de
  régression.

## 5. Critères d'acceptation

### A — Camembert + stats agrégées

- [x] Agrégation pondérée par poids testée (moyenne pondérée ≠ moyenne simple ; exclusion des
  valeurs `None` sans biaiser le poids du dénominateur)
- [x] Donut et stats portent sur **exactement** les mêmes lignes (compte/étiquette) — test de
  cohérence
- [x] Sharpe/Sortino testés (cas nominal, volatilité nulle, série plate) ; taux sans risque lu
  depuis `config.py` via les réglages persistés, défaut 0 %, affiché portefeuille ET benchmark
- [x] Stats couvrent les catégories demandées ; métrique non calculable affichée « -- »
- [x] Aucun seuil littéral côté JS (source unique `config.py` → `/api/meta`)

### B — Mensuels + par entreprise

- [x] `monthly_returns` (existant) réutilisé pour portefeuille ET benchmark ; total annuel =
  chaînage des 12 mois
- [x] Tableau cohérent avec la courbe TWR du Résumé (même méthode de chaînage) — test
- [x] Contribution par entreprise : somme des contributions ≈ perf totale (test, tolérance)
- [x] Cas limites : mois partiels, mois sans donnée, première/dernière année

### C — Détail + marqueurs

- [x] Clic ligne → détail ; graphe dédié façon Résumé (perf cumulée %, sans régression) (e2e)
- [x] Sélection d'un point d'achat recadre le graphe au point d'entrée + écart au benchmark (e2e)
- [x] Horizons TTM/3A/5A/10A/MAX du graphe de détail (défaut 5A, source `config.py`) — recadrage client sans refetch (Vitest + e2e)
- [x] Points d'entrée/sortie : titre cliquable (ligne benchmark) ouvrant un menu flottant en surimpression (jamais le graphe redimensionné) ; choisir un point recadre ET referme (Vitest + e2e)
- [x] `entry_exit_retrospective` testé : achat qui bat le benchmark / achat qui le rate
- [x] Marqueurs héro masqués par défaut, affichés à la coche ; ne modifient ni la droite ni les
  bandes (e2e)
- [x] Marqueurs basés sur le portefeuille (pas la table `events`), cohérents avec le patron
  `events.js`

### Transverse

- [x] `engine/portfolio.py` reste pur ; architecture `web → api → services → engine → data`
  respectée
- [x] `pytest -m network` vert (calibration Pernod `z = −3.81` intacte) — impact 🟠
- [x] Suite outillée verte avant fusion (ruff + mypy + pytest hors réseau, Vitest, e2e)

## 6. Invariants préservés

- **La calibration Pernod (`z = −3.81`, ±0.15) reste verte** — le test réseau est le garde-fou
  de ce jalon.
- La régression reste calculée aux **trois** endroits (serveur, `drawChart`, `computeLive`) ;
  les marqueurs sont une **couche d'annotation** qui n'entre pas dans le calcul.
- `engine/portfolio.py` reste pur ; aucun seuil littéral (fenêtres, bornes, taux sans risque dans
  `config.py`).
- Le graphe héro d'un ratio/indice n'est pas touché.
- « Jamais un 0 trompeur » : toute métrique non calculable vaut `None` → « -- » côté front.

## 7. Jalons

- **J4.0** — Socle pur (`monthly_table`, `contributions`, `sharpe_ratio`, `sortino_ratio`,
  `weighted_mean`, `aggregate_statistics`, `entry_exit_retrospective`) + config + `/api/meta`.
  *Fait* (WIP socle).
- **J4.1 (A)** — `services.performance()` + route + serialize + front (donut + panneau stats).
- **J4.2 (B)** — Mensuels P/benchmark + contribution par entreprise + front.
- **J4.3 (C)** — Grand tableau cliquable + détail + rétrospective + marqueurs héro + e2e +
  `pytest -m network`.

## 8. Note de reprise

**Jalon livré** sur la branche `feat/portefeuille-performance` (3 sous-jalons A/B/C).

- **Socle pur** (`engine/portfolio.py`) : `monthly_table` (chaînage 12 mois → total annuel),
  `contributions`, `periodic_returns`, `sharpe_ratio`, `sortino_ratio`, `weighted_mean`,
  `weighted_share`, `polarity_good`, `line_stat_cell`, `aggregate_statistics`,
  `entry_exit_retrospective` (ancrage = **première séance ≥ date**).
- **Config** : `PORTFOLIO_MONTHS`, `PORTFOLIO_STAT_REGRESSION_YEARS`, `PORTFOLIO_RISK_FREE_DEFAULT`,
  taxonomie `PORTFOLIO_STAT_GROUPS`, polarité `PORTFOLIO_STAT_POLARITY` (miroir sourcé des seuils
  calibrés), réglage `portfolio_risk_free` (groupe « technique »).
- **Service** `performance(account_id, benchmark, period, tag)` : TWR + mensuels P/benchmark,
  poids de marché (cohérents avec le donut), stats agrégées pondérées (extraction via
  `analysis.summary`, source unique), contribution par entreprise, Sharpe/Sortino P + benchmark
  (taux sans risque lu des réglages).
- **API** : `GET /api/portfolio/performance` + `serialize.portfolio_performance_to_dict` ;
  `/api/meta` expose `portfolio_stat_groups` et `portfolio_months`.
- **Front** : onglet Performance (retiré de `PORTFOLIO_PLANNED`) — donut « Répartition des
  titres », panneau de stats groupées (source `/api/meta`, `--` pour non calculable), tableau
  mensuel P + benchmark, contribution par entreprise, ratios ajustés au risque, grand tableau
  **cliquable** → fenêtre de détail (graphe compact ~300 px, toggle log/lin, sélecteur de points
  d'entrée recadrant + écart benchmark). Marqueurs de transactions sur le graphe héro (case
  « Transactions », triangles achat/vente du portefeuille, masqués par défaut, **hors** régression).
- **Tests** : `tests/test_portfolio_performance.py` (cœur), `tests/test_portfolio_performance_service.py`
  (service), `TestPerformanceRoute` (API), `web-tests/portfolio-performance.test.js` (mixins),
  `web-tests/e2e/portfolio.spec.js` (3 parcours e2e). `pytest -m network` vert.

**Post-revue** : docstring `entry_exit_retrospective` aligné sur `bisect_left` (séance ≥ date) ;
`PORTFOLIO_MONTHS` branché dans `monthly_table` ; `contributions.total` = `None` si vide ;
`PORTFOLIO_STAT_GROUPS`/`portfolio_months` exposés ; `weighted_mean` remonté avant
`aggregate_statistics`.

**Correctifs post-vérif live** — la route renvoyait un 500 sur données réelles,
que les mocks masquaient :

- **500** : `services/portfolio._perf_line_metrics` lisait `ind.perf_passe` (inexistant) au lieu
  de `ind.perf_passee` → `AttributeError`. Corrigé ; la fonction est désormais **annotée**
  (`analysis: StockAnalysis`) pour que mypy attrape ce type de coquille.
- **Pondération** : `aggregate_statistics` recevait `[1.0]*N` (moyenne simple). Désormais les
  lignes-titres portent leur **poids de marché réel** (cellules « Général » à poids nul, non
  moyennées) → vraie moyenne pondérée, testée (`test_stats_are_weighted_not_simple_mean`).
- **Rétrospective** : titre ET benchmark sur la série **ajustée** (dividendes réinvestis des deux
  côtés) — comparer brut vs ajusté était inéquitable.
- **Garde-fou CI** : `TestPerformanceRoute` ne mocke plus `analyze` mais seulement `data/yahoo`
  → l'analyse réelle s'exécute et aurait attrapé le 500. Tests `_make_analysis` (vrai
  `StockAnalysis`) au lieu de faux mocks complices.
- **e2e** : onglet Performance désormais actif (tests mis à jour) ; bandeau Performance renommé
  `.pf-perf-head` (collision de sélecteur avec `.pf-risk-head`) ; test Risque rendu déterministe
  (réglages figés — il dépendait du benchmark persisté en base réelle, bug de test préexistant).
- **Bandeau Performance simplifié (revue produit)** : le **sélecteur de période est retiré** —
  la Performance se calcule toujours sur la durée **MAX** (constante front `PF_PERF_PERIOD`,
  choix produit figé). Le **benchmark** reprend le `<select>` du Résumé (liste curée + « Autre… »),
  pour homogénéité entre sections. Le test e2e vérifie l'absence de `.pf-period-select` et que
  la requête part bien en `period=max`.
- **Rendements mensuels en graphe (revue produit)** : le **tableau années × mois est remplacé**
  par un **graphe de barres groupées** portefeuille (bleu `C.accent`) vs benchmark (ambre `C.ma1`,
  comme le Résumé/Risque — pas de turquoise). Un **sélecteur TTM / années civiles** (chips, défaut
  **TTM** = 12 derniers mois, chevauchement d'années autorisé) commande le grain affiché. Un mois
  absent est un **trou** (jamais un 0) ; axe Y en % avec ligne zéro. Logique 100 % client
  (`pfMonthlyChart`/`drawMonthlyChart`, `MONTHS_FR` pour les étiquettes) : aucun refetch au clic
  sur une année. Hauteur `CHART_HEIGHT_PORTFOLIO_MONTHLY` (config.py → `/api/meta`). Titre
  conservé (« Rendements mensuels »).
- **Contribution par entreprise en graphe (revue produit)** : le **tableau `Titre | Poids | Perf |
  Contribution` est remplacé** par un **graphe de barres verticales** (même forme que les mensuels),
  une barre par entreprise, hauteur **proportionnelle à `contribution_pct`** — **bleu `C.accent`**
  si la contribution est positive, **rouge `C.bad`** sinon (charte bleu=bien/rouge=mal). Tri
  **croissant** (la **pire** contribution à gauche, la **meilleure** à droite — inversion demandée
  en revue : lecture de la plus mauvaise à la meilleure), nom d'entreprise en abscisse (repli
  ticker), ligne zéro commune. Le **Total** (`total_pct`) passe dans l'en-tête de la carte,
  coloré selon son signe. Titre renommé **« Contribution à la performance »**. Logique 100 % client
  (`pfContributionChart`/`drawContributionChart`) ; hauteur `CHART_HEIGHT_PORTFOLIO_CONTRIB`
  (config.py → `/api/meta`).
  **Cohérence (revue visuelle)** : l'axe Y, la grille, la ligne zéro neutre, le suffixe ` %` et les
  marges sont **identiques** à ceux du graphe « Rendements mensuels » voisin — les deux cartes se
  lisent comme une paire. Le tri reste croissant (pire à gauche, meilleure à droite) et les barres
  restent colorées par signe. Deux écarts assumés, justifiés par le peu de titres : `bargap: 0.6`
  (bâtons plus fins que les colonnes groupées des mensuels) et `tickangle: -30` + marge basse
  56 px **uniquement** quand un libellé dépasse 12 caractères (sinon libellés droits, comme les
  mois).
- **Ratios ajustés au risque par période (revue produit)** : la carte « Rendement ajusté au
  risque » porte un **sélecteur de période** (chips **TTM / 3A / 5A / MAX**, défaut **MAX**,
  source unique `config.PORTFOLIO_RISK_PERIODS`). Les Sharpe/Sortino (portefeuille ET benchmark)
  sont **pré-calculés serveur pour chaque fenêtre réellement couverte** (une période n'est
  proposée que si `period_start_index > 0` ; `max` toujours) → le front bascule **sans refetch**
  (`risk_adjusted.by_period` + `periods`). `period_start_index` gère désormais `ttm` (= 1 an).
  Le sélecteur est **masqué** s'il n'y a qu'une seule période ; repli sur MAX si la période
  mémorisée disparaît. Compat : `risk_adjusted.portfolio`/`benchmark` restent (= MAX).
- **Détail par titre : benchmark + points d'achat (revue produit)** : la modale de détail d'un
  titre trace désormais, en plus du cours et de la droite de régression, le **benchmark** et les
  **triangles achat (bleu) / vente (rouge)** — mêmes conventions que la case « Transactions » du
  héro. Les deux courbes (titre + benchmark) sont ramenées à **base 100** au début de la fenêtre
  visible, sur un **axe linéaire unique** (le toggle « Échelle log » est retiré). Nouvel endpoint
  dédié `GET /api/portfolio/security?ticker=&benchmark=` (`services.portfolio.security_detail`,
  prix via cache, courbe benchmark **alignée sur les dates du titre**) : `/api/stock` reste
  inchangé. Un **sélecteur de benchmark propre à la modale** (liste curée + « Autre… », défaut =
  benchmark de la Performance) permet d'explorer sans écraser le réglage global.

**Détail par titre : refonte façon Résumé + horizons (revue produit)** : la **droite de
régression est retirée** du graphe de détail — c'est désormais un graphe de **performance
cumulée (%) calqué sur le Résumé**, plus lisible : titre (bleu `C.accent` + aire) vs benchmark
(ambre `C.ma1`), les **deux courbes rebasées à 0 %** au début de la fenêtre affichée (axe Y en
`« % »`, plus de « Base 100 »). Un **sélecteur d'horizon TTM / 3A / 5A / 10A / MAX** (source
unique `config.PORTFOLIO_DETAIL_HORIZONS`, défaut **5A** via `PORTFOLIO_DETAIL_HORIZON_DEFAULT`,
exposés dans `/api/portfolio/benchmarks` → `/api/meta`) recadre la série **purement côté client**
(aucun refetch) : `pfDetailHorizonStart`/`pfDetailWindowStart` bornent la fenêtre sur la dernière
date (comme `period_start_index` côté serveur). Les **triangles achat/vente** sont conservés
(alignés et filtrés sur la fenêtre, y rebasé en %), le **sélecteur de points d'entrée/sortie**
aussi (clic = recadrage depuis ce point, re-clic = vue pleine ; changer d'horizon efface le point
sélectionné). La **légende** porte la perf cumulée de la fenêtre pour le titre ET le benchmark.

**Points d'entrée/sortie en menu flottant (revue UX)** : la rangée horizontale de pastilles
(qui débordait en largeur sur un historique chargé) est remplacée par un **titre cliquable**
« Points d'entrée/sortie » placé sur la **ligne du benchmark** (chevron `▾/▴`). Au clic, une
liste **verticale défilable** s'ouvre **en surimpression au-dessus du graphe** (patron
`pf-breakdown-pick` : `position: absolute`, `@click.outside`, hauteur bornée par la variable CSS
`--pf-entry-menu-h`). Le graphe n'est **jamais redimensionné** (vérifié e2e : largeur et position
identiques menu fermé/ouvert/sélection faite). Choisir un point applique `selectPfEntry`
(recadrage 0 %) **et referme** le menu ; re-clic sur le titre ou clic extérieur referme sans
changer. État `pfEntryMenuOpen` + `togglePfEntryMenu()`, réinitialisé à l'ouverture/fermeture de
la modale.

## Revue de code post-merge (#17.4) — correctifs appliqués

Revue de la PR mergée (18 findings). Trois traités, le reste classé finition.

**[#1] Perf réseau — la Performance bloquait au premier affichage.**
La boucle « Stats agrégées » appelait `analysis_service.analyze()` par ligne détenue, soit
~4 requêtes yfinance **séquentielles** par titre (info, financials, balance sheet, cashflow).
Sur 30 lignes en cache froid : plusieurs dizaines de secondes derrière « Calcul de la
performance… ». Le reste du service évitait délibérément ce coût (`_attach_names` cache-only).

*Correctif* : analyse des lignes via `ThreadPoolExecutor` borné par
`config.PORTFOLIO_PERF_WORKERS` (= 8, même nature I/O-bound que `SCREEN_WORKERS`, plafonné par
le nombre de lignes). Le résultat est réassemblé **dans l'ordre du portefeuille**, donc
l'agrégation pondérée reste déterministe. Dégradation ligne par ligne conservée : une analyse
en échec est absente des stats — jamais comptée à poids nul.

*Mesures* — deux protocoles, cache FROID, **nombre d'appels réseau** comptés à la frontière
réelle (`fetch_identity` + `fetch_fundamentals`, appelés par `analyze` pour chaque ligne),
latence réseau simulée à 0,15 s/appel, 10 lignes :

| | Appels réseau | Durée | Workers |
|---|---|---|---|
| Séquentiel (avant) | 20 | 3,00 s | — |
| Parallèle (après) | 20 | **0,69 s** | 8 |

→ **4,3×, −77 % de temps** sur 10 lignes. Le nombre d'appels est identique (le correctif ne
change pas le travail, seulement son ordonnancement) ; le coût par ligne est inchangé. Gain sur
la durée seule, qui croît avec le nombre de lignes (30 lignes en cache froid : ~9 s → ~2 s).

*Garde-fous* : `test_network_calls_are_concurrent` compte les appels réseau ET mesure leur
chevauchement (4 appels attendus, `max en vol >= 2`) — **échoue sur le code d'origine**
(`max en vol = 1`), passe après. `test_no_network_on_warm_cache` verrouille en plus l'absence de
sortie réseau quand tout est déjà en cache (`yf.Ticker` rendu explosif), et
`test_analyses_run_in_parallel` mesure la concurrence côté service.

**[#5] Signe « + » sur les niveaux.**
`pfStatValue` préfixait `+` **toute** valeur `unit === "pct"` : marges, ROE, ROCE, ROIC,
agilité s'affichaient « +42,5 % », alors qu'un niveau n'est pas une variation (et que la fiche
entreprise ne les signe pas).

*Correctif* : `config.PORTFOLIO_STAT_GROUPS` porte un champ **`signed: True`** explicite, posé
uniquement sur `slope`, `pot_5y`, `pot_10y` (les vraies variations). `pfStatValue` ne préfixe
que si `signed` ; `pfStatGroups` propage le champ depuis le payload du service.

*Garde-fous* : Vitest verrouille niveau sans signe / variation avec signe, et
`labels-parity.test.js` vérifie via `parsePyStatGroups` que la source Python porte exactement
ces trois clés signées.

**[#2] Donut Performance sans observateur de redimensionnement.**
`drawPerfDonut` dupliquait `drawPortfolioDonut` sans le `ResizeObserver` : Plotly figeait le SVG
à la largeur du premier rendu, d'où un disque décalé au repli média <900px — régression d'un bug
déjà corrigé sur le donut du Résumé.

*Correctif* : les deux donuts passent par un traceur PARTAGÉ `_drawDonut(el, labels, values)`
(la duplication était la cause du bug — finding #24). `_pfObserveDonut(width, el, node)` garde un
observateur, une largeur ET le **nœud** par conteneur (clés = id du div), et rebranche dès que le
nœud change : `#pf-perf-donut` vit sous `<template x-if>`, donc Alpine le recrée au passage
vide/erreur (finding #19). Le traceur à rejouer est mémorisé dans `_pfDonutDraw[el]`.
`_pfDisconnectDonut` libère les trois maps.

*Note sur `portfolio_stat_groups` dans `/api/meta`* (finding #4) : le front lit la taxonomie
depuis le payload du service (`stat_groups`), pas depuis `/api/meta`. Le champ y resterait un
mort — laissé en l'état, à retirer ou brancher dans une passe de nettoyage dédiée.

**Non traités** : #3, #4, #6–#14, #16–#18 (finition — constantes de hauteur, devise en dur,
responsive, accessibilité des lignes, `_weights_by_ticker` renvoyant 0.0, mocks e2e fictifs…).

**[#15] Écran contradictoire dans la modale de détail.**
Le sélecteur de benchmark de la modale est LOCAL (il recharge `/api/portfolio/security`), mais
le menu « Points d'entrée/sortie » lisait `pfPerf.retrospective` — calculée côté service avec le
benchmark **global**. Après un changement de benchmark, le graphe comparait au nouveau pendant
que le menu annonçait les écarts de l'ancien.

*Correctif* : `pfDetailEntries()` **recalcule** `return_pct`/`benchmark_pct`/`delta_pct` depuis
les séries déjà alignées de la modale (`pfDetail.chart.price_adj` + `pfDetail.benchmark_curve`),
avec la même convention que le moteur (première séance >= date, dernière valeur disponible,
`None` si indisponible). Aucun appel serveur supplémentaire.

*Garde-fous* : trois tests Vitest — recalcul depuis le benchmark de la modale (le delta passe à
+15 % là où le payload global disait +5 %), suivi d'un changement de benchmark (le signe
s'inverse), et dégradation `null` quand le benchmark est indisponible.

### Seconde passe de revue (#19–#24)

- **[#19] Nœud recréé par Alpine** : `#pf-perf-donut` vit sous `<template x-if>` ; Alpine le
  détruit et le recrée au passage vide/erreur. L'observateur est désormais mémorisé **par nœud**
  (`_pfDonutNodes[el]`) et reconnecté dès que le nœud diffère de celui observé. Test : nouveau
  nœud → ré-observé + ancien déconnecté ; même nœud → pas de doublon (rouge sans le correctif).
- **[#20] Test vacuant** : `test_no_network_on_warm_cache` mockait `analyze` et n'atteignait donc
  jamais `yf.Ticker`. Il utilise maintenant `_patch_yahoo_prices` (analyse réelle) et pré-positionne
  identité **et** comptes valides pour le cache. Vérifié : sans le cache `fundamentals`, il échoue
  bien sur l'appel réseau.
- **[#21] Budget du pool** : `wait(timeout=PORTFOLIO_PERF_TIMEOUT * workers)` +
  `shutdown(wait=False, cancel_futures=True)`, même garde-fou que le screener. Un appel yfinance
  qui pend ne fige plus l'onglet ; la ligne est abandonnée et sort des stats.
- **[#22] `delta_pct` périmé** : quand la transaction est hors de l'historique du détail
  (`idx < 0` ou `>= dates.length`), les trois écarts sont remis à `null` au lieu de conserver
  ceux de l'ancien benchmark.
- **[#23] Doc/commentaires** : signature réelle d'`_pfObserveDonut(width, el, node)` et origine
  de `signed` (`stat_groups` du service, pas `/api/meta`) corrigées.
- **[#24] Duplication supprimée** : un seul traceur `_drawDonut(el, labels, values)` sert les deux
  donuts ; le traceur à rejouer est mémorisé dans `_pfDonutDraw[el]`, plus d'identifiant comparé
  en dur dans `_pfRedrawDonut`. C'est cette duplication qui avait produit le bug #2.
