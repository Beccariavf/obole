# #03 — Sauvegarde des données utilisateur

> **Statut :** **fait** · **Priorité :** 🔴 Q1 (urgent + important — cas (b) irréversible)
> **Impact Pernod :** 🟢 · **Branche (mergée) :** `feat/user-data-backup` · **Taille :** ~1-2 sessions
> **Dépend de :** #02 (versioning du schéma)

---

## 1. Contexte

**C'est le seul chantier dont le coût de l'inaction n'est pas borné : il peut être une perte
définitive.**

- `grep -nE "@app\.(get|post)" src/obole/api/app.py | grep -iE "export|backup|dump"` → **aucune
  route**. Il n'existe **aucun** export ni import des données utilisateur. (L'« Export CSV »
  existant exporte le *graphe*, pas les données.)
- Cinq tables contiennent des données **irremplaçables**, saisies à la main :
  `manual_fundamentals`, `custom_categories`, `custom_indices`, `settings`, `events`
  (`data/cache.py`, schémas `_*_SCHEMA`).
- Elles vivent dans `cache.sqlite`, qui est **gitignoré** (`.gitignore:7`), donc absent de tout
  historique de version.

Un `rm cache.sqlite`, une corruption WAL, ou un disque qui lâche détruit tout, sans filet.

## 2. Objectif

Pouvoir **sauvegarder et restaurer** en une action l'intégralité des données saisies, et pouvoir
purger le cache technique sans jamais risquer les données utilisateur.

## 3. Non-objectifs

- Pas de sauvegarde cloud ni de synchronisation : outil local.
- Pas de sauvegarde automatique planifiée (hors périmètre — on fournit le mécanisme, l'utilisateur
  déclenche).
- Pas de chiffrement de l'archive : données locales d'un outil monoposte.

## 4. Exigences

- 4.1 Une route `GET /api/backup` produit une archive unique (JSON) contenant les 5 tables
  utilisateur, avec un en-tête de version de schéma (#02).
- 4.2 Une route `POST /api/restore` restaure une archive, après validation stricte du format
  (schéma vérifié ; archive invalide → 422, aucune écriture partielle).
- 4.3 La restauration est transactionnelle : soit tout passe, soit rien.
- 4.4 Un bouton dans le front (section « Paramètres ») pour télécharger/importer l'archive.
- 4.5 La purge du cache technique (jetable) est possible **sans** toucher aux tables utilisateur.

## 5. Critères d'acceptation

- [x] `GET /api/backup` renvoie une archive JSON valide contenant les 5 tables
- [x] `POST /api/restore` restaure les données à l'identique (test aller-retour)
- [x] Une archive corrompue ou d'un schéma inconnu est **rejetée** (422) sans écriture partielle
- [x] Test : purge du cache → les 5 tables utilisateur sont intactes
- [x] Test : restauration d'une archive dans une base vide → données identiques à la source
- [x] Bouton présent dans le front et fonctionnel (vérifié à la main)

## 6. Invariants préservés

- La calibration Pernod (`z = −3.81`, ±0.15) reste verte.
- **Aucune** donnée utilisateur ne peut être perdue par une opération de sauvegarde/restauration
  (validation avant écriture, transaction).
- Le format d'archive reste lisible et documenté (JSON, pas de binaire opaque).

## 7. Jalons

- **J1** ✅ — Sérialisation des 5 tables en JSON + `GET /api/backup`.
- **J2** ✅ — Validation stricte + `POST /api/restore` (transactionnel).
- **J3** ✅ — Tests (aller-retour, archive invalide, purge isolée).
- **J4** ✅ — Boutons front (télécharger / importer).

## 8. Note de reprise

**Terminé.** Implémentation livrée sur `feat/user-data-backup`.

- **`src/obole/data/backup.py`** (nouveau) — seule couche qui touche le disque, avec `cache.py` :
  `build_archive()`, `validate_archive()`, `restore_archive()`, `restore_from_json()`,
  `purge_cache()`. La table `cache` (technique) est **exclue** de l'archive.
- **`api/app.py`** — 3 routes fines : `GET /api/backup` (JSON + `Content-Disposition` daté),
  `POST /api/restore` (multipart, champ `file`), `POST /api/cache/purge`.
- **Front** — section « Données » dans la modale Paramètres : Sauvegarder / Restaurer… /
  Vider le cache, avec messages de succès et d'erreur.

**Décisions**

- **Remplacement intégral** (DELETE puis INSERT), seule sémantique garantissant un état identique
  à la source. Ordre d'insertion parents-avant-enfants (`custom_categories` avant `custom_indices`),
  suppression en ordre inverse : `PRAGMA foreign_keys=ON` interdit de désactiver les FK dans une
  transaction, donc on respecte l'ordre.
- **`id` explicites réinsérés tels quels** : les références internes (`RATIO:A/B`, `INDEX:<id>`,
  `custom_indices.category_id`) restent valides, et `sqlite_sequence` est avancé automatiquement
  par SQLite (vérifié par test : les créations post-restauration ont des id strictement supérieurs).
- **`tickers` conservé en texte JSON brut** (pas de re-encodage) : la restauration est strictement
  fidèle, sans hypothèse de normalisation.
- **Transaction entièrement explicite** : `conn.isolation_level = None` **puis** `BEGIN`/`COMMIT`/
  `ROLLBACK`. L'atomicité ne dépend ainsi d'aucun comportement implicite du module `sqlite3`.
- **Purge des caches dérivés** dans la transaction de restauration (`_purge_derived_cache`) : séries
  de paniers (`INDEX:%`) **et** comptes (`kind='fundamentals'`, qui embarquent la table déjà fusionnée
  avec les données manuelles et portent un TTL de 7 jours). Sans cela, restaurer une sauvegarde plus
  ancienne laisserait des comptes faux une semaine. Même intention que `yahoo.refresh(ticker)` après
  une saisie manuelle. Les prix et les métadonnées `info` ne dépendent pas des données utilisateur :
  ils restent en cache.
- **`cache.connect()`** : accès brut public (contexte, ferme la connexion) pour les modules de `data/`
  ayant besoin de SQL direct — `backup.py` n'utilise plus l'API privée `cache._conn()`, comme
  `manual.py`/`events.py`/`indices.py`/`screener.py`.
- **Validation de `custom_indices.tickers`** : doit être du JSON valide (liste de chaînes). La colonne
  est consommée par `json.loads` en lecture : une chaîne non-JSON ferait planter `/api/indices` (500)
  après restauration, elle est donc refusée en 422.
- **Rejets 422** : format inconnu, `format_version`/`schema_version` plus récents, table manquante
  ou inconnue, ligne non conforme, `tickers` non-JSON, indice orphelin, contrainte SQL violée.

**Garde-fou de dérive** (`TestSchemaCoupling`) : un test compare `_TABLE_COLUMNS` à
`PRAGMA table_info` pour les 5 tables. Une future migration (#02) qui change une table sans mettre à
jour `_TABLE_COLUMNS` casse ce test au lieu de produire des sauvegardes silencieusement incomplètes.

**Preuve par mutation** (test d'atomicité) : avec `isolation_level = None` mais **sans** la
transaction explicite, les DELETE sont commités immédiatement et un échec d'insertion laisse la
base vide → le test échoue. La transaction est donc bien porteuse, le test n'est pas vide.

**Vérifications**

- `tests/test_backup.py` : structure, aller-retour, base vide, cas de rejet,
  rollback, intégrité `sqlite_sequence`, purge isolée (vidage complet), purge des caches dérivés,
  couplage schéma/`_TABLE_COLUMNS`, accès public `cache.connect()`.
- Suite complète `pytest -m "not network" -q` verte ; `-m network` vert (calibration Pernod
  intacte). `ruff check`, `ruff format --check`, `mypy` verts.
- **Revue** : nommage de la purge aligné sur son effet réel (`purge_cache()` vide tout le cache
  technique, pas seulement les prix) — libellés front/route/docstring corrigés + 1 test ; compteur
  d'échecs plafonné (`_MAX_FAILURES`) + 1 test.
- **Preuve par mutation** : (a) transaction retirée → test d'atomicité en échec ; (b) purge
  `fundamentals` retirée → test d'invalidation du cache dérivé en échec ; (c) `_validate_tickers`
  retirée → 3 tests de rejet en échec ; (d) colonne ajoutée au DDL sans MAJ `_TABLE_COLUMNS` →
  test de couplage en échec.
- `web-tests` : verts (`cd web-tests && npm test`).
- **Manuel (serveur réel, base de 1005 comptes manuels / 10 indices)** : archive téléchargée
  (`obole-backup-2026-09-17.json`), aller-retour via l'UI Playwright (sauvegarde → restauration
  avec confirmation → rechargement), compteurs et cache prix (3106 entrées) inchangés ; archive
  invalide et JSON cassé → 422 avec message explicite, base intacte.
- **Manuel (post-revue, purge du cache dérivé)** : sur une base au cache chaud
  (`fundamentals` = 602 entrées), une restauration ramène le cache de 3106 à 2504 entrées —
  exactement les 602 `fundamentals` purgées, `prices`/`info`/`identity`/`search` conservés.
  `tickers` non-JSON → 422 explicite, base et cache inchangés. `/api/indices` répond 200 après
  restauration (les comptes sont re-fetchés à la demande).

**Branches**

Le chantier a d'abord cohabité avec #01 sur une branche commune (les deux ayant été développés dans
la même session). Il a été **scindé proprement** : #03 sur `feat/user-data-backup`, #01 sur
`feat/observability`, chacune mergée séparément sur `main` (deux commits distincts, conformes à la
convention « un chantier par branche »).
