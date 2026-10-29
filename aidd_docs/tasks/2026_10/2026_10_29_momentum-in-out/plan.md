---
objective: "La table de fiabilité compare le marché pendant les séances in et out, avec buy & hold comme repère, et la polarité de la colonne out est inversée."
status: implemented
---

# Plan: Fiabilité, seconde lecture — in contre out

## Overview

| Field      | Value                                                                                             |
| ---------- | ------------------------------------------------------------------------------------------------- |
| **Goal**   | Deux colonnes in/out à la place de la stratégie, buy & hold en repère, polarité inversée sur out.  |
| **Source** | `chantiers/32-momentum-in-out.md` + brainstorm validé du 2026-10-29                                |

## Phases

| #   | Phase             | File                         |
| --- | ----------------- | ---------------------------- |
| 1   | Moteur in/out     | [`phase-1.md`](./phase-1.md) |
| 2   | Service et route  | [`phase-2.md`](./phase-2.md) |
| 3   | Table à trois colonnes | [`phase-3.md`](./phase-3.md) |
| 4   | Finitions et doc  | [`phase-4.md`](./phase-4.md) |

## Decisions

| Decision                                                              | Why                                                                                                                                  |
| --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| Deux séries conditionnelles (non affichées), par panier in/out        | La stratégie n'est investie qu'une partie du temps : comparer son rendement total au buy & hold est biaisé. Le signal se juge sur la séparation in/out. |
| CAGR annualisé sur les séances du panier (`n/252`)                    | C'est le rythme du signal, pas le temps qui passe : un panier de 1 800 séances sur 11 ans se lit sur 7 ans de marché.               |
| Buy & hold gardé comme repère, pas comme comparaison                  | Le lecteur a besoin du niveau du marché sur la période ; la comparaison, elle, se fait entre in et out.                              |
| Polarité inversée pour la colonne out                                 | Gagner quand on est dehors est un mauvais signe : le positif doit s'y lire en rouge, sinon la table ment sur ce qu'elle mesure.       |
| Pas de badge de verdict                                               | Les deux colonnes suffisent ; un verdict automatique figerait une lecture que les chiffres disent mieux.                              |
| Les courbes in/out sont non contiguës, et la légende le dit            | Leur max drawdown mesure la pire série de pertes du panier, pas un creux de portefeuille : une métrique conditionnelle, pas un vécu.  |
| Le nombre de trades et le rendement de la stratégie en pied           | Le rendement réel (cash compris) reste visible sans redevenir une colonne de comparaison.                                            |
| Max drawdown et Calmar des paniers gardés, avec la mention            | Le drawdown d'un panier est conditionnel (pire série de pertes du panier, pas un creux vécu) ; la légende le dit.                    |
