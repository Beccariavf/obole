# #27 — Conviction → tiers par seuils absolus

> **Statut :** **fait** · **Priorité :** 🟡 Q2 · **Impact Pernod :** 🟢
> **Branche proposée :** `feat/conviction-tiers` · **Taille :** 1 session
> **Plan :** `aidd_docs/tasks/2026_10/2026_10_26_conviction-tiers/`
> **Fiche parente :** #26

> **Convention de traçabilité.** Ne jamais citer de SHA ; décrire le jalon.

---

## 1. Contexte

Le jeu de convictions (#26) proposait des tiers en **conservant les effectifs actuels**
(`conviction.js::suggestTiers`) et affichait un **percentile** 0-100 (`convictionScore`).
L'utilisateur veut que le résultat **classe directement** les entreprises, avec un seuil de
conviction par tier réglable. Ces deux fonctions ont été **supprimées** à la livraison de
#27 : la règle de tiers vit désormais dans `tierForIndex` / `suggestTiersByThresholds`.

Le débat contradictoire du 2026-10-26 a établi qu'un seuil posé sur le percentile est un
**quota déguisé** : il y a toujours un 0 et un 100, et le nombre de Tier 1 change avec la
taille du groupe (5 valeurs : 1/2/2 ; 10 valeurs : 2/3/5 avec des seuils 80/50). La sortie
retenue est un **indice absolu** 0-100 dérivé du rating Elo, avec deux seuils.

## 2. Objectif

Après le minimum de duels, le jeu propose des tiers par **seuils absolus** (57/43 par
défaut, réglables dans Paramètres), peut laisser un tier vide, et applique les changements
par la route tier existante.

## 3. Non-objectifs

- Changer le schéma SQLite, les tables, les routes ou le MCP.
- Persister le score de conviction entre deux sessions.
- Appliquer les tiers sans confirmation.
- Hystérésis : testée à 24 points, elle bloquait une promotion légitime (1557 < 1574) ;
  elle est rejetée.
- Modifier la fiche, la référence ou la valorisation.
- Un nouveau moteur de régression ou de valorisation.

## 4. Exigences

### 4.1 Indice absolu

- `convictionIndex(rating) = 100 / (1 + 10^((1500 − rating)/400))`, arrondi à l'entier :
  1500 → 50, 1600 → 64, 1400 → 36.
- Le percentile ne pilote plus les tiers ; il peut rester un affichage de rang, mais aucun
  seuil ne s'appuie dessus.

### 4.2 Seuils

- `SETTING_DEFS` : `conviction_tier1_min` (défaut 57) et `conviction_tier2_min`
  (défaut 43), bornes 0-100, groupe `conviction`.
- Validation croisée : le seuil Tier 1 doit être **strictement supérieur** au seuil Tier 2
  (422 sinon).
- Les seuils sont lus via `GET /api/settings` **à l'ouverture du jeu** : aucun défaut
  dupliqué côté JS, et une modification dans Paramètres est prise en compte sans
  rechargement.

### 4.3 Règle de classement

- Tier 1 si l'indice ≥ seuil Tier 1 ; Tier 2 si ≥ seuil Tier 2 ; sinon Tier 3.
- Une valeur à **moins de 2 duels** garde son tier actuel (couverture insuffisante).
- Les tiers vides sont autorisés : la règle peut dire « personne ne mérite le Tier 1 ».
- Une valeur à **2 points ou moins** d'un seuil est signalée « limite » (bruit de mesure),
  sans changer la règle.

### 4.4 Résultat

- Rang, tier actuel → tier suggéré, indice 0-100 + nombre de duels, ligne des seuils,
  compteurs par tier, message « aucun changement », application.
- Les changements passent par `PUT /api/watchlist/items/<ticker>` ; aucune nouvelle route.
- Un tier vide est affiché avec son compteur à zéro, jamais comblé d'office.

### 4.5 Paramètres

- Une section « Conviction » dans la modale Paramètres, avec les deux champs et les actions
  Enregistrer / Rétablir partagées avec les autres réglages.
- Les seuils sont persistés dans la table `settings` existante ; aucune migration.

### 4.6 Tests et documentation

- Unitaires JS : indice, seuils, tier vide, couverture, badge limite.
- API : défauts, persistance, 422 sur inversion.
- E2e : résultat avec seuils, application, section Paramètres, responsive 390 px.
- Fiche #27, index `CHANTIERS.md`, invariant `CLAUDE.md`, mémoire `design.md`.

## 5. Critères d'acceptation

- [x] `convictionIndex(1500) = 50`, `convictionIndex(1600) = 64`, `convictionIndex(1400) = 36`.
- [x] Les priors 1600/1500/1400 tombent en Tier 1/2/3 avec les seuils 57/43.
- [x] AMUN 1557 → Tier 1 ; ENX 1470 → Tier 2 ; ACA 1532 → Tier 2.
- [x] Un tier peut être vide ; le résultat affiche « Tier 3 : 0 ».
- [x] Moins de 2 duels → tier conservé, badge « conservé ».
- [x] Seuils 60/40 persistés et relus ; 40/50 → 422.
- [x] Le résultat affiche les seuils, l'indice et les duels ; appliquer met à jour les tiers.
- [x] Aucun schéma, aucune route nouvelle, aucun outil MCP ; calibration Pernod inchangée.

## 6. Invariants préservés

- La calibration Pernod (`z = −3.81`, ±0.15) reste verte.
- La watchlist reste en total-return et la fiche en régression brute.
- La marge et le prix juste restent calculés côté serveur ; aucune formule déplacée.

## 7. Jalons

- **J1** — Moteur : indice absolu, affectation par seuils, couverture, badge limite, tests.
- **J2** — Réglages : `SETTING_DEFS`, validation croisée, section Paramètres, tests API.
- **J3** — Résultat : lecture des seuils, lignes enrichies, compteurs, application, tests.
- **J4** — Preuves : e2e, captures, fiche, index, `CLAUDE.md`, `design.md`.

## 8. Note de reprise

**Débat du 2026-10-26.** Deux agents se sont opposés : seuils absolus contre quotas par
rang. Le percentile a été écarté des deux côtés. L'utilisateur a retenu les **seuils
absolus** (option A). L'hystérésis proposée (marge 24) a été rejetée après mesure : elle
empêchait une valeur invaincue (1557) de franchir un seuil à 1550. Les seuils 57/43 sont
les milieux des ancres 1600/1500/1400 ; à couverture suffisante, ils reproduisent les
tiers actuels.

**Livré (jalons J1 à J4).**

- **Moteur** (`src/obole/web/conviction.js`) : `convictionIndex` (0-100, 50 = rating 1500),
  `tierForIndex`, `thresholdDistance`, `suggestTiersByThresholds`,
  `MIN_COMPARISONS_PER_ROW = 2`, `LIMIT_DISTANCE = 2`. `convictionScore` (percentile) et
  `suggestTiers` (effectifs) **supprimés** — plus aucun code de tiers ne les lit.
- **Réglages** : `conviction_tier1_min` (57) / `conviction_tier2_min` (43) dans
  `config.SETTING_DEFS`, groupe `conviction` après `technique`, bornes 0-100. Validation
  croisée dans `cache.set_settings` (« Le seuil Tier 1 doit être supérieur au seuil
  Tier 2 », 422). Aucune migration : la table `settings` existante suffit.
- **Résultat** : `openConviction` devient asynchrone et lit `GET /api/settings` à
  l'ouverture (aucun défaut dupliqué en JS, un seuil modifié est pris en compte sans
  rechargement) ; en cas de seuils inutilisables, message dans la modale et aucune paire.
  Le résultat affiche la ligne des seuils, l'indice et les duels, les badges « conservé »
  et « limite », les compteurs par tier (un tier vide reste à zéro) et le message « Aucun
  changement ». L'application passe par `PUT /api/watchlist/items/<ticker>`.
- **Preuves** : `web-tests/conviction.test.js` (moteur + mixin, dont la preuve que le
  moteur ne contient plus percentile ni effectifs), `tests/test_settings.py` (défauts,
  groupe, persistance 60/40, 422 sur 40/50), `web-tests/e2e/watchlist.spec.js` (parcours
  complet T3 → T2, cas sans changement, modale Paramètres) sur Chromium **et** WebKit.
  Captures : `captures/conviction-seuils.png`, `captures/conviction-seuils-390.png`,
  `captures/conviction-parametres.png`, `captures/conviction-parametres-390.png`.

**Pièges mesurés.**

- Le parcours e2e doit être **déterministe** : faire gagner OR.PA (Tier 3) à chaque duel où
  il apparaît donne toujours indice 47 → Tier 2, et les compteurs 1/3/0. Sans cette règle,
  l'issue dépend de l'ordre des paires (`nextPair` départage au hasard les égalités).
- `x-show` laisse le texte dans le DOM : `toContainText` ne prouve **pas** qu'un message
  est affiché. Les tests e2e attendent `toBeVisible()` (ou l'état du bouton) avant de
  vérifier les écritures séquentielles.
- À 390 px, le tableau de résultat masque la colonne Rang et le nom long, et resserre le
  cadran : sans cela la table dépassait la largeur de ~33 px.
- Les captures sont écrites par le seul projet Chromium (les deux moteurs partagent le
  dépôt) dans `captures/`, à la racine, et **seulement** avec `OBOLE_CAPTURE=1` : sans la
  variable, le run e2e ne touche pas au dépôt.

**Revue OpenFox (2026-10-26).** 24/24 critères passés, gate vert. Trois findings corrigés :
remise à zéro complète de la partie avant la lecture des seuils (un GET en échec ne laisse
plus « 12 / 12 » ni de boutons actifs), captures e2e opt-in pour ne pas salir le dépôt,
compteur du header masqué à 390 px avec capture régénérée.

**Prochaine action.** Aucune : chantier clos. Un réglage de seuils se fait dans
*Paramètres → Conviction* ; le jeu relit les seuils à chaque ouverture.

