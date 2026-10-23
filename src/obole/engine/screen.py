"""Moteur de calcul pur du screener : filtre + tri + score composite.

Fonctions PURES (zéro I/O, zéro réseau, zéro dépendance à data/ ni services/).
Aucune formule ni seuil dupliqué : les sens de tri et les seuils viennent de
config.py ; la réduction d'une fiche (`screen_stock`) et l'orchestration I/O
vivent dans `services/screen.py`.

Ce module ne voit jamais data/, services/ ni api/ : il ne reçoit que des
`ScreenResult` déjà construits et ne fait que les filtrer/trier.
"""

from __future__ import annotations

from obole import config
from obole.models import ScreenResult

# Sens de tri par défaut selon la nature du critère : True = décroissant (bon premier).
# SOURCE UNIQUE : `SCREEN_SORT_DESC` (config.py) complète `SCREEN_COLORS` ; le front
# consomme la direction exposée par l'API (aucun doublon de sens ici).
DEFAULT_SORT_ORDER: dict[str, bool] = dict(config.SCREEN_SORT_DESC)

# Clé virtuelle : calculée, pas une colonne brute de `ScreenResult`. `score` est
# le score composite (#14) ; il se trie comme les autres, mais sa valeur dépend
# des critères actifs (`score_keys`), pas d'un champ de la ligne.
SCORE_KEY = "score"
# Sens de tri du score : plus haut = meilleur (compromis le plus favorable).
DEFAULT_SORT_ORDER[SCORE_KEY] = True

# Critères triables (colonnes + `score`). `score` en fait partie car il se trie
# comme les autres.
SORTABLE_KEYS = tuple(DEFAULT_SORT_ORDER.keys())
# Critères FILTRABLES (bornes min/max) : les colonnes de marché uniquement.
# `score` en est EXCLU — ce n'est pas une donnée de marché mais un rang relatif
# au jeu filtré ; le filtrer serait un non-sens (il dépend du résultat du filtre).
FILTERABLE_KEYS = tuple(k for k in SORTABLE_KEYS if k != SCORE_KEY)


def composite_score(
    screens: list[ScreenResult],
    keys: list[str],
) -> dict[str, float]:
    """Score composite par **percentile** (0-100, 100 = meilleur), poids égaux.

    Classement par **compromis** : contrairement au tri en cascade (où le 2ᵉ
    critère ne départage que les égalités du 1ᵉʳ), TOUS les critères agissent
    simultanément. « ROE % haut + P/FCF bas » remonte donc les valeurs bonnes sur
    les deux, pas celles qui écrasent un seul critère.

    - Chaque critère est normalisé par son **rang** (méthode « min ») : insensible
      aux unités et aux valeurs extrêmes.
    - Le sens vient de `SCREEN_SORT_DESC` (`True` = plus grand = mieux).
    - Un critère absent (None) ou une ligne en `error` exclut la ligne du score.
    - Renvoie {} s'il y a moins de **2** critères exploitables (le tri simple suffit).

    Fonction PURE : aucun I/O, aucune mutation des lignes.
    """
    valid = [k for k in keys if k in DEFAULT_SORT_ORDER]
    if len(valid) < 2 or not screens:
        return {}

    # Lignes exploitables : ni error, ni critère manquant. On mémorise les valeurs
    # dans une passe unique (typées `float`, pas `float | None`) : le filtre
    # ci-dessus garantit qu'aucune n'est None.
    usable = [
        s for s in screens if s.error is None and all(_fvalue(s, k) is not None for k in valid)
    ]
    if not usable:
        return {}
    n = len(usable)

    totals: dict[str, float] = {s.ticker: 0.0 for s in usable}
    for key in valid:
        values: list[float] = [v for v in (_fvalue(s, key) for s in usable) if v is not None]
        descending = DEFAULT_SORT_ORDER.get(key, False)  # True = plus grand = mieux
        # Rang 1 = meilleur : « plus grand = mieux » -> ordre décroissant ;
        # « plus bas = mieux » -> ordre croissant.
        ranked = sorted(range(n), key=lambda i: values[i], reverse=descending)
        # Égalités -> même rang (le meilleur) donc même score.
        rank_of: dict[float, int] = {}
        for pos, i in enumerate(ranked, start=1):
            rank_of.setdefault(values[i], pos)
        for s in usable:
            v = _fvalue(s, key)
            if v is None:  # déjà exclu, mais on ne présume pas
                continue
            r = rank_of[v]
            # n == 1 : rang unique -> percentile neutre (pas de division par zéro).
            pct = 100.0 if n == 1 else 100.0 * (n - r) / (n - 1)
            totals[s.ticker] += pct
    return {t: total / len(valid) for t, total in totals.items()}


def filter_and_sort(
    screens: list[ScreenResult],
    filters: dict[str, tuple[float | None, float | None]] | None = None,
    sort_by: list[str | tuple[str, str]] | None = None,
    score_keys: list[str] | None = None,
) -> list[ScreenResult]:
    """Filtre (bornes min/max inclusives) puis tri multi-colonnes chaîné d'une liste.

    - `filters` : {critère: (min, max)} ; une borne None = non bornée. Un critère
      absents (None) est exclu par le filtre (on ne peut pas le comparer).
    - `sort_by` : liste de critères (chaînée : critère 1 principal, puis 2, …).
      Un élément peut être une clé (sens par défaut) ou un tuple (clé, "asc"/"desc").
    - `score_keys` : critères du score composite (#14). S'il y en a ≥ 2, `score`
      est calculé sur les lignes **filtrées** (avant tri) et **posé sur chaque
      ligne** (`ScreenResult.score`).
    - Les lignes `error` ou dont le critère de tri vaut None sont renvoyées en fin
      de liste (jamais de crash).

    Déterministe et sans I/O. ⚠️ Contrairement à `composite_score`, elle **mute**
    les `ScreenResult` reçus (elle y écrit `score`) : c'est son rôle d'assemblage,
    mais l'appelant ne doit pas réutiliser ces objets ailleurs en supposant qu'ils
    sont intacts.
    """
    if filters:
        screens = _apply_filters(screens, filters)
    if score_keys and len([k for k in score_keys if k in DEFAULT_SORT_ORDER]) >= 2:
        scores = composite_score(screens, score_keys)
        for s in screens:
            s.score = scores.get(s.ticker)
    if sort_by:
        screens = _apply_sort(screens, sort_by)
    return screens


def _apply_filters(
    screens: list[ScreenResult],
    filters: dict[str, tuple[float | None, float | None]],
) -> list[ScreenResult]:
    out: list[ScreenResult] = []
    for s in screens:
        keep = True
        for attr, (lo, hi) in filters.items():
            v = _fvalue(s, attr)
            if v is None:
                keep = False
                break
            if lo is not None and v < lo:
                keep = False
                break
            if hi is not None and v > hi:
                keep = False
                break
        if keep:
            out.append(s)
    return out


def _apply_sort(
    screens: list[ScreenResult],
    sort_by: list[str | tuple[str, str]],
) -> list[ScreenResult]:
    # Tri stable : on applique les clés de la moins à la plus importante, la
    # dernière (primaire) domine. Les lignes sans valeur (None/error) ont une clé
    # « +inf » quel que soit le sens -> renvoyées en fin.
    ordered = list(screens)
    for key_spec in reversed(sort_by):
        if isinstance(key_spec, str):
            key, ascending = key_spec, not DEFAULT_SORT_ORDER.get(key_spec, False)
        else:
            key, ascending = key_spec[0], key_spec[1] == "asc"
        # Les lignes sans valeur (None/error) sont sorties du paquet trié puis
        # réappendées en fin : elles restent en dernier quel que soit le sens.
        present = [s for s in ordered if _fvalue(s, key) is not None]
        missing = [s for s in ordered if _fvalue(s, key) is None]
        present.sort(key=lambda s: _sort_value(_fvalue(s, key)), reverse=not ascending)
        ordered = present + missing
    return ordered


def _sort_value(value: float | None) -> float:
    """Clé de tri numérique. Les lignes sans valeur sont filtrées en amont ;
    par sûreté elles partent en fin quel que soit le sens du tri."""
    return float("inf") if value is None else value


def _fvalue(s: ScreenResult, attr: str) -> float | None:
    """Valeur numérique d'un critère, ou None si absente/error."""
    if s.error is not None:
        return None
    v = getattr(s, attr, None)
    if v is None:
        return None
    return float(v)
