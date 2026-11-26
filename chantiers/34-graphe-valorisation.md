# #34 — Graphe « Prix et valorisation » à couches

> **Statut :** en cours · **Priorité :** 🟡 Q2 · **Impact Pernod :** 🟢
> **Branche proposée :** `feat/graphe-valorisation` · **Taille :** ~1 session

> **Convention de traçabilité.** La branche est un **repère de travail**, pas une preuve : elle
> n'est annotée « Branche (historique) » qu'une fois le chantier **clos** (jamais tant qu'il reste
> des jalons). Ne jamais citer de SHA — cf. `CLAUDE.md` §Workflow git.

---

## 1. Contexte

La vue « Graphique » de la calculatrice de prix juste (`web/valorisation.js::drawValuationChart`,
conteneur `#val-chart` dans `index.html`) superpose, sur tout l'historique (25 ans) :
le cours brut, la valorisation (métrique/action × multiple médian, en or, fond doré jusqu'à
zéro), une ligne horizontale du prix juste sur toute la largeur, la projection pointillée et
le dividende/action en ligne brune **sur l'échelle du prix**. Constat sur LVMH : la
valorisation (4 exercices de comptes) est écrasée à droite, le dividende est une ligne plate
illisible, le prix juste est tracé dans le passé alors que c'est un prix d'achat actuel, et
deux badges bleus identiques désignent deux choses différentes.

Une maquette validée avec l'utilisateur (variante « M2 affinée »), éprouvée sur dix titres
(MC, OR, RMS, UBI, AIR, KER, TTE, ALO, VK ; BNP sans calculatrice), a révélé quatre pièges
d'affichage, intégrés aux exigences ci-dessous : métrique courante négative (UBI), croissance
par défaut aberrante qui envoie la projection hors cadre (KER, 268 %/an), dividende de
l'année en cours partiel, et dates coincées entre les deux étages.

## 2. Objectif

Une carte « Prix et valorisation » lisible d'un coup d'œil : où est le cours par rapport à
sa valorisation (couloir bleu sous-évalué / rouge sur-évalué), ce que donnent les hypothèses
à 5 ans (scénario central, éventail optionnel), et la progression du dividende (bâtons verts
dans un étage dédié).

## 3. Non-objectifs

- Aucun changement des formules de la calculatrice (`targetEntryPrice`, `estimatedReturn`,
  `projectedValue`, miroirs serveur) ni de la Matrice.
- Pas de correction de la croissance par défaut (le 268 %/an de Kering est un constat, traité
  à part) : le graphe doit seulement rester lisible quand elle est aberrante.
- Pas de nouvelle donnée serveur : tout est déjà dans le payload (`chart.*_ps`,
  `fundamentals.valuation_calc`).
- Pas de persistance des couches allumées (état du composant, remis au défaut au rechargement).

## 4. Exigences

- 4.1 **Fenêtre** : les `VALUATION_CHART_YEARS` (10) dernières années + l'horizon
  `VALUATION_HORIZON_YEARS` (5). Zone future très légèrement teintée, trait « aujourd'hui »,
  libellés `aujourd'hui` et `horizon 5 ans` en haut.
- 4.2 **Couleurs** : trois familles seulement. Bleu `C.accent` = cours et prix juste ; ambre
  `C.valo` (nouveau jeton `#D97706` dans `theme.js`) = valorisation, projection, éventail ;
  vert `C.teal` (`#0D9488`) = dividende. Bleu/rouge (`C.good`/`C.bad`) uniquement en jugement
  (couloir, statut, pied). Aucune légende Plotly (`showlegend: false`).
- 4.3 **En-tête de carte** : titre « Prix et valorisation » et ligne de statut
  « Cours X · valorisation Y · sous-évalué de Z % » (bleu si sous, rouge si sur). Au-delà de
  `VALUATION_GAP_RATIO_LIMIT` (100 %) d'écart, on écrit « sur-évalué (cours ×N) ». Métrique
  courante ≤ 0 : « valorisation non calculable (<label> négatif) ». Multiple d'entreprise
  (EV/EBITDA) : pas de valorisation, pas de statut.
- 4.4 **Légende-interrupteurs** (pastilles HTML au-dessus du graphe, pas Plotly) :
  « Cours » et « Valorisation · <label> × <multiple> <médiane> » sont fixes (pastille sans
  bordure) ; « Sous / sur-évalué », « Scénarios 5 ans », « Dividende / action » sont des
  boutons bascule (`aria-pressed`), avec leur échantillon de couleur. Défaut : couloir et
  dividende **allumés**, scénarios **éteints**. Une pastille n'apparaît que si sa couche
  existe (pas de couloir sans valorisation, pas de dividende sans versement sur la fenêtre).
- 4.5 **Valorisation** : métrique/action × multiple **médian** de la période (comme
  aujourd'hui), tracée **en escalier** (`shape: 'hv'`), sans remplissage. Si la métrique
  courante est ≤ 0, la courbe s'arrête au dernier exercice positif. Non tracée pour un
  multiple d'entreprise.
- 4.6 **Couloir** : entre le cours et la valorisation, sur la seule plage où la valorisation
  existe ; bleu translucide quand le cours est sous la valorisation, rouge translucide au-dessus.
- 4.7 **Projection** : scénario central = `projectedValue(métrique, croissance saisie,
  multiple saisi)` relié au cours actuel, pointillé ambre, pastille de valeur à l'horizon.
  **Éventail** (couche Scénarios) : pessimiste = croissance − `VALUATION_FAN_GROWTH_SPAN` (3)
  et multiple − `VALUATION_FAN_MULTIPLE_SPAN` (4) ; optimiste = l'inverse ; zone ambre très
  pâle entre les deux, pastilles grises. Le scénario suit donc les saisies de la calculatrice.
  Un multiple qui deviendrait ≤ 0 supprime l'éventail (pas d'erreur).
- 4.8 **Prix juste** : un rond creux bleu posé sur « aujourd'hui » avec la pastille
  « Prix juste X » à sa gauche. **Plus** de ligne horizontale sur tout l'historique.
- 4.9 **Échelle verticale** : de 0 à `max(cours visible, valorisation, prix juste, scénario
  central) × 1,12`, plafonnée à `VALUATION_CHART_Y_CAP` (2,2) × le plus haut cours visible.
  Une valeur hors cadre garde sa pastille, collée en haut et préfixée « ↑ ». Si le scénario
  central est hors cadre, l'éventail n'est pas tracé et une note sous le graphe l'explique
  (« Projection hors cadre (8 353) : croissance retenue 268 %/an »).
- 4.10 **Pastilles** : fond blanc, bordure et texte de la couleur de la série, 11 px ; celles
  de la colonne de droite sont espacées d'au moins 16 px (repoussées verticalement si besoin).
- 4.11 **Dividende** : bâtons verts dans un étage bas (≈ 20 % de la hauteur, l'étage du prix
  en occupe ≈ 70 %), titre « Dividende / action » ; l'année civile en cours est un bâton
  **creux** (fond blanc, bord vert) avec « (année en cours) » au survol ; l'axe des dates est
  sous l'étage du bas. Sans dividende sur la fenêtre : étage absent, le prix prend toute la
  hauteur.
- 4.12 **Pied de carte** (remplace la légende CAGR actuelle `.val-cagr-legend`) : CAGR du cours
  sur la fenêtre, de la métrique depuis son premier exercice, du dividende sur ses années
  **complètes** ; chiffre bleu si ≥ 0, rouge sinon, « — » si non calculable.
- 4.13 **Notes** sous le graphe (texte discret) : métrique négative, multiple d'entreprise,
  projection hors cadre.
- 4.14 **Robustesse du tracé** : `ResizeObserver` sur le conteneur (comme `risk.js`), et le
  test e2e « graphe étalé (breakout) » attend que `_fullLayout` existe avant de mesurer (il a
  échoué en CI WebKit par course).
- 4.15 **Constantes** dans `config.py`, servies par `/api/meta` (lues par `thresholds.js`,
  aucune valeur littérale côté JS) : `VALUATION_CHART_YEARS = 10`,
  `VALUATION_FAN_GROWTH_SPAN = 3.0`, `VALUATION_FAN_MULTIPLE_SPAN = 4.0`,
  `VALUATION_CHART_Y_CAP = 2.2`, `VALUATION_GAP_RATIO_LIMIT = 100.0`.

## 5. Critères d'acceptation

- [x] Sur LVMH, la carte montre la ligne de statut, le couloir, le scénario central à 638 €,
      le prix juste 422 € sur « aujourd'hui » et les bâtons de dividende (2026 creux).
- [x] Sur Ubisoft : « valorisation non calculable », courbe arrêtée au dernier exercice
      positif, pas d'étage dividende.
- [x] Sur Kering : « sur-évalué (cours ×14,5) », pastille « ↑ 8 353 », pas d'éventail, note
      hors cadre ; l'échelle reste lisible.
- [x] Base EV/EBITDA : ni valorisation, ni couloir, ni statut ; aucune erreur console.
- [x] Les trois bascules allument/éteignent leur couche sans requête réseau.
- [x] Vitest : helpers purs (séries, statut, éventail, échelle, pastilles, dividendes) ;
      e2e mis à jour ; portes « Before push » vertes.

## 6. Invariants préservés

- Calibration Pernod intacte (aucune formule touchée).
- Bleu = bien, rouge = mal ; le vert du dividende est une couleur de **catégorie** (teal de la
  palette), jamais un jugement.
- Les formules de la calculatrice restent la source unique (`projectedValue`,
  `targetEntryPrice`) : le graphe ne recalcule rien d'autre.

## 7. Jalons

- **J1** — Graphe à couches, constantes, tests, documentation (`design.md`).

## 8. Note de reprise

- Maquette de référence (hors dépôt) éprouvée sur dix titres ; plan délégué à OpenCode.
- Branche : `feat/graphe-valorisation`.
- **J1 livré** (session #34) : carte à couches, cinq constantes dans `config.py` servies
  par `/api/meta`, helpers purs exportés et testés (`web-tests/valuation-chart.test.js`),
  e2e valorisation mis à jour, `design.md`. Preuve sur base jetable (`OBOLE_CACHE_DB`,
  port ≠ 8000) : **MC.PA** — statut « sous-évalué de 25,58 % », couloir, scénario central
  356,86, prix juste 235,04 posé sur « aujourd'hui », 11 bâtons de dividende dont 2026
  creux ; **UBI.PA** — « valorisation non calculable », courbe arrêtée au dernier exercice
  positif, pas d'étage dividende ; **KER.PA** — « sur-évalué (cours ×14,51) », pastille
  « ↑ 8 353,44 », éventail absent même couche allumée, note hors cadre ; **EV/EBITDA**
  (MC.PA) — ni valorisation, ni couloir, ni statut. Aucune erreur console. Les montants
  638 €/422 € de la maquette datent d'un consensus antérieur : la structure est identique,
  les valeurs suivent les saisies courantes de la calculatrice.
- Reste : revue indépendante, puis PR draft (hors périmètre de cette session).
