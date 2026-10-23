"""
Jalon 0 — Spike de calibration de la « droite d'Obole » sur Pernod Ricard.

Cibles du PDF référence (22/06/2026, cours 64.14 EUR) :
  - Distance en écart-type :        -3.81  (« Décotée »)
  - Écart-type (taille) :            30.1% (« Moyen »)
  - Performance passée (pente) :      8.5% (« Moyen »)
  - Potentiel annuel à 5 ans :       32.6% (« Excellent »)
  - Potentiel annuel à 10 ans :      20.0% (« Excellent »)
  - Période graphe : 03/01/2003 -> 19/06/2026
  - droite d'Obole (valeurs lues sur l'axe) : ~64.14 actuel, projections 174.57 / 295.11 ...

But : retrouver ces chiffres pour valider/ajuster les formules du PRD §5.
On teste plusieurs variantes (avec/sans dividendes, période complète vs 2003+).
"""
import numpy as np
import pandas as pd
import yfinance as yf

TICKER = "RI.PA"  # Pernod Ricard, Euronext Paris


def regression_log(dates, prices):
    """Régression OLS de ln(prix) sur le temps en années. Retourne a, b, sigma, t."""
    t0 = dates[0]
    t = np.array([(d - t0).days / 365.25 for d in dates])
    y = np.log(prices)
    b, a = np.polyfit(t, y, 1)  # pente, intercept
    resid = y - (a + b * t)
    sigma = resid.std(ddof=1)
    return a, b, sigma, t


def analyze(label, df, price_col):
    dates = df.index.to_pydatetime()
    prices = df[price_col].values
    mask = prices > 0
    dates, prices = dates[mask], prices[mask]

    a, b, sigma, t = regression_log(dates, prices)
    t_now = t[-1]
    p_now = prices[-1]

    perf_annuelle = np.exp(b) - 1
    ecart_type_taille = np.exp(sigma) - 1

    fitted_now = np.exp(a + b * t_now)
    resid_now = np.log(p_now) - (a + b * t_now)
    z = resid_now / sigma

    def potentiel(H):
        cible = np.exp(a + b * (t_now + H))  # point sur la droite à horizon H
        return (cible / p_now) ** (1 / H) - 1

    print(f"\n===== {label} =====")
    print(f"  Période réelle      : {dates[0].date()} -> {dates[-1].date()}  ({len(prices)} pts)")
    print(f"  Cours actuel        : {p_now:.2f}")
    print(f"  Droite à aujourd'hui: {fitted_now:.2f}")
    print(f"  Pente b (perf/an)   : {perf_annuelle*100:6.2f}%   [cible PDF: 8.5%]")
    print(f"  Écart-type (taille) : {ecart_type_taille*100:6.2f}%   [cible PDF: 30.1%]")
    print(f"  Distance en σ (z)   : {z:6.2f}    [cible PDF: -3.81]")
    print(f"  Potentiel 5 ans     : {potentiel(5)*100:6.2f}%   [cible PDF: 32.6%]")
    print(f"  Potentiel 10 ans    : {potentiel(10)*100:6.2f}%   [cible PDF: 20.0%]")


print("Téléchargement", TICKER, "...")
tk = yf.Ticker(TICKER)

# auto_adjust=False -> on a 'Close' (brut) ET 'Adj Close' (div+splits réinvestis)
hist = tk.history(period="max", auto_adjust=False)
print("Historique complet :", hist.index[0].date(), "->", hist.index[-1].date(), len(hist), "lignes")
print("Colonnes:", list(hist.columns))

# Variante 1 : historique complet, prix brut
analyze("V1 — historique complet, Close brut", hist, "Close")

# Variante 2 : historique complet, dividendes réinvestis (Adj Close)
analyze("V2 — historique complet, Adj Close (div réinvestis)", hist, "Adj Close")

# Variante 3 : période 2003+ (comme le graphe du PDF), Close brut
h2003 = hist[hist.index >= "2003-01-03"]
analyze("V3 — depuis 2003-01-03, Close brut", h2003, "Close")

# Variante 4 : période 2003+, Adj Close
analyze("V4 — depuis 2003-01-03, Adj Close (div réinvestis)", h2003, "Adj Close")
