# Review: cadrans compacts (option A)

- Rounds: 1
- Started: 2026-10-25

## Round 1 · r-2b7c

- Date: 2026-10-25
- By: Beccariavf
- Diff: `main...feat/watchlist-cadrans-compact` (plus l'arbre de travail, `review.md` exclu)
- Axes: code, functional, relevancy
- Verdict: approve
- Score: 5/5 met, 0 unmet, 0 unverified at runtime, 0 out of the diff

### Criteria

- [x] Carte ≤ 130 px et tête de tier ≤ 50 px — mesures réelles : carte **118 px**, tête **41 px** (avant 209/86), `captures/cadrans-apres.png`
- [x] La carte montre toutes les informations et le tier réel (AMUN Tier 2) — run réel, e2e cadrans, `captures/cadrans-apres.png`
- [x] « Voir » ouvre la fiche, ✕ retire, erreur/vide conservés — e2e « vue cadrans… », Voir + dialog/DELETE interceptés
- [x] A11y : ✕ nommé, sections titrées, focus visible, 3 arrêts, cibles 24 px, contrastes, reduced motion — code + e2e (h4, aria-label, hauteurs), `captures/cadrans-390.png`
- [x] E2E Chromium + WebKit, suites front/backend, aucun schéma — runs sur la tête : pytest 1266 + réseau 5, ruff/mypy, Vitest 614, Playwright 120 ; 390 px carte 135 sans débordement

### Findings

- `src/obole/web/index.html` : le nom de la carte n'est plus un bouton ; « Voir » est la seule ouverture. C'est le choix a11y du plan (3 arrêts/carte), mais un clic sur le nom ne fait plus rien → conserver le `title` (fait) et vérifier que « Voir » reste l'affordance évidente — 🟢 minor, frontend
