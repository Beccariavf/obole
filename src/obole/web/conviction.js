// Obole — moteur du jeu de convictions (#26, seuils absolus #27).
//
// L'utilisateur compare deux valeurs à la fois ; chaque choix met à jour un
// Elo dont le prior est le tier actuel (Tier 1 > 2 > 3). Le jeu ne prétend pas
// mesurer une vérité : il révèle un ordre de préférence, puis convertit le
// rating en INDICE ABSOLU 0-100 classé par deux seuils réglables (#27).
// Aucun classement relatif, aucun quota conservé : un tier peut rester vide.
export const MIN_COMPARISONS = 12;
export const K_FACTOR = 24;
// Couverture minimale : en dessous, on ne classe pas sur un duel isolé.
export const MIN_COMPARISONS_PER_ROW = 2;
// Une valeur à 2 points ou moins d'un seuil est « limite » (bruit de mesure).
export const LIMIT_DISTANCE = 2;
const PRIOR = { 1: 1600, 2: 1500, 3: 1400 };
const DEFAULT_RATING = 1500;

export function validRows(rows) {
  return (rows || []).filter((row) => row && row.ticker && !row.error);
}

export function initialRatings(rows) {
  const ratings = {};
  for (const row of validRows(rows)) {
    ratings[row.ticker] = PRIOR[Number(row.tier)] ?? DEFAULT_RATING;
  }
  return ratings;
}

export function initialComparisons(rows) {
  // Compteur de duels PAR TICKER (couverture) — pas un effectif par tier.
  const perTicker = {};
  for (const row of validRows(rows)) perTicker[row.ticker] = 0;
  return perTicker;
}

export function expectedScore(ratingA, ratingB) {
  return 1 / (1 + 10 ** ((ratingB - ratingA) / 400));
}

export function updateRatings(ratings, winner, loser, k = K_FACTOR) {
  const a = Number(ratings[winner] ?? DEFAULT_RATING);
  const b = Number(ratings[loser] ?? DEFAULT_RATING);
  const expected = expectedScore(a, b);
  return {
    ...ratings,
    [winner]: a + k * (1 - expected),
    [loser]: b - k * (1 - expected),
  };
}

export function pairKey(a, b) {
  return [a, b].sort().join("|");
}

// Paire la moins comparée, puis la plus proche en rating ; RNG injectable.
// La même paire n'est jamais rejouée deux fois de suite, sauf s'il n'en existe
// qu'une (deux valeurs dans la watchlist).
export function nextPair(rows, ratings, comparisons, lastPair = null, rng = Math.random) {
  const list = validRows(rows);
  if (list.length < 2) return null;
  const pairs = [];
  for (let i = 0; i < list.length; i += 1) {
    for (let j = i + 1; j < list.length; j += 1) {
      const a = list[i].ticker;
      const b = list[j].ticker;
      const comparisonsSum = (comparisons[a] ?? 0) + (comparisons[b] ?? 0);
      const gap = Math.abs((ratings[a] ?? DEFAULT_RATING) - (ratings[b] ?? DEFAULT_RATING));
      pairs.push({ a, b, key: pairKey(a, b), score: comparisonsSum * 1000 + gap });
    }
  }
  let candidates = pairs;
  if (lastPair) {
    const excluded = pairKey(lastPair[0], lastPair[1]);
    const others = pairs.filter((pair) => pair.key !== excluded);
    if (others.length) candidates = others;
  }
  const min = Math.min(...candidates.map((pair) => pair.score));
  const best = candidates.filter((pair) => pair.score === min);
  const pick = best[Math.min(best.length - 1, Math.floor(rng() * best.length))] || best[0];
  return [pick.a, pick.b];
}

// --- Indice absolu et seuils (#27) ------------------------------------------
//
// L'indice est une échelle 0-100 ancrée sur le rating neutre (1500 = 50) : il ne
// dépend QUE de la valeur, jamais du groupe. Deux valeurs au même rating ont donc
// le même indice, et le nombre de Tier 1 varie librement avec les seuils.

export function convictionIndex(rating) {
  const value = Number(rating);
  if (!Number.isFinite(value)) return 50; // rating illisible -> neutre
  return Math.round(100 / (1 + 10 ** ((DEFAULT_RATING - value) / 400)));
}

// Tier 1 si l'indice atteint le seuil Tier 1, Tier 2 s'il atteint le Tier 2.
export function tierForIndex(index, thresholds) {
  const tier1 = Number(thresholds?.tier1);
  const tier2 = Number(thresholds?.tier2);
  if (index >= tier1) return 1;
  if (index >= tier2) return 2;
  return 3;
}

// Seuil le plus proche d'un indice, pour le badge « limite » (`distance <= 2`).
// À égalité de distance, le seuil le plus HAUT est retenu (le franchissement
// d'un Tier 1 est le signal le plus significatif).
export function thresholdDistance(index, thresholds) {
  let best = null;
  for (const threshold of [Number(thresholds?.tier1), Number(thresholds?.tier2)]) {
    const distance = Math.abs(index - threshold);
    const better =
      !best || distance < best.distance || (distance === best.distance && threshold > best.threshold);
    if (better) best = { threshold, distance };
  }
  return best;
}

// Tiers suggérés par seuils absolus, indépendant du mixin : une valeur à moins
// de `MIN_COMPARISONS_PER_ROW` duels garde son tier actuel (couverture
// insuffisante). Aucun compte par tier n'est lu : les tiers vides sont permis.
export function suggestTiersByThresholds(rows, ratings, comparisons, thresholds) {
  const suggested = {};
  for (const row of validRows(rows)) {
    const count = Number(comparisons?.[row.ticker] ?? 0);
    if (count < MIN_COMPARISONS_PER_ROW) {
      suggested[row.ticker] = Number(row.tier);
      continue;
    }
    const rating = Number(ratings?.[row.ticker] ?? DEFAULT_RATING);
    suggested[row.ticker] = tierForIndex(convictionIndex(rating), thresholds);
  }
  return suggested;
}

export function changes(rows, suggested) {
  return validRows(rows)
    .filter((row) => Number(row.tier) !== Number(suggested[row.ticker]))
    .map((row) => ({
      ticker: row.ticker,
      from: Number(row.tier),
      to: Number(suggested[row.ticker]),
    }));
}
