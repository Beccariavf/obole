# #23 — Import CSV robuste + staging piloté par l'IA

> **Statut :** fait · **Priorité :** 🟡 Q2 · **Impact Pernod :** 🟢
> **Branche :** `feat/import-csv-ia` · **Taille :** ~2 sessions
> **Fiche parente :** — (prolonge #22)

---

## 1. Contexte

Le « document financier CSV » (#22) exporte et importe toutes les métriques du
tableau des comptes. Mais **réimporter** un CSV corrigé échouait souvent sans
explication :

- `src/obole/data/manual.py::import_csv` utilisait `csv.DictReader` avec le
  **délimiteur virgule figé** et `float()` brut. Mesuré :

  | CSV fourni | Résultat |
  |---|---|
  | `year,CA` / `2015,1000` | ✅ OK |
  | Excel FR `year;CA` | ❌ `[]` (délimiteur `;` non reconnu) |
  | Collé d'un tableur (tabulations) | ❌ `[]` |
  | Virgule décimale `2015,1,5` | ⚠️ parse `1.0` (colonne coupée) |
  | Milliers `"8 500 000"` | ❌ valeur silencieusement ignorée |

- En cas d'échec, l'API ne renvoyait qu'un `entries: N` (voire un 400 « aucune
  entrée ») : **aucun retour** sur *ce qui* a été ignoré ni *pourquoi*.
- `web/exportcsv.js::onFileSelect` recopiait le même parseur tolérant, muet sur
  les colonnes non reconnues.

Demande utilisateur : permettre à une IA (via le MCP) d'**intégrer un CSV**, en
laissant toujours l'**utilisateur valider** — un import ne doit jamais être
appliqué sans revue humaine (risque d'ajouter des données qu'on galère à
retirer).

## 2. Objectif

1. **Réparer** l'import : détecter le délimiteur, normaliser les nombres réels,
   et **rapporter** ce qui est accepté / écrasé / rejeté (avec la raison).
2. **Stager** les imports pilotés par l'IA : l'IA (via MCP) ou l'utilisateur
   (collage) **propose** un import, l'utilisateur le **valide** dans l'interface.
   Aucun outil MCP ne peut appliquer un brouillon.

## 3. Non-objectifs

- Pas d'import CSV du **portefeuille** (transactions/dividendes d'un export
  courtier) : chantier distinct (détection de doublons propre).
- Pas de « bande Imports à valider » dédiée : le collage dans la modale suffit
  (étape 2 conditionnelle, cf. D3).
- Pas de formule de régression touchée.

## 4. Exigences

- 4.1 `data/manual._detect_delimiter` : délimiteur parmi `,` `;` `\t` (le plus
  fréquent sur la 1ʳᵉ ligne non vide, repli virgule).
- 4.2 `data/manual._parse_number` : virgule décimale, milliers (espace,
  insécable, fine, apostrophe), parenthèses négatives, devise → `float | None`.
- 4.3 `import_csv` renvoie un `models.ImportReport` (entrées + rejets + colonnes
  ignorées), raisons issues de l'ensemble fermé `config.IMPORT_REJECT_*`.
- 4.4 Schéma SQLite `5 → 6` : table `import_drafts` (staging).
- 4.5 `services/imports.py` : `propose_import` (n'écrit pas en production),
  `list_drafts`/`get_draft`/`discard_draft`/`apply_draft` (seule écriture).
- 4.6 Outil MCP `propose_import` : crée un brouillon `pending`, jamais d'écriture.
- 4.7 **Garde-fou** : aucun outil MCP n'expose `apply` (test structurel).
- 4.8 Routes REST `/api/imports` (+ `apply`/`DELETE`) : seul chemin d'application.
- 4.9 Front : collage + affichage des rejets et colonnes ignorées.

## 5. Critères d'acceptation

- [x] CA1 — Fiche #23 + ligne d'index.
- [x] CA2 — Détection du délimiteur (`;`, tabulation, virgule).
- [x] CA3 — Normalisation numérique (FR/US, milliers, négatif, devise).
- [x] CA4 — `import_csv` → `ImportReport` (accepted/overridden/rejected/colonnes).
- [x] CA5 — Route CSV renvoie le rapport ; 400 seulement si 0 acceptée ; `entries` (int) conservé.
- [x] CA6 — Aperçu front enrichi (rejets + raisons + colonnes ignorées) ; parseur aligné serveur.
- [x] CA7 — Schéma `5 → 6` (`import_drafts`) + migration + backup.
- [x] CA8 — `services/imports.py` (staging + application).
- [x] CA9 — Outil MCP `propose_import` (brouillon seul).
- [x] CA10 — Garde-fou : aucun outil MCP d'application (test dédié).
- [x] CA11 — Routes REST `/api/imports`.
- [x] CA12 — UI : collage dans la modale + diff/rejets.
- [x] CA13 — Tests Python (`test_manual`, `test_imports`, `test_api`, `test_mcp_*`).
- [x] CA14 — Tests front (`importcsv.test.js`).
- [x] CA15 — Vérifs : ruff, mypy (scope CI), `pytest -m "not network"` (910), `-m network` (5), `npm test` (423), e2e (64).
- [x] CA16 — Branche dédiée + fiche + index + note de reprise.

## 6. Invariants préservés

- La calibration Pernod (`z = −3.81`, ±0.15) reste verte (`pytest -m network`).
- Couches `web → api → services → engine → data` : le MCP délègue à `services/`.
- Aucun seuil métier hors `config.py` ; les bornes d'import vivent dans `config`.
- Parsing à **source unique** : `data/manual.import_csv`, partagé API ↔ MCP.
- Aucune écriture disque hors `data/` ; le front n'appelle jamais `fetch` hors `api.js`.

## 7. Jalons

- **J1** — Parser robuste (`config`, `models.ImportReport`, `data/manual`).
- **J2** — Schéma v6 + `data/cache` + `data/backup`.
- **J3** — `services/imports.py`.
- **J4** — Routes REST + route CSV rapport.
- **J5** — Outil MCP + garde-fou.
- **J6** — Front (`util.js`, `exportcsv.js`, `index.html`, `style.css`, `api.js`).
- **J7** — Tests + vérifs.

## 8. Note de reprise

**Livré, prêt à fusionner.** Tous les jalons sur `feat/import-csv-ia`.

### Décisions

- **D1 — périmètre « comptes financiers » (arbitrage utilisateur)** : seul le CSV
  de la fiche est pilotable. Le portefeuille (transactions/dividendes) est un
  chantier distinct (détection de doublons propre), hors périmètre.
- **D2 — staging obligatoire, application humaine** : `propose_import` écrit un
  brouillon `pending` ; l'application est une route REST (`/api/imports/{id}/apply`),
  **jamais un outil MCP** — garde-fou verrouillé par
  `test_mcp_server.test_aucun_outil_n_applique_un_import`.
- **D3 — UI de validation** : bande « Imports à valider » dans la section Données
  complémentaires (liste + détail + Appliquer/Rejeter), et modale de collage/file
  qui **propose** un brouillon au lieu d'écrire. L'étape « bande seulement si le
  volume le justifie » est dépassée : sans cet écran, le staging n'était pas
  actionnable (revue de code, finding #1).
- **D4 — raisons de rejet fermées** : `config.IMPORT_REJECT_REASONS`
  (`unparseable`, `derived_column`, `unknown_column`, `bad_year`), miroir front
  (`rejectReason`), pour que l'utilisateur ne lise jamais un texte libre.
- **D5 — `dict.fromkeys(...)` remplacé par `dict(...)`** dans `manual.py` : le
  premier renvoyait un `dict[str, None]`, non utilisé ici mais trompeur.

### Pièges rencontrés

- **`_is_noise_char` trop permissif** : retirer « tout caractère non numérique »
  réduisait `"pomme0"` à `"0"` (faux positif). Corrigé en **liste bornée** de
  symboles ignorés (espaces, apostrophe, devise, `%`) — une lettre invalide la
  cellule. Détecté par un test qui aurait dû échouer.
- **Tests de migration** : `TestFutureMigration` et `test_missing_migration_raises`
  utilisaient v6 comme « futur hypothétique » ; décalés à v7 (v6 est désormais
  réelle).

### Hors périmètre (extensions)

- Import CSV du **portefeuille** (détection de doublons).
- Import **events / indices / réglages** (la sauvegarde JSON reste la référence).

### Corrections de revue de code

1. **UI de validation livrée** (finding #1) — bande « Imports à valider » dans la
   section Données complémentaires : liste, détail, Appliquer / Rejeter. Le
   collage passe désormais par le **staging** (`POST /api/imports/propose`), plus
   jamais par l'écriture directe. Les helpers `api.js` ne sont donc plus morts.
2. **Statut auditable + atomicité** (finding #2) — `cache.apply_import_draft`
   écrit les données **et** marque `applied` dans une seule transaction ; le
   brouillon est conservé (`list_drafts("applied")` observable). Un échec
   d'écriture laisse le brouillon `pending` (rejouable, pas de double écriture).
3. **Code mort retiré** (finding #3) — `APPLY_TOOL_NAMES` et l'`assert` redondant
   supprimés de `mcp/tools/imports.py`.
4. **Miroir front ↔ serveur** (finding #4) — le compteur d'écrasement s'appuie sur
   les entrées **manuelles** exposées par le payload (`manual_entries`), comme le
   serveur ; le nombre total de rejets (`rejectedTotal`) est affiché quand
   l'échantillon (50) est tronqué.
5. **Asymétrie point-milliers documentée** (finding #5) — docstring de
   `_parse_number` et de l'outil MCP.
6. **`detail` d'erreur homogène** (finding #6) — la route `POST /api/manual/{ticker}/csv`
   renvoie une **chaîne** (raison résumée), comme les autres routes.
