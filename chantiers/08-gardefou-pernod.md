# #08 — Renforcer le garde-fou Pernod (5 mesures)

> **Statut :** fait · **Priorité :** 🟡 Q2 (important, non urgent — cas (a) justesse)
> **Impact Pernod :** 🟢 · **Branche (mergée) :** `test/gardefou-pernod` · **Taille :** ~20 min

---

## 1. Contexte

Le PRD §5 calibre **cinq** mesures sur la fiche de référence (PDF dans `exemple/`),
toutes documentées dans le tableau §5.0 :

| Indicateur | Cible PDF | Valeur retenue (Close brut, historique complet) |
|---|---|---|
| Distance σ (z) | −3.81 | **−3.81** ✅ |
| Potentiel 5 ans | 32.6 % | **32.5 %** ✅ |
| Potentiel 10 ans | 20.0 % | **19.0 %** ✅ |
| Écart-type | 30.1 % | 32.8 % (écart résiduel assumé) |
| Perf passée | 8.5 % | **8.9 %** ✅ (sur Adj Close) |

Or `tests/test_calibration_network.py` ne verrouille **qu'une seule** de ces mesures : le `z`
(`test_pernod_distance_sigma_is_minus_381`). Les deux potentiels et la perf passée — pourtant
calibrés et explicitement validés dans le PRD — **ne sont pas testés**. Une régression du calcul
de potentiel passerait totalement inaperçue.

## 2. Objectif

Étendre le garde-fou central aux mesures calibrées aujourd'hui non testées, sur la **même série
figée au 22/06/2026** (`CALIBRATION_DATE`), pour comparer ce qui est comparable.

## 3. Non-objectifs

- Pas de nouveau seuil métier.
- Pas de refonte de `engine/regression.py` ni de la formule.
- Pas de test de l'écart-type (écart résiduel non résolu, cf. PRD §5.0 — on ne fige pas un
  comportement connu comme approximatif).

## 4. Exigences

- 4.1 Potentiel 5 ans ≈ **32.5 %** sur la série figée au 22/06/2026.
- 4.2 Potentiel 10 ans ≈ **19.0 %** sur la série figée au 22/06/2026.
- 4.3 Perf passée ≈ **8.9 %** sur la série figée (série **Adj Close**, cf. PRD §5.0 : la perf
  affichée se lit sur les dividendes réinvestis, pas sur le Close brut).
- 4.4 La tolérance retenue est **documentée dans le test** (comme le fait déjà le test du `z`).

## 5. Critères d'acceptation

- [x] Le potentiel 5 ans est verrouillé (± tolérance documentée)
- [x] Le potentiel 10 ans est verrouillé
- [x] La perf passée est verrouillée **sur Adj Close**
- [x] La série figée est extraite en helper partagé (évite la duplication)
- [x] `pytest -m network` vert
- [x] `pytest -m "not network"` vert (garde-fou intact)

## 6. Invariants préservés

- Le `z = −3.81` (±0.15) reste verrouillé et vert — **c'est le test qu'on ne touche pas**.
- Aucune modification de `engine/regression.py`, `engine/valuation.py` ou `engine/analysis.py`.

## 7. Jalons

- **J1** — Extraire la série figée en helper réutilisable.
- **J2** — Ajouter les assertions potentiels (5 ans, 10 ans) + perf passée.
- **J3** — Vérifier que le test échoue bien si on casse volontairement la formule (preuve du filet).

## 8. Note de reprise

**Fait.** Garde-fou étendu de 1 à 4 mesures calibrées sur la série figée au
22/06/2026 (`tests/test_calibration_network.py`) :

- `z = −3.81` (±0.15) — inchangé, toujours vert.
- Potentiel 5 ans = 32.5 % (±1.0) — mesuré 32.97 %.
- Potentiel 10 ans = 19.0 % (±1.0) — mesuré 19.16 %.
- Perf passée = 8.9 % (±0.5) sur **Adj Close** — mesuré 8.93 % (brut = 6.79 %,
  le piège PRD §5.0 est documenté dans le test).

Refactor : un helper `_pernod_series()` (séries complètes) + `_pernod_frozen_series()`
(tronquées à `CALIBRATION_DATE`) évitent la duplication ; le test « aujourd'hui »
réutilise `_pernod_series()`.

Preuve du filet (J3) : formule de potentiel biaisée → les 2 tests potentiels
échouent ; `perf_annual` biaisée → le test perf échoue. Reverté, non commité.

⚠️ **Correction de la fiche** : le compteur de tests non-network était figé dans la fiche et
faux. Il a été **retiré** au profit de la commande de vérification (`pytest -m "not network" -q`),
qui seule fait foi. Aucun test pur ajouté/retiré.

Aucune modification de `engine/regression.py`, `engine/valuation.py`,
`engine/analysis.py`, `models.py`.
