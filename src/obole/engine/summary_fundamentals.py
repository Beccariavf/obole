"""Synthèse fondamentale de la section « Résumé » (grille de lecture rapide).

Fonctions **pures** (zéro I/O) : on assemble des valeurs déjà extraites par
`data/` en une liste de cartes prêtes à afficher. Aucun seuil n'est défini ici :
les couleurs viennent de `config.SUMMARY_COLORS` (source unique, exposée au front
par `/api/meta`).

Règles invariantes :
- une valeur non calculable vaut `None` (le front affiche « -- »), jamais 0 ;
- un dénominateur nul ou négatif rend le ratio absent (jamais d'infini) ;
- un horizon de croissance non couvert par l'historique n'est pas extrapolé ;
- les modèles Altman Z et Piotroski ne s'appliquent qu'aux entreprises
  industrielles/commerciales : pour une financière, ils restent absents.
"""

from __future__ import annotations

import pandas as pd

from obole import config
from obole.engine import dividends as dividends_mod
from obole.models import CompanyKind, Fundamentals, Identity, SummaryCard, SummaryRow


def _good(key: str, value: float | None) -> bool | None:
    """Polarité couleur d'une ligne, depuis `config.SUMMARY_COLORS` (source unique)."""
    spec = config.SUMMARY_COLORS.get(key)
    if value is None or spec is None:
        return None
    sens, seuil = spec
    if seuil is None:
        return None
    if sens == "ge":
        return value >= seuil
    if sens == "le":
        return value <= seuil
    if sens == "le_pos":
        return 0 < value <= seuil
    return None


def _row(
    key: str,
    label: str,
    value: float | None,
    unit: str = "num",
    text: str | None = None,
    note: str | None = None,
) -> SummaryRow:
    """Construit une ligne ; la couleur est déduite de `config.SUMMARY_COLORS`."""
    if text is None and value is None:
        return SummaryRow(key=key, label=label, value=None, unit=unit, good=None, note=note)
    numeric = float(value) if value is not None else None
    return SummaryRow(
        key=key,
        label=label,
        value=numeric,
        unit=unit,
        text=text,
        good=_good(key, numeric),
        note=note,
    )


def _positive_row(key: str, label: str, value: float | None) -> SummaryRow:
    """Ligne d'un multiple : neutralisée si la valeur est nulle ou négative.

    Un P/E, P/FCF, P/S ou P/B ≤ 0 (bénéfice négatif, capitaux propres négatifs)
    n'est pas interprétable : on affiche « -- » plutôt qu'un nombre trompeur.
    """
    return _row(key, label, value if (value is not None and value > 0) else None, "num")


# --- Accès défensifs au tableau de comptes ----------------------------------


def _latest(table: pd.DataFrame | None, name: str) -> float | None:
    """Dernière valeur (année la plus récente) d'une ligne, ou None."""
    if table is None or table.empty or name not in table.index:
        return None
    series = table.loc[name].dropna()
    return float(series.iloc[0]) if len(series) else None


def _mean_last(table: pd.DataFrame | None, name: str, years: int) -> float | None:
    """Moyenne des `years` valeurs les plus récentes d'une ligne, ou None."""
    if table is None or table.empty or name not in table.index:
        return None
    series = table.loc[name].dropna()
    if not len(series):
        return None
    return float(series.iloc[:years].mean())


def _ratio(num: float | None, den: float | None, scale: float = 1.0) -> float | None:
    """num/den × scale, ou None si un opérande manque ou si le dénominateur est nul."""
    if num is None or den is None or den == 0:
        return None
    return num / den * scale


def _growth(by_year: dict[int, float] | None, years: int) -> float | None:
    """Croissance sur `years` ans, en % : variation simple si 1 an, CAGR au-delà.

    `by_year` = {année: valeur}. Renvoie None si l'historique est trop court ou si
    un point terminal est nul/négatif (un CAGR n'a pas de sens sur une base
    négative — cf. PRD §4). L'horizon n'est jamais extrapolé.
    """
    if not by_year:
        return None
    ordered = sorted(by_year, reverse=True)
    if len(ordered) <= years:
        return None
    recent = by_year[ordered[0]]
    past = by_year[ordered[years]]
    if years == 1:
        if past == 0:
            return None
        return (recent / past - 1) * 100
    if past <= 0 or recent <= 0:
        return None
    return ((recent / past) ** (1 / years) - 1) * 100


def _by_year(series: pd.Series | None) -> dict[int, float]:
    """Série indexée par Timestamp (comptes bruts) ou par année -> {année: valeur}.

    Les lignes du tableau de comptes sont indexées par année (int) ; les postes
    bruts de santé par Timestamp de clôture. On accepte les deux.
    """
    if series is None:
        return {}
    out: dict[int, float] = {}
    for key, value in series.items():
        if pd.isna(value):
            continue
        year = key.year if hasattr(key, "year") else int(key)
        out[year] = float(value)
    return out


# --- Cartes -----------------------------------------------------------------


def _profil_card(identity: Identity, quality: float | None) -> SummaryCard:
    rows = [
        _row("country", "Pays", None, "text", text=identity.country),
        _row("website", "Site internet", None, "text", text=identity.website),
        _row("sector", "Secteur", None, "text", text=identity.sector),
        _row("industry", "Industrie", None, "text", text=identity.industry),
    ]
    note = round(quality / 5, 1) if quality is not None else None
    rows.append(_row("quality_score", "Note quantitative", note, "score"))
    return SummaryCard(id="profil", title="Profil", rows=rows)


def _market_card(identity: Identity) -> SummaryCard:
    cap = identity.market_cap
    category = None
    if cap is not None:
        for lower, label in config.MARKET_CAP_LABELS:
            if cap >= lower:
                category = label
                break
    low, high = identity.week52_low, identity.week52_high
    rng = f"{low:.2f} – {high:.2f}" if low is not None and high is not None else None
    rows = [
        _row("cap_category", "Catégorie", None, "text", text=category),
        _row("market_cap", "Capitalisation", cap, "money"),
        _row("beta", "Bêta", identity.beta, "num"),
        _row("week52", "Range 52S", None, "text", text=rng),
        _row("volume", "Volume", identity.volume, "num"),
        _row("avg_volume", "Volume moyen", identity.avg_volume, "num"),
    ]
    return SummaryCard(id="marche", title="Marché", rows=rows)


def _latest_valuation(fundamentals: Fundamentals | None, name: str) -> float | None:
    """Dernière valeur d'une ligne de multiples (PER, P/FCF…) reconstruits."""
    if fundamentals is None or fundamentals.valuation is None:
        return None
    table = fundamentals.valuation
    if table.empty or name not in table.index:
        return None
    series = table.loc[name].dropna()
    return float(series.iloc[0]) if len(series) else None


def _valuation_card(
    fundamentals: Fundamentals | None,
    market: dict | None,
    fitted_now: float | None,
    last_price: float | None,
    fair_price_saved: bool = False,
) -> SummaryCard:
    """Valorisation : prix juste (droite 20 ans) vs cours, puis les multiples.

    « Prix juste » = valeur de la droite de régression sur les 20 dernières années
    (cours brut, série de la valorisation) ; « Prix communiqué » = dernier cours.
    C'est une lecture de tendance longue à comparer au cours — elle ne se confond
    PAS avec le KPI « distance σ », calculé sur l'historique complet (méthode
    Obole, PRD §5). Les deux lignes rendent l'écart lisible, sans dupliquer le
    calcul de σ.

    `fair_price_saved` : le prix juste affiché vient de la calculatrice de la
    section Valorisation (enregistré par l'utilisateur) et non de la droite.
    La ligne porte alors une note « enregistré » pour expliquer l'écart éventuel
    avec le calcul courant de la calculatrice.

    Les multiples sont **neutralisés** (None -> « -- ») quand leur dénominateur
    est nul ou négatif (P/B négatif = capitaux propres négatifs, P/E ou P/FCF
    sur base négative) : jamais de nombre trompeur.
    """
    market = market or {}
    cap = market.get("market_cap")
    rows = [
        _row(
            "fair_price",
            "Prix juste",
            fitted_now,
            "money",
            note="Prix juste enregistré (calculatrice)" if fair_price_saved else None,
        ),
        _row("price", "Prix communiqué", last_price, "money"),
        _positive_row("per", "P/E", market.get("trailing_pe")),
        _positive_row("forward_per", "Forward P/E", market.get("forward_pe")),
        _positive_row("p_fcf", "P/FCF", _latest_valuation(fundamentals, "P/FCF")),
        _positive_row("p_ocf", "P/OCF", _ratio(cap, market.get("ocf"))),
        _positive_row("p_s", "P/S", market.get("price_to_sales")),
        _positive_row("p_b", "P/B", market.get("price_to_book")),
    ]
    return SummaryCard(id="valorisation", title="Valorisation", rows=rows)


def _dividend_card(fundamentals: Fundamentals | None, market: dict | None) -> SummaryCard:
    market = market or {}
    div = fundamentals.dividend if fundamentals else None
    per_share = (div or {}).get("per_share") or {}
    by_year = {int(y): float(v) for y, v in per_share.items()}
    rows = [
        _row("div_yield", "Yield (TTM)", (div or {}).get("yield_pct"), "pct"),
        _row("div_rate", "Dividende annuel", market.get("dividend_rate"), "money"),
        _row("payout_fy", "Payout ratio (FY)", (div or {}).get("payout_pct"), "pct"),
        _row("div_growth_years", "Années d'augmentation", _increase_years(by_year), "years"),
    ]
    for h in config.SUMMARY_GROWTH_HORIZONS:
        rows.append(_row(f"div_cagr_{h}y", f"Div {h}A", _growth(by_year, h), "pct"))
    return SummaryCard(id="dividende", title="Dividende", rows=rows)


def _increase_years(by_year: dict[int, float]) -> float | None:
    """Années consécutives de hausse du dividende — délègue à `engine.dividends`.

    Source unique : la même fonction alimente la section Dividende et la synthèse.
    """
    return dividends_mod.increase_years(by_year)


def _growth_cells(
    table: pd.DataFrame | None, metric: str, prefix: str, future: float | None
) -> tuple[list[float | None], list[bool | None]]:
    """Valeurs + polarité d'une ligne de croissance, alignées sur les colonnes.

    Colonnes : un horizon par entrée de `config.SUMMARY_GROWTH_HORIZONS` (1A =
    variation simple, au-delà = CAGR) puis le consensus analystes (« Futur »). Un
    horizon non couvert par l'historique reste `None` (le front affiche « -- »),
    jamais extrapolé. La polarité vient de `config.SUMMARY_COLORS` (source unique).
    """
    series = (
        table.loc[metric]
        if (table is not None and not table.empty and metric in table.index)
        else None
    )
    by_year = _by_year(series)
    values: list[float | None] = []
    goods: list[bool | None] = []
    for h in config.SUMMARY_GROWTH_HORIZONS:
        value = _growth(by_year, h)
        values.append(value)
        # Clés de couleur alignées sur `config.SUMMARY_COLORS` : 1 an = « growth »,
        # au-delà = « cagr » (sinon la polarité ne s'applique pas).
        key = f"{prefix}_growth_1y" if h == 1 else f"{prefix}_cagr_{h}y"
        goods.append(_good(key, value))
    values.append(future)
    goods.append(_good(f"{prefix}_future", future))
    return values, goods


def _growth_card(
    table: pd.DataFrame | None,
    revenue_future: float | None,
    eps_future: float | None,
) -> SummaryCard:
    """Carte MATRICE « Croissance » : lignes CA/EPS, colonnes 1A/5A/10A/Futur.

    CA et EPS partagent les mêmes horizons : les présenter côte à côte (deux
    lignes d'une même carte) rend la comparaison directe et économise une carte
    par rapport à deux cartes jumelles. Chaque ligne porte ses `cells` (valeurs)
    et `cell_good` (polarité par cellule).
    """
    ca_values, ca_goods = _growth_cells(table, "Chiffre d'affaires", "rev", revenue_future)
    eps_values, eps_goods = _growth_cells(table, "BNPA dilué", "eps", eps_future)
    columns = [f"{h}A" for h in config.SUMMARY_GROWTH_HORIZONS] + ["Futur"]
    rows = [
        SummaryRow(key="ca", label="CA", unit="pct", cells=ca_values, cell_good=ca_goods),
        SummaryRow(key="eps", label="EPS", unit="pct", cells=eps_values, cell_good=eps_goods),
    ]
    return SummaryCard(id="croissance", title="Croissance", columns=columns, rows=rows)


def _margins_card(fundamentals: Fundamentals | None, health: dict | None) -> SummaryCard:
    table = fundamentals.table if fundamentals else None
    revenue = _latest(table, "Chiffre d'affaires")
    fcf = _latest(table, "Free Cash Flow")
    capex = _by_year((health or {}).get("capex"))
    capex_latest = capex[max(capex)] if capex else None
    rows = [
        _row("gross_margin", "Marge brute", _latest(table, "Marge brute"), "pct"),
        _row("op_margin", "Marge opé.", _latest(table, "Marge opérationnelle"), "pct"),
        _row("net_margin", "Marge nette", _latest(table, "Marge nette"), "pct"),
        _row("fcf_margin", "Marge FCF", _ratio(fcf, revenue, 100), "pct"),
        # %CAPEX/CA : intensité capitalistique = |CAPEX| / chiffre d'affaires.
        _row(
            "capex_sales",
            "CAPEX / CA",
            _ratio(abs(capex_latest) if capex_latest is not None else None, revenue, 100),
            "pct",
        ),
    ]
    return SummaryCard(id="marges", title="Marges", rows=rows)


def _roic_series(health: dict | None) -> pd.Series | None:
    """ROIC = EBIT × (1 − taux d'impôt) / capital investi, par exercice."""
    if not health:
        return None
    ebit = _by_year(health.get("ebit"))
    invested = _by_year(health.get("invested_capital"))
    tax = _by_year(health.get("tax_rate"))
    out: dict[int, float] = {}
    for year, ebit_v in ebit.items():
        capital = invested.get(year)
        if capital is None or capital <= 0:
            continue
        rate = tax.get(year, 0.25)
        out[year] = ebit_v * (1 - rate) / capital * 100
    if not out:
        return None
    return pd.Series(out).sort_index(ascending=False)


def _profitability_card(fundamentals: Fundamentals | None, health: dict | None) -> SummaryCard:
    """Rentabilité : ROE/ROCE/ROIC en dernier exercice (1A) et moyenne 5 ans.

    Le ROIC est reconstruit (EBIT net d'impôt / capital investi) ; le ROE et le
    ROCE viennent du tableau de comptes normalisé.
    """
    table = fundamentals.table if fundamentals else None
    roic = _roic_series(health)
    roic_5y = float(roic.iloc[:5].mean()) if roic is not None and len(roic) else None
    roic_1y = float(roic.iloc[0]) if roic is not None and len(roic) else None
    rows = [
        _row("roe_1y", "ROE 1A", _latest(table, "ROE"), "pct"),
        _row("roce_1y", "ROCE 1A", _latest(table, "ROCE"), "pct"),
        _row("roic_1y", "ROIC 1A", roic_1y, "pct"),
        _row("roe_5y", "ROE 5A", _mean_last(table, "ROE", 5), "pct"),
        _row("roce_5y", "ROCE 5A", _mean_last(table, "ROCE", 5), "pct"),
        _row("roic_5y", "ROIC 5A", roic_5y, "pct"),
    ]
    return SummaryCard(id="rentabilite", title="Rentabilité", rows=rows)


def _altman_z(health: dict | None, market_cap: float | None) -> float | None:
    """Altman Z-Score (modèle manufacturier) : None si un poste manque.

    Z = 1.2·X1 + 1.4·X2 + 3.3·X3 + 0.6·X4 + 0.999·X5. On ne calcule pas de score
    partiel (cf. data-and-design §6) : il faut les 5 entrées.
    """
    if not health:
        return None
    latest = {
        k: _by_year(health.get(k))
        for k in (
            "working_capital",
            "retained_earnings",
            "ebit",
            "total_assets",
            "total_liabilities",
            "revenue",
        )
    }
    if any(not latest[k] for k in latest):
        return None
    year = max(latest["total_assets"])
    ta = latest["total_assets"].get(year)
    tl = latest["total_liabilities"].get(year)
    if ta is None or ta == 0 or tl is None or tl == 0 or market_cap is None:
        return None
    x1 = latest["working_capital"].get(year)
    x2 = latest["retained_earnings"].get(year)
    x3 = latest["ebit"].get(year)
    x5 = latest["revenue"].get(year)
    if x1 is None or x2 is None or x3 is None or x5 is None:
        return None
    return 1.2 * x1 / ta + 1.4 * x2 / ta + 3.3 * x3 / ta + 0.6 * market_cap / tl + 0.999 * x5 / ta


def _piotroski(health: dict | None) -> float | None:
    """Piotroski F-Score (0-9) sur les deux exercices les plus récents.

    None si un critère n'est pas évaluable (donnée manquante) : on préfère
    l'absence à un score partiel présenté comme complet.
    """
    if not health:
        return None
    net_income = _by_year(health.get("net_income"))
    ocf = _by_year(health.get("ocf"))
    total_assets = _by_year(health.get("total_assets"))
    long_term_debt = _by_year(health.get("long_term_debt"))
    current_assets = _by_year(health.get("current_assets"))
    current_liabilities = _by_year(health.get("current_liabilities"))
    shares = _by_year(health.get("shares"))
    gross_profit = _by_year(health.get("gross_profit"))
    revenue = _by_year(health.get("revenue"))

    if not total_assets or len(total_assets) < 2:
        return None
    years = sorted(total_assets, reverse=True)
    y0, y1 = years[0], years[1]

    def _get(d: dict[int, float], year: int) -> float | None:
        return d.get(year)

    ni0, ni1 = _get(net_income, y0), _get(net_income, y1)
    ta0, ta1 = _get(total_assets, y0), _get(total_assets, y1)
    if ni0 is None or ni1 is None or ta0 is None or ta1 is None or ta0 == 0 or ta1 == 0:
        return None
    ocf0 = _get(ocf, y0)
    if ocf0 is None:
        return None

    score = 0
    score += 1 if ni0 > 0 else 0
    score += 1 if ocf0 > 0 else 0
    score += 1 if ni0 / ta0 > ni1 / ta1 else 0
    score += 1 if ocf0 > ni0 else 0

    ltd0, ltd1 = _get(long_term_debt, y0), _get(long_term_debt, y1)
    if ltd0 is None or ltd1 is None:
        return None
    score += 1 if ltd0 < ltd1 else 0

    ca0, ca1 = _get(current_assets, y0), _get(current_assets, y1)
    cl0, cl1 = _get(current_liabilities, y0), _get(current_liabilities, y1)
    if ca0 is None or ca1 is None or cl0 is None or cl1 is None or cl0 == 0 or cl1 == 0:
        return None
    score += 1 if ca0 / cl0 > ca1 / cl1 else 0

    sh0, sh1 = _get(shares, y0), _get(shares, y1)
    if sh0 is None or sh1 is None:
        return None
    score += 1 if sh0 <= sh1 else 0

    gp0, gp1 = _get(gross_profit, y0), _get(gross_profit, y1)
    rev0, rev1 = _get(revenue, y0), _get(revenue, y1)
    if gp0 is None or gp1 is None or rev0 is None or rev1 is None or rev0 == 0 or rev1 == 0:
        return None
    score += 1 if gp0 / rev0 > gp1 / rev1 else 0
    score += 1 if rev0 / ta0 > rev1 / ta1 else 0

    return float(score)


def _health_card(
    fundamentals: Fundamentals | None,
    health: dict | None,
    market: dict | None,
    market_cap: float | None,
    kind: CompanyKind,
) -> SummaryCard:
    market = market or {}
    table = fundamentals.table if fundamentals else None
    financial = kind is CompanyKind.FINANCIAL

    op_income = _by_year((health or {}).get("operating_income"))
    interest = _by_year((health or {}).get("interest_expense"))
    interest_coverage = None
    # Année la plus récente où les DEUX postes existent : `Interest Expense` est
    # souvent absent des exercices récents chez Yahoo (on ne force pas une année
    # vide, on ne mélange pas non plus deux exercices).
    common_years = sorted(set(op_income) & set(interest), reverse=True)
    for year in common_years:
        exp = interest.get(year)
        op = op_income.get(year)
        if exp is not None and exp != 0 and op is not None:
            interest_coverage = op / abs(exp)
            break

    goodwill = _by_year((health or {}).get("goodwill"))
    total_assets = _by_year((health or {}).get("total_assets"))
    goodwill_assets = None
    if goodwill and total_assets:
        year = max(total_assets)
        gw, ta = goodwill.get(year), total_assets.get(year)
        if gw is not None and ta:
            goodwill_assets = gw / ta * 100

    shares = _by_year((health or {}).get("shares"))
    shares_change = _growth(shares, 3)

    altman = None if financial else _altman_z(health, market_cap)
    piotroski = None if financial else _piotroski(health)
    # Infobulle explicative : les deux modèles ne s'appliquent pas aux financières.
    note = config.FINANCIAL_NOT_APPLICABLE if financial else None

    rows = [
        _row(
            "net_debt_ebitda", "Dette nette/EBITDA", _latest(table, "Dette nette / EBITDA"), "num"
        ),
        _row("interest_coverage", "Interest Coverage", interest_coverage, "num"),
        _row("goodwill_assets", "Goodwill/Assets", goodwill_assets, "pct"),
        _row("shares_change_3y", "Actions en circulation 3A", shares_change, "pct"),
        _row("altman_z", "Altman Z-Score", altman, "num", note=note),
        _row("piotroski", "Piotroski Score", piotroski, "num", note=note),
    ]
    return SummaryCard(id="sante", title="Santé", rows=rows)


def build_summary(
    identity: Identity,
    fundamentals: Fundamentals | None,
    fitted_now: float | None,
    quality_score: float | None,
    fair_price_saved: bool = False,
) -> list[SummaryCard]:
    """Grille de synthèse complète (8 cartes) pour la section « Résumé ».

    `identity` porte les données de marché (capi, bêta, 52 semaines, volumes),
    `fundamentals` les comptes/dividendes et les postes bruts de santé,
    `fitted_now` la valeur de la droite de régression (prix juste) et
    `quality_score` le score qualité 0-100 déjà calculé par `engine/quality`.
    `fair_price_saved` signale un prix juste issu de la calculatrice (enregistré) :
    la ligne « Prix juste » porte alors une note explicative.
    Une carte dont aucune ligne n'est renseignée est conservée (le front affiche
    « -- ») : la grille garde une structure stable d'un titre à l'autre.
    """
    market = fundamentals.market if fundamentals else None
    health = fundamentals.health_rows if fundamentals else None
    estimates = (fundamentals.estimates if fundamentals else None) or {}
    market_cap = identity.market_cap or (market or {}).get("market_cap")
    kind = identity.kind

    return [
        _profil_card(identity, quality_score),
        _market_card(identity),
        _valuation_card(fundamentals, market, fitted_now, identity.last_price, fair_price_saved),
        _dividend_card(fundamentals, market),
        _growth_card(
            fundamentals.table if fundamentals else None,
            estimates.get("revenue_growth"),
            estimates.get("eps_growth"),
        ),
        _margins_card(fundamentals, health),
        _profitability_card(fundamentals, health),
        _health_card(fundamentals, health, market, market_cap, kind),
    ]
