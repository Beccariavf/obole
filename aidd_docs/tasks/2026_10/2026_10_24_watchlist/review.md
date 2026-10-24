# Review: watchlist à tiers, marges et fenêtre de confiance

- Rounds: 1
- Started: 2026-10-24

## Round 1 · r-c4a1

- Date: 2026-10-24
- By: Beccariavf
- Diff: `main...feat/watchlist`
- Axes: code, functional, relevancy
- Verdict: approve
- Score: 31/31 met, 0 unmet, 0 unverified at runtime, 0 out of the diff

### Criteria

- [x] Base neuve en v8 avec les deux tables — `tests/test_schema_migration.py::TestWatchlistMigration`
- [x] Base v7 migrée sans perte — `tests/test_schema_migration.py::TestWatchlistMigration::test_v7_db_gains_tables_without_data_loss`
- [x] `added_at` préservé au changement de tier — `tests/test_watchlist.py::TestWatchlistItems::test_tier_change_preserves_added_at`
- [x] Registre de sauvegarde + archive v7 restaurable — `tests/test_backup.py::TestOlderArchive`, `TestBackupRegistry`
- [x] Tests du domaine verts + ruff — `pytest -m "not network"`, `ruff check .`
- [x] Sans référence, « Prix juste » = droite 20 ans — `tests/test_analysis.py::TestFairPriceReference::test_no_reference_keeps_20y_default`
- [x] Avec référence, droite de référence + note « prix bruts » — `tests/test_analysis.py::TestFairPriceReference::test_reference_drives_the_fair_price_and_the_note`
- [x] Prix juste enregistré prioritaire — `tests/test_analysis.py::TestFairPriceReference::test_saved_fair_price_wins_over_reference`
- [x] `windowed_analysis(ref_start=…)` tranche raw/adj — `tests/test_screen.py::TestWindowedAnalysis`
- [x] `scan_parallel` conserve budget/timeout — `tests/test_screener_j5.py`, `tests/test_services_screener.py`
- [x] Test réseau + mypy — `pytest -m network`, `mypy`
- [x] `run()` trie par marge, absentes puis erreurs — `tests/test_watchlist.py::TestRun`
- [x] Prix juste enregistré prioritaire + source de repli — `tests/test_watchlist.py::TestRun::test_rows_are_sorted_by_margin_with_saved_price`
- [x] Erreurs de ticker isolées, tier conservé — `tests/test_watchlist.py::TestRun::test_error_row_keeps_tier_and_goes_last`
- [x] `/api/stock` porte `watch`, `/api/meta` porte `watch` — `tests/test_watchlist_api.py`, smoke serveur (RI/BNP/CW8)
- [x] Validations 422 (tier/date/plafond/points) — `tests/test_watchlist_api.py`
- [x] Parité MCP `get_watchlist` / `rank_watchlist` — `tests/test_mcp_tools.py::TestWatchlistTools`
- [x] `view=summary` sous-ensemble, `max_rows`/`tier` — `tests/test_mcp_tools.py::TestWatchlistTools`
- [x] Read-only masque les écritures — `tests/test_mcp_read_only.py`
- [x] Aucun outil MCP pour la référence / le prix juste — `src/obole/mcp/tools/watchlist.py`, `WRITE_TOOLS`
- [x] Tests MCP sans réseau — `tests/test_mcp_tools.py` (services monkeypatchés)
- [x] Bouton entre Portefeuille et Paramètres — `web-tests/e2e/watchlist.spec.js`
- [x] Étoile : ajout / déplacement / retrait local — `web-tests/e2e/watchlist.spec.js`
- [x] Modale : tiers, compteurs, tri, badges, états, ligne → fiche — `web-tests/e2e/watchlist.spec.js`
- [x] Référence : définir / voir / effacer, fiche rechargée — e2e « référence », smoke serveur (Résumé suit)
- [x] Aucun seuil littéral, `app.js` < 500, fetch centralisé — `web-tests/watchlist.test.js`, `modules.test.js`
- [x] Backend non-network + network — runs cités ci-dessus
- [x] `ruff`, `ruff format --check`, `mypy` — vérifiés
- [x] `npm test` + `npm run test:e2e` — vérifiés
- [x] QA manuelle RI/BNP/CW8 sur serveur réel (schéma v8) — smoke API : refs, Résumé aligné, prix juste enregistré prioritaire, prix juste effacé → retour 20 ans
- [x] Revue sans constat bloquant — ce rapport

### Findings

- `aidd_docs/memory/data.md:67` : `valuation_settings` reste hors du registre de sauvegarde (le prix juste enregistré n'est pas protégé par une archive) → gap documenté dans `aidd_docs/memory/data.md` et #25 ; l'y ajouter exige une politique « préserver si absente » dans `restore_archive` (sinon une archive ancienne efface les prix justes) — 🟢 minor, fit
- `src/obole/services/watchlist.py:342` : `saved` est lu hors du worker du scan ; une erreur SQLite ferait échouer tout le classement au lieu d'isoler une ligne → comportement acceptable en mono-poste (les seules erreurs attendues sont isolées par ticker) — 🟢 minor, error-handling
- `src/obole/web/watchlist.js:132` : `watchError` est partagé entre le popover de l'étoile et la modale ; une erreur d'ajout peut réapparaître à l'ouverture de la modale → réinitialisée à l'ouverture de la modale, reste visible dans le popover — 🟢 minor, frontend
