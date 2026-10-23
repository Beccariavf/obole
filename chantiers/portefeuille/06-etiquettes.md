# #17.6 — Portefeuille · Étiquettes (portefeuilles virtuels)

> **Statut :** **fait** · **Priorité :** 🟡 Q2 · **Impact Pernod :** 🟢
> **Branche :** `feat/portefeuille-tags` (à créer au commit) · **Taille :** 1 session
> **Fiche parente :** #17 · **Précédent :** `01-resume.md` · **Suivant :** `03-risque.md`

---

## 1. Contexte

Un compte ne suffit pas : dans un même PEA, on veut isoler des sous-ensembles
(« Actions dividende », « Croissance »…) pour les analyser comme un portefeuille à part.
L'onglet **Résumé** portait déjà un commentaire anticipant un regroupement « par TAGS »
(`pfBreakdownOptions`) ; la fiche `03-risque.md` exigeait un « sélecteur de portefeuille
(compte ou tag) ». Cette fiche tranche le **modèle** et le livre.

Décision utilisateur : l'étiquette vit **sur la transaction** (et non sur la position).
Le portefeuille virtuel = l'ensemble **exact** des transactions étiquetées.

## 2. Objectif

Pouvoir **étiqueter** des lignes du portefeuille et **filtrer** tout l'espace (Résumé,
Positions, Risque) par compte **et/ou** étiquette, l'étiquette étant saisie depuis le
formulaire de transaction comme depuis le tableau des positions. Le MCP expose la même
capacité (cohérence API ↔ IA).

## 3. Non-objectifs

- Pas de table de référence des étiquettes (la liste est le **distinct** des `tag`).
- Pas de multi-étiquettes par transaction (une transaction = au plus une étiquette).
- Pas de portée « transactions sans étiquette » (le sélecteur propose « toutes »).
- Pas d'étiquette sur les dividendes (ils suivent le couple compte × titre étiqueté).

## 4. Exigences

- 4.1 `tag TEXT` nullable sur `portfolio_transactions` ; `config.SCHEMA_VERSION = 7` ;
  `MIGRATIONS[6] = _migrate_6_to_7` (`ALTER TABLE` + index partiel `WHERE tag IS NOT NULL`).
- 4.2 `data/portfolio.py` : `_optional_tag` (trim, vide -> None, longueur ≤
  `config.PORTFOLIO_TAG_MAX`, caractères de contrôle refusés) ; `list_transactions(account_id, tag)`
  (ET) ; `list_tags()` ; `set_tag(account_id, ticker, tag)` (étiquetage groupé par titre).
- 4.3 `data/backup.py` : colonne `tag` sauvegardée ; `_COLUMN_SINCE` tolère une archive
  antérieure (colonne remplie par None) — une sauvegarde d'avant #17.6 reste restaurable.
- 4.4 Migration **sûre en concurrence** : `BEGIN IMMEDIATE` + relecture de version après
  verrou (les connexions concurrentes ne rejouent pas la migration).
- 4.5 `services/portfolio.py` : `transactions(account_id, tag)`, `tags()`,
  `positions(account_id, tag)` (positions portant `tags`), `tag_positions(...)`,
  `summary(..., tag)` (portée + dividendes du portefeuille virtuel via `_scope_dividends`).
- 4.6 API : `tag` en écriture (transactions) et en lecture (transactions, positions,
  summary, risk) ; `GET /api/portfolio/tags` ; `POST /api/portfolio/positions/tag`.
- 4.7 MCP : `tag` sur `add/update_transaction`, `list_transactions`, `list_positions`,
  `get_portfolio_summary` ; nouvel outil `list_portfolio_tags`.
- 4.8 Front : champ **Étiquette** (datalist) dans le formulaire transaction, colonne
  étiquette dans Positions (édition en ligne) et Transactions, sélecteur de portefeuille
  virtuel en tête (`:value` + `@change`, jamais `x-model` — cf. garde-fou benchmark).

## 5. Critères d'acceptation

- [x] Migration v6 → v7 idempotente et **atomique**, base neuve et base v6 convergent
- [x] Migration **concurrente** testée (6 threads sur une base v6, aucune erreur)
- [x] Sauvegarde : `tag` exporté/restauré ; archive sans la colonne acceptée (None)
- [x] Validation : tag trop long / caractères de contrôle refusés (422)
- [x] Filtre par compte ET étiquette ; `list_tags` distinct et trié
- [x] `set_tag` étiquette/efface toutes les transactions d'un titre
- [x] API : routes + 422 (tests `test_portfolio_api.py`) ; parité MCP (tests `test_mcp_tools.py`)
- [x] Front : champ, pastille, sélecteur ; e2e Chromium + WebKit (parcours complet)
- [x] Suite hors réseau verte ; `pytest -m network` vert (Pernod `z = −3.81`)

## 6. Invariants préservés

- Calibration Pernod (`z = −3.81`) inchangée (aucune formule touchée).
- `engine/portfolio.py` reste pur ; aucune formule dupliquée.
- `config.py` = source unique (`PORTFOLIO_TAG_MAX` exposé via `/api/meta`).
- Palette projet respectée (bleu = bien) ; note libre **conservée** à côté de l'étiquette.

## 7. Jalons

- **J6.1** — Migration v6 → v7 (+ concurrence) + validation + backup + tests.
- **J6.2** — `services` + routes + `list_tags` + `set_tag` + tests API/MCP.
- **J6.3** — Front (champ, colonne, sélecteur) + Vitest + e2e.

## 8. Note de reprise

**Livré.** Modèle **A** (étiquette sur la transaction) : portefeuille virtuel = ensemble
exact des transactions étiquetées (cohérent pour le TWR et le drawdown, réutilise
`daily_values`/`twr_series` sans code neuf). L'étiquetage d'une **position** depuis l'UI
écrit en masse sur ses transactions (`set_tag`).

`services.summary(..., tag)` est **rétro-compatible** (paramètre par défaut `None`) → les
routes et outils existants continuent de fonctionner. Les faux positifs « ticker non
valorisable » de la parité sont neutralisés (`tickers` borné aux transactions de la portée).

Correctif de revue : `_migrate` passe en **`BEGIN IMMEDIATE`** + relecture de version
après verrou — l'`ALTER TABLE` (non `IF NOT EXISTS`) exposait une course
« duplicate column name » sous accès concurrent (détectée par `test_screener_j5`).
`_migrate_6_to_7` tolère en outre le doublon (ceinture et bretelles).

Revue (suite) :
- **Couleurs centralisées** : l'échelle divergente de la heatmap de corrélation quitte
  `portfolio.js` pour `theme.js` (`C.corrScale`, extrémités dérivées de `C.accent`/`C.bad`)
  et le fill du drawdown réutilise `C.badFill`.
- **Sens de l'échelle corrigé** : bleu à `z = −1` (décorrélé), rouge à `z = +1` (corrélé) —
  conforme à la légende (testé en Vitest).
- **Portée du sélecteur** : `GET /api/portfolio/tags?account_id=` scope la liste au compte
  courant ; changer de compte réinitialise l'étiquette (et `reloadPortfolioData` y retombe si
  elle a disparu), avec un message d'état vide contextualisé (`pfNoDataHint`).
- Code mort retiré (`clearPositionTag`, `_pfCorrH`).

Tests : `tests/test_portfolio_risk.py` (31), `tests/test_portfolio_{data,api}.py` étendus,
`tests/test_schema_migration.py` (+2 concurrence/`tag`), `tests/test_mcp_tools.py` (+4),
`web-tests/portfolio-risque.test.js` (17), e2e `portfolio.spec.js` (+2). Suite hors réseau
**983 ✅**, réseau **5 ✅** (Pernod `z = −3.81`), ruff/mypy verts, `pip-audit` propre.

**Prochaine action.** Jalon `02-positions` (tableau complet + agrégats consolidés) — les
étiquettes y alimentent déjà la colonne et le sélecteur.
