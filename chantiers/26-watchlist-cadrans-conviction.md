# #26 — Watchlist 2.0 : vue cadrans, jeu de convictions, Pot. 5A de valorisation

> **Statut :** **fait** · **Priorité :** 🟡 Q2 · **Impact Pernod :** 🟠
> **Branche proposée :** `feat/watchlist-cadrans-conviction` · **Taille :** 4-5 sessions
> **Plan :** `aidd_docs/tasks/2026_10/2026_10_25_watchlist-cadrans-conviction/`
> **Fiche parente :** #25 / #25.1 / #25.2

> **Convention de traçabilité.** Ne jamais citer de SHA ; décrire le jalon.

---

## 1. Contexte

La watchlist est fonctionnelle (tiers, marges, référence, MCP) mais :

1. **l'affichage du tier est faux** dans le tableau : Amundi est bien en **Tier 2** en base
   et dans le filtre/compteur, mais son `<select>` affiche **Tier 1** ;
2. la vue est un tableau dense, peu visuelle pour comparer les **tiers** ;
3. il n'existe pas d'outil pour **tester ses convictions** entre deux valeurs et faire
   émerger un tier de confiance ;
4. le **Pot. 5A** d'une valeur avec un prix juste enregistré utilise encore la droite
   total-return, alors que l'utilisateur veut **l'estimation de sa valorisation**.

Le diagnostic du point 1 est fait : l'API et la base sont correctes (`AMUN.PA` tier 2, le
filtre Tier 2 l'affiche) ; c'est la liaison Alpine `<select :value="r.tier">` + options
`x-for` qui rend le select avant ses options et retombe sur la première (Tier 1).

## 2. Objectif

Une watchlist **lisible par tiers** (vue cadrans), un **jeu de comparaisons** qui propose
des tiers cohérents avec les choix, et un **Pot. 5A sourcé** : valorisation enregistrée si
elle existe, sinon droite total-return.

## 3. Non-objectifs

- Changer le schéma SQLite, les tables watchlist/références/valorisation.
- Écrire la référence ou le prix juste depuis le jeu (le jeu ne fait que proposer des tiers).
- Persister un score de conviction entre deux sessions (le résultat est la proposition de
  tiers, appliquée à la watchlist).
- Remplacer le tableau (il reste accessible par bascule).
- Modifier la vue référence brute de la fiche (#25.1) ni la valorisation elle-même.
- Un nouveau moteur de régression ou de valorisation.

## 4. Exigences

### 4.1 Affichage du tier

- Le `<select>` de tier affiche **le tier réel** de la ligne (1, 2 ou 3) au premier rendu,
  après un changement, et après un rechargement.
- Le changement met à jour la ligne, les compteurs, le filtre et la fiche sans
  incohérence.
- Test de non-régression sur AMUN (Tier 2) + un changement vers Tier 3.

### 4.2 Pot. 5A de valorisation

- Si un prix juste est **enregistré** (`valuation_settings.fair_price` non nul) : le
  Pot. 5A est le **rendement annuel estimé de cette valorisation au cours actuel**,
  dérivé du prix juste, de la cible, du dividende et de l'horizon 5 ans :
  `projeté = prix_juste × (1 + (cible − dividende)/100)^5`, puis
  `Pot. 5A = (projeté / cours)^(1/5) − 1 + dividende`.
  Source `valuation` (badge « valo »).
- Sinon : Pot. 5A = potentiel total-return de la droite (#25.2), source `regression`
  (badge « droite »).
- Le prix juste enregistré reste prioritaire pour la marge ; l'estimation ne remplace pas
  la marge, elle éclaire le Pot. 5A.
- La cohérence est verrouillée par un test : `estimated_return_from_fair` redonne
  `estimated_return` quand le prix juste vient de `target_entry_price`.
- Le champ `pot_5y_source` est additif (full + summary API, MCP) ; le Pot. 10A reste la
  droite et le dit (`pot_10y_source="regression"`).

### 4.3 Vue cadrans

- Trois colonnes de tier (Tier 1/2/3), chacune avec un **cadran** de la marge moyenne
  (ou « — » si vide) et le nombre de valeurs.
- Chaque valeur est une **carte** avec un **cadran de marge**, le z, le Pot. 5A + sa
  source, le prix juste + sa source, le sélecteur de tier, l'ouverture de la fiche et le
  retrait.
- Bascule **Cadrans / Tableau** ; les filtres, compteurs, couverture, « masquer sans prix
  juste enregistré » et la légende s'appliquent aux deux.
- Responsive : 3 colonnes → 1 colonne ; cadrans SVG accessibles (texte de la valeur) ;
  aucun nouveau seuil de label en dur ; pas de nouvelle dépendance.

### 4.4 Jeu de convictions

- Deux valeurs à la fois, toujours issues de la watchlist ; l'utilisateur clique celle
  en laquelle il a le plus de conviction.
- Modèle **Elo** avec la priorité du tier actuel (Tier 1 > 2 > 3) ; paires choisies par
  proximité de rating et faible nombre de comparaisons ; jamais la même paire deux fois de
  suite.
- Minimum **12 comparaisons** avant le résultat ; l'utilisateur peut continuer.
- Résultat : classement, score de conviction (percentile 0-100), tier actuel → tier
  suggéré, changements ; **les effectifs actuels par tier sont conservés** (reclassement).
- « Appliquer les tiers » met à jour les changements via la route existante
  (`PUT /api/watchlist/items/<ticker>`) ; « Rejouer », « Annuler la dernière », « Fermer ».
- Session uniquement (aucun schéma, aucun score persistant) ; le jeu est désactivé avec
  moins de deux valeurs.
- Le jeu n'est **pas** exposé en écriture MCP.

## 5. Critères d'acceptation

- [x] AMUN (Tier 2) affiche Tier 2 dans le select ; le filtre/compteur et la fiche sont
      cohérents ; changer vers Tier 3 met tout à jour.
- [x] VIE (prix juste enregistré) : Pot. 5A = **estimation valorisation** (≈ 9,8 % avec la
      valorisation actuelle), badge « valo » ; la marge reste contre le prix juste.
- [x] AMUN/ACA (sans prix juste) : Pot. 5A = droite total-return, badge « droite ».
- [x] La fiche reste en vue référence brute ; la valorisation enregistrée prime.
- [x] Vue cadrans : 3 colonnes, cadrans de marge, cartes complètes, bascule tableau,
      responsive, états vides, aucun nouveau seuil en dur.
- [x] Jeu : 12 comparaisons, résultat avec tiers suggérés, application, annulation,
      rejouer, moins de 2 valeurs → désactivé.
- [x] Tests backend (dont réseau), front, e2e Chromium + WebKit ; aucun schéma ;
      calibration Pernod inchangée.

## 6. Décisions structurantes

| Décision | Pourquoi |
| --- | --- |
| Correctif du tier par `:selected` sur chaque option | Le `:value` du select est évalué avant les options `x-for` ; Alpine retombe sur le premier option. La base et l'API sont correctes. |
| Pot. 5A de valorisation dérivé du **prix juste enregistré** | Fidèle à « l'estimation qu'on a faite » : la cible et le dividende enregistrés encodent la projection ; au cours actuel, on retrouve le rendement de cette valorisation. Pas besoin du multiple/métrique courant. |
| `pot_5y_source` additif, pas de nouvelle table | Le choix de source est une propriété de la ligne, pas une donnée à persister. |
| Vue cadrans par défaut, tableau en bascule | La demande est une vue plus visuelle ; le tableau reste l'outil dense. |
| Jeu front-only, Elo, effectifs conservés | Aucun schéma, aucun écriture MCP ; le résultat est une proposition de tiers. Conserver les effectifs évite d'inventer des seuils absolus. |

## 7. Impacts fichiers (aperçu)

- **Back** : `engine/valuation_calc.py` (helper), `services/watchlist.py` (source Pot. 5A),
  `models.py` (`pot_5y_source`), `services/serialize.py` (summary), `mcp/tools/watchlist.py`
  (doc), tests.
- **Front** : `index.html` (select, cadrans, jeu), `watchlist.js` (agrégats/titre/view),
  `watchlist-dials.js` (cadrans SVG), `conviction.js` (Elo/paires), `conviction-mixin.js`
  (état jeu), `app.js` (mixin), `style.css`, tests Vitest/e2e.
- **Docs** : fiche #26, index, `CLAUDE.md`, `api.md`, `design.md`, `codebase-map.md`,
  captures.
- **Aucun** : migration, route d'écriture nouvelle, table.

## 8. Risques

- Le mapping « effectifs conservés » est un choix produit : il reclassifie sans changer le
  nombre de Tier 1/2/3 ; à valider.
- Le Pot. 5A dérivé du prix juste enregistré peut différer du rendement estimé **live** de
  la calculatrice si la métrique a changé depuis l'enregistrement ; la source « valo » et
  l'infobulle le disent.
- Basculer la vue par défaut en cadrans casse les sélecteurs e2e du tableau : les tests
  devront cliquer « Tableau ».
- Le jeu est une session : un rechargement perd le classement (les tiers appliqués, eux,
  sont persistés).
- Le cadran demande une échelle ; une plage d'affichage (≈ −50…+50 %) n'est pas un seuil
  de décision et doit rester visuelle.

## 9. Note de reprise

**J1 → J5 exécutés.** Mesures sur le serveur réel (derniers cours au 23/10) :

- **Tier** : AMUN affiche Tier 2 dans son select (3/1/0), le filtre et les compteurs sont
  cohérents. Cause : `:value` du select évalué avant les options `x-for` ; correctif
  `:selected` par option.
- **Pot. 5A** : VIE 9,77 % `valo`, ELEC 8,24 % `valo` ; ACA 8,36 % `droite`, AMUN 4,22 %
  `droite`. Le prix juste/marge enregistrés sont inchangés (VIE 28,89 / −11,08 %).
- **Cadrans** : 3 colonnes ; moyennes Tier 1 −16,47 %, Tier 2 −43,3 %, Tier 3 vide ;
  cartes avec marge, z, Pot. 5A/source, prix juste/source, tier, Voir ; bascule Tableau.
- **Jeu** : 12 comparaisons minimum, résultat classé (VIE 100, ACA 67, ELEC 33, AMUN 0 lors
  du test), effectifs 3/1/0 conservés ; aucune écriture réelle pendant la QA visuelle.

**Décisions.** Le Pot. 5A d'une valeur valorisée est dérivé du **prix juste enregistré**
(et de la cible/dividende), pas de la métrique courante : `projeté = prix juste ×
(1 + (cible − dividende)/100)^5`, puis `(projeté/cours)^(1/5) − 1 + dividende`. Le jeu est
front-only (Elo, prior du tier, paires les moins comparées, score percentile, tiers
suggérés à effectifs constants) et applique les changements via la route tier existante.

**Pièges.** (1) Le serveur cache `index.html`/CSS ; redémarrer après une modification de
l'index (le CSS non versionné est relu, l'index non). (2) Un serveur e2e ancien peut servir
un HTML périmé : vérifier le port/base URL ou repartir d'un serveur frais ; pour la suite
complète, arrêter le serveur réel et utiliser un `OBOLE_CACHE_DB` jetable. (3) Les nouveaux
modules doivent être déclarés dans `modules.test.js` (`watchlist-dials.js` utilitaire,
`conviction.js` utilitaire, `conviction-mixin.js` mixin). (4) Le label σ utilise `scored`
exposé à Alpine ; le Pot. 5A utilise `watchPotSourceLabel` (méthode, pas l'export direct).
(5) Avec deux valeurs, l'unique paire est rejouée (aucune autre paire possible). (6)
« Appliquer les tiers » fait N appels séquentiels : une erreur au milieu laisse les
changements déjà appliqués ; l'UI le signale.

**Prochaine action.** Revue puis merge (le plan est en `implemented`, la fiche/index en
`fait`).
