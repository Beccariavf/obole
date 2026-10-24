# #17.5 — Portefeuille · Dividendes (reçus, rendement, yield on cost)

> **Statut :** **fait** · **Priorité :** 🟡 Q2 · **Impact Pernod :** 🟢
> **Branche (historique) :** `feat/portefeuille` · **Taille :** ~1-2 sessions
> **Fiche parente :** #17 · **Précédent :** `04-performance.md` · **Suivant :** —

---

## 1. Contexte

La section `Dividende` répond à deux questions : **combien je reçois, quand, et de qui** ; et
**quel rendement cela représente** — rendement courant, mais surtout **rendement sur coût**
(yield on cost), par ligne et consolidé.

Dépend du jalon `00` (dividendes saisis, table `portfolio_dividends` avec statut
`proposed`/`confirmed`) et de `data/yahoo` (historique de dividende par action déjà exposé par
`_build_dividend` dans `data/yahoo.py`).

## 2. Objectif

Voir les dividendes **reçus** (montant, date, entreprise), le **rendement courant** et le
**yield on cost** du portefeuille et de chaque ligne ; et se voir **proposer** les versements
détectés par yfinance mais non encore saisis (« as-tu reçu ça ? »).

## 3. Non-objectifs

- Pas de calendrier prévisionnel des dividendes futurs (yfinance est limité sur l'Europe).
- Pas de fiscalité (brut/net, retenue à la source).
- Pas de simulation de réinvestissement.
- Pas de modification de la section `Dividende` de la **fiche entreprise** (chantier #16).

## 4. Exigences

- 4.1 `engine/portfolio.py::dividend_metrics(positions, dividends, prices)` : total perçu, revenu
  de l'année en cours, rendement courant (dividende TTM / valeur), **yield on cost**
  (dividendes perçus / prix de revient) — par ligne et consolidé. **Pur**.
- 4.2 `services/portfolio.py::dividends(account_id)` : assemble perçus saisis + versements détectés
  (yfinance × titres détenus à la date).
- 4.3 **Proposition** : pour chaque versement yfinance postérieur à la première détention et non
  présent en base, produire une proposition (`status = proposed`) que l'utilisateur confirme en
  un clic (`confirmed`). Jamais de confirmation automatique.
- 4.4 Front : tableau des dividendes (date, entreprise, montant, statut), graphique annuel
  (barres pleines = perçus, hachurées = attendus/proposés, patron des captures Baggr), KPI
  (versements, total perçu, revenu en cours, yield on cost, rendement courant, premier payeur).
- 4.5 Distinguer explicitement **dividende par action** (source yfinance) et **montant total
  perçu** (calculé = DPA × titres) — jamais l'un présenté pour l'autre.
- 4.6 Couleurs : bleu = bien, rouge = mal (rendement ; « -- » si non calculable).

## 5. Critères d'acceptation

- [ ] `dividend_metrics` testé : une ligne, plusieurs lignes, année incomplète
- [ ] Yield on cost = dividendes perçus / prix de revient (test sur fixture)
- [ ] Rendement courant = dividende TTM / valeur courante (test)
- [ ] Proposition : un versement yfinance non saisi apparaît `proposed` ; un clic le passe
      `confirmed` et l'intègre au total (test)
- [ ] Aucune confirmation automatique : une proposition non cliquée ne compte pas dans les perçus
- [ ] Tableau + graphique annuel (plein/hachuré) rendus
- [ ] « -- » pour un rendement non calculable (jamais 0)
- [ ] Suite hors réseau verte

## 6. Invariants préservés

- Calibration Pernod (`z = −3.81`) inchangée.
- `engine/portfolio.py` reste pur ; aucune formule dupliquée depuis `engine/valuation.py` ou
  `data/yahoo.py::_build_dividend`.
- Distinction DPA (source) vs montant total (calculé) préservée partout.
- Aucun seuil littéral côté JS.

## 7. Jalons

- **J5.1** — `dividend_metrics` + tests.
- **J5.2** — Détection + proposition (service) + tests.
- **J5.3** — Routes + `serialize`.
- **J5.4** — Front : tableau, graphique annuel, KPI, confirmation des propositions.

## 8. Note de reprise

**Livré (branche `feat/portefeuille`).** Page Dividende complète, avec un
arbitrage métier revu par rapport à la fiche initiale.

**Ce qui a changé de la spec d'origine :**

- **Pas de camembert** pour la répartition du revenu : illisible au-delà de 6 parts
  et il ne quantifie rien. Remplacé par des **barres horizontales triées** + trois
  chiffres de concentration (`N_eff = 1/Σw²`, Top N, 1er payeur).
- **« Part du dividende dans la performance » ≠ pente ajustée − pente brute.**
  L'Adj Close n'est pas une décomposition additive (le réinvestissement est fictif
  et la différence de pentes porte du bruit de régression). Mesure retenue :
  **double TWR** (`daily_values` avec puis sans dividendes, écart annualisé) — exact
  et gratuit, les prix étant déjà chargés.
- **Croissance agrégée** = moyenne des CAGR **pondérée par le poids de revenu**
  (pas par la capitalisation) ; une « DPA agrégée recalculée » serait fausse
  (quantités variables dans le temps).
- **Yield on cost = revenu TTM / coût des positions ouvertes**, pas dividendes
  cumulés / coût : le cumul gonfle mécaniquement avec l'âge de la position et ne
  serait pas comparable à la colonne « Div / coût » du tableau (DPA / PRU).
- **Double TWR exposée en entier** : `twr_with_dividends_pct` et
  `twr_without_dividends_pct` sont dans le payload ET affichés en sous-texte de la
  tuile, pour que l'écart soit vérifiable à l'écran.

**Bug corrigé au passage :** `summary()` sommait les montants **sans filtrer le
statut** — les propositions (`proposed`) entraient dans le KPI Dividendes et étaient
encaissées par `daily_values` (la courbe TWR prenait un euro jamais versé). Filtre
`confirmed` ajouté partout (`_confirmed_total`, `_confirmed_dividends`).

**Ajouts hors spec initiale, validés pendant le débat :**
- Tuile **Couverture des données** (part de la valeur couverte par un DPA connu) :
  sans elle, un yield calculé sur 2 lignes sur 12 se lit comme le yield du
  portefeuille.
- **Icône/état vide** propre et **année en cours** étiquetée « (en cours) », jamais
  remise à l'échelle sur 12 mois.

**Écarté volontairement** (décidé avec l'utilisateur) : fiscalité et effets de
change (compte PEA, pas de retenue ; le change est trop volatil pour une lecture
« nette » fiable), et le revenu forward 12 mois (hypothèse d'annualisation du
dernier DPA, non retenue pour la V1).

**Fichiers :** `engine/portfolio.py` (`dividend_income`, `income_weights`,
`income_concentration`, `dividend_metrics`, `dividend_line`),
`engine/dividends.py::ttm_per_share`, `services/portfolio.py::dividend_page` +
helper partagé `_analyze_lines`, route `GET /api/portfolio/dividend-metrics`,
`services/serialize.py::portfolio_dividend_page_to_dict`,
`config.py::PORTFOLIO_DIVIDEND_GROUPS/_POLARITY/_METRIC_UNITS`,
`web/portfolio-dividends.js`, section HTML + CSS.

**Tests :** `tests/test_portfolio_dividend_page.py` (30) et
`web-tests/portfolio-dividendes.test.js` (26).

**Revue de code (10 findings, tous traités) :**
(1) les deux graphes sont tracés après chaque chargement (`$nextTick`) ;
(2) `dividend_page` n'indexe plus `prices[tickers[0]]` mais le premier ticker
    réellement valorisable — plus de `KeyError` quand un cours échoue ;
(3) le « + » est réservé aux variations (`def.signed`), plus aux niveaux ;
(4) les tuiles s'affichent même sans versement saisi (`pfDivAllEmpty` vs
    `pfDivEmpty`) ;
(5) tri des colonnes texte corrigé (`localeCompare`) ;
(6) hauteurs de graphe en `--chart-h-pf-*` (plus de `300px` en dur) ;
(7) code mort et doublons payés : `_confirmed()` supprimée, `metrics`/`months`
    retirés du payload, `unit` retiré de la taxonomie (source unique
    `PORTFOLIO_DIVIDEND_METRIC_UNITS`) ;
(8) en-têtes de tri accessibles au clavier (`tabindex`, `aria-sort`,
    Entrée/Espace) ;
(9) yield on cost aligné sur la colonne « Div / coût » (numérateur TTM) ;
(10) les deux taux TWR sont affichés en sous-texte de la tuile de contribution.
