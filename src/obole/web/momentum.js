// Obole — section Momentum (Clara Vallis, #30).
//
// La table « monde de Markovitz » est recalculée CÔTÉ CLIENT sur la fenêtre
// choisie, comme le graphe héro : σ, z, pente et confiance suivent le sélecteur
// de durée sans aller-retour réseau. Les séries de satisfaction, elles, sont
// précalculées serveur (walk-forward) et arrivent dans `data.chart.momentum`.
//
// `MOMENTUM` et `CHART_HEIGHTS` sont des liaisons VIVANTES de `thresholds.js` :
// on les lit dans les méthodes, jamais dans un objet figé au chargement (elles
// sont réassignées par `applyMeta`).
import { C } from "./theme.js";
import {
  CHART_HEIGHTS,
  MOMENTUM,
  REG_YEARS_DEFAULT,
  REG_YEARS_FINANCIAL,
  olsLog,
} from "./thresholds.js";

export const momentumMixin = {
  momSeries: "raw", // "raw" | "adj"
  momWindow: null, // null = fenêtre de référence ; années ; 0 = maximum
  momStart: null, // plage dédiée du graphe historique (phase 5)
  momEnd: null,
  momLog: false,
  momShowReg: false,

  momData() {
    return this.data?.chart?.momentum || null;
  },

  momAvailable() {
    const m = this.momData();
    return !!m && (m.n_used || 0) >= 2;
  },

  momHasAdj() {
    return !!this.momData()?.adj;
  },

  momWindows() {
    return MOMENTUM.table_windows || [];
  },

  // Cours de la série choisie : c'est LUI que la table mesure (σ autour de la
  // droite, z, pente), pas le score de satisfaction — deux séries distinctes.
  momPriceValues() {
    const c = this.data?.chart || {};
    return (this.momSeries === "adj" ? c.price_adj : c.price_raw) || c.price_raw || [];
  },

  // Score de satisfaction de la série choisie : jauge, courbe à un an et
  // coloration de l'historique (phase 5).
  momScoreValues() {
    const m = this.momData();
    if (!m) return [];
    return (this.momSeries === "adj" && m.adj ? m.adj : m.raw) || [];
  },

  // Indices [début, fin] de la fenêtre de la table sur `chart.dates`.
  // `null` = la fenêtre de RÉFÉRENCE (celle de la valorisation) : la date
  // persistée si elle existe, sinon 20 ans (30 pour les financières). Autonome
  // (pas de dépendance à `idxStartBeforeWindow`) pour rester testable.
  momRange() {
    const dates = this.data?.chart?.dates || [];
    if (!dates.length) return [0, 0];
    const end = dates.length - 1;
    if (this.momWindow == null) {
      const refStart = this.data?.watch?.ref?.start;
      if (refStart) {
        const i = dates.findIndex((d) => d >= refStart);
        if (i >= 0) return [i, end];
      }
      const years =
        this.data?.identity?.kind === "financial" ? REG_YEARS_FINANCIAL : REG_YEARS_DEFAULT;
      return [this._momStartBefore(end, years), end];
    }
    if (!this.momWindow) return [0, end];
    return [this._momStartBefore(end, Number(this.momWindow)), end];
  },

  _momStartBefore(end, years) {
    const dates = this.data?.chart?.dates || [];
    const cutoff = new Date(dates[end]);
    cutoff.setFullYear(cutoff.getFullYear() - Number(years));
    for (let i = 0; i <= end; i++) {
      if (new Date(dates[i]) >= cutoff) return i;
    }
    return 0;
  },

  momMaLast(kind) {
    const c = this.data?.chart || {};
    const suffix = this.momSeries === "adj" ? "_adj" : "_raw";
    const arr = c[kind + suffix] || c[kind] || [];
    for (let i = arr.length - 1; i >= 0; i--) if (arr[i] != null) return arr[i];
    return null;
  },

  // Mesures brutes de la table (nombres), séparées du formatage pour les tests.
  momStats() {
    const dates = this.data?.chart?.dates || [];
    const values = this.momPriceValues();
    if (!dates.length || !values.length) return null;
    const [i0, i1] = this.momRange();
    const times = [];
    const prices = [];
    for (let i = i0; i <= i1; i++) {
      if (values[i] == null || values[i] <= 0) continue;
      times.push((new Date(dates[i]) - new Date(dates[i0])) / (365.25 * 864e5));
      prices.push(values[i]);
    }
    if (times.length < 2) return null;
    const { a, b, sigma } = olsLog(times, prices);
    const last = prices[prices.length - 1];
    const tNow = times[times.length - 1];
    // 1 − R² = SS_res / SS_tot. `olsLog` ne renvoie que sigma : on reconstruit
    // SS_res depuis sigma (ddof = 1) et SS_tot depuis les log-prix.
    const ys = prices.map(Math.log);
    const mean = ys.reduce((s, v) => s + v, 0) / ys.length;
    const ssTot = ys.reduce((s, v) => s + (v - mean) ** 2, 0);
    const confidence = ssTot > 0 ? (sigma * sigma * (ys.length - 1)) / ssTot : 0;
    return {
      sigma,
      z: sigma > 0 ? (Math.log(last) - (a + b * tNow)) / sigma : null,
      slope: b,
      confidence,
      maShort: this.momMaLast("ma_short"),
      maLong: this.momMaLast("ma_long"),
    };
  },

  momRows() {
    const s = this.momStats();
    if (!s) return [];
    const pct = (v) => this.fmt(v) + " %";
    return [
      { key: "sigma", label: "σ (bande)", value: pct((Math.exp(s.sigma) - 1) * 100) },
      { key: "z", label: "z", value: s.z == null ? "—" : this.fmt(s.z) },
      { key: "slope", label: "Pente", value: pct((Math.exp(s.slope) - 1) * 100) },
      { key: "ma_short", label: "MM court", value: s.maShort == null ? "—" : this.fmt(s.maShort) },
      { key: "ma_long", label: "MM long", value: s.maLong == null ? "—" : this.fmt(s.maLong) },
      { key: "confidence", label: "Confiance (1−R²)", value: this.fmt(s.confidence) },
    ];
  },

  // --- Les trois blocs ------------------------------------------------------

  momScore() {
    const m = this.momData();
    if (!m) return null;
    return this.momSeries === "adj" && m.score_adj != null ? m.score_adj : m.score_raw;
  },

  // 0 = foule frustrée (monde liquide), 1 = foule satisfaite (monde gazeux).
  momState(value) {
    if (value == null) return "neutre";
    if (value < MOMENTUM.low) return "bas";
    if (value > MOMENTUM.high) return "haut";
    return "neutre";
  },

  // Largeur des trois zones de la jauge : satisfaite (gauche), neutre, frustrée.
  momZones() {
    const low = MOMENTUM.low;
    const high = MOMENTUM.high;
    return { good: (1 - high) * 100, neutral: (high - low) * 100, bad: low * 100 };
  },

  // Aiguille : 0 % = foule satisfaite (gaz, à gauche), 100 % = frustrée.
  momGaugePos() {
    const score = this.momScore();
    if (score == null) return 50;
    return Math.max(0, Math.min(100, (1 - score) * 100));
  },

  // Intervalles contigus de même état, pour colorer le fond de l'historique.
  momRuns() {
    const dates = this.data?.chart?.dates || [];
    const values = this.momScoreValues();
    if (!dates.length || !values.length) return [];
    const runs = [];
    let current = null;
    for (let i = 0; i < dates.length; i++) {
      const state = this.momState(values[i]);
      if (!current || current.state !== state) {
        current = { state, start: i, end: i };
        runs.push(current);
      } else {
        current.end = i;
      }
    }
    return runs;
  },

  // --- Plage dédiée du graphe historique ------------------------------------

  momVisible() {
    const n = (this.data?.chart?.dates || []).length;
    if (!n) return [0, 0];
    const end = n - 1;
    let s = this.momStart == null ? this._momStartBefore(end, 10) : Number(this.momStart);
    let e = this.momEnd == null ? end : Number(this.momEnd);
    s = Math.max(0, Math.min(s, end - 1));
    e = Math.max(s + 1, Math.min(e, end));
    return [s, e];
  },

  momPctStart() {
    const n = (this.data?.chart?.dates || []).length;
    return n ? (this.momVisible()[0] / (n - 1)) * 100 : 0;
  },

  momPctEnd() {
    const n = (this.data?.chart?.dates || []).length;
    return n ? (this.momVisible()[1] / (n - 1)) * 100 : 100;
  },

  momMaxIdx() {
    return Math.max(0, (this.data?.chart?.dates || []).length - 1);
  },

  momClamp() {
    const n = (this.data?.chart?.dates || []).length;
    if (!n) return;
    const end = n - 1;
    let s = Number(this.momStart);
    let e = Number(this.momEnd);
    if (!Number.isFinite(s)) s = 0;
    if (!Number.isFinite(e)) e = end;
    this.momStart = Math.max(0, Math.min(s, end - 1));
    this.momEnd = Math.max(this.momStart + 1, Math.min(e, end));
  },

  momPreset(years) {
    const n = (this.data?.chart?.dates || []).length;
    if (!n) return;
    const end = n - 1;
    this.momEnd = end;
    this.momStart = years === "max" ? 0 : this._momStartBefore(end, Number(years));
    this.drawMomentumHistory();
  },

  // --- Tracés ---------------------------------------------------------------

  drawMomentum() {
    if (!this.momAvailable()) return;
    if (this.momStart == null || this.momEnd == null) {
      const n = (this.data?.chart?.dates || []).length;
      this.momEnd = n - 1;
      this.momStart = this._momStartBefore(this.momEnd, 10);
    }
    this.drawMomentumYear();
    this.drawMomentumHistory();
  },

  _momPurge(id) {
    const node = typeof document !== "undefined" ? document.getElementById(id) : null;
    if (!node) return null;
    if (typeof Plotly === "undefined") return null;
    return node;
  },

  drawMomentumYear() {
    const node = this._momPurge("mom-year");
    if (!node) return;
    const year = this.momData()?.year;
    if (!year || !year.dates?.length) {
      try { Plotly.purge(node); } catch { /* jamais monté */ }
      return;
    }
    const values = this.momSeries === "adj" && year.adj ? year.adj : year.raw;
    const low = MOMENTUM.low;
    const high = MOMENTUM.high;
    Plotly.react(node, [{
      x: year.dates,
      y: values,
      mode: "lines",
      name: "Satisfaction",
      line: { color: C.accent, width: 2 },
      fill: "tozeroy",
      fillcolor: "rgba(37,99,235,.06)",
      hovertemplate: "%{x|%d %b %Y} · %{y:.2f}<extra></extra>",
    }], {
      margin: { l: 40, r: 12, t: 8, b: 24 },
      height: CHART_HEIGHTS.momentum_year,
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      shapes: [
        { type: "rect", xref: "paper", x0: 0, x1: 1, y0: 0, y1: low,
          fillcolor: C.badFill, line: { width: 0 }, layer: "below" },
        { type: "rect", xref: "paper", x0: 0, x1: 1, y0: high, y1: 1,
          fillcolor: C.goodFill, line: { width: 0 }, layer: "below" },
        { type: "line", xref: "paper", x0: 0, x1: 1, y0: low, y1: low,
          line: { color: C.bad, width: 1, dash: "dot" } },
        { type: "line", xref: "paper", x0: 0, x1: 1, y0: high, y1: high,
          line: { color: C.accent, width: 1, dash: "dot" } },
      ],
      xaxis: { type: "date", color: C.text, tickformat: "%b %y", showgrid: false },
      yaxis: { range: [0, 1], color: C.text, tickvals: [0, 0.5, 1],
        gridcolor: C.grid, zeroline: false },
      showlegend: false,
    }, { displayModeBar: false, responsive: true });
  },

  drawMomentumHistory() {
    const node = this._momPurge("mom-history");
    if (!node) return;
    const dates = this.data?.chart?.dates || [];
    const prices = this.momPriceValues();
    if (!dates.length || !prices.length) {
      try { Plotly.purge(node); } catch { /* jamais monté */ }
      return;
    }
    const [i0, i1] = this.momVisible();
    const xs = dates.slice(i0, i1 + 1);
    const ys = prices.slice(i0, i1 + 1);

    // Fond coloré : un rectangle par intervalle contigu, jamais par séance.
    const shapes = [];
    for (const run of this.momRuns()) {
      const a = Math.max(run.start, i0);
      const b = Math.min(run.end, i1);
      if (b < a) continue;
      const fill = run.state === "bas" ? C.badFill : run.state === "haut" ? C.goodFill : null;
      if (!fill) continue;
      shapes.push({ type: "rect", xref: "x", x0: dates[a], x1: dates[b], yref: "paper",
        y0: 0, y1: 1, fillcolor: fill, line: { width: 0 }, layer: "below" });
    }

    const traces = [{
      x: xs,
      y: ys,
      mode: "lines",
      name: "Cours",
      line: { color: C.accent, width: 2 },
      fill: this.momLog ? "none" : "tozeroy",
      fillcolor: "rgba(37,99,235,.05)",
      hovertemplate: "%{x|%d %b %Y} · %{y:.2f}<extra></extra>",
    }];

    if (this.momShowReg) {
      const times = [];
      const vals = [];
      for (let i = i0; i <= i1; i++) {
        if (prices[i] == null || prices[i] <= 0) continue;
        times.push((new Date(dates[i]) - new Date(dates[i0])) / (365.25 * 864e5));
        vals.push(prices[i]);
      }
      if (times.length >= 2) {
        const { a, b } = olsLog(times, vals);
        traces.push({
          x: xs,
          y: xs.map((d) => Math.exp(a + b * ((new Date(d) - new Date(dates[i0])) / (365.25 * 864e5)))),
          mode: "lines",
          name: "Droite",
          line: { color: C.ma1, width: 2, dash: "dash" },
          hoverinfo: "skip",
        });
      }
    }

    Plotly.react(node, traces, {
      margin: { l: 48, r: 12, t: 8, b: 24 },
      height: CHART_HEIGHTS.momentum_history,
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      shapes,
      xaxis: { type: "date", color: C.text, showgrid: false },
      yaxis: { type: this.momLog ? "log" : "linear", color: C.text, gridcolor: C.grid,
        zeroline: false },
      showlegend: false,
      hovermode: "x unified",
    }, { displayModeBar: false, responsive: true });
  },
};
