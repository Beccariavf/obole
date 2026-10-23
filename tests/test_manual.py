"""Tests pour les données manuelles : cache CRUD, CSV, merge.

Les tests qui nécessitent pandas sont marqués "manual" (pandas peut être
lent/indisponible dans certains environnements CI).
"""

from __future__ import annotations

import pytest

from obole import config
from obole.data import cache, manual


@pytest.fixture(autouse=True)
def _clean_test_ticker():
    """Isolation : purge le ticker partagé « TEST » avant/après chaque test.

    Ces tests utilisent tous le même ticker « TEST » sur la base SQLite réelle ;
    sans purge, ils se polluent entre eux (échecs dépendant de l'ordre).
    """
    cache.delete_manual("TEST")
    yield
    cache.delete_manual("TEST")


def test_cache_crud():
    """CRUD de base sur les entrées manuelles dans le cache."""
    entries = [
        {"year": 2020, "metric": "Chiffre d'affaires", "value": 1000.0},
        {"year": 2020, "metric": "Bénéfice net", "value": 100.0},
        {"year": 2021, "metric": "Chiffre d'affaires", "value": 1200.0},
    ]
    cache.put_manual("TEST", entries)

    results = cache.get_manual("TEST")
    assert len(results) == 3
    assert {"year": 2020, "metric": "Chiffre d'affaires", "value": 1000.0} in results
    assert {"year": 2021, "metric": "Chiffre d'affaires", "value": 1200.0} in results


def test_cache_crud_upsert():
    """Mettre à jour (écraser) une entrée existante."""
    cache.put_manual("TEST", [{"year": 2020, "metric": "CA", "value": 100.0}])
    cache.put_manual("TEST", [{"year": 2020, "metric": "CA", "value": 999.0}])
    results = cache.get_manual("TEST")
    assert len(results) == 1
    assert results[0]["value"] == 999.0


def test_cache_delete_year():
    """Supprimer une année spécifique."""
    cache.put_manual(
        "TEST",
        [
            {"year": 2020, "metric": "CA", "value": 100.0},
            {"year": 2021, "metric": "CA", "value": 200.0},
        ],
    )
    cache.delete_manual_year("TEST", 2020)
    results = cache.get_manual("TEST")
    assert len(results) == 1
    assert results[0]["year"] == 2021


def test_cache_delete_all():
    """Supprimer toutes les entrées d'un ticker."""
    cache.put_manual(
        "TEST",
        [
            {"year": 2020, "metric": "CA", "value": 100.0},
            {"year": 2021, "metric": "CA", "value": 200.0},
        ],
    )
    cache.delete_manual("TEST")
    assert cache.get_manual("TEST") == []


def test_cache_delete_nonexistent_year():
    """Supprimer une année inexistante ne plante pas."""
    cache.put_manual("TEST", [{"year": 2020, "metric": "CA", "value": 100.0}])
    cache.delete_manual_year("TEST", 1999)
    assert len(cache.get_manual("TEST")) == 1


def test_cache_empty_ticker():
    """Un ticker sans données renvoie une liste vide."""
    assert cache.get_manual("INEXISTANT") == []


def test_manual_get_manual_dict():
    """get_manual_dict structure en {année: {métrique: valeur}}."""
    cache.put_manual(
        "DICT",
        [
            {"year": 2020, "metric": "CA", "value": 100.0},
            {"year": 2020, "metric": "BN", "value": 10.0},
            {"year": 2021, "metric": "CA", "value": 120.0},
        ],
    )
    d = manual.get_manual_dict("DICT")
    assert d == {2020: {"CA": 100.0, "BN": 10.0}, 2021: {"CA": 120.0}}


def test_upsert_manual():
    """upsert_manual ajoute et écrase des entrées."""
    manual.upsert_manual("TICK", [{"year": 2020, "metric": "CA", "value": 100.0}])
    manual.upsert_manual("TICK", [{"year": 2020, "metric": "CA", "value": 200.0}])
    d = manual.get_manual_dict("TICK")
    assert d[2020]["CA"] == 200.0


def test_delete_manual_year():
    """delete_manual_year supprime une année."""
    manual.upsert_manual(
        "TICK",
        [
            {"year": 2020, "metric": "CA", "value": 100.0},
            {"year": 2021, "metric": "CA", "value": 200.0},
        ],
    )
    manual.delete_manual_year("TICK", 2020)
    d = manual.get_manual_dict("TICK")
    assert 2020 not in d
    assert 2021 in d


def test_delete_manual():
    """delete_manual supprime toutes les entrées d'un ticker."""
    manual.upsert_manual("TICK", [{"year": 2020, "metric": "CA", "value": 100.0}])
    manual.delete_manual("TICK")
    assert manual.get_manual_dict("TICK") == {}


def test_import_csv_basic():
    """Import CSV basique valide."""
    csv = """year,Chiffre d'affaires,Résultat opérationnel,Bénéfice net,EBITDA,Free Cash Flow,Capitaux propres,Dette nette
2015,1000,200,100,300,80,5000,1500
2016,1100,220,110,330,88,5500,1600"""
    report = manual.import_csv("TEST", csv)
    assert report.accepted == 14  # 2 années × 7 métriques
    assert {"year": 2015, "metric": "Chiffre d'affaires", "value": 1000.0} in report.entries
    assert {"year": 2016, "metric": "Dette nette", "value": 1600.0} in report.entries


def test_import_csv_empty_cells():
    """Les cellules vides sont ignorées."""
    csv = """year,Chiffre d'affaires,Bénéfice net
2015,1000,"""
    report = manual.import_csv("TEST", csv)
    assert report.accepted == 1
    assert report.entries[0]["metric"] == "Chiffre d'affaires"


def test_import_csv_invalid_float():
    """Les cellules non numériques sont rejetées, avec leur raison."""
    csv = """year,Chiffre d'affaires
2015,pomme"""
    report = manual.import_csv("TEST", csv)
    assert report.accepted == 0
    assert report.rejected_total == 1
    assert report.rejected[0].reason == config.IMPORT_REJECT_UNPARSEABLE
    assert report.rejected[0].raw == "pomme"


def test_import_csv_bom():
    """Le BOM UTF-8 est correctement géré."""
    csv = "\ufeffyear,Chiffre d'affaires\n2015,1000"
    report = manual.import_csv("TEST", csv)
    assert report.accepted == 1
    assert report.entries[0]["value"] == 1000.0


def test_import_csv_only_some_metrics():
    """Seulement certaines métriques dans le CSV."""
    csv = """year,Chiffre d'affaires,Free Cash Flow
2015,1000,80"""
    report = manual.import_csv("TEST", csv)
    assert report.accepted == 2  # 2 métriques


def test_import_csv_extra_columns_ignored():
    """Les colonnes inconnues sont ignorées ET listées dans le rapport."""
    csv = """year,Chiffre d'affaires,Commentaire
2015,1000,rien"""
    report = manual.import_csv("TEST", csv)
    assert report.accepted == 1
    assert report.unknown_columns == ["Commentaire"]


def test_import_csv_derived_columns_ignored():
    """Les colonnes DÉRIVÉES présentes dans un CSV ne sont pas réimportées.

    Un ratio calculé (ex. « Marge nette ») n'est jamais une donnée source : même
    présent dans le fichier, il est ignoré et **signalé** comme dérivé.
    """
    csv = """year,Chiffre d'affaires,Marge nette,ROE
2015,1000,15,12"""
    report = manual.import_csv("TEST", csv)
    assert report.accepted == 1
    assert report.entries[0]["metric"] == "Chiffre d'affaires"
    assert set(report.derived_columns) == {"Marge nette", "ROE"}


def test_import_csv_all_source_metrics_recognized():
    """Toutes les colonnes poste SOURCE de la taxonomie sont lues."""
    header = ",".join(["year", *manual.SOURCE_METRICS])
    values = ",".join(["2015", *["10" for _ in manual.SOURCE_METRICS]])
    report = manual.import_csv("TEST", f"{header}\n{values}")
    assert report.accepted == len(manual.SOURCE_METRICS)
    assert {e["metric"] for e in report.entries} == set(manual.SOURCE_METRICS)


def test_import_csv_financial_schema_recognized():
    """Le template d'une financière (schéma bancaire) est reconnu à l'import.

    Les postes « Total de l'actif » / « Actif net » ne figurent que dans
    `config.FINANCIAL_METRICS` : l'import s'appuie sur l'UNION des schémas car le
    schéma d'une valeur n'est pas connu au moment du parsing.
    """
    csv = "year,Total de l'actif,Actif net,Bénéfice net\n2020,1000,500,50"
    report = manual.import_csv("FIN", csv)
    assert {e["metric"] for e in report.entries} == {
        "Total de l'actif",
        "Actif net",
        "Bénéfice net",
    }


def test_import_csv_header_case_insensitive():
    """Le rapprochement des colonnes tolère casse et espaces (miroir du front)."""
    csv = "year, chiffre d'affaires ,BÉNÉFICE NET\n2020,1000,100"
    report = manual.import_csv("TEST", csv)
    assert {e["metric"] for e in report.entries} == {"Chiffre d'affaires", "Bénéfice net"}


def test_import_csv_crlf_and_year_invalid():
    """Fins de ligne Windows gérées ; une année invalide est rejetée (`bad_year`)."""
    csv = "year,Chiffre d'affaires\r\n2015,1000\r\nn/a,999\r\n"
    report = manual.import_csv("TEST", csv)
    assert report.entries == [{"year": 2015, "metric": "Chiffre d'affaires", "value": 1000.0}]
    assert report.rejected_total == 1
    assert report.rejected[0].reason == config.IMPORT_REJECT_YEAR


def test_import_csv_semicolon_delimiter():
    """Un CSV Excel FR (point-virgule) est reconnu — le délimiteur est détecté.

    C'est le cas qui cassait : `csv.DictReader` avec la virgule figée renvoyait
    une colonne unique, donc zéro entrée, sans que l'utilisateur sache pourquoi.
    """
    csv = "year;Chiffre d'affaires;Bénéfice net\n2015;8500000000;1200000000"
    report = manual.import_csv("TEST", csv)
    assert report.delimiter == ";"
    assert {e["metric"] for e in report.entries} == {"Chiffre d'affaires", "Bénéfice net"}


def test_import_csv_tab_delimiter():
    """Un collage de tableau (tabulations) est reconnu."""
    csv = "year\tChiffre d'affaires\n2015\t1000"
    report = manual.import_csv("TEST", csv)
    assert report.delimiter == "\t"
    assert report.entries == [{"year": 2015, "metric": "Chiffre d'affaires", "value": 1000.0}]


def test_import_csv_number_formats():
    """Les formats numériques réels (FR/US, milliers, devise, négatif) sont normalisés."""
    cases = {
        "8 500 000": 8_500_000.0,  # espace ordinaire
        "8\u00a0500\u00a0000": 8_500_000.0,  # espace insécable (Excel FR)
        "8\u202f500\u202f000": 8_500_000.0,  # espace fine insécable
        "8'500'000": 8_500_000.0,  # apostrophe de milliers
        "1.234,56": 1234.56,  # décimal FR
        "1,234.56": 1234.56,  # décimal US
        "1,5": 1.5,  # virgule décimale seule
        "1,234": 1234.0,  # virgule = milliers seule
        "(1 234)": -1234.0,  # parenthèses comptables
        "€ 1 234": 1234.0,  # devise préfixée
    }
    for raw, expected in cases.items():
        report = manual.import_csv("TEST", f'year,Chiffre d\'affaires\n2015,"{raw}"')
        assert report.accepted == 1, raw
        assert report.entries[0]["value"] == expected, raw


def test_import_csv_override_counted():
    """Une valeur qui remplace une entrée existante incrémente `overridden`."""
    manual.upsert_manual("OVR", [{"year": 2020, "metric": "Chiffre d'affaires", "value": 1.0}])
    report = manual.import_csv("OVR", "year,Chiffre d'affaires\n2020,2000")
    assert report.overridden == 1
    assert report.accepted == 1


def test_import_csv_reject_list_is_bounded_but_total_is_exact():
    """Le total des rejets est exact, l'échantillon est borné (`IMPORT_MAX_REJECT_SAMPLES`)."""
    rows = "\n".join(f"2015,pomme{i}" for i in range(config.IMPORT_MAX_REJECT_SAMPLES + 10))
    report = manual.import_csv("TEST", f"year,Chiffre d'affaires\n{rows}")
    assert report.rejected_total == config.IMPORT_MAX_REJECT_SAMPLES + 10
    assert len(report.rejected) == config.IMPORT_MAX_REJECT_SAMPLES


def test_import_csv_report_round_trip_template():
    """Le template exporté se réimporte (les postes source survivent au round-trip)."""
    manual.upsert_manual(
        "RT", [{"year": 2015, "metric": "Chiffre d'affaires", "value": 8_500_000_000.0}]
    )
    csv_out = manual.export_csv("RT", [2015], metrics=manual.SOURCE_METRICS)
    report = manual.import_csv("RT", csv_out)
    assert report.entries == [
        {"year": 2015, "metric": "Chiffre d'affaires", "value": 8_500_000_000.0}
    ]
    assert report.overridden == 1


def test_export_csv_empty():
    """Export sans données renvoie une chaîne vide."""
    assert manual.export_csv("TEST") == ""


def test_export_csv_with_years():
    """Export avec années yfinance génère un CSV avec header + années."""
    cache.put_manual(
        "EXPORT",
        [
            {"year": 2020, "metric": "Chiffre d'affaires", "value": 900.0},
        ],
    )
    csv = manual.export_csv("EXPORT", yfinance_years=[2021, 2022])
    assert csv.startswith("year,")
    assert "2020" in csv
    assert "2021" in csv
    assert "2022" in csv


def test_export_csv_manual_values_present():
    """Les valeurs manuelles figurent dans le CSV d'export."""
    cache.put_manual(
        "EXPORT",
        [
            {"year": 2020, "metric": "Chiffre d'affaires", "value": 900.0},
        ],
    )
    csv = manual.export_csv("EXPORT")
    assert "900.0" in csv


def test_export_csv_header_covers_taxonomy():
    """L'en-tête contient toutes les métriques de la taxonomie (source + dérivé)."""
    csv = manual.export_csv("EXPORT", yfinance_years=[2020])
    header = csv.splitlines()[0].split(",")
    assert header[0] == "year"
    for metric in manual.SOURCE_METRICS + manual.DERIVED_METRICS:
        assert metric in header


def test_export_csv_metrics_subset():
    """Le paramètre `metrics` restreint les colonnes exportées."""
    csv = manual.export_csv("EXPORT", yfinance_years=[2020], metrics=["Chiffre d'affaires"])
    header = csv.splitlines()[0].split(",")
    assert header == ["year", "Chiffre d'affaires"]


def test_taxonomy_defines_source_and_derived():
    """La taxonomie sépare postes source et ratios dérivés (source unique)."""
    assert "Chiffre d'affaires" in manual.SOURCE_METRICS
    assert "Dette nette" in manual.SOURCE_METRICS
    assert "Marge nette" in manual.DERIVED_METRICS
    assert "ROE" in manual.DERIVED_METRICS
    # Aucun recouvrement : un dérivé n'est jamais listé comme source.
    assert not set(manual.SOURCE_METRICS) & set(manual.DERIVED_METRICS)
