"""Cœur pur du portefeuille : positions, TWR, top/flop.

100 % pur — aucune I/O, aucun réseau, aucun import de `data/` ni `services/`.
Les transactions sont la source de vérité : une position n'est jamais saisie, elle
est **dérivée**. Ce module ne connaît ni les prix de marché ni la valorisation
(jalons suivants) : il ne calcule que la quantité détenue, le prix de revient
moyen (PRU) et le résultat réalisé — à partir des seules lignes saisies.

Convention de coût (Total Return, mono-EUR) : un achat capitalise
`quantité × prix + frais` ; une vente sort de la base de coût au PRU courant et
matérialise un résultat réalisé `quantité × prix − frais − quantité × PRU`.

Long-only assumé : une vente ne peut porter que sur la quantité détenue (une
vente excédentaire est bornée à la position, jamais de quantité négative). Une
position entièrement soldée (quantité nulle) est **écartée** du résultat.

**TWR chaîné quotidien (#17.1).** La performance est calculée par chaînage de
sous-périodes délimitées par les **flux externes** : un achat est un apport, une
vente un retrait. Un **dividende est un gain interne** (il reste en trésorerie du
compte) : il augmente la valeur sans être un flux. C'est ce qui rend le TWR
**insensible au montant et au calendrier des apports** — sa propriété définissante.
"""

from __future__ import annotations

import datetime as _dt
import math
from bisect import bisect_left, bisect_right
from collections.abc import Sequence
from dataclasses import dataclass

from obole import config


@dataclass(frozen=True)
class Position:
    """Position recalculée d'un ticker (quantités et coût, hors valorisation)."""

    ticker: str
    quantity: float  # quantité détenue (0 si soldée)
    cost_basis: float  # coût d'acquisition de la quantité détenue (PRU × quantité)
    realized: float  # plus/moins-value réalisée cumulée (ventes)

    @property
    def pru(self) -> float | None:
        """Prix de revient moyen (None si la position est soldée)."""
        if self.quantity <= 0:
            return None
        return self.cost_basis / self.quantity


def positions_from_transactions(transactions: list[dict]) -> list[Position]:
    """Recalcule les positions (quantité, PRU, réalisé) depuis les transactions.

    Les transactions sont traitées par ordre chronologique (`trade_date`, puis
    `id` en départage) : l'ordre des ventes vis-à-vis des achats détermine le PRU
    appliqué. Les positions soldées sont **écartées** du résultat (quantité nulle)
    mais leur résultat réalisé est conservé sur la position retournée si le ticker
    a encore des lignes — une position entièrement soldée n'apparaît pas.

    Cas limites : aucune transaction -> liste vide ; une vente sans achat préalable
    ne rend pas le PRU négatif (base de coût bornée à zéro).
    """
    ordered = sorted(transactions, key=lambda t: (str(t.get("trade_date", "")), t.get("id", 0)))
    state: dict[str, dict[str, float]] = {}
    for tx in ordered:
        ticker = str(tx.get("ticker", "")).strip().upper()
        if not ticker:
            continue
        acc = state.setdefault(ticker, {"quantity": 0.0, "cost": 0.0, "realized": 0.0})
        side = str(tx.get("side", "")).strip().lower()
        quantity = float(tx.get("quantity", 0.0))
        price = float(tx.get("price", 0.0))
        fees = float(tx.get("fees", 0.0) or 0.0)
        if side == "buy":
            acc["quantity"] += quantity
            acc["cost"] += quantity * price + fees
        elif side == "sell":
            # Long-only : on ne peut vendre que ce que l'on détient.
            sold = min(quantity, acc["quantity"])
            pru = (acc["cost"] / acc["quantity"]) if acc["quantity"] > 0 else 0.0
            acc["realized"] += sold * price - fees - sold * pru
            acc["quantity"] -= sold
            acc["cost"] -= sold * pru
            if acc["quantity"] <= 0:
                acc["quantity"] = 0.0
                acc["cost"] = 0.0
    out: list[Position] = []
    for ticker, acc in state.items():
        if acc["quantity"] <= 0:
            continue  # position soldée : rien à montrer (le réalisé reste une info de flux)
        out.append(
            Position(
                ticker=ticker,
                quantity=acc["quantity"],
                cost_basis=acc["cost"],
                realized=acc["realized"],
            )
        )
    return out


# --- TWR chaîné quotidien (#17.1) -------------------------------------------


def _forward_fill(series: list[float | None]) -> list[float | None]:
    """Reporte la dernière valeur connue sur les trous (None)."""
    out: list[float | None] = []
    last: float | None = None
    for v in series:
        if v is not None:
            last = v
        out.append(last)
    return out


def daily_values(
    dates: list[str],
    prices_by_ticker: dict[str, list[float | None]],
    transactions: list[dict],
    dividends: list[dict],
) -> tuple[list[float], list[float]]:
    """Valeur quotidienne du portefeuille + flux externes, alignés sur `dates`.

    `dates` = calendrier croissant de dates ISO (séances de bourse). Les séries de
    prix (`prices_by_ticker`) sont alignées sur `dates` (None = séance absente,
    reportée par la dernière valeur connue). Renvoie `(values, flows)` :

    - `values[i]` = Σ(quantité × cours) + trésorerie. La trésorerie accumule les
      **dividendes** (gain interne, le dividende reste dans le compte) ;
    - `flows[i]` = flux **externe** net du jour : achat = apport (+), vente =
      retrait (−). Un dividende n'est **pas** un flux externe.

    Les événements antérieurs à `dates[0]` sont rattachés au premier jour.

    **Ticker non valorisable.** Un ticker sans série de prix ne peut pas
    contribuer à la valeur ; ses flux (achat/vente) sont donc **ignorés** eux
    aussi. Sinon un achat sur un ticker non coté serait compté comme un apport
    externe sans jamais entrer dans la valeur, ce qui ferait plonger la courbe
    TWR de tout le portefeuille (le badge « cours indisponibles » signale la
    ligne manquante). Cohérent avec l'exclusion des positions non valorisables.
    """
    n = len(dates)
    filled = {t: _forward_fill(s) for t, s in prices_by_ticker.items()}
    # Tickers réellement valorisables : seuls leurs flux comptent (cf. docstring).
    priceable = {t for t, s in filled.items() if any(v is not None for v in s)}

    events: dict[str, list[tuple[str, dict]]] = {}
    for tx in transactions:
        events.setdefault(str(tx.get("trade_date", "")), []).append(("tx", tx))
    for dv in dividends:
        events.setdefault(str(dv.get("pay_date", "")), []).append(("div", dv))
    event_dates = sorted(events)

    qty: dict[str, float] = {}
    cash = 0.0
    values = [0.0] * n
    flows = [0.0] * n
    ei = 0
    for i, day in enumerate(dates):
        # Applique tous les événements jusqu'au jour courant inclus.
        while ei < len(event_dates) and event_dates[ei] <= day:
            for kind, ev in events[event_dates[ei]]:
                ticker = str(ev.get("ticker", "")).strip().upper()
                if not ticker:
                    continue
                if kind == "div":
                    cash += float(ev.get("amount", 0.0) or 0.0)
                    continue
                if ticker not in priceable:
                    continue  # ticker non coté : ni position ni flux (cf. docstring)
                side = str(ev.get("side", "")).strip().lower()
                quantity = float(ev.get("quantity", 0.0) or 0.0)
                price = float(ev.get("price", 0.0) or 0.0)
                fees = float(ev.get("fees", 0.0) or 0.0)
                if side == "buy":
                    qty[ticker] = qty.get(ticker, 0.0) + quantity
                    flows[i] += quantity * price + fees  # apport externe
                elif side == "sell":
                    sold = min(quantity, qty.get(ticker, 0.0))
                    qty[ticker] = qty.get(ticker, 0.0) - sold
                    flows[i] -= sold * price - fees  # retrait externe
            ei += 1
        pos_val = 0.0
        for ticker, quantity in qty.items():
            if quantity == 0:
                continue
            series = filled.get(ticker)
            if not series:
                continue
            last_px = series[i]
            if last_px is None:
                continue  # cours indisponible : la ligne ne contribue pas ce jour
            pos_val += quantity * last_px
        values[i] = pos_val + cash
    return values, flows


def twr_series(values: list[float], flows: list[float]) -> list[float]:
    """Performance TWR cumulée (%) à partir des valeurs et flux quotidiens.

    Chaînage : `r_t = (V_t − F_t) / V_{t-1} − 1`, cumulé en produit. Le flux est
    supposé intervenir **en fin de séance** (un achat est exécuté au cours de
    clôture) : la nouvelle somme ne participe donc pas au rendement du jour. Les
    flux externes (`flows`) délimitent les sous-intervalles, ce qui rend le
    résultat **insensible au montant et au calendrier des apports** — un dividende
    (gain interne, hors `flows`) reste, lui, bien compté.

    La série commence à la première valeur strictement positive (0 % avant) ; si
    le portefeuille est soldé puis réapprovisionné, le chaînage repart sur la
    nouvelle base sans division par zéro.
    """
    n = len(values)
    out = [0.0] * n
    cum = 1.0
    prev: float | None = None
    for i in range(n):
        v = values[i]
        if prev is None:
            if v > 0:
                prev = v
            out[i] = 0.0
            continue
        if prev > 0:
            cum *= (v - flows[i]) / prev
        prev = v
        out[i] = (cum - 1.0) * 100.0
    return out


def benchmark_series(prices: list[float | None]) -> list[float | None]:
    """Performance cumulée (%) d'un achat-conservation (buy-and-hold).

    Base = premier cours connu (0 % à cette date) ; None tant qu'aucun cours n'est
    disponible. Sert de référence à la courbe du portefeuille.
    """
    out: list[float | None] = []
    base: float | None = None
    for p in prices:
        if p is None or p <= 0:
            out.append(None)
            continue
        if base is None:
            base = p
        out.append((p / base - 1.0) * 100.0)
    return out


def period_start_index(dates: list[str], period: str) -> int:
    """Index de début de la fenêtre pour un raccourci de période.

    `ytd` = depuis le 1er janvier de la dernière année ; `ttm` = 12 derniers mois
    (trailing twelve months, soit 1 an en arrière) ; `Na` = N dernières années ;
    `max` = 0. Un historique plus court que la fenêtre demande renvoie 0.

    Le jour est **clampé** : reculer l'année d'un 29 février vers une année non
    bissextile est invalide (`date.replace` lève) — on retombe alors sur le
    dernier jour du mois cible, jamais une exception.
    """
    if not dates:
        return 0
    end = len(dates) - 1
    if period == "max":
        return 0
    last = _dt.date.fromisoformat(dates[end])
    if period == "ytd":
        cutoff = _dt.date(last.year, 1, 1)
    else:
        years = 1 if period == "ttm" else int(period.rstrip("a"))
        target_year = last.year - years
        day = min(last.day, _days_in_month(target_year, last.month))
        cutoff = _dt.date(target_year, last.month, day)
    idx = bisect_right(dates, cutoff.isoformat())
    return min(idx, end)


def _days_in_month(year: int, month: int) -> int:
    """Nombre de jours du mois (année bissextile prise en compte)."""
    if month == 12:
        nxt = _dt.date(year + 1, 1, 1)
    else:
        nxt = _dt.date(year, month + 1, 1)
    return (nxt - _dt.timedelta(days=1)).day


def period_return(series: Sequence[float | None], start: int) -> float | None:
    """Rendement cumulé (%) d'une série de performance entre `start` et la fin.

    Base = dernière valeur connue à `start` (pourcentage cumulé du portefeuille ou
    du benchmark) ; None si la fenêtre est vide ou si la base est manquante.
    """
    if not series or start >= len(series):
        return None
    base = None
    for i in range(start, -1, -1):
        if series[i] is not None:
            base = series[i]
            break
    if base is None:
        return None
    end_val = None
    for i in range(len(series) - 1, start - 1, -1):
        if series[i] is not None:
            end_val = series[i]
            break
    if end_val is None:
        return None
    # Les séries de performance sont déjà en % cumulé : on dé-cumule la base.
    return ((1.0 + end_val / 100.0) / (1.0 + base / 100.0) - 1.0) * 100.0


def annualized_return(total_pct: float | None, days: int) -> float | None:
    """Annualise un rendement cumulé (%) sur `days` jours (CAGR). None si < 1 an."""
    if total_pct is None or days <= 0:
        return None
    years = days / 365.25
    if years < 1.0:
        return None
    growth = 1.0 + total_pct / 100.0
    if growth <= 0:
        return None
    return (growth ** (1.0 / years) - 1.0) * 100.0


def top_flop(
    positions: list[dict], perf_by_ticker: dict[str, float | None], n: int
) -> tuple[list[dict], list[dict]]:
    """Meilleures et moins bonnes positions par performance (%), sur `n` lignes.

    Les positions sans performance calculable sont **écartées** (badge explicite
    côté service, jamais un 0 trompeur). Le classement se fait par performance
    décroissante ; `top` et `flop` sont deux vues du même classement.
    """
    ranked: list[dict] = []
    for pos in positions:
        ticker = str(pos.get("ticker", "")).strip().upper()
        perf = perf_by_ticker.get(ticker)
        if perf is None:
            continue
        row = dict(pos)
        row["ticker"] = ticker
        row["perf"] = perf
        ranked.append(row)
    ranked.sort(key=lambda r: r["perf"], reverse=True)
    if n <= 0:
        return [], []
    return ranked[:n], list(reversed(ranked[-n:]))


# --- Risque : drawdown, corrélation (#17.3) ----------------------------------


def drawdown_series(values: Sequence[float | None]) -> list[float | None]:
    """Série de drawdown (%) : `(valeur / plus-haut-cumulé − 1) × 100`.

    Toujours ≤ 0 (0 = au plus haut). Le plus-haut est le maximum cumulé jusqu'à
    l'indice courant. `None` (valeur absente) reste `None` (trou préservé, pas de
    zéro trompeur). Un plus-haut ≤ 0 (valeur nulle) laisse le drawdown à 0 : la
    série ne devient négative qu'après une première valeur positive.
    """
    out: list[float | None] = []
    peak: float | None = None
    for v in values:
        if v is None:
            out.append(None)
            continue
        if peak is None or v > peak:
            peak = v
        out.append(0.0 if peak is None or peak <= 0 else (v / peak - 1.0) * 100.0)
    return out


def _days_between(start: str, end: str) -> int:
    """Nombre de jours civils entre deux dates ISO (0 si l'une est invalide)."""
    try:
        a = _dt.date.fromisoformat(start)
        b = _dt.date.fromisoformat(end)
    except (ValueError, TypeError):
        return 0
    return (b - a).days


def _longest_recovery(values: Sequence[float | None], dates: Sequence[str]) -> int:
    """Plus longue durée (jours) pour qu'un pic soit regagné après une baisse.

    Parcourt la série : à chaque nouveau plus-haut, si l'on était SOUS le pic
    précédent, la durée pic -> récupération est mesurée. Une baisse non récupérée
    en fin de série est comptée jusqu'à la dernière date. 0 si aucune baisse.
    """
    peak: float | None = None
    peak_i: int | None = None
    longest = 0
    below = False
    for i, v in enumerate(values):
        if v is None:
            continue
        if peak is None or v >= peak:
            if peak_i is not None and below:
                longest = max(longest, _days_between(dates[peak_i], dates[i]))
            peak = v
            peak_i = i
            below = False
        else:
            below = True
    if peak_i is not None and below and dates:
        longest = max(longest, _days_between(dates[peak_i], dates[-1]))
    return longest


def realized_volatility(
    values: Sequence[float | None], periods_per_year: int = 252
) -> float | None:
    """Volatilité réalisée annualisée (%) des rendements LOG quotidiens.

    None si moins de 2 rendements exploitables (les couples impliquant une valeur
    nulle/négative sont ignorés : pas de log d'un rapport non positif). Annualisée
    par `sqrt(periods_per_year)` = racine du temps (convention financière).
    """
    rets: list[float] = []
    for i in range(1, len(values)):
        a, b = values[i - 1], values[i]
        if a is None or b is None or a <= 0 or b <= 0:
            continue
        rets.append(math.log(b / a))
    if len(rets) < 2:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var * periods_per_year) * 100.0


def drawdown_metrics(values: Sequence[float | None], dates: Sequence[str] | None = None) -> dict:
    """Métriques de drawdown d'une série de valeurs (index de performance).

    - `max_drawdown_pct` : pire creux (≤ 0) ;
    - `current_drawdown_pct` : drawdown à la dernière valeur (≤ 0) ;
    - `longest_recovery_days` : plus longue durée pic -> récupération (jours) ;
    - `recovered` : True si la dernière valeur est au plus haut (drawdown nul) ;
    - `peak_at` / `trough_at` : dates ISO du pic (plus-haut) et du creux du pire DD.

    `dates` (aligné sur `values`) est optionnel : sans lui, seules les métriques
    qui ne dépendent pas du temps sont calculées (`longest_recovery_days` = 0).
    """
    dd = drawdown_series(values)
    valid = [d for d in dd if d is not None]
    max_dd = min(valid) if valid else 0.0
    current_dd = valid[-1] if valid else 0.0
    max_idx = dd.index(max_dd) if valid else None
    peak_i = None
    if max_idx is not None:
        # Pic = dernier plus-haut avant le creux (valeur maximale jusqu'au creux).
        best = None
        for i in range(max_idx + 1):
            v = values[i]
            if v is None:
                continue
            if best is None or v > best:
                best = v
                peak_i = i
    dates = dates or []
    trough_at = dates[max_idx] if (max_idx is not None and max_idx < len(dates)) else None
    peak_at = dates[peak_i] if (peak_i is not None and peak_i < len(dates)) else None
    return {
        "max_drawdown_pct": round(max_dd, 2),
        "current_drawdown_pct": round(current_dd, 2),
        "recovered": current_dd >= -1e-9,
        "longest_recovery_days": _longest_recovery(values, dates) if dates else 0,
        "peak_at": peak_at,
        "trough_at": trough_at,
    }


def monthly_returns(perf: Sequence[float | None], dates: Sequence[str]) -> list[dict]:
    """Rendements mensuels (%) dé-cumulés d'une série de performance cumulée.

    Regroupe par mois civil (`AAAA-MM`). Le rendement d'un mois =
    `((1 + fin/100) / (1 + base/100) − 1) × 100`, `base` = dernière valeur du mois
    précédent (première valeur du mois pour le tout premier). Les mois partiels
    sont inclus (premier et dernier mois de la fenêtre).
    """
    if not perf or len(perf) != len(dates):
        return []
    pts = [(dates[i][:7], perf[i]) for i in range(len(perf)) if perf[i] is not None]
    if not pts:
        return []
    out: list[dict] = []
    base: float | None = None
    i = 0
    while i < len(pts):
        key = pts[i][0]
        j = i
        while j < len(pts) and pts[j][0] == key:
            j += 1
        month = pts[i:j]
        first_v = month[0][1]
        last_v = month[-1][1]
        start_val = base if base is not None else first_v
        if start_val is not None and last_v is not None and start_val > -100:
            out.append(
                {
                    "year": int(key[:4]),
                    "month": int(key[5:7]),
                    "pct": round(((1 + last_v / 100) / (1 + start_val / 100) - 1) * 100, 2),
                }
            )
        base = last_v
        i = j
    return out


def monthly_table(perf: Sequence[float | None], dates: Sequence[str]) -> dict:
    """Tableau annuel des rendements mensuels, dérivé d'une série cumulée (%).

    Réutilise `monthly_returns` (chaînage TWR identique) puis chaîne les 12 mois
    d'une même année en un **total annuel**. Renvoie
    `{"years": [aaa, ...], "rows": [{year, months: {1..12: pct|None}, total}]}`,
    années croissantes, mois absents = `None` (jamais un 0 trompeur). Un mois peut
    manquer (première/dernière année de la fenêtre, trou de données).
    """
    months = monthly_returns(perf, dates)
    by_year: dict[int, dict[int, float]] = {}
    for m in months:
        by_year.setdefault(int(m["year"]), {})[int(m["month"])] = float(m["pct"])
    rows: list[dict] = []
    slots_range = range(1, config.PORTFOLIO_MONTHS + 1)
    for year in sorted(by_year):
        slots = {mo: by_year[year].get(mo) for mo in slots_range}
        growth = 1.0
        has = False
        for mo in slots_range:
            v = slots[mo]
            if v is None:
                continue
            growth *= 1.0 + v / 100.0
            has = True
        rows.append(
            {
                "year": year,
                "months": {str(mo): slots[mo] for mo in slots_range},
                "total": round((growth - 1.0) * 100.0, 2) if has else None,
            }
        )
    return {"years": [r["year"] for r in rows], "rows": rows}


def contributions(perf_by_ticker: dict[str, float | None], weights: dict[str, float]) -> dict:
    """Contribution (%) de chaque ligne à la performance totale du portefeuille.

    Contribution = poids × performance de la ligne (poids et perf en fractions,
    contribution renvoyée en %). Renvoie
    `{"by_ticker": {tk: pct|None}, "total": pct|None}` — une ligne sans perf ou
    sans poids vaut `None` ; le total somme les contributions connues, sans
    biaiser (les lignes non valorisables sont simplement absentes) et vaut `None`
    si aucune ligne n'est exploitable (jamais un 0 trompeur). Sert la répartition
    de la performance par entreprise de la section Performance.
    """
    by_ticker: dict[str, float | None] = {}
    total = 0.0
    any_val = False
    for ticker, weight in weights.items():
        perf = perf_by_ticker.get(ticker)
        if perf is None or weight is None:
            by_ticker[ticker] = None
            continue
        c = weight * perf  # weight déjà en fraction, perf en %
        by_ticker[ticker] = round(c, 2)
        total += c
        any_val = True
    return {"by_ticker": by_ticker, "total": round(total, 2) if any_val else None}


def periodic_returns(values: Sequence[float | None]) -> list[float]:
    """Rendements SIMPLES par période (`v_t / v_{t-1} − 1`), trous ignorés.

    Un couple n'est retenu que si les deux valeurs encadrantes sont strictement
    positives (pas de rendement sur une valeur nulle/négative). Sert de base aux
    ratios de Sharpe/Sortino.
    """
    out: list[float] = []
    for i in range(1, len(values)):
        a, b = values[i - 1], values[i]
        if a is None or b is None or a <= 0 or b <= 0:
            continue
        out.append(b / a - 1.0)
    return out


def sharpe_ratio(
    values: Sequence[float | None],
    risk_free_pct: float = 0.0,
    periods_per_year: int = 252,
) -> float | None:
    """Ratio de Sharpe annualisé : `(rendement − taux sans risque) / volatilité`.

    Rendement et volatilité sont annualisés (moyenne × N, écart-type × √N sur les
    rendements simples). `risk_free_pct` en %/an. `None` si moins de 2 rendements
    ou volatilité nulle (série plate) — jamais un infini.
    """
    rets = periodic_returns(values)
    if len(rets) < 2:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    vol = math.sqrt(var) * math.sqrt(periods_per_year)
    if vol == 0:
        return None
    ann_ret = mean * periods_per_year * 100.0
    return round((ann_ret - risk_free_pct) / (vol * 100.0), 4)


def sortino_ratio(
    values: Sequence[float | None],
    risk_free_pct: float = 0.0,
    periods_per_year: int = 252,
) -> float | None:
    """Ratio de Sortino annualisé : pénalise la seule volatilité À LA BAISSE.

    Numérateur = rendement annualisé − taux sans risque ; dénominateur = écart-type
    annualisé des seuls rendements NÉGATIFS (`√(moyenne des min(r,0)²) × √N`).
    `None` si moins de 2 rendements ou aucune baisse (dénominateur nul).
    """
    rets = periodic_returns(values)
    if len(rets) < 2:
        return None
    mean = sum(rets) / len(rets)
    downside = [r for r in rets if r < 0]
    if not downside:
        return None
    dd = math.sqrt(sum(r * r for r in downside) / len(downside)) * math.sqrt(periods_per_year)
    if dd == 0:
        return None
    ann_ret = mean * periods_per_year * 100.0
    return round((ann_ret - risk_free_pct) / (dd * 100.0), 4)


def weighted_mean(values: Sequence[float | None], weights: Sequence[float]) -> float | None:
    """Moyenne PONDÉRÉE (pondération par poids de marché), `None` ignorés.

    Un point absent est écarté du calcul ET du dénominateur : on ne le remplace
    pas par 0 (qui tirerait la moyenne) ni par une valeur tierce, et le poids
    total se recale donc sur les seuls points connus. Renvoie `None` si aucun
    point n'est exploitable ou si les poids connus somment à 0.
    """
    num = 0.0
    den = 0.0
    for v, w in zip(values, weights, strict=False):
        if v is None or w is None:
            continue
        num += float(v) * float(w)
        den += float(w)
    if den == 0:
        return None
    return num / den


def polarity_good(value: float | None, spec: tuple[str, float | None] | None) -> bool | None:
    """Polarité couleur d'une valeur scalaire, depuis une règle `(sens, seuil)`.

    `sens` : "ge" (≥ seuil favorable), "le" (≤ seuil favorable), "le_pos"
    (favorable si 0 < v ≤ seuil, neutre sinon — un multiple ≤ 0 n'est pas
    interprétable). Renvoie `None` (neutre) si la valeur ou la règle manque, si
    le seuil est `None` (métrique sans seuil : jamais de couleur) ou si le sens
    est inconnu — jamais une couleur par défaut.
    """
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


def weighted_share(
    values: Sequence[float | None], weights: Sequence[float], n: int
) -> float | None:
    """Part de poids (%) des `n` plus grosses valeurs, `None` ignorés.

    Sert le « poids du top 5 » de la synthèse (concentration). Renvoie `None` si
    aucun poids exploitable. Le tri est décroissant sur les valeurs présentes.
    """
    pairs = [
        (float(v), float(w))
        for v, w in zip(values, weights, strict=False)
        if v is not None and w is not None
    ]
    total = sum(w for _, w in pairs)
    if total <= 0:
        return None
    pairs.sort(key=lambda p: p[0], reverse=True)
    return sum(w for _, w in pairs[:n]) / total * 100.0


def line_stat_cell(key: str, value: float | None) -> dict:
    """Cellule de stat d'une ligne : `{"value", "good"}`, polarité depuis config.

    `key` est la clé de métrique de `config.PORTFOLIO_STAT_GROUPS` ; la couleur
    vient de `config.PORTFOLIO_STAT_POLARITY` (source unique). Une métrique sans
    règle (nombre, capitalisation…) reste neutre.
    """
    spec = config.PORTFOLIO_STAT_POLARITY.get(key)
    return {
        "value": None if value is None else round(float(value), 2),
        "good": polarity_good(value, spec),
    }


def aggregate_statistics(
    rows: Sequence[dict],
    weights: Sequence[float],
    groups: Sequence[dict],
) -> dict:
    """Statistiques agrégées pondérées d'un panier de lignes (#17.4).

    `rows` : une entrée par ligne détenue, `rows[i]` = {clé_metric: {"value",
    "good"}} (cellule produite par `line_stat_cell`, `None` possible). `weights` :
    poids de marché alignés sur `rows` (fraction). `groups` : taxonomie
    `config.PORTFOLIO_STAT_GROUPS` (ordre, libellés, unités).

    Pour chaque métrique : **moyenne pondérée** (points absents exclus du
    dénominateur, jamais un 0 trompeur) ; `good` = **majorité pondérée** des
    lignes favorables (`True` si la part de poids des lignes `good` ≥ 50 %),
    `None` si aucune ligne évaluable. Les métriques de catégorie « Général » qui
    ne sont pas une moyenne pondérée (`count`, `top5_weight`, `market_cap`) sont
    fournies par l'appelant et présentes dans `rows[0]` : on les recopie telles
    quelles plutôt que de les moyenner.
    """
    non_mean = {"count", "top5_weight", "market_cap"}
    out: dict[str, dict] = {}
    for group in groups:
        for metric in group["metrics"]:
            key = metric["key"]
            if key in non_mean:
                # Valeur directe (non moyennée), posée sur la première ligne.
                cell = rows[0].get(key) if rows else None
                out[key] = cell or {"value": None, "good": None}
                continue
            vals = [r.get(key, {}).get("value") if r.get(key) else None for r in rows]
            value = weighted_mean(vals, weights)
            good_num = 0.0
            good_den = 0.0
            for r, w in zip(rows, weights, strict=False):
                cell = r.get(key)
                if not cell or cell.get("good") is None:
                    continue
                good_den += float(w)
                if cell["good"]:
                    good_num += float(w)
            good = None if good_den == 0 else (good_num / good_den) >= 0.5
            out[key] = {"value": None if value is None else round(value, 2), "good": good}
    return out


def entry_exit_retrospective(
    dates: Sequence[str],
    transactions: list[dict],
    prices_by_ticker: dict[str, Sequence[float | None]],
    benchmark: Sequence[float | None],
) -> list[dict]:
    """Rétrospective par point d'entrée/sortie : a-t-on battu le benchmark ?

    Pour chaque transaction (achat ou vente), on prend la première séance >= sa
    date (`dates` croissantes) et on compare, depuis ce point, le rendement du
    titre et celui du benchmark sur la même fenêtre :

    - `return_pct` = (cours_fin / cours_entrée − 1) × 100 ;
    - `benchmark_pct` = (bench_fin / bench_entrée − 1) × 100 ;
    - `delta_pct` = `return_pct − benchmark_pct` (> 0 = le titre a battu le
      benchmark depuis ce point).

    Chaque entrée des deux séries est forward-fillée en amont ; une date hors
    historique ou un cours manquant laisse `None` (jamais d'erreur). Triées par
    date croissante puis `id`.
    """
    out: list[dict] = []
    for tx in sorted(transactions, key=lambda t: (str(t.get("trade_date", "")), t.get("id", 0))):
        ticker = str(tx.get("ticker", "")).strip().upper()
        series = prices_by_ticker.get(ticker)
        if not series:
            continue
        date = str(tx.get("trade_date", ""))
        idx = bisect_left(list(dates), date)
        if idx >= len(dates):
            idx = len(dates) - 1
        if idx < 0:
            idx = 0
        start_px = series[idx] if idx < len(series) else None
        end_px = next((v for v in reversed(series) if v is not None), None)
        b_start = benchmark[idx] if idx < len(benchmark) else None
        b_end = next((v for v in reversed(benchmark) if v is not None), None)
        ret = None
        bench_ret = None
        if start_px is not None and end_px is not None and start_px > 0:
            ret = (end_px / start_px - 1.0) * 100.0
        if b_start is not None and b_end is not None and b_start > 0:
            bench_ret = (b_end / b_start - 1.0) * 100.0
        delta = None if ret is None or bench_ret is None else ret - bench_ret
        out.append(
            {
                "id": tx.get("id"),
                "ticker": ticker,
                "side": str(tx.get("side", "")).strip().lower(),
                "date": date,
                "quantity": float(tx.get("quantity", 0.0) or 0.0),
                "price": float(tx.get("price", 0.0) or 0.0),
                "return_pct": None if ret is None else round(ret, 2),
                "benchmark_pct": None if bench_ret is None else round(bench_ret, 2),
                "delta_pct": None if delta is None else round(delta, 2),
            }
        )
    return out


def log_returns_by_ticker(
    dates: Sequence[str], prices_by_ticker: dict[str, Sequence[float | None]]
) -> dict[str, dict[str, float]]:
    """Rendements LOG quotidiens par titre, indexés par date ISO (alignés).

    Un rendement n'existe que si les deux cours encadrants sont strictement
    positifs (pas de log d'un rapport non positif). Sert la matrice de corrélation.
    """
    out: dict[str, dict[str, float]] = {}
    for ticker, series in prices_by_ticker.items():
        rets: dict[str, float] = {}
        for i in range(1, len(dates)):
            a, b = series[i - 1], series[i]
            if a is None or b is None or a <= 0 or b <= 0:
                continue
            rets[dates[i]] = math.log(b / a)
        out[ticker] = rets
    return out


def _pearson(ra: dict[str, float], rb: dict[str, float], min_obs: int) -> float | None:
    """Corrélation de Pearson sur les dates COMMUNES ; None si trop peu de points."""
    common = [d for d in ra if d in rb]
    if len(common) < min_obs:
        return None
    xs = [ra[d] for d in common]
    ys = [rb[d] for d in common]
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    return cov / math.sqrt(vx * vy)


def correlation_matrix(returns_by_ticker: dict[str, dict[str, float]], min_obs: int) -> dict:
    """Matrice de corrélation (Pearson) entre les rendements de chaque titre.

    Les titres dont le nombre d'observations propres est **inférieur** à `min_obs`
    sont **écartés** (listés dans `excluded` avec leur compte, badge explicite côté
    front — jamais un zéro trompeur). Sur les titres retenus, chaque paire est
    corrélée sur les dates communes ; une paire sous `min_obs` points communs vaut
    `None`. Diagonale = 1.0.

    Renvoie `{"tickers": [...], "matrix": [[...]], "excluded": [...]}` dans l'ordre
    ALPHABÉTIQUE (le tri par blocs est appliqué par `correlation_order`).
    """
    kept: list[str] = []
    excluded: list[dict] = []
    for ticker in sorted(returns_by_ticker):
        obs = len(returns_by_ticker[ticker])
        if obs < min_obs:
            excluded.append({"ticker": ticker, "obs": obs})
        else:
            kept.append(ticker)
    matrix: list[list[float | None]] = []
    for i, a in enumerate(kept):
        row: list[float | None] = []
        for j, b in enumerate(kept):
            if i == j:
                row.append(1.0)
                continue
            rho = _pearson(returns_by_ticker[a], returns_by_ticker[b], min_obs)
            row.append(None if rho is None else round(rho, 4))
        matrix.append(row)
    return {"tickers": kept, "matrix": matrix, "excluded": excluded}


def correlation_row(
    target: dict[str, float],
    others: dict[str, dict[str, float]],
    min_obs: int,
) -> dict[str, float | None]:
    """Corrélation de `target` contre chaque série de `others` (ordre gardé).

    Sert le « test de corrélation » (#17.3) : la ligne d'un ticker candidat face
    aux lignes détenues du périmètre. Une paire sous `min_obs` points communs (ou
    à variance nulle) vaut `None` — jamais un zéro trompeur. L'ordre des clés
    d'entrée est préservé (alignement sous les colonnes de la matrice).
    """
    out: dict[str, float | None] = {}
    for ticker, series in others.items():
        rho = _pearson(target, series, min_obs)
        out[ticker] = None if rho is None else round(rho, 4)
    return out


def mean_offdiagonal(matrix: Sequence[Sequence[float | None]]) -> float | None:
    """Moyenne des corrélations HORS diagonale (`None` ignorés).

    Renvoie `None` si aucune paire fiable n'existe. Sert la « corrélation
    moyenne » du périmètre (matrice) et l'impact d'un candidat (matrice étendue).
    """
    vals: list[float] = []
    for i, row in enumerate(matrix):
        for j, v in enumerate(row):
            if i != j and v is not None:
                vals.append(v)
    if not vals:
        return None
    return sum(vals) / len(vals)


def correlation_order(
    tickers: Sequence[str], matrix: Sequence[Sequence[float | None]]
) -> list[int]:
    """Ordre des lignes/colonnes révélant les blocs corrélés (greedy déterministe).

    On démarre sur le titre le plus corrélé en moyenne aux autres, puis on chaîne
    toujours le titre restant le plus corrélé au **dernier ajouté** (plus proche
    voisin). Les titres qui bougent ensemble se retrouvent contigus, ce qui rend
    les blocs lisibles — principe des heatmaps de corrélation (l'ordre
    alphabétique aveugle masque la structure). `None` (paire non fiable) est traité
    comme une corrélation nulle. Renvoie une liste d'INDICES.
    """
    n = len(tickers)
    if n <= 2:
        return list(range(n))
    plain = [
        [0.0 if (c is None or i == j) else abs(c) for j, c in enumerate(row)]
        for i, row in enumerate(matrix)
    ]
    avg = [sum(row) / max(1, n - 1) for row in plain]
    start = max(range(n), key=lambda i: (avg[i], -i))
    order = [start]
    remaining = set(range(n)) - {start}
    while remaining:
        last = order[-1]
        nxt = max(remaining, key=lambda i: (plain[last][i], -i))
        order.append(nxt)
        remaining.discard(nxt)
    return order


# --- Dividendes du portefeuille (#17.5) ---------------------------------------
# Agrégation d'un PANIER : c'est la juridiction de ce module (engine/dividends.py
# est mono-titre et sans notion de poids). Règle unique, identique partout : un
# point inconnu vaut None et sort du NUMÉRATEUR ET DU DÉNOMINATEUR — jamais un 0
# qui tirerait la moyenne, jamais une division par zéro.


def dividend_income(dividends: Sequence[dict]) -> dict:
    """Revenu par année, par mois et par payeur, confirmé vs proposé.

    Renvoie :
    - `years` : années civiles présentes, ordre croissant ;
    - `rows` : une entrée par année {year, months, by_ticker, total_confirmed,
      total_proposed, count} où `months` = {"1".."12": montant confirmé|None} et
      `by_ticker` = {ticker: {"months": {...}, "proposed": {...}}} pour les barres
      empilées par payeur (nécessaire pour distinguer le statut dans un même
      empilement) ;
    - `by_company` : [{ticker, amount, share_pct}] décroissant sur les montants
      CONFIRMÉS (une proposition n'est pas un revenu) ;
    - `total_confirmed`, `total_proposed`, `last_year`.

    Un mois sans versement vaut None, jamais 0 : c'est « rien reçu », pas « zéro
    euro de dividende » — la distinction commande le tracé (barre absente vs
    barre nulle).
    """

    def _blank() -> dict:
        return {str(m): None for m in range(1, 13)}

    by_year: dict[int, dict] = {}
    for d in dividends:
        iso = str(d.get("pay_date") or "")
        try:
            stamp = _dt.date.fromisoformat(iso[:10])
        except ValueError:
            continue
        ticker = str(d.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        status = str(d.get("status") or "confirmed").strip().lower()
        slot = by_year.setdefault(
            stamp.year,
            {"months": _blank(), "by_ticker": {}, "confirmed": 0.0, "proposed": 0.0, "count": 0},
        )
        amount = float(d.get("amount") or 0.0)
        month = str(stamp.month)
        if status == "confirmed":
            slot["months"][month] = (slot["months"][month] or 0.0) + amount
            slot["confirmed"] += amount
            bucket = "months"
        else:
            slot["proposed"] += amount
            bucket = "proposed"
        per_ticker = slot["by_ticker"].setdefault(
            ticker, {"months": _blank(), "proposed": _blank()}
        )
        per_ticker[bucket][month] = (per_ticker[bucket][month] or 0.0) + amount
        slot["count"] += 1

    def _round_map(mapping: dict) -> dict:
        return {k: (None if v is None else round(v, 2)) for k, v in mapping.items()}

    rows = []
    for year in sorted(by_year):
        slot = by_year[year]
        rows.append(
            {
                "year": year,
                "months": _round_map(slot["months"]),
                "by_ticker": {
                    t: {
                        "months": _round_map(v["months"]),
                        "proposed": _round_map(v["proposed"]),
                    }
                    for t, v in sorted(slot["by_ticker"].items())
                },
                "total_confirmed": round(slot["confirmed"], 2),
                "total_proposed": round(slot["proposed"], 2),
                "count": slot["count"],
            }
        )

    amounts: dict[str, float] = {}
    for row in rows:
        for ticker, payload in row["by_ticker"].items():
            total_for_ticker = sum(v for v in payload["months"].values() if v)
            if total_for_ticker:
                amounts[ticker] = amounts.get(ticker, 0.0) + total_for_ticker
    total = sum(amounts.values())
    by_company = [
        {
            "ticker": ticker,
            "amount": round(amount, 2),
            "share_pct": None if total <= 0 else round(amount / total * 100.0, 2),
        }
        for ticker, amount in sorted(amounts.items(), key=lambda p: (-p[1], p[0]))
    ]

    return {
        "years": [r["year"] for r in rows],
        "rows": rows,
        "by_company": by_company,
        "total_confirmed": round(sum(amounts.values()), 2),
        "total_proposed": round(sum(r["total_proposed"] for r in rows), 2),
        "last_year": rows[-1]["year"] if rows else None,
    }


def income_weights(amounts_by_ticker: dict[str, float]) -> dict[str, float]:
    """Poids de chaque payeur dans le revenu total (fractions sommant à 1).

    Dict vide si le total est nul ou négatif : on ne fabrique pas des poids à
    partir de rien (le front affiche alors « — »).
    """
    total = sum(float(v) for v in amounts_by_ticker.values() if v and v > 0)
    if total <= 0:
        return {}
    return {t: float(v) / total for t, v in amounts_by_ticker.items() if v and v > 0}


def income_concentration(amounts_by_ticker: dict[str, float], top_n: int) -> dict:
    """Concentration du revenu : nombre effectif de payeurs, top N, premier payeur.

    `n_eff = 1 / Σ w²` (indice de Hirschman-Herfindung inversé) : 12 payeurs à
    parts égales donnent 12 ; 12 payeurs dont un pèse 70 % donnent ~2,4. C'est la
    métrique qui dit la VRAIE diversification du revenu, là où un camembert ne
    quantifie rien.

    Renvoie {n_eff, top_n_pct, top_n, first_pct, first_ticker, payers}, tous
    None (sauf listes vides / 0) quand aucun revenu n'est exploitable.
    """
    weights = income_weights(amounts_by_ticker)
    if not weights:
        return {
            "n_eff": None,
            "top_n_pct": None,
            "top_n": top_n,
            "first_pct": None,
            "first_ticker": None,
            "payers": 0,
        }
    shares = sorted(weights.values(), reverse=True)
    n_eff = 1.0 / sum(w * w for w in shares) if shares else None
    return {
        "n_eff": None if n_eff is None else round(n_eff, 2),
        "top_n_pct": round(sum(shares[:top_n]) * 100.0, 2),
        "top_n": top_n,
        "first_pct": round(shares[0] * 100.0, 2),
        "first_ticker": max(weights, key=lambda t: weights[t]),
        "payers": len(shares),
    }


def dividend_metrics(
    dividends_total: float | None,
    cost_basis_total: float | None,
    ttm_income: float | None,
    dps_ttm_by_ticker: dict[str, float | None] | None = None,
    quantity_by_ticker: dict[str, float] | None = None,
    market_value_by_ticker: dict[str, float | None] | None = None,
    dividend_paid_by_ticker: dict[str, float | None] | None = None,
    net_income_by_ticker: dict[str, float | None] | None = None,
    shareholder_per_share_by_ticker: dict[str, float | None] | None = None,
) -> dict:
    """KPI de revenu du portefeuille, tous en AGRÉGAT (jamais une moyenne de ratios).

    - `yield_pct` = Σ(DPA TTM × quantité) / Σ valeur de marché : rendement
      COURANT, ce que le capital rapporte aujourd'hui. Le dénominateur est la
      valeur totale du périmètre (pas seulement les lignes à dividende) —
      `yield_coverage_pct` dit quelle part a un DPA connu, faute de quoi le
      rendement serait surestimé silencieusement.
    - `yield_on_cost_pct` = Σ(DPA TTM × quantité) / coût des positions ENCORE
      DÉTENUES : le MÊME numérateur que le rendement courant (donc comparable à
      la colonne « Div / coût » du tableau), rapporté au prix payé. Diviser les
      dividendes CUMULÉS par le coût ferait gonfler le chiffre avec l'âge de la
      position sans que le rendement change — ce n'est pas un yield on cost.
    - `payout_pct` = Σ dividendes versés / Σ bénéfices nets, lignes à bénéfice
      ≤ 0 ou inconnu EXCLUES des deux côtés ; `payout_coverage_pct` = part de la
      valeur de marché réellement couverte (sans elle, le payout mentirait par
      omission — un ETF n'a pas de bénéfice exploitable).
    - `shareholder_yield_pct` = Σ((DPA + rachat par action) × quantité) / Σ valeur
      de marché : même dénominateur que le rendement, numérateur élargi aux
      rachats. Les deux montants sont PAR ACTION (seule base où dividende et
      rachat sont comparables), donc aucune action en circulation requise.

    Toute valeur non calculable vaut None (jamais 0, jamais d'infini).
    """
    dps = dps_ttm_by_ticker or {}
    qty = quantity_by_ticker or {}
    mv_by = market_value_by_ticker or {}
    mv_total = sum(v for v in mv_by.values() if v and v > 0)

    def _coverage(covered: float) -> float | None:
        if mv_total <= 0:
            return None
        return round(covered / mv_total * 100.0, 2)

    metrics: dict = {
        "yield_pct": None,
        "yield_coverage_pct": None,
        "yield_on_cost_pct": None,
        "payout_pct": None,
        "payout_coverage_pct": None,
        "shareholder_yield_pct": None,
        "shareholder_coverage_pct": None,
        "ttm_income": None if ttm_income is None else round(float(ttm_income), 2),
        "total_income": None if dividends_total is None else round(float(dividends_total), 2),
    }

    # --- Rendement courant (agrégat) ------------------------------------------
    if dps and qty and mv_total > 0:
        num = 0.0
        covered_mv = 0.0
        for ticker, per_share in dps.items():
            if per_share is None:
                continue
            q = qty.get(ticker)
            if not q or q <= 0:
                continue
            num += float(per_share) * float(q)
            line_mv = mv_by.get(ticker)
            if line_mv and line_mv > 0:
                covered_mv += float(line_mv)
        if num > 0:
            metrics["yield_pct"] = round(num / mv_total * 100.0, 2)
            metrics["yield_coverage_pct"] = _coverage(covered_mv)

    # --- Yield on cost (même numérateur TTM que le rendement courant) ---------
    # Numérateur = revenu TTM (DPA × quantité), dénominateur = coût des positions
    # ouvertes : c'est la même mesure que la colonne « Div / coût » du tableau,
    # au niveau du panier. Le revenu CUMULÉ serait une autre information (rendement
    # historique sur capital engagé), qui gonfle mécaniquement avec l'ancienneté.
    if ttm_income is not None and cost_basis_total and cost_basis_total > 0:
        metrics["yield_on_cost_pct"] = round(float(ttm_income) / float(cost_basis_total) * 100.0, 2)

    # --- Payout agrégé (dividendes versés / bénéfice net) ---------------------
    paid = dividend_paid_by_ticker or {}
    earnings = net_income_by_ticker or {}
    num = 0.0
    den = 0.0
    covered_mv = 0.0
    for ticker, amount in paid.items():
        income = earnings.get(ticker)
        if amount is None or income is None or income <= 0:
            continue
        line_mv = mv_by.get(ticker)
        if not line_mv or line_mv <= 0:
            continue
        num += float(amount)
        den += float(income)
        covered_mv += float(line_mv)
    if den > 0:
        metrics["payout_pct"] = round(num / den * 100.0, 2)
        metrics["payout_coverage_pct"] = _coverage(covered_mv)

    # --- Shareholder yield (dividendes + rachats, par action) -----------------
    per_share_total = shareholder_per_share_by_ticker or {}
    sh_num = 0.0
    sh_covered_mv = 0.0
    for ticker, per_share in per_share_total.items():
        if per_share is None:
            continue
        q = qty.get(ticker)
        line_mv = mv_by.get(ticker)
        if not q or q <= 0 or not line_mv or line_mv <= 0:
            continue
        sh_num += float(per_share) * float(q)
        sh_covered_mv += float(line_mv)
    if sh_num > 0 and mv_total > 0:
        metrics["shareholder_yield_pct"] = round(sh_num / mv_total * 100.0, 2)
        metrics["shareholder_coverage_pct"] = _coverage(sh_covered_mv)
    return metrics


def dividend_line(
    ticker: str,
    quantity: float,
    cost_basis: float,
    market_value: float | None,
    dps_ttm: float | None,
    income_share_pct: float | None,
    capital_share_pct: float | None,
    cagr_pct: float | None = None,
    payout_pct: float | None = None,
) -> dict:
    """Une ligne du tableau Dividende (par titre détenu).

    `div_yield_pct` = DPA TTM / cours ; `div_to_cost_pct` = DPA TTM / PRU (le
    rendement sur le prix réellement payé, seule colonne non redondante avec la
    fiche entreprise) ; `gap_pp` = part du revenu − part du capital, en points :
    un titre qui pèse plus en revenu qu'en capital travaille pour le revenu.

    Chaque valeur manquante devient None avec un drapeau dans `flags` — le front
    affiche « — », jamais 0.
    """
    flags: list[str] = []
    price = None
    if market_value is not None and quantity and quantity > 0:
        price = float(market_value) / float(quantity)
    div_yield = None
    if dps_ttm is not None and price and price > 0:
        div_yield = round(float(dps_ttm) / price * 100.0, 2)
    div_to_cost = None
    if dps_ttm is not None and cost_basis and cost_basis > 0 and quantity and quantity > 0:
        pru = float(cost_basis) / float(quantity)
        if pru > 0:
            div_to_cost = round(float(dps_ttm) / pru * 100.0, 2)
    gap = None
    if income_share_pct is not None and capital_share_pct is not None:
        gap = round(float(income_share_pct) - float(capital_share_pct), 2)
    if dps_ttm is None:
        flags.append("dps_absent")
    if market_value is None:
        flags.append("price_absent")
    if not cost_basis:
        flags.append("cost_absent")
    if payout_pct is None:
        flags.append("payout_absent")
    return {
        "ticker": ticker,
        "quantity": round(float(quantity), 4),
        "cost_basis": round(float(cost_basis), 2),
        "market_value": None if market_value is None else round(float(market_value), 2),
        "dps_ttm": None if dps_ttm is None else round(float(dps_ttm), 4),
        "div_yield_pct": div_yield,
        "div_to_cost_pct": div_to_cost,
        "income_share_pct": None if income_share_pct is None else round(float(income_share_pct), 2),
        "capital_share_pct": None
        if capital_share_pct is None
        else round(float(capital_share_pct), 2),
        "gap_pp": gap,
        "cagr_pct": None if cagr_pct is None else round(float(cagr_pct), 2),
        "payout_pct": None if payout_pct is None else round(float(payout_pct), 2),
        "flags": flags,
    }
