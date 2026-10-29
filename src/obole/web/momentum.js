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
import { MOMENTUM, REG_YEARS_DEFAULT, REG_YEARS_FINANCIAL, olsLog } from "./thresholds.js";

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
};
