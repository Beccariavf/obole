"""`fetch_identity` — le prix n'est jamais figé par un appel « name only ».

Régression (#9) : `portfolio.resolve_names` appelle `fetch_identity(ticker, None)`
pour n'obtenir que le NOM. L'ancien code mettait en cache une `Identity` avec
`last_price=None` et, sur un hit de cache, RENDAIT l'objet tel quel en ignorant
le `last_price` reçu. Conséquence : ouvrir la fiche d'une ligne du portefeuille
APRÈS le Résumé affichait « Prix communiqué : -- » pendant tout le TTL (7 jours).

Sans réseau : le cache est semé, et tout accès réseau est transformé en échec.
"""

from __future__ import annotations

import tempfile

import pytest

from obole import config
from obole.data import cache, yahoo
from obole.models import CompanyKind, Identity


@pytest.fixture(autouse=True)
def _isolated_db():
    _orig = config.CACHE_DB
    config.CACHE_DB = tempfile.mktemp(suffix=".sqlite")
    yield
    config.CACHE_DB = _orig


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Tout appel `yf.Ticker(...).info` est interdit : le test doit rester sur le cache."""

    class _Boom:
        def __getattr__(self, _name):
            raise AssertionError("appel réseau inattendu (cache non exploité)")

    monkeypatch.setattr(yahoo.yf, "Ticker", lambda *_a, **_k: _Boom())


def _seed(ticker: str, last_price: float | None) -> None:
    """Identité complète en cache : version de modèle courante + champs requis."""
    cache.put(
        ticker,
        "identity",
        Identity(
            ticker=ticker,
            name="Société X",
            industry="Beverages",
            website="https://x.example",
            beta=0.8,
            week52_low=90.0,
            avg_volume=1_000_000.0,
            # #21 : `address` fait partie des champs marqueurs de fraîcheur
            # (profil société v8) — sans lui, l'identité serait jugée périmée.
            address="Paris, France",
            kind=CompanyKind.INDUSTRIAL,
            model_version=yahoo.MODEL_VERSION,
            last_price=last_price,
        ),
    )


def test_cache_hit_does_not_freeze_missing_price():
    """Un cache sans prix + un appel avec prix -> le prix réel est rendu."""
    _seed("RI.PA", last_price=None)
    assert yahoo.fetch_identity("RI.PA", 123.45).last_price == 123.45


def test_cache_hit_keeps_recent_price():
    """Le prix déjà connu n'est pas écrasé par un appel sans prix."""
    _seed("RI.PA", last_price=100.0)
    assert yahoo.fetch_identity("RI.PA", None).last_price == 100.0


def test_cache_hit_refreshes_with_newer_price():
    """Un prix plus récent fourni rafraîchit le cache (jamais d'écrasement figé)."""
    _seed("RI.PA", last_price=100.0)
    assert yahoo.fetch_identity("RI.PA", 200.0).last_price == 200.0
    # Le rafraîchissement est bien persisté.
    assert yahoo.fetch_identity("RI.PA", None).last_price == 200.0


def test_cache_hit_without_price_stays_none():
    """Ni cache ni argument ne portent de prix : reste None (pas d'invention)."""
    _seed("RI.PA", last_price=None)
    assert yahoo.fetch_identity("RI.PA", None).last_price is None
