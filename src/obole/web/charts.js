// Obole — graphes (héro + mini-charts), slider de période, KPI.
import { C } from "./theme.js";
import {
  olsLog, betaLive, corrLive, scored, ratioGood,
  REG_YEARS_DEFAULT, REG_YEARS_FINANCIAL, RATIO_THRESHOLDS, POTENTIAL_HORIZONS,
  QUANT_GROUPS, METRIC_UNITS, CHART_HEIGHTS,
} from "./thresholds.js";
import { slug } from "./util.js";
import { CURSOR_MARGIN_R } from "./cursor.js";

// Types de cartes SANS graphe (bandeaux de chiffres : CAGR, KPI dividende).
// SOURCE UNIQUE côté front : consommée par `chartsMixin.isChartCard` ET par
// `sections.js::expectedMiniIds` (un seul jeu de règles, pas de dérive).
export const NON_CHART_TYPES = new Set(["cagr", "kpi"]);

export const chartsMixin = {
  // Exposé à Alpine : la modale watchlist affiche le label/couleur de la
  // position σ via `scored(r.z, 'distance')`. Sans cette propriété, l'expression
  // Alpine échouait (« scored is not defined ») et le label restait vide.
  scored,
  fmt(v) { return v == null ? "—" : Number(v).toLocaleString("fr-FR", { maximumFractionDigits: 2 }); },

  fmtCap(v) {
    if (v == null) return "—";
    if (v >= 1e9) return (v / 1e9).toFixed(1) + " Md";
    if (v >= 1e6) return (v / 1e6).toFixed(0) + " M";
    return this.fmt(v);
  },

  polarity(good) { return good === true ? "good" : good === false ? "bad" : "neutral"; },

  // Nombre d'années de la fenêtre fixe (mode figé) selon le type d'entreprise.

  regWindowYears() {
    return this.data?.identity?.kind === "financial"
      ? REG_YEARS_FINANCIAL : REG_YEARS_DEFAULT;
  },

  // Index du premier point ≥ (date du dernier point − N années).
  // Si l'historique est plus court que N ans, on part du tout début.

  fixedWindowStart(dates, endIdx) {
    const cutoff = new Date(dates[endIdx]);
    cutoff.setFullYear(cutoff.getFullYear() - this.regWindowYears());
    for (let i = 0; i <= endIdx; i++) {
      if (new Date(dates[i]) >= cutoff) return i;
    }
    return 0;
  },

  // Référence persistée (#25.1) : ne s'applique QUE si la fenêtre visible est
  // exactement celle de la référence, en prix bruts et synchro. Dans ce cas la
  // droite affichée est la régression serveur (a, b, σ, start) — même source que
  // la watchlist — au lieu d'un re-fit sur la série décimée.
  referenceRegression() {
    const watch = this.data?.watch;
    const stats = watch?.ref_stats;
    const start = watch?.ref?.start;
    if (!start || !stats) return null;
    if (stats.a == null || stats.b == null || stats.sigma == null || !stats.start) return null;
    if (!this.syncRegression || this.withDividends) return null;
    const idx = this.idxForDate(start);
    if (idx == null) return null;
    const [s, e] = this.visibleRange();
    if (s !== idx || e !== this.maxIdx()) return null;
    return {
      a: stats.a,
      b: stats.b,
      sigma: stats.sigma,
      start: stats.start,
      end: stats.end || this.data.chart.dates[this.maxIdx()],
    };
  },

  // --- Slider de période à deux poignées -----------------------------------

  maxIdx() { return this.data ? this.data.chart.dates.length - 1 : 0; },

  // Index du premier point ≥ une date ISO (`AAAA-MM-JJ`). Les dates du payload
  // sont ISO : la comparaison lexicographique suffit (pas de parsing Date).
  // Sert à la fenêtre de confiance (#25), partagée avec la watchlist.
  idxForDate(iso) {
    if (!iso || !this.data?.chart?.dates) return null;
    const dates = this.data.chart.dates;
    for (let i = 0; i < dates.length; i++) {
      if (dates[i] >= iso) return i;
    }
    return null;
  },

  initRange() {
    const dates = this.data.chart.dates;
    const n = dates.length;
    const refStart = this.data?.watch?.ref?.start;
    const refIdx = refStart ? this.idxForDate(refStart) : null;
    if (refIdx != null) {
      // La fiche s'ouvre sur la fenêtre de confiance du titre (#25) : la droite
      // affichée est celle que l'utilisateur a choisi de suivre. Le slider reste
      // libre ensuite — c'est le « Prix juste » du Résumé qui fige la référence.
      this.rangeStart = refIdx;
    } else {
      // Plage par défaut : 20 dernières années.
      const cutoff = new Date(dates[n - 1]);
      cutoff.setFullYear(cutoff.getFullYear() - 20);
      let i0 = 0;
      for (let i = 0; i < n; i++) { if (new Date(dates[i]) >= cutoff) { i0 = i; break; } }
      this.rangeStart = i0;
    }
    this.rangeEnd = n - 1;
    // « Fenêtre fixe » : on replie la plage sur winYears (extrémité droite).
    if (this.winLocked) {
      this.rangeStart = this.idxStartBeforeWindow(this.rangeEnd, this.winYears);
    }
  },

  visibleRange() {
    const n = this.maxIdx();
    let s = this.rangeStart ?? 0, e = this.rangeEnd ?? n;
    if (s > e) [s, e] = [e, s];
    return [Math.max(0, s), Math.min(n, e)];
  },

  pctStart() { return this.maxIdx() ? (this.visibleRange()[0] / this.maxIdx()) * 100 : 0; },

  pctEnd() { return this.maxIdx() ? (this.visibleRange()[1] / this.maxIdx()) * 100 : 100; },

  rangeLabel() {
    if (!this.data) return "";
    const d = this.data.chart.dates;
    const [s, e] = this.visibleRange();
    const f = (iso) => new Date(iso).toLocaleDateString("fr-FR", { day: "2-digit", month: "short", year: "numeric" });
    return `${f(d[s])} – ${f(d[e])}`;
  },

  // Empêche les poignées de se croiser. En « fenêtre fixe », verrouille la
  // distance temporelle (winYears) : bouger une poignée déplace l'autre en miroir.

  clampHandles(which) {
    if (this.winLocked) {
      if (which === "start") {
        this.rangeEnd = this.idxEndForWindow(this.rangeStart, this.winYears);
      } else {
        this.rangeStart = this.idxStartBeforeWindow(this.rangeEnd, this.winYears);
      }
      return;
    }
    const gap = Math.max(20, Math.round(this.maxIdx() * 0.02));
    if (which === "start" && this.rangeStart > this.rangeEnd - gap) {
      this.rangeStart = Math.max(0, this.rangeEnd - gap);
    }
    if (which === "end" && this.rangeEnd < this.rangeStart + gap) {
      this.rangeEnd = Math.min(this.maxIdx(), this.rangeStart + gap);
    }
  },

  // Premier index dont la date ≥ (date de `endIdx` − `years` années). 0 sinon.

  idxStartBeforeWindow(endIdx, years) {
    const dates = this.data.chart.dates;
    const cutoff = new Date(dates[endIdx]);
    cutoff.setFullYear(cutoff.getFullYear() - years);
    for (let i = 0; i <= endIdx; i++) {
      if (new Date(dates[i]) >= cutoff) return i;
    }
    return 0;
  },

  // Dernier index dont la date ≤ (date de `startIdx` + `years` années). Sinon fin.

  idxEndForWindow(startIdx, years) {
    const dates = this.data.chart.dates;
    const cutoff = new Date(dates[startIdx]);
    cutoff.setFullYear(cutoff.getFullYear() + years);
    for (let i = startIdx; i < dates.length; i++) {
      if (new Date(dates[i]) > cutoff) return Math.max(startIdx, i - 1);
    }
    return dates.length - 1;
  },

  onSliderRelease() {
    // Au relâchement seulement : redessine (et recalcule la droite si synchro).
    this.drawChart();
  },

  // Bascule de la case « Synchroniser » : en passant en mode figé, on recale
  // le slider sur la fenêtre fixe 20/30 ans (base de calcul de la droite) pour
  // que l'affichage corresponde au calcul. L'utilisateur peut re-zoomer ensuite.

  onSyncToggle() {
    if (this.winLocked) {
      // Le verrou « fenêtre fixe » a priorité sur la synchro : on ne laisse
      // pas la poignée s'étendre au-delà de la taille verrouillée.
      this.syncRegression = true;
      this.rangeStart = this.idxStartBeforeWindow(this.rangeEnd, this.winYears);
    } else if (!this.syncRegression) {
      this.rangeStart = this.fixedWindowStart(this.data.chart.dates, this.maxIdx());
      this.rangeEnd = this.maxIdx();
    }
    this.drawChart();
  },

  // Active « fenêtre fixe » : verrouille la distance des poignées à winYears,
  // ancré sur l'extrémité droite du curseur (fenêtre glissante dans le temps).
  // La synchro est forcée tant que la fenêtre est verrouillée ; on mémorise
  // l'état précédent pour le restaurer à la désactivation.

  onWinToggle() {
    if (this.winLocked) {
      this._winPrevSync = this.syncRegression;
      this.syncRegression = true;
      this.rangeStart = this.idxStartBeforeWindow(this.rangeEnd, this.winYears);
    } else if (this._winPrevSync !== null) {
      this.syncRegression = this._winPrevSync;
      this._winPrevSync = null;
    }
    this.drawChart();
  },

  // Changement de la taille de la fenêtre : on garde l'extrémité droite et on
  // ajuste la gauche, puis on redessine la droite sur la nouvelle largeur.

  onWinSizeChange() {
    this.winYears = Number(this.winYears) || 5;
    this.rangeStart = this.idxStartBeforeWindow(this.rangeEnd, this.winYears);
    this.drawChart();
  },

  // Navigation clavier de la zone période (focus). Réservée au mode « fenêtre
  // fixe » : les flèches ←/→ déplacent la fenêtre entière dans le temps, sans
  // en changer la largeur. Pas grossier (~1 mois de bourse) par défaut,
  // Shift+flèche = pas fin (~1 jour) pour un positionnement précis.

  onPeriodKey(e) {
    if (!this.winLocked || !this.data) return;
    // Ignore les touches remontées depuis les poignées du slider : leurs flèches
    // sont déjà gérées nativement (clampHandles). La zone clavier ne capte que
    // quand le bloc .period lui-même est focus.
    if (e.target && e.target.tagName === "input") return;
    let dir = null;
    if (e.key === "ArrowLeft") dir = -1;
    else if (e.key === "ArrowRight") dir = 1;
    if (dir === null) return;
    e.preventDefault();
    const fine = e.shiftKey;
    this.nudgeWindow(dir, fine ? 1 : 22);
  },

  // Translate la fenêtre de `step` index sans changer sa largeur, bornée à
  // l'historique, puis redessine (droite + KPI recalés comme au drag souris).

  nudgeWindow(dir, step) {
    const n = this.maxIdx();
    const [s, e] = this.visibleRange();
    const width = e - s;
    let ns = s + dir * step;
    let ne = e + dir * step;
    if (ns < 0) { ns = 0; ne = Math.min(n, width); }
    if (ne > n) { ne = n; ns = Math.max(0, n - width); }
    this.rangeStart = ns;
    this.rangeEnd = ne;
    this.drawChart();
  },

  // Recalcule valo/potentiels/perf/écart-type sur la fenêtre de régression.
  // `live` remplace les indicateurs serveur tant qu'on regarde une période.
  // `obsIdx` = point d'observation (dernier point VISIBLE), distinct de la
  // fenêtre de calcul de la droite : en mode figé, la droite couvre tout
  // l'historique mais on lit le cours/σ à l'extrémité de la sous-période zoomée.

  computeLive(a, b, sigma, t0, allDates, series, obsIdx, obsOverride = null) {
    // `obsOverride` (#25.1) : quand la fenêtre affichée EST la référence, on lit
    // au dernier cours réel (identité + ref_stats.end) et non au dernier point
    // décimé — la décimée peut avoir quelques séances de retard.
    const obsDate = obsOverride?.date ?? allDates[obsIdx];
    const lastPrice = obsOverride?.price ?? series[obsIdx] ?? this.data.identity.last_price;
    const tNow = (new Date(obsDate) - t0) / (365.25 * 864e5);
    const z = (Math.log(lastPrice) - (a + b * tNow)) / sigma;
    const perf = (Math.exp(b) - 1) * 100;
    const ecart = (Math.exp(sigma) - 1) * 100;
    const potential = (H) => {
      const target = Math.exp(a + b * (tNow + H));
      return (Math.pow(target / lastPrice, 1 / H) - 1) * 100;
    };
    // Horizons depuis /api/meta (source unique config.POTENTIAL_HORIZONS).
    const [h5, h10] = POTENTIAL_HORIZONS.length ? POTENTIAL_HORIZONS : [5, 10];
    this.live = {
      distance_sigma: scored(z, "distance", 2),
      perf_passee: scored(perf, "perf"),
      ecart_type: scored(ecart, "ecart"),
      potential_5y: scored(potential(h5), "potential"),
      potential_10y: scored(potential(h10), "potential"),
    };
  },

  // Indicateur courant : live (période) si dispo, sinon serveur (historique complet).

  ind(key) {
    if (this.live && this.live[key]) return this.live[key];
    return this.data.indicators[key];
  },

  isRatio() { return this.data?.kind_payload === "ratio"; },

  // --- KPI ---

  kpiList() {
    const i = this.data.indicators;
    const pct = (sv) => sv.value == null ? "—" : sv.value + " %";
    const list = [
      { key: "p5", title: "Potentiel / an (5 ans)", sv: this.ind("potential_5y"), display: pct(this.ind("potential_5y")) },
      { key: "p10", title: "Potentiel / an (10 ans)", sv: this.ind("potential_10y"), display: pct(this.ind("potential_10y")) },
      { key: "perf", title: "Performance passée", sv: this.ind("perf_passee"), display: pct(this.ind("perf_passee")) },
      { key: "vol", title: "Écart-type (volatilité)", sv: this.ind("ecart_type"), display: pct(this.ind("ecart_type")) },
    ];
    // Un ratio n'a pas de comptes : il expose à la place le β (A~B) et la
    // corrélation, recalculés live. Actions et indices partagent la tendance MM
    // (série synthétique pour un indice).
    if (this.isRatio()) {
      // Ratio : corrélation (solidité du lien) puis bêta (amplitude du mouvement).
      const corr = this.ind("correlation");
      const beta = this.ind("beta");
      list.push(
        { key: "corr", title: "Corrélation (A ~ B)", sv: corr,
          display: corr.value == null ? "—" : corr.value },
        { key: "beta", title: "Bêta (A ~ B)", sv: beta,
          display: beta.value == null ? "—" : beta.value },
      );
    } else {
      list.push(
        { key: "trend", title: "Tendance boursière", sv: i.trend, display: i.trend.label || "—" },
      );
    }
    return list;
  },

  // Position de l'aiguille de la jauge valorisation (z de -2 à +2 -> 0..100 %).
  // -2σ = décoté (gauche), +2σ = cher (droite). Au-delà, l'aiguille butée.

  gaugePos() {
    const z = this.ind("distance_sigma").value;
    if (z == null) return 50;
    return Math.max(0, Math.min(100, ((z + 2) / 4) * 100));
  },

  // --- Graphe héro : cours + droite + bandes + MM (recalcul client) -------

  drawChart() {
    const c = this.data.chart;
    const [i0, i1] = this.visibleRange();
    const allDates = c.dates;

    // Mode figé (synchro OFF) : règle Obole — droite sur une fenêtre fixe de
    // 20 ans (30 pour les financières) avant aujourd'hui, DIVIDENDES INCLUS.
    // Mode synchro : droite sur la plage visible, série selon la case.
    const series = (this.syncRegression && !this.withDividends) ? c.price_raw : c.price_adj;
    const refReg = this.referenceRegression();

    let a, b, sigma, t0;
    if (refReg) {
      // Fenêtre = référence persistée : la droite est celle que la watchlist
      // utilise (régression serveur), pas un re-fit de la série décimée.
      ({ a, b, sigma } = refReg);
      t0 = new Date(refReg.start);
    } else {
      let calcStart, calcEnd;
      if (this.syncRegression) {
        calcStart = i0;
        calcEnd = i1;
      } else {
        calcEnd = allDates.length - 1;
        calcStart = this.fixedWindowStart(allDates, calcEnd);
      }

      t0 = new Date(allDates[calcStart]);
      const times = [], prices = [];
      for (let i = calcStart; i <= calcEnd; i++) {
        if (series[i] == null || series[i] <= 0) continue;
        times.push((new Date(allDates[i]) - t0) / (365.25 * 864e5));
        prices.push(series[i]);
      }
      ({ a, b, sigma } = olsLog(times, prices));
    }

    // --- Indicateurs lus au dernier point VISIBLE (i1), sur la droite ----
    // calculée ci-dessus. En mode figé, la droite est sur la fenêtre 20/30 ans
    // mais on observe le bout de la sous-période zoomée (exploration détaillée).
    // Vue référence : on lit au dernier cours réel (identité + ref_stats.end).
    const obs = refReg
      ? { price: this.data.identity.last_price, date: refReg.end }
      : null;
    this.computeLive(a, b, sigma, t0, allDates, series, i1, obs);

    // β (amplitude) & ρ (solidité) A~B : recalculés sur la fenêtre VISIBLE [i0, i1]
    // (et non calcStart/calcEnd), pour suivre ce qu'on regarde. Ratio uniquement.
    if (this.isRatio() && c.series_a && c.series_b) {
      this.live.beta = scored(betaLive(c.series_a, c.series_b, i0, i1), "beta", 2);
      this.live.correlation = scored(corrLive(c.series_a, c.series_b, i0, i1), "corr", 2);
    }

    // Droite + bandes sur toute la plage AFFICHÉE.
    const xs = allDates.slice(i0, i1 + 1);
    const line = [], up1 = [], lo1 = [], up2 = [], lo2 = [];
    for (let i = i0; i <= i1; i++) {
      const t = (new Date(allDates[i]) - t0) / (365.25 * 864e5);
      const fit = a + b * t;
      line.push(Math.exp(fit));
      up1.push(Math.exp(fit + sigma)); lo1.push(Math.exp(fit - sigma));
      up2.push(Math.exp(fit + 2 * sigma)); lo2.push(Math.exp(fit - 2 * sigma));
    }
    const ys = series.slice(i0, i1 + 1);

    const band = (yLow, yHigh, color) => [
      { x: xs, y: yHigh, line: { width: 0 }, hoverinfo: "skip", showlegend: false, mode: "lines" },
      { x: xs, y: yLow, fill: "tonexty", fillcolor: color, line: { width: 0 }, hoverinfo: "skip", showlegend: false, mode: "lines" },
    ];
    // --- Marqueurs de transactions (#17.4) : triangles achat/vente du
    // PORTEFEUILLE (jamais la table events). Couche d'annotation PURE : ils
    // n'entrent NI dans la régression NI dans les bandes (droite calculée plus
    // haut sans eux). Masqués par défaut (case « Transactions »).
    const txTraces = [];
    if (this.showTx) {
      const txCcy = this.data.identity.currency || "";
      const buys = { x: [], y: [], text: [] };
      const sells = { x: [], y: [], text: [] };
      for (const tx of this._visibleTx(i0, i1)) {
        const px = series[tx.idx];
        if (px == null || px <= 0) continue;
        const bucket = tx.side === "sell" ? sells : buys;
        bucket.x.push(allDates[tx.idx]);
        bucket.y.push(px);
        bucket.text.push(
          `${tx.side === "sell" ? "Vente" : "Achat"} · ${allDates[tx.idx]} · ${this.fmt(tx.quantity)} × ${this.fmt(tx.price)} ${txCcy}`,
        );
      }
      const marker = (bucket, symbol, color) => ({
        x: bucket.x, y: bucket.y, text: bucket.text,
        name: symbol === "triangle-up" ? "Achats" : "Ventes",
        mode: "markers", type: "scatter",
        marker: { symbol, size: 11, color, line: { width: 0 } },
        hoverinfo: "text", showlegend: false,
      });
      if (buys.x.length) txTraces.push(marker(buys, "triangle-up", C.accent));
      if (sells.x.length) txTraces.push(marker(sells, "triangle-down", C.bad));
    }

    const traces = [
      ...band(line, up2, C.badFill),
      ...band(line, up1, C.badFill),
      ...band(lo1, line, C.goodFill),
      ...band(lo2, line, C.goodFill),
      { x: xs, y: line, name: "droite d'Obole", mode: "lines", line: { color: C.neutral, width: 1.5, dash: "dash" } },
      { x: xs, y: ys, name: "Cours", mode: "lines", line: { color: C.accent, width: 2 } },
      ...txTraces,
    ];

    if (this.showMA) {
      // MM précalculées serveur sur la série pleine résolution (voir serialize.py).
      // Sélection RAW/ADJ / ratio-indice portée par _maBySeries (source unique).
      const { maShort, maLong } = this._maBySeries(series);
      if (maShort && maLong) {
        traces.push({ x: xs, y: maShort.slice(i0, i1 + 1), name: "MM" + this._maShort, mode: "lines", line: { color: C.ma1, width: 1.2 } });
        traces.push({ x: xs, y: maLong.slice(i0, i1 + 1), name: "MM" + this._maLong, mode: "lines", line: { color: C.ma2, width: 1.2 } });
      }
    }

    // Repère « aujourd'hui » : plus de marqueur Plotly dédié — l'overlay du
    // curseur marque déjà le dernier cours (et suit la souris), en évitant un
    // double point superposé au repos. `lastX` ne sert plus qu'au bornage de l'axe.
    const lastX = xs[xs.length - 1];

    // Échelle Y : ajustée à la plage visible (évite l'aplatissement).
    let yMin = Infinity, yMax = -Infinity;
    for (let i = 0; i < ys.length; i++) {
      if (ys[i] == null) continue;
      yMin = Math.min(yMin, ys[i], lo2[i]); yMax = Math.max(yMax, ys[i], up2[i]);
    }
    const yRange = this.logScale
      ? [Math.log10(yMin * 0.97), Math.log10(yMax * 1.03)]
      : [yMin * 0.97, yMax * 1.03];

    // --- Annotations d'événements : design minimaliste (case « Événements »).
    // Segment vertical PÂLE (gris de la droite, pointillé fin) partant du
    // cours à la date et borné en haut à droite + 2σ (couloir de régression) ;
    // libellé = nom seul, petit texte gris SANS boîte au-dessus du trait.
    // Description uniquement au survol.
    const evAnnotations = [];
    const evShapes = [];
    if (this.showEvents) {
      const visibleEvents = this._visibleEvents(i0, i1);
      const yConv = this.logScale ? (v) => Math.log10(v) : (v) => v;
      for (let k = 0; k < visibleEvents.length; k++) {
        const ev = visibleEvents[k];
        // Extrémités en repère data : bas = cours à la date (point de droite
        // si pas de cotation), haut = bande +2σ de la droite affichée.
        const t = (new Date(allDates[ev.idx]) - t0) / (365.25 * 864e5);
        const fit = a + b * t;
        const price = series[ev.idx];
        const yTop = Math.exp(fit + 2 * sigma);
        const yStart = price != null && price > 0 ? price : Math.exp(fit - 2 * sigma);
        evShapes.push({
          type: "line", x0: allDates[ev.idx], x1: allDates[ev.idx],
          y0: yStart, y1: yTop, yref: "y",
          line: { color: C.neutral, width: 1.5, dash: "dot" },
        });
        evAnnotations.push({
          xref: "paper", yref: "y",
          // Position X en papier (proportion dans la fenêtre visible, bornée
          // à [0.03, 0.97] pour ne pas être rognée aux bords) ; libellé juste
          // au-dessus de l'extrémité haute du trait (bande +2σ), sans fond.
          x: Math.min(0.97, Math.max(0.03, (ev.idx - i0) / Math.max(1, i1 - i0))),
          y: yConv(yTop),
          text: ev.label, showarrow: false,
          xanchor: "center", yanchor: "bottom",
          font: { size: 10, color: C.text },
          hovertext: ev.description ? `${ev.label} — ${ev.date.slice(0, 4)}<br>${ev.description}` : ev.label,
        });
      }
    }

    const layout = {
      margin: { l: 52, r: CURSOR_MARGIN_R, t: 16, b: 28 },
      height: CHART_HEIGHTS.hero, paper_bgcolor: "transparent", plot_bgcolor: "transparent",
      font: { family: "Inter, sans-serif", size: 12, color: C.text },
      // `showspikes:false` : on supprime la ligne verticale native de Plotly,
      // remplacée par celle, discrète, de l'overlay du curseur.
      xaxis: { gridcolor: C.grid, showline: false, range: [xs[0], lastX], showspikes: false },
      yaxis: { type: this.logScale ? "log" : "linear", gridcolor: C.grid, showline: false, range: yRange },
      showlegend: this.showMA, legend: { orientation: "h", y: 1.1, font: { size: 11 } },
      // Hover NATIF désactivé : l'overlay du curseur est la source unique du
      // readout prix·σ/date. Le tooltip unifié se superposait à l'overlay
      // (double lecture) — `hovermode:false` le supprime.
      hovermode: false,
      annotations: evAnnotations,
      shapes: evShapes,
    };
    Plotly.react("chart", traces, layout, { displayModeBar: false, responsive: true }).then(() => {
      // Géométrie du curseur : ce que l'overlay lit pour se projeter en pixels.
      // Séries recalculées CLIENT (line/up1/lo1/up2/lo2), jamais rejouées ici.
      const ccy = this.data.identity.currency || "";
      this._cursorGeom = {
        xs, xms: xs.map((d) => Date.parse(d)),
        sigma, ccy, line, up1, lo1, up2, lo2, ys,
      };
      this._setupCursor();
    });
  },

  // --- Sections analytiques : blocs thématiques. Chaque carte porte un `type`
  //     qui pilote le rendu (combo bar+ligne, multi-séries + seuils, barres,
  //     courbe longue…) et une `section` qui la rattache à un onglet
  //     (`sections.js`). La fiche n'affiche qu'une section à la fois : le
  //     filtrage ci-dessous ne renvoie que les blocs de la section active.

  // Blocs rattachés à la section courante. Avant l'arrivée des données (ou pour
  // un ratio/indice, qui n'a pas de comptes), on ne filtre pas : le template
  // reçoit une liste vide de toute façon et le rail reste fonctionnel.
  _groupsFor(section) {
    // La section Dividende a sa propre taxonomie serveur (DIVIDEND_GROUPS) : elle
    // ne passe pas par `fundamentalGroups` (qui ne porte que Quantitatif +
    // Valorisation). Un ratio/indice n'a pas de comptes -> liste vide.
    if (section === "dividende") {
      return typeof this.dividendGroups === "function" ? this.dividendGroups() : [];
    }
    // Section Valorisation : la calculatrice (pleine largeur) et les courbes
    // continues (VALUATION_GROUPS) sont rendues par un template DÉDIÉ, dans
    // l'ordre voulu (calculatrice puis mini-charts). On ne les expose donc PAS
    // via `sectionGroups()` (sinon doublon et ordre inversé).
    if (section === "valorisation") return [];
    // Section Momentum (Clara Vallis) : template dédié (table + trois blocs),
    // aucun groupe de cartes génériques à exposer.
    if (section === "momentum") return [];
    const groups = this.fundamentalGroups();
    if (!groups.length) return groups;
    return groups
      .map((g) => ({ ...g, cards: g.cards.filter((c) => c.section === section) }))
      .filter((g) => g.cards.length);
  },

  sectionGroups() {
    return this._groupsFor(this.activeSection);
  },

  // Une section a-t-elle du contenu pour la fiche affichée ? Sert à désactiver
  // les onglets qui n'ont rien à montrer (un ratio/indice n'a pas de
  // comptes : Quantitatif, Dividende, Finance seraient vides). Avant le
  // chargement (`data` null), la barre reste complète : on ne sait pas encore.
  sectionAvailable(id) {
    if (!this.data) return true;
    if (id === "resume") return true;
    // Thèse & Société : réservée aux actions (un ratio / un indice n'a ni
    // dirigeants ni document de thèse). C'est un contenu de FICHE ACTION.
    if (id === "these") return this.data.kind_payload === "stock";
    if (id === "finance") return !!this.data.fundamentals;  // section « données manuelles »
    // Valorisation : la calculatrice (ou les courbes) doit être calculable.
    if (id === "valorisation") {
      if (typeof this.valuationAvailable === "function" && this.valuationAvailable()) return true;
      return typeof this.valuationGroups === "function" && this.valuationGroups().length > 0;
    }
    // Momentum : actions et indices, jamais un ratio, et seulement si le
    // payload porte assez de séances pour calculer la table.
    if (id === "momentum") {
      const kind = this.data.kind_payload;
      if (kind !== "stock" && kind !== "basket") return false;
      return typeof this.momAvailable === "function" && this.momAvailable();
    }
    return this._groupsFor(id).length > 0;
  },

  fundamentalGroups() {
    const f = this.data.fundamentals;
    if (!f) return [];
    if (f.kind === "financial") return this.financialGroups(f);
    const has = (n) => f.metrics[n] !== undefined;
    // La section est un paramètre OBLIGATOIRE : une carte non taguée ne doit pas
    // retomber silencieusement dans Quantitatif (source unique du rattachement).
    const card = (section, c) => ({ ...c, section, id: slug(c.title) });
    const groups = [];

    // Blocs 1-3 — section Quantitatif. La taxonomie est la SOURCE UNIQUE
    // `config.QUANT_GROUPS` (servie par /api/meta) : le front n'invente plus de
    // cartes, il filtre celles dont la métrique existe réellement pour ce titre.
    // Une métrique par graphe (fin des combos CA+marge).
    for (const grp of QUANT_GROUPS) {
      const cards = [];
      for (const def of grp.cards) {
        if (def.type === "cagr") {
          if (f.growth) cards.push(card("quantitatif", { ...def }));
          continue;
        }
        const metrics = (def.metrics || []).filter(has);
        if (metrics.length) cards.push(card("quantitatif", { ...def, metrics }));
      }
      if (cards.length) groups.push({ title: grp.title, cards });
    }

    // La section Valorisation a sa propre taxonomie serveur (`VALUATION_GROUPS`,
    // courbes continues) et sa calculatrice : elle ne passe plus par ici.
    return groups;
  },

  financialGroups(f) {
    const has = (n) => f.metrics[n] !== undefined;
    const card = (section, c) => ({ ...c, section, id: slug(c.title) });
    const groups = [];
    const rent = ["ROE", "ROA"].filter(has);
    const cards1 = [];
    if (rent.length) cards1.push(card("quantitatif", { type: "line", title: "Rentabilités", metrics: rent }));
    if (has("Bénéfice net")) cards1.push(card("quantitatif", { type: "bars", title: "Bénéfice net", metrics: ["Bénéfice net"] }));
    if (cards1.length) groups.push({ title: "Rentabilité", cards: cards1 });
    const bilan = ["Total de l'actif", "Actif net"].filter(has)
      .map((m) => card("quantitatif", { type: "bars", title: m, metrics: [m] }));
    if (bilan.length) groups.push({ title: "Bilan", cards: bilan });
    return groups;
  },

  // CAGR (croissance annualisée), lus pour le template (carte type cagr).
  // On privilégie 5 ans ; si N/A (yfinance plafonne ~5 colonnes), on retombe sur 3 ans.

  cagrItems() {
    const g = this.data.fundamentals?.growth;
    if (!g) return [];
    const defs = [["CA", "revenue"], ["BNPA", "eps"], ["FCF", "fcf"]];
    return defs.map(([label, key]) => {
      const v5 = g[`cagr_${key}_5y`], v3 = g[`cagr_${key}_3y`];
      const v = v5 != null ? v5 : v3;
      const span = v5 != null ? "5a" : "3a";
      return {
        label: `${label} (${span})`,
        display: v == null ? "—" : (v >= 0 ? "+" : "") + v.toFixed(1) + " %",
        good: v == null ? null : v >= 0,
      };
    });
  },

  // KPI dividende : déplacé dans le mixin `dividend.js` (section dédiée).

  // --- Routage d'affichage des cartes (types Quantitatif + Dividende) -----
  // Le template est générique : ces helpers décident si une carte est un graphe,
  // sa largeur, sa puce « N ans », ses pastilles et son état vide, quel que soit
  // le module qui l'a produite.

  NON_CHART_TYPES,

  isChartCard(c) {
    return !NON_CHART_TYPES.has(c.type);
  },

  // Carte mise en avant (pleine largeur, hauteur héro de section). Piloté par la
  // taxonomie (config.QUANT_GROUPS / DIVIDEND_GROUPS, champ `wide`) : le front ne
  // décide plus quelles cartes sont larges. Les autres tiennent en colonne simple
  // (grille adaptative auto-fit minmax), comme le Quantitatif.
  isWideCard(c) {
    return !!c.wide;
  },

  // Puce de couverture « N ans » (0 = pas de puce).
  cardSpanOf(c) {
    if (c.type === "kpi" || c.type === "cagr") return 0;
    if (c.type === "vline") return 0;  // série continue : couverture portée par le zoom
    if (typeof this.dividendCardSpan === "function" && this.isDividendCard(c)) {
      return this.dividendCardSpan(c);
    }
    return this.cardSpan(c);
  },

  isDividendCard(c) {
    return ["yield", "divbars", "divgrowth", "lines", "stacked", "kpi"].includes(c.type);
  },

  // La carte est-elle extensible en plein écran ? (courbes continues uniquement).
  isValuationCard(c) {
    return c.type === "vline";
  },

  // État vide d'une carte (moins de 2 points à tracer).
  cardEmptyOf(c) {
    if (this.isValuationCard(c)) {
      const series = this.data?.chart?.[c.series];
      return !series || series.filter((v) => v != null).length < 2;
    }
    if (typeof this.dividendCardEmpty === "function" && this.isDividendCard(c)) {
      return this.dividendCardEmpty(c);
    }
    return this.cardEmpty(c);
  },

  // Pastilles sous une carte (dernière valeur / stats de fenêtre).
  cardPillsOf(c) {
    if (this.isValuationCard(c) && typeof this.valuationPills === "function") {
      return this.valuationPills(c);
    }
    if (typeof this.dividendSeriesPills === "function" && this.isDividendCard(c)) {
      if (c.type === "yield") return this.yieldPills(c);
      if (c.type === "divbars") return this.dividendPerfPills();
      if (c.type === "lines" || c.type === "stacked") return this.dividendSeriesPills(c);
      return [];
    }
    return this.cardPills(c);
  },

  // --- Rendu des cartes : route selon le type --------------------------

  drawMinis() {
    const f = this.data.fundamentals;
    if (!f) return;
    // Section Dividende : tracé délégué au mixin dédié (taxonomie DIVIDEND_GROUPS).
    if (this.activeSection === "dividende") {
      if (typeof this.drawDividendCards === "function") this.drawDividendCards();
      return;
    }
    // Section Valorisation : calculatrice (graphique + matrice) + courbes
    // continues (taxonomie VALUATION_GROUPS). Délégué au mixin dédié.
    if (this.activeSection === "valorisation") {
      if (typeof this.drawValuationChart === "function") {
        try { this.drawValuationChart(); } catch (e) { console.error("val chart error:", e); }
        this.drawValuationLines();
      }
      return;
    }
    this.sectionGroups().forEach((grp) => {
      grp.cards.forEach((c) => {
        const el = "mc-" + c.id;
        if (!document.getElementById(el)) return;
        // Pas assez de points : on purge un éventuel tracé précédent et on laisse
        // le template afficher l'état vide (message explicite, pas un cadre nu).
        if (this.cardEmpty(c)) {
          try { Plotly.purge(el); } catch { /* jamais monté */ }
          return;
        }
        try {
          if (c.type === "line") this.drawLines(el, c);
          else if (c.type === "bars") this.drawBars(el, c);
          else if (c.type === "shares") this.drawShares(el, c);
        } catch (e) { console.error("drawMinis card error:", c.id, c.type, e); }
      });
    });
    this.drawCompare();
  },

  miniLayout(extra = {}) {
    // Axe X : par défaut « category » (années discrètes). Quand une plage
    // numérique est fournie (`xRange`), l'axe devient linéaire et PARTAGÉ par
    // toutes les cartes d'une section : une série de 4 ans occupe alors 4/17 de
    // la largeur d'une série de 17 ans — l'échelle est relative au nombre de
    // données réellement disponibles (pas d'étirement trompeur).
    const { xRange, ...rest } = extra;
    const xaxis = xRange
      ? { gridcolor: C.grid, type: "linear", range: xRange, nticks: 6, tickformat: "d" }
      : { gridcolor: C.grid, type: "category" };
    return {
      // Hauteur par défaut = standard mini-chart (config.py -> /api/meta). Les
      // appelants peuvent la surcharger (héro, modale, cartes pleine largeur).
      margin: { l: 44, r: 12, t: 6, b: 36 }, height: CHART_HEIGHTS.mini,
      paper_bgcolor: "transparent", plot_bgcolor: "transparent",
      font: { family: "Inter, sans-serif", size: 10, color: C.text },
      xaxis, yaxis: { gridcolor: C.grid },
      showlegend: false,
      legend: { orientation: "h", y: -0.3, xanchor: "center", x: 0.5, font: { size: 10 } },
      ...rest,
    };
  },

  // Plage temporelle d'une carte : celle de SA donnée (années réellement
  // renseignées), étendue de 0,5 an de chaque côté pour que les barres ne
  // touchent pas les bords. C'est l'échelle RELATIVE au nombre de données : une
  // carte de 4 ans couvre 4 ans, une carte de 17 ans couvre 17 ans — aucune
  // série courte n'est étirée sur la largeur d'une série longue.
  yearRange(card = {}) {
    const years = this.cardYears(card);
    if (!years.length) return null;
    return [years[0] - 0.5, years[years.length - 1] + 0.5];
  },

  // Lignes de seuil horizontales (pointillés) pour les métriques de `series`.

  thresholdShapes(series) {
    const shapes = [];
    const seen = new Set();
    series.forEach((m) => {
      const t = RATIO_THRESHOLDS[m];
      if (t && !seen.has(t[0])) {
        seen.add(t[0]);
        shapes.push({ type: "line", xref: "paper", x0: 0, x1: 1, y0: t[0], y1: t[0],
          line: { color: C.neutral, width: 1, dash: "dash" } });
      }
    });
    return shapes;
  },

  // Années réellement renseignées d'une carte (union des métriques). Sert la
  // puce « N ans disponibles » : on ne prétend jamais couvrir plus que la donnée.
  cardYears(card) {
    const f = this.data.fundamentals;
    if (!f) return [];
    const src = card.src === "valuation" ? f.valuation : f;
    if (!src) return [];
    const years = card.src === "valuation" ? f.valuation.years : f.years;
    const set = new Set();
    for (const m of (card.metrics || [])) {
      const row = src.metrics[m];
      if (!row) continue;
      years.forEach((y, i) => { if (row[i] != null) set.add(y); });
    }
    return [...set].sort((a, b) => a - b);
  },

  cardSpan(card) { return this.cardYears(card).length; },

  // Nombre de points de la série la plus longue d'une carte. Sert l'état vide :
  // une métrique dont la ligne existe mais est entièrement vide (ou à un seul
  // point) ne doit pas produire un graphe vide sans explication.
  cardPointCount(card) {
    return (card.metrics || [])
      .reduce((max, m) => Math.max(max, this.metricSeries(card, m).values.length), 0);
  },

  // Une carte n'a pas assez de données pour un tracé lisible (< 2 points).
  // Les cartes NON basées sur `metrics` (dividende par action, rachats) lisent
  // leur propre série et ne passent jamais par cet état vide.
  cardEmpty(card) {
    if (!card.metrics || !card.metrics.length) return false;
    return this.cardPointCount(card) < 2;
  },

  // Unité d'une métrique (pour le formatage des pastilles et de l'axe Y) :
  // "pct" (%), "mult" (multiple, ex. Liquidité 2,47×, PER 12,5×) ou "money"
  // (montant/action). SOURCE UNIQUE `config.METRIC_UNITS` (via /api/meta) :
  // le front ne reclassifie rien en dur, une métrique renommée reste correcte.
  metricUnit(name) {
    return METRIC_UNITS[name] || "money";
  },

  // Dernière valeur renseignée d'une métrique (année la plus récente).
  metricLast(name) {
    const { values } = this.metricSeries({}, name);
    const last = values.length ? values[values.length - 1] : null;
    return last;
  },

  // Pastille de synthèse : « LIBELLÉ : valeur unité », colorée par la polarité du
  // ratio (bleu = bon). Les montants ne sont pas colorés (neutres). Sert la
  // lecture « où en est-on » sous le graphe, comme sur la maquette Obole.
  metricPill(name) {
    const v = this.metricLast(name);
    if (v == null) return null;
    const unit = this.metricUnit(name);
    const display = unit === "pct" ? this.fmt(v) + " %"
      : unit === "mult" ? this.fmt(v) + "×"
      : this.fmtCap(v);
    return { label: name, display, good: unit === "money" ? null : ratioGood(name, v) };
  },

  // Pastilles d'une carte : une par métrique tracée (ordre de la carte).
  cardPills(card) {
    return (card.metrics || []).map((m) => this.metricPill(m)).filter(Boolean);
  },

  // Renvoie {years, values} triés en ordre chronologique CROISSANT (ancien ->
  // récent). L'axe est HONNÊTE : on ne conserve que les années réellement
  // renseignées (les années sans donnée ne sont pas affichées comme des trous),
  // donc une série de 4 ans n'est jamais étirée sur la largeur d'une série de
  // 17 ans. La couverture est rendue explicite par la puce « N ans disponibles ».

  metricSeries(card, name) {
    const f = this.data.fundamentals;
    const src = card.src === "valuation" ? f.valuation : f;
    const years = card.src === "valuation" ? f.valuation.years : f.years;
    const row = src?.metrics?.[name];
    if (!row) return { years: [], values: [] };
    const pairs = years.map((y, i) => [y, row[i]])
      .filter((p) => p[1] != null);
    pairs.sort((a, b) => a[0] - b[0]);
    // Années NUMÉRIQUES : l'axe est linéaire (cf. miniLayout/xRange), donc une
    // série courte n'est jamais étirée sur la largeur d'une série longue.
    return { years: pairs.map((p) => p[0]), values: pairs.map((p) => p[1]) };
  },

  // Lignes + marqueurs (N métriques, une couleur par métrique). Palette unifiée
  // sans rouge ni vert (bleu, teal, violet, ambre) — cf. conventions du projet.
  // Les lignes de seuil (pointillés) sont ajoutées quand la métrique en a un.

  drawLines(el, card, height = CHART_HEIGHTS.mini) {
    const palette = [C.accent, C.teal, C.ma2, C.ma1];
    const traces = (card.metrics || []).map((m, i) => {
      const { years, values } = this.metricSeries(card, m);
      return { x: years, y: values, name: m, mode: "lines+markers",
        line: { color: palette[i % palette.length], width: 2 }, marker: { size: 6 } };
    });
    // Lignes de seuil uniquement sur une carte à UNE métrique : sur une famille
    // de ratios (Marges, Rentabilités), plusieurs seuils différents coexisteraient
    // (ROE 10 % vs ROCE 15 %) et l'utilisateur ne saurait plus quelle ligne
    // s'applique à quelle courbe.
    const single = (card.metrics || []).length === 1;
    const shapes = single ? this.thresholdShapes(card.metrics || []) : [];
    const suffix = (card.metrics || []).every((m) => this.metricUnit(m) === "pct") ? " %" : "";
    Plotly.react(el, traces, this.miniLayout({
      xRange: this.yearRange(card), shapes, height, showlegend: traces.length > 1,
      yaxis: { gridcolor: C.grid, ticksuffix: suffix },
    }), { displayModeBar: false, responsive: true });
  },

  // Barres groupées (flux : CA, bénéfice, cash, trésorerie/dette, capitaux…).
  // Si ≤6 points, lignes+marqueurs (un histogramme de 4 barres est illisible).

  drawBars(el, card, height = CHART_HEIGHTS.mini) {
    const palette = [C.accent, C.teal];
    const first = this.metricSeries(card, card.metrics[0]);
    const useLines = first.values.length <= 6;
    const traces = card.metrics.map((m, i) => {
      const { years, values } = this.metricSeries(card, m);
      if (useLines) {
        // Area fill uniquement sur une courbe SIMPLE (convention projet : pas de
        // fill sur les multi-séries, la superposition serait illisible).
        const simple = card.metrics.length === 1;
        return { x: years, y: values, name: m, mode: "lines+markers",
          line: { color: palette[i % palette.length], width: 2 }, marker: { size: 6 },
          ...(simple ? { fill: "tozeroy", fillcolor: "rgba(37,99,235,.06)" } : {}),
          showlegend: true };
      }
      return { x: years, y: values, type: "bar", name: m, marker: { color: palette[i % palette.length] },
        showlegend: true };
    });
    Plotly.react(el, traces, this.miniLayout({
      xRange: this.yearRange(card), height,
      ...(useLines ? { showlegend: true } : { barmode: "group", showlegend: true }),
    }), { displayModeBar: false, responsive: true });
  },

  // Actions en circulation : barres du nombre d'actions + variation (CAGR) en
  // annotation, pour lire d'un coup d'œil dilution (hausse) vs rachats (baisse).

  drawShares(el, card, height = CHART_HEIGHTS.mini) {
    const { years, values } = this.metricSeries(card, card.metrics[0]);
    const first = values[0], last = values[values.length - 1];
    const change = (first > 0 && values.length > 1)
      ? (Math.pow(last / first, 1 / (values.length - 1)) - 1) * 100 : null;
    const note = change == null ? "" : (change >= 0 ? "+" : "") + change.toFixed(2) + " %/an";
    Plotly.react(el, [{ x: years, y: values, type: "bar", marker: { color: C.accent } }],
      this.miniLayout({
        xRange: this.yearRange(card), height,
        // Marge haute élargie : l'annotation vit AU-DESSUS des barres (jamais
        // par-dessus le tracé, qui remplit la zone sur des valeurs proches).
        margin: { l: 44, r: 12, t: 26, b: 36 },
        annotations: note ? [{ xref: "paper", yref: "paper", x: 0.99, y: 1.14, text: note,
          showarrow: false, xanchor: "right", yanchor: "top", font: { size: 11, color: C.text } }] : [],
      }), { displayModeBar: false, responsive: true });
  },

  // Courbes du dividende (par action, rachats) : déplacées dans `dividend.js`.

  // --- Comparateur (bas de la section Quantitatif) -----------------------
  // Superpose 2-3 métriques choisies par l'utilisateur, REBASÉES à 100 sur leur
  // première valeur pour rendre comparables des unités différentes (montant vs %).
  // Aucun calcul métier nouveau : on réutilise `metricSeries`.

  compareKeys: [],

  // Plafond du comparateur (au-delà, on désactive les pastilles restantes).
  COMPARE_MAX: 3,

  // Options du comparateur : dérivées de la taxonomie `QUANT_GROUPS` (source
  // unique) plutôt que de toutes les métriques du payload — on ne propose que
  // les séries réellement cartées, dans l'ordre du registre.
  compareOptions() {
    const f = this.data?.fundamentals;
    if (!f) return [];
    const seen = new Set();
    const out = [];
    for (const grp of QUANT_GROUPS) {
      for (const c of grp.cards) {
        for (const m of (c.metrics || [])) {
          if (f.metrics?.[m] === undefined || seen.has(m)) continue;
          seen.add(m);
          out.push({ key: m, label: m });
        }
      }
    }
    return out;
  },

  compareFull() { return this.compareKeys.length >= this.COMPARE_MAX; },

  toggleCompare(key) {
    const keys = this.compareKeys.includes(key)
      ? this.compareKeys.filter((k) => k !== key)
      : (this.compareFull() ? this.compareKeys : [...this.compareKeys, key]);
    this.compareKeys = keys;
    // `#compare-chart` est en `x-show="compareKeys.length"` : à la 1re sélection
    // le conteneur est encore `display:none` (largeur nulle) au moment du
    // handler. On trace APRÈS le flush DOM, sinon Plotly rend un graphe vide.
    this.$nextTick(() => this.drawCompare());
  },

  drawCompare() {
    const el = document.getElementById("compare-chart");
    const f = this.data?.fundamentals;
    if (!el) return;
    // Hors section Quantitatif, le conteneur est masqué (x-show) : une taille
    // nulle empêcherait Plotly de tracer. On (re)dessine au retour dans la
    // section (redrawActiveSection -> drawMinis -> drawCompare).
    if (this.activeSection !== "quantitatif" || !f) {
      try { Plotly.purge(el); } catch { /* pas encore monté */ }
      return;
    }
    const keys = this.compareKeys.slice(0, 3);
    if (!keys.length) {
      try { Plotly.purge(el); } catch { /* vide */ }
      return;
    }
    const palette = [C.accent, C.teal, C.ma2];
    const traces = keys.map((k, i) => {
      const { years, values } = this.metricSeries({}, k);
      const base = values.find((v) => v != null && v !== 0);
      const y = base ? values.map((v) => (v == null ? null : (v / base) * 100)) : values;
      return { x: years, y, name: k, mode: "lines+markers",
        line: { color: palette[i % palette.length], width: 2 }, marker: { size: 6 } };
    });
    // Plage commune aux métriques sélectionnées (échelle relative à la donnée).
    const years = keys.flatMap((k) => this.cardYears({ metrics: [k] }));
    const xRange = years.length ? [Math.min(...years) - 0.5, Math.max(...years) + 0.5] : null;
    Plotly.react(el, traces, this.miniLayout({
      xRange, height: CHART_HEIGHTS.mini, showlegend: true,
      // Pas de suffixe « % » : les séries sont rebasées à un INDICE base 100
      // (150 = +50 % depuis la 1re année), pas des pourcentages.
      yaxis: { gridcolor: C.grid, title: { text: "Base 100", font: { size: 10, color: C.text } } },
    }), { displayModeBar: false, responsive: true });
  },

  // --- Info-bulles cliquables --------------------------------------------

  toggleInfo(id) {
    this.showInfo = { ...this.showInfo, [id]: !this.showInfo[id] };
  },

  infoText(id) {
    const texts = {
      "Chiffre-d-affaires": "Chiffre d'affaires annuel : le top-line, moteur de la croissance de l'entreprise.",
      "B-n-fice-net": "Bénéfice net annuel : ce qui reste à l'actionnaire après tous les coûts, intérêts et impôts.",
      "BNPA-dilu-": "Bénéfice net par action dilué = Bénéfice net / nombre d'actions dilué. C'est le vrai moteur long terme du cours (il tient compte de la dilution).",
      "G-n-ration-de-cash": "Cash-flow d'exploitation (OCF) et Free Cash Flow (FCF = OCF − CAPEX). Le FCF disponible rembourse la dette, verse les dividendes ou rachète des actions.",
      "CAPEX--investissements-": "Dépenses d'investissement (Capital Expenditure), en valeur absolue. Un CAPEX soutenu peut préparer la croissance future ou peser sur le cash libre.",
      "SBC--r-mun-ration-en-actions-": "Rémunération en actions (Stock Based Compensation). C'est un coût réel pour l'actionnaire : elle dilue, même si elle ne sort pas de cash.",
      "Croissance-annualis-e--CAGR-": "Taux de croissance annuel moyen sur 5 ans (ou 3 ans si historique insuffisant). CAGR > 0 = croissance, < 0 = décroissance.",
      "Marges": "Marge brute = (CA − coûts directs) / CA (pouvoir de fixation des prix). Marge opérationnelle = Résultat opérationnel / CA (efficacité de l'exploitation). Marge nette = Résultat net / CA (rentabilité finale).",
      "Rentabilit-s--ROE---ROA---ROCE---ROIC-": "ROE = Résultat net / Capitaux propres (rentabilité des fonds actionnaires). ROA = Résultat net / Total actif. ROCE = EBIT / Capitaux employés (seuil 15 %). ROIC = Résultat opérationnel × (1 − impôt) / capital investi (seuil 10 %, à comparer au coût du capital).",
      "Couverture-des-int-r-ts": "Résultat opérationnel / charges d'intérêts. Mesure la capacité à payer les intérêts de la dette. < 3× = couverture tendue, risque accru si les taux montent.",
      "Rentabilit-s": "ROE = Résultat net / Capitaux propres (rentabilité pour l'actionnaire). ROA = Résultat net / Total actif (efficacité de l'actif).",
      "Cash-conversion--FCF---RN-": "Free Cash Flow / Résultat net, en %. > 100 % = le cash généré dépasse le bénéfice comptable (qualité du cash).",
      "Agilit---FCF---CAPEX-": "Free Cash Flow / CAPEX (dépenses d'investissement), en %. > 50 % = l'entreprise génère suffisamment de cash pour financer ses investissements. Mesure la flexibilité financière (Obole).",
      "Levier--dette-nette---EBITDA-": "Dette nette / EBITDA. < 2 = endettement sain ; 2-4 = modéré ; > 4 = profil risqué. L'EBITDA mesure la capacité de remboursement.",
      "Gearing--dette-nette---capitaux-propres-": "Dette nette / Capitaux propres, en %. < 50 % = structure financière prudente. Un gearing élevé signale un risque de surendettement.",
      "Liquidit---actif---passif-circulant-": "Ratio de liquidité générale (current ratio) = actif circulant / passif circulant. < 1 = tension de trésorerie à court terme.",
      "Cash---dette": "Trésorerie disponible et dette brute (avant trésorerie). L'écart entre les deux est la dette nette qui pèse sur le bilan.",
      "Capitaux-propres": "Capitaux propres comptables : les fonds appartenant aux actionnaires. Une base qui se renforce = bilan qui se solidifie.",
      "Actions-en-circulation": "Nombre d'actions en circulation. En baisse = rachats (relutif pour le BNPA) ; en hausse = dilution (émissions, SBC).",
      "Total-de-l-actif": "Total du bilan (actif) : l'ensemble des ressources employées par l'établissement. Une base qui croît signale un développement du bilan.",
      "Actif-net": "Actif net comptable : ce qui reste aux actionnaires une fois les dettes déduites. C'est la base de calcul de la valeur comptable par action.",
      "Dividende---Action": "Dividende annuel versé par action. Série longue (~20-40 ans). Un dividende stable ou croissant signale une politique actionnariale généreuse.",
      "Comparateur-de-m-triques": "Superpose jusqu'à 3 métriques, rebasées à 100 sur leur première valeur, pour comparer des évolutions d'unités différentes.",
      "Dividend-Yield": "Rendement du dividende continu : dividende par action des 12 derniers mois / cours, jour après jour. La médiane et les bornes High/Low se lisent sur la période affichée.",
      "Shareholder-Yield": "Rendement pour l'actionnaire : (dividendes + rachats d'actions) / cours. Les rachats sont annuels (comptes ~5 ans) : la courbe les intègre en escalier.",
      "M-triques-cl-s": "Yield TTM, payout, régularité (années de hausse / sans baisse), CAGR du dividende, fréquence de versement et dernier paiement. Le prochain paiement n'est pas fourni de façon fiable par la source.",
      "Croissance-Dividende---Action": "Croissance annuelle du dividende par action (YoY), en %. Une progression régulière signale une politique actionnariale soutenue.",
      "Payout-Ratios": "Dividende / Bénéfice net (Earnings) et Dividende / Free Cash Flow (FCF). > 80 % = dividende peu soutenable. Historique limité aux ~5 derniers exercices.",
      "Shareholder-Payout-Ratios": "(Dividendes + rachats) / Bénéfice net ou FCF. Mesure l'effort total de retour à l'actionnaire.",
      "Shareholder-Returns": "Montants annuels versés : dividendes (bleu) + rachats d'actions (teal), empilés. Historique limité aux ~5 derniers exercices.",
      "BNPA-par-action": "Bénéfice net par action (dilué) sur la période : le moteur long terme du cours. La courbe relie les exercices connus, adoucis pour la lecture (les paliers restent la donnée réelle).",
      "FCF-par-action": "Free Cash Flow par action (Free Cash Flow total / actions en circulation). Le cash réellement disponible par action, après investissements.",
      "CA-par-action": "Chiffre d'affaires par action (chiffre d'affaires total / actions en circulation). Le top-line par action : une croissance régulière signale un développement du volume d'affaires.",
      "Actif-net-par-action": "Actif net comptable par action (capitaux propres / actions en circulation). La valeur comptable de l'actionnaire : une base qui se renforce signale un bilan qui se solidifie.",
      "P-E": "P/E (Price/Earnings) continu = cours / bénéfice par action du dernier exercice connu. Le dénominateur est reporté par palier entre deux publications.",
      "P-FCF": "P/FCF continu = cours / Free Cash Flow par action du dernier exercice connu. Un P/FCF faible signale un rendement en cash attractif.",
      "P-CA": "P/CA continu = cours / chiffre d'affaires par action. Utile pour comparer des sociétés à marges différentes, ou une société à son propre passé.",
      "P-B": "P/B continu = cours / valeur comptable par action (actif net / actions). < 1 = le cours est sous l'actif net comptable.",
      "EV-EBITDA": "EV/EBITDA continu = (capitalisation + dette nette) / EBITDA. Multiple d'acquisition : combien d'années d'EBITDA pour rembourser l'achat.",
    };
    return texts[id] || "";
  },

  // --- Zoom plein écran d'un mini-chart (modale, zéro requête réseau) ------
  // Réutilise les fonctions de tracé existantes sur un conteneur agrandi. La
  // PLAGE est celle du graphe héro : la modale lit et écrit `rangeStart`/
  // `rangeEnd` (mêmes index que le curseur de période) — source unique, aucune
  // duplication d'état. Aucune donnée n'est re-fetchée.

  detailCard: null,
  // Élément focus avant l'ouverture : restitué à la fermeture (accessibilité).
  _detailPrevFocus: null,

  openChartDetail(card) {
    this.detailCard = card;
    // La plage est PARTAGÉE avec le héro (option A). Pour une carte Dividende,
    // on l'amorce sur la fenêtre par défaut de la CARTE (10/5 ans) afin que la
    // modale s'ouvre sur ce que l'utilisateur vient de voir — sans saut visible
    // (le héro reste la source unique, la modale ne fait que la repositionner).
    // Les autres cartes (Quantitatif) gardent la plage du héro.
    const dates = this.data?.chart?.dates;
    const isDateCard =
      (typeof this.isDividendCard === "function" && this.isDividendCard(card)) ||
      (typeof this.isValuationCard === "function" && this.isValuationCard(card));
    if (dates && dates.length && isDateCard) {
      const [s, e] = this.defaultDateRange(dates);
      this.rangeStart = s;
      this.rangeEnd = e;
    } else if (this.rangeStart == null || this.rangeEnd == null) {
      this.initRange();
    }
    this._detailPrevFocus = typeof document !== "undefined" ? document.activeElement : null;
    this.$nextTick(() => {
      this.drawChartDetail();
      // Focus dans la modale pour capturer le clavier (Échap / Tab).
      const modal = document.getElementById("chart-detail-modal");
      if (modal) modal.focus();
    });
  },

  closeChartDetail() {
    this.detailCard = null;
    // Restitution du focus sur l'élément déclencheur (bouton ⤢).
    const prev = this._detailPrevFocus;
    this._detailPrevFocus = null;
    if (prev && typeof prev.focus === "function") prev.focus();
  },

  // Piège de focus (focus trap) : Tab/Shift+Tab restent dans la modale. Sans
  // plugin externe (front sans dépendance) : on boucle sur les éléments
  // focusables du conteneur.
  detailKeydown(e) {
    if (e.key !== "Tab") return;
    const modal = document.getElementById("chart-detail-modal");
    if (!modal) return;
    const focusables = modal.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    );
    if (!focusables.length) return;
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  },

  // Presets de période (YTD / 1A / 3A / 5A / MAX) : positionnent la plage
  // PARTAGÉE avec le héro (`rangeStart`/`rangeEnd`), via `idxStartBeforeWindow`.
  // Le curseur à deux poignées de la modale (x-model sur les mêmes champs) suit
  // automatiquement : le preset devient un RACCOURCI de positionnement.
  detailPreset(years) {
    const dates = this.data?.chart?.dates;
    if (!dates || !dates.length) return;
    const end = dates.length - 1;
    if (years === "ytd") {
      const y = new Date(dates[end]).getFullYear();
      let start = end;
      for (let i = 0; i <= end; i++) { if (new Date(dates[i]).getFullYear() === y) { start = i; break; } }
      this.rangeStart = start;
      this.rangeEnd = end;
    } else if (years === "max") {
      this.rangeStart = 0;
      this.rangeEnd = end;
    } else {
      this.rangeStart = this.idxStartBeforeWindow(end, Number(years));
      this.rangeEnd = end;
    }
    // La plage est PARTAGÉE avec le héro : on redessine les deux (graphe héro +
    // mini-cartes de la section active) pour éviter que le héro garde l'ancien
    // tracé après fermeture de la modale.
    this.$nextTick(() => {
      this.drawChartDetail();
      if (this.activeSection === "resume") this.drawChart();
      this.drawMinis();
    });
  },

  detailRangeLabel() {
    const dates = this.data?.chart?.dates;
    if (!dates || this.rangeStart == null || this.rangeEnd == null) return "";
    const [s, e] = this.visibleRange();
    const f = (iso) => new Date(iso).toLocaleDateString("fr-FR", { day: "2-digit", month: "short", year: "numeric" });
    return `${f(dates[s])} – ${f(dates[e])}`;
  },

  // Bornes [x0, x1] sur un axe d'ANNÉES, traduites de la plage de DATES visible.
  // Les cartes à barres (Dividende/Action, Croissance) partagent le curseur du
  // héro (index de dates) mais leur axe est en années : on convertit la plage
  // affichée en bornes d'années (+0,5 an de marge pour ne pas coller aux bords).
  detailYearRange() {
    const dates = this.data?.chart?.dates;
    if (!dates || !dates.length) return null;
    const [s, e] = this.visibleRange();
    const y0 = new Date(dates[s]).getFullYear();
    const y1 = new Date(dates[e]).getFullYear();
    return [y0 - 0.5, y1 + 0.5];
  },

  // Déplacement d'une poignée du curseur de la MODALE : la plage est PARTAGÉE
  // avec le héro (option A) -> on redessine la modale ET le héro (graphe + mini-
  // cartes de la section active) pour que l'exploration soit continue.
  onDetailSliderInput() {
    this.drawChartDetail();
    if (this.activeSection === "resume") this.drawChart();
    this.drawMinis();
  },

  drawChartDetail() {
    const card = this.detailCard;
    if (!card) return;
    const el = "chart-detail-plot";
    if (!document.getElementById(el)) return;
    const [i0, i1] = this.visibleRange();
    // Cartes à axe d'ANNÉES (barres) : la plage de dates du curseur est traduite
    // en bornes d'années, sinon la modale ignorerait le curseur (axe différent).
    const yRange = this.detailYearRange();
    try {
      if (card.type === "yield") {
        this.drawYieldCard(el, card, [i0, i1]);
      } else if (card.type === "vline") {
        // Courbes continues de la Valorisation : même patron que le Dividend
        // Yield (série alignée sur les dates + plage partagée).
        this.drawValueLine(el, card, [i0, i1]);
      } else if (card.type === "divbars") {
        this.drawDividendHist(el, CHART_HEIGHTS.detail, yRange);
      } else if (card.type === "divgrowth") {
        this.drawDividendGrowth(el, CHART_HEIGHTS.detail, yRange);
      } else if (card.type === "lines") {
        this.drawDividendLines(el, card, CHART_HEIGHTS.detail);
      } else if (card.type === "stacked") {
        this.drawDividendStacked(el, card, CHART_HEIGHTS.detail);
      } else if (card.type === "line" || card.type === "bars" || card.type === "shares") {
        // Réutilise les tracés du Quantitatif en agrandi : on leur passe la
        // hauteur de la modale (sans quoi le graphe garde la hauteur mini dans un
        // conteneur plus haut, laissant du blanc).
        if (card.type === "line") this.drawLines(el, card, CHART_HEIGHTS.detail);
        else if (card.type === "bars") this.drawBars(el, card, CHART_HEIGHTS.detail);
        else this.drawShares(el, card, CHART_HEIGHTS.detail);
      }
    } catch (e) { console.error("chart detail error:", card.id, card.type, e); }
  },

  // --- Import CSV manuel --------------------------------------------------

};
