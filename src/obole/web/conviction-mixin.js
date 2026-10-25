// Obole — état du jeu de convictions (#26).
//
// Le calcul (Elo, paires, score, tiers suggérés) vit dans `conviction.js`, pur.
// Ce mixin ne porte que l'état Alpine, les gestes et l'application des tiers
// via la route existante (`PUT /api/watchlist/items/<ticker>`) : pas de schéma,
// pas d'outil MCP, pas de nouvelle route d'écriture.
import { api } from "./api.js";
import {
  MIN_COMPARISONS,
  changes,
  convictionScore,
  initialComparisons,
  initialRatings,
  nextPair,
  suggestTiers,
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

  openConviction() {
    const rows = validRows(this.watchRows || []);
    if (rows.length < 2) {
      this.convictionError = "Il faut au moins deux valeurs dans la watchlist.";
      return;
    }
    this.convictionRows = rows;
    this.convictionRatings = initialRatings(rows);
    this.convictionComparisons = initialComparisons(rows);
    this.convictionCount = 0;
    this.convictionHistory = [];
    this.convictionResult = null;
    this.convictionApplied = false;
    this.convictionError = "";
    this.convictionLastChoice = "";
    this.convictionLastPair = null;
    this.convictionPair = nextPair(rows, this.convictionRatings, this.convictionComparisons, null);
    this.watchlistOpen = false;
    this.convictionOpen = true;
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
    const suggested = suggestTiers(this.convictionRows, this.convictionRatings);
    const rows = this.convictionRows
      .map((row) => ({
        ticker: row.ticker,
        name: row.name,
        current_tier: Number(row.tier),
        suggested_tier: suggested[row.ticker],
        score: convictionScore(this.convictionRatings[row.ticker], this.convictionRatings),
        comparisons: this.convictionComparisons[row.ticker] || 0,
      }))
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
    this.openWatchlist();
  },
};
