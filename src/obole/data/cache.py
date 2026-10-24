"""Cache disque SQLite. Seul ce module + yahoo.py touchent le disque/réseau.

Stocke des blobs picklés par (ticker, kind) avec un timestamp pour le TTL.
Un seul fichier SQLite, pas d'ORM (YAGNI). Sobriété : on évite les re-fetch.
"""

from __future__ import annotations

import json
import pickle
import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TypeVar

from obole import config
from obole.observability import get_logger, safe_label

logger = get_logger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    ticker TEXT NOT NULL,
    kind   TEXT NOT NULL,
    payload BLOB NOT NULL,
    fetched_at REAL NOT NULL,
    PRIMARY KEY (ticker, kind)
)
"""
_MANUAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS manual_fundamentals (
    ticker TEXT NOT NULL,
    year   INTEGER NOT NULL,
    metric TEXT NOT NULL,
    value  REAL NOT NULL,
    added_at REAL NOT NULL,
    PRIMARY KEY (ticker, year, metric)
)
"""
_CATEGORIES_SCHEMA = """
CREATE TABLE IF NOT EXISTS custom_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at REAL NOT NULL
)
"""
_INDICES_SCHEMA = """
CREATE TABLE IF NOT EXISTS custom_indices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL REFERENCES custom_categories(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    tickers TEXT NOT NULL,
    created_at REAL NOT NULL
)
"""
_SETTINGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL
)
"""
_EVENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ref TEXT NOT NULL,
    event_date TEXT NOT NULL,
    label TEXT NOT NULL,
    description TEXT,
    created_at REAL NOT NULL
)
"""
_CREATE_EVENTS_INDEX = "CREATE INDEX IF NOT EXISTS idx_events_ref ON events (ref, event_date)"

# --- Portefeuille (#17) ------------------------------------------------------
# Transactions = source de vérité ; les positions sont recalculées, jamais
# saisies. Mono-devise EUR assumée (`currency` conservée pour un jalon futur).
_PORTFOLIO_ACCOUNTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS portfolio_accounts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    currency   TEXT NOT NULL DEFAULT 'EUR',
    created_at REAL NOT NULL
)
"""
_PORTFOLIO_TRANSACTIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS portfolio_transactions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES portfolio_accounts(id) ON DELETE CASCADE,
    ticker     TEXT NOT NULL,
    side       TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    quantity   REAL NOT NULL,
    price      REAL NOT NULL,
    fees       REAL NOT NULL DEFAULT 0,
    currency   TEXT NOT NULL DEFAULT 'EUR',
    note       TEXT,
    created_at REAL NOT NULL
)
"""
_PORTFOLIO_DIVIDENDS_SCHEMA = """
CREATE TABLE IF NOT EXISTS portfolio_dividends (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES portfolio_accounts(id) ON DELETE CASCADE,
    ticker     TEXT NOT NULL,
    pay_date   TEXT NOT NULL,
    amount     REAL NOT NULL,
    status     TEXT NOT NULL DEFAULT 'confirmed',
    source     TEXT NOT NULL DEFAULT 'manual',
    created_at REAL NOT NULL
)
"""
_CREATE_PORTFOLIO_TX_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_portfolio_tx_account ON portfolio_transactions (account_id)"
)
_CREATE_PORTFOLIO_TX_TICKER_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_portfolio_tx_ticker "
    "ON portfolio_transactions (account_id, ticker)"
)
_CREATE_PORTFOLIO_DIV_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_portfolio_div_account ON portfolio_dividends (account_id)"
)
_CREATE_PORTFOLIO_DIV_TICKER_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_portfolio_div_ticker "
    "ON portfolio_dividends (account_id, ticker)"
)

# --- Étiquettes / portefeuilles virtuels (#17.6) -----------------------------
# Une transaction porte AU PLUS une étiquette (`tag`, nullable) : un portefeuille
# virtuel = l'ensemble des transactions étiquetées. Aucune table de référence :
# la liste des étiquettes est le DISTINCT des `tag` non nuls. Colonne ajoutée par
# `ALTER TABLE` (migration 6 -> 7) : nullable, donc sans effet sur les lignes
# existantes. Index partiel (WHERE tag IS NOT NULL) : n'indexe que ce qui compte.
_PORTFOLIO_TX_TAG_COLUMN = "ALTER TABLE portfolio_transactions ADD COLUMN tag TEXT"
_CREATE_PORTFOLIO_TX_TAG_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_portfolio_tx_tag "
    "ON portfolio_transactions (tag) WHERE tag IS NOT NULL"
)

# --- Paramètres de valorisation par titre (#20) ------------------------------
# La calculatrice de prix juste persiste ses paramètres (et le prix juste
# enregistré) PAR TICKER : « Enregistrer » fixe le prix juste de la fiche,
# « Réinitialiser » l'efface. Un seul enregistrement par titre (PK), payload
# JSON opaque (les clés sont validées côté service, pas ici).
_VALUATION_SETTINGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS valuation_settings (
    ticker     TEXT PRIMARY KEY,
    payload    TEXT NOT NULL,
    updated_at REAL NOT NULL
)
"""


# --- Thèses d'entreprise (#09.3) --------------------------------------------
# Une thèse par ticker (contrainte UNIQUE) : `content` est un JSON opaque
# (structure validée côté service, pas ici), édité par `save` (upsert).
_THESES_SCHEMA = """
CREATE TABLE IF NOT EXISTS theses (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker     TEXT NOT NULL UNIQUE,
    content    TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
)
"""

# --- Points de contrôle suivis (#21, bande « Suivi ») -----------------------
# Liste POSSÉDÉE par l'utilisateur, rattachée à un ticker et INDÉPENDANTE du
# document markdown de la thèse (les deux ne portent pas forcément les mêmes
# éléments). Pattern des `events` : lignes simples, une par point, `done` en
# entier 0/1 (SQLite n'a pas de booléen natif).
_CHECKPOINTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS checkpoints (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ref        TEXT NOT NULL,
    label      TEXT NOT NULL,
    done       INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
)
"""
_CREATE_CHECKPOINTS_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_checkpoints_ref ON checkpoints (ref, created_at)"
)

# --- Brouillons d'import (#23) ----------------------------------------------
# Un import (venu d'une IA via le MCP, ou d'un collage dans l'UI) est d'abord
# **staged** : proposé, jamais appliqué — l'application est un acte humain
# (routes REST, jamais un outil MCP). `payload` est un JSON opaque (structure
# validée côté service). `status` : pending | applied | rejected.
_IMPORT_DRAFTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS import_drafts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    target     TEXT NOT NULL,
    ref        TEXT NOT NULL,
    payload    TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'pending',
    created_at REAL NOT NULL,
    applied_at REAL
)
"""
_CREATE_IMPORT_DRAFTS_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_import_drafts_status " "ON import_drafts (status, created_at)"
)


# --- Versioning du schéma (#02) ---------------------------------------------
# `PRAGMA user_version` porte le numéro de version réellement appliqué à la base.
# Une base neuve est à 0 et reçoit la migration 0 -> 1 (le schéma ci-dessus) ;
# une base existante non versionnée (créée avant #02) est elle aussi à 0 et
# converge vers la même version sans perdre ses données, car les
# `CREATE TABLE IF NOT EXISTS` sont sans effet là où les tables existent.


def _read_user_version(conn: sqlite3.Connection) -> int:
    """Version de schéma courante de la base (0 si jamais versionnée)."""
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def _write_user_version(conn: sqlite3.Connection, version: int) -> None:
    """Écrit `PRAGMA user_version` (pas de paramètre lié possible : int validé)."""
    conn.execute(f"PRAGMA user_version={int(version)}")


def _migrate_0_to_1(conn: sqlite3.Connection) -> None:
    """Baseline : crée le schéma initial (toutes les tables + index).

    Idempotent par construction (`IF NOT EXISTS`) : sert aussi bien une base
    neuve qu'une base existante non versionnée, sans toucher aux données.
    """
    conn.execute(_SCHEMA)
    conn.execute(_MANUAL_SCHEMA)
    conn.execute(_CATEGORIES_SCHEMA)
    conn.execute(_INDICES_SCHEMA)
    conn.execute(_SETTINGS_SCHEMA)
    conn.execute(_EVENTS_SCHEMA)
    conn.execute(_CREATE_EVENTS_INDEX)


def _migrate_1_to_2(conn: sqlite3.Connection) -> None:
    """#17 : ajoute les tables du portefeuille (comptes, transactions, dividendes).

    Idempotent (`CREATE TABLE/INDEX IF NOT EXISTS`) : une base neuve passe par la
    baseline 0 -> 1 puis cette migration, une base v1 existante ne reçoit que les
    nouvelles tables — ses données sont préservées. Aucune modification des tables
    existantes.
    """
    conn.execute(_PORTFOLIO_ACCOUNTS_SCHEMA)
    conn.execute(_PORTFOLIO_TRANSACTIONS_SCHEMA)
    conn.execute(_PORTFOLIO_DIVIDENDS_SCHEMA)
    conn.execute(_CREATE_PORTFOLIO_TX_INDEX)
    conn.execute(_CREATE_PORTFOLIO_TX_TICKER_INDEX)
    conn.execute(_CREATE_PORTFOLIO_DIV_INDEX)
    conn.execute(_CREATE_PORTFOLIO_DIV_TICKER_INDEX)


def _migrate_2_to_3(conn: sqlite3.Connection) -> None:
    """#20 : ajoute la table des paramètres de valorisation par titre.

    Idempotent (`CREATE TABLE IF NOT EXISTS`) : une base neuve passe par les
    migrations successives, une base v2 existante ne reçoit que la nouvelle
    table — ses données sont préservées.
    """
    conn.execute(_VALUATION_SETTINGS_SCHEMA)


def _migrate_3_to_4(conn: sqlite3.Connection) -> None:
    """#09.3 : ajoute la table des thèses d'entreprise (MCP).

    Idempotent (`CREATE TABLE IF NOT EXISTS`) : une base neuve passe par les
    migrations successives, une base v3 existante ne reçoit que la nouvelle
    table — ses données sont préservées.
    """
    conn.execute(_THESES_SCHEMA)


def _migrate_4_to_5(conn: sqlite3.Connection) -> None:
    """#21 : ajoute la table des points de contrôle suivis (bande « Suivi »).

    Idempotent (`CREATE TABLE/INDEX IF NOT EXISTS`) : une base neuve passe par les
    migrations successives, une base v4 existante ne reçoit que la nouvelle
    table — ses données sont préservées.
    """
    conn.execute(_CHECKPOINTS_SCHEMA)
    conn.execute(_CREATE_CHECKPOINTS_INDEX)


def _migrate_5_to_6(conn: sqlite3.Connection) -> None:
    """#23 : ajoute la table des brouillons d'import (staging IA/humain).

    Idempotent (`CREATE TABLE/INDEX IF NOT EXISTS`) : une base neuve passe par les
    migrations successives, une base v5 existante ne reçoit que la nouvelle
    table — ses données sont préservées. Aucune écriture métier : un brouillon
    n'est appliqué que par un acte explicite de l'utilisateur (route REST).
    """
    conn.execute(_IMPORT_DRAFTS_SCHEMA)
    conn.execute(_CREATE_IMPORT_DRAFTS_INDEX)


def _migrate_6_to_7(conn: sqlite3.Connection) -> None:
    """#17.6 : ajoute l'étiquette (`tag`) aux transactions du portefeuille.

    `ALTER TABLE ... ADD COLUMN tag TEXT` (nullable) : les lignes existantes
    restent valides (tag NULL = « sans étiquette »). Index partiel sur les `tag`
    non nuls.

    **Idempotente et sûre en concurrence.** `ALTER TABLE` n'accepte pas
    `IF NOT EXISTS` : deux connexions peuvent lire la même version de schéma et
    tenter l'ajout en parallèle (la première migration n'étant pas encore
    commitée) — la seconde échouerait sur « duplicate column name ». On vérifie
    donc la présence de la colonne (PRAGMA) ET on tolère l'erreur de doublon
    (fenêtre entre la lecture et l'écriture), comme le font les autres migrations
    via `IF NOT EXISTS`. L'index est, lui, créé en `IF NOT EXISTS`.
    """
    columns = {row[1] for row in conn.execute("PRAGMA table_info(portfolio_transactions)")}
    if "tag" not in columns:
        try:
            conn.execute(_PORTFOLIO_TX_TAG_COLUMN)
        except sqlite3.OperationalError as exc:  # course : un autre thread l'a ajoutée
            if "duplicate column" not in str(exc).lower():
                raise
    conn.execute(_CREATE_PORTFOLIO_TX_TAG_INDEX)


# Migrations ordonnées : clé = version source, valeur = passage n -> n+1.
# Ajouter une évolution de schéma = une entrée ici + incrémenter
# `config.SCHEMA_VERSION`. Aucune rétro-compatibilité descendante (YAGNI).
MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {
    0: _migrate_0_to_1,
    1: _migrate_1_to_2,
    2: _migrate_2_to_3,
    3: _migrate_3_to_4,
    4: _migrate_4_to_5,
    5: _migrate_5_to_6,
    6: _migrate_6_to_7,
}


def _migrate(conn: sqlite3.Connection) -> None:
    """Amène le schéma à `config.SCHEMA_VERSION`, de façon atomique et idempotente.

    Une base déjà à jour ne déclenche rien. Les migrations sont appliquées
    séquentiellement. Le DDL de SQLite étant transactionnel, on ouvre une
    transaction explicite — le module sqlite3 n'en ouvre pas implicitement autour
    du DDL — afin qu'un échec en cours de route laisse la base strictement dans
    son état d'origine (aucune migration à moitié faite).

    La transaction est **`BEGIN IMMEDIATE`** (verrou d'écriture pris d'emblée) :
    deux connexions qui ouvrent une base en retard de version sont ainsi
    **sérialisées** (le `busy_timeout` fait patienter l'une derrière l'autre, au
    lieu de les faire migrer en parallèle). La version est **relue après
    l'acquisition du verrou** : la seconde découvre alors le schéma déjà à jour et
    ne rejoue pas les migrations (idempotence vraie sous concurrence).
    """
    current = _read_user_version(conn)
    if current >= config.SCHEMA_VERSION:
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        # Relecture APRÈS le verrou : une autre connexion a pu migrer entre-temps.
        current = _read_user_version(conn)
        for version in range(current, config.SCHEMA_VERSION):
            migration = MIGRATIONS.get(version)
            if migration is None:
                raise RuntimeError(f"Migration manquante : schéma v{version} -> v{version + 1}")
            migration(conn)
        _write_user_version(conn, config.SCHEMA_VERSION)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


T = TypeVar("T")


def _backoff(attempt: int) -> None:
    """Attente entre deux tentatives d'écriture.

    Isolée dans une fonction pour que les tests puissent la neutraliser (et
    relâcher un verrou simulé) sans attendre réellement.
    """
    time.sleep(config.SQLITE_WRITE_BACKOFF_S * attempt)


def _retry_locked(operation: Callable[[], T]) -> T:
    """Rejoue une opération bloquée par un verrou SQLite temporaire.

    SQLite lève `OperationalError: database is locked` quand `busy_timeout`
    expire. On rejoue l'instruction avec un back-off linéaire ; un verrou
    permanent finit par remonter l'erreur après `config.SQLITE_WRITE_RETRIES`
    tentatives (pas de boucle infinie). Toute autre erreur remonte aussitôt.
    """
    for attempt in range(config.SQLITE_WRITE_RETRIES):
        try:
            return operation()
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == config.SQLITE_WRITE_RETRIES - 1:
                raise
            _backoff(attempt + 1)
    raise AssertionError("retry épuisé sans erreur")  # pragma: no cover - inatteignable


class _LockRetryingConnection(sqlite3.Connection):
    """Connexion qui retente une instruction bloquée par un verrou temporaire.

    Le retry vit au niveau des méthodes d'exécution : toutes les écritures de ce
    module passent par là (y compris `BEGIN IMMEDIATE` / `COMMIT` des migrations),
    sans décorer une à une la trentaine de fonctions d'écriture.

    Le `commit` implicite du `with _conn()` n'est pas retenté : en WAL, le verrou
    d'écriture est acquis dès la première instruction, donc un `COMMIT` bloqué
    n'est pas le cas réaliste.
    """

    def execute(self, sql: str, parameters: Any = (), /) -> sqlite3.Cursor:
        return _retry_locked(lambda: super(_LockRetryingConnection, self).execute(sql, parameters))

    def executemany(self, sql: str, seq_of_parameters: Any, /) -> sqlite3.Cursor:
        return _retry_locked(
            lambda: super(_LockRetryingConnection, self).executemany(sql, seq_of_parameters)
        )

    def executescript(self, sql_script: str, /) -> sqlite3.Cursor:
        return _retry_locked(lambda: super(_LockRetryingConnection, self).executescript(sql_script))


def _conn() -> sqlite3.Connection:
    # Le dossier de données peut ne pas exister au premier lancement d'une
    # installation fraîche (pipx/pip) : on le crée, sinon SQLite échoue avec
    # « unable to open database file ».
    Path(config.CACHE_DB).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        config.CACHE_DB,
        timeout=config.SQLITE_BUSY_TIMEOUT,
        factory=_LockRetryingConnection,
    )
    # `busy_timeout` d'abord sur la connexion : attend sous contention plutôt
    # que lever `database is locked` (essentiel quand plusieurs threads écrivent).
    conn.execute(f"PRAGMA busy_timeout={config.SQLITE_BUSY_TIMEOUT}")
    conn.execute("PRAGMA foreign_keys=ON")
    # WAL : lecture/écriture concurrentes. Le changement de journal_mode peut
    # être en contention transitoire au tout premier accès multi-thread : on le
    # protège (un accès suivant le repassera en WAL si besoin), jamais bloquant.
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        pass
    try:
        _migrate(conn)
    except Exception:
        conn.close()
        raise
    return conn


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Connexion brute à la base (PRAGMA et migrations appliqués), fermée en sortie.

    Réservée aux modules de `data/` ayant besoin d'opérations non couvertes par
    l'API publique de ce module (sauvegarde/restauration). Tout le reste doit
    passer par les fonctions publiques : c'est ce qui garde le SQL confiné ici.
    """
    conn = _conn()
    try:
        yield conn
    finally:
        conn.close()


def get(ticker: str, kind: str, ttl: int) -> Any | None:
    """Renvoie l'objet caché s'il existe et n'a pas expiré, sinon None.

    Un blob illisible (pickle écrit par une version antérieure du paquet, classe
    renommée ou disparue) est traité comme un **miss** : l'entrée est purgée et
    l'appelant refait sa requête. Le cache est une optimisation, jamais une
    dépendance — un cache corrompu ne doit pas casser l'application.
    """
    with _conn() as conn:
        row = conn.execute(
            "SELECT payload, fetched_at FROM cache WHERE ticker=? AND kind=?",
            (ticker.upper(), kind),
        ).fetchone()
    if row is None:
        return None
    payload, fetched_at = row
    if time.time() - fetched_at > ttl:
        return None
    try:
        return pickle.loads(payload)
    except Exception as exc:  # noqa: BLE001 — tout blob illisible = miss
        logger.warning(
            "cache illisible (ticker=%s, kind=%s, type=%s) : entrée purgée",
            safe_label(ticker),
            safe_label(kind),
            type(exc).__name__,
        )
        _purge_entry(ticker, kind)
        return None


def _purge_entry(ticker: str, kind: str) -> None:
    """Supprime une entrée illisible (best-effort : jamais bloquant)."""
    try:
        with _conn() as conn:
            conn.execute(
                "DELETE FROM cache WHERE ticker=? AND kind=?",
                (ticker.upper(), kind),
            )
    except sqlite3.Error:
        pass


def put(ticker: str, kind: str, value: Any) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO cache (ticker, kind, payload, fetched_at) VALUES (?,?,?,?)",
            (ticker.upper(), kind, pickle.dumps(value), time.time()),
        )


def invalidate(ticker: str) -> None:
    """Refresh manuel : purge toutes les entrées d'un ticker."""
    with _conn() as conn:
        conn.execute("DELETE FROM cache WHERE ticker=?", (ticker.upper(),))


# --- Réglages utilisateur ----------------------------------------------------


def get_settings() -> dict[str, Any]:
    """Réglages effectifs, avec les défauts appliqués pour ceux jamais définis.

    Lit la table `settings` et fusionne avec `config.SETTING_DEFS` : toute clé
    absente (ou invalide) retombe sur son défaut. Ne lève jamais — un réglage
    corrompu en base ne doit pas casser les fiches. Le type de la valeur suit le
    défaut du `SETTING_DEFS` (`int` pour les fenêtres de MM, `str` pour le
    benchmark du portefeuille). Les index de MM sont renvoyés la longueur de la
    série étant vérifiée en aval (trend_is_bullish renvoie None).
    """
    out: dict[str, Any] = {key: defs["default"] for key, defs in config.SETTING_DEFS.items()}
    with _conn() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    for key, raw in rows:
        spec = config.SETTING_DEFS.get(key)
        if spec is None:
            continue  # clé obsolète, ignorée (schéma extensible)
        val = _coerce_setting(spec["default"], raw)
        if val is None or not _setting_valid(key, val):
            continue  # valeur corrompue -> défaut
        out[key] = val
    return out


def _coerce_setting(default: int | str, raw: object) -> int | str | None:
    """Convertit une valeur brute en base vers le type du défaut (None si invalide)."""
    try:
        if isinstance(default, bool):  # bool avant int (bool est sous-classe de int)
            return None
        if isinstance(default, int):
            return int(raw)  # type: ignore[arg-type]
        return str(raw)
    except (TypeError, ValueError):
        return None


def set_settings(partial: dict) -> dict[str, Any]:
    """Fusionne et persiste les réglages, puis renvoie l'état complet.

    N'accepte que des clés de `SETTING_DEFS` (les autres sont ignorées). Valide
    chaque valeur via `_setting_valid` (bornes + cohérence short<long) : lève
    ValueError si invalide (l'API la transforme en 422). Les clés absentes du dict
    `partial` conservent leur valeur courante.
    """
    current = get_settings()
    for key, raw in partial.items():
        spec = config.SETTING_DEFS.get(key)
        if spec is None:
            continue
        val = _coerce_setting(spec["default"], raw)
        if val is None:
            raise ValueError(f"Réglage invalide pour {key} : {raw!r}")
        if not _setting_valid(key, val):
            raise ValueError(f"Réglage hors bornes ou incohérent pour {key} : {val}")
        current[key] = val
    # Cohérence globale recalculée sur l'état complet (short < long).
    if not (
        _setting_valid("trend_ma_short", current["trend_ma_short"])
        and _setting_valid("trend_ma_long", current["trend_ma_long"])
        and current["trend_ma_short"] < current["trend_ma_long"]  # type: ignore[operator]
    ):
        raise ValueError("Moyenne mobile courte doit être < la longue")
    with _conn() as conn:
        for key, val in current.items():
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?,?,?)",
                (key, str(val), time.time()),
            )
    return current


def _setting_valid(key: str, value: int | str) -> bool:
    """Respecte les bornes du réglage (SETTING_DEFS.min/max).

    Pour un `int`, les bornes sont numériques ; pour une `str`, ce sont des bornes
    de LONGUEUR (min/max de caractères). Le type est celui du défaut. Un réglage
    qui déclare `choices` (liste fermée, ex. la période du portefeuille) n'accepte
    que ces valeurs.
    """
    spec = config.SETTING_DEFS.get(key)
    if spec is None:
        return False
    choices = spec.get("choices")
    if choices is not None and value not in choices:
        return False
    default = spec["default"]
    if isinstance(default, int) and not isinstance(default, bool):
        if isinstance(value, bool) or not isinstance(value, int):
            return False
        return spec["min"] <= value <= spec["max"]
    if isinstance(default, str):
        if not isinstance(value, str):
            return False
        return spec["min"] <= len(value) <= spec["max"]
    return False


# --- Paramètres de valorisation par titre (#20) ------------------------------


def get_valuation_settings(ticker: str) -> dict | None:
    """Paramètres de la calculatrice pour un titre, ou None si jamais enregistrés.

    Le payload est un JSON opaque : sa validation (clés, types) est faite par le
    service, pas ici. Ne lève jamais — une entrée corrompue est ignorée.
    """
    with _conn() as conn:
        row = conn.execute(
            "SELECT payload FROM valuation_settings WHERE ticker=?",
            (ticker.upper(),),
        ).fetchone()
    if row is None:
        return None
    try:
        data = json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def set_valuation_settings(ticker: str, payload: dict) -> None:
    """Enregistre (remplace) les paramètres de valorisation d'un titre."""
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO valuation_settings (ticker, payload, updated_at) "
            "VALUES (?,?,?)",
            (ticker.upper(), json.dumps(payload), time.time()),
        )


def clear_valuation_settings(ticker: str) -> None:
    """Efface les paramètres enregistrés d'un titre (« Réinitialiser »)."""
    with _conn() as conn:
        conn.execute("DELETE FROM valuation_settings WHERE ticker=?", (ticker.upper(),))


# --- Thèses d'entreprise (#09.3) --------------------------------------------


def get_thesis(ticker: str) -> dict | None:
    """Thèse d'un titre, ou None si absente. `content` décodé depuis le JSON.

    Le payload est opaque : sa structure est validée côté service, pas ici. Une
    entrée corrompue (JSON invalide) est traitée comme absente — jamais de crash.
    """
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, ticker, content, created_at, updated_at FROM theses WHERE ticker=?",
            (ticker.upper(),),
        ).fetchone()
    if row is None:
        return None
    try:
        content = json.loads(row[2])
    except (json.JSONDecodeError, TypeError):
        return None
    return {
        "id": row[0],
        "ticker": row[1],
        "content": content,
        "created_at": row[3],
        "updated_at": row[4],
    }


def list_theses() -> list[dict]:
    """Toutes les thèses (métadonnées seules, `content` exclu), par titre."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, ticker, created_at, updated_at FROM theses ORDER BY ticker"
        ).fetchall()
    return [{"id": r[0], "ticker": r[1], "created_at": r[2], "updated_at": r[3]} for r in rows]


def save_thesis(ticker: str, content: dict) -> int:
    """Crée ou remplace la thèse d'un titre (une par ticker). Renvoie l'id.

    `created_at` est préservé lors d'une mise à jour ; `updated_at` est réécrit.
    """
    now = time.time()
    key = ticker.upper()
    with _conn() as conn:
        row = conn.execute("SELECT id FROM theses WHERE ticker=?", (key,)).fetchone()
        payload = json.dumps(content)
        if row is None:
            cur = conn.execute(
                "INSERT INTO theses (ticker, content, created_at, updated_at) VALUES (?,?,?,?)",
                (key, payload, now, now),
            )
            return int(cur.lastrowid)
        conn.execute(
            "UPDATE theses SET content=?, updated_at=? WHERE ticker=?",
            (payload, now, key),
        )
        return int(row[0])


def delete_thesis(ticker: str) -> None:
    """Supprime la thèse d'un titre (silencieux si absente)."""
    with _conn() as conn:
        conn.execute("DELETE FROM theses WHERE ticker=?", (ticker.upper(),))


# --- Points de contrôle suivis (#21) -----------------------------------------


def list_checkpoints(ref: str) -> list[dict]:
    """Points de contrôle d'un ticker, par ordre de création (plus ancien d'abord).

    L'ordre de création est l'ordre d'affichage : c'est celui dans lequel
    l'utilisateur a écrit sa liste, et il ne doit pas bouger au cochage.
    """
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, label, done FROM checkpoints WHERE ref=? ORDER BY created_at, id",
            (ref,),
        ).fetchall()
    return [{"id": r[0], "label": r[1], "done": bool(r[2])} for r in rows]


def get_checkpoint(checkpoint_id: int) -> dict | None:
    """Un point de contrôle par id. None si absent."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, ref, label, done FROM checkpoints WHERE id=?", (checkpoint_id,)
        ).fetchone()
    if row is None:
        return None
    return {"id": row[0], "ref": row[1], "label": row[2], "done": bool(row[3])}


def count_checkpoints(ref: str) -> int:
    """Nombre de points de contrôle d'un ticker (cap `CHECKPOINT_MAX_PER_REF`)."""
    with _conn() as conn:
        return int(
            conn.execute("SELECT COUNT(*) FROM checkpoints WHERE ref=?", (ref,)).fetchone()[0]
        )


def add_checkpoint(ref: str, label: str, done: bool = False) -> int:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO checkpoints (ref, label, done, created_at) VALUES (?,?,?,?)",
            (ref, label, 1 if done else 0, time.time()),
        )
        return int(cur.lastrowid)


def update_checkpoint(checkpoint_id: int, label: str, done: bool) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE checkpoints SET label=?, done=? WHERE id=?",
            (label, 1 if done else 0, checkpoint_id),
        )


def delete_checkpoint(checkpoint_id: int) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM checkpoints WHERE id=?", (checkpoint_id,))


# --- Brouillons d'import (#23) ----------------------------------------------
# Staging : un import proposé (par une IA via le MCP, ou par un collage UI) est
# stocké `pending` et n'a AUCUN effet métier. Seule `apply_import_draft`
# (appelée par la route REST, jamais par un outil MCP) écrit dans les tables
# réelles. `payload` est un JSON opaque (structure validée côté service).


def add_import_draft(target: str, ref: str, payload: dict, status: str = "pending") -> int:
    """Crée un brouillon d'import et renvoie son identifiant."""
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO import_drafts (target, ref, payload, status, created_at) VALUES (?,?,?,?,?)",
            (target, ref, json.dumps(payload), status, time.time()),
        )
        return int(cur.lastrowid)


def get_import_draft(draft_id: int) -> dict | None:
    """Un brouillon par id (payload décodé). None si absent."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, target, ref, payload, status, created_at, applied_at "
            "FROM import_drafts WHERE id=?",
            (draft_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "target": row[1],
        "ref": row[2],
        "payload": json.loads(row[3]),
        "status": row[4],
        "created_at": row[5],
        "applied_at": row[6],
    }


def list_import_drafts(status: str = "pending") -> list[dict]:
    """Brouillons d'un statut, du plus récent au plus ancien (payload exclus)."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, target, ref, status, created_at, applied_at "
            "FROM import_drafts WHERE status=? ORDER BY created_at DESC, id DESC",
            (status,),
        ).fetchall()
    return [
        {
            "id": r[0],
            "target": r[1],
            "ref": r[2],
            "status": r[3],
            "created_at": r[4],
            "applied_at": r[5],
        }
        for r in rows
    ]


def count_import_drafts(status: str = "pending") -> int:
    """Nombre de brouillons d'un statut (cap `IMPORT_MAX_DRAFTS`)."""
    with _conn() as conn:
        return int(
            conn.execute("SELECT COUNT(*) FROM import_drafts WHERE status=?", (status,)).fetchone()[
                0
            ]
        )


def list_import_draft_ids_before(cutoff: float, status: str = "pending") -> list[int]:
    """Identifiants des brouillons d'un statut créés avant `cutoff` (purge TTL)."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id FROM import_drafts WHERE status=? AND created_at < ? ORDER BY created_at",
            (status, cutoff),
        ).fetchall()
    return [int(r[0]) for r in rows]


def mark_import_draft(draft_id: int, status: str) -> None:
    """Change le statut d'un brouillon (`applied` / `rejected`) et date l'acte.

    La ligne est **conservée** : c'est la trace d'audit (qui a appliqué quoi, et
    quand). On ne supprime que les brouillons purgés (TTL) ou explicitement
    effacés.
    """
    with _conn() as conn:
        conn.execute(
            "UPDATE import_drafts SET status=?, applied_at=? WHERE id=?",
            (status, time.time(), draft_id),
        )


def apply_import_draft(draft_id: int, ref: str, entries: list[Entry]) -> int:
    """Applique un brouillon **en une seule transaction** : écrit les données
    manuelles ET marque le brouillon `applied`.

    C'est le point dur de l'atomicité (#23) : si l'écriture métier et le passage
    de statut étaient séparés, un crash entre les deux laisserait un brouillon
    `pending` avec les données **déjà écrites** — le rejouer dupliquerait
    l'import. Le contexte `with _conn()` commit tout ou rien.

    La ligne `applied` est conservée (audit) : `list_import_drafts("applied")`
    reste donc observable. Renvoie le nombre d'entrées écrites.
    """
    ticker = ref.upper()
    now = time.time()
    with _conn() as conn:
        for e in entries:
            conn.execute(
                "INSERT OR REPLACE INTO manual_fundamentals "
                "(ticker, year, metric, value, added_at) VALUES (?,?,?,?,?)",
                (ticker, e["year"], e["metric"], e["value"], now),
            )
        conn.execute(
            "UPDATE import_drafts SET status=?, applied_at=? WHERE id=?",
            ("applied", now, draft_id),
        )
    return len(entries)


def delete_import_draft(draft_id: int) -> None:
    """Supprime définitivement un brouillon (purge TTL ou effacement)."""
    with _conn() as conn:
        conn.execute("DELETE FROM import_drafts WHERE id=?", (draft_id,))


# --- Manuel fundamentals ---

Entry = dict[str, str | float]  # {"ticker": str, "year": int, "metric": str, "value": float}


def get_manual(ticker: str) -> list[Entry]:
    """Toutes les entrées manuelles pour un ticker."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT year, metric, value FROM manual_fundamentals WHERE ticker=? ORDER BY year DESC, metric",
            (ticker.upper(),),
        ).fetchall()
    return [{"year": r[0], "metric": r[1], "value": r[2]} for r in rows]


def put_manual(ticker: str, entries: list[Entry]) -> None:
    """Insère ou remplace des entrées manuelles (batch)."""
    ticker = ticker.upper()
    now = time.time()
    with _conn() as conn:
        for e in entries:
            conn.execute(
                "INSERT OR REPLACE INTO manual_fundamentals (ticker, year, metric, value, added_at) VALUES (?,?,?,?,?)",
                (ticker, e["year"], e["metric"], e["value"], now),
            )


def delete_manual_year(ticker: str, year: int) -> None:
    """Supprime toutes les entrées manuelles d'une année."""
    with _conn() as conn:
        conn.execute(
            "DELETE FROM manual_fundamentals WHERE ticker=? AND year=?",
            (ticker.upper(), year),
        )


def delete_manual(ticker: str) -> None:
    """Supprime toutes les entrées manuelles d'un ticker."""
    with _conn() as conn:
        conn.execute(
            "DELETE FROM manual_fundamentals WHERE ticker=?",
            (ticker.upper(),),
        )


# --- Événements (annotations datées des graphiques) --------------------------


def list_events(ref: str) -> list[dict]:
    """Événements d'un graphe (ref = ticker, RATIO:A/B ou INDEX:<id>), par date."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, event_date, label, description FROM events WHERE ref=? ORDER BY event_date, id",
            (ref,),
        ).fetchall()
    return [{"id": r[0], "date": r[1], "label": r[2], "description": r[3]} for r in rows]


def get_event(event_id: int) -> dict | None:
    """Un événement par id. None si absent."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, ref, event_date, label, description FROM events WHERE id=?", (event_id,)
        ).fetchone()
    if row is None:
        return None
    return {"id": row[0], "ref": row[1], "date": row[2], "label": row[3], "description": row[4]}


def add_event(ref: str, date: str, label: str, description: str | None) -> int:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO events (ref, event_date, label, description, created_at) VALUES (?,?,?,?,?)",
            (ref, date, label, description, time.time()),
        )
        return int(cur.lastrowid)


def update_event(event_id: int, date: str, label: str, description: str | None) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE events SET event_date=?, label=?, description=? WHERE id=?",
            (date, label, description, event_id),
        )


def delete_event(event_id: int) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM events WHERE id=?", (event_id,))


# --- Indices personnalisés ---------------------------------------------------
# Définitions persistées (survivent au refresh et aux redémarrages), pattern des
# données manuelles. Les séries calculées, elles, passent par la table `cache`
# (clé `INDEX:<id>` / kind "basket") avec le TTL prix standard.


def list_indices_by_category() -> list[dict]:
    """Catégories + indices (définitions uniquement, aucun calcul)."""
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.name, i.id, i.name, i.tickers
            FROM custom_categories c
            LEFT JOIN custom_indices i ON i.category_id = c.id
            ORDER BY c.name, i.name
            """
        ).fetchall()
    cats: dict[int, dict] = {}
    for cat_id, cat_name, idx_id, idx_name, tickers in rows:
        if cat_id not in cats:
            cats[cat_id] = {"id": cat_id, "name": cat_name, "indices": []}
        if idx_id is not None:
            cats[cat_id]["indices"].append(
                {"id": idx_id, "name": idx_name, "tickers": json.loads(tickers)}
            )
    return list(cats.values())


def get_index_definition(index_id: int) -> dict | None:
    """Définition d'un indice (avec sa catégorie). None si absent."""
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT i.id, i.name, i.tickers, c.id, c.name
            FROM custom_indices i
            JOIN custom_categories c ON c.id = i.category_id
            WHERE i.id = ?
            """,
            (index_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "name": row[1],
        "tickers": json.loads(row[2]),
        "category_id": row[3],
        "category": row[4],
    }


def category_exists(category_id: int) -> bool:
    with _conn() as conn:
        row = conn.execute("SELECT 1 FROM custom_categories WHERE id=?", (category_id,)).fetchone()
    return row is not None


def create_category(name: str) -> int:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO custom_categories (name, created_at) VALUES (?,?)",
            (name, time.time()),
        )
        return int(cur.lastrowid)


def delete_category(category_id: int) -> None:
    """Supprime une catégorie et ses indices (cascade) + purge leurs caches."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id FROM custom_indices WHERE category_id=?", (category_id,)
        ).fetchall()
        conn.execute("DELETE FROM custom_categories WHERE id=?", (category_id,))
    for (idx_id,) in rows:
        invalidate(f"INDEX:{idx_id}")


def create_index(category_id: int, name: str, tickers: list[str]) -> int:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO custom_indices (category_id, name, tickers, created_at) VALUES (?,?,?,?)",
            (category_id, name, json.dumps(tickers), time.time()),
        )
        return int(cur.lastrowid)


def update_index(index_id: int, category_id: int, name: str, tickers: list[str]) -> None:
    """Remplace la définition complète d'un indice (+ purge de sa série cachée)."""
    with _conn() as conn:
        conn.execute(
            "UPDATE custom_indices SET category_id=?, name=?, tickers=? WHERE id=?",
            (category_id, name, json.dumps(tickers), index_id),
        )
    invalidate(f"INDEX:{index_id}")


def delete_index(index_id: int) -> None:
    """Supprime un indice (+ purge de sa série cachée)."""
    with _conn() as conn:
        conn.execute("DELETE FROM custom_indices WHERE id=?", (index_id,))
    invalidate(f"INDEX:{index_id}")


# --- Portefeuille (#17) ------------------------------------------------------
# I/O brut des tables du portefeuille. La validation vit dans `data/portfolio.py`
# (comme `events.py` au-dessus de ces fonctions) : ce module reste du SQL pur.


def list_portfolio_accounts() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, name, currency, created_at FROM portfolio_accounts ORDER BY name, id"
        ).fetchall()
    return [{"id": r[0], "name": r[1], "currency": r[2], "created_at": r[3]} for r in rows]


def get_portfolio_account(account_id: int) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, name, currency, created_at FROM portfolio_accounts WHERE id=?",
            (account_id,),
        ).fetchone()
    if row is None:
        return None
    return {"id": row[0], "name": row[1], "currency": row[2], "created_at": row[3]}


def create_portfolio_account(name: str, currency: str) -> int:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO portfolio_accounts (name, currency, created_at) VALUES (?,?,?)",
            (name, currency, time.time()),
        )
        return int(cur.lastrowid)


def delete_portfolio_account(account_id: int) -> None:
    """Supprime un compte (transactions/dividendes en cascade via FK)."""
    with _conn() as conn:
        conn.execute("DELETE FROM portfolio_accounts WHERE id=?", (account_id,))


def list_portfolio_transactions(
    account_id: int | None = None, tag: str | None = None
) -> list[dict]:
    """Transactions, filtrables par compte et/ou étiquette (#17.6). Tri : date puis id.

    Les deux filtres se **combinent** (ET) : « ce compte ET cette étiquette »
    autant que l'un ou l'autre seul. `tag=None` = pas de filtre d'étiquette (et
    non « les transactions sans étiquette ») : la sémantique « sans étiquette »
    n'est pas exposée (le sélecteur du front propose « Toutes » uniquement).
    """
    where: list[str] = []
    params: list[object] = []
    if account_id is not None:
        where.append("account_id=?")
        params.append(account_id)
    if tag is not None:
        where.append("tag=?")
        params.append(tag)
    sql = (
        "SELECT id, account_id, ticker, side, trade_date, quantity, price, fees, "
        "currency, note, tag, created_at FROM portfolio_transactions"
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY trade_date, id"
    with _conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_tx_row(r) for r in rows]


def list_portfolio_tags(account_id: int | None = None) -> list[str]:
    """Étiquettes distinctes non vides des transactions, triées (insensible casse).

    Aucune table de référence : un portefeuille virtuel n'existe que par les
    transactions qui le portent. Sert l'auto-complétion et le sélecteur du front.

    `account_id` restreint la liste aux étiquettes présentes dans ce compte
    (#17.6) : le sélecteur du front ne propose alors que des étiquettes qui
    existent réellement pour le périmètre affiché (sinon on pourrait choisir une
    étiquette absente du compte et vider l'écran sans explication).
    """
    sql = "SELECT DISTINCT tag FROM portfolio_transactions WHERE tag IS NOT NULL AND tag<>''"
    params: list[object] = []
    if account_id is not None:
        sql += " AND account_id=?"
        params.append(account_id)
    sql += " ORDER BY tag COLLATE NOCASE"
    with _conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [r[0] for r in rows]


def get_portfolio_transaction(tx_id: int) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, account_id, ticker, side, trade_date, quantity, price, fees, "
            "currency, note, tag, created_at FROM portfolio_transactions WHERE id=?",
            (tx_id,),
        ).fetchone()
    return None if row is None else _tx_row(row)


def add_portfolio_transaction(tx: dict) -> int:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO portfolio_transactions "
            "(account_id, ticker, side, trade_date, quantity, price, fees, currency, note, "
            "tag, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                tx["account_id"],
                tx["ticker"],
                tx["side"],
                tx["trade_date"],
                tx["quantity"],
                tx["price"],
                tx["fees"],
                tx["currency"],
                tx["note"],
                tx["tag"],
                time.time(),
            ),
        )
        return int(cur.lastrowid)


def update_portfolio_transaction(tx_id: int, tx: dict) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE portfolio_transactions SET account_id=?, ticker=?, side=?, trade_date=?, "
            "quantity=?, price=?, fees=?, currency=?, note=?, tag=? WHERE id=?",
            (
                tx["account_id"],
                tx["ticker"],
                tx["side"],
                tx["trade_date"],
                tx["quantity"],
                tx["price"],
                tx["fees"],
                tx["currency"],
                tx["note"],
                tx["tag"],
                tx_id,
            ),
        )


def delete_portfolio_transaction(tx_id: int) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM portfolio_transactions WHERE id=?", (tx_id,))


def set_portfolio_transactions_tag(account_id: int | None, ticker: str, tag: str | None) -> int:
    """Applique une étiquette à TOUTES les transactions d'un titre (#17.6).

    « Étiqueter une position » = étiqueter les transactions qui la composent.
    `account_id=None` = tous les comptes ; sinon le seul compte donné. `tag=None`
    efface l'étiquette. Renvoie le nombre de lignes modifiées.
    """
    where = ["ticker=?"]
    params: list[object] = [ticker]
    if account_id is not None:
        where.append("account_id=?")
        params.append(account_id)
    sql = f"UPDATE portfolio_transactions SET tag=? WHERE {' AND '.join(where)}"
    with _conn() as conn:
        cur = conn.execute(sql, [tag, *params])
        return int(cur.rowcount)


def _tx_row(r: tuple) -> dict:
    return {
        "id": r[0],
        "account_id": r[1],
        "ticker": r[2],
        "side": r[3],
        "trade_date": r[4],
        "quantity": r[5],
        "price": r[6],
        "fees": r[7],
        "currency": r[8],
        "note": r[9],
        "tag": r[10],
        "created_at": r[11],
    }


def list_portfolio_dividends(account_id: int | None = None) -> list[dict]:
    with _conn() as conn:
        if account_id is None:
            rows = conn.execute(
                "SELECT id, account_id, ticker, pay_date, amount, status, source, created_at "
                "FROM portfolio_dividends ORDER BY pay_date, id"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, account_id, ticker, pay_date, amount, status, source, created_at "
                "FROM portfolio_dividends WHERE account_id=? ORDER BY pay_date, id",
                (account_id,),
            ).fetchall()
    return [_div_row(r) for r in rows]


def get_portfolio_dividend(div_id: int) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, account_id, ticker, pay_date, amount, status, source, created_at "
            "FROM portfolio_dividends WHERE id=?",
            (div_id,),
        ).fetchone()
    return None if row is None else _div_row(row)


def add_portfolio_dividend(div: dict) -> int:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO portfolio_dividends "
            "(account_id, ticker, pay_date, amount, status, source, created_at) VALUES (?,?,?,?,?,?,?)",
            (
                div["account_id"],
                div["ticker"],
                div["pay_date"],
                div["amount"],
                div["status"],
                div["source"],
                time.time(),
            ),
        )
        return int(cur.lastrowid)


def update_portfolio_dividend(div_id: int, div: dict) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE portfolio_dividends SET account_id=?, ticker=?, pay_date=?, amount=?, "
            "status=?, source=? WHERE id=?",
            (
                div["account_id"],
                div["ticker"],
                div["pay_date"],
                div["amount"],
                div["status"],
                div["source"],
                div_id,
            ),
        )


def delete_portfolio_dividend(div_id: int) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM portfolio_dividends WHERE id=?", (div_id,))


def _div_row(r: tuple) -> dict:
    return {
        "id": r[0],
        "account_id": r[1],
        "ticker": r[2],
        "pay_date": r[3],
        "amount": r[4],
        "status": r[5],
        "source": r[6],
        "created_at": r[7],
    }
