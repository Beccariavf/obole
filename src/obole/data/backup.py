"""Sauvegarde / restauration des données utilisateur (#03).

Seule couche, avec `cache.py`, qui touche le disque. Dix tables contiennent des
données **irremplaçables** (saisies à la main ou réglées par l'utilisateur) :

    manual_fundamentals, custom_categories, custom_indices, settings, events,
    portfolio_accounts, portfolio_transactions, portfolio_dividends, theses,
    checkpoints

Elles vivent dans `cache.sqlite`, qui est gitignoré : un `rm`, une corruption WAL
ou un disque qui lâche les détruit sans filet. Ce module fournit l'export (JSON
lisible, versionné) et la restauration (transactionnelle).

La table `cache` (prix, comptes, séries calculées) est **volontairement exclue**
de l'archive : c'est du jetable, re-fetchable depuis yfinance.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from obole import config
from obole.data import cache
from obole.observability import get_logger

logger = get_logger(__name__)

# Nom et version de la STRUCTURE du fichier JSON (distincts de la version du
# SCHÉMA de la base, qui suit `config.SCHEMA_VERSION`). Incrémenter
# `FORMAT_VERSION` uniquement si l'enveloppe JSON change de forme.
FORMAT_NAME = "obole-backup"
FORMAT_VERSION = 1

# Colonnes des tables utilisateur, dans l'ordre d'INSERTION (les tables
# référencées par une clé étrangère viennent après leur parent : `custom_indices`
# référence `custom_categories`). La suppression se fait en ordre inverse.
# Types attendus par colonne ; `type(None)` = colonne nullable (schéma SQLite).
_TABLE_COLUMNS: dict[str, dict[str, tuple[type, ...]]] = {
    "manual_fundamentals": {
        "ticker": (str,),
        "year": (int,),
        "metric": (str,),
        "value": (int, float),
        "added_at": (int, float),
    },
    "custom_categories": {
        "id": (int,),
        "name": (str,),
        "created_at": (int, float),
    },
    "custom_indices": {
        "id": (int,),
        "category_id": (int,),
        "name": (str,),
        "tickers": (str,),  # JSON encodé (liste de tickers), conservé tel quel
        "created_at": (int, float),
    },
    "settings": {
        "key": (str,),
        "value": (str,),
        "updated_at": (int, float, type(None)),
    },
    "events": {
        "id": (int,),
        "ref": (str,),
        "event_date": (str,),
        "label": (str,),
        "description": (str, type(None)),
        "created_at": (int, float),
    },
    # Portefeuille (#17) : comptes AVANT leurs enfants (transactions, dividendes).
    "portfolio_accounts": {
        "id": (int,),
        "name": (str,),
        "currency": (str,),
        "created_at": (int, float),
    },
    "portfolio_transactions": {
        "id": (int,),
        "account_id": (int,),
        "ticker": (str,),
        "side": (str,),
        "trade_date": (str,),
        "quantity": (int, float),
        "price": (int, float),
        "fees": (int, float),
        "currency": (str,),
        "note": (str, type(None)),
        "tag": (str, type(None)),
        "created_at": (int, float),
    },
    "portfolio_dividends": {
        "id": (int,),
        "account_id": (int,),
        "ticker": (str,),
        "pay_date": (str,),
        "amount": (int, float),
        "status": (str,),
        "source": (str,),
        "created_at": (int, float),
    },
    # Thèses d'entreprise (#09.3) : une par ticker.
    "theses": {
        "id": (int,),
        "ticker": (str,),
        "content": (str,),  # JSON encodé, conservé tel quel
        "created_at": (int, float),
        "updated_at": (int, float),
    },
    # Points de contrôle suivis (#21) : liste possédée par l'utilisateur, une par
    # ligne, indépendante du document markdown de la thèse.
    "checkpoints": {
        "id": (int,),
        "ref": (str,),
        "label": (str,),
        "done": (int,),
        "created_at": (int, float),
    },
    # Brouillons d'import (#23) : staging d'un import proposé par une IA ou un
    # collage, en attente de validation humaine. `payload` = JSON encodé, conservé
    # tel quel. Sauvegardé (une validation humaine peut être différée).
    "import_drafts": {
        "id": (int,),
        "target": (str,),
        "ref": (str,),
        "payload": (str,),
        "status": (str,),
        "created_at": (int, float),
        "applied_at": (int, float, type(None)),
    },
}

_TABLE_NAMES = tuple(_TABLE_COLUMNS)

# Tables introduites par une version de SCHÉMA : `_TABLE_SINCE[version]` liste les
# tables ajoutées à cette version. Sert à la restauration d'archives plus
# anciennes : une table absente d'une archive d'un schéma antérieur est tolérée
# (traitée comme vide), au lieu d'être rejetée « Archive incomplète ».
_TABLE_SINCE: dict[int, tuple[str, ...]] = {
    1: (
        "manual_fundamentals",
        "custom_categories",
        "custom_indices",
        "settings",
        "events",
    ),
    2: ("portfolio_accounts", "portfolio_transactions", "portfolio_dividends"),
    4: ("theses",),
    5: ("checkpoints",),
    6: ("import_drafts",),
}

# Colonnes introduites APRÈS la création de leur table (hors baseline) :
# `(table, colonne) -> version`. Une archive d'un schéma ANTÉRIEUR ne porte pas
# la colonne : la restauration la tolère (remplie par None — la colonne est
# nullable), au lieu de rejeter « colonne manquante ». Sans cela, restaurer une
# sauvegarde faite avant l'ajout casserait (#03 : la sauvegarde protège les
# données utilisateur, elle ne doit pas devenir inexploitable).
_COLUMN_SINCE: dict[tuple[str, str], int] = {
    ("portfolio_transactions", "tag"): 7,  # #17.6
}


def _check_table_registry() -> None:
    """Garde-fou de cohérence : toute table de `_TABLE_COLUMNS` doit être déclarée
    dans `_TABLE_SINCE`.

    Sinon `validate_archive` ne l'exigerait jamais pour l'archive à la version
    courante : une sauvegarde dépourvue de cette table serait acceptée et la
    restauration la **viderait silencieusement**. On échoue au chargement du
    module plutôt qu'à la restauration (défaut de dérive attrapé en CI).
    """
    declared = {name for names in _TABLE_SINCE.values() for name in names}
    missing = set(_TABLE_COLUMNS) - declared
    if missing:
        raise RuntimeError(
            f"Tables absentes de _TABLE_SINCE (backup.py) : {sorted(missing)} — "
            "déclarez-les pour la version de schéma qui les introduit"
        )
    for table, column in _COLUMN_SINCE:
        if table not in _TABLE_COLUMNS or column not in _TABLE_COLUMNS[table]:
            raise RuntimeError(
                f"Colonne déclarée dans _COLUMN_SINCE (backup.py) introuvable : {table}.{column}"
            )


_check_table_registry()


def _tables_for(schema_version: int) -> tuple[str, ...]:
    """Tables attendues pour une archive de `schema_version` donnée.

    Une archive v1 ne contient que les 5 tables historiques : les tables
    portefeuille (v2) n'existent pas encore et ne doivent pas être exigées.
    """
    return tuple(
        name
        for version, names in _TABLE_SINCE.items()
        if version <= schema_version
        for name in names
    )


def _value_ok(value: object, types: tuple[type, ...]) -> bool:
    """Type d'une cellule. `bool` est exclu : sous-classe de `int` mais jamais
    une valeur légitime de nos colonnes numériques."""
    if value is None:
        return type(None) in types
    if isinstance(value, bool):
        return False
    return isinstance(value, types)


def build_archive() -> dict:
    """Archive complète des tables utilisateur (structure + données).

    Les `tickers` des indices sont conservés **tels quels** (texte JSON) : la
    restauration est ainsi strictement fidèle, sans hypothèse de re-encodage.
    """
    with cache.connect() as conn:
        tables: dict[str, list[dict]] = {}
        for name, columns in _TABLE_COLUMNS.items():
            cols = ", ".join(columns)
            rows = conn.execute(f"SELECT {cols} FROM {name}").fetchall()
            tables[name] = [dict(zip(columns, row, strict=True)) for row in rows]
    return {
        "format": FORMAT_NAME,
        "format_version": FORMAT_VERSION,
        "schema_version": config.SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "tables": tables,
    }


def validate_archive(data: object) -> dict[str, list[dict]]:
    """Valide une archive et renvoie ses `tables`. Lève `ValueError` si invalide.

    Contrôles : enveloppe (format + versions), présence des tables attendues pour
    la version de schéma de l'archive (une table introduite par un schéma plus
    récent n'est pas exigée — restauration d'une sauvegarde antérieure), chaque
    ligne conforme aux colonnes (ni manquante, ni inconnue, bon type) et intégrité
    référentielle (`custom_indices.category_id` et `account_id` doivent exister).

    Ne fait AUCUNE écriture : l'appelant peut donc valider avant de restaurer.
    """
    if not isinstance(data, dict):
        raise ValueError("Archive invalide : objet JSON attendu")

    if data.get("format") != FORMAT_NAME:
        raise ValueError(f"Archive invalide : format attendu « {FORMAT_NAME} »")

    fmt_version = data.get("format_version")
    if not isinstance(fmt_version, int) or isinstance(fmt_version, bool) or fmt_version < 1:
        raise ValueError("Archive invalide : format_version manquant ou invalide")
    if fmt_version > FORMAT_VERSION:
        raise ValueError(
            f"Archive d'un format plus récent (v{fmt_version} > v{FORMAT_VERSION}) : "
            "mettez à jour Obole"
        )

    schema_version = data.get("schema_version")
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version < 1
    ):
        raise ValueError("Archive invalide : schema_version manquant ou invalide")
    if schema_version > config.SCHEMA_VERSION:
        raise ValueError(
            f"Archive d'un schéma plus récent (v{schema_version} > "
            f"v{config.SCHEMA_VERSION}) : mettez à jour Obole"
        )

    tables = data.get("tables")
    if not isinstance(tables, dict):
        raise ValueError("Archive invalide : « tables » doit être un objet")

    # Tables attendues pour la version de schéma de l'archive : une table
    # introduite par un schéma PLUS RÉCENT que l'archive n'a pas à y figurer
    # (restauration d'une sauvegarde antérieure — compatibilité ascendante).
    expected = _tables_for(schema_version)
    missing = [name for name in expected if name not in tables]
    if missing:
        raise ValueError(f"Archive incomplète : table(s) manquante(s) {missing}")
    unknown = [name for name in tables if name not in _TABLE_COLUMNS]
    if unknown:
        raise ValueError(f"Archive invalide : table(s) inconnue(s) {unknown}")

    # Normalise en ajoutant les tables absentes (vides) : la restauration
    # remplacera alors leur contenu par du vide, comportement attendu d'une
    # archive qui ne les connaissait pas.
    for name in _TABLE_NAMES:
        tables.setdefault(name, [])

    # Colonnes ajoutées après coup : une archive ANTÉRIEURE à leur introduction
    # ne les porte pas — on les remplit (None, colonne nullable) avant validation.
    for (table, column), version in _COLUMN_SINCE.items():
        if version <= schema_version:
            continue
        for row in tables[table]:
            if isinstance(row, dict) and column not in row:
                row[column] = None

    for name in _TABLE_NAMES:
        _validate_table(name, tables[name])

    _validate_tickers(tables["custom_indices"])
    _validate_references(tables)
    return tables


def _validate_table(name: str, rows: object) -> None:
    columns = _TABLE_COLUMNS[name]
    if not isinstance(rows, list):
        raise ValueError(f"Table {name} : une liste de lignes est attendue")
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"Table {name}, ligne {index} : objet attendu")
        extra = [c for c in row if c not in columns]
        if extra:
            raise ValueError(f"Table {name}, ligne {index} : colonne(s) inconnue(s) {extra}")
        for column, types in columns.items():
            if column not in row:
                raise ValueError(f"Table {name}, ligne {index} : colonne « {column} » manquante")
            if not _value_ok(row[column], types):
                raise ValueError(f"Table {name}, ligne {index} : valeur invalide pour « {column} »")


def _validate_tickers(rows: list[dict]) -> None:
    """`custom_indices.tickers` doit être un JSON valide — une liste de tickers.

    La colonne est stockée en texte, mais consommée par `json.loads` côté lecture
    (`cache.list_indices_by_category`, `get_index_definition`). Une chaîne non-JSON
    passerait la validation structurelle puis ferait planter `/api/indices` (500)
    au prochain affichage : on la refuse ici, comme les autres incohérences.
    """
    for index, row in enumerate(rows):
        try:
            parsed = json.loads(row["tickers"])
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Table custom_indices, ligne {index} : « tickers » n'est pas du JSON valide"
            ) from exc
        if not isinstance(parsed, list) or not all(isinstance(t, str) for t in parsed):
            raise ValueError(
                f"Table custom_indices, ligne {index} : « tickers » doit être une liste de tickers"
            )


def _validate_references(tables: dict) -> None:
    """Intégrité référentielle : pas d'indice orphelin, pas de ligne de portefeuille
    rattachée à un compte inexistant."""
    category_ids = {row["id"] for row in tables["custom_categories"]}
    for index, row in enumerate(tables["custom_indices"]):
        if row["category_id"] not in category_ids:
            raise ValueError(
                f"Table custom_indices, ligne {index} : catégorie {row['category_id']} inexistante"
            )
    account_ids = {row["id"] for row in tables["portfolio_accounts"]}
    for name in ("portfolio_transactions", "portfolio_dividends"):
        for index, row in enumerate(tables[name]):
            if row["account_id"] not in account_ids:
                raise ValueError(
                    f"Table {name}, ligne {index} : compte {row['account_id']} inexistant"
                )


def restore_archive(tables: dict[str, list[dict]]) -> None:
    """Remplace intégralement les tables utilisateur par le contenu de l'archive.

    Sémantique de **remplacement intégral** : c'est la seule qui garantisse un
    état identique à la source. Tout se joue dans une transaction explicite —
    le module `sqlite3` n'en ouvre pas autour du DDL, et l'on ne veut surtout pas
    qu'une suppression commitée survive à un échec d'insertion.

    Les `id` explicites sont réinsérés tels quels : les références internes
    (`RATIO:A/B`, `INDEX:<id>`, `custom_indices.category_id`) restent valides, et
    `sqlite_sequence` est avancé automatiquement par SQLite (AUTOINCREMENT).
    """
    # Transaction entièrement explicite : on neutralise la gestion implicite du
    # module (qui, sinon, ouvrirait sa propre transaction au premier DML et la
    # refermerait à la fermeture). L'atomicité ne doit dépendre d'aucun
    # comportement implicite de `sqlite3`.
    with cache.connect() as conn:
        conn.isolation_level = None
        conn.execute("BEGIN")
        try:
            for name in reversed(_TABLE_NAMES):  # enfants avant parents
                conn.execute(f"DELETE FROM {name}")
            for name, columns in _TABLE_COLUMNS.items():  # parents avant enfants
                rows = tables[name]
                if not rows:
                    continue
                cols = ", ".join(columns)
                placeholders = ", ".join("?" * len(columns))
                conn.executemany(
                    f"INSERT INTO {name} ({cols}) VALUES ({placeholders})",
                    [tuple(row[c] for c in columns) for row in rows],
                )
            _purge_derived_cache(conn)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise


def _purge_derived_cache(conn: sqlite3.Connection) -> None:
    """Purge, dans la transaction, les caches DÉRIVÉS des données utilisateur.

    Sans cela, une restauration laisse des caches périmés cohérents avec
    l'ancien état :

    - les séries de paniers (`INDEX:%`) dérivent des définitions d'indices ;
    - les comptes (`kind='fundamentals'`) embarquent la table **déjà fusionnée**
      avec les données manuelles (cf. `yahoo.fetch_fundamentals`), et portent un
      TTL de 7 jours : restaurer une sauvegarde plus ancienne laisserait des
      comptes faux pendant une semaine ;
    - le marqueur négatif `kind='fundamentals_missing'` (6 h) masque les comptes
      d'un titre : s'il n'en avait pas dans l'ancien état mais en a dans la
      sauvegarde restaurée, il resterait affiché sans comptes.

    C'est la même intention que `yahoo.refresh(ticker)` après une saisie manuelle
    ou un import CSV. Les prix et les métadonnées (`info`) ne dépendent pas des
    données utilisateur : ils restent en cache.
    """
    conn.execute(
        "DELETE FROM cache WHERE ticker LIKE 'INDEX:%' "
        "OR kind = 'fundamentals' OR kind = 'fundamentals_missing'"
    )


def restore_from_json(raw: bytes) -> dict[str, int]:
    """Décode, valide et applique une archive. Renvoie le nombre de lignes par table.

    Lève `ValueError` (archive illisible, invalide ou inapplicable) — l'API la
    traduit en 422. Aucune écriture n'a lieu si la validation échoue.
    """
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Archive illisible : {exc}") from exc
    tables = validate_archive(data)
    try:
        restore_archive(tables)
    except sqlite3.Error as exc:
        raise ValueError(f"Restauration impossible : {exc}") from exc
    return {name: len(rows) for name, rows in tables.items()}


def purge_cache() -> int:
    """Vide **tout** le cache technique et renvoie le nombre d'entrées supprimées.

    Prix, comptes, métadonnées, résultats de recherche, univers : tout est
    re-fetchable depuis yfinance, donc jetable. C'est le geste sûr pour forcer un
    rechargement complet — il n'affecte **aucune** des tables utilisateur.
    """
    with cache.connect() as conn:
        removed = conn.execute("DELETE FROM cache").rowcount
        conn.commit()
        return int(removed)


def snapshot_path() -> Path:
    """Chemin de la copie de sécurité (à côté de la base courante).

    `config.CACHE_DB` peut être une `Path` (cas normal) ou une chaîne (tests qui
    la redirigent) : on normalise avant de dériver le nom.
    """
    return Path(config.CACHE_DB).with_suffix(".sqlite.bak")


def snapshot_before_write() -> bool:
    """Copie la base à côté d'elle-même avant une écriture pilotée par l'IA.

    Renvoie `True` si la copie a été écrite, `False` en cas d'échec. **Ne lève
    jamais** : un snapshot raté (disque plein, droits, base absente) ne doit pas
    rendre le serveur MCP inutilisable — mais il est journalisé pour l'audit.

    La copie passe par l'API de sauvegarde SQLite (`backup`), qui gère une base
    en cours d'écriture (mode WAL) sans la corrompre.
    """
    source = Path(config.CACHE_DB)
    if not source.exists():
        return False
    target = snapshot_path()
    try:
        with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
            src.backup(dst)
        return True
    except (sqlite3.Error, OSError) as exc:
        logger.warning(
            "snapshot avant écriture MCP impossible (type=%s) : écriture poursuivie",
            type(exc).__name__,
        )
        return False
