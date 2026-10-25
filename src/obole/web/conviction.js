// Obole — moteur du jeu de convictions (#26).
//
// L'utilisateur compare deux valeurs à la fois ; chaque choix met à jour un
// Elo dont le prior est le tier actuel (Tier 1 > 2 > 3). Le jeu ne prétend pas
// mesurer une vérité : il révèle un ordre de préférence, puis propose des tiers
// en CONSERVANT les effectifs actuels (reclassement, pas de seuil inventé).
export const MIN_COMPARISONS = 12;
export const K_FACTOR = 24;
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
  const counts = {};
  for (const row of validRows(rows)) counts[row.ticker] = 0;
  return counts;
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

// Score de conviction = percentile du rating dans le groupe (0…100).
export function convictionScore(rating, ratings) {
  const values = Object.values(ratings || {});
  if (!values.length) return 0;
  if (values.length === 1) return 100;
  const below = values.filter((value) => value < rating).length;
  const equal = values.filter((value) => value === rating).length;
  return Math.round(((below + (equal - 1) / 2) / (values.length - 1)) * 100);
}

// Tiers suggérés en conservant les effectifs actuels (n1, n2, n3).
export function suggestTiers(rows, ratings) {
  const list = validRows(rows);
  const counts = { 1: 0, 2: 0, 3: 0 };
  for (const row of list) {
    const tier = Number(row.tier);
    if (counts[tier] != null) counts[tier] += 1;
  }
  const sorted = [...list].sort(
    (a, b) =>
      (ratings[b.ticker] ?? DEFAULT_RATING) - (ratings[a.ticker] ?? DEFAULT_RATING) ||
      Number(a.tier) - Number(b.tier) ||
      String(a.ticker).localeCompare(String(b.ticker)),
  );
  const suggested = {};
  sorted.forEach((row, index) => {
    if (index < counts[1]) suggested[row.ticker] = 1;
    else if (index < counts[1] + counts[2]) suggested[row.ticker] = 2;
    else suggested[row.ticker] = 3;
  });
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
