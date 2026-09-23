---
title: "Ch. 34 : Le ML sur Kubernetes, Kubeflow Pipelines et KServe"
sidebar_label: "Ch. 34 : Kubeflow et KServe"
hide_title: true
---

import ChapterHead from '@site/src/components/ChapterHead';
import Figure from '@site/src/components/Figure';

<ChapterHead
  kicker="Semestre 3 · Bloc 3 · Chapitre 34"
  title="Le ML sur Kubernetes : Kubeflow Pipelines et KServe"
  lecture="55 min"
  competences={['C1', 'C3', 'C5']}
/>

:::objectifs
À l'issue de ce chapitre, vous saurez :

- expliquer ce qu'apporte le fait d'exécuter chaque étape d'un pipeline de ML dans son propre conteneur, et ce que cela coûte ;
- écrire un pipeline avec le SDK de Kubeflow Pipelines, le compiler, et décrire ce que devient chaque étape sur le cluster ;
- interpréter la chronologie d'une exécution : travail utile, coût d'orchestration, effet du cache ;
- décrire un `InferenceService` de KServe et ce qu'il remplace dans le service écrit à la main au chapitre 33 ;
- comparer honnêtement Airflow et Kubeflow Pipelines, et choisir selon le contexte d'une équipe.
:::

## 1. Un conteneur par étape

Le TP 26 a fait tourner l'entraînement de Listify dans Airflow. Chaque tâche lançait une commande dans **le même dossier**, avec **le même environnement Python**. Le TP s'est heurté à la limite de ce choix : deux exécutions simultanées se sont marché dessus, l'une écrasant l'instantané de données de l'autre, jusqu'à ce que DVC refuse de travailler (TP 26, §6.1). Le remède évoqué alors était de donner à chaque exécution son propre espace de travail.

Kubernetes offre ce remède en natif, et plus encore : chaque **étape** peut s'exécuter dans son **propre conteneur**, avec sa propre image, ses propres ressources (un GPU pour l'entraînement, rien pour l'extraction), et des entrées et sorties **déclarées** plutôt que partagées par un dossier commun. C'est l'idée qui a donné naissance à Kubeflow, annoncé par Google fin 2017 pour « rendre les déploiements de ML sur Kubernetes simples, portables et évolutifs », et accepté comme projet en incubation par la CNCF en 2023 [^kubeflow].

:::definition[Pipeline de ML conteneurisé]
Pipeline dont chaque étape est une image de conteneur exécutée dans son propre pod, qui reçoit ses entrées et produit ses sorties sous forme d'**artefacts** et de **paramètres** déclarés, transmis par un stockage partagé et tracés dans une base de métadonnées. L'orchestrateur ne partage aucun état de fichiers entre étapes.
:::

Cette définition corrige les deux défauts rencontrés au bloc 2 : l'état partagé (TP 26) et l'environnement partagé, qui oblige toutes les étapes à s'entendre sur les mêmes versions de bibliothèques. Elle a aussi un prix, que ce chapitre va mesurer.

Kubeflow est un ensemble de projets : notebooks, entraînement distribué, réglage d'hyperparamètres (Katib), et surtout **Kubeflow Pipelines** (KFP) pour les pipelines et **KServe**, né sous le nom de KFServing, pour le service des modèles. Ce chapitre traite ces deux derniers.

[^kubeflow]: Documentation de Kubeflow, « Introduction » et historique du projet. [kubeflow.org/docs](https://www.kubeflow.org/docs/). Les mesures de ce chapitre ont été faites avec Kubeflow Pipelines 2.17.2 (serveur) et le SDK `kfp` 2.17.0.

## 2. Kubeflow Pipelines

### 2.1 Écrire un pipeline

On décrit les étapes en Python, avec des **composants** : des fonctions décorées, dont le corps s'exécutera dans une image choisie. Voici l'entraînement de Listify, réduit à trois composants :

```python title="pipeline_listify.py"
from kfp import compiler, dsl

IMAGE = "docker.io/library/python:3.13-slim"


@dsl.component(base_image=IMAGE, packages_to_install=["pandas==3.0.6"])
def extraire(date_fin: str, instantane: dsl.Output[dsl.Dataset]):
    import urllib.request
    urllib.request.urlretrieve("http://host.containers.internal:8000/taches_completes.csv", "/tmp/base.csv")
    import pandas as pd
    df = pd.read_csv("/tmp/base.csv")
    df[df.cree_le < date_fin].to_csv(instantane.path, index=False)


@dsl.component(base_image=IMAGE, packages_to_install=["pandas==3.0.6", "scikit-learn==1.9.1"])
def entrainer(instantane: dsl.Input[dsl.Dataset], modele: dsl.Output[dsl.Model]) -> float:
    import joblib
    import pandas as pd
    from sklearn.compose import ColumnTransformer
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    df = pd.read_csv(instantane.path).sort_values("cree_le", kind="stable")
    df["categorie"] = df.categorie.str.lower().replace({"admin": "administratif"})
    coupure = int(len(df) * 0.8)
    train, test = df.iloc[:coupure], df.iloc[coupure:]
    m = Pipeline([("tfidf", ColumnTransformer([("titre", TfidfVectorizer(min_df=3, ngram_range=(1, 2)), "titre")])),
                  ("clf", LogisticRegression(C=5, max_iter=500))]).fit(train[["titre"]], train.categorie)
    joblib.dump(m, modele.path)
    return float(m.score(test[["titre"]], test.categorie))


@dsl.component(base_image=IMAGE)
def annoncer(precision: float) -> str:
    return f"précision sur les tâches récentes : {precision:.4f}"


@dsl.pipeline(name="entrainement-listify")
def entrainement_listify(date_fin: str = "2026-01-05"):
    e = extraire(date_fin=date_fin)
    t = entrainer(instantane=e.outputs["instantane"])
    with dsl.If(t.outputs["Output"] >= 0.85, name="assez-bon"):
        annoncer(precision=t.outputs["Output"])


if __name__ == "__main__":
    compiler.Compiler().compile(entrainement_listify, "entrainement_listify.yaml")
```

Trois différences avec le DAG du chapitre 32 sautent aux yeux.

- **Chaque composant est autonome.** Ses imports sont **dans** la fonction, parce que son corps sera copié tel quel dans un conteneur qui ne connaît rien du fichier d'origine. Il déclare son image et les paquets à installer.
- **Les données circulent par des artefacts typés.** `Output[Dataset]` donne au composant un chemin où écrire ; Kubeflow se charge de déposer le fichier dans le stockage d'artefacts et de le fournir, sous un autre chemin, à l'étape suivante. Aucun dossier n'est partagé.
- **Les conditions sont des objets du pipeline.** `dsl.If` n'est pas un `if` Python exécuté à l'écriture, mais une condition évaluée **pendant l'exécution**, sur la valeur réellement produite.

:::warning[Un piège rencontré en écrivant cet exemple]
Un composant qui produit un artefact **et** renvoie une valeur a **plusieurs** sorties. La première version de ce pipeline utilisait `t.output`, et la compilation a échoué :

```text
AttributeError: The task has multiple outputs. Please reference the output by its name.
```

La valeur de retour s'appelle alors `Output`, et l'on écrit `t.outputs["Output"]`.
:::

### 2.2 Ce que reçoit le cluster

La compilation produit un document YAML : ici **221 lignes**, au format de spécification de pipeline de Kubeflow (`schemaVersion: 2.1.0`). Il décrit chaque composant (image, commande, entrées, sorties), les dépendances entre tâches, et la condition, écrite comme une expression sur les paramètres : `inputs.parameter_values['pipelinechannel--entrainer-Output']`. C'est ce document, et non le code Python, que l'on soumet au serveur. On retrouve le principe des manifestes Kubernetes du semestre 2 : une **description déclarative**, versionnable, indépendante du langage qui l'a produite.

<Figure src="kfp-architecture" num="34.1" alt="Le pipeline Python est compilé en un YAML de 221 lignes (schéma 2.1), soumis au serveur KFP (API, interface), qui le confie à Argo Workflows. Pour chacune des trois étapes, extraire, entrainer et annoncer, Argo crée un pod driver puis un pod d'exécution. Les artefacts vont dans SeaweedFS, les métadonnées dans MySQL.">
  Ce que devient un pipeline Kubeflow. Chaque étape donne au moins deux pods : un *driver*, qui résout les entrées et consulte le cache, puis le conteneur qui exécute le code.
</Figure>

L'installation de Kubeflow Pipelines en mode autonome, telle qu'elle a été faite pour ce chapitre sur un cluster kind, compte **14 pods** : le serveur d'API et son interface, **Argo Workflows** (le moteur qui exécute réellement le graphe), une base **MySQL** pour les métadonnées d'exécution, **SeaweedFS** comme stockage objet des artefacts, un serveur de cache et plusieurs agents. Ils ont été prêts **161 secondes** après l'application des manifestes, et le nœud occupait alors **3,1 Go** de mémoire.

### 2.3 La chronologie d'une exécution

Le pipeline ci-dessus a été soumis avec `date_fin = 2026-01-05`, sur les mêmes données qu'au TP 26. Il a réussi en **156 secondes**, et l'étape `entrainer` a produit la même précision que l'exécution Airflow du TP 26 : **0,8706** sur les tâches récentes. La condition étant vérifiée, `annoncer` a été exécutée.

<Figure src="kfp-chronologie" num="34.2" alt="Deux chronologies sur un axe de 0 à 160 secondes. Première exécution, 156 secondes : une bande d'orchestration couvre toute la durée ; les trois étapes utiles n'en occupent qu'une partie, extraire 14 secondes, entrainer 27 secondes, annoncer 4 secondes, soit 45 secondes de travail utile, installation des paquets comprise. Seconde exécution avec les mêmes entrées : 56 secondes, uniquement des pods driver, aucun pod d'exécution.">
  Chronologie mesurée. Le travail utile ne représente qu'un peu moins du tiers de la durée ; le reste est le prix de l'isolation. Avec les mêmes entrées, le cache supprime tout le travail, mais pas l'orchestration.
</Figure>

:::exemple[Exemple 34.1 : où passent les 156 secondes]
Les horodatages des conteneurs, relevés dans le cluster, donnent :

| Étape | Pods créés | Durée du conteneur de travail |
|---|---|---|
| `extraire` | 1 *driver* + 1 exécution | 14 s |
| `entrainer` | 1 *driver* + 1 exécution | 27 s |
| `annoncer` | 1 *driver* + 1 exécution | 4 s |
| Pipeline et condition | 2 *drivers* | |
| **Total** | **8 pods** | **45 s de travail** |

Il reste $156 - 45 = 111$ secondes d'orchestration : créer chaque pod, le planifier, démarrer son conteneur, résoudre les entrées, déposer et relire les artefacts. Rapporté aux trois étapes, cela fait environ **37 secondes par étape**.

**Conséquence de conception.** Pour un pipeline de 50 petites étapes de quelques secondes, ce coût fixe dominerait : de l'ordre d'une demi-heure d'orchestration pour quelques minutes de calcul. Un pipeline Kubeflow se découpe en **peu d'étapes substantielles**, pas en une myriade de micro-tâches. C'est la même leçon que l'exécuteur Kubernetes d'Airflow au chapitre 32, §6.1.

**Où se cache une partie du travail utile.** Les 14 et 27 secondes comprennent l'installation de pandas et de scikit-learn, demandée par `packages_to_install` et **refaite à chaque exécution**. En production, on construit une image qui contient déjà ces bibliothèques, et l'on déplace ce coût de l'exécution vers la construction, une fois pour toutes.
:::

:::exemple[Exemple 34.2 : le cache]
Le même pipeline, soumis une seconde fois avec les mêmes paramètres, a réussi en **56 secondes**, et **aucun** pod d'exécution n'a été créé : seuls cinq pods *driver* ont tourné. Chaque *driver* a calculé l'empreinte des entrées de son étape, trouvé dans le cache une exécution identique, et réutilisé ses sorties.

C'est le principe de `dvc repro` (chapitre 28), appliqué par l'orchestrateur lui-même : une étape dont les entrées n'ont pas changé n'est pas recalculée. Deux différences toutefois. DVC compare les empreintes des **fichiers** ; Kubeflow compare la **spécification** de l'étape et ses entrées. Et le cache de Kubeflow suppose que l'étape est déterministe : une étape qui lit l'heure courante ou une source externe mouvante (ici, le fichier servi par HTTP) peut être « servie par le cache » alors que la source a changé. Pour ces étapes, on désactive le cache (`set_caching_options(False)`).

Enfin, même servi entièrement par le cache, le pipeline a coûté 56 secondes : c'est le plancher d'orchestration de cette installation.
:::

## 3. KServe

### 3.1 Un service de modèle déclaré

Au chapitre 33 et au TP 25, le service de prédiction a été écrit à la main : une API FastAPI, un Containerfile, un `Deployment`, un `Service`, des sondes réglées d'après le temps de chargement mesuré. KServe propose de remplacer tout cela par **un seul objet** Kubernetes, l'`InferenceService`, qui déclare **quel** modèle servir et **où** le trouver [^kserve].

```yaml
apiVersion: serving.kserve.io/v1beta1
kind: InferenceService
metadata:
  name: listify-categorie
spec:
  predictor:
    model:
      modelFormat:
        name: sklearn
      storageUri: s3://mlflow-artefacts/1/models/m-.../artifacts
```

<Figure src="kserve-architecture" num="34.3" alt="Un InferenceService déclare un prédicteur de format sklearn et l'URI de stockage du modèle. Le contrôleur KServe crée le pod du prédicteur : un conteneur d'initialisation, storage-initializer, copie le modèle depuis le stockage S3 ou MinIO, puis le serveur de modèle (sklearn, protocoles V1 et V2) le sert. Un client interroge /v1/models/...:predict.">
  Ce que KServe fabrique à partir d'un `InferenceService`. Le même objet déclare le format et l'emplacement du modèle ; KServe fournit le serveur, la mise à l'échelle et la répartition du trafic entre versions.
</Figure>

Le contrôleur de KServe transforme cette déclaration en ressources concrètes :

- un **conteneur d'initialisation** (`storage-initializer`) télécharge le modèle depuis le stockage objet avant le démarrage du serveur ;
- un **serveur de modèle** adapté au format déclaré (scikit-learn, XGBoost, PyTorch, ONNX...) charge le modèle et expose un protocole standard de prédiction, le protocole V1 hérité de TensorFlow Serving ou le protocole V2, dit **Open Inference Protocol**, partagé avec d'autres serveurs comme NVIDIA Triton ;
- la **mise à l'échelle** et, selon le mode de déploiement, la **répartition du trafic** entre une version stable et une version canari (`canaryTrafficPercent`).

[^kserve]: Documentation de KServe. [kserve.github.io/website](https://kserve.github.io/website/). KServe est né dans Kubeflow sous le nom de KFServing, puis est devenu un projet indépendant en 2021.

### 3.2 Deux modes de déploiement

KServe fonctionne selon deux modes, et le choix est structurant. Dans la version 0.20, utilisée au TP 28, ils s'appellent *Knative* (le défaut de l'installation, anciennement *Serverless*) et *Standard* (anciennement *RawDeployment*) ; on choisit le second pour un objet donné par l'annotation `serving.kserve.io/deploymentMode: Standard`.

| | Mode *Knative* (sans serveur) | Mode *Standard* |
|---|---|---|
| Ressources créées | Services Knative | `Deployment`, `Service`, `HorizontalPodAutoscaler` ordinaires |
| Mise à l'échelle | Sur le nombre de requêtes, **jusqu'à zéro réplique** | Sur le processeur ou la mémoire, au moins une réplique |
| Répartition canari | Native (révisions Knative) | **Non** : `canaryTrafficPercent` est ignoré sans erreur, et la nouvelle version reçoit 100 % du trafic (vérifié au TP 28) |
| Dépendances | Knative et une passerelle réseau (Istio, Kourier...) | cert-manager seulement |
| Premier appel après inactivité | **Démarrage à froid** : téléchargement et chargement du modèle | Immédiat |

Le mode *Knative* est séduisant pour un parc de nombreux modèles peu sollicités : une réplique qui ne sert personne ne coûte rien. Mais il ramène le problème mesuré au chapitre 33 : un modèle de Listify met 15 secondes à se charger, que le premier utilisateur après une période d'inactivité subira. Pour un service sur le chemin critique, comme la suggestion de catégorie, on garde au moins une réplique chaude (`minReplicas: 1`), ou l'on choisit le mode *Standard*.

:::exemple[Exemple 34.3 : ce que coûte le passage à zéro]
Une équipe sert 40 modèles, chacun sollicité en moyenne 2 heures par jour, avec une réplique de 500 Mio par modèle quand il est actif.

**Toujours actifs** : $40 \times 500 \text{ Mio} = 20$ Go de mémoire réservés en permanence.

**Mis à zéro quand inactifs** : en moyenne $40 \times \frac{2}{24} \approx 3{,}3$ modèles actifs, soit environ **1,7 Go**. Douze fois moins.

**Le prix** : chaque réveil coûte un démarrage à froid. Si chaque modèle se réveille 10 fois par jour et met 15 secondes à charger, cela fait 400 réveils quotidiens, donc 400 requêtes qui attendent 15 secondes. Acceptable pour un tableau de bord interne, rédhibitoire pour une suggestion affichée pendant la frappe (chapitre 30, §4.1).
:::

### 3.3 Ce que KServe ne fait pas à votre place

KServe standardise le service ; il ne supprime pas les problèmes des chapitres précédents.

- **Le chemin du modèle.** `storageUri` désigne un emplacement **figé** dans le stockage. Le registre MLflow et son alias `champion` ne sont pas compris nativement : il faut qu'une étape de la chaîne (le DAG du TP 26, ou la CI du TP 27) traduise « la version championne » en une URI, et mette à jour l'`InferenceService`. C'est d'ailleurs ce qui le rend compatible avec GitOps : la version servie est écrite dans un fichier versionné.
- **Le prétraitement.** Le serveur scikit-learn appelle `predict` sur ce qu'on lui envoie. Si le modèle attend un tableau à une colonne `titre` (chapitre 31, §5.3), le client doit envoyer exactement ce format, ou l'on ajoute un **transformateur** KServe devant le prédicteur.
- **L'environnement du serveur.** Le serveur scikit-learn de KServe 0.20 embarque **scikit-learn 1.5.2** et Python 3.11. Un modèle entraîné avec scikit-learn 1.9.1, comme celui de Listify, se charge avec un `InconsistentVersionWarning` : c'est exactement la situation du TP 22. Au TP 28, les prédictions se sont révélées identiques sur 4 800 titres, mais rien ne le garantit en général ; on le vérifie à chaque changement de version, ou l'on fournit son propre environnement de service (`ServingRuntime`) avec les bonnes versions.
- **La surveillance de la qualité.** KServe expose des métriques de service (latence, erreurs), pas la dérive des données ni la qualité des prédictions : c'est l'objet du chapitre 35.

Le TP 28 déploiera le modèle de Listify avec KServe, et comparera, chiffres à l'appui, cet objet de quelques lignes au service écrit à la main au TP 25.

## 4. Airflow ou Kubeflow Pipelines ?

La question revient dans toutes les équipes, et elle n'a pas de réponse universelle. Le tableau suivant compare ce que les deux outils ont réellement fait dans ce cours, sur le même pipeline.

| Critère | Airflow (TP 26) | Kubeflow Pipelines (ce chapitre) |
|---|---|---|
| Unité d'exécution | Une tâche : processus, ou pod avec l'exécuteur Kubernetes | Un conteneur par étape, **toujours** |
| Échange de données | Par le stockage, à la charge de l'auteur ; XCom pour les petites valeurs | Artefacts et paramètres typés, gérés par la plateforme |
| Isolation des exécutions | À construire (TP 26, §6.1) | Native : chaque étape a son pod et ses entrées |
| Notion de temps | Centrale : date logique, rattrapage, calendriers | Exécutions récurrentes, sans sémantique de rattrapage aussi riche |
| Cache des étapes | Aucun (on s'appuie sur DVC) | Intégré, par empreinte des entrées |
| Métadonnées et lignage des artefacts | Journaux et XCom ; lignage ML délégué à MLflow | Base de métadonnées intégrée (qui a produit quel artefact) |
| Dépendance à Kubernetes | Aucune (tourne sur un poste) | Totale |
| Empreinte mesurée | Un processus et quelques composants (`standalone`) | 14 pods, 3,1 Go |
| Durée d'une exécution du pipeline | 83 s, redéploiement compris (TP 26) | 156 s, dont 111 s d'orchestration |
| Cas d'usage d'origine | Pipelines de données généralistes | Pipelines de ML sur Kubernetes |

Quelques repères pour choisir :

- **Une équipe de données** qui orchestre déjà des extractions, des transformations et des rapports gagnera à rester sur **Airflow**, et à déporter les étapes lourdes dans des pods (`KubernetesPodOperator`). Son point fort, la gestion du temps et du rattrapage, est précisément ce qui manque aux pipelines de ML centrés sur Kubernetes.
- **Une équipe de ML** dont les étapes ont des besoins hétérogènes (GPU, grandes mémoires, images différentes), qui veut l'isolation par construction et le lignage des artefacts sans l'écrire, et qui dispose déjà d'un cluster exploité, trouvera dans **Kubeflow Pipelines** un outil fait pour elle.
- **Les deux se combinent** : Airflow garde le calendrier et les dépendances avec le reste du système d'information, et déclenche un pipeline Kubeflow comme une tâche parmi d'autres.

:::warning[Le coût de plateforme]
Le tableau cache l'argument le plus lourd : Kubeflow Pipelines suppose un cluster Kubernetes **exploité**, avec ses mises à jour, sa sécurité, son stockage et sa supervision. Quatorze pods et une base MySQL de plus à maintenir, c'est un service à part entière. Pour une équipe de trois personnes sans plateforme Kubernetes existante, ce coût dépasse souvent le bénéfice. La bonne question n'est pas « quel outil est le meilleur ? », mais « qui, dans l'équipe, exploitera cette plateforme dans un an ? ».
:::

## 5. Argo Workflows, le moteur sous le capot

La figure 34.1 le montre : Kubeflow Pipelines n'exécute pas lui-même le graphe. Il le traduit pour **Argo Workflows**, un moteur de flux de travaux natif de Kubernetes, du même projet Argo que l'Argo CD du TP 20. Un *workflow* Argo est un objet Kubernetes dont chaque étape est un pod.

On peut utiliser Argo Workflows **directement**, sans Kubeflow : on décrit alors le graphe en YAML, sans SDK Python, sans cache ni base de métadonnées de ML, mais avec un moteur beaucoup plus léger. C'est un choix fréquent pour les équipes qui veulent des pipelines conteneurisés sans la plateforme Kubeflow complète. On obtient ainsi une échelle à trois barreaux, du plus léger au plus intégré : Airflow (avec des pods pour les étapes lourdes), Argo Workflows, Kubeflow Pipelines.

## Ce qu'il faut retenir

<div className="retenir">

1. Sur Kubernetes, **chaque étape** d'un pipeline peut tourner dans **son** conteneur, avec ses ressources et ses entrées déclarées : l'état partagé et l'environnement partagé du bloc 2 disparaissent par construction.
2. **Kubeflow Pipelines** : des composants Python autonomes, compilés en une spécification YAML (221 lignes pour trois étapes), exécutés par **Argo Workflows** ; les artefacts transitent par un stockage objet, les métadonnées par une base.
3. Chaque étape coûte au moins **deux pods** (un *driver*, une exécution). Mesuré : 156 s pour 45 s de travail utile, soit environ 37 s d'orchestration par étape. On découpe en **peu d'étapes substantielles**, et l'on préconstruit les images au lieu d'installer les paquets à chaque exécution.
4. Le **cache** réutilise les étapes dont la spécification et les entrées n'ont pas changé (56 s, aucun pod d'exécution) ; il suppose des étapes déterministes.
5. **KServe** remplace le service écrit à la main par un `InferenceService` : un format, un emplacement, et KServe fournit l'initialisation, le serveur, la mise à l'échelle et le canari.
6. Le mode *Knative* peut descendre à **zéro réplique** (douze fois moins de mémoire dans l'exemple 34.3) au prix de **démarrages à froid** ; pour un service sur le chemin critique, on garde une réplique chaude.
7. KServe ne comprend ni l'alias du registre, ni le prétraitement, ni la dérive : il faut encore une chaîne qui traduit « le champion » en emplacement, et une surveillance de la qualité.
8. **Airflow** excelle sur le temps et le rattrapage ; **Kubeflow Pipelines** sur l'isolation, les artefacts et le lignage. Le vrai critère de choix est le coût d'exploitation de la plateforme.

</div>

## Regard recherche

:::recherche
Les plateformes de ML sur Kubernetes prolongent une lignée de travaux industriels et académiques sur l'automatisation du cycle de vie des modèles :

- **Denis Baylor et al., « TFX: A TensorFlow-Based Production-Scale Machine Learning Platform », *KDD*, 2017**, et **Konstantinos Katsiapis et al., « Towards ML Engineering: A Brief History Of TensorFlow Extended (TFX) », prépublication arXiv, 2020.** L'expérience de Google, dont Kubeflow Pipelines reprend l'idée de composants aux entrées et sorties déclarées, et de métadonnées d'exécution tracées.
- **Brendan Burns et al., « Borg, Omega, and Kubernetes », *Communications of the ACM*, 2016.** Les principes d'ordonnancement dont héritent les pipelines conteneurisés : unité d'exécution isolée, état déclaré, boucle de réconciliation.
- **Andrei Paleyes, Raoul-Gabriel Urma, Neil D. Lawrence, « Challenges in Deploying Machine Learning: a Survey of Case Studies », *ACM Computing Surveys*, 2022.** Un recensement des difficultés rencontrées à chaque étape du déploiement, qui montre que l'outillage ne résout qu'une partie d'entre elles.
- **Daniel Crankshaw et al., « Clipper », *NSDI*, 2017** (chapitre 30) et les travaux sur le service sans serveur du chapitre 33, pour les compromis de KServe entre densité et démarrage à froid.

Piste d'innovation : l'exemple 34.1 montre qu'un tiers seulement de la durée d'un pipeline est du travail utile. Réduire le coût fixe d'une étape (pods réutilisés, démarrage à partir d'instantanés, regroupement automatique de petites étapes) rendrait les pipelines conteneurisés pertinents pour des graphes fins, aujourd'hui réservés aux orchestrateurs en processus.
:::

## Bibliographie du chapitre

<div className="biblio">

### Sources primaires

- Documentation de Kubeflow Pipelines : « Components », « Pipelines », « Caching ». [kubeflow.org/docs/components/pipelines](https://www.kubeflow.org/docs/components/pipelines/)
- Documentation de KServe : « InferenceService », modes de déploiement *Knative* et *Standard*. [kserve.github.io/website](https://kserve.github.io/website/)
- Documentation d'Argo Workflows. [argoproj.github.io/workflows](https://argoproj.github.io/workflows/)

### Lectures recommandées

- Chip Huyen, *Designing Machine Learning Systems*, O'Reilly, 2022, chapitre 10 (« Infrastructure and Tooling for MLOps ») : plateformes, orchestrateurs, gestion du calcul.
- Hannes Hapke, Catherine Nelson, *Building Machine Learning Pipelines*, O'Reilly, 2020 : TFX et Kubeflow Pipelines de bout en bout.

### Pour aller plus loin

- Les articles de la rubrique « Regard recherche ».
- La spécification de l'Open Inference Protocol (protocole V2), partagée par KServe, Triton et MLServer.

</div>
