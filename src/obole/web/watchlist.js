// Obole — watchlist (#25) : tiers, classement par marge et fenêtre de confiance.
//
// Le front ne calcule NI marge NI z : le serveur renvoie des lignes déjà
// classées (`POST /api/watchlist/run`). Ce module porte l'état de la modale,
// les gestes d'appartenance (étoile de la fiche + tableau) et le contrôle de la
// fenêtre de confiance de la barre de période. Les seuils (tiers, point minimal
// d'une référence, plafond) viennent de `/api/meta` via `thresholds.js`.
import { api } from "./api.js";
import { WATCH_MIN_REF_POINTS, WATCH_TIERS } from "./thresholds.js";

// --- Helpers purs (testés sans Alpine) --------------------------------------

export function tierLabel(tier, tiers = WATCH_TIERS) {
  const found = (tiers || []).find((t) => Number(t.id) === Number(tier));
  return found ? found.label : "—";
}

export function fairPriceSourceLabel(row) {
  if (!row || row.fair_price == null) return "—";
  return row.fair_price_source === "saved" ? "calc" : "droite";
}

export function potSourceLabel(row) {
  if (row?.pot_5y_source === "valuation") return "valo";
  if (row?.pot_5y_source === "regression") return "droite";
  return "—";
}

export function watchCoverage(rows) {
  const list = rows || [];
  return {
    defined: list.filter((r) => r.fair_price_source === "saved").length,
    total: list.length,
  };
}

// Tri client (≤ plafond de la watchlist). Les valeurs absentes passent TOUJOURS
// en dernier, quel que soit le sens ; à égalité, tier puis ticker départagent.
export function sortWatchRows(rows, key, dir = "desc") {
  const sign = dir === "asc" ? 1 : -1;
  return [...(rows || [])].sort((a, b) => {
    const va = a ? a[key] : null;
    const vb = b ? b[key] : null;
    if (va == null && vb == null) {
      return (a.tier - b.tier) || String(a.ticker).localeCompare(String(b.ticker));
    }
    if (va == null) return 1;
    if (vb == null) return -1;
    const diff =
      typeof va === "string" || typeof vb === "string"
        ? sign * String(va).localeCompare(String(vb))
        : sign * (Number(va) - Number(vb));
    // Égalité : tier puis ticker, pour un ordre stable et lisible.
    return diff !== 0 ? diff : (a.tier - b.tier) || String(a.ticker).localeCompare(String(b.ticker));
  });
}

export const watchlistMixin = {
  // --- État -----------------------------------------------------------------
  watchlistOpen: false,
  watchItems: [], // appartenance (ticker, tier) — source des compteurs
  watchRows: [], // classement (lignes WatchlistRow du serveur)
  watchLoading: false,
  watchSearched: false,
  watchError: "",
  watchGeneratedAt: null,
  watchTierFilter: null,
  watchHideFallback: false,
  watchSort: null, // {key, dir} ; null = ordre serveur (marge décroissante)
  // Étoile de la fiche
  watchPopoverOpen: false,
  // Fenêtre de confiance (barre de période)
  watchRefOpen: false,
  watchRefBusy: false,
  watchRefError: "",

  // --- Lecture des métadonnées (live bindings de thresholds.js) -------------
  // `metaReady` est lu VOLONTAIREMENT : c'est une propriété Alpine réactive.
  // Les `x-for` qui appellent ces méthodes dépendent donc du chargement de
  // `/api/meta` et se réévaluent quand il aboutit (sans lui, ouvrir la modale
  // avant la fin de l'init laissait la barre de tiers vide).
  watchTierList() {
    return this.metaReady ? WATCH_TIERS : [];
  },

  watchMinRefPoints() {
    return this.metaReady ? WATCH_MIN_REF_POINTS : 0;
  },

  // Tier de la fiche courante (null si non suivie / ratio / indice).
  watchTier() {
    return this.data?.watch?.tier ?? null;
  },

  watchTierLabel(tier) {
    return tierLabel(tier, WATCH_TIERS);
  },

  watchRefStart() {
    return this.data?.watch?.ref?.start || null;
  },

  watchRefStats() {
    return this.data?.watch?.ref_stats || null;
  },

  watchRefLabel() {
    const start = this.watchRefStart();
    return start ? `Réf. ${start.slice(0, 4)}` : "Réf. droite";
  },

  watchPct(value) {
    return value == null ? "—" : this.fmt(value) + " %";
  },

  watchSourceLabel(row) {
    return fairPriceSourceLabel(row);
  },

  watchPotSourceLabel(row) {
    return potSourceLabel(row);
  },

  watchRowTitle(row) {
    if (!row) return "";
    const parts = [];
    if (row.error) parts.push(row.error);
    if (row.ref_is_default) parts.push("Fenêtre 20 ans (défaut) — total return");
    else if (row.ref_start) parts.push(`Fenêtre depuis ${row.ref_start} — total return`);
    if (row.fair_price_source === "saved") parts.push("Prix juste enregistré (calculatrice)");
    else if (row.fair_price_source === "regression") {
      parts.push("Prix juste = droite projetée 5 ans, actualisée à 12 %/an (total return)");
    }
    if (row.pot_5y_source === "valuation") {
      parts.push("Pot. 5A : estimation de la valorisation enregistrée");
    } else if (row.pot_5y_source === "regression") {
      parts.push("Pot. 5A : droite total-return");
    }
    if (row.warnings?.length) parts.push(row.warnings.join(" · "));
    return parts.join(" — ");
  },

  // --- Étoile de la fiche ---------------------------------------------------
  async setWatchTier(tier) {
    const ticker = this.data?.identity?.ticker;
    if (!ticker) return;
    const { ok, data } = await api.setWatchTier(ticker, Number(tier));
    if (!ok) {
      this.watchError = data.detail || "Ajout impossible";
      return;
    }
    this.data.watch = { ...(this.data.watch || {}), tier: data.item.tier };
    this.watchPopoverOpen = false;
    this.watchError = "";
  },

  async removeFromWatch() {
    const ticker = this.data?.identity?.ticker;
    if (!ticker) return;
    if (!window.confirm(`Retirer ${ticker} de la watchlist ? La référence de droite est conservée.`)) {
      return;
    }
    const { ok, data } = await api.removeWatchItem(ticker);
    if (!ok) {
      this.watchError = data.detail || "Retrait impossible";
      return;
    }
    this.data.watch = { ...(this.data.watch || {}), tier: null };
    this.watchPopoverOpen = false;
    this.watchError = "";
  },

  openWatchlistFromFiche() {
    this.watchPopoverOpen = false;
    this.openWatchlist();
  },

  // --- Modale ---------------------------------------------------------------
  async openWatchlist() {
    this.watchlistOpen = true;
    // La barre de tiers et les libellés viennent de /api/meta : on attend sa
    // promesse (déjà lancée par init()) plutôt que d'afficher une barre vide.
    if (!this.metaReady && this._metaPromise) {
      try { await this._metaPromise; } catch { /* seuils indisponibles */ }
    }
    this.watchError = "";
    this.watchRows = [];
    this.watchSort = null;
    this.watchTierFilter = null;
    this.watchHideFallback = false;
    this.watchSearched = false;
    await this.loadWatchState();
    await this.runWatchRanking();
  },

  closeWatchlist() {
    this.watchlistOpen = false;
  },

  async loadWatchState() {
    try {
      const data = await api.watchlist();
      if (data) this.watchItems = data.items || [];
    } catch {
      this.watchError = "Watchlist indisponible (réseau).";
    }
  },

  async runWatchRanking() {
    if (this.watchLoading) return;
    this.watchLoading = true;
    this.watchError = "";
    try {
      const { ok, data } = await api.runWatchlist({});
      if (!ok) {
        this.watchError = data.detail || "Classement impossible";
        return;
      }
      this.watchRows = data.rows || [];
      this.watchGeneratedAt = data.generated_at || null;
      this.watchSearched = true;
    } catch {
      this.watchError = "Classement impossible (réseau).";
    } finally {
      this.watchLoading = false;
    }
  },

  async refreshWatchlist() {
    await this.loadWatchState();
    await this.runWatchRanking();
  },

  setWatchTierFilter(tier) {
    this.watchTierFilter = tier == null ? null : Number(tier);
  },

  // Compteurs par tier : l'appartenance (`watchItems`) fait foi, même avant
  // la fin du classement.
  watchCounts() {
    const source = this.watchItems?.length ? this.watchItems : this.watchRows || [];
    const counts = { all: 0 };
    for (const t of WATCH_TIERS) counts[t.id] = 0;
    for (const item of source) {
      const tier = Number(item.tier);
      counts.all += 1;
      if (counts[tier] != null) counts[tier] += 1;
    }
    return counts;
  },

  watchVisibleRows() {
    const tier = this.watchTierFilter;
    return (this.watchRows || []).filter((r) => {
      if (tier != null && r.tier !== tier) return false;
      if (this.watchHideFallback && r.fair_price_source !== "saved") return false;
      return true;
    });
  },

  watchRowsSorted() {
    const rows = this.watchVisibleRows();
    if (!this.watchSort?.key) return rows;
    return sortWatchRows(rows, this.watchSort.key, this.watchSort.dir);
  },

  toggleWatchSort(key) {
    const current = this.watchSort;
    if (!current || current.key !== key) {
      this.watchSort = { key, dir: "desc" };
    } else if (current.dir === "desc") {
      this.watchSort = { key, dir: "asc" };
    } else {
      this.watchSort = null; // 3e clic : retour à l'ordre serveur (marge)
    }
  },

  watchSortClass(key) {
    if (!this.watchSort || this.watchSort.key !== key) return "";
    return this.watchSort.dir === "asc" ? "sort-asc" : "sort-desc";
  },

  watchCoverage() {
    return watchCoverage(this.watchRows);
  },

  watchGeneratedLabel() {
    if (!this.watchGeneratedAt) return "";
    return (
      "Calculé à " +
      new Date(this.watchGeneratedAt * 1000).toLocaleTimeString("fr-FR", {
        hour: "2-digit",
        minute: "2-digit",
      })
    );
  },

  async moveWatchRow(row, tier) {
    const previous = row.tier;
    const { ok, data } = await api.setWatchTier(row.ticker, Number(tier));
    if (!ok) {
      this.watchError = data.detail || "Changement de tier impossible";
      row.tier = previous; // le <select> revient à la valeur réelle
      return;
    }
    row.tier = data.item.tier;
    const item = (this.watchItems || []).find((i) => i.ticker === row.ticker);
    if (item) item.tier = row.tier;
    this.watchError = "";
  },

  async removeWatchRow(row) {
    if (!window.confirm(`Retirer ${row.ticker} de la watchlist ? La référence de droite est conservée.`)) {
      return;
    }
    const { ok, data } = await api.removeWatchItem(row.ticker);
    if (!ok) {
      this.watchError = data.detail || "Retrait impossible";
      return;
    }
    this.watchRows = (this.watchRows || []).filter((r) => r.ticker !== row.ticker);
    this.watchItems = (this.watchItems || []).filter((i) => i.ticker !== row.ticker);
    this.watchError = "";
  },

  openWatchRow(row) {
    if (!row || row.error) return; // une ligne en erreur n'a pas de fiche à ouvrir
    this.backTo = { source: "watchlist", name: "Watchlist" };
    this.watchlistOpen = false;
    this.loadTicker(row.ticker);
  },

  // --- Fenêtre de confiance (barre de période) -----------------------------
  // La référence s'étend TOUJOURS jusqu'au dernier cours : on ne l'autorise que
  // si la poignée droite y est déjà, pour éviter de définir « depuis 2005 » en
  // croyant figer une fenêtre 2005-2008.
  canDefineWatchRef() {
    if (!this.data || this.isRatio?.() || this.isBasket?.()) return false;
    if (!this.watchMinRefPoints()) return false; // méta pas encore chargée
    const [start, end] = this.visibleRange();
    if (end !== this.maxIdx()) return false;
    return end - start + 1 >= this.watchMinRefPoints();
  },

  watchRefStartDate() {
    if (!this.data?.chart?.dates) return "";
    const [start] = this.visibleRange();
    return this.data.chart.dates[start] || "";
  },

  async defineWatchRef() {
    const ticker = this.data?.identity?.ticker;
    const start = this.watchRefStartDate();
    if (!ticker || !start) return;
    this.watchRefBusy = true;
    this.watchRefError = "";
    try {
      const { ok, data } = await api.setWatchRef(ticker, start);
      if (!ok) {
        this.watchRefError = data.detail || "Référence refusée";
        return;
      }
      this.watchRefOpen = false;
      // Recharge la fiche : le « Prix juste » du Résumé et le chip suivent la
      // nouvelle fenêtre (mêmes caches, section conservée).
      await this.load();
    } catch {
      this.watchRefError = "Référence impossible (réseau).";
    } finally {
      this.watchRefBusy = false;
    }
  },

  applyWatchRef() {
    const start = this.watchRefStart();
    if (!start || !this.data) return;
    const idx = this.idxForDate(start);
    if (idx == null) return;
    this.rangeStart = idx;
    this.rangeEnd = this.maxIdx();
    this.syncRegression = true;
    this.winLocked = false;
    this.withDividends = false; // la référence est calculée sur les prix bruts
    this.watchRefOpen = false;
    this.$nextTick(() => this.drawChart());
  },

  async clearWatchRef() {
    const ticker = this.data?.identity?.ticker;
    if (!ticker) return;
    if (!window.confirm("Effacer la référence de droite ? Le Résumé revient à la fenêtre 20 ans.")) {
      return;
    }
    this.watchRefBusy = true;
    this.watchRefError = "";
    try {
      const { ok, data } = await api.clearWatchRef(ticker);
      if (!ok) {
        this.watchRefError = data.detail || "Effacement impossible";
        return;
      }
      this.watchRefOpen = false;
      // La référence était la raison de la vue prix bruts : on revient à la
      // vue par défaut (dividendes réinvestis) avant de recharger.
      this.withDividends = true;
      await this.load();
    } catch {
      this.watchRefError = "Effacement impossible (réseau).";
    } finally {
      this.watchRefBusy = false;
    }
  },
};
