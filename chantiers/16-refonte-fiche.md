# #16 — Refonte de la fiche entreprise (rail de sections)

> **Statut :** **fait** (Étapes 0 → 7 ; la section Finance est livrée via #22/#23) · **Priorité :** 🟡 Q2 (important, non urgent — cas (c) évolutivité)
> **Impact Pernod :** 🟠 · **Branche proposée :** `feat/refonte-fiche` · **Taille :** 7 étapes
> **Cadrage amont :** `amélioration/docs/product/prd.md` (non versionné)

---

## 1. Contexte

La fiche entreprise est aujourd'hui une **page unique en scroll continu** (`PRD.md` §8.3 :
« pas d'onglets »). Elle empile : header → graphe héro → KPI → 5 blocs générés par
`charts.js::fundamentalGroups()` (Croissance & tendance, Rentabilité & efficience, Solvabilité,
Valorisation, Dividende) → données manuelles. Sur un écran, retrouver « la solvabilité » ou « le
dividende » impose de parcourir toute la page.

Trois points d'entrée mènent à cette fiche : l'autocomplétion (`search.js::pick`), le screener
(`screener.js::selectRow`) et la composition d'un indice (`indices.js::openMember`). Tous
convergent vers `load()` / `loadIndex()` — c'est le point unique à préserver.

Le cadrage produit (`amélioration/`) définit une **barre latérale persistante** par section
(maquette `company-analysis.svg`) et une **section unique affichée** (décision du 25/09).

## 2. Objectif

Pouvoir consulter une section précise de la fiche **sans parcourir le reste**, via un rail
vertical d'icônes à gauche, et pouvoir **partager / recharger** une fiche directement sur une
section (`#RI.PA/quantitatif`).

## 3. Non-objectifs

- **Pas de refonte du contenu** des sections : cette fiche pose la **coquille** (navigation +
  répartition). Le détail de chaque section est traité aux étapes 2 → 7.
- **Pas de mobile** : le responsive est explicitement hors périmètre.
- **Pas de changement backend** : les données existent déjà dans `/api/stock`.
- Pas de nouvelle dépendance, pas de bundler (front sans build).

## 4. Exigences

- 4.1 Rail vertical à gauche : 6 entrées `Résumé · Quantitatif · Dividende · Finance ·
  Thèse & Société · Valorisation`, icône seule, **libellé au survol** (infobulle).
- 4.2 **Une seule section affichée** à la fois ; entrée active marquée.
- 4.3 Les graphes (héro + mini-charts) sont **redessinés au changement de section** (un graphe
  masqué par `x-show` a une taille nulle : Plotly ne peut pas le tracer).
- 4.4 Deep-link `#<ticker>/<section>` : lecture au chargement, écriture au clic, bouton retour
  du navigateur fonctionnel.
- 4.5 Répartition des cartes existantes : Quantitatif = croissance + rentabilité + **solvabilité** ;
  Valorisation = multiples ; Dividende = dividendes & rachats.
- 4.6 Les 3 points d'entrée ouvrent sur **Résumé** par défaut.
- 4.7 Aucun seuil ni formule dupliqué : `config.py` → `/api/meta` reste la source unique.

## 5. Critères d'acceptation

- [x] Rail de 6 sections, ordre validé, état actif, navigation clavier (`aria-current`, focus visible)
- [x] Une seule section affichée ; graphes redessinés au changement de section
- [x] Deep-link `#TICKER/section` (lecture, écriture, retour navigateur)
- [x] Les 3 points d'entrée ouvrent sur Résumé
- [x] Layout 2 colonnes desktop (mobile hors périmètre)
- [x] `app.js` < 500 lignes, 0 `fetch` hors `api.js`
- [x] Calibration Pernod (`z = −3.81`) inchangée — `pytest -m network` vert
- [x] 35 tests unitaires dédiés (`web-tests/sections.test.js`) + 7 e2e
- [x] Aucun changement de calcul backend (374 tests hors réseau verts)

### Corrections issues de la revue de code

- [x] **Sections sans contenu** : le rail désactive les entrées vides (un ratio/indice
  n'a pas de comptes) avec un titre explicatif.
- [x] **`amélioration/` + `.DS_Store`** ajoutés au `.gitignore` (12 Mo de PDF tiers).
- [x] **Rafraîchir ne quitte plus la section** : `applySectionsAfterLoad()` distingue
  changement de fiche (→ Résumé) et refresh de la même fiche (→ section conservée).
- [x] **Redraw différé** : `scheduleRedraw()` attend que les conteneurs `.mini-chart`
  existent réellement (un `$nextTick` ne suffit pas — bug confirmé par un e2e qui
  vérifie le rendu, pas seulement les titres).
- [x] **Mapping carte→section** : `card(section, c)` rend la section obligatoire,
  plus de repli silencieux vers Quantitatif.
- [x] **Deep-link vers une section indisponible** : `_sectionUsable()` replie sur
  « Résumé » (`applySectionsAfterLoad`, `onHashChange`, `setSection`) — plus d'écran
  blanc sous le header.
- [x] **Refresh d'un ratio / d'un indice** : `_hashRef()` renvoie une clé stable pour
  les trois types de fiche (`RI.PA`, `CW8.PA/SPY`, `INDEX:7`) au lieu de `null`.
- [x] **« Thèse & Société »** : `PLANNED_SECTIONS` + `sectionTitle()` distinguent
  « à venir » (contenu non construit) de « aucune donnée pour ce titre ».
- [x] **README** : section Fonctionnalités réécrite (rail de 6 sections, une seule
  affichée, deep-link) — la description « 5 sections en scroll continu » était périmée.

### Étape 2 — Résumé : grille de synthèse (J3)

- [x] 9 cartes de synthèse (PROFIL · MARCHÉ · VALORISATION · DIVIDENDE · CA · EPS · MARGES ·
  RENTABILITÉ · SANTÉ) — vue rapide non interactive, sans graphe
- [x] Module pur `engine/summary_fundamentals.py` (Altman Z, Piotroski, ROIC, marges, CAGR…)
- [x] `Identity` étendue (industrie, site, bêta, 52S, volumes) + `Fundamentals.market/health_rows/estimates`
- [x] Consensus analystes (croissance CA/EPS à 1 an) étiquetés « consensus »
- [x] Seuils source unique (`config.SUMMARY_COLORS`, capi, zones) servis par `/api/summary-meta`
- [x] `web/summary.js` + `.summary-grid` (3 colonnes) ; `app.js` < 500 l., 0 `fetch` hors `api.js`
- [x] Altman Z / Piotroski exclus pour les financières ; ISIN/PEA/sous-industrie/WACC retirés
- [x] Horizons 1A/5A/10A calculés sur l'historique réel, `--` si non couvert (jamais extrapolé)
- [x] 18 tests unitaires engine + test API payload + 11 tests front (`web-tests/summary.test.js`)

### Corrections issues de la revue (étape 2)

- [x] **%CAPEX/CA** ajouté à la carte Marges (poste `Capital Expenditure` préparé par `data/`).
  Ligne volontairement **neutre** (pas de couleur) : l'intensité capitalistique dépend du
  secteur, ni bonne ni mauvaise en soi — assumé dans `config.py`.
- [x] **ROE/ROCE/ROIC 1A** ajoutés à la carte Rentabilité (dernier exercice, en plus des
  moyennes 5A) et **colorés comme les 5A** (`config.SUMMARY_COLORS`).
- [x] **Infobulle financière** : Altman Z et Piotroski portent une note courte « Non applicable
  aux financières » (champ `SummaryRow.note`, exposé au front, affiché une seule fois sous la
  valeur — pas de doublon `:title`).
- [x] **Multiples neutralisés** : un multiple ≤ 0 (P/B négatif = capitaux propres négatifs,
  P/E ou P/FCF sur base négative) affiche `--` au lieu d'un nombre trompeur.
- [x] **« Prix juste »** = droite de régression sur la **fenêtre 20 ans** (cours brut,
  série de la valorisation). Ce n'est PAS la distance σ du KPI (historique complet) ni la
  droite du graphe (série ajustée, fenêtre visible) : trois lectures distinctes, documentées.
- [x] **Cache** : marqueur `MODEL_VERSION` (`Identity`/`Fundamentals`) — un objet caché d'une
  version antérieure du modèle est re-fetché au lieu de servir une grille incomplète.

### Étape 2bis — Résumé : densification et lisibilité (revue UX)

- [x] **KPI** : suppression du KPI « Qualité de l'exploitation » (orphelin sur une 2ᵉ ligne) ;
  la qualité reste lisible via la carte PROFIL (« Note quantitative » sur 20) → 5 KPI, 1 rangée
- [x] **Carte matrice « Croissance »** : CA + EPS fusionnés (lignes CA/EPS × colonnes 1A/5A/10A/
  Futur) — fin des deux cartes jumelles ; `SummaryCard.columns` + `SummaryRow.cells`/`cell_good`
- [x] **Grille masonry** (`columns: 3 240px` + `break-inside: avoid`) : plus de trou vertical,
  8 cartes au lieu de 9
- [x] **Densification** : paddings/gaps/polices réduits (~15-20 % de hauteur en moins)
- [x] **Carte vedette** Valorisation plus sobre (jauge et valeur compactées)
- [x] Aucun seuil littéral ajouté au JS ; `/api/meta` et `/api/summary-meta` inchangés
- [x] Tests : engine (matrice fusionnée), API (8 cartes), front (`summaryColumns`/`summaryCell`)

## 6. Invariants préservés

- La calibration Pernod (`z = −3.81`, ±0.15) reste verte.
- La régression reste calculée aux trois endroits (serveur, `drawChart`, `computeLive`).
- `config.py` reste la seule source des seuils (aucun seuil littéral ajouté au JS).
- Les 3 points d'entrée (recherche, screener, indice) continuent d'ouvrir la fiche.
- `app.js` reste le composant seul, < 500 lignes ; aucun `fetch` hors `api.js`.

## 7. Jalons

- **J1 — Étape 0 : coquille.** Rail + section unique + deep-link + répartition des cartes.
  ✅ fait.
- **J2 — Étape 1 : organisation.** Vérifier la répartition, ajuster les titres de blocs. ✅ fait.
- **J3 — Étape 2 : Résumé.** Grille de synthèse fondamentale ✅ fait — 9 cartes initialement,
  ramenées à **8** par la revue UX (CA+EPS fusionnés en carte matrice « Croissance », KPI Qualité
  retiré).
- **J4 → J8 — Étapes 3 → 7.** Une section par étape, dans l'ordre : Quantitatif,
  Dividende, Finance, Thèse & Société, Valorisation. ✅ toutes faites — Quantitatif (#18),
  Dividende (#19), Finance (#22/#23), Thèse & Société (#21), Valorisation (#20).

## 8. Note de reprise

**Fait (J1).** `src/obole/web/sections.js` (nouveau) porte le registre `SECTIONS` + le mixin de
navigation (`setSection`, `parseHash`, `onHashChange`, `applySectionsAfterLoad`,
`scheduleRedraw`, `redrawActiveSection`). `charts.js` expose `sectionGroups()` /
`sectionAvailable()` qui filtrent `fundamentalGroups()` sur `activeSection` ; la section est un
paramètre obligatoire de `card(section, c)`. `index.html` a un `aside.rail` + une div
`.fiche-main` ; les blocs sont conditionnés par `x-show="activeSection === '…'"`.
`app.js` monte `sectionsMixin`, garde `init()` idempotent (`_initialized` : Alpine appelle
`init()` deux fois) et lit le hash APRÈS le chargement des seuils `/api/meta`.

**Fait (J3 — Étape 2 : Résumé).** Grille de synthèse fondamentale, vue rapide **non
interactive** (valeurs seules, aucun graphe, aucun clic), placée après les KPI de la section
Résumé. 8 cartes (revue UX) : PROFIL · MARCHÉ · VALORISATION · DIVIDENDE · CROISSANCE (CA+EPS) ·
MARGES · RENTABILITÉ · SANTÉ.

- **Backend.** `engine/summary_fundamentals.py` (nouveau, **100 % pur**) calcule la grille
  (`build_summary`) ; `models.py` porte `SummaryCard`/`SummaryRow` (+ `StockAnalysis.summary`) ;
  `Identity` est étendue (`industry`, `website`, `beta`, `week52_low/high`, `volume`,
  `avg_volume`) ; `Fundamentals` porte `market` (instantanés `info`), `health_rows` (postes
  bruts de bilan/CF) et `estimates` (consensus analystes). `services/analysis.analyze`
  orchestre ; `api/serialize` expose `identity` étendue + `summary`.
- **Seuils.** `config.SUMMARY_COLORS` (polarité couleur des lignes), `MARKET_CAP_LABELS`,
  `ALTMAN_ZONES`, `PIOTROSKI_ZONES`, `SUMMARY_GROWTH_HORIZONS` — **source unique**, servie au
  front par une route dédiée **`GET /api/summary-meta`** (séparée de `/api/meta`, dont la liste
  de champs est verrouillée par un test de parité).
- **Front.** `web/summary.js` (nouveau mixin) + `thresholds.js` (`applySummaryMeta`,
  `summaryGood`, `zoneLabel`, `marketCapLabel`). Grille CSS `.summary-grid` (3 colonnes desktop).
- **Décisions produit.** « Prix juste » = valeur de la droite de régression **sur les 20
  dernières années, cours brut** (série de la valorisation) ; « Prix communiqué » = dernier
  cours. À ne pas confondre avec le KPI « distance σ » (historique complet, méthode de la droite) ni
  avec la droite du graphe (série ajustée, fenêtre visible) : trois lectures distinctes.
  « Note quantitative » = `quality_score` ÷ 5 (sur 20).
  ISIN et PEA **retirés** (données non fiables : ISIN absent chez Yahoo ⇒ PEA indétectable).
  Sous-industrie et WACC **exclus** (n'existent pas / non calculables). Horizons 1A/5A/10A
  calculés sur l'historique réel (yfinance ≈ 5 ans + données manuelles) : un horizon non couvert
  affiche « -- », jamais extrapolé. Altman Z et Piotroski **uniquement industrielles** (exclus
  pour les financières).
- **Cache.** `_fresh_cached()` + `MODEL_VERSION` dans `data/yahoo` invalident les objets
  cachés d'une version antérieure du modèle (un cache 7 j peut ne pas porter les nouveaux
  champs, ex. `capex` dans `health_rows`).

**Pièges identifiés.** (1) Un graphe masqué par `x-show` a une taille nulle : Plotly ne peut pas
le tracer → `scheduleRedraw()` attend que les conteneurs `.mini-chart` existent (un `$nextTick`
unique ne suffit pas, Alpine flush après). (2) `render_index` est `lru_cache` : après une
modification de `index.html`, il faut **redémarrer le serveur** (pas de `--reload`).

**Prochaine action.** Aucune — chantier clos. Les étapes 3 → 7 sont livrées par #18 (Quantitatif),
#19 (Dividende), #22/#23 (Finance), #21 (Thèse & Société) et #20 (Valorisation).

**Prototype.** `amélioration/prototypes/coquille.html` (non versionné) : coquille statique pour
valider l'ordre et le rendu du rail avant implémentation.
