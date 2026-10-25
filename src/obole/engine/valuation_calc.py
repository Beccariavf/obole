"""Calculatrice de prix juste — logique **pure** (zéro I/O).

Modèle de rendement estimé, reconstitué et validé par rétro-ingénierie de la
matrice Baggr (fit au 0,01 pt sur 45 cellules) :

    R(g, m) = (1 + g) × (m / m0)^(1/H) − 1 + D

où `g` = croissance annuelle, `m` = multiple de sortie, `m0` = multiple COURANT
(cours / métrique par action), `H` = horizon (`config.VALUATION_HORIZON_YEARS`)
et `D` = rendement du dividende (0 quand les dividendes sont exclus).

Équivalent à `(Valeur projetée / Cours)^(1/H) − 1 + D`, avec
`Valeur projetée = Métrique₀ × (1 + g)^H × m`.

Le front porte un **miroir** de ces fonctions (`web/valorisation.js`) pour le
recalcul live ; un test de parité verrouille l'égalité des deux (même invariant
que la régression, calculée serveur ET client). Toute modification doit toucher
les deux.

Invariants : une valeur non calculable vaut `None` (jamais 0, jamais d'infini) ;
un dénominateur nul/négatif rend le résultat absent.
"""

from __future__ import annotations

import pandas as pd


def fair_price(
    metric_value: float | None,
    multiple: float | None,
    net_debt_per_share: float | None = None,
) -> float | None:
    """Valeur médiane = Métrique × Multiple médian historique.

    ⚠️ Ne pas confondre avec le « prix juste » de la calculatrice (KPI de tête),
    qui est le PRIX D'ENTRÉE atteignant la cible (`target_entry_price`). Cette
    fonction rend la valeur intrinsèque historique (métrique × multiple médian),
    affichée en info secondaire ; l'identifiant `fair_price` est conservé pour la
    parité avec la fixture, mais son sens ici est « valeur médiane ».

    `net_debt_per_share` : bridge EV -> capitaux propres, utilisé UNIQUEMENT pour
    un multiple d'entreprise (EV/EBITDA) — on retranche la dette nette par action
    de la valeur d'entreprise pour obtenir la valeur par action. `None` (cas
    standard) = pas de bridge.
    """
    if metric_value is None or multiple is None:
        return None
    if metric_value <= 0 or multiple <= 0:
        return None
    value = metric_value * multiple
    if net_debt_per_share is not None:
        value -= net_debt_per_share
    return value


def safety_margin(fair: float | None, price: float | None) -> float | None:
    """Marge de sécurité = (Prix juste − Cours) / Prix juste, en %.

    Négatif = le cours dépasse le prix juste (pas de marge).
    """
    if fair is None or price is None or fair == 0:
        return None
    return (fair - price) / fair * 100


def projected_value(
    metric_value: float | None,
    growth_pct: float,
    multiple: float | None,
    horizon: int,
    net_debt_per_share: float | None = None,
) -> float | None:
    """Valeur projetée par action = Métrique₀ × (1 + g)^H × multiple − dette nette.

    `net_debt_per_share` : bridge EV -> capitaux propres pour un multiple
    d'entreprise (EV/EBITDA). `None` = pas de bridge (multiple de capitalisation).
    """
    if metric_value is None or multiple is None:
        return None
    if metric_value <= 0 or multiple <= 0:
        return None
    value = metric_value * (1 + growth_pct / 100) ** horizon * multiple
    if net_debt_per_share is not None:
        value -= net_debt_per_share
    return value


def estimated_return(
    metric_value: float | None,
    price: float | None,
    growth_pct: float,
    multiple: float | None,
    horizon: int,
    dividend_yield_pct: float = 0.0,
    net_debt_per_share: float | None = None,
) -> float | None:
    """Rendement annuel estimé, en %.

    `(Valeur projetée / Cours)^(1/H) − 1 + rendement_dividende`. Le dividende est
    ajouté linéairement (comportement observé sur la matrice Baggr) ; il vaut 0
    quand la case « Inclure les dividendes » est décochée.
    """
    projected = projected_value(metric_value, growth_pct, multiple, horizon, net_debt_per_share)
    if projected is None or price is None or price <= 0 or projected <= 0:
        return None
    if horizon <= 0:
        return None
    growth = (projected / price) ** (1 / horizon) - 1
    return growth * 100 + dividend_yield_pct


def estimated_return_from_fair(
    fair_price: float | None,
    price: float | None,
    target_pct: float,
    horizon: int,
    dividend_yield_pct: float = 0.0,
) -> float | None:
    """Rendement annuel estimé à partir du **prix juste enregistré**, en %.

    Inverse de `target_entry_price` : le prix juste est le prix d'entrée qui
    atteint la cible ; la valeur projetée qu'il encode vaut donc
    `fair × (1 + (cible − dividende)/100)^H`. Au cours actuel, le rendement de
    cette valorisation (appréciation + dividende) est
    `(projeté / cours)^(1/H) − 1 + dividende`.

    Utilisé par la watchlist (#26) pour que le Pot. 5A d'une valeur valorisée
    vienne de la valorisation enregistrée, pas de la droite de régression.
    """
    if fair_price is None or fair_price <= 0 or price is None or price <= 0 or horizon <= 0:
        return None
    net_target = (target_pct - dividend_yield_pct) / 100
    if net_target <= -1:
        return None
    projected = fair_price * (1 + net_target) ** horizon
    if projected <= 0:
        return None
    return ((projected / price) ** (1 / horizon) - 1) * 100 + dividend_yield_pct


def target_entry_price(
    metric_value: float | None,
    growth_pct: float,
    multiple: float | None,
    horizon: int,
    target_pct: float,
    dividend_yield_pct: float = 0.0,
    net_debt_per_share: float | None = None,
) -> float | None:
    """Prix d'entrée qui fait EXACTEMENT atteindre le rendement cible, en %.

    Inverse de `estimated_return` : c'est le prix à payer aujourd'hui pour que
    `(Valeur projetée / Prix)^(1/H) − 1 + dividende` égale la cible, soit
    `Valeur projetée / (1 + (cible − dividende)/100)^H`. C'est le « prix juste »
    de la calculatrice : il dérive des hypothèses saisies (croissance, multiple
    de sortie, horizon, dividende), contrairement à la valeur médiane historique.

    Renvoie `None` si non calculable : métrique/multiple absent ou ≤ 0, horizon
    ≤ 0, valeur projetée ≤ 0, ou cible nette (cible − dividende) ≤ −100 % (aucun
    prix ne peut produire un tel rendement).
    """
    projected = projected_value(metric_value, growth_pct, multiple, horizon, net_debt_per_share)
    if projected is None or projected <= 0 or horizon <= 0:
        return None
    net_target = (target_pct - dividend_yield_pct) / 100
    if net_target <= -1:
        return None
    return projected / (1 + net_target) ** horizon


def matrix_grid(
    center_growth_pct: float,
    center_multiple: float,
    n_rows: int,
    n_cols: int,
    growth_step: float,
    multiple_step: float,
) -> tuple[list[float], list[float]]:
    """Grille centrée de la matrice : (croissances, multiples).

    Les lignes (croissance) et colonnes (multiple) sont centrées sur les valeurs
    courantes, régulièrement espacées par `step`. Le nombre de pas est réparti
    autour du centre (le centre occupe l'index `n // 2`).
    """
    growths = [round(center_growth_pct + (i - n_rows // 2) * growth_step, 4) for i in range(n_rows)]
    multiples = [
        round(center_multiple + (j - n_cols // 2) * multiple_step, 4) for j in range(n_cols)
    ]
    return growths, multiples


def return_matrix(
    metric_value: float | None,
    price: float | None,
    growths: list[float],
    multiples: list[float],
    horizon: int,
    dividend_yield_pct: float = 0.0,
    net_debt_per_share: float | None = None,
) -> list[list[float | None]]:
    """Matrice des rendements estimés (lignes = croissances, colonnes = multiples)."""
    return [
        [
            estimated_return(
                metric_value, price, g, m, horizon, dividend_yield_pct, net_debt_per_share
            )
            for m in multiples
        ]
        for g in growths
    ]


def color_bucket(value: float | None, target_pct: float, ratios: tuple[float, float]) -> int | None:
    """Bucket de couleur d'une cellule (0=rouge, 1=brun, 2=jaune, 3=vert).

    Ancré sur la cible : < 0 -> 0 ; < ratio[0]·cible -> 1 ; < ratio[1]·cible -> 2 ;
    >= cible -> 3. Une cible non positive rend la coloration neutre (`None`).
    """
    if value is None or target_pct <= 0:
        return None
    if value < 0:
        return 0
    if value < ratios[0] * target_pct:
        return 1
    if value < ratios[1] * target_pct:
        return 2
    return 3


def median_multiple(valuation_row: pd.Series | None, years: int) -> float | None:
    """Médiane du multiple sur les `years` dernières années disponibles.

    `valuation_row` = ligne d'un multiple indexée par année (colonnes du tableau
    de valorisation). Les années vides sont écartées ; une série vide -> None.
    """
    if valuation_row is None:
        return None
    clean = valuation_row.dropna()
    if clean.empty:
        return None
    ordered = clean.sort_index(ascending=False).head(years)
    if ordered.empty:
        return None
    return float(ordered.median())


def _asof(by_year: dict[int, float] | None, year: int) -> float | None:
    """Valeur de l'exercice `year`, ou du dernier exercice connu antérieur.

    Report par palier (forward-fill) : c'est ce qui rend une série de multiples
    continue — le dénominateur annuel « saute » aux échéances tandis que le cours
    bouge en continu.
    """
    if not by_year:
        return None
    candidates = [y for y in by_year if y <= year]
    if not candidates:
        return None
    return by_year[max(candidates)]


def step_series(dates: pd.DatetimeIndex, by_year: dict[int, float] | None) -> pd.Series:
    """Série en ESCALIER alignée sur `dates` : valeur du dernier exercice ≤ année.

    C'est le report par palier (forward-fill) qui rend un multiple continu : le
    dénominateur annuel « saute » aux échéances tandis que le cours bouge en
    continu. None avant le premier exercice connu.
    """
    return pd.Series([_asof(by_year, ts.year) for ts in dates], index=dates, dtype=float)


def price_over_step(
    dates: pd.DatetimeIndex,
    prices: pd.Series,
    per_share_by_year: dict[int, float] | None,
) -> pd.Series:
    """Multiple continu = cours / métrique par action (escalier), aligné sur `dates`.

    None quand le cours ou le dénominateur manque (ou dénominateur ≤ 0) : jamais
    d'infini, jamais de valeur trompeuse.
    """
    denom = step_series(dates, per_share_by_year).to_numpy()
    out: list[float | None] = []
    for price, d in zip(prices.to_numpy(), denom, strict=False):
        if price is None or pd.isna(price) or price <= 0 or d is None or pd.isna(d) or d <= 0:
            out.append(None)
        else:
            out.append(float(price) / float(d))
    return pd.Series(out, index=dates, dtype=float)


def enterprise_multiple_series(
    dates: pd.DatetimeIndex,
    prices: pd.Series,
    shares_by_year: dict[int, float] | None,
    ebitda_by_year: dict[int, float] | None,
    net_debt_by_year: dict[int, float] | None,
) -> pd.Series:
    """EV/EBITDA continu = (cours × actions + dette nette) / EBITDA, par palier."""
    shares = step_series(dates, shares_by_year).to_numpy()
    ebitda = step_series(dates, ebitda_by_year).to_numpy()
    net_debt = step_series(dates, net_debt_by_year).to_numpy()
    out: list[float | None] = []
    for price, n, e, nd in zip(prices.to_numpy(), shares, ebitda, net_debt, strict=False):
        if (
            price is None
            or pd.isna(price)
            or price <= 0
            or n is None
            or pd.isna(n)
            or n <= 0
            or e is None
            or pd.isna(e)
            or e <= 0
            or nd is None
            or pd.isna(nd)
        ):
            out.append(None)
        else:
            out.append((float(price) * float(n) + float(nd)) / float(e))
    return pd.Series(out, index=dates, dtype=float)
