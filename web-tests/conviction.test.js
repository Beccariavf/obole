import { describe, expect, it } from "vitest";
import { convictionMixin } from "../src/obole/web/conviction-mixin.js";
import {
  MIN_COMPARISONS,
  changes,
  convictionScore,
  initialComparisons,
  initialRatings,
  nextPair,
  pairKey,
  suggestTiers,
  updateRatings,
  validRows,
} from "../src/obole/web/conviction.js";

const ROWS = [
  { ticker: "A", tier: 1, safety_margin_pct: 10 },
  { ticker: "B", tier: 1, safety_margin_pct: -5 },
  { ticker: "C", tier: 2, safety_margin_pct: -20 },
  { ticker: "D", tier: 3, safety_margin_pct: -40 },
];

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

  it("calcule un percentile de conviction 0…100", () => {
    const ratings = { A: 1600, B: 1550, C: 1500, D: 1400 };
    expect(convictionScore(1600, ratings)).toBe(100);
    expect(convictionScore(1400, ratings)).toBe(0);
    expect(convictionScore(1500, ratings)).toBeGreaterThan(0);
    expect(convictionScore(1500, ratings)).toBeLessThan(100);
  });

  it("conserve les effectifs par tier et propose des changements", () => {
    // D (ex-Tier 3) remonte, A (ex-Tier 1) descend : les effectifs restent
    // 2 Tier 1 / 1 Tier 2 / 1 Tier 3.
    const suggested = suggestTiers(ROWS, { A: 1400, B: 1550, C: 1500, D: 1600 });
    expect(Object.values(suggested).filter((t) => t === 1)).toHaveLength(2);
    expect(Object.values(suggested).filter((t) => t === 2)).toHaveLength(1);
    expect(Object.values(suggested).filter((t) => t === 3)).toHaveLength(1);
    expect(suggested.D).toBe(1);
    expect(suggested.A).toBe(3);
    const diff = changes(ROWS, suggested);
    expect(diff).toEqual(
      expect.arrayContaining([
        { ticker: "A", from: 1, to: 3 },
        { ticker: "D", from: 3, to: 1 },
      ]),
    );
  });

  it("le minimum de comparaisons est de 12", () => {
    expect(MIN_COMPARISONS).toBe(12);
  });

  it("refuse moins de deux valeurs", () => {
    const c = { ...convictionMixin, watchRows: [{ ticker: "A", tier: 1 }], openWatchlist() {} };
    c.openConviction();
    expect(c.convictionError).toContain("deux");
    expect(c.convictionOpen).toBe(false);
  });
});
