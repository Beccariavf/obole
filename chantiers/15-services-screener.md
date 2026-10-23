# #15 — Finir la couche `services/` (extraire le cas d'usage screener)

> **Statut :** fait · **Priorité :** 🟡 Q2 (important — cas (c) évolutivité)
> **Impact Pernod :** 🟠 · **Branche (mergée) :** `refactor/services-screener` · **Taille :** ~1 session
> **Fiche parente :** #05 (couche `services/`)

---

## 1. Contexte

`CLAUDE.md` pose l'invariant `web → api → services → engine → data`. Le chantier #05 a extrait
`services/analysis.py` et `services/screen.py` (`screen_stock` par ticker), mais **le cas d'usage
screener complet est resté inline dans `api/app.py`** :

- `api/app.py` importait `engine` **en direct** (`from obole.engine import screen as screen_engine`,
  utilisé pour `FILTERABLE_KEYS`, `SORTABLE_KEYS`, `filter_and_sort`) — violation de la règle
  « `api/` n'appelle jamais `engine/` ».
- `_scan_universe` (scan parallèle + garde-fou timeout), la clé de cache de scan et la construction
  des `ScreenResult` vivaient dans `api/app.py` : `api/` faisait le travail de `services/`.

Conséquence : la chaîne était fausse sur son maillon central — précisément celui que le MCP (#09)
devrait réutiliser. Un outil MCP screener aurait dû soit appeler l'API HTTP, soit dupliquer cette
orchestration.

## 2. Objectif

Que `api/` redevienne une frontière fine (validation HTTP + sérialisation) et que **tout le cas
d'usage screener** vive dans `services/`, réutilisable par l'API et, à terme, par le MCP.

## 3. Non-objectifs

- Ne pas toucher aux formules ni aux seuils (`engine/`, `config.py` inchangés).
- Ne pas changer le comportement observable (mêmes routes, mêmes réponses, mêmes 422).
- Ne pas déplacer la **validation HTTP** (`_cast_*`, `_validate_*`) hors de `api/` : c'est une
  frontière web, pas du métier.

## 4. Exigences

- 4.1 Créer `services/screener.py::run_screen(...)` : passe 1 (`fetch_universe`) + passe 2
  (`_scan_universe`) + cache de scan + `filter_and_sort`.
- 4.2 Déplacer `_scan_universe` de `api/app.py` vers `services/screener.py`.
- 4.3 Ré-exporter `FILTERABLE_KEYS` / `SORTABLE_KEYS` via `services/screener.py` (l'API ne touche
  plus `engine`).
- 4.4 `api/app.py::screener_run` = validation + appel `run_screen` + sérialisation.
- 4.5 La **clé de cache** de scan reste strictement identique (un cache chaud reste exploité).

## 5. Critères d'acceptation

- [x] `grep "from obole.engine" src/obole/api/` → 0 résultat
- [x] `screener_run` : aucune boucle de scan, 5 instructions hors docstring
- [x] `run_screen` testé hors réseau (yfinance mocké) — `tests/test_services_screener.py`
- [x] Clé de cache inchangée (test `test_cache_key_is_stable`)
- [x] 422 préservés (filters/sort_by/capi/fenêtre) ; dégradation gracieuse intacte
- [x] `FILTERABLE_KEYS`/`SORTABLE_KEYS` exposés via `services/screener.py`

## 6. Invariants préservés

- Calibration Pernod (`z = −3.81`, ±0.15) verte (`pytest -m network`).
- Aucune duplication de formule ni de seuil (`config.py` reste la source unique).
- Parallélisme (`SCREEN_WORKERS`) et garde-fou timeout global intacts.
- La clé de cache de scan est inchangée (sinon purge = re-scan réseau).

## 7. Jalons

- **J1** — `services/screener.py::run_screen` + `_scan_universe`.
- **J2** — Amincissement de `api/app.py` (imports, suppression `_scan_universe`, `screener_run`).
- **J3** — Tests service + mise à jour des tests existants (chemins de patch).

## 8. Note de reprise

Fait : `services/screener.py` créé (127 l.), `api/app.py` allégé (~35 l. en moins), 5 tests service
ajoutés. Suite hors réseau verte (`pytest -m "not network" -q`), `-m network` vert,
`ruff check` + `ruff format --check` + `mypy` verts. Reste : commit
+ merge `--no-ff`.
