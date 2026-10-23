// Obole — curseur du graphe héro (inspiration Baggr / design B-2).
//
// Au survol de la droite de régression, un overlay SVG « pointer-events: none »
// est superposé au graphe Plotly et affiche :
//   - une fine ligne verticale pointillée + une guide horizontale au cours ;
//   - un losange sur chaque courbe (cours, μ, ±1σ, ±2σ) au x du curseur ;
//   - une colonne de valeurs à DROITE, hors du cadre du tracé (μ, +1σ, +2σ,
//     −1σ, −2σ) ;
//   - un badge prix · niveau-σ au-dessus (couleur = polarité Obole) et un
//     badge date en dessous ;
//   - la mise en évidence de la bande σ qui contient le cours.
//
// Les maths de régression ne sont JAMAIS recalculées ici : on relit les séries
// déjà produites par `drawChart` (line/up1/lo1/up2/lo2/ys). σ et a,b restent
// la propriété de `olsLog` (parité intacte, cf. CLAUDE.md).
//
// La projection valeur→pixel passe par les échelles RÉELLES de Plotly
// (`xaxis.d2p` / `yaxis.d2p` de `_fullLayout`) : exact en log comme en linéaire,
// et resynchronisée après zoom/pan via `plotly_relayout`. La GÉOMÉTRIE PURE
// (bornage, pixel→index, classification σ, formatage) est exportée et testée
// unitairement (`web-tests/cursor.test.js`) — sans DOM ni I/O.

import { C } from "./theme.js";

const SVG_NS = "http://www.w3.org/2000/svg";
const MINUS = "\u2212"; // signe moins typographique (cohérent avec les libellés)
const PAIRS = [0, 2, 4, 6];
// Paire [kBas, kHaut] d'écart-types bornant chaque bande, par index de paire.
const PAIR_KS = { 0: [1, 2], 2: [0, 1], 4: [-1, 0], 6: [-2, -1] };

// Largeur de la gouttière droite du graphe héro : place pour la colonne de
// valeurs du curseur (design B-2). Source unique, consommée par `drawChart`.
export const CURSOR_MARGIN_R = 92;

// --- Géométrie & formatage purs (aucune dépendance) ----------------------

export function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v));
}

// Pointeur sans survol (tactile / stylet) : on garde alors le readout prix·σ
// affiché une fois posé, au lieu de l'effacer au « leave » (qui n'existe pas
// sans hover). `mq` = `window.matchMedia` (injectable pour le test, sans DOM).
export function coarsePointer(mq) {
  if (typeof mq !== "function") return false;
  try {
    return mq("(pointer: coarse)").matches || mq("(hover: none)").matches;
  } catch {
    return false;
  }
}

// Bord gauche d'un bloc de largeur `w` centré sur `x`, maintenu dans
// [left, right] (jamais inversé si le bloc déborde de la plage).
export function centerX(x, w, left, right) {
  const lo = left;
  const hi = Math.max(left, right - w);
  return clamp(x - w / 2, lo, hi);
}

// Index du point le plus proche dans une série croissante (dichotomie).
export function nearestIndex(xms, x) {
  const n = xms.length;
  if (!n) return -1;
  if (x <= xms[0]) return 0;
  if (x >= xms[n - 1]) return n - 1;
  let lo = 0, hi = n - 1;
  while (lo + 1 < hi) {
    const mid = (lo + hi) >> 1;
    if (xms[mid] === x) return mid;
    if (xms[mid] < x) lo = mid;
    else hi = mid;
  }
  return (x - xms[lo]) <= (xms[hi] - x) ? lo : hi;
}

// Bande σ qui contient le z donné, comme index de paire (0/2/4/6). Découpage
// identique au design B-2 : z ≥ 1 → extérieur haut, 0 ≤ z < 1 → intérieur haut,
// −1 < z < 0 → intérieur bas, z ≤ −1 → extérieur bas.
export function bandPairIndex(z) {
  if (z == null || Number.isNaN(z)) return null;
  if (z >= 1) return 0;
  if (z >= 0) return 2;
  if (z > -1) return 4;
  return 6;
}

export function sigmaLabel(k) {
  if (k === 0) return "μ";
  return (k > 0 ? "+" : MINUS) + Math.abs(k) + "σ";
}

// Niveau d'écart-type signé, virgule française (« −2,9σ », « +1,4σ »).
export function fmtSigma(z) {
  if (z == null || Number.isNaN(z)) return "";
  const s = Math.abs(z).toFixed(1).replace(".", ",");
  const sign = z > 0 ? "+" : z < 0 ? MINUS : "";
  return sign + s + "σ";
}

export function fmtCursorPrice(v, ccy) {
  if (v == null || Number.isNaN(v)) return "—";
  const s = Number(v).toLocaleString("fr-FR", {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  });
  return ccy ? s + " " + ccy : s;
}

// Date ISO -> « 24 juin 2025 ». Parsing local (jamais UTC) pour éviter le
// décalage d'un jour sur les fuseaux négatifs.
export function fmtCursorDate(iso) {
  if (!iso) return "";
  const [y, m, d] = String(iso).slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return "";
  return new Date(y, m - 1, d).toLocaleDateString("fr-FR", {
    day: "numeric", month: "short", year: "numeric",
  });
}

// Valeur de la droite (k=0) ou de la bande ±kσ à l'index i.
function sigmaValue(g, i, k) {
  if (k === 2) return g.up2[i];
  if (k === 1) return g.up1[i];
  if (k === 0) return g.line[i];
  if (k === -1) return g.lo1[i];
  return g.lo2[i];
}

// --- Mixin Alpine : état + rendu de l'overlay -----------------------------

export const cursorMixin = {
  _cursorRaf: 0,
  _cursorEvent: null,
  _cursorTouch: false,
  _cursorGd: null,
  _cursorResizeWired: false,
  _cursorBandPolys: null,
  _cursorPolysDirty: true,

  // Prépare l'overlay (dimensions, projection) et câble les événements. Volontairement
  // LÉGER : il ne reconstruit PAS les polygones de bande (coûteux, O(n·4)) — ceux-ci
  // sont bâtis à la demande au premier rendu (`_ensureBandPolys`). `plotly_relayout`
  // (zoom/pan continu) se contente donc de rafraîchir la projection pixel, sans rejouer
  // la géométrie → zéro jank. `this._cursorGeom` doit être posé par `drawChart`.
  _setupCursor() {
    const gd = document.getElementById("chart");
    const g = this._cursorGeom;
    if (!gd || !g || !(g.xs && g.xs.length > 1)) return;
    const fl = gd._fullLayout;
    if (!fl || !fl._size || !fl.xaxis || !fl.yaxis || !(fl.width > 0)) return;
    const size = fl._size;
    if (!(size.w > 0) || !(size.h > 0)) return;

    const stack = gd.parentElement || gd;
    let svg = stack.querySelector(".cursor-overlay");
    if (!svg) {
      svg = document.createElementNS(SVG_NS, "svg");
      svg.setAttribute("class", "cursor-overlay");
      stack.appendChild(svg);
    }
    svg.setAttribute("viewBox", `0 0 ${fl.width} ${fl.height}`);
    svg.setAttribute("width", fl.width);
    svg.setAttribute("height", fl.height);

    this._cursorSvg = svg;
    // `d2p`/`p2c` sont RELATIFS À LA ZONE DE TRACÉ (0 = bord gauche/haut du
    // plot), alors que le SVG couvre tout le graph-div (0 = coin du div). On
    // ajoute donc les marges `size.l`/`size.t` pour aligner l'overlay.
    this._cursorMap = {
      plotLeft: size.l, plotTop: size.t,
      plotRight: size.l + size.w, plotBottom: size.t + size.h,
      xPix: (ms) => size.l + fl.xaxis.d2p(ms),
      yPix: (v) => size.t + fl.yaxis.d2p(v),
      // Pixel écran (relatif au div) → valeur d'axe, via l'échelle RÉELLE de
      // Plotly : reste juste après zoom/pan (plage visible ≠ plage complète).
      xVal: (pxDiv) => fl.xaxis.p2c(pxDiv - size.l),
    };
    // Les échelles ont pu bouger (zoom/pan) : les polygones en pixels sont périmés.
    this._cursorPolysDirty = true;
    // Le graphe héro vit sous `<template x-if>` : Alpine détruit/recrée `#chart`
    // à chaque nouvelle fiche. On re-câble donc dès que le graph-div change
    // (sinon le nouveau nœud resterait sans listeners → curseur inerte).
    if (gd !== this._cursorGd) {
      this._wireCursor(gd);
      this._cursorGd = gd;
    }
    // Réaffiche le curseur s'il est sous la souris (ex. après zoom).
    this._scheduleCursor();
  },

  // Polygones de bande σ (pixels) bâtis PARESSEUSEMENT : seulement quand un rendu
  // les réclame et que la géométrie a été invalidée. Réutilise le cache sinon.
  _ensureBandPolys() {
    const g = this._cursorGeom, map = this._cursorMap;
    if (!g || !map) return;
    if (!this._cursorPolysDirty && this._cursorBandPolys) return;
    this._cursorBandPolys = this._buildBandPolys(g, map);
    this._cursorPolysDirty = false;
  },

  // Quatre polygones pleine largeur (une par bande σ), points en pixels.
  _buildBandPolys(g, map) {
    const out = {};
    for (const pair of PAIRS) {
      const [kLo, kHi] = PAIR_KS[pair];
      const up = [], dn = [];
      for (let i = 0; i < g.xs.length; i++) {
        const x = map.xPix(g.xms[i]);
        const yHi = map.yPix(sigmaValue(g, i, kHi));
        const yLo = map.yPix(sigmaValue(g, i, kLo));
        if (Number.isFinite(x) && Number.isFinite(yHi) && Number.isFinite(yLo)) {
          up.push(`${x.toFixed(1)},${yHi.toFixed(1)}`);
          dn.push(`${x.toFixed(1)},${yLo.toFixed(1)}`);
        }
      }
      if (up.length > 1) out[pair] = up.concat(dn.reverse()).join(" ");
    }
    return out;
  },

  _wireCursor(gd) {
    // Pointeur sans survol (tactile) : on garde le readout affiché au lieu de
    // l'effacer (aucun « leave » fiable au doigt) → fallback persistant.
    this._cursorTouch = coarsePointer(window.matchMedia);
    const onMove = (ev) => { this._cursorEvent = ev; this._scheduleCursor(); };
    gd.addEventListener("pointermove", onMove);
    gd.addEventListener("pointerdown", onMove);
    const clear = () => {
      if (this._cursorTouch) return; // au doigt, on garde la dernière position
      this._cursorEvent = null;
      this._scheduleCursor();
    };
    gd.addEventListener("pointerleave", clear);
    gd.addEventListener("pointercancel", clear);
    // Zoom / pan : les échelles changent → on rafraîchit la projection et on
    // marque les polys périmés, sans les reconstruire maintenant (rendu paresseux).
    gd.on("plotly_relayout", () => this._setupCursor());
    // `resize` est global : on ne le câble qu'une fois, même si le graph-div est
    // recréé à chaque fiche (sinon les listeners s'empileraient).
    if (!this._cursorResizeWired) {
      let rsz = 0;
      window.addEventListener("resize", () => {
        if (rsz) return;
        rsz = requestAnimationFrame(() => { rsz = 0; this._setupCursor(); });
      });
      this._cursorResizeWired = true;
    }
  },

  // Un seul rAF en vol : mousemove/relayout ne déclenchent jamais deux rendus.
  _scheduleCursor() {
    if (this._cursorRaf) return;
    this._cursorRaf = requestAnimationFrame(() => {
      this._cursorRaf = 0;
      this._cursorTick();
    });
  },

  _cursorTick() {
    const svg = this._cursorSvg, map = this._cursorMap, g = this._cursorGeom;
    if (!svg || !map || !g) return;
    const ev = this._cursorEvent;
    if (!ev) {
      // Repos (aucun survol, ou sortie du graphe) : readout posé sur le dernier
      // point de la plage VISIBLE, comme si on le survolait. Toujours affiché
      // (desktop inclus), pas seulement au doigt — le dernier cours reste lisible
      // d'un coup d'œil sans geste.
      //
      // Après un zoom/pan pur (relayout, sans redraw), `g.xms` couvre encore la
      // plage d'avant : on relit le bord droit via l'échelle RÉELLE de Plotly
      // (`xVal(plotRight)`) pour viser le dernier point effectivement visible.
      const edge = map.xVal(map.plotRight);
      const idx = Number.isFinite(edge) ? nearestIndex(g.xms, edge) : g.xs.length - 1;
      this._renderCursor(idx < 0 ? g.xs.length - 1 : idx);
      return;
    }
    const rect = svg.getBoundingClientRect();
    const px = ev.clientX - rect.left;
    // Pixel écran → valeur d'axe via l'échelle RÉELLE de Plotly (juste après
    // zoom/pan), puis index le plus proche dans la série.
    const idx = nearestIndex(g.xms, map.xVal(px));
    if (idx < 0) return;
    this._renderCursor(idx);
  },

  _renderCursor(idx) {
    const g = this._cursorGeom, svg = this._cursorSvg, map = this._cursorMap;
    if (!g || !svg || !map) return;
    const i = clamp(idx, 0, g.xs.length - 1);
    const xi = map.xPix(g.xms[i]);
    const lineV = g.line[i];
    const price = g.ys[i] ?? lineV;
    const z = (g.sigma > 0 && price > 0 && lineV > 0)
      ? Math.log(price / lineV) / g.sigma : null;
    const color = z == null ? C.neutral : (z < 0 ? C.accent : C.bad);
    const yp = map.yPix(price);

    this._ensureBandPolys();
    const parts = [];

    // Bande σ contenant le cours : polygone mis en évidence (cache paresseux).
    const pair = bandPairIndex(z);
    if (pair != null && this._cursorBandPolys && this._cursorBandPolys[pair]) {
      const fill = pair <= 2 ? C.badBandFill : C.goodBandFill;
      parts.push(`<polygon class="cur-band" points="${this._cursorBandPolys[pair]}" fill="${fill}"/>`);
    }

    // Ligne verticale discrète (remplace la spikeline native) + guide
    // HORIZONTALE au cours, de la gauche du tracé au bord droit.
    parts.push(`<line class="cur-line" x1="${xi.toFixed(1)}" x2="${xi.toFixed(1)}" y1="${map.plotTop}" y2="${map.plotBottom}"/>`);
    parts.push(`<line class="cur-hline" x1="${map.plotLeft}" x2="${map.plotRight}" y1="${yp.toFixed(1)}" y2="${yp.toFixed(1)}" stroke="${color}"/>`);
    parts.push(`<path d="M${map.plotRight},${yp.toFixed(1)} l9,-6 v12z" fill="${color}"/>`);

    // Losanges sur chaque courbe (μ, ±1σ, ±2σ) + colonne de valeurs à droite.
    // Les pastilles sont émises centrées à l'origine : `_fitLabels` les
    // redimensionne au texte réel mesuré (jamais de largeur magique qui rogne).
    const ccy = g.ccy || "";
    for (const k of [-2, -1, 0, 1, 2]) {
      const v = sigmaValue(g, i, k);
      if (v == null || !Number.isFinite(v)) continue;
      const yk = map.yPix(v);
      parts.push(`<circle class="cur-kd" cx="${xi.toFixed(1)}" cy="${yk.toFixed(1)}" r="3.5"/>`);
      const label = `${sigmaLabel(k)} ${Math.round(v).toLocaleString("fr-FR")}`;
      parts.push(
        `<g class="cur-pill-g" data-y="${yk.toFixed(1)}">`
        + `<rect class="cur-pill" height="20" rx="10"/>`
        + `<text class="cur-pt" y="14" text-anchor="middle">${label}</text></g>`,
      );
    }

    // Pastille accentuée sur le cours.
    parts.push(`<circle cx="${xi.toFixed(1)}" cy="${yp.toFixed(1)}" r="9" fill="${color}" opacity=".22"/>`);
    parts.push(`<circle class="cur-dot" cx="${xi.toFixed(1)}" cy="${yp.toFixed(1)}" r="6" stroke="${color}" stroke-width="3.5"/>`);

    // Badge prix · niveau-σ (au-dessus) et badge date (en dessous) : redimensionnés
    // et repositionnés par `_fitLabels` d'après la largeur réelle du texte.
    const badgeTxt = `${fmtCursorPrice(price, ccy)}${z != null ? " · " + fmtSigma(z) : ""}`;
    parts.push(
      `<g class="cur-badge-g" data-x="${xi.toFixed(1)}">`
      + `<rect class="cur-badge-bg" height="26" rx="13" stroke="${color}" stroke-opacity=".4"/>`
      + `<text class="cur-badge" y="17.5" text-anchor="middle">${badgeTxt}</text></g>`,
    );
    parts.push(
      `<g class="cur-date-g" data-x="${xi.toFixed(1)}">`
      + `<rect class="cur-date-bg" height="22" rx="11"/>`
      + `<text class="cur-date" y="15" text-anchor="middle">${fmtCursorDate(g.xs[i])}</text></g>`,
    );

    svg.innerHTML = parts.join("");
    this._fitLabels(svg, xi, map);
  },

  // Redimensionne les pastilles/badges d'après la largeur RÉELLE du texte
  // (`getComputedTextLength`) et les recentre, bornés au cadre du tracé.
  _fitLabels(svg, xi, map) {
    const measure = (t) => {
      if (typeof t.getComputedTextLength !== "function") return t.textContent.length * 6.2;
      const w = t.getComputedTextLength();
      return w > 0 ? w : t.textContent.length * 6.2;
    };
    const sizeGroup = (g, w, h) => {
      const rect = g.querySelector("rect");
      const text = g.querySelector("text");
      if (rect) { rect.setAttribute("width", w); rect.setAttribute("x", 0); }
      if (text) { text.setAttribute("x", w / 2); text.setAttribute("y", h / 2 + 4); }
    };
    for (const g of svg.querySelectorAll(".cur-pill-g")) {
      const w = measure(g.querySelector("text")) + 18;
      sizeGroup(g, w, 20);
      const y = Number(g.getAttribute("data-y"));
      g.setAttribute("transform", `translate(${(map.plotRight + 12).toFixed(1)},${(y - 10).toFixed(1)})`);
    }
    for (const g of svg.querySelectorAll(".cur-badge-g")) {
      const w = measure(g.querySelector("text")) + 28;
      sizeGroup(g, w, 26);
      const gx = centerX(xi, w, map.plotLeft, map.plotRight);
      g.setAttribute("transform", `translate(${gx.toFixed(1)},${(map.plotTop - 34).toFixed(1)})`);
    }
    for (const g of svg.querySelectorAll(".cur-date-g")) {
      const w = measure(g.querySelector("text")) + 22;
      sizeGroup(g, w, 22);
      const gx = centerX(xi, w, map.plotLeft, map.plotRight);
      g.setAttribute("transform", `translate(${gx.toFixed(1)},${(map.plotBottom + 3).toFixed(1)})`);
    }
  },
};
