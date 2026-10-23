"""Outils MCP du portefeuille (comptes, transactions, dividendes, positions, résumé).

Délègue à `services/portfolio.py` — le point d'entrée **partagé API ↔ MCP** du
domaine : les deux transports consomment les mêmes cas d'usage, donc la même
validation (la couche `mcp/` ne peut pas importer `api/`).

Les erreurs sont **typées** côté service et traduites en `ToolError` :

- `portfolio_data.NotFoundError` -> ressource absente (compte, transaction,
  dividende) ;
- `ValueError` -> entrée invalide (date, sens, quantité, devise…).

Les payloads de lecture passent par `services/serialize`
(`portfolio_positions_to_list`, `portfolio_summary_to_dict`) : ils sont
**identiques** à ceux servis par l'API HTTP (garantie de parité outil ↔ route).

C'est la brique **MCP-B** du PRD §12.2 (famille 2) : l'IA extrait les lignes d'un
document fourni par l'utilisateur et les **importe** ici, une opération à la
fois. Le serveur ne parse aucun document : c'est l'IA qui structure.
"""

from __future__ import annotations

from mcp.server.mcpserver.exceptions import ToolError

from obole import config
from obole.data import portfolio as portfolio_data
from obole.services import portfolio as portfolio_service
from obole.services import serialize


def list_accounts() -> list[dict]:
    """Liste les comptes du portefeuille (triés par nom).

    Un portefeuille se compose de plusieurs **comptes** (ex. « PEA », « CTO »).
    Toute transaction ou dividende est rattaché à un compte : c'est le prérequis
    de tout import.

    Returns:
        Liste de `{"id", "name", "currency"}`. Identique à
        `GET /api/portfolio/accounts`.
    """
    return portfolio_service.accounts()


def create_account(name: str, currency: str | None = None) -> dict:
    """Crée un compte de portefeuille.

    Args:
        name: nom du compte (non vide, ex. `"PEA"`).
        currency: devise du compte. **Mono-devise EUR** (fiche #17 §3) : seul
            `"EUR"` (ou null) est accepté, toute autre devise est refusée.

    Returns:
        `{"status": "ok", "id": int}`. Identique à `POST /api/portfolio/accounts`.

    Raises:
        ToolError: nom vide ou devise non supportée.
    """
    try:
        account_id = portfolio_service.create_account(name, currency)
    except ValueError as exc:
        raise ToolError(str(exc)) from None
    return {"status": "ok", "id": account_id}


def delete_account(account_id: int) -> dict:
    """Supprime un compte ET ses transactions et dividendes (cascade).

    ⚠️ **Destructif, sans confirmation** : les transactions et dividendes du
    compte sont définitivement supprimés.

    Args:
        account_id: identifiant du compte (voir `list_accounts`).

    Returns:
        `{"status": "deleted", "id": int}`. Identique à
        `DELETE /api/portfolio/accounts/{account_id}`.

    Raises:
        ToolError: compte inconnu.
    """
    try:
        portfolio_service.delete_account(account_id)
    except portfolio_data.NotFoundError as exc:
        raise ToolError(str(exc)) from None
    except ValueError as exc:
        raise ToolError(str(exc)) from None
    return {"status": "deleted", "id": account_id}


def list_transactions(account_id: int | None = None, tag: str | None = None) -> list[dict]:
    """Liste les transactions, éventuellement filtrées par compte et/ou étiquette.

    Args:
        account_id: compte à filtrer ; `null` (défaut) = tous les comptes.
        tag: étiquette à filtrer (#17.6) ; `null` (défaut) = toutes les
            étiquettes. Un « portefeuille virtuel » est l'ensemble des
            transactions portant une même étiquette (ex. « Actions dividende »).

    Returns:
        Liste de transactions (triées par date), chacune portant `id`,
        `account_id`, `ticker`, `side` (`"buy"`/`"sell"`), `trade_date`,
        `quantity`, `price`, `fees`, `currency`, `note`, `tag`. Identique à
        `GET /api/portfolio/transactions`.
    """
    return portfolio_service.transactions(account_id, tag)


def add_transaction(
    account_id: int,
    ticker: str,
    side: str,
    trade_date: str,
    quantity: float,
    price: float,
    fees: float = 0.0,
    currency: str | None = None,
    note: str | None = None,
    tag: str | None = None,
) -> dict:
    """Ajoute une transaction (achat ou vente) au portefeuille.

    Les transactions sont la **source de vérité** : les positions en sont
    recalculées, jamais saisies. L'entrée est **hostile par défaut** (elle vient
    de l'IA) : chaque champ est validé avant persistance.

    Args:
        account_id: compte d'accueil (voir `list_accounts`) — doit exister.
        ticker: symbole Yahoo de l'entreprise (ex. `"RI.PA"`), normalisé en
            majuscules.
        side: sens de l'opération, `"buy"` ou `"sell"`.
        trade_date: date de l'opération au format ISO `AAAA-MM-JJ`.
        quantity: nombre de titres, **strictement positif**.
        price: prix unitaire, **positif ou nul**.
        fees: frais de courtage, positifs ou nuls (défaut 0).
        currency: devise — mono-devise EUR, seul `"EUR"` (ou null) est accepté.
        note: commentaire libre optionnel.
        tag: étiquette libre optionnelle (#17.6) qui rattache la transaction à un
            **portefeuille virtuel** (ex. `"Actions dividende"`). Longueur bornée,
            `null` = sans étiquette.

    Returns:
        `{"status": "ok", "id": int}`. Identique à
        `POST /api/portfolio/transactions`.

    Raises:
        ToolError: compte inconnu, date/sens/devise invalide, quantité non
            positive, prix ou frais négatif, étiquette invalide.
    """
    try:
        tx_id = portfolio_service.add_transaction(
            account_id=account_id,
            ticker=ticker,
            side=side,
            trade_date=trade_date,
            quantity=quantity,
            price=price,
            fees=fees,
            currency=currency,
            note=note,
            tag=tag,
        )
    except ValueError as exc:
        raise ToolError(str(exc)) from None
    return {"status": "ok", "id": tx_id}


def update_transaction(
    tx_id: int,
    account_id: int,
    ticker: str,
    side: str,
    trade_date: str,
    quantity: float,
    price: float,
    fees: float = 0.0,
    currency: str | None = None,
    note: str | None = None,
    tag: str | None = None,
) -> dict:
    """Remplace une transaction existante (tous les champs).

    La transaction est **entièrement** remplacée : fournir tous les champs, pas
    seulement ceux qui changent.

    Args:
        tx_id: identifiant de la transaction à modifier (voir `list_transactions`).
        account_id: compte d'accueil.
        ticker: symbole Yahoo.
        side: `"buy"` ou `"sell"`.
        trade_date: date ISO `AAAA-MM-JJ`.
        quantity: nombre de titres, strictement positif.
        price: prix unitaire, positif ou nul.
        fees: frais de courtage, positifs ou nuls.
        currency: devise (mono-devise EUR).
        note: commentaire libre optionnel.
        tag: étiquette libre optionnelle (#17.6), `null` = sans étiquette.

    Returns:
        `{"status": "ok", "id": int}`. Identique à
        `PUT /api/portfolio/transactions/{tx_id}`.

    Raises:
        ToolError: transaction inconnue, compte inconnu, ou champ invalide.
    """
    try:
        portfolio_service.update_transaction(
            tx_id,
            account_id=account_id,
            ticker=ticker,
            side=side,
            trade_date=trade_date,
            quantity=quantity,
            price=price,
            fees=fees,
            currency=currency,
            note=note,
            tag=tag,
        )
    except portfolio_data.NotFoundError as exc:
        raise ToolError(str(exc)) from None
    except ValueError as exc:
        raise ToolError(str(exc)) from None
    return {"status": "ok", "id": tx_id}


def delete_transaction(tx_id: int) -> dict:
    """Supprime une transaction.

    Args:
        tx_id: identifiant de la transaction (voir `list_transactions`).

    Returns:
        `{"status": "deleted", "id": int}`. Identique à
        `DELETE /api/portfolio/transactions/{tx_id}`.

    Raises:
        ToolError: transaction inconnue.
    """
    try:
        portfolio_service.delete_transaction(tx_id)
    except portfolio_data.NotFoundError as exc:
        raise ToolError(str(exc)) from None
    except ValueError as exc:
        raise ToolError(str(exc)) from None
    return {"status": "deleted", "id": tx_id}


def list_dividends(account_id: int | None = None) -> list[dict]:
    """Liste les dividendes, éventuellement filtrés par compte.

    Args:
        account_id: compte à filtrer ; `null` (défaut) = tous les comptes.

    Returns:
        Liste de dividendes (triés par date), chacun portant `id`, `account_id`,
        `ticker`, `pay_date`, `amount`, `status` (`"proposed"`/`"confirmed"`),
        `source` (`"manual"`/`"yahoo"`). Identique à
        `GET /api/portfolio/dividends`.
    """
    return portfolio_service.dividends(account_id)


def add_dividend(
    account_id: int,
    ticker: str,
    pay_date: str,
    amount: float,
    status: str = "confirmed",
    source: str = "manual",
) -> dict:
    """Ajoute un dividende perçu (ou annoncé) à un compte.

    Args:
        account_id: compte d'accueil — doit exister.
        ticker: symbole Yahoo (ex. `"RI.PA"`).
        pay_date: date de versement au format ISO `AAAA-MM-JJ`.
        amount: montant total encaissé, **positif ou nul**.
        status: `"proposed"` (annoncé) ou `"confirmed"` (versé, défaut).
        source: `"manual"` (saisi, défaut) ou `"yahoo"` (détecté).

    Returns:
        `{"status": "ok", "id": int}`. Identique à `POST /api/portfolio/dividends`.

    Raises:
        ToolError: compte inconnu, date invalide, montant négatif, statut ou
            source hors liste fermée.
    """
    try:
        div_id = portfolio_service.add_dividend(
            account_id=account_id,
            ticker=ticker,
            pay_date=pay_date,
            amount=amount,
            status=status,
            source=source,
        )
    except ValueError as exc:
        raise ToolError(str(exc)) from None
    return {"status": "ok", "id": div_id}


def update_dividend(
    div_id: int,
    account_id: int,
    ticker: str,
    pay_date: str,
    amount: float,
    status: str = "confirmed",
    source: str = "manual",
) -> dict:
    """Remplace un dividende existant (tous les champs).

    Args:
        div_id: identifiant du dividende (voir `list_dividends`).
        account_id: compte d'accueil.
        ticker: symbole Yahoo.
        pay_date: date de versement ISO `AAAA-MM-JJ`.
        amount: montant total encaissé, positif ou nul.
        status: `"proposed"` ou `"confirmed"`.
        source: `"manual"` ou `"yahoo"`.

    Returns:
        `{"status": "ok", "id": int}`. Identique à
        `PUT /api/portfolio/dividends/{div_id}`.

    Raises:
        ToolError: dividende inconnu, compte inconnu, ou champ invalide.
    """
    try:
        portfolio_service.update_dividend(
            div_id,
            account_id=account_id,
            ticker=ticker,
            pay_date=pay_date,
            amount=amount,
            status=status,
            source=source,
        )
    except portfolio_data.NotFoundError as exc:
        raise ToolError(str(exc)) from None
    except ValueError as exc:
        raise ToolError(str(exc)) from None
    return {"status": "ok", "id": div_id}


def delete_dividend(div_id: int) -> dict:
    """Supprime un dividende.

    Args:
        div_id: identifiant du dividende (voir `list_dividends`).

    Returns:
        `{"status": "deleted", "id": int}`. Identique à
        `DELETE /api/portfolio/dividends/{div_id}`.

    Raises:
        ToolError: dividende inconnu.
    """
    try:
        portfolio_service.delete_dividend(div_id)
    except portfolio_data.NotFoundError as exc:
        raise ToolError(str(exc)) from None
    except ValueError as exc:
        raise ToolError(str(exc)) from None
    return {"status": "deleted", "id": div_id}


def list_positions(account_id: int | None = None, tag: str | None = None) -> list[dict]:
    """Positions **recalculées** depuis les transactions (quantité, PRU, coût).

    Les positions ne sont jamais saisies : elles sont dérivées des transactions
    (consolidées « comme une entreprise »). Les positions soldées (quantité
    nulle) sont omises. Aucune valorisation de marché ici (elle vit dans
    `get_portfolio_summary`). Liste **vide** si le portefeuille n'a aucune
    transaction (pas d'erreur).

    Args:
        account_id: compte à filtrer ; `null` (défaut) = vue consolidée
            « Tous les comptes ».
        tag: étiquette à filtrer (#17.6) ; `null` (défaut) = toutes. Une position
            étiquetée porte une liste `tags` (ses étiquettes distinctes).

    Returns:
        Liste de positions triées par coût décroissant, chacune portant
        `ticker`, `quantity`, `pru`, `cost_basis`, `realized`, `tags`. Identique
        à `GET /api/portfolio/positions`.
    """
    return serialize.portfolio_positions_to_list(portfolio_service.positions(account_id, tag))


def list_portfolio_tags(account_id: int | None = None) -> list[str]:
    """Liste les étiquettes du portefeuille (portefeuilles virtuels, #17.6).

    Une étiquette regroupe des transactions en un portefeuille virtuel (ex.
    « Actions dividende »), sans créer de compte. La liste est le **distinct**
    des étiquettes portées par les transactions, triée (insensible à la casse).

    Args:
        account_id: restreint la liste au compte donné ; `null` (défaut) = toutes
            les étiquettes de l'espace.

    Returns:
        Liste de libellés d'étiquettes. Identique au champ `tags` de
        `GET /api/portfolio/tags`. Liste vide si aucune étiquette.
    """
    return portfolio_service.tags(account_id)


def get_portfolio_summary(
    account_id: int | None = None,
    benchmark: str | None = None,
    period: str | None = None,
    tag: str | None = None,
) -> dict:
    """Résumé de performance du portefeuille face à un benchmark (TWR).

    Assemble la courbe **TWR** du portefeuille et celle du benchmark
    (buy-and-hold), 4 KPI (valeur totale, montant investi, Total Return,
    dividendes + rendement), la répartition par compte et les Top/Flop N
    positions. Les prix viennent du cache local : aucun appel réseau n'est
    refait si les cours y sont déjà.

    Args:
        account_id: compte à résumer ; `null` (défaut) = vue consolidée.
        benchmark: ticker du benchmark ; `null` = défaut de la méthode
            (<<BENCHMARK_DEFAULT>>). Benchmarks curés proposés :
            <<BENCHMARKS>>. Un ticker libre est accepté même hors de cette liste.
        period: fenêtre d'analyse. Valeurs admises : <<PERIODS>> ; `null` =
            défaut (`config.PORTFOLIO_PERIOD_DEFAULT`, soit <<PERIOD_DEFAULT>>).
        tag: étiquette à résumer (#17.6) ; `null` (défaut) = toutes. Restreint le
            résumé à un **portefeuille virtuel** (les transactions étiquetées),
            combinable avec `account_id`.

    Returns:
        Payload du résumé (`dates`, `kpis`, `accounts`, `top`, `flop`,
        `warnings`…). Identique à `GET /api/portfolio/summary`.

    Raises:
        ToolError: période inconnue ou benchmark introuvable sur Yahoo.
    """
    try:
        summary = portfolio_service.summary(account_id, benchmark, period, tag)
    except ValueError as exc:
        raise ToolError(str(exc)) from None
    return serialize.portfolio_summary_to_dict(summary)


def get_portfolio_risk(
    account_id: int | None = None,
    benchmark: str | None = None,
    period: str | None = None,
    tag: str | None = None,
) -> dict:
    """Risque du portefeuille : drawdown face au benchmark + corrélations (#17.3).

    Renvoie la courbe de **drawdown** du portefeuille (aire, rouge) et du
    benchmark (comparaison), les **métriques de drawdown** (perte maximale,
    baisse en cours, plus longue récupération en jours, volatilité réalisée,
    meilleur et pire mois) et la **matrice de corrélation** entre les lignes
    détenues (rendements log quotidiens sur la fenêtre). Réutilise le TWR du
    résumé : aucun appel réseau supplémentaire si les cours sont en cache.

    Les titres dont l'historique est trop court (`config.PORTFOLIO_CORR_MIN_OBS`
    observations) sont **écartés** de la matrice et listés dans `correlation
    .excluded` (jamais un zéro trompeur).

    Args:
        account_id: compte à analyser ; `null` (défaut) = vue consolidée.
        benchmark: ticker de comparaison (voir `get_portfolio_summary`).
        period: fenêtre d'analyse (voir `get_portfolio_summary`).
        tag: étiquette à analyser (#17.6) ; `null` (défaut) = toutes.

    Returns:
        Payload (`dates`, `drawdown`, `benchmark_drawdown`, `metrics`,
        `benchmark_metrics`, `months`, `correlation`, `warnings`). Identique à
        `GET /api/portfolio/risk`.

    Raises:
        ToolError: période inconnue ou benchmark introuvable sur Yahoo.
    """
    try:
        risk = portfolio_service.risk(account_id, benchmark, period, tag)
    except ValueError as exc:
        raise ToolError(str(exc)) from None
    return serialize.portfolio_risk_to_dict(risk)


def test_portfolio_correlation(
    ticker: str,
    account_id: int | None = None,
    benchmark: str | None = None,
    period: str | None = None,
    tag: str | None = None,
) -> dict:
    """Test de corrélation : impact d'un titre candidat sur le portefeuille (#17.3).

    Corrèle le `ticker` candidat (rendements log quotidiens, fenêtre de la
    période) à chaque ligne DÉTENUE du périmètre, dans l'ordre des colonnes de la
    matrice de corrélation (`get_portfolio_risk`), puis renvoie la **corrélation
    moyenne** hors diagonale avant (`current_avg`) et après (`new_avg`) ajout du
    candidat, avec le `delta` signé : un titre peu corrélé ABAISSE la moyenne
    (diversification), un titre très corrélé la RELÈVE.

    Args:
        ticker: code du titre à tester (obligatoire, ex. `MC.PA`).
        account_id: compte à analyser ; `null` (défaut) = vue consolidée.
        benchmark: ticker de comparaison (voir `get_portfolio_summary`).
        period: fenêtre d'analyse (voir `get_portfolio_summary`).
        tag: étiquette à analyser (#17.6) ; `null` (défaut) = toutes.

    Returns:
        Payload (`ticker`, `tickers`, `row`, `obs`, `current_avg`, `new_avg`,
        `delta`, `warning`). `tickers`/`row` sont alignés (une corrélation par
        ligne détenue) ; `None` = historique commun insuffisant.

    Raises:
        ToolError: ticker vide, introuvable, déjà détenu, périmètre sans ligne,
            période inconnue ou benchmark introuvable.
    """
    try:
        result = portfolio_service.correlation_test(account_id, benchmark, period, tag, ticker)
    except ValueError as exc:
        raise ToolError(str(exc)) from None
    return serialize.portfolio_correlation_test_to_dict(result)


def _inject_doc_tokens() -> None:
    """Injecte les périodes/benchmarks du résumé dans la docstring depuis `config`.

    Motif identique à `screener.py` : les énumérations (périodes admises,
    benchmarks curés) viennent de la **SOURCE UNIQUE** (`config.py`) et non d'un
    littéral en dur qui pourrait dériver silencieusement de la route
    `GET /api/portfolio/benchmarks`.
    """
    doc = get_portfolio_summary.__doc__ or ""
    get_portfolio_summary.__doc__ = (
        doc.replace("<<PERIODS>>", ", ".join(f"`{p}`" for p in config.PORTFOLIO_PERIODS))
        .replace("<<PERIOD_DEFAULT>>", f"`{config.PORTFOLIO_PERIOD_DEFAULT}`")
        .replace("<<BENCHMARK_DEFAULT>>", f"`{config.PORTFOLIO_BENCHMARK_DEFAULT}`")
        .replace(
            "<<BENCHMARKS>>",
            ", ".join(f"`{b['ticker']}` ({b['label']})" for b in config.PORTFOLIO_BENCHMARKS),
        )
    )


# Les périodes/benchmarks sont injectés dans la docstring depuis la SOURCE UNIQUE
# (`config.py`) : aucune énumération en dur qui pourrait dériver de la route.
_inject_doc_tokens()


def register(server) -> None:
    """Enregistre les outils du portefeuille sur le serveur MCP."""
    for fn in (
        list_accounts,
        create_account,
        delete_account,
        list_transactions,
        add_transaction,
        update_transaction,
        delete_transaction,
        list_dividends,
        add_dividend,
        update_dividend,
        delete_dividend,
        list_positions,
        list_portfolio_tags,
        get_portfolio_summary,
        get_portfolio_risk,
        test_portfolio_correlation,
    ):
        server.tool()(fn)
