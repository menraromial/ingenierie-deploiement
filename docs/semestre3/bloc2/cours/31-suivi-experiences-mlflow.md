---
title: "Ch. 31 : Suivre les expériences et gérer les modèles avec MLflow"
sidebar_label: "Ch. 31 : Expériences et registre (MLflow)"
hide_title: true
---

import ChapterHead from '@site/src/components/ChapterHead';
import Figure from '@site/src/components/Figure';

<ChapterHead
  kicker="Semestre 3 · Bloc 2 · Chapitre 31"
  title="Suivre les expériences et gérer les modèles avec MLflow"
  lecture="55 min"
  competences={['C4', 'C5']}
/>

:::objectifs
À l'issue de ce chapitre, vous saurez :

- distinguer ce que versionne DVC de ce que doit tracer un outil de suivi d'expériences, et pourquoi il faut les deux ;
- définir une expérience, un run, un paramètre, une métrique, une étiquette et un artefact, et instrumenter un entraînement avec MLflow ;
- choisir une configuration parmi des dizaines sans vous laisser tromper par le bruit de mesure ni par le biais de sélection ;
- décrire l'architecture d'un serveur de suivi et dimensionner ce qu'il stocke ;
- expliquer ce que contient un modèle au format MLflow (saveurs, signature, environnement) et éviter ses pièges ;
- gérer les versions d'un modèle dans un registre, les promouvoir et les retirer par des alias, et retrouver le lignage complet d'un modèle en production.
:::

## 1. Douze essais, et aucun commit

Reprenez le dépôt `listify-ml` du TP 23. Vous voulez savoir si `C = 5` et `min_df = 3` sont de bons réglages. Vous essayez trois valeurs de `C` et quatre de `min_df` : douze entraînements. DVC sait rejouer n'importe lequel d'entre eux, **à condition de l'avoir commité**. Or personne ne commite douze essais dont onze seront abandonnés. À la fin de l'après-midi, les résultats vivent dans un terminal qu'on a fermé, dans un tableur rempli à la main, ou nulle part.

C'est exactement la situation de Claire au TP 22 (« C=10 marchait mieux, j'ai aussi essayé 5 »), et ce n'est pas un défaut de discipline : c'est un défaut d'outil. Le versionnement répond à la question « comment refaire **ce** modèle ? ». L'exploration pose une autre question : « parmi **tout ce que j'ai essayé**, qu'est-ce qui a marché, dans quelles conditions ? ». Il faut, pour y répondre, un système qui enregistre **chaque** exécution automatiquement, qu'on la garde ou non.

:::definition[Suivi d'expériences]
Enregistrement systématique, pour chaque exécution d'un entraînement, de ce qui la définit (paramètres, version du code et des données) et de ce qu'elle a produit (métriques, fichiers, modèle), dans un stockage interrogeable, afin de comparer les exécutions entre elles et de retrouver celle qui a produit un résultat donné [^zaharia].
:::

Le besoin a été formalisé à la fin des années 2010, quand les équipes ont constaté que leurs modèles de production étaient issus de milliers d'essais dont elles ne gardaient pas trace. ModelDB, développé au MIT à partir de 2016, est l'un des premiers systèmes académiques dédiés à la gestion des modèles et de leurs expériences [^vartak]. MLflow, lancé par Databricks en 2018 et placé depuis sous l'égide de la Linux Foundation, est devenu l'outil libre le plus répandu [^zaharia]. On l'utilise dans ce cours parce qu'il est libre, qu'il fonctionne sans service extérieur, et que ses concepts se retrouvent dans tous ses concurrents (Weights & Biases, Neptune, les services des fournisseurs de cloud).

:::exemple[Exemple 31.1 : ce que coûte le tableur]
Une data scientist mène une campagne de réglage : 3 valeurs de `C`, 4 de `min_df`, 3 graines pour mesurer la dispersion, soit $3 \times 4 \times 3 = 36$ entraînements. Pour chacun, elle recopie à la main 4 paramètres et 2 métriques dans un tableur : 6 cellules, $36 \times 6 = 216$ saisies.

**Le taux d'erreur.** Les études sur les tableurs trouvent des taux d'erreur par cellule de l'ordre du pour cent [^panko]. Prenons une hypothèse prudente, deux fois plus basse : 0,5 % d'erreurs de saisie. Avec 216 saisies, on attend $216 \times 0{,}005 \approx 1{,}1$ erreur, et la probabilité qu'**aucune** cellule ne soit fausse vaut :

$$
0{,}995^{216} \approx 0{,}34.
$$

Deux fois sur trois, le tableau contient au moins une erreur. Si elle tombe sur la meilleure ligne, c'est le mauvais modèle qui part en production.

**Ce qui manque de toute façon.** Même sans erreur, le tableur ne dit pas quel commit, quelles données, quelle version de scikit-learn ont produit chaque ligne. Un outil de suivi enregistre tout cela sans saisie, en moins de 20 ms par exécution (§4.3).
:::

[^zaharia]: Matei Zaharia et al., « Accelerating the Machine Learning Lifecycle with MLflow », *IEEE Data Engineering Bulletin*, vol. 41, n° 4, 2018.

[^vartak]: Manasi Vartak et al., « ModelDB: a system for machine learning model management », *Workshop on Human-In-the-Loop Data Analytics (HILDA)*, 2016.

[^panko]: Raymond R. Panko, « What We Know About Spreadsheet Errors », *Journal of End User Computing*, vol. 10, n° 2, 1998 (révisé en 2008). Cette synthèse d'études expérimentales et d'audits de tableurs réels conclut que les erreurs sont la règle plutôt que l'exception.

## 2. Le vocabulaire du suivi

MLflow Tracking organise l'information en quelques objets, que l'on retrouve sous d'autres noms dans tous les outils du domaine [^mlflowdoc].

<Figure src="mlflow-modele-donnees" num="31.1" alt="Une expérience, listify-categorie, regroupe des runs nommés C1-min_df1, C5-min_df3, C20-min_df2. Le contenu d'un run : des paramètres (C = 20, min_df = 2), des métriques (precision_val = 0,898), des étiquettes (donnees = v2) et des artefacts (fichiers, graphiques). La fonction log_model produit, à partir d'un run, un modèle journalisé identifié par models:/m-2889..., qui contient le fichier MLmodel, le modèle sérialisé, la signature et l'environnement.">
  Le modèle de données de MLflow. Une expérience regroupe des runs ; un run enregistre ce qui l'a défini et ce qu'il a produit ; un modèle journalisé est un artefact particulier, que l'on pourra enregistrer au registre (§6).
</Figure>

- Une **expérience** regroupe les exécutions qui répondent à une même question : « quel modèle pour suggérer une catégorie ? ». Elle porte un nom (`listify-categorie`).
- Un **run** est **une** exécution d'un entraînement. Il reçoit un identifiant unique (une chaîne de 32 caractères hexadécimaux), une date de début et de fin, un statut (en cours, terminé, échoué).
- Un **paramètre** est une entrée fixée **avant** l'exécution : `C`, `min_df`, le nom du fichier de données. Il est enregistré une fois, sous forme de texte, et ne change plus.
- Une **métrique** est une valeur numérique **mesurée** pendant ou après l'exécution : une précision, une perte. Elle peut être enregistrée plusieurs fois avec un numéro d'étape (`step`), ce qui trace une courbe d'apprentissage.
- Une **étiquette** (*tag*) est une annotation libre, modifiable après coup : `donnees = v2`, `auteur = claire`, `abandonne = oui`. MLflow en pose certaines lui-même : nom du script, utilisateur, et commit Git lorsque le script est exécuté depuis un dépôt Git (`mlflow.source.git.commit`).
- Un **artefact** est un fichier produit par le run : un graphique, une matrice de confusion, un rapport, et surtout le modèle lui-même.

La frontière entre paramètre et métrique est celle entre **cause** et **effet**. Se tromper de case a des conséquences pratiques : on ne peut pas trier les runs par un paramètre enregistré comme métrique sans fausser la comparaison, ni tracer l'évolution d'une métrique enregistrée comme paramètre.

Instrumenter un entraînement tient en quelques lignes. Voici la campagne de réglage de Listify, exécutée sur les données v2 du TP 23 :

```python title="campagne.py"
import mlflow
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

mlflow.set_tracking_uri("sqlite:///mlflow.db")          # §4 : où sont stockés les runs
mlflow.set_experiment("listify-categorie")

tout = pd.read_csv("data/prepared/train.csv")           # les 80 % les plus anciens
coupure = int(len(tout) * 7 / 8)                         # 70 % entraînement, 10 % validation
train, val = tout.iloc[:coupure], tout.iloc[coupure:]

for C in [1, 5, 20]:
    for min_df in [1, 2, 3, 5]:
        with mlflow.start_run(run_name=f"C{C}-min_df{min_df}"):
            mlflow.log_params({"C": C, "min_df": min_df, "ngram_max": 2, "max_iter": 500})
            mlflow.set_tag("donnees", "v2")
            modele = Pipeline([
                ("tfidf", TfidfVectorizer(min_df=min_df, ngram_range=(1, 2))),
                ("clf", LogisticRegression(C=C, max_iter=500)),
            ]).fit(train.titre, train.categorie)
            mlflow.log_metric("precision_val", modele.score(val.titre, val.categorie))
            mlflow.log_metric("vocabulaire", len(modele.named_steps["tfidf"].vocabulary_))
```

Le bloc `with mlflow.start_run()` ouvre un run et le ferme à la sortie, en le marquant « échoué » si une exception survient : un essai qui plante reste visible, avec ses paramètres, au lieu de disparaître. Remarquez aussi que le choix se fait sur un jeu de **validation** découpé dans l'entraînement : le jeu de test du TP 23 n'est pas touché (§3).

:::exemple[Exemple 31.2 : la campagne, relue en une requête]
Les douze runs ont pris 7,7 secondes, entraînements compris. On les relit et on les trie sans aucune saisie :

```python
runs = mlflow.search_runs(order_by=["metrics.precision_val DESC"])
print(runs[["tags.mlflow.runName", "params.C", "params.min_df", "metrics.precision_val"]].to_string(index=False))
```

```text
tags.mlflow.runName params.C params.min_df  metrics.precision_val
        C20-min_df2       20             2               0.898333
        C20-min_df1       20             1               0.897917
         C5-min_df2        5             2               0.894167
         C5-min_df1        5             1               0.894167
         C5-min_df3        5             3               0.892500
        C20-min_df5       20             5               0.892083
        C20-min_df3       20             3               0.891667
         C1-min_df1        1             1               0.891667
         C1-min_df2        1             2               0.889167
         C5-min_df5        5             5               0.888750
         C1-min_df3        1             3               0.882917
         C1-min_df5        1             5               0.875000
```

`search_runs` renvoie un tableau pandas : on peut filtrer (`filter_string="params.C = '20'"`), grouper, tracer. L'interface web de MLflow affiche le même tableau, avec des graphiques de comparaison entre runs. Notez que les paramètres reviennent sous forme de **texte** (`'20'`) : MLflow les stocke ainsi, et il faut les convertir pour faire des calculs.

La configuration `C = 20, min_df = 2` arrive en tête, à 89,8 %. Faut-il l'adopter ? C'est la question du paragraphe suivant.
:::

[^mlflowdoc]: Documentation de MLflow, « MLflow Tracking ». [mlflow.org/docs/latest](https://mlflow.org/docs/latest/). Les exemples de ce chapitre ont été exécutés avec MLflow 3.16.1.

## 3. Choisir sans se laisser tromper

Un outil de suivi rend facile d'essayer beaucoup de configurations. Il rend donc facile une erreur statistique : prendre la meilleure d'entre elles pour meilleure qu'elle n'est.

### 3.1 Le bruit de mesure

Une précision mesurée sur un jeu fini est une **estimation**. Sur $n$ exemples, si la vraie précision vaut $p$, l'écart-type de l'estimation vaut approximativement :

$$
\sigma = \sqrt{\frac{p\,(1-p)}{n}}.
$$

:::exemple[Exemple 31.3 : les douze runs sont-ils vraiment différents ?]
Le jeu de validation compte $n = 2\,400$ tâches, pour une précision voisine de $p = 0{,}894$ :

$$
\sigma = \sqrt{\frac{0{,}894 \times 0{,}106}{2\,400}} \approx 0{,}0063,
$$

soit 0,63 point. Les quatre premières configurations (89,4 % à 89,8 %) tiennent dans un intervalle de 0,4 point, plus petit que l'écart-type de la mesure : le classement entre elles est **du bruit**. Seules les configurations les plus régularisées (`C = 1` avec `min_df` élevé, 87,5 % à 88,3 %) sont nettement moins bonnes.
:::

### 3.2 Le biais de sélection

Même si toutes les configurations étaient **exactement** équivalentes, leurs précisions mesurées différeraient, à cause du bruit, et l'on en prendrait la plus haute. Cette plus haute valeur surestime systématiquement la vraie performance.

:::exemple[Exemple 31.4 : l'optimisme du meilleur de douze]
Supposons douze configurations de vraie précision identique, mesurées chacune avec un bruit d'écart-type $\sigma = 0{,}63$ point, indépendant d'un run à l'autre. Le maximum de douze variables normales centrées réduites a pour espérance environ $1{,}63$ (valeur obtenue par simulation, ou dans les tables des statistiques d'ordre). La meilleure mesure dépasse donc la vraie précision, en moyenne, de :

$$
1{,}63 \times 0{,}63 \approx 1{,}0 \text{ point}.
$$

Avec cent configurations, l'espérance du maximum passe à environ $2{,}5$, et l'optimisme à $1{,}6$ point. Plus on essaie, plus le meilleur score de validation ment. Cawley et Talbot ont montré que ce biais peut être du même ordre de grandeur que les écarts entre algorithmes que l'on cherche à départager [^cawley].

**Vérification sur Listify.** On réentraîne la configuration gagnante et la configuration de référence du TP 23 sur tout l'entraînement, et on les mesure **une seule fois** sur le jeu de test, jamais utilisé pour choisir :

| Configuration | Validation | Test |
|---|---|---|
| `C = 20, min_df = 2` (gagnante) | 89,8 % | 87,58 % |
| `C = 5, min_df = 3` (référence) | 89,3 % | 87,50 % |

L'avance de 0,5 point en validation s'est réduite à 0,08 point sur le test, soit **4 tâches** sur 4 800. Le §6.3 montrera qu'elle n'est pas significative.
:::

Trois règles en découlent, qu'un outil de suivi permet enfin d'appliquer :

1. **Choisir sur la validation, mesurer sur le test**, une seule fois, à la fin. Un jeu de test consulté pour choisir devient un jeu de validation.
2. **Enregistrer tous les essais**, y compris les mauvais. Le nombre de configurations essayées fait partie du résultat : « meilleur de 12 » et « meilleur de 300 » n'ont pas la même valeur.
3. **Répéter sur plusieurs graines** ou plusieurs découpages quand l'écart est faible, et comparer des moyennes avec leur dispersion (chapitre 28).

[^cawley]: Gavin C. Cawley, Nicola L. C. Talbot, « On Over-fitting in Model Selection and Subsequent Selection Bias in Performance Evaluation », *Journal of Machine Learning Research*, vol. 11, 2010.

## 4. L'architecture d'un serveur de suivi

### 4.1 Trois composants

Dans l'exemple ci-dessus, `set_tracking_uri("sqlite:///mlflow.db")` fait écrire les runs dans un fichier SQLite local. C'est suffisant pour un poste, pas pour une équipe. En équipe, on déploie un **serveur de suivi**, auquel tous les clients s'adressent.

<Figure src="mlflow-architecture" num="31.2" alt="Trois clients, le script d'entraînement, le navigateur et le service de prédiction, s'adressent au serveur de suivi mlflow server, qui expose une API REST sur le port 5000. Le serveur range les runs, paramètres et métriques dans une base de métadonnées (PostgreSQL ou SQLite), et les fichiers et modèles dans un stockage d'artefacts (S3, MinIO ou disque).">
  L'architecture d'un déploiement MLflow en équipe. Les métadonnées, petites et interrogées souvent, vont dans une base relationnelle ; les artefacts, gros et lus rarement, vont dans un stockage objet.
</Figure>

- Le **serveur de suivi** (`mlflow server`) expose une API REST et l'interface web. Il est sans état : on peut le redémarrer ou le répliquer.
- La **base de métadonnées** (*backend store*) contient les expériences, les runs, les paramètres, les métriques, les étiquettes et le registre. En production, c'est une base relationnelle comme PostgreSQL.
- Le **stockage d'artefacts** contient les fichiers : modèles, graphiques, rapports. En production, c'est un stockage objet (S3, MinIO, Google Cloud Storage).

La séparation suit la nature des données, exactement comme au semestre 2 on séparait la base PostgreSQL de Listify de ses fichiers statiques. Une commande typique de lancement :

```bash
mlflow server --host 0.0.0.0 --port 5000 \
  --backend-store-uri postgresql://mlflow:secret@db:5432/mlflow \
  --artifacts-destination s3://mlflow-artefacts
```

Les clients n'ont plus qu'à pointer vers lui, par le code (`mlflow.set_tracking_uri("http://mlflow:5000")`) ou, mieux, par la variable d'environnement `MLFLOW_TRACKING_URI` : la configuration par l'environnement du facteur III des *Twelve-Factor Apps* (chapitre 24). Avec l'option par défaut, le serveur sert aussi d'intermédiaire pour les artefacts : les clients n'ont pas besoin d'identifiants sur le stockage objet, seul le serveur en a.

### 4.2 Ce qu'il stocke

:::exemple[Exemple 31.5 : dimensionner le stockage]
Pour la campagne de l'exemple 31.2 et les deux modèles finaux, on a mesuré : 856 Kio pour la base SQLite (qui contient aussi le schéma et les index de MLflow), et 2 Mio d'artefacts, dont 979 Kio pour chacun des deux modèles journalisés.

**Si l'on journalisait le modèle à chaque run.** Douze runs, un modèle de 979 Kio chacun : $12 \times 0{,}98 \approx 11{,}8$ Mio. Négligeable.

**Avec un modèle de langage.** Remplaçons le classifieur par un petit modèle de langage affiné, de 500 Mo. La même campagne de 36 runs (exemple 31.1), modèle journalisé à chaque run :

$$
36 \times 500 \text{ Mo} = 18 \text{ Go}
$$

pour un seul après-midi de réglage, dont 35 modèles qui ne serviront jamais. La règle pratique : pendant l'exploration, on journalise paramètres et métriques ; on ne journalise le modèle que pour les **candidats**, ceux qu'on envisage d'enregistrer au registre. Et l'on prévoit une politique de suppression des runs abandonnés (`mlflow gc` supprime définitivement les runs placés à la corbeille).
:::

### 4.3 Ce qu'il coûte en temps

:::exemple[Exemple 31.6 : le coût d'une métrique]
Mesuré sur un poste avec une base SQLite locale : un run complet (ouverture, 4 paramètres, 1 métrique, fermeture) prend 15,4 ms ; un appel `log_metric` isolé, 2,84 ms.

**Un entraînement court.** Notre classifieur s'entraîne en environ 0,6 s. 15 ms de suivi représentent 2,5 % de surcoût : invisible.

**Une boucle d'entraînement longue.** Un réseau de neurones entraîné sur 10 000 itérations, qui enregistre 3 métriques (perte, précision, taux d'apprentissage) à **chaque** itération :

$$
10\,000 \times 3 \times 2{,}84 \text{ ms} \approx 85 \text{ s}
$$

de temps perdu à journaliser, et 30 000 lignes dans la base. Enregistrer toutes les 100 itérations divise les deux par cent, sans rien perdre de la forme de la courbe. MLflow propose aussi `log_metrics` (plusieurs métriques en un appel) et une journalisation asynchrone, qui n'attend pas la réponse du serveur. Avec un serveur distant, le coût par appel grimpe de la latence réseau : c'est un argument de plus pour espacer les enregistrements.
:::

## 5. Le format de modèle MLflow

### 5.1 Un dossier, pas un fichier

Au TP 22, le modèle de Claire était un fichier `pickle` sans mode d'emploi : on ne savait ni quelle version de scikit-learn l'avait produit, ni ce qu'il attendait en entrée. MLflow définit un **format de modèle**, qui répond à ces deux questions. La fonction `mlflow.sklearn.log_model` produit un dossier :

```text
MLmodel                      description du modèle (ci-dessous)
model.skops                  le modèle sérialisé
requirements.txt             bibliothèques et versions exactes
python_env.yaml              version de Python et dépendances
conda.yaml                   la même chose, pour conda
input_example.json           un exemple d'entrée
serving_input_example.json   le même, au format attendu par un serveur
```

Le fichier `MLmodel` est la fiche d'identité du modèle. Voici l'essentiel de celui qu'a produit le modèle de référence de Listify :

```yaml title="MLmodel (extrait)"
flavors:
  python_function:
    env:
      conda: conda.yaml
      virtualenv: python_env.yaml
    loader_module: mlflow.sklearn
    model_path: model.skops
    python_version: 3.14.4
  sklearn:
    pickled_model: model.skops
    serialization_format: skops
    sklearn_version: 1.9.1
mlflow_version: 3.16.1
model_id: m-84944822addc45aba0248da928440401
run_id: e6075e659d6a4c498651ef1cfc6bdbef
signature:
  inputs: '[{"type": "string", "name": "titre", "required": true}]'
  outputs: '[{"type": "tensor", "tensor-spec": {"dtype": "object", "shape": [-1]}}]'
```

Trois notions à comprendre.

**Les saveurs** (*flavors*). Un même modèle peut être chargé de plusieurs façons. La saveur `sklearn` le recharge en objet scikit-learn natif, pour qui veut l'inspecter ou le réentraîner. La saveur `python_function`, ou **pyfunc**, le présente sous une interface **unique**, quelle que soit la bibliothèque d'origine : une fonction `predict` qui prend un tableau pandas et renvoie des prédictions. Un service de prédiction écrit pour pyfunc sert indifféremment un modèle scikit-learn, PyTorch ou XGBoost. C'est l'idée d'interface commune des conteneurs OCI (chapitre 16), appliquée aux modèles.

**La signature.** Elle décrit les entrées et les sorties attendues : ici, une colonne `titre` de type texte, obligatoire. MLflow la vérifie à chaque prédiction faite par pyfunc.

**L'environnement.** `requirements.txt` et `python_env.yaml` notent les versions exactes de Python et des bibliothèques (`scikit-learn==1.9.1`, `numpy==2.5.3`, etc.). C'est exactement l'information qu'il avait fallu extraire d'un avertissement au TP 22.

:::note[Pourquoi `model.skops` et pas `model.pkl` ?]
Dans la version de MLflow utilisée ici (3.16), la saveur scikit-learn sérialise par défaut au format **skops** plutôt qu'avec `pickle`. Un fichier `pickle` peut exécuter du code arbitraire au chargement (chapitre 28). Le format skops, lui, n'instancie au chargement que des types jugés sûrs, et refuse les autres tant qu'on ne les a pas explicitement déclarés de confiance (champ `skops_trusted_types`). Ce n'est pas une garantie absolue, mais c'est une réduction nette de la surface d'attaque [^skops].
:::

[^skops]: Documentation de skops, « Secure persistence with skops ». [skops.readthedocs.io](https://skops.readthedocs.io/). Le projet est développé en lien avec l'équipe de scikit-learn.

### 5.2 La signature à l'épreuve

:::exemple[Exemple 31.7 : une colonne mal nommée]
Un développeur de l'API appelle le modèle avec une colonne `title` au lieu de `titre` :

```python
modele = mlflow.pyfunc.load_model("models:/listify-categorie@champion")
modele.predict(pd.DataFrame({"title": ["acheter du pain"]}))
```

```text
MlflowException: Failed to enforce schema of data '             title
0  acheter du pain' with schema '['titre': string (required)]'.
Error: Model is missing inputs ['titre']. Note that there were extra inputs: ['title'].
```

L'erreur est immédiate et explicite. Sans signature, selon le modèle, on aurait obtenu une erreur obscure au fond de scikit-learn, ou, pire, une prédiction absurde. La signature transforme un désaccord entre deux équipes en **contrat** vérifié, comme le schéma d'une API (chapitre 33).
:::

### 5.3 Un piège vécu : le pipeline qui lit les noms de colonnes

La signature ne protège pas de tout. En préparant ce chapitre, le pipeline du TP 23 (`TfidfVectorizer` suivi d'une régression logistique) a été journalisé tel quel. Chargé par pyfunc et appelé sur deux titres, il a renvoyé **une seule** prédiction :

```python
modele.predict(pd.DataFrame({"titre": ["  Acheter du PAIN ", "voir Kévin"]}))
# array(['maison'], dtype=object)       une prédiction pour deux titres !
```

L'explication tient à un détail de Python. Pyfunc transmet au pipeline un tableau pandas. Or `TfidfVectorizer` attend une liste de textes, et parcourt son entrée élément par élément. Parcourir un tableau pandas avec une boucle `for` donne... les **noms de ses colonnes**. Le modèle a donc vectorisé le mot `titre`, et prédit sa catégorie. Aucune erreur, aucun avertissement : une panne silencieuse, typique du chapitre 27.

Le remède consiste à faire accepter au pipeline **le même type d'entrée** que ce que pyfunc lui donnera, grâce à un `ColumnTransformer` qui extrait explicitement la colonne :

```python
from sklearn.compose import ColumnTransformer

modele = Pipeline([
    ("tfidf", ColumnTransformer([
        ("titre", TfidfVectorizer(min_df=3, ngram_range=(1, 2)), "titre"),
    ])),
    ("clf", LogisticRegression(C=5, max_iter=500)),
]).fit(train[["titre"]], train.categorie)          # un tableau à une colonne, pas une série
```

Après correction, le même appel renvoie `['courses' 'travail']`. La leçon est générale : **testez le modèle tel qu'il sera appelé en production**, c'est-à-dire rechargé par le même chemin que le service (ici pyfunc), sur plusieurs lignes. Le TP 24 en fait un test automatique.

## 6. Le registre de modèles

### 6.1 Du run au modèle enregistré

Un run produit un modèle ; une campagne en produit des dizaines. Le service de prédiction, lui, a besoin d'une réponse simple à une question simple : **quel modèle dois-je servir ?** C'est le rôle du **registre de modèles**.

:::definition[Registre de modèles]
Catalogue centralisé des modèles destinés à la production. Chaque **modèle enregistré** porte un nom stable (`listify-categorie`) et possède des **versions** numérotées, chacune reliée au modèle journalisé et au run qui l'ont produite. Des **alias** mobiles (`champion`, `challenger`) désignent les versions ayant un rôle, et le service charge un alias plutôt qu'un numéro [^registry].
:::

<Figure src="mlflow-registre" num="31.3" alt="Le modèle enregistré listify-categorie a trois versions, chacune reliée à son run par le lignage. Version 1 : C = 5, min_df = 3, précision de test 87,50 %, désignée par l'alias @champion. Version 2 : C = 20, min_df = 2, précision de test 87,58 %, portant l'étiquette decision = refuse. Version 3 : données v3, en évaluation, désignée par l'alias @challenger.">
  Versions, alias et étiquettes. Les numéros de version sont immuables ; les alias se déplacent. Promouvoir un modèle, c'est déplacer l'alias `champion` ; revenir en arrière, c'est le remettre où il était. La version 2 n'a pas été promue (exemple 31.8), et l'étiquette en garde la raison.
</Figure>

L'enregistrement se fait au moment de la journalisation, ou plus tard, à partir d'un run existant :

```python
from mlflow.models import infer_signature

exemple = pd.DataFrame({"titre": ["acheter du pain", "payer le loyer"]})
info = mlflow.sklearn.log_model(
    modele, name="modele",
    signature=infer_signature(exemple, modele.predict(exemple)),
    input_example=exemple,
    registered_model_name="listify-categorie",
)
# Successfully registered model 'listify-categorie'.
# Created version '1' of model 'listify-categorie'.
```

Un second appel avec le même nom crée la version 2, et ainsi de suite. Les numéros ne sont jamais réutilisés : la version 1 désignera toujours le même modèle, comme une étiquette Git.

[^registry]: Documentation de MLflow, « MLflow Model Registry ». Les « stages » (`Staging`, `Production`, `Archived`) des versions antérieures de MLflow sont dépréciés depuis MLflow 2.9 au profit des alias, plus souples : un nombre quelconque d'alias, aux noms libres, chacun pointant vers une seule version.

### 6.2 Les alias : promouvoir et revenir en arrière

Le service de prédiction ne charge jamais « la version 2 ». Il charge `models:/listify-categorie@champion`, une adresse qui ne change pas quand le modèle change :

```python
from mlflow import MlflowClient

client = MlflowClient()
client.set_registered_model_alias("listify-categorie", "champion", 1)
client.set_registered_model_alias("listify-categorie", "challenger", 2)

modele = mlflow.pyfunc.load_model("models:/listify-categorie@champion")
```

Promouvoir le challenger, c'est déplacer un pointeur :

```python
client.set_registered_model_alias("listify-categorie", "champion", 2)
client.delete_registered_model_alias("listify-categorie", "challenger")
```

Et revenir en arrière après un incident, c'est le remettre sur la version 1. L'opération est instantanée et ne reconstruit rien : le service n'a qu'à recharger son modèle (au démarrage, ou périodiquement, chapitre 33). On retrouve le principe de la version déclarée et du retour arrière par un changement de référence, que GitOps appliquait aux images au chapitre 25.

### 6.3 Décider d'une promotion

Le registre permet de promouvoir ; il ne dit pas **quand**. La règle de promotion du chapitre 29 s'applique : un challenger remplace le champion s'il est **significativement** meilleur sur les mêmes données récentes, sans régression par catégorie, et s'il respecte les contraintes d'exploitation.

:::exemple[Exemple 31.8 : faut-il promouvoir la version 2 ?]
Les versions 1 (`C = 5, min_df = 3`) et 2 (`C = 20, min_df = 2`) sont évaluées sur les mêmes 4 800 tâches de test :

- version 1 : 4 200 bonnes réponses (87,50 %) ;
- version 2 : 4 204 bonnes réponses (87,58 %).

Sur les tâches où elles ne sont pas d'accord, la version 2 seule a raison $b = 34$ fois, la version 1 seule $c = 30$ fois. Le test de McNemar avec correction de continuité (chapitre 29, §6) donne :

$$
\chi^2 = \frac{(|b - c| - 1)^2}{b + c} = \frac{(4 - 1)^2}{64} \approx 0{,}14,
$$

très loin du seuil de 3,84 (niveau 5 %) ; la valeur p vaut environ 0,71. **Aucune différence démontrée.** Promouvoir la version 2 reviendrait à changer de modèle pour du bruit, avec les risques de tout changement (comportement différent sur des cas rares, surprise des utilisateurs). La décision rationnelle : garder le champion, et enregistrer au registre, en étiquette de la version 2, la raison du refus (`decision = refuse`, `raison = mcnemar p=0.71`). La prochaine fois qu'on se posera la question, la réponse sera écrite.
:::

### 6.4 Le lignage : de la production jusqu'aux données

Chaque version du registre est reliée à son modèle journalisé, lui-même relié à son run, qui porte ses paramètres, ses métriques et ses étiquettes. Si le run a été lancé depuis le dépôt `listify-ml`, il porte aussi le commit Git (`mlflow.source.git.commit`), et donc, par `dvc.lock`, les empreintes exactes des données.

:::exemple[Exemple 31.9 : remonter d'un incident au jeu de données]
Le service signale un comportement étrange. On part de ce qu'il sert :

```python
version = client.get_model_version_by_alias("listify-categorie", "champion")
run = client.get_run(version.run_id)
print(version.version, run.data.params, run.data.tags["mlflow.source.git.commit"])
```

En trois appels, on obtient le numéro de version, les hyperparamètres et le commit. Ensuite, les commandes du TP 23 : `git checkout <commit>`, `dvc pull`, et l'on dispose des données, du code et du modèle exacts du champion. Au TP 22, la même question avait demandé une demi-journée d'enquête, et n'avait abouti que parce que Claire avait laissé des sorties dans son notebook.
:::

## 7. DVC et MLflow : deux outils, deux questions

On oppose parfois DVC et MLflow. Ils répondent en réalité à des questions différentes, et se combinent naturellement.

| Question | DVC | MLflow |
|---|---|---|
| Comment refaire exactement ce modèle ? | Oui : données, pipeline, empreintes | Partiellement : paramètres et commit, pas les données |
| Qu'ai-je essayé, et qu'est-ce qui a marché ? | Seulement ce qui est commité | Oui : chaque run, automatiquement |
| Où sont les données ? | Stockage adressé par le contenu | Hors de son périmètre |
| Quel modèle la production doit-elle servir ? | Non | Oui : registre et alias |
| Comment le charger, quelle entrée attend-il ? | Non | Oui : format MLmodel, signature, pyfunc |
| Interface pour comparer | En ligne de commande (`metrics diff`) | Interface web, recherche, graphiques |

La combinaison du bloc 2 : DVC versionne les données et décrit le pipeline ; chaque exécution de l'étape `train` ouvre un run MLflow qui enregistre paramètres, métriques et commit ; le modèle candidat est journalisé et enregistré ; la promotion déplace un alias. C'est ce que construit le TP 24.

## 8. Limites et précautions

- **La sécurité par défaut est faible.** Un serveur MLflow lancé sans option n'authentifie personne : quiconque peut l'atteindre peut lire les données, supprimer des runs, ou déplacer l'alias `champion` vers un modèle de son choix, qui sera servi en production. MLflow propose une authentification de base en option ; en entreprise, on place le serveur derrière un mandataire d'authentification et l'on restreint les droits d'écriture sur le registre. Déplacer l'alias `champion`, c'est déployer : cela mérite les mêmes contrôles qu'un déploiement.
- **Les artefacts peuvent contenir des données personnelles.** Un exemple d'entrée, une matrice de confusion commentée, un échantillon d'erreurs : autant de fichiers qui peuvent contenir des titres de tâches réels. Le droit à l'effacement du RGPD (chapitre 28, §9) s'applique aussi au stockage d'artefacts.
- **Tout n'est pas tracé automatiquement.** MLflow enregistre ce qu'on lui donne. La version des données n'est tracée que si on l'enregistre (commit Git, empreinte DVC en étiquette). Un run lancé depuis un dossier qui n'est pas un dépôt Git, ou avec des modifications non commitées, perd son lignage.
- **La journalisation automatique est tentante et bavarde.** `mlflow.sklearn.autolog()` enregistre sans une ligne de code les paramètres, des métriques d'entraînement et le modèle, à chaque `fit`. Pratique pour explorer, mais elle journalise aussi les modèles qu'on ne voulait pas garder (exemple 31.5) et les métriques calculées sur l'entraînement, qu'il ne faut pas confondre avec la validation.

## Ce qu'il faut retenir

<div className="retenir">

1. DVC répond à « comment refaire **ce** modèle ? », le suivi d'expériences à « parmi **tout ce que j'ai essayé**, qu'est-ce qui a marché ? ». Il faut les deux.
2. Une **expérience** regroupe des **runs** ; un run enregistre des **paramètres** (causes, fixées avant), des **métriques** (effets, mesurés), des **étiquettes** (annotations) et des **artefacts** (fichiers, dont le modèle).
3. Une précision mesurée a un **bruit** d'écart-type $\sqrt{p(1-p)/n}$ ; le meilleur de $k$ essais est **optimiste** (environ $1{,}63\,\sigma$ pour $k = 12$). Choisir sur la validation, mesurer une fois sur le test, enregistrer tous les essais.
4. Un serveur MLflow sépare la **base de métadonnées** (PostgreSQL) et le **stockage d'artefacts** (S3, MinIO). Les clients le trouvent par `MLFLOW_TRACKING_URI`.
5. Le **format MLflow** est un dossier : `MLmodel`, le modèle sérialisé (skops par défaut dans les versions récentes), l'environnement exact, un exemple d'entrée. La saveur **pyfunc** donne une interface unique ; la **signature** est un contrat vérifié.
6. Testez le modèle **tel qu'il sera appelé** : un pipeline qui reçoit un tableau pandas au lieu d'une liste de textes peut prédire le nom de la colonne, sans erreur.
7. Le **registre** donne un nom stable et des versions immuables ; les **alias** (`champion`, `challenger`) se déplacent. Promouvoir ou revenir en arrière, c'est déplacer un alias.
8. Une promotion se **décide** : McNemar sur les mêmes données, non-régression par catégorie. Sur Listify, 4 204 contre 4 200 bonnes réponses ne justifient pas de changer de modèle.
9. Déplacer l'alias `champion`, c'est déployer : le registre mérite authentification et contrôle des droits.

</div>

## Regard recherche

:::recherche
La gestion des expériences et des modèles a donné lieu à des systèmes de recherche avant de devenir un marché d'outils :

- **Manasi Vartak et al., « ModelDB: a system for machine learning model management », *HILDA*, 2016.** L'un des premiers systèmes académiques de gestion de modèles : enregistrement automatique des exécutions et requêtes sur l'historique des modèles.
- **Matei Zaharia et al., « Accelerating the Machine Learning Lifecycle with MLflow », *IEEE Data Engineering Bulletin*, 2018.** La présentation de MLflow par ses auteurs : le suivi, le format de modèle et les projets, conçus pour être indépendants de toute bibliothèque d'apprentissage.
- **Sebastian Schelter et al., « Automatically Tracking Metadata and Provenance of Machine Learning Experiments », *Workshop on ML Systems at NIPS*, 2017.** Un système qui extrait automatiquement métadonnées et provenance des expériences, pour les interroger ensuite ; il montre tout ce qu'un enregistrement manuel laisse échapper.
- **Mohammad Hossein Namaki et al., « Vamsa: Automated Provenance Tracking in Data Science Scripts », *KDD*, 2020.** Retrouver automatiquement, par analyse statique des scripts, quelles colonnes des données ont servi à entraîner un modèle.
- **Gavin C. Cawley, Nicola L. C. Talbot, « On Over-fitting in Model Selection and Subsequent Selection Bias in Performance Evaluation », *JMLR*, 2010.** Le biais de sélection du §3.2, étudié en profondeur : il peut égaler les écarts entre méthodes qu'on prétend mesurer.

Piste d'innovation : un outil de suivi voit **tous** les essais d'une équipe. Il pourrait corriger automatiquement le biais de sélection des scores qu'il affiche, en tenant compte du nombre de configurations essayées, et avertir quand un écart annoncé est inférieur au bruit de mesure. Aucun outil répandu ne le fait aujourd'hui.
:::

## Bibliographie du chapitre

<div className="biblio">

### Sources primaires

- Documentation de MLflow : « MLflow Tracking », « MLflow Models », « MLflow Model Registry ». [mlflow.org/docs/latest](https://mlflow.org/docs/latest/)
- Matei Zaharia et al., « Accelerating the Machine Learning Lifecycle with MLflow », *IEEE Data Engineering Bulletin*, 2018.

### Lectures recommandées

- Chip Huyen, *Designing Machine Learning Systems*, O'Reilly, 2022, chapitre 6 (« Model Development and Offline Evaluation »), sections sur le suivi et le versionnement des expériences.
- Mark Treveil et al., *Introducing MLOps*, O'Reilly, 2020, chapitre 7 (gouvernance des modèles, registre).

### Pour aller plus loin

- Les articles de la rubrique « Regard recherche ».
- Sebastian Raschka, « Model Evaluation, Model Selection, and Algorithm Selection in Machine Learning », prépublication arXiv:1811.12808, 2018 : une synthèse claire des protocoles de validation et des tests de comparaison.

</div>
