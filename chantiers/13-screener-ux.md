# #13 — UX du screener (doublon capi, plein écran, filtres repliables, ancre de ligne)

> **Statut :** fait · **Priorité :** 🔵 Q3 (urgent, pas important — confort d'un outil qui marche)
> **Impact Pernod :** 🟢 · **Branche (historique) :** `feat/screener-ux` · **Taille :** ~1 session
> **Fiche parente :** `chantiers/screener.md` (le screener lui-même ; ici, uniquement l'UX)

---

## 1. Contexte

Quatre défauts d'usage constatés sur la modale screener (`src/obole/web/index.html`,
`src/obole/web/app.js`, `src/obole/web/style.css`), captures à l'appui :

1. **Doublon de capitalisation.** Deux champs de saisie de capi coexistaient : le champ global
   « Capi min univers (Md€) — restreint le scan (passe 1) » (`index.html`, rangée
   `idx-form-row`) **et** la paire « min Capi / max Capi » de la grille de pré-filtres
   (`_screenRangeCols()` dans `app.js`). Sémantiquement distincts (passe 1 Yahoo vs passe 2),
   mais indistinguables pour l'utilisateur.
2. **Espace perdu.** `.modal.modal-screen` était plafonnée à `max-width:1200px; max-height:92vh`
   (`style.css`) ; le tableau devait tenir dans la hauteur restante, amputée de tout le bloc de
   filtres empilé en haut.
3. **Filtres non repliables.** Le panneau occupait une hauteur fixe, sans possibilité de le
   masquer une fois le scan lancé.
4. **Perte d'identité de ligne.** Seuls les `thead th` étaient `position:sticky` ; aucune
   colonne n'était gelée. En scrollant horizontalement vers PER/P/B/FCF/Qualité, le nom de
   l'entreprise quittait l'écran — on ne savait plus quelle ligne on lisait.

## 2. Objectif

Rendre le screener confortable à lire et à filtrer : un seul champ de capitalisation, un
tableau qui prend toute la place disponible, des filtres qu'on peut replier, et une identité de
ligne toujours visible. Ajouter un écran d'accueil qui explique la méthode et propose des
presets cliquables.

## 3. Non-objectifs

- Pas d'extension Europe (J6, `chantiers/screener.md`).
- Pas de MCP screener (`chantiers/mcp/02-screener-fr.md`).
- Aucune modification du moteur, de l'API, du schéma ou des seuils.
- Pas de persistance des presets en base (YAGNI).
- Pas de filtre par colonne (piste notée pour plus tard, non retenue ici).

## 4. Exigences

- 4.1 Un **seul** couple de saisie « Capi (Md€) min/max ». Le champ global est retiré.
- 4.2 Le `min` capi alimente `min_market_cap` (passe 1 Yahoo **et** filtre passe 2) ; le `max`
  ne filtre qu'en passe 2. `min` vide → défaut serveur (1 Md€).
- 4.3 Panneau de filtres **repliable** (bouton « Filtres »), replié automatiquement après un
  scan réussi.
- 4.4 État replié = **chips** des filtres actifs + bouton « tout effacer ».
- 4.5 Modale **plein écran** ; le tableau occupe tout l'espace restant.
- 4.6 Première colonne **« Entreprise » gelée** (ticker + nom, ombre, z-index > thead) et survol
  de ligne visible sur toute la largeur.
- 4.7 Écran d'accueil : hero (méthode) + CTA + ≥ 3 presets cliquables pré-remplissant les
  filtres puis lançant le scan.
- 4.8 Aucun seuil métier en dur côté front : les presets composent uniquement les bornes
  exposées par `/api/screener/meta` (`colors`).

## 5. Critères d'acceptation

- [x] Un seul couple « Capi (Md€) min/max » ; plus aucune occurrence de « Capi min univers »
- [x] `min` capi → passe 1 + passe 2 ; `max` → passe 2 ; min vide → défaut 1 Md€
- [x] Panneau filtres repliable ; replié après un scan réussi
- [x] Chips récapitulatifs des filtres actifs + « ✕ tout » (aucun chip si aucun filtre)
- [x] Modale plein écran (98vw × 96vh), tableau en zone flexible
- [x] Colonne « Entreprise » gelée (`position:sticky left`), ombre, z-index > thead
- [x] Survol de ligne visible sur toute la largeur
- [x] Écran d'accueil : hero + CTA « Scanner l'univers FR »
- [x] 3 presets cliquables (Décotées de qualité, Rendement en cash, Croissance + tendance)
- [x] Zéro seuil en dur côté front (presets dérivés de `/meta`)
- [x] Aucune modification de `engine/`, `data/`, `api/`, `config.py`
- [x] `pytest -m "not network"` vert · `npm test` vert · `node --check` OK
- [x] E2E Playwright : accueil → preset → scan → colonne gelée
- [x] **Design A** : 4 groupes thématiques repliables, badge de filtres actifs visible replié
- [x] `min`/`max` en suffixe dans le champ (plus de placeholder redondant)
- [x] **Hiérarchie de tri** : priorité 1/2 sur les en-têtes + barre « Tri : … (cascade) »

## 6. Invariants préservés

- La calibration Pernod (`z = −3.81`, ±0.15) reste verte : le chantier est **front pur**.
- `engine/regression.py`, `engine/analysis.py`, `api/app.py`, `config.py` : inchangés.
- Aucun seuil dupliqué : `LABELS` / `RATIO_THRESHOLDS` / `SCREEN_COLORS` restent la source unique.
- Le contrat de l'API (`POST /api/screener/run`, `filters`, `sort_by`) est inchangé.

## 7. Jalons

- **J1** — Retirer le doublon capi, fusionner dans `screenerRanges.market_cap`.
- **J2** — Plein écran + colonne d'ancrage gelée + survol de ligne.
- **J3** — Filtres repliables + chips récapitulatifs.
- **J4** — Écran d'accueil (hero + presets) dérivé de `/meta`.
- **J5** — Test E2E + fiche.
- **J6 (design A)** — Filtres groupés par thème (repliables + badge) + suffixe min/max.
- **J7** — Hiérarchie de tri visible (priorité 1/2 + libellé récapitulatif).

## 7bis. Design A — groupes de filtres & hiérarchie de tri (J6-J7)

**Problème (J6)** : la grille à plat répétait le placeholder `"min Capi (Md€)"` sur 10 critères et
n'offrait aucune hiérarchie de lecture — « pas beau ».

**Solution** : 4 groupes thématiques repliables, mapping critère→groupe en **source unique**
(`_screenFilterGroups()`, libellés via `_screenCols()`) :

| Groupe | Critères |
|---|---|
| Taille | Capi |
| Technique | σ, Pente %, Écart-type %, Pot. 5a %, Pot. 10a % |
| Rentabilité | ROE %, Qualité |
| Valorisation | PER, P/B, P/FCF, FCF yield % |

- `min`/`max` passent en **suffixe interne** au champ (fin du placeholder redondant).
- Chaque groupe porte un **badge** du nombre de filtres actifs, **visible même replié**.

**Problème (J7)** : le tri était une cascade **lexicographique** — le 2ᵉ critère ne départage que
les égalités strictes du 1ᵉʳ. Avec des valeurs continues, il ne s'appliquait donc jamais, d'où
l'impression qu'il « ne servait à rien ».

**Solution** : rendre la cascade **explicite** — badge de priorité `1`/`2` sur les en-têtes +
barre « Tri : 1. ROE % ▼ · 2. P/FCF ▲ » avec mention « cascade ». Le classement par compromis
(score composite) est traité au **chantier #14**.

## 8. Note de reprise

**Fait** (branche `feat/screener-ux`).

Livré :

- `app.js` : `screenerFilters.min_market_cap` supprimé ; la capi vit dans
  `screenerRanges.market_cap` (min → `min_market_cap`, max → passe 2). Nouveaux helpers
  `screenerToggleFilters`, `screenerActiveFilters`, `clearScreenerFilters`,
  `screenerPresets`, `applyScreenerPreset`, `_screenTailCols`. État `screenerColors`
  alimenté par `/api/screener/meta`.
- `index.html` : en-tête avec bouton « Filtres », chips, panneau repliable, hero + presets,
  tableau à colonne d'ancrage.
- `style.css` : `.modal-screen` en 98vw × 96vh ; `.screen-col-anchor` sticky + ombre ;
  chips, presets, survol de ligne.
- `web-tests/e2e/screener.spec.js` : parcours accueil → preset → scan → colonne gelée.

**Correctif en cours de route** : `z` et `p_fcf` manquaient dans `screenerRanges` et
`_screenRangeCols()` — les presets « Décotées de qualité » (critère σ) et « Rendement en cash »
(P/FCF) étaient donc **silencieusement amputés**. Ajoutés.

**Correctifs de revue (6 findings)** :

1. **[HIGH] Preset « Rendement en cash » inversé** : `bound()` traitait `le_pos` (P/FCF, PER)
   comme `ge` → posait un **min**, donc sélectionnait les valeurs **chères**. Corrigé :
   `le_pos` → `[0, seuil]` (bon si 0 < v ≤ seuil). Vérifié : `p_fcf: [0, 10]`.
2. **[MEDIUM] `clearScreenerFilters` relançait avec une fenêtre périmée** : `regression_window`
   remis à `null` **avant** `resetScreenerRanges()` (qui relance `searchScreener()` de façon
   synchrone).
3. **[MEDIUM] E2E flaky** : `POST /api/screener/run` désormais **mocké** (`page.route`) — plus
   aucune dépendance réseau, 0.9 s au lieu de 60 s+. Assertion no-op (`hasText` sur input)
   remplacée par `getByText("Capi min univers")`.
4. **[LOW] Chips en doublon** : `x-show="!screenerFiltersOpen && screenerActiveFilters().length"`.
5. **[LOW] Presets inaccessibles après un scan** : nouveau bouton **« ← Accueil »**
   (`screenerBackHome()`) — remet à zéro sans fermer la modale.
6. **[LOW] Panneau rogné sur viewport court** : `.screen-filters-panel` en
   `max-height:45vh; overflow-y:auto`.

**Vérifié** : modale 1400×864 dans un viewport 1440×900 (plein écran effectif) ; 3 presets ;
0 occurrence de « Capi min univers » ; 1 champ min Capi + 1 max ; preset « Rendement en cash »
→ `p_fcf [0, 10]` (valeurs bon marché) ; colonne d'ancrage `position:sticky` et visible après
scroll horizontal ; E2E Chromium + WebKit 2/2 en < 3 s ; aucune erreur JS console.

**Reste** : rien de bloquant. Piste notée pour plus tard : filtre par colonne (au plus près de
la donnée).

**J6-J7 (design A + hiérarchie de tri)** — ajoutés :

- `_screenFilterGroups()`, `screenerGroupCols()`, `screenerGroupCount()`, `screenerToggleGroup()` ;
  état `screenerGroupsOpen`.
- `screenerSortRank()`, `screenerSortLabel()` ; barre `.screen-sort-bar`, badges `.screen-th-rank`.
- `screenerRanges` complété (`pot_10y_pct`, `p_b`) — les groupes couvrent les 12 critères.
  Garde-fou `filter(k => this.screenerRanges[k])` dans `screenerGroupCols()` pour qu'une
  divergence future ne casse pas l'UI (bug attrapé en vérification : `TypeError ... reading 'min'`).
- Bouton « ↺ tri » déplacé de l'en-tête vers la barre de tri (évite le doublon).

**Suite** : le classement par compromis (score composite) → **chantier #14**.
