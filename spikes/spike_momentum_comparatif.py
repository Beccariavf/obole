"""Test décisif de la Clara Vallis — hors ligne, cache.sqlite en LECTURE SEULE.

Compare, sur toutes les séries de prix ajustées du cache (>= 8 ans), la Clara Vallis
à trois règles simples, puis teste le momentum en COUPE (classement entre titres),
seule forme où la littérature trouve un effet robuste.

1. Série temporelle (titre par titre) : la position de t est décidée en t−1.
   - CV      : hystérésis LOW/HIGH sur la satisfaction (moteur du dépôt, tel quel)
   - STOCH   : stochastique 250 j > 0,5 (version « nue » de la CV)
   - MM200   : cours > moyenne mobile 200 j
   - MOM12-1 : rendement de t−252 à t−21 > 0 (momentum de Jegadeesh-Titman)
   Pour chaque règle : écart moyen in − out (pb/jour), part des titres où in > out,
   test placebo par décalage circulaire des positions, volatilité in/out.
2. Sensibilité de la CV à la fenêtre W et aux bornes.
3. Coupe transversale mensuelle : terciles du signal en fin de mois, rendement du
   mois suivant, écart haut − bas et sa statistique t.

Limites : l'univers est celui du cache (biais de survivance, non défini à l'avance),
les rendements sont bruts de frais sauf mention.

Usage : .venv/bin/python spikes/spike_momentum_comparatif.py [sortie.csv]
"""

from __future__ import annotations

import pickle
import sqlite3
import sys

import numpy as np
import pandas as pd

from obole import config

MIN_YEARS = 8
N_PLACEBO = 200
rng = np.random.default_rng(0)

# Constantes de l'étude, recopiées localement : le spike reste autonome depuis
# le retrait de la Clara Vallis du dépôt (#33).
LOW = 0.35
HIGH = 0.60
FEE_PCT = 0.1


def _bubble_window(window_prices: np.ndarray) -> np.ndarray:
    """Bulles de toutes les entrées d'une fenêtre fermée à droite (formule CV)."""
    last = window_prices[-1]
    suffix_min = np.minimum.accumulate(window_prices[::-1])[::-1]
    suffix_max = np.maximum.accumulate(window_prices[::-1])[::-1]
    span = suffix_max - suffix_min
    safe = np.where(span > 0, span, 1.0)
    return np.where(span > 0, (last - suffix_min) / safe, 0.5)


def _satisfaction_series(prices: pd.Series, window: int = 250) -> pd.Series:
    """Copie locale du score de satisfaction, pour que le spike reste exécutable."""
    s = prices.dropna()
    s = s[s > 0]
    out = pd.Series(np.nan, index=s.index, dtype=float)
    n = len(s)
    if n < 2:
        return out
    p = s.to_numpy(dtype=float)
    if n < window:
        out.iloc[-1] = float(np.mean(_bubble_window(p)))
        return out
    view = np.lib.stride_tricks.sliding_window_view(p, window)
    last = p[window - 1 :]
    scores = np.empty(len(view), dtype=float)
    for start in range(0, len(view), 2000):
        stop = min(start + 2000, len(view))
        block = view[start:stop][:, ::-1]
        suffix_min = np.minimum.accumulate(block, axis=1)
        suffix_max = np.maximum.accumulate(block, axis=1)
        span = suffix_max - suffix_min
        safe = np.where(span > 0, span, 1.0)
        bubbles = np.where(span > 0, (last[start:stop, None] - suffix_min) / safe, 0.5)
        scores[start:stop] = bubbles.mean(axis=1)
    out.iloc[window - 1 :] = scores
    return out


def _norm(s: pd.Series) -> pd.Series:
    s = s.dropna()
    s = s[s > 0]
    if s.index.tz is not None:
        s = s.copy()
        s.index = s.index.tz_localize(None)
    return s[~s.index.duplicated()]


def load_series(
    universe: set[str] | None = None, min_years: float = MIN_YEARS
) -> dict[str, pd.Series]:
    con = sqlite3.connect(f"file:{config.CACHE_DB}?mode=ro", uri=True)
    rows = con.execute("select ticker, payload from cache where kind='prices'").fetchall()
    out = {}
    for ticker, blob in rows:
        if ticker.startswith("^"):
            continue  # indices exclus : on teste des actions
        if universe is not None and ticker not in universe:
            continue
        try:
            ps = pickle.loads(blob)
        except Exception:
            continue
        s = getattr(ps, "adjusted", None)
        if s is None:
            continue
        s = _norm(s)
        if len(s) >= 252 * min_years:
            out[ticker] = s
    return out


def momentum_universe(series: dict[str, pd.Series], groups: dict[str, str]) -> None:
    """Rang 12-1 en coupe sur un univers FIXÉ à l'avance, par groupe de taille.

    Deux lectures : haut − bas (long-short, la mesure académique) et haut − moyenne
    de l'univers (la question d'un investisseur long-only : acheter les forts bat-il
    l'achat de tout ?). Le tiers haut est équipondéré, rebalancé chaque mois.
    """
    px = pd.DataFrame(series).sort_index()
    me = px.resample("ME").last()
    fwd = me.shift(-1) / me - 1.0
    mom = me.shift(1) / me.shift(12) - 1.0
    last = me.index[-1]
    stale = [t for t, s in series.items() if (last - s.index[-1]).days > 31]
    print(f"Dernier mois : {last:%Y-%m} ; séries arrêtées > 1 mois avant : {len(stale)}")

    def run(cols: list[str], min_n: int) -> dict[str, float]:
        ls, lo, turn, ns = [], [], [], []
        prev: set[str] = set()
        for d in me.index[:-1]:
            x, y = mom.loc[d, cols], fwd.loc[d, cols]
            m = x.notna() & y.notna()
            if m.sum() < min_n:
                prev = set()
                continue
            q = x[m].rank(pct=True)
            top = set(q[q > 2 / 3].index)
            ls.append(y[m][q > 2 / 3].mean() - y[m][q <= 1 / 3].mean())
            lo.append(y[m][q > 2 / 3].mean() - y[m].mean())
            if prev:
                turn.append(1 - len(top & prev) / len(top))
            prev = top
            ns.append(int(m.sum()))
        ls_a, lo_a = np.array(ls), np.array(lo)

        def t(a: np.ndarray) -> float:
            return a.mean() / (a.std(ddof=1) / np.sqrt(len(a)))

        # Frais : chaque titre renouvelé = une vente + un achat à 0,1 % l'ordre.
        cost = np.mean(turn) * 2 * FEE_PCT / 100 if turn else 0.0
        return {
            "mois": len(ls_a),
            "N médian": float(np.median(ns)) if ns else np.nan,
            "haut−bas %/an": ((1 + ls_a.mean()) ** 12 - 1) * 100,
            "t haut−bas": t(ls_a),
            "haut−moyenne %/an": ((1 + lo_a.mean()) ** 12 - 1) * 100,
            "t haut−moy.": t(lo_a),
            "haut−moy. net frais %/an": ((1 + lo_a.mean() - cost) ** 12 - 1) * 100,
            "rotation/mois %": np.mean(turn) * 100 if turn else np.nan,
            "mois haut>moy. %": (lo_a > 0).mean() * 100,
        }

    rows = []
    every = [t for t in series if t in groups]
    rows.append({"groupe": "Tout l'univers", **run(every, 30)})
    for g in sorted(set(groups.values())):
        cols = [t for t in every if groups[t] == g]
        rows.append({"groupe": g, **run(cols, 20)})
    # Moitié de l'historique chacune : l'effet tient-il sur les deux périodes ?
    print(pd.DataFrame(rows).round(2).to_string(index=False))
    mid = me.index[len(me.index) // 2]
    for label, sl in (("1re moitié", me.index <= mid), ("2de moitié", me.index > mid)):
        sub = me.index[sl]
        global_fwd, global_mom = fwd, mom
        fwd_s, mom_s = global_fwd.loc[sub], global_mom.loc[sub]
        ls = []
        for d in sub[:-1]:
            x, y = mom_s.loc[d, every], fwd_s.loc[d, every]
            m = x.notna() & y.notna()
            if m.sum() < 30:
                continue
            q = x[m].rank(pct=True)
            ls.append(y[m][q > 2 / 3].mean() - y[m].mean())
        a = np.array(ls)
        print(
            f"{label} ({sub[0]:%Y}-{sub[-1]:%Y}, {len(a)} mois) : haut−moyenne "
            f"{((1 + a.mean()) ** 12 - 1) * 100:.2f} %/an, t = {a.mean() / (a.std(ddof=1) / np.sqrt(len(a))):.2f}"
        )


def hysteresis(score: np.ndarray, low: float, high: float) -> np.ndarray:
    """Position décidée par le score de la VEILLE (pos[t] dépend de score[t-1])."""
    pos = np.zeros(len(score), dtype=bool)
    state = False
    for t in range(1, len(score)):
        x = score[t - 1]
        if np.isnan(x):
            state = False
        elif x > high:
            state = True
        elif x < low:
            state = False
        pos[t] = state
    return pos


def lagged(flag: np.ndarray, valid: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Décale d'une séance : la décision de t−1 s'applique en t."""
    pos = np.zeros_like(flag)
    ok = np.zeros_like(valid)
    pos[1:] = flag[:-1]
    ok[1:] = valid[:-1]
    return pos, ok


def signals(
    s: pd.Series, w: int = 250
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    p = s.to_numpy(dtype=float)
    sat = _satisfaction_series(s, window=w).reindex(s.index).to_numpy(dtype=float)
    lo = s.rolling(250).min().to_numpy()
    hi = s.rolling(250).max().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        st = (p - lo) / (hi - lo)
    ma = s.rolling(200).mean().to_numpy()
    mom = s.shift(21).to_numpy() / s.shift(252).to_numpy() - 1.0

    cv_pos = hysteresis(sat, LOW, HIGH)
    cv_ok = np.r_[False, ~np.isnan(sat[:-1])]
    return {
        "CV": (cv_pos, cv_ok),
        "STOCH": lagged(st > 0.5, ~np.isnan(st)),
        "MM200": lagged(p > ma, ~np.isnan(ma)),
        "MOM12-1": lagged(mom > 0, ~np.isnan(mom)),
    }


def evaluate(r: np.ndarray, pos: np.ndarray, ok: np.ndarray) -> dict[str, float]:
    """r[t] = rendement log de t−1 à t ; pos/ok indexés pareil."""
    pv, rv = pos[ok], r[ok]
    if pv.sum() < 50 or (~pv).sum() < 50:
        return {}
    diff = rv[pv].mean() - rv[~pv].mean()
    null = np.empty(N_PLACEBO)
    for i in range(N_PLACEBO):
        p2 = np.roll(pv, rng.integers(252, len(pv) - 252))
        null[i] = rv[p2].mean() - rv[~p2].mean()
    ann = np.sqrt(252)
    sh_in = rv[pv].mean() / rv[pv].std(ddof=1) * ann
    sh_out = rv[~pv].mean() / rv[~pv].std(ddof=1) * ann
    trades = int((pv[1:] & ~pv[:-1]).sum())
    strat = np.where(pv, rv, 0.0)
    strat_net = strat.copy()
    switches = np.r_[pv[0], pv[1:] != pv[:-1]]
    strat_net[switches] += np.log(1 - FEE_PCT / 100)
    years = len(rv) / 252
    return {
        "diff_bp": diff * 1e4,
        "p_placebo": float((np.abs(null) >= abs(diff)).mean()),
        "in_pct": pv.mean() * 100,
        "sh_in": sh_in,
        "sh_out": sh_out,
        "vol_in": rv[pv].std(ddof=1) * ann * 100,
        "vol_out": rv[~pv].std(ddof=1) * ann * 100,
        "trades": trades,
        "cagr_bh": (np.exp(rv.sum() / years) - 1) * 100,
        "cagr_strat": (np.exp(strat_net.sum() / years) - 1) * 100,
    }


def time_series_test(series: dict[str, pd.Series]) -> pd.DataFrame:
    rows = []
    for tk, s in series.items():
        p = s.to_numpy(dtype=float)
        r = np.r_[np.nan, np.log(p[1:] / p[:-1])]
        for name, (pos, ok) in signals(s).items():
            ok = ok & ~np.isnan(r)
            m = evaluate(r, pos, ok)
            if m:
                rows.append({"ticker": tk, "signal": name, "years": len(s) / 252, **m})
    return pd.DataFrame(rows)


def summarize_ts(df: pd.DataFrame) -> pd.DataFrame:
    df = df.assign(
        pos=(df.diff_bp > 0) * 100.0,
        sig_ok=((df.p_placebo < 0.05) & (df.diff_bp > 0)) * 100.0,
        sig_ko=((df.p_placebo < 0.05) & (df.diff_bp < 0)) * 100.0,
        beat=(df.cagr_strat > df.cagr_bh) * 100.0,
        excess=df.cagr_strat - df.cagr_bh,
    )
    g = df.groupby("signal")
    out = pd.DataFrame(
        {
            "n": g.size(),
            "in>out %": g.pos.mean(),
            "écart méd. pb/j": g.diff_bp.median(),
            "écart moy. pb/j": g.diff_bp.mean(),
            "signif. bon sens %": g.sig_ok.mean(),
            "signif. mauvais sens %": g.sig_ko.mean(),
            "Sharpe in méd.": g.sh_in.median(),
            "Sharpe out méd.": g.sh_out.median(),
            "vol in méd.": g.vol_in.median(),
            "vol out méd.": g.vol_out.median(),
            "% investi méd.": g.in_pct.median(),
            "trades méd.": g.trades.median(),
            "strat > B&H %": g.beat.mean(),
            "CAGR strat−B&H méd.": g.excess.median(),
        }
    )
    return out.round(2)


def sensitivity(series: dict[str, pd.Series]) -> pd.DataFrame:
    rows = []
    for w in (125, 250, 500):
        for low, high in ((0.35, 0.60), (0.30, 0.70), (0.50, 0.50), (0.40, 0.55)):
            res = []
            for s in series.values():
                p = s.to_numpy(dtype=float)
                r = np.r_[np.nan, np.log(p[1:] / p[:-1])]
                sat = _satisfaction_series(s, window=w).reindex(s.index).to_numpy(dtype=float)
                pos = hysteresis(sat, low, high)
                ok = np.r_[False, ~np.isnan(sat[:-1])] & ~np.isnan(r)
                pv, rv = pos[ok], r[ok]
                if pv.sum() < 50 or (~pv).sum() < 50:
                    continue
                res.append(rv[pv].mean() - rv[~pv].mean())
            res = np.array(res) * 1e4
            rows.append(
                {
                    "W": w,
                    "LOW": low,
                    "HIGH": high,
                    "n": len(res),
                    "in>out %": (res > 0).mean() * 100,
                    "écart méd. pb/j": np.median(res),
                }
            )
    return pd.DataFrame(rows).round(2)


def cross_section(series: dict[str, pd.Series]) -> pd.DataFrame:
    """Terciles mensuels : signal en fin de mois m, rendement du mois m+1."""
    px = pd.DataFrame(series).sort_index()
    month_end = px.resample("ME").last()
    fwd = month_end.shift(-1) / month_end - 1.0

    sig = {}
    sig["MOM12-1"] = month_end.shift(1) / month_end.shift(12) - 1.0
    daily = {}
    for tk, s in series.items():
        sat = _satisfaction_series(s)
        daily[tk] = sat
    sig["CV"] = pd.DataFrame(daily).sort_index().resample("ME").last()
    # Calcul par titre, sur SES séances : sur l'index joint (calendriers mêlés), les
    # trous de cotation font tomber les fenêtres glissantes sous leur minimum.
    st, gap = {}, {}
    for tk, s in series.items():
        st[tk] = (s - s.rolling(250).min()) / (s.rolling(250).max() - s.rolling(250).min())
        gap[tk] = s / s.rolling(200).mean() - 1
    sig["STOCH"] = pd.DataFrame(st).sort_index().resample("ME").last()
    sig["MM200 (écart)"] = pd.DataFrame(gap).sort_index().resample("ME").last()

    rows = []
    for name, sdf in sig.items():
        sdf = sdf.reindex(month_end.index)
        spreads = []
        for d in month_end.index[:-1]:
            x, y = sdf.loc[d], fwd.loc[d]
            m = x.notna() & y.notna()
            if m.sum() < 30:
                continue
            q = x[m].rank(pct=True)
            spreads.append(y[m][q > 2 / 3].mean() - y[m][q <= 1 / 3].mean())
        sp = np.array(spreads)
        t = sp.mean() / (sp.std(ddof=1) / np.sqrt(len(sp)))
        rows.append(
            {
                "signal": name,
                "mois": len(sp),
                "écart haut−bas %/mois": sp.mean() * 100,
                "t": t,
                "mois positifs %": (sp > 0).mean() * 100,
                "écart annualisé %": ((1 + sp.mean()) ** 12 - 1) * 100,
            }
        )
    return pd.DataFrame(rows).round(2)


def main() -> None:
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    if "--univers" in sys.argv:
        from univers_sbf120 import UNIVERS

        series = load_series(set(UNIVERS), min_years=2)
        print(f"Univers fixé : {len(series)} / {len(UNIVERS)} tickers avec ≥ 2 ans de cours\n")
        print("=== Rang 12-1 en coupe, terciles, mois suivant ===")
        momentum_universe(series, UNIVERS)
        return
    series = load_series()
    print(f"Univers : {len(series)} actions (série ajustée, >= {MIN_YEARS} ans)\n")

    ts = time_series_test(series)
    if len(sys.argv) > 1:
        ts.to_csv(sys.argv[1], index=False)
    print("=== 1. Série temporelle, titre par titre ===")
    print(summarize_ts(ts).to_string())

    print("\n=== 2. Sensibilité de la CV (W, bornes) ===")
    print(sensitivity(series).to_string(index=False))

    print("\n=== 3. Coupe transversale mensuelle (terciles, mois suivant) ===")
    print(cross_section(series).to_string(index=False))


if __name__ == "__main__":
    main()
