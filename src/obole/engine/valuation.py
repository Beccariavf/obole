"""Reconstruction des multiples de valorisation historiques (PER, P/FCF, …).

Fonction PURE (zéro I/O) : c'est la seule logique qui croise PRIX et COMPTES.
Pour chaque exercice clos, on prend le cours à la date de clôture (asof) et on le
rapproche du bénéfice / cash-flow / capitaux de cet exercice. Tout poste manquant
ou dénominateur nul -> ratio absent (jamais d'inf, jamais de crash).

Choix assumé : le prix de clôture sert pour TOUS les exercices, y compris le plus
récent (série homogène, comparable d'année en année — c'est une lecture de tendance,
pas un point spot). Le dernier multiple peut donc différer du PER « live » de Yahoo,
qui rapporte le cours du jour : c'est un décalage temporel normal, pas une erreur.

`analysis.py` est le seul appelant : c'est lui qui détient à la fois la série de
prix (data/) et le tableau de comptes (data/), et les passe ici pour l'assemblage.
"""

from __future__ import annotations

import pandas as pd


def _price_asof(price_raw: pd.Series, when: pd.Timestamp) -> float | None:
    """Dernier cours connu à la date de clôture `when` (tz-naïf). None si avant l'IPO."""
    idx = price_raw.index
    if getattr(idx, "tz", None) is not None:
        price_raw = price_raw.copy()
        price_raw.index = idx.tz_localize(None)
    prior = price_raw[price_raw.index <= when]
    if prior.empty:
        return None
    return float(prior.iloc[-1])


def _at(s: pd.Series | None, ts: pd.Timestamp) -> float | None:
    """Valeur d'une série brute à la date de clôture `ts`, ou None si absente/NaN."""
    if s is None or ts not in s.index:
        return None
    val = s[ts]
    return None if pd.isna(val) else float(val)


def _safe_ratio(num: float | None, den: float | None) -> float | None:
    """num/den, ou None si l'un manque ou si le dénominateur est nul/négatif.

    Un multiple (PER, P/FCF…) n'a pas de sens sur un bénéfice nul ou négatif :
    on renvoie None plutôt qu'un nombre trompeur ou un infini.
    """
    if num is None or den is None or den <= 0:
        return None
    return num / den


def build(
    table: pd.DataFrame,
    raw_rows: dict[str, pd.Series],
    price_raw: pd.Series,
) -> pd.DataFrame:
    """Table de valorisation historique (lignes = multiples, colonnes = années).

    `table` : tableau de comptes normalisé (déjà construit, colonnes = année int).
    `raw_rows` : postes bruts nécessaires non normalisés en %, indexés par
        Timestamp de clôture — 'shares', 'net_income', 'fcf', 'ocf', 'ebitda',
        'equity', 'net_debt' (chacun optionnel ; absent -> ratios dépendants None).
    `price_raw` : cours brut (Close), pour le prix à chaque date de clôture.

    Renvoie un DataFrame vide si rien n'est calculable.
    """
    shares = raw_rows.get("shares")
    if shares is None or price_raw is None or price_raw.empty:
        return pd.DataFrame()

    net_income = raw_rows.get("net_income")
    fcf = raw_rows.get("fcf")
    revenue = raw_rows.get("revenue")
    ebitda = raw_rows.get("ebitda")
    equity = raw_rows.get("equity")
    net_debt = raw_rows.get("net_debt")

    out: dict[str, dict] = {}

    for ts in shares.dropna().index:
        n = float(shares[ts])
        if n <= 0:
            continue
        price = _price_asof(price_raw, ts)
        if price is None:
            continue
        market_cap = price * n
        year = ts.year

        per = _safe_ratio(market_cap, _at(net_income, ts))
        p_fcf = _safe_ratio(market_cap, _at(fcf, ts))
        p_s = _safe_ratio(market_cap, _at(revenue, ts))
        p_b = _safe_ratio(market_cap, _at(equity, ts))
        fcf_v = _at(fcf, ts)
        fcf_yield = (fcf_v / market_cap * 100) if (fcf_v is not None and fcf_v > 0) else None
        nd = _at(net_debt, ts)
        ev = market_cap + nd if nd is not None else None
        ev_ebitda = _safe_ratio(ev, _at(ebitda, ts))

        col = {
            "PER": per,
            "P/FCF": p_fcf,
            "P/CA": p_s,
            "Price / Book": p_b,
            "EV / EBITDA": ev_ebitda,
            "FCF yield": fcf_yield,
        }
        for metric, value in col.items():
            out.setdefault(metric, {})[year] = value

    if not out:
        return pd.DataFrame()
    df = pd.DataFrame(out).T  # lignes = multiples, colonnes = années
    # Colonnes triées du plus récent au plus ancien, comme le tableau de comptes.
    df = df[sorted(df.columns, reverse=True)]
    # Une ligne entièrement vide (multiple jamais calculable) est retirée.
    return df.dropna(how="all")
