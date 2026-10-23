"""Compare notre écart-type (taille) vs celui des vraies fiches Obole.

Cibles lues dans les PDF du dossier exemple/. On teste plusieurs variantes
pour comprendre l'écart : Close vs Adj Close, quotidien vs hebdo, fenêtre.
"""
import numpy as np
import yfinance as yf

# (ticker, cible Obole %, with_dividends affiché dans l'URL du PDF)
CIBLES = {
    "RI.PA": (30.1, "RI.PA dividendes=true (Pernod)"),
    "TTE.PA": (18.7, "Total dividendes=false"),
    "BNP.PA": (41.2, "BNP dividendes=false"),
    "BN.PA": (15.8, "Danone dividendes=true"),
    "RNO.PA": (51.0, "Renault dividendes=true"),
    "STMPA.PA": (80.6, "STMicro dividendes=true"),
}


def ecart_type(series):
    s = series.dropna()
    s = s[s > 0]
    t0 = s.index[0]
    t = np.array([(d - t0).days / 365.25 for d in s.index])
    y = np.log(s.to_numpy())
    b, a = np.polyfit(t, y, 1)
    sigma = (y - (a + b * t)).std(ddof=1)
    return (np.exp(sigma) - 1) * 100  # « taille » Obole = e^sigma - 1


print(f"{'Ticker':10} {'cible':>6} | {'Close max':>9} {'Adj max':>9} {'Close hebdo':>11} {'Adj hebdo':>9}")
print("-" * 70)
for tk, (cible, desc) in CIBLES.items():
    h = yf.Ticker(tk).history(period="max", auto_adjust=False)
    if h.empty:
        print(f"{tk:10} -- pas de données")
        continue
    close = h["Close"]
    adj = h.get("Adj Close", close)
    cw = h["Close"].resample("W-FRI").last()
    aw = adj.resample("W-FRI").last()
    print(f"{tk:10} {cible:6.1f} | {ecart_type(close):9.1f} {ecart_type(adj):9.1f} "
          f"{ecart_type(cw):11.1f} {ecart_type(aw):9.1f}   ({desc})")
