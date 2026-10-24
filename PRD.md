# PRD — « Obole » : outil perso d'analyse fondamentale long terme

> Document de cadrage produit. Statut : **spécification & prototypage** (v0.2 — 24/09/2026).
> Tout ce qui est marqué 🔶 est une décision ouverte / à challenger.
> **Nouveauté v0.2** : le PRD est réorganisé en **niveaux de traçabilité** (cf. §0) et la
> **feuille de route** (§10) intègre les évolutions futures (MCP, portefeuille, thèse, DCF,
> Monte-Carlo).

---

## 0. Comment lire ce PRD

Le PRD suit une **pyramide de traçabilité** à quatre niveaux. Chaque niveau **découle** du
niveau supérieur : rien n'existe sans une justification au-dessus de lui.

```
VISION            Pourquoi / où on va / la dette technique à éviter
   │  (chaque feature sert un objectif de vision)
   ▼
FEATURES          Quoi / périmètre fonctionnel (MVP → phases futures)
   │  (chaque brique d'archi existe pour servir une feature)
   ▼
ARCHITECTURE      Comment / couches, contrats, invariants
   │  (chaque invariant se prouve par un test)
   ▼
TESTS             Preuve / garde-fous (parité, calibration, e2e)
```

**Règles de lecture** :

- Une **fonctionnalité sans feature** est de la sur-ingénierie → elle sort du périmètre.
- Une **couche d'architecture sans feature à servir** est de la dette → elle ne se justifie pas.
- Un **test sans invariant à prouver** est orphelin → il ne protège rien.

Correspondance dans ce document : Vision → §1 ; Features → §4 (+ feuille de route §10) ;
Architecture → §7 / §7bis / §12 ; Tests → §11 et le garde-fou de calibration (§5.0).

---

## 1. Vision

### 1.1 Ce que Obole doit devenir

Deux choses, dans cet ordre :

1. **Un outil perso d'analyse fondamentale long terme** — reconstruire la méthode « Droite de
   Obole » pour mon usage personnel (fiche valeur, screener). *Réalisé.*
2. **Un poste de pilotage pour une IA** — via le **MCP**, une IA (Claude, etc.) consomme et
   **alimente** Obole : lire les analyses, remplir un portefeuille depuis un document de
   transactions, tenir une thèse à jour, construire un DCF, simuler en Monte-Carlo. Le MCP n'est
   pas un greffon : c'est **la colonne vertébrale des évolutions futures**.

### 1.2 Les briques futures (vision, non spécifiées ici)

Ces briques sont **actées comme direction** ; leur spécification viendra plus tard (cf. §10).

- **Portefeuille** — l'IA lit un document de transactions et remplit seule les positions.
- **Thèse vivante** — l'IA écrit, modifie et évalue une thèse, puis la confronte aux résultats
  réels (attentes vs réalisé).
- **DCF** — l'IA construit un modèle d'actualisation et le fait varier selon plusieurs hypothèses.
- **Monte-Carlo** — l'IA simule plusieurs scénarios et en tire une distribution de valeur.
- **Extension Europe** — élargir l'univers du screener au-delà de la France.

### 1.3 La dette technique comme principe de vision

Chaque évolution doit **réduire ou contenir** la dette technique, jamais l'aggraver. Concrètement :
toute nouvelle fonctionnalité **s'appuie** sur les couches existantes (`services/`), ne **duplique
jamais** une formule ni un seuil (`config.py` = source unique), et n'ajoute **aucune** couche
« au cas où ». La sobriété structurelle fait partie de la vision, au même titre que les features.

---

## 1bis. Contexte & intention

Recréer pour mon usage personnel un outil d'analyse boursière inspiré d'un outil commercial de référence (méthode de la « droite de régression » long terme), avec l'esthétique premium et épurée de **Baggr**.

Ce n'est **pas un SaaS** : pas d'auth multi-utilisateurs, pas de paiement, pas de statut presse/CPPAP, pas de contenu éditorial. Un seul utilisateur : moi. L'app tourne en local sur ma machine.

### Décisions déjà actées
| Sujet | Décision |
|---|---|
| Nature | Outil **perso / MVP**, mono-utilisateur, local |
| Lien avec la référence | Aucun (client/fan) — méthode reconstruite, pas de code/données internes |
| Source de données | **yfinance** (Python, gratuit) |
| Forme | **Web app locale** (backend Python + front web) |
| Style visuel | À la **Baggr** : moderne, premium, épuré, bi-thème clair/sombre |
| Méthode d'analyse | **Répliquer au mieux** la « droite d'Obole » |
| MVP | **Fiche valeur** d'abord, puis **screener** |
| Layout fiche | **Scroll unique sectionné** (style Baggr), pas d'onglets |
| Front | **Léger** (HTML + Alpine.js/htmx + Plotly), CSS soigné pour approcher Baggr |
| Portefeuille | **Réintroduit** (alimenté par l'IA via MCP, à partir d'un document de transactions fourni) — cf. §10 |
| Thèse vivante | **Actée** (écriture/évaluation par l'IA via MCP) — cf. §10 |
| DCF | **Acté** (modèle piloté par l'IA, multi-hypothèses) — cf. §10 |
| Monte-Carlo | **Acté** (simulation multi-scénarios par l'IA) — cf. §10 |
| Phase actuelle | **Spécification & prototypage** — le MCP est le pivot des évolutions |
| Process | **Spike de calibration d'abord** (Jalon 0) avant de figer les formules |

---

## 2. Objectifs & non-objectifs

### Objectifs (ce que l'outil DOIT faire)
1. Saisir un ticker → afficher une **fiche valeur** complète façon outil de référence.
2. Calculer et tracer la **droite de régression long terme** (échelle log, dividendes réinvestis en option) avec **bandes ±1σ / ±2σ**.
3. Donner des **indicateurs synthétiques notés** : distance en σ (décote/surcote), pente (perf annuelle), potentiel annualisé 5 ans / 10 ans, qualité de l'exploitation, tendance boursière.
4. Afficher les **comptes** disponibles (CA, marge op, résultat net, capitaux propres, ROE, CP/bilan, cash-flow) + TCAM.
5. **Cacher localement** les données (yfinance est lent et fragile).

### Non-objectifs (explicitement hors périmètre MVP)
- ❌ Comptes (multi-utilisateurs / auth)
- ❌ Paiement / abonnement
- ❌ Contenu éditorial, formation, articles
- ❌ Données temps réel intraday (on travaille en clôture quotidienne)
- ❌ Reproduction de l'historique comptable **10 ans** (yfinance ne donne que ~4-5 ans — voir §6)

> **Hors MVP mais actées** : le portefeuille, la thèse vivante, le DCF et le Monte-Carlo **ne
> sont pas abandonnés** — ce sont des **phases futures** portées par le MCP (cf. §1.2 et §10).
> Ils sont hors du périmètre MVP, pas hors du produit.

---

## 3. Personae & usage

**Persona unique : moi, investisseur particulier long terme.**
Workflow type :
1. J'ai une idée / je tombe sur une valeur → je tape le ticker.
2. Je regarde où le cours se situe par rapport à sa droite de régression (décoté ? surcoté ?).
3. Je vérifie la cohérence : la pente boursière est-elle soutenue par le ROE et la croissance des bénéfices ?
4. Je consulte le potentiel 5/10 ans et les comptes.
5. (Phase 2) Je screene une liste de valeurs pour trouver les plus décotées de qualité.
6. (Phase 3, via MCP) Je confie à une IA mes documents : elle remplit mon portefeuille, tient mes
   thèses à jour, construit des DCF et des simulations Monte-Carlo à partir des données Obole.

---

## 4. Périmètre fonctionnel

### Phase 1 — Fiche valeur (MVP)
Écran unique : barre de recherche ticker + fiche. Structure calquée sur le PDF de référence, onglets :

#### 4.1 Header
- Nom société, dernier cours, devise, ISIN/ticker, pays, secteur, capitalisation.
- Mini-sparkline.

#### 4.2 Graphe principal (le cœur)
- Cours en **échelle logarithmique**, historique max (20-30 ans selon dispo).
- **Droite de régression** superposée.
- **Bandes ±1σ et ±2σ** (canaux parallèles).
- Toggles : `Dividendes réinvestis` · `Moyennes mobiles` · `Synchroniser la régression avec la période affichée`.
- (V1.1) Objectif de cours consensus si dispo via yfinance (`info['targetMeanPrice']`). 🔶

#### 4.3 Indicateurs synthétiques (cartes notées)
- **Valorisation actuelle** : distance en σ → label (Très décotée / Décotée / Neutre / Surcotée / Très surcotée).
- **Performance passée** : pente annualisée de la régression + label.
- **Écart-type (volatilité long terme)** + label.
- **Tendance boursière** : haussière / neutre / baissière (pente + position récente).
- **Potentiel annuel à 5 ans** et **à 10 ans** + label.
- **Qualité de l'exploitation** : score basé sur ROE moyen, régularité du CA, structure de bilan.

> Formules détaillées en **§5**.

> ⚠️ **Pas de tableau de comptes brut** (style référence abandonné). À la place, **3 sections analytiques thématiques** orientées graphes « pour comprendre vite ». Type de graphe **mixte** : barres pour les flux (CA, FCF, résultat), lignes pour les ratios (marges, ROE…).

#### 4.4 Section RENTABILITÉ
Indicateurs de qualité économique, en graphes sur les années dispo :
- ROE, ROIC, ROA
- Marge brute / opérationnelle / nette
- Croissance du CA, croissance du FCF
> Objectif : voir d'un coup d'œil si l'entreprise est rentable et si ça progresse.

#### 4.5 Section FINANCE / SOLIDITÉ
Ratios de structure financière :
- Dette nette, Dette nette / EBITDA, gearing (dette/CP)
- Couverture des intérêts
- BFR (besoin en fonds de roulement) et son évolution
- Liquidité (current ratio)
> Objectif : l'entreprise est-elle solide / endettée ?

#### 4.6 Section VALORISATION
Multiples classiques, chacun en **valeur actuelle + médiane historique** (cher/pas cher vs son propre passé) :
- P/E, P/CA (P/S), P/B
- EV/EBITDA
- FCF yield, P/FCF
- PEG, rendement du dividende
> Pas de comparaison vs pairs au MVP (vient avec le screener, phase 2). Conceptuellement cohérent avec la droite de régression : on compare toujours **l'actuel à sa propre norme historique**.

> ⚠️ **Disponibilité yfinance** : ROIC, EV/EBITDA, dette nette, BFR, FCF demandent des postes bilan/cash-flow incomplets et limités (~4-5 ans). Certains seront calculés, d'autres approximés ou **N/A** avec badge de fiabilité (cf. §8).

#### 4.7 Cas spécial : sociétés financières (banques / assurances)
> Découvert via la fiche BNP des exemples : la référence affiche un **schéma de comptes différent** pour les financières.

- Une banque n'a **pas** de « chiffre d'affaires », ni de « marge opérationnelle », ni de BFR au sens classique.
- La référence affiche pour BNP : **Total de l'actif, Actif net, Bénéfice net, BNPA, Actif net/Total actif, ROA, ROE** (pas CA/marge op/CP-bilan).
- Ratios pertinents différents : P/B (cours/actif net) au lieu d'EV/EBITDA, ROA/ROE au lieu de marges, etc.
- ⇒ **Détection du type d'entreprise** (secteur `Banques`/`Assurance` via yfinance `info['sector']`) → **2 schémas de fiche** : « industriel/commercial » (défaut) vs « financier ». Les sections Rentabilité/Finance/Valorisation adaptent leurs métriques.
- 🔶 MVP : on peut livrer le schéma standard d'abord, puis ajouter le schéma financier. Mais l'architecture (`models.py`) doit prévoir le **polymorphisme de schéma de comptes** dès le départ pour ne pas tout refactorer.

### Phase 2 — Watchlist + Screener
- **Watchlist** (#25) : 3 **tiers de conviction** fixes, une appartenance par ticker, ajout/déplacement depuis la fiche. Classement par **marge de sécurité** contre le prix juste enregistré (calculatrice) ou, à défaut, la droite de référence ; **position σ** et **écart à la droite** sur les prix bruts. **Fenêtre de confiance par titre** (date de départ → aujourd'hui, 20 ans par défaut), qui pilote aussi le « Prix juste » du Résumé. La watchlist est exposée au MCP en lecture et en organisation (jamais la référence ni le prix juste).
- **Tag « en portefeuille »** : marquer une valeur de la watchlist comme détenue (simple booléen/label, pas de suivi de lignes ni de valorisation).
  > **Lien avec le Portefeuille (Phase 3)** : le tag est un **raccourci manuel provisoire** (booléen, sans lignes ni valorisation). Quand le **Portefeuille** réel (MCP-B) arrive, il devient la **source de vérité** : le tag en est dérivé (valeur présente dans les positions) plutôt que saisi à la main. Le filtre screener « tag portefeuille » s'appuiera alors sur les positions réelles.
- **Screener** : appliquer des filtres sur la watchlist (et/ou un univers de tickers fourni).
  - Filtres : distance σ (décote), ROE moyen, pente, potentiel 5 ans, secteur, capi, tag portefeuille.
  - Tableau triable → clic = ouvre la fiche.

### Phase 3 — Pilotage IA (briques futures) 🔶
Ces briques sont **actées comme direction** (cf. §1.2) ; leur **spécification détaillée viendra
plus tard** (fiches chantiers dérivées de la feuille de route §10). Elles s'appuient toutes sur le
MCP (§12) comme surface d'accès et sur `services/` pour la logique.

| Brique | Ce que fait l'IA | Données manipulées | État |
|---|---|---|---|
| **Portefeuille** | lit un document de transactions, remplit les positions | transactions + positions | à spécifier |
| **Thèse vivante** | écrit/modifie la thèse, l'évalue vs le réalisé | thèses + évaluations | à spécifier |
| **DCF** | construit le modèle (croissance, marge, actualisation) et le fait varier | paramètres DCF | à spécifier |
| **Monte-Carlo** | simule plusieurs hypothèses → distribution de valeur | distributions d'hypothèses | à spécifier |

**Principe transverse** : l'IA est le **cerveau** (raisonnement, rédaction, hypothèses) ; Obole
fournit les **données** et la **persistance**. Le serveur ne fait **pas** d'appel LLM (cf. §12.1).

---

## 5. Spécification mathématique de la « droite d'Obole »

> ✅ **CALIBRÉE & VALIDÉE** sur Pernod Ricard (spike Jalon 0, voir `spike_calibration.py`).
> Sur prix de clôture brut, historique complet : **distance σ = −3.81 (exact)**, potentiel 5 ans = 32.5% (cible 32.6%), potentiel 10 ans = 19.0% (cible 20.0%). La méthode ci-dessous reproduit Obole.

### 5.0 Résultats de calibration (réf.)
Chaque indicateur n'utilise PAS la même série — c'est la clé. ✅ = source retenue.

| Indicateur | Cible PDF | Close brut (hist. complet) | Adj Close (div réinvestis) |
|---|---|---|---|
| Distance σ (z) | −3.81 | **−3.81** ✅ | −3.72 |
| Potentiel 5 ans | 32.6% | **32.5%** ✅ | 34.0% |
| Potentiel 10 ans | 20.0% | **19.0%** ✅ | 20.8% |
| Écart-type | 30.1% | 32.8% | 32.2% (résiduel ~2pts, cf. infra) |
| **Perf passée** | 8.5% | 6.8% | **8.9%** ✅ |

> ⚠️ **Piège levé** : la « perf passée » 8.5% se lit sur la droite **div réinvestis (8.9%)**, PAS sur la droite brute (6.8%). Mettre 6.8% en face de « perf passée » serait une erreur de lecture — c'est la perf hors dividendes. Logique : la perf de l'actionnaire inclut les dividendes.

> ⚠️ **Pente ≠ CAGR** : la perf affichée est la **pente de la régression log**, pas le CAGR point-à-point. Pour Pernod, CAGR Adj Close = 6.78% mais pente Adj Close = 8.92%. Toujours utiliser la pente.

**Lecture** : la **valorisation/distance σ et les potentiels** se calculent sur **prix brut, historique complet**. La **perf passée** affichée par Obole se calcule **dividendes réinvestis** (Adj Close → 8.9% ≈ 8.5%). ⇒ on calcule **les deux droites** ; le toggle « dividendes » bascule l'affichage, et la carte « perf passée » utilise la version div réinvestis.

**Fréquence d'échantillonnage** : testée (spike `spike_sampling.py`). Le **quotidien** donne le z exact (−3.81) ; hebdo et mensuel dégradent légèrement. ⇒ on reste en **quotidien**. L'échantillonnage n'explique PAS l'écart résiduel sur l'écart-type.

**Écart-type (30.1% vs ~32.8% calculé)** : écart résiduel non résolu (~2 pts), indépendant de la fréquence et du choix brut/ajusté. Hypothèses restantes (fenêtre de régression légèrement différente, ou σ calculé sur une sous-période). **Jugé acceptable** : n'affecte ni la décision d'investissement, ni le z (exact), ni l'architecture. Non bloquant — on n'investit pas plus de temps en reverse-engineering. À recaler éventuellement plus tard sur un échantillon de valeurs.

> Reconstruction validée. Détails ci-dessous.

### 5.1 Série de prix
- Prix de clôture quotidiens, **historique max** (yfinance remonte à 2000 pour Pernod ; on prend tout, on ne tronque PAS à 2003).
- yfinance `auto_adjust=False` → on récupère `Close` (brut) **et** `Adj Close` (dividendes+splits réinvestis).
- On calcule **deux régressions** : une sur `Close` (valorisation, distance σ, potentiels) et une sur `Adj Close` (perf passée affichée, toggle dividendes). ✅ validé en calibration.

### 5.2 Régression en échelle log
On régresse `y = ln(P)` contre le temps `t` (en années).
- `ln(P_t) ≈ a + b·t`
- **Pente `b`** → performance annualisée continue. Performance annuelle simple = `e^b − 1`.
- Droite ajustée : `P̂_t = e^(a + b·t)`.
- Méthode : moindres carrés ordinaires.

### 5.3 Écart-type & bandes
- Résidus `r_t = ln(P_t) − (a + b·t)`.
- **σ = écart-type des résidus** (en unités log).
- Bandes : `P̂_t · e^(±k·σ)` pour `k ∈ {1, 2}`.
- L'« écart-type (taille) » noté par l'outil d'origine = `e^σ − 1` en % (validé : Pernod σ → 30.1%).

> **Seuils ci-dessous calibrés sur 6 fiches réelles** (Pernod, Total, BNP, Danone, Renault, STMicro — voir `spike_seuils.py`, 100% concordant). ⚠️ = borne sans observation directe, hypothèse à confirmer.

### 5.3bis Écart-type (taille) → label volatilité ✅ calibré
Obs : Danone 15.8/Total 18.7 = Faible · Pernod 30.1 = Moyen · BNP 41.2/Renault 51.0 = Plutôt élevée · STMicro 80.6 = Elevée.
- `< 20%` : **Faible**
- `20–35%` : **Moyen**
- `35–55%` : **Plutôt élevée**
- `≥ 55%` : **Elevée**

### 5.4 Distance en écart-type (valorisation actuelle) ✅ calibré
- `z = r_aujourd'hui / σ = (ln(P_actuel) − (a + b·t_actuel)) / σ`.
- Pernod : z = **−3.81** identique au PDF. Formule confirmée.
- Labels (obs : −3.81 Décotée · −0.96/−0.17 Légèrement sous-cotée · +1.02/+1.38/+1.79 Surcotée) :
  - `z ≤ −2` : **Décotée** (⚠️ une « Très décotée » possible plus bas, non observée)
  - `−2 < z ≤ −1` : **Sous-cotée** ⚠️ (zone non observée)
  - `−1 < z < 0` : **Légèrement sous-cotée**
  - `0 ≤ z < 0.5` : **Légèrement surcotée** ⚠️ (borne sup à confirmer)
  - `z ≥ 0.5` : **Surcotée** (le plus bas observé « Surcotée » = 1.02 ; borne réelle entre 0 et 1.02)

### 5.5 Performance passée → label ✅ calibré
Sur la pente Adj Close (div réinvestis), en %/an. Obs : Total 1.2/Renault 1.9/BNP 3.0 = Médiocre · Danone 5.7/Pernod 8.5/STMicro 8.9 = Moyen.
- `< 4%` : **Médiocre**
- `4–10%` : **Moyen**
- `≥ 10%` : **Bien** ⚠️ (borne haute non observée)

### 5.6 Potentiel annualisé 5 / 10 ans (formule + label) ✅ calibré
Formule (validée Pernod : 5a = 32.5% vs 32.6%, 10a = 19.0% vs 20.0%) :
- Cible à H : `P̂_(t+H) = e^(a + b·(t_actuel + H))` (point sur la droite). Potentiel = `(P̂_(t+H)/P_actuel)^(1/H) − 1`.
- Labels (même échelle 5a et 10a) — obs : <0 Mauvais · 0.4 Médiocre · 5.9/6.0/6.2 Moyen · 10.3 Bien · 20/32.6 Excellent :
  - `< 0%` : **Mauvais**
  - `0–5%` : **Médiocre**
  - `5–10%` : **Moyen**
  - `10–15%` : **Bien**
  - `≥ 15%` : **Excellent**

### 5.7 Tendance boursière ✅ calibré (MM11 / MM200)
Indépendante de la valorisation (momentum). **Croisement de deux moyennes mobiles** sur le cours de clôture :
- `MM11` = moyenne mobile 11 jours · `MM200` = moyenne mobile 200 jours.
- **Haussière si `MM11 > MM200`, sinon Baissière.** (binaire, pas de Neutre observé)
- **Validé 5/5** sur les fiches réelles (Total/BNP/STMicro Haussière, Danone/Renault Baissière + Pernod cohérent) — voir `spike_tendance.py`.

### 5.8 Qualité de l'exploitation (score composite) ✅ conçu & testé
> Score **raisonné** (pas une réplication de la référence — pas de référence dispo dans les PDF). Validé sur les 6 valeurs : classement sensé (Renault Médiocre à 16 ; Pernod/Danone/Total/STMicro/BNP Bon 67-71). Voir `spike_qualite.py`.

Score **0-100**, somme de 4 composantes :
| Composante | Calcul | Poids max |
|---|---|---|
| ROE moyen | `clamp(roe_moy, 0, 15)/15 × 40` | 40 |
| ROE dernière année (anti-effondrement) | `clamp(roe_last, 0, 15)/15 × 25` | 25 |
| Régularité CA | `clamp(20 − nb_années_baisse×2, 0, 20)` | 20 |
| Solidité bilan | industriel : `clamp((cp_bilan−10)/30×15,0,15)` · financier : 15 (neutralisé) | 15 |

Labels : `<35` **Médiocre** · `35–55` **Moyen** · `55–75` **Bon** · `≥75` **Excellent**.

> 🔶 Amélioration optionnelle (post-MVP) : pénaliser plus fort l'**écart ROE moyen ↔ ROE récent** (STMicro 18%→1% est masqué par la moyenne). Le score discrimine déjà bien.

### 5.9 « Potentiel de l'action » (2ᵉ score de référence) 🔶
Visuel non extractible des PDF. Vraisemblablement dérivé du potentiel 5/10 ans (§5.6). Pour le MVP : traité comme le label de §5.6.

### 5.10 Cohérence pente ↔ fondamentaux (thèse de référence)
Indicateur de **cohérence** : comparer `b` (pente boursière annualisée) à la croissance des bénéfices et au ROE. Affiché comme un check visuel (« le cours suit-il les bénéfices ? »).

---

## 6. Données — yfinance

### Ce que yfinance fournit (fiable)
- **Cours historique** : `Ticker.history(period="max")` → 20-30 ans → ✅ droite de régression OK.
- **Dividendes / splits** : ✅ (prix ajustés).
- **`info`** : capi, secteur, PER, beta, targetMeanPrice, dividendYield… (champs parfois manquants).

### Limites à assumer
- **Comptes annuels : ~4-5 ans seulement** (`financials`, `balance_sheet`, `cashflow`). ⇒ le tableau « 10 ans » d'Obole **n'est pas reproductible**. On affiche ce qu'on a.
- **Fragilité** : yfinance casse quand Yahoo change son backend ; rate-limits. ⇒ **cache local obligatoire** + gestion d'erreur propre.
- **ISIN / champs exotiques** : pas toujours présents.

### Stratégie de cache ✅
- Cache disque par ticker : prix + comptes + info.
- TTL : **prix = 1 jour**, **comptes/info = 7 jours**. **Bouton refresh manuel** force la MAJ.
- Politique : **cache agressif** — on ne re-fetch jamais en intra-journée (inutile pour du long terme). Minimise les appels réseau (= sobriété).

---

## 7. Architecture technique

| Couche | Choix | Raison |
|---|---|---|
| Langage | **Python** | yfinance ; numpy/pandas naturels |
| Backend | **FastAPI** + uvicorn | léger, sert l'API + le front, async |
| Calculs | numpy / pandas | régression, σ, ratios |
| Cache | **SQLite** (1 fichier) | persistance locale simple, zéro serveur |
| Front | **HTML + Alpine.js** servi par FastAPI | léger, look clair premium via CSS |
| Graphes | **Plotly** | échelle log + bandes en aplat |
| Lancement | `uvicorn` sur `localhost` | mono-utilisateur local |

---

## 7bis. Principes d'ingénierie (calibrés outil perso local)

> Niveau **Architecture** de la pyramide (§0). Ces principes existent pour **servir les features**
> (§4) : chaque couche a une raison d'être, aucune n'est « au cas où » (cf. §1.3, la dette comme
> principe de vision).
>
> Objectif : code **qui évolue bien, efficace énergétiquement, robuste** — SANS sur-ingénierie. On applique les grands principes *seulement là où ils servent ce projet*. Pas de microservices, pas d'abstractions spéculatives, pas de couches « au cas où ».

### 7bis.1 Séparation en couches (la règle structurante n°1)
Dépendances **à sens unique** : `web → api → services → engine → data`. Le cœur ne connaît pas l'extérieur.

```
src/obole/
  data/        # I/O : fetch yfinance + cache SQLite. SEUL endroit qui touche le réseau/disque.
  engine/      # Cœur métier PUR : régression, σ, z, potentiels, ratios, scores.
               # Aucune I/O, aucun import yfinance/fastapi. Fonctions pures sur des DataFrames.
  services/    # Cas d'usage : orchestre data+engine (analyse, screener). Appelé par api/ et le MCP.
  api/         # FastAPI : expose JSON. Pas de logique métier ici.
  web/         # HTML/Alpine/CSS/Plotly. Pas de calcul ici (hors recalcul à la volée du graphe).
  mcp/         # surface de pilotage IA : outils MCP vers services/engine/data.
               # Colonne vertébrale des évolutions futures (§10).
  config.py    # constantes (TTL cache, seuils labels, couleurs) centralisées
  models.py    # dataclasses typées (StockAnalysis, Indicators...) = contrats entre couches
```
**Pourquoi** : `engine/` pur = testable sans réseau, recalculable, réutilisable par la fiche ET le screener. C'est ce qui rend le code évolutif. C'est LE principe qui compte ici.

### 7bis.2 Robustesse (yfinance est fragile — non négociable)
- **Toute I/O yfinance est isolée dans `data/`** et enveloppée : try/except, timeout, retry léger (1-2 essais avec back-off court).
- **Dégradation gracieuse** : une donnée manquante (EV/EBITDA, BFR…) → `None` propagé proprement → affichée « N/A » avec badge, **jamais un crash**. Le cœur ne suppose jamais qu'un champ existe.
- **Modèles typés** (`models.py` + type hints) : les champs optionnels sont `Optional[...]` explicites → on est forcé de gérer l'absence.
- **Validation d'entrée** : ticker inconnu → erreur claire renvoyée au front, pas une stack trace.

### 7bis.3 Efficacité énergétique = sobriété des I/O et du calcul
C'est ici que ça se joue (pas dans la micro-optimisation CPU) :
- **Cache agressif** (§6) : le coût dominant est l'appel réseau yfinance. On le minimise → moins de réseau = plus sobre.
- **Mémoïsation des calculs** : indicateurs calculés à la demande puis **mis en cache tant que la donnée source est inchangée** (clé = ticker + date de fetch). Pas de recalcul à chaque réouverture.
- **Calcul vectorisé** numpy/pandas (pas de boucles Python sur les séries de prix).
- **Pas de polling, pas de tâche de fond au repos** : rien ne tourne quand tu ne regardes pas une fiche. (Le pré-calcul watchlist sera *opt-in*, réservé au screener.)
- **Lazy** : on ne fetch/calcule une section (ex. comptes) que si elle est demandée.

### 7bis.4 Principes « propres » qu'on applique (et ceux qu'on s'interdit)
**On applique** (rapport bénéfice/coût positif pour un solo local) :
- **DRY raisonnable** : un seul module `engine/regression.py`, réutilisé partout. Pas de copier-coller des formules.
- **Fonctions courtes et nommées** par ce qu'elles calculent (`distance_sigma`, `potentiel_annualise`).
- **Constantes centralisées** dans `config.py` (les seuils de labels qu'on calera, les TTL, la charte couleur). Aucun « nombre magique » éparpillé.
- **Tests sur le cœur** : `engine/` testé (le test de non-régression Pernod `z = −3.81` est le garde-fou). On ne teste PAS le front ni yfinance (mock).
- **Type hints** partout dans `engine/` et `models/`.

**On s'interdit** (sur-ingénierie inutile ici) :
- ❌ Pas d'injection de dépendances / interfaces abstraites « pour plus tard ». YAGNI.
- ❌ Pas de couche ORM lourde (SQLite brut ou un helper de 30 lignes suffit).
- ❌ Pas d'archi microservices, pas de message queue, pas de Docker obligatoire.
- ❌ Pas d'abstraction « multi-source de données » tant qu'on n'a que yfinance (mais `data/` isolé rend l'ajout futur facile sans le préparer aujourd'hui).
- ❌ Pas d'auth/sécurité réseau (localhost, un seul utilisateur).

### 7bis.5 Outillage minimal
- Gestion deps : `requirements.txt` (ou `pyproject` + `uv` si tu veux). Versions épinglées (yfinance casse → on contrôle quand on met à jour).
- Tests : `pytest` sur `engine/`.
- Format/lint léger : `ruff` (rapide, un seul outil format+lint).
- Lancement : un script `run.py` / `make run` → `uvicorn`.

---

## 8. Design / UI — style clair premium (esprit Baggr, version claire)

> ✅ **Volet UI verrouillé.** Direction : épure premium claire, type Stripe/Linear/Baggr-light. Tout est en thème **clair uniquement**.

### 8.1 Charte visuelle
| Élément | Valeur |
|---|---|
| Thème | **Clair uniquement** (pas de mode sombre) |
| Fond page | `#F7F8FA` (blanc cassé / gris très clair) |
| Cartes | `#FFFFFF`, coins arrondis (~12px), ombre douce très légère |
| Bordures | grises très fines `#E5E7EB` |
| Accent UI (boutons, liens, actif, courbe du cours) | **Bleu `#2563EB`** |
| Typo | **Inter** (chiffres tabulaires pour alignement) |
| Densité | **Aérée / spacieuse** : beaucoup d'espace blanc, gros chiffres |

### 8.2 Code couleur sémantique : **bleu = bien / rouge = mal** (pas de vert)
Convention unique sur toute l'app :
- **Valorisation** : décoté = **bleu**, surcoté = **rouge**, neutre = gris.
- **Autres indicateurs** (ROE, marges, potentiel, qualité, solidité…) : favorable = **bleu**, défavorable = **rouge**, neutre = gris.
- ⚠️ Nuance pour éviter la confusion avec l'accent : accent UI = bleu vif `#2563EB` ; **signal positif** = via **fond bleu pâle** (`#EFF6FF`) + texte bleu foncé, pour le distinguer d'un simple lien/bouton.
- Signal négatif : rouge `#DC2626` sur fond rouge pâle `#FEF2F2`.

### 8.3 Layout de la fiche (scroll unique sectionné — pas d'onglets)
De haut en bas :
1. **Barre de recherche** en haut (ticker/nom, autocomplétion) — entrée principale de navigation.
2. **Header valeur** : nom, cours, devise, pays, secteur, capi + badge fiabilité données.
3. **Graphe héro pleine largeur** : cours en échelle log + droite de régression + **bandes ±1σ/±2σ en aplats translucides dégradés** (bleu pâle sous la droite = zone décote, rouge pâle au-dessus = zone surcote). Toggles dividendes / moyennes mobiles / synchro période.
4. **Rangée de cartes KPI notées** (gros chiffre + label coloré) : jauge Valorisation (distance σ), Potentiel 5 ans, Potentiel 10 ans, Perf passée, Tendance, Qualité.
5. **Section CROISSANCE & TENDANCE** — cf. §4.4
6. **Section RENTABILITÉ & EFFICIENCE** — cf. §4.5
7. **Section SOLVABILITÉ** — cf. §4.6
8. **Section VALORISATION** (multiples + PEG) — cf. §4.7
9. **Section DIVIDENDE & RETOUR À L'ACTIONNAIRE** — cf. §4.8

### 8.4 Composants clés
- **Carte KPI** : gros chiffre (Inter, tabular), label coloré dessous selon §8.2.
- **Graphes de section (mini-charts)** : Plotly dans une grille `auto-fit`, hauteur 220px. Règles de typage (app.js) :
  - **Combo** : barres (flux) + ligne (ratio) sur axe Y secondaire. Barres en bleu accent, ligne en ambre avec area fill `rgba(245,158,11,.08)`. Axe secondaire titre + couleur.
  - **Multi** : N lignes+marqueurs. Palette unifiée `[bleu, teal, violet, ambre, or]`.
  - **Bars** : si ≤6 points → lignes+marqueurs (area fill) ; sinon barres groupées.
  - **Mono** : ratio → ligne+area fill ; montant → barres (sauf si ≤6 points → ligne).
  - **Dividende** : barres bleues, pleine largeur (__wide__).
  - **Rachats** : lignes+marqueurs bleus avec area fill, pleine largeur (__wide__). **Jamais en rouge** : les rachats ne sont pas un signal négatif.
- **Badge de fiabilité** : indique quand une donnée manque ou que l'historique est court (ex. « comptes : 5 ans dispo », « EV/EBITDA : N/A »). Petit, gris, non intrusif mais toujours présent.
- **Recherche** : autocomplétion sur ticker/nom.
- **Info-bulles** : chaque carte a un bouton ⓘ/✕ qui déroule une explication claire de la métrique.

### 8.5 Conventions design & palette
- **Rachats d'actions** : toujours en bleu (`C.accent`), jamais en rouge. Les rachats sont un retour à l'actionnaire, pas un signal négatif.
- **Graphiques ≤6 points** : toujours en ligne+marqueurs, jamais en barres (sinon aspect histogramme vide).
- **Area fill** : ajouté sous toutes les courbes simples (mono, combo, rachats) avec une opacité de 6-8%, pour un rendu plus premium (inspiré Baggr).
- **Multi-séries** : pas d'area fill (évite les superpositions illisibles).
- **Palette ordonnée** : `[#2563EB (bleu), #0D9488 (teal), #7C3AED (violet), #F59E0B (ambre), #F59E0B (or)]` — pas de rouge ni de vert dans la palette catégorielle.
- **Cartes « wide »** (pleine largeur dans la grille) : dividend-kpi, dividend-hist, buyback-hist. Les échelles temporelles très différentes (dividendes 20-40 ans vs rachats 4-5 ans) sont séparées visuellement en largeur.

### 8.6 Stack front
- Front **léger** : HTML + **Alpine.js** (interactions) servi par FastAPI, **Plotly** pour tous les graphes (gère l'échelle log + aplats de bandes).
- CSS custom soigné (variables = la charte §8.1) pour atteindre le rendu premier-de-classe malgré la légèreté.

---

## 9. Risques & points ouverts

Les points ouverts sont reclassés **par niveau** (cf. §0).

### Vision
| # | Risque / question | Impact |
|---|---|---|
| Q3 | Périmètre exact des briques futures (portefeuille, thèse, DCF, Monte-Carlo) | À spécifier par fiches (§10) |

### Features
| # | Risque / question | Impact |
|---|---|---|
| Q1 | Labels/seuils des scores (qualité, σ, tendance) | À caler ensemble |
| Q2 | Définition exacte du « potentiel 5/10 ans » pour matcher la référence | À caler ensemble |
| Q4 🔶 | Portefeuille : modèle de données (transactions vs positions, devises, frais) | À trancher |
| Q5 🔶 | Thèse : sémantique de l'évaluation « attentes vs réalisé » | À trancher |
| Q6 🔶 | DCF : FCFF vs FCFE, horizon, WACC | À trancher |
| Q7 🔶 | Monte-Carlo : variables simulées (croissance, marge, multiple de sortie) | À trancher |

### Architecture
| # | Risque / question | Impact |
|---|---|---|
| R1 | Formules de la référence non publiques → mes calculs peuvent ne pas matcher les chiffres affichés | Moyen — on calibre sur exemples (Pernod) |
| R2 | yfinance casse / rate-limit | Élevé sur la durée — mitigé par cache |
| R3 | Comptes limités à ~4-5 ans | Moyen — on assume, ou source comptable complémentaire plus tard 🔶 |
| R4 | Choix front (React vs léger) | Faible — affecte délai |

---

## 10. Feuille de route

> Table unique, alignée **vision → features**. Chaque ligne = un futur chantier (une branche
> dédiée, merge `--no-ff`). Le **détail** de chaque brique sera spécifié dans sa fiche, pas ici.
> Statut : ✅ fait · 🔶 à faire.

### Fondations (web, mono-utilisateur)

| Étape | Objectif | Dépend de | Statut |
|---|---|---|---|
| **J0** | Spike de calibration (Pernod `z=−3.81`) | — | ✅ |
| **J1–J5** | Fiche valeur, watchlist, screener, indices | J0 | ✅ |
| **#15** | Couche `services/` (orchestration hors `api/`) | J1–J5 | ✅ |
| **#06** | Source unique des seuils (`/api/meta`) | #15 | ✅ |
| **#04** | Découpage du front (modules ES natifs) | #06 | ✅ |
| **J6 Europe** | Élargir l'univers du screener au-delà de la France | J1–J5 | 🔶 |

### Pilotage IA (MCP — colonne vertébrale des évolutions)

| Étape | Objectif | Dépend de | Statut |
|---|---|---|---|
| **MCP-A** | Socle (serveur `MCPServer` SDK v2, stdio) + outils de **lecture** (stock, ratio, search, indices) | #15 | ✅ |
| **MCP-B** | **Portefeuille** : l'IA remplit les positions depuis un doc de transactions | MCP-A | ✅ |
| **MCP-C** | **Thèse vivante** : écriture, modification, évaluation (attentes vs réalisé) | MCP-A | 🔶 |
| **MCP-D** | **DCF** : modèle piloté par l'IA, multi-hypothèses | MCP-A | 🔶 |
| **MCP-E** | **Monte-Carlo** : simulation multi-scénarios → distribution de valeur | MCP-A | 🔶 |

> **Ordre** : MCP-A d'abord (débloque tout) ; MCP-B → MCP-E ensuite, chacun spécifié par sa fiche.
> Le screener FR côté MCP (fiche `mcp/02`) est un complément de lecture rattachable à MCP-A.
>
> **Traçabilité** : les fiches `chantiers/mcp/00`→`04` couvrent MCP-A (socle, lecture, screener),
> la thèse et la brique **Portefeuille (MCP-B)** (jalon 09.4, mergé sur `main`). Les briques
> **DCF (MCP-D)** et **Monte-Carlo (MCP-E)** — ainsi que **J6 Europe** — n'ont **pas encore de
> fiche** : à créer depuis `chantiers/_gabarit.md` au moment de les démarrer. Les lignes ci-dessus
> sont la **source** dont les fiches découleront.

### Chantiers transverses (dette & robustesse)

| Étape | Objectif | Statut |
|---|---|---|
| **#07** | Tests manquants (`data/indices.py`, couverture) | 🔶 |
| **#10** | Nettoyage doc (PRD obsolète) | 🔶 |
| **#11** | Retry SQLite sur `database is locked` | 🔶 |

---

## 11. Critères d'acceptation du MVP (Jalon 1)

> Niveau **Tests** de la pyramide (§0). Ces critères prouvent les invariants d'architecture (§7bis).
> **Statut : validés** (Jalon 1 livré — cf. §10).

- [x] Je tape `RI.PA` (Pernod) → fiche s'affiche en < 3 s (cache chaud).
- [x] Graphe log + droite + bandes ±1/±2σ corrects visuellement.
- [x] Distance σ affichée et cohérente avec l'ordre de grandeur de référence (négative & forte pour Pernod mi-2026).
- [x] Pente annualisée, potentiel 5/10 ans, comptes dispo affichés.
- [x] Fonctionne sur ≥ 5 tickers de pays/devises différents sans crash.
- [x] Erreur propre si ticker inconnu / données manquantes.

### Traçabilité invariant ↔ test

Chaque invariant d'architecture se prouve par un test (cf. §0). Exemples :

| Invariant (archi) | Test qui le prouve |
|---|---|
| Calibration « droite d'Obole » figée | `tests/test_calibration_network.py` (Pernod `z=−3.81`) |
| `engine/` pur (zéro I/O) | absence d'import `data/`/`services/` dans `engine/` (grep) |
| Seuils à source unique (`config.py` → `/api/meta`) | `web-tests/labels-parity.test.js` |
| Front sans build, `fetch` centralisés | `web-tests/modules.test.js` (0 fetch hors `api.js`, `app.js` < 500 l.) |
| Parité régression Python ↔ JS | `web-tests/regression-parity.test.js` + fixture |
| MCP ne touche pas `web/`/`api/` | grep sur `mcp/` (à venir avec MCP-A) |

---

## 12. Projet MCP (surface de pilotage IA)

> **Statut : acté.** Le MCP est **la colonne vertébrale des évolutions futures** (cf. §1.1 et §10),
> développé en **cohérence stricte** avec l'outil existant — pas un greffon.

## 12.1 Nature & principes
- **C'est la même app, une surface de plus.** Le serveur MCP n'est **pas** un produit séparé : c'est une couche d'accès qui permet à une IA (Claude, etc.) de **consommer ET d'alimenter** Obole sans passer par le front web.
- **L'IA est le cerveau, Obole fournit les données et la persistance.** Le serveur ne fait **aucun** appel LLM : il expose des données et des opérations ; l'IA cliente raisonne, rédige et propose (thèse, hypothèses DCF, scénarios Monte-Carlo).
- **Invariants non négociables** :
  - Réutiliser `services/` + `engine/` + `data/` ; **aucune duplication** de formule ni de seuil.
  - Respecter la règle `web → api → services → engine → data` : le MCP est une couche de transport à sens unique vers `services`/`engine`/`data`, il ne contourne pas le cœur.
  - Les seuils restent **exclusivement** dans `config.py` (source unique, exposée au front par `/api/meta`). Le MCP ne définit **aucun** seuil.
  - Le test de calibration réseau (Pernod `z = −3.81`) et les tests non-network restent **verts**.

## 12.2 Périmètre (2 familles)

**Famille 1 — Lecture** (exposer l'existant)
1. **Lecture & indices** — analyse fiche (`stock`), ratio A/B, recherche, CRUD complet des indices personnalisés. L'IA peut **composer ses propres indices**.
2. **Screener FR** — `screen_french_stocks(filters)` sur un **univers FR éditable**, filtres = seuils PRD §5 (σ, ROE, potentiels, capi, secteur). Tableau trié. Cache agressif obligatoire (un scan = N appels yfinance).

**Famille 2 — Écriture & calcul pilotés par l'IA** (les briques futures, cf. §4 Phase 3)
3. **Portefeuille** — l'IA extrait les transactions d'un document fourni par l'utilisateur et les **importe** (outil d'import à validation stricte). Le serveur **ne parse pas** le document : c'est l'IA qui structure.
4. **Thèse vivante** — prompt structuré (pitch, bull/bear, métriques clés, catalyseurs, points de contrôle) + **persistance SQLite** (`save/list/get/delete`), et **évaluation** attentes vs réalisé.
5. **DCF** — l'IA fournit les hypothèses (croissance, marge, WACC, horizon) ; Obole calcule et persiste le modèle, et le fait varier.
6. **Monte-Carlo** — l'IA définit les distributions ; Obole simule et renvoie la distribution de valeur.

> Chaque brique de la famille 2 est **spécifiée dans sa propre fiche** (§10), pas ici.

## 12.3 Règles d'ingénierie (miroir §7bis)
- Les outils MCP sont des **verbes** aux docstrings descriptives (la docstring = la doc de l'IA) ; pas de logique métier dans les outils (délégation à `engine`/`services`).
- Transport : **stdio** en local (défaut), **streamable-http** en option.
- Le MCP ne touche jamais `web/` ni `api/app.py` (sauf à exposer un outil qui appelle l'API existante, jamais l'inverse).
- Toute entrée venue de l'IA est **hostile par défaut** : validation stricte (schémas) avant persistance.
- L'introduction d'un outil de lecture ne suppose **aucun** nouvel appel réseau non-cache.

## 12.4 Points ouverts 🔶
- Q : univers FR initial = CAC 40 + MidCaps FR (éditable) ou base watchlist existante ?
- Q : modèle de données du portefeuille (transactions vs positions, devises, frais) — cf. Q4 §9.
- Q : méthode d'évaluation de la thèse (attentes vs réalisé) — cf. Q5 §9.
- Q : périmètre du DCF (FCFF/FCFE, horizon, WACC) — cf. Q6 §9.
- Q : variables simulées en Monte-Carlo — cf. Q7 §9.

> **Décision prise (ex-point ouvert)** : l'écriture de la thèse est un **prompt** que l'IA cliente
> déroule avec les données de `get_stock_analysis` — **aucun appel LLM côté serveur** (cf. §12.1).
> Idem pour DCF et Monte-Carlo : l'IA fournit hypothèses/distributions, Obole calcule et persiste.
