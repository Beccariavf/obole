"""Tests purs du mapping des comptes (sans réseau)."""

from __future__ import annotations

import pandas as pd
import pytest

from obole.data import fundamentals as f
from obole.models import CompanyKind


def _df(rows: dict, years=(2025, 2024, 2023)) -> pd.DataFrame:
    cols = [pd.Timestamp(f"{y}-12-31") for y in years]
    return pd.DataFrame(
        {c: [rows[k][i] for k in rows] for i, c in enumerate(cols)}, index=list(rows.keys())
    )


def test_industrial_schema_builds_expected_metrics():
    fin = _df(
        {"Total Revenue": [100, 90, 80], "Operating Income": [20, 18, 16], "Net Income": [10, 9, 8]}
    )
    bs = _df({"Stockholders Equity": [50, 48, 45], "Total Assets": [120, 115, 110]})
    cf = pd.DataFrame()
    table = f.build_table(fin, bs, cf, CompanyKind.INDUSTRIAL)
    assert "Chiffre d'affaires" in table.index
    assert "Marge opérationnelle" in table.index
    assert "ROE" in table.index
    # marge op 2025 = 20/100 = 20 %
    assert table.loc["Marge opérationnelle"][2025] == 20.0


def test_financial_schema_uses_bank_metrics():
    fin = _df({"Total Revenue": [50, 48, 45], "Net Income": [10, 9, 8]})
    bs = _df({"Stockholders Equity": [100, 95, 90], "Total Assets": [2000, 1900, 1800]})
    table = f.build_table(fin, bs, pd.DataFrame(), CompanyKind.FINANCIAL)
    assert "Total de l'actif" in table.index
    assert "ROA" in table.index
    assert "Chiffre d'affaires" not in table.index  # pas de CA pour une banque


def test_quality_inputs_counts_declines():
    fin = _df(
        {"Total Revenue": [80, 100, 90], "Net Income": [8, 10, 9]}
    )  # 2025<2024 = 1 baisse récente
    bs = _df({"Stockholders Equity": [50, 48, 45], "Total Assets": [120, 115, 110]})
    table = f.build_table(fin, bs, pd.DataFrame(), CompanyKind.INDUSTRIAL)
    qi = f.quality_inputs(table, CompanyKind.INDUSTRIAL)
    assert qi["roe_last"] is not None
    assert qi["ca_decline_years"] >= 1


def test_empty_inputs_give_empty_table():
    table = f.build_table(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), CompanyKind.INDUSTRIAL)
    assert table.empty
    assert f.quality_inputs(table, CompanyKind.INDUSTRIAL)["roe_mean"] is None


def test_extended_ratios_industrial():
    fin = _df(
        {
            "Total Revenue": [100, 90, 80],
            "Gross Profit": [60, 54, 48],
            "Operating Income": [20, 18, 16],
            "EBIT": [21, 19, 17],
            "Interest Expense": [3, 3, 3],
            "Net Income": [10, 9, 8],
            "Diluted EPS": [2.0, 1.8, 1.6],
        }
    )
    bs = _df(
        {
            "Stockholders Equity": [50, 48, 45],
            "Total Assets": [120, 115, 110],
            "Net Debt": [25, 30, 35],
            "Invested Capital": [70, 68, 65],
            "Working Capital": [10, 12, 14],
        }
    )
    cf = _df({"Free Cash Flow": [12, 10, 9], "Operating Cash Flow": [15, 13, 11]})
    t = f.build_table(fin, bs, cf, CompanyKind.INDUSTRIAL)
    assert t.loc["Marge brute"][2025] == 60.0  # 60/100
    assert t.loc["ROA"][2025] == pytest.approx(10 / 120 * 100)  # ~8.33 %
    assert t.loc["ROCE"][2025] == pytest.approx(21 / 70 * 100)  # EBIT / capital investi
    assert t.loc["Cash conversion"][2025] == 120.0  # FCF/RN = 12/10
    assert t.loc["Gearing"][2025] == 50.0  # 25/50
    assert t.loc["BNPA dilué"][2025] == 2.0
    assert "Agilité" not in t.index  # pas de CAPEX dans ce test


def test_agilite_uses_absolute_capex():
    """Agilité = FCF / |CAPEX| : un CAPEX négatif (sortie de cash) ne doit pas
    inverser le signe du ratio (garde-fou : 12 / |−8| = 150 %, jamais −150 %)."""
    fin = _df({"Total Revenue": [100, 90, 80], "Net Income": [10, 9, 8]})
    bs = _df({"Stockholders Equity": [50, 48, 45]})
    cf = _df({"Free Cash Flow": [12, 10, 9], "Capital Expenditure": [-8, -7, -6]})
    t = f.build_table(fin, bs, cf, CompanyKind.INDUSTRIAL)
    assert t.loc["Agilité"][2025] == pytest.approx(150.0)  # 12 / |−8|


def test_extended_metrics_roic_liquidity_cash_debt_shares():
    """Métriques étendues du Quantitatif : ROIC, liquidité, trésorerie, dette, actions."""
    fin = _df(
        {
            "Total Revenue": [100, 90, 80],
            "Operating Income": [20, 18, 16],
            "Net Income": [10, 9, 8],
            "Tax Rate For Calcs": [0.25, 0.25, 0.25],
        }
    )
    bs = _df(
        {
            "Stockholders Equity": [50, 48, 45],
            "Total Assets": [120, 115, 110],
            "Invested Capital": [80, 78, 76],
            "Current Assets": [60, 58, 55],
            "Current Liabilities": [30, 29, 28],
            "Cash And Cash Equivalents": [15, 14, 13],
            "Total Debt": [40, 42, 44],
            "Ordinary Shares Number": [1000, 1020, 1040],
        }
    )
    cf = _df({"Free Cash Flow": [12, 10, 9], "Capital Expenditure": [-8, -7, -6]})
    t = f.build_table(fin, bs, cf, CompanyKind.INDUSTRIAL)
    assert t.loc["ROIC"][2025] == pytest.approx(20 * 0.75 / 80 * 100)  # 18.75 %
    assert t.loc["Liquidité"][2025] == pytest.approx(2.0)  # 60/30
    assert t.loc["Trésorerie"][2025] == 15.0
    assert t.loc["Dette brute"][2025] == 40.0
    assert t.loc["Actions en circulation"][2025] == 1000.0


def test_roic_absent_without_invested_capital():
    """Sans capital investi, ROIC est absent (jamais de division par zéro)."""
    fin = _df({"Operating Income": [20, 18, 16], "Net Income": [10, 9, 8]})
    bs = _df({"Stockholders Equity": [50, 48, 45], "Total Assets": [120, 115, 110]})
    t = f.build_table(fin, bs, pd.DataFrame(), CompanyKind.INDUSTRIAL)
    assert "ROIC" not in t.index
    assert "Liquidité" not in t.index  # pas de current assets/liabilities


def test_interest_coverage_metric():
    """Couverture des intérêts = Résultat opérationnel / |Intérêts| (ratio tracé)."""
    fin = _df(
        {
            "Total Revenue": [100, 90, 80],
            "Operating Income": [20, 18, 16],
            "Interest Expense": [-2, -3, -4],
            "Net Income": [10, 9, 8],
        }
    )
    bs = _df({"Stockholders Equity": [50, 48, 45]})
    t = f.build_table(fin, bs, pd.DataFrame(), CompanyKind.INDUSTRIAL)
    assert t.loc["Couverture des intérêts"][2025] == pytest.approx(10.0)  # 20 / |−2|


def test_interest_coverage_absent_without_interest():
    """Sans poste d'intérêts, la couverture est absente (pas de crash)."""
    fin = _df({"Operating Income": [20, 18, 16], "Net Income": [10, 9, 8]})
    bs = _df({"Stockholders Equity": [50, 48, 45]})
    t = f.build_table(fin, bs, pd.DataFrame(), CompanyKind.INDUSTRIAL)
    assert "Couverture des intérêts" not in t.index


def test_ratio_absent_when_poste_missing():
    # Pas de Gross Profit ni Invested Capital -> marge brute et ROCE absents, pas de crash.
    fin = _df({"Total Revenue": [100, 90, 80], "Net Income": [10, 9, 8]})
    bs = _df({"Stockholders Equity": [50, 48, 45], "Total Assets": [120, 115, 110]})
    t = f.build_table(fin, bs, pd.DataFrame(), CompanyKind.INDUSTRIAL)
    assert "Marge brute" not in t.index
    assert "ROCE" not in t.index
    assert "ROE" in t.index  # celui-là reste calculable


def test_cagr_and_growth_inputs():
    # CA : 80 -> 100 sur 2 ans (colonnes : 2025=100, 2024=90, 2023=80).
    fin = _df({"Total Revenue": [100, 90, 80], "Net Income": [10, 9, 8]})
    bs = _df({"Stockholders Equity": [50, 48, 45], "Total Assets": [120, 115, 110]})
    t = f.build_table(fin, bs, pd.DataFrame(), CompanyKind.INDUSTRIAL)
    expected = ((100 / 80) ** (1 / 2) - 1) * 100
    assert f.cagr(t.loc["Chiffre d'affaires"], 2) == pytest.approx(expected)
    assert f.cagr(t.loc["Chiffre d'affaires"], 5) is None  # pas assez d'années
    g = f.growth_inputs(t, CompanyKind.INDUSTRIAL)
    assert g["cagr_revenue_3y"] is None  # 3 ans -> besoin de 4 points, on n'en a que 3


def test_cagr_none_on_negative_base():
    # Point de départ (le plus ancien) négatif -> CAGR sans signification -> None.
    s = pd.Series([10.0, 4.0, -3.0], index=[2025, 2024, 2023])
    assert f.cagr(s, 2) is None


def test_merge_manual_updates_existing_metrics():
    """Les données manuelles remplacent les métriques existantes."""
    fin = _df({"Total Revenue": [100], "Net Income": [10]}, years=(2025,))
    bs = _df({"Stockholders Equity": [50]}, years=(2025,))
    table = f.build_table(fin, bs, pd.DataFrame(), CompanyKind.INDUSTRIAL)

    manual = {2025: {"Chiffre d'affaires": 120.0, "Bénéfice net": 12.0}}
    merged, enriched = f.merge_manual(table, manual, CompanyKind.INDUSTRIAL)

    assert merged.at["Chiffre d'affaires", 2025] == 120.0
    assert merged.at["Bénéfice net", 2025] == 12.0
    assert "Chiffre d'affaires" in enriched
    assert "Bénéfice net" in enriched


def test_merge_manual_adds_new_metric_rows():
    """Les métriques manuelles inconnues du tableau sont ajoutées comme nouvelles lignes."""
    fin = _df({"Total Revenue": [100]}, years=(2025,))
    bs = _df({"Stockholders Equity": [50]}, years=(2025,))
    table = f.build_table(fin, bs, pd.DataFrame(), CompanyKind.INDUSTRIAL)

    manual = {2025: {"EBITDA": 25.0}}
    merged, enriched = f.merge_manual(table, manual, CompanyKind.INDUSTRIAL)

    assert "EBITDA" in merged.index
    assert merged.at["EBITDA", 2025] == 25.0
    assert "EBITDA" in enriched


def test_merge_manual_derived_metrics_recomputed():
    """Les métriques dérivées sont recalculées après fusion manuelle."""
    fin = _df({"Total Revenue": [100], "Net Income": [10]}, years=(2025,))
    bs = _df({"Stockholders Equity": [50]}, years=(2025,))
    table = f.build_table(fin, bs, pd.DataFrame(), CompanyKind.INDUSTRIAL)
    assert "Marge nette" in table.index

    manual = {2025: {"Chiffre d'affaires": 200.0, "Bénéfice net": 30.0}}
    merged, enriched = f.merge_manual(table, manual, CompanyKind.INDUSTRIAL)

    assert merged.at["Marge nette", 2025] == 15.0  # 30/200 * 100
    assert "Marge nette" in enriched


def test_merge_manual_adds_new_years():
    """Les données manuelles peuvent ajouter des années absentes."""
    fin = _df({"Total Revenue": [100], "Net Income": [10]}, years=(2025,))
    bs = _df({"Stockholders Equity": [50]}, years=(2025,))
    table = f.build_table(fin, bs, pd.DataFrame(), CompanyKind.INDUSTRIAL)

    manual = {2025: {"Chiffre d'affaires": 110.0}, 2020: {"Chiffre d'affaires": 80.0}}
    merged, _ = f.merge_manual(table, manual, CompanyKind.INDUSTRIAL)

    assert 2020 in merged.columns
    assert merged.at["Chiffre d'affaires", 2020] == 80.0


def test_merge_manual_empty_returns_unchanged():
    """Données manuelles vides → table inchangée + set vide."""
    fin = _df({"Total Revenue": [100]}, years=(2025,))
    bs = _df({"Stockholders Equity": [50]}, years=(2025,))
    table = f.build_table(fin, bs, pd.DataFrame(), CompanyKind.INDUSTRIAL)

    merged, enriched = f.merge_manual(table, {}, CompanyKind.INDUSTRIAL)

    assert merged is table  # pas de copie
    assert enriched == set()


def test_merge_manual_recomputes_all_derivable_ratios():
    """Le recalcul couvre TOUS les dérivés dérivables des postes source.

    Marge opérationnelle, marge nette, ROE, Cash conversion, Dette nette/EBITDA,
    Gearing, Agilité et BFR/CA doivent être recalculés après saisie manuelle —
    pas seulement les 6 historiques.
    """
    fin = _df(
        {
            "Total Revenue": [100],
            "Operating Income": [10],
            "Net Income": [10],
            "EBITDA": [60],
        },
        years=(2025,),
    )
    bs = _df({"Stockholders Equity": [50], "Net Debt": [40]}, years=(2025,))
    cf = _df(
        {"Free Cash Flow": [12], "Capital Expenditure": [-8]},
        years=(2025,),
    )
    table = f.build_table(fin, bs, cf, CompanyKind.INDUSTRIAL)

    manual = {
        2025: {
            "Chiffre d'affaires": 200.0,
            "Résultat opérationnel": 40.0,
            "Bénéfice net": 30.0,
            "EBITDA": 80.0,
            "Free Cash Flow": 24.0,
            "CAPEX": 12.0,
            "Capitaux propres": 100.0,
            "Dette nette": 50.0,
            "BFR (working capital)": 20.0,
        }
    }
    merged, enriched = f.merge_manual(table, manual, CompanyKind.INDUSTRIAL)

    assert merged.at["Marge opérationnelle", 2025] == pytest.approx(20.0)  # 40/200
    assert merged.at["Marge nette", 2025] == pytest.approx(15.0)  # 30/200
    assert merged.at["ROE", 2025] == pytest.approx(30.0)  # 30/100
    assert merged.at["Cash conversion", 2025] == pytest.approx(80.0)  # 24/30
    assert merged.at["Dette nette / EBITDA", 2025] == pytest.approx(0.625)  # 50/80
    assert merged.at["Gearing", 2025] == pytest.approx(50.0)  # 50/100
    assert merged.at["Agilité", 2025] == pytest.approx(200.0)  # 24/12
    assert merged.at["BFR / CA", 2025] == pytest.approx(10.0)  # 20/200
    for metric in (
        "Marge opérationnelle",
        "Marge nette",
        "ROE",
        "Cash conversion",
        "Dette nette / EBITDA",
        "Gearing",
        "Agilité",
        "BFR / CA",
    ):
        assert metric in enriched


def test_merge_manual_leaves_internal_derived_untouched():
    """Un dérivé reposant sur un poste interne non saisissable est préservé.

    ROA/ROCE/ROIC/Liquidité/Capitaux propres÷bilan/couverture dépendent de postes
    absents du CSV (total actif, capital investi…) : une saisie manuelle d'un autre
    poste ne doit PAS les écraser (jamais de None propagé).
    """
    fin = _df(
        {"Total Revenue": [100], "Operating Income": [20], "Net Income": [10]},
        years=(2025,),
    )
    bs = _df(
        {"Stockholders Equity": [50], "Total Assets": [200], "Invested Capital": [80]},
        years=(2025,),
    )
    table = f.build_table(fin, bs, pd.DataFrame(), CompanyKind.INDUSTRIAL)
    roa_before = table.at["ROA", 2025]

    manual = {2025: {"Chiffre d'affaires": 999.0}}
    merged, _ = f.merge_manual(table, manual, CompanyKind.INDUSTRIAL)

    assert merged.at["ROA", 2025] == roa_before  # inchangé (total actif non saisi)


def test_shared_derivation_build_and_recompute_agree():
    """Source unique des formules : `build_table` et le recalcul concordent.

    On construit un tableau via `build_table`, puis on rejoue EXACTEMENT les mêmes
    postes source via une saisie manuelle : les dérivés dérivables doivent être
    identiques (preuve qu'une même fonction `_derive` sert les deux chemins).
    """
    fin = _df(
        {"Total Revenue": [100], "Operating Income": [20], "Net Income": [10]},
        years=(2025,),
    )
    bs = _df({"Stockholders Equity": [50], "Net Debt": [40]}, years=(2025,))
    cf = _df({"Free Cash Flow": [12], "Capital Expenditure": [-8]}, years=(2025,))
    table = f.build_table(fin, bs, cf, CompanyKind.INDUSTRIAL)

    manual = {
        2025: {
            "Chiffre d'affaires": float(table.at["Chiffre d'affaires", 2025]),
            "Résultat opérationnel": float(table.at["Résultat opérationnel", 2025]),
            "Bénéfice net": float(table.at["Bénéfice net", 2025]),
            "Free Cash Flow": float(table.at["Free Cash Flow", 2025]),
            "CAPEX": float(table.at["CAPEX", 2025]),
            "Capitaux propres": float(table.at["Capitaux propres", 2025]),
            "Dette nette": float(table.at["Dette nette", 2025]),
        }
    }
    merged, _ = f.merge_manual(table, manual, CompanyKind.INDUSTRIAL)

    for metric in (
        "Marge opérationnelle",
        "Marge nette",
        "ROE",
        "Cash conversion",
        "Gearing",
        "Agilité",
    ):
        assert merged.at[metric, 2025] == pytest.approx(table.at[metric, 2025])


def test_recompute_derived_financial_kind():
    """Pour une financière, le recalcul dérive ROE/ROA depuis les postes source."""
    fin = _df({"Net Income": [10]}, years=(2025,))
    bs = _df({"Total Assets": [200], "Stockholders Equity": [100]}, years=(2025,))
    table = f.build_table(fin, bs, pd.DataFrame(), CompanyKind.FINANCIAL)

    merged, enriched = f.merge_manual(
        table, {2025: {"Bénéfice net": 20.0, "Actif net": 100.0}}, CompanyKind.FINANCIAL
    )

    assert merged.at["ROE", 2025] == pytest.approx(20.0)  # 20/100
    assert "ROE" in enriched


def test_recompute_derived_financial_roa_alias():
    """ROA est recalculé quand l'utilisateur édite « Total de l'actif » (financière).

    ROA lit le poste interne `_total_assets` : l'alias vers la ligne source
    « Total de l'actif » est indispensable, sinon ROA reste figé sur la valeur
    yfinance malgré la saisie manuelle (bug de round-trip du template bancaire).
    """
    fin = _df({"Net Income": [10]}, years=(2025,))
    bs = _df({"Total Assets": [200], "Stockholders Equity": [100]}, years=(2025,))
    table = f.build_table(fin, bs, pd.DataFrame(), CompanyKind.FINANCIAL)
    assert table.at["ROA", 2025] == pytest.approx(5.0)  # 10/200

    merged, enriched = f.merge_manual(
        table, {2025: {"Total de l'actif": 400.0, "Bénéfice net": 40.0}}, CompanyKind.FINANCIAL
    )

    assert merged.at["ROA", 2025] == pytest.approx(10.0)  # 40/400
    assert "ROA" in enriched


def test_shareholder_payout_buybacks_available_on_any_year():
    """Rachats présents sur un exercice ANCIEN seulement -> disponibles.

    Cas Amundi : `Repurchase Of Capital Stock` renseigné en 2021/2022 puis NaN.
    Le test sur la seule colonne courante masquait les rachats existants.
    """
    cf = _df(
        {
            "Cash Dividends Paid": [-100, -100, -100],
            "Repurchase Of Capital Stock": [float("nan"), float("nan"), -50],
        },
        years=(2025, 2024, 2023),
    )
    out = f.shareholder_payout(cf, net_income=1000.0)
    assert out["buybacks_available"] is True


def test_shareholder_payout_no_buybacks_available():
    cf = _df({"Cash Dividends Paid": [-100, -100, -100]}, years=(2025, 2024, 2023))
    out = f.shareholder_payout(cf, net_income=1000.0)
    assert out["buybacks_available"] is False
    assert out["payout_pct"] == pytest.approx(10.0)
