# Retry SQLite au niveau de la connexion

- Date: 2026-10-24
- Status: Accepted

## Context

Le screener écrit dans SQLite depuis un pool de threads et l'IA peut écrire en parallèle
(portefeuille, thèses). `PRAGMA busy_timeout` amortit un verrou court, mais une écriture qui
dépasse le délai remontait `OperationalError: database is locked` et faisait échouer l'analyse
(chantier #11). Il fallait un filet borné, sans changer le modèle de concurrence.

## Decision

Envelopper les méthodes d'exécution de la connexion (`execute`, `executemany`,
`executescript`) dans `_LockRetryingConnection`, avec 3 tentatives et un back-off linéaire
(`config.SQLITE_WRITE_RETRIES`, `SQLITE_WRITE_BACKOFF_S`). Seul un message contenant
« locked » est rejoué ; toute autre erreur remonte immédiatement.

## Alternatives

- **Décorer chaque fonction d'écriture** : explicite, mais une trentaine de décorateurs à ne pas
  oublier, et les migrations (`BEGIN IMMEDIATE` / `COMMIT`) resteraient hors du filet.
- **Ne retenter que le commit** : ne couvre pas une instruction bloquée à l'exécution, qui est
  le cas réel avec `busy_timeout`.
- **Augmenter `busy_timeout`** : allonge toutes les lectures et ne borne pas l'attente.

## Consequences

- Toutes les écritures présentes et futures passent par le filet, sans toucher aux fonctions.
- Le `commit` implicite du `with _conn()` n'est pas retenté : en WAL, le verrou d'écriture est
  acquis dès la première instruction, donc ce n'est pas le cas réaliste.
- Un verrou permanent échoue après ≈ 15 s au pire (3 × `busy_timeout`), jamais en boucle.
- Les migrations héritent du retry, ce qui sérialise mieux deux ouvertures concurrentes.
