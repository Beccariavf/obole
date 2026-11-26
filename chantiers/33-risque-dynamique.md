# #33 — Risque & dynamique (remplace la Clara Vallis)

> **Statut :** en cours · **Priorité :** 🟡 Q2 · **Impact Pernod :** 🟢
> **Branche proposée :** `feat/risque-dynamique` · **Taille :** ~2 sessions

> **Convention de traçabilité.** La branche est un **repère de travail**, pas une preuve : elle
> n'est annotée « Branche (historique) » qu'une fois le chantier **clos** (jamais tant qu'il reste
> des jalons). Ne jamais citer de SHA — cf. `CLAUDE.md` §Workflow git.

---

## 1. Contexte

L'onglet Momentum (#30, #31, #32) affiche la **Clara Vallis** : un score de « satisfaction »
(`engine/clara_vallis.py`), une jauge, son historique coloré et une carte « Fiabilité »
(`engine/momentum_backtest.py`, `services/momentum.py`, `web/momentum.js`). Une étude dédiée
(rapport hors dépôt « Momentum actions et trajectoire Obole », spikes
`spikes/spike_momentum_comparatif.py` et `spikes/univers_sbf120.py`) a établi :

- le score est un stochastique 250 séances habillé (corrélation 0,88), sans pouvoir prédictif
  (corrélation de rang avec le rendement à 12 mois ≈ 0) ; sur 186 titres, les résultats
  significatifs vont plutôt dans le **mauvais** sens (11,8 % contre 4,3 %), et classé entre
  titres il donne −4,2 %/an ;
- aucun réglage de fenêtre ni de bornes ne crée d'effet (12 combinaisons testées) ;
- même le momentum 12-1 classique n'a **pas d'avantage démontré** sur un univers fixé CAC 40 +
  SBF 120 (tiers fort − moyenne : +2,1 %/an, t = 1,34 ; rien sur le CAC 40 ; +0,35 %/an depuis
  2008) ;
- le seul effet robuste commun à toutes les règles est un effet de **volatilité** : le risque se
  prédit (regroupement de la volatilité), le rendement non.

La table « monde de Markovitz » du même onglet (σ de bande, z, pente, 1 − R² par fenêtre,
recalculée côté client dans `momentum.js::momStats/momRows`) parle de la droite, pas du momentum.

## 2. Objectif

Remplacer l'onglet Momentum par un onglet **« Risque & dynamique »** très léger, qui dit
factuellement si une baisse est en cours et si le titre traverse une période anormalement agitée,
sans jamais suggérer un achat ou une vente. La table Markovitz rejoint Valorisation.

## 3. Non-objectifs

- Aucun indicateur présenté comme prédictif du rendement, aucune flèche, aucun verdict.
- Pas de rang dans un univers (SBF 120) : non validé, coûteux à tenir à jour.
- Pas de backtest, pas de carte « fiabilité ».
- Aucun outil MCP nouveau.
- Aucun changement de `fit_log_regression`, `distance_sigma` ni des trois calculs de régression.

## 4. Exigences

- 4.1 **Suppression complète** de la Clara Vallis : `engine/clara_vallis.py`,
  `engine/momentum_backtest.py`, `engine/momentum_stats.py`, `services/momentum.py`, les routes
  `/api/stock/{ticker}/momentum-backtest` et `/api/index/{index_id}/momentum-backtest`, la clé
  `chart.momentum` de `services/serialize.py`, les constantes `MOMENTUM_*` et
  `CHART_HEIGHT_MOMENTUM_*` de `config.py`, le bloc `momentum` de `/api/meta`, la jauge,
  l'historique, la carte Fiabilité, leurs tests (pytest, Vitest, e2e), le kind de cache
  `momentum` et le test de calibration CAC (`tests/test_clara_vallis_calibration.py`,
  `spikes/spike_clara_vallis*.py`). Les spikes de l'étude (`spike_momentum_comparatif.py`,
  `univers_sbf120.py`) restent, en lecture autonome : ils importent `clara_vallis` et doivent
  être adaptés (voir §4.9).
- 4.2 La **table Markovitz** est déplacée dans la section Valorisation, comportement identique
  (même calcul client, mêmes fenêtres, même sélecteur de série brute/ajustée), tests de parité
  conservés et renommés en conséquence.
- 4.3 Nouvel onglet `risque` (« Risque & dynamique ») à la place de `momentum` dans
  `sections.js::SECTIONS` ; un ancien lien `#<ticker>/momentum` retombe sur le Résumé sans erreur.
- 4.4 **Moteur pur** `engine/risk.py` : `drawdown_series(prices)` (chute depuis le plus haut
  courant, en %), `realized_vol_series(prices, window)` (écart-type des rendements log ×
  √252, en %), `percentile_of_last(series, min_points)` (rang de la dernière valeur dans
  l'historique, `None` sous le minimum), `momentum_12_1(prices, lookback, skip)` (rendement de
  t−252 à t−21, `None` si historique trop court). Tout absent est `None`, jamais un crash.
- 4.5 **Données servies** : `services/serialize.py` ajoute `chart.risk` pour une action et pour un
  panier, calculé sur la série **pleine résolution ajustée** (série du panier pour un indice) puis
  décimé sur la **même grille** que le cours (comme les moyennes mobiles). Scalaires : chute
  actuelle et date du plus haut, volatilité actuelle et son percentile, seuil de volatilité
  (valeur au percentile d'anomalie de son historique), volatilité actuelle du CAC 40, 12-1 du
  titre et du CAC 40 sur **cours bruts** (hors dividendes, des deux côtés). Le CAC 40 est
  `^FCHI`, lu via la couche `data/` (cache) ; s'il est indisponible, ses champs valent `None`.
- 4.6 **Constantes** dans `config.py`, exposées par `/api/meta` (bloc `risk`) :
  `RISK_VOL_WINDOW = 60`, `RISK_VOL_ANOMALY_PCTILE = 90`, `RISK_VOL_MIN_POINTS = 504`,
  `RISK_MOM_LOOKBACK = 252`, `RISK_MOM_SKIP = 21`, `RISK_BENCHMARK = "^FCHI"`,
  `CHART_HEIGHT_RISK`. Aucun seuil littéral côté JS.
- 4.7 **Front** `web/risk.js` (mixin, remplace `momentum.js`) : un graphique Plotly à deux étages
  à axe X partagé — en haut la chute depuis le plus haut (aire, couleur neutre), en bas la
  volatilité 60 j (ligne neutre) avec le seuil d'anomalie en pointillé et les passages au-dessus
  du seuil en **rouge**. Plage propre avec puces 1A / 5A / 10A / 20A / Max, **10 ans par
  défaut**. Sous le graphique, trois lignes :
  « Chute depuis le plus haut : −35 % (plus haut le …) » ;
  « Volatilité 60 j : 34 % · plus haute que 92 % de son historique · CAC 40 : 15 % » (le
  percentile en rouge seulement s'il dépasse le seuil d'anomalie) ;
  « 12-1 (hors dividendes) : −18 % · CAC 40 : +4 % ». Couleurs neutres partout ailleurs.
- 4.8 **Historique court** : moins de 13 mois → 12-1 affiché « — » avec une infobulle ; moins de
  `RISK_VOL_MIN_POINTS` → volatilité affichée sans percentile, mention « historique trop court
  pour situer » ; le graphique montre ce qui existe.
- 4.9 Documentation : `PRD.md` (sections Momentum), `aidd_docs/memory/architecture.md`,
  `design.md`, `codebase-map.md`, `api.md`, `CLAUDE.md` si concerné, `CHANTIERS.md`.

## 5. Critères d'acceptation

- [x] `grep -rniE "clara|satisfaction_series|momentum_backtest" src tests web-tests/*.js web-tests/e2e`
      ne renvoie plus rien (hors mentions historiques volontaires dans `chantiers/`).
- [x] La table Markovitz s'affiche dans Valorisation, ses tests de parité passent.
- [x] `GET /api/stock/RI.PA` porte `chart.risk` aligné sur la grille du cours ; un panier aussi.
- [x] Tests unitaires `engine/risk.py` : série plate, nouveau plus haut, historique < 13 mois,
      historique < `RISK_VOL_MIN_POINTS`, valeurs non positives écartées.
- [x] Vitest : le mixin lit ses seuils depuis `/api/meta`, rouge seulement au-dessus du seuil,
      « — » sur historique court.
- [x] e2e : l'onglet « Risque & dynamique » s'ouvre et trace son graphique ; `#X/momentum`
      retombe sur Résumé.
- [x] Portes `coding-assertions.md` « Before push » vertes (le test réseau n'est pas
      obligatoire : impact 🟢).

## 6. Invariants préservés

- La calibration Pernod (`z = −3.81`, ±0.15) reste verte : aucune formule de régression touchée.
- Couches à sens unique `web → api → services → engine → data` ; `engine/risk.py` sans I/O.
- Séries précalculées serveur sur la pleine résolution puis décimées (jamais sur la grille
  décimée).
- Bleu = bien, rouge = mal ; ici, neutre par défaut, rouge pour la seule anomalie de volatilité.

## 7. Jalons

- **J1** — Retrait de la Clara Vallis et déplacement de la table Markovitz dans Valorisation
  (onglet Momentum retiré ; dépôt vert).
- **J2** — Moteur `risk.py`, données `chart.risk`, constantes et `/api/meta`, onglet
  « Risque & dynamique », tests et documentation.

## 8. Note de reprise

- **J1 livré** : Clara Vallis retirée, table Markovitz déplacée dans Valorisation.
- **J2 livré** : moteur `risk.py` (jalon J2a), `chart.risk` action et panier, bloc `risk`
  de `/api/meta`, onglet « Risque & dynamique » (`web/risk.js`), tests pytest/Vitest/e2e
  et documentation.
- Plan d'exécution : délégué à OpenCode, un plan par jalon (hors dépôt).
- Branche : `feat/risque-dynamique`. **J2 livré, prêt à fusionner** ; l'index reste
  « en cours » et la branche ne sera annotée « Branche (historique) » qu'après la
  fusion sur `main`, comme le veut la convention.
