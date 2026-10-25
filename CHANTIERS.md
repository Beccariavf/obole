# Chantiers Obole — index

> **Mémoire de travail du projet.** Une ligne = un chantier, une fiche = `chantiers/<id>.md`.
> Les fiches sont des **specs** : elles décrivent le problème, le périmètre, les critères
> d'acceptation et les invariants à préserver, pour être reprises à froid à n'importe quel moment.
>
> **Pour reprendre un chantier :** « reprends le #03 ». Pour en ajouter un : « ajoute un chantier
> X là-dedans » (copie `chantiers/_gabarit.md`).
>
> **Règle d'or :** ne jamais mélanger deux chantiers dans une même branche.

---

## 1. Comment un chantier est classé

Deux axes **orthogonaux**, à ne pas confondre :

- La **priorité** (matrice d'Eisenhower) répond à *« quand le faire ? »*.
- L'**impact Pernod** répond à *« comment vérifier que je ne casse rien ? »*.

### 1.1 Priorité — matrice d'Eisenhower

**Urgent** = il y a une horloge. Trois cas, et trois seulement :

- **(a) Blocage** — le chantier empêche d'utiliser l'outil ou bloque un autre chantier.
- **(b) Irréversible** — ne pas le faire expose à une perte qu'on ne peut pas réparer.
- **(c) Dépendance externe** — quelqu'un d'autre attend, ou une échéance impose une date.

**Important** = ça sert l'objectif du produit. Trois cas :

- **(a) Justesse** — ça protège l'exactitude de la méthode (la « droite d'Obole »).
- **(b) Confiance** — ça protège les données de l'utilisateur.
- **(c) Évolutivité** — ça permet de continuer à faire évoluer le code sans le casser.

| Quadrant | Signification | Traitement |
|---|---|---|
| 🔴 **Q1** — urgent + important | Le seul quadrant qui impose d'agir **maintenant** | Immédiat |
| 🟡 **Q2** — important, pas urgent | Le cœur du travail : c'est là qu'on construit | À planifier |
| 🔵 **Q3** — urgent, pas important | À **expédier** vite, sans y investir | Batch court |
| ⚪ **Q4** — ni l'un ni l'autre | Inscrit pour mémoire, **non planifié** | Abandonné (assumé) |

> Un chantier qui n'entre dans **aucun** des cas (a)/(b)/(c) des deux axes n'est ni urgent ni
> important : il va en Q4. Cette règle évite l'inflation de priorités.

### 1.2 Impact Pernod — le rayon d'action sur le cœur

Le garde-fou central du projet est la calibration Pernod (`z = −3.81`, cf. `PRD.md` §5). Un
chantier est classé selon ce qu'il risque de casser :

| Tag | Signification | Vérification requise |
|---|---|---|
| 🟢 **Nul** | Ne touche pas au calcul (docs, tests ajoutés, I/O, infra) | Tests hors réseau suffisent |
| 🟠 **Indirect** | Déplace du code qui **appelle** la régression (refactor, front) | `pytest -m network` **obligatoire** |
| 🔴 **Direct** | Modifie la **formule** elle-même | `-m network` + validation manuelle de la fiche |

---

## 2. Index des chantiers

| # | Chantier | Priorité | Impact | Taille | Statut | Fiche |
|---|---|:---:|:---:|:---:|---|---|
| 01 | Observabilité (logs structurés, `/api/health`) | 🟡 Q2 | 🟢 | 1 session | **fait** | [→](chantiers/01-observabilite.md) |
| 02 | Versioning du schéma SQLite | 🟡 Q2 | 🟢 | ½ session | **fait** | [→](chantiers/02-versioning-schema.md) |
| 03 | Sauvegarde des données utilisateur | 🔴 Q1 | 🟢 | 1-2 sessions | **fait** | [→](chantiers/03-sauvegarde-donnees.md) |
| 04 | Découpage du front (modules ES natifs) | 🟡 Q2 | 🟠 | 2-3 sessions | **fait** | [→](chantiers/04-decoupage-front.md) |
| 05 | Extraire une couche `services/` (engine pur) | 🟡 Q2 | 🟠 | 1-2 sessions | **fait** | [→](chantiers/05-services.md) |
| 06 | Source unique des seuils (`/api/meta`) | 🔵 Q3 | 🟠 | 1 session | **fait** | [→](chantiers/06-seuils-source-unique.md) |
| 07 | Tests manquants (`data/indices.py`, couverture) | 🔵 Q3 | 🟢 | ½ session | à faire | [→](chantiers/07-tests-manquants.md) |
| 08 | Renforcer le garde-fou Pernod (5 mesures) | 🟡 Q2 | 🟢 | 20 min | **fait** | [→](chantiers/08-gardefou-pernod.md) |
| 09 | **MCP — surface IA** (projet PRD §12) | 🟡 Q2 | 🟢 | 3 jalons + extensions | **fait** (09.0 → 09.4 ✅) | [→](chantiers/09-mcp.md) |
| 10 | Consolidation documentaire (source unique de la doc) | 🟡 Q2 | 🟢 | 1-2 sessions | à faire | [→](chantiers/10-consolidation-doc.md) |
| 11 | Retry SQLite sur `database is locked` | 🔵 Q3 | 🟢 | ½ session | à faire | [→](chantiers/11-sqlite-retry.md) |
| 12 | Cache `pickle` → format inspectable | ⚪ Q4 | 🟢 | 1 session | **abandonné** | [→](chantiers/12-pickle-q4.md) |
| 13 | UX du screener (capi, plein écran, filtres, ancre) | 🔵 Q3 | 🟢 | 1 session | **fait** | [→](chantiers/13-screener-ux.md) |
| 14 | Score composite du screener (classement par compromis) | 🔵 Q3 | 🟠 | 1 session | **fait** | [→](chantiers/14-screener-score.md) |
| 15 | Finir `services/` (extraire le cas d'usage screener) | 🟡 Q2 | 🟠 | 1 session | **fait** | [→](chantiers/15-services-screener.md) |
| 16 | Refonte de la fiche entreprise (rail de sections) | 🟡 Q2 | 🟠 | 7 étapes | **fait** (É0 → É7 ✅) | [→](chantiers/16-refonte-fiche.md) |
| 17 | Portefeuille (positions, risque, performance, dividendes) | 🟡 Q2 | 🟠 | 7 jalons | en cours — **J2 (positions) restant**, le reste ✅ | [→](chantiers/17-portefeuille.md) |
| 18 | Quantitatif : cartes, axe honnête, comparateur | 🟡 Q2 | 🟠 | 1 session | **fait** | [→](chantiers/18-quantitatif-fiche.md) |
| 19 | Section Dividende (rendements continus, zoom) | 🟡 Q2 | 🟠 | 1 session | **fait** | [→](chantiers/19-section-dividende.md) |
| 20 | Section Valorisation (calculatrice de prix juste) | 🟡 Q2 | 🟠 | 1 session | **fait** | [→](chantiers/20-valorisation-fiche.md) |
| 21 | **Thèse & Société** (document markdown + profil société) | 🟡 Q2 | 🟠 | 7 jalons | **fait** | [→](chantiers/21-these-societe.md) |
| 21.1 | Suivi : points de contrôle persistés + carte Thèse | 🟡 Q2 | 🟠 | 1 session | **fait** | [→](chantiers/21-these-societe.md#11-extension-211--bande-suivi) |
| 21.2 | Replier le plan de la thèse | 🟡 Q2 | 🟢 | 1 session | **fait** | [→](chantiers/21-these-societe.md#12-extension-212--replier-le-plan-de-la-thèse) |
| 21.3 | Poignée de bord du plan (ouverture/fermeture en cours de lecture) | 🟡 Q2 | 🟢 | 1 session | **fait** | [→](chantiers/21-these-societe.md#13-extension-213--poignée-de-bord-du-plan) |
| 21.4 | Densité « Suivi » & « Profil société » | 🟡 Q2 | 🟢 | 1 session | **fait** | [→](chantiers/21-these-societe.md#14-extension-214--densité-suivi--profil-société) |
| 22 | Document financier CSV exhaustif (toutes les métriques) | 🟡 Q2 | 🟠 | 1 session | **fait** | [→](chantiers/22-csv-comptes.md) |
| 23 | Import CSV robuste + staging piloté par l'IA | 🟡 Q2 | 🟢 | 2 sessions | **fait** | [→](chantiers/23-import-csv-ia.md) |
| 24 | **Calendrier du portefeuille en séances** + contexte unique | 🔴 Q3 | 🟠 | 2 sessions | **fait** | [→](chantiers/24-calendrier-portefeuille.md) |
| 25 | **Watchlist à tiers** + marges de sécurité + fenêtre de confiance + MCP | 🟡 Q2 | 🟠 | 2-3 sessions | **fait** | [→](chantiers/25-watchlist.md) |
| 25.1 | Watchlist : lier la référence à la performance 5 ans + popover | 🟡 Q2 | 🟠 | 1 session | **fait** | [→](chantiers/25.1-watchlist-reference.md) |
| 25.2 | Watchlist en total-return + prix juste à 12 % sur la droite | 🟡 Q2 | 🟠 | 1 session | **fait** | [→](chantiers/25.2-watchlist-total-return.md) |
| — | Screener (J0–J5ter ✅ · J6 Europe restant) | 🔵 Q3 | 🟠 | — | en cours | [→](chantiers/screener.md) |

### Sous-fiches Portefeuille (#17)

| # | Jalon | Statut | Fiche |
|---|---|---|---|
| 17.0 | Socle persistant + saisie (schéma v2, comptes, transactions) | **fait** | [→](chantiers/portefeuille/00-socle.md) |
| 17.1 | Résumé (TWR vs benchmark, top/flop 5) | **fait** | [→](chantiers/portefeuille/01-resume.md) |
| 17.2 | Positions (taille, PRU, consolidation « comme une entreprise ») | à faire | [→](chantiers/portefeuille/02-positions.md) |
| 17.3 | Risque (drawdown, matrice de corrélation) | **fait** | [→](chantiers/portefeuille/03-risque.md) |
| 17.4 | Performance (stats pondérées, mensuels, points d'entrée/sortie) | **fait** | [→](chantiers/portefeuille/04-performance.md) |
| 17.5 | Dividendes (reçus, rendement, yield on cost) | **fait** | [→](chantiers/portefeuille/05-dividendes.md) |
| 17.6 | Étiquettes (portefeuilles virtuels) | **fait** | [→](chantiers/portefeuille/06-etiquettes.md) |

### Sous-fiches MCP (#09)

| # | Jalon | Statut | Fiche |
|---|---|---|---|
| 09.0 | Socle (serveur `MCPServer`, transport stdio) | **fait** | [→](chantiers/mcp/00-socle.md) |
| 09.1 | Outils de lecture (stock, ratio, search, indices) | **fait** | [→](chantiers/mcp/01-outils-lecture.md) |
| 09.2 | Screener FR (`screen_french_stocks`) | **fait** | [→](chantiers/mcp/02-screener-fr.md) |
| 09.3 | Thèse d'entreprise (`write_thesis` + persistance) | **fait** | [→](chantiers/mcp/03-these-entreprise.md) |
| 09.4 | **Portefeuille (MCP-B)** + points de contrôle suivis | **fait** | [→](chantiers/mcp/04-portefeuille-suivi.md) |
| #23 | **Staging d'import CSV** (`propose_import`, validation humaine) | **fait** | [→](chantiers/23-import-csv-ia.md) |

> **Extensions actées sans fiche dédiée** (`PRD.md` §10) : **MCP-D DCF** et
> **MCP-E Monte-Carlo** — à spécifier au moment de les démarrer. **MCP-B** (Portefeuille) est
> désormais couvert par le jalon 09.4.

---

## 3. Ordre d'attaque recommandé

1. ~~**#03** — seul chantier Q1 (perte irréversible possible). À faire en premier.~~ ✅ fait
2. ~~**#08** — 20 minutes, et il protège tout le reste.~~ ✅ fait
3. ~~**#02** — prérequis technique de #03.~~ ✅ fait
4. ~~**#01** — débloque le diagnostic de tous les autres.~~ ✅ fait
5. ~~**#05** — à faire **avant** d'étendre le back (sinon la dette grandit avec le MCP).~~ ✅ fait
6. **#17** — le Portefeuille : reste **J2 (positions)**. MCP-B est déjà livré (#09.4).
7. ~~**#09** — la valeur produit, quand le socle est sain.~~ ✅ fait
8. Le reste (Q3) en batch, #12 abandonné.

---

## 4. Cycle de vie d'un chantier

```
idée → fiche créée depuis _gabarit.md + ligne dans l'index (statut : à faire)
     → branche dédiée (statut : en cours)
     → critères cochés un à un dans la fiche
     → note de reprise remplie
     → merge sur main (statut : fait)
```

**En fin de session**, toujours : mettre à jour le **statut** dans l'index et la **note de reprise**
dans la fiche. C'est ce qui permet de reprendre trois semaines plus tard sans rien réexpliquer.

**Plan d'exécution.** Quand un chantier est planifié, son plan vit dans
`aidd_docs/tasks/<yyyy_mm>/<yyyy_mm_dd>_<slug>/` (format AIDD : `plan.md`, phases, revue). La fiche
reste la **spec** et porte en §8 le chemin du plan et la branche ; l'index garde le statut produit.

**Traçabilité.** Les branches citées dans les fiches sont annotées « Branche (historique) » quand
le travail est clos. Ne jamais citer de SHA ni figer un décompte de commits : décrire le jalon.
Détail et justification : cf. `CLAUDE.md` §Workflow git.
