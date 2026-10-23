# #17.2 — Portefeuille · Positions

> **Statut :** à faire · **Priorité :** 🟡 Q2 · **Impact Pernod :** 🟢
> **Branche :** `feat/portefeuille` · **Taille :** ~1 session
> **Fiche parente :** #17 · **Précédent :** `01-resume.md` · **Suivant :** `03-risque.md`

---

## 1. Contexte

La section `Positions` répond à « comment est composé mon portefeuille ? ». Elle doit montrer
chaque ligne avec sa taille et ses caractéristiques, puis une lecture **consolidée** — « comme si
mon portefeuille était une grosse entreprise ».

Dépend du jalon `00` (transactions) ; réutilise les prix de `data/yahoo` (déjà en cache).

## 2. Objectif

Voir le tableau complet des positions (quantité, PRU, dernier cours, +/- value latente et
réalisée, poids, secteur) **et** les agrégats consolidés du portefeuille (capi pondérée, PER
moyen, rendement, secteur dominant) pour le lire comme une entreprise unique.

## 3. Non-objectifs

- Pas de drawdown ni de corrélation (jalon `03-risque`).
- Pas de rendements mensuels (jalon `04-performance`).
- Pas de yield-on-cost détaillé (jalon `05-dividendes`).
- Pas de rééquilibrage / poids cibles.

## 4. Exigences

- 4.1 `engine/portfolio.py::positions_metrics(positions, prices)` : PRU, valeur, +/- value
  latente/réalisée, poids — **pur**.
- 4.2 Agrégats consolidés (pondérés par la valeur) : capitalisation, PER, rendement du dividende,
  répartition sectorielle, nombre de lignes.
- 4.3 `services/portfolio.py::positions(account_id)` enrichit avec les fondamentaux déjà exposés
  par `services/analysis` (aucune formule dupliquée).
- 4.4 Front : tableau triable (patron `screen-table` du screener) + camembert/donut de
  répartition (comptes ou secteurs, cf. capture Baggr).
- 4.5 Couleurs sémantiques projet (bleu = bien, rouge = mal) ; **rachats toujours en bleu** si
  une notion de rachat apparaît.
- 4.6 Valeurs absentes → « -- », jamais 0.

## 5. Critères d'acceptation

- [ ] `positions_metrics` testé : achat unique, achats multiples (PRU pondéré), vente partielle
      (plus-value réalisée), position soldée
- [ ] Poids = valeur ligne / valeur totale ; somme des poids ≈ 100 %
- [ ] Agrégats consolidés pondérés corrects (test sur fixture à 2-3 lignes)
- [ ] Tableau triable ; donut de répartition rendu
- [ ] Chaque ligne ouvre la fiche entreprise existante
- [ ] Valeur non calculable affichée « -- »
- [ ] Suite hors réseau verte

## 6. Invariants préservés

- Calibration Pernod (`z = −3.81`) inchangée.
- `engine/portfolio.py` reste pur ; aucune formule de `engine/` dupliquée.
- Les fondamentaux (PER, capi…) viennent de `services/analysis`, pas d'un recalcul parallèle.
- Aucun seuil littéral côté JS.

## 7. Jalons

- **J2.1** — `positions_metrics` + tests.
- **J2.2** — Agrégats consolidés + route + `serialize`.
- **J2.3** — Tableau + donut (front).

## 8. Note de reprise

_(vide — jalon non commencé)_
