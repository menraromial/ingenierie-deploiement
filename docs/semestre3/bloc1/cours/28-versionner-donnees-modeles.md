---
title: "Ch. 28 : Versionner le code, les données et le modèle"
sidebar_label: "Ch. 28 : Versionner le code, les données et le modèle"
hide_title: true
---

import ChapterHead from '@site/src/components/ChapterHead';
import Figure from '@site/src/components/Figure';

<ChapterHead
  kicker="Semestre 3 · Bloc 1 · Chapitre 28"
  title="Versionner le code, les données et le modèle : la reproductibilité"
  lecture="50 min"
  competences={['C2', 'C4']}
/>

:::objectifs
À l'issue de ce chapitre, vous saurez :

- distinguer répétabilité, reproductibilité et réplicabilité, et dire laquelle on exige d'un système en production ;
- énumérer les cinq entrées qui déterminent un modèle entraîné, et la façon de figer chacune ;
- expliquer, chiffres à l'appui, pourquoi l'aléa de l'entraînement et les versions des bibliothèques changent le modèle obtenu ;
- expliquer le principe du stockage adressé par le contenu, et pourquoi il permet de versionner des données volumineuses sans les mettre dans Git ;
- décrire le fonctionnement de DVC : fichiers pointeurs, cache, stockage distant, pipelines et `dvc repro` ;
- reconstituer, à partir d'un identifiant de commit, le modèle exact qui a été déployé.
:::

## 1. « Peux-tu refaire le modèle v1 ? »

Le modèle de catégorisation de Listify a été déployé il y a trois mois ; appelons-le **v1**. Aujourd'hui, on constate que sa précision a chuté (ch. 27) et l'on veut comprendre : v1 était-il vraiment à 94 % ? Qu'est-ce qui a changé depuis ? Une question simple se pose alors, et elle révèle presque toujours une réponse embarrassante : **peut-on reconstruire exactement le modèle v1 ?**

Pour cela, il faudrait retrouver le code tel qu'il était ce jour-là (Git le sait), mais aussi les données d'entraînement exactes (l'export de 20 000 tâches a été régénéré depuis, et la base a changé), les hyperparamètres (modifiés dans une cellule du notebook, puis remodifiés), la version de scikit-learn (installée sans numéro de version, elle a été mise à jour entre-temps) et la graine aléatoire (il n'y en avait pas). Sur ces cinq éléments, un seul est versionné. Le modèle v1 est **perdu** : on dispose du fichier binaire qui tourne en production, mais personne ne sait plus le refaire, ni même dire précisément de quoi il est fait.

Ce chapitre traite de ce problème, préalable à tout le reste du semestre. On ne peut ni comparer deux modèles, ni expliquer une régression, ni automatiser un réentraînement, ni auditer une décision si l'on ne sait pas **reproduire** un entraînement.

## 2. Trois mots à ne pas confondre

Le vocabulaire de la reproductibilité est flottant dans la littérature. On adopte ici celui de l'ACM, révisé en 2020 pour s'aligner sur les recommandations de l'organisme de normalisation américain NISO [^acm] :

| Terme | Qui refait l'expérience ? | Dans quelles conditions ? | Question posée |
|---|---|---|---|
| **Répétabilité** | La même équipe | Le même montage expérimental | « Est-ce que j'obtiens le même résultat si je relance ? » |
| **Reproductibilité** | Une autre équipe | Le même montage (même code, mêmes données) | « Quelqu'un d'autre obtient-il mon résultat avec mes artefacts ? » |
| **Réplicabilité** | Une autre équipe | Un autre montage (code réécrit, autres données du même type) | « Le résultat tient-il indépendamment de mon implémentation ? » |

En recherche, la réplicabilité est l'idéal scientifique. En ingénierie de production, l'exigence minimale est la **reproductibilité** au sens ci-dessus, avec une nuance importante : l'« autre équipe », c'est souvent **vous-même dans six mois**, ou un **pipeline automatique** qui n'a accès qu'au dépôt et au stockage de données. Un entraînement reproductible est un entraînement qu'une machine neutre peut rejouer à partir d'un identifiant, sans aide humaine : exactement l'exigence du build de CI au chapitre 23.

[^acm]: ACM, *Artifact Review and Badging, Version 1.1*, août 2020. [acm.org/publications/policies/artifact-review-and-badging-current](https://www.acm.org/publications/policies/artifact-review-and-badging-current). La version 1.1 a interverti les définitions de « reproductibilité » et de « réplicabilité » de la version de 2016.

## 3. Ce qui détermine un modèle

Un modèle entraîné est une fonction de cinq entrées. Si l'une d'elles change, on obtient un autre modèle.

<Figure src="determinants-modele" num="28.1" alt="Cinq entrées alimentent l'entraînement, qui produit un modèle et ses métriques : le code (versionné par Git), les données (DVC), la configuration (fichier versionné), l'environnement (versions épinglées, image) et l'aléa (graine fixée).">
  Les cinq entrées d'un entraînement, et la façon de figer chacune. Oublier d'en figer une seule suffit à rendre le modèle irreproductible.
</Figure>

On sait déjà versionner la première, le code, depuis le semestre 1. Les sections suivantes traitent des quatre autres, en commençant par les deux qu'on sous-estime le plus : l'aléa et l'environnement.

## 4. L'aléa de l'entraînement

### 4.1 D'où vient le hasard ?

Un entraînement fait intervenir le hasard à plusieurs endroits, souvent sans que le code le montre :

- le **découpage** des données entre entraînement et évaluation (`train_test_split` tire les lignes au hasard) ;
- l'**initialisation** des paramètres (les poids d'un réseau de neurones, les points de départ d'un algorithme) ;
- l'**ordre** de présentation des exemples (mélangés à chaque passe dans les méthodes par descente de gradient) ;
- l'**échantillonnage** interne de certains algorithmes (une forêt aléatoire tire, pour chaque arbre, un sous-échantillon des lignes et des variables).

Tous ces tirages utilisent un générateur de nombres **pseudo-aléatoires**, qui produit une suite entièrement déterminée par sa valeur de départ, la **graine** (*seed*). Même graine, même suite de tirages, même résultat ; graine différente, résultat différent.

:::exemple[Combien vaut le hasard ? Une mesure réelle]
On entraîne une forêt aléatoire de 100 arbres (scikit-learn 1.7.2) sur un jeu de 2 000 exemples **toujours le même**, avec le **même code**. Seule change la graine, passée à la fois au découpage et à la forêt. Voici les précisions obtenues sur les 20 % d'exemples réservés à l'évaluation, pour les graines 0 à 9 (mesure réalisée pour ce cours) :

$$
89{,}5 \quad 92{,}0 \quad 90{,}2 \quad 89{,}0 \quad 89{,}8 \quad 92{,}0 \quad 92{,}0 \quad 91{,}0 \quad 91{,}0 \quad 89{,}0
$$

La précision varie de **89,0 % à 92,0 %**, soit trois points d'écart, pour une moyenne de 90,55 % et un écart-type de 1,22 point. Trois constats :

1. Relancer **deux fois avec la graine 42** donne deux fois exactement 90,25 % : avec une graine fixée, l'entraînement est **répétable**.
2. **Sans graine**, trois exécutions successives ont donné 90,5 %, 88,2 % et 92,2 % : impossible de savoir quel modèle on a mis en production, ni de le refaire.
3. Une « amélioration » de 1 point entre deux versions du modèle est **inférieure à la variation due au seul hasard**. Comparer deux configurations sur une seule exécution chacune, c'est comparer deux tirages au sort. Il faut plusieurs graines et regarder la moyenne et la dispersion, ce que vous ferez avec MLflow au chapitre 31.
:::

### 4.2 Fixer la graine, et ce que cela ne garantit pas

En Python, on fixe les graines des générateurs utilisés (celui du module `random`, celui de NumPy, et le paramètre `random_state` des fonctions de scikit-learn), idéalement à partir d'une valeur lue dans la configuration plutôt qu'écrite en dur. C'est nécessaire, mais pas suffisant :

- une graine garantit le même résultat **avec la même version** des bibliothèques. Une mise à jour peut changer l'ordre des tirages ou l'algorithme lui-même ;
- sur processeur graphique (GPU), certaines opérations sont **non déterministes** par construction (l'ordre des additions en parallèle varie, et l'addition en virgule flottante n'est pas associative) ; les bibliothèques d'apprentissage profond proposent des modes déterministes, plus lents.

## 5. L'environnement : les versions comptent

Au semestre 1, le `requirements.txt` de Listify épinglait déjà les versions (`flask==3.0.3`). Pour un entraînement, l'exigence est plus forte encore, parce qu'une nouvelle version d'une bibliothèque de ML peut changer le **modèle** produit sans rien casser.

:::exemple[Même code, autre modèle : la version 0.22 de scikit-learn]
En décembre 2019, la version 0.22 de scikit-learn a modifié deux valeurs par défaut très utilisées [^sklearn022] :

- le nombre d'arbres d'une forêt aléatoire (`n_estimators`) est passé de **10 à 100** ;
- l'algorithme d'optimisation par défaut de la régression logistique (`solver`) est passé de **`liblinear` à `lbfgs`**.

Un script qui écrivait simplement `RandomForestClassifier()` ou `LogisticRegression()`, sans préciser ces paramètres, et dont l'environnement installait scikit-learn **sans numéro de version**, a produit du jour au lendemain un modèle différent : dix fois plus d'arbres (donc un modèle plus lent, plus lourd, et de précision différente), ou une régression optimisée autrement, avec une régularisation qui ne se comporte pas pareil. Aucune ligne du projet n'avait changé.

Deux leçons, qui valent pour tout le semestre : **épingler les versions** de toutes les dépendances, et **écrire explicitement** les hyperparamètres importants au lieu de se fier aux valeurs par défaut, qui sont une configuration cachée.
:::

Trois niveaux de rigueur existent pour figer l'environnement, du plus simple au plus sûr :

| Niveau | Moyen | Ce qui reste variable |
|---|---|---|
| Versions directes épinglées | `scikit-learn==1.7.2` dans `requirements.txt` | Les dépendances **des** dépendances (NumPy, SciPy...) |
| Fichier de verrouillage | `pip-compile --generate-hashes`, `uv lock` : toutes les dépendances, avec leur empreinte | Le système d'exploitation, les bibliothèques système |
| Image de conteneur | L'environnement complet, identifié par son **digest** (ch. 24) | Le matériel (processeur, GPU) |

L'image de conteneur est la réponse du semestre 2, et elle reste la meilleure : l'entraînement s'exécute dans une image identifiée par son digest, exactement comme le service qui le déploie.

[^sklearn022]: scikit-learn, *Release Highlights for scikit-learn 0.22* et *Changelog* de la version 0.22, décembre 2019. [scikit-learn.org/stable/whats_new/v0.22.html](https://scikit-learn.org/stable/whats_new/v0.22.html).

## 6. Versionner les données

### 6.1 Pourquoi pas Git ?

La solution évidente serait de mettre les données dans Git, avec le code. Elle échoue pour trois raisons :

- **la taille** : Git garde **chaque version** de chaque fichier dans l'historique, et tout clone télécharge cet historique complet. Un jeu de données de 2 Go modifié dix fois donne un dépôt de 20 Go que chaque développeur et chaque job de CI doit cloner. Les hébergeurs imposent d'ailleurs des limites : GitHub refuse les fichiers de plus de 100 Mo ;
- **les formats binaires** : Git calcule et stocke efficacement les différences entre versions d'un fichier texte, mais pas d'un fichier Parquet, d'une image ou d'un modèle sérialisé ;
- **l'emplacement** : les données vivent souvent ailleurs (un stockage objet, un disque partagé), et n'ont pas à transiter par la forge.

On veut donc garder dans Git ce que Git fait bien (l'historique, les branches, les revues) et mettre les données ailleurs, **sans perdre le lien** entre une version du code et la version des données qui va avec. C'est exactement ce que permet le stockage adressé par le contenu.

### 6.2 Le principe : nommer un fichier par son contenu

Au lieu de désigner un fichier par son **nom** (`taches.csv`), qui ne dit rien de ce qu'il contient, on le désigne par une **empreinte** de son contenu, calculée par une fonction de hachage : une suite d'octets de taille quelconque en entrée, un identifiant de taille fixe en sortie.

:::exemple[Une empreinte, calculée]
Sur votre poste, calculez l'empreinte MD5 d'un fichier d'une ligne contenant le mot `hello` :

```bash
printf 'hello\n' | md5sum
# b1946ac92492d2347c6235b4d2611184  -
```

Trois propriétés rendent cette empreinte utile comme **adresse** :

- **déterminisme** : le même contenu donne toujours la même empreinte, sur toute machine. Deux copies identiques d'un jeu de données ont la même adresse, et on n'en stocke qu'une ;
- **sensibilité** : changer un seul octet change complètement l'empreinte (`printf 'hellp\n'` donne une empreinte sans rapport). Si l'adresse n'a pas changé, le contenu n'a pas changé ;
- **taille fixe** : que le fichier fasse 6 octets ou 240 Mio, l'adresse fait 32 caractères, et se range sans peine dans un petit fichier texte versionné par Git.

MD5 n'est plus sûr face à un attaquant qui fabrique volontairement des collisions ; pour détecter des changements **accidentels** de données, il reste largement suffisant, et c'est ce qu'utilise DVC par défaut.
:::

Ce principe n'est pas neuf : **Git lui-même** fonctionne ainsi. Chaque fichier, chaque répertoire et chaque commit y est un objet rangé sous l'empreinte SHA-1 de son contenu [^progit]. C'est pour cela qu'un identifiant de commit désigne sans ambiguïté un état exact du code. DVC applique la même idée aux données, en stockant le contenu **hors** de Git.

[^progit]: Scott Chacon, Ben Straub, *Pro Git*, 2ᵉ éd., Apress, 2014, chapitre 10, « Git Internals », en particulier la section 10.2, « Git Objects ». Gratuit en ligne : [git-scm.com/book/fr/v2](https://git-scm.com/book/fr/v2).

### 6.3 DVC

**DVC** (*Data Version Control*) est un outil libre, créé en 2017, qui s'utilise **à côté** de Git dans le même dépôt [^dvc]. Son fonctionnement tient en une figure :

<Figure src="adressage-contenu" num="28.2" alt="Le fichier taches.csv de 240 Mio passe par MD5, qui produit une empreinte. L'empreinte est écrite dans un petit fichier taches.csv.dvc, versionné par Git ; le contenu est copié dans le cache DVC sous un chemin formé de l'empreinte ; le cache se synchronise avec un stockage distant par dvc push et dvc pull.">
  Le stockage adressé par le contenu, tel que le pratique DVC. Git versionne l'adresse, un petit fichier texte ; DVC range le contenu sous cette adresse, dans un cache local et un stockage distant partagé.
</Figure>

Suivons ce qui se passe quand on met un fichier de données sous contrôle :

```bash
dvc init                          # une fois : crée le dossier .dvc/ dans le dépôt Git
dvc add data/taches.csv           # calcule l'empreinte, copie le contenu dans le cache
git add data/taches.csv.dvc data/.gitignore
git commit -m "Données : export des tâches pour l'entraînement de v1"
dvc remote add -d partage /mnt/partage/dvc-listify    # un dossier, MinIO, S3...
dvc push                          # envoie le contenu vers le stockage distant
```

La commande `dvc add` fait trois choses. Elle calcule l'empreinte MD5 du fichier. Elle copie le contenu dans le **cache** local, `.dvc/cache/files/md5/`, sous un chemin formé de l'empreinte (les deux premiers caractères forment un sous-dossier). Et elle écrit un petit fichier **pointeur**, `taches.csv.dvc`, qui contient l'empreinte et la taille :

```yaml title="data/taches.csv.dvc"
outs:
- md5: 3f2a9c4e8b1d7a60c2f5e9b83d4a71e0
  size: 251658240
  hash: md5
  path: taches.csv
```

C'est **ce fichier** que Git versionne, pas les 240 Mio. Elle ajoute enfin `taches.csv` au `.gitignore`, pour que Git ne le prenne jamais par erreur.

Pour revenir à une version antérieure, on combine les deux outils : Git restaure les pointeurs, DVC restaure les contenus qu'ils désignent.

```bash
git checkout v1.0                 # les fichiers .dvc reviennent à leur état de la v1.0
dvc checkout                      # DVC remet dans data/ les contenus correspondants
```

Et sur une machine neuve, un job de CI ou le poste d'un collègue : `git clone`, puis `dvc pull`, qui télécharge depuis le stockage distant exactement les contenus désignés par les pointeurs du commit courant.

[^dvc]: Documentation de DVC, « Versioning Data and Models » et « Internal Files » : [dvc.org/doc](https://dvc.org/doc). DVC est développé par la société Iterative et distribué sous licence Apache 2.0.

### 6.4 Le coût du stockage dépend de la granularité

DVC déduplique **par fichier** : deux fichiers identiques ne sont stockés qu'une fois, mais un fichier dont un seul octet change est stocké **en entier** une seconde fois. La façon de découper les données a donc un effet direct sur l'espace consommé.

:::exemple[Un gros fichier ou cent petits ?]
Le jeu d'entraînement de Listify fait 2 Go. À chaque nouvelle version, environ 2 % des lignes changent (nouvelles tâches, catégories corrigées). On conserve dix versions.

**Un seul fichier CSV de 2 Go.** Chaque version modifie ce fichier, qui est donc stocké en entier à chaque fois :

$$
10 \times 2 \text{ Go} = 20 \text{ Go}.
$$

**Cent fichiers de 20 Mo**, découpés par exemple par mois de création des tâches. Les modifications se concentrent dans les fichiers récents : supposons que chaque version ne touche que 2 fichiers sur 100. La première version coûte 2 Go ; chacune des neuf suivantes ajoute $2 \times 20 \text{ Mo} = 40 \text{ Mo}$ :

$$
2 \text{ Go} + 9 \times 0{,}04 \text{ Go} = 2{,}36 \text{ Go}.
$$

Soit **8,5 fois moins** d'espace, et des `dvc pull` d'autant plus rapides. Le découpage des données n'est pas qu'une question de performance des traitements (on le reverra avec Parquet et Spark au chapitre 36) : c'est aussi une question de coût de versionnement.
:::

### 6.5 Figer une source vivante

Un piège fréquent : les données d'entraînement proviennent d'une **requête** sur une base vivante (`SELECT title, category FROM tasks`), relancée à chaque entraînement. Deux exécutions à un mois d'intervalle n'entraînent pas le modèle sur les mêmes données, même si tout le reste est figé.

:::exemple[Une requête n'est pas un jeu de données]
La table `tasks` de Listify contient 20 000 tâches catégorisées. Chaque mois, 1 500 tâches sont ajoutées, 200 supprimées, et les utilisateurs corrigent la catégorie de 300 tâches existantes. Au bout de trois mois, relancer la même requête renvoie :

- $20\,000 + 3 \times (1\,500 - 200) = 23\,900$ lignes au lieu de 20 000 ;
- dont environ $3 \times 300 = 900$ étiquettes modifiées parmi les tâches d'origine (un peu moins si certaines ont été corrigées deux fois).

Le modèle v1 ne peut plus être reproduit à partir de la requête : il faut avoir **figé un instantané** du résultat au moment de l'entraînement (le fichier `taches.csv` exporté, versionné par DVC), ou disposer d'une base qui permet d'interroger son état passé. La règle : **on n'entraîne jamais sur une source vivante, mais sur un instantané versionné**.
:::

## 7. Les pipelines : figer aussi les étapes

Figer les données d'entrée ne suffit pas si les étapes qui les transforment sont exécutées à la main, dans un ordre que seul l'auteur connaît : c'est la « jungle de pipelines » du chapitre 27. DVC permet de décrire ces étapes dans un fichier `dvc.yaml`, versionné avec le code :

```yaml title="dvc.yaml"
stages:
  prepare:
    cmd: python src/prepare.py data/taches.csv data/train.csv data/test.csv
    deps: [src/prepare.py, data/taches.csv]
    outs: [data/train.csv, data/test.csv]
  train:
    cmd: python src/train.py data/train.csv model.joblib
    deps: [src/train.py, data/train.csv]
    params: [train.C, train.seed]          # lus dans params.yaml
    outs: [model.joblib]
  evaluate:
    cmd: python src/evaluate.py model.joblib data/test.csv metrics.json
    deps: [src/evaluate.py, model.joblib, data/test.csv]
    metrics: [metrics.json]
```

Chaque étape déclare sa commande, ses **dépendances** (code et données), les **paramètres** qu'elle lit dans `params.yaml`, et ses **sorties**. La commande `dvc repro` exécute le pipeline, puis enregistre dans `dvc.lock` l'empreinte de chaque dépendance et de chaque sortie. Aux exécutions suivantes, elle compare les empreintes actuelles à celles du fichier de verrouillage et ne relance que les étapes dont une entrée a changé, exactement comme l'outil `make` le fait depuis 1976 à partir des dates de modification [^feldman].

<Figure src="pipeline-dvc" num="28.3" alt="Pipeline en trois étapes : prepare transforme taches.csv en train.csv ; train produit model.joblib ; evaluate produit metrics.json. Le paramètre C de params.yaml est modifié : prepare est à jour et ignorée, train et evaluate sont réexécutées.">
  Ce que réexécute `dvc repro` quand on modifie un hyperparamètre. L'étape de préparation, dont aucune entrée n'a changé, est ignorée ; l'entraînement et l'évaluation, qui en dépendent, sont relancés.
</Figure>

:::exemple[Ce que rapporte l'exécution incrémentale]
Sur le jeu complet, l'étape `prepare` dure 20 minutes (nettoyage de 2 Go de textes), `train` 5 minutes et `evaluate` 1 minute. On veut tester quatre valeurs de l'hyperparamètre de régularisation `C`.

- **Tout relancer à chaque fois** : $4 \times (20 + 5 + 1) = 104$ minutes.
- **Avec `dvc repro`** : `prepare` ne s'exécute qu'une fois, puisque ni ses données ni son code ne changent, soit $20 + 4 \times (5 + 1) = 44$ minutes.

Le gain dépasse le temps de calcul : chaque résultat est associé, dans `dvc.lock`, aux empreintes exactes des données, du code et des paramètres qui l'ont produit.
:::

`dvc.yaml` et `params.yaml` sont de simples fichiers versionnés par Git : on retrouve la configuration déclarative et versionnée des semestres précédents, appliquée à un entraînement. Au bloc 2, Airflow prendra le relais pour orchestrer ces étapes dans le temps (chaque nuit, avec reprise sur erreur) ; DVC reste l'outil qui garantit **ce que** l'on a calculé.

[^feldman]: Stuart I. Feldman, « Make: A Program for Maintaining Computer Programs », *Software: Practice and Experience*, vol. 9, n° 4, 1979. L'outil a été écrit aux Bell Labs en 1976.

## 8. Versionner le modèle

Le modèle entraîné est lui aussi un fichier, souvent volumineux : on le versionne avec DVC comme une donnée (c'est une sortie du pipeline, `model.joblib`). Mais un fichier de modèle seul ne sert à rien si l'on ne sait pas **d'où il vient**. On appelle **lignage** (*lineage*) l'ensemble des informations qui relient un modèle à tout ce qui l'a produit :

| Information | Exemple | Où elle vit |
|---|---|---|
| Version du code | commit `4e1b9c2` | Git |
| Version des données | empreinte de `train.csv` | `dvc.lock` |
| Paramètres | `C: 0.5`, `seed: 42` | `params.yaml`, `dvc.lock` |
| Environnement | digest de l'image d'entraînement | pipeline de CI |
| Métriques | précision 0,941 sur le jeu de test | `metrics.json` |

Avec ce lignage, la question du début trouve une réponse mécanique :

:::exemple[Reconstruire le modèle v1]
Le service en production expose la version de son modèle, qui correspond au commit `4e1b9c2` du dépôt d'entraînement. Sur n'importe quelle machine qui a accès au dépôt et au stockage distant :

```bash
git clone http://forge/etudiant/listify-ml.git && cd listify-ml
git checkout 4e1b9c2            # code, params.yaml, dvc.yaml et dvc.lock de v1
dvc pull                        # les données et le modèle de v1, désignés par dvc.lock
dvc repro                       # « Data and pipelines are up to date. »
```

Le dernier message signifie que toutes les empreintes des fichiers présents correspondent à celles de `dvc.lock` : on a bien reconstitué l'état exact du jour où v1 a été entraîné. Pour vérifier la reproductibilité, on force un réentraînement (`dvc repro --force`) dans l'image d'entraînement de v1 : avec les mêmes données, le même code, les mêmes paramètres, la même graine et le même environnement, on doit retrouver le même modèle et la même précision.
:::

:::danger[Un fichier de modèle est du code exécutable]
Les modèles scikit-learn se sauvegardent le plus souvent avec `pickle` ou `joblib`. Or charger un fichier `pickle` peut **exécuter du code arbitraire** : la documentation de Python l'écrit en toutes lettres, et recommande de ne jamais charger un fichier dont on n'est pas sûr de la provenance [^pickle]. Un modèle téléchargé sur Internet, ou déposé dans un stockage partagé mal protégé, est donc une porte d'entrée. Pour un modèle échangé entre équipes, on préfère des formats qui ne contiennent que des données (comme ONNX), ou l'on vérifie l'empreinte du fichier avant de le charger, ce que le lignage permet justement.
:::

[^pickle]: Documentation de Python, module `pickle` : « Warning: The pickle module is not secure. Only unpickle data you trust. » [docs.python.org/3/library/pickle.html](https://docs.python.org/3/library/pickle.html).

## 9. Limites et tensions

La reproductibilité parfaite a des limites qu'un ingénieur doit connaître :

- **le matériel** : certains calculs sur GPU ne sont pas déterministes ; on vise alors une reproductibilité **statistique** (même précision à la dispersion près) plutôt qu'au bit près ;
- **le coût** : conserver toutes les versions des données a un prix, qu'on maîtrise par la granularité (§6.4) et par le nettoyage des versions inutiles (`dvc gc`) ;
- **le droit** : le Règlement général sur la protection des données (RGPD) donne à toute personne le droit d'obtenir l'effacement de ses données personnelles (article 17) [^rgpd]. Or un système qui conserve **toutes** les versions de ses données d'entraînement, par principe immuables, conserve aussi les données d'une personne qui a demandé leur effacement. Il faut donc prévoir, dès la conception, comment purger une personne de toutes les versions et du stockage distant, et comment réentraîner les modèles qui en dépendaient. La reproductibilité n'est pas un absolu : elle se négocie avec d'autres exigences, et c'est une décision d'architecture (C1). Le chapitre 38 y reviendra.

[^rgpd]: Règlement (UE) 2016/679 du Parlement européen et du Conseil du 27 avril 2016 (RGPD), article 17, « Droit à l'effacement ».

## Ce qu'il faut retenir

<div className="retenir">

1. **Répétabilité** (moi, même montage), **reproductibilité** (un autre, même montage), **réplicabilité** (un autre, autre montage). La production exige au minimum la reproductibilité, par une machine neutre, à partir d'un identifiant.
2. Un modèle est déterminé par **cinq entrées** : code, données, configuration, environnement, aléa. Il faut figer les cinq.
3. L'**aléa** pèse autant qu'une « amélioration » : sur un même jeu, trois points d'écart entre graines (89,0 % à 92,0 %). Fixer la graine, et comparer sur plusieurs graines.
4. Les **versions des bibliothèques** changent le modèle sans changer le code (scikit-learn 0.22). Épingler, verrouiller, idéalement entraîner dans une image identifiée par son digest, et écrire les hyperparamètres explicitement.
5. Le **stockage adressé par le contenu** nomme un fichier par l'empreinte de son contenu. Git versionne l'adresse (fichier `.dvc`), DVC stocke le contenu (cache, stockage distant). C'est le principe de Git lui-même.
6. DVC déduplique **par fichier** : la granularité des données fixe le coût du versionnement. On n'entraîne jamais sur une source vivante, mais sur un **instantané versionné**.
7. `dvc.yaml` décrit les étapes, `dvc.lock` enregistre les empreintes, `dvc repro` ne relance que ce qui a changé.
8. Le **lignage** (commit, empreinte des données, paramètres, environnement, métriques) permet de reconstruire un modèle déployé : `git checkout`, `dvc pull`, `dvc repro`. Un fichier `pickle` est du code exécutable.

</div>

## Regard recherche

:::recherche
La reproductibilité est devenue un sujet de recherche à part entière en apprentissage automatique, où l'on a constaté que de nombreux résultats publiés ne résistaient pas à une nouvelle exécution :

- **Joelle Pineau et al., « Improving Reproducibility in Machine Learning Research (A Report from the NeurIPS 2019 Reproducibility Program) », *Journal of Machine Learning Research*, 2021.** Le bilan du programme de reproductibilité de la conférence NeurIPS, avec la liste de contrôle (*checklist*) désormais demandée aux auteurs.
- **Odd Erik Gundersen, Sigbjørn Kjensmo, « State of the Art: Reproducibility in Artificial Intelligence », *AAAI*, 2018.** Une étude systématique de 400 articles de conférences d'IA, qui mesure la part de ceux qui documentent assez leurs expériences pour être reproduits.
- **Xavier Bouthillier, César Laurent, Pascal Vincent, « Unreproducible Research is Reproducible », *ICML*, 2019.** Une mise en garde très claire sur la confusion entre répétabilité et reproductibilité, et sur le rôle des graines.
- **Xavier Bouthillier et al., « Accounting for Variance in Machine Learning Benchmarks », *MLSys*, 2021.** Combien de sources de variance (graines, découpages, ordre des données) faut-il prendre en compte pour conclure qu'un modèle est meilleur qu'un autre ? Le prolongement rigoureux de l'exemple du §4.1.
- **Manasi Vartak et al., « ModelDB: A System for Machine Learning Model Management », atelier HILDA de SIGMOD, 2016.** L'un des premiers systèmes de gestion des versions et du lignage des modèles, ancêtre des registres comme celui de MLflow (ch. 31).

Piste d'innovation : **désapprendre** (*machine unlearning*), c'est-à-dire retirer l'influence de données précises d'un modèle déjà entraîné sans tout réentraîner, est un domaine très actif, directement motivé par le droit à l'effacement du §9.
:::

## Bibliographie du chapitre

<div className="biblio">

### Sources primaires

- Documentation de DVC : [dvc.org/doc](https://dvc.org/doc), en particulier « Get Started », « Data Pipelines » et « Internal Files ».
- ACM, *Artifact Review and Badging, Version 1.1*, 2020 : les définitions du §2.
- Scott Chacon, Ben Straub, *Pro Git*, chapitre 10 : le stockage adressé par le contenu, dans Git.

### Lectures recommandées

- Chip Huyen, *Designing Machine Learning Systems*, O'Reilly, 2022, chapitre 6 (« Model Development and Offline Evaluation »), section sur le suivi et le versionnement des expériences.
- Valliappa Lakshmanan, Sara Robinson, Michael Munn, *Machine Learning Design Patterns*, O'Reilly, 2020, motif *Repeatable Splitting* (chapitre 6) : découper les données de façon déterministe.

### Pour aller plus loin

- Les articles de la rubrique « Regard recherche ».
- Documentation de NumPy, « Random Generator » : le fonctionnement des générateurs pseudo-aléatoires et de leurs graines.

</div>
