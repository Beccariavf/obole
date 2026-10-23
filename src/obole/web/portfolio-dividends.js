// Obole — onglet Dividende du PORTEFEUILLE (#17.5).
//
// Un domaine = un module (comme `dividend.js` pour la fiche, `summary.js` pour la
// synthèse). Ce mixin assemble le payload de `/api/portfolio/dividend-metrics` :
// tuiles KPI (taxonomie `config.PORTFOLIO_DIVIDEND_GROUPS` via /api/meta), graphe
// mensuel héros, concentration du revenu et tableau par ligne.
//
// Aucun calcul financier ici : les agrégats (rendement, yield on cost, payout,
// shareholder yield, contribution à la performance) sont calculés SERVEUR. Le
// front ne fait que filtrer l'année affichée, trier et mettre en forme — même
// partage des rôles que la Performance (`computeLive` ne touche jamais un ratio).
import { api } from "./api.js";
import { C } from "./theme.js";
import {
  CHART_HEIGHTS,
  PORTFOLIO_DIVIDEND_GROUPS,
  PORTFOLIO_DIVIDEND_POLARITY,
  PORTFOLIO_DIVIDEND_UNITS,
  PORTFOLIO_DIVIDEND_GAP_SCALE_PP,
} from "./thresholds.js";

// Mois abrégés des barres mensuelles (libellés d'affichage seulement — le
// découpage temporel, lui, vient du serveur).
const MONTH_LABELS = [
  "Janv", "Févr", "Mars", "Avr", "Mai", "Juin",
  "Juil", "Août", "Sept", "Oct", "Nov", "Déc",
];

// Palette catégorielle unifiée du projet (aucun rouge ni vert : charte).
const CATEGORICAL = [C.accent, C.teal, C.ma2, C.ma1];

// Polarité d'un KPI de dividende depuis la source unique `DIVIDEND_POLARITY`.
function dividendPageGood(key, value) {
  const t = PORTFOLIO_DIVIDEND_POLARITY[key];
  if (!t || value == null || Number.isNaN(value)) return null;
  const [sens, seuil] = t;
  if (seuil == null) return null;
  if (sens === "ge") return value >= seuil;
  if (sens === "le") return value <= seuil;
  if (sens === "le_pos") return value > 0 && value <= seuil;
  return null;
}

export const portfolioDividendsMixin = {
  pfDiv: null,              // payload de la page Dividende
  pfDivLoading: false,
  pfDivError: "",
  pfDivYear: "ttm",         // période affichée : "ttm" (12 derniers mois) ou "2025"
  pfDivSortKey: "income_share_pct",
  pfDivSortDir: -1,         // -1 = décroissant (défaut : poids de revenu)

  // Charge la page Dividende sur le périmètre courant (compte et/ou étiquette).
  async loadPortfolioDividends() {
    this.pfDivLoading = true;
    this.pfDivError = "";
    try {
      this.pfDiv = await api.portfolioDividendPage(
        this.portfolioAccountId,
        this.portfolioTag || null,
      );
      // Les tracés Plotly ne se dessinent que sur un conteneur VISIBLE et
      // dimensionné : on redessine après le rendu Alpine, puis au retour d'onglet.
      this.$nextTick(() => this.drawPortfolioDividends());
    } catch (e) {
      this.pfDivError = `Chargement des dividendes impossible : ${e?.message || "erreur réseau"}.`;
    } finally {
      this.pfDivLoading = false;
    }
  },
  // --- Période affichée -----------------------------------------------------
  // Deux boutons seulement : « TTM » (12 derniers mois) et un SÉLECTEUR d'année
  // précise. Une chip par année devenait illisible dès qu'un portefeuille a
  // 5-10 ans d'historique — et la chip « (en cours) » poussait la rangée hors de
  // l'en-tête de carte.

  // Années proposées (décroissant) pour le sélecteur.
  pfDivYears() {
    return [...(this.pfDiv?.income?.years || [])].sort((a, b) => b - a);
  },

  pfDivIsTtm() {
    return this.pfDivYear === "ttm";
  },

  // Année réellement sélectionnée dans le sélecteur : la valeur retenue si elle
  // existe encore, sinon la plus récente. `null` en mode TTM (aucune année).
  pfDivActiveYear() {
    if (this.pfDivIsTtm()) return null;
    const years = this.pfDivYears();
    if (!years.length) return null;
    const chosen = Number(this.pfDivYear);
    return years.includes(chosen) ? chosen : years[0];
  },

  pfDivYearLabel(year) {
    const now = new Date().getFullYear();
    return String(year) + (year === now ? " (en cours)" : "");
  },

  // Bascule la période : "ttm" ou une année. Redessine le graphe (Plotly ne se
  // met à jour que sur un conteneur visible et déjà dimensionné).
  setPfDivPeriod(value) {
    const next = String(value || "ttm");
    if (next === this.pfDivYear) return;
    this.pfDivYear = next;
    this.$nextTick(() => this.drawPfDivMonthly());
  },

  // Alias historique (les chips appelaient `setPfDivYear(y)`).
  setPfDivYear(year) {
    this.setPfDivPeriod(year);
  },

  // Fenêtre de mois affichée : la liste ordonnée de {year, month} à tracer.
  //   • TTM : les 12 derniers mois CALENDAIRES de la série (compteur année×12 +
  //     mois), donc un trou mensuel ne rallonge jamais la fenêtre ;
  //   • une année : ses mois présents (année partielle incluse).
  pfDivWindowMonths() {
    const rows = (this.pfDiv?.income?.rows || []).slice();
    if (!rows.length) return [];
    if (!this.pfDivIsTtm()) {
      const year = this.pfDivActiveYear();
      const row = rows.find((r) => r.year === year);
      if (!row) return [];
      return Object.keys(row.months || {})
        .map((m) => ({ year, month: Number(m) }))
        .sort((a, b) => a.month - b.month);
    }
    const keys = [];
    for (const r of rows) {
      for (const m of Object.keys(r.months || {})) {
        keys.push({ year: r.year, month: Number(m) });
      }
    }
    if (!keys.length) return [];
    keys.sort((a, b) => a.year * 12 + a.month - (b.year * 12 + b.month));
    const last = keys[keys.length - 1];
    const cutoff = last.year * 12 + last.month - 11;
    return keys.filter((k) => k.year * 12 + k.month >= cutoff);
  },

  // Ligne(s) de revenu couvertes par la fenêtre (deux en TTM quand la fenêtre
  // chevauche deux années civiles). Payload serveur, jamais recalculée.
  pfDivIncomeRows() {
    const rows = this.pfDiv?.income?.rows || [];
    if (this.pfDivIsTtm()) return rows;
    const year = this.pfDivActiveYear();
    return rows.filter((r) => r.year === year);
  },

  // Compat : la ligne unique de l'année sélectionnée (`null` en TTM).
  pfDivIncomeRow() {
    if (this.pfDivIsTtm()) return null;
    const year = this.pfDivActiveYear();
    if (year == null) return null;
    return (this.pfDiv?.income?.rows || []).find((r) => r.year === year) || null;
  },

  // --- Tuiles KPI -----------------------------------------------------------

  // Tuiles prêtes à rendre : taxonomie serveur + valeur/polarité + sous-texte.
  // Une valeur absente affiche « — » (jamais 0) et le sous-texte porte la raison.
  pfDivKpis() {
    const stats = this.pfDiv?.stats || {};
    if (!Object.keys(stats).length) return [];
    const out = [];
    for (const group of PORTFOLIO_DIVIDEND_GROUPS) {
      for (const def of group.metrics || []) {
        const cell = stats[def.key] || {};
        const value = cell.value;
        out.push({
          key: def.key,
          label: def.label,
          value: this.pfDivFormatValue(def.key, value, def.signed === true),
          good: cell.good ?? dividendPageGood(def.key, value),
          sub: this.pfDivSubLabel(def, stats),
        });
      }
    }
    return out;
  },

  // Repère l'unité d'une métrique (source unique `PORTFOLIO_DIVIDEND_UNITS`).
  pfDivUnit(key) {
    return PORTFOLIO_DIVIDEND_UNITS[key] || "pct";
  },

  // `signed` vient de la taxonomie (`config.PORTFOLIO_DIVIDEND_GROUPS`) : le « + »
  // est réservé aux VARIATIONS (CAGR, contribution), jamais à un NIVEAU — même
  // convention que `pfStatValue`. « +3,2 % » de yield serait faux.
  pfDivFormatValue(key, v, signed = false) {
    if (v == null) return "—";
    const unit = this.pfDivUnit(key);
    const sign = signed && v > 0 ? "+" : "";
    if (unit === "money") return this.pfMoney(v) + " €";
    if (unit === "pt") return sign + this.fmt(v) + " pt";
    return sign + this.fmt(v) + " %";
  },

  // Sous-texte d'une tuile : libellé fixe (`sub`), taux de couverture associé
  // (`coverage_of`) ou revenu cumulé (`sub_of`) — jamais une seconde valeur mise
  // en avant (le sous-texte ne prend aucune couleur sémantique).
  pfDivSubLabel(def, stats) {
    const parts = [];
    if (def.sub) parts.push(def.sub);
    if (def.coverage_of) {
      const cov = (stats[def.coverage_of] || {}).value;
      if (cov != null) parts.push("couverture " + this.fmt(cov) + " %");
    }
    if (def.sub_of) {
      const total = (stats[def.sub_of] || {}).value;
      if (total != null) parts.push("cumul " + this.pfMoney(total) + " €");
    }
    // Les DEUX taux annualisés qui composent la contribution : la soustraction
    // devient vérifiable à l'écran (sinon le chiffre est inauditable).
    if (def.key === "dividend_contribution_pct") {
      const withDiv = (stats.twr_with_dividends_pct || {}).value;
      const withoutDiv = (stats.twr_without_dividends_pct || {}).value;
      if (withDiv != null && withoutDiv != null) {
        parts.push(this.fmt(withDiv) + " % avec · " + this.fmt(withoutDiv) + " % sans");
      }
    }
    return parts.join(" · ");
  },

  // --- Graphique héros : dividendes reçus par mois --------------------------

  // Séries empilées par payeur sur la FENÊTRE courante (TTM ou une année). Une
  // proposition (`proposed`) est rendue dans la MÊME pile mais hachurée côté tracé.
  pfDivMonthlySeries() {
    const windowMonths = this.pfDivWindowMonths();
    if (!windowMonths.length) return { months: [], labels: [], series: [] };
    const rows = this.pfDiv?.income?.rows || [];
    const byYear = new Map(rows.map((r) => [r.year, r]));
    // Payeurs de la fenêtre : union des `by_ticker` des années couvertes.
    const payers = new Set();
    for (const { year } of windowMonths) {
      const row = byYear.get(year);
      for (const ticker of Object.keys(row?.by_ticker || {})) payers.add(ticker);
    }
    // Valeur d'un payeur pour un mois donné : on interroge l'année de ce mois,
    // jamais une autre (les montants d'années différentes ne se mélangent pas).
    const pick = (ticker, k, bucket) => {
      const row = byYear.get(k.year);
      const cell = row?.by_ticker?.[ticker]?.[bucket] || {};
      return cell[String(k.month)] ?? null;
    };
    const sumOf = (ticker) =>
      windowMonths.reduce((acc, k) => acc + (pick(ticker, k, "months") || 0), 0);
    // Ordre d'empilement : plus gros payeur en bas (lecture décroissante).
    const tickers = [...payers].sort((a, b) => sumOf(b) - sumOf(a));
    const series = tickers.map((ticker, i) => ({
      ticker,
      values: windowMonths.map((k) => pick(ticker, k, "months")),
      proposed: windowMonths.map((k) => pick(ticker, k, "proposed")),
      color: i < CATEGORICAL.length ? CATEGORICAL[i] : C.neutral,
    }));
    const years = new Set(windowMonths.map((k) => k.year));
    const multiYear = years.size > 1;
    return {
      months: windowMonths.map((k) => k.month),
      // Étiquette d'axe : mois seul ; l'année n'apparaît que si la fenêtre
      // chevauche plusieurs années civiles (cas du TTM), où elle lève l'ambiguïté.
      labels: windowMonths.map((k, i) => {
        const name = MONTH_LABELS[k.month - 1] || String(k.month);
        if (!multiYear) return name;
        const prev = windowMonths[i - 1];
        return !prev || prev.year !== k.year ? `${name} ${k.year}` : name;
      }),
      series,
    };
  },

  // Total confirmé / proposé de la FENÊTRE affichée, pour la légende.
  // En TTM on additionne les années couvertes (la fenêtre n'est pas une année
  // civile) ; un mois hors fenêtre ne compte jamais.
  pfDivYearTotals() {
    const rows = this.pfDiv?.income?.rows || [];
    if (!rows.length) return { confirmed: null, proposed: null, count: 0 };
    if (!this.pfDivIsTtm()) {
      const row = this.pfDivIncomeRow();
      return {
        confirmed: row ? row.total_confirmed : null,
        proposed: row ? row.total_proposed : null,
        count: row ? row.count : 0,
      };
    }
    const windowMonths = this.pfDivWindowMonths();
    const byYear = new Map(rows.map((r) => [r.year, r]));
    let confirmed = 0;
    let proposed = 0;
    let count = 0;
    let seen = false;
    for (const k of windowMonths) {
      const row = byYear.get(k.year);
      if (!row) continue;
      const c = row.months?.[String(k.month)];
      if (c != null) {
        confirmed += c;
        count += 1;
        seen = true;
      }
      for (const t of Object.values(row.by_ticker || {})) {
        const p = t.proposed?.[String(k.month)];
        if (p != null) {
          proposed += p;
          count += 1;
          seen = true;
        }
      }
    }
    return {
      confirmed: seen ? Math.round(confirmed * 100) / 100 : null,
      proposed: proposed ? Math.round(proposed * 100) / 100 : null,
      count,
    };
  },

  // « Aucun dividende reçu » (état vide du GRAPHE et du tableau) n'est PAS
  // « aucune donnée » : un portefeuille sans versement saisi produit quand même
  // un rendement courant, un revenu TTM et une couverture. Les tuiles restent
  // donc affichées dès qu'un KPI est calculable.
  pfDivEmpty() {
    return !(this.pfDiv?.income?.rows || []).length;
  },

  pfDivAllEmpty() {
    return this.pfDivEmpty() && !Object.keys(this.pfDiv?.stats || {}).length;
  },

  // Tracé des barres mensuelles empilées : plein = confirmé, hachuré = proposé
  // (`marker.pattern`, natif Plotly 2.35 vendorisé — aucune dépendance ajoutée).
  drawPfDivMonthly() {
    if (typeof document === "undefined" || typeof Plotly === "undefined") return;
    const el = document.getElementById("pf-div-monthly");
    if (!el) return;
    const data = this.pfDivMonthlySeries();
    if (!data.series.length) {
      Plotly.purge(el);
      return;
    }
    const traces = [];
    data.series.forEach((s) => {
      traces.push({
        x: data.labels,
        y: s.values,
        type: "bar",
        name: s.ticker,
        marker: { color: s.color },
        hovertemplate: "%{x}<br>" + s.ticker + " · %{y:.2f} €<extra></extra>",
      });
      // Proposition : même teinte, hachurée. Le hachurage est le seul canal qui
      // survit au daltonisme et à l'impression N&B (une opacité serait illisible).
      if (s.proposed.some((v) => v != null && v !== 0)) {
        traces.push({
          x: data.labels,
          y: s.proposed,
          type: "bar",
          name: s.ticker + " (proposé)",
          marker: {
            color: s.color,
            pattern: { shape: "/", bgcolor: s.color, fgcolor: "rgba(0,0,0,.18)" },
          },
          hovertemplate:
            "%{x}<br>" + s.ticker + " proposé · %{y:.2f} €<extra></extra>",
        });
      }
    });
    Plotly.react(el, traces, {
      barmode: "stack",
      bargap: 0.25,
      margin: { l: 44, r: 12, t: 6, b: 40 },
      height: CHART_HEIGHTS.portfolio_dividends || 300,
      paper_bgcolor: "transparent",
      plot_bgcolor: "transparent",
      font: { family: "Inter, sans-serif", size: 10, color: C.text },
      xaxis: { gridcolor: C.grid, showline: false, type: "category" },
      yaxis: {
        gridcolor: C.grid,
        showline: false,
        zeroline: true,
        zerolinecolor: C.neutral,
        ticksuffix: " €",
      },
      hovermode: "x unified",
      showlegend: false,
    }, { displayModeBar: false, responsive: true });
  },

  // --- Concentration du revenu ---------------------------------------------

  // Barres horizontales triées décroissantes, une seule teinte : c'est une même
  // quantité (le revenu) mesurée sur des payeurs, pas des catégories — une
  // palette ici serait une faute de grammaire. Remplace le camembert (illisible
  // au-delà de 6 parts et qui ne quantifie rien).
  pfDivConcentrationItems() {
    return (this.pfDiv?.income?.by_company || []).filter((c) => c.share_pct != null);
  },

  drawPfDivConcentration() {
    if (typeof document === "undefined" || typeof Plotly === "undefined") return;
    const el = document.getElementById("pf-div-concentration");
    if (!el) return;
    const items = this.pfDivConcentrationItems().slice().reverse(); // haut = plus gros
    if (!items.length) {
      Plotly.purge(el);
      return;
    }
    // Une barre par payeur : hauteur PROPORTIONNELLE au nombre de lignes, sans
    // plancher (base) ni plafond (au-delà de ~8 payeurs, on défile plutôt que de
    // faire des barres de 4 px). Une hauteur figée débordait de la carte.
    const rowH = CHART_HEIGHTS.portfolio_div_conc_row || 34;
    const pad = CHART_HEIGHTS.portfolio_div_conc_pad || 40;
    const height = Math.max(
      CHART_HEIGHTS.portfolio_div_conc || 0,
      items.length * rowH + pad,
    );
    // Le conteneur suit le tracé (sinon le SVG déborde sur la carte suivante) :
    // CSS ne pose qu'une hauteur MINIMALE, la hauteur réelle vient d'ici.
    el.style.height = height + "px";
    Plotly.react(el, [{
      x: items.map((c) => c.share_pct),
      y: items.map((c) => c.ticker),
      type: "bar",
      orientation: "h",
      marker: { color: C.accent },
      hovertemplate: "%{y}<br>%{x:.2f} % du revenu<extra></extra>",
    }], {
      margin: { l: 92, r: 12, t: 6, b: 24 },
      height,
      bargap: 0.6,
      paper_bgcolor: "transparent",
      plot_bgcolor: "transparent",
      font: { family: "Inter, sans-serif", size: 10, color: C.text },
      xaxis: { gridcolor: C.grid, showline: false, ticksuffix: " %" },
      yaxis: { gridcolor: C.grid, showline: false, type: "category", automargin: true },
      showlegend: false,
    }, { displayModeBar: false, responsive: true });
  },

  // Chiffres de contexte de la concentration (jamais des tuiles de pilotage).
  pfDivConcentrationStats() {
    const c = this.pfDiv?.concentration;
    if (!c || c.n_eff == null) return [];
    return [
      { label: "Payeurs", value: this.fmt(c.payers) },
      { label: "Payeurs effectifs", value: this.fmt(c.n_eff) },
      { label: "Top " + c.top_n, value: this.fmt(c.top_n_pct) + " %" },
      { label: "1er payeur", value: this.fmt(c.first_pct) + " %" },
    ];
  },

  // --- Tableau par ligne ---------------------------------------------------

  // Lignes triées (client) : par défaut le poids de revenu décroissant, c'est-à-
  // dire « d'où vient l'argent ». Une valeur absente passe toujours en dernier.
  pfDivLines() {
    const rows = [...(this.pfDiv?.lines || [])];
    const key = this.pfDivSortKey;
    const dir = this.pfDivSortDir;
    return rows.sort((a, b) => {
      const va = a[key];
      const vb = b[key];
      if (va == null && vb == null) return a.ticker.localeCompare(b.ticker);
      if (va == null) return 1;
      if (vb == null) return -1;
      // Une colonne TEXTE (le titre) se compare alphabétiquement : `"RI.PA" -
      // "AI.PA"` vaut NaN en JS et laissait l'ordre figé dans les deux sens.
      if (typeof va === "string" || typeof vb === "string") {
        const cmp = String(va).localeCompare(String(vb), "fr");
        return cmp === 0 ? 0 : cmp * dir;
      }
      if (va === vb) return a.ticker.localeCompare(b.ticker);
      return (va - vb) * dir;
    });
  },

  setPfDivSort(key) {
    if (this.pfDivSortKey === key) {
      this.pfDivSortDir = -this.pfDivSortDir;
    } else {
      this.pfDivSortKey = key;
      this.pfDivSortDir = -1;
    }
  },

  pfDivSortIcon(key) {
    if (this.pfDivSortKey !== key) return "";
    return this.pfDivSortDir < 0 ? " ▼" : " ▲";
  },

  // `aria-sort` de l'en-tête trié (accessibilité lecteurs d'écran).
  pfDivAriaSort(key) {
    if (this.pfDivSortKey !== key) return "none";
    return this.pfDivSortDir < 0 ? "descending" : "ascending";
  },

  // Affichage d'une cellule numérique du tableau (None -> « — », jamais 0).
  pfDivCell(key, v) {
    if (v == null) return "—";
    if (key === "gap_pp") return (v > 0 ? "+" : "") + this.fmt(v) + " pt";
    return this.fmt(v) + " %";
  },

  // Largeur de la micro-barre divergente de l'écart (0 à 1, bornée). L'échelle
  // pleine vient de `config.py` (`PORTFOLIO_DIVIDEND_GAP_SCALE_PP` via /api/meta) :
  // aucun seuil visuel codé en dur ici.
  pfDivGapWidth(v) {
    if (v == null) return 0;
    const scale = PORTFOLIO_DIVIDEND_GAP_SCALE_PP || 10;
    return Math.min(1, Math.abs(v) / scale);
  },

  pfDivGapSide(v) {
    if (v == null) return "none";
    return v >= 0 ? "pos" : "neg";
  },

  // --- Badges de fiabilité -------------------------------------------------

  pfDivWarnings() {
    return this.pfDiv?.warnings || [];
  },

  // Trace les deux cartes après le rendu (Alpine détruit/recrée le DOM de
  // l'onglet à chaque bascule : on rejoue donc les tracés à l'affichage).
  drawPortfolioDividends() {
    this.$nextTick(() => {
      this.drawPfDivMonthly();
      this.drawPfDivConcentration();
    });
  },
};
