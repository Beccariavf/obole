# #25 — Watchlist à tiers, marges de sécurité et fenêtre de confiance

> **Statut :** **fait** · **Priorité :** 🟡 Q2 (important, non urgent — cas (c) évolutivité)
> **Impact Pernod :** 🟠 · **Branche proposée :** `feat/watchlist` · **Taille :** 2-3 sessions
> **Fiche parente :** — · **Dépend de :** #16 (rail), #20 (valorisation), #17 (portefeuille, lecture seule), #09 (MCP)

> **Convention de traçabilité.** La branche est un **repère de travail**, pas une preuve : elle
> n'est annotée « Branche (historique) » qu'une fois le chantier **clos**. Ne jamais citer de SHA
> — cf. `CLAUDE.md` §Workflow git.

---

## 1. Contexte

Le PRD §Phase 2 prévoyait une « watchlist : liste de tickers persistée localement », jamais
livrée (la ligne de feuille de route §10 la déclare à tort ✅). Aujourd'hui :

- une fiche n'a **aucun moyen de marquer une valeur comme suivie** ; la seule liste persistée
  est `custom_indices` (paniers calculés), sémantiquement différente ;
- le **prix juste** est déjà persisté par titre dans `valuation_settings` (`fair_price`,
  `target_yield`, `updated_at`) et la marge existe en formule pure
  (`engine/valuation_calc.py::safety_margin`, miroir JS testé) ;
- le screener sait déjà réduire N tickers en `z`, `ecart_type_pct`, `pente_pct`, `pot_*`
  **avec une fenêtre de régression**, pool de threads et budget inclus (`services/screen.py`,
  `services/screener.py`) ;
- **rien ne persiste la fenêtre de confiance** : le slider de la fiche est un état d'affichage
  (indices sur la série), perdu au rechargement (`web/charts.js::initRange`) ;
- le « Prix juste » du Résumé est une droite **20 ans** fixe (`services/analysis.py::_fair_price`) ;
- le MCP expose déjà des écritures pilotées avec snapshot préalable (`mcp/tools/__init__.py`,
  `WRITE_TOOLS`, `_SnapshotServer`), donc une surface watchlist est possible sans nouveau
  garde-fou structurel.

## 2. Objectif

Pouvoir suivre des valeurs dans **3 tiers fixes**, les ajouter depuis leur fiche en un geste, et
les **classer par marge de sécurité** contre deux références :

1. le **prix juste enregistré** (objectif de rendement choisi dans la calculatrice) ;
2. la **droite de régression de confiance**, définie par une **date de départ par titre**
   (jusqu'à aujourd'hui), avec la position en σ et l'écart à la droite.

Deux prolongements actés :

- le **« Prix juste » du Résumé** utilise, au chargement de la fiche, la fenêtre de référence
  persistée du titre (sinon 20 ans) — le prix juste enregistré reste prioritaire ;
- le **MCP** expose la watchlist en lecture (`get_watchlist`, `rank_watchlist`) et en écriture
  d'appartenance (`add_to_watchlist`, `remove_from_watchlist`) ; **la référence et le prix juste
  restent des gestes humains**, jamais écrits par l'IA.

## 3. Non-objectifs

- Pas de tiers personnalisables, pas de multi-listes : 3 rangs fixes, une appartenance par ticker.
- Pas de badge « détenu en portefeuille » (le portefeuille reste la source de vérité ; intégration
  ultérieure).
- Pas d'ajout manuel hors fiche (la fiche est le point d'entrée ; le MCP peut ajouter, cf. §4).
- Pas de mobile/responsive (hors périmètre de #16).
- Pas de prompt MCP de revue de watchlist ; l'IA compose à partir de `rank_watchlist`.
- Pas de modification de formule ni de calibration ; pas de nouveau calcul côté client.
- Pas de DCF, Monte-Carlo ni comparaison vs pairs.

## 4. Exigences

- 4.1 Schéma v8 : `watchlist_items (ticker PK, tier 1..3, added_at)` et `ticker_refs
  (ticker PK, ref_start ISO, updated_at)`. Migration idempotente ; tables déclarées dans
  `data/backup.py` (`_TABLE_COLUMNS`, `_TABLE_SINCE[8]`).
- 4.2 Source unique : `WATCH_TIERS`, `WATCHLIST_MAX_ITEMS`, `REGRESSION_MIN_POINTS` dans
  `config.py`, exposés par `/api/meta` (`watch: {tiers, min_ref_points, max_items}`).
- 4.3 `services/analysis.reference_window(ticker, raw)` : référence persistée sinon 20 ans ;
  tranche `> 0`, ≥ 30 points ; une référence inexploitable retombe sur 20 ans.
- 4.4 « Prix juste » du Résumé : enregistré > ligne de référence > 20 ans. Note de carte
  (« Prix juste enregistré (calculatrice) », « Droite de référence (prix bruts, depuis AAAA) »,
  ou absente pour 20 ans). Calculé au chargement, pas sur le slider.
- 4.5 `services/watchlist.py` : validation (ticker, tier, date, plafond), CRUD, `ref_stats`,
  `stock_state`/`decorate_stock_payload`, `run(tier)` (scan parallèle partagé, lignes triées,
  erreurs isolées).
- 4.6 Marge : `safety_margin_pct = (fair − cours)/fair` avec `fair` = prix juste enregistré
  (`source="saved"`) sinon `line_ref` (`source="regression"`). La marge historique est
  `trend_gap_pct` et `z` sur les **prix bruts**. `margin_good` porte la polarité.
- 4.7 API : `GET /api/watchlist`, `PUT/DELETE /api/watchlist/items/{ticker}`,
  `PUT/DELETE /api/watchlist/ref/{ticker}`, `POST /api/watchlist/run` ; `/api/stock` porte
  `watch` ; `/api/meta` porte `watch`.
- 4.8 MCP : `get_watchlist`, `rank_watchlist(tier, max_rows, view)`, `add_to_watchlist(ticker,
  tier)`, `remove_from_watchlist(ticker)` ; `get_stock_analysis` porte `watch`. Écritures dans
  `WRITE_TOOLS` (masquées en read-only, snapshot automatique). **Aucun outil de référence ni de
  prix juste.**
- 4.9 Front : bouton `★ Watchlist` entre `Portefeuille` et `⚙ Paramètres` ; étoile + popover
  dans le header ; chip de référence dans la barre de période ; modale plein écran (tiers,
  compteurs, tableau triable, badges de source, états vides/erreur).
- 4.10 Recalcul serveur uniquement : le front n'implémente ni marge ni `z` ; aucun seuil littéral
  JS ; `app.js` < 500 lignes ; `fetch` uniquement dans `api.js`.

## 5. Critères d'acceptation

- [ ] Ajout/déplacement/retrait depuis la fiche, persistant après rechargement, état visible.
- [ ] Modale : filtre par tier + compteurs, tri par marge, badges de source, repli visible.
- [ ] Une ligne dit la fenêtre (`depuis AAAA` ou `20 ans (défaut)`) et la série (prix bruts).
- [ ] Définition/effacement d'une référence ; la fiche se recharge et le Résumé suit.
- [ ] Résumé : enregistré > référence > 20 ans, avec la bonne note.
- [ ] Erreurs par ligne isolées ; plafond et validations en 422.
- [ ] MCP : parité payload avec l'API, read-only masque les écritures, aucun outil de référence.
- [ ] Schéma v8 : base neuve, migration 7→8, sauvegarde/restauration (archive v7 tolérée).
- [ ] `pytest -m "not network"` vert, `pytest -m network` vert (Pernod `z = −3.81`).
- [ ] `ruff`, `mypy`, `npm test`, `npm run test:e2e` verts.
- [ ] Aucun seuil littéral JS ; `app.js` < 500 lignes ; 0 `fetch` hors `api.js`.
- [ ] Doc : #25, index, mémoire (`api`, `data`, `design`, `codebase-map`), CLAUDE.md, README,
      PRD (ligne de roadmap), renvoi #16.

## 6. Invariants préservés

- Calibration Pernod `z = −3.81` (±0,15) : la formule de régression n'est **pas** modifiée.
- Régression calculée aux trois endroits existants (serveur, `drawChart`, `computeLive`) : aucun
  quatrième calcul client n'est ajouté (la référence est calculée serveur).
- `config.py` reste la seule source des seuils et des libellés ; le front et le MCP les lisent.
- Deux séries de prix : `raw` pour la valorisation (marge, référence), `adjusted` pour la perf.
- Le prix juste de la watchlist est **lu** de `valuation_settings`, jamais recalculé.
- Le MCP n'ajoute aucune formule ni seuil ; il délègue à `services/`.
- Données utilisateur sauvegardées : toute nouvelle table est déclarée dans `backup.py`.

## 7. Jalons

- **J1** — Schéma v8, config, SQL, backup, tests.
- **J2** — Fenêtrage + Résumé aligné (`reference_window`, `build_summary(fair_price_note)`),
  `windowed_analysis`, `scan_parallel`, tests + réseau.
- **J3** — Classement + API (`WatchlistRow`, service, serialize, routes, `/api/stock`, `/api/meta`).
- **J4** — MCP (outils, parité, read-only).
- **J5** — Front (topbar, étoile, chip, modale, rechargement après référence).
- **J6** — E2E, doc, revue.

## 8. Note de reprise

**J1 → J6 exécutés dans la même session** (schéma v8, domaine, fenêtrage + Résumé, API, MCP,
front, e2e). Détail des décisions et pièges dans
`aidd_docs/tasks/2026_10/2026_10_24_watchlist/plan.md`.

**Décisions.** 3 tiers fixes, une appartenance par ticker (`ticker` PK) ; la référence est
**par titre** (`ticker_refs`) et survit au retrait de la watchlist. Le prix juste est **lu**
de `valuation_settings` (jamais recalculé) ; le repli sur la droite de référence est assumé
et signalé (badge `droite`, légende, filtre). Défaut **20 ans** (aligné sur l'ouverture de la
fiche et le Résumé). Marge historique sur **prix bruts**. MCP : lecture + appartenance ;
la référence et le prix juste restent hors de la surface d'écriture.

**Pièges.** (1) La barre de tiers lit `metaReady` dans `watchTierList()` : sans cette
dépendance réactive, ouvrir la modale avant la fin de `init()` laissait les libellés vides.
(2) `windowed_analysis(ref_start=...)` **refuse** une fenêtre < `REGRESSION_MIN_POINTS` (pas de
repli silencieux) ; le classement choisit la fenêtre effective via `reference_window` pour
que le Résumé et la watchlist ne divergent pas. (3) `initRange` ouvre la fiche sur la
référence ; après définition/effacement, la fiche est **rechargée** pour que la carte
« Prix juste » suive. (4) `valuation_settings` reste **hors** du registre de sauvegarde : l'y
ajouter maintenant ferait qu'une restauration d'archive ancienne (qui ne contient pas
la table) effacerait les prix justes enregistrés. Le correctif demande une politique
« préserver si absente » dans `restore_archive` — gap connu, hors #25. (5) Le PUT de référence valide la
fenêtre avec les prix (cache chaud de la fiche) : réseau/`TickerNotFound` -> 422, jamais
d'écriture partielle trompeuse.

**Corrections post-livraison (#25.1).** La fiche d'un titre référencé s'ouvre désormais en
**prix bruts + synchro** et utilise la **régression persistée** (`ref_stats.a/b/sigma`) quand
la plage visible est la référence : la droite, les KPI (`z`, σ, performance, `Pot. 5A`) et la
watchlist lisent la même régression (avant, sur ACA : 7,6 % en fiche contre 2,9 % en
watchlist, parce que la fiche régressait l'ajusté sur la série décimée). `_downsample`
conserve le dernier point (le graphe s'arrêtait au 19 oct./15,30 € au lieu du 23 oct./14,92 €).
La ligne de watchlist porte la pente brute ; le popover de référence est en items bloc.

**Vue total-return (#25.2).** La watchlist est passée en **dividendes réinvestis** (`z`, σ,
écart, pente, `Pot. 5A/10A`) ; sans prix juste enregistré, son prix juste est le **prix
d'entrée à 12 %/an** jusqu'à la droite à 5 ans, converti en unités du cours brut. La fiche
reste en droite brute : les deux vues diffèrent volontairement. Corrigé au passage : le
label σ de la modale (`scored` non exposé à Alpine) et les libellés « Prix justes
enregistrés ».

**Prochaine action.** Aucune — revue passée (`review.md`, verdict approve), chantier clos.
