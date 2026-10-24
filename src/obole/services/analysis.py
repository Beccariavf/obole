"""Cas d'usage « analyse » : orchestre data + engine en un StockAnalysis complet.

Couche `services/` : elle **appelle** `data/` (I/O) et `engine/` (logique pure),
jamais l'inverse. C'est ici que vit l'orchestration, pas dans `engine/` (qui reste
100 % pur). Les prix sont reçus en paramètre (l'API les fetch une seule fois).
"""

from __future__ import annotations

import pandas as pd

from obole import config
from obole.data import cache, yahoo
from obole.data.fundamentals import quality_inputs
from obole.data.yahoo import TickerNotFound as TickerNotFound
from obole.engine import basket as basket_mod
from obole.engine import dividends as dividends_mod
from obole.engine import labels
from obole.engine import ratio as ratio_mod
from obole.engine import regression as reg
from obole.engine import summary as summary_mod
from obole.engine import summary_fundamentals as summary_fund_mod
from obole.engine import valuation as valuation_mod
from obole.engine import valuation_calc as vc
from obole.engine.quality import quality_score
from obole.models import (
    BasketAnalysis,
    Indicators,
    PriceSeries,
    RatioAnalysis,
    ScoredValue,
    StockAnalysis,
)


def reference_window(ticker: str, raw: pd.Series) -> tuple[pd.Series, str | None]:
    """Fenêtre de confiance d'un titre : depuis la date persistée, sinon 20 ans.

    SOURCE UNIQUE de la sélection (#25) : le « Prix juste » du Résumé et le
    classement de la watchlist lisent la même tranche. La référence est une date
    ISO persistée par titre (`ticker_refs`) ; une référence illisible ou trop
    courte (< `config.REGRESSION_MIN_POINTS` points) est ignorée et on retombe
    sur la fenêtre 20 ans — dégradation silencieuse, jamais de crash.

    Renvoie `(série filtrée > 0, ref_start | None)`. `ref_start` vaut None quand
    la fenêtre par défaut est utilisée (aucune note à afficher).
    """
    ref = cache.get_ticker_ref(ticker)
    if ref:
        try:
            window = summary_mod.window_since(raw, ref).dropna()
            window = window[window > 0]
            if len(window) >= config.REGRESSION_MIN_POINTS:
                return window, ref
        except (TypeError, ValueError):
            pass  # date corrompue en base : on retombe sur le défaut
    window = summary_mod.regression_window(raw).dropna()
    return window[window > 0], None


def _fair_price(ticker: str, raw: pd.Series) -> tuple[float | None, str | None]:
    """« Prix juste » : droite de la fenêtre de référence (prix brut) + sa note.

    La fenêtre vient de `reference_window` : date de confiance persistée si elle
    existe, sinon 20 ans. Le cours brut est la série de référence de la
    valorisation (PRD §5) : c'est aussi celle du cours affiché en en-tête, donc
    la comparaison « prix juste / prix communiqué » est homogène.

    Ce n'est PAS la distance σ du KPI : celle-ci se calcule sur l'historique
    complet (droite d'Obole), ni la droite du graphe (série ajustée, fenêtre
    visible). Trois lectures distinctes, chacune documentée.

    Renvoie `(valeur, note)` ; la note n'existe que pour une référence
    persistée (le défaut 20 ans garde le comportement historique, sans note).
    """
    window, ref = reference_window(ticker, raw)
    try:
        value = reg.fit_log_regression(window).fitted_now
    except ValueError:
        return None, None
    if ref:
        return value, f"Droite de référence (prix bruts, depuis {ref[:4]})"
    return value, None


def _shares_by_year(ticker: str, fundamentals) -> dict[int, float]:
    """Nombre d'actions en circulation par exercice, depuis les comptes.

    Lu de la ligne « Actions en circulation » du tableau normalisé (instantané de
    fin d'exercice). Sert à ramener les rachats TOTAUX (cash-flow) en par-action
    ET à calculer les métriques par action de la calculatrice de prix juste.

    Repli `info["sharesOutstanding"]` (cache, déjà chaud via fetch_identity)
    quand la ligne est absente du tableau : les profils financiers (banques,
    assurances — ex. Amundi) n'exposent pas ce poste dans les comptes yfinance,
    alors que le nombre d'actions courant reste disponible. Sans ce repli, la
    composante rachat serait nulle (Shareholder Yield faux) et la section
    Valorisation serait masquée alors que la section Dividende, elle, sait
    calculer ses valeurs par action. Dict vide seulement si les deux sources
    manquent.
    """
    table = fundamentals.table if fundamentals is not None else None
    by_year = _shares_by_year_raw(table)
    if by_year:
        return by_year
    # Repli : actions courantes (snapshot) — rattachées à l'exercice courant. Les
    # consommateurs appliquent un repli « exercice le plus proche » par année.
    info = cache.get(ticker, "info", config.TTL_FUNDAMENTALS) or {}
    shares = info.get("sharesOutstanding")
    if shares:
        year = pd.Timestamp.today().year
        return {year: float(shares)}
    return {}


def _shares_for_year(shares: dict[int, float], year: int) -> float | None:
    """Actions de l'exercice `year`, ou de l'exercice connu le plus PROCHE.

    Le nombre d'actions est un instantané de fin d'exercice : quand l'exercice
    exact manque (ou qu'un unique snapshot courant a servi de repli), on retombe
    sur l'exercice connu le plus proche — même règle que
    `engine/dividends.buybacks_per_share`. `None` si aucun nombre exploitable.
    """
    if not shares:
        return None
    if year in shares:
        return shares[year]
    closest = min(shares, key=lambda y: (abs(y - year), -y))
    value = shares[closest]
    return value if value and value > 0 else None


def _per_share_by_year(
    table: pd.DataFrame,
    metric: str,
    shares: dict[int, float],
    already_per_share: bool = False,
) -> dict[int, float]:
    """Métrique par action par exercice = poste / actions de l'exercice.

    `already_per_share=True` (ex. BNPA dilué) : la ligne est DÉJÀ par action, on
    la renvoie telle quelle (ne pas la rediviser par les actions — sinon le
    multiple serait absurde). Les actions de l'exercice viennent de
    `_shares_for_year` (repli « exercice le plus proche ») : un exercice sans
    nombre d'actions exploitable est ignoré.
    """
    if table is None or table.empty or metric not in table.index or not shares:
        return {}
    out: dict[int, float] = {}
    for year, value in table.loc[metric].items():
        if value is None or pd.isna(value):
            continue
        y = int(getattr(year, "year", year))
        if already_per_share:
            out[y] = float(value)
            continue
        n = _shares_for_year(shares, y)
        if n:
            out[y] = float(value) / float(n)
    return out


def _net_debt_per_share(rows: dict | None, shares: dict[int, float]) -> dict[int, float]:
    """Dette nette PAR ACTION par exercice (bridge EV -> capitaux propres).

    Sert les multiples d'entreprise (EV/EBITDA) : valeur par action = EBITDA/action
    × multiple − dette nette/action. Dict vide si la dette nette manque.
    """
    by_year = _raw_by_year((rows or {}).get("net_debt"))
    out: dict[int, float] = {}
    for year, value in by_year.items():
        n = _shares_for_year(shares, year)
        if n:
            out[year] = value / float(n)
    return out


def _raw_by_year(row: pd.Series | None) -> dict[int, float]:
    """Série brute (indexée par Timestamp de clôture) -> {année: valeur}."""
    if row is None:
        return {}
    out: dict[int, float] = {}
    for ts, value in row.items():
        if value is None or pd.isna(value):
            continue
        out[int(getattr(ts, "year", ts))] = float(value)
    return out


def _valuation_series(fundamentals, prices: PriceSeries, ticker: str) -> dict | None:
    """Séries CONTINUES de multiples (cours quotidien / métrique annuelle).

    Chaque série est alignée sur `prices.raw.index` (donc sur `chart.dates` après
    décimation) : le dénominateur annuel est reporté par palier (forward-fill),
    le numérateur suit le cours au quotidien. C'est le patron du Dividend Yield.
    """
    if fundamentals is None or not fundamentals.valuation_rows:
        return None
    table = fundamentals.table
    rows = fundamentals.valuation_rows
    shares = _shares_by_year(ticker, fundamentals)
    if not shares:
        return None
    dates = prices.raw.index
    eps_ps = _per_share_by_year(table, "BNPA dilué", shares, already_per_share=True)
    fcf_ps = _per_share_by_year(table, "Free Cash Flow", shares)
    sales_ps = _per_share_by_year(table, "Chiffre d'affaires", shares)
    book_ps = _per_share_by_year(table, "Capitaux propres", shares)
    ebitda_by_year = _raw_by_year(rows.get("ebitda"))
    net_debt_by_year = _raw_by_year(rows.get("net_debt"))

    series: dict[str, pd.Series] = {
        "eps_ps": vc.step_series(dates, eps_ps),
        "fcf_ps": vc.step_series(dates, fcf_ps),
        "sales_ps": vc.step_series(dates, sales_ps),
        "book_ps": vc.step_series(dates, book_ps),
        "per": vc.price_over_step(dates, prices.raw, eps_ps),
        "p_fcf": vc.price_over_step(dates, prices.raw, fcf_ps),
        "p_s": vc.price_over_step(dates, prices.raw, sales_ps),
        "p_b": vc.price_over_step(dates, prices.raw, book_ps),
        "ev_ebitda": vc.enterprise_multiple_series(
            dates, prices.raw, shares, ebitda_by_year, net_debt_by_year
        ),
    }
    # Une série entièrement vide n'apporte rien : on ne l'expose pas.
    return {k: s for k, s in series.items() if s.notna().any()} or None


def _shares_by_year_raw(table: pd.DataFrame) -> dict[int, float]:
    """Actions en circulation par exercice, depuis le tableau normalisé."""
    if table is None or table.empty or "Actions en circulation" not in table.index:
        return {}
    out: dict[int, float] = {}
    for year, value in table.loc["Actions en circulation"].items():
        if value is None or pd.isna(value) or value <= 0:
            continue
        out[int(getattr(year, "year", year))] = float(value)
    return out


def _valuation_calc_payload(fundamentals, prices: PriceSeries, ticker: str) -> dict | None:
    """Données de la calculatrice de prix juste (le front recalcule en live).

    On fournit les INGRÉDIENTS (métrique par action par exercice, multiple médian
    par période, multiple courant, dividende, paramètres de grille et de couleur)
    — jamais le résultat : le calcul (prix juste, rendement, matrice) est fait
    côté client, avec `engine/valuation_calc.py` comme référence testée.
    """
    if fundamentals is None:
        return None
    table = fundamentals.table
    shares = _shares_by_year(ticker, fundamentals)
    if not shares:
        return None
    valuation = fundamentals.valuation
    dividend = fundamentals.dividend or {}
    periods = list(config.VALUATION_PERIODS)
    rows = fundamentals.valuation_rows or {}
    net_debt_ps = _net_debt_per_share(rows, shares)
    metrics = []
    for spec in config.VALUATION_METRICS:
        per_share = _per_share_by_year(
            table, spec["metric"], shares, already_per_share=spec["per_share"]
        )
        if not per_share:
            continue
        latest_year = max(per_share)
        latest = per_share[latest_year]
        median: dict[str, float | None] = {}
        if valuation is not None and spec["multiple"] in valuation.index:
            row = valuation.loc[spec["multiple"]]
            for period in periods:
                median[str(period)] = vc.median_multiple(row, period)
        last_price = float(prices.raw.iloc[-1]) if len(prices.raw) else None
        # Multiple COURANT (m0 de la formule) : pour un multiple de capitalisation,
        # cours / métrique par action ; pour un multiple d'entreprise (EV/EBITDA),
        # (cours + dette nette/action) / EBITDA par action.
        current = None
        bridge = net_debt_ps.get(latest_year) if spec["enterprise"] else None
        if last_price is not None and latest > 0:
            if spec["enterprise"]:
                current = (last_price + (bridge or 0.0)) / latest
            else:
                current = last_price / latest
        metrics.append(
            {
                "key": spec["key"],
                "label": spec["label"],
                "multiple": spec["multiple"],
                "unit": spec["unit"],
                "enterprise": spec["enterprise"],
                "multiple_step": spec["multiple_step"],
                "per_share": {str(y): v for y, v in sorted(per_share.items())},
                "latest": round(latest, 4),
                "median": median,
                "current_multiple": round(current, 4) if current is not None else None,
                # Bridge EV -> capitaux propres (multiple d'entreprise seulement).
                "net_debt_per_share": round(bridge, 4) if bridge is not None else None,
            }
        )
    if not metrics:
        return None
    return {
        "metrics": metrics,
        "periods": periods,
        "period_default": config.VALUATION_PERIOD_DEFAULT,
        "horizon": config.VALUATION_HORIZON_YEARS,
        "target_default": config.VALUATION_TARGET_YIELD_DEFAULT,
        "matrix": {
            "rows": config.VALUATION_MATRIX_ROWS,
            "cols": config.VALUATION_MATRIX_COLS,
            "growth_step": config.VALUATION_MATRIX_GROWTH_STEP,
            "multiple_step": config.VALUATION_MATRIX_MULTIPLE_STEP,
        },
        "color_ratios": list(config.VALUATION_COLOR_RATIOS),
        "dividend_yield": dividend.get("yield_pct"),
        "dividend_per_share": dividend.get("per_share") or {},
        "saved": cache.get_valuation_settings(ticker),
    }


def analyze_ticker(ticker: str) -> tuple[StockAnalysis, PriceSeries]:
    """Analyse complète d'une valeur à partir de son ticker (fetch + analyse).

    Point d'entrée **partagé API ↔ MCP** : l'orchestration « récupérer les prix
    puis analyser » vit ici, jamais dans `api/` ni `mcp/`. Lève
    `yahoo.TickerNotFound` si le ticker est inconnu, `ValueError` si l'historique
    est trop court.

    Renvoie `(analysis, prices)` : les prix restent nécessaires à la
    sérialisation (cours brut/ajusté, moyennes mobiles précalculées).
    """
    prices = yahoo.fetch_prices(ticker)
    return analyze(ticker, prices), prices


def analyze(ticker: str, prices: PriceSeries) -> StockAnalysis:
    """Construit l'analyse complète d'une valeur. Lève yahoo.TickerNotFound si inconnu."""
    last_price = float(prices.raw.iloc[-1])
    identity = yahoo.fetch_identity(ticker, last_price)
    fundamentals = yahoo.fetch_fundamentals(ticker, identity.kind)

    # Rendement continu (dividende, puis dividende + rachats) : série dérivée du
    # cours, calculée en pleine résolution puis décimée comme le cours (même
    # principe que les moyennes mobiles). Seul `services/` voit prix + dividendes.
    if fundamentals is not None and fundamentals.dividend:
        div = fundamentals.dividend
        events = div.get("events") or {}
        # Statistiques de la section Dividende (régularité, CAGR, fréquence,
        # croissance annuelle) : calculées par `engine/dividends` (pur) — source
        # unique, exposée au front via le payload. Le front ne les recalcule pas.
        div["stats"] = dividends_mod.summary(events, div.get("per_share") or {})
        # Rachats d'actions ramenés PAR ACTION : le cash-flow donne des montants
        # TOTAUX (ex. 230 M€), qu'on divise par les actions en circulation de
        # l'exercice — sinon le rendement actionnaire serait aberrant (milliards
        # de %). Le front n'a plus qu'à additionner dividendes + rachats/action.
        div["buybacks_per_share"] = dividends_mod.buybacks_per_share(
            div.get("buyback_history"), _shares_by_year(ticker, fundamentals)
        )
        if events:
            fundamentals.dividend_yield = dividends_mod.rolling_yield_series(
                prices.raw.index, prices.raw, events
            )
            # Shareholder Yield = dividendes + rachats, en % du cours (même calcul
            # que Dividend Yield). Toujours calculé, même sans rachats : la
            # composante rachat vaut alors 0 et la courbe se confond avec le
            # rendement du dividende (continuité voulue).
            fundamentals.shareholder_yield = dividends_mod.rolling_yield_series(
                prices.raw.index,
                prices.raw,
                events,
                extra_by_year=div.get("buybacks_per_share"),
            )

    warnings: list[str] = []

    # Deux régressions : Close (valorisation) et Adj Close (perf passée). Cf. PRD §5.
    reg_raw = reg.fit_log_regression(prices.raw)
    reg_adj = reg.fit_log_regression(prices.adjusted)

    z = reg.distance_sigma(reg_raw, last_price)
    perf = reg_adj.perf_annual * 100
    ecart = reg_raw.ecart_type_size * 100
    pot5 = reg.annualized_potential(reg_raw, last_price, config.POTENTIAL_HORIZONS[0]) * 100
    pot10 = reg.annualized_potential(reg_raw, last_price, config.POTENTIAL_HORIZONS[1]) * 100
    # MM configurables (panneau Paramètres) ; la tendance suit la même règle que
    # le tracé (services/analysis déjà lié à data/cache pour les réglages).
    _settings = cache.get_settings()
    bullish = reg.trend_is_bullish(
        prices.raw, _settings["trend_ma_short"], _settings["trend_ma_long"]
    )

    # Score qualité (depuis les comptes, si dispo).
    quality = None
    if fundamentals is not None:
        qi = quality_inputs(fundamentals.table, identity.kind)
        quality = quality_score(
            qi["roe_mean"],
            qi["roe_last"],
            qi["ca_decline_years"],
            qi["equity_to_assets_pct"],
            identity.kind,
        )
        if fundamentals.available_years < 5:
            warnings.append(f"Comptes : {fundamentals.available_years} an(s) disponibles")

        # Valorisation historique : croisement prix (raw) × comptes. Seul endroit
        # qui voit les deux. Dégradation gracieuse si non calculable.
        if fundamentals.valuation_rows:
            v = valuation_mod.build(fundamentals.table, fundamentals.valuation_rows, prices.raw)
            fundamentals.valuation = v if not v.empty else None
            if fundamentals.valuation is None:
                warnings.append("Valorisation historique indisponible")
        # Séries continues de multiples + ingrédients de la calculatrice :
        # calculés AVANT de libérer `valuation_rows` (les séries d'entreprise
        # lisent les postes bruts EBITDA / dette nette).
        fundamentals.valuation_series = _valuation_series(fundamentals, prices, identity.ticker)
        fundamentals.valuation_calc = _valuation_calc_payload(fundamentals, prices, identity.ticker)
        fundamentals.valuation_rows = None  # données brutes consommées, on libère
    else:
        warnings.append("Comptes indisponibles (yfinance)")

    fair_price, fair_price_note = _fair_price(identity.ticker, prices.raw)
    # Prix juste de la calculatrice ENREGISTRÉ (par titre) : il prime sur la
    # droite de référence dans la synthèse « Résumé » — c'est l'objectif que
    # l'utilisateur s'est fixé. Absent (ou <= 0 : valeur non exploitable) -> on
    # garde la droite. La ligne porte une note « enregistré » pour ne pas la
    # confondre avec le calcul courant.
    saved = cache.get_valuation_settings(identity.ticker)
    saved_fair = float(saved["fair_price"]) if saved and saved.get("fair_price") else None
    if saved_fair is not None and saved_fair > 0:
        fair_price = saved_fair
        fair_price_note = "Prix juste enregistré (calculatrice)"
    summary = summary_fund_mod.build_summary(
        identity=identity,
        fundamentals=fundamentals,
        fitted_now=fair_price,
        quality_score=quality,
        fair_price_note=fair_price_note,
    )

    indicators = Indicators(
        distance_sigma=labels.label_distance_sigma(z),
        perf_passee=labels.label_perf(perf),
        ecart_type=labels.label_ecart_type(ecart),
        potential_5y=labels.label_potential(pot5),
        potential_10y=labels.label_potential(pot10),
        trend=labels.label_trend(bullish),
        quality=labels.label_quality(quality),
    )

    return StockAnalysis(
        identity=identity,
        indicators=indicators,
        regression_raw=reg_raw,
        regression_adj=reg_adj,
        fundamentals=fundamentals,
        warnings=warnings,
        summary=summary,
    )


def analyze_ratio_tickers(
    ticker_a: str, ticker_b: str
) -> tuple[RatioAnalysis, pd.Series, pd.Series, pd.Series]:
    """Analyse d'un ratio A/B à partir des tickers (fetch + analyse).

    Point d'entrée **partagé API ↔ MCP** : les deux séries de prix sont récupérées
    ici (chacune via le cache), puis `analyze_ratio` construit le ratio total
    return. Lève `yahoo.TickerNotFound` si un actif est inconnu, `ValueError` si
    l'historique commun est trop court.

    Renvoie `(analysis, series_ratio, series_a_aligned, series_b_aligned)`.
    """
    prices_a = yahoo.fetch_prices(ticker_a)
    prices_b = yahoo.fetch_prices(ticker_b)
    return analyze_ratio(ticker_a, ticker_b, prices_a, prices_b)


def analyze_ratio(
    ticker_a: str, ticker_b: str, prices_a: PriceSeries, prices_b: PriceSeries
) -> tuple[RatioAnalysis, pd.Series, pd.Series, pd.Series]:
    """Analyse d'un ratio A/B. Lève yahoo.TickerNotFound si un actif est inconnu.

    Le ratio est construit en « total return » (séries dividendes réinvestis des
    deux côtés) pour comparer équitablement un actif distribuant à un capitalisant.
    Mêmes indicateurs prix que pour une action ; trend/quality restent vides.

    Renvoie (analysis, series_ratio, series_a_aligned, series_b_aligned).
    """
    sa, sb = ratio_mod.aligned_pair(prices_a.adjusted, prices_b.adjusted)
    series = sa / sb
    last_ratio = float(series.iloc[-1])

    regression = reg.fit_log_regression(series)
    z = reg.distance_sigma(regression, last_ratio)
    perf = regression.perf_annual * 100
    ecart = regression.ecart_type_size * 100
    pot5 = reg.annualized_potential(regression, last_ratio, config.POTENTIAL_HORIZONS[0]) * 100
    pot10 = reg.annualized_potential(regression, last_ratio, config.POTENTIAL_HORIZONS[1]) * 100

    indicators = Indicators(
        distance_sigma=labels.label_distance_sigma(z),
        perf_passee=labels.label_perf(perf),
        ecart_type=labels.label_ecart_type(ecart),
        potential_5y=labels.label_potential(pot5),
        potential_10y=labels.label_potential(pot10),
        trend=ScoredValue(None, None, None),  # un ratio n'a pas de tendance MM
        quality=ScoredValue(None, None, None),  # ni de qualité d'exploitation
        # β (amplitude) & ρ (solidité du lien) sur tout l'historique commun ;
        # recalculés en live côté front sur la fenêtre du slider.
        beta=labels.label_beta(ratio_mod.beta(sa, sb)),
        correlation=labels.label_correlation(ratio_mod.correlation(sa, sb)),
    )

    warnings: list[str] = []
    years = ratio_mod.common_years(series)
    if years < 20:
        warnings.append(f"Historique commun : {years:.0f} an(s)")

    name_a = (yahoo.fetch_identity(ticker_a, last_ratio).name) or ticker_a.upper()
    name_b = (yahoo.fetch_identity(ticker_b, last_ratio).name) or ticker_b.upper()

    return (
        RatioAnalysis(
            ticker_a=ticker_a.upper(),
            ticker_b=ticker_b.upper(),
            label=f"{name_a} / {name_b}",
            last_ratio=last_ratio,
            indicators=indicators,
            regression=regression,
            warnings=warnings,
        ),
        series,
        sa,
        sb,
    )


def analyze_index(index_id: int, definition: dict) -> tuple[BasketAnalysis, pd.Series]:
    """Analyse complète d'un indice personnalisé à partir de sa définition.

    Point d'entrée **partagé API ↔ MCP** : récupère les prix de chaque membre
    (via le cache) puis chaîne le panier. Lève `yahoo.TickerNotFound` si un
    membre est introuvable, `ValueError` si le panier est trop court.

    `definition` vient de `services/indices.get_index` : `{id, name, category,
    tickers}`. La définition est passée en paramètre (pas re-lue) pour que
    l'appelant garde la main sur le 404 « indice inconnu ».
    """
    members: dict[str, PriceSeries] = {}
    for ticker in definition["tickers"]:
        members[ticker] = yahoo.fetch_prices(ticker)
    return analyze_basket(index_id, definition["name"], definition["category"], members)


def analyze_basket(
    index_id: int, name: str, category: str, members: dict[str, PriceSeries]
) -> tuple[BasketAnalysis, pd.Series]:
    """Analyse d'un indice personnalisé : panier equal-weight chaîné total return.

    `members` : {ticker: PriceSeries complet} — l'ajusté sert à la série de
    l'indice, le brut + l'ajusté aux stats « coup d'œil » de chaque membre
    (position σ, pente, tendance), sans aucun fetch réseau supplémentaire.
    La série synthétique est mise en cache (TTL prix, clé `INDEX:<id>/basket`).

    Mêmes indicateurs prix que pour une action/ratio ; pas de fondamentaux ni de
    β/ρ (un indice n'a pas d'actif de référence). La tendance MM est calculée
    sur la série synthétique (visible dans le résumé et les KPI).
    Renvoie (analysis, series).
    """
    adjusted = {ticker: prices.adjusted for ticker, prices in members.items()}
    frame = basket_mod.aligned_frame(adjusted)
    series = _basket_series(index_id, frame)

    last_value = float(series.iloc[-1])
    regression = reg.fit_log_regression(series)
    z = reg.distance_sigma(regression, last_value)
    perf = regression.perf_annual * 100
    ecart = regression.ecart_type_size * 100
    pot5 = reg.annualized_potential(regression, last_value, config.POTENTIAL_HORIZONS[0]) * 100
    pot10 = reg.annualized_potential(regression, last_value, config.POTENTIAL_HORIZONS[1]) * 100
    _settings = cache.get_settings()

    indicators = Indicators(
        distance_sigma=labels.label_distance_sigma(z),
        perf_passee=labels.label_perf(perf),
        ecart_type=labels.label_ecart_type(ecart),
        potential_5y=labels.label_potential(pot5),
        potential_10y=labels.label_potential(pot10),
        trend=labels.label_trend(
            reg.trend_is_bullish(series, _settings["trend_ma_short"], _settings["trend_ma_long"])
        ),
        quality=ScoredValue(None, None, None),  # pas de qualité d'exploitation
    )

    warnings: list[str] = []
    total = basket_mod.span_years(series)
    if total < 20:
        warnings.append(f"Historique : {total:.0f} an(s)")
    else:
        full = basket_mod.full_coverage_years(frame)
        if full < 20:
            warnings.append(f"Panier complet depuis {full:.0f} an(s) seulement")

    member_rows: list[dict] = []
    for ticker, prices in members.items():
        adjusted_series = prices.adjusted.dropna()
        last_member = float(adjusted_series.iloc[-1]) if len(adjusted_series) else None
        ident = yahoo.fetch_identity(ticker, last_member)
        member_rows.append(
            {
                "ticker": ticker.upper(),
                "name": ident.name,
                **summary_mod.member_stats(
                    prices.raw,
                    prices.adjusted,
                    _settings["trend_ma_short"],
                    _settings["trend_ma_long"],
                ),
            }
        )

    return (
        BasketAnalysis(
            index_id=index_id,
            name=name,
            category=category,
            members=member_rows,
            last_value=last_value,
            indicators=indicators,
            regression=regression,
            warnings=warnings,
        ),
        series,
    )


def summarize_index(index_definition: dict) -> dict:
    """Stats « coup d'œil » d'un indice pour la liste « Mes indices ».

    Repose sur les prix cachés (TTL prix) et la série chaînée cachée : aucun
    réseau si le cache est chaud. Un membre indisponible (ticker introuvable,
    historique trop court…) isole l'indice via le champ `error` — les autres
    indices restent calculés. `stats` vaut None en cas d'erreur.
    """
    index_id = index_definition["id"]
    _settings = cache.get_settings()
    try:
        members = {ticker: yahoo.fetch_prices(ticker) for ticker in index_definition["tickers"]}
        frame = basket_mod.aligned_frame(
            {ticker: prices.adjusted for ticker, prices in members.items()}
        )
        series = _basket_series(index_id, frame)
        stats = summary_mod.index_stats(
            series, _settings["trend_ma_short"], _settings["trend_ma_long"]
        )
    except (yahoo.TickerNotFound, ValueError) as exc:
        return {"index_id": index_id, "stats": None, "error": str(exc)}
    return {"index_id": index_id, "stats": stats, "error": None}


def summarize_indices(definitions: list[dict]) -> list[dict]:
    """Stats de tous les indices passés, dans l'ordre. Chaque erreur est isolée."""
    return [summarize_index(d) for d in definitions]


def _basket_series(index_id: int, frame: pd.DataFrame) -> pd.Series:
    """Série de l'indice, mise en cache TTL prix (clé `INDEX:<id>/basket`).

    La série chaînée est coûteuse à reconstruire (alignement + chaînage) mais
    stable : on la cache pour servir les affichages suivants sans recalcul.
    """
    cached = cache.get(f"INDEX:{index_id}", "basket", config.TTL_PRICES)
    if cached is not None:
        return cached
    series = basket_mod.build_series(frame)
    cache.put(f"INDEX:{index_id}", "basket", series)
    return series
