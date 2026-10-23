# #12 — Cache `pickle` → format inspectable

> **Statut :** **abandonné** · **Priorité :** ⚪ Q4 (ni urgent ni important)
> **Impact Pernod :** 🟢 · **Branche proposée :** _(aucune — non planifié)_ · **Taille :** ~1 session

---

## 1. Contexte

`data/cache.py::get` utilise `pickle.loads` pour désérialiser les blobs du cache. Le PRD et
`CLAUDE.md` le documentent : les blobs sont **picklés**, dans une base locale que l'utilisateur
contrôle seul.

Le point de sécurité est théorique : `pickle` est dangereux sur des données **non maîtrisées**
(désérialisation arbitraire). Ici la source est exclusivement locale et produite par l'application
elle-même — pas de donnée entrante externe. Le risque est donc **nul en pratique** pour un outil
monoposte sans exposition réseau.

## 2. Objectif

_(Non poursuivi.)_ Remplacer `pickle` par un format inspectable (JSON / Parquet) aurait un intérêt
marginal : lisibilité du cache à la main, et suppression d'un vecteur théorique.

## 3. Non-objectifs

Tout le chantier est hors périmètre, par décision assumée.

## 4. Exigences

_(Aucune.)_

## 5. Critères d'acceptation

_Chantier abandonné : aucun critère technique. Le seul critère applicable est la traçabilité de la
décision._

- [x] Décision d'abandon documentée et justifiée par la règle §1.1 (ni urgent ni important)
- [x] Condition de réouverture explicite (exposition réseau) mentionnée en note de reprise

## 6. Invariants préservés

Le comportement actuel du cache est conservé tel quel.

## 7. Jalons

_(Aucun.)_

## 8. Note de reprise

**Décision : abandonné, assumé.**

Justification (règle §1.1 : ni urgent ni important) :
- **Pas urgent** : aucun cas (a) blocage, (b) irréversible, (c) dépendance externe.
- **Pas important** : ne sert ni la justesse (a), ni la confiance dans les données (b — le cache
  est jetable par nature), ni l'évolutivité (c — `pickle` fonctionne).

Le chantier est **inscrit pour mémoire** afin que la question ne soit pas rouverte sans raison.
À reconsidérer uniquement si l'outil venait à être exposé au réseau (ce qui contredirait sa nature
monoposte) — auquel cas `#03` (sauvegarde) et l'observabilité deviendraient prioritaires avant
celui-ci.
