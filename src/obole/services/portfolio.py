"""Cas d'usage « portefeuille » : orchestre `data/` (I/O) et `engine/` (pur).

Couche `services/` : elle assemble les transactions persistées (`data/portfolio`)
et le recalcul pur des positions (`engine/portfolio`). **Point d'entrée unique**,
partagé par l'API et, à terme, par le MCP-B — aucune orchestration dupliquée :
l'API ne touche jamais `data/portfolio` en direct.

Jalons livrés : positions brutes (`#17.0`) et **résumé TWR vs benchmark**
(`#17.1`). Les prix viennent de `data/yahoo` (déjà en cache) : le calcul de
performance ne coûte aucun appel réseau supplémentaire au premier affichage.
Les noms des lignes Top/Flop sont résolus **cache only** (`fetch_identity_cached`,
aucun appel `info`) : un nom absent laisse le front retomber sur le ticker.
"""

from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, wait
from typing import TypedDict

import pandas as pd

from obole import config, observability
from obole.data import cache as cache_data
from obole.data import portfolio as portfolio_data
from obole.data import yahoo
from obole.engine import dividends as dividends_mod
from obole.engine import portfolio as portfolio_engine
from obole.models import StockAnalysis
from obole.services import analysis as analysis_service
from obole.services import serialize

logger = observability.get_logger(__name__)

# --- Comptes -----------------------------------------------------------------


def accounts() -> list[dict]:
    """Comptes du portefeuille."""
    return portfolio_data.list_accounts()


def create_account(name: str, currency: str | None = None) -> int:
    """Crée un compte (Lève `ValueError` si le nom est vide)."""
    return portfolio_data.create_account(name, currency)


def delete_account(account_id: int) -> None:
    """Supprime un compte et ses lignes (Lève `NotFoundError` si inconnu)."""
    portfolio_data.delete_account(account_id)


# --- Transactions ------------------------------------------------------------


def transactions(account_id: int | None = None, tag: str | None = None) -> list[dict]:
    """Transactions, filtrables par compte et/ou étiquette (#17.6)."""
    return portfolio_data.list_transactions(account_id, tag)


def tags(account_id: int | None = None) -> list[str]:
    """Étiquettes distinctes des transactions (portefeuilles virtuels), triées.

    `account_id` restreint la liste au compte donné (#17.6).
    """
    return portfolio_data.list_tags(account_id)


def add_transaction(**fields) -> int:
    """Ajoute une transaction (Lève `ValueError` si invalide)."""
    return portfolio_data.add_transaction(**fields)


def update_transaction(tx_id: int, **fields) -> None:
    """Remplace une transaction (Lève `NotFoundError` / `ValueError`)."""
    portfolio_data.update_transaction(tx_id, **fields)


def delete_transaction(tx_id: int) -> None:
    """Supprime une transaction (Lève `NotFoundError` si inconnue)."""
    portfolio_data.delete_transaction(tx_id)


def tag_positions(account_id: int | None, ticker: str, tag: str | None) -> int:
    """Étiquette toutes les transactions d'un titre (#17.6). Renvoie le compte.

    « Étiqueter une position » depuis l'onglet Positions = une écriture groupée
    sur les transactions de ce titre (scope compte courant). Lève `ValueError` sur
    entrée invalide.
    """
    return portfolio_data.set_tag(account_id, ticker, tag)


# --- Dividendes --------------------------------------------------------------


def dividends(account_id: int | None = None) -> list[dict]:
    """Dividendes, éventuellement filtrés par compte."""
    return portfolio_data.list_dividends(account_id)


def add_dividend(**fields) -> int:
    """Ajoute un dividende (Lève `ValueError` si invalide)."""
    return portfolio_data.add_dividend(**fields)


def update_dividend(div_id: int, **fields) -> None:
    """Remplace un dividende (Lève `NotFoundError` / `ValueError`)."""
    portfolio_data.update_dividend(div_id, **fields)


def delete_dividend(div_id: int) -> None:
    """Supprime un dividende (Lève `NotFoundError` si inconnu)."""
    portfolio_data.delete_dividend(div_id)


# --- Positions ---------------------------------------------------------------


def positions(account_id: int | None = None, tag: str | None = None) -> list[dict]:
    """Positions recalculées depuis les transactions.

    `account_id` None = vue consolidée « Tous » (toutes les transactions) ; sinon
    les transactions du seul compte demandé. `tag` (#17.6) restreint en plus aux
    transactions étiquetées (portefeuille virtuel) ; les deux filtres se
    combinent. Chaque position est renvoyée sous forme sérialisable : ticker,
    quantité, PRU, coût, réalisé, et la liste de ses étiquettes (libellés).
    Les positions soldées (quantité nulle) sont omises.
    """
    transactions = portfolio_data.list_transactions(account_id, tag)
    tags_by_ticker: dict[str, set[str]] = {}
    for t in transactions:
        label = t.get("tag")
        if label:
            tags_by_ticker.setdefault(str(t["ticker"]).upper(), set()).add(label)
    rows: list[dict] = []
    for pos in portfolio_engine.positions_from_transactions(transactions):
        if pos.quantity <= 0:
            continue
        rows.append(
            {
                "ticker": pos.ticker,
                "quantity": pos.quantity,
                "pru": pos.pru,
                "cost_basis": pos.cost_basis,
                "realized": pos.realized,
                "tags": sorted(tags_by_ticker.get(pos.ticker, set()), key=str.lower),
            }
        )
    return rows


# --- Résumé : TWR vs benchmark (#17.1) ---------------------------------------


def benchmarks() -> list[dict]:
    """Liste curée des benchmarks (ETF EUR) — source unique `config.py`."""
    return [dict(b) for b in config.PORTFOLIO_BENCHMARKS]


def _validate_benchmark(ticker: str | None) -> str:
    """Normalise et valide le ticker du benchmark (liste curée ou libre)."""
    ticker = (ticker or config.PORTFOLIO_BENCHMARK_DEFAULT).strip().upper()
    if not ticker:
        raise ValueError("Benchmark vide")
    return ticker


def _validate_period(period: str | None) -> str:
    period = (period or config.PORTFOLIO_PERIOD_DEFAULT).strip().lower()
    if period not in config.PORTFOLIO_PERIODS:
        raise ValueError(f"Période inconnue : {period!r}")
    return period


def _series_to_list(series) -> list[float | None]:
    """Série pandas (dates -> valeur) -> liste alignée sur son index (NaN -> None)."""
    return [None if v != v else float(v) for v in series]  # NaN != NaN


def _session_days(series) -> pd.DatetimeIndex:
    """Jours de cotation d'une série, en dates NAÏVES dédoublonnées.

    Les index Yahoo sont tz-aware et **chaque place a son fuseau** (`Europe/Paris`
    pour Paris, `UTC` pour un actif coté 24/7, `America/New_York` pour Wall
    Street). Unionner ces index compare des INSTANTS : une barre Paris 14/05
    (00:00+02:00 = 13/05 22:00 UTC) ne coïncide avec aucune barre UTC et
    produisait un second point à la même date calendaire — dents de scie dans la
    courbe et décalage d'un jour des cours européens. On ramène donc tout à des
    jours naïfs, seule base comparable entre places.
    """
    index = series.index
    if getattr(index, "tz", None) is not None:
        index = index.tz_localize(None)
    return pd.DatetimeIndex(index.normalize()).drop_duplicates()


def _is_round_the_clock(days: pd.DatetimeIndex) -> bool:
    """Vrai si la série cote VRAIMENT le week-end (actif 24/7 : crypto).

    Un tel actif n'a pas de « séance » : l'ajouter au calendrier ferait entrer
    samedis et dimanches dans la courbe du portefeuille (points plats pour les
    actions) et gonflerait le nombre de points par an, faussant l'annualisation
    (`realized_volatility`, Sharpe, Sortino divisent par √252).

    Critère **proportionnel**, pas « au moins une fois » : une barre de week-end
    parasite (séance de rattrapage, fuseau mal interprété) sur une action ordinaire
    la priverait sinon de ses séances propres — silencieusement. On compare donc
    les week-ends COUVERTS à ceux que la période contient (`config.
    PORTFOLIO_ROUND_CLOCK_WEEKEND_RATIO`).
    """
    if not len(days):
        return False
    weekend = days[days.weekday >= 5]
    if not len(weekend):
        return False
    span = pd.date_range(days[0], days[-1], freq="D")
    expected = int((span.weekday >= 5).sum())
    if expected == 0:
        return False
    return len(weekend) / expected >= config.PORTFOLIO_ROUND_CLOCK_WEEKEND_RATIO


def _trading_index(
    prices: dict, bench: str | None, start: str, field: str = "adjusted"
) -> pd.DatetimeIndex:
    """Axe temps commun = SÉANCES DE MARCHÉ, en jours calendaires naïfs.

    Source unique des index du portefeuille (`summary`, `risk`, `performance`,
    `dividend_page`) : quatre copies de cette logique avaient laissé le bug de
    fuseaux se propager sur tous les graphes.

    Règle : les séances du **benchmark** forment la base (c'est lui qui donne son
    rythme à la comparaison) ; on y ajoute les séances ouvrées des titres du
    périmètre que le benchmark n'a pas (jour férié local d'une autre place) ; on
    écarte les actifs cotés 24/7, qui n'ont pas de séance. Le résultat est trié,
    dédoublonné, sans week-end et borné à `start` (inclus).

    `bench=None` : aucune base de référence, on réunit les séances de tous les
    titres (usage interne du double TWR de la page Dividende).
    """
    sessions: set[pd.Timestamp] = set()
    if bench is not None and bench in prices:
        sessions |= set(_session_days(getattr(prices[bench], field)))
    for tk, ps in prices.items():
        if tk == bench:
            continue
        days = _session_days(getattr(ps, field))
        if _is_round_the_clock(days):
            logger.info("Portefeuille : %s coté 24/7 (week-ends), écarté du calendrier", tk)
            continue
        sessions |= set(days)
    index = pd.DatetimeIndex(sorted(sessions))
    index = index[index.weekday < 5]
    return index[index >= pd.Timestamp(start)]


def _scope_dividends(
    div_all: list[dict], tx: list[dict], account_id: int | None, tag: str | None
) -> list[dict]:
    """Dividendes de la portée courante (compte et/ou étiquette, #17.6).

    Sans étiquette : filtre par compte uniquement (un dividende porte un
    `account_id`). Avec une étiquette : un dividende n'a pas d'étiquette propre —
    on retient ceux dont le couple (compte, titre) est couvert par une transaction
    ÉTIQUETÉE (le portefeuille virtuel inclut donc bien ses dividendes).
    """
    if tag is None:
        return [d for d in div_all if account_id is None or d["account_id"] == account_id]
    pairs = {(t["account_id"], str(t["ticker"]).upper()) for t in tx}
    return [d for d in div_all if (d["account_id"], str(d["ticker"]).upper()) in pairs]


def _confirmed_total(div: Sequence[dict]) -> float:
    """Somme des dividendes RÉELLEMENT encaissés (statut `confirmed`).

    Une proposition (`proposed`) n'est pas un revenu : l'inclure dans un total
    fausserait le rendement et le TWR (la courbe encaisserait un euro jamais
    versé). Le statut absent vaut confirmé (saisies antérieures au champ).
    """
    return sum(
        float(d.get("amount") or 0.0)
        for d in div
        if str(d.get("status") or "confirmed").strip().lower() == "confirmed"
    )


def _confirmed_dividends(div: Sequence[dict]) -> list[dict]:
    """Versements confirmés seulement — entrée de `daily_values` (TWR).

    Le TWR ne doit encaisser que de l'argent réellement reçu : une proposition
    gonflerait la valeur du compte sans flux correspondant.
    """
    return [d for d in div if str(d.get("status") or "confirmed").strip().lower() == "confirmed"]


def _align(series, index: pd.DatetimeIndex):
    """Réindexe une série (index tz-aware) sur un axe de jours naïfs.

    Un `reindex` direct entre un index tz-aware et un index naïf ne matche RIEN
    (tout NaN) : on ramène d'abord la série sur des jours naïfs, en gardant la
    DERNIÈRE valeur du jour quand plusieurs barres y tombent (barre du soir).
    """
    naive = series.copy()
    if getattr(naive.index, "tz", None) is not None:
        naive.index = naive.index.tz_localize(None)
    naive.index = naive.index.normalize()
    if naive.index.has_duplicates:
        naive = naive[~naive.index.duplicated(keep="last")]
    return naive.reindex(index)


def summary(
    account_id: int | None,
    benchmark: str | None,
    period: str | None,
    tag: str | None = None,
) -> dict:
    """Résumé de performance du portefeuille face à un benchmark.

    Assemble : courbe **TWR** du portefeuille + courbe du benchmark (buy-and-hold),
    4 KPI (valeur totale, montant investi, Total Return, dividendes + rendement),
    répartition par compte et Top/Flop N positions. Les prix viennent de
    `data/yahoo` (cache) : aucun appel réseau n'est refait si les cours sont en
    cache. `ValueError` si la période est inconnue ou le benchmark introuvable.

    `account_id` et `tag` (#17.6) restreignent la portée : un compte, une
    étiquette (« portefeuille virtuel »), ou les deux combinés. Pour une étiquette,
    les dividendes pris en compte sont ceux dont le couple (compte, titre) est
    couvert par une transaction étiquetée (un dividende n'a pas d'étiquette
    propre) — le portefeuille virtuel inclut donc bien ses dividendes.
    """
    period = _validate_period(period)
    bench = _validate_benchmark(benchmark)

    accounts = portfolio_data.list_accounts()
    ctx = _portfolio_context(account_id, benchmark, period, tag)
    tx = ctx["tx"]
    empty = _empty_summary(bench, period)
    if ctx["empty"]:
        return empty

    idx = ctx["index"]
    if idx is None:  # jamais avec `empty=False`, mais on ne le suppose pas
        return empty
    dates = ctx["dates"]
    prices = ctx["prices"]
    tickers = sorted(set(ctx["tickers"]) | {bench})
    div = ctx["div"]
    twr = ctx["twr"]
    bench_curve = ctx["bench_curve"]

    start_idx = ctx["start_idx"]
    days = (idx[-1] - idx[start_idx]).days if len(idx) > start_idx else 0
    period_perf = portfolio_engine.period_return(twr, start_idx)
    period_bench = portfolio_engine.period_return(bench_curve, start_idx)

    values = ctx["values"]
    flows = ctx["flows"]
    total_value = values[-1] if values else 0.0
    invested = sum(flows)
    dividends_total = _confirmed_total(div)
    total_return = total_value - invested if invested else None

    last_prices = {tk: _last_price(ps) for tk, ps in prices.items()}
    rows = ctx["rows"]
    perf_by_ticker = {r["ticker"]: r["perf"] for r in rows}
    top, flop = portfolio_engine.top_flop(rows, perf_by_ticker, config.PORTFOLIO_TOP_N)
    # Noms résolus UNIQUEMENT pour les lignes affichées (Top/Flop) : évite un
    # appel réseau `info` par position du portefeuille à chaque Résumé.
    _attach_names(top)
    _attach_names(flop)

    bench_meta = next(
        (b for b in config.PORTFOLIO_BENCHMARKS if b["ticker"] == bench),
        {"key": "custom", "ticker": bench, "label": bench},
    )
    return {
        "dates": dates,
        "period": period,
        "period_start": dates[start_idx],
        "benchmark": dict(bench_meta),
        "portfolio": [round(v, 2) for v in twr],
        "benchmark_curve": [None if v is None else round(v, 2) for v in bench_curve],
        "kpis": {
            "total_value": round(total_value, 2),
            "invested": round(invested, 2),
            "total_return": None if total_return is None else round(total_return, 2),
            "total_return_pct": _pct(total_return, invested),
            "period_return_pct": None if period_perf is None else round(period_perf, 2),
            "annualized_pct": _round_or_none(portfolio_engine.annualized_return(period_perf, days)),
            "dividends": round(dividends_total, 2),
            "dividend_yield_pct": _pct(dividends_total, invested),
            "benchmark_period_pct": None if period_bench is None else round(period_bench, 2),
        },
        "accounts": _accounts_breakdown(tx, accounts, last_prices, account_id),
        "holdings": _holdings_breakdown(rows),
        "account": _account_meta(tx, accounts, account_id, div),
        "top": top,
        "flop": flop,
        "warnings": _warnings(rows, tickers, prices),
    }


def _account_meta(
    tx: list[dict],
    accounts: list[dict],
    account_id: int | None,
    dividends: list[dict],
) -> dict | None:
    """Métadonnées du compte affiché (bandeau) : nom, depuis, frais, taxes, solde.

    `None` en vue consolidée « Tous les comptes ». « Depuis » = date de la
    première transaction. Les **frais** sont la somme des frais de transaction.
    Les **taxes** ne sont pas modélisées dans le schéma (aucune colonne dédiée) :
    elles valent donc 0 (affichées « 0,00 € », jamais un `None` trompeur). Le
    **solde** = trésorerie du compte = dividendes perçus − frais payés (un achat
    consomme la trésorerie mais celle-ci n'est pas saisie : le solde est donc le
    reliquat des dividendes non réinvestis, approche sobre et honnête).
    """
    if account_id is None:
        return None
    name = next((a["name"] for a in accounts if int(a["id"]) == account_id), "—")
    since = min((str(t["trade_date"]) for t in tx), default=None)
    fees = sum(float(t.get("fees") or 0.0) for t in tx)
    div_total = _confirmed_total(dividends)
    return {
        "account_id": account_id,
        "name": name,
        "since": since,
        "fees": round(fees, 2),
        "taxes": 0.0,  # non modélisées (schéma sans colonne) — jamais None
        "balance": round(div_total - fees, 2),
    }


def _last_price(ps) -> float | None:
    series = ps.raw.dropna()
    if series.empty:
        return None
    return float(series.iloc[-1])


def _pct(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return round(numerator / denominator * 100.0, 2)


def _round_or_none(v: float | None) -> float | None:
    return None if v is None else round(v, 2)


def _position_rows(tx: list[dict], last_prices: dict[str, float | None]) -> list[dict]:
    """Une ligne par position détenue : quantité, valeur, gain et perf (%).

    `perf` = plus/moins-value latente / coût. Les positions sans cours connu sont
    renvoyées avec `perf=None` (écartées du classement, jamais un 0 trompeur).
    """
    rows: list[dict] = []
    for pos in portfolio_engine.positions_from_transactions(tx):
        if pos.quantity <= 0:
            continue
        price = last_prices.get(pos.ticker)
        market_value = None if price is None else price * pos.quantity
        gain = None if market_value is None else market_value - pos.cost_basis
        perf = None if gain is None or pos.cost_basis <= 0 else gain / pos.cost_basis * 100.0
        rows.append(
            {
                "ticker": pos.ticker,
                "name": None,  # résolu pour les seules lignes affichées (Top/Flop)
                "quantity": pos.quantity,
                "cost_basis": round(pos.cost_basis, 2),
                "market_value": None if market_value is None else round(market_value, 2),
                "gain": None if gain is None else round(gain, 2),
                "perf": None if perf is None else round(perf, 2),
                "realized": round(pos.realized, 2),
            }
        )
    return rows


def _attach_names(rows: list[dict]) -> None:
    """Renseigne `name` (yfinance `identity`) pour une petite liste de lignes.

    Résolution **cache only** : `yahoo.fetch_identity_cached` ne fait AUCUN appel
    réseau (il rend None si l'identité n'est pas déjà en cache). Le nom est un
    ornement best-effort : le front retombe sur le ticker. On évite ainsi ~10
    requêtes `info` (0,5-2 s chacune) qui bloquaient le premier rendu du Résumé.
    """
    for row in rows:
        try:
            ident = yahoo.fetch_identity_cached(row["ticker"])
        except Exception:  # dégradation gracieuse : le nom est optionnel
            continue
        if ident and ident.name:
            row["name"] = ident.name


def resolve_names(tickers: list[str]) -> dict[str, str | None]:
    """Résout les noms de société (yfinance `identity`) HORS du chemin critique.

    Complément **paresseux** de `summary()` : appelé par le front APRÈS le premier
    rendu, il tolère le réseau (contrairement à `_attach_names`, cache only). Un
    ticker en échec vaut None — le front conserve alors l'affichage du ticker.
    Les doublons et entrées vides sont ignorés, et la liste est **bornée** à
    `config.PORTFOLIO_NAMES_MAX` (chaque appel `info` étant synchrone et lent).
    """
    out: dict[str, str | None] = {}
    for raw in tickers:
        ticker = (raw or "").strip().upper()
        if not ticker or ticker in out:
            continue
        if len(out) >= config.PORTFOLIO_NAMES_MAX:
            logger.warning(
                "Portefeuille : plafond de noms atteint (%d), tickers ignorés",
                config.PORTFOLIO_NAMES_MAX,
            )
            break
        try:
            ident = yahoo.fetch_identity(ticker, None)
        except Exception:  # dégradation gracieuse : le nom reste optionnel
            logger.warning("Portefeuille : nom indisponible pour %s", ticker)
            out[ticker] = None
            continue
        out[ticker] = ident.name if ident else None
    return out


def _accounts_breakdown(
    tx_all: list[dict],
    accounts: list[dict],
    last_prices: dict[str, float | None],
    account_id: int | None,
) -> list[dict]:
    """Valeur de marché par compte (donut « Répartition des comptes »).

    La valeur est recalculée compte par compte depuis ses propres transactions
    (positions consolidées « comme une entreprise »), puis le dernier cours connu
    est appliqué. Un compte sans position valorisable est omis.
    """
    by_account: dict[int, list[dict]] = {}
    for t in tx_all:
        by_account.setdefault(int(t["account_id"]), []).append(t)
    names = {int(a["id"]): a["name"] for a in accounts}
    out: list[dict] = []
    for acc_id, txs in by_account.items():
        if account_id is not None and acc_id != account_id:
            continue
        value = 0.0
        for pos in portfolio_engine.positions_from_transactions(txs):
            price = last_prices.get(pos.ticker)
            if pos.quantity > 0 and price is not None:
                value += pos.quantity * price
        if value <= 0:
            continue
        out.append({"account_id": acc_id, "name": names.get(acc_id, "—"), "value": round(value, 2)})
    out.sort(key=lambda r: r["value"], reverse=True)
    return out


def _holdings_breakdown(rows: list[dict]) -> list[dict]:
    """Valeur de marché par TITRE (donut « Répartition des titres »).

    Une ligne par position valorisable (cours connu), triée par valeur
    décroissante — sert la vue « par titres » du donut (à côté de « par
    comptes »). `rows` provient de `_position_rows(tx, …)` : la répartition suit
    donc le filtre de compte courant. Les noms de société sont résolus en
    **cache uniquement** (`_attach_names`) : le front retombe sur le ticker.
    """
    out = [
        {"ticker": r["ticker"], "name": None, "value": r["market_value"]}
        for r in rows
        if r["market_value"] is not None and r["market_value"] > 0
    ]
    out.sort(key=lambda r: r["value"], reverse=True)
    _attach_names(out)
    return out


def _warnings(rows: list[dict], tickers: list[str], prices: dict) -> list[str]:
    """Badges de fiabilité : tickers sans cours, positions non valorisables."""
    missing = [tk for tk in tickers if tk not in prices]
    if missing:
        return [f"Cours indisponibles : {', '.join(missing)}"]
    if any(r["perf"] is None for r in rows):
        return ["Certaines positions n'ont pas de cours : exclues du Top/Flop."]
    return []


def _empty_summary(bench: str, period: str) -> dict:
    """Résumé vide (aucune transaction) : structure complète, valeurs nulles."""
    bench_meta = next(
        (b for b in config.PORTFOLIO_BENCHMARKS if b["ticker"] == bench),
        {"key": "custom", "ticker": bench, "label": bench},
    )
    return {
        "dates": [],
        "period": period,
        "period_start": None,
        "benchmark": dict(bench_meta),
        "portfolio": [],
        "benchmark_curve": [],
        "kpis": {
            "total_value": 0.0,
            "invested": 0.0,
            "total_return": None,
            "total_return_pct": None,
            "period_return_pct": None,
            "annualized_pct": None,
            "dividends": 0.0,
            "dividend_yield_pct": None,
            "benchmark_period_pct": None,
        },
        "accounts": [],
        "holdings": [],
        "account": None,
        "top": [],
        "flop": [],
        "warnings": [],
    }


# --- Risque : drawdown + corrélation (#17.3) ---------------------------------


def _benchmark_meta(bench: str) -> dict:
    """Métadonnées d'affichage d'un benchmark (nom curé ou ticker libre)."""
    return next(
        (b for b in config.PORTFOLIO_BENCHMARKS if b["ticker"] == bench),
        {"key": "custom", "ticker": bench, "label": bench},
    )


class PortfolioContext(TypedDict):
    """Contexte commun du portefeuille (#24), consommé par 3 cas d'usage.

    Une SEULE construction sert `summary()`, `risk()` (et `correlation_test()`) et
    `performance()` : trois copies de cette orchestration avaient laissé diverger
    l'axe temps (le bug de fuseaux se propageait graphe par graphe) et rendaient
    toute correction triplement coûteuse. Les champs restent vides/neutres quand
    la portée n'a aucune transaction (`tx == []`) ou qu'aucune date n'est
    exploitable : l'appelant décide d'afficher un vide ou de refuser.
    """

    period: str
    bench: str
    tx: list[dict]
    div: list[dict]
    index: pd.DatetimeIndex | None
    dates: list[str]
    start_idx: int
    twr: list[float]
    bench_curve: list[float | None]
    values: list[float]
    flows: list[float]
    raw_by_ticker: dict[str, list[float | None]]
    adj_by_ticker: dict[str, list[float | None]]
    prices: dict
    rows: list[dict]
    held: list[str]
    tickers: list[str]
    empty: bool


def _portfolio_context(
    account_id: int | None,
    benchmark: str | None,
    period: str | None,
    tag: str | None,
) -> PortfolioContext:
    """Contexte UNIQUE des sections portefeuille (#24) : cours, axe, TWR, lignes.

    Un seul passage sur `data/` (les prix sortent du cache : aucun appel réseau
    supplémentaire) et **un seul axe temps**, celui des séances (`_trading_index`).
    `ValueError` si la période est inconnue ou le benchmark introuvable.

    Ne fait AUCUNE analyse fondamentale (coûteuse) : `performance()` l'ajoute à
    part, par ligne, pour ses stats agrégées.
    """
    period = _validate_period(period)
    bench = _validate_benchmark(benchmark)
    tx = portfolio_data.list_transactions(account_id, tag)
    ctx: PortfolioContext = {
        "period": period,
        "bench": bench,
        "tx": tx,
        "div": [],
        "index": None,
        "dates": [],
        "start_idx": 0,
        "twr": [],
        "bench_curve": [],
        "values": [],
        "flows": [],
        "raw_by_ticker": {},
        "adj_by_ticker": {},
        "prices": {},
        "rows": [],
        "held": [],
        "tickers": [],
        "empty": True,
    }
    if not tx:
        return ctx

    # Tickers de la FENÊTRE historique (TWR/drawdown) : toutes les transactions
    # de la portée, y compris les lignes soldées (leur performance passée reste
    # légitime dans la courbe).
    tickers = sorted({str(t["ticker"]).upper() for t in tx})
    # Tickers DÉTENUS aujourd'hui (quantité > 0) : la matrice de corrélation ne
    # porte que sur les lignes encore en portefeuille — une entreprise sortie du
    # portefeuille n'a rien à y faire (retour utilisateur).
    held = sorted(
        pos.ticker for pos in portfolio_engine.positions_from_transactions(tx) if pos.quantity > 0
    )
    prices: dict = {}
    for tk in sorted(set(tickers) | {bench}):
        try:
            prices[tk] = yahoo.fetch_prices(tk)
        except yahoo.TickerNotFound:
            logger.warning("Portefeuille : cours indisponibles pour %s", tk)
    if bench not in prices:
        raise ValueError(f"Benchmark introuvable sur Yahoo : {bench}")

    start = min(str(t["trade_date"]) for t in tx)
    idx = _trading_index(prices, bench, start)
    if len(idx) == 0:
        return ctx
    dates = [d.date().isoformat() for d in idx]

    div = _scope_dividends(portfolio_data.list_dividends(), tx, account_id, tag)
    raw_by_ticker = {tk: _series_to_list(_align(ps.raw, idx).ffill()) for tk, ps in prices.items()}
    adj_by_ticker = {
        tk: _series_to_list(_align(ps.adjusted, idx).ffill()) for tk, ps in prices.items()
    }
    values, flows = portfolio_engine.daily_values(
        dates, raw_by_ticker, tx, _confirmed_dividends(div)
    )
    twr = portfolio_engine.twr_series(values, flows)
    bench_curve = portfolio_engine.benchmark_series(adj_by_ticker[bench])
    start_idx = portfolio_engine.period_start_index(dates, period)

    last_prices = {tk: _last_price(ps) for tk, ps in prices.items()}
    ctx.update(
        {
            "div": div,
            "index": idx,
            "dates": dates,
            "start_idx": start_idx,
            "twr": twr,
            "bench_curve": bench_curve,
            "values": values,
            "flows": flows,
            "raw_by_ticker": raw_by_ticker,
            "adj_by_ticker": adj_by_ticker,
            "prices": prices,
            "rows": _position_rows(tx, last_prices),
            "held": held,
            "tickers": tickers,
            "empty": False,
        }
    )
    return ctx


def _risk_context(
    account_id: int | None,
    benchmark: str | None,
    period: str | None,
    tag: str | None,
) -> dict:
    """Vue « Risque » du contexte commun (#17.3), fenêtrée sur la période.

    Simple projection de `_portfolio_context` : `dates_w`/`twr_w`/`bench_w` sont
    les séries **tronquées au début de la période**, forme attendue par
    `risk()` et `correlation_test()`. Aucune orchestration propre — c'est
    précisément la duplication supprimée au #24.
    """
    ctx = _portfolio_context(account_id, benchmark, period, tag)
    start_idx = ctx["start_idx"]
    return {
        "period": ctx["period"],
        "bench": ctx["bench"],
        "tx": ctx["tx"],
        "index": ctx["index"],
        "start_idx": start_idx,
        "dates_w": ctx["dates"][start_idx:],
        "twr_w": ctx["twr"][start_idx:],
        "bench_w": ctx["bench_curve"][start_idx:],
        "adj_by_ticker": ctx["adj_by_ticker"],
        "prices": ctx["prices"],
        "held": ctx["held"],
        "tickers": ctx["tickers"],
    }


def _correlation_block(ctx: dict) -> dict:
    """Rendements log des lignes détenues + matrice réordonnée (#17.3).

    Extrait de `risk()` pour être partagé avec `correlation_test()` : les deux
    doivent voir EXACTEMENT le même ordre de colonnes (clustering) pour que la
    ligne du candidat s'aligne sous la matrice.
    """
    start_idx = ctx["start_idx"]
    adj = ctx["adj_by_ticker"]
    returns = portfolio_engine.log_returns_by_ticker(
        ctx["dates_w"],
        {tk: adj[tk][start_idx:] for tk in ctx["held"] if tk in ctx["prices"]},
    )
    corr = portfolio_engine.correlation_matrix(returns, config.PORTFOLIO_CORR_MIN_OBS)
    corr = _reorder_correlation(
        corr, portfolio_engine.correlation_order(corr["tickers"], corr["matrix"])
    )
    return {"returns": returns, "matrix": corr}


def risk(
    account_id: int | None,
    benchmark: str | None,
    period: str | None,
    tag: str | None = None,
) -> dict:
    """Risque du portefeuille (#17.3) : drawdown (vs benchmark) + corrélations.

    Assemble : la courbe de **drawdown** du portefeuille et du benchmark (index de
    performance TWR / buy-and-hold, base 1), les **métriques de drawdown** (perte
    max, baisse en cours, plus longue récupération, volatilité réalisée, meilleur
    et pire mois) et la **matrice de corrélation** entre les lignes DÉTENUES
    aujourd'hui (quantité > 0) — rendements log quotidiens sur la fenêtre de la
    période ; une ligne soldée n'y figure pas (sa performance passée reste, elle,
    dans la courbe TWR). Réutilise le TWR du Résumé : aucun réseau supplémentaire
    si les cours sont en cache.

    `account_id` et `tag` (#17.6) restreignent la portée. `ValueError` si la
    période est inconnue ou le benchmark introuvable.
    """
    ctx = _risk_context(account_id, benchmark, period, tag)
    if not ctx["dates_w"]:
        return _empty_risk(ctx["bench"], ctx["period"])

    dates_w = ctx["dates_w"]
    twr_w = ctx["twr_w"]
    bench_w = ctx["bench_w"]

    pf_index = [1.0 + t / 100.0 for t in twr_w]
    bench_index = [None if b is None else 1.0 + b / 100.0 for b in bench_w]

    dd_pf = portfolio_engine.drawdown_series(pf_index)
    dd_bench = portfolio_engine.drawdown_series(bench_index)
    metrics = portfolio_engine.drawdown_metrics(pf_index, dates_w)
    bench_metrics = portfolio_engine.drawdown_metrics(bench_index, dates_w)
    months = portfolio_engine.monthly_returns(twr_w, dates_w)
    pcts = [m["pct"] for m in months]
    metrics["volatility_pct"] = _round_or_none(portfolio_engine.realized_volatility(pf_index))
    bench_metrics["volatility_pct"] = _round_or_none(
        portfolio_engine.realized_volatility(bench_index)
    )
    if pcts:
        metrics["best_month_pct"] = max(pcts)
        metrics["worst_month_pct"] = min(pcts)
    else:
        metrics["best_month_pct"] = None
        metrics["worst_month_pct"] = None

    corr = _correlation_block(ctx)["matrix"]
    _attach_names(corr["excluded"])  # noms best-effort pour les lignes écartées

    corr_avg = portfolio_engine.mean_offdiagonal(corr["matrix"])
    warnings = _risk_warnings(ctx["held"], ctx["prices"], corr)

    return {
        "dates": dates_w,
        "period": ctx["period"],
        "period_start": dates_w[0] if dates_w else None,
        "benchmark": _benchmark_meta(ctx["bench"]),
        "drawdown": [None if v is None else round(v, 2) for v in dd_pf],
        "benchmark_drawdown": [None if v is None else round(v, 2) for v in dd_bench],
        "metrics": metrics,
        "benchmark_metrics": bench_metrics,
        "months": months,
        "corr_avg": None if corr_avg is None else round(corr_avg, 4),
        "correlation": corr,
        "warnings": warnings,
    }


def correlation_test(
    account_id: int | None,
    benchmark: str | None,
    period: str | None,
    tag: str | None,
    ticker: str | None,
) -> dict:
    """Test de corrélation (#17.3) : impact d'un titre candidat sur le périmètre.

    Corrèle le ticker candidat (rendements log quotidiens, même fenêtre de période)
    à chaque ligne DÉTENUE du périmètre, dans l'ordre des colonnes de la matrice
    (même clustering) : la ligne renvoyée s'aligne sous la matrice. Calcule aussi
    la **corrélation moyenne** hors diagonale AVANT (`current_avg`) et APRÈS
    (`new_avg`) ajout du candidat, plus le `delta` signé — un titre peu corrélé
    abaisse la moyenne (diversification), un titre très corrélé la relève.

    `ValueError` (-> 422) si le ticker est vide, introuvable sur Yahoo, déjà
    détenu, ou si le périmètre n'a aucune ligne exploitable.
    """
    code = (ticker or "").strip().upper()
    if not code:
        raise ValueError("Ticker vide.")
    ctx = _risk_context(account_id, benchmark, period, tag)
    if not ctx["dates_w"]:
        raise ValueError("Aucune transaction dans le périmètre : rien à corréler.")
    block = _correlation_block(ctx)
    matrix = block["matrix"]
    labels = matrix["tickers"]
    if not labels:
        raise ValueError("Pas assez d'historique pour corréler les lignes du périmètre.")
    if code in labels:
        raise ValueError(f"{code} fait déjà partie des lignes détenues.")
    try:
        prices = yahoo.fetch_prices(code)
    except yahoo.TickerNotFound:
        raise ValueError(f"Ticker introuvable sur Yahoo : {code}") from None

    start_idx = ctx["start_idx"]
    cand_w = _series_to_list(_align(prices.adjusted, ctx["index"]).ffill())[start_idx:]
    cand_returns = portfolio_engine.log_returns_by_ticker(ctx["dates_w"], {code: cand_w}).get(
        code, {}
    )
    row_map = portfolio_engine.correlation_row(
        cand_returns,
        {t: block["returns"][t] for t in labels},
        config.PORTFOLIO_CORR_MIN_OBS,
    )
    row = [row_map[t] for t in labels]

    current = portfolio_engine.mean_offdiagonal(matrix["matrix"])
    extended = [list(r) + [row[i]] for i, r in enumerate(matrix["matrix"])]
    extended.append(list(row) + [None])
    new_avg = portfolio_engine.mean_offdiagonal(extended)

    obs = len(cand_returns)
    warning = None
    if obs < config.PORTFOLIO_CORR_MIN_OBS:
        warning = (
            f"Historique insuffisant pour {code} : {obs} observations "
            f"(minimum {config.PORTFOLIO_CORR_MIN_OBS})."
        )
    return {
        "ticker": code,
        "tickers": labels,
        "row": row,
        "obs": obs,
        "current_avg": None if current is None else round(current, 4),
        "new_avg": None if new_avg is None else round(new_avg, 4),
        "delta": None if current is None or new_avg is None else round(new_avg - current, 4),
        "warning": warning,
    }


def _reorder_correlation(corr: dict, order: list[int]) -> dict:
    """Réordonne une matrice de corrélation selon `order` (indices de clustering)."""
    tickers = [corr["tickers"][i] for i in order]
    matrix = [[corr["matrix"][i][j] for j in order] for i in order]
    return {"tickers": tickers, "matrix": matrix, "excluded": corr["excluded"]}


def _risk_warnings(tickers: list[str], prices: dict, corr: dict) -> list[str]:
    """Badges de fiabilité de la section Risque."""
    warnings: list[str] = []
    missing = [tk for tk in tickers if tk not in prices]
    if missing:
        warnings.append(f"Cours indisponibles : {', '.join(missing)}")
    excluded = corr.get("excluded") or []
    if excluded:
        names = ", ".join(f"{e['ticker']} ({e['obs']} obs)" for e in excluded)
        warnings.append(f"Corrélations écartées faute d'historique suffisant : {names}")
    return warnings


def _empty_risk(bench: str, period: str) -> dict:
    """Risque vide (aucune transaction) : structure complète, valeurs neutres."""
    return {
        "dates": [],
        "period": period,
        "period_start": None,
        "benchmark": _benchmark_meta(bench),
        "drawdown": [],
        "benchmark_drawdown": [],
        "metrics": {
            "max_drawdown_pct": 0.0,
            "current_drawdown_pct": 0.0,
            "recovered": True,
            "longest_recovery_days": 0,
            "peak_at": None,
            "trough_at": None,
            "volatility_pct": None,
            "best_month_pct": None,
            "worst_month_pct": None,
        },
        "benchmark_metrics": {
            "max_drawdown_pct": 0.0,
            "current_drawdown_pct": 0.0,
            "recovered": True,
            "longest_recovery_days": 0,
            "peak_at": None,
            "trough_at": None,
            "volatility_pct": None,
        },
        "months": [],
        "corr_avg": None,
        "correlation": {"tickers": [], "matrix": [], "excluded": []},
        "warnings": [],
    }


# --- Performance (#17.4) -----------------------------------------------------


def _perf_line_metrics(analysis: StockAnalysis) -> dict:
    """Une cellule de stat par métrique de `config.PORTFOLIO_STAT_GROUPS`.

    Extrait d'un `StockAnalysis` les valeurs par ligne puis les emballe via
    `engine.line_stat_cell` (polarité depuis `config.PORTFOLIO_STAT_POLARITY`).
    Les valeurs de comptes sont lues de `analysis.summary` (grille du Résumé,
    SOURCE UNIQUE d'extraction — jamais recalculées ici) ; les métriques de prix
    viennent des indicateurs. `market_cap` est posé sur la ligne (catégorie
    « Général », non moyennée). Toute valeur manquante -> `{"value": None,
    "good": None}` (le front affiche « -- »).
    """
    ind = analysis.indicators
    rowmap = {row.key: row.value for card in (analysis.summary or []) for row in card.rows}
    f = analysis.fundamentals
    table = f.table if f is not None else None
    agility = None
    if table is not None and not table.empty and "Agilité" in table.index:
        ag = table.loc["Agilité"].dropna()
        agility = float(ag.iloc[0]) if len(ag) else None
    vals = {
        "quality": ind.quality.value,
        "gross_margin": rowmap.get("gross_margin"),
        "op_margin": rowmap.get("op_margin"),
        "net_margin": rowmap.get("net_margin"),
        "roe": rowmap.get("roe_1y"),
        "roce": rowmap.get("roce_1y"),
        "roic": rowmap.get("roic_1y"),
        "net_debt_ebitda": rowmap.get("net_debt_ebitda"),
        "piotroski": rowmap.get("piotroski"),
        "altman_z": rowmap.get("altman_z"),
        "agility": agility,
        "slope": ind.perf_passee.value,
        "pot_5y": ind.potential_5y.value,
        "pot_10y": ind.potential_10y.value,
        "per": rowmap.get("per"),
        "p_fcf": rowmap.get("p_fcf"),
        "p_b": rowmap.get("p_b"),
    }
    return {key: portfolio_engine.line_stat_cell(key, value) for key, value in vals.items()}


def _level(series: Sequence[float | None]) -> list[float | None]:
    """Série de performance cumulée (%) -> indice de niveau (base 1), None préservé."""
    return [None if v is None else 1.0 + v / 100.0 for v in series]


def _analyze_lines(rows: Sequence[dict], prices: dict) -> dict[str, StockAnalysis]:
    """Analyse les lignes détenues en parallèle BORNÉ, par dégradation gracieuse.

    `analysis.analyze` touche le réseau (identité + comptes) : en séquentiel, un
    portefeuille de 30 lignes en cache froid enchaînait ~120 requêtes yfinance
    avant le premier rendu (revue #17.4, finding #1). Les lignes sont donc
    analysées en parallèle borné (même nature I/O-bound que le screener) et le
    résultat est réassemblé dans l'ordre du portefeuille, ce qui garde les
    agrégations déterministes.

    Une ligne dont l'analyse échoue (ou dépasse le budget) est simplement ABSENTE
    du dict : elle n'entre ni au numérateur ni au dénominateur des moyennes
    pondérées (jamais un 0 trompeur). Partagé par la Performance (#17.4) et le
    Dividende (#17.5) pour ne pas dupliquer le bornage ni le budget.
    """
    analysable = [
        (r["ticker"], prices[r["ticker"]]) for r in rows if prices.get(r["ticker"]) is not None
    ]
    analyses: dict[str, StockAnalysis] = {}
    if not analysable:
        return analyses
    workers = min(config.PORTFOLIO_PERF_WORKERS, len(analysable))
    # Budget GLOBAL (revue #17.4, finding #21) : `analyze` fait du réseau et
    # `_with_retry` n'a pas de borne propre. Sans plafond, un appel qui pend
    # figeait l'onglet indéfiniment. Même garde-fou que le screener :
    # `wait(timeout=...)` puis `shutdown(wait=False)`, pour qu'un thread bloqué
    # ne retienne jamais le retour.
    budget = config.PORTFOLIO_PERF_TIMEOUT * workers
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        futures = {pool.submit(analysis_service.analyze, tk, ps): tk for tk, ps in analysable}
        done, pending = wait(futures, timeout=budget)
        for fut in done:
            tk = futures[fut]
            try:
                analyses[tk] = fut.result()
            except (yahoo.TickerNotFound, ValueError, KeyError, IndexError) as exc:
                logger.warning("Portefeuille : analyse impossible pour %s (%s)", tk, exc)
        for fut in pending:
            fut.cancel()
            logger.warning("Portefeuille : analyse abandonnée après %ss (%s)", budget, futures[fut])
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return analyses


def _performance_context(
    account_id: int | None,
    benchmark: str | None,
    period: str | None,
    tag: str | None,
) -> dict:
    """Vue « Performance » du contexte commun (#17.4).

    Simple projection de `_portfolio_context` : plus aucune orchestration propre
    (cours, axe, TWR, lignes), donc plus aucun axe temps susceptible de diverger
    du Résumé et du Risque. `empty=True` quand la portée n'a aucune transaction.
    """
    ctx = _portfolio_context(account_id, benchmark, period, tag)
    return {
        "period": ctx["period"],
        "bench": ctx["bench"],
        "tx": ctx["tx"],
        "empty": ctx["empty"],
        "index": ctx["index"],
        "dates": ctx["dates"],
        "start_idx": ctx["start_idx"],
        "twr": ctx["twr"],
        "bench_curve": ctx["bench_curve"],
        "raw_by_ticker": ctx["raw_by_ticker"],
        "adj_by_ticker": ctx["adj_by_ticker"],
        "prices": ctx["prices"],
        "rows": ctx["rows"],
        "tickers": ctx["tickers"],
    }


def _weights_by_ticker(rows: list[dict]) -> dict[str, float]:
    """Poids de marché (fraction) de chaque ligne détenue, normalisés à 1.

    Les lignes non valorisables (cours inconnu) sont écartées : elles n'ont pas de
    poids et n'entrent ni au numérateur ni au dénominateur (jamais un 0 trompeur).
    """
    total = sum(r["market_value"] for r in rows if r.get("market_value"))
    if not total or total <= 0:
        return {r["ticker"]: 0.0 for r in rows}
    return {r["ticker"]: (r["market_value"] or 0.0) / total for r in rows}


def performance(
    account_id: int | None,
    benchmark: str | None,
    period: str | None,
    tag: str | None = None,
) -> dict:
    """Performance du portefeuille (#17.4) : stats pondérées, mensuels, rétrospective.

    Assemble, sur le périmètre sélectionné (compte et/ou étiquette) et la période :
    - la **synthèse fondamentale pondérée** (`aggregate_statistics`) des lignes
      détenues, chacune évaluée via `services.analysis.analyze` (mêmes métriques que
      la fiche) ; les poids sont les poids de marché (cohérents avec le donut) ;
    - le **tableau mensuel** du portefeuille et du benchmark (`monthly_table`,
      chaînage TWR identique au Résumé) ;
    - la **contribution par entreprise** (`contributions`) ;
    - les **ratios ajustés au risque** (Sharpe/Sortino) du portefeuille ET du
      benchmark, taux sans risque lu des réglages persistés ;
    - la **rétrospective** des points d'entrée/sortie (`entry_exit_retrospective`).
    """
    ctx = _performance_context(account_id, benchmark, period, tag)
    if ctx["empty"]:
        return _empty_performance(ctx["bench"], ctx["period"])

    bench = ctx["bench"]
    period = ctx["period"]
    start_idx = ctx["start_idx"]
    dates = ctx["dates"]
    twr = ctx["twr"]
    bench_curve = ctx["bench_curve"]
    rows = ctx["rows"]
    weights = _weights_by_ticker(rows)

    # --- Stats agrégées (A) ---------------------------------------------------
    # `analysis.analyze` touche le réseau (identité + comptes) : en séquentiel, un
    # portefeuille de 30 lignes en cache froid enchaînait ~120 requêtes yfinance
    # avant le premier rendu (revue #17.4, finding #1). Les lignes sont donc
    # analysées en parallèle BORNÉ (même nature I/O-bound que le screener) : le
    # résultat est réassemblé dans l'ordre du portefeuille, donc l'agrégation
    # pondérée reste déterministe.
    analyses = _analyze_lines(rows, ctx["prices"])

    line_rows: list[dict] = []
    line_weights: list[float] = []
    for r in rows:
        analysis = analyses.get(r["ticker"])
        if analysis is None:
            continue
        line_rows.append(_perf_line_metrics(analysis))
        # Poids aligné 1:1 sur les lignes réellement analysées (les lignes sans
        # analyse sont exclues du dénominateur, jamais comptées à poids nul).
        line_weights.append(weights.get(r["ticker"], 0.0))

    # Cellules « Général » (non moyennées, valeurs directes) : posées sur une ligne
    # dédiée à poids NUL, pour qu'elles ne faussent pas l'agrégation pondérée.
    # `aggregate_statistics` recopie ces clés telles quelles (jamais moyennées).
    market_values = [r["market_value"] for r in rows]
    general: dict = {
        "count": portfolio_engine.line_stat_cell("count", float(len(rows))),
        "top5_weight": portfolio_engine.line_stat_cell(
            "top5_weight", portfolio_engine.weighted_share(market_values, market_values, 5)
        ),
        "market_cap": portfolio_engine.line_stat_cell(
            "market_cap",
            sum(r["market_value"] for r in rows if r.get("market_value")) or None,
        ),
    }
    stats = portfolio_engine.aggregate_statistics(
        [general, *line_rows], [0.0, *line_weights], config.PORTFOLIO_STAT_GROUPS
    )

    # --- Mensuels (B) ---------------------------------------------------------
    monthly = {
        "portfolio": portfolio_engine.monthly_table(twr[start_idx:], dates[start_idx:]),
        "benchmark": portfolio_engine.monthly_table(bench_curve[start_idx:], dates[start_idx:]),
        "months": config.PORTFOLIO_MONTHS,
    }

    # --- Contribution par entreprise (B) --------------------------------------
    # `contributions` attend une perf en % (convention du moteur : poids × perf%).
    # Ne PAS diviser par 100 : `r["perf"]` est déjà en pourcent.
    perf_by_ticker = {r["ticker"]: r["perf"] for r in rows}
    contrib = portfolio_engine.contributions(perf_by_ticker, weights)
    companies = [
        {
            "ticker": r["ticker"],
            "name": None,
            "weight_pct": None
            if weights.get(r["ticker"]) is None
            else round(weights[r["ticker"]] * 100, 2),
            "perf_pct": r["perf"],
            "contribution_pct": contrib["by_ticker"].get(r["ticker"]),
        }
        for r in rows
    ]
    _attach_names(companies)

    # --- Ratios ajustés au risque (A) -----------------------------------------
    # Calculés sur PLUSIEURS fenêtres (TTM / 3A / 5A / MAX) pré-calculées ici :
    # le passage sur les prix est déjà fait, ces fenêtres ne coûtent donc AUCUN
    # I/O supplémentaire et le front peut basculer sans refetch. Une période n'est
    # retenue que si l'historique la couvre réellement (start_idx > 0) ; `max` est
    # toujours proposée. La forme historique `portfolio`/`benchmark` (= MAX) est
    # conservée pour la compatibilité des consommateurs existants.
    risk_free_bp = cache_data.get_settings().get("portfolio_risk_free", 0)
    risk_free_pct = float(risk_free_bp) / 100.0

    def _risk_for(idx_start: int) -> dict:
        return {
            "portfolio": {
                "sharpe": portfolio_engine.sharpe_ratio(_level(twr[idx_start:]), risk_free_pct),
                "sortino": portfolio_engine.sortino_ratio(_level(twr[idx_start:]), risk_free_pct),
            },
            "benchmark": {
                "sharpe": portfolio_engine.sharpe_ratio(
                    _level(bench_curve[idx_start:]), risk_free_pct
                ),
                "sortino": portfolio_engine.sortino_ratio(
                    _level(bench_curve[idx_start:]), risk_free_pct
                ),
            },
        }

    by_period: dict[str, dict] = {}
    for rp in config.PORTFOLIO_RISK_PERIODS:
        rp_idx = portfolio_engine.period_start_index(dates, rp)
        if rp == "max" or rp_idx > 0:
            by_period[rp] = _risk_for(rp_idx)
    max_risk = by_period.get("max", _risk_for(0))
    risk = {
        "risk_free_pct": risk_free_pct,
        "periods": list(by_period.keys()),
        "by_period": by_period,
        "portfolio": max_risk["portfolio"],
        "benchmark": max_risk["benchmark"],
    }

    # --- Rétrospective points d'entrée/sortie (C) -----------------------------
    # Titre ET benchmark sur la série AJUSTÉE (dividendes réinvestis des deux
    # côtés) : comparer un titre en cours brut à un benchmark en total return
    # serait inéquitable (droite d'Obole : la perf passée se lit sur l'ajusté).
    adj_prices_by_ticker = {
        tk: ctx["adj_by_ticker"][tk] for tk in ctx["tickers"] if tk in ctx["adj_by_ticker"]
    }
    retrospective = portfolio_engine.entry_exit_retrospective(
        dates, ctx["tx"], adj_prices_by_ticker, ctx["adj_by_ticker"].get(bench, [])
    )

    # --- Grand tableau (C) ----------------------------------------------------
    table = [
        {
            "ticker": r["ticker"],
            "name": None,
            "weight_pct": None
            if weights.get(r["ticker"]) is None
            else round(weights[r["ticker"]] * 100, 2),
            "perf_pct": r["perf"],
            "contribution_pct": contrib["by_ticker"].get(r["ticker"]),
            "market_value": r["market_value"],
        }
        for r in rows
    ]
    _attach_names(table)

    return {
        "period": period,
        "period_start": dates[start_idx] if dates else None,
        "benchmark": _benchmark_meta(bench),
        "stat_groups": config.PORTFOLIO_STAT_GROUPS,
        "stats": stats,
        "monthly": monthly,
        "contributions": {"items": companies, "total_pct": contrib["total"]},
        "risk_adjusted": risk,
        "retrospective": retrospective,
        "table": table,
        "warnings": _warnings(rows, ctx["tickers"], ctx["prices"]),
    }


def security_detail(ticker: str, benchmark: str | None = None) -> dict:
    """Détail d'un titre pour la modale Performance : perf cumulée + benchmark alignés.

    Renvoie la série ajustée du titre (dates + `price_adj`, via
    `serialize.security_chart_payload`) et la **courbe du benchmark réindexée sur
    les MÊMES dates** (forward-fill) pour un tracé comparatif de performance
    cumulée (rebasée à 0 % côté front). Le graphe ne trace aucune régression. Les
    prix viennent du cache ; `ValueError` si le ticker est vide,
    `yahoo.TickerNotFound` si le titre ou le benchmark est introuvable.
    """
    ticker = (ticker or "").strip().upper()
    if not ticker:
        raise ValueError("Ticker vide")
    bench = _validate_benchmark(benchmark)
    prices = yahoo.fetch_prices(ticker)
    bench_prices = yahoo.fetch_prices(bench)
    chart = serialize.security_chart_payload(prices)
    # Alignement du benchmark sur les dates EXACTES du titre (même décimation) :
    # les deux séries partagent alors le même axe X, condition d'un rebasage commun.
    # Les index Yahoo sont tz-aware, et chaque place a SON fuseau (titre US
    # `America/New_York` vs benchmark Paris `Europe/Paris`) : un reindex entre deux
    # fuseaux distincts ne matcherait rien (tout NaN). On normalise donc le benchmark
    # en naïf, comme les dates du chart (mêmes dates ISO), avant reindex (même patron
    # que `engine/dividends.py`).
    bench_adjusted = bench_prices.adjusted
    if getattr(bench_adjusted.index, "tz", None) is not None:
        bench_adjusted = bench_adjusted.copy()
        bench_adjusted.index = bench_adjusted.index.tz_localize(None)
    idx = pd.to_datetime(chart["dates"])
    bench_aligned = bench_adjusted.reindex(idx).ffill()
    return {
        "ticker": ticker,
        "benchmark": _benchmark_meta(bench),
        "chart": chart,
        "benchmark_curve": _series_to_list(bench_aligned),
    }


def _empty_performance(bench: str, period: str) -> dict:
    """Performance vide (aucune transaction) : structure complète, valeurs neutres."""
    return {
        "period": period,
        "period_start": None,
        "benchmark": _benchmark_meta(bench),
        "stat_groups": config.PORTFOLIO_STAT_GROUPS,
        "stats": {},
        "monthly": {
            "portfolio": {"years": [], "rows": []},
            "benchmark": {"years": [], "rows": []},
            "months": config.PORTFOLIO_MONTHS,
        },
        "contributions": {"items": [], "total_pct": None},
        "risk_adjusted": {
            "risk_free_pct": config.PORTFOLIO_RISK_FREE_DEFAULT,
            "periods": [],
            "by_period": {},
            "portfolio": {"sharpe": None, "sortino": None},
            "benchmark": {"sharpe": None, "sortino": None},
        },
        "retrospective": [],
        "table": [],
        "warnings": [],
    }


# --- Dividende du portefeuille (#17.5) --------------------------------------


def _last_numeric(mapping: dict | None) -> float | None:
    """Dernière valeur NON NULLE d'une série {année: valeur} (exercice le plus récent)."""
    if not mapping:
        return None
    for year in sorted(mapping, reverse=True):
        value = mapping[year]
        if value is not None:
            return float(value)
    return None


def _net_income_last(analysis: StockAnalysis | None) -> float | None:
    """Bénéfice net du dernier exercice, lu du tableau normalisé des comptes.

    Source UNIQUE d'extraction : `fundamentals.table` (la grille du Résumé), jamais
    recalculée depuis les états bruts. None si la ligne manque (ETF, banque sans
    poste standardisé).
    """
    table = analysis.fundamentals.table if analysis and analysis.fundamentals else None
    if table is None or table.empty or "Bénéfice net" not in table.index:
        return None
    row = table.loc["Bénéfice net"].dropna()
    return float(row.iloc[0]) if len(row) else None


def dividend_page(account_id: int | None, tag: str | None = None) -> dict:
    """Page Dividende du portefeuille (#17.5) : revenu reçu, KPI agrégés, pilotage.

    Assemble, sur la portée sélectionnée (compte et/ou étiquette) :
    - le revenu par année / mois / payeur (`engine.dividend_income`), avec la
      distinction confirmé / proposé — une proposition n'entre dans AUCUN agrégat;
    - les KPI de revenu agrégés (`engine.dividend_metrics`) : rendement courant,
      yield on cost, payout agrégé et shareholder yield, chacun avec son taux de
      couverture (sans lui le ratio mentirait par omission) ;
    - la **contribution du dividende à la performance**, mesurée par DOUBLE TWR :
      la courbe chaînée avec les dividendes (revenu encaissé) moins la même courbe
      sans eux. C'est une mesure exacte, sans l'hypothèse de réinvestissement que
      suppose l'utilisation d'une série ajustée ;
    - le tableau par ligne (rendement, rendement sur coût, poids du revenu vs
      poids du capital, croissance 5 ans, payout).

    Les prix viennent du cache yfinance (aucun appel réseau de plus que la
    Performance) et l'analyse fondamentale par ligne réutilise le helper borné
    `_analyze_lines`. Portée vide -> structure complète, valeurs neutres.
    """
    tx = portfolio_data.list_transactions(account_id, tag)
    div_all = portfolio_data.list_dividends()
    div = _scope_dividends(div_all, tx, account_id, tag)

    income = portfolio_engine.dividend_income(div)
    empty = _empty_dividend_page(income)
    if not tx:
        return empty

    tickers = sorted({str(t["ticker"]).upper() for t in tx})
    prices: dict = {}
    for tk in tickers:
        try:
            prices[tk] = yahoo.fetch_prices(tk)
        except yahoo.TickerNotFound:
            logger.warning("Dividende : cours indisponibles pour %s", tk)
    if not prices:
        return empty

    last_prices = {tk: _last_price(ps) for tk, ps in prices.items()}
    rows = _position_rows(tx, last_prices)
    if not rows:
        return empty

    analyses = _analyze_lines(rows, prices)

    # --- Contribution du dividende à la performance (double TWR) --------------
    # Deux courbes identiques, à UNE différence près : la seconde n'encaisse pas
    # les dividendes. L'écart annualisé des deux TWR est la contribution réelle du
    # revenu, sans hypothèse de réinvestissement (contrairement à une série
    # ajustée). Aucun appel réseau supplémentaire : les prix sont déjà là.
    # Les DEUX taux annualisés sont conservés dans le payload (pas seulement leur
    # écart) : ils rendent la soustraction auditable côté client.
    contribution_pct = None
    twr_with_pct = None
    twr_without_pct = None
    start = min(str(t["trade_date"]) for t in tx)
    # Même axe de SÉANCES que les autres sections : le double TWR doit être
    # calculé sur le calendrier du portefeuille, pas sur un axe propre (le bug
    # de fuseaux y créait aussi des points intra-jour).
    idx = _trading_index(prices, None, start, field="raw")
    if len(idx) > 1:
        dates = [d.date().isoformat() for d in idx]
        raw_by_ticker = {
            tk: _series_to_list(_align(ps.raw, idx).ffill()) for tk, ps in prices.items()
        }
        confirmed = _confirmed_dividends(div)
        values_with, flows_with = portfolio_engine.daily_values(dates, raw_by_ticker, tx, confirmed)
        values_without, flows_without = portfolio_engine.daily_values(dates, raw_by_ticker, tx, [])
        twr_with = portfolio_engine.twr_series(values_with, flows_with)
        twr_without = portfolio_engine.twr_series(values_without, flows_without)
        days = (idx[-1] - idx[0]).days
        ann_with = portfolio_engine.annualized_return(
            portfolio_engine.period_return(twr_with, 0), days
        )
        ann_without = portfolio_engine.annualized_return(
            portfolio_engine.period_return(twr_without, 0), days
        )
        if ann_with is not None and ann_without is not None:
            twr_with_pct = round(ann_with, 2)
            twr_without_pct = round(ann_without, 2)
            contribution_pct = round(ann_with - ann_without, 2)

    # --- Poids : revenu (payeurs) vs capital (valeur de marché) ---------------
    income_weights = portfolio_engine.income_weights(
        {c["ticker"]: c["amount"] for c in income["by_company"]}
    )
    market_value_by_ticker = {r["ticker"]: r["market_value"] for r in rows if r.get("market_value")}
    total_market_value = sum(v for v in market_value_by_ticker.values() if v and v > 0)

    dps_ttm: dict[str, float | None] = {}
    cagr_by_ticker: dict[str, float | None] = {}
    shareholder_ps: dict[str, float | None] = {}
    dividend_paid: dict[str, float | None] = {}
    net_income: dict[str, float | None] = {}
    for tk in (r["ticker"] for r in rows):
        analysis = analyses.get(tk)
        payload = analysis.fundamentals.dividend if analysis and analysis.fundamentals else None
        payload = payload or {}
        events = payload.get("events") or {}
        dps_ttm[tk] = dividends_mod.ttm_per_share(events)
        stats = payload.get("stats") or {}
        horizons = config.DIVIDEND_CAGR_HORIZONS
        cagr_map = stats.get("cagr") or {}
        cagr_by_ticker[tk] = cagr_map.get(horizons[0]) if horizons else None
        buybacks = payload.get("buybacks_per_share") or {}
        per_share_ttm = dps_ttm[tk]
        if per_share_ttm is not None:
            annual_buyback = _last_numeric(buybacks) or 0.0
            shareholder_ps[tk] = per_share_ttm + annual_buyback
        dividend_paid[tk] = _last_numeric(payload.get("dividend_paid_history"))
        net_income[tk] = _net_income_last(analysis)

    quantity_by_ticker = {r["ticker"]: r["quantity"] for r in rows}
    cost_basis_total = sum(r["cost_basis"] for r in rows if r.get("cost_basis"))
    ttm_income = sum(
        (dps_ttm[t] or 0.0) * q for t, q in quantity_by_ticker.items() if dps_ttm.get(t) is not None
    )
    metrics = portfolio_engine.dividend_metrics(
        dividends_total=income["total_confirmed"],
        cost_basis_total=cost_basis_total,
        ttm_income=ttm_income if ttm_income > 0 else None,
        dps_ttm_by_ticker=dps_ttm,
        quantity_by_ticker=quantity_by_ticker,
        market_value_by_ticker=market_value_by_ticker,
        dividend_paid_by_ticker=dividend_paid,
        net_income_by_ticker=net_income,
        shareholder_per_share_by_ticker=shareholder_ps,
    )

    # Croissance agrégée : moyenne des CAGR PONDÉRÉE par le poids de REVENU (fidèle
    # à « croissance de mon revenu »), pas par la capitalisation — un titre qui ne
    # verse presque rien ne doit pas peser dans la croissance du revenu.
    income_weight_list = [income_weights.get(r["ticker"], 0.0) for r in rows]
    cagr_aggregate = portfolio_engine.weighted_mean(
        [cagr_by_ticker.get(r["ticker"]) for r in rows], income_weight_list
    )

    stats = {
        "yield_pct": _dividend_cell("yield_pct", metrics["yield_pct"]),
        "yield_on_cost_pct": _dividend_cell("yield_on_cost_pct", metrics["yield_on_cost_pct"]),
        "payout_pct": _dividend_cell("payout_pct", metrics["payout_pct"]),
        "shareholder_yield_pct": _dividend_cell(
            "shareholder_yield_pct", metrics["shareholder_yield_pct"]
        ),
        "yield_coverage_pct": _dividend_cell("yield_coverage_pct", metrics["yield_coverage_pct"]),
        "payout_coverage_pct": _dividend_cell(
            "payout_coverage_pct", metrics["payout_coverage_pct"]
        ),
        "shareholder_coverage_pct": _dividend_cell(
            "shareholder_coverage_pct", metrics["shareholder_coverage_pct"]
        ),
        "ttm_income": _dividend_cell("ttm_income", metrics["ttm_income"]),
        "total_income": _dividend_cell("total_income", metrics["total_income"]),
        "cagr_pct": _dividend_cell("cagr_pct", cagr_aggregate),
        "dividend_contribution_pct": _dividend_cell("dividend_contribution_pct", contribution_pct),
        # Les deux taux annualisés qui composent la contribution (double TWR) :
        # exposés pour que l'écart soit vérifiable et réutilisable (MCP, front).
        "twr_with_dividends_pct": _dividend_cell("twr_with_dividends_pct", twr_with_pct),
        "twr_without_dividends_pct": _dividend_cell("twr_without_dividends_pct", twr_without_pct),
    }

    lines = []
    for r in rows:
        ticker = r["ticker"]
        capital_share = (
            None
            if total_market_value <= 0 or not r.get("market_value")
            else r["market_value"] / total_market_value * 100.0
        )
        income_share = income_weights.get(ticker)
        lines.append(
            portfolio_engine.dividend_line(
                ticker=ticker,
                quantity=r["quantity"],
                cost_basis=r["cost_basis"],
                market_value=r.get("market_value"),
                dps_ttm=dps_ttm.get(ticker),
                income_share_pct=None if income_share is None else income_share * 100.0,
                capital_share_pct=capital_share,
                cagr_pct=cagr_by_ticker.get(ticker),
                payout_pct=_dividend_payout_ratio(analyses.get(ticker)),
            )
        )
    _attach_names(lines)
    lines.sort(key=lambda line: (-(line["income_share_pct"] or 0.0), line["ticker"]))

    return {
        "income": income,
        "stat_groups": config.PORTFOLIO_DIVIDEND_GROUPS,
        "stats": stats,
        "concentration": portfolio_engine.income_concentration(
            {c["ticker"]: c["amount"] for c in income["by_company"]},
            config.PORTFOLIO_TOP_N,
        ),
        "lines": lines,
        "warnings": _dividend_warnings(rows, analyses, metrics),
    }


def _dividend_payout_ratio(analysis: StockAnalysis | None) -> float | None:
    """Payout sur bénéfices du dernier exercice, lu du payload de la fiche.

    SOURCE UNIQUE : `fundamentals.dividend.payout_history`,
    `earnings_payout` (`data/yahoo._payout_series`), dernier exercice connu.
    None sur un ETF ou une société sans bénéfice exploitable (jamais 0).
    """
    if analysis is None or analysis.fundamentals is None:
        return None
    payload = analysis.fundamentals.dividend or {}
    history = payload.get("payout_history") or {}
    return _last_numeric(history.get("earnings_payout"))


def _dividend_cell(key: str, value: float | None) -> dict:
    """Cellule de KPI dividende : polarité depuis `config.PORTFOLIO_DIVIDEND_POLARITY`."""
    spec = config.PORTFOLIO_DIVIDEND_POLARITY.get(key)
    return {
        "value": None if value is None else round(float(value), 2),
        "good": portfolio_engine.polarity_good(value, spec),
    }


def _dividend_warnings(
    rows: Sequence[dict], analyses: dict[str, StockAnalysis], metrics: dict
) -> list[str]:
    """Manques de la SOURCE, en clair — un badge par manque réel, aucun si tout est là.

    Le payout n'existe pas pour un ETF : sans ce signalement, un payout agrégé
    calculé sur 2 lignes sur 12 se lirait comme le payout du portefeuille.
    """
    out: list[str] = []
    missing_payout = 0
    buybacks_missing = 0
    for row in rows:
        analysis = analyses.get(row["ticker"])
        if _dividend_payout_ratio(analysis) is None:
            missing_payout += 1
        fundamentals = analysis.fundamentals if analysis is not None else None
        if fundamentals is not None and not (fundamentals.dividend or {}).get("buybacks_available"):
            buybacks_missing += 1
    # Les manques de données forment UN SEUL badge de couverture : empiler
    # « payout sur 2 lignes », « rendement couvert sur 96 % » et « rachats
    # absents » noierait l'information (au-delà de 2 badges, on n'en lit aucun).
    coverage = metrics.get("yield_coverage_pct")
    details: list[str] = []
    if missing_payout:
        details.append(f"payout absent sur {missing_payout} ligne(s)")
    if coverage is not None and coverage < 100:
        details.append(f"rendement couvert sur {round(coverage)} % de la valeur")
    if details:
        out.append("Couverture des données : " + " · ".join(details))
    if buybacks_missing:
        out.append(f"Rachats d'actions : non disponibles sur {buybacks_missing} ligne(s)")
    return out


def _empty_dividend_page(income: dict) -> dict:
    """Structure complète de la page Dividende quand le périmètre est vide."""
    return {
        "income": income,
        "stat_groups": config.PORTFOLIO_DIVIDEND_GROUPS,
        "stats": {},
        "concentration": portfolio_engine.income_concentration(
            {c["ticker"]: c["amount"] for c in income.get("by_company") or []},
            config.PORTFOLIO_TOP_N,
        ),
        "lines": [],
        "warnings": [],
    }
