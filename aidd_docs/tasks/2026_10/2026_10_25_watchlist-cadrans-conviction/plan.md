---
objective: "Quand la watchlist est ouverte, chaque valeur affiche son tier réel, la vue cadrans hiérarchise les convictions par tier, le jeu de comparaisons propose des tiers cohérents avec les choix, et le Pot. 5A d'une valeur avec prix juste enregistré vient de sa valorisation enregistrée, pas de la droite."
status: reviewed
---

# Plan: watchlist cadrans, jeu de convictions et Pot. 5A de valorisation

## Overview

| Field      | Value                                                                 |
| ---------- | --------------------------------------------------------------------- |
| **Goal**   | Rendre la watchlist visuelle par tiers, corriger l'affichage du tier, ajouter un jeu de convictions et sourcer le Pot. 5A sur la valorisation enregistrée. |
| **Source** | Demande utilisateur du 2026-10-25 + fiche `chantiers/26-watchlist-cadrans-conviction.md` |

## Phases

| #   | Phase                       | File                         |
| --- | --------------------------- | ---------------------------- |
| 1   | Affichage du tier           | [`phase-1.md`](./phase-1.md) |
| 2   | Pot. 5A de valorisation     | [`phase-2.md`](./phase-2.md) |
| 3   | Vue cadrans                 | [`phase-3.md`](./phase-3.md) |
| 4   | Jeu de convictions          | [`phase-4.md`](./phase-4.md) |
| 5   | Documentation et preuves    | [`phase-5.md`](./phase-5.md) |

## Decisions

| Decision | Why |
| --- | --- |
| Corriger le `<select>` de tier par `:selected` sur chaque option, en gardant `@change` | La base et l'API sont correctes (AMUN tier 2, filtre Tier 2) ; le `:value` du select est évalué avant les options `x-for`, Alpine retombe sur la première option. |
| Pot. 5A d'une valeur avec prix juste enregistré = rendement de la valorisation au cours actuel, dérivé du prix juste, de la cible et du dividende enregistrés | Fidèle à « l'estimation qu'on a faite » ; la cible et le prix juste encodent la projection, sans dépendre de la métrique courante. |
| Champ additif `pot_5y_source` (`valuation` / `regression`) et `pot_10y_source` ; pas de nouvelle table | La source est une propriété de la ligne ; le schéma reste en v8 et le prix juste reste lu, jamais dupliqué. |
| Vue cadrans par défaut, tableau en bascule ; cadrans SVG sans dépendance | La demande est une vue plus visuelle des tiers ; le tableau dense reste l'outil de tri et le repli accessible. |
| Jeu front-only, Elo avec priorité du tier actuel, minimum 12 comparaisons, effectifs actuels conservés, application par la route tier existante | Aucun schéma, aucune écriture MCP nouvelle ; le jeu propose, l'utilisateur applique. Conserver les effectifs évite d'inventer des seuils absolus de conviction. |
