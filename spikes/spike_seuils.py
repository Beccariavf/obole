"""
Inférence des seuils de labels Obole à partir de 6 fiches réelles.
On définit des seuils candidats puis on vérifie qu'ils classent correctement les 6 observations.
"""

# (valeur, label observé) extraits des PDF
DISTANCE_SIGMA = [
    (-3.81, "Décotée"),
    (-0.96, "Légèrement sous-cotée"),
    (-0.17, "Légèrement sous-cotée"),
    (1.02, "Surcotée"),
    (1.38, "Surcotée"),
    (1.79, "Surcotée"),
]
ECART_TYPE = [
    (15.8, "Faible"), (18.7, "Faible"), (30.1, "Moyen"),
    (41.2, "Plutôt élevée"), (51.0, "Plutôt élevée"), (80.6, "Elevée"),
]
PERF = [
    (1.2, "Médiocre"), (1.9, "Médiocre"), (3.0, "Médiocre"),
    (5.7, "Moyen"), (8.5, "Moyen"), (8.9, "Moyen"),
]
POTENTIEL = [
    (-7.5, "Mauvais"), (-4.8, "Mauvais"), (-4.0, "Mauvais"),
    (-1.9, "Mauvais"), (-0.5, "Mauvais"), (0.4, "Médiocre"),
    (5.9, "Moyen"), (6.0, "Moyen"), (6.2, "Moyen"),
    (10.3, "Bien"), (20.0, "Excellent"), (32.6, "Excellent"),
]


def label_distance(z):
    if z <= -2: return "Décotée"
    if z <= -1: return "Sous-cotée"          # hypothèse (pas d'observation entre -2 et -1)
    if z < 0:   return "Légèrement sous-cotée"
    if z < 0.5: return "Légèrement surcotée"  # hypothèse
    return "Surcotée"

def label_ecart_type(s):
    if s < 20: return "Faible"
    if s < 35: return "Moyen"
    if s < 55: return "Plutôt élevée"   # NB Renault 51 = Plutôt élevée, STMicro 80.6 = Elevée
    return "Elevée"

def label_perf(p):
    if p < 4:  return "Médiocre"
    if p < 10: return "Moyen"           # borne haute inconnue (pas d'obs >8.9)
    return "Bien"                        # hypothèse

def label_potentiel(p):
    if p < 0:   return "Mauvais"
    if p < 5:   return "Médiocre"        # 0.4 = Médiocre
    if p < 10:  return "Moyen"           # 5.9/6.0/6.2 = Moyen
    if p < 15:  return "Bien"            # 10.3 = Bien
    return "Excellent"                   # 20/32.6 = Excellent


def check(name, data, fn):
    print(f"=== {name} ===")
    ok = True
    for v, expected in data:
        got = fn(v)
        flag = "OK " if got == expected else "XX "
        if got != expected: ok = False
        print(f"  {flag} {v:>7} -> attendu '{expected}' | calculé '{got}'")
    print(f"  => {'TOUT BON' if ok else 'INCOHÉRENCES'}\n")

check("Distance sigma", DISTANCE_SIGMA, label_distance)
check("Ecart-type", ECART_TYPE, label_ecart_type)
check("Performance passee", PERF, label_perf)
check("Potentiel", POTENTIEL, label_potentiel)
