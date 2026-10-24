# #02 — Versioning du schéma SQLite

> **Statut :** **fait** · **Priorité :** 🟡 Q2 (importante, non urgente — cas (c) évolutivité)
> **Impact Pernod :** 🟢 · **Branche (historique) :** `feat/schema-versioning` · **Taille :** ~½ session
> **Prérequis de :** #03 (sauvegarde)

---

## 1. Contexte

`data/cache.py` crée ses tables avec `CREATE TABLE IF NOT EXISTS` (schémas `_*_SCHEMA`)
et active WAL (`PRAGMA journal_mode=WAL`) — mais **aucun `PRAGMA user_version`**, aucune
migration, aucun `ALTER TABLE`.

Conséquence : le jour où une colonne est ajoutée à `events`, `settings` ou `custom_indices`, la
base **existante** de l'utilisateur ne sera pas mise à jour. Le code plantera sur un champ absent —
et **uniquement chez lui**, puisque la CI et les tests partent d'une base neuve.

## 2. Objectif

Pouvoir faire évoluer le schéma en toute confiance : une base ancienne se met à niveau
automatiquement, et l'état du schéma est lisible en une requête.

## 3. Non-objectifs

- Pas d'ORM, pas d'Alembic : on reste en SQL brut (sobriété assumée du projet).
- Pas de rétro-compatibilité descendante (downgrade) : seul l'upgrade est nécessaire.
- Pas de refonte des requêtes existantes.

## 4. Exigences

- 4.1 `PRAGMA user_version` porte le numéro de version du schéma, lu à l'ouverture.
- 4.2 Une table de migrations ordonnées (liste de fonctions `v1→v2`, `v2→v3`…) appliquée à la
  première ouverture de la base, de façon idempotente.
- 4.3 Un test qui crée une base « ancienne version » et vérifie qu'elle est migrée correctement.
- 4.4 La migration est atomique : en cas d'échec, la base n'est pas laissée à moitié migrée.

## 5. Critères d'acceptation

- [x] `PRAGMA user_version` est défini et lu
- [x] Une base à `user_version = N` est migrée vers `N+1` à la première ouverture, sans perte de données
- [x] Relancer sur une base déjà à jour ne fait rien (idempotent)
- [x] Test dédié : base ancienne → migrée ; données préservées
- [x] Test dédié : échec de migration → base inchangée

## 6. Invariants préservés

- La calibration Pernod (`z = −3.81`, ±0.15) reste verte.
- Les données utilisateur existantes (saisie manuelle, indices, événements, réglages) sont
  **intégralement préservées** par toute migration.
- Aucune modification du comportement de lecture/écriture courant du cache.

## 7. Jalons

- **J1** ✅ — `PRAGMA user_version` + lecture/écriture (`_read_user_version` / `_write_user_version`).
- **J2** ✅ — Mécanisme de migration ordonnée (`MIGRATIONS` + `_migrate`, idempotent, atomique).
- **J3** ✅ — Tests (upgrade nominal, idempotence, échec/rollback, migration future simulée).

## 8. Note de reprise

**Terminé.** Implémentation livrée sur `feat/schema-versioning`.

- `config.SCHEMA_VERSION = 1` : source unique de la version cible.
- `data/cache.py` : `_read_user_version` / `_write_user_version` (autour de `PRAGMA user_version`),
  `MIGRATIONS: dict[int, Callable]` (clé = version source → passage `n → n+1`), `_migrate(conn)`
  appelé par `_conn()`.
- **Baseline 0 → 1** = création du schéma actuel (les 6 `CREATE TABLE IF NOT EXISTS` + index
  `idx_events_ref`). Les `IF NOT EXISTS` rendent la migration sûre sur une base existante : une
  base non versionnée (celle d'avant #02) converge vers v1 sans perdre ses données.
- **Atomicité** : transaction explicite `BEGIN` / `COMMIT` / `ROLLBACK`. Point clé — le module
  `sqlite3` n'ouvre **pas** de transaction implicite autour du DDL, il faut donc un `BEGIN` manuel,
  sinon un échec laisse la base à moitié migrée. Vérifié par mutation : sans `BEGIN`, le test de
  rollback échoue (la colonne ajoutée fuit).
- **Idempotence** : `_migrate` sort immédiatement si `user_version >= SCHEMA_VERSION`.
- **Tests** : `tests/test_schema_migration.py` (base temporaire isolée). La suite complète
  (`pytest -m "not network" -q`) reste verte. `ruff check` / `ruff format --check` /
  `mypy` verts.
- **Vérif manuelle** : boot de `run.py` sur le `cache.sqlite` réel (156 Mo, 1005 lignes manuelles) →
  HTTP 200 ; copie de la base forcée à `user_version = 0` → migrée à 1 avec les 5 tables intactes.

**Pour ajouter une évolution de schéma** : incrémenter `config.SCHEMA_VERSION` et ajouter une
entrée dans `MIGRATIONS` (clé = version source). Aucun autre point à toucher.

**Suivant** : #03 (sauvegarde des données utilisateur) consomme ce `user_version` comme
`schema_version` de l'archive.
