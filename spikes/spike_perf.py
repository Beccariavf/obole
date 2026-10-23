"""
Investigation : pourquoi la perf passée Obole = 8.5% alors que ma pente Close = 6.78% ?
On regarde les bornes réelles et plusieurs définitions de "performance passée".
"""
import numpy as np
import yfinance as yf

tk = yf.Ticker("RI.PA")
hist = tk.history(period="max", auto_adjust=False)

c = hist["Close"].dropna()
ac = hist["Adj Close"].dropna()
d0, d1 = c.index[0], c.index[-1]
yrs = (d1 - d0).days / 365.25

print(f"Période : {d0.date()} -> {d1.date()}  ({yrs:.2f} ans)")
print(f"Close      début {c.iloc[0]:7.2f}  fin {c.iloc[-1]:7.2f}")
print(f"Adj Close  début {ac.iloc[0]:7.2f}  fin {ac.iloc[-1]:7.2f}")
print()

def cagr(s):
    return (s.iloc[-1] / s.iloc[0]) ** (1 / yrs) - 1

def slope(s):
    t = np.array([(d - s.index[0]).days / 365.25 for d in s.index])
    b, a = np.polyfit(t, np.log(s.values), 1)
    return np.exp(b) - 1

print("CAGR point-à-point (début->fin) :")
print(f"  Close     : {cagr(c)*100:5.2f}%")
print(f"  Adj Close : {cagr(ac)*100:5.2f}%")
print()
print("Pente de régression (perf moyenne lissée) :")
print(f"  Close     : {slope(c)*100:5.2f}%")
print(f"  Adj Close : {slope(ac)*100:5.2f}%   <-- cible Obole ~8.5%")
print()

# Et si on régresse depuis 2003 (la borne affichée dans le PDF) ?
ac03 = ac[ac.index >= "2003-01-03"]
c03 = c[c.index >= "2003-01-03"]
print("Depuis 2003-01-03 :")
print(f"  pente Close     : {slope(c03)*100:5.2f}%")
print(f"  pente Adj Close : {slope(ac03)*100:5.2f}%")
