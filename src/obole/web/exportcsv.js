// Obole — export CSV (régression/simulation) et import CSV manuel.
import { api } from "./api.js";
import { FUNDAMENTAL_METRICS, olsLog } from "./thresholds.js";
import { parseCSV, parseNumber } from "./util.js";

// Nombre maximal de rejets détaillés conservés dans l'aperçu (le total réel
// reste affiché) — miroir de `config.IMPORT_MAX_REJECT_SAMPLES` côté serveur.
const REJECT_SAMPLE_MAX = 50;

export const exportMixin = {
  openExport() {
    if (!this.data) return;
    const d = this.data.chart.dates;
    const [s, e] = this.visibleRange();
    this.exportForm = {
      mode: "regression",
      startDate: d[s],
      endDate: d[e],
      dividends: this.withDividends,
      windowYears: this.winYears,
    };
    this.exportError = "";
    this.exportOpen = true;
  },

  closeExport() { this.exportOpen = false; },

  onExportModeChange() { this.exportError = ""; },

  onExportDateChange() { this.exportError = ""; },

  // Valide les paramètres : plage dans l'historique, dates ordonnées.

  exportReady() {
    if (!this.data) return false;
    const f = this.exportForm;
    if (!f.startDate || !f.endDate) return false;
    if (f.startDate > f.endDate) return false;
    const d = this.data.chart.dates;
    if (f.startDate < d[0] || f.endDate > d[d.length - 1]) return false;
    return true;
  },

  // Sélectionne la série (raw vs adj) selon la case dividendes.

  _exportSeries() {
    const c = this.data.chart;
    // Case « dividendes réinvestis » cochée -> adj ; décochée -> raw.
    // Pour un ratio/indice, raw = adj (un seul jeu) -> on prend adj.
    if (this.isRatio() || this.isBasket()) return c.price_adj || c.price_raw;
    return this.exportForm.dividends ? c.price_adj : c.price_raw;
  },

  // Sélectionne les séries de MM à exporter selon la série affichée (RAW vs ADJ).
  // Même logique que drawChart : action -> ma_*_raw/ma_*_adj ; ratio/indice -> ma_short/ma_long.

  _maBySeries(series) {
    const c = this.data.chart;
    const maShort = c.ma_short_raw ? (series === c.price_raw ? c.ma_short_raw : c.ma_short_adj) : c.ma_short;
    const maLong = c.ma_long_raw ? (series === c.price_raw ? c.ma_long_raw : c.ma_long_adj) : c.ma_long;
    return { maShort, maLong };
  },

  // Indices de la plage exportée dans data.chart.dates.

  _exportRange() {
    const d = this.data.chart.dates;
    const f = this.exportForm;
    let i0 = 0, i1 = d.length - 1;
    for (let i = 0; i < d.length; i++) { if (d[i] >= f.startDate) { i0 = i; break; } }
    for (let i = d.length - 1; i >= 0; i--) { if (d[i] <= f.endDate) { i1 = i; break; } }
    return [i0, i1];
  },

  // Fenêtre de calcul de la droite (Mode 1) — reproduit la logique de drawChart.
  // Respecte syncRegression et winLocked (fenêtre verrouillée à winYears).

  _exportCalcWindow(i0, i1) {
    const d = this.data.chart.dates;
    if (this.winLocked) {
      // Fenêtre fixe : la droite se calcule sur la plage visible verrouillée.
      return [i0, i1];
    }
    if (this.syncRegression) return [i0, i1];
    const calcEnd = d.length - 1;
    const calcStart = this.fixedWindowStart(d, calcEnd);
    return [calcStart, calcEnd];
  },

  doExport() {
    if (!this.exportReady()) {
      this.exportError = "Paramètres invalides (dates hors historique ou inversées).";
      return;
    }
    this.exportError = "";
    try {
      if (this.exportForm.mode === "regression") this._exportRegression();
      else this._exportSimulation();
    } catch (e) {
      this.exportError = e.message || "Erreur lors de l'export.";
    }
  },

  // Mode 1 : une ligne par point dans la plage, avec droite + bandes + z.

  _exportRegression() {
    const d = this.data.chart.dates;
    const series = this._exportSeries();
    const [i0, i1] = this._exportRange();
    const [calcStart, calcEnd] = this._exportCalcWindow(i0, i1);

    const t0 = new Date(d[calcStart]);
    const times = [], prices = [];
    for (let i = calcStart; i <= calcEnd; i++) {
      if (series[i] == null || series[i] <= 0) continue;
      times.push((new Date(d[i]) - t0) / (365.25 * 864e5));
      prices.push(series[i]);
    }
    if (times.length < 30) {
      this.exportError = "Fenêtre de calcul trop courte (minimum 30 points).";
      return;
    }
    const { a, b, sigma } = olsLog(times, prices);
    const perf = (Math.exp(b) - 1) * 100;
    const { maShort, maLong } = this._maBySeries(series);
    const hasMa = !!(maShort && maLong);

    const lines = [];
    lines.push(`# Obole — droite d'Obole`);
    lines.push(`# ticker: ${this.data.identity.ticker}`);
    lines.push(`# periode: ${this.exportForm.startDate} -> ${this.exportForm.endDate}`);
    lines.push(`# dividendes_reinvestis: ${this.exportForm.dividends ? "oui" : "non"}`);
    lines.push(`# fenetre_calcul: ${d[calcStart]} -> ${d[calcEnd]} (${times.length} points)`);
    lines.push(`# a (intercept): ${a}`);
    lines.push(`# b (pente): ${b}`);
    lines.push(`# sigma (ecart-type log): ${sigma}`);
    lines.push(`# perf_annualisee_pct: ${perf.toFixed(2)}`);
    const mmHeader = hasMa ? `,MM${this._maShort},MM${this._maLong}` : "";
    if (hasMa) {
      lines.push(`# mm_courte: ${this._maShort}`);
      lines.push(`# mm_longue: ${this._maLong}`);
    }
    lines.push("date,prix_observe,droite_fitted,bande_sup_1s,bande_inf_1s,bande_sup_2s,bande_inf_2s,z" + mmHeader);
    for (let i = i0; i <= i1; i++) {
      const p = series[i];
      if (p == null || p <= 0) { lines.push(`${d[i]},,,,,,,${hasMa ? ",," : ""}`); continue; }
      const t = (new Date(d[i]) - t0) / (365.25 * 864e5);
      const fit = a + b * t;
      const z = (Math.log(p) - fit) / sigma;
      const row = [
        d[i], p, Math.exp(fit), Math.exp(fit + sigma), Math.exp(fit - sigma),
        Math.exp(fit + 2 * sigma), Math.exp(fit - 2 * sigma), z,
      ];
      if (hasMa) row.push(maShort[i], maLong[i]);
      lines.push(row.map((v) => this._csvCell(v)).join(","));
    }
    this._downloadCsv(lines.join("\n"), "regression");
  },

  // Mode 2 : pour chaque position de la fenêtre glissante, paramètres + indicateurs.

  _exportSimulation() {
    const d = this.data.chart.dates;
    const series = this._exportSeries();
    const [i0, i1] = this._exportRange();
    const years = Number(this.exportForm.windowYears) || 5;
    const { maShort, maLong } = this._maBySeries(series);
    const hasMa = !!(maShort && maLong);

    const lines = [];
    lines.push(`# Obole — Simulation fenêtre glissante`);
    lines.push(`# ticker: ${this.data.identity.ticker}`);
    lines.push(`# plage: ${this.exportForm.startDate} -> ${this.exportForm.endDate}`);
    lines.push(`# taille_fenetre_ans: ${years}`);
    lines.push(`# pas: natif (serie disponible)`);
    lines.push(`# dividendes_reinvestis: ${this.exportForm.dividends ? "oui" : "non"}`);
    const mmHeader = hasMa ? `,MM${this._maShort},MM${this._maLong}` : "";
    if (hasMa) {
      lines.push(`# mm_courte: ${this._maShort}`);
      lines.push(`# mm_longue: ${this._maLong}`);
    }
    lines.push("date_obs,a,b,sigma,fitted,z,perf_annualisee_pct,potentiel_5y_pct,potentiel_10y_pct,n_points" + mmHeader);

    let count = 0;
    for (let pos = i0; pos <= i1; pos++) {
      const winEnd = this.idxEndForWindow(pos, years);
      if (winEnd > i1) break;  // fenêtre déborde la plage : les suivantes aussi (monotone)
      if (winEnd < pos) continue;
      const t0 = new Date(d[pos]);
      const times = [], prices = [];
      for (let i = pos; i <= winEnd; i++) {
        if (series[i] == null || series[i] <= 0) continue;
        times.push((new Date(d[i]) - t0) / (365.25 * 864e5));
        prices.push(series[i]);
      }
      if (times.length < 30) continue;
      const { a, b, sigma } = olsLog(times, prices);
      const obsPrice = series[winEnd];
      if (obsPrice == null || obsPrice <= 0) continue;
      const tNow = (new Date(d[winEnd]) - t0) / (365.25 * 864e5);
      const fit = a + b * tNow;
      const z = (Math.log(obsPrice) - fit) / sigma;
      const perf = (Math.exp(b) - 1) * 100;
      const pot = (H) => {
        const target = Math.exp(a + b * (tNow + H));
        return (Math.pow(target / obsPrice, 1 / H) - 1) * 100;
      };
      lines.push([
        d[winEnd], a, b, sigma, Math.exp(fit), z, perf, pot(5), pot(10), times.length,
      ].concat(hasMa ? [maShort[winEnd], maLong[winEnd]] : []).map((v) => this._csvCell(v)).join(","));
      count++;
    }
    if (count === 0) {
      this.exportError = "Aucune fenêtre valide (minimum 30 points par fenêtre). Élargis la plage ou la taille de fenêtre.";
      return;
    }
    this._downloadCsv(lines.join("\n"), "simulation");
  },

  // Formate une valeur pour le CSV : décimale point, pas de séparateur de milliers.

  _csvCell(v) {
    if (v == null) return "";
    if (typeof v === "number") {
      if (!isFinite(v)) return "";
      return Number(v.toFixed(6)).toString();
    }
    return String(v);
  },

  // Déclenche le téléchargement du CSV via Blob + <a download>.

  _downloadCsv(content, mode) {
    const ticker = (this.data.identity.ticker || "obole").toUpperCase();
    const yyyymmdd = new Date().toISOString().slice(0, 10).replace(/-/g, "");
    const fname = `obole_${ticker}_${mode}_${yyyymmdd}.csv`;
    const blob = new Blob([content], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = fname;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    this.exportOpen = false;
  },

  // --- Événements (annotations datées des graphiques) ----------------------

  // Ref brut de l'événement : ticker (action), "A/B" (ratio), "INDEX:<id>"
  // (panier). Miroir de data/events.py::event_key. Le passage à l'API se fait
  // via _eventsQuery() : le « / » d'un ratio est interdit dans un segment de
  // chemin (Starlette le décode avant le routage), donc query params.

  openImport() {
    this.showImportModal = true;
    this.importPreview = null;
    this.importError = "";
    this.importPasteText = "";
  },

  // Normalise un en-tête CSV pour un rapprochement tolérant (casse + espaces),
  // identique à `data/manual._normalize_header` côté serveur : l'aperçu et
  // l'import reconnaissent donc les mêmes colonnes.
  _normHeader(s) { return String(s).trim().toLowerCase(); },

  // Libellé français d'une raison de rejet (source : `config.IMPORT_REJECT_REASONS`).
  rejectReason(reason) {
    return {
      unparseable: "valeur non numérique",
      derived_column: "ratio calculé (recalculé serveur)",
      unknown_column: "colonne inconnue",
      bad_year: "année illisible",
    }[reason] || reason;
  },

  // Analyse un texte CSV (fichier OU collage) et construit l'aperçu, en MIROIR du
  // serveur (délimiteur + nombres + raisons de rejet). L'utilisateur voit donc
  // exactement ce qui sera écrit, écrasé, et ce qui est écarté — et pourquoi.
  _buildPreview(text) {
    const f = this.data.fundamentals;
    // Écrasement = une valeur MANUELLE existante remplacée. On se base sur les
    // entrées manuelles réelles, pas sur les années yfinance : le serveur compte
    // `metric in existing.get(year)` (manuel seul). Un aperçu qui compterait les
    // années yfinance annoncerait « écrasement » là où le serveur dira « ajout ».
    const manualByYear = new Map();
    for (const e of f?.manual_entries || []) {
      if (!manualByYear.has(e.year)) manualByYear.set(e.year, new Set());
      manualByYear.get(e.year).add(e.metric);
    }
    // Métriques ÉDITABLES : seules les colonnes « source » de la taxonomie
    // (source unique /api/meta) sont réimportées ; dérivées et inconnues sont
    // listées à part. Aucun nom en dur ici.
    const sourceMetrics = FUNDAMENTAL_METRICS.filter((m) => m.role === "source").map((m) => m.name);
    const derivedMetrics = FUNDAMENTAL_METRICS.filter((m) => m.role === "derived").map((m) => m.name);

    const rows = parseCSV(text);
    if (rows.length < 2) { this.importError = "Fichier vide ou invalide"; return; }

    const header = rows[0];
    const headerKeys = header.map((h) => this._normHeader(h));
    const yearIdx = headerKeys.indexOf("year");
    if (yearIdx < 0) { this.importError = "Colonne 'year' introuvable"; return; }
    const colByMetric = {};
    for (const metric of sourceMetrics) {
      const idx = headerKeys.indexOf(this._normHeader(metric));
      if (idx >= 0) colByMetric[metric] = idx;
    }
    // Colonnes vues mais non importées, pour expliquer l'écart au total.
    const sourceKeys = new Set(sourceMetrics.map((m) => this._normHeader(m)));
    const derivedKeys = new Set(derivedMetrics.map((m) => this._normHeader(m)));
    const unknownColumns = [], derivedColumns = [];
    headerKeys.forEach((key, i) => {
      if (key === "" || key === "year" || sourceKeys.has(key)) return;
      (derivedKeys.has(key) ? derivedColumns : unknownColumns).push(header[i]);
    });

    const entries = [], rejected = [];
    let overrideCount = 0;
    let rejectedTotal = 0;
    for (let i = 1; i < rows.length; i++) {
      const cols = rows[i];
      const yearVal = parseNumber(cols[yearIdx]);
      const year = yearVal == null ? null : Math.trunc(yearVal);
      if (year == null) {
        if (sourceMetrics.some((m) => colByMetric[m] !== undefined && (cols[colByMetric[m]] || "").trim())) {
          rejectedTotal++;
          if (rejected.length < REJECT_SAMPLE_MAX) {
            rejected.push({ year: null, metric: null, raw: (cols[yearIdx] || "").trim(), reason: "bad_year" });
          }
        }
        continue;
      }
      for (const metric of sourceMetrics) {
        const hIdx = colByMetric[metric];
        if (hIdx === undefined || hIdx >= cols.length) continue;
        const raw = (cols[hIdx] || "").trim();
        if (!raw) continue;
        const v = parseNumber(raw);
        if (v == null) {
          rejectedTotal++;
          if (rejected.length < REJECT_SAMPLE_MAX) rejected.push({ year, metric, raw, reason: "unparseable" });
          continue;
        }
        const override = manualByYear.get(year)?.has(metric) || false;
        if (override) overrideCount++;
        entries.push({ year, metric, value: v, override });
      }
    }

    if (!entries.length && !rejected.length) { this.importError = "Aucune valeur valide trouvée"; return; }

    this.importPreview = {
      rows: entries,
      years: [...new Set(entries.map((r) => r.year))],
      entries,
      overrideCount,
      rejected,
      // Nombre réel de rejets (le serveur renvoie `rejected_total`) : sans lui,
      // l'utilisateur croirait que le tableau (borné à 50) est exhaustif.
      rejectedTotal,
      unknownColumns,
      derivedColumns,
      // Texte brut analysé : renvoyé tel quel au staging (le serveur re-parse en
      // source unique des règles ; le front ne fait qu'un aperçu).
      rawText: text,
    };
  },

  // --- Brouillons d'import (#23) -------------------------------------------
  // Un import proposé (IA via MCP, ou collage) est un brouillon `pending` : il
  // n'est appliqué que sur validation explicite ici. Le front ne fait
  // qu'appeler les routes REST dédiées (`api.js`), jamais d'écriture directe.

  async openDrafts() {
    this.draftsOpen = true;
    this.draftError = "";
    await this.refreshDrafts();
  },

  async refreshDrafts() {
    try {
      const drafts = await api.importDrafts();
      // On ne montre que les brouillons du ticker courant : la fiche est
      // monoligne, un lot d'un autre titre se valide sur SA fiche.
      const ticker = this.data?.identity?.ticker;
      this.importDrafts = (drafts || []).filter((d) => !ticker || d.ref === ticker);
      this.draftCount = this.importDrafts.length;
    } catch (e) {
      this.draftError = e.message || "Impossible de lire les imports en attente";
    }
  },

  drainSummary(d) {
    const n = d.accepted ?? "?";
    return `${n} valeur(s) à importer`;
  },
  async openDraftDetail(id) {
    try {
      const d = await api.importDraft(id);
      this.draftDetail = d;
    } catch (e) {
      this.draftError = e.message;
    }
  },

  async applyDraft(id) {
    this.draftsBusy = true;
    this.draftError = "";
    try {
      const { ok, data } = await api.applyImportDraft(id);
      if (!ok) throw new Error(data.detail || "Application refusée");
      this.draftsOpen = false;
      this.load();  // recharge la fiche pour voir les données fusionnées
    } catch (e) {
      this.draftError = e.message;
    } finally {
      this.draftsBusy = false;
    }
  },

  async rejectDraft(id) {
    this.draftsBusy = true;
    this.draftError = "";
    try {
      const { ok, data } = await api.discardImportDraft(id);
      if (!ok) throw new Error(data.detail || "Rejet refusé");
      await this.refreshDrafts();
    } catch (e) {
      this.draftError = e.message;
    } finally {
      this.draftsBusy = false;
    }
  },

  // Parse le fichier CSV sélectionné et affiche un aperçu.
  onFileSelect(e) {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => this._buildPreview(String(ev.target.result).replace(/^\ufeff/, ""));
    reader.readAsText(file);
  },

  // Analyse le texte COLLÉ (l'utilisateur corrige un export au format cassé sans
  // passer par un fichier). Même pipeline que le fichier.
  onPastePreview() {
    this.importError = "";
    if (!this.importPasteText || !this.importPasteText.trim()) {
      this.importError = "Colle d'abord un contenu CSV";
      return;
    }
    this._buildPreview(this.importPasteText.replace(/^\ufeff/, ""));
  },

  cancelImport() {
    this.showImportModal = false;
    this.importPreview = null;
    this.importPasteText = "";
  },

  async confirmImport() {
    if (!this.importPreview) return;
    this.importing = true;
    this.importError = "";
    const ticker = this.data.identity.ticker;
    try {
      // Le collage/fichier passe par le STAGING : on ne crée pas un brouillon
      // (`POST /api/imports/propose`) — l'écriture métier reste conditionnée à la
      // validation de l'utilisateur dans la bande « Imports à valider ».
      // Le texte source est celui du fichier (rawText) ou du collage. Le serveur
      // re-parse en source unique des règles ; le front ne fait qu'un aperçu.
      const text = (this.importPreview.rawText || "").trim();
      if (!text) throw new Error("Contenu CSV indisponible, relance l'analyse");
      const { ok, data } = await api.proposeImport("fundamentals", ticker, text);
      if (!ok) throw new Error(data.detail || "Proposition d'import refusée");
      this.showImportModal = false;
      this.importPreview = null;
      this.importPasteText = "";
      // Ouvre la bande de validation sur le brouillon fraîchement créé.
      await this.refreshDrafts();
      this.draftsOpen = true;
    } catch (e) {
      this.importError = e.message;
    } finally {
      this.importing = false;
    }
  },

  // --- Export CSV (droite de régression / simulation fenêtre glissante) ---
  // Tout est côté client : on réutilise olsLog et la série data.chart déjà
  // disponible (décimée à ~1200 pts). Aucun appel serveur.

};
