"""Accès yfinance isolé + cache. SEUL point d'I/O réseau avec cache.py.

Robustesse : retry léger, dégradation gracieuse (un bloc qui échoue -> None,
jamais de crash). Le ticker inconnu lève TickerNotFound pour l'API.
"""

from __future__ import annotations

import time
from dataclasses import replace
from datetime import date

import pandas as pd
import yfinance as yf

from obole import config, observability
from obole.data import cache, fundamentals
from obole.data.manual import get_manual_dict
from obole.models import CompanyKind, CompanyOfficer, Fundamentals, Identity, PriceSeries

logger = observability.get_logger(__name__)


class TickerNotFound(Exception):
    """Levée quand yfinance ne renvoie aucune donnée de prix exploitable."""


def _with_retry(fn, attempts: int = 2, delay: float = 0.6, context: str = ""):
    """Exécute fn avec un petit retry. Renvoie None si tout échoue (dégradation).

    Point d'instrumentation **unique** de tous les appels yfinance : mesure la
    durée (appel lent -> WARNING) et trace les échecs (debug à chaque tentative
    ratée, warning avec la cause à l'abandon, puis alimentation du compteur lu
    par `/api/health`). Ne journalise jamais le résultat de `fn` (payload brut).
    """
    label = observability.safe_label(context) or "yfinance"
    for attempt in range(1, attempts + 1):
        started = time.monotonic()
        try:
            result = fn()
        except Exception:  # yfinance lève des exceptions variées
            if attempt < attempts:
                logger.debug("Appel %s en échec, tentative %d/%d", label, attempt, attempts)
                time.sleep(delay)
                continue
            observability.record_failure(label)
            logger.warning("Appel %s abandonné après %d tentatives", label, attempts, exc_info=True)
            return None
        _log_slow_call(label, time.monotonic() - started)
        return result
    return None


def _log_slow_call(label: str, elapsed_s: float) -> None:
    """Signale un appel yfinance anormalement lent (seuil : config.SLOW_CALL_MS)."""
    elapsed_ms = elapsed_s * 1000
    if elapsed_ms >= config.SLOW_CALL_MS:
        logger.warning(
            "Appel %s lent : %.0f ms (seuil %d ms)", label, elapsed_ms, config.SLOW_CALL_MS
        )


def _detect_kind(sector: str | None) -> CompanyKind:
    if sector and sector in config.FINANCIAL_SECTORS:
        return CompanyKind.FINANCIAL
    return CompanyKind.INDUSTRIAL


def _fresh_cached(obj, cls, required: tuple[str, ...]):
    """Objet caché valide pour la version courante du modèle, sinon None.

    Un cache TTL long (7 jours) peut contenir un objet sérialisé AVANT l'ajout de
    champs (identité étendue, marché, postes de santé) : les champs neufs y sont
    absents. On préfère alors un re-fetch à une grille de synthèse vide. Le
    marqueur `model_version` couvre le cas où les champs requis existent déjà mais
    qu'un poste plus fin (ex. `capex` dans `health_rows`) manque encore.
    """
    if obj is None or not isinstance(obj, cls):
        return None
    if getattr(obj, "model_version", None) != MODEL_VERSION:
        return None
    if all(getattr(obj, name, None) is not None for name in required):
        return obj
    return None


# Version du modèle de données (`Identity` / `Fundamentals`). À incrémenter quand
# un champ est ajouté : un objet caché d'une version antérieure est considéré
# comme périmé (re-fetch), au lieu de servir une grille de synthèse incomplète.
# v3 : dividende enrichi (events, payout_history, séries de rendement continu).
# v4 : stats du dividende précalculées (`dividend.stats`), champ mort retiré.
# v5 : `buybacks_available` détecté sur tout l'historique + repli actions courantes.
# v6 : croissance du dividende calculée hors année partielle (même exclusion que la
#      régularité) ; `buybacks_available` évalué avant le court-circuit dividendes.
# v7 : section Valorisation — séries continues de multiples (`valuation_series`) et
#      données de la calculatrice (`valuation_calc`) ; poste brut `revenue`.
# v8 : section Thèse & Société — profil société (`employees`, `officers`, `address`,
#      `summary`) et agenda (prochain résultat + détachement de dividende).
MODEL_VERSION = 8

# Aucun champ n'est exigé : `model_version` suffit à périmer une identité d'une
# version antérieure du modèle. Exiger des champs d'entreprise (`industry`,
# `website`, `address`…) rendait le cache INDÉFINIMENT périmé pour les titres qui
# n'en ont pas par nature — ETF, crypto, petite place : `fetch_identity` rejouait
# `info` + `calendar` (2 tentatives) à CHAQUE ouverture de la Performance, soit
# ~1 s de réseau par titre et par affichage (mesuré #24). Même défaut que
# `market` ci-dessous, côté identité.
_IDENTITY_FIELDS: tuple[str, ...] = ()
# Même raison pour les comptes : `health_rows` est Optional (une entreprise peut
# n'avoir AUCUN poste de santé reconnu alors que sa table est remplie), l'exiger
# rendrait le cache perpétuellement périmé. `model_version` couvre la péremption.
_FUNDAMENTALS_FIELDS: tuple[str, ...] = ()


def fetch_prices(ticker: str) -> PriceSeries:
    """Cours historiques (Close brut + Adj Close). Caché TTL_PRICES."""
    cached = cache.get(ticker, "prices", config.TTL_PRICES)
    if cached is not None:
        return cached

    def _fetch():
        return yf.Ticker(ticker).history(period="max", auto_adjust=False)

    hist = _with_retry(_fetch, context=f"prices {ticker}")
    if hist is None or hist.empty or "Close" not in hist:
        raise TickerNotFound(ticker)

    ps = PriceSeries(
        raw=hist["Close"].dropna(),
        adjusted=hist.get("Adj Close", hist["Close"]).dropna(),
        fetched_at=date.today(),
    )
    cache.put(ticker, "prices", ps)
    return ps


def _num(value) -> float | None:
    """Convertit une valeur yfinance en float, ou None si absente/non numérique."""
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None  # écarte NaN


def _market_snapshot(info: dict) -> dict | None:
    """Instantanés de marché pour la synthèse « Résumé » (depuis `info`).

    Un champ absent -> clé à None (jamais 0). `ocf` sert au P/OCF de la carte
    Valorisation (capitalisation / flux d'exploitation).
    """
    if not info:
        return None
    return {
        "market_cap": _num(info.get("marketCap")),
        "trailing_pe": _num(info.get("trailingPE")),
        "forward_pe": _num(info.get("forwardPE")),
        "price_to_sales": _num(info.get("priceToSalesTrailing12Months")),
        "price_to_book": _num(info.get("priceToBook")),
        "dividend_rate": _num(info.get("dividendRate")),
        "ocf": _num(info.get("operatingCashflow")),
    }


def _health_rows(fin: pd.DataFrame, bs: pd.DataFrame, cf: pd.DataFrame) -> dict | None:
    """Postes BRUTS (Timestamp de clôture) requis par les scores de santé.

    Alimente Altman Z, Piotroski F et la couverture d'intérêts. Chaque poste
    absent est simplement omis -> le score dépendant reste None en aval.
    """
    candidates: dict[str, tuple[pd.DataFrame, str]] = {
        "net_income": (fin, "Net Income"),
        "operating_income": (fin, "Operating Income"),
        "ebit": (fin, "EBIT"),
        "interest_expense": (fin, "Interest Expense"),
        "tax_rate": (fin, "Tax Rate For Calcs"),
        "revenue": (fin, "Total Revenue"),
        "gross_profit": (fin, "Gross Profit"),
        "total_assets": (bs, "Total Assets"),
        "total_liabilities": (bs, "Total Liabilities Net Minority Interest"),
        "working_capital": (bs, "Working Capital"),
        "retained_earnings": (bs, "Retained Earnings"),
        "current_assets": (bs, "Current Assets"),
        "current_liabilities": (bs, "Current Liabilities"),
        "long_term_debt": (bs, "Long Term Debt"),
        "invested_capital": (bs, "Invested Capital"),
        "goodwill": (bs, "Goodwill"),
        "shares": (bs, "Ordinary Shares Number"),
        "ocf": (cf, "Operating Cash Flow"),
        "capex": (cf, "Capital Expenditure"),
    }
    rows: dict[str, pd.Series] = {}
    for key, (frame, name) in candidates.items():
        row = fundamentals._row(frame, name)
        if row is not None:
            rows[key] = row
    return rows or None


def _estimates(t: yf.Ticker, ticker: str) -> dict | None:
    """Consensus analystes : croissance CA / BNPA à 1 an (fraction -> %).

    `yfinance` renvoie une ligne `+1y` avec une colonne `growth` (ex. 0.0283).
    Toute absence -> clé à None (le front affiche « -- », jamais 0).
    """
    rev = _with_retry(lambda: t.revenue_estimate, context=f"revenue_estimate {ticker}")
    eps = _with_retry(lambda: t.earnings_estimate, context=f"earnings_estimate {ticker}")

    def _growth_1y(frame) -> float | None:
        if frame is None or getattr(frame, "empty", True) or "growth" not in frame.columns:
            return None
        if "+1y" not in frame.index:
            return None
        value = _num(frame.loc["+1y", "growth"])
        return None if value is None else value * 100

    out = {"revenue_growth": _growth_1y(rev), "eps_growth": _growth_1y(eps)}
    if out["revenue_growth"] is None and out["eps_growth"] is None:
        return None
    return out


def _with_last_price(ident: Identity, last_price: float | None) -> Identity:
    """Rend `ident` avec un `last_price` à jour, sans jamais écraser par `None`.

    - identité sans prix + prix fourni  -> prix appliqué (et persisté) ;
    - identité avec prix + `None`       -> prix conservé, cache inchangé ;
    - identité avec prix + prix neuf    -> prix rafraîchi (et persisté) ;
    - sans prix des deux côtés          -> inchangé.
    """
    if last_price is None or last_price == ident.last_price:
        return ident
    updated = replace(ident, last_price=last_price)
    cache.put(ident.ticker, "identity", updated)
    return updated


def fetch_identity(ticker: str, last_price: float | None) -> Identity:
    """Métadonnées société. Champs manquants tolérés (Optional).

    `last_price` est **rafraîchi** même sur un hit de cache : un appel « name only »
    (`last_price=None`, ex. `resolve_names` du portefeuille) ne doit jamais figer
    un prix absent — sinon la fiche d'une ligne du portefeuille afficherait
    « Prix communiqué : -- » pendant tout le TTL. Le prix déjà connu n'est
    écrasé que par une valeur réelle (jamais par `None`).
    """
    cached = cache.get(ticker, "identity", config.TTL_FUNDAMENTALS)
    if cached is not None:
        fresh = _fresh_cached(cached, Identity, _IDENTITY_FIELDS)
        if fresh is not None:
            return _with_last_price(fresh, last_price)

    t = yf.Ticker(ticker)
    info = _with_retry(lambda: t.info, context=f"info {ticker}")
    # Échec réseau (toutes tentatives abandonnées) : on NE met RIEN en cache. Un
    # `info` vide mis en cache 7 jours figerait une fiche sans nom ni secteur
    # après un simple blip ; la mémoire courte du marché est gérée par le TTL, pas
    # par un négatif permanent (le rafraîchir resterait le seul recours).
    if not info:
        return Identity(ticker=ticker.upper(), last_price=last_price)
    # info brut mis en cache à part : réutilisé par fetch_fundamentals (dividende,
    # filet de valorisation instantanée) sans nouvel appel réseau.
    cache.put(ticker, "info", info)
    sector = info.get("sector")
    next_earnings, next_earnings_estimated = _earnings_date(t, info)
    ex_dividend = _epoch_date(info.get("exDividendDate"))
    ident = Identity(
        ticker=ticker.upper(),
        name=info.get("longName") or info.get("shortName"),
        isin=info.get("isin"),
        country=info.get("country"),
        sector=sector,
        industry=info.get("industry"),
        website=info.get("website"),
        currency=info.get("currency"),
        market_cap=_num(info.get("marketCap")),
        last_price=last_price,
        beta=_num(info.get("beta")),
        week52_low=_num(info.get("fiftyTwoWeekLow")),
        week52_high=_num(info.get("fiftyTwoWeekHigh")),
        volume=_num(info.get("volume")),
        avg_volume=_num(info.get("averageVolume")),
        employees=_employees(info.get("fullTimeEmployees")),
        officers=_officers(info),
        address=_address(info),
        summary=info.get("longBusinessSummary") or None,
        next_earnings=next_earnings,
        next_earnings_estimated=next_earnings_estimated,
        ex_dividend=ex_dividend,
        kind=_detect_kind(sector),
        model_version=MODEL_VERSION,
    )
    cache.put(ticker, "identity", ident)
    return ident


def fetch_identity_cached(ticker: str) -> Identity | None:
    """Identité DÉJÀ en cache (TTL courant), sans aucun appel réseau.

    Sert les usages best-effort qui ne doivent pas déclencher de requête
    `info` yfinance (noms des lignes Top/Flop du portefeuille) : mieux vaut
    laisser le nom absent — le front retombe sur le ticker — que bloquer
    l'affichage plusieurs secondes.
    """
    cached = cache.get(ticker, "identity", config.TTL_FUNDAMENTALS)
    if cached is None:
        return None
    return _fresh_cached(cached, Identity, _IDENTITY_FIELDS)


def fetch_fundamentals(ticker: str, kind: CompanyKind) -> Fundamentals | None:
    """Comptes normalisés + dividende + données brutes de valorisation.

    Reste 100 % « data » : extraction et normalisation, aucun calcul engine. La
    reconstruction des multiples (qui croise prix×comptes) est faite par
    services/analysis, qui détient la série de prix. Ici on prépare seulement les
    postes bruts nécessaires (`valuation_rows`), portés par le modèle.
    Renvoie None si les comptes sont indisponibles (dégradation).

    **Cache négatif.** Un titre sans comptes (crypto, petite place Xetra, ETF)
    renvoie systématiquement 404 : sans mémoire de cet échec, chaque ouverture de
    l'onglet Performance rejouait les 3 appels + 2 tentatives (~1 à 2 s par
    titre, mesuré). Un marqueur `fundamentals_missing` de TTL court
    (`config.TTL_MISSING_FUNDAMENTALS`) évite cette dépense répétée tout en
    laissant une chance au titre de publier des comptes.
    """
    cached = cache.get(ticker, "fundamentals", config.TTL_FUNDAMENTALS)
    if cached is not None:
        fresh = _fresh_cached(cached, Fundamentals, _FUNDAMENTALS_FIELDS)
        if fresh is not None:
            return fresh
    if cache.get(ticker, "fundamentals_missing", config.TTL_MISSING_FUNDAMENTALS) is not None:
        return None

    t = yf.Ticker(ticker)
    fin = _with_retry(lambda: t.financials, context=f"financials {ticker}")
    bs = _with_retry(lambda: t.balance_sheet, context=f"balance_sheet {ticker}")
    cf = _with_retry(lambda: t.cashflow, context=f"cashflow {ticker}")

    empty = pd.DataFrame()
    # « Aucune comptes » n'est mémorisable que si Yahoo A RÉPONDU (au moins un des
    # trois tableaux rendu, même vide). Trois échecs réseau ne disent rien du
    # titre : les figer 6 h masquerait des comptes qui existent.
    answered = fin is not None or bs is not None or cf is not None
    fin = fin if fin is not None else empty
    bs = bs if bs is not None else empty
    cf = cf if cf is not None else empty
    table = fundamentals.build_table(fin, bs, cf, kind)
    if table.empty:
        if answered:
            cache.put(ticker, "fundamentals_missing", True)
        return None

    # Fusion avec les données manuelles (priorité manuel > yfinance).
    manual = get_manual_dict(ticker)
    manual_years: list[int] | None = sorted(manual.keys()) if manual else None
    if manual:
        table, _ = fundamentals.merge_manual(table, manual, kind)

    rows = fundamentals.valuation_rows(fin, bs, cf) if kind is not CompanyKind.FINANCIAL else {}
    info = cache.get(ticker, "info", config.TTL_FUNDAMENTALS) or {}

    fund = Fundamentals(
        table=table,
        kind=kind,
        available_years=table.shape[1],
        fetched_at=date.today(),
        dividend=_build_dividend(ticker, t, cf, table),
        growth=fundamentals.growth_inputs(table, kind) or None,
        valuation_rows=rows or None,
        manual_years=manual_years,
        market=_market_snapshot(info),
        health_rows=_health_rows(fin, bs, cf),
        estimates=_estimates(t, ticker),
        model_version=MODEL_VERSION,
    )
    cache.put(ticker, "fundamentals", fund)
    return fund


def _build_dividend(ticker: str, t, cashflow: pd.DataFrame, table: pd.DataFrame) -> dict | None:
    """Dividende : yield + payout (info) + shareholder payout (cash-flow) + série/action.

    Tout est optionnel : un titre sans dividende renvoie None. `info` est relu du
    cache (déjà chaud via fetch_identity) -> pas d'appel réseau supplémentaire.

    Champs exposés (tous optionnels) :
    - instantanés `info` : yield TTM, payout TTM, dernier paiement (montant + date) ;
    - `per_share` : dividende par action agrégé par année (série longue) ;
    - `events` : versements bruts {date ISO: montant} — base des courbes continues ;
    - `payout_history` / `shareholder_payout_history` : ratios par exercice (~5 ans) ;
    - `dividend_paid_history` / `buyback_history` : montants annuels (cash-flow) ;
    - `buybacks_available` : les rachats existent-ils (sinon « -- »).
    """
    info = cache.get(ticker, "info", config.TTL_FUNDAMENTALS) or {}
    div_yield = info.get("dividendYield")
    payout = info.get("payoutRatio")

    net_income = None
    if "Bénéfice net" in table.index:
        ni = table.loc["Bénéfice net"].dropna()
        net_income = float(ni.iloc[0]) if len(ni) else None
    sh = fundamentals.shareholder_payout(cashflow, net_income)

    # Historique du dividende par action (~20-40 ans dispo, bien au-delà des comptes).
    hist = _with_retry(lambda: t.dividends, context=f"dividends {ticker}")
    per_share = None
    events: dict[str, float] = {}
    if hist is not None and not hist.empty:
        annual = hist.groupby(hist.index.year).sum()
        per_share = {int(y): round(float(v), 4) for y, v in annual.items()}
        events = {
            ts.strftime("%Y-%m-%d"): round(float(v), 4) for ts, v in hist.items() if pd.notna(v)
        }

    # Statistiques de la section Dividende (régularité, CAGR, fréquence, croissance
    # annuelle) : calculées par `services/analysis` (couche qui peut appeler
    # engine/) et stockées dans `dividend["stats"]`. Le front les affiche ; seules
    # les stats de FENÊTRE du rendement continu restent côté client.

    # Montants annuels (cash-flow) : dividendes versés + rachats d'actions.
    dividend_paid = _annual_amounts(cashflow, "Cash Dividends Paid")
    buyback_hist = _annual_amounts(cashflow, "Repurchase Of Capital Stock", "Common Stock Payments")

    # Ratios par exercice : payout (dividendes / RN ou FCF) et payout actionnaire
    # (dividendes + rachats) / RN ou FCF. ~5 ans (limite des comptes yfinance).
    net_income_by_year = _annual_amounts(table, "Bénéfice net", abs_value=False)
    fcf_by_year = _annual_amounts(table, "Free Cash Flow", abs_value=False)
    payout_history = _payout_series(dividend_paid, buyback_hist, net_income_by_year, fcf_by_year)

    last_value = _num(info.get("lastDividendValue"))
    # Date du dernier VERSEMENT uniquement : `exDividendDate` est la date de
    # détachement (≠ date de paiement) — l'utiliser ici serait factuellement faux.
    # Absente -> le front n'affiche que le montant (sans date).
    last_date = _epoch_date(info.get("lastDividendDate"))

    if div_yield is None and payout is None and sh["payout_pct"] is None and not per_share:
        return None
    return {
        "yield_pct": round(div_yield, 2) if div_yield is not None else None,
        "payout_pct": round(payout * 100, 1) if payout is not None else None,
        "shareholder_payout_pct": (
            round(sh["payout_pct"], 1) if sh["payout_pct"] is not None else None
        ),
        "buybacks_available": sh["buybacks_available"],
        "per_share": per_share,
        "events": events or None,
        "buyback_history": buyback_hist or None,
        "dividend_paid_history": dividend_paid or None,
        "payout_history": payout_history or None,
        "last_payment_value": last_value,
        "last_payment_date": last_date,
        # Prochain paiement : yfinance Europe ne fournit aucun calendrier fiable
        # (seule une date ex-div approximative) -> aucun champ, le front affiche
        # une ligne « — » assumée (cf. fiche #19 §4.3).
        # `stats` (régularité, CAGR, fréquence) est ajouté par services/analysis.
    }


def _annual_amounts(
    frame: pd.DataFrame, *names: str, abs_value: bool = True
) -> dict[int, float] | None:
    """Somme annuelle (valeur absolue par défaut) d'une ligne de comptes/CF.

    Renvoie {année: montant} ou None si le poste est absent. Les sorties de cash
    sont négatives chez Yahoo : `abs_value=True` les rend lisibles.
    """
    row = fundamentals._first_row(frame, *names)
    if row is None:
        return None
    out: dict[int, float] = {}
    for ts, val in row.items():
        if pd.isna(val):
            continue
        v = float(val)
        year = int(ts.year) if hasattr(ts, "year") else int(ts)
        out[year] = round(abs(v) if abs_value else v, 0)
    return out or None


def _payout_series(
    dividend_paid: dict[int, float] | None,
    buybacks: dict[int, float] | None,
    net_income: dict[int, float] | None,
    fcf: dict[int, float] | None,
) -> dict[str, dict[int, float]] | None:
    """Ratios de distribution par exercice (dividendes et dividendes + rachats).

    Quatre séries : Earnings/FCF Payout Ratio (dividendes seuls) et
    Earnings/FCF Shareholder Payout Ratio (dividendes + rachats). Un dénominateur
    nul/négatif rend le ratio absent pour l'année (jamais d'infini).
    """
    if not dividend_paid:
        return None

    def _ratio(num_by_year: dict[int, float], den_by_year: dict[int, float] | None):
        if not den_by_year:
            return None
        out: dict[int, float] = {}
        for year, num in num_by_year.items():
            den = den_by_year.get(year)
            if den is None or den <= 0:
                continue
            out[year] = round(num / den * 100, 1)
        return out or None

    total = {
        year: amount + (buybacks.get(year, 0.0) if buybacks else 0.0)
        for year, amount in dividend_paid.items()
    }
    series = {
        "earnings_payout": _ratio(dividend_paid, net_income),
        "fcf_payout": _ratio(dividend_paid, fcf),
        "earnings_shareholder_payout": _ratio(total, net_income),
        "fcf_shareholder_payout": _ratio(total, fcf),
    }
    return {k: v for k, v in series.items() if v} or None


def _epoch_date(value) -> str | None:
    """Timestamp epoch (s) -> date ISO, ou None si absent/invalide."""
    if value is None:
        return None
    try:
        return date.fromtimestamp(float(value)).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _employees(value) -> int | None:
    """Effectif (`fullTimeEmployees`) -> entier, ou None si absent/invalide."""
    num = _num(value)
    return None if num is None else int(num)


def _officers(info: dict) -> tuple[CompanyOfficer, ...]:
    """Dirigeants (`companyOfficers`) normalisés, dans l'ordre de la source.

    Un dirigeant sans nom est écarté (aucune ligne utile) ; les autres champs
    restent Optionnels. Renvoie un tuple (objet gelé) — jamais None : une liste
    vide signifie simplement « non fourni ».
    """
    raw = info.get("companyOfficers")
    if not isinstance(raw, list):
        return ()
    officers = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        age = _num(item.get("age"))
        officers.append(
            CompanyOfficer(
                # yfinance double parfois les espaces dans les noms
                # (« Mr. Alexandre  Ricard ») : on normalise pour l'affichage.
                name=" ".join(name.split()),
                title=item.get("title") or None,
                age=None if age is None else int(age),
            )
        )
    return tuple(officers)


def _address(info: dict) -> str | None:
    """Adresse du siège : ville (+ pays), si l'une des deux est connue."""
    parts = [p for p in (info.get("city"), info.get("country")) if isinstance(p, str) and p]
    return ", ".join(parts) if parts else None


def _earnings_date(t: yf.Ticker, info: dict) -> tuple[str | None, bool | None]:
    """Prochain résultat : date ISO + drapeau « estimé ».

    `earningsTimestamp` est la source principale ; à défaut, on interroge
    `calendar` (un échec réseau n'est pas fatal — l'agenda est un complément).
    `t` est l'objet `yf.Ticker` DÉJÀ construit : passer le ticker (une chaîne)
    rendrait le repli `calendar` inopérant.

    Renvoie `(None, None)` si aucune date : le front omet alors la ligne.
    """
    iso = _epoch_date(info.get("earningsTimestamp") or info.get("earningsTimestampStart"))
    if iso is not None:
        estimated = info.get("isEarningsDateEstimate")
        return iso, estimated if isinstance(estimated, bool) else None
    try:
        calendar = t.calendar or {}
        dates = calendar.get("Earnings Date") if isinstance(calendar, dict) else None
        if dates:
            first = dates[0] if isinstance(dates, (list, tuple)) else dates  # noqa: UP038
            return (first.isoformat() if hasattr(first, "isoformat") else str(first)), True
    except Exception:  # noqa: BLE001 — l'agenda est best-effort, jamais bloquant
        return None, None
    return None, None


def refresh(ticker: str) -> None:
    """Refresh manuel : purge le cache du ticker (prochaine lecture re-fetch)."""
    cache.invalidate(ticker)


def search(query: str, limit: int = 8) -> list[dict]:
    """Autocomplétion nom/ticker -> liste de {symbol, name, exchange}.

    Filtre sur les actions (EQUITY) ; les ETF/fonds/indices sont du bruit ici.
    Caché brièvement (la requête tapée sert de clé).
    """
    query = query.strip()
    if len(query) < 2:
        return []

    cache_key = f"search:{query.lower()}"
    cached = cache.get(cache_key, "search", config.TTL_SEARCH)
    if cached is not None:
        return cached

    # Pas de requête brute dans le libellé : c'est une saisie libre de
    # l'utilisateur (assainie de toute façon par `safe_label`).
    result = _with_retry(lambda: yf.Search(query, max_results=limit * 2), context="search")
    quotes = (result.quotes if result else []) or []

    candidates = []
    seen = set()
    for q in quotes:
        if q.get("quoteType") != "EQUITY":
            continue
        symbol = q.get("symbol")
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        candidates.append(
            {
                "symbol": symbol,
                "name": q.get("shortname") or q.get("longname") or symbol,
                "exchange": q.get("exchange"),
            }
        )

    def rank(item: dict) -> int:
        ex = item["exchange"]
        return config.EXCHANGE_PRIORITY.index(ex) if ex in config.EXCHANGE_PRIORITY else 999

    candidates.sort(key=rank)
    out = candidates[:limit]

    cache.put(cache_key, "search", out)
    return out
