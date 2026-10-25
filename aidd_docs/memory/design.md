# Design

Le langage visuel : charte, jetons et conventions de graphiques.

## System

- Pas de design system externe ni de build : CSS écrit à la main, Alpine.js pour
  l'interactivité, Plotly pour les graphes. Bibliothèques vendorisées, aucune dépendance
  CDN.
- Un seul thème clair ; la charte est centralisée dans `config.COLOR_*` (serveur) et `C`
  (`src/obole/web/theme.js`).

## Tokens

- Fond `#F7F8FA`, carte blanche, bordure `#E5E7EB`, accent `#2563EB`.
- **Sémantique** : bleu = bien, rouge = mal — **jamais vert/rouge**. Le champ `good` d'un
  `ScoredValue` pilote la couleur (True = bleu, False = rouge, None = neutre).
- Les rachats d'actions sont **toujours en bleu** : un retour à l'actionnaire n'est pas un
  signal négatif.
- Palette catégorielle unifiée : `#2563EB` (bleu), `#0D9488` (teal), `#7C3AED` (violet),
  `#F59E0B` (ambre/or). Pas de rouge ni de vert dans cette palette.

## Components

- **Graphiques ≤ 6 points** : ligne + marqueurs, jamais de barres (aspect histogramme
  vide). Concerne les rachats, la génération de cash, les mono-montants courts.
- **Area fill** : sous les courbes simples (mono, combo, rachats), opacité 6-8 %. Pas de
  fill sur les multi-séries (superposition illisible).
- **Cartes wide** : dividend-kpi, dividend-hist, buyback-hist — les échelles temporelles
  différentes (dividendes 20-40 ans vs rachats 4-5 ans) sont séparées visuellement.
- **Mini-charts** : 220 px de haut (CSS `.mini-chart`), cohérent avec le layout Plotly.
- **Watchlist** (#25) : espace plein écran (même gabarit que Screener/Portefeuille), barre
  de tiers avec compteurs, tableau dense à première colonne gelée. La **source du prix
  juste** est un badge neutre (`calc` / `droite`) — jamais une couleur de jugement ; la
  marge et l'écart suivent la polarité bleu/rouge. L'**étoile** du header est l'action
  d'appartenance (popover des 3 tiers), le **chip de référence** de la barre de période
  porte la fenêtre de confiance (prix bruts) et ses stats (`z`, σ). Son popover est en
  **items bloc** (libellé + date sur deux lignes), pas la grille des tiers : une grille
  16 px/1fr sans colonne de coche cassait les libellés en un mot par ligne. Une fiche qui a
  une référence s'ouvre en **prix bruts** (vue référence), dividendes décochés.
  La watchlist est en **total-return** (dividendes réinvestis) : σ/écart/Pot. 5A sont lus
  sur la droite ajustée ; le prix juste d'une ligne sans valorisation enregistrée est le
  prix d'entrée à 12 %/an jusqu'à la droite à 5 ans. La légende du tableau le dit
  explicitement, et rappelle que la fiche garde la droite brute de valorisation.
  La vue par défaut est un **tableau de bord de trois colonnes de tier** (#26) : cadran de
  marge moyenne par tier (SVG 180°, bleu/rouge), cartes avec cadran de marge, z, Pot. 5A et
  sa source, prix juste et sa source, sélecteur de tier, ouverture. Bascule Tableau pour le
  tri dense.
  Depuis #26.1, la carte est compacte (118 px, tête de tier 41 px) : mini-cadran 44 px
  **décoratif**, valeur de marge en texte HTML (un `<text>` SVG serait illisible à cette
  taille), métriques en 2 colonnes (Prix juste pleine largeur), pied 24 px. Le titre n'est
  plus un bouton : « Voir » est la seule ouverture ; le ✕ est nommé ; les sections ont un
  `h4`/`aria-labelledby`. À 390 px, les métriques passent à 1 colonne et l'en-tête de modale
  se replie. Les règles sont scopées sous `.wl-card`/`.wl-tier-head` (le duel garde ses
  cadrans). Le **jeu de convictions** est un duel plein écran (deux cartes, VS, progression,
  12 minimum) puis un résultat (rang, tiers actuel/suggéré, conviction 0–100, Δ).

## Accessibility

- Rail de sections : entrée active marquée (`aria-current`), focus visible, navigation
  clavier.
- Fenêtre fixe du graphe héro : flèches ←/→ pour déplacer la fenêtre quand la zone est
  focus, `Shift` pour un pas fin.
- Contraste assuré sur les fonds colorés (bandes σ, matrice de corrélation).
