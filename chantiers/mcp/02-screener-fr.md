# #09.2 — MCP · Screener FR (`screen_french_stocks`)

> **Statut :** **fait** · **Priorité :** 🟡 Q2 (important, non urgent — cas (c) évolutivité)
> **Impact Pernod :** 🟢 · **Branche (historique) :** `feat/mcp-screener` · **Taille :** ~1 session
> **Fiche parente :** #09 (MCP — surface IA) · **Précédent :** `mcp/01-outils-lecture.md`
> **Dépend de :** le screener web (fiche `chantiers/screener.md`, J0–J5 déjà validés)

---

## 1. Contexte

`PRD.md` §12.2, temps 2 — « Screener FR » : exposer `screen_french_stocks(filters)` sur un univers
FR éditable, avec les filtres = seuils du PRD §5 (σ, ROE, potentiels, capi, secteur…).

Le moteur existe déjà côté web : `data/screener.py` (univers + cache), `engine/screen.py` (logique
pure de filtrage/tri), `api/app.py` (routes `/api/screener/*`). Le travail est une **exposition**,
pas une réécriture.

## 2. Objectif

Qu'une IA puisse demander « les actions FR décotées avec un ROE > 10 % » et recevoir un tableau
trié, sans passer par la modale web.

## 3. Non-objectifs

- Pas de nouvel univers (l'extension Europe est le jalon J6 du screener web, hors MCP).
- Pas de nouveau critère de filtrage : on réutilise ceux du PRD §5.
- Pas de logique métier dupliquée depuis `engine/screen.py`.

## 4. Exigences

- 4.1 Outil `screen_french_stocks(filters)` → tableau trié de résultats.
- 4.2 Les filtres correspondent aux seuils du PRD §5 (aucun nouveau seuil défini dans `mcp/`).
- 4.3 **Cache agressif obligatoire** : un scan = N appels yfinance (PRD §12.2).
- 4.4 Les paramètres d'entrée sont validés strictement (entrée hostile par défaut).
- 4.5 **Prérequis (identifié lors du jalon 09.0)** : déplacer la validation des filtres de
  `api/app.py` (`_validate_filters`, `_validate_sort_by`, `_validate_score_keys`) vers
  `services/screener.py` **avant** d'écrire l'outil. Le MCP ne peut pas importer `api/`
  (invariant de couche) : sans ce déplacement, la validation serait dupliquée. Après le
  déplacement, l'API et le MCP consomment la **même** validation.

## 5. Critères d'acceptation

- [x] L'outil est exposé et appelable avec des filtres
- [x] Aucun seuil littéral dans `mcp/` (tout vient de `config.py`)
- [x] Le cache est utilisé : un second appel identique ne refait pas le scan réseau
- [x] Les entrées invalides sont rejetées proprement (pas de crash)
- [x] La suite hors réseau reste verte (`pytest -m "not network" -q`)

## 6. Invariants préservés

- La calibration Pernod (`z = −3.81`, ±0.15) reste verte.
- Aucune duplication de formule ni de seuil (PRD §12.1).
- Aucun nouvel appel réseau non-cache (PRD §12.3).
- Le MCP ne touche pas `web/` ni `api/app.py` (PRD §12.3).

## 7. Jalons

- **J1** — Outil + validation des filtres.
- **J2** — Vérification du cache (pas de re-scan).
- **J3** — Tests (filtres nominaux, entrées invalides, cache).

## 8. Note de reprise

**Jalon 09.2 livré** (branche `feat/mcp-screener`).

**Prérequis 4.5 soldé — validation partagée.** `_validate_filters`,
`_validate_sort_by` et `_validate_score_keys` sont **sortis de `api/app.py`** et
vivent désormais dans `services/screener.py` sous forme **publique** :
`validate_filters`, `validate_sort_by`, `validate_score_keys`. **Le bornage des
pré-filtres est partagé lui aussi** : `validate_min_market_cap` (`>= 0`) et
`validate_regression_window` (`> 0`) vivent dans `services/` (borne de valeur =
métier), appelés par `api/app.py::_cast_capi`/`_cast_window` **et** par l'outil
MCP. Toutes lèvent `ValueError` (erreur métier, plus de `HTTPException` dans
`services/`) ; l'API les enveloppe pour produire un **422** avec les mêmes
messages qu'avant, et le MCP les traduit en `ToolError`. Seul le sentinelle
`_UNSET` (défaut de body HTTP) reste dans `api/` : c'est du transport pur.

**Sérialisation partagée.** Nouveau `services/serialize.py::screen_run_to_dict(run)`
(composition unique du payload `{source, count, tickers_count, rows}`). L'API et
l'outil MCP l'appellent tous les deux : leurs réponses sont **strictement
identiques** (parité, décision D3). Le payload n'est **pas** allégé pour l'IA
(`colors`, `warnings` conservés) — c'est la garantie de parité du jalon 09.1.

**Outil MCP.** `src/obole/mcp/tools/screener.py::screen_french_stocks(...)`
(`min_market_cap`, `sectors`, `regression_window`, `filters`, `sort_by`,
`score_keys`), branché par `tools/__init__.py::register`. Le défaut de capi est
`config.SCREEN_DEFAULT_MIN_CAP` (aucun littéral) ; `null` = univers complet.
Docstring verbe détaillée (critères filtrables, format `sort_by`, usage du score).

**Tests.** `tests/test_mcp_tools.py` étendu : parité stricte `outil ==
POST /api/screener/run` (payload complet, avec et sans filtres/tri), cache (un
seul scan réseau pour deux appels identiques, `source == "cache"`), entrées
hostiles (filtre/tri inconnus, bornes inversées, sens invalide, capi négative,
fenêtre <= 0 -> `ToolError`), `score_keys` inconnu ignoré, défaut capi = `config`,
docstring énumérant les critères depuis la source unique. `tests/test_services_screener.py`
étendu : tests unitaires des `validate_*` **et** du bornage (`validate_min_market_cap`,
`validate_regression_window`). Suite complète : **700 non-network + 5 network** vertes.

**Vérifications.** `ruff check` + `ruff format --check` verts ; `mypy`
engine+services+mcp+models = 29 fichiers OK ; `pytest -m "not network"` =
**700 passed** ; `pytest -m network` = **5 passed** (Pernod `z = −3.81` préservé).
Smoke stdio réel : **12 outils** listés (dont `screen_french_stocks`), erreur
métier remontée proprement (`ToolError`), stderr sans traceback.

**Prochaine action** : jalon **09.3** (`mcp/03-these-entreprise.md`) — thèse
d'entreprise + persistance SQLite (migration schéma 3 → 4).
