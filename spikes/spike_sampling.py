"""
Jalon 0bis — Test de l'échantillonnage (quotidien vs hebdo vs mensuel)
pour resserrer écart-type (cible 30.1%) et perf passée (cible 8.5%) sur Pernod.

On teste chaque fréquence sur Close brut ET Adj Close, historique complet.
"""
import numpy as np
import yfinance as yf

TICKER = "RI.PA"

CIBLES = {"z": -3.81, "sigma": 30.1, "perf": 8.5, "p5": 32.6, "p10": 20.0}


def regression_log(dates, prices):
    t0 = dates[0]
    t = np.array([(d - t0).days / 365.25 for d in dates])
    y = np.log(prices)
    b, a = np.polyfit(t, y, 1)
    resid = y - (a + b * t)
    sigma = resid.std(ddof=1)
    return a, b, sigma, t


def metrics(dates, prices):
    a, b, sigma, t = regression_log(dates, prices)
    t_now, p_now = t[-1], prices[-1]
    perf = np.exp(b) - 1
    et = np.exp(sigma) - 1
    z = (np.log(p_now) - (a + b * t_now)) / sigma
    def pot(H):
        return (np.exp(a + b * (t_now + H)) / p_now) ** (1 / H) - 1
    return perf, et, z, pot(5), pot(10)


def row(label, df, col):
    s = df[col].dropna()
    s = s[s > 0]
    perf, et, z, p5, p10 = metrics(s.index.to_pydatetime(), s.values)
    print(f"{label:38s} | perf {perf*100:5.2f}% | σ {et*100:5.2f}% | z {z:6.2f} | "
          f"5a {p5*100:5.2f}% | 10a {p10*100:5.2f}% | n={len(s)}")


tk = yf.Ticker(TICKER)
hist = tk.history(period="max", auto_adjust=False)
print(f"Cibles PDF                             | perf  8.50% | σ 30.10% | z  -3.81 | 5a 32.60% | 10a 20.00%")
print("-" * 110)

for col in ["Close", "Adj Close"]:
    daily = hist[[col]]
    weekly = hist[[col]].resample("W-FRI").last()
    monthly = hist[[col]].resample("ME").last()
    print(f"--- {col} ---")
    row(f"  quotidien", daily, col)
    row(f"  hebdo (vendredi)", weekly, col)
    row(f"  mensuel (fin de mois)", monthly, col)
