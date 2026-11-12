# Atelier Images

Application locale indépendante des catalogues scolaires. L’atelier prépare des prompts, génère des WebP individuels et présente les résultats à revoir. Il lit les sources et écrit ses résultats dans son propre dossier `donnees`.

## Démarrer

1. Extraire le ZIP dans `C:\mycode\Ekole` pour obtenir `C:\mycode\Ekole\Atelier-Images`. Il peut aussi être installé ailleurs.
2. Double-cliquer sur `LANCER_ATELIER_IMAGES.cmd`. La fenêtre de commande maintient le site ouvert dans le navigateur. Python 3.10 ou plus récent est requis. Pour joindre des images et générer, installer Pillow une fois avec `py -3 -m pip install Pillow`.
3. Choisir **École Québec** ou **École pastorale · exemple** et charger le catalogue. Pour Québec, entrer le chemin de la copie locale si elle se trouve ailleurs. L’atelier lit les Kristals et le registre des univers depuis cette copie.
4. Choisir un thème et une branche. Copier le prompt de référence dans ChatGPT, enregistrer une seule image et l’ajouter à l’atelier. On peut aussi générer avec le seul prompt de style.
5. Choisir **Préparer le plan et la galerie** pour vérifier la sélection gratuitement. Entrer ensuite l’identifiant du compte et le jeton Cloudflare autorisé à appeler Workers AI pour lancer un essai de 12 images. Le jeton est transmis au processus local et utilisé pendant la génération. Pour poursuivre une branche, relancer le lot. Les fichiers existants sont sautés.

Le site écoute sur `127.0.0.1`. La génération est effectuée par Cloudflare Workers AI. La fermeture de la fenêtre de commande arrête le processus local. Le compteur partage le plafond de 4 800 appels avec le lanceur Québec précédent et le conserve dans `%LOCALAPPDATA%\Ekole\GenerationImages`.

## Ajouter une école ou un autre projet

1. Copier `profils/ecole-pastorale.profil.json` sous un nouveau nom en minuscules, par exemple `mon-projet.profil.json`.
2. Personnaliser le nom visible, la direction artistique et les thèmes. Chaque thème possède un identifiant, un nom, une introduction, une palette et une scène pour le prompt de référence.
3. Copier le CSV d’exemple sous le nom indiqué dans `source`. Exporter depuis Excel en CSV UTF-8 avec les colonnes `theme;branche;id;slot;titre;prompt;alt`. Les identifiants sont composés de lettres minuscules, de chiffres et de tirets. Actualiser le site pour charger le nouveau profil.

Les sorties restent séparées dans `donnees/<profil>/lots`. Pour récupérer les sorties ou références du premier lanceur Québec, copier les dossiers `lots` et `references` de `ekole-quebec/.ekole-images` vers `donnees/ecole-quebec`. Le CSV facultatif `prompts-excel.csv` de l’ancien lanceur se déplace au même endroit. L’intégration dans une école se fait ensuite à partir de ses fichiers approuvés.


## Générer tous les thèmes

Choisir un moteur ComfyUI local, cocher **Générer tous les thèmes** et laisser la limite à **0**. Le lot suit les thèmes du catalogue et utilise leur palette respective. L’atelier reprend les images manquantes si tu relances le lot. Pendant le lot, garder Atelier Images et ComfyUI ouverts et laisser le portable branché, avec le couvercle ouvert.
