"""Portefeuille — couche données : schéma, validation, sauvegarde (#17.0).

Sans réseau. Le cache est isolé sur une base temporaire (config.CACHE_DB), comme
tests/test_backup.py. On couvre : convergence v1 -> v2, idempotence, validation
stricte des transactions/dividendes, et l'intégration à la sauvegarde.
"""

from __future__ import annotations

import sqlite3
import tempfile

import pytest

from obole import config
from obole.data import backup, cache
from obole.data import portfolio as portfolio_data


@pytest.fixture(autouse=True)
def _isolated_db():
    _orig = config.CACHE_DB
    config.CACHE_DB = tempfile.mktemp(suffix=".sqlite")
    yield
    config.CACHE_DB = _orig


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _account(name: str = "PEA") -> int:
    return portfolio_data.create_account(name)


class TestSchemaV2:
    """J0.1 — migration 1 -> 2 et tables du portefeuille."""

    def test_fresh_db_is_v2_with_portfolio_tables(self):
        conn = cache._conn()
        try:
            assert cache._read_user_version(conn) == config.SCHEMA_VERSION
            assert config.SCHEMA_VERSION >= 2
            assert {
                "portfolio_accounts",
                "portfolio_transactions",
                "portfolio_dividends",
            } <= _table_names(conn)
        finally:
            conn.close()

    def test_v1_db_upgraded_and_data_preserved(self):
        # Base v1 : baseline seule, données utilisateur insérées, version forcée à 1.
        conn = sqlite3.connect(config.CACHE_DB)
        try:
            cache.MIGRATIONS[0](conn)
            conn.execute(
                "INSERT INTO events (ref, event_date, label, description, created_at)"
                " VALUES ('RI.PA','2020-01-01','Ancien',NULL,1.0)"
            )
            cache._write_user_version(conn, 1)
            conn.commit()
        finally:
            conn.close()

        conn = cache._conn()  # déclenche les migrations 1 -> 2 -> …
        try:
            assert cache._read_user_version(conn) == config.SCHEMA_VERSION
            assert "portfolio_transactions" in _table_names(conn)
            assert conn.execute("SELECT label FROM events").fetchone()[0] == "Ancien"
        finally:
            conn.close()

    def test_migration_1_to_2_is_idempotent(self):
        cache._conn().close()  # base en v2
        conn = sqlite3.connect(config.CACHE_DB)
        try:
            cache.MIGRATIONS[1](conn)  # rejouée : aucun effet, aucune erreur
            conn.commit()
        finally:
            conn.close()
        conn = cache._conn()
        try:
            assert "portfolio_accounts" in _table_names(conn)
        finally:
            conn.close()


class TestAccounts:
    """J0.2 — CRUD comptes + validation."""

    def test_create_and_list(self):
        acc = _account("PEA")
        rows = portfolio_data.list_accounts()
        assert [r["id"] for r in rows] == [acc]
        assert rows[0]["currency"] == "EUR"

    def test_empty_name_rejected(self):
        with pytest.raises(ValueError, match="nom de compte"):
            portfolio_data.create_account("   ")

    def test_default_currency_is_eur(self):
        acc = portfolio_data.create_account("PEA")
        assert portfolio_data.list_accounts()[0]["currency"] == "EUR"
        assert acc > 0

    def test_non_eur_currency_rejected(self):
        """Mono-devise assumée : une autre devise rendrait la consolidation fausse."""
        with pytest.raises(ValueError, match="Devise non supportée"):
            portfolio_data.create_account("PEA", "USD")

    def test_delete_unknown_rejected(self):
        with pytest.raises(ValueError, match="Compte inconnu"):
            portfolio_data.delete_account(999)

    def test_delete_cascades_children(self):
        acc = _account()
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2024-01-02", 10, 100.0)
        portfolio_data.delete_account(acc)
        assert portfolio_data.list_transactions() == []
        assert portfolio_data.list_accounts() == []


class TestTransactionValidation:
    """J0.2 — validation stricte des transactions."""

    def test_valid_transaction_roundtrip(self):
        acc = _account()
        tx_id = portfolio_data.add_transaction(
            acc, "ri.pa", "buy", "2024-01-02", 10, 100.0, fees=1.5, note="initiale"
        )
        (tx,) = portfolio_data.list_transactions(acc)
        assert tx["id"] == tx_id
        assert tx["ticker"] == "RI.PA"  # normalisé upper
        assert tx["side"] == "buy"
        assert tx["quantity"] == 10
        assert tx["fees"] == 1.5
        assert tx["note"] == "initiale"
        assert tx["currency"] == "EUR"

    def test_invalid_date_rejected(self):
        acc = _account()
        with pytest.raises(ValueError, match="Date invalide"):
            portfolio_data.add_transaction(acc, "RI.PA", "buy", "02/01/2024", 10, 100.0)

    def test_non_positive_quantity_rejected(self):
        acc = _account()
        for qty in (0, -3):
            with pytest.raises(ValueError, match="quantité"):
                portfolio_data.add_transaction(acc, "RI.PA", "buy", "2024-01-02", qty, 100.0)

    def test_negative_price_rejected(self):
        acc = _account()
        with pytest.raises(ValueError, match="prix"):
            portfolio_data.add_transaction(acc, "RI.PA", "buy", "2024-01-02", 10, -1.0)

    def test_negative_fees_rejected(self):
        acc = _account()
        with pytest.raises(ValueError, match="frais"):
            portfolio_data.add_transaction(acc, "RI.PA", "buy", "2024-01-02", 10, 100.0, fees=-1)

    def test_unknown_side_rejected(self):
        acc = _account()
        with pytest.raises(ValueError, match="Sens invalide"):
            portfolio_data.add_transaction(acc, "RI.PA", "hold", "2024-01-02", 10, 100.0)

    def test_empty_ticker_rejected(self):
        acc = _account()
        with pytest.raises(ValueError, match="ticker"):
            portfolio_data.add_transaction(acc, "  ", "buy", "2024-01-02", 10, 100.0)

    def test_unknown_account_rejected(self):
        with pytest.raises(ValueError, match="Compte inconnu"):
            portfolio_data.add_transaction(999, "RI.PA", "buy", "2024-01-02", 10, 100.0)

    def test_update_and_delete(self):
        acc = _account()
        tx_id = portfolio_data.add_transaction(acc, "RI.PA", "buy", "2024-01-02", 10, 100.0)
        portfolio_data.update_transaction(tx_id, acc, "RI.PA", "buy", "2024-01-03", 12, 101.0)
        (tx,) = portfolio_data.list_transactions(acc)
        assert tx["quantity"] == 12 and tx["trade_date"] == "2024-01-03"
        portfolio_data.delete_transaction(tx_id)
        assert portfolio_data.list_transactions(acc) == []
        with pytest.raises(ValueError, match="Transaction inconnue"):
            portfolio_data.delete_transaction(tx_id)


class TestDividendValidation:
    """J0.2 — validation stricte des dividendes."""

    def test_valid_dividend_roundtrip(self):
        acc = _account()
        portfolio_data.add_dividend(acc, "ri.pa", "2024-06-15", 42.0)
        (div,) = portfolio_data.list_dividends(acc)
        assert div["ticker"] == "RI.PA"
        assert div["amount"] == 42.0
        assert div["status"] == "confirmed"
        assert div["source"] == "manual"

    def test_invalid_date_rejected(self):
        acc = _account()
        with pytest.raises(ValueError, match="Date invalide"):
            portfolio_data.add_dividend(acc, "RI.PA", "15/06/2024", 42.0)

    def test_negative_amount_rejected(self):
        acc = _account()
        with pytest.raises(ValueError, match="montant"):
            portfolio_data.add_dividend(acc, "RI.PA", "2024-06-15", -1.0)

    def test_unknown_status_rejected(self):
        acc = _account()
        with pytest.raises(ValueError, match="Statut invalide"):
            portfolio_data.add_dividend(acc, "RI.PA", "2024-06-15", 42.0, status="maybe")

    def test_unknown_account_rejected(self):
        with pytest.raises(ValueError, match="Compte inconnu"):
            portfolio_data.add_dividend(999, "RI.PA", "2024-06-15", 42.0)


class TestTags:
    """#17.6 — étiquettes / portefeuilles virtuels sur les transactions."""

    def test_tag_roundtrip_and_normalization(self):
        acc = _account()
        portfolio_data.add_transaction(
            acc, "RI.PA", "buy", "2024-01-02", 10, 100.0, tag="  Actions dividende  "
        )
        (tx,) = portfolio_data.list_transactions(acc)
        assert tx["tag"] == "Actions dividende"  # trim, casse conservée

    def test_empty_tag_is_none(self):
        acc = _account()
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2024-01-02", 10, 100.0, tag="   ")
        assert portfolio_data.list_transactions(acc)[0]["tag"] is None

    def test_tag_too_long_rejected(self):
        acc = _account()
        with pytest.raises(ValueError, match="Étiquette trop longue"):
            portfolio_data.add_transaction(
                acc,
                "RI.PA",
                "buy",
                "2024-01-02",
                10,
                100.0,
                tag="x" * (config.PORTFOLIO_TAG_MAX + 1),
            )

    def test_tag_control_chars_rejected(self):
        acc = _account()
        with pytest.raises(ValueError, match="caractères de contrôle"):
            portfolio_data.add_transaction(
                acc, "RI.PA", "buy", "2024-01-02", 10, 100.0, tag="div\nidende"
            )

    def test_list_tags_distinct_sorted(self):
        a = _account("PEA")
        b = _account("CTO")
        portfolio_data.add_transaction(a, "RI.PA", "buy", "2024-01-02", 10, 100.0, tag="Croissance")
        portfolio_data.add_transaction(a, "AI.PA", "buy", "2024-01-02", 10, 100.0, tag="dividende")
        portfolio_data.add_transaction(b, "OR.PA", "buy", "2024-01-02", 10, 100.0, tag="Croissance")
        portfolio_data.add_transaction(b, "MC.PA", "buy", "2024-01-02", 10, 100.0)
        assert portfolio_data.list_tags() == ["Croissance", "dividende"]

    def test_list_tags_scoped_by_account(self):
        a = _account("PEA")
        b = _account("CTO")
        portfolio_data.add_transaction(a, "RI.PA", "buy", "2024-01-02", 10, 100.0, tag="Div")
        portfolio_data.add_transaction(b, "OR.PA", "buy", "2024-01-02", 10, 100.0, tag="Croissance")
        assert portfolio_data.list_tags(a) == ["Div"]
        assert portfolio_data.list_tags(b) == ["Croissance"]
        assert portfolio_data.list_tags() == ["Croissance", "Div"]

    def test_filter_by_tag_and_account(self):
        a = _account("PEA")
        b = _account("CTO")
        portfolio_data.add_transaction(a, "RI.PA", "buy", "2024-01-02", 10, 100.0, tag="Div")
        portfolio_data.add_transaction(a, "AI.PA", "buy", "2024-01-02", 10, 100.0)
        portfolio_data.add_transaction(b, "OR.PA", "buy", "2024-01-02", 10, 100.0, tag="Div")
        assert len(portfolio_data.list_transactions(tag="Div")) == 2
        assert len(portfolio_data.list_transactions(a, "Div")) == 1
        assert portfolio_data.list_transactions(a, "Div")[0]["ticker"] == "RI.PA"
        # Filtre d'étiquette vide = pas de filtre.
        assert len(portfolio_data.list_transactions(tag="  ")) == 3

    def test_set_tag_bulk_and_clear(self):
        acc = _account()
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2024-01-02", 10, 100.0)
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2024-02-02", 10, 120.0)
        portfolio_data.add_transaction(acc, "AI.PA", "buy", "2024-01-02", 5, 150.0)

        updated = portfolio_data.set_tag(acc, "ri.pa", "Actions dividende")
        assert updated == 2
        tagged = [t for t in portfolio_data.list_transactions(acc) if t["tag"]]
        assert {t["ticker"] for t in tagged} == {"RI.PA"}
        assert len(tagged) == 2

        cleared = portfolio_data.set_tag(acc, "RI.PA", None)
        assert cleared == 2
        assert portfolio_data.list_tags() == []

    def test_set_tag_empty_ticker_rejected(self):
        acc = _account()
        with pytest.raises(ValueError, match="ticker"):
            portfolio_data.set_tag(acc, "  ", "Div")

    def test_update_transaction_changes_tag(self):
        acc = _account()
        tx_id = portfolio_data.add_transaction(
            acc, "RI.PA", "buy", "2024-01-02", 10, 100.0, tag="Avant"
        )
        portfolio_data.update_transaction(
            tx_id, acc, "RI.PA", "buy", "2024-01-02", 10, 100.0, tag="Après"
        )
        assert portfolio_data.list_transactions(acc)[0]["tag"] == "Après"


class TestBackupIntegration:
    """J0.3 — les 3 tables du portefeuille sont sauvegardées et restaurées."""

    def test_table_columns_cover_portfolio(self):
        for name in ("portfolio_accounts", "portfolio_transactions", "portfolio_dividends"):
            assert name in backup._TABLE_COLUMNS

    def test_every_table_declared_in_table_since(self):
        """Garde-fou : toute table de `_TABLE_COLUMNS` doit figurer dans `_TABLE_SINCE`."""
        declared = {n for names in backup._TABLE_SINCE.values() for n in names}
        assert set(backup._TABLE_COLUMNS) == declared

    def test_registry_guard_detects_missing_declaration(self, monkeypatch):
        """Un oubli dans `_TABLE_SINCE` doit échouer au chargement, pas à la restauration."""
        incomplete = {1: tuple(backup._TABLE_SINCE[1])}  # table portefeuille non déclarée
        monkeypatch.setattr(backup, "_TABLE_SINCE", incomplete)
        with pytest.raises(RuntimeError, match="absentes de _TABLE_SINCE"):
            backup._check_table_registry()

    def test_columns_match_database_schema(self):
        with cache.connect() as conn:
            for name in ("portfolio_accounts", "portfolio_transactions", "portfolio_dividends"):
                actual = {r[1] for r in conn.execute(f"PRAGMA table_info({name})")}
                assert set(backup._TABLE_COLUMNS[name]) == actual

    def test_parent_before_children(self):
        names = list(backup._TABLE_COLUMNS)
        assert names.index("portfolio_accounts") < names.index("portfolio_transactions")
        assert names.index("portfolio_accounts") < names.index("portfolio_dividends")

    def test_export_purge_restore_preserves_rows(self):
        acc = _account("PEA")
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2024-01-02", 10, 100.0)
        portfolio_data.add_dividend(acc, "RI.PA", "2024-06-15", 42.0)

        archive = backup.build_archive()
        assert len(archive["tables"]["portfolio_accounts"]) == 1
        assert len(archive["tables"]["portfolio_transactions"]) == 1
        assert len(archive["tables"]["portfolio_dividends"]) == 1

        with cache.connect() as conn:
            for name in ("portfolio_transactions", "portfolio_dividends", "portfolio_accounts"):
                conn.execute(f"DELETE FROM {name}")
            conn.commit()
        assert portfolio_data.list_accounts() == []

        backup.restore_archive(archive["tables"])
        rows = portfolio_data.list_accounts()
        assert len(rows) == 1 and rows[0]["name"] == "PEA"
        assert len(portfolio_data.list_transactions()) == 1
        assert len(portfolio_data.list_dividends()) == 1

    def test_tag_column_saved_and_restored(self):
        acc = _account()
        portfolio_data.add_transaction(
            acc, "RI.PA", "buy", "2024-01-02", 10, 100.0, tag="Actions dividende"
        )
        archive = backup.build_archive()
        assert archive["tables"]["portfolio_transactions"][0]["tag"] == "Actions dividende"

        with cache.connect() as conn:
            conn.execute("DELETE FROM portfolio_transactions")
            conn.commit()
        backup.restore_archive(archive["tables"])
        assert portfolio_data.list_transactions()[0]["tag"] == "Actions dividende"

    def test_v6_archive_without_tag_column_accepted(self):
        # Une archive exportée AVANT l'ajout de `tag` (schéma <= 6) n'a pas la
        # colonne : la restauration la tolère (remplie par None, nullable), au
        # lieu de rejeter « colonne manquante ».
        acc = _account()
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2024-01-02", 10, 100.0)
        archive = backup.build_archive()
        archive["schema_version"] = 6
        for row in archive["tables"]["portfolio_transactions"]:
            del row["tag"]
        tables = backup.validate_archive(archive)
        assert tables["portfolio_transactions"][0]["tag"] is None

    def test_v6_archive_without_portfolio_tables_still_accepted(self):
        # Garde-fou : la tolérance de colonne ne doit pas régresser la tolérance
        # de table (archive v1 sans tables portefeuille).
        archive = backup.build_archive()
        archive["schema_version"] = 1
        for name in ("portfolio_accounts", "portfolio_transactions", "portfolio_dividends"):
            del archive["tables"][name]
        tables = backup.validate_archive(archive)
        assert tables["portfolio_transactions"] == []

    def test_orphan_transaction_rejected(self):
        acc = _account()
        portfolio_data.add_transaction(acc, "RI.PA", "buy", "2024-01-02", 10, 100.0)
        archive = backup.build_archive()
        archive["tables"]["portfolio_accounts"] = []
        with pytest.raises(ValueError, match="compte .* inexistant"):
            backup.validate_archive(archive)

    def test_v1_archive_without_portfolio_tables_accepted(self):
        # Compatibilité ascendante : une archive exportée en schéma v1 (5 tables
        # historiques, sans les tables portefeuille) reste restaurable — les
        # tables absentes sont traitées comme vides, pas rejetées.
        _account("PEA")
        archive = backup.build_archive()
        archive["schema_version"] = 1
        for name in ("portfolio_accounts", "portfolio_transactions", "portfolio_dividends"):
            del archive["tables"][name]
        tables = backup.validate_archive(archive)
        for name in ("portfolio_accounts", "portfolio_transactions", "portfolio_dividends"):
            assert tables[name] == []

    def test_v2_archive_missing_portfolio_table_rejected(self):
        # Une archive déclarée v2 DOIT porter les tables portefeuille : leur
        # absence est une vraie incohérence (et non un schéma plus ancien).
        _account("PEA")
        archive = backup.build_archive()
        del archive["tables"]["portfolio_accounts"]
        with pytest.raises(ValueError, match="Archive incomplète"):
            backup.validate_archive(archive)
