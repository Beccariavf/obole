"""Constantes centralisées — aucun nombre magique éparpillé dans le code.

Les seuils de labels sont calibrés sur 6 fiches Obole réelles (cf. PRD §5).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import NotRequired, TypedDict

# --- Chemins / cache ---------------------------------------------------------
# Racine du dépôt en développement ; placée sous `site-packages` quand le paquet
# est installé, d'où l'importance de `DATA_HOME` ci-dessous.
ROOT = Path(__file__).resolve().parents[2]


def _default_data_home() -> Path:
    """Répertoire des données utilisateur, hors du paquet installé.

    Un paquet installé (pipx/pip) ne doit **jamais** écrire dans `site-packages` :
    cela mélangerait données et code, et un `pip uninstall` les emporterait. En
    développement (checkout), on conserve la racine du dépôt — c'est là que
    l'utilisateur s'attend à trouver `cache.sqlite`.

    Priorités : `OBOLE_DATA_DIR` > racine du dépôt si elle est inscriptible >
    `$XDG_DATA_HOME/obole` > `~/.local/share/obole`.
    """
    override = os.environ.get("OBOLE_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if (ROOT / "pyproject.toml").is_file():
        return ROOT
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share"
    return base / "obole"


DATA_HOME = _default_data_home()
# Base de cache. `OBOLE_CACHE_DB` la redirige vers une base **jetable** : les
# suites e2e (qui écrivent : thèses, points de contrôle) ne doivent JAMAIS taper
# la base réelle de l'utilisateur — un incident a montré qu'un `try/finally` ne
# protège pas d'une interruption brutale entre l'écriture et la restauration.
CACHE_DB = Path(os.environ.get("OBOLE_CACHE_DB") or (DATA_HOME / "cache.sqlite"))
# Images insérées dans les thèses (#21) : dossier de données utilisateur, hors
# dépôt (sauvegarde de fichiers, pas de base). Jamais servi depuis le front.
THESIS_ASSETS_DIR = DATA_HOME / "thesis_assets"

# Points de contrôle suivis (#21, bande « Suivi ») : liste possédée par
# l'utilisateur, INDÉPENDANTE du document markdown de la thèse (les deux ne
# portent pas forcément les mêmes éléments). Bornes partagées par la validation
# (`data/checkpoints.py`) et le front — miroir des bornes d'`events.py`.
CHECKPOINT_LABEL_MAX = 120
CHECKPOINT_MAX_PER_REF = 50

# --- Import CSV piloté (#23) -------------------------------------------------
# Un CSV vient de l'extérieur (Excel FR, export courtier, collage de tableau) :
# le format n'est jamais garanti. Ces bornes et cet ensemble fermé de raisons de
# rejet sont la SEULE source — le parseur (`data/manual`), le staging
# (`services/imports`), le front et l'IA les lisent ici, jamais en dur.
#
# Raisons de rejet d'une cellule (ensemble fermé). Sert au rapport d'import :
# l'utilisateur (et l'IA) doit savoir POURQUOI une valeur n'a pas été reprise,
# au lieu du silence actuel.
IMPORT_REJECT_UNPARSEABLE = "unparseable"  # valeur non numérique (ou hors format)
IMPORT_REJECT_DERIVED = "derived_column"  # ratio calculé : jamais réimporté
IMPORT_REJECT_UNKNOWN = "unknown_column"  # colonne hors taxonomie
IMPORT_REJECT_YEAR = "bad_year"  # ligne sans année exploitable
IMPORT_REJECT_REASONS = (
    IMPORT_REJECT_UNPARSEABLE,
    IMPORT_REJECT_DERIVED,
    IMPORT_REJECT_UNKNOWN,
    IMPORT_REJECT_YEAR,
)
# Colonnes cibles d'un import piloté (`services/imports.TARGETS`).
IMPORT_TARGET_FUNDAMENTALS = "fundamentals"
IMPORT_MAX_CSV_BYTES = 2_000_000  # taille maximale du texte CSV collé/envoyé
IMPORT_MAX_ENTRIES = 5_000  # nombre maximal de valeurs acceptées par lot
IMPORT_MAX_DRAFTS = 50  # brouillons `pending` conservés simultanément
IMPORT_DRAFT_TTL_DAYS = 30  # au-delà, un brouillon non validé est purgé
IMPORT_MAX_REJECT_SAMPLES = 50  # échantillons de rejets détaillés (le reste compté)

# Bornes des uploads HTTP. Un `UploadFile.read()` sans plafond charge tout en
# mémoire : un corps de plusieurs Go suffirait à faire tomber un serveur sans
# authentification. Le plafond est vérifié AVANT la lecture complète.
UPLOAD_MAX_CSV_BYTES = IMPORT_MAX_CSV_BYTES  # CSV de comptes (route manuelle)
UPLOAD_MAX_RESTORE_BYTES = 50 * 1024 * 1024  # archive JSON de sauvegarde
UPLOAD_MAX_ASSET_BYTES = 5 * 1024 * 1024  # image de thèse (aligné sur data/thesis_assets)

# TTL du cache (secondes). Cache agressif : minimise les appels réseau yfinance.
TTL_PRICES = 24 * 3600  # prix : 1 jour
TTL_FUNDAMENTALS = 7 * 24 * 3600  # comptes / info : 7 jours
# Cache NÉGATIF des comptes indisponibles (crypto, ETF, petite place) : sans lui,
# chaque ouverture de l'onglet Performance rejouait les appels + retries (~1-2 s
# par titre). Court, pour laisser une chance à un titre de publier ses comptes.
TTL_MISSING_FUNDAMENTALS = 6 * 3600  # absence de comptes : 6 heures
TTL_SEARCH = 24 * 3600  # autocomplétion nom -> ticker : 1 jour
SQLITE_BUSY_TIMEOUT = 5000  # ms : attendre en WAL plutôt que lever « database is locked »
# Retry des écritures sous contention (#11). `busy_timeout` amortit un verrou
# court ; au-delà, l'instruction est rejouée avec un back-off linéaire. Un verrou
# permanent doit remonter après un nombre borné de tentatives (pas de boucle infinie).
SQLITE_WRITE_RETRIES = 5  # tentatives par instruction (dont la première)
SQLITE_WRITE_BACKOFF_S = 0.05  # attente de base, multipliée par le numéro de tentative

# --- Observabilité (#01) -----------------------------------------------------
# Journalisation locale : console (stderr) + fichier à rotation dans `logs/`
# (dossier gitignoré, comme les caches d'outils). Le niveau se règle par
# `OBOLE_LOG_LEVEL` (défaut INFO).
LOG_DIR = DATA_HOME / "logs"
LOG_FILE = LOG_DIR / "obole.log"
LOG_MAX_BYTES = 1_000_000  # 1 Mo par fichier avant rotation
LOG_BACKUP_COUNT = 3  # fichiers conservés (obole.log.1 … .3)
# Au-delà de ce seuil, un appel yfinance est signalé comme lent (WARNING).
SLOW_CALL_MS = 3000
# Fenêtre « échecs récents » de la brique yfinance de /api/health (secondes).
HEALTH_FAILURE_WINDOW_S = 300

# Version courante du schéma de `cache.sqlite` (chantier #02). Source unique :
# toute évolution du schéma incrémente cette constante ET ajoute une migration
# dans `data/cache.MIGRATIONS` (clé = version source, valeur = fonction n -> n+1).
# Une base d'une version antérieure est mise à niveau automatiquement à la
# première ouverture de la base ; `PRAGMA user_version` porte la version
# réellement appliquée.
SCHEMA_VERSION = 7

# --- Méthode « droite d'Obole » ---------------------------------------------
# Horizons pour le potentiel annualisé.
POTENTIAL_HORIZONS = (5, 10)

# Moyennes mobiles pour la tendance boursière (validé 5/5 sur fiches réelles).
TREND_MA_SHORT = 11
TREND_MA_LONG = 200

# Fenêtre de régression « non synchronisée » (règle Obole, dividendes inclus) :
# 30 ans pour les financières (banques/assurances), 20 ans pour les autres.
# « Des droites trop longues peuvent mal renseigner sur les évolutions futures. »
REGRESSION_YEARS_DEFAULT = 20
REGRESSION_YEARS_FINANCIAL = 30

# --- Portefeuille : benchmarks (#17.1) ---------------------------------------
# Liste curée d'ETF UCITS cotés en EUR (historique long vérifié sur Yahoo), pour
# comparer la performance du portefeuille à un indice de référence. SOURCE UNIQUE
# servie par l'API (`/api/portfolio/benchmarks`) : le front n'a aucun ticker en dur.
PORTFOLIO_BENCHMARKS = [
    {"key": "world", "ticker": "CW8.PA", "label": "MSCI World"},
    {"key": "sp500", "ticker": "ESE.PA", "label": "S&P 500"},
    {"key": "europe", "ticker": "ETZ.PA", "label": "STOXX Europe 600"},
    {"key": "eurostoxx50", "ticker": "MSE.PA", "label": "EURO STOXX 50"},
    {"key": "cac40", "ticker": "CACC.PA", "label": "CAC 40"},
    {"key": "nasdaq100", "ticker": "ANX.PA", "label": "Nasdaq-100"},
    {"key": "emerging", "ticker": "PAEEM.PA", "label": "MSCI Emerging"},
]
PORTFOLIO_BENCHMARK_DEFAULT = "CW8.PA"
# Périodes proposées dans le sélecteur de la section Résumé (raccourcis) : `ytd`
# = depuis le 1er janvier ; les autres = N dernières années ; `max` = tout.
PORTFOLIO_PERIODS = ("ytd", "1a", "3a", "5a", "max")
PORTFOLIO_PERIOD_DEFAULT = "1a"
# Périodes proposées pour les ratios ajustés au risque (Sharpe/Sortino) de la
# Performance (#17.4) : `ttm` = 12 derniers mois, `Na` = N dernières années,
# `max` = historique complet. `ttm` est PROPRE à ces ratios (absent de
# PORTFOLIO_PERIODS, donc refusé par `_validate_period` de la route) ; les autres
# recoupent PORTFOLIO_PERIODS. Le front masque le sélecteur sous une seule période.
PORTFOLIO_RISK_PERIODS = ("ttm", "3a", "5a", "max")
# Horizons temporels du graphe de détail par titre (modale Performance, #17.4) :
# TTM / 3A / 5A / 10A / MAX. Purement client (recadrage de la série déjà chargée),
# mais la liste reste la source unique lue par le front via `/api/meta`.
PORTFOLIO_DETAIL_HORIZONS = ("ttm", "3a", "5a", "10a", "max")
PORTFOLIO_DETAIL_HORIZON_DEFAULT = "5a"
# Nombre de lignes des cartes « Top 5 » / « Flop 5 ».
PORTFOLIO_TOP_N = 5
# Plafond de tickers traités par `/api/portfolio/names` : chaque ticker non caché
# coûte un appel `info` yfinance (0,5-2 s), synchrone. Le front n'en demande que
# pour le Top/Flop, on borne donc pour qu'une liste forgée ne bloque pas la requête.
PORTFOLIO_NAMES_MAX = 20

# --- Portefeuille : étiquettes / portefeuilles virtuels (#17.6) --------------
# Une transaction porte AU PLUS une étiquette (`tag`, nullable) : un portefeuille
# virtuel = l'ensemble des transactions étiquetées (ex. « Actions dividende » dans
# un PEA). Une étiquette n'est donc pas une entité persistée à part : la liste des
# étiquettes d'un portefeuille est le **distinct** des `tag` non nuls (aucune
# table de référence, aucune liste en dur — cohérent avec la sobriété du projet).
# Longueur bornée (miroir de la validation de `data/portfolio`), exposée au front
# via `/api/meta` (`portfolio_tag_max`) pour le `maxlength` du champ de saisie.
PORTFOLIO_TAG_MAX = 40

# --- Portefeuille : risque (#17.3) -------------------------------------------
# Corrélations entre lignes calculées sur les rendements LOG QUOTIDIENS de la
# fenêtre courante. En deçà d'un nombre minimal d'observations communes, la
# corrélation n'est pas fiable : la ligne est ÉCARTÉE de la matrice avec un badge
# explicite (jamais un zéro trompeur). Seuil unique, exposé via `/api/meta`.
PORTFOLIO_CORR_MIN_OBS = 20
# Part des week-ends de la période qu'une série doit couvrir pour être jugée
# « cotée 24/7 » (crypto) et donc écartée du calendrier de séances. Proportionnel
# et non « au moins une fois » : une barre de week-end parasite (séance de
# rattrapage, fuseau mal interprété) ne doit pas priver une action de ses séances.
PORTFOLIO_ROUND_CLOCK_WEEKEND_RATIO = 0.5
# Au-delà de cette taille (nombre de lignes), le front masque les valeurs
# annotées dans la heatmap (cellules illisibles) et bascule sur l'infobulle au
# survol : au-delà, l'annotation devient du bruit. Exposé via `/api/meta`.
PORTFOLIO_CORR_ANNOTATE_MAX = 12

# --- Portefeuille : performance (#17.4) --------------------------------------
# Nombre de mois affichés dans le tableau des rendements mensuels (colonnes).
PORTFOLIO_MONTHS = 12
# Fenêtre de régression (années) pour la « pente » et les potentiels moyens des
# stats agrégées (méthode « droite d'Obole », même fenêtre que la valorisation).
# Une seule constante, jamais un littéral côté service.
PORTFOLIO_STAT_REGRESSION_YEARS = 20
# Workers du calcul des stats agrégées de la Performance (#17.4, revue #1) : la
# boucle appelle `analysis.analyze` par ligne, soit ~4 requêtes yfinance
# séquentielles (info, financials, balance sheet, cashflow). Les exécuter en
# parallèle borné ramène N×4 appels séquentiels à ~4 vagues. Aligné sur
# `SCREEN_WORKERS` (même nature I/O-bound), plafonné par le nombre de lignes.
PORTFOLIO_PERF_WORKERS = 8
# Budget par worker (s) pour l'analyse d'une ligne de la Performance : multiplié
# par le nombre de workers, il forme le plafond global de la boucle (même garde-fou
# anti-blocage que `SCREEN_FETCH_TIMEOUT` du screener). Au-delà, les lignes encore
# en cours sont abandonnées et n'entrent pas dans les stats.
PORTFOLIO_PERF_TIMEOUT = 20
# Taux sans risque PAR DÉFAUT du ratio de Sharpe/Sortino (%/an). 0 % = le taux
# neutre : Sharpe = rendement / volatilité. Réglable dans la modale Paramètres
# (réglage `portfolio_risk_free`, groupe « Mesure technique »).
PORTFOLIO_RISK_FREE_DEFAULT = 0.0
# Taxonomie des statistiques agrégées de la section Performance (#17.4) : SOURCE
# UNIQUE de l'ordre, des libellés et des clés. Le service produit un dict
# {clé: {"value", "good"}} ; le front rend les groupes dans cet ordre, sans
# aucun libellé ni seuil en dur. `unit` : "pct" | "num" | "money" | "score".
# `signed: True` marque une VARIATION (pente, potentiels) : le front préfixe
# alors d'un « + » les valeurs positives. Absent = un NIVEAU (marge, ROE, ROCE,
# agilité…), jamais signé — afficher « +42,5 % » de marge brute serait faux, et
# la fiche entreprise montre ces mêmes métriques sans signe.
# La polarité couleur d'une métrique n'est PAS portée ici : elle vient de
# `PORTFOLIO_STAT_POLARITY` (source unique des seuils, cf. ci-dessous).
PORTFOLIO_STAT_GROUPS = [
    {
        "id": "general",
        "title": "Général",
        "metrics": [
            {"key": "count", "label": "Nombre d'actions", "unit": "num"},
            {"key": "top5_weight", "label": "Top 5 du portefeuille", "unit": "pct"},
            {"key": "market_cap", "label": "Valeur investie", "unit": "money"},
            {"key": "quality", "label": "Note Q", "unit": "score"},
        ],
    },
    {
        "id": "marges",
        "title": "Marges",
        "metrics": [
            {"key": "gross_margin", "label": "Marge brute", "unit": "pct"},
            {"key": "op_margin", "label": "Marge opérationnelle", "unit": "pct"},
            {"key": "net_margin", "label": "Marge nette", "unit": "pct"},
        ],
    },
    {
        "id": "rentabilite",
        "title": "Retours sur capitaux",
        "metrics": [
            {"key": "roe", "label": "ROE", "unit": "pct"},
            {"key": "roce", "label": "ROCE", "unit": "pct"},
            {"key": "roic", "label": "ROIC", "unit": "pct"},
        ],
    },
    {
        "id": "sante",
        "title": "Santé",
        "metrics": [
            {"key": "net_debt_ebitda", "label": "Dette nette / EBITDA", "unit": "num"},
            {"key": "piotroski", "label": "Piotroski", "unit": "num"},
            {"key": "altman_z", "label": "Altman Z", "unit": "num"},
            {"key": "agility", "label": "Agilité", "unit": "pct"},
        ],
    },
    {
        "id": "croissance",
        "title": "Croissance",
        "metrics": [
            {"key": "slope", "label": "Pente 20 ans", "unit": "pct", "signed": True},
            {"key": "pot_5y", "label": "Potentiel 5 ans", "unit": "pct", "signed": True},
            {"key": "pot_10y", "label": "Potentiel 10 ans", "unit": "pct", "signed": True},
        ],
    },
    {
        "id": "valorisation",
        "title": "Valorisation",
        "metrics": [
            {"key": "per", "label": "P/E", "unit": "num"},
            {"key": "p_fcf", "label": "P/FCF", "unit": "num"},
            {"key": "p_b", "label": "P/B", "unit": "num"},
        ],
    },
]

# --- Réglages utilisateur (panneau « Paramètres », persistés en base) --------
# Défauts de la méthode ; les valeurs effectives vivent en base (table settings).
# SETTING_DEFS décrit chaque réglage : son défaut, ses bornes, son libellé UI et
# son groupe de la modale. Ajouter un paramètre = une ligne ici, la logique de
# lecture (cache.get_settings) et l'UI (groupe) le rendent sans autre changement.


class SettingDef(TypedDict):
    """Description d'un réglage persisté.

    `choices` est OPTIONNEL : quand il est présent, la valeur est restreinte à
    une liste fermée (le front n'envoie jamais autre chose, la base non plus).
    """

    default: int | str
    min: int
    max: int
    label: str
    group: str
    choices: NotRequired[list[str]]


SETTING_DEFS: dict[str, SettingDef] = {
    "trend_ma_short": {
        "default": TREND_MA_SHORT,
        "min": 2,
        "max": 250,
        "label": "Moyenne mobile courte",
        "group": "technique",  # section « Mesure technique »
    },
    "trend_ma_long": {
        "default": TREND_MA_LONG,
        "min": 2,
        "max": 250,
        "label": "Moyenne mobile longue",
        "group": "technique",
    },
    # Benchmark du portefeuille (#17.1) : réglage TEXTE, dont la valeur est un
    # ticker yfinance. La « liste fermée » est `PORTFOLIO_BENCHMARKS` (ci-dessus)
    # ; un ticker arbitraire reste accepté (recherche libre du front). Le groupe
    # `portefeuille` n'est PAS listé dans SETTING_GROUPS : ce réglage se pilote
    # depuis la section Résumé (dernier choix = norme), pas depuis la modale.
    "portfolio_benchmark": {
        "default": PORTFOLIO_BENCHMARK_DEFAULT,
        "min": 1,
        "max": 24,
        "label": "Benchmark du portefeuille",
        "group": "portefeuille",
    },
    # Période d'analyse du portefeuille (#17.1, bandeau de contexte unifié) :
    # dernier choix mémorisé, comme le benchmark. `choices` restreint la valeur
    # à PORTFOLIO_PERIODS — le front n'envoie jamais autre chose, la base non plus.
    "portfolio_period": {
        "default": PORTFOLIO_PERIOD_DEFAULT,
        "min": 1,
        "max": 8,
        "choices": list(PORTFOLIO_PERIODS),
        "label": "Période du portefeuille",
        "group": "portefeuille",
    },
    # Taux sans risque du ratio de Sharpe/Sortino (#17.4), en POINTS DE BASE
    # (0-1000 = 0-10 %/an) : un entier pour rester dans le mécanisme de validation
    # existant (bornes numériques). 0 = taux neutre (Sharpe = rendement/volatilité).
    "portfolio_risk_free": {
        "default": int(round(PORTFOLIO_RISK_FREE_DEFAULT * 100)),
        "min": 0,
        "max": 1000,
        "label": "Taux sans risque (pb/an)",
        "group": "technique",
    },
}
# Ordre d'affichage des groupes dans la modale Paramètres. `portefeuille` est
# volontairement absent : son réglage vit dans la section Résumé du portefeuille.
SETTING_GROUPS = ["technique"]

# --- Seuils de labels (calibrés, PRD §5) -------------------------------------
# Chaque liste : (borne_sup_exclue, label). Le dernier capte le reste (None).

# Écart-type (taille), en % : e^sigma - 1
ECART_TYPE_LABELS = [
    (20, "Faible"),
    (35, "Moyen"),
    (55, "Plutôt élevée"),
    (None, "Elevée"),
]

# Distance en écart-type (z) -> valorisation
DISTANCE_SIGMA_LABELS = [
    (-2, "Décotée"),
    (-1, "Sous-cotée"),
    (0, "Légèrement sous-cotée"),
    (0.5, "Légèrement surcotée"),
    (None, "Surcotée"),
]

# Performance passée (pente Adj Close), en %/an
PERF_LABELS = [
    (4, "Médiocre"),
    (10, "Moyen"),
    (None, "Bien"),
]

# Potentiel annualisé (5 ou 10 ans), en %/an
POTENTIAL_LABELS = [
    (0, "Mauvais"),
    (5, "Médiocre"),
    (10, "Moyen"),
    (15, "Bien"),
    (None, "Excellent"),
]

# Qualité de l'exploitation (score 0-100)
QUALITY_LABELS = [
    (35, "Médiocre"),
    (55, "Moyen"),
    (75, "Bon"),
    (None, "Excellent"),
]

# Polarité couleur des labels prix (bleu = bon) : (sens, seuil).
#   sens "lt" : bon si valeur < seuil (plus petit = mieux)
#   sens "ge" : bon si valeur >= seuil (plus grand = mieux)
# SOURCE UNIQUE : consommée par `engine.labels` (couleur serveur) ET exposée au
# front via /api/meta (le miroir `scored` de app.js n'a aucun seuil en dur).
LABEL_POLARITY: dict[str, tuple[str, float]] = {
    "distance": ("lt", 0.0),  # décoté (z<0) = opportunité
    "ecart": ("lt", 35.0),  # volatilité faible = favorable
    "perf": ("ge", 4.0),  # miroir PERF_LABELS (Médiocre < 4 %)
    "potential": ("ge", 5.0),  # miroir POTENTIAL_LABELS
    "quality": ("ge", 55.0),  # miroir QUALITY_LABELS (Moyen < 55)
}

# --- Bêta d'un ratio A/B (sensibilité de A à B, rendements log quotidiens) ----
# β de A (numérateur) sur B (dénominateur/benchmark) : OLS r_a = α + β·r_b.
# Recalculé en live côté front sur la fenêtre du slider (miroir dans app.js).
BETA_MIN_POINTS = 20  # en deçà (rendements dans la fenêtre), β non fiable -> neutre
# β = AMPLITUDE (de combien A bouge quand B bouge). Interprétation NEUTRE ;
# β<0 traité à part ("Inversés"). Échelle défensif (<1) / neutre (~1) / offensif (>1).
BETA_LABELS = [
    (0.25, "Très défensif"),
    (0.75, "Défensif"),
    (1.25, "Neutre"),
    (2.0, "Offensif"),
    (None, "Très offensif"),
]

# --- Corrélation d'un ratio A/B (ρ de Pearson, rendements log quotidiens) -----
# ρ = SOLIDITÉ du lien (à quel point A et B bougent ensemble), bornée [−1, +1].
# Complète β. Recalculée en live sur la fenêtre du slider (miroir dans app.js).
CORR_MIN_POINTS = 20  # en deçà, ρ non fiable -> neutre
# Échelle 5 niveaux sur |ρ| ; suffixe "(inverse)" ajouté si ρ<0. Neutre (pas de couleur).
CORR_LABELS = [
    (0.2, "Très peu corrélés"),
    (0.4, "Peu corrélés"),
    (0.6, "Moyennement corrélés"),
    (0.8, "Fortement corrélés"),
    (None, "Très fortement corrélés"),
]

# Pondérations du score qualité (somme des max = 100).
QUALITY_WEIGHTS = {
    "roe_mean": 40,  # ROE moyen, plafonné à 15 %
    "roe_last": 25,  # ROE dernière année (anti-effondrement)
    "regularity": 20,  # régularité du CA (nb d'années de baisse)
    "balance": 15,  # solidité du bilan (CP / total bilan)
}
QUALITY_ROE_CAP = 15.0  # ROE plafonné à 15 % pour le score

# --- Seuils des ratios fondamentaux étendus ----------------------------------
# Doctrine quality-value (Higgons / Novy-Marx). Chaque entrée :
#   (seuil, sens) où sens="ge" -> bon si valeur >= seuil ; "le" -> bon si <= seuil.
# Pilote la couleur (bleu=bon / rouge=mauvais) côté front. Miroir dans app.js.
# Horizons CAGR (croissance annualisée) : autant que les comptes le permettent.
CAGR_HORIZONS = (3, 5)

RATIO_THRESHOLDS = {
    # Rentabilité & efficience
    "Marge brute": (30.0, "ge"),  # pricing power (marge brute soutenue)
    "Marge opérationnelle": (5.0, "ge"),  # plancher Higgons : pricing power
    "Marge nette": (5.0, "ge"),
    "ROE": (10.0, "ge"),  # seuil minimal Higgons
    "ROA": (5.0, "ge"),
    "ROCE": (15.0, "ge"),  # allocation du capital (cible Higgons)
    "ROIC": (10.0, "ge"),  # rentabilité du capital investi (coût du capital ~)
    "Cash conversion": (100.0, "ge"),  # FCF/RN : >100 % = cash réel >= comptable
    "Agilité": (50.0, "ge"),  # FCF/CAPEX : >50 % = flexibilité financière
    # Solvabilité
    "Dette nette / EBITDA": (2.0, "le"),  # < 2x sain ; >= 4x = profil risqué
    "Gearing": (50.0, "le"),  # DN / CP < 50 % = structure prudente
    "Liquidité": (1.0, "ge"),  # current ratio > 1 = pas de tension CT
    "Couverture des intérêts": (3.0, "ge"),  # < 3x = couverture tendue
    # Valorisation (Palier B)
    "PER": (12.0, "le"),  # achat Higgons < 12 ; vente > 20
    "P/FCF": (10.0, "le"),  # filtre Higgons
    "FCF yield": (8.0, "ge"),  # > 8 % = forte génération vs prix
    # Dividende (Palier B)
    "Taux de distribution": (80.0, "le"),  # > 80 % = dividende peu soutenable
}

# --- Cartes de la section « Quantitatif » ------------------------------------
# TAXONOMIE UNIQUE des graphes de la fiche quantitative. Le front ne décide plus
# quoi afficher : il lit ce plan (via /api/meta) et rend chaque carte.
#
# Principe de lisibilité : une carte par graphe de FLUX (CA, bénéfice, cash,
# CAPEX…), et un graphe multi-lignes par FAMILLE de ratios (Marges, Rentabilités)
# — comparer des ratios de même nature sur un même axe a du sens, superposer des
# flux d'ordres de grandeur différents non. Chaque carte : type ("bars" flux |
# "line" ratios | "shares" actions en circulation | "cagr" croissance annualisée),
# un titre, la ou les métrique(s) source, et — pour les
# ratios — le seuil de couleur (repris de RATIO_THRESHOLDS).
#
# L'axe temporel est HONNÊTE : la largeur du tracé est proportionnelle au nombre
# d'années réellement disponibles (une série de 3 ans n'occupe pas la largeur
# d'une série de 17 ans) et la carte affiche « N ans disponibles ».
QUANT_GROUPS = [
    {
        "title": "Croissance & flux",
        "cards": [
            {"type": "bars", "title": "Chiffre d'affaires", "metrics": ["Chiffre d'affaires"]},
            {"type": "bars", "title": "Bénéfice net", "metrics": ["Bénéfice net"]},
            {"type": "line", "title": "BNPA dilué", "metrics": ["BNPA dilué"]},
            {
                "type": "bars",
                "title": "Génération de cash",
                "metrics": ["Cash-flow d'exploitation", "Free Cash Flow"],
            },
            {"type": "bars", "title": "CAPEX (investissements)", "metrics": ["CAPEX"]},
            {"type": "bars", "title": "SBC (rémunération en actions)", "metrics": ["SBC"]},
            {"type": "cagr", "title": "Croissance annualisée (CAGR)"},
        ],
    },
    {
        "title": "Rentabilité & marges",
        "cards": [
            {
                "type": "line",
                "title": "Marges",
                "metrics": ["Marge brute", "Marge opérationnelle", "Marge nette"],
            },
            {
                "type": "line",
                "title": "Rentabilités (ROE · ROA · ROCE · ROIC)",
                "metrics": ["ROE", "ROA", "ROCE", "ROIC"],
            },
            {"type": "line", "title": "Cash conversion (FCF / RN)", "metrics": ["Cash conversion"]},
            {"type": "line", "title": "Agilité (FCF / CAPEX)", "metrics": ["Agilité"]},
        ],
    },
    {
        "title": "Structure financière",
        "cards": [
            {
                "type": "line",
                "title": "Levier (dette nette / EBITDA)",
                "metrics": ["Dette nette / EBITDA"],
            },
            {
                "type": "line",
                "title": "Gearing (dette nette / capitaux propres)",
                "metrics": ["Gearing"],
            },
            {
                "type": "line",
                "title": "Liquidité (actif / passif circulant)",
                "metrics": ["Liquidité"],
            },
            {
                "type": "line",
                "title": "Couverture des intérêts",
                "metrics": ["Couverture des intérêts"],
            },
            {"type": "bars", "title": "Cash & dette", "metrics": ["Trésorerie", "Dette brute"]},
            {"type": "bars", "title": "Capitaux propres", "metrics": ["Capitaux propres"]},
            {
                "type": "shares",
                "title": "Actions en circulation",
                "metrics": ["Actions en circulation"],
            },
        ],
    },
]

# Unité d'AFFICHAGE par métrique du Quantitatif (pour l'axe Y et les pastilles) :
# "pct" (%) ou "mult" (multiple, ex. 2,47×). Toute métrique absente est un
# montant ("money"). SOURCE UNIQUE : exposée au front par /api/meta
# (`metric_units`) — le JS ne reclassifie plus rien en dur, une métrique
# renommée côté serveur reste correctement formatée.
METRIC_UNITS: dict[str, str] = {
    # Ratios exprimés en pourcentage
    "Marge brute": "pct",
    "Marge opérationnelle": "pct",
    "Marge nette": "pct",
    "ROE": "pct",
    "ROA": "pct",
    "ROCE": "pct",
    "ROIC": "pct",
    "Gearing": "pct",
    "Cash conversion": "pct",
    "Agilité": "pct",
    "FCF yield": "pct",
    "Taux de distribution": "pct",
    "BFR / CA": "pct",
    "Capitaux propres / Total bilan": "pct",
    # Multiples (sans dimension, exprimés en « × »)
    "PER": "mult",
    "P/FCF": "mult",
    "P/CA": "mult",
    "EV / EBITDA": "mult",
    "Price / Book": "mult",
    "Dette nette / EBITDA": "mult",
    "Liquidité": "mult",
    "Couverture des intérêts": "mult",
}

# --- Taxonomie des comptes (document financier CSV par ticker) ---------------
# SOURCE UNIQUE des métriques du tableau des comptes : sert l'export/import CSV
# (`data/manual.py`) ET l'aperçu d'import du front (via `/api/meta`). Aucune
# liste de métriques n'est définie ailleurs.
#
# Chaque entrée : (nom canonique, rôle) où rôle ∈ {"source", "derived"}.
#   - "source"  : poste saisissable par l'utilisateur (colonne ÉDITABLE / réimportée) ;
#   - "derived" : ratio calculé à partir des sources (colonne EN LECTURE SEULE,
#     recalculée par `data.fundamentals` — jamais réimportée).
# L'ORDRE est significatif : il pilote l'ordre des lignes du tableau (source
# d'abord, puis dérivées). Les 7 métriques cœur historiques (CA, Résultat op.,
# Bénéfice net, EBITDA, FCF, Capitaux propres, Dette nette) sont le sous-ensemble
# "source" du schéma INDUSTRIEL : elles maximisent les dérivés.
FUNDAMENTAL_METRICS: tuple[tuple[str, str], ...] = (
    # -- Croissance ----------------------------------------------------------
    ("Chiffre d'affaires", "source"),
    ("Résultat opérationnel", "source"),
    ("Bénéfice net", "source"),
    ("BNPA dilué", "source"),
    ("EBITDA", "source"),
    # -- Rentabilité & marges ------------------------------------------------
    ("Marge brute", "derived"),
    ("Marge opérationnelle", "derived"),
    ("Marge nette", "derived"),
    ("ROE", "derived"),
    ("ROA", "derived"),
    ("ROCE", "derived"),
    ("ROIC", "derived"),
    ("Cash conversion", "derived"),
    ("Agilité", "derived"),
    # -- Solvabilité & structure ---------------------------------------------
    ("Capitaux propres", "source"),
    ("Dette nette", "source"),
    ("Dette brute", "source"),
    ("Trésorerie", "source"),
    ("Actions en circulation", "source"),
    ("BFR (working capital)", "source"),
    ("Capitaux propres / Total bilan", "derived"),
    ("Dette nette / EBITDA", "derived"),
    ("Gearing", "derived"),
    ("Liquidité", "derived"),
    ("Couverture des intérêts", "derived"),
    ("BFR / CA", "derived"),
    # -- Résultat & cash -----------------------------------------------------
    ("Cash-flow d'exploitation", "source"),
    ("Free Cash Flow", "source"),
    ("CAPEX", "source"),
    ("SBC", "source"),
)

# Schéma FINANCIER (banques/assurances) : postes propres, sans CA/marge op.
FINANCIAL_METRICS: tuple[tuple[str, str], ...] = (
    ("Total de l'actif", "source"),
    ("Actif net", "source"),
    ("Bénéfice net", "source"),
    ("ROA", "derived"),
    ("ROE", "derived"),
)

# UNION des deux schémas (ordre stable, sans doublon). Sert la reconnaissance à
# l'import CSV (`data/manual.import_csv`) et l'aperçu d'import du front : le
# schéma d'une valeur (industriel vs financier) n'est PAS connu au moment du
# parsing — on accepte donc l'union (l'export, lui, reste piloté par le tableau
# réel de la valeur, donc par le bon schéma).
FUNDAMENTAL_METRICS_ALL: tuple[tuple[str, str], ...] = tuple(
    dict.fromkeys((*FUNDAMENTAL_METRICS, *FINANCIAL_METRICS))
)

# --- Synthèse fondamentale (section Résumé) ----------------------------------
# Grille de lecture rapide : identité, marché, multiples, croissance, marges,
# rentabilité, santé. Tous les seuils ci-dessous sont la SOURCE UNIQUE (exposés
# au front par /api/meta) : aucun nombre magique dans la grille côté client.

# Catégories de capitalisation : borne INF incluse, décroissante (la première
# franchie gagne). Seuils de la spec `amélioration/…/company-summary.md`.
MARKET_CAP_LABELS = [
    (10_000_000_000, "Large Cap"),
    (2_000_000_000, "Mid Cap"),
    (0, "Small Cap"),
]

# Horizons de croissance de la synthèse (CA, BNPA, dividende) : 1 an = variation
# simple (YoY) ; au-delà = CAGR. Un horizon non couvert par l'historique (ou les
# données manuelles) reste absent -> « -- », jamais extrapolé.
SUMMARY_GROWTH_HORIZONS = (1, 5, 10)

# Zones Altman Z-Score (modèle manufacturier) : borne INF incluse. Le modèle ne
# s'applique PAS aux financières (banques/assurances) -> non calculé.
ALTMAN_ZONES = [
    (2.99, "Sain"),
    (1.81, "Zone grise"),
    (None, "Détresse"),
]
ALTMAN_SAFE_MIN = 2.99  # >= : zone saine
ALTMAN_DISTRESS_MAX = 1.81  # < : zone de détresse

# Zones Piotroski F-Score (0-9) : borne INF incluse. Non calculé pour les
# financières (postes de bilan non comparables).
PIOTROSKI_ZONES = [
    (7, "Solide"),
    (4, "Correct"),
    (0, "Fragile"),
]
PIOTROSKI_MAX = 9

# Note affichée (infobulle) quand un modèle de santé n'est pas applicable.
FINANCIAL_NOT_APPLICABLE = "Non applicable aux financières"

# Polarité couleur des lignes de la synthèse (bleu = bon), même convention que
# SCREEN_COLORS : "ge" (plus = mieux), "le" (moins = mieux), "le_pos"
# (strictement positif et <= seuil). SEULE source des couleurs de la grille.
SUMMARY_COLORS: dict[str, tuple[str, float | None]] = {
    # Santé / solvabilité
    "net_debt_ebitda": ("le", 2.0),  # miroir RATIO_THRESHOLDS
    "interest_coverage": ("ge", 3.0),  # < 3x : couverture tendue
    "goodwill_assets": ("le", 30.0),  # goodwill lourd = risque de dépréciation
    "shares_change_3y": ("le", 0.0),  # <= 0 = rachats (bleu) ; > 0 = dilution
    "altman_z": ("ge", ALTMAN_DISTRESS_MAX),  # au-dessus de la détresse
    "piotroski": ("ge", 7.0),  # miroir PIOTROSKI_ZONES
    # Rentabilité
    "roe_1y": ("ge", 10.0),  # miroir RATIO_THRESHOLDS (dernier exercice)
    "roce_1y": ("ge", 15.0),
    "roic_1y": ("ge", 10.0),
    "roe_5y": ("ge", 10.0),  # miroir RATIO_THRESHOLDS
    "roce_5y": ("ge", 15.0),  # miroir RATIO_THRESHOLDS
    "roic_5y": ("ge", 10.0),  # coût du capital approximatif
    # Marges
    "gross_margin": ("ge", 30.0),
    "op_margin": ("ge", 5.0),  # miroir RATIO_THRESHOLDS
    "net_margin": ("ge", 5.0),
    "fcf_margin": ("ge", 5.0),
    # CAPEX / CA volontairement ABSENT : l'intensité capitalistique n'est ni
    # bonne ni mauvaise en soi (elle dépend du secteur) -> ligne neutre assumée.
    # Multiples (miroir RATIO_THRESHOLDS, multiples strictement positifs)
    "per": ("le_pos", 12.0),
    "forward_per": ("le_pos", 12.0),
    "p_fcf": ("le_pos", 10.0),
    "p_ocf": ("le_pos", 10.0),
    "p_s": ("le_pos", 2.0),
    "p_b": ("le_pos", 1.5),
    # Dividende
    "div_yield": ("ge", 3.0),
    "payout_fy": ("le", 80.0),  # miroir RATIO_THRESHOLDS
    "div_growth_years": ("ge", 5.0),  # régularité de la hausse
    # Croissances (toutes : positif = bleu)
    "div_cagr_1y": ("ge", 0.0),
    "div_cagr_5y": ("ge", 0.0),
    "div_cagr_10y": ("ge", 0.0),
    "rev_growth_1y": ("ge", 0.0),
    "rev_cagr_5y": ("ge", 0.0),
    "rev_cagr_10y": ("ge", 0.0),
    "eps_growth_1y": ("ge", 0.0),
    "eps_cagr_5y": ("ge", 0.0),
    "eps_cagr_10y": ("ge", 0.0),
    "rev_future": ("ge", 0.0),  # consensus analystes
    "eps_future": ("ge", 0.0),  # consensus analystes
    # Note quantitative /20 : miroir de LABEL_POLARITY["quality"] (55/100 → 11/20),
    # car la ligne affiche le score ramené sur 20.
    "quality_score": ("ge", 11.0),
}

# --- Section « Dividende » ---------------------------------------------------
# TAXONOMIE UNIQUE des cartes de la section Dividende (même principe que
# QUANT_GROUPS) : le front ne décide plus quoi afficher, il lit ce plan via
# /api/meta. Types : "yield" (courbe continue de rendement), "divbars" (barres
# du dividende par action), "divgrowth" (barres de croissance YoY), "lines"
# (multi-lignes de ratios), "stacked" (barres empilées dividendes + rachats),
# "kpi" (bandeau de chiffres sans graphe).
DIVIDEND_GROUPS = [
    {
        "title": "Rendement",
        "cards": [
            # Dividend Yield = carte mise en avant (pleine largeur, hauteur héro de
            # section). Les autres cartes restent en colonne simple (2 par ligne,
            # comme le Quantitatif) : le front ne décide pas, il lit `wide`.
            {"type": "yield", "title": "Dividend Yield", "series": "div_yield", "wide": True},
            {"type": "kpi", "title": "Métriques clés"},
            {"type": "yield", "title": "Shareholder Yield", "series": "sh_yield"},
        ],
    },
    {
        "title": "Dividende par action",
        "cards": [
            {"type": "divbars", "title": "Dividende / Action"},
            {"type": "divgrowth", "title": "Croissance Dividende / Action"},
        ],
    },
    {
        "title": "Payout",
        "cards": [
            {
                "type": "lines",
                "title": "Payout Ratios",
                "metrics": ["Earnings Payout Ratio", "FCF Payout Ratio"],
            },
            {
                "type": "lines",
                "title": "Shareholder Payout Ratios",
                "metrics": [
                    "Earnings Shareholder Payout Ratio",
                    "FCF Shareholder Payout Ratio",
                ],
            },
        ],
    },
    {
        "title": "Retour à l'actionnaire",
        "cards": [
            {
                "type": "stacked",
                "title": "Shareholder Returns",
                "metrics": ["Dividendes versés", "Rachats d'actions"],
            },
        ],
    },
]

# Unités d'affichage des métriques de la section Dividende (source unique,
# exposée par /api/meta via `metric_units`). Toute métrique absente = montant.
DIVIDEND_METRIC_UNITS: dict[str, str] = {
    "Earnings Payout Ratio": "pct",
    "FCF Payout Ratio": "pct",
    "Earnings Shareholder Payout Ratio": "pct",
    "FCF Shareholder Payout Ratio": "pct",
    "Dividendes versés": "money",
    "Rachats d'actions": "money",
}

# Polarité couleur des métriques de la section Dividende (bleu = bon). Même
# convention que RATIO_THRESHOLDS : "ge" (plus = mieux), "le" (moins = mieux).
# Un payout > 80 % signale un dividende peu soutenable ; un rendement élevé est
# favorable. Le rendement continu est coloré sur sa MÉDIANE de fenêtre.
DIVIDEND_COLORS: dict[str, tuple[str, float | None]] = {
    # Polarité des RATIOS de distribution (seule famille réellement colorée par
    # cette table : pastilles de « Payout Ratios » et KPI « Payout (TTM) »).
    # Les pastilles High/Médiane/Low des courbes de rendement ont leur propre
    # sémantique (max = favorable, min = défavorable) et ne passent pas par ici ;
    # les montants (dividendes versés, rachats) sont neutres par nature.
    "Earnings Payout Ratio": ("le", 80.0),
    "FCF Payout Ratio": ("le", 80.0),
    "Earnings Shareholder Payout Ratio": ("le", 100.0),
    "FCF Shareholder Payout Ratio": ("le", 100.0),
}

# Polarité couleur des métriques agrégées de la Performance (#17.4) : SOURCE
# UNIQUE des seuils. Miroir ASSUMÉ des seuils déjà calibrés ailleurs
# (`RATIO_THRESHOLDS`, `SUMMARY_COLORS`, `LABEL_POLARITY`) : on reprend la valeur
# de la méthode au même endroit plutôt que d'ouvrir une seconde vérité — un seul
# point à ajuster si un seuil calibré bouge. Le dict vit APRÈS ses sources
# (labels/ratio/summary) car il les lit.
#   - `sens` ∈ {"ge", "le", "le_pos"} ; "le_pos" neutralise les valeurs nulles ou
#     négatives (un P/E ≤ 0 n'est pas interprétable -> « -- », jamais un nombre) ;
#   - une clé absente = métrique neutre (jamais de couleur).
PORTFOLIO_STAT_POLARITY: dict[str, tuple[str, float | None]] = {
    "quality": ("ge", LABEL_POLARITY["quality"][1]),
    "gross_margin": ("ge", RATIO_THRESHOLDS["Marge brute"][0]),
    "op_margin": ("ge", RATIO_THRESHOLDS["Marge opérationnelle"][0]),
    "net_margin": ("ge", RATIO_THRESHOLDS["Marge nette"][0]),
    "roe": ("ge", RATIO_THRESHOLDS["ROE"][0]),
    "roce": ("ge", RATIO_THRESHOLDS["ROCE"][0]),
    "roic": ("ge", RATIO_THRESHOLDS["ROIC"][0]),
    "net_debt_ebitda": ("le", RATIO_THRESHOLDS["Dette nette / EBITDA"][0]),
    "piotroski": ("ge", SUMMARY_COLORS["piotroski"][1]),
    "altman_z": ("ge", SUMMARY_COLORS["altman_z"][1]),
    "agility": ("ge", RATIO_THRESHOLDS["Agilité"][0]),
    "per": ("le_pos", RATIO_THRESHOLDS["PER"][0]),
    "p_fcf": ("le_pos", RATIO_THRESHOLDS["P/FCF"][0]),
    "p_b": ("le_pos", SUMMARY_COLORS["p_b"][1]),
    "slope": ("ge", 0.0),
    "pot_5y": ("ge", 0.0),
    "pot_10y": ("ge", 0.0),
}

# --- Section Dividende du PORTEFEUILLE (#17.5) --------------------------------
# Taxonomie UNIQUE des tuiles KPI de l'onglet Dividende (même principe que
# `PORTFOLIO_STAT_GROUPS`) : le service produit un dict {clé: {value, good}}, le
# front rend ces tuiles dans cet ordre, sans libellé ni seuil en dur.
#   l'unité d'affichage n'est PAS portée ici : elle vit dans
#   `PORTFOLIO_DIVIDEND_METRIC_UNITS` (une seule source, exposée par /api/meta) ;
#   `signed: True` marque une VARIATION (CAGR, contribution) : le front préfixe
#   les valeurs positives d'un « + ». Absent = un NIVEAU.
#   `coverage_of` : le taux de couverture associé, affiché en SOUS-TEXTE de la
#   tuile (jamais en tuile séparée) — sans lui le ratio mentirait par omission.
PORTFOLIO_DIVIDEND_GROUPS = [
    {
        "id": "rendement",
        "metrics": [
            {
                "key": "yield_pct",
                "label": "Yield portefeuille",
                "sub": "dividendes / valeur de marché",
            },
            {
                "key": "yield_on_cost_pct",
                "label": "Yield on cost",
                "sub": "rendement TTM / prix payé",
            },
            {
                "key": "payout_pct",
                "label": "Payout agrégé",
                "sub": "dividendes / bénéfices",
                "coverage_of": "payout_coverage_pct",
            },
            {
                "key": "shareholder_yield_pct",
                "label": "Shareholder yield",
                "sub": "dividendes + rachats",
                "coverage_of": "shareholder_coverage_pct",
            },
        ],
    },
    {
        "id": "revenu",
        "metrics": [
            {
                "key": "ttm_income",
                "label": "Revenu TTM",
                "sub_of": "total_income",
            },
            {"key": "cagr_pct", "label": "Croissance 5 ans", "signed": True},
            {
                "key": "dividend_contribution_pct",
                "label": "Part dans la perf",
                "signed": True,
                "sub": "TWR avec / sans dividende",
            },
            {
                "key": "yield_coverage_pct",
                "label": "Couverture données",
                "sub": "part de la valeur avec DPA connu",
            },
        ],
    },
]

# Polarité couleur des KPI de dividende du portefeuille : source unique des
# seuils, même convention que `PORTFOLIO_STAT_POLARITY` ("ge" = plus = mieux).
PORTFOLIO_DIVIDEND_POLARITY: dict[str, tuple[str, float | None]] = {
    # Un payout élevé signale un dividende peu soutenable (même seuil que la
    # section Dividende de la fiche : `DIVIDEND_COLORS`, lu ici et non recopié).
    "payout_pct": ("le", DIVIDEND_COLORS["Earnings Payout Ratio"][1]),
    "cagr_pct": ("ge", 0.0),
    "dividend_contribution_pct": ("ge", 0.0),
}

# Unités d'affichage des KPI de dividende du portefeuille ("pt" = points de
# pourcentage d'une contribution annualisée, signée).
PORTFOLIO_DIVIDEND_METRIC_UNITS: dict[str, str] = {
    "yield_pct": "pct",
    "yield_on_cost_pct": "pct",
    "payout_pct": "pct",
    "shareholder_yield_pct": "pct",
    "yield_coverage_pct": "pct",
    "payout_coverage_pct": "pct",
    "shareholder_coverage_pct": "pct",
    "cagr_pct": "pct",
    "dividend_contribution_pct": "pt",
    "twr_with_dividends_pct": "pct",
    "twr_without_dividends_pct": "pct",
    "ttm_income": "money",
    "total_income": "money",
}

# Échelle (points de %) de la micro-barre divergente de la colonne « Écart » du
# tableau Dividende (#17.5) : un écart de cette amplitude remplit la demi-barre.
# Purement visuel, mais SOURCE UNIQUE côté serveur (aucun seuil littéral en JS).
PORTFOLIO_DIVIDEND_GAP_SCALE_PP = 10.0

# Fréquence de versement : fenêtre d'observation et seuils (nb de versements
# sur ~12 mois -> libellé). yfinance n'expose pas la fréquence : on la déduit.
# SOURCE UNIQUE servie par /api/meta (`dividend_frequency_*`) — le front ne
# redéfinit ni la fenêtre ni les seuils.
DIVIDEND_FREQUENCY_WINDOW_DAYS = 366
DIVIDEND_FREQUENCY_LABELS = [
    (4, "Trimestriel"),
    (2, "Semestriel"),
    (1, "Annuel"),
]

# Horizons de croissance du dividende affichés dans la carte « Métriques clés »
# (CAGR du dividende par action). SOURCE UNIQUE servie par /api/meta.
DIVIDEND_CAGR_HORIZONS = (5, 10)

# Fenêtre par défaut des séries LONGUES de la section Dividende (cours de
# rendement continu, dividende par action, croissance) : on n'affiche que les
# dernières années par défaut (le zoom sert à explorer plus loin). Règle :
# `years` si l'historique le permet, sinon 5, sinon tout l'historique.
# SOURCE UNIQUE servie par /api/meta (`dividend_default_window_years`).
DIVIDEND_DEFAULT_WINDOW_YEARS = 10
DIVIDEND_MIN_WINDOW_YEARS = 5

# --- Section « Valorisation » : calculatrice de prix juste --------------------
# Modèle de rendement estimé, VALIDÉ par rétro-ingénierie de la matrice Baggr
# (fit au 0,01 pt sur 45 cellules) :
#
#     R(g, m) = (1 + g) × (m / m0)^(1/H) − 1 + D
#
# H = horizon de projection (années), m0 = multiple COURANT, D = rendement du
# dividende (0 quand la case « Inclure les dividendes » est décochée).
# Équivalent à (Valeur projetée / Cours)^(1/H) − 1 + D.
VALUATION_HORIZON_YEARS = 5

# Rendement cible par défaut (%/an) : c'est le BENCHMARK que l'utilisateur se
# fixe. Le rendement estimé est comparé à cette cible (on la bat ou pas) et
# l'échelle de couleur de la matrice s'y accroche (vert dès la cible).
VALUATION_TARGET_YIELD_DEFAULT = 12.0

# Périodes historiques proposées (fenêtre du multiple médian et du CAGR).
VALUATION_PERIODS = (5, 10, 15, 20)
VALUATION_PERIOD_DEFAULT = 10


# Bases de valorisation de la calculatrice. Chaque entrée :
#   key      : identifiant stable (front + persistance)
#   label    : libellé du menu « Données utilisées »
#   metric   : ligne du tableau de comptes (par action ou totale selon `per_share`)
#   multiple : ligne de `fundamentals.valuation` (multiple associé)
#   per_share: la ligne est-elle déjà par action ?
#   enterprise: multiple d'entreprise (EV/EBITDA) — la valeur par action est
#             obtenue en retranchant la dette nette par action (bridge EV->cap).
#   unit     : unité d'affichage de la série continue ("money" | "mult")
#   multiple_step: pas des colonnes de la matrice pour cette base. Un multiple de
#             capitalisation qui vaut ~1 (P/CA, P/B) exige un pas fin (0,1–0,2) ;
#             un multiple à deux chiffres (PER, P/FCF, EV/EBITDA) garde un pas de
#             1. Le repli global reste `VALUATION_MATRIX_MULTIPLE_STEP`.
class ValuationMetricSpec(TypedDict):
    """Contrat d'une base de valorisation de la calculatrice (cf. `VALUATION_METRICS`)."""

    key: str
    label: str
    metric: str
    multiple: str
    per_share: bool
    enterprise: bool
    unit: str
    multiple_step: float


VALUATION_METRICS: list[ValuationMetricSpec] = [
    {
        "key": "eps",
        "label": "Bénéfices/Actions",
        "metric": "BNPA dilué",
        "multiple": "PER",
        "per_share": True,
        "enterprise": False,
        "unit": "money",
        "multiple_step": 1.0,
    },
    {
        "key": "fcf",
        "label": "Free Cash Flow/Action",
        "metric": "Free Cash Flow",
        "multiple": "P/FCF",
        "per_share": False,
        "enterprise": False,
        "unit": "money",
        "multiple_step": 1.0,
    },
    {
        "key": "sales",
        "label": "Chiffre d'affaires/Action",
        "metric": "Chiffre d'affaires",
        "multiple": "P/CA",
        "per_share": False,
        "enterprise": False,
        "unit": "money",
        "multiple_step": 0.1,
    },
    {
        "key": "book",
        "label": "Actif net/Action",
        "metric": "Capitaux propres",
        "multiple": "Price / Book",
        "per_share": False,
        "enterprise": False,
        "unit": "money",
        "multiple_step": 0.2,
    },
    {
        "key": "ebitda",
        "label": "EBITDA",
        "metric": "EBITDA",
        "multiple": "EV / EBITDA",
        "per_share": False,
        "enterprise": True,
        "unit": "money",
        "multiple_step": 1.0,
    },
]

# Grille de la matrice : nombre de lignes (croissance) et de colonnes (multiple),
# centrées sur les valeurs courantes, avec leur pas. Le front génère la grille à
# partir de ces constantes (aucun pas littéral côté JS).
VALUATION_MATRIX_ROWS = 15
VALUATION_MATRIX_COLS = 15
VALUATION_MATRIX_GROWTH_STEP = 0.5  # points de %/an
VALUATION_MATRIX_MULTIPLE_STEP = 1.0  # points de multiple

# Échelle de couleur de la matrice, ANCRÉE SUR LA CIBLE : les bornes sont des
# fractions du rendement cible. < 0 = rouge brique (négatif) ; [0, 0.5·cible[ =
# brun/orange ; [0.5·cible, cible[ = jaune/ocre ; >= cible = vert. Un changement
# de cible re-colore toute la matrice sans toucher au JS.
VALUATION_COLOR_RATIOS = (0.5, 1.0)

# Cartes de la partie 2 de la section Valorisation : COURBES CONTINUES (jamais
# de barres, patron du Dividend Yield — série pleine résolution décimée serveur,
# alignée sur `chart.dates`). Types : "vline" (courbe continue + pastilles de
# fenêtre). `pills` (au niveau du GROUPE) choisit la pastille : "cagr" = croissance
# annualisée de la métrique sur la fenêtre affichée (groupes de croissance) ;
# absent = High/Médiane/Low (groupes de multiples). Les `series` sont les clés du
# payload `chart`.
VALUATION_GROUPS = [
    {
        "title": "Croissance",
        "pills": "cagr",
        "cards": [
            {"type": "vline", "title": "BNPA par action", "series": "eps_ps", "unit": "money"},
            {"type": "vline", "title": "FCF par action", "series": "fcf_ps", "unit": "money"},
            {"type": "vline", "title": "CA par action", "series": "sales_ps", "unit": "money"},
            {
                "type": "vline",
                "title": "Actif net par action",
                "series": "book_ps",
                "unit": "money",
            },
        ],
    },
    {
        "title": "Valorisation",
        "cards": [
            {"type": "vline", "title": "P/E", "series": "per", "unit": "mult"},
            {"type": "vline", "title": "P/FCF", "series": "p_fcf", "unit": "mult"},
            {"type": "vline", "title": "P/CA", "series": "p_s", "unit": "mult"},
            {"type": "vline", "title": "P/B", "series": "p_b", "unit": "mult"},
            {"type": "vline", "title": "EV/EBITDA", "series": "ev_ebitda", "unit": "mult"},
        ],
    },
]

# --- Hauteurs de graphiques (standard UI) ------------------------------------
# SOURCE UNIQUE des hauteurs de tracé, servie par /api/meta : le CSS et le layout
# Plotly doivent coïncider, et aucune valeur ne doit être écrite en dur côté JS.
# `HERO` = graphe principal (section Résumé) ; `MINI` = cartes secondaires (même
# hauteur dans toutes les sections, y compris le Quantitatif) ; `DIVIDEND_HERO` =
# carte Dividend Yield mise en avant (pleine largeur) dans la section Dividende ;
# `DETAIL` = modale de zoom plein écran.
CHART_HEIGHT_HERO = 440
CHART_HEIGHT_MINI = 200
CHART_HEIGHT_DIVIDEND_HERO = 300  # carte Dividend Yield (héro de la section Dividende)
CHART_HEIGHT_VALUATION_HERO = 560  # graphe de la calculatrice de prix juste (héro de section)
CHART_HEIGHT_PORTFOLIO_RESUME = 360  # courbe TWR du portefeuille (carte Résumé)
CHART_HEIGHT_PORTFOLIO_DONUT = 320  # donut de répartition des comptes (carte Résumé)
CHART_HEIGHT_PORTFOLIO_DRAWDOWN = 300  # courbe de drawdown (section Risque)
CHART_HEIGHT_PORTFOLIO_CORR = 460  # heatmap de corrélation (section Risque)
CHART_HEIGHT_PORTFOLIO_CORR_TEST = 110  # ligne du test de corrélation (section Risque)
CHART_HEIGHT_PORTFOLIO_MONTHLY = 300  # barres des rendements mensuels (Performance)
CHART_HEIGHT_PORTFOLIO_CONTRIB = 300  # barres de contribution par entreprise (Performance)
CHART_HEIGHT_PORTFOLIO_DIVIDENDS = (
    300  # barres mensuelles des dividendes reçus (héros section Dividende)
)
CHART_HEIGHT_PORTFOLIO_DIV_CONC = (
    300  # hauteur MINIMALE des barres de concentration du revenu (section Dividende)
)
# La concentration affiche une barre PAR PAYEUR : sa hauteur réelle est
# `nb_payeurs × ROW + PAD`, sinon le tracé déborde de la carte dès ~7 payeurs.
CHART_HEIGHT_PORTFOLIO_DIV_CONC_ROW = 34  # hauteur d'une barre + son espacement
CHART_HEIGHT_PORTFOLIO_DIV_CONC_PAD = 40  # marges haute et basse du tracé
CHART_HEIGHT_DETAIL = 420  # modale de zoom plein écran

# --- Recherche : priorité des bourses principales (vs OTC/pink sheets) ------
# Plus l'indice est petit, plus l'exchange est prioritaire dans les suggestions.
EXCHANGE_PRIORITY = ["PAR", "NMS", "NYQ", "NGM", "LSE", "GER", "AMS", "MIL", "MCE"]

# --- Détection type d'entreprise (schéma de comptes) -------------------------
FINANCIAL_SECTORS = {"Financial Services", "Banques", "Banks", "Insurance", "Assurance"}

# --- Screener : univers français (J1) ---------------------------------------
# Univers FR de CONFIANCE (CAC 40 + grandes valeurs Euronext Paris, tickers
# .PA validés) : sert de base sûre et de fallback quand Yahoo casse. Éditable.
UNIVERSE_FR = [
    "AIR.PA",
    "AI.PA",
    "RI.PA",
    "OR.PA",
    "SAN.PA",
    "CS.PA",
    "KER.PA",
    "LR.PA",
    "AC.PA",
    "VIV.PA",
    "VK.PA",
    "EL.PA",
    "GLE.PA",
    "SU.PA",
    "EN.PA",
    "TEP.PA",
    "VIL.PA",
    "BNP.PA",
    "TTE.PA",
    "STLAP.PA",
    "ML.PA",
    "BIM.PA",
    "SPIE.PA",
    "AF.PA",
    "UBI.PA",
    "ORA.PA",
    "SK.PA",
    "MC.PA",
]
# Région(s) Yahoo de la France pour l'API screener (`eq`).
FR_REGIONS = ["fr"]
# Bourse(s) Euronext Paris (le filtre région seul ramène du bruit : warrants,
# ETP, OTC ; l'exchange PAR restreint au marché principal).
FR_EXCHANGES = ["PAR"]
# TTL du cache univers (cohérent avec TTL_PRICES : on ne re-screen pas en intra-journée).
TTL_UNIVERSE = 24 * 3600
# Taille de page max de l'API screener Yahoo (limite réelle : 250).
SCREEN_PAGE_SIZE = 250
# Workers du scan screener (ThreadPool, I/O-bound). Borné pour ne pas déclencher
# le rate-limit Yahoo. À ajuster au premier scan réel (note J5).
SCREEN_WORKERS = 8
# Budget GLOBAL (s) = SCREEN_WORKERS × ce facteur : filet anti-scan-infini.
# PAS une limite par ticker — les threads déjà lancés ne sont pas préemptables ;
# à l'expiration, les tickers non-aboutis sont isolés en `error="timeout"` et le
# pool est arrêté sans attendre (scan borne l'HTTP, pas chaque thread).
SCREEN_FETCH_TIMEOUT = 20
# Capi minimale par défaut du scan (décision J2 : « scan rapide »). L'utilisateur
# peut passer `min_market_cap` explicite (None = univers complet).
SCREEN_DEFAULT_MIN_CAP = 1_000_000_000
# Direction de tri « bon premier » par critère, SOURCE UNIQUE : True = décroissant
# (plus = mieux), False = croissant (moins = mieux). Consommée par
# `engine.screen.DEFAULT_SORT_ORDER` (aucun doublon) et exposée au front par l'API.
SCREEN_SORT_DESC: dict[str, bool] = {
    "z": False,  # z faible = décoté -> croissant (les plus décotés en premier)
    "pente_pct": True,
    "pot_5y_pct": True,
    "pot_10y_pct": True,
    "roe_pct": True,
    "fcf_yield_pct": True,
    "quality_score": True,
    "market_cap": True,
    "per": False,
    "p_b": False,
    "p_fcf": False,
    "ecart_type_pct": False,
    "trend_bullish": True,  # Haussière (True) avant Baissière
}
# Polarité « couleur » (bleu = bon) d'un critère screener : (sens, seuil).
#   sens "ge"      : bon si valeur >= seuil  (plus = mieux)
#   sens "le"      : bon si valeur <= seuil  (moins = mieux)
#   sens "le_pos"  : bon si 0 < valeur <= seuil (multiple strictement positif)
# SEULE source de vérité des couleurs du tableau : les seuils sont ceux déjà
# calibrés (labels + RATIO_THRESHOLDS), PAS de valeur magique côté client.
SCREEN_COLORS: dict[str, tuple[str, float | None]] = {
    "z": ("le", 0.0),  # z <= 0 -> décoté
    "pente_pct": ("ge", 4.0),  # miroir PERF_LABELS (Médiocre < 4 %)
    "ecart_type_pct": ("le", 35.0),  # miroir ECART_TYPE_LABELS (Moyen < 35 %)
    "pot_5y_pct": ("ge", 5.0),  # miroir POTENTIAL_LABELS
    "pot_10y_pct": ("ge", 5.0),
    "trend_bullish": ("ge", 0.0),  # True (haussière) >= 0 -> bon
    "roe_pct": ("ge", 10.0),  # miroir RATIO_THRESHOLDS["ROE"]
    "per": ("le_pos", 12.0),  # miroir RATIO_THRESHOLDS["PER"] : positif <= 12
    "p_b": ("ge", 0.0),  # P/B > 0 = fonds propres positifs ; <= 0 -> mauvais
    "p_fcf": ("le_pos", 10.0),  # miroir RATIO_THRESHOLDS["P/FCF"] : positif <= 10
    "fcf_yield_pct": ("ge", 8.0),  # miroir RATIO_THRESHOLDS["FCF yield"]
    "quality_score": ("ge", 55.0),  # miroir QUALITY_LABELS (Moyen < 55)
}
# Marqueurs (insensibles à la casse) pour exclure les non-actions du résultat
# dynamique : ETP/trackers physiques (WisdomTree, CoinShares…), obligations
# (coupon « % » / échéance)… Les vraies actions n'en ont pas dans leur nom.
SCREEN_EXCLUDE_MARKERS = [
    " etp",
    "physical",
    "wisdomtree",
    "coinbase",
    "tracker",
    "wrapped",
    "wheat",
    "vix",
    "%",
]

# --- Charte couleur (sémantique bleu=bien / rouge=mal, PRD §8) ---------------
COLOR_BG = "#F7F8FA"
COLOR_CARD = "#FFFFFF"
COLOR_BORDER = "#E5E7EB"
COLOR_ACCENT = "#2563EB"  # accent UI + courbe du cours
COLOR_GOOD = "#2563EB"  # signal positif (bleu)
COLOR_GOOD_BG = "#EFF6FF"
COLOR_BAD = "#DC2626"  # signal négatif (rouge)
COLOR_BAD_BG = "#FEF2F2"
COLOR_NEUTRAL = "#6B7280"
