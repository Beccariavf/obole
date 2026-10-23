# #09.0 — MCP · Socle (serveur MCPServer, transport stdio)

> **Statut :** **fait** · **Priorité :** 🟡 Q2 (important, non urgent — cas (c) évolutivité)
> **Impact Pernod :** 🟢 · **Branche proposée :** `feat/mcp-socle` · **Taille :** ~1 session
> **Fiche parente :** #09 (MCP — surface IA, `PRD.md` §12)

---

## 1. Contexte

`PRD.md` §12 acte le MCP comme **projet à part entière** : « la même app, une surface de plus »,
permettant à une IA de consommer la méthode « droite d'Obole » sans passer par le front web.
`CLAUDE.md` documente la couche `mcp/` comme **planifiée et non implémentée** — le module n'existe
pas dans le dépôt.

Prérequis implicite : le socle doit s'appuyer sur une couche de service propre (#05), sans quoi il
dupliquerait l'orchestration de `engine/analysis.py`.

## 2. Objectif

Un serveur MCP démarrable localement, exposant au moins un outil trivial, avec le transport stdio
par défaut — socle sur lequel brancher les jalons suivants.

## 3. Non-objectifs

- Aucun outil métier à ce stade (jalons 09.1 → 09.3).
- Pas de transport HTTP (option ultérieure, cf. PRD §12.3).
- Pas de modification de `web/` ni de `api/app.py` (règle PRD §12.3).

## 4. Exigences

- 4.1 Créer `src/obole/mcp/server.py` : instance `MCPServer` (SDK MCP v2).
- 4.2 Transport **stdio** par défaut (PRD §12.3).
- 4.3 Un outil de vérification minimal (ex. `ping` / version de l'app) pour valider la chaîne.
- 4.4 Dépendance MCP ajoutée au projet (nom et version **vérifiés**, cf. §6 sécurité).
- 4.5 Docstring descriptive sur chaque outil (la docstring = la doc de l'IA, PRD §12.3).

## 5. Critères d'acceptation

- [x] `src/obole/mcp/server.py` existe et démarre en stdio
- [x] Au moins un outil exposé et appelable (`obole_status`, testé in-memory)
- [x] La dépendance MCP est épinglée dans `requirements.txt` (version réelle vérifiée)
- [x] `grep` : aucun import de `web/` dans `mcp/`
- [x] Aucun seuil ni formule dupliqué (délégation à `engine`/`services`)
- [x] La suite hors réseau reste verte (`pytest -m "not network" -q`)

## 6. Invariants préservés

- La calibration Pernod (`z = −3.81`, ±0.15) reste verte.
- Règle de couches `web → api → services → engine → data` : le MCP est une couche de transport à
  sens unique vers `engine`/`data`, il ne contourne pas le cœur (PRD §12.1).
- Les seuils restent **exclusivement** dans `config.py` (PRD §12.1).
- La dépendance MCP est vérifiée avant installation (pas de nom de paquet halluciné, §2 des règles
  globales).

## 7. Jalons

- **J1** — Vérifier et ajouter la dépendance MCP.
- **J2** — `server.py` + transport stdio.
- **J3** — Outil de vérification minimal + test de démarrage.

## 8. Note de reprise

**Jalon 09.0 livré** (branche `feat/mcp-socle`). Décisions tranchées :

- **Dépendance** : `mcp==2.3.0` (ligne stable **v2**, API `MCPServer`). v1.29.1 est la ligne
  maintenance : démarrer un module neuf dessus aurait imposé une migration à court terme.
  Upstream installe 2.x par défaut. `pip-audit` reste vert malgré les transitives
  (`httpx2`, `jsonschema`, `pyjwt`, `opentelemetry-api`, `sse-starlette`).
- **Emplacement** : `src/obole/mcp/` (et non `mcp/` à la racine) — cohérent avec `where=["src"]`
  du `pyproject` et le layout `src/obole/{api,web,data,...}`. `CLAUDE.md` corrigé en conséquence.
- **Périmètre** : 09.0 seul. 09.1 → 09.3 restent des branches dédiées.

Fichiers : `src/obole/mcp/__init__.py`, `src/obole/mcp/server.py` (instance `mcp` + outil
`obole_status`), `tests/test_mcp_server.py` (transport in-memory + invariants de couche).

**Invariant clé** : stdout = canal du protocole stdio → **jamais de `print()`** dans `mcp/`
(test dédié). Journalisation via `observability` (stderr).

**Prochaine action** : jalon **09.1** (`mcp/01-outils-lecture.md`). Prérequis identifié :
extraire `services/analysis.analyze_ticker(ticker)` (aujourd'hui `fetch_prices` + `analyze`
sont faits inline dans `api/app.py`) pour que l'API **et** le MCP partagent le même point
d'entrée ; prévoir un `services/indices.py` si l'outil indices est retenu. Le 09.2 devra en
outre **déplacer** `_validate_filters`/`_validate_sort_by`/`_validate_score_keys` de
`api/app.py` vers `services/screener.py` (le MCP ne peut pas importer `api/`). Le 09.3 exige
une migration **3 → 4** + extension de `backup.py::_TABLE_COLUMNS`.
