"""Calculs purs autour du dividende et du retour à l'actionnaire.

Fonctions **pures** (zéro I/O, numpy/pandas only) : elles reçoivent des séries
déjà extraites par `data/` (dates de versement, montants, cours, rachats) et
produisent les indicateurs de la section « Dividende ». Aucun seuil ni nombre
magique : les fenêtres viennent de `config.py`.

Invariants :
- une valeur non calculable vaut `None` (jamais 0, jamais d'infini) ;
- un dénominateur nul/négatif rend le ratio absent ;
- le yield continu est une série dérivée du cours (comme les moyennes mobiles) :
  calculée en pleine résolution ici, décimée ailleurs avec le même pas que le
  cours, donc alignée 1:1 sur la série de prix.
"""

from __future__ import annotations

import pandas as pd

from obole import config


def frequency(events: dict[str, float]) -> str | None:
    """Fréquence déduite du nombre de versements des ~12 derniers mois.

    yfinance n'expose aucune fréquence : on la lit sur le rythme réel des
    versements (annualisation assumée). None si aucun versement.
    """
    if not events:
        return None
    stamps = []
    for iso in events:
        try:
            stamps.append(pd.Timestamp(iso))
        except (ValueError, TypeError):
            continue
    if not stamps:
        return None
    latest = max(stamps)
    cutoff = latest - pd.Timedelta(days=config.DIVIDEND_FREQUENCY_WINDOW_DAYS)
    count = sum(1 for s in stamps if s >= cutoff)
    for min_count, label in config.DIVIDEND_FREQUENCY_LABELS:
        if count >= min_count:
            return label
    return None


def increase_years(by_year: dict[int, float]) -> float | None:
    """Années consécutives d'AUGMENTATION STRICTE du dividende (les plus récentes).

    « Augmentation » = hausse stricte (`>`). Une année de stabilité interrompt la
    série — c'est ce qui la distingue de `no_cut_years` (qui compte la stabilité).
    """
    if not by_year:
        return None
    years = sorted(by_year, reverse=True)
    count = 0
    for newer, older in zip(years, years[1:], strict=False):
        if by_year[newer] > by_year[older]:
            count += 1
        else:
            break
    return float(count)


def no_cut_years(by_year: dict[int, float]) -> float | None:
    """Années consécutives SANS BAISSE du dividende (les plus récentes).

    « Sans baisse » = hausse OU stabilité (`>=`) : une année plate compte, une
    baisse interrompt la série. Distinct de `increase_years` (hausse stricte).
    """
    if not by_year:
        return None
    years = sorted(by_year, reverse=True)
    count = 0
    for newer, older in zip(years, years[1:], strict=False):
        if by_year[newer] >= by_year[older]:
            count += 1
        else:
            break
    return float(count)


def cagr(by_year: dict[int, float], years: int) -> float | None:
    """Taux de croissance annuel moyen du dividende sur `years` ans, en %.

    None si l'historique est trop court ou si un point terminal est nul/négatif
    (un CAGR n'a pas de sens sur une base ≤ 0).
    """
    ordered = sorted(by_year, reverse=True)
    if len(ordered) <= years:
        return None
    recent = by_year[ordered[0]]
    past = by_year[ordered[years]]
    if past <= 0 or recent <= 0:
        return None
    return ((recent / past) ** (1 / years) - 1) * 100


def growth_series(by_year: dict[int, float]) -> dict[int, float | None]:
    """Croissance annuelle (YoY) du dividende par action, en %, par exercice.

    None quand l'année précédente manque ou est nulle (base non interprétable).
    """
    out: dict[int, float | None] = {}
    for year in sorted(by_year):
        prev = by_year.get(year - 1)
        cur = by_year[year]
        if prev is None or prev == 0 or cur is None:
            out[year] = None
        else:
            out[year] = (cur / prev - 1) * 100
    return out


def ttm_per_share(events: dict[str, float], today: str | None = None) -> float | None:
    """Somme des versements des 365 derniers jours, par action.

    `per_share` (l'historique annuel) est groupé par année CIVILE : sur l'année en
    cours il est incomplet, et sur l'année précédente il inclut des versements qui
    sortent de la fenêtre glissante. Le rendement courant d'un portefeuille se lit
    donc sur les ÉVÉNEMENTS bruts, pas sur le total annuel.

    `today` = date ISO de référence (None -> aujourd'hui). Renvoie None quand aucun
    versement n'entre dans la fenêtre (jamais 0 : un dividende nul n'est pas
    « pas de dividende »).
    """
    if not events:
        return None
    window_end = pd.Timestamp(today) if today else pd.Timestamp.today().normalize()
    cutoff = window_end - pd.Timedelta(days=365)
    total = 0.0
    seen = False
    for iso, amount in events.items():
        try:
            stamp = pd.Timestamp(iso)
        except (ValueError, TypeError):
            continue
        if getattr(stamp, "tz", None) is not None:
            stamp = stamp.tz_localize(None)
        if cutoff <= stamp <= window_end:
            total += float(amount)
            seen = True
    return total if seen else None


def buybacks_per_share(
    buyback_history: dict[int, float] | None,
    shares_by_year: dict[int, float] | None,
) -> dict[int, float]:
    """Rachats d'actions ramenés PAR ACTION, par exercice.

    `buyback_history` = montants TOTAUX (cash-flow, ex. 230 800 000 €) ; on les
    divise par le nombre d'actions en circulation de l'exercice pour obtenir un
    montant par action, seul comparable au dividende par action (les deux entrent
    dans le rendement actionnaire, exprimé en % du cours).

    Le nombre d'actions est un instantané de fin d'exercice : si l'exercice exact
    manque, on retombe sur l'exercice connu le plus PROCHE (puis, à défaut, le
    dernier connu). Actions absentes ou nulles -> exercice ignoré (jamais de
    division par zéro ni de valeur aberrante).

    Renvoie {année: rachat_par_action}. Dict vide si rien n'est exploitable.
    """
    if not buyback_history:
        return {}
    shares = {int(y): float(v) for y, v in (shares_by_year or {}).items() if v}
    if not shares:
        return {}
    known = sorted(shares)
    out: dict[int, float] = {}
    for year, amount in buyback_history.items():
        year = int(year)
        if amount is None:
            continue
        # Exercice le plus proche dont le nombre d'actions est connu.
        closest = min(known, key=lambda y: (abs(y - year), -y))
        n_shares = shares[closest]
        if n_shares <= 0:
            continue
        out[year] = float(amount) / n_shares
    return out


def summary(events: dict[str, float], per_share: dict[int, float]) -> dict:
    """Statistiques de la section Dividende, calculées UNE fois côté serveur.

    SOURCE UNIQUE des indicateurs non dépendants de la fenêtre affichée
    (régularité, CAGR, fréquence, croissance annuelle, performance cumulée).
    Le front les affiche telles quelles ; seules les stats de FENÊTRE (High /
    Médiane / Low du rendement continu) restent recalculées côté client, comme
    `computeLive` pour les indicateurs de prix.

    L'année civile en cours est écartée des stats de régularité ET de croissance :
    son total est incomplet (versements restants non encore payés) et se lirait à
    tort comme une baisse (barre de croissance YoY négative en plein milieu d'année).
    """
    current_year = pd.Timestamp.today().year
    complete = {y: v for y, v in per_share.items() if y < current_year}
    ordered = sorted(complete)
    perf_pct = None
    if len(ordered) >= 2 and complete[ordered[0]] > 0 and complete[ordered[-1]] > 0:
        perf_pct = (complete[ordered[-1]] / complete[ordered[0]] - 1) * 100
    return {
        "increase_years": increase_years(complete),
        "no_cut_years": no_cut_years(complete),
        "cagr": {h: cagr(complete, h) for h in config.DIVIDEND_CAGR_HORIZONS},
        "frequency": frequency(events),
        "perf_pct": perf_pct,
        # Croissance sur les exercices COMPLETS uniquement (même exclusion que la
        # régularité) : une année partielle produirait une fausse chute.
        "growth": growth_series(complete),
    }


def rolling_yield_series(
    dates: pd.DatetimeIndex | pd.Series,
    prices: pd.Series,
    events: dict[str, float],
    extra_by_year: dict[int, float] | None = None,
    window_days: int = 365,
) -> pd.Series:
    """Série de rendement continu (%) alignée sur `dates`.

    Rendement(t) = somme des versements des `window_days` derniers jours / cours(t).
    `extra_by_year` ajoute une composante annuelle (rachats d'actions) au numérateur,
    en escalier : la valeur de l'exercice en cours s'applique jusqu'à la suivante.

    Renvoie une série indexée comme `prices` (mêmes dates), valeurs en %, None là
    où le cours est nul/négatif. Aucune donnée de versement -> série vide.
    """
    if prices is None or len(prices) == 0:
        return pd.Series(dtype=float)
    # Prix et dates d'événements peuvent porter des fuseaux différents (le cours
    # est tz-aware, les dates ISO parsées sont naïves) : on normalise tout en
    # naïf pour comparer des Timestamp homogènes.
    index = prices.index
    if getattr(index, "tz", None) is not None:
        index = index.tz_localize(None)
    stamps: list[pd.Timestamp] = []
    amounts: list[float] = []
    for iso, amount in events.items():
        try:
            stamps.append(
                pd.Timestamp(iso).tz_localize(None)
                if pd.Timestamp(iso).tz is not None
                else pd.Timestamp(iso)
            )
        except (ValueError, TypeError):
            continue
        amounts.append(float(amount))
    if not stamps and not extra_by_year:
        return pd.Series(index=prices.index, dtype=float)

    order = sorted(range(len(stamps)), key=lambda i: stamps[i])
    stamps = [stamps[i] for i in order]
    amounts = [amounts[i] for i in order]

    extra_vals = sorted((extra_by_year or {}).items())

    def extra_asof(ts: pd.Timestamp) -> float:
        """Composante annuelle (rachats) en escalier : dernier exercice ≤ ts."""
        val = 0.0
        for year, amount in extra_vals:
            if ts.year >= year:
                val = float(amount)
        return val

    out: list[float | None] = []
    for ts, price in zip(index, prices.to_numpy(), strict=False):
        if price is None or pd.isna(price) or price <= 0:
            out.append(None)
            continue
        cutoff = ts - pd.Timedelta(days=window_days)
        total = sum(
            amount for stamp, amount in zip(stamps, amounts, strict=False) if cutoff <= stamp <= ts
        )
        total += extra_asof(ts)
        out.append(total / float(price) * 100)
    return pd.Series(out, index=prices.index, dtype=float)
