---
objective: "La fiche expose un onglet Momentum qui note la satisfaction de la foule (250 entrées glissantes) et colore l'historique du cours par régime, sans jamais lire une séance future."
status: implemented
---

# Plan: La Clara Vallis — onglet Momentum

## Overview

| Field      | Value                                                                                              |
| ---------- | -------------------------------------------------------------------------------------------------- |
| **Goal**   | Moteur de satisfaction, payload caché, onglet Momentum (table, jauge, un an, historique walk-forward). |
| **Source** | `chantiers/30-clara-vallis.md` (spec) + brainstorm validé du 2026-10-29                            |

## Phases

| #   | Phase                      | File                         |
| --- | -------------------------- | ---------------------------- |
| 1   | Moteur de la Clara Vallis  | [`phase-1.md`](./phase-1.md) |
| 2   | Payload et cache           | [`phase-2.md`](./phase-2.md) |
| 3   | Seuils et calibration      | [`phase-3.md`](./phase-3.md) |
| 4   | Onglet et table            | [`phase-4.md`](./phase-4.md) |
| 5   | Les trois blocs            | [`phase-5.md`](./phase-5.md) |
| 6   | Finitions et documentation | [`phase-6.md`](./phase-6.md) |

## Resources

| Source                                                                                | Verified                                                                                                                                                                            |
| ------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [Psychologie des marchés — la stratégie du maçon](https://www.youtube.com/watch?v=F0IwyPj49oU) | La bulle se place entre le creux et le sommet parcourus depuis l'entrée ; l'agrégat sur une foule entrée à des dates différentes donne la satisfaction collective ; l'insatisfaction signale le danger. |
| CAC 40 (`^FCHI`), clôtures quotidiennes 2000 → 2023 (Yahoo Finance) | Mesures de calibration au 2026-10-29 : crises 0,174 (2008) · 0,239 (2011) · 0,255 (2020) · 0,174 (2002) ; calmes 0,762 (2017) · 0,859 (2021) · 0,704 (2023) ; 2015 (0,515) reste dans la bande neutre. Bornes retenues : 0,35 et 0,60. |

## Decisions

| Decision                                                              | Why                                                                                                                                  |
| --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| Score = moyenne des 250 bulles, fenêtre glissante de 250 séances      | Formulation retenue au brainstorm ; 250 séances ≈ un an de bourse, sans trou de calendrier.                                          |
| Walk-forward vectorisé, mesuré et découpé en blocs de 2 000 dates     | Mesuré à 10,6 ms (5 000 séances), 17,8 ms (8 000) et 24,9 ms (12 000) par série ; le découpage borne la mémoire sur les indices très longs. |
| Walk-forward précalculé serveur et caché (kind `momentum`)            | Deux séries recalculées à chaque rendu côté navigateur coûteraient plus que le calcul serveur une fois par jour.                     |
| La table « monde de Markovitz » est calculée côté client              | Même mécanisme que le graphe héro (`olsLog`) : σ, z, pente et confiance suivent le sélecteur de durée sans aller-retour réseau.       |
| Plage dédiée `momStart`/`momEnd`                                      | `rangeStart`/`rangeEnd` est partagée entre le héro et la modale ; la réutiliser ferait bouger le graphe du Résumé.                    |
| Prix bruts par défaut, ajustés au toggle                              | Le maçon regarde le cours coté ; le total-return reste disponible pour les titres à gros dividende.                                  |
| Seuils dans `config.py`, exposés par `/api/meta`                      | Règle du projet : aucun seuil littéral côté JS.                                                                                      |
| Calibration sur une série CAC 40 figée (2000 → 2023)                  | Le test devient pur et reproductible : plus de dépendance réseau, plus de dérive au fil des séances.                                |
| Pas de colonne « verdict » dans la table                              | Le seul verdict gaz/liquide est la jauge ; la table porte la confiance `1 − R²` en clair, sans second vocabulaire concurrent.         |
