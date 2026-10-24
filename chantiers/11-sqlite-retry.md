# #11 — Retry SQLite sur `database is locked`

> **Statut :** en cours — revue approuvée, PR draft à relire · **Priorité :** 🔵 Q3 (urgent, pas important — à expédier)
> **Impact Pernod :** 🟢 · **Branche :** `fix/sqlite-retry` · **Taille :** ~½ session

---

## 1. Contexte

Le screener écrit en base depuis plusieurs threads : `api/app.py::screener_run` crée un
`ThreadPoolExecutor(max_workers=config.SCREEN_WORKERS)` et soumet une tâche par
ticker. Ces tâches écrivent leur résultat dans le cache SQLite.

`data/cache.py::_conn` active WAL (`PRAGMA journal_mode=WAL`) et un `busy_timeout`
(`config.SQLITE_BUSY_TIMEOUT`), ce qui **amortit** la contention — mais aucun retry
explicite n'existe si le timeout est malgré tout dépassé : `sqlite3.OperationalError: database is
locked` remonterait brut.

## 2. Objectif

Rendre les écritures concurrentes robustes : un verrou temporaire ne doit jamais faire échouer une
analyse.

## 3. Non-objectifs

- Pas de passage à un serveur de base (Postgres, etc.) : outil local monoposte.
- Pas de refonte de la couche `cache.py` : on ajoute un filet ciblé sur l'écriture.
- Pas de changement du modèle de concurrence (le ThreadPoolExecutor reste).

## 4. Exigences

- 4.1 Les écritures (`cache.put`, `put_manual`, etc.) retentent avec un court back-off en cas de
  `OperationalError: database is locked`.
- 4.2 Le nombre de tentatives et le délai sont des constantes dans `config.py` (pas de nombre
  magique).
- 4.3 Un test simule un verrou temporaire et vérifie que l'écriture finit par réussir.
- 4.4 Un verrou **permanent** remonte une erreur claire (pas de boucle infinie).

## 5. Critères d'acceptation

- [x] Les écritures retentent sur `database is locked`
- [x] Les constantes de retry sont dans `config.py`
- [x] Test : verrou temporaire → succès après retry
- [x] Test : verrou permanent → erreur remontée, pas de blocage
- [x] La suite hors réseau reste verte (`pytest -m "not network" -q`)

## 6. Invariants préservés

- La calibration Pernod (`z = −3.81`, ±0.15) reste verte.
- Le comportement du cache (TTL, clés, format) est inchangé.
- Aucune donnée écrite partiellement en cas d'échec.

## 7. Jalons

- **J1** — Constantes de retry dans `config.py` + helper d'écriture.
- **J2** — Tests (verrou temporaire / permanent).

## 8. Note de reprise

**Plan :** `aidd_docs/tasks/2026_10/2026_10_24_sqlite-retry/` — `plan.md` `reviewed`, revue
approuvée au tour 2. **Implémenté :** retry au niveau de la connexion
(`execute`/`executemany`/`executescript`), constantes `SQLITE_WRITE_RETRIES` (3) et
`SQLITE_WRITE_BACKOFF_S`, trois tests (`tests/test_cache_retry.py`). **Vérifié :** 1 179 tests
hors réseau, 579 tests front, lint et types verts. **Reste :** relire la PR draft, fusionner sur
`main`, puis passer le statut de l'index à « fait ».
