---
title: "Ch. 36 : Big data et calcul distribué"
sidebar_label: "Ch. 36 : Big data et calcul distribué"
hide_title: true
---

import ChapterHead from '@site/src/components/ChapterHead';
import Figure from '@site/src/components/Figure';

<ChapterHead
  kicker="Semestre 3 · Bloc 3 · Chapitre 36"
  title="Big data et calcul distribué : MapReduce, Spark et le prix du shuffle"
  lecture="60 min"
  competences={['C1', 'C5']}
/>

:::objectifs
À l'issue de ce chapitre, vous saurez dire quand des données cessent de tenir sur une machine, et quand elles y tiennent encore alors qu'on croit le contraire. Vous saurez expliquer le modèle MapReduce et ce que Spark y a changé, lire un plan d'exécution Spark, repérer un shuffle et estimer ce qu'il coûte, reconnaître une clé déséquilibrée, choisir un format de fichier en connaissance de cause, et situer les formats de table du *lakehouse* dans une chaîne de ML.
:::

## 1. Cent millions d'événements

Chaque action d'un utilisateur de Listify laisse une trace : l'ouverture d'une tâche, sa modification, sa complétion. Pour ce chapitre, on a fabriqué un journal de ces actions sur dix-huit mois, en reprenant les vrais titres et les vraies catégories de Listify : **100 millions de lignes**, un fichier CSV de 10,09 Go. C'est le genre de fichier qu'on veut exploiter pour le ML. Il permet d'y calculer des caractéristiques (combien de tâches un utilisateur complète par semaine, à quelle heure il travaille), d'y chercher des étiquettes (une catégorie corrigée par l'utilisateur est une étiquette gratuite, chapitre 35), ou d'appliquer un modèle par lots à tout l'historique (chapitre 30).

Le premier réflexe d'un data scientist est d'ouvrir le fichier avec pandas. On l'a fait, sur une machine de 22 cœurs et 15 Gio de mémoire, en plafonnant la mémoire du processus à 6 Gio pour ne pas faire tomber le reste du poste. Au bout de 64 secondes, le noyau a tué le processus : signal 9, code de sortie 137, celui que vous avez vu au TP 25 sur un pod `OOMKilled`. Il n'y a eu ni message d'erreur Python, ni résultat partiel.

:::exemple[Exemple 36.1 : combien pèse un DataFrame]
Avant de conclure qu'il faut un cluster, mesurons. On a chargé les premières lignes du journal avec pandas 2.3, dans un processus neuf à chaque fois :

| Lignes lues | Temps | Taille du DataFrame | Pic mémoire du processus |
|---|---|---|---|
| 1 million | 1,2 s | 0,32 Gio | 0,37 Gio |
| 5 millions | 6,4 s | 1,60 Gio | 1,44 Gio |
| 10 millions | 13,4 s | 3,20 Gio | 2,83 Gio |

La croissance est linéaire : 0,32 Gio par million de lignes. Pour 100 millions, il faudrait environ 32 Gio, plus de trois fois la taille du fichier sur disque (10,09 Go, soit 9,4 Gio). L'écart vient de la représentation : pandas range chaque chaîne de caractères dans un objet Python séparé, avec son en-tête, et `"consultation"` coûte bien plus que ses douze octets.

On peut aider pandas en lui donnant les bons types : entiers sur 32 bits, catégories pour les colonnes qui n'ont que quelques valeurs (`action`, `categorie`, `client`), vraies dates. Sur 10 millions de lignes, le DataFrame tombe de 3,20 à 0,98 Gio. Pour le fichier entier, cela ferait encore environ 10 Gio : toujours trop pour la machine, et la lecture est plus lente (20,7 s au lieu de 13,4 s pour 10 millions de lignes).
:::

Retenez l'ordre de grandeur : **une table chargée en mémoire par pandas pèse souvent deux à quatre fois son CSV**. Avant d'installer quoi que ce soit, faites ce calcul.

## 2. Les trois V, et la question qui compte

L'expression *big data* est souvent rattachée à une note de 2001 du cabinet META Group, dans laquelle Doug Laney décrivait trois dimensions de la gestion des données : le **volume**, la **vélocité** (la vitesse à laquelle elles arrivent) et la **variété** (des formats hétérogènes) [^laney]. D'autres V se sont ajoutés depuis, au gré des présentations commerciales : véracité, valeur, variabilité. La grille a le mérite de rappeler que la difficulté n'est pas toujours la taille. Un flux de quelques mégaoctets par seconde qu'il faut traiter en moins d'une seconde (chapitre 37) pose des problèmes qu'un fichier de plusieurs téraoctets traité une fois par nuit ne pose pas.

Pour un ingénieur, une question est plus utile que les trois V : **le travail tient-il sur une machine ?** Une machine s'achète aujourd'hui avec des centaines de gigaoctets de mémoire et des dizaines de téraoctets de disque. Jordan Tigani, qui a longtemps travaillé sur BigQuery chez Google, a défendu en 2023 que la plupart des entreprises n'ont pas de *big data* au sens où elles le croient : leurs données totales sont grandes, mais les requêtes qu'elles exécutent n'en touchent qu'une petite partie, généralement récente [^tigani]. On reviendra sur cette idée au §7, chiffres à l'appui.

:::exemple[Exemple 36.2 : le temps de lire]
Le premier coût d'un traitement sur de gros volumes, c'est souvent le temps de **lire** les données. Prenons des ordres de grandeur de débit séquentiel : environ 150 Mo/s pour un disque dur, 500 Mo/s pour un SSD SATA, 2 à 5 Go/s pour un SSD NVMe récent.

Lire 1 To sur un disque dur prend donc $10^{12} / (150 \times 10^6) \approx 6\,700$ s, près de deux heures. Sur un SSD NVMe à 3 Go/s, un peu plus de cinq minutes. Réparti sur 50 machines qui lisent chacune leur part en parallèle, sur disques durs, un peu plus de deux minutes.

C'est exactement le calcul qui a motivé MapReduce en 2004. Les disques de l'époque étaient lents, et il fallait traiter l'index du web entier. La seule façon de lire plus vite était de lire à plusieurs endroits à la fois. Sur du matériel actuel, le même téraoctet se lit en quelques minutes sur une seule machine. Le seuil à partir duquel la distribution devient indispensable s'est déplacé très haut.
:::

[^laney]: Doug Laney, « 3D Data Management: Controlling Data Volume, Velocity, and Variety », note de recherche, META Group, 2001.

[^tigani]: Jordan Tigani, « Big Data is Dead », blog de MotherDuck, 2023.

## 3. MapReduce, l'idée qui a tout lancé

En 2003 et 2004, deux articles de Google ont décrit l'infrastructure qui permettait à l'entreprise de traiter ses volumes. Le premier présentait le **Google File System**, un système de fichiers qui découpe les fichiers en gros blocs de 64 Mo, répliqués sur plusieurs machines ordinaires [^gfs]. Le second présentait **MapReduce**, un modèle de programmation pour traiter ces fichiers sur des milliers de machines [^mapreduce].

L'idée de MapReduce tient en deux fonctions écrites par le programmeur. La fonction **map** reçoit un enregistrement et émet des paires (clé, valeur). La fonction **reduce** reçoit une clé et toutes les valeurs associées à cette clé, et produit le résultat. Entre les deux, le système fait lui-même le travail difficile : il regroupe toutes les paires d'une même clé sur la même machine. C'est l'étape qu'on appelle le **shuffle** (« rebattre les cartes »). Par défaut, la clé est envoyée au reducer numéro $\text{hachage}(\text{clé}) \bmod R$, où $R$ est le nombre de reducers.

<Figure src="mapreduce-flux" num="36.1" alt="Trois morceaux de titres de tâches passent chacun par un map qui émet des paires (mot, 1), puis par un combineur qui les additionne localement. Le shuffle envoie chaque mot au reducer choisi par crc32 du mot modulo 2 ; chaque reducer additionne et produit le résultat, par exemple (le, 3) et (la, 3). Mesuré sur 5 millions de titres, 8 mappers et 4 reducers : sans combineur, 22 680 376 paires traversent le shuffle, et le reducer le plus chargé en reçoit 8,5 millions contre 3,6 millions au moins chargé ; avec combineur, 1 968 paires.">
  Compter les mots des titres avec MapReduce. Tout ce qui est à gauche du shuffle se fait sur place ; le shuffle est la seule étape où les machines échangent des données.
</Figure>

Ce modèle est pauvre, et c'est sa force. Parce que le programmeur n'écrit que des fonctions sans effet de bord, le système peut les exécuter où il veut, autant de fois qu'il veut. Si une machine tombe en panne, ses tâches sont simplement relancées ailleurs. Si une tâche traîne sur une machine lente (l'article parle de *stragglers*), le système en lance une copie de secours et garde le premier résultat arrivé. Et parce que les fichiers sont déjà répartis par GFS, le système place autant que possible chaque map sur une machine qui possède une copie de son bloc : on déplace le calcul vers les données, pas l'inverse.

:::exemple[Exemple 36.3 : ce que fait le combineur]
On a écrit MapReduce à la main, en Python, sur les titres des 5 premiers millions d'événements : 8 mappers, 4 reducers, un partitionnement par `crc32(mot) mod 4`. Le script compte les paires qui traversent le shuffle.

Sans rien d'autre, chaque mot de chaque titre devient une paire `(mot, 1)` : **22 680 376 paires** à transporter, pour seulement 246 mots distincts. L'article de Google propose une optimisation qui s'applique dès que l'opération du reduce est associative et commutative, comme une somme : une fonction **combineur**, exécutée sur la machine du mapper, qui additionne localement avant l'envoi. Chaque mapper n'envoie alors qu'une paire par mot distinct qu'il a vu, et il n'en passe plus que **1 968** (8 mappers × 246 mots). C'est 11 500 fois moins de données échangées, pour le même résultat. En pur Python, sur une seule machine, le calcul passe aussi de 11,2 s à 5,0 s.

Le même essai montre un second phénomène. Sans combineur, le reducer le plus chargé reçoit 8,5 millions de paires, le moins chargé 3,6 millions. Les mots « la » (1,75 million d'occurrences) et « le » (1,73 million) tombent chez les reducers auxquels le hachage les attribue, et ceux-là travaillent deux fois plus que les autres. On retrouvera ce déséquilibre au §5.2.
:::

**Hadoop**, l'implémentation libre de GFS et de MapReduce lancée chez Yahoo à partir de 2006, a porté ce modèle dans toute l'industrie. Il avait une faiblesse, que le ML a rendue flagrante : entre deux étapes, tout est écrit sur disque, et répliqué. Un algorithme itératif, comme une descente de gradient qui parcourt les mêmes données cinquante fois, devient une chaîne de cinquante jobs MapReduce qui relisent et réécrivent tout à chaque tour.

[^gfs]: Sanjay Ghemawat, Howard Gobioff, Shun-Tak Leung, « The Google File System », *SOSP*, 2003.

[^mapreduce]: Jeffrey Dean, Sanjay Ghemawat, « MapReduce: Simplified Data Processing on Large Clusters », *OSDI*, 2004.

## 4. Spark : le même principe, gardé en mémoire et planifié

Spark est né en 2009 au laboratoire AMPLab de Berkeley, précisément pour les calculs itératifs et interactifs que MapReduce servait mal. L'article fondateur, publié en 2012, introduit les **RDD** (*Resilient Distributed Datasets*) : des collections partitionnées, immuables, que l'on transforme par des opérations comme `map`, `filter` ou `reduceByKey` [^rdd]. Deux idées les distinguent.

La première est que Spark peut garder un résultat intermédiaire **en mémoire** et le réutiliser, au lieu de le réécrire sur disque. Les auteurs mesuraient jusqu'à 20 fois moins de temps que Hadoop sur des applications itératives.

La seconde est la manière de tolérer les pannes. Un RDD retient la suite de transformations qui l'a produit à partir des données d'origine, sa **lignée** (*lineage*), plutôt que des copies de ses données. Si une partition est perdue, Spark la recalcule à partir de cette recette.

Aujourd'hui, on n'écrit presque plus de RDD à la main. On manipule des **DataFrames**, des tables avec un schéma, par une interface proche de SQL et de pandas. Cette interface a une conséquence décisive : Spark sait *ce que* vous voulez calculer, et pas seulement *comment*. Un optimiseur, Catalyst, réécrit la requête avant de l'exécuter. Il repousse les filtres au plus près de la lecture, ne lit que les colonnes utiles et choisit la stratégie de jointure [^sparksql]. C'est aussi pourquoi Spark est **paresseux**. `df.where(...)` et `df.groupBy(...)` ne calculent rien : ils construisent un plan. Le calcul ne part qu'au moment d'une **action** qui demande un résultat, comme `count()`, `collect()` ou l'écriture d'un fichier.

### 4.1 Driver, exécuteurs, étapes et tâches

Une application Spark se compose d'un **driver**, le programme qui construit le plan et l'ordonnance, et d'**exécuteurs**, des processus répartis sur les machines du cluster qui exécutent les tâches. En mode local (`local[*]`), celui du TP 30, driver et exécuteurs vivent dans un même processus Java, et chaque cœur de la machine exécute une tâche à la fois.

Quand une action arrive, le driver découpe le plan en **étapes** (*stages*). La frontière entre deux étapes, c'est toujours un shuffle. À l'intérieur d'une étape, les transformations ont des **dépendances étroites** : chaque partition du résultat ne dépend que d'une partition de l'entrée. Lire, filtrer, calculer une colonne, pré-agréger : tout cela s'enchaîne sur place, dans la même tâche, sans rien écrire. Une **dépendance large**, comme un regroupement par clé, une jointure ou un tri global, exige que chaque partition du résultat reçoive des morceaux de *toutes* les partitions de l'entrée. Spark doit alors terminer l'étape en cours, écrire son résultat sur le disque local, rangé par partition de destination, puis démarrer l'étape suivante, dont les tâches vont chercher leurs morceaux chez toutes les autres. Chaque étape est enfin découpée en **tâches**, une par partition.

<Figure src="spark-etapes" num="36.2" alt="Le driver traduit groupBy utilisateur count en plan et le coupe en deux étapes. Étape 1, 26 tâches : chaque tâche lit la colonne utilisateur de ses fichiers Parquet et compte en local. Toutes écrivent dans des fichiers de shuffle sur disque local, 106 Mio, 200 partitions par hachage de l'utilisateur. Étape 2, 22 tâches : chaque tâche additionne les comptes reçus de toutes les tâches de l'étape 1. Mesuré sur 100 millions d'événements : 7,3 s.">
  Un regroupement par utilisateur sur le journal. Les flèches droites sont des dépendances étroites, le faisceau croisé est la dépendance large qui coupe le job en deux.
</Figure>

:::exemple[Exemple 36.4 : premier contact avec le journal]
Spark 4.2.0, mode local sur 22 cœurs. On compte les lignes du CSV de deux façons.

```python
spark.read.csv("journal.csv", header=True, inferSchema=True).count()   # 31,7 s
spark.read.csv("journal.csv", header=True, schema=SCHEMA).count()      #  4,4 s
```

Avec `inferSchema=True`, Spark ne connaît pas le type des colonnes. Il lit donc le fichier une première fois pour le deviner, puis une seconde fois pour compter. L'interface de Spark (`http://localhost:4040`, onglet *Stages*) affiche 18,81 Gio lus, deux fois le fichier, et quatre jobs. En donnant le schéma, on lit 9,40 Gio en une seule passe.

Le comptage lui-même prend 4,4 s, et un regroupement par catégorie sur le même CSV 16,9 s. La différence ne vient pas des octets lus, identiques, mais du **décodage** : pour compter, Spark n'a pas besoin de découper les lignes en colonnes, alors que pour regrouper, il doit analyser 100 millions de lignes de texte. Le CSV coûte du calcul, pas seulement de la lecture.

L'étape de lecture compte 76 tâches. Spark découpe les fichiers en tranches d'au plus 128 Mio (`spark.sql.files.maxPartitionBytes`), et $10\,092\,568\,727 / 134\,217\,728 \approx 75{,}2$, arrondi à 76. Sur 22 cœurs, ces 76 tâches s'exécutent en un peu moins de quatre vagues.
:::

[^rdd]: Matei Zaharia, Mosharaf Chowdhury, Tathagata Das, Ankur Dave, Justin Ma, Murphy McCauley, Michael J. Franklin, Scott Shenker, Ion Stoica, « Resilient Distributed Datasets: A Fault-Tolerant Abstraction for In-Memory Cluster Computing », *NSDI*, 2012.

[^sparksql]: Michael Armbrust et al., « Spark SQL: Relational Data Processing in Spark », *SIGMOD*, 2015.

## 5. Le shuffle, là où part le temps

Tout ce qui se passe à l'intérieur d'une étape est bon marché : chaque cœur traite ses données sans attendre personne. Le shuffle, lui, cumule les trois coûts d'un système distribué. Il faut sérialiser les lignes et les écrire sur disque, les transférer par le réseau (en mode local, le disque et la mémoire en tiennent lieu), et attendre que la dernière tâche de l'étape précédente ait fini. Apprendre à optimiser Spark, c'est d'abord apprendre à voir ses shuffles.

On les lit dans le **plan physique**, que `explain()` affiche. Voici celui du regroupement par utilisateur de la figure 36.2 :

```text
AdaptiveSparkPlan isFinalPlan=false
+- HashAggregate(keys=[utilisateur#1], functions=[count(1)])
   +- Exchange hashpartitioning(utilisateur#1, 200), ENSURE_REQUIREMENTS
      +- HashAggregate(keys=[utilisateur#1], functions=[partial_count(1)])
         +- FileScan parquet [utilisateur#1] ... ReadSchema: struct<utilisateur:int>
```

Il se lit de bas en haut. Spark lit la seule colonne `utilisateur`, compte partiellement dans chaque tâche (`partial_count` : le combineur de MapReduce, que Spark ajoute tout seul), puis l'`Exchange` redistribue les comptes partiels en 200 partitions par hachage de l'utilisateur. C'est le shuffle. Il reste à additionner les comptes partiels de chaque utilisateur. Chaque `Exchange` d'un plan est un shuffle, et donc une frontière d'étape.

Le nombre 200 est la valeur par défaut de `spark.sql.shuffle.partitions`, fixée une fois pour toutes quelle que soit la taille des données. Depuis Spark 3, l'**exécution adaptative** (*Adaptive Query Execution*, AQE) corrige ce choix pendant l'exécution. Une fois l'étape 1 terminée, Spark connaît la taille réelle de chaque partition et regroupe les petites, avec une cible d'environ 64 Mio [^aqe]. Ici, les 200 partitions sont devenues 22 tâches.

:::exemple[Exemple 36.5 : trois regroupements, trois shuffles]
Sur le journal converti en Parquet (§6), trois requêtes qui se ressemblent :

| Requête | Clés distinctes | Shuffle écrit | Temps |
|---|---|---|---|
| nombre d'événements par catégorie | 5 | 8,9 Kio | 4,1 s[^premier] |
| nombre d'événements par utilisateur | 500 000 | 106,4 Mio | 7,3 s |
| nombre de tâches distinctes (exact) | 28,9 millions | 462,6 Mio | 20,1 s |
| nombre de tâches distinctes (approché) | | 11,4 Kio | 2,0 s |

Le volume du shuffle suit le nombre de clés, pas le nombre de lignes. Grâce à la pré-agrégation, chaque tâche de lecture n'envoie qu'une ligne par clé qu'elle a vue. Pour 5 catégories, c'est 26 tâches × 5 lignes : rien. Pour les utilisateurs, chaque tâche en voit presque tous : au plus 26 × 500 000 = 13 millions de comptes partiels, environ 8 octets chacun une fois compressés. Pour les tâches distinctes, il n'y a presque rien à pré-agréger, puisque chaque tâche voit 3,8 millions d'identifiants presque tous différents, et le shuffle transporte près de 100 millions de valeurs.

On peut vérifier le résultat exact par le calcul. On a tiré 100 millions d'identifiants au hasard parmi 30 millions. La probabilité qu'un identifiant donné ne soit jamais tiré vaut $(1 - 1/N)^{n} \approx e^{-n/N} = e^{-10/3} \approx 0{,}036$. On attend donc $30 \times 10^6 \times (1 - 0{,}036) \approx 28{,}93$ millions d'identifiants distincts : Spark en trouve 28 928 454.

La dernière ligne remplace le calcul exact par `approx_count_distinct`, qui utilise HyperLogLog++ [^hll]. Chaque tâche résume ses identifiants dans une petite structure de taille fixe (quelques kilooctets), et ces structures se fusionnent. Le shuffle passe de 462,6 Mio à 11,4 Kio, le temps de 20,1 s à 2,0 s. En échange, le résultat vaut 29 871 570, soit 3,3 % de trop. L'erreur relative visée par défaut est de 5 %. Pour un tableau de bord, c'est parfait. Pour une facture, non.
:::

[^premier]: La première requête d'une session paie en plus le démarrage des exécuteurs et la lecture des métadonnées des fichiers. Répétée, elle prend 1,4 s (§6).

### 5.1 Lire l'interface de Spark

Pendant qu'une application tourne, Spark sert une interface web sur le port 4040 du driver. L'onglet *SQL / DataFrame* montre le plan de chaque requête avec, sur chaque opérateur, le nombre de lignes réellement produites. L'onglet *Stages* donne, pour chaque étape, le nombre de tâches, les octets lus, les octets écrits et lus par le shuffle, et surtout la **répartition des durées des tâches** : minimum, médiane, 75ᵉ centile, maximum. C'est cette ligne qu'on regarde en premier. Quand le maximum vaut dix fois la médiane, le problème n'est pas la puissance de calcul : c'est une partition trop grosse.

Une mise en garde, vécue pendant la préparation. Pour les fichiers Parquet, la colonne *Input* de Spark 4.2 affichait environ 480 Kio lus, quelle que soit la requête, alors que le système d'exploitation voyait le processus lire entre 26 Mio et 1,7 Gio. Le lecteur Parquet vectorisé ne rapporte pas toutes ses lectures dans cette métrique. Tous les volumes lus donnés dans ce chapitre pour Parquet viennent donc du compteur du noyau (`rchar` dans `/proc/<pid>/io`), recoupé avec les métadonnées des fichiers. Une métrique qu'on n'a jamais confrontée à une autre source n'est qu'une hypothèse.

### 5.2 Le déséquilibre

Le hachage répartit bien les clés entre les partitions. Il ne peut rien contre une **clé** qui porte à elle seule une grande partie des lignes. Dans notre journal, l'utilisateur 42 n'est pas une personne mais la synchronisation automatique d'un calendrier, qui produit 9 999 500 événements, 10 % du total. L'utilisateur suivant en a 22 336. Tout regroupement ou toute jointure par utilisateur envoie ces dix millions de lignes dans une seule partition, donc à une seule tâche.

:::exemple[Exemple 36.6 : une jointure qui attend une seule tâche]
On veut la durée moyenne des actions selon la formule d'abonnement : il faut joindre le journal (100 millions de lignes) à la table des utilisateurs (500 000 lignes). La stratégie de jointure la plus générale, la **jointure par tri-fusion** (*sort-merge join*), fait passer les deux tables par un shuffle sur la clé de jointure, puis trie et fusionne chaque partition. On l'a forcée en désactivant la diffusion (voir plus bas) :

- Shuffle : 816,6 Mio. Durée totale : 18,3 s.
- Étape de la jointure : 200 tâches, de 0,5 s en médiane, 1,9 s au 90ᵉ centile, et **5,6 s** pour la plus longue.
- Cette tâche lit 50,4 Mio et 10,4 millions de lignes. La médiane est de 3,9 Mio et 453 000 lignes.

Pendant les dernières secondes, un seul cœur sur 22 travaille : celui qui traite l'utilisateur 42.

L'exécution adaptative n'a pas corrigé ce déséquilibre. Elle sait découper une partition trop grosse, mais seulement si elle dépasse à la fois cinq fois la taille médiane *et* 256 Mio [^aqe]. Notre partition fait treize fois la médiane, mais 50 Mio seulement. AQE a bien regroupé les 200 partitions en 24 tâches plus grosses (7,4 s de médiane, 12,1 s pour la plus longue), sans gain de temps : 19,5 s.

La vraie solution consiste à ne pas faire de shuffle du tout. Si l'une des deux tables est petite, Spark peut l'envoyer entière à chaque tâche, qui fait la jointure sur place, sur son morceau du journal : c'est la **jointure par diffusion** (*broadcast join*). Le shuffle tombe de 816,6 Mio à 3,8 Kio (le résultat final), le temps de 18,3 à 7,9 s, et les 25 tâches durent toutes entre 2,8 et 3,3 s. L'utilisateur 42 ne gêne plus personne, puisque ses lignes ne quittent jamais leur tâche.

Avec ses réglages par défaut, Spark a d'ailleurs choisi cette stratégie tout seul (7,5 s) : il diffuse automatiquement une table estimée à moins de 10 Mo (`spark.sql.autoBroadcastJoinThreshold`). Le déséquilibre apparaît donc quand la « petite » table dépasse ce seuil, ce qui arrive vite : il suffit d'ajouter à la table des utilisateurs leur nom, leur pays et leur date d'inscription. On peut alors relever le seuil, forcer la diffusion par `F.broadcast(utilisateurs)`, ou traiter la clé problématique à part.
:::

<Figure src="jointure-desequilibre" num="36.3" alt="À gauche, la jointure par tri-fusion : le journal de 100 millions de lignes et la table de 500 000 utilisateurs passent par un shuffle par hachage de l'utilisateur, 816,6 Mio. Parmi les partitions, une barre rouge treize fois plus haute que les autres : la partition de l'utilisateur 42, 10,4 millions de lignes, 50,4 Mio, 5,6 s ; les 199 autres font 453 000 lignes, 3,9 Mio et 0,5 s en médiane. Durée 18,3 s. À droite, la jointure par diffusion : la table des utilisateurs est copiée dans chaque tâche, le journal reste sur place ; shuffle 3,8 Kio, 7,9 s, 25 tâches de 2,8 à 3,3 s.">
  La même jointure, mesurée. Les hauteurs des barres respectent le rapport mesuré entre la partition de l'utilisateur 42 et la partition médiane.
</Figure>

Deux autres techniques reviennent souvent quand la diffusion n'est pas possible. On peut **isoler** la clé lourde : la traiter dans une requête séparée, puis réunir les résultats. On peut aussi **saler** la clé (*salting*) : ajouter à l'utilisateur 42 un suffixe aléatoire de 0 à 9, pour répartir ses lignes sur dix partitions, en dupliquant d'autant les lignes correspondantes de l'autre table. Les deux supposent de savoir quelles clés sont lourdes, et c'est l'interface de Spark qui vous le dit.

[^aqe]: Documentation d'Apache Spark, « Performance Tuning », section *Adaptive Query Execution*. Valeurs par défaut vérifiées sur Spark 4.2.0 : `advisoryPartitionSizeInBytes` 64 Mio, `skewedPartitionFactor` 5, `skewedPartitionThresholdInBytes` 256 Mio.

[^hll]: Philippe Flajolet, Éric Fusy, Olivier Gandouet, Frédéric Meunier, « HyperLogLog: the analysis of a near-optimal cardinality estimation algorithm », *AofA*, 2007 ; Stefan Heule, Marc Nunkesser, Alexander Hall, « HyperLogLog in Practice », *EDBT*, 2013.

## 6. Le format des fichiers compte autant que le moteur

Un fichier CSV range les données **ligne après ligne**. C'est naturel pour écrire un journal, et désastreux pour l'analyser. Pour connaître la catégorie de chaque événement, il faut lire chaque ligne en entier, titre compris, et la découper caractère par caractère.

Les formats **en colonnes** rangent au contraire toutes les valeurs d'une même colonne ensemble. L'idée est ancienne dans les bases de données analytiques. Elle s'est imposée dans l'écosystème distribué avec Dremel, le moteur de requêtes interactives de Google, décrit en 2010 [^dremel], dont s'inspire directement **Apache Parquet** [^parquet]. Un fichier Parquet est découpé en **groupes de lignes** (*row groups*). Dans chaque groupe, chaque colonne forme un bloc séparé, compressé à part. Un pied de fichier décrit le schéma, l'emplacement de chaque bloc et, pour chaque bloc, des **statistiques** : le minimum, le maximum et le nombre de valeurs nulles.

<Figure src="ligne-colonne" num="36.4" alt="À gauche, un CSV : des lignes complètes les unes après les autres. À droite, un fichier Parquet : des groupes de lignes, chacun découpé en blocs par colonne (horodatage, utilisateur, tâche, action, catégorie, client, durée, titre), et un pied de fichier avec le schéma et les min et max de chaque colonne de chaque groupe ; 76 groupes de 1,33 million de lignes. En bas, les octets lus par Spark pour la même réponse, en échelle logarithmique : nombre par catégorie sur le CSV, 9,4 Gio et 19,9 s ; sur Parquet, 37 Mio et 1,4 s ; moyenne d'un mois sur Parquet INT96, 447 Mio et 2,3 s ; sur Parquet avec statistiques, 26,6 Mio et 0,7 s.">
  Deux façons de ranger les mêmes données, et ce qu'une requête doit lire dans chaque cas (mesuré).
</Figure>

Ce rangement permet trois économies, qui se cumulent :

- **ne lire que les colonnes utiles** (*projection pushdown*) : une requête sur la catégorie ignore les blocs des sept autres colonnes ;
- **ne pas lire les groupes inutiles** (*predicate pushdown*) : si le maximum de l'horodatage d'un groupe est antérieur au début de la période demandée, le groupe est sauté sans être ouvert ;
- **mieux compresser** : une colonne contient des valeurs du même type, souvent répétées. Parquet la code par **dictionnaire** (la liste des valeurs distinctes, puis un petit numéro par ligne), puis compresse les suites de numéros identiques (*run-length encoding*), avant d'appliquer un compresseur général comme Snappy ou Zstandard.

:::exemple[Exemple 36.7 : le même journal, en Parquet]
La conversion avec Spark prend 45,8 s (une lecture du CSV, une écriture) et produit 76 fichiers :

| Format | Taille | Rapport |
|---|---|---|
| CSV | 10,09 Go | 1 |
| Parquet, compression Snappy (défaut) | 1,51 Go | 6,7 fois plus petit |
| Parquet, compression Zstandard | 1,15 Go | 8,8 fois plus petit |

Les métadonnées des fichiers donnent la place de chaque colonne dans la version Snappy. Les identifiants (`tache` 382 Mio, `utilisateur` 357 Mio) et l'horodatage (328 Mio) en occupent les trois quarts : ce sont des nombres presque tous différents, qui se compressent mal. La colonne `categorie` ne pèse que 36 Mio pour 100 millions de valeurs, grâce au dictionnaire : 5 valeurs possibles, donc 3 bits par ligne avant compression. Même le `titre`, colonne la plus lourde du CSV, tombe à 159 Mio, parce que les 100 millions de titres n'en contiennent que 4 395 distincts (repris des 24 000 tâches de Listify, où les mêmes titres reviennent souvent).

Mêmes requêtes, mêmes résultats :

| Requête | CSV | Parquet |
|---|---|---|
| nombre d'événements par catégorie | 19,9 s, 9,4 Gio lus | 1,4 s, 37 Mio lus |

Parquet lit ici 250 fois moins d'octets. Les 37 Mio correspondent presque exactement aux 36 Mio de la colonne `categorie` : Spark n'a rien lu d'autre.
:::

:::exemple[Exemple 36.8 : le piège des horodatages INT96]
Deuxième requête : la durée moyenne des actions en mars 2026, un mois sur dix-huit. Le journal est trié par date, si bien que chaque fichier couvre une tranche de temps d'environ une semaine. Les statistiques devraient permettre de sauter tous les groupes hors du mois demandé. Or la première conversion a lu **447 Mio** et mis 2,3 s, soit deux colonnes entières sur tout le journal.

Les métadonnées des fichiers expliquent pourquoi. La colonne `horodatage` y est de type `INT96`, un ancien format d'horodatage hérité d'Impala et de Hive, que Spark 4.2 écrit encore par défaut (`spark.sql.parquet.outputTimestampType = INT96`). Pour ce type, Parquet n'enregistre ni minimum ni maximum : `has_min_max: False`. Le filtre figure bien dans le plan (`PushedFilters: [GreaterThanOrEqual(horodatage, ...)]`), mais sans statistiques, il n'a rien sur quoi s'appuyer.

En réécrivant avec le type standard :

```python
spark.conf.set("spark.sql.parquet.outputTimestampType", "TIMESTAMP_MICROS")
```

les statistiques apparaissent. Seuls 5 groupes sur 76 recouvrent mars 2026, soit 28,8 Mio d'après les métadonnées. Spark lit **26,6 Mio**, et la requête prend 0,7 s. Le réglage n'a rien changé à la taille des fichiers : il a changé ce qu'on peut **ne pas lire**.

La leçon dépasse Spark. Un filtre « poussé vers le stockage » n'économise quelque chose que si le stockage peut y répondre sans lire les données. Il faut donc des statistiques, et des données **triées ou regroupées** selon la colonne filtrée. Le même filtre sur `utilisateur`, dispersé dans tous les fichiers, ne sauterait aucun groupe.
:::

Parquet permet enfin de **partitionner** un jeu de données en répertoires selon une colonne, par exemple `journal/mois=2026-03/part-0001.parquet`. Un filtre sur le mois élimine alors des répertoires entiers avant même d'ouvrir un fichier. C'est puissant sur une colonne de faible cardinalité comme la date. Sur une colonne comme l'utilisateur, c'est désastreux : on crée des centaines de milliers de minuscules fichiers, et le simple fait de les lister coûte plus cher que de les lire. Le TP 30 mesure ce piège.

[^dremel]: Sergey Melnik, Andrey Gubarev, Jing Jing Long, Geoffrey Romer, Shiva Shivakumar, Matt Tolton, Theo Vassilakis, « Dremel: Interactive Analysis of Web-Scale Datasets », *VLDB*, 2010.

[^parquet]: Apache Parquet, documentation du format de fichier. [parquet.apache.org/docs/file-format](https://parquet.apache.org/docs/file-format/)

## 7. Faut-il vraiment Spark ?

En 2015, trois chercheurs ont publié un article au titre provocateur, « Scalability! But at what COST? » [^cost]. Ils y définissent le **COST** d'un système distribué (*Configuration that Outperforms a Single Thread*) : le nombre de cœurs dont il a besoin pour battre une bonne implémentation sur **un seul fil d'exécution**. Pour plusieurs systèmes de traitement de graphes publiés dans les grandes conférences, ce nombre se comptait en centaines de cœurs, et pour certains il était infini : ils étaient plus lents qu'un seul cœur quelle que soit la taille du cluster. Un système qui passe bien à l'échelle n'est pas pour autant un système rapide. Il peut passer à l'échelle justement parce qu'il gaspille beaucoup à chaque étape, et qu'ajouter des machines dilue ce gaspillage.

On a refait l'exercice sur notre journal, avec un moteur analytique qui tourne dans un seul processus : **DuckDB**, une base de données en colonnes qui s'importe comme une bibliothèque, et interroge directement des fichiers CSV ou Parquet en SQL [^duckdb].

<Figure src="cout-spark-duckdb" num="36.5" alt="Barres horizontales des temps de Spark et de DuckDB sur la même machine. Nombre par catégorie sur le CSV : Spark 19,9 s, DuckDB 5,2 s. Nombre par catégorie sur Parquet : Spark 1,4 s, DuckDB 0,1 s. Tâches distinctes exactes sur Parquet : Spark 20,1 s, DuckDB 1,4 s. Jointure avec les utilisateurs sur Parquet : Spark 18,3 s, ou 7,9 s par diffusion, DuckDB 0,8 s. pandas, tout le CSV en mémoire : tué par le noyau après 64 s, au plafond de 6 Gio.">
  Les mêmes requêtes, sur les mêmes fichiers et la même machine de 22 cœurs. Spark en mode local, hors démarrage de la session ; DuckDB 1.5.5, 2,2 Gio de mémoire au plus.
</Figure>

Sur une machine, DuckDB va de 4 à 23 fois plus vite que Spark selon la requête, sans configuration, sans JVM, et sans les 6 s de démarrage d'une session Spark. Il utilise lui aussi tous les cœurs, mais il n'a pas à se préparer à ce que ses données soient ailleurs. Il n'écrit pas de fichiers de shuffle, ne sérialise pas ses lignes pour les envoyer à d'autres processus, et ne découpe pas son travail en tâches ordonnancées une à une. Tout ce que Spark paie pour pouvoir s'étendre à cent machines, il le paie aussi sur une seule.

Ce n'est pas un argument contre Spark, c'est un argument pour **choisir**. Spark se justifie quand :

- les données ou les résultats intermédiaires ne tiennent vraiment pas sur les disques et dans la mémoire d'une machine, même bien équipée ;
- le travail dure des heures, et il faut qu'une panne de machine ne le fasse pas recommencer de zéro ;
- l'entreprise dispose déjà d'un cluster et d'une plateforme autour (Databricks, EMR, Dataproc), et c'est là que vivent les données ;
- on a besoin du même moteur pour les lots et pour les flux (chapitre 37), ou de ses bibliothèques.

Pour un jeu de 10 Go, et même de quelques centaines, commencez par une machine et un moteur en colonnes. Passez à Spark quand une mesure vous y oblige, pas avant.

[^cost]: Frank McSherry, Michael Isard, Derek G. Murray, « Scalability! But at what COST? », *HotOS*, 2015.

[^duckdb]: Mark Raasveldt, Hannes Mühleisen, « DuckDB: an Embeddable Analytical Database », *SIGMOD* (démonstration), 2019.

## 8. Du lac de données au *lakehouse*

Pendant longtemps, les entreprises ont rangé leurs données analytiques dans un **entrepôt de données** (*data warehouse*) : une base relationnelle spécialisée, avec des tables, des transactions, un schéma contrôlé, mais un stockage propriétaire et coûteux. Avec Hadoop, puis le stockage objet du cloud (S3, et le MinIO de vos TP), est apparu le **lac de données** (*data lake*). On y dépose des fichiers, souvent en Parquet, à bas coût, et n'importe quel moteur peut les lire.

Un lac de fichiers n'a rien d'une base de données, et les problèmes arrivent vite :

- **Pas de transactions.** Un job Spark qui écrit 76 fichiers et tombe au 40ᵉ laisse une table à moitié écrite, que les lecteurs voient telle quelle.
- **Pas de mises à jour ni de suppressions.** Pour effacer un utilisateur, ce que le RGPD impose à sa demande (chapitre 38), il faut réécrire chaque fichier qui contient une de ses lignes, sans que personne ne lise pendant ce temps.
- **Pas d'historique.** On ne peut pas relire la table telle qu'elle était au moment de l'entraînement d'un modèle.
- **Des listes de fichiers coûteuses.** Sur un stockage objet, lister des milliers de fichiers prend du temps, et deux écrivains simultanés peuvent se marcher dessus.

Les **formats de table** répondent à ces problèmes sans quitter les fichiers Parquet. Delta Lake (Databricks, 2019), Apache Iceberg (né chez Netflix) et Apache Hudi (né chez Uber) ajoutent à côté des fichiers de données un **journal des transactions**. Chaque modification de la table y est un nouveau fichier qui dit : « la version 18 de la table, ce sont ces fichiers-là ». Écrire une nouvelle version revient à ajouter atomiquement une entrée au journal. Une écriture interrompue n'a donc jamais existé, et un lecteur voit toujours une version complète [^delta]. Les versions anciennes restent lisibles tant qu'on n'a pas supprimé leurs fichiers : c'est le **voyage dans le temps** (*time travel*). Le journal contient aussi les statistiques des fichiers, ce qui évite de lister le stockage et permet de sauter des fichiers entiers.

L'article « Lakehouse » de 2021 a donné un nom à cette architecture : un lac de données en formats ouverts, doté par-dessus des garanties d'un entrepôt (transactions, schéma, gouvernance), et lisible aussi bien par les outils de BI que par les outils de ML [^lakehouse].

Pour une chaîne de ML, le voyage dans le temps rejoint une question que le chapitre 28 réglait avec DVC : **sur quelles données exactes ce modèle a-t-il été entraîné ?** Enregistrer, dans le run MLflow, le numéro de version de la table d'entraînement donne la même traçabilité que l'empreinte d'un fichier suivi par DVC, sans copier les données.

[^delta]: Michael Armbrust et al., « Delta Lake: High-Performance ACID Table Storage over Cloud Object Stores », *Proceedings of the VLDB Endowment*, vol. 13, n° 12, 2020.

[^lakehouse]: Michael Armbrust, Ali Ghodsi, Reynold Xin, Matei Zaharia, « Lakehouse: A New Generation of Open Platforms that Unify Data Warehousing and Advanced Analytics », *CIDR*, 2021.

## 9. Où Spark s'insère dans une chaîne de ML

Dans les chaînes que vous avez construites ce semestre, Spark (ou DuckDB, selon la taille) intervient surtout à deux endroits :

- **en amont de l'entraînement**, pour calculer des caractéristiques sur de gros historiques. Nombre de tâches complétées par utilisateur et par semaine, heure habituelle d'activité, catégories corrigées à la main : autant de regroupements, donc de shuffles, sur le journal complet, dont le résultat est une table bien plus petite qui sert à l'entraînement ;
- **en aval**, pour la **prédiction par lots** du chapitre 30 : appliquer le modèle à des millions de lignes chaque nuit. Chaque tâche charge le modèle une fois et l'applique à sa partition, sans aucun shuffle. C'est le cas idéal pour Spark : un travail parfaitement parallèle.

L'entraînement lui-même se fait rarement avec Spark. La bibliothèque MLlib existe, avec des régressions et des arbres distribués. Mais les modèles de la plupart des équipes s'entraînent sur une machine, éventuellement avec des GPU, à partir de la table de caractéristiques que Spark a préparée. Les grands modèles profonds, eux, ont leurs propres outils de distribution. Quand le DAG Airflow du chapitre 32 appelle Spark, c'est en général pour une tâche `extraire` ou `predire_par_lots`, rarement pour la tâche `entrainer`.

## Ce qu'il faut retenir

<div className="retenir">

1. Avant de distribuer, mesurez. Un DataFrame pandas pèse souvent deux à quatre fois son CSV (ici 32 Gio pour 10 Go), mais des types bien choisis, un format en colonnes et un moteur comme DuckDB repoussent très loin la limite d'une machine.
2. MapReduce se résume à deux fonctions sans effet de bord (map, reduce) et une étape gérée par le système, le shuffle. Ce modèle permet de relancer les tâches en panne et de rapprocher le calcul des données.
3. Spark garde les résultats en mémoire, recalcule les partitions perdues à partir de leur lignée et, avec les DataFrames, optimise la requête avant de l'exécuter. Il est paresseux : rien ne se calcule avant une action.
4. Un job se découpe en étapes, et chaque frontière d'étape est un shuffle, visible comme un `Exchange` dans le plan. Le volume d'un shuffle suit le nombre de clés distinctes, pas le nombre de lignes (8,9 Kio pour 5 clés, 463 Mio pour 29 millions).
5. Une clé qui porte une grande part des lignes fait attendre toute l'étape pour une seule tâche. On le voit en comparant la durée maximale des tâches à leur médiane. La jointure par diffusion supprime le shuffle quand une table est petite.
6. Parquet range par colonnes, compresse par dictionnaire et garde des statistiques par groupe de lignes : 37 Mio lus au lieu de 9,4 Gio. Ces statistiques n'existent que pour des types qui les supportent (pas INT96) et ne servent que si les données sont triées ou regroupées selon le filtre.
7. Les formats de table (Delta Lake, Iceberg, Hudi) ajoutent aux fichiers Parquet un journal de transactions : écritures atomiques, suppressions, voyage dans le temps. C'est ce qui permet de savoir sur quelle version exacte des données un modèle a été entraîné.

</div>

## Regard recherche

:::recherche
Le calcul distribué sur données massives est un domaine où quelques articles ont façonné l'industrie entière :

- **Jeffrey Dean, Sanjay Ghemawat, « MapReduce », *OSDI*, 2004.** Treize pages qui restent un modèle de clarté ; la section sur la tolérance aux pannes et les tâches de secours se lit encore avec profit.
- **Matei Zaharia et al., « Resilient Distributed Datasets », *NSDI*, 2012.** La lignée comme alternative à la réplication, et pourquoi elle suffit pour des transformations déterministes.
- **Frank McSherry, Michael Isard, Derek G. Murray, « Scalability! But at what COST? », *HotOS*, 2015.** Cinq pages qui devraient précéder tout achat de cluster.
- **Michael Armbrust et al., « Lakehouse », *CIDR*, 2021**, et **Delta Lake, *PVLDB*, 2020.** La justification de l'architecture qui domine aujourd'hui les plateformes de données.
- **Daniel Abadi, Samuel Madden, Nabil Hachem, « Column-Stores vs. Row-Stores: How Different Are They Really? », *SIGMOD*, 2008.** Pourquoi le stockage en colonnes gagne, et quelles optimisations y contribuent vraiment.

Piste d'innovation : la gestion automatique du déséquilibre et du choix des partitions reste imparfaite, comme l'exemple 36.6 l'a montré. Des travaux récents cherchent à apprendre ces décisions (nombre de partitions, stratégie de jointure) à partir de l'historique des exécutions, plutôt que de les régler par des seuils fixes.
:::

## Bibliographie du chapitre

<div className="biblio">

### Sources primaires

- Jeffrey Dean, Sanjay Ghemawat, « MapReduce: Simplified Data Processing on Large Clusters », *OSDI*, 2004.
- Matei Zaharia et al., « Resilient Distributed Datasets », *NSDI*, 2012.
- Documentation d'Apache Spark, en particulier « Performance Tuning » et « Parquet Files ». [spark.apache.org/docs/latest](https://spark.apache.org/docs/latest/)
- Documentation du format Apache Parquet. [parquet.apache.org](https://parquet.apache.org/docs/)

### Lectures recommandées

- Martin Kleppmann, *Designing Data-Intensive Applications*, O'Reilly, 2017, chapitre 10 (« Batch Processing ») : de la philosophie Unix à MapReduce et aux moteurs de flux de données, le meilleur exposé d'ensemble.
- Bill Chambers, Matei Zaharia, *Spark: The Definitive Guide*, O'Reilly, 2018 : l'ouvrage de référence sur l'API DataFrame et le fonctionnement interne de Spark.
- Holden Karau, Rachel Warren, *High Performance Spark*, O'Reilly, 2017 : les jointures, le déséquilibre, le salage, en détail.

### Pour aller plus loin

- Les articles de la rubrique « Regard recherche ».
- Sergey Melnik et al., « Dremel », *VLDB*, 2010, et sa rétrospective, « Dremel: A Decade of Interactive SQL Analysis at Web Scale », *VLDB*, 2020.
- Jordan Tigani, « Big Data is Dead », 2023 : un plaidoyer, à lire comme tel, pour les traitements sur une seule machine.

</div>
