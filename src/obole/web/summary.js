// Obole — synthèse fondamentale de la section « Résumé » (grille de lecture rapide).
//
// Vue d'ensemble NON interactive : 8 cartes de valeurs (PROFIL, MARCHÉ,
// VALORISATION, DIVIDENDE, CROISSANCE [CA+EPS], MARGES, RENTABILITÉ, SANTÉ).
// Aucun graphe, aucun clic. Les valeurs viennent du payload `/api/stock` (bloc
// `summary`) ; les seuils de couleur et les zones de scores viennent de
// `/api/summary-meta` (source unique `config.py`) — aucun seuil littéral ici.
import { api } from "./api.js";
import { applySummaryMeta, summaryGood, zoneLabel, marketCapLabel } from "./thresholds.js";

// Abrège un grand nombre à la française (Md / M / k), pour les montants et volumes.
function _abbrev(v) {
  const abs = Math.abs(v);
  if (abs >= 1e9) return (v / 1e9).toFixed(2).replace(".", ",") + " Md";
  if (abs >= 1e6) return (v / 1e6).toFixed(2).replace(".", ",") + " M";
  if (abs >= 1e3) return (v / 1e3).toFixed(1).replace(".", ",") + " k";
  return Number(v).toLocaleString("fr-FR", { maximumFractionDigits: 2 });
}

export const summaryMixin = {
  // Seuils de la synthèse (catégories de capi, zones Altman/Piotroski, polarité).
  summaryMetaReady: false,
  _summaryMeta: null,

  // Charge les seuils de la synthèse depuis `/api/summary-meta` (source unique).
  async loadSummaryMeta() {
    try {
      const m = await api.summaryMeta();
      if (m) {
        applySummaryMeta(m);
        this._summaryMeta = m;
        this.summaryMetaReady = true;
      }
    } catch {
      /* seuils indisponibles : la grille reste affichée, sans couleur */
    }
  },

  // Cartes de la synthèse pour la fiche courante (vide pour un ratio/indice).
  summaryCards() {
    return this.data?.summary || [];
  },

  // Devise de la fiche, pour les montants (vide pour un ratio/indice).
  summaryCurrency() {
    return this.data?.identity?.currency || "";
  },

  // Formate une valeur selon son unité. `--` si absente (jamais 0).
  summaryValue(row) {
    if (row.key === "week52" && row.text) return this._summaryRange(row.text);
    if (row.text != null && row.text !== "") return row.text;
    if (row.value == null) return "--";
    const v = row.value;
    if (row.unit === "pct") return this.fmt(v) + " %";
    if (row.unit === "score") return this.fmt(v) + "/20";
    if (row.unit === "money") {
      const ccy = this.summaryCurrency();
      return _abbrev(v) + (ccy ? " " + ccy : "");
    }
    if (row.key === "volume" || row.key === "avg_volume") return _abbrev(v);
    return this.fmt(v);
  },

  // Range 52 semaines : « 15,23 – 30,85 » (nombres localisés).
  _summaryRange(text) {
    const parts = text.split("–").map((p) => p.trim());
    if (parts.length !== 2) return text;
    return this.fmt(Number(parts[0])) + " – " + this.fmt(Number(parts[1]));
  },

  // Couleur d'une ligne (bleu = bon) depuis `config.SUMMARY_COLORS`.
  summaryGood(row) {
    return summaryGood(row.key, row.value);
  },

  // Classe de couleur : bleu (bon) / rouge (mauvais) / neutre.
  summaryClass(row) {
    return this.polarity(this.summaryGood(row));
  },

  // Carte MATRICE (ex. Croissance) : colonnes fixes, une ligne par série.
  summaryColumns(card) {
    return card.columns || [];
  },

  // Valeur d'une cellule de matrice, formatée selon l'unité de la ligne.
  summaryCell(row, value) {
    if (value == null) return "--";
    if (row.unit === "pct") return this.fmt(value) + " %";
    return this.fmt(value);
  },

  // Classe de couleur d'une cellule de matrice (polarité précalculée serveur).
  summaryCellClass(row, index) {
    const good = row.cell_good ? row.cell_good[index] : null;
    return this.polarity(good);
  },

  // Zone d'un score (Altman Z, Piotroski) : libellé court sous la valeur.
  summaryZone(row) {
    if (row.key === "altman_z") return zoneLabel(row.value, this._summaryMeta?.altman_zones);
    if (row.key === "piotroski") return zoneLabel(row.value, this._summaryMeta?.piotroski_zones);
    return null;
  },

  // Note explicative d'une ligne (ex. modèle non applicable aux financières).
  // N'est affichée que si la ligne n'a pas de zone (mutuellement exclusives).
  summaryNote(row) {
    return row.note || null;
  },

  // Catégorie de capitalisation : valeur serveur, repli client si absente.
  summaryCapLabel(row) {
    return row.text || marketCapLabel(this.data?.identity?.market_cap);
  },
};
