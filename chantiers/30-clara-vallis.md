# #30 — La Clara Vallis : le régime de foule dans la fiche

> **Statut :** à faire · **Priorité :** 🟡 Q2 · **Impact Pernod :** 🟢
> **Branche proposée :** `feat/clara-vallis` (créée) · **Taille :** 3-4 sessions

> **Convention de traçabilité.** La branche est un **repère de travail**, pas une preuve : elle
> n'est annotée « Branche (historique) » qu'une fois le chantier **clos** (jamais tant qu'il reste
> des jalons). Ne jamais citer de SHA — cf. `CLAUDE.md` §Workflow git.

---

## 1. Contexte

Obole répond aujourd'hui à deux questions sur une entreprise : **combien elle vaut** (la droite
de régression, `engine/regression.py:25`, PRD §5) et **dans quel sens va son cours** (croisement
MM11/MM200, `engine/regression.py:88`, PRD §5.7). Il en manque une troisième, que Didier Darcet
formule dans *Psychologie des marchés : la stratégie du maçon* (Grand Angle) : **dans quel état
est la foule qui porte ce cours ?**

L'idée de Darcet tient en une image. Tant que les intervenants ne s'imitent pas, le marché se
comporte comme un **gaz** : les opinions restent indépendantes, les distributions tiennent à peu
près (Markovitz, courbe de Gauss). Dès qu'ils se mettent en file indienne — vendre parce que les
autres vendent —, le marché devient un **liquide visqueux** (Mandelbrot, queues épaisses) : les
pertes se cumulent, la mémoire de la perte ne se résorbe pas, et le drawdown s'installe. Le
« niveau à bulle du maçon » mesure cet état : pour un investisseur entré à une date donnée, la
bulle se place entre le creux et le sommet parcourus depuis son entrée. Agrégée sur une foule
entrée à des dates différentes, elle donne un niveau de satisfaction collective ; quand la foule
devient nettement insatisfaite, le danger est imminent.

Le socle technique existe déjà. La fiche a six sections déclarées dans `web/sections.js:13`, la
Valorisation fermant la marche (`web/sections.js:46`) et rendue par un template dédié
(`web/index.html:518`). Les séries de prix sont déjà chargées et décimées côté serveur
(`services/serialize.py:154`, `_downsample` à `:130`), la fenêtre de référence est centralisée
(`services/analysis.py:36`), et le cache SQLite (`data/cache.py:24`) sait stocker un artefact
picklé par `(ticker, kind)` avec TTL — c'est là que le walk-forward précalculé ira. Les seuils du
projet sont à source unique (`config.py` → `/api/meta`), et les moyennes mobiles sont
précalculées serveur puis décimées.

Ce qui manque : le calcul, le payload, l'onglet et ses trois blocs.

---

## 2. Objectif

Ajouter à la fiche un **7ᵉ onglet « Momentum »** qui lit l'état de la foule, pour une action ou
un indice : une table « monde de Markovitz », puis trois blocs sous un titre commun
**« Invalidation ? : La Clara Vallis »** — une jauge gaz ↔ liquide, l'évolution du score sur un
an, et l'historique du cours coloré par état, en walk-forward.

Après ce chantier, on peut dire, sur une fiche : « la valorisation est favorable, mais la foule
est frustrée et le marché est passé en régime liquide » — et donc distinguer un point d'entrée
d'un piège.

---

## 3. Non-objectifs

- **Pas** de screener, watchlist, conviction ni outil MCP : la v1 est une lecture dans la fiche.
- **Pas** de remplacement de la tendance MM11/MM200 : les deux lectures coexistent (PRD §5.7).
- **Pas** de nouveau modèle de valorisation, ni de modification de `fit_log_regression`.
- **Pas** de backtest de performance : le walk-forward **colore** l'histoire, il ne prétend pas
  prédire ni produire un rendement.
- **Pas** de ratios (`ticker A / ticker B`) en v1 : entreprises et indices seulement.
- **Pas** de seuil littéral côté JS : tout passe par `config.py` et `/api/meta`.
- **Pas** de calcul du walk-forward dans le navigateur : il est précalculé serveur et caché.

---

## 4. Exigences

- **4.1 — Registre.** `SECTIONS` (`web/sections.js:13`) gagne une entrée `momentum`
  (libellé « Momentum ») **après** `valorisation`. L'onglet n'est proposé que pour une action
  (`stock`) ou un indice (`basket`) ; il est masqué pour un ratio et pour une série trop courte
  (via `sectionAvailable`).
- **4.2 — Moteur pur.** Un module `engine/clara_vallis.py` (aucune I/O, vectorisé numpy) expose
  `satisfaction_score(prices, window=250) -> ScoreResult` : valeur dans `[0, 1]`, nombre
  d'entrées utilisées, drapeaux de dégradation.
- **4.3 — Bulle.** Pour chaque entrée `i` parmi les `window` dernières séances :
  `lo_i = min(p[i:])`, `hi_i = max(p[i:])`, `bulle_i = (p[-1] - lo_i) / (hi_i - lo_i)` quand
  `hi_i > lo_i`, sinon `0.5` (neutre). Le score est la moyenne des bulles. **Près de 1 = foule
  satisfaite** (cours près des plus hauts), **près de 0 = foule frustrée** (près des plus bas).
- **4.4 — Régime.** `regime_score(window) -> 1 - R²` de la régression de `ln(prix)` sur le temps,
  calculé sur la fenêtre d'un an (365 jours calendaires). C'est la **confiance de la droite**,
  colonne de la table — pas l'aiguille de la jauge.
- **4.5 — Série historique.** `satisfaction_series(prices, window=250)` renvoie, pour chaque
  séance à partir de la 251ᵉ, la satisfaction calculée sur la fenêtre **antérieure** — c'est le
  walk-forward : à chaque date, le score n'utilise que les séances déjà écoulées. Aucune donnée
  future ne fuit.
- **4.6 — Payload.** La fiche transporte un bloc `momentum` : le score courant (brut et ajusté),
  la série de satisfaction alignée sur le graphe, la série sur 12 mois en pas quotidien, et les
  drapeaux de dégradation. Les mesures de la table sont recalculées côté client sur la fenêtre
  choisie — le payload ne transporte que ce que le navigateur ne peut pas recalculer.
- **4.7 — Cache.** La série de satisfaction est précalculée par référence (ticker ou
  `INDEX:<id>`) et stockée dans la table `cache` (`data/cache.py:24`), kind `momentum`, invalidé
  par `cache.invalidate(ref)`. TTL aligné sur celui du cache des prix.
- **4.8 — Table « monde de Markovitz ».** Colonnes : σ de la bande (l'écart-type du cours
  autour de la droite de référence, `(e^sigma − 1) × 100`), z, pente, MM court/long, confiance
  (`1 - R²`). **Aucune colonne « verdict »** : le seul verdict gaz/liquide est porté par la
  jauge, pour ne pas faire cohabiter deux vocabulaires concurrents. Fenêtre par défaut : la
  **référence de valorisation** (20 ans, 30 pour les financières) ; un sélecteur de durée permet
  de changer ce qu'on regarde.
- **4.9 — Bloc 1, la jauge.** Une jauge **horizontale** à deux pôles (gaz ↔ liquide) avec
  aiguille, sur le modèle visuel de la jauge de valorisation (`web/index.html:311`). Elle affiche
  le **score de satisfaction**. Graduations et libellés viennent de `config.py`.
- **4.10 — Bloc 2, la vue à un an.** Courbe quotidienne du score sur 12 mois, avec **bandes de
  seuils** (zone rouge sous le seuil bas, zone neutre, zone bleue au-dessus du seuil haut).
- **4.11 — Bloc 3, l'historique.** Cours + **fond coloré par état** (rouge = insatisfaction /
  régime liquide, bleu = satisfaction), **droite de régression optionnelle**, **échelle log
  optionnelle**. Walk-forward : les 250 premières séances restent neutres. Contrôle de durée :
  chips **1A / 5A / 10A / Max** + double poignée, comme la modale de zoom (`web/index.html:2872`).
- **4.12 — Brut / ajusté.** Un toggle bascule **tout le module** (table, jauge, courbe,
  historique) entre prix bruts et prix ajustés (dividendes réinvestis). État par fiche, non
  persisté. Si la série ajustée manque (certains indices), le toggle est désactivé avec une
  infobulle.
- **4.13 — Seuils.** Les bornes `MOMENTUM_*` vivent dans `config.py`, sont sérialisées par
  `/api/meta` et consommées par le front comme les autres seuils. Un test de parité les verrouille
  (même mécanisme que `web-tests/labels-parity.test.js`). La calibration s'appuie sur une **série
  CAC 40 figée** (2000 → 2023, `tests/fixtures/cac40_daily.csv`) : quatre fenêtres de crise, trois
  de calme, une neutre. Le test est pur, sans réseau ni dérive.
- **4.14 — Dégradations.** Moins de 250 séances : score sur les entrées disponibles + badge
  « historique court ». Moins d'un an : pas de walk-forward, message explicite. Série vide ou
  ticker sans prix : onglet masqué, jamais d'écran vide.
- **4.15 — Accessibilité.** L'onglet suit le pattern ARIA des autres (`aria-selected`, clavier) ;
  la jauge porte `role="meter"` et `aria-valuenow` ; les bandes de couleur ont une légende
  textuelle, jamais la couleur seule.

---

## 5. Critères d'acceptation

- [ ] L'onglet « Momentum » apparaît après « Valorisation » sur une action et sur un indice, et
      **pas** sur un ratio.
- [ ] Le score de satisfaction d'une fiche connue est reproductible : même série, même fenêtre,
      même valeur (test unitaire sur une série synthétique).
- [ ] Le walk-forward ne regarde jamais une séance postérieure à la date évaluée (test unitaire :
      ajouter une séance future ne change aucune valeur passée).
- [ ] La table affiche les six colonnes, sur la fenêtre de référence par défaut.
- [ ] La jauge, la courbe 12 mois et l'historique coloré se dessinent sur la fiche Pernod, sans
      erreur console.
- [ ] Le toggle brut/ajusté change visiblement les trois blocs et la table.
- [ ] Les chips 1A/5A/10A/Max et la double poignée bornent l'historique au bon intervalle.
- [ ] `/api/meta` expose les seuils `MOMENTUM_*` et le front les lit (test de parité vert).
- [ ] `pytest -m "not network"` et `cd web-tests && npm test` verts.
- [ ] La calibration Pernod (`z = -3.81`, ±0.15) reste verte.

---

## 6. Invariants préservés

- La calibration Pernod (`tests/test_calibration_network.py`, `z = -3.81` ±0.15) reste verte : le
  chantier **n'ajoute** aucune régression, il n'en modifie aucune.
- La formule de régression reste calculée aux **trois** endroits cohérents (serveur,
  `charts.js::drawChart`, `charts.js::computeLive`) — `fit_log_regression` n'est pas touché.
- Les moyennes mobiles restent **précalculées serveur** puis décimées : la table lit
  `ma_short_raw`/`ma_long_raw` (ou ajustés), elle ne les recalcule pas.
- Les seuils restent à **source unique** (`config.py` → `/api/meta`) : aucun littéral dans le JS.
- La polarité couleur reste **bleu = bien, rouge = mal** : le rouge de l'insatisfaction est bien
  un signal négatif, le bleu de la satisfaction un signal positif.
- `services/serialize._downsample` conserve toujours le dernier point : la série walk-forward ne
  doit pas s'arrêter avant le dernier cours.
- Aucun SHA ni décompte de commits dans la documentation (`tests/test_doc_coherence.py`).

---

## 7. Jalons

- **J1 — Moteur.** `engine/clara_vallis.py` : score de satisfaction, régime `1 - R²`, série
  walk-forward. Tests unitaires sur séries synthétiques (monotone, en V, plate, courte).
- **J2 — Service et payload.** Calcul dans `services/` (fenêtre de référence, brut/ajusté),
  précalcul du walk-forward et cache SQLite, exposition dans le dict de la fiche, route
  inchangée ou enrichie.
- **J3 — Onglet et table.** Entrée `momentum` dans `SECTIONS`, template de la section, table
  « monde de Markovitz » avec son sélecteur de durée.
- **J4 — Les trois blocs.** Jauge gaz ↔ liquide, courbe 12 mois avec bandes, historique coloré
  walk-forward avec chips et double poignée, toggle brut/ajusté.
- **J5 — Calibration.** Série CAC 40 figée (2000 → 2023), mesure des fenêtres de crise et de
  calme, réglage des seuils `MOMENTUM_*`, verrouillage par un test pur et un test de parité.
- **J6 — Finitions.** Dégradations (historique court, série absente), accessibilité, infobulles,
  mise à jour de `PRD.md` (§5.11), de `CHANTIERS.md` et de la mémoire projet.

---

## 8. Note de reprise

- **Plan :** `aidd_docs/tasks/2026_10/2026_10_29_clara-vallis/` (6 phases).
- **Branche :** `feat/clara-vallis`.
- **État :** spec écrite, plan validé, aucune phase commencée.
