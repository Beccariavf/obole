# #22 — Document financier CSV exhaustif (toutes les métriques du tableau)

> **Statut :** fait · **Priorité :** 🟡 Q2 · **Impact Pernod :** 🟠
> **Branche (historique) :** `feat/csv-comptes-complet` · **Taille :** ~1 session

---

## 1. Contexte

Le « document financier CSV » de la fiche (export/import des données manuelles) ne couvrait
que **7 métriques cœur** figées, alors que le tableau des comptes réel en porte le double :

- `src/obole/data/manual.py` : `CORE_METRICS` = 7 noms en dur ; `export_csv`/`import_csv`
  itèrent dessus.
- `src/obole/data/fundamentals.py::build_table` construit en fait ~15 postes **source** et
  ~15 ratios **dérivés** (marges, ROE/ROA/ROCE/ROIC, liquidité, cash conversion, agilité,
  CP/total bilan, DN/EBITDA, gearing, couverture des intérêts, BFR/CA…).
- `_recompute_derived` ne recalculait que **6** dérivés après saisie manuelle.
- `src/obole/web/exportcsv.js::onFileSelect` **redéfinissait en dur** les mêmes 7 noms.

Le reste de l'app (Dividende, Valorisation, Synthèse, Screener) consomme ce tableau : élargir
le CSV élargit tout le reste.

## 2. Objectif

Le CSV exporte/importe **toutes** les données du tableau des comptes : une colonne par métrique,
postes source éditables et ratios dérivés recalculés. La taxonomie est à **source unique**
(`config.py`), servie par `/api/meta` — aucune métrique en dur, ni Python ni JS.

## 3. Non-objectifs

- Pas d'export/import CSV des autres données utilisateur (événements, portefeuille, thèses,
  indices, réglages) : la sauvegarde JSON (`data/backup.py`) reste la référence. Hors périmètre.
- Pas de nouvelle UI : la barre et la modale d'import existantes sont conservées.
- Pas de formule de régression touchée.

## 4. Exigences

- 4.1 `config.FUNDAMENTAL_METRICS` : taxonomie (nom, `role` source|derived) pour le
  schéma industriel, `config.FINANCIAL_METRICS` pour le schéma bancaire, et leur union
  `FUNDAMENTAL_METRICS_ALL` — source unique, exposée par `/api/meta`.
- 4.2 Export CSV exhaustif : une colonne par métrique du tableau réel, pré-remplie (yfinance
  fusionné + manuel), source éditables puis dérivés.
- 4.3 Import CSV : lit toutes les colonnes **source** canoniques, ignore dérivés et colonnes
  inconnues, gère BOM UTF-8 et `\r\n`.
- 4.4 Recalcul complet des dérivés après saisie manuelle, via une fonction de dérivation unique
  partagée avec `build_table`.
- 4.5 Front piloté par `/api/meta` : `exportcsv.js` sans nom de métrique en dur.

## 5. Critères d'acceptation

- [x] CA1 — Taxonomie unique (`config.FUNDAMENTAL_METRICS` + `FINANCIAL_METRICS` + union), exposée par `/api/meta`.
- [x] CA2 — Export CSV exhaustif (toutes les métriques, source/dérivé distingués).
- [x] CA3 — Import lit toutes les colonnes source, ignore dérivées/inconnues, gère BOM/CRLF.
- [x] CA4 — Recalcul complet des dérivés (fonction de dérivation unique `_derive`).
- [x] CA5 — Front piloté par la meta (aucune métrique en dur dans `exportcsv.js`).
- [x] CA6 — Tests : `test_manual.py`, `test_fundamentals.py`, `test_api.py`,
  `labels-parity.test.js`.
- [x] CA7 — Vérifs vertes : ruff, mypy, `pytest -m "not network"`, `pytest -m network`, `npm test`.
- [x] CA8 — Branche dédiée + fiche + index MAJ + note de reprise.

## 6. Invariants préservés

- La calibration Pernod (`z = −3.81`, ±0.15) reste verte — `pytest -m network` OK.
- Les 7 métriques cœur historiques restent des postes **source** (compat des CSV existants).
- Source unique : aucun seuil/métrique dupliqué ; `/api/meta` reste la source des listes.
- Couches à sens unique `web → api → services → engine → data` respectées.
- Les dérivés reposant sur des postes internes non saisissables (ROA, ROCE, ROIC, liquidité,
  CP/total bilan, couverture des intérêts) ne sont **jamais** écrasés par un None.

## 7. Jalons

- **J1** — `config.FUNDAMENTAL_METRICS` + fisc `FINANCIAL_METRICS`.
- **J2** — `data/manual.py` : `SOURCE_METRICS`/`DERIVED_METRICS`, export/import exhaustifs.
- **J3** — `data/fundamentals.py` : `_derive` unique (build_table + recalcul), passage à la
  taxonomie.
- **J4** — `/api/meta` (`fundamental_metrics`) + route template exhaustive.
- **J5** — Front : `thresholds.js` (`FUNDAMENTAL_METRICS`), `exportcsv.js`, `index.html`.
- **J6** — Tests (Python + Vitest) et vérifs outillées.

## 8. Note de reprise

**État : terminé, prêt à fusionner.** Tous les jalons livrés sur
`feat/csv-comptes-complet`, revue de code intégrée.

- Back : `config.FUNDAMENTAL_METRICS` (schéma industriel, 15 source + 15 dérivé) et
  `config.FINANCIAL_METRICS` (schéma bancaire), plus l'union `FUNDAMENTAL_METRICS_ALL`
  (32 métriques) ; `manual.py` (`SOURCE_METRICS`/`DERIVED_METRICS`/`CSV_METRICS`,
  export/import exhaustifs, reconnaissance sur l'union), `fundamentals.py`
  (dérivation factorisée dans `_derive`, partagée par `build_table` et le recalcul
  `_recompute_derived`), `/api/meta` expose `fundamental_metrics` (union), route
  template exhaustive.
- Front : `thresholds.js` porte `FUNDAMENTAL_METRICS` ; `exportcsv.js` lit la
  taxonomie et rapproche les en-têtes sans tenir compte de la casse/des espaces
  (miroir du serveur) ; `index.html` libellés neutres.
- Suite : 842 tests Python hors réseau verts, 5 tests réseau verts, 403 tests front
  verts, ruff + mypy verts.

**Revue de code (5 findings, tous traités) :**
1. Round-trip financier — `manual.py` reconnaît désormais l'union des schémas.
2. ROA financier — alias `_total_assets → Total de l'actif` au recalcul.
3. Aperçu — rapprochement des en-têtes insensible casse/espaces côté front.
4. Libellés — retirés les compteurs sur-vendeurs (texte neutre).
5. Config morte — `FUNDAMENTAL_METRIC_CATEGORIES` et le champ `category` retirés.

**Fusion** : faite sur `main` et poussée, branche `feat/csv-comptes-complet` supprimée (locale et
distante) — chantier clos.
