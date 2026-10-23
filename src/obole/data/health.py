"""Contrôle de santé des briques techniques (#01), servi par `GET /api/health`.

Vivrait dans `api/` s'il ne touchait pas le disque : c'est un accès I/O, donc il
reste dans `data/` (seule couche autorisée). L'API se contente de l'exposer.

Sémantique des briques :
  - `sqlite` et `cache` sont **critiques** : sans elles, l'application ne peut
    rien faire (503) ;
  - `yfinance` est **non critique** : la dégradation gracieuse est un principe du
    projet (un titre indisponible renvoie None, jamais de crash), donc un
    yfinance HS donne un statut `degraded` mais laisse l'app utilisable (200).

Aucun appel réseau : la brique yfinance rapporte l'importabilité, la version et
les échecs récents observés par `_with_retry`.
"""

from __future__ import annotations

import time
from types import ModuleType

from obole import config, observability
from obole.data import cache

logger = observability.get_logger(__name__)

# Clé sentinelle du test d'aller-retour cache : écrite puis supprimée aussitôt.
_HEALTH_KEY = "__health__"
_HEALTH_KIND = "health"
_HEALTH_TTL = 60

# Briques dont la panne rend l'application inutilisable (-> 503).
_CRITICAL = ("sqlite", "cache")


def _import_yfinance() -> ModuleType | None:
    """Importe yfinance, ou None s'il est indisponible (dégradation)."""
    try:
        import yfinance
    except Exception:  # noqa: BLE001 - l'import peut échouer de mille façons
        logger.warning("yfinance non importable", exc_info=True)
        return None
    return yfinance


def check_sqlite() -> dict:
    """La base est ouvrable et son schéma est versionné."""
    try:
        with cache.connect() as conn:
            conn.execute("SELECT 1").fetchone()
            version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    except Exception as exc:  # noqa: BLE001 - on rapporte, on ne propage pas
        logger.warning("Brique sqlite en échec", exc_info=True)
        return {"status": "down", "error": type(exc).__name__}
    return {"status": "ok", "schema_version": version}


def check_cache() -> dict:
    """Aller-retour écriture/lecture du cache, sur une clé sentinelle purgée ensuite."""
    try:
        stamp = time.time()
        cache.put(_HEALTH_KEY, _HEALTH_KIND, stamp)
        read_back = cache.get(_HEALTH_KEY, _HEALTH_KIND, _HEALTH_TTL)
    except Exception as exc:  # noqa: BLE001
        _purge_health_key()
        logger.warning("Brique cache en échec", exc_info=True)
        return {"status": "down", "error": type(exc).__name__}
    _purge_health_key()
    if read_back != stamp:
        return {"status": "down", "error": "aller-retour incohérent"}
    return {"status": "ok"}


def _purge_health_key() -> None:
    """Supprime la clé sentinelle (jamais bloquant : le diagnostic prime)."""
    try:
        cache.invalidate(_HEALTH_KEY)
    except Exception:  # noqa: BLE001
        logger.warning("Clé sentinelle de santé non purgée", exc_info=True)


def check_yfinance() -> dict:
    """Importabilité, version et échecs récents — sans aucun appel réseau."""
    module = _import_yfinance()
    if module is None:
        return {"status": "down", "error": "import"}
    failures = observability.recent_failures(config.HEALTH_FAILURE_WINDOW_S)
    return {
        "status": "degraded" if failures else "ok",
        "version": getattr(module, "__version__", None),
        "recent_failures": failures,
        "last_failure": observability.last_failure(),
    }


def snapshot() -> dict:
    """Rapport complet : statut agrégé + une entrée par brique.

    Ne lève jamais : une brique qui explose est rapportée `down` (c'est le but
    d'un contrôle de santé).
    """
    bricks: dict[str, dict] = {}
    for name, check in (
        ("yfinance", check_yfinance),
        ("sqlite", check_sqlite),
        ("cache", check_cache),
    ):
        try:
            bricks[name] = check()
        except Exception as exc:  # noqa: BLE001
            bricks[name] = {"status": "down", "error": type(exc).__name__}

    if any(bricks[name]["status"] != "ok" for name in _CRITICAL):
        overall = "down"
    elif any(brick["status"] != "ok" for brick in bricks.values()):
        overall = "degraded"
    else:
        overall = "ok"
    return {"status": overall, "bricks": bricks}
