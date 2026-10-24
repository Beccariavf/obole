# #05 — Extraire une couche `services/` (rendre `engine/` pur)

> **Statut :** fait · **Priorité :** 🟡 Q2 (important, non urgent — cas (c) évolutivité)
> **Impact Pernod :** 🟠 · **Branche (historique) :** `refactor/services-layer` · **Taille :** ~1-2 sessions

---

## 1. Contexte

`CLAUDE.md` pose comme **invariant structurel principal** : `web → api → engine → data`, les
dépendances ne remontant jamais dans l'autre sens. `engine/` est décrit comme « cœur 100 % pur
(zéro I/O, zéro réseau) ».

Or `engine/analysis.py` **importe `data/`** :

```python
from obole.data import cache, yahoo
from obole.data.fundamentals import quality_inputs
```

Le fichier fait 291 lignes et orchestre quatre appels réseau (`fetch_identity`,
`fetch_fundamentals`, `fetch_prices`…). Ce n'est plus du `engine` pur : c'est un **cas d'usage**.
L'exception est documentée, mais elle **grandit** — et le MCP (#09) va devoir orchestrer les mêmes
enchaînements.

## 2. Objectif

Rendre `engine/` **effectivement pur** (invariant tenu, testable sans mock, `mypy` étendable), en
isolant l'orchestration dans une couche dédiée réutilisable par `api/` **et** par le MCP.

## 3. Non-objectifs

- Pas de nouvelle logique métier : c'est un **déplacement**, pas une réécriture.
- Pas de framework (pas d'injection de dépendances, pas de conteneur) : des fonctions simples.
- Pas de changement de contrat d'API : les routes renvoient exactement la même chose.

## 4. Exigences

- 4.1 Créer `src/obole/services/` (cas d'usage) entre `api/` et `engine/`.
- 4.2 Déplacer l'orchestration de `engine/analysis.py` vers `services/` (analyse, ratio, basket,
  indices).
- 4.3 `engine/` n'importe **plus rien** de `data/` (vérifiable par `grep`).
- 4.4 `api/app.py` appelle `services/`, pas `engine/analysis.py`.
- 4.5 La règle documentée devient `web → api → services → engine → data`.

## 5. Critères d'acceptation

- [x] `grep -rn "from obole.data" src/obole/engine/` → **0 résultat**
- [x] `engine/analysis.py` supprimé ; `engine/screen.py` réduit au pur (filtre/tri/score)
- [x] Les tests hors réseau restent verts **sans modification de leur logique** (seuls
  les chemins de patch `obole.engine.analysis.*` → `obole.services.*` et les imports changent)
- [x] La calibration Pernod (`-m network`) reste verte (dont `z = −3.81`)
- [x] `mypy src/obole/engine src/obole/services src/obole/models.py` vert
- [x] `CLAUDE.md` mis à jour avec la nouvelle règle de couches

## 6. Invariants préservés

- La calibration Pernod (`z = −3.81`, ±0.15) reste verte.
- Les réponses JSON de l'API sont **identiques** (mêmes clés, mêmes valeurs).
- La dégradation gracieuse de `data/` est conservée (jamais de crash sur un champ vide).

## 7. Jalons

- **J1** — Créer `services/` + y déplacer l'orchestration de `analyze`. ✅
- **J2** — Déplacer ratio / basket / indices + `screen_stock`. ✅
- **J3** — Nettoyer les imports de `engine/`, vérifier le `grep` à zéro. ✅
- **J4** — Mettre à jour `CLAUDE.md` + étendre `mypy` à `services/` (CI incluse). ✅

## 8. Note de reprise

**Fait (2026-09-24).** `engine/analysis.py` supprimé ; orchestration déplacée dans
`services/analysis.py` (analyze, analyze_ratio, analyze_basket, summarize_index,
summarize_indices, `_basket_series`) et `services/screen.py` (`screen_stock` +
helpers `_recompute_window`/`_from_analysis`/`_load_fundamentals`/`_latest`/`_trend_bool`).
`engine/screen.py` ne garde que le pur : `filter_and_sort`, `composite_score`,
`SORTABLE_KEYS`/`FILTERABLE_KEYS`. `api/app.py` importe `obole.services.screen` (alias
`screen_service`, pour le seul `screen_stock`) et `obole.services.analysis` ; `screen_engine`
reste pour les helpers purs. Tests retargetés (patchs `obole.engine.analysis.*` →
`obole.services.*`, `screen.screen_stock` → `screen_service.screen_stock`) — **aucune
assertion touchée**. Doc alignée : `CLAUDE.md`, `PRD.md` §7bis.1/§12, `observability.py`,
`data/yahoo.py`, `api/serialize.py`, CI (`mypy` étendu à `services/`).

Vérifs : `ruff check .` + `ruff format --check .` verts ; `mypy engine services models` vert ;
`pytest -m "not network"` vert ; `pytest -m network` vert (calibration Pernod OK).
