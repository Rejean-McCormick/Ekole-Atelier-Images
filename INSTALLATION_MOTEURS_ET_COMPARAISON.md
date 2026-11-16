# Atelier Images — FLUX locaux, Replicate, Cloudflare et collections parallèles

**Version du correctif : 15 novembre 2026 — fondé sur le ZIP Atelier-Images fourni.**

## Installation sans perte des images

1. Ferme Atelier Images avant de modifier les fichiers.
2. Fais une sauvegarde du dossier `Atelier-Images/` (particulièrement `donnees/`, `profils/`, `moteurs/` et les fichiers `.py`).
3. Décompresse **le contenu de ce correctif ZIP directement dans `C:\mycode\Ekole\Atelier-Images\`** (ou dans ton dossier Atelier Images existant).
4. Accepte uniquement le remplacement des fichiers de code et d'interface présents dans le ZIP. **Le ZIP ne contient aucun fichier `profils/`, aucun fichier `donnees/`, ni les workflows Flat Cartoon actuels.** Les 12 thèmes pastoraux, références et images Cloudflare existantes ne sont donc pas remplacés par l'archive.
5. Relance `LANCER_ATELIER_IMAGES.cmd`.

Ne pas placer ces fichiers dans `ekole-quebec/` ni dans `ecole-pastorale/`.

## Nouveaux moteurs disponibles

### FLUX local (ComfyUI)

- `FLUX.1 Dev · Flat Cartoon rapide` — existant, 12 étapes, LoRA actuel.
- `FLUX.1 Dev · Flat Cartoon Illustration` — existant, 20 étapes, LoRA actuel.
- **`FLUX.1 Dev · Artistique polyvalent`** — nouveau workflow 20 étapes, **sans LoRA Flat Cartoon**.
- **`FLUX.1 Dev · Artistique haute qualité`** — nouveau workflow 28 étapes, **sans LoRA Flat Cartoon**.
- `ComfyUI local · Workflow importé` — fonctionnalité existante.

Les deux nouveaux workflows réutilisent les mêmes fichiers de base que Flat Cartoon (`flux1-dev.safetensors`, `t5xxl_fp8_e4m3fn.safetensors`, `clip_l.safetensors`, `ae.safetensors`). Ils exigent ComfyUI sur `127.0.0.1:8188` et sont testés structurellement, **pas sur ta carte graphique**.

### Cloud (estimations à environ 1 MP, sans référence)

| Moteur | Fournisseur | Estimation / image | 4 000 images | Authentification |
| --- | --- | ---: | ---: | --- |
| FLUX.2 Klein 4B | Replicate | 0,001 $ | **4 $** | jeton Replicate |
| FLUX 3 Image Klein | **Black Forest Labs API** | 0,009 $ | **36 $** | clé BFL |
| FLUX.2 Klein 9B | Replicate | 0,015 $ | **60 $** | jeton Replicate |
| FLUX.2 Pro | Replicate | 0,030 $ | **120 $** | jeton Replicate |
| FLUX.2 Klein 4B (ancien) | Cloudflare | ≈ 0,001148 $ | **≈ 4,59 $** | compte + jeton Cloudflare |
| FLUX.2 Klein 9B | Cloudflare | 0,015 $ | **60 $** | compte + jeton Cloudflare |

**Important :** FLUX 3 Image Klein n'avait pas de modèle officiel confirmé chez Replicate ou Cloudflare lors de la vérification. Pour avoir exactement ce modèle et son estimation de 36 $/4 000 images, le correctif utilise donc l'**API directe de Black Forest Labs (BFL)**. Replicate est utilisé pour les 3 modèles FLUX.2 demandés ; Cloudflare héberge les 2 modèles Klein.

Les prix sont **indicatifs**, non des devis : les références d'image, la résolution réelle, la facturation minimale, les taxes, les éventuels crédits et les changements de tarifs peuvent les modifier. L'Atelier affiche le coût estimé avant confirmation du lot. Aucun paiement n'est déclenché avant que tu ne confirmes **Générer**, puis que le fournisseur accepte les requêtes.

Sources :
- https://replicate.com/black-forest-labs/flux-2-klein-4b
- https://replicate.com/black-forest-labs/flux-2-klein-9b
- https://replicate.com/black-forest-labs/flux-2-pro
- https://bfl.ai/pricing
- https://developers.cloudflare.com/workers-ai/platform/pricing/
- https://developers.cloudflare.com/workers-ai/models/

## Deux collections, sans écrasement

Les anciennes images Cloudflare restent où elles étaient :

```text
Atelier-Images/donnees/<profil>/lots/<theme>/<branche>/<cours>/<slot>.webp
```

Chaque nouveau moteur possède son propre sous-dossier, par exemple :

```text
Atelier-Images/donnees/<profil>/collections/artistique-polyvalent/lots/...
Atelier-Images/donnees/<profil>/collections/artistique-haute-qualite/lots/...
Atelier-Images/donnees/<profil>/collections/replicate-klein-4b/lots/...
Atelier-Images/donnees/<profil>/collections/replicate-pro/lots/...
Atelier-Images/donnees/<profil>/collections/cf-klein-9b/lots/...
```

Même scène + autre moteur : **nouveau fichier distinct**. Un fichier déjà produit par le même moteur est ignoré au prochain lot, sauf si tu coches volontairement l'option de remplacement après modification du prompt. 

Dans **Voir les images** les cases **Cloudflare**, **FLUX local / ComfyUI**, **Replicate** et **BFL** permettent d'afficher les collections séparément ou ensemble. Les variantes de la même scène apparaissent l'une à côté de l'autre quand la largeur le permet.

Si une image est intégrée dans Ékole via la fonction d'intégration existante (actuellement prise en charge pour le catalogue Québec), les autres variantes affichent **Cette scène possède déjà une autre variante intégrée dans Ékole**. Les validations restent spécifiques à la variante ; l'original reste intact lorsqu'on intègre une alternative.

## Pour générer cette nuit

1. Choisir le profil et charger le catalogue.
2. Choisir **FLUX.1 Dev · Artistique polyvalent (20 étapes)** ou **Artistique haute qualité (28 étapes)**.
3. Cocher **Générer tous les thèmes**.
4. Ne **pas** cocher **Remplacer les images non validées**.
5. Indiquer **0** en nombre maximal d'images (toutes les images manquantes dans la collection du moteur choisi).
6. Lancer ComfyUI puis cliquer **Générer**. Atelier Images et ComfyUI doivent rester ouverts ; garder le PC alimenté et ne pas le laisser entrer en veille.
7. Au retour, sélectionner un thème, cliquer **Voir les images**, cocher **Cloudflare** et **FLUX local / ComfyUI**.

## Remarques et limites

- Le correctif conserve la compatibilité avec le chargeur `kristals-pastorale` précédent mais **ne remplace pas** tes fichiers de profils et scènes.
- La publication existante dans le dépôt **Ékole Québec** est conservée ; la structure réelle d'intégration du dépôt pastoral ne pouvait pas être validée à partir du seul wiki fourni. Il n'y a donc **pas d'écriture pastorale présentée comme officiellement intégrée** sans définir ce chemin canonique.
- Les API des fournisseurs ont été vérifiées dans leurs documentations, et les appels sont testés par simulation ; **aucun test de génération payante en conditions réelles n'a été effectué**, car les clés privées et le serveur ComfyUI du PC ne sont pas accessibles ici.
- Les jetons sont utilisés seulement en mémoire pendant le lot et ne sont pas enregistrés dans des fichiers de configuration par le correctif.
- Les prix ne tiennent pas compte de la consommation électrique ni de l'amortissement du matériel local.
