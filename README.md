# Bookmarkholic

**Bookmarkholic** est un gestionnaire de favoris minimaliste, rapide et léger, inspiré de **Shaarli**. 

## L'histoire du projet

À l'origine, je me suis naturellement tourné vers **Shaarli** pour gérer mes liens. Cependant, confronté à des déboires de disponibilité (*uptime*) sur différents serveurs distants, j'ai d'abord fait le choix d'exécuter une instance locale sous Windows à l'aide de PHP CLI. 

Afin de gagner en réactivité et en légèreté de ressources, j'ai adapté et réécrit le projet sous **Python** avec le framework **Flask** et une base de données **SQLite**.entièrement conçu en **vibecoding**, ce projet est le fruit d'une écriture assistée par IA générative, combinant intuition, itérations fluides et plaisir du code rapide pour obtenir une alternative autonome, ultra-légère et parfaitement fluide.

---

## Fonctionnalités principales

* Gestion simple des favoris : Ajout, modification, suppression et affichage des favoris avec prise en compte des liens privés, incluant l'utilisation d'un bookmarklet pour l'enregistrement rapide de pages web.
* Recherche avancée et multi-tags : Recherche textuelle globale et filtrage par tags multiples indépendamment de l'ordre de saisie.
* Outils d'import / export : Importation et exportation de fichiers de favoris au format standard Netscape / Shaarli (.html).
* Pages utilitaires intégrées : 
  * Recommandations RSS (/rss-recommendations)
  * Optimisation et nettoyage des tags (/optimize-tags)
  * Historique et statistiques par année (/tags-by-year)
  * Renommage global d'un tag (/rename-tags)
  * Analyse des domaines les plus fréquents (/top-domains)
* Pagination flexible : Choix du nombre de liens affichés par page (15, 20, 50 ou 100).

## Prérequis

Assurez-vous d'avoir installé sur votre machine :
- Python (version 3.10 ou supérieure recommandée)
- Pip

## Installation et Lancement

1. Clonez ou téléchargez les sources du projet sur votre machine.

2. Créez et activez un environnement virtuel à la racine du projet :
   python -m venv venv

   Sur Linux / macOS :
   source venv/bin/activate

   Sur Windows :
   venv\Scripts\activate

3. Installez les dépendances nécessaires :
   pip install -r requirements.txt

4. Pour démarrer le serveur de développement :
   python app.py

L'application sera alors accessible dans votre navigateur à l'adresse : http://127.0.0.1:5000

## Utilisation du Bookmarklet

Pour ajouter rapidement n'importe quelle page web à votre instance locale Bookmarkholic en un clic, vous pouvez utiliser un bookmarklet.

1. Créer le Bookmarklet
Créez un nouveau favori dans la barre des signets de votre navigateur web, donnez-lui le nom de ➕ Shaare, et collez le code JavaScript suivant dans le champ URL / Adresse :

``` Javascript
javascript:void(window.open('http://localhost:5000/add?url='+encodeURIComponent(location.href)+'&title='+encodeURIComponent(document.title)+'&selection='+encodeURIComponent(window.getSelection()), '_blank', 'width=600,height=650'));
```

3. Fonctionnement
- Lorsque vous naviguez sur le web et que vous cliquez sur ce favori, une fenêtre pop-up s'ouvre pour enregistrer le lien.
- Si le lien existe déjà en base, le formulaire se préemplit automatiquement avec ses informations actuelles pour vous permettre de le mettre à jour.
- Si le lien est nouveau, l'URL et le titre de la page active sont récupérés. De plus, si vous avez préalablement surligné/sélectionné du texte sur la page, celui-ci est automatiquement injecté dans le champ Description.

## Structure de la base de données et du projet

L'application utilise une base de données SQLite locale nommée bookmarks.sqlite3 créée automatiquement au premier lancement. Elle gère une table unique bookmarks contenant :
* id : Identifiant unique auto-incrémenté
* url : Adresse web du favori (clé unique)
* title : Titre du lien
* description : Notes ou description textuelle
* tags : Mots-clés associés séparés par des espaces
* add_date : Timestamp de création
* private : Indicateur de confidentialité (0 pour public, 1 pour privé)

Fichiers du projet :
- app.py : Fichier principal de l'application Flask, routes et logique SQLite.
- requirements.txt : Liste des dépendances du projet (Flask).
- .gitignore : Fichiers ignorés par Git (base de données locale, cache, venv).
- README.md : Documentation du projet.

## Licence

Ce projet est distribué sous licence libre, idéal pour un usage personnel et un auto-hébergement sur serveur privé virtuel ou conteneur local.
