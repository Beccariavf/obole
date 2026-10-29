# #31 — Fiabilité de la Clara Vallis

> **Statut :** fait · **Priorité :** 🟡 Q2 · **Impact Pernod :** 🟢
> **Branche proposée :** `feat/clara-vallis-fiabilite` (depuis `feat/clara-vallis`, tant que #30 n'est pas fusionné) · **Taille :** 2-3 sessions

> **Convention de traçabilité.** La branche est un **repère de travail**, pas une preuve : elle
> n'est annotée « Branche (historique) » qu'une fois le chantier **clos** (jamais tant qu'il reste
> des jalons). Ne jamais citer de SHA — cf. `CLAUDE.md` §Workflow git.

---

## 1. Contexte

Le chantier #30 a livré l'onglet Momentum : jauge de satisfaction, courbe à un an, historique
coloré. Trois retours d'usage, et une question de fond.

**Les mots de la jauge.** L'échelle affiche « gaz · satisfaite » et « liquide · frustrée ». Le
vocabulaire de Darcet (gaz = Markovitz, liquide = Mandelbrot) explique le modèle, mais il
alourdit la lecture : l'utilisateur veut **« satisfaite » / « frustrée »**, point. Les côtés
restent (satisfait à gauche, frustré à droite).

**Le chip manquant.** La table « monde de Markovitz » a un chip « Réf. » qui applique la fenêtre
de référence (date persistée, sinon 20 ans, 30 pour les financières) ; l'historique du régime,
lui, n'a que 1A/5A/10A/MAX. Il manque le même repère.

**La fiabilité.** Une jauge dit l'état de la foule, pas si l'indicateur **marche** sur cet actif.
Il faut la preuve : comparer buy & hold et une stratégie pilotée par le score, sur la fenêtre
qu'on regarde, avec les mesures de risque usuelles.

**La mécanique.** « Est-ce que le score revient au même que le pourcentage de personnes
satisfaites ? » Non : le score est la **moyenne des positions de bulle** (il pèse l'intensité),
la part ne compte que les gens. 60 % de gens à peine satisfaits et 40 % très frustrés donnent un
score bas et 60 % de « satisfaits ». La moyenne est plus fine ; la part est plus lisible. Pour
cette version, on garde la moyenne seule — deux chiffres sur une jauge invitent à la mauvaise
lecture.

---

## 2. Objectif

Rendre l'onglet Momentum lisible et **évaluable** : des mots simples sur la jauge, le chip
« Réf. » sur l'historique, et sous l'historique une table qui compare buy & hold à la stratégie
Clara Vallis sur la fenêtre visible — CAGR, volatilité, Sharpe, Sortino, max drawdown, Calmar,
temps investi, nombre de trades.

---

## 3. Non-objectifs

- **Pas** de part de satisfaits affichée (moyenne seule) : décision assumée, réversible plus tard.
- **Pas** de comparaison de plusieurs stratégies : une seule règle, celle de Darcet.
- **Pas** de backtest côté client : la grille du graphe est décimée, un backtest dessus raterait
  des croisements et fausserait drawdown et trades (même piège que les moyennes mobiles).
- **Pas** de frais ni de taux réglables dans Paramètres : deux constantes dans `config.py`.
- **Pas** de portage au screener, à la watchlist ou au MCP.

---

## 4. Exigences

- **4.1 — Jauge simplifiée.** L'échelle devient **« satisfaite »** (gauche) et **« frustrée »**
  (droite) ; « gaz » et « liquide » disparaissent de l'échelle. Le titre « Satisfaction de la
  foule », l'aiguille (`1 − score`) et les zones (bleu à gauche, rouge à droite) ne changent pas.
- **4.2 — Chip « Réf. » de l'historique.** Un chip **« Réf. »** précède 1A. Il applique la
  **fenêtre de référence** : date persistée si elle existe, sinon 20 ans (30 pour les
  financières). Le défaut de l'historique reste **10 ans** ; le chip est un repère, pas le défaut.
- **4.3 — Stratégie.** Investi quand le score dépasse `HIGH` (0,60), hors marché quand il passe
  sous `LOW` (0,35), état conservé entre les deux (hystérésis). Départ hors marché.
- **4.4 — Pas de fuite du futur.** Le score de la séance `t` ne décide que la position de
  `t+1` ; le rendement de `t+1` est `P[t+1]/P[t] − 1`.
- **4.5 — Base de calcul.** Le backtest suit la **série affichée** (brut ou ajusté), comme le
  reste du module : la bascule doit tout changer. La légende le dit — en brut, les dividendes ne
  sont pas comptés, et la lecture ajustée reste à un clic.
- **4.6 — Frais.** `MOMENTUM_FEE_PCT = 0.1` % **par ordre** (entrée et sortie), taux sans
  risque `MOMENTUM_RISK_FREE_PCT = 0`. Constantes `config.py`.
- **4.7 — Période.** La fenêtre **visible** de l'historique (chips et poignée). Un changement de
  fenêtre relance le calcul ; une fenêtre de moins de deux séances affiche un état vide.
- **4.8 — Mesures.** Pour chaque colonne (buy & hold, Clara Vallis) : CAGR, volatilité
  annualisée, Sharpe, Sortino, max drawdown, Calmar, temps investi, nombre de trades.
  Réutilisation de `engine/portfolio.sharpe_ratio`, `sortino_ratio` et `drawdown_metrics` — pas
  de seconde formule.
- **4.9 — Calcul serveur.** Le moteur reçoit la série **pleine résolution** et la série de
  satisfaction (walk-forward) ; il renvoie les deux jeux de mesures. Le service tranche la
  fenêtre et résout la référence (ticker ou `INDEX:<id>`).
- **4.10 — Transport.** Deux routes : `GET /api/stock/{ticker}/momentum-backtest?start=&end=&series=`
  et `GET /api/index/{id}/momentum-backtest?start=&end=&series=`. Dates ISO validées, `series`
  dans `raw|adj` (défaut `raw`), fenêtre bornée à la série, 422 sinon.
- **4.11 — Interface.** Une carte « Fiabilité de l'indicateur » sous l'historique : un tableau à
  deux colonnes, les huit lignes, la légende total-return, un état de chargement et un état vide.
- **4.12 — Dégradations.** Fenêtre courte, aucun trade, aucune baisse (Sortino nul), série plate
  (Sharpe nul) : `—` plutôt qu'un infini ou un crash.

---

## 5. Critères d'acceptation

- [ ] La jauge n'affiche plus « gaz » ni « liquide » ; elle dit « satisfaite » / « frustrée ».
- [ ] Le chip « Réf. » précède 1A sur l'historique et applique la même fenêtre que la table.
- [ ] La stratégie est investie au-dessus de 0,60, sortie sous 0,35, état conservé entre les deux.
- [ ] Le signal de `t` ne décide que `t+1` (test unitaire : décaler la série décale les trades).
- [ ] Le backtest suit la bascule brut/ajusté (test unitaire : la série choisie change les chiffres).
- [ ] Les huit mesures sont présentes pour les deux colonnes, `—` quand non calculables.
- [ ] Les frais de 0,1 % par ordre réduisent le rendement de la stratégie (test unitaire).
- [ ] La table suit la fenêtre visible et se recharge au changement de fenêtre.
- [ ] `pytest -m "not network"` et `cd web-tests && npm test` verts.
- [ ] La calibration Pernod (`z = -3.81`, ±0.15) reste verte.

---

## 6. Invariants préservés

- La calibration Pernod (`tests/test_calibration_network.py`, `z = -3.81` ±0.15) reste verte : le
  chantier n'ajoute aucune régression.
- Le backtest ne lit **jamais** une séance postérieure à la date évaluée.
- Le calcul se fait sur la série **pleine résolution**, puis la fenêtre est tranchée : pas de
  backtest sur la grille décimée du graphe.
- Les seuils restent à **source unique** (`config.py` → `/api/meta`).
- Les formules de Sharpe, Sortino et drawdown restent celles de `engine/portfolio.py` : une
  seule implémentation.
- La polarité couleur reste **bleu = bien, rouge = mal**.
- Aucun SHA ni décompte de commits dans la documentation (`tests/test_doc_coherence.py`).

---

## 7. Jalons

- **J1 — Jauge et chip.** Échelle simplifiée, chip « Réf. » de l'historique, tests de rendu.
- **J2 — Moteur.** `engine/momentum_backtest.py` : équité buy & hold et stratégie, hystérésis,
  frais, décalage d'un jour ; réutilisation des mesures du portefeuille. Tests purs.
- **J3 — Service et routes.** Tranche de fenêtre, résolution ticker / indice, deux routes
  validées, tests API.
- **J4 — Table et fetch.** Carte « Fiabilité de l'indicateur », appel au changement de fenêtre,
  états de chargement et vides, tests vitest.
- **J5 — Finitions.** Dégradations, accessibilité, e2e, `PRD.md` §5.12, mémoire projet, statut de
  la fiche.

---

## 8. Note de reprise

**Terminé.** Implémentation livrée sur `feat/clara-vallis-fiabilite`.

- **Plan :** `aidd_docs/tasks/2026_10/2026_10_29_clara-vallis-fiabilite/` (5 phases).
- **Jauge :** « satisfaite » / « frustrée » ; le chip « Réf. » de l'historique lit la même
  référence que la table (`_momReferenceStart`), le défaut reste 10 ans.
- **Moteur :** `engine/momentum_backtest.py` (pur) — hystérésis 0,35/0,60, signal de `t`
  décalé sur `t+1`, frais 0,1 % **par ordre**, Sharpe/Sortino/drawdown réutilisés de
  `engine/portfolio.py`.
- **Service et routes :** `services/momentum.momentum_backtest` calcule la satisfaction sur
  la série PLEINE puis tranche la fenêtre ; deux routes validées (dates ISO, `raw|adj`,
  404 pour une référence inconnue). L'index yfinance tz-aware est normalisé.
- **Interface :** carte « Fiabilité de l'indicateur » à trois colonnes et huit lignes,
  jeton de requête contre les réponses tardives, états vide/chargement/erreur, `caption`
  et `scope="col"`, défilement horizontal sous 640 px.
- **Preuve :** tests unitaires du moteur, tests API, vitest (formatage, lignes, jeton,
  états) et smoke Playwright Chromium + WebKit.
- **Reste hors périmètre :** pas de comparaison de plusieurs stratégies, pas de portage au
  screener, à la watchlist ni au MCP, pas de frais réglables dans Paramètres.
