"""Tests du score composite (chantier #14) — pur, sans réseau.

Le score est un **classement par compromis** : chaque critère est normalisé en
percentile (0-100, 100 = meilleur selon `SCREEN_SORT_DESC`), puis moyenné à poids
égaux. Contrairement au tri en cascade (où le 2e critère ne départage que les
égalités), il fait agir TOUS les critères simultanément.

Exigence métier (chantier #14) : « ROE % ▼ + P/FCF ▲ » doit remonter les valeurs
qui ont à la fois un ROE élevé ET un P/FCF bas — pas les ROE les plus hauts.
"""

from __future__ import annotations

from obole.engine import screen
from obole.models import ScreenResult


def _sr(ticker: str, **kw) -> ScreenResult:
    """ScreenResult minimal pour les tests de score."""
    return ScreenResult(ticker=ticker.upper(), name=ticker, **kw)


class TestCompositeScore:
    def test_returns_none_when_fewer_than_two_keys(self):
        """Avec 0 ou 1 critère, pas de score : le tri simple suffit."""
        rows = [_sr("A", roe_pct=10.0), _sr("B", roe_pct=20.0)]
        assert screen.composite_score(rows, []) == {}
        assert screen.composite_score(rows, ["roe_pct"]) == {}

    def test_empty_rows(self):
        assert screen.composite_score([], ["roe_pct", "p_fcf"]) == {}

    def test_single_row_gets_neutral_score(self):
        """Une seule valeur : percentile indéfini -> score neutre (100 sur un
        rang unique, méthode « min »), pas de division par zéro."""
        out = screen.composite_score([_sr("A", roe_pct=10.0, p_fcf=9.0)], ["roe_pct", "p_fcf"])
        assert out == {"A": 100.0}

    def test_compromise_beats_single_extreme(self):
        """Le cœur de l'exigence : le compromis gagne sur l'extrême isolé.

        ROE % (desc) + P/FCF (asc). B est bien classé sur les DEUX critères.
        A écrase le ROE mais est le plus cher ; D est le moins cher mais a le
        pire ROE. B doit passer devant A et D.

        ⚠️ Les rangs ne doivent PAS être parfaitement anti-corrélés : dans ce cas
        la moyenne des percentiles est constante (50 partout), ce qui masquerait
        le compromis. Ici B est meilleur que C sur les deux critères.
        """
        rows = [
            _sr("A", roe_pct=30.0, p_fcf=30.0),  # 1er ROE, dernier P/FCF
            _sr("B", roe_pct=25.0, p_fcf=9.0),  # 2e ROE, 2e P/FCF -> compromis
            _sr("C", roe_pct=20.0, p_fcf=10.0),  # 3e ROE, 3e P/FCF
            _sr("D", roe_pct=10.0, p_fcf=5.0),  # dernier ROE, 1er P/FCF
        ]
        score = screen.composite_score(rows, ["roe_pct", "p_fcf"])
        assert score["B"] > score["A"]
        assert score["B"] > score["D"]
        assert score["B"] == max(score.values())

    def test_percentile_direction_follows_sort_desc(self):
        """Un critère « le_pos » (P/FCF, plus bas = mieux) doit donner le
        meilleur percentile à la valeur la plus basse."""
        rows = [_sr("cheap", p_fcf=5.0, roe_pct=10.0), _sr("pricey", p_fcf=20.0, roe_pct=10.0)]
        score = screen.composite_score(rows, ["p_fcf", "roe_pct"])
        assert score["CHEAP"] > score["PRICEY"]

    def test_missing_value_excluded(self):
        """Une ligne privée d'au moins un critère actif n'a pas de score."""
        rows = [
            _sr("A", roe_pct=20.0, p_fcf=10.0),
            _sr("B", roe_pct=15.0, p_fcf=None),  # P/FCF manquant
        ]
        score = screen.composite_score(rows, ["roe_pct", "p_fcf"])
        assert "A" in score
        assert "B" not in score

    def test_error_rows_excluded(self):
        rows = [_sr("A", roe_pct=20.0, p_fcf=10.0), _sr("B", roe_pct=15.0, p_fcf=9.0, error="boom")]
        score = screen.composite_score(rows, ["roe_pct", "p_fcf"])
        assert set(score) == {"A"}

    def test_score_bounds(self):
        rows = [
            _sr("A", roe_pct=30.0, p_fcf=5.0),
            _sr("B", roe_pct=20.0, p_fcf=10.0),
            _sr("C", roe_pct=10.0, p_fcf=20.0),
        ]
        score = screen.composite_score(rows, ["roe_pct", "p_fcf"])
        assert all(0.0 <= v <= 100.0 for v in score.values())

    def test_ties_get_equal_score(self):
        """Deux lignes identiques doivent avoir le même score (pas d'arbitraire)."""
        rows = [_sr("A", roe_pct=20.0, p_fcf=10.0), _sr("B", roe_pct=20.0, p_fcf=10.0)]
        score = screen.composite_score(rows, ["roe_pct", "p_fcf"])
        assert score["A"] == score["B"]

    def test_is_deterministic(self):
        rows = [
            _sr("A", roe_pct=30.0, p_fcf=5.0),
            _sr("B", roe_pct=20.0, p_fcf=10.0),
            _sr("C", roe_pct=10.0, p_fcf=20.0),
        ]
        assert screen.composite_score(rows, ["roe_pct", "p_fcf"]) == screen.composite_score(
            rows, ["roe_pct", "p_fcf"]
        )

    def test_unknown_key_ignored(self):
        """Une clé inconnue est ignorée (pas de crash) ; il reste 2 critères."""
        rows = [_sr("A", roe_pct=20.0, p_fcf=10.0), _sr("B", roe_pct=10.0, p_fcf=5.0)]
        score = screen.composite_score(rows, ["roe_pct", "p_fcf", "inconnu"])
        assert len(score) == 2


class TestScoreInFilterAndSort:
    def test_score_key_is_sortable(self):
        assert "score" in screen.SORTABLE_KEYS

    def test_score_is_not_filterable(self):
        """Le score est un rang calculé, pas une donnée de marché : il ne doit
        pas être filtrable (sinon résultat vide silencieux, cf. revue #14)."""
        assert "score" not in screen.FILTERABLE_KEYS
        assert "roe_pct" in screen.FILTERABLE_KEYS
        assert set(screen.FILTERABLE_KEYS) == set(screen.SORTABLE_KEYS) - {"score"}

    def test_sortable_keys_has_no_duplicate(self):
        assert len(screen.SORTABLE_KEYS) == len(set(screen.SORTABLE_KEYS))

    def test_sort_by_score_desc_puts_best_compromise_first(self):
        rows = [
            _sr("A", roe_pct=30.0, p_fcf=30.0),
            _sr("B", roe_pct=25.0, p_fcf=9.0),
            _sr("C", roe_pct=20.0, p_fcf=10.0),
            _sr("D", roe_pct=10.0, p_fcf=5.0),
        ]
        out = screen.filter_and_sort(
            rows, sort_by=[("score", "desc")], score_keys=["roe_pct", "p_fcf"]
        )
        assert out[0].ticker == "B"

    def test_score_computed_only_when_at_least_two_keys(self):
        rows = [_sr("A", roe_pct=20.0, p_fcf=10.0), _sr("B", roe_pct=10.0, p_fcf=5.0)]
        out = screen.filter_and_sort(rows, sort_by=["roe_pct"], score_keys=["roe_pct"])
        assert all(r.score is None for r in out)

    def test_score_set_on_rows(self):
        rows = [_sr("A", roe_pct=20.0, p_fcf=10.0), _sr("B", roe_pct=10.0, p_fcf=5.0)]
        out = screen.filter_and_sort(
            rows, sort_by=[("score", "desc")], score_keys=["roe_pct", "p_fcf"]
        )
        assert all(r.score is not None for r in out)

    def test_no_score_keys_leaves_score_none(self):
        rows = [_sr("A", roe_pct=20.0, p_fcf=10.0)]
        out = screen.filter_and_sort(rows, sort_by=["roe_pct"])
        assert out[0].score is None
