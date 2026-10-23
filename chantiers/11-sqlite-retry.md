# #11 — Retry SQLite sur `database is locked`

> **Statut :** à faire · **Priorité :** 🔵 Q3 (urgent, pas important — à expédier)
> **Impact Pernod :** 🟢 · **Branche proposée :** `fix/sqlite-retry` · **Taille :** ~½ session

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

- [ ] Les écritures retentent sur `database is locked`
- [ ] Les constantes de retry sont dans `config.py`
- [ ] Test : verrou temporaire → succès après retry
- [ ] Test : verrou permanent → erreur remontée, pas de blocage
- [ ] La suite hors réseau reste verte (`pytest -m "not network" -q`)

## 6. Invariants préservés

- La calibration Pernod (`z = −3.81`, ±0.15) reste verte.
- Le comportement du cache (TTL, clés, format) est inchangé.
- Aucune donnée écrite partiellement en cas d'échec.

## 7. Jalons

- **J1** — Constantes de retry dans `config.py` + helper d'écriture.
- **J2** — Tests (verrou temporaire / permanent).

## 8. Note de reprise

_(vide — chantier non commencé)_
