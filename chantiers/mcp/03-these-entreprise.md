# #09.3 — MCP · Thèse d'entreprise (`write_thesis` + persistance)

> **Statut :** **fait** · **Priorité :** 🟡 Q2 (important, non urgent — cas (c) évolutivité)
> **Impact Pernod :** 🟢 · **Branche :** `feat/mcp-these` · **Taille :** ~1 session
> **Fiche parente :** #09 (MCP — surface IA) · **Précédent :** `mcp/02-screener-fr.md`

---

## 1. Contexte

`PRD.md` §12.2, temps 3 — « Thèse d'entreprise » : un prompt structuré (`write_thesis`) produisant
pitch, bull/bear, métriques clés (σ, perf, ROE, potentiels, qualité), catalyseurs et points de
contrôle, avec **persistance SQLite** des thèses (pattern `data/manual.py` / `data/indices.py`).

Point ouvert explicite (`PRD.md` §12.4) : la thèse fait-elle un **appel LLM côté serveur** ou
est-elle un **prompt** que l'IA cliente déroule ? La valeur par défaut proposée est **prompt** —
sobre, sans dépendance à une API LLM.

## 2. Objectif

Qu'une IA puisse générer une thèse structurée à partir des données Obole, puis la sauvegarder,
lister, relire et supprimer.

## 3. Non-objectifs

- **Pas d'appel LLM côté serveur** (décision par défaut, PRD §12.4) : l'outil fournit le prompt et
  les données, l'IA cliente rédige.
- Pas d'édition collaborative, pas de versionnage des thèses.
- Pas de nouvelle formule : les métriques viennent de l'analyse existante.

## 4. Exigences

- 4.1 Outil `write_thesis(ticker)` → prompt structuré + métriques clés.
- 4.2 Persistance SQLite des thèses : `save` / `list` / `get` / `delete` (pattern `data/manual.py`).
- 4.3 Les thèses survivent au redémarrage et sont **incluses dans la sauvegarde** (#03).
- 4.4 Les entrées sont validées strictement.
- 4.5 **Prérequis (identifié lors du jalon 09.0)** : la persistance des thèses = **nouvelle
  table** → migration schéma **3 → 4** (`config.SCHEMA_VERSION`, `MIGRATIONS[3]` dans
  `data/cache.py`) **et** extension de `backup.py::_TABLE_COLUMNS` (sinon les thèses sont
  absentes de l'export/restauration, contre l'exigence 4.3).

## 5. Critères d'acceptation

- [x] L'outil renvoie un prompt structuré avec les métriques du PRD §12.2
- [x] CRUD des thèses fonctionnel et testé (aller-retour)
- [x] Aucune dépendance à une API LLM ajoutée
- [x] Aucun seuil littéral dans `mcp/`
- [x] La suite hors réseau reste verte (`pytest -m "not network" -q`)

## 6. Invariants préservés

- La calibration Pernod (`z = −3.81`, ±0.15) reste verte.
- Aucune duplication de formule ni de seuil (PRD §12.1).
- Le MCP ne touche pas `web/` ni `api/app.py` (PRD §12.3).
- **Décision PRD §12.4 respectée** : pas d'appel LLM côté serveur.

## 7. Jalons

- **J1** — Outil `write_thesis` (prompt + métriques).
- **J2** — Persistance SQLite (CRUD).
- **J3** — Intégration à la sauvegarde (#03) + tests.

## 8. Note de reprise

**Livré (mergé sur `main`).** Jalon 09.3 complet, réancré sur le code réel (existant) :

- **Schéma 3 → 4** : `config.SCHEMA_VERSION = 4`, `_migrate_3_to_4` (`data/cache.py`) créant
  `theses(id, ticker UNIQUE, content, created_at, updated_at)`. Accesseurs `get/list/save/delete_thesis`
  dans `cache.py`.
- **`data/thesis.py`** : I/O + validation bornée (`THESIS_CONTENT_MAX`), une thèse par ticker (upsert).
- **`services/thesis.py`** : `write_thesis` (prompt + `analysis_to_dict` **privé de `chart`**),
  `save/list/get/delete_thesis` ; erreur typée `ThesisNotFound`.
- **`mcp/tools/thesis.py`** : 5 outils (`write_thesis`, `save_thesis`, `list_theses`,
  `get_thesis`, `delete_thesis`), branchés dans `tools/__init__.py::register`.
- **Sauvegarde (#03)** : `_TABLE_COLUMNS["theses"]` + `_TABLE_SINCE[4]` ; `_check_table_registry()` vert.

**Décisions** : D1 table minimale (ni version ni évaluation) · D2 une thèse par ticker `UNIQUE` ·
D3 métriques via `analysis_to_dict` sans `chart`.

**Tests** : `tests/test_thesis.py` (data + services + backup round-trip), `tests/test_mcp_tools.py`
(cycle CRUD via transport in-memory, erreurs typées), `tests/test_schema_migration.py` (migration
3 → 4, préservation des données, une thèse par ticker). Deux tests utilisaient `3 → 4` comme
emplacement « futur » libre — décalés en `4 → 5`.

**Hors périmètre (fonctionnalité ultérieure)** : évaluation « attentes vs réalisé » (incrément
schéma `4 → 5`), versionnage, DCF, Monte-Carlo, extension Europe.
