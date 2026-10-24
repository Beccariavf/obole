# Review: Retry SQLite sur `database is locked`

- Rounds: 2
- Started: 2026-10-24

## Round 1 · r-7c3a

- Date: 2026-10-24
- By: Beccariavf
- Diff: `main...HEAD` plus the working tree
- Axes: code, functional, relevancy
- Verdict: changes-requested
- Score: 8/8 met, 0 unmet, 0 unverified at runtime, 0 out of the diff

### Criteria

- [x] 4.1 Les écritures retentent sur `database is locked` — `src/obole/data/cache.py:413` (`execute` surchargé)
- [x] 4.2 Les constantes de retry sont dans `config.py` — `src/obole/config.py:102`
- [x] 4.3 Test : verrou temporaire → succès après retry — `tests/test_cache_retry.py::test_verrou_temporaire_est_rejoue`
- [x] 4.4 Test : verrou permanent → erreur remontée, pas de blocage — `tests/test_cache_retry.py::test_verrou_permanent_remonte_apres_n_tentatives`
- [x] 5 La suite hors réseau reste verte — 1 179 passés, 1 ignoré (`pytest -m "not network"`)
- [x] 6 La calibration Pernod reste verte — aucun fichier de calcul touché (`git diff --name-only`)
- [x] 6 Le comportement du cache (TTL, clés, format) est inchangé — seul `execute` est enveloppé
- [x] 6 Aucune donnée écrite partiellement en cas d'échec — le test permanent vérifie `get` → `None`

### Findings

- `src/obole/data/cache.py:413` : `executemany` et `executescript` court-circuitent `_retry_locked` (aucune écriture ne les utilise aujourd'hui, mais un ajout futur passerait sous le radar) → surcharger les deux — 🟡 major, code
- `aidd_docs/tasks/2026_10/2026_10_24_sqlite-retry/plan.md:27` : « un verrou permanent échoue en moins d'une seconde » est faux — 5 tentatives × `busy_timeout` 5 s ≈ 25 s → ramener à 3 tentatives (≈ 15 s pire cas) et corriger la décision — 🟡 major, functional
- `src/obole/data/cache.py:405` : le `commit` implicite du `with _conn()` n'est pas retenté ; la limite est acceptable en WAL (le verrou d'écriture est tenu dès la première instruction) mais doit être dite → compléter la docstring — 🟢 minor, code
- `aidd_docs/memory/data.md:40` : la nouvelle garantie (retry borné) n'est pas documentée dans la mémoire projet → une ligne au §Cache — 🟢 minor, doc

## Round 2 · r-91be

- Date: 2026-10-24
- By: Beccariavf
- Diff: `main...HEAD` plus the working tree
- Axes: code, functional, relevancy
- Verdict: approved
- Score: 8/8 met, 0 unmet, 0 unverified at runtime, 0 out of the diff

### Criteria

- [x] 4.1 Les écritures retentent sur `database is locked` — `src/obole/data/cache.py::_LockRetryingConnection` (`execute`, `executemany`, `executescript`)
- [x] 4.2 Les constantes de retry sont dans `config.py` — `SQLITE_WRITE_RETRIES = 3`, `SQLITE_WRITE_BACKOFF_S = 0.05`
- [x] 4.3 Test : verrou temporaire → succès après retry — `tests/test_cache_retry.py::test_verrou_temporaire_est_rejoue`
- [x] 4.4 Test : verrou permanent → erreur remontée, pas de blocage — `tests/test_cache_retry.py::test_verrou_permanent_remonte_apres_n_tentatives`
- [x] 5 La suite hors réseau reste verte — 1 179 passés, 1 ignoré (`pytest -m "not network"`)
- [x] 6 La calibration Pernod reste verte — aucun fichier de calcul touché
- [x] 6 Le comportement du cache (TTL, clés, format) est inchangé — seul le transport SQL est enveloppé
- [x] 6 Aucune donnée écrite partiellement en cas d'échec — le test permanent vérifie `get` → `None`

Les quatre constats du tour 1 sont traités : `executemany`/`executescript` surchargés, pire cas ramené à ≈ 15 s (3 tentatives) et décision corrigée, limite du `commit` documentée, mémoire `data.md` mise à jour.
