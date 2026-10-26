import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../src/obole/web/api.js";
import { convictionMixin } from "../src/obole/web/conviction-mixin.js";
import { readConvictionSource } from "./helpers/load-app.js";
import {
  LIMIT_DISTANCE,
  MIN_COMPARISONS,
  MIN_COMPARISONS_PER_ROW,
  changes,
  convictionIndex,
  initialComparisons,
  initialRatings,
  nextPair,
  pairKey,
  suggestTiersByThresholds,
  thresholdDistance,
  tierForIndex,
  updateRatings,
  validRows,
} from "../src/obole/web/conviction.js";

// Source brute du moteur : sert à prouver qu'aucune règle de tiers ne lit le
// percentile ni les effectifs (#27, C17).
const convictionSource = readConvictionSource();

const ROWS = [
  { ticker: "A", tier: 1, safety_margin_pct: 10 },
  { ticker: "B", tier: 1, safety_margin_pct: -5 },
  { ticker: "C", tier: 2, safety_margin_pct: -20 },
  { ticker: "D", tier: 3, safety_margin_pct: -40 },
];

const SEUILS = { tier1: 57, tier2: 43 };

// Composant Alpine partiel : état réinitialisé à chaque appel (le spread du
// mixin partage les objets mutables, on les remplace par des copies neuves).
function comp(overrides = {}) {
  return {
    ...convictionMixin,
    watchRows: [],
    watchItems: [],
    watchlistOpen: true,
    convictionRows: [],
    convictionRatings: {},
    convictionComparisons: {},
    convictionHistory: [],
    openWatchlist() {
      this.watchlistOpen = true;
    },
    ...overrides,
  };
}

// Ouvre le jeu avec des seuils lus via `/api/settings` (stub : aucun réseau).
async function startGame(rows, thresholds = SEUILS) {
  const settings = vi.spyOn(api, "settings").mockResolvedValue({
    values: {
      conviction_tier1_min: thresholds.tier1,
      conviction_tier2_min: thresholds.tier2,
    },
  });
  const c = comp({ watchRows: rows });
  await c.openConviction();
  settings.mockRestore();
  return c;
}

afterEach(() => {
  vi.restoreAllMocks();
});

// Jeu de cinq valeurs : c'est la couverture (>= 2 duels) et l'indice qui
// classent, pas la taille du groupe. E n'a qu'un duel : son tier est conservé.
const GAME_ROWS = [
  { ticker: "A", tier: 1 },
  { ticker: "B", tier: 1 },
  { ticker: "C", tier: 2 },
  { ticker: "D", tier: 3 },
  { ticker: "E", tier: 3 },
];
const GAME_RATINGS = { A: 1610, B: 1524, C: 1500, D: 1550, E: 1450 };
const GAME_COMPARISONS = { A: 5, B: 3, C: 4, D: 2, E: 1 };

async function finishGame(rows = GAME_ROWS, ratings = GAME_RATINGS, comparisons = GAME_COMPARISONS, thresholds = SEUILS) {
  const c = await startGame(rows, thresholds);
  c.convictionRatings = { ...ratings };
  c.convictionComparisons = { ...comparisons };
  c.convictionCount = MIN_COMPARISONS;
  c.finishConviction();
  return c;
}

describe("jeu de convictions (#26)", () => {
  it("filtre les erreurs et initialise les ratings par tier", () => {
    const rows = [...ROWS, { ticker: "ERR", tier: 1, error: "boom" }];
    expect(validRows(rows).map((r) => r.ticker)).toEqual(["A", "B", "C", "D"]);
    expect(initialRatings(ROWS)).toEqual({ A: 1600, B: 1600, C: 1500, D: 1400 });
    expect(initialComparisons(ROWS)).toEqual({ A: 0, B: 0, C: 0, D: 0 });
  });

  it("met à jour l'Elo et conserve la somme des ratings", () => {
    const before = { A: 1600, B: 1500 };
    const after = updateRatings(before, "B", "A");
    expect(after.B).toBeGreaterThan(before.B);
    expect(after.A).toBeLessThan(before.A);
    expect(after.A + after.B).toBeCloseTo(before.A + before.B);
  });

  it("choisit les paires les moins comparées, sans répétition immédiate", () => {
    const ratings = initialRatings(ROWS);
    const comparisons = initialComparisons(ROWS);
    const first = nextPair(ROWS, ratings, comparisons, null, () => 0);
    expect(first).toHaveLength(2);
    expect(pairKey(first[0], first[1])).toBe(pairKey("A", "B"));
    const second = nextPair(ROWS, ratings, comparisons, first, () => 0);
    expect(pairKey(second[0], second[1])).not.toBe(pairKey("A", "B"));
    // Avec deux valeurs seulement, l'unique paire est rejouée.
    const two = ROWS.slice(0, 2);
    const only = nextPair(two, ratings, comparisons, ["A", "B"], () => 0);
    expect(pairKey(only[0], only[1])).toBe(pairKey("A", "B"));
    expect(nextPair(ROWS.slice(0, 1), ratings, comparisons)).toBeNull();
  });

  it("le minimum de comparaisons est de 12", () => {
    expect(MIN_COMPARISONS).toBe(12);
  });

  it("refuse moins de deux valeurs", () => {
    const c = comp({ watchRows: [{ ticker: "A", tier: 1 }] });
    c.openConviction();
    expect(c.convictionError).toContain("deux");
    expect(c.convictionOpen).toBe(false);
  });
});

// --- Indice absolu et seuils (#27) ------------------------------------------
//
// Les lignes ont volontairement un tier actuel DIFFÉRENT du tier attendu : un
// classement par seuils absolus doit les reclasser sans regarder les effectifs.
const SEED_ROWS = [
  { ticker: "HAUT", tier: 2 },
  { ticker: "MILIEU", tier: 3 },
  { ticker: "BAS", tier: 1 },
];
const SEED_RATINGS = { HAUT: 1600, MILIEU: 1500, BAS: 1400 };
const SEED_COMPARISONS = { HAUT: 2, MILIEU: 2, BAS: 2 };

describe("conviction par seuils absolus (#27)", () => {
  it("convertit le rating Elo en indice absolu 0-100", () => {
    expect(convictionIndex(1500)).toBe(50);
    expect(convictionIndex(1600)).toBe(64);
    expect(convictionIndex(1400)).toBe(36);
    // Les seuils par défaut sont les milieux des ancres : 1550 → 57, 1450 → 43.
    expect(convictionIndex(1550)).toBe(57);
    expect(convictionIndex(1450)).toBe(43);
  });

  it("classe un indice par les deux seuils", () => {
    expect(tierForIndex(64, SEUILS)).toBe(1);
    expect(tierForIndex(57, SEUILS)).toBe(1);
    expect(tierForIndex(50, SEUILS)).toBe(2);
    expect(tierForIndex(43, SEUILS)).toBe(2);
    expect(tierForIndex(36, SEUILS)).toBe(3);
  });

  it("donne le seuil le plus proche et sa distance", () => {
    expect(thresholdDistance(58, SEUILS)).toEqual({ threshold: 57, distance: 1 });
    expect(thresholdDistance(57, SEUILS)).toEqual({ threshold: 57, distance: 0 });
    expect(thresholdDistance(46, SEUILS)).toEqual({ threshold: 43, distance: 3 });
  });

  it("affecte Tier 1/2/3 aux ratings 1600/1500/1400 couverts", () => {
    const suggested = suggestTiersByThresholds(SEED_ROWS, SEED_RATINGS, SEED_COMPARISONS, SEUILS);
    expect(suggested).toEqual({ HAUT: 1, MILIEU: 2, BAS: 3 });
    // Le reclassement ne dépend pas des effectifs : les lignes étaient 2/3/1.
    expect(changes(SEED_ROWS, suggested)).toEqual(
      expect.arrayContaining([
        { ticker: "HAUT", from: 2, to: 1 },
        { ticker: "MILIEU", from: 3, to: 2 },
        { ticker: "BAS", from: 1, to: 3 },
      ]),
    );
  });

  it("conserve le tier actuel sous deux duels, même si l'indice change de tier", () => {
    // BAS est en Tier 3 mais son rating 1600 (indice 64) le classerait en Tier 1 :
    // avec un seul duel, la couverture est insuffisante et le tier est conservé.
    const rows = [{ ticker: "BAS", tier: 3 }];
    const suggested = suggestTiersByThresholds(rows, { BAS: 1600 }, { BAS: 1 }, SEUILS);
    expect(suggested.BAS).toBe(3);
    // Couverture suffisante (2 duels) : le même rating passe en Tier 1.
    const couvert = suggestTiersByThresholds(rows, { BAS: 1600 }, { BAS: MIN_COMPARISONS_PER_ROW }, SEUILS);
    expect(couvert.BAS).toBe(1);
  });

  it("laisse un tier vide quand les seuils sont au-dessus des indices", () => {
    // Indices 64/50/36 : avec 75/65, personne n'atteint le Tier 1 ni le Tier 2.
    const suggested = suggestTiersByThresholds(SEED_ROWS, SEED_RATINGS, SEED_COMPARISONS, {
      tier1: 75,
      tier2: 65,
    });
    expect(Object.values(suggested)).not.toContain(1);
    expect(suggested).toEqual({ HAUT: 3, MILIEU: 3, BAS: 3 });
  });

  it("ne lit plus le percentile ni les effectifs dans le moteur", () => {
    expect(convictionSource).not.toMatch(/convictionScore/);
    expect(convictionSource).not.toMatch(/percentile/i);
    expect(convictionSource).not.toMatch(/suggestTiers\b/);
    // Aucun comptage par tier : les effectifs ne pilotent plus rien.
    expect(convictionSource).not.toMatch(/counts\[/);
    // La règle de tiers n'existe plus qu'à un seul endroit.
    expect(convictionSource.match(/function tierForIndex/g)).toHaveLength(1);
  });
});

// --- Mixin : lecture des seuils, résultat, application ----------------------
describe("mixin de conviction (#27)", () => {
  it("lit les seuils à l'ouverture, ferme la watchlist et ouvre la modale", async () => {
    const settings = vi.spyOn(api, "settings").mockResolvedValue({
      values: { conviction_tier1_min: 60, conviction_tier2_min: 40 },
    });
    const c = comp({ watchRows: GAME_ROWS });
    await c.openConviction();
    expect(settings).toHaveBeenCalledTimes(1);
    expect(c.convictionThresholds).toEqual({ tier1: 60, tier2: 40 });
    expect(c.convictionOpen).toBe(true);
    expect(c.watchlistOpen).toBe(false);
    expect(c.convictionPair).toHaveLength(2);
  });

  it("refuse d'ouvrir une paire si les seuils sont inutilisables", async () => {
    vi.spyOn(api, "settings").mockResolvedValue({
      values: { conviction_tier1_min: 40, conviction_tier2_min: 50 },
    });
    const c = comp({ watchRows: GAME_ROWS });
    await c.openConviction();
    expect(c.convictionThresholds).toBeNull();
    expect(c.convictionPair).toBeNull();
    expect(c.convictionError).toContain("Seuils");
    // Panne réseau : même refus, sans exception.
    vi.spyOn(api, "settings").mockRejectedValue(new Error("réseau"));
    const d = comp({ watchRows: GAME_ROWS });
    await d.openConviction();
    expect(d.convictionPair).toBeNull();
    expect(d.convictionError).toContain("Seuils");
  });

  it("réinitialise la partie quand les seuils échouent après une partie terminée", async () => {
    // F1 de la revue OpenFox : un GET /api/settings en échec ne doit pas laisser
    // le compteur, l'historique ou les ratings de la partie précédente.
    vi.spyOn(api, "settings").mockRejectedValue(new Error("réseau"));
    const c = comp({
      watchRows: GAME_ROWS,
      convictionCount: MIN_COMPARISONS,
      convictionRatings: { A: 1600, B: 1500 },
      convictionComparisons: { A: 5, B: 4 },
      convictionHistory: [{ count: 11 }],
      convictionLastPair: ["A", "B"],
      convictionPair: ["A", "B"],
    });
    await c.openConviction();
    expect(c.convictionCount).toBe(0);
    expect(c.convictionHistory).toEqual([]);
    expect(c.convictionRatings).toEqual({});
    expect(c.convictionComparisons).toEqual({});
    expect(c.convictionLastPair).toBeNull();
    expect(c.convictionPair).toBeNull();
    expect(c.convictionProgress()).toBe(0);
    expect(c.convictionCanFinish()).toBe(false);
    expect(c.convictionError).toContain("Seuils");
  });

  it("produit un indice entier, un tier suggéré et les seuils utilisés", async () => {
    const c = await finishGame();
    const result = c.convictionResult;
    expect(result.thresholds).toEqual(SEUILS);
    expect(result.comparisons).toBe(MIN_COMPARISONS);
    for (const row of result.rows) expect(Number.isInteger(row.score)).toBe(true);
    // Tri par indice décroissant : A (65) > D (57) > B (53) > C (50) > E (43).
    expect(result.rows.map((r) => r.ticker)).toEqual(["A", "D", "B", "C", "E"]);
    expect(result.rows.map((r) => r.score)).toEqual([65, 57, 53, 50, 43]);
    expect(result.rows.map((r) => r.suggested_tier)).toEqual([1, 1, 2, 2, 3]);
    expect(result.rows.map((r) => r.comparisons)).toEqual([5, 2, 3, 4, 1]);
    // Compteurs par tier du résultat.
    expect(c.convictionTierSummary()).toEqual({ 1: 2, 2: 2, 3: 1 });
    expect(c.convictionNoChange()).toBe(false);
    expect(c.convictionChanges()).toEqual([
      { ticker: "B", from: 1, to: 2 },
      { ticker: "D", from: 3, to: 1 },
    ]);
  });

  it("garde le tier d'une valeur à moins de deux duels et la marque non testée", async () => {
    const c = await finishGame();
    const row = c.convictionResult.rows.find((r) => r.ticker === "E");
    expect(row.comparisons).toBe(1);
    expect(row.tested).toBe(false);
    expect(row.limit).toBe(false);
    expect(row.current_tier).toBe(3);
    expect(row.suggested_tier).toBe(3);
    // D est testé et pile sur le seuil 57 : badge « limite », règle inchangée.
    const near = c.convictionResult.rows.find((r) => r.ticker === "D");
    expect(near.tested).toBe(true);
    expect(near.distance).toBe(0);
    expect(near.threshold).toBe(57);
    expect(near.limit).toBe(true);
    expect(LIMIT_DISTANCE).toBe(2);
  });

  it("affiche un tier vide avec zéro, jamais comblé", async () => {
    // Seuils 75/45 : A(65)/D(57)/B(53)/C(50) tombent en Tier 2, E reste Tier 3.
    const c = await finishGame(GAME_ROWS, GAME_RATINGS, GAME_COMPARISONS, { tier1: 75, tier2: 45 });
    expect(c.convictionTierSummary()).toEqual({ 1: 0, 2: 4, 3: 1 });
    expect(c.convictionResult.rows.filter((r) => r.suggested_tier === 1)).toHaveLength(0);
    expect(c.convictionThresholdLine()).toContain("Tier 1 ≥ 75");
    expect(c.convictionThresholdLine()).toContain("Tier 2 ≥ 45");
  });

  it("détecte l'absence de changement quand les tiers sont confirmés", async () => {
    const rows = [
      { ticker: "A", tier: 1 },
      { ticker: "B", tier: 2 },
      { ticker: "C", tier: 3 },
    ];
    const c = await finishGame(
      rows,
      { A: 1600, B: 1500, C: 1400 },
      { A: 4, B: 4, C: 4 },
    );
    expect(c.convictionChanges()).toEqual([]);
    expect(c.convictionNoChange()).toBe(true);
    expect(c.convictionResult.rows.map((r) => r.suggested_tier)).toEqual([1, 2, 3]);
  });

  it("applique les tiers par la route existante et met à jour la watchlist", async () => {
    const c = await finishGame();
    c.watchRows = GAME_ROWS.map((row) => ({ ...row }));
    c.watchItems = GAME_ROWS.map((row) => ({ ...row }));
    const put = vi.spyOn(api, "setWatchTier").mockImplementation(async (ticker, tier) => ({
      ok: true,
      data: { item: { ticker, tier } },
    }));
    await c.applyConvictionTiers();
    // Une seule route d'écriture, celle de la watchlist (#25).
    expect(put).toHaveBeenCalledTimes(2);
    expect(put.mock.calls).toEqual([
      ["B", 2],
      ["D", 1],
    ]);
    expect(c.watchRows.find((r) => r.ticker === "D").tier).toBe(1);
    expect(c.watchItems.find((r) => r.ticker === "B").tier).toBe(2);
    expect(c.convictionApplied).toBe(true);
  });

  it("signale l'échec d'application sans marquer les tiers appliqués", async () => {
    const c = await finishGame();
    vi.spyOn(api, "setWatchTier").mockResolvedValue({ ok: false, data: { detail: "refus" } });
    await c.applyConvictionTiers();
    expect(c.convictionApplied).toBe(false);
    expect(c.convictionError).toContain("refus");
  });
});
