"""Extraction et normalisation des comptes yfinance.

Deux schémas (PRD §4.7) : industriel/commercial (défaut) vs financier (banque).
Tout accès aux postes est défensif : un poste manquant -> None, jamais de crash.
"""

from __future__ import annotations

import pandas as pd

from obole import config
from obole.models import CompanyKind

# Noms des métriques du schéma INDUSTRIEL, depuis la taxonomie unique
# (`config.FUNDAMENTAL_METRICS`) : la construction du tableau et le recalcul
# après saisie manuelle itèrent sur ces mêmes listes (aucune métrique en dur).
_INDUSTRIAL_SOURCE = [name for name, role in config.FUNDAMENTAL_METRICS if role == "source"]
_INDUSTRIAL_DERIVED = [name for name, role in config.FUNDAMENTAL_METRICS if role == "derived"]


def _row(df: pd.DataFrame, name: str) -> pd.Series | None:
    """Récupère une ligne d'un DataFrame yfinance, ou None si absente."""
    if df is None or df.empty or name not in df.index:
        return None
    return df.loc[name]


def _first_row(df: pd.DataFrame, *names: str) -> pd.Series | None:
    """Premier poste disponible parmi plusieurs noms candidats (évite `or` sur Series)."""
    for name in names:
        r = _row(df, name)
        if r is not None:
            return r
    return None


def _div(num, den, scale: float = 1.0):
    """Division tolérante : None si un opérande manque ou si le dénominateur est nul.

    Fonctionne sur scalaires ET sur `pd.Series` (cas de `build_table`) — pour une
    Series, les zéros deviennent NA, jamais de division par zéro.
    """
    if num is None or den is None:
        return None
    if isinstance(den, pd.Series):
        den = den.replace(0, pd.NA)
    elif den == 0:
        return None
    return num / den * scale


def _absv(x):
    """Valeur absolue d'une Series ou d'un scalaire."""
    return x.abs() if isinstance(x, pd.Series) else abs(x)


def _derive(name: str, get):
    """Calcule une métrique DÉRIVÉE depuis un accesseur de postes `get(cle)`.

    `get` renvoie un scalaire (recalcul après saisie manuelle) ou une `pd.Series`
    (construction du tableau), ou None si le poste est absent. Les clés internes
    (préfixées `_`) désignent des postes NON exposés comme lignes du tableau
    (EBIT, total actif, capital investi, intérêts…) : elles ne sont donc pas
    accessibles au recalcul issu de la seule saisie manuelle, et la métrique est
    alors laissée inchangée (jamais écrasée par un None).
    """
    if name == "Marge brute":
        return _div(get("_gross_profit"), get("Chiffre d'affaires"), 100)
    if name == "Marge opérationnelle":
        return _div(get("Résultat opérationnel"), get("Chiffre d'affaires"), 100)
    if name == "Marge nette":
        return _div(get("Bénéfice net"), get("Chiffre d'affaires"), 100)
    if name == "ROE":
        return _div(get("Bénéfice net"), get("Capitaux propres"), 100)
    if name == "ROA":
        return _div(get("Bénéfice net"), get("_total_assets"), 100)
    if name == "ROCE":
        return _div(get("_ebit"), get("_invested_capital"), 100)
    if name == "ROIC":
        # ROIC = Résultat opérationnel × (1 − taux d'impôt) / capital investi.
        # Taux d'impôt absent -> hypothèse 25 % (défaut fiscal usuel).
        op = get("Résultat opérationnel")
        if op is None:
            return None
        tax = get("_tax_rate")
        effective_tax = 0.25 if tax is None else tax
        return _div(op * (1 - effective_tax), get("_invested_capital"), 100)
    if name == "Cash conversion":
        return _div(get("Free Cash Flow"), get("Bénéfice net"), 100)
    if name == "Agilité":
        # CAPEX est stocké en valeur absolue (sortie de cash) -> pas de re-abs.
        return _div(get("Free Cash Flow"), get("CAPEX"), 100)
    if name == "Capitaux propres / Total bilan":
        return _div(get("Capitaux propres"), get("_total_assets"), 100)
    if name == "Dette nette / EBITDA":
        return _div(get("Dette nette"), get("EBITDA"))
    if name == "Gearing":
        return _div(get("Dette nette"), get("Capitaux propres"), 100)
    if name == "Liquidité":
        return _div(get("_current_assets"), get("_current_liabilities"))
    if name == "Couverture des intérêts":
        interest = get("_interest")
        if interest is None:
            return None
        return _div(get("Résultat opérationnel"), _absv(interest))
    if name == "BFR / CA":
        return _div(get("BFR (working capital)"), get("Chiffre d'affaires"), 100)
    return None


def build_table(
    financials: pd.DataFrame,
    balance_sheet: pd.DataFrame,
    cashflow: pd.DataFrame,
    kind: CompanyKind,
) -> pd.DataFrame:
    """Construit le tableau de comptes normalisé (colonnes = années, du + récent au + ancien).

    Renvoie un DataFrame avec un sous-ensemble de métriques selon le schéma.
    Les métriques indisponibles sont simplement absentes (gérées en aval -> N/A).
    """
    revenue = _row(financials, "Total Revenue")
    net_income = _row(financials, "Net Income")
    op_income = _row(financials, "Operating Income")
    ebitda = _row(financials, "EBITDA")
    gross_profit = _row(financials, "Gross Profit")
    ebit = _row(financials, "EBIT")
    interest_expense = _row(financials, "Interest Expense")
    diluted_eps = _row(financials, "Diluted EPS")
    equity = _first_row(
        balance_sheet, "Stockholders Equity", "Total Equity Gross Minority Interest"
    )
    total_assets = _row(balance_sheet, "Total Assets")
    net_debt = _row(balance_sheet, "Net Debt")
    invested_capital = _row(balance_sheet, "Invested Capital")
    working_capital = _row(balance_sheet, "Working Capital")
    current_assets = _row(balance_sheet, "Current Assets")
    current_liabilities = _row(balance_sheet, "Current Liabilities")
    cash = _row(balance_sheet, "Cash And Cash Equivalents")
    total_debt = _row(balance_sheet, "Total Debt")
    shares = _first_row(balance_sheet, "Ordinary Shares Number", "Share Issued")
    tax_rate = _row(financials, "Tax Rate For Calcs")
    op_cashflow = _row(cashflow, "Operating Cash Flow")
    fcf = _row(cashflow, "Free Cash Flow")
    capex = _row(cashflow, "Capital Expenditure")
    sbc = _row(cashflow, "Stock Based Compensation")

    data: dict[str, pd.Series] = {}

    if kind is CompanyKind.FINANCIAL:
        # Schéma bancaire : postes propres, sans CA/marge op.
        sources = {
            "Total de l'actif": total_assets,
            "Actif net": equity,
            "Bénéfice net": net_income,
        }
        for name, series in sources.items():
            if series is not None:
                data[name] = series
        # Getter depuis les données déjà posées (Series) : ROA/ROE se dérivent de
        # « Bénéfice net » / « Total de l'actif » / « Actif net ». `_total_assets`
        # et « Capitaux propres » (alias d'« Actif net ») sont câblés pour que la
        # dérivation financière partage EXACTEMENT les formules du recalcul manuel.
        getter = lambda key: {  # noqa: E731 — accesseur de postes dérivés
            "Bénéfice net": data.get("Bénéfice net"),
            "_total_assets": data.get("Total de l'actif"),
            "Capitaux propres": data.get("Actif net"),
        }.get(key)
        for name, role in config.FINANCIAL_METRICS:
            if role != "derived":
                continue
            value = _derive(name, getter)
            if value is not None:
                data[name] = value
    else:
        # Schéma industriel/commercial.
        # -- Croissance --
        if revenue is not None:
            data["Chiffre d'affaires"] = revenue
        if op_income is not None:
            data["Résultat opérationnel"] = op_income
        if net_income is not None:
            data["Bénéfice net"] = net_income
        if diluted_eps is not None:
            data["BNPA dilué"] = diluted_eps
        if ebitda is not None:
            data["EBITDA"] = ebitda
        # -- Résultat & cash (source) --
        if equity is not None:
            data["Capitaux propres"] = equity
        if net_debt is not None:
            data["Dette nette"] = net_debt
        if total_debt is not None:
            # Dette brute (avant trésorerie) : opposée à la trésorerie dans la
            # carte « Cash & Dette » pour lire la structure de financement.
            data["Dette brute"] = total_debt
        if cash is not None:
            data["Trésorerie"] = cash
        if shares is not None:
            # Nombre d'actions en circulation (fin d'exercice) : sert la carte
            # « Actions en circulation » (dilution vs rachats).
            data["Actions en circulation"] = shares
        if working_capital is not None:
            data["BFR (working capital)"] = working_capital
        if op_cashflow is not None:
            data["Cash-flow d'exploitation"] = op_cashflow
        if fcf is not None:
            data["Free Cash Flow"] = fcf
        if capex is not None:
            # CAPEX (investissements) : sortie de cash, souvent négative chez
            # Yahoo -> valeur absolue pour un affichage lisible (et l'Agilité).
            data["CAPEX"] = capex.abs()
        if sbc is not None:
            # Rémunération en actions (dilution non cash) : coût réel pour
            # l'actionnaire, à suivre en parallèle des rachats.
            data["SBC"] = sbc.abs()

        # -- Ratios dérivés : calculés par la fonction unique `_derive`, sur les
        # MÊMES postes que le recalcul après saisie manuelle (source unique des
        # formules). `_ebit`, `_total_assets`, `_invested_capital`, `_interest`
        # et `_tax_rate` sont des postes internes NON exposés comme lignes.
        internal = {
            "Chiffre d'affaires": revenue,
            "Bénéfice net": net_income,
            "Résultat opérationnel": op_income,
            "EBITDA": ebitda,
            "Capitaux propres": equity,
            "Dette nette": net_debt,
            "Free Cash Flow": fcf,
            "CAPEX": data.get("CAPEX"),
            "BFR (working capital)": working_capital,
            "_gross_profit": gross_profit,
            "_total_assets": total_assets,
            "_ebit": ebit,
            "_invested_capital": invested_capital,
            "_current_assets": current_assets,
            "_current_liabilities": current_liabilities,
            "_interest": interest_expense,
            "_tax_rate": tax_rate,
        }
        getter = lambda key: internal.get(key)  # noqa: E731 — accesseur de postes dérivés
        for name in _INDUSTRIAL_DERIVED:
            value = _derive(name, getter)
            if value is not None:
                data[name] = value

    if not data:
        return pd.DataFrame()
    table = pd.DataFrame(data).T  # lignes = métriques, colonnes = années
    table.columns = [c.year for c in table.columns]
    # Ordre des lignes : celui de la taxonomie (source puis dérivé), pour un CSV
    # et un affichage stables. Les lignes hors taxonomie (postes internes d'un
    # merge manuel) restent en fin, dans leur ordre d'insertion.
    ordered = [m for m in (*_INDUSTRIAL_SOURCE, *_INDUSTRIAL_DERIVED) if m in table.index]
    if kind is CompanyKind.FINANCIAL:
        fin_order = [m for m, _role in config.FINANCIAL_METRICS]
        ordered = [m for m in fin_order if m in table.index]
    extra = [m for m in table.index if m not in ordered]
    return table.reindex(ordered + extra)


def quality_inputs(table: pd.DataFrame, kind: CompanyKind) -> dict:
    """Extrait les entrées du score qualité depuis le tableau normalisé.

    Renvoie roe_mean, roe_last, ca_decline_years, equity_to_assets_pct.
    """
    out: dict[str, float | int | None] = {
        "roe_mean": None,
        "roe_last": None,
        "ca_decline_years": None,
        "equity_to_assets_pct": None,
    }
    if table.empty:
        return out

    if "ROE" in table.index:
        roe = table.loc["ROE"].dropna()
        if len(roe):
            out["roe_mean"] = float(roe.mean())
            out["roe_last"] = float(roe.iloc[0])  # colonne 0 = année la plus récente

    rev_key = "Total de l'actif" if kind is CompanyKind.FINANCIAL else "Chiffre d'affaires"
    if rev_key in table.index:
        rev = table.loc[rev_key].dropna()
        # années de baisse : on compare chaque année à la précédente (ordre chronologique)
        chrono = rev.iloc[::-1]
        declines = int((chrono.diff() < 0).sum())
        out["ca_decline_years"] = declines

    if kind is not CompanyKind.FINANCIAL and "Capitaux propres / Total bilan" in table.index:
        ratio = table.loc["Capitaux propres / Total bilan"].dropna()
        if len(ratio):
            out["equity_to_assets_pct"] = float(ratio.iloc[0])

    return out


def cagr(series: pd.Series, years: int) -> float | None:
    """Taux de croissance annuel moyen sur `years` ans, en %.

    `series` est une ligne du tableau (colonnes = années, la 0 = la plus récente).
    Renvoie None si l'historique est trop court ou si le point de départ est <= 0
    (un CAGR n'a pas de sens sur une base négative ou nulle).
    """
    s = series.dropna()
    if len(s) <= years:
        return None
    recent = float(s.iloc[0])
    past = float(s.iloc[years])
    if past <= 0 or recent <= 0:
        return None
    return ((recent / past) ** (1 / years) - 1) * 100


def growth_inputs(table: pd.DataFrame, kind: CompanyKind) -> dict:
    """CAGR (3 et 5 ans) du CA, du BNPA et du FCF, en %.

    Clés : 'cagr_revenue_3y', 'cagr_revenue_5y', 'cagr_eps_3y', … (None si N/A).
    Pas de croissance pour les financières (pas de CA dans leur schéma).
    """
    out: dict[str, float | None] = {}
    if kind is CompanyKind.FINANCIAL or table.empty:
        return out

    series_by_key = {
        "revenue": "Chiffre d'affaires",
        "eps": "BNPA dilué",
        "fcf": "Free Cash Flow",
    }
    for key, metric in series_by_key.items():
        for h in config.CAGR_HORIZONS:
            out[f"cagr_{key}_{h}y"] = cagr(table.loc[metric], h) if metric in table.index else None
    return out


def valuation_rows(
    financials: pd.DataFrame,
    balance_sheet: pd.DataFrame,
    cashflow: pd.DataFrame,
) -> dict[str, pd.Series]:
    """Postes BRUTS (non normalisés en %) requis par engine/valuation.build.

    Indexés par Timestamp de clôture. Chaque clé est optionnelle : un poste absent
    n'est simplement pas dans le dict -> les ratios qui en dépendent seront None.
    'shares' privilégie le nombre d'actions au bilan (instantané fin d'exercice).
    """
    rows: dict[str, pd.Series] = {}
    candidates = {
        "shares": _first_row(balance_sheet, "Ordinary Shares Number", "Share Issued"),
        "net_income": _row(financials, "Net Income"),
        "revenue": _row(financials, "Total Revenue"),
        "ebitda": _row(financials, "EBITDA"),
        "equity": _first_row(
            balance_sheet, "Stockholders Equity", "Total Equity Gross Minority Interest"
        ),
        "net_debt": _row(balance_sheet, "Net Debt"),
        "fcf": _row(cashflow, "Free Cash Flow"),
        "ocf": _row(cashflow, "Operating Cash Flow"),
    }
    for key, series in candidates.items():
        if series is not None:
            rows[key] = series
    return rows


def _manual_getter(table: pd.DataFrame, year: int, aliases: dict[str, str] | None = None):
    """Accesseur de postes pour le recalcul depuis le tableau (retourne un scalaire).

    `aliases` remappe une clé logique vers le nom de ligne réel (schéma financier :
    « Capitaux propres » → « Actif net »). Les clés internes (`_`-préfixées) non
    aliasées ne sont pas des lignes du tableau : elles renvoient None, et la
    métrique qui en dépend est laissée inchangée (jamais écrasée par une valeur
    fausse). Idem pour une cellule absente (NA).
    """
    aliases = aliases or {}

    def get(key: str):
        actual = aliases.get(key)
        if actual is None:
            if key.startswith("_") or key not in table.index:
                return None
            actual = key
        if actual not in table.index:
            return None
        value = table.at[actual, year]
        return None if pd.isna(value) else float(value)

    return get


def _recompute_derived(
    table: pd.DataFrame,
    years: list[int],
    kind: CompanyKind,
    enriched: set[str] | None = None,
) -> None:
    """Recalcule **tous** les ratios dérivés des années modifiées par l'utilisateur.

    Itère sur les métriques `derived` de la taxonomie (`config.FUNDAMENTAL_METRICS`)
    et applique la fonction de dérivation UNIQUE (`_derive`, partagée avec
    `build_table`) : une seule source des formules. Un dérivé dont tous les postes
    source sont renseignés est recalculé (marges, ROE/ROA, cash conversion, dette
    nette/EBITDA, gearing, agilité, BFR/CA…) ; les autres (ROCE, ROIC, ROA, CP/
    total bilan, liquidité, couverture des intérêts) dépendent de postes internes
    non saisissables et restent donc inchangés.

    Si `enriched` est fourni, les métriques recalculées y sont ajoutées.
    """
    financial = kind is CompanyKind.FINANCIAL
    derived = (
        [m for m, role in config.FINANCIAL_METRICS if role == "derived"]
        if financial
        else _INDUSTRIAL_DERIVED
    )
    # Schéma financier : les clés logiques attendues par `_derive` sont remappées
    # vers les lignes réelles du tableau (le fonds propres s'appelle « Actif net »,
    # le total d'actif est un poste source). Sans cela, ROA/ROE resteraient figés.
    aliases = (
        {"Capitaux propres": "Actif net", "_total_assets": "Total de l'actif"} if financial else {}
    )

    for year in years:
        if year not in table.columns:
            continue
        get = _manual_getter(table, year, aliases)
        for name in derived:
            value = _derive(name, get)
            if value is None:
                continue
            if name not in table.index:
                # Métrique absente du tableau yfinance mais calculable à partir
                # des postes saisis (ex. BFR/CA) -> nouvelle ligne.
                table.loc[name] = pd.NA
            table.at[name, year] = value
            if enriched is not None:
                enriched.add(name)


def merge_manual(
    table: pd.DataFrame, manual: dict[int, dict[str, float]], kind: CompanyKind
) -> tuple[pd.DataFrame, set[str]]:
    """Fusionne les données manuelles dans le tableau des comptes.

    - Années absentes de yfinance → ajoutées
    - Années déjà présentes → override
    - Les métriques dérivées (marges, ROE, etc.) sont recalculées.

    Renvoie (table_fusionnée, set_des_métriques_enrichies).
    """
    enriched: set[str] = set()

    if not manual:
        return table, enriched

    table = table.copy()
    years_to_recompute: list[int] = []

    for year, metrics in manual.items():
        year = int(year)
        years_to_recompute.append(year)

        if year not in table.columns:
            table[year] = pd.NA

        for metric, value in metrics.items():
            if metric in table.index:
                table.at[metric, year] = value
                enriched.add(metric)
            else:
                new_row = pd.Series(pd.NA, index=table.columns, name=metric)
                new_row[year] = value
                table = pd.concat([table, new_row.to_frame().T])
                enriched.add(metric)

    sorted_cols = sorted(table.columns, reverse=True)
    table = table[sorted_cols]

    _recompute_derived(table, years_to_recompute, kind, enriched)

    return table, enriched


def shareholder_payout(cashflow: pd.DataFrame, net_income: float | None) -> dict:
    """Retour total à l'actionnaire (dividendes + rachats nets d'actions) / RN, en %.

    yfinance compte les sorties de cash négativement -> on prend la valeur absolue.
    Les rachats (`Repurchase Of Capital Stock`) manquent pour certains titres :
    dans ce cas on tombe sur le dividende seul et on signale `buybacks_available=False`.

    `buybacks_available` est vrai dès qu'un rachat existe sur N'IMPORTE quel
    exercice de l'historique (pas seulement le plus récent) : un titre comme
    Amundi n'a des rachats que sur 2021/2022, et le test sur la seule colonne
    courante les masquait. La disponibilité est évaluée AVANT le calcul du payout,
    pour rester vraie même quand la ligne « Cash Dividends Paid » manque (cas
    Amundi) — le payout vaut alors None, mais les rachats restent exploitables.
    """
    out: dict = {"payout_pct": None, "buybacks_available": False}
    buybacks = _first_row(cashflow, "Repurchase Of Capital Stock", "Common Stock Payments")
    if buybacks is not None and buybacks.notna().any():
        out["buybacks_available"] = True
    if net_income is None or net_income <= 0:
        return out
    div = _row(cashflow, "Cash Dividends Paid")
    if div is None:
        return out
    div_amt = abs(float(div.iloc[0])) if pd.notna(div.iloc[0]) else 0.0
    total = div_amt
    # Le payout reste calculé sur l'exercice courant (div + rachat courant).
    if buybacks is not None and pd.notna(buybacks.iloc[0]):
        total += abs(float(buybacks.iloc[0]))
    out["payout_pct"] = total / net_income * 100
    return out
