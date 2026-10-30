# Retrait — la carte du rendement conditionnel

La phase 2 (carte « Ce qui a suivi le score ») a été retirée le 2026-10-30,
après usage réel sur la fiche. Le percentile de la phase 1 est conservé.

## Pourquoi

- **Aucune décision.** La carte décrivait ce qui avait suivi des niveaux passés ;
  elle ne changeait rien au moment d'ouvrir une fiche.
- **Des chiffres qui ne se distinguent pas.** Médianes 10,3 / 10,4 / 8,6 % pour
  une dispersion de ±30 % : quatre lignes pour dire « le bas a été mauvais ».
- **Doublon.** La table de fiabilité compare déjà les deux régimes du signal.
- **Trop lourde.** Il fallait une info-bulle de 45 mots pour la lire, ce qui est
  le signe qu'elle n'avait pas sa place sur un écran de diagnostic.

## Ce qui a été retiré

La carte et son info-bulle, les champs `conditional_raw`/`conditional_adj` du
payload, `conditional_forward_returns` du moteur, les constantes
`MOMENTUM_FORWARD_SESSIONS` et `MOMENTUM_CONDITIONAL_MIN_EPISODES`, et leurs
tests (backend, front, e2e). La clé de cache passe à `lecture3`.

## Ce qui reste

Le rang du score dans l'histoire du titre (`score_percentile`), sa date de
départ brute et ajustée, et la ligne sous la jauge.
