# Atelier Images — chargeur du pack Ekole Pastorale

Ce correctif est adapté à la version d'**Atelier Images** fournie le 15 novembre 2026.
Il permet de sélectionner **École Pastorale · 12 styles (pack local)**, puis de pointer vers le dépôt `ecole-pastorale` comme on le fait déjà pour le pack Québec.

## Où placer les fichiers

**Extraire le contenu de ce ZIP directement dans le dossier `Atelier-Images/`.**
Conserver l'arborescence interne, et autoriser le remplacement des 5 fichiers existants.

```text
C:\mycode\Ekole\
├── Atelier-Images\                  ← EXTRAIRE ICI
│   ├── catalogues.py                ← remplace l'ancien
│   ├── web\
│   │   ├── app.js                  ← remplace l'ancien
│   │   └── index.html              ← remplace l'ancien
│   └── profils\
│       ├── ecole-pastorale.profil.json  ← remplace l'exemple
│       └── ecole-pastorale.csv          ← remplace l'exemple
└── ecole-pastorale\                 ← dépôt EXISTANT, ne rien y installer
    ├── pack.json
    └── cours\
```

L'archive contient également `INSTALLATION.md` (ce fichier). **Ne pas l'extraire dans `ekole/` (le moteur Core), ni dans `ecole-pastorale/`.**
Faire une copie de sauvegarde des cinq fichiers avant remplacement.

## Utilisation

1. Relancer `Atelier-Images/LANCER_ATELIER_IMAGES.cmd`.
2. Dans la liste **Profil**, choisir `École Pastorale · 12 styles (pack local)`.
3. Dans **Chemin du pack local École Pastorale** :
   - laisser vide si `ecole-pastorale/` est au même niveau que `Atelier-Images/` ;
   - sinon entrer son chemin **absolu**, par exemple `D:\Projets\ecole-pastorale`.
4. Cliquer sur **Charger le catalogue**.
5. Choisir un style visuel dans **Thème**, puis `message` ou `foi` dans **Branche**.
6. Comme auparavant, préparer le plan / galerie, puis lancer une génération.

Le chemin désigne le **dossier** contenant `pack.json` et `cours/`, pas le fichier `pack.json` lui-même et pas le dépôt `.wiki`.

## Ce que charge le logiciel

- `pack.json` du **vrai dépôt local** : les IDs et titres canoniques des cours `EPC-MSG-...` et `EPC-FOI-...` ; la sélection porte sur les cours présents dans ce pack.
- `Atelier-Images/profils/ecole-pastorale.profil.json` : **12 styles visuels** et leurs palettes, avec prompts de référence.
- `Atelier-Images/profils/ecole-pastorale.csv` : **propositions de scènes**, 2 visuels par cours (`concept`, `situation`) et par style.

Si des cours du pack ne figurent pas dans le CSV, le chargeur indique ceux à compléter au lieu d'omettre silencieusement leurs illustrations.

**Attention :** le CSV conserve des propositions éditoriales de travail fondées sur le wiki. Le chargeur ne prétend pas extraire des scènes approuvées des Kristals et ne publie rien automatiquement dans le dépôt pastoral. Les résultats restent dans `Atelier-Images/donnees/ecole-pastorale/`.

## Vérifications effectuées

Des tests automatisés contre un **pack de test synthétique** ont vérifié : la lecture des 32 cours, la création de 768 tâches (12 styles × 32 cours × 2 visuels), l'utilisation des titres du `pack.json`, la sélection de cours partielle, et les messages d'erreur pour les répertoires / scènes manquants. Le dépôt pastoral complet n'étant pas joint (seul son wiki est présent), il faudra vérifier une fois son `pack.json` réel.
