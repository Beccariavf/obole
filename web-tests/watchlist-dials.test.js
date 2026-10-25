import { describe, expect, it } from "vitest";
import {
  MARGIN_MAX,
  MARGIN_MIN,
  clamp,
  dialArc,
  dialPoint,
  dialTone,
  dialTrack,
  gaugeFraction,
  tierAverageMargin,
} from "../src/obole/web/watchlist-dials.js";

describe("cadrans watchlist (#26)", () => {
  it("borne la valeur dans la plage d'affichage", () => {
    expect(clamp(-80, MARGIN_MIN, MARGIN_MAX)).toBe(MARGIN_MIN);
    expect(clamp(80, MARGIN_MIN, MARGIN_MAX)).toBe(MARGIN_MAX);
    expect(gaugeFraction(0, MARGIN_MIN, MARGIN_MAX)).toBe(0.5);
    expect(gaugeFraction(MARGIN_MIN, MARGIN_MIN, MARGIN_MAX)).toBe(0);
    expect(gaugeFraction(MARGIN_MAX, MARGIN_MIN, MARGIN_MAX)).toBe(1);
    expect(gaugeFraction(80, MARGIN_MIN, MARGIN_MAX)).toBe(1);
    expect(gaugeFraction(null, MARGIN_MIN, MARGIN_MAX)).toBeNull();
  });

  it("dessine un demi-cercle de la gauche vers la droite", () => {
    const start = dialPoint(50, 50, 38, 180);
    expect(start.x).toBeCloseTo(12);
    expect(start.y).toBeCloseTo(50);
    const top = dialPoint(50, 50, 38, 90);
    expect(top.x).toBeCloseTo(50);
    expect(top.y).toBeCloseTo(12);

    expect(dialArc(0, -50, 50)).toBe("M 12 50 A 38 38 0 0 1 50 12");
    expect(dialArc(-50, -50, 50)).toBe("");
    expect(dialArc(50, -50, 50)).toBe("M 12 50 A 38 38 0 0 1 88 50");
    expect(dialTrack()).toBe("M 12 50 A 38 38 0 0 1 88 50");
  });

  it("donne la polarité bleu/rouge/neutre", () => {
    expect(dialTone(10)).toBe("good");
    expect(dialTone(-10)).toBe("bad");
    expect(dialTone(0)).toBe("neutral");
    expect(dialTone(null)).toBe("neutral");
  });

  it("moyenne les marges d'un tier en ignorant les absentes", () => {
    expect(tierAverageMargin([{ safety_margin_pct: 10 }, { safety_margin_pct: 20 }])).toBe(15);
    expect(tierAverageMargin([{ safety_margin_pct: 10 }, { safety_margin_pct: null }])).toBe(10);
    expect(tierAverageMargin([])).toBeNull();
    expect(tierAverageMargin([{ safety_margin_pct: null }])).toBeNull();
  });
});
