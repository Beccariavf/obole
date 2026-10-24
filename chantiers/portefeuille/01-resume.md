# #17.1 — Portefeuille · Résumé (TWR vs benchmark, top/flop)

> **Statut :** **fait** (J1) · **Priorité :** 🟡 Q2 · **Impact Pernod :** 🟢
> **Branche (historique) :** `feat/portefeuille-resume` · **Taille :** ~1 session
> **Fiche parente :** #17 · **Précédent :** `00-socle.md` · **Suivant :** `02-positions.md`

---

## 1. Contexte

La section `Résumé` est la page d'accueil de l'espace Portefeuille : elle doit donner en un
coup d'œil la performance face au marché et les extrêmes du portefeuille. C'est la transposition
de la capture Baggr « Performance (TWR) » + « top 5 / flop 5 ».

Dépend du jalon `00` (transactions saisies) et du module pur `engine/portfolio.py` (TWR, cf.
fiche parente §4.3.2 et §6).

## 2. Objectif

Voir une courbe de **performance TWR cumulative** du portefeuille comparée à un **benchmark**,
avec 4 KPI (valeur totale, total return, TRI annualisé, dividendes) et les **5 meilleures** /
**5 moins bonnes** positions.

## 3. Non-objectifs

- Pas de tableau mensuel détaillé (jalon `04-performance`).
- Pas de drawdown ni de corrélation (jalon `03-risque`).
- Pas de détail par position au-delà du top/flop (jalon `02-positions`).
- Pas de choix de période avancé : YTD / 1A / 3A / 5A / MAX suffisent ici.

## 4. Exigences

- 4.1 `engine/portfolio.py::twr_series(flows, prices_by_ticker)` : **pur**, chaînage quotidien
  (cf. §6 de la fiche parente).
- 4.2 `services/portfolio.py::summary(account_id, benchmark, period)` : assemble TWR portefeuille
  + TWR benchmark (prix via `data/yahoo`).
- 4.3 Courbe : portefeuille (bleu, `C.accent`) + benchmark (ambre), area fill 6-8 % sous le
  portefeuille (convention projet).
- 4.4 4 KPI : valeur totale (+ montant investi), Total Return, TRI annualisé, dividendes perçus
  (+ rendement).
- 4.5 Top 5 / flop 5 : positions triées par performance relative, avec lien vers la fiche.
- 4.6 Sélecteur de période (YTD / 1A / 3A / 5A / MAX) et de benchmark.
- 4.7 Couleurs sémantiques projet : **bleu = bien, rouge = mal** (jamais vert/rouge).

## 5. Critères d'acceptation

- [ ] `twr_series` testé : cas nominal, un seul flux, aucun flux (série plate), flux multiples
- [ ] TWR insensible au montant des apports (test : doubler un apport ne change pas le TWR)
- [ ] Dividendes inclus dans le rendement (test avec un versement connu)
- [ ] Courbe portefeuille + benchmark tracée ; aire sous la courbe portefeuille
- [ ] 4 KPI corrects ; « -- » si non calculable (jamais 0)
- [ ] Top 5 / flop 5 cohérents avec les positions ; clic ouvre la fiche de la valeur
- [ ] Changement de période/benchmark recalcule la courbe (e2e)
- [ ] Suite hors réseau verte

## 6. Invariants préservés

- Calibration Pernod (`z = −3.81`) inchangée.
- `engine/portfolio.py` reste pur (aucun import `data/`/`services/`).
- Aucun seuil littéral côté JS : périodes et bornes viennent de `config.py` via l'API.
- Palette projet respectée (bleu/rouge, jamais vert/rouge).

## 7. Jalons

- **J1.1** — `twr_series` + tests.
- **J1.2** — `services.portfolio.summary` + route + `serialize`.
- **J1.3** — Courbe + KPI (front).
- **J1.4** — Top 5 / flop 5.

## 8. Note de reprise

**Jalon terminé (branche `feat/portefeuille-resume`).** Résumé livré et vert.

**Convention TWR retenue (décisions actées).**
- Flux **externes** = achats (apport +) / ventes (retrait −) : ils délimitent les
  sous-intervalles du chaînage → TWR **insensible au montant ET au calendrier**
  des apports (testé).
- **Dividende = gain interne** (reste en trésorerie du compte) : il augmente la
  valeur sans être un flux → **inclus** dans le rendement.
- Chaînage en **fin de séance** : `r_t = (V_t − F_t) / V_{t−1} − 1` (un achat est
  exécuté au cours de clôture ; la somme nouvelle ne participe pas au rendement
  du jour).
- **« TRI » de la maquette = CAGR du TWR** sur la fenêtre (`annualized_return`).

**Livré.**
- `engine/portfolio.py` (pur) : `daily_values`, `twr_series`, `benchmark_series`,
  `period_start_index`, `period_return`, `annualized_return`, `top_flop`.
- `config.py` : `PORTFOLIO_BENCHMARKS` (7 ETF UCITS EUR : CW8.PA, ESE.PA, ETZ.PA,
  MSE.PA, CACC.PA, ANX.PA, PAEEM.PA), `PORTFOLIO_BENCHMARK_DEFAULT = "CW8.PA"`,
  `PORTFOLIO_PERIODS`, `PORTFOLIO_PERIOD_DEFAULT`, `PORTFOLIO_TOP_N`. Réglage
  **texte** `portfolio_benchmark` (dernier choix = norme) ; `cache.get_settings`/
  `set_settings`/`_setting_valid` élargis aux valeurs `str` (bornes = longueur).
  Le groupe `portefeuille` n'est **pas** listé dans `SETTING_GROUPS` (le réglage
  se pilote depuis la section Résumé, pas depuis la modale Paramètres).
- `services/portfolio.py::summary(account_id, benchmark, period)` : TWR + courbe
  benchmark + 4 KPI + répartition par compte + Top/Flop + métadonnées de compte.
- `api/` : `GET /api/portfolio/summary` (422 période/ticker invalide),
  `GET /api/portfolio/benchmarks`, `serialize.portfolio_summary_to_dict`.
- Front : onglet **Résumé** livré et **section par défaut** ; 3 cartes KPI, courbe
  TWR + benchmark (aire sous le portefeuille), **donut répartition des comptes**,
  **Top 5 / Flop 5** cliquables, **bandeau compte**. Zoom **plein écran** via un
  état **propre** (`pfChartFull` + `#pf-detail-modal`, classe `modal-pf-detail`
  distincte de `modal-detail` pour ne pas capturer les sélecteurs e2e du héro).
  Sélecteur benchmark (liste curée + ticker libre) et période (chips) ; dernier
  benchmark **mémorisé**. Aucun seuil littéral (tout vient de l'API).

Tests : `tests/test_portfolio_twr.py` (29) + `tests/test_portfolio_summary.py` (23)
+ `web-tests/portfolio-resume.test.js` (27) + e2e `portfolio.spec.js` (4, Chromium
+ WebKit). Suite hors réseau **566 ✅**, réseau **5 ✅** (Pernod `z = −3.81`),
`ruff`/`mypy` verts, Vitest **194 ✅**, e2e **46 ✅**.

**Correctifs de revue (post-livraison).**
- Sélecteur de benchmark : retrait de `x-model` (Alpine mettait à jour
  `pfBenchmark` avant `@change`, ce qui faisait sortir `setPfBenchmark` sur son
  garde-fou → aucun recalcul). Valeur pilotée par `:value` + `@change`.
- TWR : les flux d'un ticker **non valorisable** (sans cours) sont ignorés — ils
  ne sont plus comptés comme apport, ce qui faisait plonger la courbe (−90 % avec
  un achat fantôme). Test `test_unpriceable_ticker_flows_are_ignored`.
- `period_start_index` : jour **clampé** (un 29/02 reculé vers une année non
  bissextile levait « day is out of range for month » → 500). Test dédié.
- Chips de période : la courbe est désormais **découpée à `period_start`** (avant,
  seul le badge/KPI changeait, pas le tracé).
- `pfPerfBadge()` : compare au **benchmark** (rouge si sous-performance), plus à 0.
- Noms Top/Flop résolus **uniquement pour les lignes affichées** (plus d'appel
  `info` par position du portefeuille à chaque Résumé).
- Bandeau compte : badge « PRO » codé en dur retiré ; « Solde » renommé
  « Dividendes nets de frais » (les achats ne débitent pas la trésorerie, non
  modélisée) ; Flop masqué quand il duplique le Top.
- **Donut « Répartition des comptes » recentré (correctif #17.1).** Le tracé
  laissait Plotly dimensionner le SVG : il le **figeait à la largeur du premier
  rendu** (700 px) et le disque se décalait à gauche dès que la carte changeait
  de largeur (repli média 1 colonne → −39 px ; fenêtre ≥ 2 500 px → −86 px).
  Correctif : layout **explicite** (`width`/`height` mesurés sur le conteneur,
  `margin` nulles, `domain` plein cadre → centre du disque = centre du SVG) +
  **`ResizeObserver`** (`_pfObserveDonut`, feature-détecté, garde anti-boucle sur
  la largeur, `disconnect()` dans `closePortfolio`) car `responsive: true` de
  Plotly n'écoute que `window.resize`, pas le conteneur. Tests : `e2e` mesure le
  centre du disque (±2 px) avant/après repli média ; Vitest vérifie le layout et
  l'observateur (jsdom sans `ResizeObserver` ne lève pas).
- **Libellés du donut replacés DANS le disque.** Une fois le SVG collé à la
  largeur du conteneur, les noms de comptes longs des parts étroites débordaient
  (Plotly met `overflow: hidden` sur le `svg`) : mesuré jusqu'à **−77 px** hors
  cadre avec 5 comptes (« Assurance Vie Linxea… », « PEE Entreprise… »). Passage
  à `textposition: "inside"` + `insidetextorientation: "horizontal"` : plus rien
  ne sort du cadre (0 libellé rogné), disque toujours centré et plein. Le e2e
  vérifie l'absence de rognage ; le Vitest verrouille les deux options de trace.

**Décisions prises pendant le jalon (pour les suivants).**
- Donut « Répartition des comptes » **inclus** dans ce jalon (demande utilisateur).
- Le **dernier benchmark choisi est la norme** (persisté), pas de nouveau champ UI
  dans la modale Paramètres.
- Le résumé est **la page d'accueil** du portefeuille (l'onglet Positions reste
  la saisie).

**Prochaine action.** Jalon `02-positions` : tableau complet (taille, PRU,
+/- value, poids) + lecture « comme une entreprise » (agrégats consolidés).
Reste à trancher (décision différée du J0) : afficher une ligne clôturée
(quantité 0, réalisé seul) ou un récapitulatif du réalisé.

