\# Bookmarkholic



\*\*Bookmarkholic\*\* est un gestionnaire de favoris minimaliste, rapide et léger, inspiré de \*\*Shaarli\*\*. 



\## L'histoire du projet

À l'origine, je me suis naturellement tourné vers \*\*Shaarli\*\* pour gérer mes liens. Cependant, confronté à des déboires de disponibilité (\*uptime\*) sur différents serveurs distants, j'ai d'abord fait le choix d'exécuter une instance locale sous Windows à l'aide de PHP CLI. 



Afin de gagner en réactivité et en légèreté de ressources, j'ai adapté et réécrit le projet sous \*\*Python\*\* avec le framework \*\*Flask\*\* et une base de données \*\*SQLite\*\*. Le résultat : une alternative autonome, ultra-légère et parfaitement fluide.



\---



\## Prérequis



Assurez-vous d'avoir installé sur votre machine :

\- Python (version 3.10 ou supérieure recommandée)

\- Pip



\## Installation



1\. Clonez ou téléchargez les sources du projet sur votre machine.



2\. Créez et activez un environnement virtuel à la racine du projet :

&#x20;  ```bash

&#x20;  python -m venv venv



Sur Linux / macOS :

&#x20;   Bash



&#x20;   source venv/bin/activate



&#x20;   Sur Windows :

&#x20;   Bash



&#x20;   venv\\Scripts\\activate



&#x20;   Installez les dépendances nécessaires :

&#x20;   Bash



&#x20;   pip install -r requirements.txt



Lancement de l'application



Pour démarrer le serveur de développement :

Bash



python app.py



L'application sera alors accessible dans votre navigateur à l'adresse : http://127.0.0.1:5000

Utilisation du Bookmarklet



Pour ajouter rapidement n'importe quelle page web à votre instance locale Bookmarkholic en un clic, vous pouvez utiliser un bookmarklet.

1\. Créer le Bookmarklet



Créez un nouveau favori dans la barre des signets de votre navigateur web, donnez-lui le nom de ➕ Shaare (ou Ajouter au Python), et collez le code JavaScript suivant dans le champ URL / Adresse :

JavaScript



javascript:void(location.href='http://localhost:5000/bookmarklet?url='+encodeURIComponent(location.href)+'\&title='+encodeURIComponent(document.title)+'\&selection='+encodeURIComponent(window.getSelection()));



2\. Fonctionnement



&#x20;   Lorsque vous naviguez sur le web et que vous cliquez sur ce favori, une fenêtre pop-up s'ouvre pour enregistrer le lien.



&#x20;   Si le lien existe déjà en base, le formulaire se préemplit automatiquement avec ses informations actuelles pour vous permettre de le mettre à jour.



&#x20;   Si le lien est nouveau, l'URL et le titre de la page active sont récupérés. De plus, si vous avez préalablement surligné/sélectionné du texte sur la page, celui-ci est automatiquement injecté dans le champ Description.



Structure du projet



&#x20;   app.py : Fichier principal de l'application Flask, routes et logique SQLite.



&#x20;   requirements.txt : Liste des dépendances du projet (Flask).



&#x20;   .gitignore : Fichiers ignorés par Git (base de données locale, cache, venv).



&#x20;   README.md : Documentation du projet.

