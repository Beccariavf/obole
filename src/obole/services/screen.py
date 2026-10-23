"""Cas d'usage « screener » : réduit une valeur en `ScreenResult` triable.

Couche `services/` : orchestre `data/` (via `services/analysis.analyze`) et
`engine/` (logique pure). La partie **pure** du screener (filtre + tri +
score composite) reste dans `engine/screen.py` — ce module ne fait que
l'orchestration I/O + réduction.
"""

from __future__ import annotations

from obole import config
from obole.data.yahoo import TickerNotFound as TickerNotFound
from obole.engine import labels
from obole.engine import regression as reg
from obole.engine import summary as summary_mod
from obole.models import PriceSeries, ScreenResult, StockAnalysis
from obole.services.analysis import analyze


def screen_stock(
    ticker: str,
    prices: PriceSeries,
    regression_window: float | None = None,
) -> ScreenResult:
    """Réduit une valeur à ses critères triables (méthode « droite d'Obole »).

    Délègue à `services.analysis.analyze(ticker, prices)` (aucune formule recalculée
    ici, aucun appel réseau : les prix arrivent déjà fetchés). Si `regression_window`
    (années) est fourni, la distance σ ET la pente sont recalculées sur cette
    fenêtre (via summary.regression_window, même règle que summary.member_stats) ;
    sinon historique complet. La tendance MM reste sur l'historique complet.

    Les fondamentaux (ROE, PER, P/B, P/FCF, FCF yield) sont extraits de
    `analysis.fundamentals` et valent None si les comptes sont indisponibles.

    Ne lève jamais : un ticker invalide (données absentes, historique trop court)
    renvoie un ScreenResult avec `error` posé. N'englobe QUE les erreurs de
    données connues — un vrai bug (TypeError, AttributeError…) doit rester visible.
    """
    try:
        analysis: StockAnalysis = analyze(ticker, prices)
    # Données indisponibles/invalides (ticker inconnu, série trop courte) :
    # on isole le ticker pour que le scan continue. Jamais de crash global.
    except (TickerNotFound, ValueError, KeyError, IndexError) as exc:
        return ScreenResult(ticker=ticker.upper(), error=str(exc))

    # Décision « fenêtre » : σ et pente sur la fenêtre définie (sinon complet).
    if regression_window is not None:
        raw = summary_mod.regression_window(prices.raw, int(regression_window)).dropna()
        adj = summary_mod.regression_window(prices.adjusted, int(regression_window)).dropna()
    else:
        raw = prices.raw.dropna()
        adj = prices.adjusted.dropna()
    raw = raw[raw > 0]
    adj = adj[adj > 0]

    _recompute_window(analysis, raw, adj)

    return _from_analysis(analysis)


def _recompute_window(analysis: StockAnalysis, raw, adj) -> None:
    """Recalcule σ/pente/potentiels sur la fenêtre choisie (in place).

    On ne réutilise pas `summary.member_stats` ici : elle ne renvoie que 3 stats
    étiquetées (z, pente, tendance) sur la série ajustée seulement — le screener a
    besoin des valeurs brutes, des potentiels 5/10 ans ET de la régression brute+ajustée.
    La fenêtre elle-même est bien `summary.regression_window` (même règle), seule
    la consommation diffère. Toute modification de la sémantique de fenêtre doit
    rester synchronisée entre `summary` et `_recompute_window` (invariant J2).
    """
    try:
        reg_raw = reg.fit_log_regression(raw)
    except ValueError:
        reg_raw = None
    try:
        reg_adj = reg.fit_log_regression(adj)
    except ValueError:
        reg_adj = None

    if reg_raw is not None:
        analysis.regression_raw = reg_raw
        analysis.indicators.ecart_type = labels.label_ecart_type(reg_raw.ecart_type_size * 100)
        analysis.indicators.distance_sigma = labels.label_distance_sigma(
            reg.distance_sigma(reg_raw, float(raw.iloc[-1]))
        )
        analysis.indicators.potential_5y = labels.label_potential(
            reg.annualized_potential(reg_raw, float(raw.iloc[-1]), config.POTENTIAL_HORIZONS[0])
            * 100
        )
        analysis.indicators.potential_10y = labels.label_potential(
            reg.annualized_potential(reg_raw, float(raw.iloc[-1]), config.POTENTIAL_HORIZONS[1])
            * 100
        )
    if reg_adj is not None:
        analysis.regression_adj = reg_adj
        analysis.indicators.perf_passee = labels.label_perf(reg_adj.perf_annual * 100)


def _from_analysis(analysis: StockAnalysis) -> ScreenResult:
    """Construit le ScreenResult depuis un StockAnalysis (extraction, aucun calcul)."""
    ident = analysis.identity
    ind = analysis.indicators

    out = ScreenResult(
        ticker=ident.ticker.upper(),
        name=ident.name,
        sector=ident.sector,
        market_cap=ident.market_cap,
        kind=ident.kind,
        z=ind.distance_sigma.value,
        pente_pct=ind.perf_passee.value,
        ecart_type_pct=ind.ecart_type.value,
        pot_5y_pct=ind.potential_5y.value,
        pot_10y_pct=ind.potential_10y.value,
        trend_bullish=_trend_bool(analysis),
        quality_score=ind.quality.value,
        warnings=list(analysis.warnings),
    )
    _load_fundamentals(out, analysis.fundamentals)
    return out


def _load_fundamentals(out: ScreenResult, f) -> None:
    """ROE/PER/P/B/P/FCF/FCF yield depuis les comptes (None si indisponible)."""
    if f is None or f.table is None or f.table.empty:
        return
    if "ROE" in f.table.index:
        roe = f.table.loc["ROE"].dropna()
        if len(roe):
            out.roe_pct = float(roe.iloc[0])
    if f.valuation is not None and not f.valuation.empty:
        out.per = _latest(f.valuation, "PER")
        out.p_b = _latest(f.valuation, "Price / Book")
        out.p_fcf = _latest(f.valuation, "P/FCF")
        out.fcf_yield_pct = _latest(f.valuation, "FCF yield")


def _latest(table, metric: str) -> float | None:
    """Valeur la plus récente d'une ligne (colonnes = années, 0 = la plus récente)."""
    if table is None or table.empty or metric not in table.index:
        return None
    row = table.loc[metric].dropna()
    if row.empty:
        return None
    return float(row.iloc[0])


def _trend_bool(analysis: StockAnalysis) -> bool | None:
    """Tendance en booléen (Haussière=True, Baissière=False, None=inconnu)."""
    t = analysis.indicators.trend
    if t.label == "Haussière":
        return True
    if t.label == "Baissière":
        return False
    return None
