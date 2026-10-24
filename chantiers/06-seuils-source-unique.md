# #06 — Source unique des seuils (`/api/meta`)

> **Statut :** fait · **Priorité :** 🔵 Q3 (urgent, pas important — à expédier)
> **Impact Pernod :** 🟠 · **Branche (historique) :** `refactor/seuils-source-unique` · **Taille :** ~1 session

---

## 1. Contexte

Les seuils calibrés existaient **en double** : `config.py` côté serveur
(`DISTANCE_SIGMA_LABELS`, `ECART_TYPE_LABELS`, `PERF_LABELS`, `POTENTIAL_LABELS`, `BETA_LABELS`,
`CORR_LABELS`, `RATIO_THRESHOLDS`) et un miroir dans `web/app.js` (`LABELS`, `RATIO_THRESHOLDS`,
`REG_YEARS_*`, `BETA_MIN_POINTS`). La polarité couleur des labels prix était de plus codée **en
dur des deux côtés** (`good = z < 0`, `value < 35`, `>= 4`, `>= 5`).

La duplication était protégée par `web-tests/labels-parity.test.js`, mais l'utilisateur devait
toujours modifier **les deux côtés**.

## 2. Objectif

Supprimer la duplication **par construction** : le front lit les seuils depuis `/api/meta` au lieu
de les redéfinir.

## 3. Non-objectifs

- Pas de génération de code (codegen) : introduirait un build front, interdit par l'invariant.
- Pas de changement des **valeurs** de seuil (calibrées, cf. PRD §5).
- Pas de suppression des tests de parité (adaptés à la nouvelle source).

## 4. Exigences

- 4.1 `GET /api/meta` renvoie les seuils sérialisés depuis `config.py` (source unique).
- 4.2 `app.js` initialise `LABELS`/`RATIO_THRESHOLDS`/`REG_YEARS_*`/`BETA_MIN_POINTS`/
  `LABEL_POLARITY` depuis cette route (`applyMeta`).
- 4.3 Le front gère l'état « seuils pas encore chargés » (`metaReady` ; `load()` attend la promesse
  `/api/meta`).
- 4.4 `config.LABEL_POLARITY` devient la source unique de la polarité couleur, consommée par
  `engine/labels.py` **et** exposée au front (fin des seuils en dur dans `scored`).
- 4.5 Les tests de parité vérifient que le payload construit depuis `config.py` pilote bien le JS.

## 5. Critères d'acceptation

- [x] `GET /api/meta` renvoie tous les seuils présents dans `config.py`
- [x] Plus aucun seuil littéral dans `app.js` (hors style/couleurs)
- [x] Le front attend le chargement avant tout calcul dépendant d'un seuil
- [x] Tests front verts (`cd web-tests && npm test`) + e2e Chromium/WebKit verts
- [x] Calibration Pernod (`-m network`) verte
- [x] `config.LABEL_POLARITY` : source unique (labels.py + /api/meta)

## 6. Invariants préservés

- Calibration Pernod (`z = −3.81`, ±0.15) verte.
- Valeurs de seuil **inchangées** (on change la source, pas la donnée).
- Front fonctionnel **sans build** et **hors ligne** (seuils servis par le serveur local).

## 7. Jalons

- **J1** — `config.LABEL_POLARITY` + `engine/labels.py` (polarité source unique).
- **J2** — Route `GET /api/meta`.
- **J3** — `app.js::applyMeta` + état de chargement ; suppression des seuils littéraux.
- **J4** — Tests de parité adaptés + tests `/api/meta`.

## 8. Note de reprise

Fait : `config.LABEL_POLARITY` (source unique polarité), `engine/labels._good()` lit `config`,
route `/api/meta`, `app.js::applyMeta` + `metaReady`/`_metaPromise`. `app.js` sans aucun seuil
littéral. **Tout le payload `/api/meta` est consommé** (`corr_min_points` → `corrLive`,
`potential_horizons` → `computeLive`), plus aucun champ mort. Défensif si `/api/meta` échoue
(`classify` renvoie null, `load()`/`loadIndex()` affichent une erreur explicite). Suite backend
verte (`pytest -m "not network" -q`), tests front verts, e2e verts, `ruff` + `mypy` verts.
Clos : travail intégré sur `main`.
