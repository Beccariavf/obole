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
- **Momentum — La Clara Vallis** (#30, #31) : onglet frère de Valorisation. Une **jauge
  horizontale** (« satisfaite » à gauche, « frustrée » à droite) dont l'aiguille vaut
  `(1 − score)` ; les zones suivent les bornes calibrées, pas un 50/50. Le score et les
  bandes sont **bleu = satisfaite, rouge = frustrée** — la sémantique habituelle, appliquée
  à un état de foule. L'historique colore le **fond** par intervalles contigus (un rectangle
  par régime, jamais un par séance) : une ligne bicolore se lirait mal sur vingt ans. Sa
  plage est propre (`momStart`/`momEnd`) et ne touche pas celle du héro ; un chip « Réf. »
  précède 1A mais le défaut reste 10 ans.
  Sous l'historique, la carte **« Fiabilité de l'indicateur »** est un tableau à **trois
  colonnes de valeurs** — `Buy & hold`, `in`, `out` — et **sept lignes** : CAGR, volatilité,
  Sharpe, Sortino, max drawdown, Calmar, part des séances. Nombres alignés à droite, `—`
  (avec infobulle) pour une mesure non calculable, légende d'en-tête qui dit la **série**
  (brute/ajustée), la **durée** et les **frais par ordre**, puis un **pied** `N trades ·
  stratégie X %/an` et la phrase qui rappelle que le drawdown des paniers est
  **conditionnel**. **Polarité** : bleu = bien, rouge = mal, mais la colonne `out` l'**inverse
  localement** (un CAGR ou un Sharpe positif dehors est rouge : gagner quand on n'est pas
  investi est un mauvais signe) ; volatilité, max drawdown et part des séances restent
  neutres. Le CSS ne décide d'aucune couleur sémantique : il ne fait que rendre la classe
  `good`/`bad` posée par le JS. Sous 640 px, le tableau défile dans la carte, le pied et la
  légende passent sur deux lignes.

## Navigation (coquille)

- **Deux rangs, deux sens.** Le **rail gauche** sort de la fiche : Analyse, Mes indices,
  Screener, Portefeuille, Watchlist, puis **Paramètres en pied** (séparé par un filet — ce
  n'est pas un espace de consultation). Les **onglets horizontaux** au-dessus du contenu
  changent de section DANS la fiche : Résumé, Quantitatif, Dividende, Finance,
  Thèse & Société, Valorisation, Momentum.
- **Un espace est une PAGE, pas une couche.** Les cinq espaces sont des vues **sœurs** de
  l'analyse dans `.app-main` (`.app-view.view-<espace>`), sur lesquelles `x-show` bascule :
  le rail reste donc visible ET cliquable en permanence, et passer d'un espace à l'autre
  est un clic. Avant, chaque espace était une modale plein écran (98vw) posée sur la
  fiche : elle recouvrait le rail, donc il fallait fermer pour changer d'espace. Les
  **couches secondaires** restent des overlays (zoom de graphe, export, événements, import
  CSV, jeu de conviction, détails du portefeuille) : ce sont des gestes ponctuels, ils
  doivent recouvrir et rendre la main en se fermant.
- **Pas de croix dans une vue** : on ne ferme pas une page. On en change (rail) ou on
  revient à Analyse ; Échap referme l'espace ouvert (`closeAnySpace`), après la couche du
  dessus s'il y en a une. **Pas de hash d'URL** pour un espace : `parseHash` départage la
  fiche et la section, et le bouton retour du navigateur ne quitte pas une vue.
- **Une vue n'impose ni hauteur ni défilement interne** (plus de `96vh`, plus de barre
  dans la barre) : c'est le DOCUMENT qui défile, comme pour la fiche. Un seul élément
  collant par vue s'accroche à `--head-top` — le bandeau du portefeuille, l'en-tête du
  tableau du screener. Le titre de la vue (`.view-head`) est un titre de page ordinaire :
  il défile. Corollaire mesuré : `.screen-table-wrap` ne doit créer AUCUN conteneur de
  défilement (`auto` comme `clip` rattachent le `sticky` de l'en-tête à une boîte qui ne
  défile jamais, l'en-tête partait alors à −763 px) ; la colonne « Entreprise » reste
  gelée par son propre `sticky left`. **Trade-off assumé** : sans conteneur, un tableau
  plus large que la fenêtre fait déborder le DOCUMENT en largeur, donc le défilement
  horizontal emporte aussi le contenu du rail — d'où son `left: 0` (accroche dans les deux
  axes), mesuré en e2e : `railX` ne bouge plus d'un pixel pendant un défilement X.
- **Une vue neuve se lit depuis son titre** : `openSpaceEntry` remet le document en haut
  (`scrollToTop`) à chaque changement d'espace — `x-show` ne touche pas au défilement, et
  sans ça on arrivait au milieu de la page suivante (titre à y = −568).
- **Re-cliquer l'entrée déjà active ne fait rien** (sinon : résultats du screener vidés,
  onglet du portefeuille retombé sur Résumé, et des requêtes inutiles) ; une vue montée
  **redimensionne ses tracés** (`resizeViewPlots`), car `responsive: true` n'écoute que
  `window.resize` — mesuré : hôte 378 px, SVG resté à 710 px.
- **Le retour dans une vue retrace la fiche** : masquée (`display: none`), elle donne une
  largeur nulle à Plotly ; `openSpaceEntry("analyse")` appelle donc `scheduleRedraw()`.
- Le rail est **étiqueté (176 px) à partir de 1280 px** de fenêtre ; en dessous il passe en
  **icônes seules (68 px)** jusqu'à 900 px, puis en **bandeau horizontal**. Le seuil est
  calculé : à 1280 px le contenu garde assez de largeur pour deux colonnes de graphes,
  en dessous un rail étiqueté coûterait plus qu'il n'apporte.
- Le contenu est **fluide, plafonné à 1560 px** (au lieu de 1100 px figés) : la largeur
  gagnée fait tenir une colonne de plus, elle n'étire pas les tuiles (plancher 380 px).
- **La recherche est le rang 1 d'un en-tête collant à deux rangs** (recherche, puis
  onglets de section collés dessous), dans la colonne Analyse — ni dans le rail (le rail
  porte les *espaces*, pas l'entrée d'une espace), ni en bandeau global (une vue occupant
  la colonne, une barre globale n'aurait pas de place à elle). C'est ce rang qui
  **remplit** ce que la recherche laissait de vide à droite : le champ garde 420 px
  (au-delà, le regard perd le curseur) et les actions (Analyser, ↻, Retour) occupent la
  droite. Le bouton de retour est **en tête du groupe calé à droite** : il grandit vers la
  gauche et ne décale jamais « Analyser ». À l'accueil, le rang ne colle pas et devient un
  **héros centré** (un seul axe avec l'invite). Sous 900 px, plus rien ne colle et le rang
  passe sur deux lignes.
- L'entrée active du rail suit l'espace affiché ; au repos c'est **Analyse**. La marque
  ramène à l'accueil (aucune fiche, aucun espace, champ de recherche vidé).
- **Un seul espace affiché à la fois** : `openSpaceEntry` referme les autres avant
  d'ouvrir. Une modale du dessus cachait celle du dessous ; une vue, elle, s'empilerait
  visiblement (deux vues affichées, deux entrées actives).
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
- **Le rail n'est jamais recouvert** : les espaces sont des vues, pas des couches. Le
  passage d'un espace à l'autre se fait donc au clic comme au clavier (Tab dans le rail) ;
  Échap reste le raccourci de retour à Analyse.
- Fenêtre fixe du graphe héro : flèches ←/→ pour déplacer la fenêtre quand la zone est
  focus, `Shift` pour un pas fin.
- Contraste assuré sur les fonds colorés (bandes σ, matrice de corrélation).
