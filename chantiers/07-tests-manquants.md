# #07 — Tests manquants (`data/indices.py`, couverture)

> **Statut :** à faire · **Priorité :** 🔵 Q3 (urgent, pas important — à expédier)
> **Impact Pernod :** 🟢 · **Branche proposée :** `test/data-coverage` · **Taille :** ~½ session

---

## 1. Contexte

- `data/indices.py` (101 lignes) est la **seule brique de `data/` sans test direct**. Les indices
  personnalisés sont testés indirectement via `tests/test_indices_api.py` (couche API), mais pas
  la logique du module lui-même.
- La **couverture n'est pas mesurée** : `pytest-cov` n'est même pas dans `requirements.txt`, alors
  que `CLAUDE.md` en parle (« passer `-p no:cov` »). On ne connaît donc pas les zones non couvertes.

## 2. Objectif

Connaître la couverture réelle et combler les trous les plus critiques, en commençant par
`data/indices.py`.

## 3. Non-objectifs

- Pas d'objectif de « 100 % de couverture » : c'est un indicateur, pas une fin.
- Pas de test du réseau (yfinance reste mocké).
- Pas de refonte de `data/indices.py`.

## 4. Exigences

- 4.1 `pytest-cov` ajouté aux dépendances de dev, avec un rapport de couverture activable.
- 4.2 Tests unitaires directs de `data/indices.py` (CRUD des définitions d'indices).
- 4.3 Un seuil de couverture raisonnable est fixé dans la config (`fail_under`) — valeur à
  déterminer après la première mesure, pas avant.
- 4.4 Les cas limites sont couverts : indice inexistant, catégorie inexistante, liste vide.

## 5. Critères d'acceptation

- [ ] `pytest-cov` installé et utilisable (`pytest --cov`)
- [ ] Couverture mesurée et consignée dans la fiche (note de reprise)
- [ ] `data/indices.py` a des tests directs (cas nominal + limites + erreurs)
- [ ] Un seuil `fail_under` est défini dans `pyproject.toml`
- [ ] La suite hors réseau reste verte (`pytest -m "not network" -q`)

## 6. Invariants préservés

- La calibration Pernod (`z = −3.81`, ±0.15) reste verte.
- Aucun test existant modifié dans sa logique (on en ajoute).
- Le temps de la suite hors réseau reste raisonnable (< 30 s).

## 7. Jalons

- **J1** — Ajouter `pytest-cov`, mesurer la couverture, consigner le chiffre.
- **J2** — Tests directs de `data/indices.py`.
- **J3** — Fixer le seuil `fail_under` en dessous du chiffre mesuré (marge de sécurité).

## 8. Note de reprise

_(vide — chantier non commencé)_
