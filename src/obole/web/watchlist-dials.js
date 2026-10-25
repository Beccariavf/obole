// Obole — cadrans SVG de la watchlist (#26).
//
// Géométrie pure, testable sans DOM : un demi-cercle de 180° (gauche → droite
// par le haut), une valeur bornée dans une plage d'affichage, et une couleur
// sémantique (bleu = marge positive, rouge = négative, neutre = zéro). Aucun
// seuil de DÉCISION ici : la plage est une échelle visuelle.
export const MARGIN_MIN = -50;
export const MARGIN_MAX = 50;

const round = (v) => Math.round(v * 100) / 100;

export function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

export function gaugeFraction(value, min, max) {
  const v = Number(value);
  if (value == null || !Number.isFinite(v) || !Number.isFinite(min) || !Number.isFinite(max)) {
    return null;
  }
  if (max <= min) return null;
  return (clamp(v, min, max) - min) / (max - min);
}

// Point du cadran à un angle en degrés (180 = gauche, 90 = haut, 0 = droite).
export function dialPoint(cx, cy, r, angleDeg) {
  const rad = (angleDeg * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy - r * Math.sin(rad) };
}

// Arc SVG de la valeur, du point de départ (gauche) jusqu'à la fraction.
// Renvoie "" quand la valeur est au minimum (aucun arc à dessiner).
export function dialArc(value, min = MARGIN_MIN, max = MARGIN_MAX, cx = 50, cy = 50, r = 38) {
  const fraction = gaugeFraction(value, min, max);
  if (fraction == null || fraction <= 0) return "";
  const start = dialPoint(cx, cy, r, 180);
  const end = dialPoint(cx, cy, r, 180 - fraction * 180);
  return `M ${round(start.x)} ${round(start.y)} A ${r} ${r} 0 0 1 ${round(end.x)} ${round(end.y)}`;
}

// Arc de fond complet (180°).
export function dialTrack(cx = 50, cy = 50, r = 38) {
  return dialArc(1, 0, 1, cx, cy, r);
}

export function dialTone(value) {
  const v = Number(value);
  if (value == null || !Number.isFinite(v) || v === 0) return "neutral";
  return v > 0 ? "good" : "bad";
}

// Marge moyenne d'un paquet de lignes (null si aucune marge calculable).
export function tierAverageMargin(rows) {
  const values = (rows || [])
    .map((row) => row?.safety_margin_pct)
    .filter((value) => value != null && Number.isFinite(Number(value)))
    .map(Number);
  if (!values.length) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}
