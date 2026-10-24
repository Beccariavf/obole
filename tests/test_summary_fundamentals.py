"""Tests purs de la synthèse fondamentale (engine/summary_fundamentals) — sans réseau.

Couvre le cas nominal, les bornes (dénominateur nul/négatif, historique court) et
l'exclusion des scores de santé pour une entreprise financière.
"""

from __future__ import annotations

import pandas as pd
import pytest

from obole import config
from obole.engine import summary_fundamentals as sf
from obole.models import CompanyKind, Fundamentals, Identity


def _table(rows: dict[str, list], years=(2025, 2024, 2023, 2022, 2021)) -> pd.DataFrame:
    """Tableau de comptes : lignes = métriques, colonnes = années (récent d'abord)."""
    return pd.DataFrame(rows, index=list(years)).T


def _series(values: dict[int, float]) -> pd.Series:
    return pd.Series({pd.Timestamp(f"{y}-12-31"): v for y, v in values.items()})


def _fundamentals(table: pd.DataFrame, **kwargs) -> Fundamentals:
    return Fundamentals(
        table=table,
        kind=kwargs.pop("kind", CompanyKind.INDUSTRIAL),
        available_years=table.shape[1],
        fetched_at=pd.Timestamp("today").date(),
        **kwargs,
    )


def _identity(**kwargs) -> Identity:
    base = {"ticker": "FAKE", "last_price": 100.0, "kind": CompanyKind.INDUSTRIAL}
    base.update(kwargs)
    return Identity(**base)


def _card(cards, card_id):
    return next(c for c in cards if c.id == card_id)


def _row(cards, card_id, key):
    return next(r for r in _card(cards, card_id).rows if r.key == key)


class TestGrowth:
    def test_one_year_is_simple_variation(self):
        assert sf._growth({2025: 110.0, 2024: 100.0}, 1) == pytest.approx(10.0)

    def test_multi_year_is_cagr(self):
        # 100 -> 121 sur 2 ans : (121/100)^(1/2) - 1 = 10 %.
        assert sf._growth({2025: 121.0, 2024: 110.0, 2023: 100.0}, 2) == pytest.approx(10.0)

    def test_horizon_not_covered_returns_none(self):
        # 5 ans demandés, 3 points seulement -> pas d'extrapolation.
        assert sf._growth({2025: 1.0, 2024: 1.0, 2023: 1.0}, 5) is None

    def test_negative_base_returns_none(self):
        assert (
            sf._growth(
                {2025: 120.0, 2024: 110.0, 2023: 100.0, 2022: 90.0, 2021: 80.0, 2020: -100.0}, 5
            )
            is None
        )

    def test_zero_denominator_returns_none(self):
        assert sf._growth({2025: 100.0, 2024: 0.0}, 1) is None


class TestAltmanPiotroski:
    def test_altman_none_when_a_post_missing(self):
        health = {"total_assets": _series({2025: 1000}), "ebit": _series({2025: 100})}
        assert sf._altman_z(health, market_cap=500) is None

    def test_altman_computes_full_score(self):
        health = {
            "working_capital": _series({2025: 100.0}),
            "retained_earnings": _series({2025: 200.0}),
            "ebit": _series({2025: 300.0}),
            "total_assets": _series({2025: 1000.0}),
            "total_liabilities": _series({2025: 400.0}),
            "revenue": _series({2025: 2000.0}),
        }
        z = sf._altman_z(health, market_cap=600.0)
        # 1.2·0.1 + 1.4·0.2 + 3.3·0.3 + 0.6·1.5 + 0.999·2 = 4.288
        assert z == pytest.approx(4.288)

    def test_piotroski_full_nine(self):
        health = {
            "net_income": _series({2025: 100.0, 2024: 50.0}),
            "ocf": _series({2025: 150.0, 2024: 40.0}),
            "total_assets": _series({2025: 1000.0, 2024: 900.0}),
            "long_term_debt": _series({2025: 200.0, 2024: 300.0}),
            "current_assets": _series({2025: 500.0, 2024: 400.0}),
            "current_liabilities": _series({2025: 200.0, 2024: 250.0}),
            "shares": _series({2025: 100.0, 2024: 120.0}),
            "gross_profit": _series({2025: 400.0, 2024: 300.0}),
            "revenue": _series({2025: 800.0, 2024: 700.0}),
        }
        assert sf._piotroski(health) == 9.0

    def test_piotroski_none_when_data_missing(self):
        health = {
            "net_income": _series({2025: 100.0, 2024: 50.0}),
            "total_assets": _series({2025: 1000.0, 2024: 900.0}),
        }
        assert sf._piotroski(health) is None


class TestCards:
    def test_financial_company_has_no_health_scores(self):
        table = _table({"Bénéfice net": [10, 9, 8, 7, 6]})
        fund = _fundamentals(table, kind=CompanyKind.FINANCIAL)
        cards = sf.build_summary(_identity(kind=CompanyKind.FINANCIAL), fund, 10.0, 50.0)
        assert _row(cards, "sante", "altman_z").value is None
        assert _row(cards, "sante", "piotroski").value is None

    def test_quality_note_is_scaled_over_twenty(self):
        table = _table({"Bénéfice net": [10, 9, 8, 7, 6]})
        cards = sf.build_summary(_identity(), _fundamentals(table), 10.0, 70.0)
        row = _row(cards, "profil", "quality_score")
        assert row.value == 14.0
        assert row.good is True  # 14/20 >= 11/20 (seuil config)

    def test_quality_note_below_threshold_is_bad(self):
        table = _table({"Bénéfice net": [10, 9, 8, 7, 6]})
        cards = sf.build_summary(_identity(), _fundamentals(table), 10.0, 30.0)
        assert _row(cards, "profil", "quality_score").good is False

    def test_missing_values_stay_none(self):
        cards = sf.build_summary(_identity(), None, None, None)
        assert _row(cards, "valorisation", "per").value is None
        assert _row(cards, "marges", "net_margin").value is None
        assert _row(cards, "marges", "net_margin").good is None

    def test_market_cap_category_thresholds(self):
        cards = sf.build_summary(_identity(market_cap=15e9), None, None, None)
        assert _row(cards, "marche", "cap_category").text == "Large Cap"
        cards = sf.build_summary(_identity(market_cap=5e9), None, None, None)
        assert _row(cards, "marche", "cap_category").text == "Mid Cap"
        cards = sf.build_summary(_identity(market_cap=1e9), None, None, None)
        assert _row(cards, "marche", "cap_category").text == "Small Cap"

    def test_interest_coverage_uses_common_year(self):
        table = _table({"Bénéfice net": [10, 9, 8, 7, 6]})
        health = {
            "operating_income": _series({2025: 300.0, 2024: 200.0}),
            "interest_expense": _series({2024: 100.0}),  # seule 2024 a les deux
        }
        fund = _fundamentals(table, health_rows=health)
        cards = sf.build_summary(_identity(), fund, 10.0, 50.0)
        assert _row(cards, "sante", "interest_coverage").value == 2.0

    def test_p_b_negative_is_neutralized(self):
        table = _table({"Bénéfice net": [10, 9, 8, 7, 6]})
        fund = _fundamentals(table, market={"price_to_book": -6.0})
        cards = sf.build_summary(_identity(), fund, 10.0, 50.0)
        row = _row(cards, "valorisation", "p_b")
        # Un P/B négatif (capitaux propres négatifs) n'est pas interprétable -> --.
        assert row.value is None
        assert row.good is None

    def test_p_b_positive_is_kept(self):
        table = _table({"Bénéfice net": [10, 9, 8, 7, 6]})
        fund = _fundamentals(table, market={"price_to_book": 0.98})
        cards = sf.build_summary(_identity(), fund, 10.0, 50.0)
        assert _row(cards, "valorisation", "p_b").value == 0.98

    def test_fair_price_note_when_saved(self):
        """Un prix juste venu de la calculatrice porte la note « enregistré » (#20)."""
        table = _table({"Bénéfice net": [10, 9, 8, 7, 6]})
        fund = _fundamentals(table)
        plain = sf.build_summary(_identity(), fund, 10.0, 50.0)
        assert _row(plain, "valorisation", "fair_price").note is None
        saved = sf.build_summary(
            _identity(),
            fund,
            10.0,
            50.0,
            fair_price_note="Prix juste enregistré (calculatrice)",
        )
        assert _row(saved, "valorisation", "fair_price").note == (
            "Prix juste enregistré (calculatrice)"
        )

    def test_fair_price_note_passes_through_for_reference(self):
        """Une note de référence (#25) est portée telle quelle par la carte."""
        fund = _fundamentals(_table({"Bénéfice net": [10, 9, 8, 7, 6]}))
        note = "Droite de référence (prix bruts, depuis 2012)"
        cards = sf.build_summary(_identity(), fund, 10.0, 50.0, fair_price_note=note)
        assert _row(cards, "valorisation", "fair_price").note == note

    def test_capex_sales_ratio(self):
        table = _table({"Chiffre d'affaires": [1000, 900, 800, 700, 600]})
        health = {"capex": _series({2025: -60.0})}  # CAPEX sortant, négatif
        fund = _fundamentals(table, health_rows=health)
        cards = sf.build_summary(_identity(), fund, 10.0, 50.0)
        # |−60| / 1000 = 6 %.
        assert _row(cards, "marges", "capex_sales").value == 6.0

    def test_capex_sales_none_without_capex(self):
        table = _table({"Chiffre d'affaires": [1000, 900, 800, 700, 600]})
        cards = sf.build_summary(_identity(), _fundamentals(table), 10.0, 50.0)
        assert _row(cards, "marges", "capex_sales").value is None

    def test_profitability_has_1y_and_5y(self):
        table = _table(
            {"ROE": [12, 11, 10, 9, 8], "ROCE": [20, 18, 16, 14, 12]},
            years=(2025, 2024, 2023, 2022, 2021),
        )
        health = {
            "ebit": _series({2025: 100.0, 2024: 90.0}),
            "invested_capital": _series({2025: 500.0, 2024: 500.0}),
            "tax_rate": _series({2025: 0.0, 2024: 0.0}),
        }
        fund = _fundamentals(table, health_rows=health)
        cards = sf.build_summary(_identity(), fund, 10.0, 50.0)
        assert _row(cards, "rentabilite", "roe_1y").value == 12.0
        assert _row(cards, "rentabilite", "roce_1y").value == 20.0
        assert _row(cards, "rentabilite", "roic_1y").value == 20.0  # 100/500
        assert _row(cards, "rentabilite", "roe_5y").value == 10.0
        assert _row(cards, "rentabilite", "roic_5y").value == 19.0  # moyenne (20, 18)

    def test_financial_scores_carry_explanatory_note(self):
        table = _table({"Bénéfice net": [10, 9, 8, 7, 6]})
        fund = _fundamentals(table, kind=CompanyKind.FINANCIAL)
        cards = sf.build_summary(_identity(kind=CompanyKind.FINANCIAL), fund, 10.0, 50.0)
        assert _row(cards, "sante", "altman_z").note == config.FINANCIAL_NOT_APPLICABLE
        assert _row(cards, "sante", "piotroski").note == config.FINANCIAL_NOT_APPLICABLE
        # Pour une industrielle, aucune note (le score est calculé).
        cards = sf.build_summary(_identity(), _fundamentals(table), 10.0, 50.0)
        assert _row(cards, "sante", "altman_z").note is None

    def test_1y_and_5y_profitability_share_colors(self):
        # Les lignes 1A et 5A de la carte Rentabilité sont toutes colorées
        # (config.SUMMARY_COLORS) : aucune incohérence visuelle entre elles.
        table = _table(
            {"ROE": [12, 11, 10, 9, 8], "ROCE": [20, 18, 16, 14, 12]},
            years=(2025, 2024, 2023, 2022, 2021),
        )
        cards = sf.build_summary(_identity(), _fundamentals(table), 10.0, 50.0)
        for key in ("roe_1y", "roce_1y", "roe_5y", "roce_5y"):
            assert _row(cards, "rentabilite", key).good is True, key

    def test_dividend_growth_horizons(self):
        table = _table({"Bénéfice net": [10, 9, 8, 7, 6]})
        per_share = {2025: 2.0, 2024: 1.8, 2023: 1.6, 2022: 1.4, 2021: 1.2, 2020: 1.0}
        fund = _fundamentals(table, dividend={"per_share": per_share, "yield_pct": 4.0})
        cards = sf.build_summary(_identity(), fund, 10.0, 50.0)
        assert _row(cards, "dividende", "div_cagr_1y").value is not None
        assert _row(cards, "dividende", "div_cagr_5y").value is not None
        assert _row(cards, "dividende", "div_cagr_10y").value is None  # historique trop court
        assert _row(cards, "dividende", "div_growth_years").value == 5.0

    def test_growth_matrix_fuses_revenue_and_eps(self):
        # CA + EPS fusionnés en une seule carte MATRICE : deux lignes alignées sur
        # les colonnes 1A/5A/10A/Futur (fin des deux cartes jumelles).
        table = _table(
            {"Chiffre d'affaires": [121, 110, 100, 90, 80], "BNPA dilué": [12, 11, 10, 9, 8]},
            years=(2025, 2024, 2023, 2022, 2021),
        )
        fund = _fundamentals(table, estimates={"revenue_growth": 4.4, "eps_growth": 9.3})
        cards = sf.build_summary(_identity(), fund, 10.0, 50.0)
        assert [c.id for c in cards].count("croissance") == 1
        assert "ca" not in [c.id for c in cards]
        card = _card(cards, "croissance")
        assert card.columns == ["1A", "5A", "10A", "Futur"]
        ca = next(r for r in card.rows if r.key == "ca")
        eps = next(r for r in card.rows if r.key == "eps")
        assert ca.cells[0] == pytest.approx(10.0)  # 121/110 - 1
        assert ca.cells[3] == 4.4  # consensus analystes
        assert eps.cells[0] == pytest.approx(9.09, abs=0.01)  # 12/11 - 1
        assert ca.cell_good[0] is True  # croissance positive = bleu
        assert ca.cells[1] is None  # 5A non couvert (historique trop court)

    def test_growth_matrix_missing_series_stays_none(self):
        # Sans comptes : la carte existe (structure stable), toutes cellules None.
        cards = sf.build_summary(_identity(), None, None, None)
        card = _card(cards, "croissance")
        assert card.columns == ["1A", "5A", "10A", "Futur"]
        assert all(c is None for r in card.rows for c in r.cells)
