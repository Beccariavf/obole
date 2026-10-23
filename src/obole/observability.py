"""Observabilité : journalisation du serveur Obole (#01).

Module **feuille** de l'arbre de dépendances (stdlib + `config` uniquement, comme
`config.py`) : toutes les couches peuvent l'importer, il n'importe rien de
l'application. C'est ce qui permet de tracer depuis `data/` sans casser
l'invariant `web → api → services → engine → data`.

Trois responsabilités, toutes sans I/O réseau :

  - `configure_logging()` : installe la sortie (console sur **stderr** + fichier
    local à rotation). Idempotente.
  - `safe_label()` : nettoie un libellé d'origine externe avant journalisation.
  - `record_failure()` / `recent_failures()` : compteur d'échecs d'appels
    externes, lu par `GET /api/health` (brique yfinance).
"""

from __future__ import annotations

import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from obole import config

LOGGER_NAME = "obole"
_LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"
_LABEL_MAX = 120
_VALID_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


class _ConsoleHandler(logging.StreamHandler):
    """Handler console marqué : permet à `configure_logging` d'être idempotente."""

    _obole = True


class _FileHandler(RotatingFileHandler):
    """Handler fichier marqué (cf. `_ConsoleHandler`)."""

    _obole = True


def safe_label(value: object) -> str:
    """Nettoie un libellé avant de le journaliser (anti-injection de logs).

    Un ticker ou une requête de recherche vient de l'extérieur : un saut de ligne
    permettrait de forger de fausses entrées d'audit. On ne conserve que les
    caractères imprimables, bornés en longueur.
    """
    text = "".join(char if char.isprintable() else " " for char in str(value))
    return text[:_LABEL_MAX]


def resolve_level() -> int:
    """Niveau de log depuis `OBOLE_LOG_LEVEL` (défaut INFO ; valeur inconnue -> INFO)."""
    raw = os.environ.get("OBOLE_LOG_LEVEL", "INFO").strip().upper()
    if raw in _VALID_LEVELS:
        return int(logging.getLevelName(raw))
    return logging.INFO


def get_logger(name: str) -> logging.Logger:
    """Logger de l'application, rangé sous l'arbre `obole`."""
    if name == LOGGER_NAME or name.startswith(f"{LOGGER_NAME}."):
        return logging.getLogger(name)
    return logging.getLogger(f"{LOGGER_NAME}.{name}")


def configure_logging(log_file: Path | None = None, level: int | None = None) -> logging.Logger:
    """Configure la journalisation et renvoie le logger racine. Idempotente.

    Console sur **stderr** : stdout reste réservé au message de démarrage
    (« Obole prêt sur … », émis par `__main__._serve` une fois le bind réussi),
    que le harnais de lancement attend sur stdout.
    Un fichier de log inaccessible (droits, disque plein) dégrade vers la
    console seule plutôt que de faire échouer le démarrage.
    """
    logger = logging.getLogger(LOGGER_NAME)
    if any(getattr(handler, "_obole", False) for handler in logger.handlers):
        return logger

    logger.setLevel(resolve_level() if level is None else level)
    logger.propagate = False  # pas de double sortie via le logger racine
    formatter = logging.Formatter(_LOG_FORMAT)

    console = _ConsoleHandler(sys.stderr)
    console.setFormatter(formatter)
    logger.addHandler(console)

    path = Path(log_file) if log_file is not None else config.LOG_FILE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = _FileHandler(
            path,
            maxBytes=config.LOG_MAX_BYTES,
            backupCount=config.LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
    except OSError as exc:  # disque plein, droits… : la console suffit
        logger.warning(
            "Fichier de log indisponible (%s) : sortie console seule", type(exc).__name__
        )
    else:
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    return logger


# --- Compteur d'échecs d'appels externes ------------------------------------
# Alimenté par les points d'appel (cf. `data/yahoo.py::_with_retry`) et lu par la
# brique yfinance de `/api/health`. Aucune I/O : simple horodatage monotone.

_failures: list[tuple[float, str]] = []
# Plafond dur : la purge par fenêtre n'a lieu que dans `recent_failures()`
# (appelée par `/api/health`). Sans poll de santé, la liste croîtrait sans
# borne sur un serveur long-running — on garde donc les N derniers.
_MAX_FAILURES = 1000


def record_failure(label: str = "") -> None:
    """Enregistre un échec d'appel externe (libellé déjà assaini)."""
    _failures.append((time.monotonic(), safe_label(label)))
    if len(_failures) > _MAX_FAILURES:
        del _failures[:-_MAX_FAILURES]


def recent_failures(window_s: float) -> int:
    """Échecs survenus dans la fenêtre glissante (les anciens sont purgés)."""
    cutoff = time.monotonic() - window_s
    while _failures and _failures[0][0] < cutoff:
        _failures.pop(0)
    return len(_failures)


def last_failure() -> str | None:
    """Libellé du dernier échec enregistré, ou None."""
    return _failures[-1][1] if _failures else None


def reset_stats() -> None:
    """Vide le compteur d'échecs (isolation des tests)."""
    _failures.clear()
