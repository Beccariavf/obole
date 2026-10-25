"""Contrats typés échangés entre les couches (data -> engine -> api).

Les champs susceptibles de manquer (yfinance incomplet) sont Optional explicites :
on est forcé de gérer l'absence partout, jamais de crash sur un champ vide.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum

import pandas as pd


class CompanyKind(str, Enum):
    """Schéma de comptes : industriel/commercial (défaut) ou financier (banque/assurance)."""

    INDUSTRIAL = "industrial"
    FINANCIAL = "financial"


@dataclass(frozen=True)
class CompanyOfficer:
    """Dirigeant d'une société (issu de `info.companyOfficers`).

    Sert la carte « Profil société » (section Thèse & Société) : le front lit le
    premier dirigeant pour le « DG » (ex. CEO/Président). Absence -> objet vide,
    jamais de crash.
    """

    name: str
    title: str | None = None
    age: int | None = None


@dataclass(frozen=True)
class Identity:
    ticker: str
    name: str | None = None
    isin: str | None = None
    country: str | None = None
    sector: str | None = None
    industry: str | None = None
    website: str | None = None
    currency: str | None = None
    market_cap: float | None = None
    last_price: float | None = None
    # Marché (synthèse « Résumé ») : volatilité, amplitude 52 semaines, liquidité.
    beta: float | None = None
    week52_low: float | None = None
    week52_high: float | None = None
    volume: float | None = None
    avg_volume: float | None = None
    # Profil société (section « Thèse & Société »). Tous Optionnels : yfinance les
    # fournit pour la plupart des grandes valeurs, mais l'absence doit se gérer.
    employees: int | None = None
    officers: tuple[CompanyOfficer, ...] = ()
    address: str | None = None
    summary: str | None = None
    next_earnings: str | None = None  # date ISO (prochain résultat)
    next_earnings_estimated: bool | None = None
    ex_dividend: str | None = None  # date ISO (prochain détachement)
    kind: CompanyKind = CompanyKind.INDUSTRIAL
    # Version du modèle (cf. `data/yahoo.MODEL_VERSION`) : un objet caché d'une
    # version antérieure est considéré comme périmé.
    model_version: int = 0


@dataclass
class PriceSeries:
    """Cours historiques. `raw` = Close brut, `adjusted` = Adj Close (div réinvestis)."""

    raw: pd.Series  # index = dates, valeurs = Close
    adjusted: pd.Series  # index = dates, valeurs = Adj Close
    fetched_at: date


@dataclass
class Fundamentals:
    """Comptes annuels (autant d'années que yfinance fournit, ~4-5).

    DataFrame indexé par année. Colonnes selon le schéma (industriel vs financier).
    `available_years` sert au badge de fiabilité.

    `valuation` : multiples historiques (PER, P/FCF, EV/EBITDA…), reconstruits par
    croisement prix×comptes (engine/valuation). None si non calculable.
    `dividend` : instantanés + historique du dividende (yield, payout, série/action).
    `growth` : CAGR (3a/5a) du CA, BNPA, FCF.
    `market` : instantanés de marché issus de `info` (multiples courants, dividende
        annuel, OCF) pour la synthèse « Résumé ». None si indisponibles.
    `health_rows` : postes BRUTS (indexés par Timestamp de clôture) requis par les
        scores de santé (Altman Z, Piotroski) et la couverture d'intérêts.
    `estimates` : consensus analystes (croissance CA / BNPA à 1 an), en %.
    """

    table: pd.DataFrame
    kind: CompanyKind
    available_years: int
    fetched_at: date
    valuation: pd.DataFrame | None = None
    dividend: dict | None = None
    growth: dict | None = None
    # Postes bruts (indexés par date de clôture) préparés par data/ pour que
    # engine/valuation reconstruise les multiples ; non sérialisé vers le front.
    valuation_rows: dict | None = None
    # Séries de rendement continu (%) alignées sur la série de prix : calculées
    # par services/analysis (seule couche qui voit prix + dividendes), décimées
    # comme le cours. Non sérialisées ici (passent par le payload `chart`).
    dividend_yield: pd.Series | None = None
    shareholder_yield: pd.Series | None = None
    # Années pour lesquelles l'utilisateur a fourni des données manuelles.
    manual_years: list[int] | None = None
    # Synthèse « Résumé » : instantanés de marché, postes de santé, consensus.
    market: dict | None = None
    health_rows: dict | None = None
    estimates: dict | None = None
    # Section « Valorisation » : séries CONTINUES de multiples (cours quotidien ×
    # métrique annuelle reportée par palier), alignées sur la série de prix et
    # décimées comme elle. Calculées par services/analysis (seule couche qui voit
    # prix + comptes), consommées par le payload `chart`.
    valuation_series: dict | None = None
    # Calculatrice de prix juste : métrique par action (série annuelle), multiple
    # médian par période, CAGR, dividende — données dont le front a besoin pour
    # reconstruire le calcul en live. Non sérialisé tel quel (payload dédié).
    valuation_calc: dict | None = None
    # Version du modèle de données. Un objet caché d'une version antérieure (TTL
    # 7 jours) peut ne pas porter les derniers champs : `data/yahoo` le considère
    # comme périmé et re-fetch. À incrémenter à chaque évolution du dataclass.
    model_version: int = 0


@dataclass(frozen=True)
class RegressionResult:
    """Résultat d'une régression log : ln(P) = a + b·t."""

    a: float  # intercept
    b: float  # pente (perf continue annualisée)
    sigma: float  # écart-type des résidus (unités log)
    t_now: float  # temps actuel (années depuis le début)
    fitted_now: float  # valeur de la droite aujourd'hui
    start: date
    end: date
    n_points: int

    @property
    def perf_annual(self) -> float:
        """Performance annuelle simple = e^b − 1."""
        import math

        return math.exp(self.b) - 1

    @property
    def ecart_type_size(self) -> float:
        """« Écart-type (taille) » Obole = e^sigma − 1."""
        import math

        return math.exp(self.sigma) - 1


@dataclass(frozen=True)
class ScoredValue:
    """Une valeur numérique + son label calibré + sa polarité (pour la couleur)."""

    value: float | None
    label: str | None
    good: bool | None = None  # True=favorable(bleu), False=défavorable(rouge), None=neutre


@dataclass(frozen=True)
class SummaryRow:
    """Une ligne « libellé → valeur » de la grille de synthèse (section Résumé).

    `unit` pilote le formatage côté front : "pct" (%), "x" (multiple), "money"
    (montant dans la devise de la source), "num", "years", "score" (sur 20),
    "text" (valeur non numérique portée par `text`). Une valeur non calculable
    reste None : le front affiche « -- ».
    """

    key: str
    label: str
    value: float | None = None
    unit: str = "num"
    text: str | None = None
    good: bool | None = None
    # Note explicative (infobulle) : sert à documenter une absence volontaire
    # (ex. Altman Z / Piotroski non applicables aux financières).
    note: str | None = None
    # Carte MATRICE uniquement (ex. Croissance : lignes CA/EPS, colonnes 1A/5A/10A/
    # Futur) : valeurs alignées sur les colonnes de la carte, et leur polarité.
    # Vides pour une carte « libellé → valeur » classique.
    cells: list[float | None] = field(default_factory=list)
    cell_good: list[bool | None] = field(default_factory=list)


@dataclass(frozen=True)
class SummaryCard:
    """Une carte thématique de la grille de synthèse (PROFIL, MARCHÉ…).

    `columns` non vide = carte MATRICE (les lignes portent `cells`) ; vide = carte
    « libellé → valeur » classique (les lignes portent `value`).
    """

    id: str
    title: str
    rows: list[SummaryRow] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)


@dataclass
class Indicators:
    """Tous les indicateurs synthétiques d'une fiche."""

    distance_sigma: ScoredValue  # valorisation (z)
    perf_passee: ScoredValue  # pente Adj Close
    ecart_type: ScoredValue  # volatilité
    potential_5y: ScoredValue
    potential_10y: ScoredValue
    trend: ScoredValue  # Haussière / Baissière
    quality: ScoredValue  # qualité de l'exploitation
    # Bêta (amplitude) & corrélation (solidité du lien) A~B : peuplés uniquement
    # pour un ratio (neutres par défaut pour une action).
    beta: ScoredValue = field(default_factory=lambda: ScoredValue(None, None, None))
    correlation: ScoredValue = field(default_factory=lambda: ScoredValue(None, None, None))


@dataclass
class StockAnalysis:
    """Objet complet renvoyé par l'API pour une fiche valeur."""

    identity: Identity
    indicators: Indicators
    regression_raw: RegressionResult  # sur Close (valorisation)
    regression_adj: RegressionResult  # sur Adj Close (perf passée)
    fundamentals: Fundamentals | None
    warnings: list[str] = field(default_factory=list)  # badges de fiabilité
    # Grille de synthèse (section Résumé) : lecture rapide, valeurs seules.
    summary: list[SummaryCard] = field(default_factory=list)


@dataclass
class RatioAnalysis:
    """Analyse d'un ratio A/B entre deux actifs (ETF, indices…).

    Un ratio est une série de prix synthétique : mêmes indicateurs PRIX que pour
    une action (distance σ, perf, écart-type, potentiels), mais pas de
    fondamentaux (un ratio n'a ni comptes ni dividendes propres). Les champs
    `trend`/`quality` d'`indicators` restent vides (ScoredValue(None,None,None)).
    """

    ticker_a: str
    ticker_b: str
    label: str  # "CW8.PA / SPY"
    last_ratio: float
    indicators: Indicators  # seuls les champs prix sont peuplés
    regression: RegressionResult
    warnings: list[str] = field(default_factory=list)


@dataclass
class ScreenResult:
    """Ligne de résultat du screener : une valeur réduite à des champs triables.

    Champs numériques (peuvent être None = donnée indisponible) sur lesquels
    s'appliquent les filtres et le tri multi-colonnes. `error` isole un ticker
    cassé au J3 (le scan complet ne doit jamais crasher sur une valeur).

    **Fenêtre de régression** : quand `screen_stock` reçoit un `regression_window`,
    `z`, `pente_pct`, `ecart_type_pct` et `pot_*_pct` sont calculés sur cette
    fenêtre (règle de `summary.member_stats`) ; `trend_bullish` (croisement MM11/200)
    reste sur l'historique complet. Sans fenêtre, tout est sur l'historique plein.
    """

    ticker: str
    name: str | None = None
    sector: str | None = None
    market_cap: float | None = None
    kind: CompanyKind = CompanyKind.INDUSTRIAL

    # Indicateurs prix (méthode « droite d'Obole »).
    z: float | None = None  # distance σ (valorisation) — un z faible = décoté
    pente_pct: float | None = None  # performance passée, %/an
    ecart_type_pct: float | None = None  # volatilité, %
    pot_5y_pct: float | None = None
    pot_10y_pct: float | None = None
    trend_bullish: bool | None = None

    # Fondamentaux (None si comptes indisponibles).
    roe_pct: float | None = None
    per: float | None = None
    p_b: float | None = None
    p_fcf: float | None = None
    fcf_yield_pct: float | None = None

    quality_score: float | None = None  # qualité de l'exploitation (0-100)
    # Score composite (#14) : classement par compromis sur ≥ 2 critères actifs.
    # Percentile 0-100 par critère (100 = meilleur), moyenné à poids égaux.
    # None quand aucun score n'a été demandé ou qu'un critère actif manque.
    score: float | None = None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class BasketAnalysis:
    """Analyse d'un indice personnalisé (panier d'actions, equal-weight chaîné).

    Comme un ratio : une série de prix synthétique qui passe dans la régression,
    mêmes indicateurs PRIX (distance σ, perf, écart-type, potentiels), mais pas de
    fondamentaux ni de β/ρ (un indice n'a pas d'actif de référence). `members`
    liste les membres avec leurs stats « coup d'œil »
    [{ticker, name, distance_sigma, pente, trend} : ScoredValue] pour l'affichage,
    le refresh et la navigation. La tendance MM est calculée sur la série
    synthétique (résumé + KPI).
    """

    index_id: int
    name: str
    category: str
    members: list[dict]  # [{"ticker": str, "name": str | None}]
    last_value: float
    indicators: Indicators  # seuls les champs prix sont peuplés
    regression: RegressionResult
    warnings: list[str] = field(default_factory=list)


# --- Watchlist (#25) ---------------------------------------------------------
# Une ligne de classement : la valeur suivie + SES deux lectures de marge.
# `fair_price_source` dit d'où vient le prix juste ("saved" = calculatrice,
# "regression" = droite de référence) ; `margin_good` porte la polarité couleur
# (bleu > 0, rouge < 0) pour que le front n'ait aucun seuil à connaître.
@dataclass(frozen=True)
class WatchlistRow:
    """Une valeur suivie, réduite à ses champs de classement.

    Depuis #25.2, la ligne est en **total-return** : `z`, `ecart_type_pct`,
    `trend_gap_pct`, `pente_pct` et les potentiels viennent de la régression
    ajustée (dividendes réinvestis) et du dernier cours ajusté ; `price` reste le
    cours brut et `ref_line` est la ligne ajustée ramenée à son échelle.
    `safety_margin_pct` est la marge contre le prix juste : enregistré
    (`fair_price_source="saved"`, `target_yield` propre) ou, à défaut, prix
    d'entrée à 12 %/an jusqu'à la droite à 5 ans (`fair_price_source="regression"`,
    `target_yield=12`). Dans ce repli, la marge ne coïncide plus avec l'écart.
    """

    ticker: str
    tier: int
    name: str | None = None
    sector: str | None = None
    currency: str | None = None
    price: float | None = None

    fair_price: float | None = None
    fair_price_source: str | None = None  # "saved" | "regression" | None
    target_yield: float | None = None  # objectif de la source (12 par défaut sur la ligne)
    safety_margin_pct: float | None = None
    margin_good: bool | None = None

    ref_start: str | None = None  # début EFFECTIF de la fenêtre (ISO)
    ref_is_default: bool = True  # True = fenêtre 20 ans (aucune référence)
    ref_line: float | None = None
    trend_gap_pct: float | None = None
    z: float | None = None
    ecart_type_pct: float | None = None

    pente_pct: float | None = None
    pot_5y_pct: float | None = None
    pot_10y_pct: float | None = None
    trend_bullish: bool | None = None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class WatchlistRun:
    """Résultat d'un classement : lignes triées + horodatage du calcul."""

    generated_at: float
    rows: list[WatchlistRow] = field(default_factory=list)


# --- Import piloté (#23) -----------------------------------------------------
# Contrats du staging d'import : un CSV venu de l'extérieur (IA via MCP, ou
# collage humain) est d'abord PARSÉ puis PROPOSÉ, jamais appliqué. Le rapport
# dit exactement ce qui a été accepté / écrasé / rejeté (et pourquoi).


@dataclass(frozen=True)
class ImportRejection:
    """Une cellule ou une ligne écartée à l'import, avec sa raison exploitable.

    `reason` appartient à l'ensemble fermé `config.IMPORT_REJECT_REASONS` :
    l'UI et l'IA n'ont pas à interpréter un texte libre pour comprendre un rejet.
    """

    year: int | None
    metric: str | None
    raw: str | None
    reason: str  # cf. config.IMPORT_REJECT_*


@dataclass
class ImportReport:
    """Rapport complet d'un parsing d'import (jamais une écriture métier).

    `entries` sont les valeurs SOURCE retenues (à upsert par `apply_draft`
    uniquement) ; `overridden` compte les cellules qui remplacent une valeur
    existante ; `rejected` liste les rejets (échantillon borné par
    `config.IMPORT_MAX_REJECT_SAMPLES`, `rejected_total` portant le total réel).
    `unknown_columns` / `derived_columns` : en-têtes vus mais non importés, pour
    que l'utilisateur comprenne pourquoi une colonne a été ignorée.
    """

    entries: list[dict] = field(default_factory=list)
    overridden: int = 0
    rejected: list[ImportRejection] = field(default_factory=list)
    rejected_total: int = 0
    unknown_columns: list[str] = field(default_factory=list)
    derived_columns: list[str] = field(default_factory=list)
    delimiter: str = ","

    @property
    def accepted(self) -> int:
        """Nombre de valeurs source retenues (à appliquer si l'utilisateur valide)."""
        return len(self.entries)

    def summary(self) -> dict:
        """Vue courte (sans les entrées) : ce que l'IA et l'UI affichent."""
        return {
            "accepted": self.accepted,
            "overridden": self.overridden,
            "rejected_total": self.rejected_total,
            "unknown_columns": self.unknown_columns,
            "derived_columns": self.derived_columns,
            "delimiter": self.delimiter,
        }

    def to_dict(self) -> dict:
        """Payload complet (rapport + entrées + échantillon de rejets) — JSON-ready."""
        return {
            **self.summary(),
            "entries": self.entries,
            "rejected": [
                {"year": r.year, "metric": r.metric, "raw": r.raw, "reason": r.reason}
                for r in self.rejected
            ],
        }


@dataclass
class ImportDraft:
    """Un import proposé, en attente de validation humaine (`import_drafts`).

    `payload` porte le rapport complet (`ImportReport.to_dict()`). Tant que
    `status == "pending"`, aucun effet métier : c'est le garde-fou du chantier.
    """

    id: int
    target: str  # cf. `services/imports.TARGETS` (ex. "fundamentals")
    ref: str  # ticker (ou autre clé selon la cible)
    payload: dict
    status: str  # "pending" | "applied" | "rejected"
    created_at: float
    applied_at: float | None = None
