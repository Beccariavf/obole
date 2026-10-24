# Phase 1 — Domaine persistant

## Scope

- `config.py` : `WATCH_TIERS`, `WATCHLIST_MAX_ITEMS`, `REGRESSION_MIN_POINTS`, `SCHEMA_VERSION = 8`.
- `data/cache.py` : tables `watchlist_items` et `ticker_refs`, migration `_migrate_7_to_8`,
  fonctions SQL (items + refs), `upsert_watch_item` qui préserve `added_at`.
- `data/backup.py` : déclaration des deux tables (`_TABLE_COLUMNS`, `_TABLE_SINCE[8]`).
- Tests : migration base neuve et 7→8, CRUD SQL, registry backup, restauration d'une archive v7.

## Acceptance

- [ ] Une base neuve est en v8 avec les deux tables.
- [ ] Une base v7 migre sans perte et reçoit les tables.
- [ ] `upsert_watch_item` ne réécrit pas `added_at` lors d'un changement de tier.
- [ ] `_check_table_registry()` passe ; l'archive v7 reste restaurable.
- [ ] `pytest -m "not network"` vert ; `ruff` vert.
