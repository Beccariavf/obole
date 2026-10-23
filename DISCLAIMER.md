# Avertissement

Obole est un **outil d'analyse technique et statistique**. Il n'est ni un conseil en
investissement, ni une recommandation d'achat ou de vente, ni une prestation de gestion de
portefeuille.

## Pas de conseil en investissement

Les indicateurs affichés (distance σ, pente, potentiels, tendances, notes de qualité) sont le
résultat mécanique d'un calcul de régression sur des séries de prix passées. **Les performances
passées ne préjugent en rien des performances futures.** Une valeur « décotée » au sens de la
droite d'Obole peut continuer de baisser indéfiniment — la méthode décrit une trajectoire
historique, elle ne prédit rien.

Toute décision d'investissement relève de la seule responsabilité de l'utilisateur. Si vous
avez besoin d'un conseil financier, adressez-vous à un professionnel habilité.

## Non-affiliation à Yahoo et yfinance

Obole consomme des données via la bibliothèque libre [yfinance](https://github.com/ranaroussi/yfinance),
qui interroge des interfaces publiques de Yahoo. **Obole n'est ni affilié, ni sponsorisé, ni
approuvé par Yahoo Inc.** « Yahoo », « Yahoo Finance » et les marques associées appartiennent à
leurs détenteurs respectifs.

L'usage de yfinance est soumis aux conditions d'utilisation de Yahoo et à celles du projet
yfinance lui-même. Les données ne sont pas garanties exactes, complètes ni disponibles : un
changement côté fournisseur peut casser une fonctionnalité sans préavis. Obole les utilise
telles quelles, sans validation.

## Indépendance de la méthode

La méthode dite « droite d'Obole » est une **reconstitution indépendante** d'une approche
publique de régression log-prix sur le long terme. Aucun code, aucune formule propriétaire et
aucune donnée interne d'un éditeur commercial n'a été utilisée ou reproduite. Les libellés et
seuils sont calibrés sur des observations publiques et documentés dans le code (`config.py`).

## Absence de garantie

Le logiciel est fourni « en l'état », sans garantie d'aucune sorte, expresse ou implicite.
Reportez-vous à la [licence AGPL-3.0](LICENSE) pour la clause de non-garantie complète.

## Données personnelles

Obole fonctionne localement. Les données que vous saisissez (portefeuille, transactions,
thèses) restent sur votre machine, dans un fichier SQLite que vous contrôlez. Le projet ne
collecte ni ne transmet aucune donnée. **Vous êtes responsable de la sauvegarde** de ce
fichier (l'interface propose un export JSON).
