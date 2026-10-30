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
import { api } from "./api.js";
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
  _momRef: null, // référence de la fiche dont la plage est valide
  // Backtest de fiabilité (#31) : une requête par fenêtre, jamais par pixel.
  momBacktest: null,
  momBacktestLoading: false,
  momBacktestError: "",
  _momBacktestToken: 0, // jeton : une réponse tardive ne remplace pas la récente
  _momBacktestKeyLoaded: "",
  _momBacktestRefKey: "", // référence dont les chiffres sont affichés

  momData() {
    return this.data?.chart?.momentum || null;
  },

  // La plage est un INDEX sur `chart.dates` : elle ne survit pas à une autre
  // série. Sans ce garde, changer de fiche puis ouvrir l'onglet clampe
  // l'ancienne plage à `[end-1, end]` et l'historique n'affiche que deux points.
  momSyncRef() {
    const ref = typeof this._hashRef === "function" ? this._hashRef() : null;
    if (this._momRef !== ref) {
      this._momRef = ref;
      this.momStart = null;
      this.momEnd = null;
    }
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

  // Indice de départ de la fenêtre de RÉFÉRENCE (celle de la valorisation) :
  // la date persistée si elle existe, sinon 20 ans (30 pour les financières).
  // SOURCE UNIQUE : `momRange()` et le chip « Réf. » de l'historique passent
  // par elle, sinon les deux repères pourraient diverger. Autonome (pas de
  // dépendance à `idxStartBeforeWindow`) pour rester testable.
  _momReferenceStart(end) {
    const dates = this.data?.chart?.dates || [];
    const refStart = this.data?.watch?.ref?.start;
    if (refStart) {
      const i = dates.findIndex((d) => d >= refStart);
      if (i >= 0) return i;
    }
    const years =
      this.data?.identity?.kind === "financial" ? REG_YEARS_FINANCIAL : REG_YEARS_DEFAULT;
    return this._momStartBefore(end, years);
  },

  // Indices [début, fin] de la fenêtre de la table sur `chart.dates`.
  // `null` = la fenêtre de RÉFÉRENCE, `0` = le maximum.
  momRange() {
    const dates = this.data?.chart?.dates || [];
    if (!dates.length) return [0, 0];
    const end = dates.length - 1;
    if (this.momWindow == null) return [this._momReferenceStart(end), end];
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

  // --- Fiabilité de l'indicateur (backtest, #31 puis #32) -------------------
  //
  // Depuis #32, la table ne compare plus la stratégie au buy & hold (deux
  // expositions différentes) : elle montre le MARCHÉ pendant les séances in et
  // out, séparées par la position décidée la veille. Le rendement réel de la
  // stratégie reste en pied, hors des colonnes.

  // Nature de la référence pour le backtest : une action ou un indice.
  // Un ratio n'en a pas (l'onglet est désactivé).
  _momBacktestRef() {
    const d = this.data;
    if (!d) return null;
    if (d.kind_payload === "stock" && d.identity?.ticker) {
      return { kind: "stock", ref: d.identity.ticker };
    }
    if (d.kind_payload === "basket" && d.identity?.index_id != null) {
      return { kind: "basket", ref: d.identity.index_id };
    }
    return null;
  },

  // Clé d'une requête : référence + bornes visibles + série affichée. Un
  // redraw de section ne doit pas relancer le calcul ; changer la fenêtre ou
  // la série le doit.
  _momBacktestKey() {
    const r = this._momBacktestRef();
    const dates = this.data?.chart?.dates || [];
    if (!r || !dates.length) return "";
    const [i0, i1] = this.momVisible();
    return `${r.kind}:${r.ref}:${dates[i0]}:${dates[i1]}:${this.momSeries}`;
  },

  async loadMomentumBacktest() {
    const ref = this._momBacktestRef();
    const key = this._momBacktestKey();
    if (!ref || !key) return;
    // Changer de fiche ne doit pas laisser les chiffres du ticker précédent
    // sous les yeux pendant la requête : on vide l'état AVANT de demander.
    const refKey = `${ref.kind}:${ref.ref}`;
    if (refKey !== this._momBacktestRefKey) {
      this._momBacktestRefKey = refKey;
      this.momBacktest = null;
      this.momBacktestError = "";
      this._momBacktestKeyLoaded = "";
    }
    if (key === this._momBacktestKeyLoaded && (this.momBacktest || this.momBacktestLoading)) {
      return; // même fenêtre, même série : rien de neuf à demander
    }
    const dates = this.data?.chart?.dates || [];
    const [i0, i1] = this.momVisible();
    if (i1 - i0 < 1) {
      this.momBacktest = null;
      this.momBacktestError = "";
      return;
    }
    this._momBacktestKeyLoaded = key;
    const token = ++this._momBacktestToken;
    this.momBacktestLoading = true;
    this.momBacktestError = "";
    try {
      const payload = await api.momentumBacktest(
        ref.kind,
        ref.ref,
        dates[i0],
        dates[i1],
        this.momSeries,
      );
      if (token !== this._momBacktestToken) return; // réponse ancienne : ignorée
      this.momBacktest = payload;
    } catch (e) {
      if (token !== this._momBacktestToken) return;
      this.momBacktest = null;
      // Un échec réseau parle anglais (« Failed to fetch ») : on le traduit en
      // une phrase lisible ; les messages métier du serveur sont déjà français.
      const message = e?.message || "";
      this.momBacktestError = /failed to fetch|networkerror|load failed/i.test(message)
        ? "Calcul impossible : le serveur ne répond pas. Réessayez."
        : message || "Calcul du backtest impossible.";
    } finally {
      if (token === this._momBacktestToken) this.momBacktestLoading = false;
    }
  },

  // Format commun des mesures : deux décimales, « — » si non calculable.
  _momNum(v) {
    const n = Number(v);
    if (v == null || !Number.isFinite(n)) return "—";
    return n.toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  },

  // Polarité d'une mesure SIGNÉE, selon la colonne. Convention globale bleu =
  // bien, rouge = mal ; la colonne `out` l'INVERSE localement : gagner quand on
  // est dehors est un mauvais signe (le signal n'a rien évité), donc un CAGR ou
  // un Sharpe positif y est rouge. Un zéro ne dit rien : il reste neutre.
  // `value` est la valeur AFFICHÉE (déjà arrondie) : voir `_momShown`.
  _momBacktestGood(value, column) {
    const v = Number(value);
    if (value == null || !Number.isFinite(v) || v === 0) return null;
    return column === "out" ? v < 0 : v > 0;
  },

  // Valeur telle qu'elle est LUE (deux décimales, comme `_momNum`) : la couleur
  // suit ce que l'écran montre. Un CAGR de 0,0004 % s'affiche « 0,00 % » ; le
  // colorer bleu ou rouge lui prêterait un signe que le lecteur ne voit pas.
  // Arrondi demi vers l'EXTÉRIEUR, comme `Intl` : −0,005 s'affiche « -0,01 % »
  // et doit donc se colorer, là où `Math.round` arrondirait vers zéro.
  _momShown(value) {
    const n = Number(value);
    if (value == null || !Number.isFinite(n)) return null;
    return (Math.sign(n) * Math.round(Math.abs(n) * 100)) / 100;
  },

  // Classe CSS d'une cellule : elle ne décide d'aucune couleur sémantique, elle
  // traduit en classe le `good` calculé par `momBacktestRows()` (polarité
  // standard, ou inversée pour la colonne `out`).
  momCellClass(cell) {
    if (cell?.good === true) return "good";
    if (cell?.good === false) return "bad";
    return "";
  },

  momBacktestRows() {
    const b = this.momBacktest;
    if (!b?.buy_hold || !b?.in || !b?.out) return [];
    const pct = (v) => (v == null ? "—" : this._momNum(v) + " %");
    const num = (v) => (v == null ? "—" : this._momNum(v));
    // Une ligne par mesure, trois cellules dans l'ordre des colonnes. `signed`
    // dit si la polarité s'applique (les autres mesures restent neutres : une
    // volatilité ou un drawdown n'est ni bien ni mal en soi).
    const specs = [
      { key: "cagr", label: "CAGR", field: "cagr_pct", fmt: pct, signed: true },
      {
        key: "volatility",
        label: "Volatilité",
        field: "volatility_pct",
        fmt: pct,
        signed: false,
      },
      { key: "sharpe", label: "Sharpe", field: "sharpe", fmt: num, signed: true },
      { key: "sortino", label: "Sortino", field: "sortino", fmt: num, signed: true },
      {
        key: "max_drawdown",
        label: "Max drawdown",
        field: "max_drawdown_pct",
        fmt: pct,
        signed: false,
      },
      { key: "calmar", label: "Calmar", field: "calmar", fmt: num, signed: true },
      {
        key: "sessions",
        label: "Part des séances",
        field: "sessions_pct",
        fmt: pct,
        signed: false,
      },
    ];
    const columns = ["buy_hold", "in", "out"];
    const rows = specs.map((spec) => ({
      key: spec.key,
      label: spec.label,
      cells: columns.map((column) => {
        const raw = b[column]?.[spec.field];
        if (!spec.signed) return { value: spec.fmt(raw), good: null };
        // Une seule valeur arrondie : elle est à la fois ce que l'écran affiche
        // et ce que la couleur lit. Formater la valeur brute puis la colorer
        // après un second arrondi faisait vivre deux règles pour un chiffre.
        const shown = this._momShown(raw);
        return {
          value: shown == null ? "—" : spec.fmt(shown),
          good: this._momBacktestGood(shown, column),
        };
      }),
    }));
    // Infobulles des mesures non calculables : le tiret reste, l'explication
    // évite de le lire comme une panne (série plate, aucune baisse, panier vide).
    const hints = {
      sharpe: "Volatilité nulle ou fenêtre trop courte : le Sharpe n'est pas calculable.",
      sortino: "Aucune baisse sur la fenêtre : le Sortino n'est pas calculable.",
      calmar: "Pas de baisse mesurable : le Calmar n'est pas calculable.",
    };
    for (const row of rows) {
      const hint = hints[row.key];
      if (hint && row.cells.some((c) => c.value === "—")) row.hint = hint;
    }
    return rows;
  },

  // Nombre de trades de la stratégie, « — » s'il manque.
  momBacktestTrades() {
    const trades = this.momBacktest?.trades;
    const n = Number(trades);
    if (trades == null || !Number.isFinite(n)) return "—";
    return String(Math.round(n));
  },

  // Pied de table : le nombre de trades et le rendement RÉEL de la stratégie
  // (cash compris). Il reste hors des colonnes : le lecteur garde ce qu'il a
  // obtenu sans en refaire une comparaison avec le buy & hold.
  momBacktestFoot() {
    if (!this.momBacktest) return "";
    const trades = this.momBacktestTrades();
    const label = trades === "—" ? "—" : `${trades} trade${Number(trades) > 1 ? "s" : ""}`;
    const cagr = this.momBacktest.strategy_cagr_pct;
    const rate = cagr == null ? "—" : this._momNum(cagr) + " %";
    return `${label} · stratégie ${rate}/an`;
  },

  // Légende de lecture de la table : ce que mesure chaque colonne, et la nature
  // CONDITIONNELLE du drawdown des paniers (leur pire série de pertes, pas un
  // creux vécu : les séances d'un panier ne sont pas contiguës).
  momBacktestNote() {
    return (
      "Le marché pendant les séances in et out ; la stratégie n'est investie " +
      "qu'une partie du temps. Le drawdown des paniers est conditionnel."
    );
  },

  // Durée de la fenêtre tranchée par le serveur, en années ou en mois.
  momBacktestSpan() {
    const w = this.momBacktest?.window;
    if (!w?.start || !w?.end) return "";
    const days = (new Date(w.end) - new Date(w.start)) / 864e5;
    if (!Number.isFinite(days) || days <= 0) return "";
    if (days >= 365.25) {
      const years = days / 365.25;
      return years.toLocaleString("fr-FR", { maximumFractionDigits: 1 }) + " ans";
    }
    return Math.max(1, Math.round(days / 30.44)) + " mois";
  },

  // La légende dit la série ET son sens. Un indice est chaîné en total-return
  // (services/serialize.py) : sa série « brute » inclut déjà les dividendes.
  // Pour une action, le brut ne les compte pas ; l'ajusté reste à un clic.
  momBacktestLegend() {
    if (!this.momBacktest) return "";
    let series;
    if (this.data?.kind_payload === "basket") {
      series = "indice total-return, dividendes réinvestis";
    } else if (this.momSeries === "adj") {
      series = "ajustée, dividendes réinvestis";
    } else {
      series = "brute, dividendes non comptés";
    }
    const span = this.momBacktestSpan();
    const fee = MOMENTUM.fee_pct;
    const fees = fee == null ? "" : ` · frais ${this._momNum(fee)} % par ordre`;
    return `Sur la série affichée (${series})${span ? " — " + span : ""}${fees}`;
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

  // Série effectivement affichée. La bascule « ajusté » ne vaut que si le
  // payload porte la série : un indice n'en a pas, et `momSeries` peut rester
  // sur « adj » après une fiche action (le radio est alors désactivé).
  momUsesAdj() {
    return this.momSeries === "adj" && this.momHasAdj();
  },

  // Rang du score dans l'histoire du titre (0–100). Le payload le porte déjà
  // calculé sur l'historique COMPLET : le front ne refait pas le percentile sur
  // la plage affichée, et un payload sans le champ (cache ancien) ne casse rien.
  momPercentile() {
    const m = this.momData();
    if (!m) return null;
    const value = this.momUsesAdj() ? m.percentile_adj : m.percentile_raw;
    const n = Number(value);
    return value == null || !Number.isFinite(n) ? null : n;
  },

  // Libellé de la ligne sous la jauge : ordinal français (« 1er », « 51e ») et
  // année de départ de l'historique. La date suit la SÉRIE AFFICHÉE : l'ajusté
  // peut commencer ailleurs, ou manquer, sans que le rang brut soit faux pour
  // autant. Vide quand le rang manque — la ligne disparaît, elle ne montre pas
  // un « — » qui laisserait croire à une panne.
  momPercentileLabel() {
    const rank = this.momPercentile();
    if (rank == null) return "";
    const ordinal = rank === 1 ? "1er" : `${rank}e`;
    const start = this.momUsesAdj()
      ? this.momData()?.history_start_adj
      : this.momData()?.history_start;
    const year = String(start || "").slice(0, 4);
    const since = /^\d{4}$/.test(year) ? `, depuis ${year}` : "";
    return `${ordinal} percentile de l'historique du titre${since}`;
  },

  // --- Ce qui a suivi chaque zone de score -----------------------------------
  //
  // Le payload porte déjà les rendements conditionnels (médiane, 10e/90e,
  // épisodes) et la prudence (`thin`) : le front ne calcule rien, il choisit la
  // série affichée et formate. Une zone sans fenêtre complète vaut `null` et
  // s'affiche en tirets — elle garde sa ligne, sinon le lecteur croirait la
  // zone disparue.

  momConditional() {
    const m = this.momData();
    if (!m) return null;
    return (this.momUsesAdj() ? m.conditional_adj : m.conditional_raw) || null;
  },

  // Pourcentage à une décimale : un rendement conditionnel se lit au dixième,
  // pas au centième (les mesures du backtest, elles, gardent deux décimales).
  _momPctOne(value) {
    const n = Number(value);
    if (value == null || !Number.isFinite(n)) return "—";
    return (
      n.toLocaleString("fr-FR", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + " %"
    );
  },

  _momPctRange(block) {
    const p10 = this._momPctOne(block?.p10_pct);
    const p90 = this._momPctOne(block?.p90_pct);
    return p10 === "—" || p90 === "—" ? "—" : `${p10} / ${p90}`;
  },

  // Quatre lignes : les trois zones, puis le repère de tout l'historique. La
  // zone du score courant est marquée (fond et gras), et une zone `thin` porte
  // sa mention de prudence.
  momConditionalRows() {
    const conditional = this.momConditional();
    const zones = conditional?.zones;
    if (!zones) return [];
    const hasWindow = (block) =>
      block?.median_pct != null && Number.isFinite(Number(block.median_pct));
    // Aucune zone n'a de fenêtre complète : la carte n'a rien à dire.
    if (!hasWindow(zones.bas) && !hasWindow(zones.neutre) && !hasWindow(zones.haut)) return [];

    const current = this.momState(this.momScore());
    const low = MOMENTUM.low;
    const high = MOMENTUM.high;
    const spec = [
      {
        key: "bas",
        label: low == null ? "Score bas" : `Score bas (< ${this.fmt(low)})`,
        block: zones.bas,
      },
      { key: "neutre", label: "Score neutre", block: zones.neutre },
      {
        key: "haut",
        label: high == null ? "Score haut" : `Score haut (> ${this.fmt(high)})`,
        block: zones.haut,
      },
      { key: "baseline", label: "Tout l'historique", block: conditional.baseline },
    ];
    return spec.map(({ key, label, block }) => {
      const episodes = Number(block?.episodes);
      const row = {
        key,
        label,
        current: key === current,
        median: this._momPctOne(block?.median_pct),
        range: this._momPctRange(block),
        episodes:
          block?.episodes != null && Number.isFinite(episodes)
            ? String(Math.round(episodes))
            : "—",
        thin: block?.thin === true,
      };
      if (row.thin) {
        row.hint = "Trop peu d'épisodes indépendants : cette zone ne dit presque rien.";
      }
      return row;
    });
  },

  // Note de lecture : l'horizon vient du payload (jamais un « 12 mois » en
  // dur), et le chevauchement des fenêtres est dit en toutes lettres — c'est
  // lui qui interdit de lire les centiles comme un échantillon indépendant.
  momConditionalNote() {
    const conditional = this.momConditional();
    const horizon = Number(conditional?.horizon);
    const span =
      conditional?.horizon != null && Number.isFinite(horizon) && horizon > 0
        ? `${Math.round(horizon)} séances`
        : "";
    const lead = span
      ? `Le rendement des ${span} qui ont suivi chaque date.`
      : "Le rendement qui a suivi chaque date.";
    const note =
      `${lead} Les fenêtres se chevauchent : les centiles mesurent une dispersion, ` +
      "pas des observations indépendantes. Les épisodes ne retiennent qu'une fenêtre par horizon.";
    const thin = this.momConditionalRows().some((row) => row.thin);
    return thin ? `${note} Une zone à trop peu d'épisodes ne dit presque rien.` : note;
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

  // Presets de l'historique : `"ref"` (fenêtre de référence), `"max"` ou un
  // nombre d'années. Le défaut de l'historique reste 10 ans (`drawMomentum`) :
  // « Réf. » est un repère, pas la fenêtre d'ouverture.
  momPreset(preset) {
    const n = (this.data?.chart?.dates || []).length;
    if (!n) return;
    const end = n - 1;
    this.momEnd = end;
    if (preset === "ref") this.momStart = this._momReferenceStart(end);
    else if (preset === "max") this.momStart = 0;
    else this.momStart = this._momStartBefore(end, Number(preset));
    this.drawMomentumHistory();
    this.loadMomentumBacktest();
  },

  // Relâchement d'une poignée (ou clic sur un chip) : un seul calcul par geste.
  momRangeChanged() {
    this.drawMomentumHistory();
    this.loadMomentumBacktest();
  },

  // --- Tracés ---------------------------------------------------------------

  drawMomentum() {
    if (!this.momAvailable()) return;
    this.momSyncRef();
    if (this.momStart == null || this.momEnd == null) {
      const n = (this.data?.chart?.dates || []).length;
      this.momEnd = n - 1;
      this.momStart = this._momStartBefore(this.momEnd, 10);
    }
    this.drawMomentumYear();
    this.drawMomentumHistory();
    this.loadMomentumBacktest();
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
