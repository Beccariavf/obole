# #28 — Coquille de navigation (rail d'espaces + onglets de section)

**Priorité** : 🟡 Q2 (important, pas urgent — ergonomie de l'écran principal)
**Impact Pernod** : 🟢 Nul (uniquement du rendu client, aucun appel au calcul)
**Taille** : 2 sessions
**Statut** : **fait**

## Problème

L'écran principal était plat et étroit :

1. La barre de recherche portait **tout** : la recherche, les actions de fiche et **cinq
   boutons d'espace** (Mes indices, Screener, Portefeuille, Watchlist, Paramètres). Elle
   débordait sur deux lignes et mélangeait deux niveaux de navigation.
2. La fiche rangeait ses six sections dans un **rail vertical d'icônes** dont les libellés
   n'apparaissaient qu'au survol : il fallait explorer pour savoir où aller.
3. Le contenu était **figé à 1100 px**, laissant de larges marges mortes sur tout écran
   un peu large.

Autrement dit : deux rangs de navigation confondus, et une largeur qui ne servait à rien.

## Solution

**Deux rangs, un sens chacun.**

| Rang | Composant | Contenu | Sémantique |
| --- | --- | --- | --- |
| Rail gauche | `.app-rail` (`nav.js`) | Analyse · Mes indices · Screener · Portefeuille · Watchlist, puis **Paramètres en pied** | Sortir de la fiche |
| Onglets | `.section-tabs` (`sections.js`) | Résumé · Quantitatif · Dividende · Finance · Thèse & Société · Valorisation | Changer de section DANS la fiche |

Les **modales restent des modales** : seul leur déclencheur a déménagé. Aucune réécriture
d'écran, aucun changement de route, aucun schéma touché.

**Largeurs, calculées plutôt que choisies :**

| Fenêtre | Rail | Contenu | Colonnes de graphes |
| --- | --- | --- | --- |
| 1920 | étiqueté 176 | 1316 | 3 |
| 1600 | étiqueté 176 | 1316 | 3 |
| 1440 | étiqueté 176 | 1196 | 3 |
| 1280 | étiqueté 176 | 1036 | 2 |
| 1279 – 900 | icônes 68 | 1143 → 764 | 2 |
| < 900 | bandeau horizontal | pleine largeur | 1-2 |

Le seuil de 1280 px est le point où un rail étiqueté **ne coûte pas** une colonne de
graphes. En dessous, il en coûterait une : le rail se replie en icônes.

Le contenu est fluide, plafonné à **1560 px** (au lieu de 1100 px figés). Les grilles
plafonnent leurs colonnes (`.charts-grid` ≤ 3, `.kpis` ≤ 5) : la largeur gagnée fait tenir
une colonne de plus, elle n'étire pas les tuiles existantes.

## Ce qui a disparu

- Le **rail vertical de sections** et ses infobulles (`.rail`, `.rail-btn`, `.rail-tip`) :
  remplacés par des onglets dont les libellés sont toujours visibles.
- Le **breakout** de la section Valorisation (`.section-breakout`) : il élargissait la
  section de 180 px pour étaler le graphe du prix juste, or le contenu est désormais déjà
  étalé. La marge calculée valait 0 partout — un réglage mort.
- La **troisième copie du helper `icon()`** : extraite dans `util.js`, elle servait déjà
  `sections.js` et `portfolio.js`.

## Dettes soldées après revue

- `goHome()` vide désormais `query` (sinon « Analyser » rouvrait l'ancien ticker), remet
  `_lastRef` à zéro (sinon le même ticker revenait sur l'ancienne section au lieu de
  Résumé) et **invalide un `load()` en vol** via `_loadGeneration` — la fiche ne peut plus
  se rouvrir seule après un retour à l'accueil.
- Le rail d'icônes a un **nom accessible** (`aria-label`), pas seulement une infobulle
  inexistante au tactile, et il **défile** quand la fenêtre est plus courte que lui.
- **Échap** referme la couche du dessus (modale imbriquée, puis espace) : les modales plein
  écran recouvrant le rail, c'était le seul chemin de portefeuille à watchlist au clavier.
- `SPACE_OPENERS` (les cinq noms de méthodes d'ouverture) est **vérifié contre les vrais
  mixins** par `nav.test.js` : un renommage casse un test au lieu de casser le rail en
  silence.

## Ce qui est préservé (invariants)

- `sections.js::SECTIONS` reste la **source unique** : onglets, filtrage des cartes et
  deep-link lisent le même registre.
- Le deep-link `#<ticker>/<section>` et le bouton « retour » du navigateur.
- Les modales plein écran et leurs sélecteurs (`.modal-portfolio`, `.modal-watchlist`,
  `.modal-screen`, `.modal-indices`, `.modal-settings`).
- Le gel du rail au défilement, l'état actif (`aria-current`), le focus clavier.
- La pastille « une thèse existe » — déplacée du rail vers l'onglet Thèse & Société.

## Critères d'acceptation livrés

| # | Critère |
| --- | --- |
| C0 | Travail sur `feat/coquille-navigation`, merge `--no-ff` sur `main`. |
| C1 | Rail étiqueté (176 px) dès 1280 px, libellés complets sans troncature. |
| C2 | Rail sticky sur toute la hauteur du contenu. |
| C3 | La barre de recherche ne garde qu'Analyser / ↻ / Retour. |
| C4 | Chaque entrée du rail ouvre la MÊME modale qu'avant. |
| C5 | Six onglets horizontaux libellés, ordre de `SECTIONS`, actif souligné. |
| C6 | Onglet → `#<ticker>/<section>`, retour navigateur fonctionnel. |
| C7 | Onglet indisponible désactivé avec infobulle explicative. |
| C8 | Repli 1279–900 px (68 px), < 900 px (bandeau), aucun débordement. |
| C9 | Entrée active = espace ouvert ; fermer rend la main à « Analyse ». |
| C10 | Paramètres en pied de rail, séparé par un filet. |
| C11 | La marque ramène à l'accueil. |
| C12 | Contenu ≥ 1300 px à 1600 px de fenêtre ; colonnes plafonnées. |
| C13 | Graphe héro retracé après redimensionnement. |
| C14 | `SECTIONS` source unique, `sections.test.js` intact. |
| C15 | Suites vertes (pytest, ruff, vitest, e2e Chromium + WebKit). |
| C16 | `design.md`, `CLAUDE.md`, `codebase-map.md`, cette fiche, index. |

## Tests

- `web-tests/nav.test.js` — registre des espaces, entrée active, `openSpaceEntry`,
  `goHome` (13 tests).
- `web-tests/e2e/sections.spec.js` — ruban d'onglets, barre sans espace, coquille sticky,
  repli responsive (4 tests ajoutés).
- `web-tests/modules.test.js` — `nav.js` déclaré comme mixin.
- `web-tests/e2e/watchlist.spec.js` — deux tests rendus indépendants de la base locale
  (ils présumaient un `RI.PA` non suivi).
- `tests/test_doc_coherence.py` — `nav.js` documenté dans `codebase-map.md`.

## Note de reprise

Rien en attente. Si la largeur du rail doit changer, les valeurs à ajuster sont dans trois
media queries de `style.css` (`.app-shell`, `.app-rail-label`, `.app-rail`) et le seuil est
commenté sur place. Le registre des espaces vit dans `nav.js::SPACES`.
