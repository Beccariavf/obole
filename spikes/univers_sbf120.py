"""Univers explicite du test momentum : CAC 40 puis le reste du SBF 120 (et quelques
valeurs moyennes liquides). Composition ACTUELLE (biais de survie assumé), tickers
Yahoo. Un ticker qui ne répond pas est simplement écarté par le spike.

Le premier test prenait tout le cache, ETF, devises et crypto compris : cette liste
fixe l'univers à l'avance, ce qui évite de choisir l'échantillon après coup.
"""

CAC40 = [
    "AC.PA", "AI.PA", "AIR.PA", "MT.AS", "CS.PA", "BNP.PA", "EN.PA", "BVI.PA",
    "CAP.PA", "CA.PA", "ACA.PA", "BN.PA", "DSY.PA", "EDEN.PA", "ENGI.PA", "EL.PA",
    "ERF.PA", "RMS.PA", "KER.PA", "LR.PA", "OR.PA", "MC.PA", "ML.PA", "ORA.PA",
    "RI.PA", "PUB.PA", "RNO.PA", "SAF.PA", "SGO.PA", "SAN.PA", "SU.PA", "GLE.PA",
    "STLAP.PA", "STMPA.PA", "TEP.PA", "HO.PA", "TTE.PA", "URW.PA", "VIE.PA", "DG.PA",
]  # fmt: skip

SBF120_HORS_CAC = [
    "ADP.PA", "AF.PA", "AKE.PA", "ALO.PA", "AMUN.PA", "ARG.PA", "ATE.PA", "AYV.PA",
    "BB.PA", "BEN.PA", "BIM.PA", "BOL.PA", "CARM.PA", "COFA.PA", "COV.PA", "DBG.PA",
    "DIM.PA", "ELIS.PA", "ENX.PA", "ERA.PA", "ETL.PA", "EXENS.PA", "FDJU.PA",
    "FGR.PA", "FR.PA", "FRVIA.PA", "GET.PA", "GFC.PA", "GTT.PA", "ICAD.PA", "IPN.PA",
    "IPS.PA", "ITP.PA", "LI.PA", "MERY.PA", "MF.PA", "MMB.PA", "MMT.PA", "NEX.PA",
    "NK.PA", "ODET.PA", "OPM.PA", "OVH.PA", "PLNW.PA", "RBT.PA", "RCO.PA", "RF.PA",
    "RUI.PA", "RXL.PA", "SCR.PA", "SESG.PA", "SK.PA", "SOI.PA", "SOP.PA", "SPIE.PA",
    "SW.PA", "TE.PA", "TFI.PA", "TRI.PA", "UBI.PA", "VCT.PA", "VIRP.PA", "VIV.PA",
    "VK.PA", "VLA.PA", "VU.PA", "WLN.PA", "ALTA.PA", "AM.PA", "CLARI.PA", "ELIOR.PA",
    "EXA.PA", "FII.PA", "IDL.PA", "LSS.PA", "MRN.PA", "NXI.PA", "QDT.PA", "TKO.PA",
    "VIRI.PA", "KOF.PA", "NRO.PA", "BOI.PA", "SII.PA", "GBT.PA", "LTA.PA", "MAU.PA",
    "FNAC.PA", "ABVX.PA", "BAIN.PA", "EMEIS.PA", "CO.PA", "DEC.PA",
]  # fmt: skip

UNIVERS = {**{t: "CAC 40" for t in CAC40}, **{t: "SBF 120 hors CAC" for t in SBF120_HORS_CAC}}
