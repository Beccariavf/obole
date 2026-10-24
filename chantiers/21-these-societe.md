# #21 — Thèse & Société (document markdown + profil société)

> **Statut :** **fait** · **Priorité :** 🟡 Q2 (important, non urgent — cas (c) évolutivité)
> **Impact Pernod :** 🟠 · **Branche (historique) :** `feat/these-societe` · **Taille :** 7 jalons (~2 sessions)
> **Fiche parente :** #09.3 (thèse MCP, socle serveur) · **Références produit :** `PRD.md` §8.3, §12.2/§12.4

---

## 1. Contexte

Le jalon **09.3** a livré le socle serveur de la thèse (`data/thesis.py`,
`services/thesis.py`, 5 outils MCP) — mais **rien n'était exposé au front** : la
section « Thèse & Société » était déclarée `PLANNED_SECTIONS` et grisée « à venir »
dans le rail, aucune route HTTP n'existait, et le contenu persisté était un **objet
JSON** (pitch, bull, bear…) peu adapté à une rédaction libre.

La fiche #16 (refonte) a préparé la coquille : rail de sections, deep-link,
une seule section visible. Il restait à **remplir** la section.

## 2. Objectif

Que l'utilisateur dispose, dans la fiche d'une action, d'une section **Thèse &
Société** réunissant :

1. un **profil société** (données yfinance non exploitées jusqu'ici : dirigeants,
   effectif, siège, description, agenda) ;
2. un **document markdown** vivant, rédigé dans l'app **ou** par une IA connectée
   (MCP), avec sommaire automatique, points de contrôle cochables et images.

## 3. Non-objectifs

- **Pas d'appel LLM côté serveur** (décision PRD §12.4) : l'UI propose de copier le
  prompt, d'écrire, d'importer, ou de passer par MCP — jamais un bouton « Générer »
  qui mentirait.
- Pas d'éditeur bloc-style (`contenteditable`) : textarea + toolbar + aperçu.
- Pas de versionnage ni d'évaluation « attentes vs réalisé » (extensions futures,
  incrément de schéma).
- Pas de partage d'ancre par URL (`#pitch`) : conflit avec le routeur de hash.

## 4. Décisions

| # | Décision | Retenu |
|---|---|---|
| D1 | Rendu markdown | Client — `marked` + `DOMPurify` **vendoriés** (0 CDN, 0 dep Python) |
| D2 | Modèle de données | **Markdown string** ; objet JSON accepté (rétro-compat #09.3) |
| D3 | Éditeur | textarea + toolbar + aperçu |
| D4 | Images | Upload serveur validé (magic bytes) + nom régénéré (hash) |
| D5 | Modèle du socle | `Identity` étendu (profil + agenda), `MODEL_VERSION` 7 → 8 |
| D6 | Points de contrôle | Task-list GFM `- [ ]`, compteur dérivé |
| D7 | Sommaire | Généré au rendu, **jamais persisté** |
| D8 | Pastille rail | `has_thesis` dans `/api/stock` (0 appel supplémentaire) |
| D9 | Profondeurs | Sommaire intégré 2 niveaux ; plan latéral et menu 3 niveaux |
| D10 | Ancres | Clic intercepté, **jamais** d'écriture de `location.hash` |

## 5. Critères d'acceptation

### 5.1 Fonctionnel

- [x] **CA1** — Section active dans le rail, deep-link `#RI.PA/these`
- [x] **CA2** — Profil société (DG + titre, effectif, siège, site, description repliable)
- [x] **CA3** — Agenda : prochain résultat (« estimé »/« publié ») et ex-dividende
- [x] **CA4** — Markdown persisté, auto-save, export/import `.md`
- [x] **CA5** — Toolbar (titres, gras, italique, listes, cases, image, lien)
- [x] **CA6** — Rendu **sanitisé** (`<script>`, `onerror`, `javascript:` neutralisés)
- [x] **CA7** — Image uploadée : type/taille/signature validés, chemin normalisé
- [x] **CA8** — MCP : `save_thesis` accepte le markdown ; dict rétro-compatible
- [x] **CA9** — Invariants (0 `fetch` hors `api.js`, `app.js` < 500, 0 seuil littéral)
- [x] **CA10** — Tests backend + front verts

### 5.2 UI / parcours

- [x] **CA-UI1** — État vide : 3 actions + encadré MCP (jamais de page blanche)
- [x] **CA-UI2** — Pastille du rail via `has_thesis`
- [x] **CA-UI3** — Compteur « n/N points de contrôle » dérivé
- [x] **CA-UI4** — Auto-save à 3 états, échec visible, contenu conservé
- [x] **CA-UI5** — Détection « modifiée ailleurs » + Recharger / Garder
- [x] **CA-UI6** — Cochage sans mode édition, persistant
- [x] **CA-UI7** — Case accessible (input natif, focus, clavier)
- [x] **CA-UI8** — Raccourcis ⌘B / ⌘I / ⌘S / Échap
- [x] **CA-UI9** — Import par bouton et glisser-déposer
- [x] **CA-UI10** — Agenda absolu + relatif (« dans 44 j »), « estimé », « publié »
- [x] **CA-UI11** — Pas de saut de mise en page au chargement
- [x] **CA-UI12** — Tokens existants ; ratio/indice → section non consultable

### 5.3 Sommaire & plan

- [x] **CA-TOC1** — Sommaire généré des `#`/`##`, aucune donnée en base
- [x] **CA-TOC2** — `id` des titres == liens du sommaire (posés par nos soins)
- [x] **CA-TOC3** — Masqué sous 2 titres ; H3+ hors sommaire intégré
- [x] **CA-TOC4** — `#` en bloc de code non listés (via tokens `marked`)
- [x] **CA-TOC5** — Clic d'ancre : `location.hash` **inchangé**
- [x] **CA-TOC6** — Plan latéral ≥ 1100 px, surlignage au défilement
- [x] **CA-TOC7** — Slugs uniques (`pitch`, `pitch-2`), accents dépliés, vide → `section`
- [x] **CA-TOC8** — Menu ☰ : saut au titre + insertion de structure
- [x] **CA-TOC9** — `markdown.js` pur, testé (parité + XSS)
- [x] **CA-TOC10** — Aucun token nouveau ; pas de sommaire vide
- [x] **CA-TOC11** — Sommaire jamais persisté (absent de l'export)
- [x] **CA-TOC12** — Aucune donnée société dans le document (la carte Profil suffit)

## 6. Architecture livrée

```
web → api → services → engine → data
```

| Couche | Livrable |
|---|---|
| `models.py` | `CompanyOfficer` ; `Identity` += `employees`, `officers`, `address`, `summary`, `next_earnings`, `next_earnings_estimated`, `ex_dividend` |
| `data/yahoo.py` | `_officers`, `_employees`, `_address`, `_earnings_date` ; `MODEL_VERSION` 8 ; `_IDENTITY_FIELDS` += `address` |
| `data/thesis.py` | `_valid_content` accepte une **chaîne markdown** (− rétro-compat dict) |
| `data/thesis_assets.py` | **nouveau** : validation (MIME, taille, magic bytes), nom = hash du contenu, `path_for` anti-traversée |
| `services/serialize.py` | `_profile_payload`, `_has_thesis` → bloc `profile` + `has_thesis` du payload |
| `services/thesis.py` | `save_thesis` documente le markdown |
| `api/app.py` | `GET /api/theses`, `GET/PUT/DELETE /api/thesis/{t}`, `POST /api/thesis/{t}/prompt`, `POST/GET /api/thesis/assets[/{f}]` |
| `mcp/tools/thesis.py` | `save_thesis` documenté markdown |
| `web/markdown.js` | **nouveau** : `slugify`, `extractHeadings`, `buildToc`, `renderMarkdown`, `setTask`, `relativeDays`, `THESIS_SKELETON` (`countTasks` retiré en 21.1) |
| `web/thesis.js` | **nouveau** : mixin complet (profil, CRUD, auto-save, toolbar, ancres, upload) |
| `web/index.html` | Template de section + scripts vendoriés (`marked`, `DOMPurify`) |
| `web/style.css` | ~230 lignes, tokens existants uniquement |
| `web/sections.js` | `PLANNED_SECTIONS` vidé, chargement paresseux de la thèse |
| `web/charts.js` | `sectionAvailable("these")` → actions seulement |

## 7. Invariants préservés

- Calibration Pernod (`z = −3.81`) : `pytest -m network` vert (impact 🟠 : `/api/stock` et le cache identité sont touchés → test réseau **requis**).
- `0 fetch` hors `api.js` (vérifié par `modules.test.js`).
- `app.js` < 500 lignes.
- Aucun seuil littéral hors `config.py` ; aucune formule dupliquée.
- Aucune dépendance Python ajoutée (`pip-audit` inchangé) ; libs JS vendorisées.
- `x-html` reste confiné : le seul usage à contenu utilisateur passe par `DOMPurify`.

## 8. Points de vigilance (retours d'implémentation)

1. **`id` unique des titres** — l'aperçu et la lecture ne doivent jamais coexister
   dans le DOM (`x-if`, pas `x-show`) : sinon deux blocs portent les mêmes ancres.
2. **Double dispatch d'un clic** — un clic sur une case peut être livré deux fois
   (case + libellé) : le cochage fixe l'état **voulu** (`setTask`) au lieu de basculer.
3. **Cache d'index.html** — `render_index` est mémoïsé (`lru_cache`) : après une
   modification du template, **redémarrer** le serveur (pas de `--reload`).
4. **Borne de contenu** — `THESIS_CONTENT_MAX` (100 k) : le markdown est plus
   volumineux qu'un dict ; dépassement → 422.
5. **`MODEL_VERSION` 7 → 8** — invalide une fois le cache identité (re-fetch
   silencieux), `address` servant de marqueur de fraîcheur.

### 8.1 Corrections issues de la revue de code

Sept défauts réels, tous corrigés avec test de non-régression :

1. **Fuite d'état entre fiches** — changer de titre affichait encore la thèse du
   précédent, et une saisie en cours serait partie sous le mauvais ticker. Le
   mixin suit `thesisTicker` ; l'alignement se fait dans `_loadThesisIfNeeded`
   **avant** le court-circuit « section non affichée » (changer de fiche quitte
   la section « these »).
2. **`_earnings_date`** recevait le ticker (chaîne) au lieu du `yf.Ticker` : le
   repli `calendar` levait `AttributeError`, avalée — la ligne « Prochain
   résultat » disparaissait quand `info` n'avait pas `earningsTimestamp`.
3. **`PUT` ne renvoyait pas `updated_at`** : le client le remettait à `null`
   après chaque enregistrement, rendant la détection de conflit inopérante.
4. **Course d'auto-save** — « Enregistré » s'affichait sur un texte encore
   modifié (frappe pendant la requête).
5. **Ids de titres désalignés** — un titre cité était rendu `<hN>` mais absent
   de la collecte : tous les `id` suivants glissaient d'un cran et le sommaire
   pointait sur la citation. Collecte récursive + drapeau `topLevel`.
6. **Scroll-spy non armé sur deep-link** — le branchement passe désormais par le
   point de passage commun (`_loadThesisIfNeeded`).
7. **Cul-de-sac** — aucun moyen de supprimer une thèse : bouton ajouté, avec la
   confirmation des autres collections.

## 9. Tests

| Fichier | Couverture |
|---|---|
| `tests/test_company_profile.py` (19) | `_officers`, `_employees`, `_address`, `_earnings_date`, bloc `profile`, `has_thesis`, invalidation v7 |
| `tests/test_thesis.py` (+22) | markdown round-trip, rétro-compat dict, routes CRUD/prompt, 404/422 |
| `tests/test_thesis_assets.py` (23) | MIME, signature, taille, hash du nom, traversée, exécutable renommé, service |
| `web-tests/markdown.test.js` (35) | parité ancres ↔ sommaire, XSS, blocs de code, slugs dupliqués, cases, `relativeDays`, squelette |
| `web-tests/thesis.test.js` (45) | profil, agenda, états, auto-save, conflit, cochage, ancre, toolbar, import/export, upload |

## 10. Note de reprise

**Livré.** 7 jalons, ~1 340 lignes ajoutées (dont 230 CSS), **795 tests backend** et
**327 tests front** verts, `ruff` + `mypy` verts.

Points d'entrée :
- `web/thesis.js` (mixin) et `web/markdown.js` (logique pure) — le second est le
  point d'extension naturel de tout futur usage markdown (notes, journal).
- `data/thesis_assets.py` — frontière hostile de l'upload, à réutiliser pour toute
  autre pièce jointe.

**Dette assumée / extensions** : évaluation « attentes vs réalisé », versionnage
des thèses, entrée « Thèse » dans la **sauvegarde** JSON des images (aujourd'hui
hors archive), DCF et Monte-Carlo (famille 2 du MCP).

---

## 11. Extension 21.1 — bande « Suivi »

> **Statut :** fait · **Branche (historique) :** `feat/these-suivi` · **Impact Pernod :** 🟠
> (schéma 4 → 5)

### 11.1 Motif

Deux défauts d'ergonomie après la livraison de #21 :

1. **Le bouton « Éditer » flottait.** `.thesis-title` était une étiquette capitale
   posée sur le **fond de page**, son action alignée à l'extrémité droite, sans
   bord ni ancrage avec la carte blanche qu'elle commandait. Aucune autre section
   du projet ne fait cela : partout ailleurs l'action primaire vit **dans** un
   en-tête de carte (`.val-bar-actions`, `.manual-actions`, `.idx-head-actions`).
2. **Les points de contrôle n'étaient pas ceux qu'on veut suivre.** Le compteur
   dérivait des `- [ ]` du markdown : impossible de suivre une chose à cocher qui
   ne figure pas dans le document rédigé.

### 11.2 Décisions

| # | Décision | Retenu |
|---|---|---|
| D1 | Thèse | **Carte** (en-tête / corps / pied) ; plus d'étiquette flottante |
| D2 | Bande « Suivi » | Distincte, **au-dessus** de la thèse (échéance + liste) |
| D3 | Prochain résultat | **Retiré** de l'agenda du profil (une seule occurrence) |
| D4 | « Thèse modifiée » | **Retiré** de l'agenda (doublon du statut d'auto-save) |
| D5 | Points de contrôle | **Liste persistée indépendante** (patron `events`) |
| D6 | Cases GFM du document | **Inchangées et cliquables** (document libre) |
| D7 | Compteur | Un seul, celui de la liste suivie, **dans la bande** |
| D8 | `thesisTasksLabel` / `thesisView.tasks` | **Supprimés** (code mort) |
| D9 | Suppression d'un point | Bouton `×` direct, sans confirmation (re-saisie triviale) |

### 11.3 Architecture

| Couche | Livrable |
|---|---|
| `config.py` | `CHECKPOINT_LABEL_MAX` (120), `CHECKPOINT_MAX_PER_REF` (50) ; `SCHEMA_VERSION` 5 |
| `data/cache.py` | `_CHECKPOINTS_SCHEMA` + index, CRUD, `_migrate_4_to_5` |
| `data/checkpoints.py` | **nouveau** : I/O + bornes (miroir d'`events.py`) |
| `services/checkpoints.py` | **nouveau** : cas d'usage partagé API ↔ MCP, `CheckpointNotFound` |
| `data/backup.py` | table `checkpoints` + `_TABLE_SINCE[5]` |
| `api/app.py` | `GET/POST /api/checkpoints/{ticker}`, `PUT/DELETE /api/checkpoints/{id}` ; `checkpoint_label_max` dans `/api/meta` |
| `web/suivi.js` | **nouveau** mixin : échéance, liste, mutations sérialisées |
| `web/api.js` | 4 appels (aucun `fetch` ailleurs) |
| `web/thesis.js` | agenda allégé, compteur retiré ; `thesisView.tasks` disparu |
| `web/markdown.js` | `countTasks` supprimé : `renderThesis` ne dérive plus aucun compteur |
| `web/sections.js` | chargement paresseux + reset au changement de fiche |
| `web/index.html` / `style.css` | carte Thèse, bande Suivi, tokens existants |

### 11.4 Critères

- [x] **CA-P1** — Migration 4→5 idempotente et transactionnelle ; base existante
      préservée.
- [x] **CA-P2** — Bornes testées : libellé vide refusé, libellé > `CHECKPOINT_LABEL_MAX`
      refusé (422), cap `CHECKPOINT_MAX_PER_REF` par ticker.
- [x] **CA-P3** — Export/restauration incluent `checkpoints` ; archive d'un schéma
      antérieur tolérée.
- [x] **CA-P4** — `GET` vide → `[]` (pas 404) ; `PUT`/`DELETE` sur id inconnu → 404.
- [x] **CA-UX1** — Thèse en carte (en-tête / corps / pied) ; plus d'étiquette flottante.
- [x] **CA-UX2** — Éditer / Terminé / Réessayer dans l'en-tête, **même emplacement**.
- [x] **CA-UX3** — Exporter / Importer / Supprimer au pied de la carte.
- [x] **CA-UX4** — Tokens existants, SVG monochrome, aucun emoji nouveau.
- [x] **CA-B1** — « Prochain résultat » une seule fois sur la fiche.
- [x] **CA-B2** — Date absolue + relative, badge « estimé », « publié » si passée.
- [x] **CA-B3** — Compteur `n/N` + barre de progression dans la bande ; retiré de
      l'en-tête de la thèse.
- [x] **CA-B4** — Bande affichée même sans thèse.
- [x] **CA-B5** — Bande absente pour un ratio / indice.
- [x] **CA-B6** — « Thèse modifiée » retiré de l'agenda.
- [x] **CA-CK1** — Ajout par champ + `Entrée` ou bouton ; libellé trimé, vide refusé,
      borné (front via `/api/meta` **et** back).
- [x] **CA-CK2** — Cochage optimiste ; échec non silencieux (retour à l'état précédent).
- [x] **CA-CK3** — Suppression par `×`, sans confirmation.
- [x] **CA-CK4** — Mutations sérialisées (`cpBusy`).
- [x] **CA-CK5** — Aucun appel avant l'ouverture de la section.
- [x] **CA-CK6** — Reset au changement de fiche (alignement `cpTicker`).
- [x] **CA-CK7** — Cases GFM du document toujours cliquables et persistées.
- [x] **CA-D1** — `thesisTasksLabel()`, `thesisView.tasks` et `countTasks` supprimés ;
      `renderThesis` ne dérive plus aucun compteur, aucun test orphelin.
- [x] **CA-V1** — 0 `fetch` hors `api.js`, `app.js` 207 lignes, seuils dans `config.py`.
- [x] **CA-V2** — `ruff`, `ruff format --check`, `mypy`, `pytest -m "not network"`,
      `vitest` verts.
- [x] **CA-V3** — `pytest -m network` vert (Pernod `z = −3.81`).
- [x] **CA-V4** — e2e non destructif, Chromium **et** WebKit.
- [x] **CA-V5** — Fiche + index mis à jour.
- [x] **CA-V6** — Tests repris dans le même commit (aucun test rouge).

### 11.5 Points de vigilance (21.1)

1. **Tests de schéma indexés sur la version.** `TestFutureMigration` supposait
   « 4 → 5 » ; il utilise désormais « 5 → 6 » (hypothétique), sinon il testait une
   migration désormais réelle. Idem pour `test_missing_migration_raises`.
2. **`_TABLE_SINCE` par version, pas par table.** `test_table_registry_declares_theses`
   interrogeait `_TABLE_SINCE[SCHEMA_VERSION]` : il cherche maintenant la table dans
   l'ensemble des versions déclarées.
3. **Deux surfaces de cochage assumées (D6)** : document libre + liste suivie. Le
   test e2e vérifie que le compteur n'est PAS dupliqué dans l'en-tête.
4. **Dates : source unique `markdown.js`.** `daysUntil` / `formatDate` / `agendaRow`
   servent l'agenda du profil ET la bande « Suivi ». Le caractère « passé » se
   calcule (`daysUntil < 0`), il ne se déduit plus du libellé renvoyé par
   `relativeDays` — un renommage du texte aurait cassé silencieusement l'affichage.
5. **Route du prompt = POST.** `@app.post("/api/thesis/{ticker}/prompt")` exécute
   une analyse complète (ce n'est pas une simple lecture) : le front doit appeler
   `_send(..., "POST", {})`. Un `GET` renvoyait **405**, et l'échec était invisible
   (`thesisError` n'est rendu que par le bloc conditionné à `thesisStatus ===
   'error'`) : `copyThesisPrompt` pose désormais ce statut. Deux tests couvrent le
   câblage (méthode HTTP + visibilité de l'échec).

### 11.6 Corrections issues de la revue de code

| # | Défaut | Correctif |
|---|---|---|
| 1 | **Bouton « Copier le prompt » HS (405)** — `GET` sur une route `POST`, échec silencieux | `_send(..., "POST", {})` + `thesisStatus = "error"` dans les deux branches d'échec ; 2 tests |
| 2 | Méthode `backup()` collée à la précédente (double espace) | Mise en forme d'origine rétablie |
| 3 | `fmtDate` dupliquée (thesis + suivi) et « passé » déduit du texte `« il y a »` | `daysUntil`/`formatDate`/`agendaRow` dans `markdown.js`, consommés par les deux |
| 4 | Images de thèses absentes de la sauvegarde, sans avertissement UI | Avertissement explicite dans le panneau Données (référence `thesis_assets/`) |

---

## 12. Extension 21.2 — replier le plan de la thèse

> **Statut :** fait · **Branche (historique) :** `feat/these-suivi` · **Impact Pernod :** 🟢
> (front seul : ni schéma, ni route, ni sauvegarde)

### 12.1 Motif

Le plan latéral (`.thesis-plan`) était **toujours affiché** au-delà de 1100 px :
`x-show="!thesisEditing && thesisTocVisible()"` ne dépendait que de la largeur
d'écran, jamais d'un choix de l'utilisateur. Or il **double** le sommaire intégré
(`.md-toc`) à l'ouverture : le sommaire donne déjà la structure, le plan n'a
d'intérêt que **pendant** la lecture (il est le seul à 3 niveaux, et le seul avec
le scroll-spy). Il fallait donc pouvoir le replier.

### 12.2 Décisions

| # | Décision | Retenu |
|---|---|---|
| D1 | Emplacement du bouton | Dans l'en-tête de la **carte** (même slot que « Éditer ») |
| D2 | Défaut | **Fermé** — le sommaire intégré couvre l'ouverture |
| D3 | Persistance | **`localStorage`** (préférence locale, dépendante de l'écran) |
| D4 | Sous 1100 px | Bouton **absent** (la colonne n'existe pas) |
| D5 | Largeur de lecture | Corps toujours borné à 72ch, mais **recentré** quand le plan est fermé |
| D6 | Pendant l'édition | Plan masqué et bouton retiré (une seule surface de travail) |

**Pourquoi `localStorage` et non la table `settings`** : `SETTING_DEFS` porte des
réglages de **méthode** (moyennes mobiles, benchmark), persistés et inclus dans la
sauvegarde JSON. L'état d'un panneau d'affichage est autre chose : il dépend de la
taille de la fenêtre, n'a pas de sens à la restauration, et n'a rien à faire dans
la modale Paramètres. C'est la **première** utilisation du stockage local dans le
projet : l'accès est isolé dans deux helpers à lecture/écriture défensives
(`readFlag`/`writeFlag`) — un stockage refusé (mode privé, quota) ne casse jamais
la fiche, la bascule restant effective pour la session.

**Pourquoi le recentrage** : `.md-body` est borné à 72ch (~620 px). Sans
recentrage, fermer le plan libérait la colonne mais laissait un vide à droite — le
résultat aurait été *moins* bon que le plan ouvert. `.thesis-main` est donc centré
(`margin: 0 auto`) sous la même media query, ce qui recentre l'ensemble sommaire +
texte et garde leur alignement.

**Pourquoi pas d'écouteur `resize`** : la visibilité du bouton suit la **même**
media query `@media (min-width: 1100px)` que la colonne (CSS pur). Aucun JS ne
tourne au redimensionnement, donc aucun re-render.

### 12.3 Architecture

| Fichier | Livrable |
|---|---|
| `web/thesis.js` | État `thesisPlanOpen`, `loadThesisPlanPreference`, `toggleThesisPlan`, `thesisPlanVisible`, `thesisPlanAvailable` ; helpers `readFlag`/`writeFlag` défensifs |
| `web/index.html` | Bande `.thesis-edge` (`<label>` + input caché) en premier enfant de `.thesis-flow` ; onglet `.thesis-pin` ; `id="thesis-plan"` ; `x-show="thesisPlanVisible()"` ; classe `plan-closed` sur `.thesis-flow` |
| `web/style.css` | `--thesis-pad-x` (source unique du rembourrage et de la largeur de bande) ; `.thesis-edge` absolue, `.thesis-pin` `sticky` ; recentrage `.thesis-flow.plan-closed > .thesis-main` |
| `web/app.js` | Lecture de la préférence au démarrage (avec les autres métadonnées) |

### 12.4 Critères

- [x] **CA-PL1** — Bouton « Plan » dans l'en-tête de la carte, état actif visible.
- [x] **CA-PL2** — Bascule sans rechargement ni saut de mise en page (0 requête).
- [x] **CA-PL3** — Bouton et colonne sur la **même** media query (1100 px), sans
      écouteur `resize`.
- [x] **CA-PL4** — `aria-expanded` + `aria-controls="thesis-plan"`, bouton natif
      (Tab / Entrée / Espace) et `:focus-visible`.
- [x] **CA-PL5** — Infobulle « Afficher le plan » / « Masquer le plan », SVG
      monochrome, aucun emoji.
- [x] **CA-PL6** — État mémorisé : restitué au rechargement et au changement de fiche.
- [x] **CA-PL7** — Sans préférence (ou stockage refusé/corrompu) → **fermé**, sans crash.
- [x] **CA-PL8** — Préférence **globale** (pas par ticker), absente de la sauvegarde.
- [x] **CA-PL9** — Plan fermé : colonne retirée, corps élargi et **recentré**.
- [x] **CA-PL10** — Plan rouvert en lecture : section courante surlignée (scroll-spy).
- [x] **CA-PL11** — En édition : plan masqué et bouton retiré.
- [x] **CA-PL12** — Sommaire intégré inchangé dans les deux états.
- [x] **CA-PL13** — Invariants (0 seuil hors `config.py`, 0 `fetch` hors `api.js`,
      `app.js` < 500 l., jetons de charte, aucun emoji).
- [x] **CA-PL14** — `vitest` 393 · Playwright 10 Chromium + 10 WebKit **sur base
      neuve comme sur base existante** (le test sème et restaure sa fixture) ·
      pytest 827/5.
- [x] **CA-PL15** — Cette fiche.

### 12.5 Points de vigilance (21.2)

1. **Port 8000 occupé par un autre serveur.** La suite e2e a d'abord échoué en
   entier : `playwright.config.js` fait `reuseExistingServer: true` sur
   `127.0.0.1:8000`, où tournait une **autre** application (`/` → 200,
   `/api/health` → 404). Diagnostic : `lsof -nP -iTCP:8000 -sTCP:LISTEN`. Pour
   vérifier sans toucher à ce serveur, lancer uvicorn sur un port libre et pointer
   une config temporaire (`OBOLE_E2E_PORT`). La CI n'est pas concernée (port libre).
2. **`thesisPlanOpen: null` = « jamais chargé »**, distinct de `false`. La
   préférence n'est lue qu'une fois (idempotent), au démarrage ; un test qui
   instancie le mixin doit appeler `loadThesisPlanPreference()` explicitement.
3. **Recentrage conditionné à la media query** : `.plan-closed` est posée par le
   template sur `.thesis-flow`, mais la règle de largeur vit dans le CSS. Sous
   1100 px, la classe n'a aucun effet (le corps est déjà pleine largeur).

### 12.6 Correction issue de la revue de code

**[Bloquant CI] Le test e2e du plan dépendait de données utilisateur.** Le parcours
exige une thèse AVEC sommaire (≥ 2 titres), mais la CI part d'un checkout neuf
(`cache.sqlite` est gitignoré) : aucune thèse n'existe, le plan restait masqué
après le clic, et le test expirait sur Chromium **et** WebKit.

Le test **sème sa propre fixture** via l'API (`PUT /api/thesis/RI.PA`) et la
restaure en `finally` : remise du contenu précédent s'il existait, suppression
sinon. Vérifié dans les trois situations :

| Situation | Résultat |
|---|---|
| Base neuve (mime la CI) | ✓ Chromium + WebKit, base laissée vide après coup |
| Base avec thèse utilisateur | ✓ contenu restauré à l'identique (`updated_at` seul bouge) |
| Base courante (vraie) | ✓ 20/20 (Chromium + WebKit) |

Le test couvre en plus le repli du plan pendant l'édition (CA-PL11).

---

## 13. Extension 21.3 — poignée de bord du plan

> **Statut :** fait · **Branche (historique) :** `feat/these-suivi` · **Impact Pernod :** 🟢

### 13.1 Motif

Défaut d'usage signalé après livraison de 21.2 :

1. **On ne peut pas OUVRIR le plan en cours de lecture** — le bouton vivait dans
   `.thesis-card-head`, qui sort du champ dès qu'on descend dans le document.
2. **On ne peut pas REFERMER un plan affiché** — le plan est `sticky` (il suit la
   lecture, comportement voulu), mais son seul moyen de fermeture était remonté
   avec l'en-tête. La symétrie était cassée : on ouvrait depuis le haut, on ne
   pouvait fermer que depuis le haut.

Le lieu du contrôle était donc le seul défaut. Le mécanisme de repli lui-même
(`thesisPlanOpen`, mémorisation `localStorage`, `plan-closed`) est conservé tel quel.

### 13.2 Décisions

| # | Décision | Retenu |
|---|---|---|
| D11 | Emplacement du contrôle | **Bande de survol du bord droit** de la carte ; l'ancien bouton d'en-tête est **supprimé** |
| D12 | Un ou deux contrôles | **Un seul**, deux états : il ouvre et ferme au même endroit |
| D13 | Largeur de la bande | **Exactement le rembourrage de carte** (`--thesis-pad-x`, 22 px) — donc **hors flux** et **_zéro_ chevauchement du contenu** |
| D14 | Forme de l'onglet | **Chevron seul** (22 px) ; libellé « Plan » / « Masquer » en **overlay au survol** (n'élargit pas l'onglet) |
| D15 | Épinglage | Bande `absolute` pleine hauteur + onglet `sticky` → atteignable à toute position de défilement |
| D16 | Affordance quand ouvert | Onglet **faiblement visible** hors survol (opacité .45) : sans cela on perdrait le seul moyen de refermer |
| D17 | Contrôle | **Bouton natif** `.thesis-pin` (Tab/Entrée/Espace), état porté par la classe `.open` — pas d'input caché, donc aucun sélecteur dépendant de l'ordre dans l'arbre |

### 13.3 Mécanisme

```
.thesis-card  { --thesis-pad-x: 22px; padding: 18px var(--thesis-pad-x) }
  .thesis-flow { position: relative }                  ← repère de la bande
    .thesis-edge { position: absolute; right: calc(-1*var(--pad)); width: var(--pad) }
       (bande survolable, pleine hauteur du flux — jamais la rangée d'actions)
       .thesis-pin (bouton sticky, classe .open quand le plan est affiché)
    .thesis-main  …  .thesis-plan
```

**Pourquoi la fiche ne rétrécit pas** (exigence explicite de l'utilisateur) : la
bande est `position: absolute`, donc sa contribution au layout est **nulle**. Le
rembourrage de la carte et la largeur de la bande partagent **une seule source**
(`--thesis-pad-x`) : impossible de dériver l'un de l'autre. Preuve en e2e — forcer
la largeur de la bande à 300 px ne change pas `clientWidth` de la carte, et la
largeur mesurée de la bande égale exactement `padding-right` calculé.

**Hors flux, mais pas sur la rangée d'actions** : la bande vit **dans**
`.thesis-flow` (donc sous l'en-tête), pas sur la carte entière. Sinon elle
recouvrirait les 22 px droits du bouton « Éditer » et un clic toucherait l'onglet
au lieu du bouton.

### 13.4 Critères

- [x] **CA-PL16** — `.thesis-plan-toggle` retiré du template **et** ses règles CSS
      supprimées (aucun style orphelin).
- [x] **CA-PL17** — Bande `.thesis-edge` `position:absolute` à hauteur de
      `.thesis-flow`, largeur = rembourrage de carte (source unique
      `--thesis-pad-x`) : aucun recouvrement du contenu cliquable.
- [x] **CA-PL18** — Atteignable à toute hauteur de lecture (bande pleine hauteur +
      onglet `sticky`) : e2e qui défile au milieu du document, survole, ouvre,
      referme.
- [x] **CA-PL19** — **La fiche garde exactement sa largeur** : bande absolue,
      `clientWidth` invariant ; recentrage fermé (820 px) inchangé.
- [x] **CA-PL20** — Ouvert : onglet faiblement visible (.45) hors survol, contrasté
      au survol ; fermé : invisible hors survol. Un contrôle, un clic, deux états.
      Libellé en overlay (n'élargit pas l'onglet).
- [x] **CA-PL21** — `aria-expanded`, `aria-controls="thesis-plan"`, `title` inversé,
      `:focus-visible` avec anneau d'accent, chevron SVG monochrome orienté.
- [x] **CA-PL22** — Poignée absente si le plan ne peut exister (édition,
      sommaire < 2 entrées via `thesisPlanAvailable()`, < 1100 px) — media query,
      **aucun écouteur `resize`** ; `@media (hover: none)` la révèle en permanence.
- [x] **CA-PL23** — Bascule sans requête réseau et sans décalage de mise en page.
- [x] **CA-PL24** — Tests à jour : `thesis.test.js` (poignée hors de l'en-tête,
      `thesisPlanAvailable()`, `--thesis-pad-x` partagé, media query, zéro
      `resize`, garde-fou du sélecteur de survol) ; `sections.spec.js` (survol
      avant clic, parcours mi-document, invariance de largeur) sur **base jetable**
      (`OBOLE_CACHE_DB`).
- [x] **CA-PL25** — Vérification verte (cf. 13.8).
- [x] **CA-PL26** — Cette fiche + `CHANTIERS.md`.

### 13.5 Points de vigilance (21.3)

1. **La bande de survol ne doit pas couvrir la rangée d'actions.** Elle vit dans
   `.thesis-flow`, pas sur la carte : sinon « Supprimer la thèse » (aligné à
   droite, dans le rembourrage) devient partiellement inatteignable.
2. **`--thesis-pad-x` est une source unique.** Écrire `22px` en dur d'un côté et
   `var()` de l'autre rouvre exactement le défaut que 21.3 corrige.
3. **Onglet ouvert à 45 %** et non 50/60 : assez visible pour être trouvé, assez
   discret pour ne pas concurrencer la colonne.

### 13.6 Incident de données (à ne pas reproduire)

Une **sonde de capture ad hoc** (`web-tests/.shot.mjs`) a été écrite pour vérifier
le rendu visuel. Elle faisait un `PUT /api/thesis/RI.PA` **sans restaurer l'état
initial** : la vraie thèse Pernod Ricard de l'utilisateur a été écrasée par la
fixture de test.

- **Récupération** : 2 834 caractères retrouvés dans le journal WAL de SQLite
  (8 copies identiques), soit le titre, la synthèse du pitch et le début du bull
  case. Restaurés avec un commentaire HTML signalant la troncature.
- **Perte résiduelle** : la fin du bull case, le bear case, la conclusion et les
  cibles (non présents ailleurs : ni WAL, ni `cache.sqlite`, ni sauvegarde JSON du
  17/09, ni Time Machine, ni corbeille).
- **Règles qui en découlent** :
  1. **La suite e2e tape une base JETABLE** : `playwright.config.js` redirige le
     serveur qu'il démarre via `OBOLE_CACHE_DB=web-tests/.tmp-cache/e2e.sqlite`
     (gitignoré). Un `try/finally` ne protège pas d'une interruption brutale ;
     seule une base séparée le fait.
  2. **Aucun script de capture ad hoc** laissé dans `web-tests/` : pour un contrôle
     visuel, passer par Playwright avec la fixture restaurée, ou lire le DOM.
  3. La **sauvegarde JSON du 17/09 est antérieure au schéma v5** : elle ne contient
     pas les thèses. Ne pas la considérer comme un filet de sécurité.

Vérification globale : la base réelle n'est jamais modifiée par la suite e2e
(`OBOLE_CACHE_DB` → base jetable).

### 13.7 Corrections issues de la revue de code

| # | Finding | Correction |
|---|---|---|
| 1 | **Sélecteur de survol mort** — `.thesis-plan-input:checked ~ .thesis-edge:hover .thesis-pin` ne pouvait jamais matcher (`~` est un combinateur de **frères**, or l'input était l'**enfant** de `.thesis-edge`). Résultat : plan ouvert, la poignée restait figée à 45 % au survol. | L'état vit désormais dans une **classe `.open` sur le bouton** : plus aucun sélecteur dépendant de la position dans l'arbre. Règle de survol placée **après** celle des 45 % (à spécificité égale, l'ordre tranche). **Reproduit puis vérifié** en Chromium (0,45 → 1). Garde-fou vitest (`iHover > iOpen`) + assertion e2e sur le survol ouvert. |
| 2 | **L'e2e écrivait dans la base RÉELLE** (`PUT /api/thesis/RI.PA`, restauration seulement en `finally` : un kill/timeout entre les deux corrompt les données). | Nouvelle **redirection `OBOLE_CACHE_DB`** (lue par `config.py`, même patron que `OBOLE_LOG_LEVEL`). `playwright.config.js` pointe le serveur qu'il démarre vers `web-tests/.tmp-cache/e2e.sqlite` (gitignoré). Vérifié : base jetable créée, thèse absente (404), base réelle **intacte** après la suite. |
| 3a | `position: relative` inutilisé sur `.thesis-card`. | Retiré. |
| 3b | `aria-expanded` sur un `<input type="checkbox">` : annonce AT « case à cocher, déplié » — sémantiquement bancal. | Le contrôle redevient un **bouton natif** `.thesis-pin` — le patron ARIA attendu pour un dépliement. Un seul signal d'état. |

### 13.8 Vérification

`vitest` 398 · Playwright **64** (32 Chromium + 32 WebKit, sur **base jetable**) ·
`pytest -m "not network"` 827 · `pytest -m network` 5 (Pernod z = −3,81) ·
`ruff check` / `format --check` / `mypy` verts.

La base réelle de l'utilisateur n'est **jamais** touchée par la suite e2e : son état
est vérifié identique après exécution (thèse + points de contrôle).

---

## 14. Extension 21.4 — densité « Suivi » & « Profil société »

> **Statut :** fait · **Branche (historique) :** `feat/these-suivi` · **Impact Pernod :** 🟢

### 14.1 Motif

Deux lourdeurs signalées à l'usage :

1. **Bande « Suivi »** — trois étages empilés (`Prochain résultat`, puis un bloc
   « Points de contrôle » avec son libellé + sa barre, puis la liste). À un seul
   point suivi, la barre vide pleine largeur se lisait comme un **filet de
   séparation** et non comme une progression : elle n'informait pas.
2. **Profil société** — la grille `1.1fr 1fr` réservait **la moitié** de la largeur
   à l'agenda, qui ne porte souvent qu'**une** échéance (`Ex-dividende`). 4/5 de
   cette colonne restaient vides, plus une bande vide sous la description repliée.
   `.profile-agenda` n'avait d'ailleurs **aucune règle CSS** : elle héritait du
   grid par accident.

### 14.2 Décisions

| # | Décision | Retenu |
|---|---|---|
| D18 | Ligne de tête « Suivi » | **Une seule** : échéance à gauche, compteur à droite (`margin-left: auto`) |
| D19 | Libellé « Points de contrôle » | **Supprimé** (le compteur seul suffit) ; son sens passe par un **intitulé accessible** |
| D20 | Barre de progression | Seulement à partir de **2** points suivis — à 1, elle n'exprime rien |
| D21 | Couleur du compteur | Neutre à 0 coché, accent dès le premier (un « 0/1 » en bleu brillerait pour rien) |
| D22 | Grille du profil | **Unique**, `auto-fit minmax(420px, 1fr)` → **2 colonnes** équilibrées |
| D23 | Regroupement faits/agenda | **Fusionné** : avec un seul item d'agenda, le regroupement était de toute façon invisible, et chaque libellé se décrit |
| D24 | Description repliée | **2 colonnes** (`columns: 2 340px`), au lieu d'un pavé vertical laissant un blanc à droite |

**Pourquoi 420 px de minimum** : une première passe à `minmax(240px)` donnait
**3 colonnes**, trop étroites — l'URL du site et « · dans 43 j » se coupaient en
deux. Deux colonnes larges équilibrent les six lignes et laissent chaque valeur
sur une ligne.

### 14.3 Architecture

| Fichier | Livrable |
|---|---|
| `web/index.html` | `.suivi-topline` (échéance + compteur), `.suivi-count` ; profil en grille unique, `.agenda-row` → `.profile-row` |
| `web/style.css` | `.suivi-topline`/`.suivi-count` (dont `.done`) ; `.profile-grid` fluide, `.profile-label` 112 px, description en 2 colonnes |
| `web/suivi.js` | `cpBarVisible()`, `cpLabelTitle()`, `cpHasDone()` |

### 14.4 Critères

- [x] **CA-D1** — Libellé « Points de contrôle » retiré du template (0 occurrence).
- [x] **CA-D2** — Compteur sur la **même ligne** que « Prochain résultat », poussé à droite.
- [x] **CA-D3** — Sans échéance : la ligne tient, compteur seul à droite.
- [x] **CA-D4** — Sans point suivi : ni compteur, ni barre.
- [x] **CA-D5** — Barre à partir de 2 points (`cpTotal() >= 2`).
- [x] **CA-D6** — Compteur neutre à 0 coché, accent dès le premier.
- [x] **CA-D7** — Intitulé accessible **réellement exposé** (« 1 point validé sur 2 points de contrôle »), via un nœud `.sr-only` ; accords singulier/pluriel séparés.
- [x] **CA-D8** — Grille unique fluide ; `.profile-agenda` supprimé (plus de règle fantôme).
- [x] **CA-D9** — Largeur exploitée (> 80 % de la carte), 2 colonnes, aucun trou.
- [x] **CA-D10** — Toutes les valeurs au même x (libellé 112 px partagé).
- [x] **CA-D11** — Description sur 2 colonnes au-delà de 340 px de contenu.
- [x] **CA-D12** — Aucun token de couleur nouveau, aucun emoji, hairlines `--border`, chiffres tabulaires.
- [x] **CA-D13** — Sous 620 px : 1 colonne, aucun débordement ni troncature — **vérifié par assertion e2e sur 9 largeurs (720→320 px)**, prouvée discriminante.
- [x] **CA-D14** — Tests : `suivi.test.js` (barre, intitulé + accord `total = 1`, accent) ; `sections.spec.js` (ligne unique, alignement, exposition de l'intitulé, barre conditionnelle, colonnes et non-débordement du profil) — fixture semée puis retirée.
- [x] **CA-D15** — Vérification verte (cf. 14.7).
- [x] **CA-D16** — Cette fiche + `CHANTIERS.md`.
- [x] **CA-D17** — Contrôle visuel avant/après ; **aucun script ad hoc conservé** dans `web-tests/` (leçon de 13.6), et la mesure utile promue en assertion.

### 14.5 Corrections issues de la revue de code

| # | Finding | Correction |
|---|---|---|
| 1 | **Régression responsive** — `minmax(420px, 1fr)` nu : un track ne descend jamais sous son minimum, donc la grille **débordait sa carte de 360 à 580 px** (jusqu'à +225 px à 360). Le contrôle visuel initial n'avait été fait qu'à 700 px, où le contenu tenait encore : toute la plage étroite était passée sous le radar. CA-D13 était donc faux. | `minmax(min(420px, 100%), 1fr)` : la plage est bornée par la largeur disponible, la grille retombe à 1 colonne. **Vérifié par assertion e2e sur 9 largeurs** (720→320 px, débordement ≤ 1 px) — et le test a été **prouvé discriminant** : avec l'ancienne valeur, il échoue à 500 px (+65 px). |
| 2 | **Intitulé accessible non exposé** — `aria-label` posé sur un `<span>` **sans rôle** : ignoré par les technologies d'assistance. L'arbre Playwright ne lisait que « 0/1 », sans contexte. D19 (retrait du libellé visible) reposait dessus → CA-D7 non livré. | Un nœud **`.sr-only`** porte l'intitulé (seul procédé réellement exposé) et le chiffre visible passe en `aria-hidden`. Ajout de la classe utilitaire `.sr-only` (absente du projet). Vérifié par `ariaSnapshot` : il lit désormais « 0 point validé sur 2 points de contrôle ». |
| 3 | **Script de contrôle ad hoc** `web-tests/e2e/_m4.spec.js` laissé dans le dépôt : sans assertion, compté comme test réussi (64 → 66) et tournant en CI pour rien. Violait CA-D17. | Supprimé. Sa mesure utile (débordement sur écran étroit) est **devenue l'assertion** du test e2e — c'est exactement ce qui manquait pour attraper le finding 1. |
| 4 | **Accord fautif** : « 1 point validé sur 1 points de contrôle » — les deux accords partageaient la variable `done`, alors que le pluriel de « point(s) de contrôle » suit `total`. `suivi.test.js` ne couvrait que `total = 2` (faux vert). | Deux accords dérivés de leurs variables respectives (`done` pour « validé(s) », `total` pour « point(s) de contrôle »). Cas `total = 1` ajouté au test. |

**Leçon transverse** : le contrôle visuel par capture ne vaut que par la **couverture des largeurs** qu'il balaie. Un rendu vérifié à une seule largeur confortable ne dit rien de la plage étroite — d'où le passage de ces vérifications en **assertions e2e multi-largeurs**.

### 14.6 Points de vigilance (21.4)

1. **Le compteur est muet sans son `.sr-only`.** Le libellé visible ayant été
   supprimé, retirer l'intitulé masqué rendrait la ligne ininterprétable par un
   lecteur d'écran (et un simple `aria-label` sur un `<span>` ne suffit pas — il
   n'est pas exposé).
2. **Seuil de la barre à 2, pas « > 1 point »** : c'est une décision de lecture,
   pas de mathématiques (à 1 point, `0/1` et `1/1` disent déjà tout).
3. **`minmax` avec borne en dur et grille fluide** : toujours `min(…, 100%)` sur
   le minimum, sinon un track refuse de se comprimer et déborde sa carte.
4. **Débordement horizontal à 700 px** : préexistant (un `.btn ghost` de
   l'en-tête), **présent sur toutes les sections**, indépendant de ce chantier.
   Constaté et isolé pendant le contrôle visuel, non traité ici (hors périmètre).

### 14.7 Vérification

`vitest` 402 · Playwright **64** (32 Chromium + 32 WebKit, base jetable) ·
`pytest -m "not network"` 827 · `pytest -m network` 5 (Pernod z = −3,81) ·
`ruff check` / `format --check` / `mypy` verts.

