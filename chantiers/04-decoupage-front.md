# #04 — Découpage du front (modules ES natifs)

> **Statut :** fait · **Priorité :** 🟡 Q2 (important, non urgent — cas (c) évolutivité)
> **Impact Pernod :** 🟠 · **Branche (mergée) :** `refactor/front-modules` · **Taille :** ~2-3 sessions

---

## 1. Contexte

`src/obole/web/app.js` fait **2110 lignes** et contient un unique objet Alpine `obole()` avec
**~80 méthodes** couvrant des domaines sans rapport : recherche (`onSearchInput`, `pick`), graphe
(`drawChart`, `drawMinis`, `olsLog`), screener (`_buildFilters`, `toggleSortHeader`), indices
(`openIndex`, `addMember`), événements (`openEvents`, `_eventRef`), export (`doExport`,
`_downloadCsv`), import CSV (`onFileSelect`). `index.html` fait 731 lignes.

Les tests front (ajoutés récemment, `cd web-tests && npm test`) couvrent les **fonctions pures** (`olsLog`, `classify`,
`scored`, `computeLive`) — mais **aucune méthode d'orchestration** n'est testable isolément : elles
sont soudées au DOM et à l'état global de l'objet.

## 2. Objectif

Pouvoir modifier une partie du front (ex. le screener) sans risquer de casser une autre (ex. le
graphe), et tester unitairement chaque domaine isolément.

## 3. Non-objectifs

- **Pas de bundler** (Vite, Webpack, esbuild) : l'invariant « front sans build » est non négociable.
- Pas de framework (Svelte, React) : Alpine reste.
- Pas de réécriture : on **déplace** du code, on ne le réécrit pas.

## 4. Exigences

- 4.1 Découper `app.js` en modules ES natifs (`<script type="module">`, servi tel quel par le
  navigateur) : `charts.js`, `screener.js`, `indices.js`, `events.js`, `export.js`, `api.js`.
- 4.2 `api.js` centralise **tous** les `fetch` (aujourd'hui dispersés dans les ~80 méthodes).
- 4.3 `app.js` ne contient plus que le composant Alpine qui assemble ces modules.
- 4.4 Le comportement est **strictement identique** : aucune régression fonctionnelle visible.
- 4.5 Chaque module découpé gagne des tests unitaires dédiés.

## 5. Critères d'acceptation

- [x] `app.js` < 500 lignes (composant Alpine seul) — 163 l.
- [x] Aucun `fetch` en dehors de `api.js` (vérifié par `modules.test.js`)
- [x] Aucun bundler ajouté ; `index.html` charge des `<script type="module">` locaux
- [x] Les tests front existants restent verts (davantage de tests après découpage)
- [x] Le smoke e2e (Chromium + WebKit) reste vert
- [x] Vérification manuelle : chaque modale (Screener, Indices, Événements, Export, Paramètres) fonctionne (e2e)
- [x] Chaque nouveau module a au moins un test unitaire (`modules.test.js`)

## 6. Invariants préservés

- La calibration Pernod (`z = −3.81`, ±0.15) reste verte.
- **`olsLog` calcule exactement comme avant** : `regression-parity.test.js` vert.
- Aucune dépendance CDN réintroduite (tout reste vendorisé, cf. `web/vendor/`).
- Le front reste fonctionnel **sans build** et **hors ligne**.

## 7. Jalons

- **J1** — `api.js` (fetch centralisés) + `thresholds.js`/`theme.js`/`util.js` (briques partagées).
- **J2** — `search.js` + `screener.js` + `indices.js`.
- **J3** — `charts.js` + `exportcsv.js` + `events.js` + `settings.js` + `app.js` réduit au composant.
- **J4** — Tests (`modules.test.js`) + vérification e2e complète.

## 8. Note de reprise

**Fait.** `app.js` (2479 → **163 l.**) réduit au composant Alpine qui assemble 7 mixins ES :
`search.js` (110 l.), `screener.js` (531), `indices.js` (243), `charts.js` (775), `exportcsv.js`
(330), `events.js` (134), `settings.js` (154). Briques partagées : `api.js` (fetch, 129 l.),
`thresholds.js` (maths + seuils /api/meta, 116), `theme.js`, `util.js`. `index.html` charge
`app.js` en `type="module"`. Tests front verts (dont `modules.test.js`), e2e verts,
suite backend verte (`pytest -m "not network" -q`), `ruff`/`mypy` verts. Déplacement **verbatim**
(aucune réécriture de logique) : seule adaptation = `fetch` → `api.*`. Reste : commit + merge
`--no-ff`.
