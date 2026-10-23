"""Cas d'usage « thèses d'entreprise » : construction du prompt + CRUD.

Couche `services/` : elle assemble `data/` (persistance + validation) et
l'analyse existante (`services/analysis` + `services/serialize`) sans dupliquer
la logique métier. C'est le point d'entrée **partagé API ↔ MCP** du domaine :
les deux transports consomment les mêmes fonctions, donc la même validation.

Décision actée (`PRD.md` §12.4) : **aucun appel LLM côté serveur**. `write_thesis`
renvoie un prompt structuré que l'IA cliente déroule, accompagné des données de
l'analyse — Obole fournit les données et la persistance, l'IA est le cerveau.

Les erreurs sont **typées** pour que chaque transport les traduise dans son
vocabulaire (`api/` : HTTP 404/422 ; `mcp/` : erreur d'outil) :

- `ThesisNotFound` -> thèse absente -> 404 ;
- `ValueError` -> entrée invalide -> 422.
"""

from __future__ import annotations

from typing import Any

from obole.data import thesis as thesis_data
from obole.services import analysis as analysis_service
from obole.services import serialize


class ThesisNotFound(Exception):
    """Thèse absente pour le ticker demandé."""


# Gabarit du prompt de thèse. Les métriques sont injectées depuis l'analyse
# existante (source unique) ; le gabarit ne fixe que la STRUCTURE attendue du
# raisonnement, jamais un seuil ni une formule.
PROMPT_TEMPLATE = """\
Tu es analyste actions long terme. Rédige une thèse d'investissement structurée
sur {name} ({ticker}), en t'appuyant EXCLUSIVEMENT sur les données ci-dessous
(méthode « droite d'Obole » : régression de ln(prix) sur le temps, distance σ =
valorisation).

# Données Obole
{metrics}

# Structure attendue de la thèse
1. **Pitch** — l'idée d'investissement en quelques phrases.
2. **Bull case** — les arguments haussiers, adossés aux métriques ci-dessus.
3. **Bear case** — les risques et arguments baissiers.
4. **Catalyseurs** — les événements à venir susceptibles de faire bouger le titre.
5. **Points de contrôle** — les indicateurs à surveiller pour invalider ou
   confirmer la thèse.

Reste factuel, cite les chiffres, et signale toute donnée manquante ou peu
fiable.
"""


def write_thesis(ticker: object) -> dict:
    """Construit le prompt de thèse + les données d'analyse d'un titre.

    `ticker` est **hostile par défaut** (vient de l'IA ou d'un corps HTTP libre).
    Lève `yahoo.TickerNotFound` si le titre est inconnu, `ValueError` si l'entrée
    est invalide ou l'historique trop court.

    Renvoie `{"prompt": str, "data": dict, "warnings": list[str]}` : le prompt
    structuré, les données de l'analyse (payload identique à `GET /api/stock`,
    privé de la série de prix `chart` — inutile à une thèse), et les
    avertissements de fiabilité.
    """
    if not isinstance(ticker, str):
        raise ValueError("Ticker requis")
    ticker = ticker.strip()
    if not ticker:
        raise ValueError("Ticker requis")
    analysis, prices = analysis_service.analyze_ticker(ticker)
    # La série de prix (`chart`) est inutile à un prompt : la projection commune
    # l'écarte (aucun contournement local, source unique de la règle).
    payload = serialize.analysis_to_dict(analysis, prices, include_chart=False)
    data = dict(payload)
    prompt = PROMPT_TEMPLATE.format(
        name=(analysis.identity.name or ticker),
        ticker=analysis.identity.ticker,
        metrics=_render_metrics(payload),
    )
    return {"prompt": prompt, "data": data, "warnings": list(analysis.warnings)}


def save_thesis(ticker: object, content: object) -> dict:
    """Enregistre (crée ou remplace) la thèse d'un ticker.

    `content` est du **markdown** (chaîne) — forme courante écrite par l'auteur ou
    par l'IA — ou un objet JSON (forme historique du jalon #09.3, conservée pour
    la rétro-compatibilité). Lève `ValueError` si le ticker ou le contenu est
    invalide.

    Renvoie `{"status", "ticker", "id", "updated_at"}`. `updated_at` est
    **indispensable au client** : c'est l'horodatage auquel il comparera une
    version écrite ailleurs (IA via MCP, autre onglet) pour détecter un conflit.
    Sans lui, la détection se tait après le premier enregistrement local.
    """
    if not isinstance(ticker, str):
        raise ValueError("Ticker requis")
    key = ticker.strip().upper()
    thesis_id = thesis_data.save_thesis(ticker, content)
    # Relecture des métadonnées : l'horodatage est décidé par la base (upsert),
    # on ne le devine pas côté client.
    saved = thesis_data.get_thesis(key) or {}
    return {
        "status": "ok",
        "ticker": key,
        "id": thesis_id,
        "updated_at": saved.get("updated_at"),
    }


def list_theses() -> list[dict]:
    """Thèses enregistrées (métadonnées seules, sans le contenu)."""
    return thesis_data.list_theses()


def get_thesis(ticker: object) -> dict:
    """Thèse d'un ticker. Lève `ThesisNotFound` si absente."""
    if not isinstance(ticker, str) or not ticker.strip():
        raise ValueError("Ticker requis")
    thesis = thesis_data.get_thesis(ticker)
    if thesis is None:
        raise ThesisNotFound(f"Aucune thèse pour : {ticker.strip().upper()}")
    return thesis


def delete_thesis(ticker: object) -> dict:
    """Supprime la thèse d'un ticker. Lève `ThesisNotFound` si absente."""
    if not isinstance(ticker, str) or not ticker.strip():
        raise ValueError("Ticker requis")
    if thesis_data.get_thesis(ticker) is None:
        raise ThesisNotFound(f"Aucune thèse pour : {ticker.strip().upper()}")
    thesis_data.delete_thesis(ticker)
    return {"status": "deleted", "ticker": ticker.strip().upper()}


def _render_metrics(payload: dict[str, Any]) -> str:
    """Rend les métriques clés du payload d'analyse en lignes lisibles.

    Aucun seuil n'est appliqué : les libellés et la polarité viennent déjà
    calculés par `engine/labels` (via la sérialisation). On se contente de les
    mettre en forme pour le prompt.
    """
    identity = payload.get("identity", {})
    indicators = payload.get("indicators", {})
    regression = payload.get("regression", {})
    lines = [
        f"- Identité : {_fmt(identity.get('name'))} ({_fmt(identity.get('ticker'))}), "
        f"secteur {_fmt(identity.get('sector'))}, devise {_fmt(identity.get('currency'))}",
        f"- Capitalisation : {_fmt(identity.get('market_cap'))} ; "
        f"cours : {_fmt(identity.get('last_price'))}",
        f"- Distance σ (valorisation) : {_labeled(indicators.get('distance_sigma'))}",
        f"- Performance passée : {_labeled(indicators.get('perf_passee'))}",
        f"- Écart-type (volatilité) : {_labeled(indicators.get('ecart_type'))}",
        f"- Potentiel 5 ans : {_labeled(indicators.get('potential_5y'))}",
        f"- Potentiel 10 ans : {_labeled(indicators.get('potential_10y'))}",
        f"- Tendance : {_labeled(indicators.get('trend'))}",
        f"- Qualité de l'exploitation : {_labeled(indicators.get('quality'))}",
        f"- Régression : perf annualisée {_fmt(regression.get('perf_annual_raw'))} % sur "
        f"{_fmt(regression.get('n_points'))} points "
        f"({_fmt(regression.get('start'))} → {_fmt(regression.get('end'))})",
    ]
    card = _card(payload, "rentabilite")
    if card:
        roe = _row(card, "roe_1y")
        if roe:
            lines.append(f"- ROE (dernier exercice) : {_labeled_row(roe)}")
    return "\n".join(lines)


def _card(payload: dict, card_id: str) -> dict | None:
    for card in payload.get("summary", []):
        if card.get("id") == card_id:
            return card
    return None


def _row(card: dict, key: str) -> dict | None:
    for row in card.get("rows", []):
        if row.get("key") == key:
            return row
    return None


def _labeled(scored: dict | None) -> str:
    """« valeur (libellé) » à partir d'un `ScoredValue` sérialisé.

    Certaines métriques sont **label-only** (ex. la tendance : « Haussière »/
    « Baissière »), leur `value` étant `None` alors que `label` porte l'information.
    On affiche donc le label même sans valeur numérique.
    """
    if not scored:
        return "n/d"
    label = scored.get("label")
    value = scored.get("value")
    if value is None:
        return label or "n/d"
    rendered = _fmt(value)
    return f"{rendered} ({label})" if label else rendered


def _labeled_row(row: dict | None) -> str:
    """« valeur unité (libellé) » à partir d'une ligne de synthèse."""
    if row is None or row.get("value") is None:
        return "n/d"
    value = row.get("value")
    unit = row.get("unit")
    suffix = "%" if unit == "pct" else ("x" if unit == "x" else "")
    out = f"{_fmt(value)}{suffix}"
    note = row.get("note")
    if note:
        out += f" — {note}"
    return out


def _fmt(value: object) -> str:
    if value is None:
        return "n/d"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)
