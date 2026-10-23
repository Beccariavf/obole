"""Portefeuille : comptes, transactions, dividendes (I/O + validation).

Les transactions sont la **source de vérité** ; les positions sont recalculées
(jamais saisies). Cette couche ne fait que de l'I/O + validation stricte : aucun
calcul d'agrégat (engine). Toute entrée est traitée comme hostile par défaut
(l'import MCP-B passera par ici) : date ISO, quantité > 0, prix/frais >= 0, sens
et statut dans une liste fermée, ticker non vide normalisé en majuscules.

Toutes les fonctions publiques lèvent `ValueError` sur entrée invalide (l'API la
transforme en 422) et `ValueError` sur identifiant inconnu (l'API -> 404).
"""

from __future__ import annotations

import datetime as _dt

from obole import config
from obole.data import cache

# Listes fermées (schéma exact dans la fiche #17 §4.1).
SIDES = ("buy", "sell")
DIVIDEND_STATUSES = ("proposed", "confirmed")
DIVIDEND_SOURCES = ("manual", "yahoo")

DEFAULT_CURRENCY = "EUR"


class NotFoundError(ValueError):
    """Identifiant inconnu (compte, transaction, dividende).

    Sous-classe de `ValueError` (rétro-compatible avec les appelants qui
    attrapent `ValueError`) : l'API la traduit en **404**, distincte d'une entrée
    invalide (422). Le contrat HTTP ne dépend donc plus du texte du message.
    """


# --- Comptes -----------------------------------------------------------------


def list_accounts() -> list[dict]:
    """Comptes du portefeuille, triés par nom."""
    return cache.list_portfolio_accounts()


def create_account(name: str, currency: str | None = None) -> int:
    """Crée un compte. Lève ValueError si le nom est vide."""
    return cache.create_portfolio_account(
        _require(name, "nom de compte"), _valid_currency(currency)
    )


def delete_account(account_id: int) -> None:
    """Supprime un compte et ses lignes (cascade). Lève ValueError si inconnu."""
    if cache.get_portfolio_account(account_id) is None:
        raise NotFoundError(f"Compte inconnu : {account_id}")
    cache.delete_portfolio_account(account_id)


# --- Transactions ------------------------------------------------------------


def list_transactions(account_id: int | None = None, tag: str | None = None) -> list[dict]:
    """Transactions, filtrables par compte et/ou étiquette (#17.6). Tri par date.

    Les deux filtres se combinent. `tag` est normalisé (trim, non vide) avant la
    requête ; `tag=None` = aucun filtre d'étiquette.
    """
    return cache.list_portfolio_transactions(account_id, _normalize_tag_query(tag))


def list_tags(account_id: int | None = None) -> list[str]:
    """Étiquettes distinctes des transactions (portefeuilles virtuels), triées.

    `account_id` restreint la liste au compte donné (#17.6) — le sélecteur du
    front ne propose que des étiquettes réellement présentes dans le périmètre.
    """
    return cache.list_portfolio_tags(account_id)


def add_transaction(
    account_id: int,
    ticker: str,
    side: str,
    trade_date: str,
    quantity: float,
    price: float,
    fees: float = 0.0,
    currency: str | None = None,
    note: str | None = None,
    tag: str | None = None,
) -> int:
    """Ajoute une transaction. Lève ValueError si une donnée est invalide."""
    tx = _clean_transaction(
        account_id, ticker, side, trade_date, quantity, price, fees, currency, note, tag
    )
    return cache.add_portfolio_transaction(tx)


def update_transaction(
    tx_id: int,
    account_id: int,
    ticker: str,
    side: str,
    trade_date: str,
    quantity: float,
    price: float,
    fees: float = 0.0,
    currency: str | None = None,
    note: str | None = None,
    tag: str | None = None,
) -> None:
    """Remplace une transaction. Lève ValueError si invalide ou inconnue."""
    if cache.get_portfolio_transaction(tx_id) is None:
        raise NotFoundError(f"Transaction inconnue : {tx_id}")
    tx = _clean_transaction(
        account_id, ticker, side, trade_date, quantity, price, fees, currency, note, tag
    )
    cache.update_portfolio_transaction(tx_id, tx)


def delete_transaction(tx_id: int) -> None:
    """Supprime une transaction. Lève ValueError si inconnue."""
    if cache.get_portfolio_transaction(tx_id) is None:
        raise NotFoundError(f"Transaction inconnue : {tx_id}")
    cache.delete_portfolio_transaction(tx_id)


def set_tag(account_id: int | None, ticker: str, tag: str | None) -> int:
    """Étiquette TOUTES les transactions d'un titre (#17.6) et renvoie le compte.

    « Étiqueter une position » = étiqueter les transactions qui la composent (dans
    le compte courant, ou tous les comptes si `account_id` est None). `tag=None`
    efface l'étiquette. Lève ValueError sur ticker vide ou étiquette invalide.
    """
    ticker = _valid_ticker(ticker)
    if account_id is not None:
        _valid_account_id(account_id)
    return cache.set_portfolio_transactions_tag(account_id, ticker, _optional_tag(tag))


# --- Dividendes --------------------------------------------------------------


def list_dividends(account_id: int | None = None) -> list[dict]:
    """Dividendes, éventuellement filtrés par compte (tri par date)."""
    return cache.list_portfolio_dividends(account_id)


def add_dividend(
    account_id: int,
    ticker: str,
    pay_date: str,
    amount: float,
    status: str = "confirmed",
    source: str = "manual",
) -> int:
    """Ajoute un dividende. Lève ValueError si une donnée est invalide."""
    div = _clean_dividend(account_id, ticker, pay_date, amount, status, source)
    return cache.add_portfolio_dividend(div)


def update_dividend(
    div_id: int,
    account_id: int,
    ticker: str,
    pay_date: str,
    amount: float,
    status: str = "confirmed",
    source: str = "manual",
) -> None:
    """Remplace un dividende. Lève ValueError si invalide ou inconnu."""
    if cache.get_portfolio_dividend(div_id) is None:
        raise NotFoundError(f"Dividende inconnu : {div_id}")
    div = _clean_dividend(account_id, ticker, pay_date, amount, status, source)
    cache.update_portfolio_dividend(div_id, div)


def delete_dividend(div_id: int) -> None:
    """Supprime un dividende. Lève ValueError si inconnu."""
    if cache.get_portfolio_dividend(div_id) is None:
        raise NotFoundError(f"Dividende inconnu : {div_id}")
    cache.delete_portfolio_dividend(div_id)


# --- Validation --------------------------------------------------------------


def _clean_transaction(
    account_id: int,
    ticker: str,
    side: str,
    trade_date: str,
    quantity: float,
    price: float,
    fees: float,
    currency: str | None,
    note: str | None,
    tag: str | None = None,
) -> dict:
    _require_account(account_id)
    side = (side or "").strip().lower()
    if side not in SIDES:
        raise ValueError(f"Sens invalide : {side!r} (attendu : {' ou '.join(SIDES)})")
    return {
        "account_id": _valid_account_id(account_id),
        "ticker": _valid_ticker(ticker),
        "side": side,
        "trade_date": _valid_date(trade_date),
        "quantity": _positive(quantity, "quantité"),
        "price": _non_negative(price, "prix"),
        "fees": _non_negative(fees, "frais"),
        "currency": _valid_currency(currency),
        "note": _optional_note(note),
        "tag": _optional_tag(tag),
    }


def _clean_dividend(
    account_id: int,
    ticker: str,
    pay_date: str,
    amount: float,
    status: str,
    source: str,
) -> dict:
    _require_account(account_id)
    status = (status or "").strip().lower()
    if status not in DIVIDEND_STATUSES:
        raise ValueError(f"Statut invalide : {status!r}")
    source = (source or "").strip().lower()
    if source not in DIVIDEND_SOURCES:
        raise ValueError(f"Source invalide : {source!r}")
    return {
        "account_id": _valid_account_id(account_id),
        "ticker": _valid_ticker(ticker),
        "pay_date": _valid_date(pay_date),
        "amount": _non_negative(amount, "montant"),
        "status": status,
        "source": source,
    }


def _require_account(account_id: int) -> None:
    if cache.get_portfolio_account(_valid_account_id(account_id)) is None:
        raise NotFoundError(f"Compte inconnu : {account_id}")


def _valid_account_id(account_id: int) -> int:
    if isinstance(account_id, bool) or not isinstance(account_id, int):
        raise ValueError(f"Identifiant de compte invalide : {account_id!r}")
    return account_id


def _valid_ticker(ticker: str) -> str:
    ticker = (ticker or "").strip().upper()
    if not ticker:
        raise ValueError("Le ticker ne peut pas être vide")
    return ticker


def _valid_date(date: str) -> str:
    """Normalise et valide la date ISO (AAAA-MM-JJ)."""
    date = (date or "").strip()
    try:
        return _dt.date.fromisoformat(date).isoformat()
    except ValueError as exc:
        raise ValueError(f"Date invalide : {date!r} (format attendu AAAA-MM-JJ)") from exc


def _positive(value: float, what: str) -> float:
    value = _number(value, what)
    if value <= 0:
        raise ValueError(f"La {what} doit être strictement positive ({value})")
    return value


def _non_negative(value: float, what: str) -> float:
    value = _number(value, what)
    if value < 0:
        raise ValueError(f"Le {what} ne peut pas être négatif ({value})")
    return value


def _number(value: float, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"Valeur numérique attendue pour {what} : {value!r}")
    return float(value)


def _valid_currency(currency: str | None) -> str:
    """Devise du compte. Mono-devise **EUR** tant que la conversion n'existe pas
    (fiche #17 §3) : accepter une autre devise produirait des positions
    consolidées fausses (somme de montants sans conversion)."""
    currency = (currency or "").strip().upper()
    if currency and currency != DEFAULT_CURRENCY:
        raise ValueError(
            f"Devise non supportée : {currency!r} (mono-devise {DEFAULT_CURRENCY} uniquement)"
        )
    return DEFAULT_CURRENCY


def _optional_note(note: str | None) -> str | None:
    if note is None:
        return None
    note = str(note).strip()
    return note or None


def _optional_tag(tag: str | None) -> str | None:
    """Normalise l'étiquette (#17.6) : trim, non vide -> None, longueur bornée.

    L'étiquette est une clé de regroupement libre (portefeuille virtuel). Elle est
    stockée **telle quelle** après trim (accents, espaces et casse conservés : un
    libellé lisible), bornée à `config.PORTFOLIO_TAG_MAX`. Les caractères de
    contrôle (retours ligne, tabulations) sont refusés : une étiquette tient sur
    une ligne et sert de libellé d'interface.
    """
    if tag is None:
        return None
    tag = str(tag).strip()
    if not tag:
        return None
    if len(tag) > config.PORTFOLIO_TAG_MAX:
        raise ValueError(
            f"Étiquette trop longue ({len(tag)} > {config.PORTFOLIO_TAG_MAX} caractères)"
        )
    if any(ch in "\r\n\t" or ord(ch) < 32 for ch in tag):
        raise ValueError("Étiquette invalide : caractères de contrôle interdits")
    return tag


def _normalize_tag_query(tag: str | None) -> str | None:
    """Filtre d'étiquette d'une lecture : `None` ou chaîne vide = pas de filtre."""
    if tag is None:
        return None
    tag = str(tag).strip()
    return tag or None


def _require(value: str, what: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ValueError(f"Le {what} ne peut pas être vide")
    return value
