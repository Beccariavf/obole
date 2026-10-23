# #09.1 — MCP · Outils de lecture (stock, ratio, search, indices)

> **Statut :** **fait** · **Priorité :** 🟡 Q2 (important, non urgent — cas (c) évolutivité)
> **Impact Pernod :** 🟢 · **Branche proposée :** `feat/mcp-lecture` · **Taille :** ~1-2 sessions
> **Fiche parente :** #09 (MCP — surface IA) · **Précédent :** `mcp/00-socle.md`

---

## 1. Contexte

`PRD.md` §12.2, temps 1 — « Lecture & indices » : exposer l'existant pour que l'IA puisse lire la
fiche d'une valeur, comparer un ratio A/B, rechercher un ticker, et **composer ses propres
indices** (CRUD complet).

Toute la logique existe déjà (`engine/`, `data/`, couche de service #05). Le travail consiste donc
en une **exposition**, sans nouvelle logique métier (PRD §12.3 : « pas de logique métier dans les
outils »).

## 2. Objectif

Qu'une IA cliente puisse consommer l'analyse Obole complète sans navigateur : fiche, ratio,
recherche, et gestion des indices personnalisés.

## 3. Non-objectifs

- Pas de screener (jalon 09.2), pas de thèse (jalon 09.3).
- Aucune nouvelle formule, aucun nouveau seuil.
- Pas d'écriture hors CRUD des indices (qui existe déjà).

## 4. Exigences

- 4.1 Outil `get_stock_analysis(ticker)` → analyse complète (identité, indicateurs, valorisation).
- 4.2 Outil `get_ratio_analysis(a, b)` → ratio A/B (β, ρ, régression).
- 4.3 Outil `search_tickers(query)` → suggestions.
- 4.4 Outils CRUD des indices personnalisés (créer, lister, lire, mettre à jour, supprimer).
- 4.5 Chaque outil est un **verbe** à docstring descriptive, sans logique métier (délégation).
- 4.6 **Prérequis (identifié lors du jalon 09.0)** : extraire
  `services/analysis.analyze_ticker(ticker)` — aujourd'hui `api/app.py::get_stock` fait
  `yahoo.fetch_prices` puis `services.analysis.analyze` **inline**, ce que le MCP ne peut pas
  réutiliser sans dupliquer l'orchestration (interdit). L'extraction fait de `services/` le
  point d'entrée **partagé API ↔ MCP**. Si l'outil indices est retenu (4.4), prévoir de même un
  `services/indices.py` (aujourd'hui `data/indices.py` n'a pas de façade de service).

## 5. Critères d'acceptation

- [x] Les 4 familles d'outils sont exposées et appelables
- [x] Chaque outil délègue à `services/`/`engine/` (aucune formule dans `mcp/`)
- [x] Un test vérifie qu'un outil renvoie la même donnée que la route API équivalente
- [x] `grep` : aucun seuil littéral dans `mcp/`
- [x] La suite hors réseau reste verte (`pytest -m "not network" -q`)

## 6. Invariants préservés

- La calibration Pernod (`z = −3.81`, ±0.15) reste verte.
- **Aucune duplication de formule ni de seuil** : `config.py` reste la source unique (PRD §12.1).
- Le MCP ne touche pas `web/` ni `api/app.py` (PRD §12.3).
- Aucun nouvel appel réseau non-cache (PRD §12.3).

## 7. Jalons

- **J1** — `get_stock_analysis` + `search_tickers`.
- **J2** — `get_ratio_analysis`.
- **J3** — CRUD des indices.
- **J4** — Tests de parité outil ↔ API.

## 8. Note de reprise

**Jalon 09.1 livré** (branche `feat/mcp-lecture`).

**Façades `services/` (prérequis 4.6, extrait au 09.0).** L'orchestration
« fetch prix + analyse » ne vit plus dans `api/` : trois points d'entrée partagés
API ↔ MCP ont été ajoutés à `services/analysis.py` :

- `analyze_ticker(ticker) -> (StockAnalysis, PriceSeries)` ;
- `analyze_ratio_tickers(a, b) -> (RatioAnalysis, série…)` ;
- `analyze_index(index_id, definition) -> (BasketAnalysis, série)`.

Nouveau `services/indices.py` : façade CRUD (list/get/create/update/delete +
catégories + refresh), portant la validation/coercion et une erreur **typée**
`IndexNotFound` (ressource absente → 404 côté API). `data/indices.py` garde la
validation métier (nom vide, < 2 membres) ; l'API ne duplique plus rien.

**Déplacement de la sérialisation.** `api/serialize.py` a été **déplacé** vers
`services/serialize.py` (le MCP ne peut pas importer `api/`) et l'ancien module
`api/` a été **supprimé** : `api/app.py` et les tests importent désormais
`obole.services.serialize` directement (sens `api → services`, légal). Correction
de typage au passage : `_events_payload(kind, ref: str | int)`.

**Outils MCP** (`src/obole/mcp/tools/`, un module par famille, `register(server)`) :

- `stock.py` → `get_stock_analysis(ticker)` ;
- `ratio.py` → `get_ratio_analysis(a, b)` ;
- `search.py` → `search_tickers(query)` ;
- `indices.py` → `list_indices`, `get_index_analysis`, `create_index_category`,
  `delete_index_category`, `create_index`, `update_index`, `delete_index`.

`server.py` appelle `tools.register(mcp)` en fin de module (import tardif pour
éviter un cycle). Erreurs traduites en `ToolError` (message lisible côté IA).

**Tests.** `tests/test_mcp_tools.py` (14 tests) : parité stricte
`outil == route HTTP` pour stock / ratio / search / indice, CRUD via outil,
erreurs typées, entrée hostile. `tests/test_mcp_server.py` étendu : la lecture
des sources `mcp/` est désormais **récursive** (sous-dossier `tools/` couvert
par les invariants « pas d'import api/web », « pas de print/stdout », « pas de
seuil littéral »).

**Vérifications.** `ruff check` + `ruff format --check` verts ; `mypy`
engine+services+mcp+models = 28 fichiers OK ; `pytest -m "not network"` =
**655 passed** ; `pytest -m network` = **5 passed** (Pernod `z = −3.81`
préservé). Smoke stdio réel : 11 outils listés, `search_tickers` OK, **stderr
vide**.

**Prochaine action** : jalon **09.2** (`mcp/02-screener-fr.md`). Prérequis
(4.5) : **déplacer** `_validate_filters`/`_validate_sort_by`/
`_validate_score_keys` de `api/app.py` vers `services/screener.py` avant
d'écrire l'outil (le MCP ne peut pas importer `api/`).
