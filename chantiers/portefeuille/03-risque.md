# #17.3 — Portefeuille · Risque (drawdown, corrélation)

> **Statut :** **fait** · **Priorité :** 🟡 Q2 · **Impact Pernod :** 🟢
> **Branche :** `feat/portefeuille-risque` (à créer au commit) · **Taille :** ~1 session
> **Fiche parente :** #17 · **Précédent :** `02-positions.md` · **Suivant :** `04-performance.md`

---

## 1. Contexte

La section `Risque` répond à « à quel point mon portefeuille peut souffrir, et mes lignes
bougent-elles ensemble ? ». C'est la transposition des captures Baggr « Drawdown » et « Matrice
de corrélation ».

Dépend du jalon `01` (série TWR) et des prix par ligne, et de `06-etiquettes` (portée
compte/étiquette du sélecteur).

## 2. Objectif

Voir la **courbe de drawdown** du portefeuille avec ses métriques (perte maximale, baisse en
cours, durée de récupération, volatilité réalisée, meilleur/pire mois) et la **matrice de
corrélation** entre les lignes détenues, pour un périmètre sélectionnable (compte et/ou
étiquette).

## 3. Non-objectifs

- Pas de frontière efficiente ni d'optimisation de poids.
- Pas de VaR / CVaR (hors périmètre).
- Pas de corrélation au niveau ligne vs benchmark (seulement entre lignes).
- Pas de choix de période avancé (mêmes bornes que le résumé).

## 4. Exigences

- 4.1 `engine/portfolio.py::drawdown_series(values)` et `drawdown_metrics(values, dates)` : **purs**.
- 4.2 `engine/portfolio.py::correlation_matrix(returns_by_ticker, min_obs)` : matrice de
  corrélation ; les lignes sous `min_obs` observations sont **écartées** avec un badge explicite
  (jamais un zéro trompeur) — `min_obs` vient de `config.py` (`PORTFOLIO_CORR_MIN_OBS`). La
  matrice ne porte que sur les lignes **détenues aujourd'hui** (quantité > 0) : une ligne soldée
  en est exclue (retour utilisateur).
- 4.3 Métriques drawdown : perte maximale, baisse en cours, récupération la plus longue (jours),
  volatilité réalisée annualisée, meilleur mois, pire mois.
- 4.4 Front : courbe drawdown (aire **rouge**, convention projet) + benchmark (ambre) + panneau
  « Métriques de drawdown » ; matrice de corrélation en heatmap **séquentielle monochrome**
  blanc (faible) → bleu foncé (forte) — une seule teinte, « plus c'est bleu, plus les lignes
  bougent ensemble » (retour utilisateur) —, **triée par clustering** (`correlation_order`),
  annotations masquées au-delà de `PORTFOLIO_CORR_ANNOTATE_MAX` (infobulle au survol).
- 4.5 Sélecteur de périmètre (compte ET/OU étiquette, cf. `06-etiquettes`) — cohérent avec le
  reste de l'espace.

## 5. Critères d'acceptation

- [x] `drawdown_series` testé : série monotone croissante (drawdown nul), série avec un creux connu
- [x] `drawdown_metrics` : perte maximale et durée de récupération vérifiées sur fixture
- [x] `correlation_matrix` : diagonale = 1, symétrie, lignes sous `min_obs` écartées + badge
- [x] `correlation_matrix` ne contient que les lignes détenues (une ligne soldée est absente)
- [x] Cas limite : moins de 2 lignes → matrice indisponible (message, pas de crash)
- [x] Courbe + métriques rendues ; heatmap séquentielle annotée (adaptatif)
- [x] Changement de périmètre/période recalcule le risque (e2e)
- [x] Suite hors réseau verte ; `pytest -m network` vert

## 6. Invariants préservés

- Calibration Pernod (`z = −3.81`) inchangée.
- `engine/portfolio.py` reste pur ; les seuils viennent de `config.py` (aucun littéral JS).
- Palette projet : rouge pour le drawdown, bleu pour la décorrélation (pas de vert).

## 7. Jalons

- **J3.1** — `drawdown_series` / `drawdown_metrics` + `realized_volatility` + `monthly_returns`.
- **J3.2** — `correlation_matrix` + `correlation_order` (clustering) + tests.
- **J3.3** — `services.portfolio.risk` + route `/api/portfolio/risk` + `serialize`.
- **J3.4** — Front : courbe, métriques, heatmap, sélecteur ; outil MCP `get_portfolio_risk`.

## 8. Note de reprise

**Jalon terminé.** Livré sur la branche `feat/portefeuille-risque`, après `06-etiquettes`
(le sélecteur compte/tag est un prérequis).

- `engine/portfolio.py` (pur) : `drawdown_series`, `drawdown_metrics` (perte max, baisse en
  cours, plus longue récupération, dates pic/creux), `realized_volatility` (log, annualisée),
  `monthly_returns` (dé-cumulé), `log_returns_by_ticker`, `correlation_matrix`, `correlation_order`.
- Corrélation sur **rendements log quotidiens** de la fenêtre (plus réactif que mensuel, cohérent
  avec le β/ρ des ratios) ; paires sous `min_obs` points communs → `None` (jamais 0).
- **Matrice restreinte aux lignes détenues** (quantité > 0) : une ligne soldée conserve sa
  performance passée dans le TWR mais quitte la matrice (retour utilisateur).
- `services.portfolio.risk(account_id, benchmark, period, tag)` : réutilise le TWR du Résumé,
  aucun réseau supplémentaire si les cours sont en cache. `_scope_dividends` partagé.
- `api` : `GET /api/portfolio/risk` ; `serialize.portfolio_risk_to_dict`.
- MCP : `get_portfolio_risk` (payload identique à la route, testé en parité).
- Front : section **Risque** (bandeau de périmètre + période + benchmark ; courbe drawdown ;
  table des métriques portefeuille/référence ; heatmap **séquentielle monochrome**
  blanc → bleu foncé, triée par blocs, adaptative ; légende dégradé sous l'en-tête).

**Ajustements post-livraison (retour utilisateur).**
- Matrice de corrélation : n'inclut plus les lignes **soldées** (elles n'ont plus de poids, mais
  polluaient la lecture). La courbe de drawdown reste, elle, sur l'historique complet.
- Couleurs de la heatmap : passage d'une échelle **divergente** bleu↔rouge à une échelle
  **séquentielle monochrome** blanc → bleu → bleu foncé (`C.corrScale`, `zmin: 0, zmax: 1`). Une
  seule teinte : « plus c'est bleu, plus les lignes bougent ensemble ». Légende = barre de dégradé
  HTML (fiable, contrairement à la légende Plotly qui débordait du tracé).
- Résumé : nom du portefeuille + benchmark sortis du graphe → **légende HTML sous le tracé**
  (`pfSeriesLegend`) ; plus de légende Plotly superposée aux courbes.
- Drawdown : même traitement — la légende Plotly flottait en haut de la zone de tracé et
  chevauchait la ligne 0 % et les courbes → **légende HTML sous le tracé** (`pfRiskLegend`,
  pastille + nom + perte max de chaque série ; `showlegend: false`). Badge « Perte max » de
  l'en-tête retiré (redondant avec la légende) et `zeroline: false` sur les deux axes (le trait
  noir à 0 % parasitait la lecture).
- Matrice de corrélation : l'en-tête ne garde que le titre — la **légende dégradé HTML**
  (« faible → forte ») est retirée (retour utilisateur) ; la barre d'échelle Plotly de la
  heatmap reste, c'est le repère numérique de lecture.
- Matrice — design « précis » (retour utilisateur, réf. visuelle) : `xgap`/`ygap` séparent les
  cellules (grille lisible), chaque cellule de la diagonale est **détourée** (`shapes`, anneau
  `C.accentLight` — clair, lisible sur la cellule bleu nuit) et un **grain** léger (`feTurbulence`
  CSS, `opacity .07`, `mix-blend-mode: multiply`) posé au-dessus du tracé donne la profondeur
  « papier ». Passer à des **axes numériques** (0..n-1, libellés = tickers) a été nécessaire pour
  aligner les formes de la diagonale sur les cellules.
- Matrice — **échelle recalée sur le bleu de l'interface** (retour utilisateur : cohérence de
  couleur) : le pôle haut de `C.corrScale` est `C.accent` (#2563EB, le bleu des boutons), donc
  corrélation 1,0 = bleu de référence du produit, dégradé blanc → ce bleu. Anneau de diagonale
  `C.accentLight` (#BFDBFE). Le libellé de corrélation moyenne est, lui aussi, en `var(--accent)`.
- Matrice — **corrélation moyenne** du périmètre affichée à droite du titre
  (`risk.corr_avg`, calculé SERVEUR — `engine.mean_offdiagonal`) : « 9 lignes · corrélation
  moyenne +0,17 ». Reflète le compte/étiquette sélectionné, puisqu'elle lit la matrice scopée.
- Bandeau Risque : le libellé de périmètre figé est remplacé par un **sélecteur de périmètre
  sur place** (compte + étiquette, réutilisant `setPortfolioAccount`/`setPortfolioTag`) — la
  portée se choisit sans remonter à l'en-tête de la modale. Bug latent corrigé au passage :
  l'attribut `class="pf-risk-bench x-text=…"` avalait la directive, le « vs _benchmark_ » du
  bandeau n'était **jamais** rendu (désormais `class` et `x-text` séparés, couvert par l'e2e).

**Ajout — Test de corrélation (sous la matrice).** Un champ sous la matrice où l'on saisit un
ticker candidat ; renvoie **une ligne** (heatmap 1×N, même échelle `C.corrScale`, alignée sous
les colonnes de la matrice) donnant sa corrélation à chaque ligne détenue, plus l'**impact
global** sur la corrélation moyenne du périmètre (`current_avg` → `new_avg`, delta signé ;
baisse = bleu/diversification, hausse = rouge/redondance).

- `engine/portfolio.py` : `correlation_row` (corrélation d'une cible vs plusieurs séries, ordre
  gardé) et `mean_offdiagonal` (moyenne hors diagonale, `None` ignorés) — purs.
- `services/portfolio.py` : refactor — `_risk_context` (entrées communes : cours, fenêtre, TWR,
  lignes) et `_correlation_block` (rendements + matrice réordonnée) partagés par `risk()` et le
  nouveau `correlation_test()` ; ce dernier réutilise l'ordre de clustering de la matrice (la
  ligne s'aligne). `ValueError` → 422 : ticker vide / introuvable / déjà détenu / périmètre sans
  ligne. Aucun réseau supplémentaire si les cours sont en cache.
- API : `GET /api/portfolio/risk/correlation-test` ; `serialize.portfolio_correlation_test_to_dict`.
- MCP : `test_portfolio_correlation` (payload identique à la route, testé en parité).
- Front : `api.portfolioCorrelationTest` (seul `fetch`) ; `portfolio.js` — **recherche par NOM
  OU code** (`onCorrTestInput` → `/api/search`, suggestions cliquables réutilisant le style de
  la barre principale) : un code exact testé directement, sinon l'utilisateur choisit un ticker
  dans la liste (évite l'erreur parasite pendant la frappe d'un nom) ; **jeton anti-course**
  (`_pfCorrTestSeq` : une réponse périmée — champ vidé, ticker/portée changés entre-temps — est
  ignorée), `pfCorrTestImpact` (libellé + polarité) et `drawCorrTestRow` (ruban 1×N). Hauteur via
  `config.CHART_HEIGHT_PORTFOLIO_CORR_TEST` → `/api/meta` → `thresholds.js` (parité verrouillée).
- **Source unique** de la corrélation moyenne : `risk()` expose `corr_avg`
  (`engine.mean_offdiagonal`) ; le front lit `pfRisk.corr_avg` au lieu de recalculer la moyenne
  hors diagonale en JS (fin du doublon de logique serveur/client).

