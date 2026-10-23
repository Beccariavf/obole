// Obole — charte couleur et constantes visuelles (charte §8 : bleu=bien / rouge=mal).
export const C = {
  accent: "#2563EB", good: "#2563EB", bad: "#DC2626", neutral: "#6B7280",
  goodFill: "rgba(37,99,235,.10)", badFill: "rgba(220,38,38,.08)",
  grid: "#EEF1F5", text: "#6B7280", ma1: "#F59E0B", ma2: "#7C3AED",
  // Teinte « terre de sienne » : série Dividende/Action (calculatrice de prix
  // juste). Sortie des littéraux pour rester dans la charte centralisée.
  brown: "#B45309",
  // 2e couleur de la palette catégorielle unifiée (cf. conventions projet) :
  // sert les séries secondaires (rachats, 2e ligne de ratios) sans rouge ni vert.
  teal: "#0D9488",
  // Bleu clair : anneau de la diagonale de la matrice de corrélation (#17.3).
  // Contraste sur la cellule la plus saturée (corrélation 100 %) où l'accent
  // serait noyé.
  accentLight: "#BFDBFE",
  // Surlignage de la bande σ contenant le cours (curseur du graphe héro) :
  // mêmes teintes que goodFill/badFill, un cran plus dense pour rester lisible
  // par-dessus les bandes déjà remplies. Sorti des littéraux de cursor.js pour
  // rester dans la charte centralisée.
  goodBandFill: "rgba(37,99,235,.14)",
  badBandFill: "rgba(220,38,38,.14)",
};

// Échelle SÉQUENTIELLE monochrome de la matrice de corrélation (section Risque
// #17.3) : blanc (corrélation faible) → bleu de l'interface (corrélation forte,
// 100 %). `C.accent` (le bleu des boutons) est le PÔLE HAUT de l'échelle : la
// corrélation = 1 se lit dans le bleu de référence du produit, et le dégradé en
// part. Demande utilisateur : une seule teinte, cohérente avec l'UI.
// Consommée par `drawCorrelationHeatmap` (Plotly). Avec `zmin: 0, zmax: 1`, la
// borne 0.0 = blanc et la borne 1.0 = `C.accent` ; les valeurs négatives sont
// bornées au blanc.
C.corrScale = [
  [0.0, "#FFFFFF"], [0.25, "#E8EFFD"], [0.5, "#BFD3FA"], [0.75, "#6E9BEF"], [1.0, C.accent],
];


