import { describe, expect, it, vi } from "vitest";

import {
  appSource,
  loadApp,
  portfolioMetaFromConfig,
  readConfigSource,
  readIndexSource,
  readStyleSource,
} from "./helpers/load-app.js";
import { portfolioMixin } from "../src/obole/web/portfolio.js";
import { api } from "../src/obole/web/api.js";

// #17.1 : la source unique des benchmarks/périodes est `config.py`, servie par
// `/api/portfolio/benchmarks`. Le front ne doit contenir AUCUN ticker ni période
// en dur — il lit le payload. On compare une lecture indépendante de config.py
// au comportement réel du mixin.

function comp(overrides = {}) {
  // `fmt` vient de chartsMixin dans l'app réelle : on le fournit ici pour
  // tester le mixin Résumé isolément (le composant `obole` assemble tout).
  const fmt = (v) => (v == null ? "—" : Number(v).toLocaleString("fr-FR", { maximumFractionDigits: 2 }));
  return { fmt, ...portfolioMixin, ...overrides };
}

describe("parité des benchmarks du portefeuille (config.py -> front)", () => {
  const configSource = readConfigSource();
  const meta = portfolioMetaFromConfig(configSource);

  it("le payload config.py liste des ETF EUR (tickers .PA/.AS/.DE/.MI)", () => {
    expect(meta.benchmarks.length).toBeGreaterThanOrEqual(4);
    for (const b of meta.benchmarks) {
      expect(b.ticker).toMatch(/\.(PA|AS|DE|MI)$/);
      expect(b.label).toBeTruthy();
    }
  });

  it("applyPortfolioMeta charge les benchmarks/périodes/défauts de config.py", () => {
    const app = loadApp();
    app.applyPortfolioMeta(meta);
    expect(app.PORTFOLIO_BENCHMARKS).toEqual(meta.benchmarks);
    expect(app.PORTFOLIO_BENCHMARK_DEFAULT).toBe(meta.default);
    expect(app.PORTFOLIO_PERIODS).toEqual(meta.periods);
    expect(app.PORTFOLIO_PERIOD_DEFAULT).toBe(meta.period_default);
    expect(app.PORTFOLIO_DETAIL_HORIZONS).toEqual(meta.detail_horizons);
    expect(app.PORTFOLIO_DETAIL_HORIZON_DEFAULT).toBe(meta.detail_horizon_default);
    expect(app.PORTFOLIO_TOP_N).toBe(meta.top_n);
  });

  it("le défaut config.py est présent dans la liste curée", () => {
    const tickers = meta.benchmarks.map((b) => b.ticker);
    expect(tickers).toContain(meta.default);
  });

  it("periodLabel() met en forme les raccourcis", () => {
    const app = loadApp();
    expect(app.periodLabel("ytd")).toBe("YTD");
    expect(app.periodLabel("max")).toBe("MAX");
    expect(app.periodLabel("3a")).toBe("3A");
  });

  it("portfolio.js ne contient aucun ticker ni période en dur", () => {
    // Les benchmarks/périodes arrivent de l'API : un littéral « CW8.PA » ou une
    // liste de périodes dans le mixin signalerait une réintroduction de seuil.
    const src = appSource().replace(/appSource[\s\S]*$/, "");
    expect(src).not.toMatch(/CW8\.PA|ESE\.PA|CACC\.PA/);
  });

  it("le CSS du résumé utilise les tokens de la charte (pas de couleur en dur)", () => {
    const css = readStyleSource();
    expect(css).toMatch(/\.pf-summary-grid\s*{[^}]*grid-template-columns/);
    expect(css).toMatch(/\.pf-kpis\s*{/);
    // Les pastilles de perf passent par les tokens good/bad (jamais #16a34a…).
    expect(css).toMatch(/\.pf-rank-perf\.good[^{]*{\s*color:\s*var\(--good\)/);
    expect(css).toMatch(/\.pf-rank-perf\.bad[^{]*{\s*color:\s*var\(--bad\)/);
    // La puce de période ACTIVE est bien stylée (bleu accent, texte blanc).
    expect(css).toMatch(/\.period-chip\.active\s*{[^}]*var\(--accent\)/);
  });

  it("le bandeau de contexte n'a AUCUNE couleur en dur (tokens seulement)", () => {
    const css = readStyleSource();
    // Bloc `.pf-context` jusqu'à la règle suivante du résumé : on isole la zone
    // du bandeau et on vérifie qu'aucun littéral hexadécimal n'y vit (le chevron
    // SVG et le texte sur aplat accent passent désormais par des tokens).
    const start = css.indexOf(".pf-context {");
    expect(start).toBeGreaterThan(-1);
    const block = css.slice(start, css.indexOf(".pf-perf-top {", start));
    expect(block).not.toMatch(/#[0-9a-fA-F]{3,8}/);
    expect(block).toMatch(/var\(--chevron-soft\)/);
    expect(block).toMatch(/var\(--on-accent\)/);
  });
});

describe("mixin Résumé — KPI, badge, libellés", () => {
  const KPI = {
    total_value: 2126.82, invested: 1836.5, total_return: 290.33, total_return_pct: 15.81,
    period_return_pct: 30.85, annualized_pct: 25.16, dividends: 72.97, dividend_yield_pct: 3.97,
    benchmark_period_pct: 14.58,
  };

  it("pfKpis() formate les 3 cartes (montants, %, pastille)", () => {
    const c = comp({ pfSummary: { kpis: KPI } });
    const k = c.pfKpis();
    expect(k.total_value.value).toContain("2");
    expect(k.total_value.sub).toContain("investis");
    expect(k.total_value.label).toBe("+15,81 %");
    expect(k.total_return.label).toBe("+25,16 %");
    expect(k.dividends.label).toBe("3,97 %");
    expect(k.total_value.good).toBe(true);
  });

  it("pfKpis() renvoie « — » sur valeur absente (jamais 0)", () => {
    const c = comp({ pfSummary: { kpis: {} } });
    const k = c.pfKpis();
    expect(k.total_value.value).toBe("—");
    expect(k.total_return.label).toBe("");
    expect(k.dividends.value).toBe("—");
  });

  it("pfPerfBadge() signe la performance de la période", () => {
    expect(comp({ pfSummary: { kpis: KPI } }).pfPerfBadge()).toEqual({ text: "+30,85 %", good: true });
    const neg = comp({ pfSummary: { kpis: { period_return_pct: -4.2 } } }).pfPerfBadge();
    expect(neg).toEqual({ text: "-4,2 %", good: false });
    expect(comp({ pfSummary: { kpis: {} } }).pfPerfBadge()).toEqual({ text: "—", good: null });
  });

  it("pfPerfBadge() compare au benchmark (rouge si sous-performance)", () => {
    // +5 % de perf mais +12 % de benchmark : le portefeuille SOUS-performe.
    const c = comp({ pfSummary: { kpis: { period_return_pct: 5, benchmark_period_pct: 12 } } });
    expect(c.pfPerfBadge()).toEqual({ text: "+5 %", good: false });
    // Perf positive au-dessus du benchmark : bleu.
    const d = comp({ pfSummary: { kpis: { period_return_pct: 15, benchmark_period_pct: 12 } } });
    expect(d.pfPerfBadge().good).toBe(true);
  });

  it("pfShowFlop() masque le Flop redondant (≤ top_n positions)", () => {
    const few = comp({ pfSummary: { top: [{ ticker: "A" }, { ticker: "B" }], flop: [{ ticker: "B" }, { ticker: "A" }] } });
    expect(few.pfShowFlop()).toBe(false); // mêmes lignes inversées
    const many = comp({
      pfTopNVal: 2,
      pfSummary: { top: [{ ticker: "A" }, { ticker: "B" }], flop: [{ ticker: "Z" }, { ticker: "Y" }] },
    });
    expect(many.pfShowFlop()).toBe(true); // lignes distinctes
  });

  it("pfPct() signe et localise un pourcentage", () => {
    const c = comp();
    expect(c.pfPct(12.5)).toBe("+12,5 %");
    expect(c.pfPct(-3)).toBe("-3 %");
    expect(c.pfPct(null)).toBe("—");
  });

  it("pfSigned() signe un montant en euros", () => {
    const c = comp();
    expect(c.pfSigned(101.69)).toBe("+101,69 €");
    expect(c.pfSigned(-17.33)).toBe("-17,33 €");
    expect(c.pfSigned(null)).toBe("");
  });

  it("pfInitials() produit deux lettres depuis le nom (repli sur le ticker)", () => {
    const c = comp();
    expect(c.pfInitials({ name: "Edenred SE" })).toBe("ES");
    expect(c.pfInitials({ name: "Worldline SA" })).toBe("WS");
    expect(c.pfInitials({ ticker: "RI.PA" })).toBe("RI");
    expect(c.pfInitials({})).toBe("?");
  });

  it("noms de traces : performance de période + annualisé (maquette)", () => {
    const c = comp({
      pfSummary: {
        benchmark: { ticker: "CW8.PA", label: "MSCI World" },
        kpis: { period_return_pct: 30.85, annualized_pct: 25.16, benchmark_period_pct: 14.58 },
      },
    });
    expect(c.pfPortfolioTraceName()).toBe("Performance (Perf: 30,85 %) (CAGR: 25,16 %)");
    expect(c.pfBenchmarkTraceName()).toBe("MSCI World (CW8.PA) (Perf: 14,58 %)");
  });

  it("pfBenchmarkLabel() résout un libellé depuis la liste curée", () => {
    const c = comp({ pfBenchmarks: [{ key: "world", ticker: "CW8.PA", label: "MSCI World" }] });
    expect(c.pfBenchmarkLabel("CW8.PA")).toBe("MSCI World (CW8.PA)");
    expect(c.pfBenchmarkLabel("XYZ.PA")).toBe("XYZ.PA");
  });

  it("pfChartEmpty() reflète l'absence de série", () => {
    expect(comp({ pfSummary: { dates: [] } }).pfChartEmpty()).toBe(true);
    expect(comp({ pfSummary: { dates: ["2024-01-01"] } }).pfChartEmpty()).toBe(false);
  });
});

describe("mixin Résumé — délégation à api.js et mémorisation du benchmark", () => {
  it("loadPortfolioSummary interroge le résumé avec le compte/benchmark/période", async () => {
    const spy = vi.spyOn(api, "portfolioSummary").mockResolvedValue({ dates: [], kpis: {} });
    const c = comp({
      _pfMetaReady: true, portfolioAccountId: 3, pfBenchmark: "CW8.PA", pfPeriod: "1a",
      portfolioTag: "Div", $nextTick: (fn) => fn(),
    });
    await c.loadPortfolioSummary();
    expect(spy).toHaveBeenCalledWith(3, "CW8.PA", "1a", "Div");
    spy.mockRestore();
  });

  it("loadPortfolioSummary reformule les erreurs serveur (vide vs introuvable)", async () => {
    const cases = [
      ["Benchmark vide", "Aucun benchmark choisi — saisis un ticker libre."],
      ["Benchmark introuvable sur Yahoo : XX.PA",
        "Benchmark introuvable : « CW8.PA » — corrige le ticker libre."],
      ["Période inconnue", "Résumé indisponible : Période inconnue."],
    ];
    for (const [serverMsg, expected] of cases) {
      const spy = vi.spyOn(api, "portfolioSummary")
        .mockRejectedValue(new Error(serverMsg));
      const c = comp({
        _pfMetaReady: true, pfBenchmark: "CW8.PA", pfPeriod: "1a",
        $nextTick: (fn) => fn(),
      });
      await c.loadPortfolioSummary();
      expect(c.pfSummaryError).toBe(expected);
      spy.mockRestore();
    }
  });

  it("setPfBenchmark persiste le dernier choix puis recalcule la section visible", async () => {
    const save = vi.spyOn(api, "saveSettings").mockResolvedValue({ ok: true, data: {} });
    const reload = vi.fn().mockResolvedValue();
    const c = comp({ pfBenchmark: "CW8.PA", portfolioSection: "resume",
      loadPortfolioSummary: reload });
    await c.setPfBenchmark("ese.pa"); // normalisé en majuscules
    expect(save).toHaveBeenCalledWith({ portfolio_benchmark: "ESE.PA" });
    expect(c.pfBenchmark).toBe("ESE.PA");
    expect(reload).toHaveBeenCalledTimes(1);
    save.mockRestore();
  });

  it("un changement de contexte ne recharge QUE la section visible", async () => {
    vi.spyOn(api, "saveSettings").mockResolvedValue({ ok: true, data: {} });
    const summary = vi.fn().mockResolvedValue();
    const risk = vi.fn().mockResolvedValue();
    const perf = vi.fn().mockResolvedValue();
    const div = vi.fn().mockResolvedValue();
    const c = comp({ pfBenchmark: "CW8.PA", pfPeriod: "1a",
      portfolioSection: "performance",
      loadPortfolioSummary: summary, loadPortfolioRisk: risk,
      loadPortfolioPerformance: perf, loadPortfolioDividends: div });
    await c.setPfBenchmark("ESE.PA");
    expect(perf).toHaveBeenCalledTimes(1);
    expect(summary).not.toHaveBeenCalled();
    expect(risk).not.toHaveBeenCalled();
    expect(div).not.toHaveBeenCalled();
  });

  it("le <select> benchmark n'a PAS de x-model (sinon @change sort trop tôt)", () => {
    // Régression : `x-model` met à jour `pfBenchmark` AVANT `@change`, donc
    // `setPfBenchmark(value)` voyait `value === this.pfBenchmark` et sortait
    // sans recalculer. La valeur vient de `:value` + pfBenchmark.
    const html = readIndexSource();
    const select = html.match(/<select[^>]*pf-bench-select[\s\S]*?>/)[0];
    expect(select).not.toMatch(/x-model/);
    expect(select).toMatch(/:value="pfBenchmark"/);
    expect(select).toMatch(/@change="setPfBenchmark/);
  });

  it("le popover « ticker libre » : ouverture, saisie, fermeture à la validation", async () => {
    // Le bouton « Autre… » ouvre un popover ANCRÉ dans le bandeau de contexte
    // (aucune modale empilée) ; le bouton « Valider » et la touche Entrée
    // partagent `applyPfBenchFree`, qui ferme le popover — aucune traversée DOM.
    const save = vi.spyOn(api, "saveSettings").mockResolvedValue({ ok: true, data: {} });
    const reload = vi.fn().mockResolvedValue();
    const c = comp({
      pfBenchmark: "CW8.PA",
      portfolioSection: "resume",
      $nextTick: (fn) => fn(),
      loadPortfolioSummary: reload,
    });
    // Ouverture : le champ est remis à zéro et la fenêtre s'ouvre.
    c.openPfBenchFree();
    expect(c.pfBenchFreeOpen).toBe(true);
    expect(c.pfBenchFree).toBe("");
    // Saisie puis validation : le benchmark est appliqué, en majuscules, et la
    // fenêtre se referme.
    c.pfBenchFree = " meud.pa ";
    await c.applyPfBenchFree();
    expect(save).toHaveBeenCalledWith({ portfolio_benchmark: "MEUD.PA" });
    expect(reload).toHaveBeenCalledTimes(1);
    expect(c.pfBenchFreeOpen).toBe(false);
    // Fermeture manuelle.
    c.openPfBenchFree();
    c.closePfBenchFree();
    expect(c.pfBenchFreeOpen).toBe(false);
    save.mockRestore();

    const html = readIndexSource();
    expect(html).toMatch(/x-model="pfBenchFree"/);
    expect(html).toMatch(/@click="applyPfBenchFree\(\)"/);
    // Le déclencheur bascule l'état (ouvre / ferme) : un seul bouton, pas deux.
    expect(html).toMatch(/pfBenchFreeOpen \? closePfBenchFree\(\) : openPfBenchFree\(\)/);
    // Le popover est DANS le bandeau de contexte, plus dans une modale empilée.
    const context = html.slice(html.indexOf('class="pf-context"'));
    expect(context.slice(0, 4000)).toMatch(/pf-bench-free-pop/);
    expect(html).not.toMatch(/modal-overlay-stacked/);
  });

  it("loadPortfolioNames complète les noms seulement si absents", async () => {
    const names = vi.spyOn(api, "portfolioNames").mockResolvedValue({
      names: { "AI.PA": "L'Air Liquide S.A.", "RI.PA": "Pernod Ricard SA" },
    });
    const c = comp({
      pfSummary: { top: [{ ticker: "RI.PA", name: null }], flop: [{ ticker: "AI.PA", name: null }] },
    });
    await c.loadPortfolioNames();
    expect(names).toHaveBeenCalledWith(["RI.PA", "AI.PA"]);
    expect(c.pfSummary.top[0].name).toBe("Pernod Ricard SA");
    expect(c.pfSummary.flop[0].name).toBe("L'Air Liquide S.A.");

    // Déjà nommées : aucun appel réseau (pas de requête inutile).
    names.mockClear();
    c.pfSummary = { top: [{ ticker: "RI.PA", name: "Pernod" }], flop: [] };
    await c.loadPortfolioNames();
    expect(names).not.toHaveBeenCalled();
    names.mockRestore();
  });

  it("setPfPeriod persiste la période et recalcule la section visible", async () => {
    const save = vi.spyOn(api, "saveSettings").mockResolvedValue({ ok: true, data: {} });
    const reload = vi.fn().mockResolvedValue();
    const c = comp({ pfPeriod: "1a", portfolioSection: "resume",
      loadPortfolioSummary: reload });
    await c.setPfPeriod("1a");
    expect(reload).not.toHaveBeenCalled();
    expect(save).not.toHaveBeenCalled();
    await c.setPfPeriod("5a");
    expect(save).toHaveBeenCalledWith({ portfolio_period: "5a" });
    expect(c.pfPeriod).toBe("5a");
    expect(reload).toHaveBeenCalledTimes(1);
    save.mockRestore();
  });

  it("le registre des capacités pilote les contrôles du bandeau", () => {
    // Une seule source : ajouter un onglet = une entrée, zéro markup dupliqué.
    expect(comp({ portfolioSection: "positions" }).portfolioControls())
      .toEqual({ scope: true, period: false, bench: false });
    expect(comp({ portfolioSection: "resume" }).portfolioControls())
      .toEqual({ scope: true, period: true, bench: true });
    expect(comp({ portfolioSection: "risque" }).portfolioControls())
      .toEqual({ scope: true, period: true, bench: true });
    expect(comp({ portfolioSection: "performance" }).portfolioControls())
      .toEqual({ scope: true, period: false, bench: true });
    expect(comp({ portfolioSection: "dividende" }).portfolioControls())
      .toEqual({ scope: true, period: false, bench: false });
  });

  it("un seul bandeau de contexte : aucun contrôle dupliqué dans le HTML", () => {
    const html = readIndexSource();
    expect((html.match(/class="pf-context"/g) || []).length).toBe(1);
    for (const cls of ["pf-account-select", "pf-tag-select", "pf-bench-select"]) {
      const count = (html.match(new RegExp(`class="[^"]*${cls}`, "g")) || []).length;
      expect(count, `${cls} ne doit apparaître qu'une fois`).toBe(1);
    }
    // Les quatre bandeaux d'onglet et le texte mort « vs … » ont disparu.
    for (const gone of ["pf-risk-head", "pf-perf-head", "pf-div-head", "pf-risk-bench"]) {
      expect(html).not.toContain(gone);
    }
  });

  it("openPfChartFull/closePfChartFull basculent l'état propre (sans le héro)", () => {
    const c = comp({
      pfSummary: { dates: ["2024-01-01"] },
      $nextTick: (fn) => fn(),
      drawPortfolioChart: vi.fn(),
    });
    c.openPfChartFull();
    expect(c.pfChartFull).toBe(true);
    c.closePfChartFull();
    expect(c.pfChartFull).toBe(false);
    // Le héro (detailCard) n'est jamais touché par cet espace.
    expect(c.detailCard).toBeUndefined();
  });
});

describe("mixin Résumé — donut centré (layout explicite + resize)", () => {
  // jsdom ne fait aucun layout : on remplace `document.getElementById` par un
  // faux nœud qui expose les dimensions mesurées (`clientWidth`/`clientHeight`).
  function fakeEl(w, h) {
    return { id: "pf-summary-donut", clientWidth: w, clientHeight: h };
  }

  function captureLayout(el = fakeEl(700, 320)) {
    const seen = {};
    globalThis.Plotly = {
      react: (id, traces, layout) => {
        seen.id = id;
        seen.traces = traces;
        seen.layout = layout;
      },
    };
    const spy = vi.spyOn(document, "getElementById").mockReturnValue(el);
    return { seen, spy };
  }

  it("drawPortfolioDonut fixe largeur/hauteur sur le conteneur (marges nulles)", () => {
    const { seen, spy } = captureLayout();
    const c = comp({ pfSummary: { accounts: [{ name: "PEA", value: 100 }] } });
    c.drawPortfolioDonut("pf-summary-donut");
    // Zone de tracé = conteneur : disque centré sur les deux axes.
    expect(seen.layout.margin).toEqual({ l: 0, r: 0, t: 0, b: 0 });
    expect(seen.layout.width).toBe(700);
    expect(seen.layout.height).toBe(320);
    expect(seen.layout.autosize).toBe(false);
    expect(seen.layout.showlegend).toBe(false);
    // La galette reste un cercle (hauteur = largeur du disque côté Plotly).
    expect(seen.traces[0].hole).toBe(0.62);
    expect(seen.traces[0].domain).toEqual({ x: [0, 1], y: [0, 1] });
    // Libellés DANS le disque : en « outside », les noms longs des parts
    // étroites débordaient du SVG et étaient rognés.
    expect(seen.traces[0].textposition).toBe("inside");
    expect(seen.traces[0].insidetextorientation).toBe("horizontal");
    spy.mockRestore();
  });

  it("sans conteneur mesurable, la hauteur par défaut est réutilisée", () => {
    const { seen, spy } = captureLayout({ id: "pf-summary-donut" });
    // clientWidth absent (ex. avant layout) : on ne doit pas tracer 0×0.
    const c = comp({ pfSummary: { accounts: [{ name: "PEA", value: 100 }] } });
    c.drawPortfolioDonut("pf-summary-donut");
    expect(seen.layout.width).toBeGreaterThan(0);
    expect(seen.layout.height).toBeGreaterThan(0);
    spy.mockRestore();
  });

  it("drawPortfolioDonut ne lève pas si ResizeObserver est absent (jsdom)", () => {
    const { spy } = captureLayout();
    delete globalThis.ResizeObserver;
    const c = comp({ pfSummary: { accounts: [{ name: "PEA", value: 100 }] } });
    expect(() => c.drawPortfolioDonut("pf-summary-donut")).not.toThrow();
    spy.mockRestore();
  });

  it("observe le conteneur (ResizeObserver) et re-trace au changement de largeur", async () => {
    const { spy } = captureLayout();
    let cb = null;
    globalThis.ResizeObserver = class {
      constructor(fn) { cb = fn; }
      observe() {}
      disconnect() {}
    };
    const c = comp({ pfSummary: { accounts: [{ name: "PEA", value: 100 }] } });
    c.drawPortfolioDonut("pf-summary-donut");
    expect(typeof cb).toBe("function");
    // Largeur inchangée : pas de re-tracé (garde anti-boucle).
    const redraw = vi.spyOn(c, "_drawDonut");
    cb([{ target: fakeEl(700, 320) }]);
    await new Promise((r) => setTimeout(r, 20));
    expect(redraw).not.toHaveBeenCalled();
    // Largeur changée : re-tracé demandé (au tour d'animation suivant), sur le
    // bon conteneur.
    cb([{ target: fakeEl(812, 320) }]);
    await new Promise((r) => setTimeout(r, 20));
    expect(redraw).toHaveBeenCalledWith("pf-summary-donut", expect.anything(), expect.anything());
    delete globalThis.ResizeObserver;
    spy.mockRestore();
  });

  it("closePortfolio déconnecte l'observateur (pas de fuite)", () => {
    const { spy } = captureLayout();
    const disconnect = vi.fn();
    globalThis.ResizeObserver = class {
      constructor() {}
      observe() {}
      disconnect() { disconnect(); }
    };
    const c = comp({ pfSummary: { accounts: [{ name: "PEA", value: 100 }] } });
    c.drawPortfolioDonut("pf-summary-donut");
    c.closePortfolio();
    expect(disconnect).toHaveBeenCalledTimes(1);
    delete globalThis.ResizeObserver;
    spy.mockRestore();
  });
});

describe("mixin Résumé — répartition Comptes / Titres (donut)", () => {
  function captureLayout(el = { id: "pf-summary-donut", clientWidth: 700, clientHeight: 320 }) {
    const seen = {};
    globalThis.Plotly = {
      react: (id, traces, layout) => { seen.id = id; seen.traces = traces; seen.layout = layout; },
      purge: () => { seen.purged = true; },
    };
    const spy = vi.spyOn(document, "getElementById").mockReturnValue(el);
    return { seen, spy };
  }

  it("pfBreakdownData bascule entre comptes et titres", () => {
    const c = comp({
      pfSummary: {
        accounts: [{ name: "PEA", value: 100 }, { name: "CTO", value: 50 }],
        holdings: [{ ticker: "RI.PA", name: null, value: 90 }, { ticker: "AI.PA", name: null, value: 60 }],
      },
    });
    expect(c.pfBreakdown).toBe("accounts");
    expect(c.pfBreakdownData().labels).toEqual(["PEA", "CTO"]);
    expect(c.pfBreakdownData().title).toBe("Répartition des comptes");
    c.pfBreakdown = "holdings";
    // Le libellé retombe sur le ticker quand le nom n'est pas résolu.
    expect(c.pfBreakdownData().labels).toEqual(["RI.PA", "AI.PA"]);
    expect(c.pfBreakdownData().title).toBe("Répartition des titres");
  });

  it("pfBreakdownOptions pilote le libellé du bouton (extensible)", () => {
    const c = comp({});
    expect(c.pfBreakdownOptions().map((o) => o.key)).toEqual(["accounts", "holdings"]);
    expect(c.pfBreakdownLabel()).toBe("Comptes");
    c.pfBreakdown = "holdings";
    expect(c.pfBreakdownLabel()).toBe("Titres");
  });

  it("togglePfBreakdownMenu ouvre/ferme le menu ; setPfBreakdown le referme", () => {
    const c = comp({ pfSummary: { accounts: [{ name: "PEA", value: 100 }] }, $nextTick: (fn) => fn() });
    expect(c.pfBreakdownMenuOpen).toBe(false);
    c.togglePfBreakdownMenu();
    expect(c.pfBreakdownMenuOpen).toBe(true);
    c.togglePfBreakdownMenu();
    expect(c.pfBreakdownMenuOpen).toBe(false);
    c.togglePfBreakdownMenu();
    c.setPfBreakdown("holdings");
    expect(c.pfBreakdownMenuOpen).toBe(false);
  });

  it("pfBreakdownData préfère le nom de société quand il est résolu", () => {
    const c = comp({ pfSummary: { holdings: [{ ticker: "RI.PA", name: "Pernod Ricard", value: 90 }] } });
    c.pfBreakdown = "holdings";
    expect(c.pfBreakdownData().labels).toEqual(["Pernod Ricard"]);
  });

  it("setPfBreakdown ignore la dimension identique et re-trace sinon", () => {
    const { seen, spy } = captureLayout();
    const c = comp({ pfSummary: { accounts: [{ name: "PEA", value: 100 }] }, $nextTick: (fn) => fn() });
    const redraw = vi.spyOn(c, "drawPortfolioDonut");
    c.setPfBreakdown("accounts"); // identique -> aucun effet
    expect(redraw).not.toHaveBeenCalled();
    c.setPfBreakdown("holdings");
    expect(c.pfBreakdown).toBe("holdings");
    expect(redraw).toHaveBeenCalled();
    spy.mockRestore();
    void seen;
  });

  it("drawPortfolioDonut trace la dimension choisie (titres)", () => {
    const { seen, spy } = captureLayout();
    const c = comp({
      pfSummary: { accounts: [{ name: "PEA", value: 100 }], holdings: [{ ticker: "RI.PA", name: null, value: 90 }] },
    });
    c.pfBreakdown = "holdings";
    c.drawPortfolioDonut("pf-summary-donut");
    expect(seen.traces[0].labels).toEqual(["RI.PA"]);
    expect(seen.traces[0].values).toEqual([90]);
    spy.mockRestore();
  });

  it("dimension vide : purge le tracé (pas de disque périmé sous le message)", () => {
    const { seen, spy } = captureLayout();
    const c = comp({ pfSummary: { accounts: [{ name: "PEA", value: 100 }], holdings: [] } });
    c.pfBreakdown = "holdings";
    c.drawPortfolioDonut("pf-summary-donut");
    expect(seen.purged).toBe(true);
    expect(seen.traces).toBeUndefined();
    spy.mockRestore();
  });
});
