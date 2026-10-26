// Obole — état du jeu de convictions (#26, seuils absolus #27).
//
// Le calcul (Elo, paires, indice absolu, tiers par seuils) vit dans
// `conviction.js`, pur. Ce mixin ne porte que l'état Alpine, les gestes et
// l'application des tiers via la route existante
// (`PUT /api/watchlist/items/<ticker>`) : pas de schéma, pas d'outil MCP, pas de
// nouvelle route d'écriture.
import { api } from "./api.js";
import {
  LIMIT_DISTANCE,
  MIN_COMPARISONS,
  MIN_COMPARISONS_PER_ROW,
  changes,
  convictionIndex,
  initialComparisons,
  initialRatings,
  nextPair,
  suggestTiersByThresholds,
  thresholdDistance,
  updateRatings,
  validRows,
} from "./conviction.js";

export const convictionMixin = {
  convictionOpen: false,
  convictionRows: [],
  convictionRatings: {},
  convictionComparisons: {},
  convictionCount: 0,
  convictionPair: null,
  convictionLastPair: null,
  convictionHistory: [],
  convictionResult: null,
  convictionApplied: false,
  convictionBusy: false,
  convictionError: "",
  convictionLastChoice: "",
  // Seuils lus à l'ouverture du jeu (#27) ; null = pas encore chargés. Aucun
  // défaut dupliqué ici : la source unique est `config.SETTING_DEFS`.
  convictionThresholds: null,

  convictionMin() {
    return MIN_COMPARISONS;
  },

  convictionProgress() {
    return Math.min(100, Math.round((this.convictionCount / MIN_COMPARISONS) * 100));
  },

  convictionCanFinish() {
    return this.convictionCount >= MIN_COMPARISONS;
  },

  convictionRow(ticker) {
    return (this.convictionRows || []).find((row) => row.ticker === ticker) || null;
  },

  convictionChanges() {
    return this.convictionResult?.changes || [];
  },

  // Valide le payload de `/api/settings` (entiers 0-100, Tier 1 > Tier 2).
  // Renvoie null si les seuils sont inutilisables : on n'ouvre pas de paire.
  convictionThresholdsFrom(payload) {
    const values = payload?.values || {};
    const tier1 = Number(values.conviction_tier1_min);
    const tier2 = Number(values.conviction_tier2_min);
    const inRange = (value) => Number.isInteger(value) && value >= 0 && value <= 100;
    if (!inRange(tier1) || !inRange(tier2) || tier1 <= tier2) return null;
    return { tier1, tier2 };
  },

  // Ligne d'en-tête du résultat : seuils ET échelle, pour que l'indice affiché
  // soit lisible sans ouvrir Paramètres.
  convictionThresholdLine() {
    const thresholds = this.convictionResult?.thresholds;
    if (!thresholds) return "";
    return `Seuils : Tier 1 ≥ ${thresholds.tier1} · Tier 2 ≥ ${thresholds.tier2} · indice 0-100 (50 = neutre)`;
  },

  // Compteurs par tier du RÉSULTAT (tiers suggérés) : un tier vide reste
  // affiché avec zéro, jamais comblé d'office.
  convictionTierSummary() {
    const summary = { 1: 0, 2: 0, 3: 0 };
    for (const row of this.convictionResult?.rows || []) {
      const tier = Number(row.suggested_tier);
      if (summary[tier] != null) summary[tier] += 1;
    }
    return summary;
  },

  convictionNoChange() {
    return Boolean(this.convictionResult) && this.convictionChanges().length === 0;
  },

  async openConviction() {
    const rows = validRows(this.watchRows || []);
    if (rows.length < 2) {
      this.convictionError = "Il faut au moins deux valeurs dans la watchlist.";
      return;
    }
    // Modale ouverte et watchlist refermée AVANT l'appel réseau : l'utilisateur
    // voit l'attente, pas une modale vide par-dessus la watchlist.
    this.watchlistOpen = false;
    this.convictionOpen = true;
    this.convictionError = "";
    this.convictionPair = null;
    this.convictionResult = null;
    this.convictionApplied = false;
    this.convictionLastChoice = "";
    // Réinitialise TOUTE la partie avant l'appel réseau : si les seuils sont
    // indisponibles, aucun compte, historique ou rating de la partie précédente
    // ne doit survivre (sinon « 12 / 12 » et « Voir le résultat » restent actifs
    // alors qu'aucune paire n'existe).
    this.convictionRows = [];
    this.convictionRatings = {};
    this.convictionComparisons = {};
    this.convictionCount = 0;
    this.convictionHistory = [];
    this.convictionLastPair = null;
    this.convictionThresholds = null;
    let thresholds = null;
    try {
      thresholds = this.convictionThresholdsFrom(await api.settings());
    } catch {
      thresholds = null;
    }
    if (!thresholds) {
      // Pas de seuils = pas de règle : on n'invente ni défaut ni paire.
      this.convictionRows = [];
      this.convictionThresholds = null;
      this.convictionError =
        "Seuils de conviction indisponibles : vérifie-les dans Paramètres (Tier 1 > Tier 2).";
      return;
    }
    this.convictionThresholds = thresholds;
    this.convictionRows = rows;
    this.convictionRatings = initialRatings(rows);
    this.convictionComparisons = initialComparisons(rows);
    this.convictionCount = 0;
    this.convictionHistory = [];
    this.convictionLastPair = null;
    this.convictionPair = nextPair(rows, this.convictionRatings, this.convictionComparisons, null);
  },

  chooseConviction(ticker) {
    if (this.convictionBusy || this.convictionResult || !this.convictionPair) return;
    const [a, b] = this.convictionPair;
    if (ticker !== a && ticker !== b) return;
    const loser = ticker === a ? b : a;
    this.convictionHistory.push({
      ratings: { ...this.convictionRatings },
      comparisons: { ...this.convictionComparisons },
      count: this.convictionCount,
      pair: [...this.convictionPair],
      lastPair: this.convictionLastPair,
    });
    this.convictionRatings = updateRatings(this.convictionRatings, ticker, loser);
    this.convictionComparisons = {
      ...this.convictionComparisons,
      [ticker]: (this.convictionComparisons[ticker] || 0) + 1,
      [loser]: (this.convictionComparisons[loser] || 0) + 1,
    };
    this.convictionCount += 1;
    this.convictionLastChoice = ticker;
    this.convictionLastPair = [a, b];
    this.convictionPair = nextPair(
      this.convictionRows,
      this.convictionRatings,
      this.convictionComparisons,
      this.convictionLastPair,
    );
    setTimeout(() => {
      this.convictionLastChoice = "";
    }, 220);
  },

  undoConviction() {
    const previous = this.convictionHistory.pop();
    if (!previous) return;
    this.convictionRatings = previous.ratings;
    this.convictionComparisons = previous.comparisons;
    this.convictionCount = previous.count;
    this.convictionPair = previous.pair;
    this.convictionLastPair = previous.lastPair;
    this.convictionResult = null;
    this.convictionApplied = false;
    this.convictionLastChoice = "";
  },

  finishConviction() {
    if (!this.convictionCanFinish()) return;
    const thresholds = this.convictionThresholds;
    if (!thresholds) return;
    // Règle unique : indice absolu classé par les deux seuils, couverture
    // minimale pour les valeurs à moins de deux duels. Aucun effectif lu.
    const suggested = suggestTiersByThresholds(
      this.convictionRows,
      this.convictionRatings,
      this.convictionComparisons,
      thresholds,
    );
    const rows = this.convictionRows
      .map((row) => {
        const score = convictionIndex(this.convictionRatings[row.ticker]);
        const comparisons = this.convictionComparisons[row.ticker] || 0;
        const tested = comparisons >= MIN_COMPARISONS_PER_ROW;
        const nearest = thresholdDistance(score, thresholds);
        return {
          ticker: row.ticker,
          name: row.name,
          current_tier: Number(row.tier),
          suggested_tier: suggested[row.ticker],
          score,
          comparisons,
          tested,
          // « limite » = indice à 2 points ou moins d'un seuil, sur une valeur
          // réellement testée (bruit de mesure, la règle ne change pas).
          limit: tested && nearest.distance <= LIMIT_DISTANCE,
          distance: nearest.distance,
          threshold: nearest.threshold,
        };
      })
      .sort(
        (a, b) =>
          b.score - a.score ||
          a.current_tier - b.current_tier ||
          String(a.ticker).localeCompare(String(b.ticker)),
      );
    this.convictionResult = {
      rows,
      changes: changes(this.convictionRows, suggested),
      comparisons: this.convictionCount,
      thresholds: { ...thresholds },
    };
    this.convictionPair = null;
  },

  async applyConvictionTiers() {
    const list = this.convictionChanges();
    if (!list.length || this.convictionBusy) return;
    this.convictionBusy = true;
    this.convictionError = "";
    try {
      for (const change of list) {
        const { ok, data } = await api.setWatchTier(change.ticker, change.to);
        if (!ok) {
          this.convictionError = data.detail || `Application impossible pour ${change.ticker}`;
          return;
        }
        const row = (this.watchRows || []).find((item) => item.ticker === change.ticker);
        if (row) row.tier = Number(change.to);
        const item = (this.watchItems || []).find((entry) => entry.ticker === change.ticker);
        if (item) item.tier = Number(change.to);
      }
      this.convictionApplied = true;
    } catch {
      this.convictionError = "Application impossible (réseau).";
    } finally {
      this.convictionBusy = false;
    }
  },

  replayConviction() {
    this.openConviction();
  },

  closeConviction() {
    this.convictionOpen = false;
    this.convictionResult = null;
    this.convictionPair = null;
    this.convictionRows = [];
    this.convictionHistory = [];
    this.convictionError = "";
    this.convictionThresholds = null;
    this.openWatchlist();
  },
};
