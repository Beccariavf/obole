# #20 — Fiche entreprise : section Valorisation (calculatrice de prix juste)

> **Statut :** en cours · **Priorité :** 🟡 Q2 (important, non urgent — cas (c) évolutivité)
> **Impact Pernod :** 🟠 · **Branche :** `feat/valorisation-fiche` · **Taille :** ~1 session
> **Fiche parente :** #16 (refonte fiche) — étape 7 « Valorisation ».
> **Précédents :** #18 (Quantitatif), #19 (Dividende) — même patron de taxonomie.

---

## 1. Contexte

La section Valorisation était réduite à des cartes multiples produites en dur dans
`charts.js::fundamentalGroups` (Multiples de résultat, PEG, EV/EBITDA, P/B, FCF yield).
La maquette cible (captures Baggr) demande une **calculatrice de prix juste** pleine
largeur : trois KPI (prix juste, rendement estimé, marge de sécurité), une bascule
Graphique/Matrice, un volet Paramètres, puis des **courbes continues** de croissance
par action et de multiples.

## 2. Modèle mathématique (rétro-ingénierie de la matrice Baggr)

Validé par fit global sur 45 cellules (RMSE 0,01 pt) :

```
R(g, m) = (1 + g) × (m / m0)^(1/H) − 1 + D
```

- **H** = horizon de projection = **5 ans** (`config.VALUATION_HORIZON_YEARS`).
- **m0** = multiple COURANT (cours / métrique par action la plus récente).
- **D** = rendement du dividende (0 quand la case « Inclure les dividendes » est décochée).
- Équivalent à `(Valeur projetée / Cours)^(1/H) − 1 + D`.

Dérivés :
- **Prix juste** = prix d'ENTRÉE qui fait atteindre la cible : `Valeur projetée / (1 + (cible − D)/100)^H`
  (inverse de `estimated_return`). Il dérive des hypothèses saisies (croissance, multiple de
  sortie, horizon, dividende) — c'est le KPI de tête, libellé « Prix juste (objectif X %/an) ».
- **Valeur médiane** = Métrique × multiple médian historique (valeur intrinsèque, info secondaire).
- **Valeur projetée** = Métrique₀ × (1 + g)^H × multiple de sortie.
- **Marge de sécurité** = (Prix juste − Cours) / Prix juste.
- **Cible** (12 %/an par défaut) = benchmark ; le rendement estimé est comparé à la cible
  et l'échelle de couleur de la matrice s'y accroche (vert dès la cible).

**Bridge EV → capitaux propres** (multiple d'entreprise, EV/EBITDA) : la valeur par action
est `EBITDA/action × multiple − dette nette/action`.

## 3. Objectif

Une section Valorisation **cohérente avec la méthode** : déterminer un prix juste à partir
de deux hypothèses (croissance, multiple), visualiser l'objectif sur le graphique et la
matrice de sensibilité, comparer le rendement estimé au benchmark, et **enregistrer** le
prix juste pour qu'il alimente la synthèse « Résumé ».

## 4. Non-objectifs

- Pas de DCF (chantier IA futur, PRD §12).
- Pas de Monte-Carlo.
- Pas de comparaison vs pairs (vient avec le screener).
- Pas de modification de la formule de régression (invariant métier).

## 5. Exigences

- 5.1 **Taxonomie unique** `config.VALUATION_METRICS` (5 bases : Bénéfices/Action→PER,
  FCF/Action→P/FCF, CA/Action→P/CA, Actif net/Action→P/B, EBITDA→EV/EBITDA) et
  `config.VALUATION_GROUPS` (cartes `vline`), servies par `/api/meta`.
- 5.2 **Calculatrice pleine largeur** : en-tête + 3 KPI + segmented control Graphique/Matrice.
  **Layout vertical** : graphique/matrice pleine largeur, volet Paramètres en dessous (grille
  de champs responsive).
- 5.3 **Volet Paramètres** : Données utilisées, Période historique, Croissance estimée
  (+ « Prévisions » consensus), Multiple final estimé (+ « médiane N A »), Rendement cible,
  « Inclure les dividendes », Enregistrer / Télécharger / Réinitialiser. **Pas de ligne
  « Communauté »** (inexistante en mono-poste).
- 5.4 **Vue Graphique** : cours (bleu) + valorisation (métrique × multiple médian, or) +
  dividende/action (brun) + **projection pointillée** vers le prix projeté + **badges prix
  juste et projeté** + ligne de prix juste (pointillés) + **légende CAGR** des séries.
- 5.5 **Vue Matrice** : heatmap croissance × multiple → rendement, cellule active encadrée,
  échelle rouge/brun/jaune/vert ancrée sur la cible.
- 5.6 **Recalcul 100 % client** : miroir JS de `engine/valuation_calc.py` (référence),
  verrouillé par une **fixture de parité** partagée.
- 5.7 **Persistance par ticker** (`valuation_settings`, schéma v3) : « Enregistrer » fixe le
  prix juste, « Réinitialiser » l'efface. Le Résumé affiche le prix juste enregistré s'il
  existe, sinon la droite de régression 20 ans.
- 5.8 **Courbes continues (partie 2)** : Croissance (BNPA/action, FCF/action, CA/action,
  Actif net/action — pastille **CAGR de la fenêtre**) et Valorisation (P/E, P/FCF, P/CA, P/B,
  EV/EBITDA — pastilles High/Médiane/Low) — jamais de barres, patron du Dividend Yield (série
  pleine résolution décimée serveur, alignée 1:1 sur `chart.dates`), **axe borné à la
  disponibilité réelle** de la série, **fenêtre par défaut + zoom plein écran** (bouton ⤢,
  presets de période, curseur à deux poignées partagé avec le héro).
- 5.9 **Télécharger** : CSV (paramètres + séries + matrice).
- 5.10 Périmètre : actions uniquement (ratio/indice → section désactivée).

## 6. Critères d'acceptation

- [x] Taxonomie `config.VALUATION_METRICS` / `VALUATION_GROUPS` = source unique (`/api/meta`),
      testée API + parité front.
- [x] `engine/valuation_calc.py` **pur** (zéro I/O, aucun import `data/`/`services/`).
- [x] Formule validée au 0,01 pt sur la matrice Baggr (`test_valuation_calc.py`).
- [x] Parité JS/Python verrouillée par fixture (`valuation_parity.json`).
- [x] Calculatrice : KPI, segmented control, volet Paramètres, graphique, matrice.
- [x] Vue Graphique complète : badges prix juste + prix projeté (annotations), projection
      pointillée, légende CAGR des séries.
- [x] Courbes continues (patron Dividend Yield) : 4 croissance + 5 valorisation, avec
      **zoom plein écran** (bouton ⤢, presets, curseur partagé), fenêtre par défaut et
      **axe borné à la disponibilité réelle**.
- [x] Pastilles du groupe Croissance = **CAGR de la fenêtre affichée** ; groupes de multiples
      = High/Médiane/Low.
- [x] Layout vertical pleine largeur (volet Paramètres sous la calculatrice).
- [x] Recalcul live côté client (aucun aller-retour réseau).
- [x] Persistance par ticker + override du prix juste dans le Résumé (schéma v3).
- [x] Bridge EV → capitaux propres pour EV/EBITDA.
- [x] Aucun seuil littéral JS (horizon, cible, grille, couleur depuis `config.py`).
- [x] `app.js` < 500 l., 0 `fetch` hors `api.js`.
- [x] Calibration Pernod inchangée — `pytest -m network` vert.
- [x] Tests : engine (42), API (7 valuation), schéma (4), front (17 + 12 parité), e2e (5).

## 7. Invariants préservés

- La calibration Pernod (`z = −3.81`, ±0.15) reste verte.
- La régression reste calculée aux trois endroits (serveur, `drawChart`, `computeLive`).
- `config.py` reste la seule source des seuils et de la taxonomie des cartes.
- `app.js` reste le composant seul, < 500 lignes ; aucun `fetch` hors `api.js`.

## 8. Note de reprise

**Fait.** Backend : `engine/valuation_calc.py` (pur), `config.VALUATION_*` (taxonomie, horizon,
grille, couleur, hauteur), table `valuation_settings` (schéma v3), séries continues de multiples
et payload calculatrice dans `services/analysis.py`, routes `GET/PUT/DELETE /api/valuation/<ticker>`,
`/api/meta` étendu. Front : `web/valorisation.js` (miroir de la formule + UI), section dans
`index.html`, CSS `.val-*`, `sections.js`/`charts.js` câblés, `thresholds.js` étendu.

**Décisions.** Recalcul **100 % client** (cohérent avec la régression, test de parité). Séries
de multiples **continues** par report de palier du dénominateur annuel (le cours bouge au
quotidien). « Communauté » **supprimée** (mono-poste). Bridge EV pour EV/EBITDA (numérateur ≠ cours).

**Pièges.** (1) BNPA dilué est DÉJÀ par action : ne pas le rediviser par les actions.
(2) `valuation_rows` doit être libéré APRÈS le calcul des séries d'entreprise. (3) La section
Valorisation rend ses cartes par un template dédié : ne pas les exposer via `sectionGroups()`
(doublon + ordre inversé). (4) `:class` avec objet dans `x-for` ne fonctionne pas sous Alpine →
méthode `valCellClass`. (5) Cache comptes 7 j : `POST /api/refresh/<ticker>` pour tester.
(6) Les courbes de la partie 2 doivent être extensibles comme le Dividend Yield : brancher
`isValuationCard` dans `openChartDetail` et une branche `vline` dans `drawChartDetail`, sinon
le bouton ⤢ n'apparaît pas (vérifié par un e2e). (7) Un badge d'annotation au bord droit du
graphe est rogné : `xanchor: "right"` pour le badge de prix juste.

**Corrections post-vérification.** Vue Graphique complétée (badges prix juste + projeté,
projection pointillée, légende CAGR) et zoom plein écran câblé sur les courbes de la partie 2
(bouton ⤢, branche `drawChartDetail`/`drawValueLine` avec plage, presets, curseur partagé).

**Corrections post-revue (8 constats).** (1) Panneau `info-panel` + textes d'infobulle ajoutés
pour les 7 cartes de la partie 2 (le ⓘ affichait le vide) ; (2) `fair_price` NULLABLE côté API
(bouton Enregistrer désactivé + message si incalculable, plus de 422 technique) ;
(3) contrat serveur corrigé (le prix juste vient du client, miroir testé — `net_debt_per_share`
désormais persisté, plus de champ mort) ; (4) bloc mort `b4` de `fundamentalGroups` et ses
`infoText` orphelins supprimés (la section a sa propre taxonomie) ; (5) `valMatrix()` mémoïsé
sur la clé de ses entrées (fini les ~50 k évaluations par rendu) ; (6) `confirm()` sur
« Réinitialiser » (cohérent avec les autres gestes destructeurs) ; (7) code mort retiré
(`safe_ratio`, `cagr_series`, `diluted_eps`, import `VALUATION_TARGET_DEFAULT`, `valLoaded`) ;
(8) commentaire orphelin de `services/analysis.py` supprimé.

**Corrections UX (4 points).** (1) Partie 1 en **colonne unique** : `.val-layout` en
`flex-direction: column`, le volet Paramètres passe SOUS le graphique/matrice (pleine largeur) ;
les champs se répartissent en grille responsive `.val-fields` (`auto-fit minmax(180px,1fr)`),
actions sur une ligne. Hauteurs **inchangées** (cohérence config.py ↔ CSS). (2) Groupe
« Croissance » étendu de 2 à **4 courbes** : `CA par action` (`sales_ps`) et `Actif net par
action` (`book_ps`) ajoutés ; `infoText` complété (`CA-par-action`, `Actif-net-par-action`).
(3) Pastilles du groupe Croissance = **CAGR de la fenêtre affichée** (« Croissance : X %/an »,
bleu si ≥ 0) au lieu de High/Médiane/Low — c'est la valeur qui alimente la saisie « Croissance
estimée ». Le choix est porté par `config.VALUATION_GROUPS[].pills` ("cagr" vs absent) propagé
aux cartes ; les groupes de multiples gardent High/Médiane/Low. (4) `drawValueLine` **borne
l'axe X à la disponibilité réelle** de la série (`_seriesAvailableRange` : premier/dernier point
non nul, intersecté avec la plage curseur en modale) : une série de ~5 ans n'est plus étirée sur
la fenêtre calendaire par défaut ; stats et CAGR calculés sur la même plage bornée.

**Corrections post-revue UX (7 constats).** (1) Changer la base ou la période **ré-amorce**
le multiple sur la nouvelle médiane (`valOnBase`) — fini l'indice « médiane N A » contredisant
le champ ; les « Prévisions » (consensus BNPA) ne s'affichent plus que pour la base
« Bénéfices/Actions ». (2) Le KPI est libellé « **Prix juste (médiane N ans)** » : il s'appuie
sur la médiane historique, distincte du « Multiple final estimé » qui pilote le rendement —
plus de contrôle qui semble cassé. (3) Test d'entreprise via `def.enterprise` (plus de
comparaison de chaîne `"EV / EBITDA"` en dur). (4) Fixture de parité **étendue** à
`matrix_grid`/`return_matrix`/`color_bucket` (4 grilles) — la dérive Python↔JS de la matrice
est désormais verrouillée, plus seulement par des attentes dupliquées. (5) `downloadValuation`
réutilise le chemin CSV du projet (`_csvCell` + `_downloadCsv`, séparateur « , », décimales à
point) au lieu d'un format « ; » divergent. (6) Légende CAGR : un multiple d'entreprise est
étiqueté par son multiple (EV/EBITDA) et non « EBITDA ». (7) Helpers d'actions **mutualisés** :
`_shares_by_year` (avec repli `sharesOutstanding`) alimente la Valorisation via
`_shares_for_year` (repli « exercice le plus proche ») — la section n'est plus masquée pour une
société sans ligne « Actions en circulation » alors que le Dividende savait calculer.

**Corrections post-revue (polish, 2 constats).** (1) **État désactivé des boutons** : ajout d'une
règle générique `.btn:disabled { opacity:.45; cursor:not-allowed }` (absente jusqu'ici) — les
actions icônes de la calculatrice (Enregistrer désactivé si prix incalculable, Réinitialiser
pendant l'enregistrement) affichent désormais un état inactif visible. (2) **Garde-fou e2e
breakout** : l'assertion « les autres sections gardent leur largeur » ciblait le premier `.section`
du DOM (carte héro du Résumé, masquée → largeur 0, assertion vide de sens) ; elle sélectionne
maintenant la section RÉELLEMENT visible (`getBoundingClientRect().width > 0`, hors breakout) et
exige une largeur > 0 — le test mord vraiment.

**Prochaine action.** Rien — chantier prêt à fusionner (CI verte).

**Polish design (2e passe).** (1) **Boutons d'action en icônes** : Enregistrer/Télécharger/
Réinitialiser passent en boutons carrés 34px SANS emoji (SVG inline monochrome `currentColor`,
`title` + `aria-label`), alignés à droite de `.val-bar-foot` ; plein accent / ghost. (2) **Points
annuels** : les courbes de croissance (lissées) reçoivent un marqueur discret (cercle blanc bordé
bleu, size 6) à chaque exercice ; les multiples restent nets, sans marqueur. (3) **Graphe prix
juste étalé** (« breakout » ciblé) : la section Valorisation déborde de son conteneur pour offrir
~1120px au graphe (vs 942px), via un débordement **calculé et borné**
(`-max(0px, min(180px, (100vw-1100px)/2 - 24px))`) → **aucun impact sur `.wrap` ni les autres
sections** (Résumé/Quantitatif/Dividende inchangés), aucun scroll horizontal, débordement nul sur
écran étroit. Échelle **linéaire conservée**, hauteur 560px inchangée. (4) **Fond doré pâle +
projection dorée** (rendu Baggr, variante A) : la ligne de valorisation du hero porte un fond
`tozeroy` or très pâle (`rgba(245,158,11,.08)`) + marqueurs annuels dorés ; la projection vers
l'horizon devient une **ligne pointillée dorée** (au lieu du gris) et le fond se poursuit jusqu'à
la cible projetée — on lit d'un coup la sous/sur-évaluation vs le cours bleu.

**Refonte design (Option A, 4 demandes).** (1) **Barre Paramètres compacte** : le pavé pleine
largeur devient UNE rangée dense de 6 champs (labels courts au-dessus) sous le graphe, les 3
actions remontées à droite du titre. Repli 3 colonnes < 1000px, 2 colonnes < 720px. (2) **Toggle
Graphique/Matrice déplacé** au-dessus de la zone de données, **sans emoji** (texte seul). (3)
**Matrice entièrement visible** : libellés et valeurs à **1 décimale** (`valNum1`), table en
`table-layout: fixed` → 15×15 tiennent dans 942px, **aucun scroll horizontal**. (4) **Graphe
prix juste rehaussé** : `CHART_HEIGHT_VALUATION_HERO` 420 → **560** (ratio 942×560 ≈ 1,68:1),
les 3 emplacements alignés (config.py, thresholds.js, var CSS). (5) **Courbes lissées** :
séries en escalier des cartes de **Croissance** réduites à leurs **coins** (`_stepCorners`) et
tracées en `spline` (`smoothing: 0.3`) — coins arrondis façon Baggr, **bleu inchangé** ; les
multiples restent nets. (6) **Ligne de valorisation en OR `#F59E0B`** et lissée (même
traitement), sur le seul graphique du prix juste.

**Refonte sémantique du prix juste (option B).** Le KPI de tête « Prix juste » n'est plus la
valeur médiane (métrique × multiple médian) mais le **prix d'entrée qui fait atteindre le
rendement cible**, dérivé des hypothèses saisies : `Valeur projetée / (1 + (cible − dividende)/100)^H`.
Motif : l'ancien KPI ignorait le champ « Multiple final » (le rendement changeait, le prix juste
non) — incohérence signalée par l'utilisateur (ELEC.PA, base Actif net : 151,58 € médiane vs
116,16 € pour atteindre 12 %/an avec g=2 %, multiple 1,3). Ajouts : `engine/valuation_calc.py::target_entry_price`
(pur, inverse de `estimated_return`), miroir `web/valorisation.js::targetEntryPrice`,
`valMedianValue()` pour la valeur médiane (désormais hint « Valeur médiane N A » sous la barre),
libellé KPI « Prix juste (objectif X %/an) ». Fixture de parité étendue (`target_entry_price` par
cas, champ `target`). `fair_price` persisté = nouvelle notion ; le Résumé suit.

