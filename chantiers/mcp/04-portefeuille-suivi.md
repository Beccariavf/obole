# #09.4 — MCP · Portefeuille (MCP-B) et points de contrôle suivis

> **Statut :** **fait** · **Priorité :** 🟡 Q2 (important, non urgent — cas (c) évolutivité)
> **Impact Pernod :** 🟢 · **Branche (historique) :** `feat/mcp-portefeuille-suivi` · **Taille :** ~1 session
> **Fiche parente :** #09 (MCP — surface IA) · **Précédent :** `mcp/03-these-entreprise.md`

---

## 1. Contexte

Constat de départ : l'inventaire de la couche `mcp/` montre que **17 outils** sont exposés
(stock, ratio, search, indices, screener, thèse) alors que l'API HTTP en sert beaucoup plus.
Deux domaines de données utilisateur étaient **entièrement absents** de la surface IA, alors que
leur orchestration partagée existe déjà :

- **Portefeuille** (`services/portfolio.py`) : comptes, transactions, dividendes, positions et
  résumé TWR — 15 routes dans `api/app.py` (`/api/portfolio/...`), **aucun** outil MCP.
- **Suivi** (`services/checkpoints.py`) : points de contrôle persistés (bande « Suivi », #21) —
  4 routes `/api/checkpoints/...`, **aucun** outil MCP.

Les deux services sont déjà des **cas d'usage partagés API ↔ MCP** : ils portent la validation
et des erreurs typées (`NotFoundError` / `CheckpointNotFound`), documentés comme tels
(`services/portfolio.py` : « point d'entrée unique, partagé par l'API et, à terme, par le MCP-B »).
Il ne manquait donc que la couche de transport.

C'est la brique **MCP-B** du `PRD.md` §10/§12.2 (« Portefeuille : l'IA remplit les positions
depuis un doc de transactions ») — les points de contrôle complètent **MCP-C** (thèse vivante) :
ce sont les critères de suivi que le prompt de thèse produit.

## 2. Objectif

Qu'une IA cliente puisse **alimenter et lire** le portefeuille (comptes, transactions,
dividendes, positions, résumé) et **gérer les points de contrôle suivis** d'un titre — sans
navigateur, et sans que le serveur n'analyse aucun document (c'est l'IA qui structure).

## 3. Non-objectifs

- Pas d'import « en masse » d'un document : l'IA appelle `add_transaction` / `add_dividend`
  ligne à ligne, avec la validation existante. Aucun parseur côté serveur.
- Pas d'outils events, settings, valuation, manuel, refresh, backup/restore (hors périmètre
  retenu — cf. note de reprise, extensions ultérieures).
- Aucune nouvelle formule, aucun nouveau seuil, aucune nouvelle table, aucune migration.
- Pas de modification de `web/` ni de `api/app.py`.
- Pas d'outil MCP d'évaluation « attentes vs réalisé » des thèses (incrément ultérieur).

## 4. Exigences

- 4.1 `src/obole/mcp/tools/portfolio.py` : outils comptes (`list_accounts`, `create_account`,
  `delete_account`), transactions (`list_transactions`, `add_transaction`,
  `update_transaction`, `delete_transaction`), dividendes (`list_dividends`, `add_dividend`,
  `update_dividend`, `delete_dividend`), positions (`list_positions`), résumé
  (`get_portfolio_summary`).
- 4.2 `src/obole/mcp/tools/checkpoints.py` : `list_checkpoints`, `add_checkpoint`,
  `update_checkpoint`, `delete_checkpoint`.
- 4.3 Enregistrement des deux modules dans `mcp/tools/__init__.py::register`.
- 4.4 Chaque outil est un **verbe** à docstring descriptive (sa docstring EST la doc de l'IA),
  qui **délègue** à `services/portfolio.py` / `services/checkpoints.py` ; aucune I/O directe
  hors `data/`, aucune logique métier.
- 4.5 Les lectures passent par `services/serialize` (`portfolio_positions_to_list`,
  `portfolio_summary_to_dict`) : payload **identique** à celui de l'API HTTP.
- 4.6 Traduction des erreurs typées en `ToolError` : `portfolio_data.NotFoundError` et
  `CheckpointNotFound` (ressource absente), `ValueError` (entrée invalide).

## 5. Critères d'acceptation

- [x] 13 outils portefeuille + 4 outils suivi exposés (34 outils au total, vs 17 avant)
- [x] Périodes et benchmarks du résumé dérivés de `config.py` dans la docstring (aucun
  littéral qui pourrait dériver de la route `GET /api/portfolio/benchmarks`)
- [x] Parité outil ↔ API testée : `list_positions` et `get_portfolio_summary` renvoient le
  payload exact des routes `GET /api/portfolio/positions` et `.../summary` ;
  `list_checkpoints` celui de `GET /api/checkpoints/{ticker}`
- [x] Cycles CRUD complets testés (comptes, transactions, dividendes, points de contrôle)
- [x] Entrées hostiles rejetées en `ToolError` lisible (compte inconnu, sens/statut/date/devise
  invalide, quantité non positive, montant négatif, libellé vide ou trop long, plafond atteint)
- [x] Aucun seuil littéral dans `mcp/` ; aucun import `obole.api`/`obole.web` ; aucun `print`
  (tests structurels `tests/test_mcp_server.py` verts)
- [x] `pytest -m "not network"` vert (855 tests) ; `ruff check` + `ruff format --check` +
  `mypy` (engine, services, mcp, models) verts

## 6. Invariants préservés

- La calibration Pernod (`z = −3.81`, ±0.15) reste verte (aucun code de calcul touché).
- Règle de couches `web → api → services → engine → data` respectée : le MCP est une couche de
  transport à sens unique vers `services`/`engine`/`data`.
- Les seuils restent **exclusivement** dans `config.py` (`PRD.md` §12.1).
- Mono-devise EUR conservée (aucune conversion introduite).
- `web/` et `api/app.py` inchangés.

## 7. Jalons

- **J1** — Outils portefeuille (comptes, transactions, dividendes).
- **J2** — Lectures sérialisées (positions, résumé) + points de contrôle.
- **J3** — Tests de parité et d'entrées hostiles + vérification outillée.

## 8. Note de reprise

**Livré** (branche `feat/mcp-portefeuille-suivi`).

Décisions :

- **D1 — périmètre « portefeuille + suivi »** (arbitrage utilisateur) : les outils events,
  settings, valuation, saisie manuelle, refresh et backup/restore restent hors périmètre. Ce
  sont les extensions naturelles si un besoin apparaît (chacune une fiche).
- **D4 — discoverabilité du résumé** : les périodes et benchmarks ne sont pas codés en dur dans
  la docstring, ils sont injectés depuis `config.py` (motif `screener.py`), pour rester alignés
  sur la route `GET /api/portfolio/benchmarks` (test de dérive dédié).
- **D2 — pas de point de départ sur `feat/mcp-payload-lean`** : cette branche était très en
  retard sur `main` et supprimait massivement le front (`web/thesis.js`,
  `markdown.js`, `suivi.js`, `checkpoints`, `test_checkpoints.py`…) et **restreint `save_thesis`
  aux objets JSON** (fin du markdown) — rupture de parité thèse MCP ↔ API. Écartée.
- **D3 — état vérifié (déjà couvert)** : la thèse (création + modification) est un **upsert**
  (`save_thesis`, une par ticker) exposé par le MCP ; la création de points de contrôle était
  côté API seulement, désormais exposée.

Fichiers : `mcp/tools/portfolio.py` (13 outils), `mcp/tools/checkpoints.py` (4 outils),
`mcp/tools/__init__.py` (enregistrement + docstring de couche), `tests/test_mcp_tools.py`
(2 classes de test : `TestPortefeuilleViaOutil`, `TestSuiviViaOutil`, fixture `isolated_db`
mutualisée au niveau module).

**Hors périmètre (extensions)** : outils events (annotations de graphe), settings (fenêtres MM),
valuation (prix juste), saisie manuelle des comptes, refresh, backup/restore ; évaluation
« attentes vs réalisé » des thèses (`PRD.md` §12.4, schéma `5 → 6`).
