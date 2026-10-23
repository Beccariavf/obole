// Obole — section Dividende : cartes pilotées par la taxonomie serveur.
//
// La taxonomie `config.DIVIDEND_GROUPS` (via /api/meta) est la SOURCE UNIQUE des
// cartes : le front ne décide plus quoi afficher. Ce mixin assemble les groupes
// de la section et trace les courbes. Il est séparé de `charts.js` (déjà dense)
// comme `portfolio.js`/`summary.js` : un domaine = un module.
import { C } from "./theme.js";
import {
  DIVIDEND_GROUPS,
  DIVIDEND_COLORS,
  DIVIDEND_CAGR_HORIZONS,
  DIVIDEND_DEFAULT_WINDOW_YEARS,
  DIVIDEND_MIN_WINDOW_YEARS,
  CHART_HEIGHTS,
} from "./thresholds.js";
import { slug } from "./util.js";

// Polarité d'une métrique de dividende depuis la source unique `DIVIDEND_COLORS`.
// "ge" (plus = mieux), "le" (moins = mieux) ; seuil null = toujours neutre.
function dividendGood(key, value) {
  const t = DIVIDEND_COLORS[key];
  if (!t || value == null || isNaN(value)) return null;
  const [sens, seuil] = t;
  if (seuil == null) return null;
  if (sens === "ge") return value >= seuil;
  if (sens === "le") return value <= seuil;
  return null;
}

export const dividendMixin = {
  // Groupes de la section Dividende, filtrés selon les données réellement
  // disponibles pour le titre (un titre sans dividende -> section vide).
  dividendGroups() {
    const f = this.data?.fundamentals;
    if (!f || !f.dividend) return [];
    const div = f.dividend;
    const series = f.dividend_series || null;
    const has = (name) => !!series?.metrics?.[name];
    const chart = this.data.chart || {};
    const groups = [];
    for (const grp of DIVIDEND_GROUPS) {
      const cards = [];
      for (const def of grp.cards) {
        if (def.type === "yield") {
          // Shareholder Yield n'est affiché QUE si des rachats existent : sans
          // eux, la courbe se confondrait exactement avec Dividend Yield
          // (doublon inutile). La disponibilité vient du serveur
          // (`buybacks_available`, vrai dès qu'un exercice porte un rachat).
          const needsBuybacks = def.series === "sh_yield";
          if (chart[def.series] && (!needsBuybacks || div.buybacks_available))
            cards.push({ ...def, section: "dividende", id: slug(def.title) });
        } else if (def.type === "kpi") {
          cards.push({ ...def, section: "dividende", id: slug(def.title) });
        } else if (def.type === "divbars") {
          if (div.per_share && Object.keys(div.per_share).length)
            cards.push({ ...def, section: "dividende", id: slug(def.title) });
        } else if (def.type === "divgrowth") {
          if (div.per_share && Object.keys(div.per_share).length)
            cards.push({ ...def, section: "dividende", id: slug(def.title) });
        } else if (def.type === "lines" || def.type === "stacked") {
          const metrics = (def.metrics || []).filter(has);
          if (metrics.length) cards.push({ ...def, metrics, section: "dividende", id: slug(def.title) });
        }
      }
      if (cards.length) groups.push({ title: grp.title, cards });
    }
    return groups;
  },

  // KPI de la carte « Métriques clés » (bandeau de chiffres, sans graphe).
  // Les statistiques (régularité, CAGR, fréquence) viennent du serveur
  // (`dividend.stats`, calculé par engine/dividends — source unique) : le front
  // ne les recalcule plus.
  dividendKeyMetrics() {
    const d = this.data?.fundamentals?.dividend;
    if (!d) return [];
    const stats = d.stats || {};
    const out = [];
    const push = (title, value, display, good = null) => {
      if (value != null) out.push({ title, display, good });
    };
    push("Yield (TTM)", d.yield_pct, d.yield_pct != null ? d.yield_pct + " %" : null);
    push("Payout (TTM)", d.payout_pct, d.payout_pct != null ? d.payout_pct + " %" : null,
      dividendGood("Earnings Payout Ratio", d.payout_pct));
    const inc = stats.increase_years;
    push("Années d'augmentation", inc, inc != null ? this.fmt(inc) + " an" + (inc > 1 ? "s" : "") : null);
    const noCut = stats.no_cut_years;
    push("Années sans baisse", noCut, noCut != null ? this.fmt(noCut) + " an" + (noCut > 1 ? "s" : "") : null);
    for (const h of DIVIDEND_CAGR_HORIZONS) {
      const g = (stats.cagr || {})[h];
      push("CAGR " + h + "A", g, g == null ? null : (g >= 0 ? "+" : "") + g.toFixed(2) + " %",
        g == null ? null : g >= 0);
    }
    if (stats.frequency) out.push({ title: "Fréquence", display: stats.frequency, good: null });
    if (d.last_payment_value != null)
      out.push({ title: "Dernier paiement",
        display: this.fmt(d.last_payment_value) + (d.last_payment_date ? " · " + this._fmtDivDate(d.last_payment_date) : ""),
        good: null });
    // Prochain paiement : yfinance Europe ne fournit aucun calendrier fiable
    // (seule une date ex-div approximative, distincte du paiement) -> ligne
    // « — » assumée (cf. fiche #19 §4.3), sans champ sérialisé associé.
    out.push({ title: "Prochain paiement", display: "—", good: null });
    return out;
  },

  _fmtDivDate(iso) {
    const dt = new Date(iso);
    return isNaN(dt) ? iso : dt.toLocaleDateString("fr-FR", { day: "2-digit", month: "short", year: "numeric" });
  },

  // Années du dividende par action (ordre chronologique croissant).
  _divYears() {
    const ps = this.data?.fundamentals?.dividend?.per_share || {};
    return Object.keys(ps).map(Number).sort((a, b) => a - b);
  },

  // Perf cumulée (1re -> dernière année COMPLÈTE) et CAGR, pour les pastilles des
  // cartes « Dividende / Action » et « Croissance ». Viennent du serveur (source
  // unique `dividend.stats`) ; le 1er horizon de CAGR sert de pastille de synthèse.
  _divPerfAndCagr() {
    const stats = this.data?.fundamentals?.dividend?.stats;
    if (!stats) return { perf: null, cagr: null };
    const horizons = DIVIDEND_CAGR_HORIZONS;
    const cagr = horizons.length ? (stats.cagr || {})[horizons[0]] : null;
    return { perf: stats.perf_pct ?? null, cagr: cagr ?? null };
  },

  _divValues() {
    const ps = this.data.fundamentals.dividend.per_share;
    return this._divYears().map((y) => ps[y]);
  },

  // Croissance annuelle (YoY) du dividende par action, en %, par exercice.
  // Série précalculée par le serveur (`dividend.stats.growth`) — source unique.
  _divGrowthSeries() {
    const growth = this.data?.fundamentals?.dividend?.stats?.growth || {};
    const xs = [], ys = [];
    for (const y of Object.keys(growth).map(Number).sort((a, b) => a - b)) {
      if (growth[y] != null) { xs.push(y); ys.push(growth[y]); }
    }
    return { years: xs, values: ys };
  },

  // --- Tracés ----------------------------------------------------------------

  drawDividendCards() {
    const f = this.data?.fundamentals;
    if (!f) return;
    this.dividendGroups().forEach((grp) => {
      grp.cards.forEach((c) => {
        const el = "mc-" + c.id;
        if (!document.getElementById(el)) return;
        // Hauteur : standard UI piloté par config.py (via /api/meta). Les cartes
        // simples sont en mini (200 px, comme le Quantitatif) ; la carte mise en
        // avant (`wide`, Dividend Yield) est plus haute. Le conteneur CSS et le
        // layout Plotly partagent la même valeur (cf. drawYieldCard pour la hauteur).
        const h = CHART_HEIGHTS.mini;
        try {
          if (c.type === "yield") this.drawYieldCard(el, c);
          else if (c.type === "divbars") this.drawDividendHist(el, h);
          else if (c.type === "divgrowth") this.drawDividendGrowth(el, h);
          else if (c.type === "lines") this.drawDividendLines(el, c, h);
          else if (c.type === "stacked") this.drawDividendStacked(el, c, h);
        } catch (e) { console.error("dividend card error:", c.id, c.type, e); }
      });
    });
  },

  // Fenêtre par défaut d'une série LONGUE (rendement continu, dividende par
  // action) : les dernières `DIVIDEND_DEFAULT_WINDOW_YEARS` années si
  // l'historique le permet, sinon `DIVIDEND_MIN_WINDOW_YEARS`, sinon tout.
  // Le zoom (modale) sert à explorer plus loin. Bornes de l'historique fournies
  // en années (barres) ou en dates (courbes).
  defaultWindowYears(availableYears) {
    if (availableYears >= DIVIDEND_DEFAULT_WINDOW_YEARS) return DIVIDEND_DEFAULT_WINDOW_YEARS;
    if (availableYears >= DIVIDEND_MIN_WINDOW_YEARS) return DIVIDEND_MIN_WINDOW_YEARS;
    return availableYears;
  },

  // Index [i0, i1] de la fenêtre par défaut sur une série de dates (courbes).
  defaultDateRange(dates) {
    if (!dates || !dates.length) return [0, 0];
    const end = dates.length - 1;
    const first = new Date(dates[0]);
    const last = new Date(dates[end]);
    const spanYears = (last - first) / (365.25 * 864e5);
    const win = this.defaultWindowYears(spanYears);
    if (win >= spanYears) return [0, end];
    const cutoff = new Date(last);
    cutoff.setFullYear(cutoff.getFullYear() - win);
    let start = end;
    for (let i = 0; i <= end; i++) { if (new Date(dates[i]) >= cutoff) { start = i; break; } }
    return [start, end];
  },

  // Bornes [x0, x1] de la fenêtre par défaut sur un axe d'ANNÉES (barres).
  defaultYearRange(years) {
    if (!years || !years.length) return null;
    const spanYears = years[years.length - 1] - years[0];
    const win = this.defaultWindowYears(spanYears);
    const start = Math.max(years[0], years[years.length - 1] - win);
    return [start - 0.5, years[years.length - 1] + 0.5];
  },

  // Rendement continu : courbe tracée + médiane / high / low recalculés client
  // (même principe que computeLive). Par défaut la carte affiche la FENÊTRE PAR
  // DÉFAUT de la section (10/5 ans, `defaultDateRange`) ; le zoom (modale) passe
  // une plage `[i0, i1]` — partagée avec le curseur du héro.
  // `range` = [i0, i1] optionnel ; sinon la fenêtre par défaut.
  // Hauteur : la carte mise en avant (`wide`) est plus haute que les autres — le
  // layout Plotly doit coïncider avec le conteneur CSS (`.mini.wide .mini-chart`),
  // sinon la courbe déborde sur les pastilles.
  drawYieldCard(el, card, range = null) {
    const chart = this.data.chart;
    const series = chart[card.series];
    if (!series) return;
    const [i0, i1] = range || this.defaultDateRange(chart.dates);
    const xs = chart.dates.slice(i0, i1 + 1);
    const ys = series.slice(i0, i1 + 1);
    const stats = this._yieldStats(ys);
    const shapes = [];
    if (stats.median != null) shapes.push(this._hLine(stats.median, C.neutral));
    if (stats.high != null) shapes.push(this._hLine(stats.high, C.accent));
    if (stats.low != null) shapes.push(this._hLine(stats.low, C.bad));
    const height = range
      ? CHART_HEIGHTS.detail
      : card.wide ? CHART_HEIGHTS.dividend_hero : CHART_HEIGHTS.mini;
    Plotly.react(el, [{
      x: xs, y: ys, mode: "lines", line: { color: C.accent, width: 2 },
      fill: "tozeroy", fillcolor: "rgba(37,99,235,.06)", name: card.title,
    }], this.miniLayout({
      // Axe X DATE (et non « category ») : une série quotidienne compte plus de
      // 1000 points, une catégorie par point produirait un axe illisible.
      xaxis: { gridcolor: C.grid, type: "date", nticks: 6 },
      shapes, height,
      yaxis: { gridcolor: C.grid, ticksuffix: " %" },
    }), { displayModeBar: false, responsive: true });
    // Le cache des stats alimente les pastilles de la CARTE : on ne l'écrase pas
    // quand on trace la modale (une plage différente fausserait les pastilles).
    if (!range) this._yieldStatsCache[card.id] = stats;
  },

  _yieldStatsCache: {},

  _hLine(y, color) {
    return { type: "line", xref: "paper", x0: 0, x1: 1, y0: y, y1: y,
      line: { color, width: 1, dash: "dash" } };
  },

  _yieldStats(values) {
    const clean = values.filter((v) => v != null && v === v);
    if (!clean.length) return { median: null, high: null, low: null };
    const sorted = [...clean].sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    const median = sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
    return { median, high: sorted[sorted.length - 1], low: sorted[0] };
  },

  // Pastilles d'une carte de rendement : High / Médiane / Low de la fenêtre.
  yieldPills(card) {
    const stats = this._yieldStatsCache[card.id];
    if (!stats || stats.median == null) return [];
    const fmt = (v) => this.fmt(v) + " %";
    return [
      { label: "High", display: fmt(stats.high), good: true },
      { label: "Médiane", display: fmt(stats.median), good: null },
      { label: "Low", display: fmt(stats.low), good: false },
    ];
  },

  // Dividende par action : série longue -> fenêtre par défaut (10/5 ans).
  // `yearRange` force une plage d'axe (modale zoom : traduite de la plage de dates).
  drawDividendHist(el, height = CHART_HEIGHTS.mini, yearRange = null) {
    const years = this._divYears();
    const values = this._divValues();
    const trace = { x: years, y: values, type: "bar", marker: { color: C.accent } };
    Plotly.react(el, [trace],
      this.miniLayout({ xRange: yearRange || this.defaultYearRange(years), height }),
      { displayModeBar: false, responsive: true });
  },

  // Croissance du dividende : série longue -> fenêtre par défaut.
  drawDividendGrowth(el, height = CHART_HEIGHTS.mini, yearRange = null) {
    const { years, values } = this._divGrowthSeries();
    if (!years.length) return;
    Plotly.react(el, [{ x: years, y: values, type: "bar", marker: { color: C.accent } }],
      this.miniLayout({ xRange: yearRange || this.defaultYearRange(years), height,
        yaxis: { gridcolor: C.grid, ticksuffix: " %" } }),
      { displayModeBar: false, responsive: true });
  },

  // Multi-lignes de ratios (payouts) sur les exercices disponibles (~5 ans :
  // série courte, la fenêtre par défaut ne la tronque pas).
  drawDividendLines(el, card, height = CHART_HEIGHTS.mini) {
    const ds = this.data.fundamentals.dividend_series;
    const palette = [C.accent, C.ma2];
    const traces = card.metrics.map((m, i) => {
      const row = ds.metrics[m];
      const pairs = ds.years.map((y, j) => [y, row[j]]).filter((p) => p[1] != null);
      return { x: pairs.map((p) => p[0]), y: pairs.map((p) => p[1]), name: m,
        mode: "lines+markers", line: { color: palette[i % palette.length], width: 2 }, marker: { size: 6 } };
    });
    const years = this.dividendSeriesYears(card);
    Plotly.react(el, traces, this.miniLayout({
      xRange: years.length ? [years[0] - 0.5, years[years.length - 1] + 0.5] : null,
      showlegend: true, height, yaxis: { gridcolor: C.grid, ticksuffix: " %" },
    }), { displayModeBar: false, responsive: true });
  },

  // Barres empilées : dividendes (bleu accent) + rachats (2e couleur de la
  // palette unifiée du projet, teal) — jamais de rouge.
  drawDividendStacked(el, card, height = CHART_HEIGHTS.mini) {
    const ds = this.data.fundamentals.dividend_series;
    const palette = [C.accent, C.teal];
    const traces = card.metrics.map((m, i) => {
      const row = ds.metrics[m];
      const pairs = ds.years.map((y, j) => [y, row[j]]).filter((p) => p[1] != null);
      return { x: pairs.map((p) => p[0]), y: pairs.map((p) => p[1]), name: m, type: "bar",
        marker: { color: palette[i % palette.length] } };
    });
    const years = this.dividendSeriesYears(card);
    Plotly.react(el, traces, this.miniLayout({
      xRange: years.length ? [years[0] - 0.5, years[years.length - 1] + 0.5] : null,
      barmode: "stack", showlegend: true, height,
    }), { displayModeBar: false, responsive: true });
  },

  // Années réellement renseignées d'une carte (union des métriques).
  dividendSeriesYears(card) {
    const ds = this.data?.fundamentals?.dividend_series;
    if (!ds) return [];
    const set = new Set();
    for (const m of (card.metrics || [])) {
      const row = ds.metrics[m];
      if (!row) continue;
      ds.years.forEach((y, i) => { if (row[i] != null) set.add(y); });
    }
    return [...set].sort((a, b) => a - b);
  },

  // Pastilles d'une carte multi-métriques (payouts / montants) : dernière valeur.
  dividendSeriesPills(card) {
    const ds = this.data?.fundamentals?.dividend_series;
    if (!ds) return [];
    return (card.metrics || []).map((m) => {
      const row = ds.metrics[m];
      if (!row) return null;
      const idx = [...row].reduce((acc, v, i) => (v != null ? i : acc), -1);
      if (idx < 0) return null;
      const v = row[idx];
      const unit = this.metricUnit(m);
      const display = unit === "pct" ? this.fmt(v) + " %" : this.fmtCap(v);
      return { label: m, display, good: unit === "pct" ? dividendGood(m, v) : null };
    }).filter(Boolean);
  },

  // Pastilles Perf / CAGR des cartes « Dividende / Action ».
  dividendPerfPills() {
    const { perf, cagr } = this._divPerfAndCagr();
    const out = [];
    if (perf != null) out.push({ label: "Perf", display: (perf >= 0 ? "+" : "") + perf.toFixed(2) + " %", good: perf >= 0 });
    if (cagr != null) out.push({ label: "CAGR", display: (cagr >= 0 ? "+" : "") + cagr.toFixed(2) + " %", good: cagr >= 0 });
    return out;
  },

  // Une carte dividende a-t-elle assez de données pour tracer ? (état vide).
  dividendCardEmpty(card) {
    if (card.type === "kpi") return false;
    if (card.type === "yield") return false;
    if (card.type === "divbars" || card.type === "divgrowth") return this._divYears().length < 2;
    if (card.type === "lines" || card.type === "stacked") return this.dividendSeriesYears(card).length < 2;
    return false;
  },

  // Nombre d'années pour la puce « N ans » (cartes à axe temporel).
  dividendCardSpan(card) {
    if (card.type === "divbars" || card.type === "divgrowth") return this._divYears().length;
    if (card.type === "lines" || card.type === "stacked") return this.dividendSeriesYears(card).length;
    return 0;
  },

  // Badge de fiabilité de la section : signale les manques de la source (rachats
  // absents, historique de comptes court). Petit, gris, non intrusif — même
  // esprit que le badge de fiabilité de l'en-tête. Renvoie [] si tout est complet.
  dividendWarnings() {
    const f = this.data?.fundamentals;
    const div = f?.dividend;
    if (!div) return [];
    const out = [];
    if (!div.buybacks_available) out.push("Rachats d'actions : non disponibles (source)");
    const seriesYears = this.data?.fundamentals?.dividend_series?.years?.length ?? 0;
    if (seriesYears && seriesYears < 5)
      out.push(`Payout / retour à l'actionnaire : ${seriesYears} an(s) disponibles`);
    return out;
  },
};
