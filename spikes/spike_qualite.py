"""
Conception du score 'Qualité de l'exploitation' (raisonné, non issu d'Obole).
On le teste sur les 6 valeurs des fiches pour vérifier un classement sensé.

Ingrédients (données lues dans les PDF de référence) :
  - roe_moy   : ROE moyen sur la période
  - roe_last  : ROE dernière année (détecte les effondrements type STMicro/Renault)
  - ca_baisses: nb d'années de baisse du CA (régularité)
  - cp_bilan  : Capitaux propres / Total bilan en 2025 (solidité)
Note : BNP (banque) a un schéma différent -> traité à part (ROE/ROA), ici on met ses valeurs équivalentes.

Score 0-100, puis label.
"""

DATA = {
    # nom        roe_moy roe_last ca_baisses cp_bilan(%)   secteur
    "Pernod":   dict(roe_moy=9.8,  roe_last=10.7, ca_baisses=4, cp_bilan=41, fin=False),
    "Danone":   dict(roe_moy=11.2, roe_last=10.8, ca_baisses=6, cp_bilan=38, fin=False),
    "Total":    dict(roe_moy=10.3, roe_last=11.4, ca_baisses=6, cp_bilan=39, fin=False),
    "STMicro":  dict(roe_moy=13.8, roe_last=1.0,  ca_baisses=3, cp_bilan=72, fin=False),
    "Renault":  dict(roe_moy=-3.7, roe_last=-52.6,ca_baisses=4, cp_bilan=17, fin=False),
    "BNP":      dict(roe_moy=8.1,  roe_last=9.7,  ca_baisses=2, cp_bilan=4.5, fin=True),  # cp_bilan = actif net/actif (banque)
}


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def score_qualite(d):
    # 1) ROE moyen : 0 à 15%+ -> 0..40 pts
    s_roe = clamp(d["roe_moy"], 0, 15) / 15 * 40

    # 2) ROE dernière année (pénalise effondrement) : 0 à 15%+ -> 0..25 pts
    s_roe_last = clamp(d["roe_last"], 0, 15) / 15 * 25

    # 3) Régularité CA : 0 baisse=20pts, chaque année de baisse -2 (sur ~10 ans)
    s_reg = clamp(20 - d["ca_baisses"] * 2, 0, 20)

    # 4) Solidité bilan : seuil adapté banque vs industriel
    if d["fin"]:
        # banque : actif net/actif ~4-6% est normal -> on neutralise (15/15)
        s_bilan = 15
    else:
        # industriel : 40%+ = solide (15pts), 20% = limite, <15% = faible
        s_bilan = clamp((d["cp_bilan"] - 10) / 30 * 15, 0, 15)

    total = s_roe + s_roe_last + s_reg + s_bilan
    return round(total)


def label(score):
    if score < 35:  return "Médiocre"
    if score < 55:  return "Moyen"
    if score < 75:  return "Bon"
    return "Excellent"


print(f"{'Valeur':9} {'score':>5}  {'label':10}  détail")
print("-" * 55)
rows = []
for name, d in DATA.items():
    sc = score_qualite(d)
    rows.append((sc, name, d))
for sc, name, d in sorted(rows, reverse=True):
    print(f"{name:9} {sc:5}  {label(sc):10}  ROEmoy={d['roe_moy']:>5} ROElast={d['roe_last']:>6} baisses={d['ca_baisses']} bilan={d['cp_bilan']}")

print("\nClassement attendu (intuition) : Danone/Pernod/Total bons ; STMicro pénalisé (ROE s'effondre) ; Renault mauvais.")
