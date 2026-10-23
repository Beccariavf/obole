"""
Calibration de la TENDANCE BOURSIÈRE via MM200 et MM11.
Labels réels observés dans les fiches Obole (24/06/2026) :
  TotalEnergies = Haussière | BNP = Haussière | STMicro = Haussière
  Danone = Baissière | Renault = Baissière | (Pernod : non lu, baissière attendue)
On teste : Haussière si MM11 > MM200, sinon Baissière.
"""
import yfinance as yf

CIBLES = {
    "TTE.PA": "Haussière",   # TotalEnergies
    "BNP.PA": "Haussière",   # BNP Paribas
    "STMPA.PA": "Haussière", # STMicro (Euronext Paris)
    "BN.PA": "Baissière",    # Danone
    "RNO.PA": "Baissière",   # Renault
    "RI.PA": None,           # Pernod (pas de label lu, info)
}


def tendance(ticker):
    h = yf.Ticker(ticker).history(period="2y", auto_adjust=False)
    if h.empty:
        return None, None, None
    close = h["Close"].dropna()
    mm11 = close.rolling(11).mean().iloc[-1]
    mm200 = close.rolling(200).mean().iloc[-1]
    label = "Haussière" if mm11 > mm200 else "Baissière"
    return label, mm11, mm200


print(f"{'Ticker':10} {'calculé':10} {'attendu':10} {'MM11':>8} {'MM200':>8}  match")
print("-" * 60)
for tk, cible in CIBLES.items():
    lab, mm11, mm200 = tendance(tk)
    if lab is None:
        print(f"{tk:10} -- pas de données (ticker à corriger ?)")
        continue
    match = "" if cible is None else ("OK" if lab == cible else "XX <<<")
    cib = cible or "(info)"
    print(f"{tk:10} {lab:10} {cib:10} {mm11:8.2f} {mm200:8.2f}  {match}")
