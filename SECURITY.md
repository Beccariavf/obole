# Politique de sécurité

## Signaler une vulnérabilité

**N'ouvrez pas d'issue publique.** Utilisez l'onglet *Security → Report a vulnerability* du
dépôt GitHub, ou écrivez à `security@[domaine-du-mainteneur]` (adresse disponible sur le profil
GitHub du mainteneur).

Précisez : version concernée, étapes de reproduction, impact estimé. Une réponse est apportée
sous 7 jours. Une divulgation coordonnée est préférée — vous serez crédité sauf demande
contraire.

## Modèle de menace

Obole est un serveur **mono-poste, sans authentification**, conçu pour écouter sur la boucle
locale. Ce choix est assumé et n'est pas un oubli : il conditionne les garanties réelles.

### Ce qui est protégé

- **Exposition réseau** : le binaire refuse de démarrer sur une adresse non locale. Un bind
  distant exige `OBOLE_ALLOW_REMOTE=1` explicite — la barrière est une décision consciente,
  pas un défaut silencieux.
- **Injection HTML dans les documents** : les thèses sont du markdown rédigé par l'utilisateur
  ou une IA. Le HTML produit est passé à DOMPurify, et les sources d'image sont restreintes aux
  assets locaux (`/api/thesis/assets/`), à `blob:` et aux `data:image/*` en base64. Une URL
  externe dans une image est retirée.
- **Corps de requête géants** : les uploads (CSV, archive de sauvegarde, image) sont bornés
  **avant** la lecture complète.
- **En-têtes** : `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` et une CSP
  stricte (`script-src 'self'`, aucun CDN) sur toutes les réponses de l'application.
- **Écritures pilotées par l'IA** : chaque outil MCP d'écriture copie la base
  (`cache.sqlite.bak`) avant de s'exécuter.

### Ce qui n'est pas protégé (par construction)

- **Pas d'authentification, pas de multi-utilisateur.** Quiconque atteint le port a un accès
  complet. C'est pour cela que le bind distant est refusé par défaut.
- **Pas de chiffrement au repos.** `cache.sqlite` est un fichier SQLite en clair. Sur une
  machine partagée, utilisez un volume chiffré (FileVault, LUKS) — hors du périmètre du
  projet.
- **Le cache picklé est une frontière de confiance.** Les blobs stockés sont désérialisés avec
  `pickle`. Un blob illisible est traité comme un cache manqué et purgé, mais **ne confiez pas
  votre `cache.sqlite` à une source non fiable** : un pickle forgé s'exécute.
- **Le MCP écrit dans vos données.** Un modèle de langage qui hallucine peut créer de fausses
  transactions. C'est pour cela que le snapshot existe et que le mode `--read-only` n'expose
  pas du tout les outils d'écriture.

### Recommandation pour un usage prudent

Si vous branchez une IA à laquelle vous ne donnez pas une confiance totale :

```bash
obole --mcp --read-only
```

Et si vous voulez tester des écritures sans risquer votre portefeuille réel, pointez Obole sur
un répertoire de données dédié :

```bash
OBOLE_DATA_DIR=~/obole-bac-a-sable obole --mcp
```

## Versions supportées

Le projet est en v0.x : seule la dernière version publiée reçoit des correctifs de sécurité.
