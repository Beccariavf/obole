# #17.0 — Portefeuille · Socle persistant + saisie

> **Statut :** **fait** (J0) · **Priorité :** 🟡 Q2 · **Impact Pernod :** 🟢
> **Branche (historique) :** `feat/portefeuille` · **Taille :** ~2 sessions
> **Fiche parente :** #17 (Portefeuille) · **Précédent :** — · **Suivant :** `01-resume.md`

---

## 1. Contexte

Premier jalon : **rendre le portefeuille saisissable et persistant**, sans aucun calcul
d'agrégat. C'est le prérequis de tous les jalons suivants et la base de l'import MCP-B.

Points d'ancrage : `data/cache.py` (`SCHEMA_VERSION = 1`, `MIGRATIONS`, `_migrate_0_to_1`) ;
`data/backup.py::_TABLE_COLUMNS` ; `data/indices.py` et `data/events.py` comme **patrons de
couche `data/`** (I/O + validation, aucun calcul) ; `src/obole/web/index.html` (barre
`.searchbar`) pour le bouton ; `src/obole/web/sections.js` pour le rail.

## 2. Objectif

Pouvoir créer un compte, y saisir des achats/ventes/dividendes, les modifier et les supprimer,
et voir ses **positions brutes recalculées** (quantité et PRU) — le tout persistant et sauvegardé.

## 3. Non-objectifs

- Aucun calcul de performance, risque ou rendement (jalons suivants).
- Aucune proposition automatique de dividende (jalon `05`).
- Pas de marqueur sur la fiche entreprise (jalon `04`).
- Pas de multi-devise.

## 4. Exigences

- 4.1 `config.SCHEMA_VERSION = 2` ; `MIGRATIONS[1] = _migrate_1_to_2` dans `data/cache.py`.
- 4.2 Tables (schéma exact dans la fiche parente §4.1) : `portfolio_accounts`,
  `portfolio_transactions`, `portfolio_dividends`. Index sur `account_id` et
  `(account_id, ticker)`.
- 4.3 `data/portfolio.py` : fonctions `list_accounts`/`create_account`/`delete_account`,
  `list_transactions`/`add_transaction`/`update_transaction`/`delete_transaction`,
  `list_dividends`/`add_dividend`/`update_dividend`/`delete_dividend`. Validation stricte :
  date ISO, `quantity > 0`, `price >= 0`, `fees >= 0`, `side ∈ {buy, sell}`,
  `status ∈ {proposed, confirmed}`, ticker non vide (normalisé upper).
- 4.4 `data/backup.py::_TABLE_COLUMNS` étendu (comptes **avant** transactions/dividendes) ;
  `_validate_references` vérifie que `account_id` existe.
- 4.5 `services/portfolio.py::positions(account_id)` : recalcul des positions brutes depuis les
  transactions (aucune formule de valorisation — juste quantité et PRU).
- 4.6 Routes API : `GET/POST/DELETE /api/portfolio/accounts`,
  `GET/POST/PUT/DELETE /api/portfolio/transactions`,
  `GET/POST/PUT/DELETE /api/portfolio/dividends`. 422 sur entrée invalide, 404 sur id inconnu.
- 4.7 Front : bouton **Portefeuille** entre `Screener` et `⚙ Paramètres` ; vue plein écran à
  **onglets horizontaux** (libellés lisibles ; « Positions » actif, autres « à venir ») ;
  sélecteur de compte (« Tous » + un compte) ; carte de saisie unifiée (bascule
  Transaction/Dividende) ; tableaux des positions, transactions et dividendes.
  Saisie numérique **à la virgule** (`type="text"` + `inputmode="decimal"`).
- 4.8 `src/obole/web/api.js` porte **tous** les `fetch` du portefeuille ;
  `src/obole/web/portfolio.js` = mixin.

## 5. Critères d'acceptation

- [x] Base neuve et base v1 existante convergent vers `SCHEMA_VERSION = 2` (test, miroir de
  `tests/test_schema_migration.py`)
- [x] Migration idempotente (rejouée sans effet) et atomique (échec → rollback)
- [x] `add_transaction` rejette date invalide, quantité ≤ 0, sens inconnu, prix négatif (tests)
- [x] `add_dividend` rejette date invalide, montant négatif (tests)
- [x] Positions recalculées correctes : achats multiples → PRU pondéré ; vente → quantité réduite
  (tests sur fixture, cas nominal + vente partielle + compte vide)
- [x] `backup.py` : export → purge → restauration conserve les 3 tables (test)
- [x] Routes répondent 200/422/404 attendus (tests `tests/test_portfolio_api.py`)
- [x] Bouton Portefeuille entre `Screener` et `⚙ Paramètres` ; rail + sélecteur fonctionnels (e2e)
- [x] `modules.test.js` : `portfolio.js` exporte un mixin, 0 `fetch` hors `api.js`
- [x] Suite hors réseau verte

## 6. Invariants préservés

- Calibration Pernod (`z = −3.81`) inchangée — ce jalon ne touche aucun calcul existant.
- `engine/` reste pur ; `data/portfolio.py` ne fait aucune formule.
- Les données utilisateur existantes (indices, événements, manuel, réglages) survivent à la
  migration.
- Aucun seuil littéral : rien de numérique dans ce jalon n'a besoin de `config.py` hormis le
  numéro de version.

## 7. Jalons

- **J0.1** — Migration 1→2 + 3 tables + tests de schéma.
- **J0.2** — `data/portfolio.py` (validation) + tests.
- **J0.3** — `backup.py` étendu + test export/restauration.
- **J0.4** — `services/portfolio.py::positions` + tests.
- **J0.5** — Routes API + `serialize` + tests.
- **J0.6** — Front : bouton, rail, sélecteur, formulaires, tableaux + e2e.

## 8. Note de reprise

**Jalon terminé (branche `feat/portefeuille`).** Socle livré et vert.

Livré :
- `config.SCHEMA_VERSION = 2` ; `MIGRATIONS[1] = _migrate_1_to_2` (3 tables + index),
  idempotente et transactionnelle (`data/cache.py`). Fonctions SQL bas niveau ajoutées.
- `data/portfolio.py` : CRUD comptes/transactions/dividendes + validation stricte
  (date ISO, quantité > 0, prix/frais ≥ 0, sens/statut/source en liste fermée, ticker
  upper non vide, `account_id` existant). `ValueError` → 422/404 par l'API.
- `data/backup.py` : 3 tables dans `_TABLE_COLUMNS` (comptes avant enfants) ;
  `_validate_references` étendu à `account_id` ; export/purge/restauration testé.
- `engine/portfolio.py` (pur) : `positions_from_transactions` — PRU pondéré, ventes
  **long-only** (une vente excédentaire est bornée à la position), positions soldées
  écartées. Aucun import `data/`/`services/`.
- `services/portfolio.py::positions` (assemblage data + engine, vue consolidée incluse).
- `api/app.py` : routes `/api/portfolio/accounts|transactions|dividends|positions`.
- Front : bouton **Portefeuille entre Screener et ⚙ Paramètres** ; modale plein écran
  `modal-portfolio` à rail interne `pf-*` (classes distinctes du rail de fiche pour ne
  pas casser les sélecteurs e2e de #16) ; sélecteur de compte ; formulaires + tableaux.
  `portfolio.js` = mixin ; tous les `fetch` dans `api.js`.

Tests : `tests/test_portfolio_{data,engine,api}.py` (69) + `web-tests/portfolio.test.js`
(12) + `web-tests/e2e/portfolio.spec.js` (Chromium + WebKit). Suite hors réseau 463 ✅,
réseau 5 ✅ (Pernod `z = −3.81`), ruff/mypy verts, `pip-audit` propre.

**Décisions tranchées au J0** (pour les jalons suivants) :
- Positions **long-only** : pas de vente à découvert (une vente sans position est ignorée).
- **Mono-devise EUR** imposée à la création de compte (une autre devise est refusée en 422) :
  la vue consolidée « Tous » ne peut donc pas sommer des montants hétérogènes.
- Rail portefeuille **propre** (`pf-rail`), jamais `sections.js` (couplé au deep-link de fiche).
- Sections Résumé/Risque/Performance/Dividende marquées « à venir » (grisées).

**Prochaine action.** Jalon `01-resume` : `engine/portfolio.py::twr_series` (TWR chaîné
quotidien, dividendes réinvestis) + `services.portfolio.summary` + courbe vs benchmark.

**Décision différée (revue J0).** Une position **entièrement soldée** disparaît de la vue
(quantité 0 écartée) et le réalisé cumulé n'est affiché nulle part. À trancher au jalon `02`
(Positions) : ligne clôturée (quantité 0, réalisé seul) ou récapitulatif du réalisé.
