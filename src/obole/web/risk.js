// Obole — section « Risque & dynamique » (#33).
//
// Remplace l'ancien onglet Momentum : deux étages factuels (chute depuis le plus
// haut, volatilité 60 j), sans verdict ni flèche. Les séries sont PRÉCALCULÉES
// serveur sur la pleine résolution puis décimées (`chart.risk`), et suivent une
// plage propre au graphe (10 ans par défaut), indépendante de celle du héro.
//
// `RISK` et `CHART_HEIGHTS` sont des liaisons VIVANTES de `thresholds.js`
// (réassignées par `applyMeta`) : on les lit dans les méthodes, jamais dans un
// objet figé au chargement.
import { C } from "./theme.js";
import { CHART_HEIGHTS, RISK } from "./thresholds.js";

export const riskMixin = {
  // Plage propre du graphique : INDEX sur `chart.dates` (jamais des dates).
  riskStart: null,
  riskEnd: null,
  // Puces de période : null = plage par défaut (RISK.default_years), 0 = Max.
  riskWindow: null,
  _riskRef: null, // référence de la fiche dont la plage est valide

  riskData() {
    return this.data?.chart?.risk || null;
  },

  riskNow() {
    return this.riskData()?.now || null;
  },

  riskAvailable() {
    const r = this.riskData();
    const dates = this.data?.chart?.dates || [];
    return !!r && dates.length >= 2 && Array.isArray(r.drawdown_pct);
  },

  // La plage est un INDEX : elle ne survit pas à une autre série. Changer de
  // fiche repart sur la plage par défaut au lieu de clamper l'ancienne.
  riskSyncRef() {
    const ref = typeof this._hashRef === "function" ? this._hashRef() : null;
    if (this._riskRef !== ref) {
      this._riskRef = ref;
      this.riskStart = null;
      this.riskEnd = null;
      this.riskWindow = null;
    }
  },

  riskVolWindow() {
    const n = Number(RISK.vol_window);
    return Number.isFinite(n) && n > 0 ? n : null;
  },

  riskAnomalyPctile() {
    const n = Number(RISK.vol_anomaly_pctile);
    return Number.isFinite(n) ? n : null;
  },

  riskDefaultYears() {
    const n = Number(RISK.default_years);
    return Number.isFinite(n) && n > 0 ? n : 10;
  },

  // Puces de la plage : 1A / 5A / 10A / 20A / MAX. Le défaut (10 ans) vient de
  // `config.RISK_DEFAULT_YEARS` via /api/meta, pas d'un littéral du mixin.
  riskPresets() {
    return [1, 5, 10, 20, "max"];
  },

  riskPresetLabel(preset) {
    return preset === "max" ? "MAX" : `${preset}A`;
  },

  riskChipActive(preset) {
    const value = preset === "max" ? 0 : Number(preset);
    if (this.riskWindow == null) return value === this.riskDefaultYears();
    return Number(this.riskWindow) === value;
  },

  _riskStartBefore(end, years) {
    const dates = this.data?.chart?.dates || [];
    const cutoff = new Date(dates[end]);
    cutoff.setFullYear(cutoff.getFullYear() - Number(years));
    for (let i = 0; i <= end; i++) {
      if (new Date(dates[i]) >= cutoff) return i;
    }
    return 0;
  },

  // Bornes [début, fin] de la plage affichée, clampées à l'historique.
  riskVisible() {
    const n = (this.data?.chart?.dates || []).length;
    if (!n) return [0, 0];
    const end = n - 1;
    let s =
      this.riskStart == null
        ? this._riskStartBefore(end, this.riskDefaultYears())
        : Number(this.riskStart);
    let e = this.riskEnd == null ? end : Number(this.riskEnd);
    s = Math.max(0, Math.min(s, end - 1));
    e = Math.max(s + 1, Math.min(e, end));
    return [s, e];
  },

  riskPreset(preset) {
    this.riskSyncRef();
    const n = (this.data?.chart?.dates || []).length;
    if (!n) return;
    const end = n - 1;
    this.riskEnd = end;
    if (preset === "max") {
      this.riskWindow = 0;
      this.riskStart = 0;
    } else {
      this.riskWindow = Number(preset);
      this.riskStart = this._riskStartBefore(end, Number(preset));
    }
    this.drawRiskChart();
  },

  // --- Lecture factuelle ----------------------------------------------------

  // Format commun des mesures : deux décimales, « — » si non calculable.
  _riskNum(v) {
    const n = Number(v);
    if (v == null || !Number.isFinite(n)) return "—";
    return n.toLocaleString("fr-FR", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
  },

  // Pourcentage signé (« +4 % », « -18 % ») ou « — ».
  _riskPct(v) {
    const n = Number(v);
    if (v == null || !Number.isFinite(n)) return "—";
    return (n > 0 ? "+" : "") + this._riskNum(n) + " %";
  },

  // Niveau (volatilité) : une amplitude n'est pas signée (« 34 % »).
  _riskLevel(v) {
    const n = Number(v);
    if (v == null || !Number.isFinite(n)) return "—";
    return this._riskNum(n) + " %";
  },

  // Date ISO -> « jj/mm/aaaa », sans décalage de fuseau (lecture des segments).
  _riskDate(iso) {
    const parts = String(iso || "").split("-");
    if (parts.length !== 3) return String(iso || "");
    return `${parts[2]}/${parts[1]}/${parts[0]}`;
  },

  riskDrawdownText() {
    const now = this.riskNow();
    const value = now ? now.drawdown_pct : null;
    const peak = now && now.peak_date ? ` (plus haut le ${this._riskDate(now.peak_date)})` : "";
    return `Chute depuis le plus haut : ${this._riskPct(value)}${peak}`;
  },

  // Le percentile n'est rouge qu'au-dessus du centile d'anomalie de config.py.
  riskPercentileAnomaly() {
    const value = this.riskNow()?.vol_percentile;
    const n = Number(value);
    const threshold = this.riskAnomalyPctile();
    return (
      value != null && Number.isFinite(n) && threshold != null && n >= threshold
    );
  },

  // Segments de volatilité AU-DESSUS du seuil ; `null` hors des passages, pour
  // que Plotly laisse la ligne bleue visible entre deux pics.
  riskAbove(values) {
    const raw = this.riskData()?.vol_threshold_pct;
    const threshold = raw == null ? NaN : Number(raw);
    if (!Number.isFinite(threshold)) return (values || []).map(() => null);
    return (values || []).map((v) => {
      const n = Number(v);
      return v != null && Number.isFinite(n) && n > threshold ? n : null;
    });
  },

  // Deuxième ligne : volatilité, percentile (rouge si anomalie) et benchmark.
  // « historique trop court pour situer » remplace le percentile absent.
  riskVolParts() {
    const now = this.riskNow();
    const window = this.riskVolWindow();
    const vol = now ? now.vol_pct : null;
    const parts = [
      {
        key: "vol",
        text: `Volatilité${window == null ? "" : " " + window + " j"} : ${this._riskLevel(vol)}`,
        bad: false,
      },
    ];
    if (vol != null) {
      const pctile = now ? now.vol_percentile : null;
      if (pctile == null) {
        parts.push({
          key: "short",
          text: "historique trop court pour situer",
          bad: false,
        });
      } else {
        parts.push({
          key: "pctile",
          text: `plus haute que ${Math.round(Number(pctile))} % de son historique`,
          bad: this.riskPercentileAnomaly(),
        });
      }
    }
    parts.push({
      key: "bench",
      text: `CAC 40 : ${this._riskLevel(now ? now.bench_vol_pct : null)}`,
      bad: false,
    });
    return parts;
  },

  // Troisième ligne : 12-1 hors dividendes et son repère de marché. Un 12-1
  // absent (moins de 13 mois d'historique) garde « — » ET son infobulle.
  riskMomentumParts() {
    const now = this.riskNow();
    const mom = now ? now.mom_12_1_pct : null;
    return [
      {
        key: "mom",
        text: `12-1 (hors dividendes) : ${this._riskPct(mom)}`,
        title: mom == null ? "Historique trop court (moins de 13 mois)" : "",
        bad: false,
      },
      {
        key: "bench",
        text: `CAC 40 : ${this._riskPct(now ? now.bench_mom_12_1_pct : null)}`,
        title: "",
        bad: false,
      },
    ];
  },

  // --- Tracé ----------------------------------------------------------------

  drawRiskChart() {
    if (typeof document === "undefined") return;
    const node = document.getElementById("risk-chart");
    if (!node || typeof Plotly === "undefined") return;
    if (!this.riskAvailable()) {
      try {
        Plotly.purge(node);
      } catch {
        /* jamais monté */
      }
      return;
    }

    this.riskSyncRef();
    const dates = this.data.chart.dates || [];
    const [i0, i1] = this.riskVisible();
    const xs = dates.slice(i0, i1 + 1);
    const r = this.riskData();
    const drawdown = (r.drawdown_pct || []).slice(i0, i1 + 1);
    const vol = (r.vol_pct || []).slice(i0, i1 + 1);
    const above = this.riskAbove(vol);
    const rawThreshold = r.vol_threshold_pct;
    const threshold = rawThreshold == null ? NaN : Number(rawThreshold);

    // Étages empilés, axe X partagé : chute en haut (aire neutre), volatilité
    // en bas (ligne d'accent). Le rouge ne marque QUE les passages au-dessus
    // du seuil d'anomalie — la ligne de seuil elle-même reste neutre.
    const traces = [
      {
        x: xs,
        y: drawdown,
        mode: "lines",
        name: "Chute",
        line: { color: C.neutral, width: 1.6 },
        fill: "tozeroy",
        fillcolor: C.neutralFill,
        hovertemplate: "%{x|%d %b %Y} · %{y:.1f} %<extra>Chute</extra>",
      },
      {
        x: xs,
        y: vol,
        mode: "lines",
        name: "Volatilité",
        yaxis: "y2",
        line: { color: C.accent, width: 1.8 },
        hovertemplate: "%{x|%d %b %Y} · %{y:.1f} %<extra>Volatilité</extra>",
      },
    ];
    if (Number.isFinite(threshold)) {
      traces.push({
        x: xs,
        y: above,
        mode: "lines",
        name: "Au-dessus du seuil",
        yaxis: "y2",
        connectgaps: false,
        line: { color: C.bad, width: 2.4 },
        hovertemplate: "%{x|%d %b %Y} · %{y:.1f} %<extra>Au-dessus du seuil</extra>",
      });
    }

    const shapes = [];
    if (Number.isFinite(threshold)) {
      shapes.push({
        type: "line",
        xref: "paper",
        x0: 0,
        x1: 1,
        yref: "y2",
        y0: threshold,
        y1: threshold,
        line: { color: C.neutral, width: 1, dash: "dot" },
      });
    }

    Plotly.react(
      node,
      traces,
      {
        margin: { l: 48, r: 16, t: 10, b: 28 },
        height: CHART_HEIGHTS.risk,
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: { family: "Inter, sans-serif", size: 11, color: C.text },
        xaxis: { type: "date", color: C.text, showgrid: false, zeroline: false },
        yaxis: {
          domain: [0.56, 1],
          color: C.text,
          gridcolor: C.grid,
          zeroline: false,
          ticksuffix: " %",
        },
        yaxis2: {
          domain: [0, 0.44],
          anchor: "x",
          color: C.text,
          gridcolor: C.grid,
          zeroline: false,
          ticksuffix: " %",
        },
        shapes,
        showlegend: false,
        hovermode: "x unified",
      },
      { displayModeBar: false, responsive: true },
    );
  },
};
