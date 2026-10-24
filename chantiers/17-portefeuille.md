# #17 — Portefeuille (positions, risque, performance, dividendes)

> **Statut :** en cours — J0, J1, J3, J4, J5, J6, J7 ✅ · **J2 (positions) restant** · **Priorité :** 🟡 Q2 (important, non urgent — cas (c) évolutivité)
> **Impact Pernod :** 🟠 (indirect — J4 touche le graphe héro de la fiche) · **Branche :** `feat/portefeuille` · **Taille :** 7 jalons
> **Fiche parente :** — (chantier racine) · **Dépend de :** #15 (`services/`), #16 (patron rail)
> **Cible MCP :** **MCP-B** (`PRD.md` §10, §12.2 famille 2 n°3) — le portefeuille est
> **acté** au PRD, mais il n'avait **aucune fiche** : c'est celle-ci.

---

## 1. Contexte

`PRD.md` §10 acte la brique **Portefeuille (MCP-B)** : « l'IA remplit les positions depuis un doc
de transactions ». `PRD.md` §12.2 la classe dans la famille 2 (« écriture & calcul pilotés par
l'IA ») et §12.4 laisse **ouvert** le point Q4 : *« modèle de données du portefeuille
(transactions vs positions, devises, frais) »*. Cette fiche **tranche Q4**.

Le cadrage produit de la refonte de fiche (`amélioration/docs/product/prd.md`, non versionné)
déclare le portefeuille **hors périmètre** de la roadmap « fiche entreprise » — ce n'est pas une
contradiction : le portefeuille est un **espace distinct**, pas une section de fiche. La
contradiction de périmètre entre les deux PRD est traitée par le chantier #10.

Faits observés dans le code (points d'ancrage de l'implémentation) :

- **Persistance** : `src/obole/data/cache.py` — SQLite mono-fichier, schéma versionné par
  `PRAGMA user_version` + `config.SCHEMA_VERSION` (= **1**) et le dict `MIGRATIONS`
  (`cache.py::MIGRATIONS`). Toute nouvelle table = **migration 1 → 2**.
- **Sauvegarde** : `src/obole/data/backup.py::_TABLE_COLUMNS` énumère les
  tables utilisateur ; toute table ajoutée doit y figurer, sinon elle est absente de l'export.
- **Couches** : `web → api → services → engine → data` (`CLAUDE.md` §Architecture). `engine/`
  est **100 % pur** (zéro I/O), `data/` est la seule couche réseau/disque.
- **Prix** : `src/obole/data/yahoo.py::fetch_prices` (retry + dégradation gracieuse) — déjà en
  cache, donc le calcul de performance ne coûte **aucun** appel réseau supplémentaire.
- **Patron de vue** : `src/obole/web/sections.js` (chantier #16) porte un registre de sections +
  un mixin de navigation à deep-link. À réutiliser tel quel pour la vue Portefeuille.
- **Modale plein écran** : le Screener (`src/obole/web/index.html`, bloc `modal-overlay`) est le
  patron d'une surface qui n'est pas une fiche ; le Portefeuille suivra le même esprit mais avec
  un **rail interne**.

## 2. Objectif

Pouvoir **saisir ses lignes de portefeuille** (achats, ventes, dividendes, rattachés à une
entreprise suivie par yfinance) dans un **espace dédié**, séparé en **plusieurs comptes**, et
voir sa **performance TWR** face à un benchmark choisi, sa **répartition**, son **risque**
(drawdown, corrélation), ses **rendements mensuels** et ses **dividendes** (reçus et
yield-on-cost).

Le but à terme : que l'IA, via le **MCP**, remplisse seule ces lignes depuis un document de
transactions fourni — d'où l'exigence que toute l'orchestration vive dans
`services/portfolio.py`, réutilisable par l'API **et** par le MCP.

## 3. Non-objectifs

- **Pas de multi-devise** : mono-devise **EUR** assumée. Un ticker non-EUR reçoit un **badge de
  fiabilité** (`warnings`), jamais une conversion silencieuse. La conversion est un jalon futur.
- **Pas de flux de trésorerie / apports-retraits** (la 6ᵉ section Baggr) : hors périmètre.
- **Pas d'optimisation de portefeuille** (frontière efficiente, poids cibles) : hors périmètre.
- **Pas de réécriture de la méthode** : aucune formule ni seuil dupliqué ; tout ce qui est
  numérique vient de `engine/` et `config.py`.
- **Pas de parsing de document côté serveur** : c'est l'IA (MCP-B) qui structure, le serveur
  valide et persiste (`PRD.md` §12.2).
- **Pas de modification de `api/app.py` au-delà du montage** des nouvelles routes : le MCP ne
  passe pas par HTTP.

## 4. Exigences

### 4.1 Modèle de données (tranche Q4)

- 4.1.1 **Transactions = source de vérité** ; les positions sont **recalculées**, jamais saisies.
- 4.1.2 Table `portfolio_accounts` : `id`, `name`, `currency` (défaut `EUR`), `created_at`.
- 4.1.3 Table `portfolio_transactions` : `id`, `account_id` (FK → `portfolio_accounts`,
  `ON DELETE CASCADE`), `ticker`, `side` (`buy` | `sell`), `trade_date` (ISO), `quantity`
  (> 0), `price` (≥ 0), `fees` (≥ 0, défaut 0), `currency`, `note` (nullable), `created_at`.
- 4.1.4 Table `portfolio_dividends` : `id`, `account_id` (FK), `ticker`, `pay_date` (ISO),
  `amount` (total perçu, ≥ 0), `status` (`proposed` | `confirmed`), `source`
  (`manual` | `yahoo`), `created_at`.
- 4.1.5 Migration **1 → 2** : `MIGRATIONS[1] = _migrate_1_to_2` dans `data/cache.py`,
  `config.SCHEMA_VERSION = 2`. Idempotente (`CREATE TABLE IF NOT EXISTS`), transactionnelle.
- 4.1.6 `data/backup.py::_TABLE_COLUMNS` étendu aux 3 tables (ordre : comptes **avant** leurs
  enfants) ; la purge de cache n'y touche pas.

### 4.2 Couches

- 4.2.1 `data/portfolio.py` : I/O + **validation** (dates ISO, quantités > 0, ticker non vide,
  sens valide, montants ≥ 0). Lève `ValueError` (l'API la transforme en 422).
- 4.2.2 `engine/portfolio.py` : **100 % pur** (numpy/pandas). Aucun import de `data/` ni
  `services/`.
- 4.2.3 `services/portfolio.py` : orchestration (prix via `data/yahoo`, benchmark, assemblage).
  Point d'entrée **unique**, partagé API ↔ MCP.
- 4.2.4 `api/` : routes + `serialize.py` ; `api/` reste une frontière fine (validation HTTP +
  sérialisation), il n'appelle jamais `engine/` en direct.
- 4.2.5 `src/obole/web/portfolio.js` (mixin) + `api.js` (tous les `fetch`) + `thresholds.js`
  (seuils).

### 4.3 Calculs (`engine/portfolio.py`, purs)

- 4.3.1 **Positions** : quantité, prix de revient moyen (PRU), valeur au dernier cours, plus/moins
  value latente et réalisée, poids en % du portefeuille.
- 4.3.2 **TWR chaîné quotidien** (cf. §6) : série de performance cumulative, comparable à un
  benchmark.
- 4.3.3 **Drawdown** : série `(valeur / plus-haut-cumulé − 1)` + métriques (perte max, durée de
  récupération la plus longue, volatilité réalisée, meilleur/pire mois).
- 4.3.4 **Matrice de corrélation** : corrélation des rendements mensuels entre lignes ; les
  lignes sous un minimum d'observations sont **écartées** (badge explicite, jamais un zéro).
- 4.3.5 **Rendements mensuels** : table année × mois du portefeuille, avec le benchmark en
  regard.
- 4.3.6 **Yield on cost** : dividendes perçus / prix de revient, par ligne **et** portefeuille.

### 4.4 Interface

- 4.4.1 Bouton **Portefeuille** dans la barre, **entre `Screener` et `⚙ Paramètres`**
  (`src/obole/web/index.html`, barre `.searchbar`).
- 4.4.2 Vue plein écran à **rail interne** (patron `sections.js`) : `Résumé · Positions ·
  Risque · Performance · Dividende`.
- 4.4.3 **Sélecteur de compte / portefeuille** (vue consolidée « Tous » + un compte).
- 4.4.4 Saisie/édition des transactions et dividendes depuis l'UI (formulaire + tableau).
- 4.4.5 **Proposition de dividende** : pour chaque ligne détenue, si yfinance signale un
  versement non saisi, proposer « as-tu reçu ça ? » → un clic confirme et intègre.
- 4.4.6 Benchmark = **n'importe quel ticker/ETF yfinance** (champ de recherche + autocomplétion).

### 4.5 Cohérence MCP (MCP-B)

- 4.5.1 `services/portfolio.py` est le **seul** point d'entrée : le MCP l'appellera sans
  dupliquer d'orchestration.
- 4.5.2 L'import de transactions venu de l'IA est **hostile par défaut** : validation stricte
  (§4.2.1) avant persistance.
- 4.5.3 **Aucun seuil** dupliqué : tout nombre/borne vient de `config.py`.

## 5. Critères d'acceptation

- [ ] `config.SCHEMA_VERSION == 2` ; migration 1→2 idempotente et atomique (test dédié)
- [ ] Les 3 tables existent après ouverture d'une base neuve **et** d'une base v1 (test)
- [ ] `backup.py::_TABLE_COLUMNS` couvre les 3 tables ; export → purge → restauration conserve
  les lignes (test, miroir de `tests/test_backup.py`)
- [ ] `data/portfolio.py` rejette une date invalide, une quantité ≤ 0, un sens inconnu (tests)
- [ ] `engine/portfolio.py` : TWR, drawdown, corrélation, mensuels, yield-on-cost testés sur
  fixtures déterministes (cas nominal + bornes : 1 seule transaction, compte vide, vente seule)
- [ ] `grep` : aucun import de `data/` ni `services/` dans `engine/portfolio.py`
- [ ] Routes `/api/portfolio/*` (comptes, transactions, dividendes, résumé, positions, risque,
  performance) + sérialisation ; 422 sur entrée invalide
- [ ] Bouton Portefeuille entre `Screener` et `⚙ Paramètres` ; rail interne + sélecteur de compte
- [ ] `web-tests/modules.test.js` étendu : `portfolio.js` exporte un mixin, 0 `fetch` hors `api.js`
- [ ] Benchmark sélectionnable par ticker arbitraire ; proposition de dividende fonctionnelle
- [ ] Suite hors réseau verte ; **`pytest -m network` vert** (impact 🟠, J4)
- [ ] Aucun seuil littéral ajouté au JS (`config.py` → API = source unique)

## 6. Invariants préservés

- **La calibration Pernod (`z = −3.81`, ±0.15) reste verte.** J4 ajoute des marqueurs au graphe
  héro de la fiche : la droite de régression, ses bandes et les trois lieux de calcul
  (serveur, `drawChart`, `computeLive`) restent **inchangés**.
- **TWR chaîné quotidien, dividendes réinvestis au cours de clôture du jour de paiement**
  (Total Return). C'est la définition retenue : les flux (achat/vente/dividende) **délimitent
  les sous-intervalles** du chaînage, ce qui rend le résultat insensible au montant et au
  timing des apports — c'est la propriété qui distingue le TWR d'un simple rendement.
- **Les couches ne se contournent pas** : `engine/` reste pur, `data/` reste seule couche I/O,
  `api/` reste fin.
- **Les seuils restent exclusivement dans `config.py`** (exposés au front par l'API) : le
  portefeuille n'introduit **aucun** seuil littéral.
- **Les données utilisateur survivent** : schéma versionné + sauvegarde/restauration étendues.
- **Le MCP ne touche jamais `web/` ni `api/app.py`** (`PRD.md` §12.3).

## 7. Jalons

Chaque jalon laisse le dépôt dans un état **vert** (lint + types + tests hors réseau).
**6 sous-fiches**, une par jalon (`chantiers/portefeuille/`), chacune avec exigences numérotées
et critères d'acceptation propres.

- **J0 — Socle persistant + saisie.** Migration 1→2, 3 tables, `data/portfolio.py` (validation),
  `backup.py` étendu, CRUD comptes/transactions/dividendes (API + `src/obole/web/portfolio.js`),
  bouton dans la barre, vue à rail interne, sélecteur de compte, tableau des positions brutes.
  → fiche `portefeuille/00-socle.md`
- **J1 — Résumé.** Courbe TWR vs benchmark + top 5 / flop 5 positions.
  → fiche `portefeuille/01-resume.md`
- **J2 — Positions.** Tableau complet (taille, PRU, +/- value, poids) + lecture « comme une
  entreprise » (agrégats consolidés).
  → fiche `portefeuille/02-positions.md`
- **J3 — Risque.** Drawdown + matrice de corrélation, sélecteur de portefeuille.
  → fiche `portefeuille/03-risque.md`
- **J4 — Performance.** Benchmark + dates (YTD, 1A, 3A, 5A, MAX) + tableau des rendements
  mensuels vs benchmark + **points d'entrée/sortie** (marqueurs sur le graphe héro de la fiche,
  à cocher, rétrospective « ai-je battu le benchmark depuis ce point ? »).
  → fiche `portefeuille/04-performance.md`
- **J5 — Dividendes.** Reçus (montant, quand, par entreprise), rendement courant,
  **yield on cost** portefeuille + par ligne, proposition « as-tu reçu ça ? ».
  → fiche `portefeuille/05-dividendes.md`

> **Hors des 7 jalons (rattaché au chantier #09).** La **surface MCP-B** (outils d'import et
> de lecture adossés à `services/portfolio.py`) n'est pas développée dans cette branche, mais
> l'architecture la prépare (§4.5).
>
> **Impact Pernod.** J0 → J4 sont 🟢 (aucun contact avec le calcul de la fiche) **sauf** les
> marqueurs d'entrée/sortie de J4, qui touchent le graphe héro → 🟠, `pytest -m network`
> obligatoire à ce jalon.

## 8. Note de reprise

**État au démarrage** (`feat/portefeuille` créée depuis `main` propre). Aucun code écrit.
Les décisions de cadrage sont tranchées :

| Sujet | Décision |
|---|---|
| Modèle | **Transactions** = source de vérité ; positions recalculées |
| Dividendes | **Saisie manuelle** + **proposition** depuis yfinance × titres détenus |
| Devises | **Mono-devise EUR** ; non-EUR = badge, pas de conversion |
| Benchmark | **N'importe quel ticker/ETF yfinance** |
| TWR | **Chaîné quotidien**, dividendes réinvestis au cours du jour |
| Placement | Bouton **entre `Screener` et `⚙ Paramètres`** |
| Rail | Patron `sections.js` (#16) réutilisé, 5 sections internes |

**Prochaine action.** J0 : ajouter la migration 1→2 et les 3 tables dans `data/cache.py`, créer
`data/portfolio.py` (validation) et étendre `data/backup.py`, avec leurs tests.

**Prérequis réglé.** Le travail non commité de `feat/resume-fiche` (étape 2 du #16) a été commité
puis intégré sur `main` avant d'ouvrir `feat/portefeuille` — c'est reparti d'une base propre (règle
d'or : un chantier par branche).

**Mise à jour (après J3 et J6).** Deux jalons livrés depuis :

- **J6 — Étiquettes / portefeuilles virtuels** (`chantiers/portefeuille/06-etiquettes.md`,
  branche `feat/portefeuille-tags`) : `tag` nullable sur les transactions (schéma **v7**),
  filtre compte ET/OU étiquette sur tout l'espace, sélecteur de portefeuille virtuel, MCP
  (`list_portfolio_tags`, `tag` sur transactions/positions/résumé). Prérequis du sélecteur
  de périmètre.
- **J3 — Risque** (`chantiers/portefeuille/03-risque.md`, branche `feat/portefeuille-risque`) :
  drawdown (aire rouge + benchmark) et matrice de corrélation (heatmap divergente triée par
  clustering, adaptative), sur la portée compte/étiquette. Outil MCP `get_portfolio_risk`.

Reste : **J2 (Positions)** — seul jalon non livré.

**Ordre des onglets (retour utilisateur).** Réordonnés pour la logique de lecture
**Résumé → Risque → Performance → Dividende → Positions** : les vues d'analyse d'abord, la
saisie (Positions) **tout à droite**, à côté de Dividende — c'est un écran de consultation,
la saisie n'est pas l'entrée principale. `PORTFOLIO_SECTIONS` porte cet ordre (source unique,
nav `x-for`), verrouillé par `web-tests/portfolio.test.js` et l'e2e.


**Mise à jour (J7 — bandeau de contexte unifié).** Le périmètre était recopié **cinq fois** avec
des variantes : en-tête de modale, `.pf-risk-head`, `.pf-perf-head`, `.pf-div-head`, plus le
sélecteur local de la modale « détail par titre » — et le Risque affichait une référence en texte
mort (`vs MSCI World`) qu'on ne pouvait pas changer sur place.

Livré (branche `feat/portefeuille-perimetre-unifie`) :

- **Un seul `.pf-context`** collant sous les onglets : trois groupes `PÉRIMÈTRE · PÉRIODE ·
  BENCHMARK`, hauteur unique 34 px (les chips mesuraient 26 px, les selects 44 px, les boutons
  34 px). Les quatre bandeaux d'onglet, leurs classes CSS et le périmètre de l'en-tête ont été
  **supprimés**.
- **Registre de capacités** `SECTIONS_CONTROLS` (`portfolio.js`) : un contrôle sans objet pour la
  section n'est pas rendu — Positions → périmètre ; Résumé/Risque → les trois ; Performance → sans
  période (MAX par principe) ; Dividende → sans période ni benchmark.
- **Rechargement par section** : `reloadActiveSection()` + `SECTION_LOADERS` remplacent les
  `if (section === « risque ») …` en cascade. Une section masquée ne paie plus d'appel réseau.
- **Période persistée** (`portfolio_period` dans `SETTING_DEFS`, liste fermée via une clé
  `choices` lue par `cache._setting_valid`), comme le benchmark.
- **Popover « ticker libre »** ancré dans le bandeau (plus de `modal-overlay-stacked`, donc un
  seul niveau de focus), `Escape` ferme et restitue le focus.
- **Modale « détail par titre »** : plus de sélecteur de benchmark — elle hérite du benchmark
  global, et se recharge si le contexte change pendant qu'elle est ouverte.
- Tests : `web-tests/portfolio-resume.test.js` (capacités, bandeau unique, rechargement ciblé),
  unitaires Performance mis à jour, et deux e2e dédiés (hauteur unique, `position: sticky`,
  capacités par onglet). `ruff`/`mypy`/`pytest -m "not network"`/`npm test` verts.

Reste : J2 (Positions). Note : `web-tests/e2e/dividende.spec.js` « Shareholder Yield » échoue
**déjà sur `main`** (sélecteur `.div-warnings` ambigu, deux conteneurs) — dette de test
indépendante de ce chantier.
