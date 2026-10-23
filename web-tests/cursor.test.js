import { describe, expect, it } from "vitest";

import {
  bandPairIndex,
  centerX,
  clamp,
  coarsePointer,
  fmtCursorDate,
  fmtCursorPrice,
  fmtSigma,
  nearestIndex,
  sigmaLabel,
} from "../src/obole/web/cursor.js";

// Géométrie PURE du curseur du graphe héro (overlay B-2) : aucune I/O, aucun DOM.
// Ces fonctions pilotent la conversion pixel -> index, la classification de la
// bande σ et le formatage des badges. Elles doivent rester déterministes.

describe("curseur héro — géométrie pure", () => {
  it("clamp borne des deux côtés", () => {
    expect(clamp(5, 0, 10)).toBe(5);
    expect(clamp(-1, 0, 10)).toBe(0);
    expect(clamp(99, 0, 10)).toBe(10);
  });

  it("nearestIndex trouve le point le plus proche par dichotomie", () => {
    const xms = [0, 10, 20, 30, 40];
    expect(nearestIndex(xms, -5)).toBe(0);
    expect(nearestIndex(xms, 100)).toBe(4);
    expect(nearestIndex(xms, 21)).toBe(2);
    expect(nearestIndex(xms, 26)).toBe(3);
    expect(nearestIndex(xms, 24)).toBe(2);
    expect(nearestIndex([], 10)).toBe(-1);
  });

  it("bandPairIndex classe la bande σ contenant le cours", () => {
    expect(bandPairIndex(2.7)).toBe(0);
    expect(bandPairIndex(1.0)).toBe(0);
    expect(bandPairIndex(0.4)).toBe(2);
    expect(bandPairIndex(-0.4)).toBe(4);
    expect(bandPairIndex(-1.2)).toBe(6);
    expect(bandPairIndex(-4)).toBe(6);
    expect(bandPairIndex(NaN)).toBeNull();
    expect(bandPairIndex(null)).toBeNull();
  });

  it("fmtSigma formate le niveau d'écart-type (signe + virgule)", () => {
    expect(fmtSigma(-2.9)).toBe("−2,9σ");
    expect(fmtSigma(1.4)).toBe("+1,4σ");
    expect(fmtSigma(0)).toBe("0,0σ");
    expect(fmtSigma(null)).toBe("");
    expect(fmtSigma(NaN)).toBe("");
  });

  it("sigmaLabel nomme μ / +1σ / −2σ", () => {
    expect(sigmaLabel(0)).toBe("μ");
    expect(sigmaLabel(1)).toBe("+1σ");
    expect(sigmaLabel(2)).toBe("+2σ");
    expect(sigmaLabel(-1)).toBe("−1σ");
    expect(sigmaLabel(-2)).toBe("−2σ");
  });

  it("fmtCursorPrice ajoute la devise et deux décimales", () => {
    expect(fmtCursorPrice(65.52, "EUR")).toBe("65,52 EUR");
    expect(fmtCursorPrice(200.3, "$US")).toBe("200,30 $US");
    expect(fmtCursorPrice(null, "EUR")).toBe("—");
  });

  it("fmtCursorDate rend une date française lisible", () => {
    expect(fmtCursorDate("2025-06-24")).toMatch(/24/);
    expect(fmtCursorDate("2025-06-24")).toMatch(/2025/);
    expect(fmtCursorDate(null)).toBe("");
  });

  it("coarsePointer détecte un pointeur sans survol (tactile)", () => {
    // Pas de matchMedia (ex. jsdom nu) : pas de course → false.
    expect(coarsePointer(null)).toBe(false);
    expect(coarsePointer(undefined)).toBe(false);
    // `(pointer: coarse)` vrai → tactile.
    expect(coarsePointer(() => ({ matches: true }))).toBe(true);
    expect(coarsePointer(() => ({ matches: false }))).toBe(false);
    // `hover: none` suffit aussi à classer en tactile.
    expect(coarsePointer((q) => ({ matches: /hover:\s*none/.test(q) }))).toBe(true);
    // Requête non supportée (throw) : dégradation gracieuse → false.
    expect(coarsePointer(() => { throw new Error("unsupported"); })).toBe(false);
  });

  it("centerX maintient un bloc de largeur w dans [left, right]", () => {
    // Assez de place : bord gauche = x - w/2.
    expect(centerX(100, 40, 50, 300)).toBe(80);
    // Trop à gauche : buté sur left.
    expect(centerX(0, 40, 50, 300)).toBe(50);
    // Trop à droite : buté sur right - w.
    expect(centerX(1000, 40, 50, 300)).toBe(260);
    // Bloc plus large que la plage : buté sur left, jamais inversé.
    expect(centerX(100, 500, 50, 300)).toBe(50);
  });
});
