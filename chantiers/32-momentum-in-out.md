# #32 — Fiabilité, seconde lecture : in contre out

> **Statut :** fait · **Priorité :** 🟡 Q2 · **Impact Pernod :** 🟢
> **Branche proposée :** `feat/momentum-in-out` · **Taille :** ~1 session

> **Convention de traçabilité.** La branche est un **repère de travail**, pas une preuve : elle
> n'est annotée « Branche (historique) » qu'une fois le chantier **clos** (jamais tant qu'il reste
> des jalons). Ne jamais citer de SHA — cf. `CLAUDE.md` §Workflow git.

---

## 1. Contexte

Le chantier #31 a livré la table de fiabilité : buy & hold contre la stratégie Clara Vallis, sur
la fenêtre visible. Le retour d'usage est net : **la comparaison est biaisée**. La stratégie n'est
investie que 60 à 70 % du temps (64 % sur RI.PA 2015-2025) ; lui demander de battre un buy & hold
investi à 100 % revient à comparer deux expositions différentes. Ce n'est pas la stratégie qui est
mauvaise, c'est la question posée.

La bonne question : **le signal sépare-t-il les bons jours des mauvais ?** Autrement dit, le marché
monte-t-il quand on est dedans et stagne-t-il (ou baisse-t-il) quand on est dehors ? Pour cela, on
garde la stratégie telle quelle et on ajoute la partie « quand on n'est pas dedans ».

La construction retenue : chaque séance appartient à **in** (position investie) ou **out**
(hors marché) ; les rendements du marché de chaque panier composent deux courbes conditionnelles.
Le panier « in » est exactement ce que vit la stratégie quand elle est investie ; le panier « out »
est ce qu'elle a évité.

---

## 2. Objectif

Remplacer la colonne « Clara Vallis » de la table de fiabilité par **deux colonnes « in » et
« out »**, garder buy & hold comme repère de la période, et laisser la comparaison in/out dire si
le signal est bon — sans badge automatique.

---

## 3. Non-objectifs

- **Pas** de badge de verdict : les deux colonnes suffisent, l'utilisateur lit la comparaison.
- **Pas** de suppression du buy & hold : il reste le repère de la période, pas la comparaison.
- **Pas** de changement de la règle (hystérésis 0,35/0,60), des frais (0,1 % par ordre) ni du
  décalage d'un jour.
- **Pas** de nouvelle mesure : les huit existantes, adaptées aux paniers.
- **Pas** de portage au screener, à la watchlist ou au MCP.

---

## 4. Exigences

- **4.1 — Deux paniers.** Chaque séance de la fenêtre est classée **in** (position investie à cette
  séance) ou **out** (hors marché). Les deux paniers partitionnent la fenêtre.
- **4.2 — Deux séries conditionnelles (non affichées).** La série **in** compose les rendements du
  marché des séances in ; la série **out** compose ceux des séances out. Une série part de 1 et ne
  contient que les séances de son panier. Elle n'est pas dessinée : elle sert à calculer les
  mesures des deux colonnes.
- **4.3 — Mesures.** Pour chaque colonne (buy & hold, in, out) : CAGR, volatilité annualisée,
  Sharpe, Sortino, max drawdown, Calmar, **part des séances** (%). Le CAGR d'un panier est
  annualisé sur **ses propres séances** (`n/252`), pas sur la durée calendaire : c'est le rythme du
  signal, pas le temps qui passe.
- **4.4 — Pied de table.** Le nombre de trades **et le rendement total de la stratégie**
  (cash compris) restent affichés une fois, sous le tableau, pas dans les colonnes : le lecteur
  garde le rendement réellement obtenu sans en refaire une comparaison.
- **4.5 — Contrat.** La réponse de la route devient
  `{buy_hold, in, out, window, trades, strategy_cagr_pct}` ; plus de bloc `strategy` complet ni
  d'`equity`/`positions` dans le transport.
- **4.6 — Table.** Trois colonnes : **Buy & hold**, **in**, **out** ; sept lignes de mesures ; la
  part des séances somme à 100 % entre in et out ; buy & hold à 100 %.
- **4.7 — Couleurs.** Polarité **inversée pour la colonne out** : un CAGR ou un Sharpe positif en
  « out » est **rouge** (gagner quand on est dehors est un mauvais signe). Les colonnes buy & hold
  et in gardent la polarité standard (positif = bleu).
- **4.8 — Légende.** La carte explique la lecture : « performance du marché pendant les séances in
  et out ; la stratégie n'est investie qu'une partie du temps ». Elle précise aussi que le
  **drawdown des paniers est conditionnel** : c'est la pire série de pertes du panier, pas un
  creux vécu dans le temps réel.
- **4.9 — Dégradations.** Panier vide (aucune séance in ou out), aucune baisse (Sortino nul), série
  plate : `—` plutôt qu'un infini ou un crash.
- **4.10 — Pas de fuite.** Le classement in/out d'une séance utilise la position décidée par le
  score de la veille, comme le backtest existant.

---

## 5. Critères d'acceptation

- [ ] La table affiche trois colonnes : Buy & hold, in, out.
- [ ] La part des séances de in et out somme à 100 % (aux arrondis près).
- [ ] La courbe in compose les rendements du marché des seules séances in (test unitaire).
- [ ] Un panier vide donne `—` et ne casse pas la table.
- [ ] La colonne out inverse la polarité : positif = rouge (test unitaire).
- [ ] Le pied affiche le rendement de la stratégie et le nombre de trades.
- [ ] La légende dit que le drawdown des paniers est conditionnel.
- [ ] La réponse de la route ne contient plus `strategy`, `equity` ni `positions`.
- [ ] `pytest -m "not network"` et `cd web-tests && npm test` verts.
- [ ] La calibration Pernod (`z = -3.81`, ±0.15) reste verte.

---

## 6. Invariants préservés

- La calibration Pernod reste verte : le chantier n'ajoute aucune régression.
- Le classement in/out ne lit **jamais** une séance postérieure à la date évaluée.
- Les mesures restent celles de `engine/portfolio.py` (Sharpe, Sortino, drawdown) : une seule
  implémentation.
- Les seuils et les frais restent à **source unique** (`config.py` → `/api/meta`).
- La polarité globale reste **bleu = bien, rouge = mal** ; l'inversion de la colonne out est une
  convention locale, documentée dans la légende.
- Aucun SHA ni décompte de commits dans la documentation (`tests/test_doc_coherence.py`).

---

## 7. Jalons

- **J1 — Moteur.** `momentum_backtest` renvoie `in` et `out` (courbes conditionnelles, mesures,
  part des séances) et `trades` ; tests purs (partition, composition, panier vide, polarité).
- **J2 — Service et route.** Contrat `{buy_hold, in, out, window, trades}`, plus de `strategy` ni
  d'`equity` ; tests API (clés exactes).
- **J3 — Table.** Trois colonnes, sept lignes, polarité inversée sur out, trades en pied, légende ;
  tests vitest.
- **J4 — Finitions.** e2e, `PRD.md` §5.12, mémoire projet, statut de la fiche et de l'index.

---

## 8. Note de reprise

**Livré.** La colonne « Clara Vallis » de la table de fiabilité a laissé la place aux deux
paniers `in` et `out`, avec le buy & hold en repère.

- **Moteur :** `engine/momentum_backtest.py` classe chaque séance de rendement dans le panier
  de la position décidée la veille (aucune fuite), compose deux courbes conditionnelles qui
  partent de 1 et ne contiennent que leurs séances, et mesure chacune avec les mêmes sept
  mesures. Le CAGR est annualisé sur les **séances du panier** (`n/252`), le buy & hold suit
  la même règle ; `trades` et `strategy_cagr_pct` sortent au premier niveau. `equity`,
  `strategy_equity` et `positions` restent internes (tests de frais, d'hystérésis et de
  décalage).
- **Service et route :** contrat exact `{buy_hold, in, out, window, trades,
  strategy_cagr_pct}` — plus de bloc `strategy`, plus d'`equity` ni de `positions` dans le
  transport. Paramètres et codes d'erreur inchangés ; un panier vide renvoie des mesures
  nulles et une part de 0 %.
- **Interface :** trois colonnes de valeurs et sept lignes (dont la « Part des séances », qui
  somme à 100 % entre in et out), pied `N trades · stratégie X %/an`, légende qui dit que le
  drawdown des paniers est conditionnel. La polarité de `out` est **inversée** (positif =
  rouge), `in` et buy & hold gardent la polarité standard, les trois mesures non signées
  restent neutres. `caption` et `scope="col"` à jour.
- **Preuve :** tests purs du moteur (partition, composition, panier vide, décalage, CAGR sur
  les séances), tests API (six clés exactes, zéro fuite de `strategy`/`equity`/`positions`),
  vitest (sept lignes × trois cellules, polarité inversée, panier vide, pied) et smoke
  Playwright Chromium + WebKit (trois colonnes, pied, classes `good`/`bad`, défilement à
  640 px).
- **Reste hors périmètre :** pas de badge de verdict, pas de courbes in/out dessinées, pas de
  changement de la règle d'hystérésis, des frais ni du décalage, pas de portage au screener,
  à la watchlist ni au MCP.
