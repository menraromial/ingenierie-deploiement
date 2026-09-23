---
title: "Ch. 32 : Orchestrer des tâches, le DAG et Airflow"
sidebar_label: "Ch. 32 : Le DAG et Airflow"
hide_title: true
---

import ChapterHead from '@site/src/components/ChapterHead';
import Figure from '@site/src/components/Figure';

<ChapterHead
  kicker="Semestre 3 · Bloc 2 · Chapitre 32"
  title="Orchestrer des tâches : le DAG et Airflow"
  lecture="55 min"
  competences={['C2', 'C5']}
/>

:::objectifs
À l'issue de ce chapitre, vous saurez :

- expliquer pourquoi une suite de tâches planifiées par `cron` finit par échouer, et ce qu'un orchestrateur apporte de plus ;
- décrire un traitement comme un **DAG** de tâches **idempotentes** et **atomiques**, et justifier ce découpage ;
- nommer les composants d'Airflow et dire lequel fait quoi quand une tâche s'exécute ;
- écrire un DAG avec le Task SDK, passer des valeurs entre tâches, brancher selon un résultat, gérer les réessais ;
- raisonner sur le temps dans Airflow : date logique, calendrier à déclenchement ou à intervalles, rattrapage, fuseaux horaires ;
- choisir un exécuteur et dimensionner le parallélisme ; distinguer un orchestrateur de **tâches** d'un orchestrateur de **services** comme Kubernetes.
:::

## 1. Ce que `cron` ne sait pas faire

Le TP 23 a laissé Listify avec un entraînement reproductible que l'on lance à la main : `dvc repro`. Pour le réentraîner chaque nuit, la tentation est d'écrire une ligne de `cron`. Elle marchera quelques semaines, puis posera les problèmes que rencontre toute équipe qui enchaîne des traitements.

:::exemple[Exemple 32.1 : la chaîne de cinq lignes de cron]
Une équipe planifie cinq scripts qui dépendent les uns des autres, en estimant leur durée puis en espaçant les horaires :

| Script | Heure | Durée estimée | Durée réelle après six mois |
|---|---|---|---|
| Export des tâches | 3 h 00 | 5 min | 18 min |
| Validation | 3 h 20 | 2 min | 4 min |
| Entraînement | 3 h 40 | 15 min | 35 min |
| Évaluation | 4 h 10 | 3 min | 6 min |
| Publication des métriques | 4 h 20 | 1 min | 1 min |

Le volume de données a grandi ; l'export dure maintenant 18 minutes et se termine à 3 h 18, deux minutes avant la validation. Le jour où il dure 21 minutes, la validation lit un fichier **incomplet** et l'entraînement apprend sur des données tronquées, sans que rien n'échoue.

**Ce qui manque, et qu'aucun réglage d'horaires ne donnera :**

- **les dépendances** : la validation doit attendre la **fin** de l'export, pas une heure fixe ;
- **la reprise** : si l'entraînement échoue, les deux étapes suivantes s'exécutent quand même, sur le modèle de la veille ;
- **les réessais** : une coupure réseau d'une minute fait perdre la nuit entière ;
- **la visibilité** : pour savoir ce qui s'est passé, il faut lire cinq fichiers de journal sur la machine ;
- **le rattrapage** : après trois jours d'arrêt, il faut rejouer les trois jours manquants, dans l'ordre, à la main.

Chacun de ces manques peut se coder. Les coder tous, c'est réécrire un orchestrateur.
:::

:::definition[Orchestrateur de tâches]
Système qui exécute des **traitements finis** (*batch*) en respectant leurs dépendances, à des moments déterminés par un calendrier ou par des événements, en conservant l'état de chaque exécution, en réessayant les échecs et en permettant de rejouer le passé.
:::

Notez bien « traitements **finis** ». Kubernetes, au semestre 2, orchestrait des **services** : des processus que l'on veut voir tourner en permanence, et qu'il redémarre s'ils s'arrêtent. Un orchestrateur de tâches gère l'inverse : des processus que l'on veut voir **se terminer**, dans un certain ordre (§7).

## 2. Le DAG et ses tâches

### 2.1 Un graphe orienté acyclique

On décrit un traitement comme un **graphe orienté sans cycle** (*directed acyclic graph*, DAG) : les nœuds sont les **tâches**, les arcs les **dépendances**. Le graphe dit ce qui doit précéder quoi, et donc aussi ce qui peut s'exécuter **en parallèle**. L'absence de cycle garantit qu'un ordre d'exécution existe.

<Figure src="dag-entrainement" num="32.1" alt="Le DAG d'entraînement de Listify : extraire (export du jour) précède valider (schéma, catégories), qui précède entraîner (run MLflow), qui précède décider (branchement). Depuis décider, deux chemins : si la précision dépasse le seuil, promouvoir (alias champion) ; sinon, alerter (le candidat est refusé). Chaque tâche est un processus distinct, qui peut échouer, être relancé, s'exécuter sur une autre machine.">
  Le DAG d'entraînement de Listify, que le TP 26 construira. La dernière étape du chapitre 29, la promotion conditionnelle, devient un **branchement** dans le graphe.
</Figure>

Cette représentation n'a rien de propre au ML. Les systèmes de flux de travaux scientifiques l'utilisent depuis les années 2000 pour enchaîner des calculs sur des grilles de machines, comme Pegasus ou Kepler [^pegasus]. Ce qu'Airflow y a ajouté, à partir de 2014, c'est la description du graphe **en Python** plutôt que dans un format déclaratif, et une place centrale donnée au temps et au rattrapage [^airflowdoc].

### 2.2 Deux propriétés non négociables

Un orchestrateur réessaie les tâches et rejoue le passé. Ces deux comportements n'ont de sens que si les tâches respectent deux propriétés.

**L'idempotence** : exécuter la tâche deux fois sur la même entrée doit donner le même résultat qu'une seule fois.

:::exemple[Exemple 32.2 : la tâche qui n'est pas idempotente]
L'étape de publication insère les métriques du jour dans une table :

```sql
INSERT INTO metriques (jour, precision) VALUES ('2026-09-17', 0.8758);
```

La tâche réussit, mais la connexion se coupe avant qu'elle ne signale sa réussite. L'orchestrateur, qui la croit échouée, la réessaie : la ligne est insérée **deux fois**. Le tableau de bord affiche alors une moyenne fausse, et un rattrapage de trois jours triple les lignes.

La version idempotente écrase au lieu d'ajouter :

```sql
INSERT INTO metriques (jour, precision) VALUES ('2026-09-17', 0.8758)
ON CONFLICT (jour) DO UPDATE SET precision = EXCLUDED.precision;
```

La règle générale, popularisée par Maxime Beauchemin, le créateur d'Airflow, sous le nom d'**ingénierie de données fonctionnelle** : une tâche écrit une **partition** identifiée par sa date, et la réécrit entièrement si on la rejoue [^beauchemin]. Ni `INSERT` aveugle, ni mise à jour partielle, ni « ajouter les nouvelles lignes depuis la dernière fois ».
:::

**L'atomicité** : une tâche fait **une** chose. Si « entraîner et publier le modèle » est une seule tâche qui échoue à la publication, la réessayer refait l'entraînement, et l'on ne sait pas si le modèle existe déjà. Deux tâches séparées permettent de ne reprendre que ce qui a échoué, et rendent le graphe lisible.

Une conséquence pratique : une tâche ne **transmet** jamais de gros volumes de données à la suivante. Elle écrit un fichier ou une partition, et transmet **son chemin**. Les données passent par le stockage, pas par l'orchestrateur (§4.3).

[^pegasus]: Ewa Deelman et al., « Pegasus: A framework for mapping complex scientific workflows onto distributed systems », *Scientific Programming*, vol. 13, n° 3, 2005. Voir aussi Bertram Ludäscher et al., « Scientific workflow management and the Kepler system », *Concurrency and Computation*, 2006.

[^airflowdoc]: Documentation d'Apache Airflow. [airflow.apache.org/docs](https://airflow.apache.org/docs/). Airflow est né chez Airbnb en 2014, est entré à la fondation Apache en 2016 (projet de premier plan en 2019), et a publié sa version 3 en 2025. Les exemples de ce chapitre ont été exécutés avec Airflow 3.3.2.

[^beauchemin]: Maxime Beauchemin, « Functional Data Engineering: a modern paradigm for batch data processing », 2018. Voir aussi « The Rise of the Data Engineer », 2017.

## 3. Les composants d'Airflow

<Figure src="airflow-composants" num="32.2" alt="Le dossier de DAGs, des fichiers Python versionnés, est lu par l'ordonnanceur, qui décide quoi lancer et quand, et écrit dans la base de métadonnées (runs, états, XCom). L'ordonnanceur transmet les tâches à exécuter au serveur d'API (interface web et API d'exécution), qui s'appuie sur l'exécuteur (Local, Celery ou Kubernetes) pour les confier à des workers. Les workers renvoient leur état et leurs XCom au serveur d'API par l'API d'exécution, et le serveur écrit dans la base de métadonnées.">
  Les composants d'Airflow 3. Les tâches ne touchent plus directement la base de métadonnées : elles passent par l'**API d'exécution** du serveur d'API, ce qui permet de les exécuter ailleurs, dans un autre langage ou un autre réseau.
</Figure>

- Le **dossier de DAGs** contient des fichiers Python. Airflow les relit périodiquement : déployer un DAG, c'est déposer un fichier (et donc, en pratique, faire un `git push` dans un dépôt que l'orchestrateur synchronise, comme au chapitre 25).
- L'**ordonnanceur** (*scheduler*) décide quoi lancer : il regarde les calendriers, les dépendances et l'état des exécutions précédentes, puis met les tâches prêtes en file.
- La **base de métadonnées** conserve les DAG connus, les exécutions, l'état de chaque tâche, les journaux d'exécution et les valeurs échangées entre tâches. C'est la mémoire du système ; une base PostgreSQL en production.
- Le **serveur d'API** sert l'interface web **et** l'API d'exécution que les tâches utilisent pour signaler leur état.
- L'**exécuteur** et les **workers** exécutent réellement les tâches (§6).

:::warning[Un composant oublié, et rien ne s'exécute]
En préparant ce chapitre, le DAG d'exemple a d'abord été lancé avec le seul ordonnanceur. Les exécutions restaient indéfiniment à l'état `running`, sans message d'erreur explicite : les tâches ne pouvaient pas signaler leur état, faute de serveur d'API. Une fois `airflow api-server` démarré à côté de l'ordonnanceur, les quatre exécutions en attente sont passées à `success` en moins d'une minute. Retenez la règle : dans Airflow 3, **ordonnanceur et serveur d'API vont toujours ensemble**.
:::

## 4. Écrire un DAG

### 4.1 Le Task SDK

Airflow 3 décrit un DAG avec des décorateurs : une fonction Python décorée par `@task` devient une tâche, et l'appel d'une fonction dans une autre crée la dépendance. Voici le DAG de la figure 32.1, dans sa version d'illustration (le TP 26 en écrira la version réelle) :

```python title="dags/entrainement_listify.py"
import pendulum
from airflow.sdk import dag, task

SEUIL = 0.85


@dag(
    dag_id="entrainement_listify",
    schedule="0 3 * * *",                                   # chaque nuit à 3 h
    start_date=pendulum.datetime(2026, 1, 1, tz="Europe/Paris"),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": pendulum.duration(minutes=5)},
    tags=["listify", "ml"],
)
def entrainement_listify():
    @task
    def extraire(logical_date=None) -> dict:
        return {"lignes": 19200, "jusqu_au": str(logical_date)}

    @task
    def valider(export: dict) -> dict:
        if export["lignes"] < 1000:
            raise ValueError(f"export trop petit : {export['lignes']} lignes")
        return export

    @task
    def entrainer(export: dict) -> dict:
        return {"version": 7, "precision": 0.8758, "lignes": export["lignes"]}

    @task.branch
    def decider(candidat: dict) -> str:
        return "promouvoir" if candidat["precision"] >= SEUIL else "alerter"

    @task
    def promouvoir(candidat: dict) -> str:
        return f"version {candidat['version']} promue championne"

    @task
    def alerter(candidat: dict) -> str:
        return f"candidat refusé : {candidat['precision']:.4f} < {SEUIL}"

    export = valider(extraire())
    candidat = entrainer(export)
    decider(candidat) >> [promouvoir(candidat), alerter(candidat)]


entrainement_listify()
```

Quatre points à relever.

- **Le graphe se déduit du code.** `valider(extraire())` crée la dépendance ; l'opérateur `>>` l'exprime explicitement quand il n'y a pas de valeur à passer.
- **`@task.branch` choisit un chemin.** La fonction renvoie le nom de la tâche à exécuter ; les autres branches sont marquées **ignorées** (*skipped*), état distinct de « réussie » et de « échouée ».
- **Les réessais sont déclaratifs** : `retries` et `retry_delay` dans `default_args` s'appliquent à toutes les tâches.
- **Les paramètres temporels sont injectés** : en déclarant `logical_date`, la tâche reçoit l'instant que représente l'exécution, et définit ses données par rapport à lui (§5).

### 4.2 Exécuter et observer

Pour mettre au point un DAG, `airflow dags test` l'exécute **en une fois**, dans le processus courant :

```bash
airflow dags test entrainement_listify
```

Sur le DAG ci-dessus, l'exécution complète a pris **4,9 secondes** et s'est terminée ainsi :

```text
DagRun Finished: dag_id=entrainement_listify, run_id=manual__2026-09-22T18:04:56...,
run_duration=4.896217, state=success, run_type=manual
```

La branche `promouvoir` a été exécutée (précision 0,8758 au-dessus du seuil de 0,85) et `alerter` marquée ignorée. C'est la commande à utiliser en développement : elle ne demande ni ordonnanceur, ni serveur d'API.

### 4.3 XCom : ce qui circule entre les tâches

Les valeurs renvoyées par les tâches (ici, des dictionnaires) transitent par un mécanisme appelé **XCom** (*cross-communication*) : elles sont sérialisées et stockées dans la base de métadonnées, puis relues par la tâche suivante. C'est pratique, et strictement limité aux **petites** valeurs.

:::exemple[Exemple 32.3 : ce qu'il ne faut pas faire passer par XCom]
Comparons deux façons d'enchaîner `extraire` et `entrainer` sur l'export de Listify (19 200 lignes, environ 1 Mio en CSV, et jusqu'à plusieurs Go dans une vraie application).

**Par XCom.** La tâche `extraire` renvoie le tableau pandas complet. Chaque exécution écrit 1 Mio dans la base de métadonnées, puis le relit. Avec un rattrapage de 365 jours, cela fait 365 Mio de données stockées dans une base conçue pour des métadonnées, qui ralentit l'interface et les requêtes de l'ordonnanceur. Avec un export de 2 Go, la tâche échoue, ou fait tomber la base.

**Par le stockage.** La tâche `extraire` écrit `s3://listify/exports/2026-09-17.csv` et renvoie **ce chemin** : une centaine d'octets. La tâche suivante lit le fichier. La base ne contient que des métadonnées, et les deux tâches peuvent s'exécuter sur des machines différentes.

La règle : **XCom transporte des références, pas des données**. Un identifiant, un chemin, un nombre, une décision.
:::

## 5. Le temps : date logique, rattrapage, fuseaux

C'est la partie d'Airflow qui surprend le plus, et celle qui explique le plus d'erreurs de débutant.

### 5.1 Chaque exécution représente un instant : la date logique

Une exécution ne représente pas « le moment où elle tourne » : elle porte une **date logique** (*logical date*), l'instant qu'elle est censée représenter. L'exécution planifiée du lundi 3 h a pour date logique le lundi 3 h, qu'elle tourne à l'heure, avec vingt minutes de retard, ou trois mois plus tard lors d'un rattrapage.

Ce que l'on associe à cette date dépend du **calendrier** (*timetable*), et c'est là qu'Airflow 3 a changé :

| Calendrier | Date logique | Données associées | Comment l'obtenir |
|---|---|---|---|
| `CronTriggerTimetable` | L'instant du déclenchement | Aucun intervalle : début et fin sont confondus | **Défaut d'Airflow 3** pour un `schedule` écrit en `cron` |
| `CronDataIntervalTimetable` | Le **début** d'un intervalle | L'intervalle entre deux déclenchements ; l'exécution part à sa **fin** | Défaut d'Airflow 2 ; en Airflow 3, `schedule=CronDataIntervalTimetable("0 3 * * *", timezone="Europe/Paris")` ou l'option `[scheduler] create_cron_data_intervals = True` |

Le second modèle est celui de la plupart des tutoriels écrits pour Airflow 2 : chaque exécution traite exactement une tranche de données, de la fin de la précédente jusqu'à son propre déclenchement. Le premier est plus proche de `cron` : l'exécution représente un instant, et la tâche décide elle-même quelles données lui correspondent, **par rapport à cet instant** (« les tâches créées avant la date logique », « les 24 heures qui précèdent »).

<Figure src="intervalles-airflow" num="32.3" alt="Une ligne de temps graduée du 15 au 19 à 3 h. Les déclenchements du 15, du 16 et du 17 sont marqués « rattrapée » : ce sont les exécutions créées par airflow backfill create du 15 au 18. Le déclenchement du 18 est l'exécution planifiée. Chaque exécution a pour date logique l'instant de son déclenchement, et ne considère que les données antérieures à cet instant.">
  Dates logiques et rattrapage, avec le calendrier par défaut d'Airflow 3. Chaque exécution représente un instant ; ses données s'arrêtent à cet instant.
</Figure>

:::warning[Un piège vécu en préparant ce cours]
Avec un simple `schedule="0 3 * * *"`, une tâche qui lit `data_interval_start` et `data_interval_end` reçoit **deux fois la même valeur** dans Airflow 3. Lors de la préparation, `airflow dags test` a affiché `intervalle [2026-09-17 00:00:00+00:00, 2026-09-17 00:00:00+00:00]`. Une tâche recopiée d'un exemple Airflow 2, qui « traite les données de l'intervalle », ne traite alors **rien**, sans la moindre erreur. Soit on raisonne sur la date logique, soit on choisit explicitement `CronDataIntervalTimetable`.
:::

Dans les deux cas, la règle de fond est la même, et elle rend les tâches **reproductibles** : une tâche qui définit ses données à partir de la date logique, et n'utilise **jamais** l'heure courante, donne le même résultat qu'elle soit exécutée à l'heure ou trois mois plus tard. C'est l'équivalent, pour le temps, de l'interdiction d'entraîner sur une source vivante du chapitre 28.

:::danger[Ne jamais écrire `datetime.now()` dans une tâche]
Une tâche qui lit l'heure courante produit un résultat différent à chaque exécution, et un rattrapage recalcule alors tout sur les données d'aujourd'hui au lieu de celles du jour rejoué. Utilisez la date logique fournie par Airflow.
:::

### 5.2 Rattraper le passé

Deux mécanismes existent. `catchup=True` demande à Airflow, au démarrage, de créer **toutes** les exécutions manquantes depuis `start_date` : très utile pour un historique, dangereux quand on l'ignore (un `start_date` vieux de deux ans déclenche 730 exécutions d'un coup). Notre DAG utilise donc `catchup=False`, et le rattrapage se demande **explicitement** :

```bash
airflow backfill create --dag-id entrainement_listify \
  --from-date 2026-09-15 --to-date 2026-09-18
```

:::exemple[Exemple 32.4 : ce que le rattrapage a réellement créé]
La commande ci-dessus, exécutée sur le DAG de la §4.1, puis l'ordonnanceur et le serveur d'API démarrés, ont produit ces exécutions :

```text
run_id                                  | state   | logical_date
scheduled__2026-09-22T01:00:00+00:00    | success | 2026-09-22T01:00:00+00:00
backfill__2026-09-17T01:00:00+00:00     | success | 2026-09-17T01:00:00+00:00
backfill__2026-09-16T01:00:00+00:00     | success | 2026-09-16T01:00:00+00:00
backfill__2026-09-15T01:00:00+00:00     | success | 2026-09-15T01:00:00+00:00
```

Trois observations, chacune instructive :

1. **Trois exécutions, pas quatre.** La borne `--to-date 2026-09-18` s'entend le 18 à minuit ; le déclenchement du 18 à 3 h tombe après. Un essai à blanc sur un autre DAG, hebdomadaire, le confirme : `--from-date 2025-07-07 --to-date 2025-07-21 --dry-run` annonce les exécutions du 7 et du 14, pas celle du 21.
2. **`01:00:00+00:00`, alors que le DAG dit 3 h.** Le calendrier est interprété dans le fuseau du `start_date` (`Europe/Paris`), et Airflow stocke tout en temps universel : 3 h à Paris en été, c'est 1 h UTC. Le même DAG s'exécutera à 2 h UTC en hiver, et l'heure locale restera 3 h, y compris les nuits de changement d'heure.
3. **Le préfixe du `run_id` dit l'origine** : `scheduled__`, `backfill__` ou `manual__`. La ligne `scheduled__` est l'exécution normale, créée dès que le DAG a été réactivé.
:::

## 6. Exécuteurs, parallélisme et attente

### 6.1 Choisir un exécuteur

L'**exécuteur** décide **où** tourne une tâche.

| Exécuteur | Où s'exécutent les tâches | Pour qui |
|---|---|---|
| `LocalExecutor` | Processus sur la machine de l'ordonnanceur | Poste de développement, petite installation |
| `CeleryExecutor` | Workers permanents, alimentés par une file (Redis, RabbitMQ) | Beaucoup de tâches courtes, parc de machines stable |
| `KubernetesExecutor` | Un *pod* créé pour chaque tâche, détruit ensuite | Tâches hétérogènes, besoins ponctuels (GPU, mémoire), isolation |

:::exemple[Exemple 32.5 : pod par tâche, ou workers permanents ?]
Un DAG lance 2 000 tâches courtes par jour (2 secondes chacune) et 4 tâches lourdes (30 minutes, 16 Gio de mémoire).

**Tout en `KubernetesExecutor`.** Créer un pod coûte, en ordre de grandeur, 5 à 10 secondes (planification, téléchargement de l'image si elle n'est pas en cache, démarrage). Pour les tâches courtes :

$$
2\,000 \times 7 \text{ s} \approx 3 \text{ h } 53 \text{ de démarrage}, \text{ pour } 2\,000 \times 2 = 67 \text{ minutes de travail utile}.
$$

Plus des trois quarts du temps est consacré à démarrer des conteneurs.

**Tout en `CeleryExecutor`.** Les tâches courtes partent immédiatement sur des workers déjà chauds. Mais les 4 tâches lourdes imposent de dimensionner **tous** les workers à 16 Gio, alors qu'ils passent l'essentiel du temps à exécuter des tâches de 200 Mio.

**La solution usuelle** : `CeleryExecutor` pour le gros du trafic, et les tâches lourdes déportées dans des pods dédiés par un opérateur spécialisé (`KubernetesPodOperator`), qui demande exactement les ressources nécessaires. La tâche Airflow se contente alors de lancer le pod et d'attendre sa fin.
:::

### 6.2 Limiter le parallélisme

Trois réglages se superposent : le parallélisme global de l'installation, `max_active_tasks` par DAG, et les **pools**, qui rationnent une ressource partagée. Un pool `base_listify` de 5 places garantit qu'au plus cinq tâches, tous DAG confondus, interrogeront la base de production en même temps. C'est la même idée que la limitation du nombre de connexions simultanées au chapitre 30 : on dimensionne pour la ressource la plus fragile.

### 6.3 Attendre sans bloquer

Une tâche attend souvent quelque chose : un fichier déposé par une autre équipe, la fin d'un travail externe. Les **capteurs** (*sensors*) font cela. Dans leur mode naïf, ils occupent une place d'exécution pendant toute l'attente.

:::exemple[Exemple 32.6 : vingt capteurs suffisent à bloquer l'installation]
Vingt DAG attendent chacun le dépôt d'un fichier, en moyenne pendant 4 heures. L'installation dispose de 16 places d'exécution simultanées.

**Capteurs classiques** : chaque capteur occupe une place pendant 4 heures. Les 16 places sont prises par des tâches qui **ne font rien**, et les vrais traitements attendent. C'est un interblocage de fait.

**Capteurs différables** (`deferrable=True`) : la tâche enregistre sa condition auprès d'un processus spécialisé (le *triggerer*), qui surveille des milliers de conditions en parallèle de façon asynchrone, et **libère sa place**. Elle est reprise quand la condition devient vraie. Les 16 places restent disponibles pour du travail utile.

La règle : au-delà de quelques minutes d'attente, un capteur doit être différable.
:::

### 6.4 Les réessais, et ce qu'ils ne résolvent pas

:::exemple[Exemple 32.7 : trois essais valent-ils mieux qu'un ?]
Une tâche échoue 2 % du temps à cause d'une coupure réseau transitoire, indépendante d'un essai à l'autre. Avec `retries=2`, elle a trois chances :

$$
P(\text{échec après 3 essais}) = 0{,}02^{3} = 8 \times 10^{-6},
$$

soit un échec tous les 342 ans pour une tâche quotidienne. Le réessai transforme une panne hebdomadaire en non-événement.

**Mais attention au faux confort.** Si la cause n'est pas transitoire (un identifiant expiré, un schéma de données changé), les trois essais échouent tous, et le seul effet des réessais est de **retarder** l'alerte de deux fois `retry_delay`. Et si la tâche n'est pas idempotente (exemple 32.2), chaque réessai aggrave la situation. Les réessais traitent les pannes transitoires, rien d'autre.
:::

## 7. Orchestrer des tâches ou des services

Le semestre 2 a installé Kubernetes, que l'on appelle aussi un « orchestrateur ». Les deux mots recouvrent des objets différents, et la confusion est fréquente en entretien comme en conception.

| | Orchestrateur de **services** (Kubernetes) | Orchestrateur de **tâches** (Airflow) |
|---|---|---|
| Objet géré | Processus qui doivent tourner **en permanence** | Traitements qui doivent **se terminer** |
| Objectif | Maintenir un état désiré (3 répliques en marche) | Faire avancer un graphe d'exécutions jusqu'au bout |
| Réaction à l'arrêt d'un processus | Le redémarrer, toujours | Marquer la tâche réussie ou échouée, puis continuer le graphe |
| Notion de temps | Peu présente | Centrale (intervalles, rattrapage) |
| Dépendances | Réseau et découverte de services | Ordre d'exécution |
| Question posée | « Le service est-il en bonne santé ? » | « L'exécution du 17 est-elle terminée, et juste ? » |

Ils se complètent : Airflow tourne **sur** Kubernetes (ses composants sont des services), et lance des tâches **dans** Kubernetes (un pod par tâche). Kubernetes sait exécuter des travaux finis avec ses objets `Job` et `CronJob`, mais il ne connaît ni dépendances entre travaux, ni intervalles de données, ni rattrapage, ni interface de reprise : au-delà de deux ou trois travaux enchaînés, on veut un orchestrateur de tâches. Le chapitre 34 présentera Kubeflow Pipelines et Argo Workflows, qui décrivent des DAG **en objets Kubernetes**, et comparera cette approche à celle d'Airflow.

## 8. Orchestrer un entraînement

Le DAG de la figure 32.1 assemble les outils des chapitres précédents, chacun à sa place :

| Tâche | Ce qu'elle fait | Outil |
|---|---|---|
| `extraire` | Exporte les tâches créées avant la date logique, dépose un fichier, le versionne | SQL, DVC (ch. 28) |
| `valider` | Vérifie schéma, catégories, volume ; échoue bruyamment | Le script `prepare.py` du TP 23 |
| `entrainer` | Entraîne, journalise paramètres et métriques, enregistre le modèle | MLflow (ch. 31) |
| `decider` | Compare le candidat au champion sur les mêmes données | McNemar (ch. 29) |
| `promouvoir` | Déplace l'alias `champion` | Registre MLflow (ch. 31) |
| `alerter` | Prévient l'équipe et laisse le champion en place | Alertmanager (ch. 26) |

Deux principes de conception, qui valent pour tout DAG de ML :

- **L'orchestrateur orchestre, il ne calcule pas.** Un entraînement qui demande 16 Gio et un GPU ne s'exécute pas dans le worker Airflow : la tâche lance un pod dédié (ou un travail sur un cluster de calcul) et attend sa fin. Le worker ne fait que piloter.
- **Le déclencheur du chapitre 29 devient une tâche.** Le calendrier est le déclencheur le plus simple, mais Airflow 3 sait aussi déclencher un DAG sur la mise à jour d'un **actif** (*asset*) produit par un autre DAG : la chaîne « données prêtes, alors réentraîner » se décrit sans capteur ni horaire deviné.

## 9. Pièges classiques

- **Du code lourd au niveau du fichier.** Le fichier du DAG est réévalué à chaque relecture, toutes les quelques dizaines de secondes. Une requête à une base ou un chargement de données écrit **en dehors** d'une fonction de tâche s'exécute à chaque relecture, et ralentit tout l'ordonnanceur. Tout le travail va dans les tâches.
- **Un exemple d'Airflow 2 recopié tel quel.** Il lit `data_interval_start` et `data_interval_end`, qui sont égaux avec le calendrier par défaut d'Airflow 3 : la tâche ne traite rien, sans erreur (§5.1).
- **`catchup=True` oublié.** Un `start_date` ancien et un rattrapage automatique déclenchent des centaines d'exécutions au premier démarrage. Mettre `catchup=False` et rattraper explicitement.
- **Un `start_date` dynamique.** `start_date=pendulum.now()` change à chaque relecture du fichier : le DAG ne se déclenche jamais, ou de façon erratique. La date de début est une constante.
- **Des secrets dans le code du DAG.** Les identifiants vont dans les connexions et variables d'Airflow, elles-mêmes reliées à un gestionnaire de secrets, jamais dans le fichier versionné (chapitre 9).
- **Une base de métadonnées qui grossit sans fin.** Chaque exécution laisse des lignes d'état et de journal. Sans purge régulière, la base devient le goulot d'étranglement de l'ordonnanceur.

## Ce qu'il faut retenir

<div className="retenir">

1. `cron` planifie des **horaires** ; un orchestrateur gère des **dépendances**, un **état**, des **réessais**, une **visibilité** et un **rattrapage**. Enchaîner des scripts par des horaires espacés finit toujours par lire des données incomplètes.
2. On décrit un traitement comme un **DAG** de tâches **idempotentes** (rejouable sans effet de bord) et **atomiques** (une tâche, une chose).
3. Les données passent par le **stockage**, pas par l'orchestrateur : **XCom transporte des références**, pas des tableaux.
4. Airflow 3 : ordonnanceur, base de métadonnées, serveur d'API (interface **et** API d'exécution), exécuteur et workers. Sans serveur d'API, les tâches restent bloquées.
5. Chaque exécution représente un instant, sa **date logique**. Dans Airflow 3, un calendrier `cron` n'a par défaut **pas d'intervalle** (`CronTriggerTimetable`) ; les intervalles d'Airflow 2 se demandent explicitement (`CronDataIntervalTimetable`). Une tâche ne lit jamais l'heure courante : elle définit ses données par rapport à la date logique.
6. Le calendrier s'interprète dans le fuseau du `start_date` et se stocke en UTC : « 3 h » reste 3 h locales, y compris au changement d'heure.
7. `catchup=False` par défaut, rattrapage explicite avec `airflow backfill create` ; le préfixe du `run_id` dit l'origine de chaque exécution.
8. L'**exécuteur** fixe le lieu d'exécution : Local, Celery (workers chauds, tâches courtes) ou Kubernetes (un pod par tâche, isolation, coût de démarrage). Les tâches lourdes se déportent dans des pods dédiés.
9. Les **capteurs** qui attendent longtemps doivent être **différables**, sinon ils monopolisent les places d'exécution.
10. Les **réessais** ne réparent que les pannes transitoires, et seulement si la tâche est idempotente.
11. Orchestrateur de **tâches** (Airflow) et orchestrateur de **services** (Kubernetes) sont complémentaires : le premier tourne sur le second, et lui confie ses calculs.

</div>

## Regard recherche

:::recherche
L'orchestration de flux de travaux est un domaine ancien, né dans le calcul scientifique bien avant les pipelines de données :

- **Ewa Deelman et al., « Pegasus: A framework for mapping complex scientific workflows onto distributed systems », *Scientific Programming*, 2005.** Un système qui transforme un flux de travaux abstrait en plan d'exécution sur des ressources distribuées, avec optimisation et reprise sur erreur.
- **Bertram Ludäscher et al., « Scientific workflow management and the Kepler system », *Concurrency and Computation*, 2006.** L'autre grande famille : des flux de travaux composés visuellement, avec une sémantique explicite de l'exécution.
- **Tyler Akidau et al., « The Dataflow Model », *VLDB*, 2015.** La distinction entre **temps de l'événement** et **temps de traitement**, et la gestion des données arrivées en retard. C'est la formalisation de ce que la date logique d'Airflow traite de façon pragmatique ; elle sera centrale au chapitre 37.
- **Ewa Deelman et al., « The future of scientific workflows », *International Journal of High Performance Computing Applications*, 2018.** Un état des lieux et des défis ouverts : hétérogénéité des ressources, reproductibilité, flux de travaux pilotés par les données.
- **D. Sculley et al., « Hidden Technical Debt in Machine Learning Systems », *NeurIPS*, 2015.** Les « jungles de pipelines » du chapitre 27 : la dette que l'orchestration discipline, sans la supprimer.

Piste d'innovation : un orchestrateur connaît la durée, le coût et le taux d'échec de chaque tâche passée. Il pourrait **planifier** en conséquence : décaler les traitements non urgents vers les heures où l'électricité est la moins carbonée, choisir la taille des ressources à partir de l'historique, prédire les dépassements avant qu'ils ne se produisent. L'ordonnancement sous contrainte énergétique est un sujet de recherche actif, et les orchestrateurs de production n'en tirent presque rien.
:::

## Bibliographie du chapitre

<div className="biblio">

### Sources primaires

- Documentation d'Apache Airflow (version 3) : « Core Concepts », « Authoring and Scheduling », « Executors ». [airflow.apache.org/docs](https://airflow.apache.org/docs/)
- Maxime Beauchemin, « Functional Data Engineering: a modern paradigm for batch data processing », 2018.

### Lectures recommandées

- Bas Harenslak, Julian de Ruiter, *Data Pipelines with Apache Airflow*, Manning, 2021 : le livre de référence sur Airflow, à lire en gardant à l'esprit les changements apportés par la version 3.
- Joe Reis, Matt Housley, *Fundamentals of Data Engineering*, O'Reilly, 2022, chapitre 8 (orchestration, idempotence, gestion des dépendances).

### Pour aller plus loin

- Les articles de la rubrique « Regard recherche ».
- Documentation d'Argo Workflows et de Kubeflow Pipelines, pour comparer avec l'approche « DAG décrit en objets Kubernetes » du chapitre 34.

</div>
