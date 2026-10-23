"""Données fondamentales saisies manuellement par l'utilisateur.

Permet d'étendre l'historique des comptes au-delà des ~4-5 ans de yfinance.
Les données survivent au refresh (table séparée du cache TTL).
Fusionnées avec yfinance dans fundamentals.build_table via merge_manual().

Le CSV n'est plus limité à 7 métriques : il couvre **toutes** les colonnes du
tableau des comptes (postes source éditables + ratios dérivés en lecture seule).
La taxonomie vient de `config.FUNDAMENTAL_METRICS` (source unique) — aucune
métrique n'est listée en dur ici.

Un CSV vient de l'extérieur (Excel FR, export courtier, collage de tableau) : le
format n'est jamais garanti. `import_csv` détecte donc le **délimiteur** et
normalise les **nombres** (virgule décimale, séparateurs de milliers, devise,
parenthèses négatives), et renvoie un **rapport** : ce qui a été accepté, ce qui
a écrasé une valeur existante, et ce qui a été rejeté **avec la raison**.
"""

from __future__ import annotations

import csv
import io

from obole import config
from obole.data import cache
from obole.models import ImportRejection, ImportReport

# Colonnes ÉDITABLES du CSV : postes source saisis par l'utilisateur, réimportés.
# Ordre = celui de la taxonomie INDUSTRIELLE `config.FUNDAMENTAL_METRICS`. La
# reconnaissance à l'import (`import_csv`) couvre l'UNION des deux schémas, pour
# accepter aussi le template d'une financière (Total de l'actif, Actif net…).
SOURCE_METRICS = [name for name, role in config.FUNDAMENTAL_METRICS if role == "source"]

# Colonnes EN LECTURE SEULE : ratios dérivés, recalculés par `data.fundamentals`
# (`merge_manual`) — jamais réimportés (un import ne fait pas foi sur un dérivé).
DERIVED_METRICS = [name for name, role in config.FUNDAMENTAL_METRICS if role == "derived"]

# Ordre des colonnes du CSV : les postes source d'abord (éditables), puis les
# dérivés (lecture seule). Le `year` est ajouté en tête à l'export.
CSV_METRICS = SOURCE_METRICS + DERIVED_METRICS

# Garde-fou de cohérence : la taxonomie ne décrit que deux rôles.
assert set(role for _name, role in config.FUNDAMENTAL_METRICS_ALL) <= {"source", "derived"}


def get_manual(ticker: str) -> list[dict]:
    """Toutes les entrées manuelles d'un ticker."""
    return cache.get_manual(ticker)


def get_manual_dict(ticker: str) -> dict[int, dict[str, float]]:
    """Entrées manuelles structurées en {année: {métrique: valeur}}."""
    entries = cache.get_manual(ticker)
    out: dict[int, dict[str, float]] = {}
    for e in entries:
        year = int(e["year"])
        if year not in out:
            out[year] = {}
        out[year][e["metric"]] = e["value"]
    return out


def upsert_manual(ticker: str, entries: list[dict]) -> None:
    """Ajoute ou remplace des entrées manuelles (batch JSON).

    Chaque entrée : {"year": int, "metric": str, "value": float}
    Les métriques de type « source » (cf. `config.FUNDAMENTAL_METRICS`) sont les
    seules réellement recomposables ; une valeur hors de ces postes est conservée
    mais ne participe pas à la dérivation des ratios.
    """
    cache.put_manual(ticker, entries)


def delete_manual_year(ticker: str, year: int) -> None:
    """Supprime une année de données manuelles."""
    cache.delete_manual_year(ticker, year)


def delete_manual(ticker: str) -> None:
    """Supprime toutes les données manuelles d'un ticker."""
    cache.delete_manual(ticker)


def export_csv(
    ticker: str,
    yfinance_years: list[int] | None = None,
    manual_override: dict[int, dict[str, float]] | None = None,
    metrics: list[str] | None = None,
) -> str:
    """Génère un CSV exhaustif pré-rempli (données yfinance + manuelles).

    `metrics` : colonnes à exporter (défaut `CSV_METRICS` = postes source +
    dérivés). Les valeurs manquantes pour une année restent des cellules vides.

    `yfinance_years` : plage d'années couverte (colonnes du tableau), pré-remplie.
    `manual_override` : source pré-remplie (yfinance + manuel) ; sinon les seules
    données manuelles du ticker. Le template va de min(all_years) à max(all_years).
    """
    manual = manual_override if manual_override is not None else get_manual_dict(ticker)
    cols = metrics if metrics is not None else CSV_METRICS

    all_years: set[int] = set(manual.keys())
    if yfinance_years:
        all_years.update(yfinance_years)
    if not all_years:
        return ""

    min_year = min(all_years)
    max_year = max(all_years)
    years = list(range(max_year, min_year - 1, -1))

    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["year", *cols])

    for y in years:
        yr_manual = manual.get(y, {})
        row: list[str | float | None] = [y]
        for m in cols:
            row.append(yr_manual.get(m) if m in yr_manual else None)
        w.writerow(row)

    return out.getvalue()


def _normalize_header(name: str) -> str:
    """Clé de rapprochement d'une colonne : sans espaces superflus, minuscule."""
    return name.strip().casefold()


# Délimiteurs candidats d'un CSV « venu de l'extérieur » : virgule (norme),
# point-virgule (Excel FR), tabulation (copier-coller d'un tableur).
_DELIMITERS = (",", ";", "\t")

# Séparateurs de milliers à retirer avant conversion : espace ordinaire, espace
# insécable (U+00A0, Excel FR), espace fine insécable (U+202F), apostrophe
# suisse/allemande. La virgule et le point sont traités séparément (décimale).
_THOUSANDS_CHARS = " \u00a0\u202f'’"


def _detect_delimiter(content: str) -> str:
    """Choisit le délimiteur de colonnes de la première ligne non vide.

    Le plus fréquent gagne (`;` d'Excel FR, tabulation d'un collage de tableau,
    virgule par défaut). Le comptage se fait sur la ligne d'en-tête uniquement :
    une valeur entre guillemets contenant un autre délimiteur pourrait fausser un
    comptage global, jamais une en-tête. Repli sur la virgule (norme CSV).
    """
    for line in content.splitlines():
        if line.strip():
            counts = {d: line.count(d) for d in _DELIMITERS}
            best = max(counts, key=lambda d: (counts[d], -_DELIMITERS.index(d)))
            return best if counts[best] > 0 else ","
    return ","


def _parse_number(raw: str) -> float | None:
    """Convertit une cellule en `float`, ou `None` si elle n'est pas numérique.

    Tolère les formats réellement rencontrés — jamais de `float()` nu qui casse
    silencieusement :
      - virgule décimale (`1,5`) et séparateurs de milliers (`1 234`, `1'234`) ;
      - formats mixtes `1.234,56` (FR) et `1,234.56` (US) ;
      - parenthèses comptables négatives `(1 234)` ;
      - symbole monétaire préfixé/suffixé (`€`, `$`, `%`…), ignoré.

    Asymétrie assumée (documentée) : les milliers par **virgule** sont reconnus
    (`8,500,000` -> 8500000), mais un point isolé est lu comme **décimal**
    (`1.234` -> 1.234) — c'est le sens US. Un export FR qui écrirait ses milliers
    au point (`8.500.000`) est donc ambigu et rejeté ; le format dominant (espace,
    virgule décimale, ou mélange point-milliers/virgule-décimale) est couvert.

    Ne lève jamais : une cellule non numérique renvoie `None` (l'appelant la
    consigne en rejet, avec sa raison).
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1].strip()
    # Symboles non numériques (devise, %, espaces restants) : retirés.
    s = "".join(ch for ch in s if not _is_noise_char(ch))
    if not s:
        return None
    if s.startswith("-"):
        negative = not negative
        s = s[1:].strip()
    elif s.startswith("+"):
        s = s[1:].strip()
    has_dot = "." in s
    has_comma = "," in s
    if has_dot and has_comma:
        # Le séparateur décimal est le DERNIER à apparaître ; l'autre est un
        # séparateur de milliers (couvre `1.234,56` et `1,234.56`).
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif has_comma:
        # Virgule seule : décimale si un unique groupe court la suit (`1,5`),
        # sinon séparateur de milliers (`1,234`).
        parts = s.split(",")
        if len(parts) == 2 and len(parts[1]) != 3:
            s = f"{parts[0]}.{parts[1]}"
        else:
            s = s.replace(",", "")
    try:
        value = float(s)
    except ValueError:
        return None
    return -value if negative else value


def _is_noise_char(ch: str) -> bool:
    """Caractère à ignorer dans une cellule numérique (milliers, devise, unité).

    Liste BORNÉE de symboles connus : espaces (y compris insécables), apostrophe
    de milliers, sigles monétaires et `%`. Une **lettre** n'en fait pas partie —
    sinon `"pomme0"` serait réduit à `"0"` et passerait pour un nombre (faux
    positif silencieux). Une cellule contenant une lettre est donc rejetée.
    """
    return ch in _THOUSANDS_CHARS or ch in _CURRENCY_CHARS


# Symboles tolérés dans une cellule numérique (devise, pourcentage). Le signe et
# les séparateurs décimaux/milliers sont traités dans `_parse_number`.
_CURRENCY_CHARS = "€$£¥%"


# Table de correspondance nom canonique -> clé normalisée (tolérance casse/espaces,
# y compris sur l'accentuation telle qu'écrite dans le CSV). Couvre l'UNION des
# schémas (industriel + financier) : le schéma d'une valeur n'est pas connu à
# l'import, on accepte donc les deux jeux de postes.
_SOURCE_BY_KEY = {
    _normalize_header(name): name
    for name, role in config.FUNDAMENTAL_METRICS_ALL
    if role == "source"
}

# Colonnes DÉRIVÉES reconnues (clé normalisée) : présentes dans un CSV, elles sont
# signalées comme telles (jamais réimportées — un dérivé est recalculé serveur).
_DERIVED_BY_KEY = {
    _normalize_header(name): name
    for name, role in config.FUNDAMENTAL_METRICS_ALL
    if role == "derived"
}


def import_csv(ticker: str, csv_content: str) -> ImportReport:
    """Parse un CSV et retourne un **rapport** (postes SOURCE uniquement).

    C'est le point d'entrée unique du parsing (API et MCP) : le **délimiteur** est
    détecté (`;` d'Excel FR, tabulation d'un collage), les **nombres** sont
    normalisés (`_parse_number`) et chaque cellule écartée est **consignée** avec
    sa raison, au lieu du silence d'un `float()` qui échoue.

    Format attendu :
        year,Chiffre d'affaires,Résultat opérationnel,...,SBC
        2015,8500000000,1200000000,...,3500000000

    - Seules les colonnes **source** reconnues par nom canonique sont lues
      (comparaison insensible à la casse et aux espaces) ; les ratios dérivés et
      les colonnes inconnues sont **listés** dans le rapport (jamais importés —
      un dérivé n'est jamais réimporté).
    - BOM UTF-8 et fins de ligne `\\r\\n` gérés.

    Aucune écriture : c'est ce rapport que `services/imports.propose_import`
    transforme en brouillon soumis à validation.
    """
    content = csv_content.lstrip("\ufeff")
    delimiter = _detect_delimiter(content)
    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
    if reader.fieldnames is None:
        return ImportReport(delimiter=delimiter)

    # Colonnes reconnues : nom canonique par index de champ normalisé. Les autres
    # sont classées (dérivée vs inconnue) pour être rapportées.
    recognized: dict[str, str] = {}
    derived_columns: list[str] = []
    unknown_columns: list[str] = []
    existing = get_manual_dict(ticker)
    for field in reader.fieldnames:
        key = _normalize_header(field)
        canonical = _SOURCE_BY_KEY.get(key)
        if canonical is not None:
            recognized[field] = canonical
        elif key in _DERIVED_BY_KEY:
            derived_columns.append(field)
        elif key not in ("", "year"):
            unknown_columns.append(field)

    report = ImportReport(
        unknown_columns=unknown_columns,
        derived_columns=derived_columns,
        delimiter=delimiter,
    )
    for row in reader:
        _parse_row(row, recognized, existing, report)
    return report


def _parse_row(
    row: dict,
    recognized: dict[str, str],
    existing: dict[int, dict[str, float]],
    report: ImportReport,
) -> None:
    """Ajoute au rapport les valeurs source d'une ligne, les rejets sinon.

    Une année illisible invalide la **ligne entière** (raison `bad_year`) : sans
    année, aucune valeur n'est rattachable.
    """
    year_str = (row.get("year") or "").strip()
    year = _parse_year(year_str)
    if year is None:
        if any((row.get(f) or "").strip() for f in recognized):
            _record(report, None, None, year_str, config.IMPORT_REJECT_YEAR)
        return
    for field, metric in recognized.items():
        raw = (row.get(field) or "").strip()
        if raw == "":
            continue
        value = _parse_number(raw)
        if value is None:
            _record(report, year, metric, raw, config.IMPORT_REJECT_UNPARSEABLE)
            continue
        if metric in existing.get(year, {}):
            report.overridden += 1
        report.entries.append({"year": year, "metric": metric, "value": value})


def _parse_year(raw: str) -> int | None:
    """Année d'une ligne : entier (virgule/décimales tolérées), sinon None."""
    if not raw:
        return None
    value = _parse_number(raw)
    if value is None:
        return None
    return int(value)


def _record(
    report: ImportReport, year: int | None, metric: str | None, raw: str, reason: str
) -> None:
    """Consigne un rejet (échantillon borné) et incrémente le total réel."""
    report.rejected_total += 1
    if len(report.rejected) < config.IMPORT_MAX_REJECT_SAMPLES:
        report.rejected.append(
            ImportRejection(year=year, metric=metric, raw=raw or None, reason=reason)
        )
