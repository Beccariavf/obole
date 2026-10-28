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
  12 minimum) puis un résultat (rang, « Tier actuel → suggéré », **indice absolu 0-100**
  avec le nombre de duels sous le cadran, Δ, compteurs par tier). Depuis #27, le résultat
  rappelle la **ligne des seuils** (« Tier 1 ≥ 57 · Tier 2 ≥ 43 · indice 0-100, 50 = neutre »),
  affiche un tier vide avec **zéro** au lieu de le combler, et pose deux badges :
  **« conservé »** (moins de 2 duels, tier actuel gardé) et **« limite »** (indice à 2 points
  ou moins d'un seuil — bleu clair, informatif, la règle ne change pas). Le message « Aucun
  changement » remplace l'action quand les tiers sont confirmés ; « Appliquer les tiers »
  reste alors désactivé. La modale Paramètres a une section **Conviction** (deux seuils
  0-100, aperçu « valeur / 100 ») et **une seule paire** Enregistrer / Rétablir pour tous
  les groupes (`.settings-actions`). À 390 px, la colonne Rang et le nom long s'effacent
  pour que le tableau tienne dans la largeur.

## Navigation (coquille)

- **Deux rangs, deux sens.** Le **rail gauche** sort de la fiche : Analyse, Mes indices,
  Screener, Portefeuille, Watchlist, puis **Paramètres en pied** (séparé par un filet — ce
  n'est pas un espace de consultation). Les **onglets horizontaux** au-dessus du contenu
  changent de section DANS la fiche : Résumé, Quantitatif, Dividende, Finance,
  Thèse & Société, Valorisation.
- Le rail est **étiqueté (176 px) à partir de 1280 px** de fenêtre ; en dessous il passe en
  **icônes seules (68 px)** jusqu'à 900 px, puis en **bandeau horizontal**. Le seuil est
  calculé : à 1280 px le contenu garde assez de largeur pour deux colonnes de graphes,
  en dessous un rail étiqueté coûterait plus qu'il n'apporte.
- Le contenu est **fluide, plafonné à 1560 px** (au lieu de 1100 px figés) : la largeur
  gagnée fait tenir une colonne de plus, elle n'étire pas les tuiles (plancher 380 px).
- **La recherche est le rang 1 d'un en-tête collant à deux rangs** (recherche, puis
  onglets de section collés dessous), dans la colonne Analyse — ni dans le rail (le rail
  porte les *espaces*, pas l'entrée d'une espace), ni en bandeau global (les modales sont
  plein écran : une barre globale serait masquée cinq fois sur six, tout en coûtant sa
  hauteur au graphe héro). C'est ce rang qui **remplit** ce que la recherche laissait de
  vide à droite : le champ garde 420 px (au-delà, le regard perd le curseur) et les
  actions (Analyser, ↻, Retour) occupent la droite. Le bouton de retour est **en tête du
  groupe calé à droite** : il grandit vers la gauche et ne décale jamais « Analyser ».
  À l'accueil, le rang ne colle pas et devient un **héros centré** (un seul axe avec
  l'invite). Sous 900 px, plus rien ne colle et le rang passe sur deux lignes.
- L'entrée active du rail suit l'espace ouvert ; au repos c'est **Analyse**. La marque
  ramène à l'accueil (aucune fiche, aucun espace, champ de recherche vidé).
- **Échap referme la couche du dessus** : une modale imbriquée (zoom de graphe, export,
  événements…) d'abord, l'espace ensuite. Les modales plein écran recouvrant le rail, le
  clavier est le seul chemin de portefeuille à watchlist sans viser la croix.
- **Les modales ne bougent pas** : seul leur déclencheur a déménagé de la barre de
  recherche vers le rail.
- **Grille de cartes en `flex-wrap`, sans colonnes.** `.charts-grid` répartit les cartes
  par rangées (`flex: 1 1 380px`, plancher 380 px, `min-width: 0` pour rétrécir sous
  390 px de fenêtre). Grid a été écarté pour deux raisons mesurées : un
  `repeat(3, minmax(0,1fr))` forcé dès 1450 px laissait une colonne morte (443 px sur
  « Dividende par action » et « Payout », 887 px pour la carte seule de « Retour à
  l'actionnaire »), et `auto-fit` ne corrige que les groupes dont le nombre de cartes est
  un multiple du nombre de colonnes — 7 cartes en 3+3+1 laissaient encore 807 px à
  1440 px, et 4 cartes en 3+1 la même chose. Grid ne sait pas étirer une rangée
  incomplète ; flex si (la carte orpheline s'étire jusqu'au bord).
  Ce que décide la **taxonomie** (`config.DIVIDEND_GROUPS` / `QUANT_GROUPS`, champ
  `wide`), c'est quelles cartes sont pleine largeur **par nature** — « Métriques clés »
  l'est, parce que ses huit chiffres tiennent sur un rang en pleine largeur et sur trois
  rangs en tuile étroite. Nuance assumée : le flex étire AUSSI la carte orpheline d'un
  groupe impair (3+3+1 → la dernière occupe la rangée), ce qui est le prix payé pour
  supprimer la colonne morte. Ce n'est donc pas `wide` qui rend une carte large, c'est
  `wide` qui la rend large **même quand elle n'est pas seule sur sa rangée**.

## Accessibility

- Rail et onglets : entrée active marquée (`aria-current`), focus visible, navigation
  clavier. Les libellés des onglets sont toujours rendus (jamais une infobulle seule) ; en
  rail d'icônes, le `<button>` porte un `aria-label` (le nom de l'espace) en plus du
  `title` (son explication), donc il reste nommable une fois le libellé visuellement
  retiré — les infobulles n'existent pas au tactile.
- Fenêtre fixe du graphe héro : flèches ←/→ pour déplacer la fenêtre quand la zone est
  focus, `Shift` pour un pas fin.
- Contraste assuré sur les fonds colorés (bandes σ, matrice de corrélation).
