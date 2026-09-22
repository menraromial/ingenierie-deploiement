---
title: "Ch. 27 : Pourquoi le ML en production est différent"
sidebar_label: "Ch. 27 : Pourquoi le ML en production est différent"
hide_title: true
---

import ChapterHead from '@site/src/components/ChapterHead';
import Figure from '@site/src/components/Figure';

<ChapterHead
  kicker="Semestre 3 · Bloc 1 · Chapitre 27"
  title="Pourquoi le ML en production est différent : la dette technique cachée"
  lecture="50 min"
  competences={['C1', 'C4']}
/>

:::objectifs
À l'issue de ce chapitre, vous saurez :

- expliquer en quoi un système d'apprentissage automatique diffère d'un logiciel classique, et pourquoi cette différence rend sa mise en production plus difficile ;
- définir la dette technique propre au ML et en citer les grandes familles, d'après l'article de Sculley et al. (2015) ;
- reconnaître sur un cas concret l'intrication des variables (principe CACE), les dépendances de données instables, le décalage entre entraînement et service, et les boucles de rétroaction cachées ;
- calculer, sur des exemples chiffrés, l'effet silencieux de ces défauts sur les prédictions ;
- relier chaque famille de dette à l'outil que vous mettrez en place ce semestre.
:::

## 1. Un modèle excellent qui se dégrade sans bruit

Commençons par une histoire, celle qui servira de fil rouge à tout le semestre. L'équipe de Listify veut qu'à la saisie d'une tâche, l'application **suggère une catégorie** : « travail », « courses », « maison », « administratif », « loisirs ». Une data scientist récupère un export de 20 000 tâches déjà classées par les utilisateurs, ouvre un notebook Jupyter, et en un après-midi obtient un classifieur de textes (une représentation TF-IDF des mots, puis une régression logistique) qui atteint **94 % de bonnes réponses** sur des tâches mises de côté pour l'évaluation. Le résultat est excellent ; on décide de le mettre en production.

Un développeur recopie la logique du notebook dans une petite API Python, l'image est construite par le pipeline du semestre 2, Argo CD la déploie, Prometheus la surveille. Tout est vert : les requêtes aboutissent, la latence est de 20 ms, aucune erreur 500. Trois mois plus tard, en regardant les tâches que les utilisateurs recatégorisent à la main, quelqu'un constate que le modèle ne donne plus la bonne catégorie qu'**une fois sur cinq**. À aucun moment un indicateur n'est passé au rouge.

Que s'est-il passé ? Plusieurs choses, que ce chapitre va démonter une par une : l'API ne prétraitait pas les textes exactement comme le notebook, une équipe voisine a changé le format d'une donnée d'entrée, les utilisateurs ont pris l'habitude d'accepter la suggestion sans la relire, et les tâches saisies aujourd'hui ne ressemblent plus tout à fait à celles de l'export sur lequel le modèle a appris. Aucune de ces causes n'est un « bogue » au sens du semestre 2 : le code fait exactement ce qu'on lui a demandé. C'est la raison d'être de ce semestre, et de la discipline qu'on appelle **MLOps**.

:::info[Le fil rouge du semestre]
Le classifieur de catégories de Listify accompagne tout le semestre : on le rendra reproductible (bloc 1), on suivra ses entraînements et on les orchestrera (bloc 2), on le servira sur Kubernetes et on surveillera sa dérive (bloc 3). Listify reste l'application déployée ; le modèle devient un service de plus, avec ses propres exigences.
:::

## 2. Ce qui change quand le comportement vient des données

### 2.1 Deux façons de produire un comportement

Dans un logiciel classique, le comportement est **écrit** : un développeur formule des règles (« si le titre contient “réunion”, catégorie travail »), et le programme applique ces règles aux données. En apprentissage automatique, on renverse la démarche : on fournit des données **et** les réponses attendues, et l'algorithme d'apprentissage en déduit les règles, rangées dans un objet qu'on appelle le **modèle** [^chollet].

<Figure src="ml-programmation" num="27.1" alt="En haut, programmation classique : des règles écrites et des données entrent dans un programme qui produit des réponses. En bas, apprentissage automatique : des données et les réponses attendues entrent dans l'apprentissage, qui produit un modèle, c'est-à-dire des règles apprises.">
  Deux paradigmes. En apprentissage automatique, les règles ne sont plus écrites mais apprises ; le comportement du système dépend donc des données au moins autant que du code.
</Figure>

Andrej Karpathy a résumé la conséquence par une formule qui a fait date : le ML est un « logiciel 2.0 », dont le code source est en grande partie **le jeu de données** [^karpathy]. Changer les données d'entraînement change le programme, exactement comme changer une ligne de code, mais sans commit, sans revue et sans test.

[^chollet]: François Chollet, *Deep Learning with Python*, Manning, 2017 (2ᵉ éd. 2021), chapitre 1, « Machine learning : un nouveau paradigme de programmation ». La figure 27.1 reprend son schéma.

[^karpathy]: Andrej Karpathy, « Software 2.0 », billet publié sur Medium, novembre 2017.

### 2.2 Ce que cela change pour l'exploitation

Chaque certitude acquise aux semestres 1 et 2 vacille. Le tableau suivant est le point de départ du semestre ; gardez-le sous les yeux.

| Question | Logiciel classique (S1, S2) | Système de ML |
|---|---|---|
| Qu'est-ce qui définit le comportement ? | Le code | Le code, **les données d'entraînement**, les hyperparamètres, l'aléa de l'entraînement |
| Qu'est-ce qu'il faut versionner ? | Le code (Git), l'image | Le code, **les données**, **le modèle**, la configuration de l'entraînement |
| Qu'est-ce qu'un test ? | Une sortie attendue, exacte | Une **qualité statistique** attendue (précision au-dessus d'un seuil), jamais une sortie exacte pour chaque entrée |
| À quoi ressemble une panne ? | Une erreur, un code 500, un processus mort | Le plus souvent **rien** : des réponses plausibles mais fausses, plus souvent qu'avant |
| Le système vieillit-il si personne n'y touche ? | Non : une version figée se comporte pareil dans dix ans | **Oui** : le monde change, les données aussi, le modèle devient obsolète |
| Quand sait-on qu'une réponse était fausse ? | Immédiatement (erreur, test) | Souvent **plus tard**, quand l'étiquette réelle arrive (la catégorie corrigée, le prêt remboursé ou non) |

Les deux dernières lignes sont les plus lourdes de conséquences. Un modèle **se dégrade même quand personne ne le modifie**, et sa panne est **silencieuse** : la surveillance du semestre 2 (taux d'erreurs HTTP, latence) ne la voit pas. Il faudra surveiller autre chose, la **qualité des prédictions** et la **distribution des données**, ce qui fera l'objet du chapitre 35.

## 3. La dette technique cachée des systèmes de ML

### 3.1 L'article fondateur

En 2015, une équipe d'ingénieurs de Google publie à la conférence NeurIPS un article au titre volontairement provocateur, « Hidden Technical Debt in Machine Learning Systems » [^sculley2015]. Il prolonge un premier texte de 2014, qui comparait déjà le ML à « une carte de crédit à fort taux d'intérêt » [^sculley2014]. Son propos tient en une phrase : développer et déployer un modèle est **rapide et bon marché**, mais le **maintenir** au fil du temps est **difficile et coûteux**, parce que les systèmes de ML accumulent, en plus de la dette technique ordinaire, des formes de dette qui leur sont propres.

La notion de **dette technique**, due à Ward Cunningham, désigne le coût futur des raccourcis pris aujourd'hui : un code écrit vite rapporte immédiatement, mais chaque modification ultérieure paie des « intérêts » en temps et en risque, jusqu'à ce qu'on rembourse en réécrivant proprement [^cunningham]. La thèse de Sculley et al. est que le ML crée de la dette **au niveau du système**, et non seulement du code, ce qui la rend invisible aux outils habituels (revue de code, analyse statique, tests unitaires).

[^sculley2015]: D. Sculley, Gary Holt, Daniel Golovin, Eugene Davydov, Todd Phillips, Dietmar Ebner, Vinay Chaudhary, Michael Young, Jean-François Crespo, Dan Dennison, « Hidden Technical Debt in Machine Learning Systems », *Advances in Neural Information Processing Systems (NeurIPS)*, 2015.

[^sculley2014]: D. Sculley et al., « Machine Learning: The High-Interest Credit Card of Technical Debt », *SE4ML: Software Engineering for Machine Learning*, atelier de NeurIPS, 2014.

[^cunningham]: Ward Cunningham, « The WyCash Portfolio Management System », *OOPSLA'92 Experience Report*, 1992, qui introduit la métaphore de la dette.

### 3.2 Le code ML n'est qu'une petite partie du système

La figure la plus citée de l'article représente un système de ML réel comme un ensemble de blocs, au centre duquel une toute petite case figure le code qui entraîne le modèle et produit les prédictions. Tout le reste est de l'infrastructure : collecter et vérifier les données, en extraire des variables, gérer les machines, orchestrer les traitements, servir les prédictions, surveiller.

<Figure src="dette-systeme-ml" num="27.2" alt="Un petit bloc « code ML » au centre, entouré de dix blocs plus grands : configuration, collecte des données, vérification des données, extraction des variables, gestion des ressources, outils d'analyse, gestion des processus, infrastructure de service, surveillance, tests et validation.">
  Le code d'apprentissage n'est qu'une petite partie d'un système de ML en production, d'après la figure 1 de Sculley et al. (2015). Les proportions sont indicatives ; le message ne l'est pas.
</Figure>

Les auteurs écrivent qu'un système mature peut n'être composé « au plus de 5 % de code de ML et au moins de 95 % de code de glue » [^sculley2015]. Ce semestre porte sur ces 95 %.

:::exemple[Compter le code d'un service de ML]
Voici la répartition des lignes de code d'un service de catégorisation comme celui de Listify, une fois industrialisé comme vous le ferez d'ici la fin du semestre. Les chiffres sont ceux d'un projet type, arrondis.

| Composant | Lignes |
|---|---|
| Extraction des données depuis PostgreSQL, nettoyage | 250 |
| Validation des données (types, valeurs manquantes, distributions) | 150 |
| Transformation des textes en variables | 120 |
| **Entraînement et évaluation du modèle** | **60** |
| Configuration (chemins, hyperparamètres, seuils) | 90 |
| API de prédiction, schémas d'entrée et de sortie | 280 |
| Orchestration (DAG de réentraînement) | 140 |
| Surveillance de la dérive, métriques | 180 |
| Tests | 400 |
| **Total** | **1 670** |

La part du code d'apprentissage proprement dit vaut $60 / 1\,670 \approx 3{,}6\,\%$. Le chiffre de l'article n'est pas une exagération rhétorique : c'est l'ordre de grandeur de tout projet réel.
:::

Il faut maintenant comprendre **pourquoi** ces 95 % accumulent une dette particulière. L'article en propose une typologie, que les sections suivantes reprennent avec des exemples tirés de Listify.

## 4. L'érosion des frontières

Le génie logiciel classique repose sur l'**encapsulation** : un module a une interface claire, et on peut modifier son intérieur sans casser le reste. Un modèle de ML détruit ces frontières, parce que son comportement résulte d'un **mélange** de toutes ses entrées.

### 4.1 L'intrication : tout changer change tout

Un modèle combine ses variables d'entrée de façon non indépendante. Si l'on modifie la distribution d'une seule variable, les poids appris pour **toutes** les autres changent au réentraînement. Sculley et al. appellent cela le principe **CACE** : *Changing Anything Changes Everything*, changer n'importe quoi change tout [^sculley2015]. Le principe vaut pour les variables, mais aussi pour les hyperparamètres, la façon d'échantillonner les données ou le seuil de convergence.

:::exemple[Deux variables jumelles]
Le modèle de Listify prédit, en plus de la catégorie, la **durée** d'une tâche en minutes. Parmi ses variables figurent deux indicateurs qui valent presque toujours la même chose : $x_1$, qui vaut 1 si le titre contient le mot « réunion », et $x_2$, qui vaut 1 si la tâche vient de l'agenda de l'entreprise (qui ne contient guère que des réunions). L'effet réel d'une réunion est d'ajouter 30 minutes. Comme les deux variables sont presque identiques, l'algorithme partage cet effet entre elles de façon arbitraire ; il apprend par exemple :

$$
\text{durée} = 15 + 18\,x_1 + 12\,x_2 + \ldots
$$

Pour une réunion, la prédiction vaut bien $15 + 18 + 12 = 45$ minutes.

Six mois plus tard, l'équipe qui gère l'import de l'agenda le désactive, et $x_2$ vaut désormais toujours 0. Sans réentraînement, toute réunion est prédite à $15 + 18 = 33$ minutes, soit 12 minutes, ou 27 %, de moins qu'avant. Aucune erreur n'est levée. Et si l'on réentraîne, le poids de $x_1$ passe à 30 : **un coefficient que personne n'a touché a changé de 67 %**. Voilà le principe CACE, sur deux lignes.
:::

### 4.2 Les cascades de corrections

Pour aller vite, on corrige souvent un modèle existant par un second modèle qui prend en entrée les sorties du premier et les ajuste pour un cas particulier (« le modèle général se trompe sur les tâches administratives : ajoutons un petit modèle correctif »). Chaque correction dépend de la précédente ; améliorer le premier modèle **dégrade** alors les suivants, calés sur ses anciennes erreurs. On aboutit à une cascade qu'on ne peut plus améliorer nulle part, parce que toute amélioration locale est une régression globale.

### 4.3 Les consommateurs non déclarés

Les prédictions d'un modèle finissent souvent par être lues par des systèmes qui n'étaient pas prévus : une équipe voisine utilise les catégories prédites par Listify pour **router les notifications** (les tâches « travail » partent sur la messagerie professionnelle). Ce consommateur n'est déclaré nulle part. Le jour où l'on améliore le modèle, et donc où la distribution des catégories change, les notifications partent au mauvais endroit, et personne ne fait le lien. C'est l'analogue, pour les données, des utilisateurs non documentés d'une API : sans contrôle d'accès ni contrat, tout changement est potentiellement une rupture (ch. 24, §4.1).

## 5. Les dépendances de données coûtent plus cher que les dépendances de code

Au semestre 2, les dépendances de code étaient épinglées (`flask==3.0.3`), analysées par Trivy, visibles dans un fichier. Les dépendances **de données** d'un modèle ne bénéficient d'aucun de ces outils : on ne sait souvent même pas lister précisément quelles tables et quelles colonnes il consomme.

### 5.1 Les dépendances instables

Une variable d'entrée est **instable** quand elle est produite par un autre système qui peut changer de comportement sans prévenir : un autre modèle, une table gérée par une autre équipe, un service externe.

:::exemple[Des minutes devenues des secondes]
Un second modèle de Listify estime la probabilité qu'une tâche soit **en retard**. C'est une régression logistique ; parmi ses entrées figure la durée estimée de la tâche, fournie par le service de planification, **en minutes**. Pour une tâche de 45 minutes, avec une ordonnée à l'origine de $-2$ et un poids de $0{,}02$ par minute :

$$
z = -2 + 0{,}02 \times 45 = -1{,}1, \qquad p = \frac{1}{1 + e^{-z}} = \frac{1}{1 + e^{1{,}1}} \approx 0{,}25.
$$

Un lundi, l'équipe du service de planification passe ses durées en **secondes**, pour plus de précision, et l'annonce dans son propre canal de discussion. La même tâche arrive désormais avec la valeur 2 700 :

$$
z = -2 + 0{,}02 \times 2\,700 = 52, \qquad p = \frac{1}{1 + e^{-52}} \approx 1.
$$

Toutes les tâches de plus de quelques minutes sont maintenant jugées « certainement en retard ». Le service de prédiction répond en 20 ms, sans erreur ; Prometheus n'a rien à signaler. Seul un contrôle **sur les données d'entrée** (la durée médiane a été multipliée par 60 du jour au lendemain) aurait pu détecter le problème : c'est la **validation des données** du bloc 2.
:::

### 5.2 Les dépendances sous-utilisées

À l'inverse, un modèle accumule des variables qui ne lui apportent presque rien : des variables historiques devenues redondantes, des variables ajoutées en lot parce que « certaines aident », des variables qui n'améliorent la précision que d'un epsilon. Chacune est une dépendance de plus, qui peut changer, disparaître ou se corrompre, pour un bénéfice négligeable. La recommandation de l'article est d'évaluer régulièrement l'apport de chaque variable, en la retirant pour mesurer la perte, et de supprimer celles qui ne paient pas leur coût de maintenance.

## 6. Le décalage entre l'entraînement et le service

Martin Zinkevich, dans ses « règles du machine learning » rédigées à partir de l'expérience de Google, désigne par *training-serving skew* l'écart entre les performances d'un modèle à l'entraînement et en production [^zinkevich]. L'une de ses causes les plus fréquentes est d'une banalité désarmante : le prétraitement des données n'est pas **le même** dans les deux chemins, parce qu'il a été écrit deux fois, une fois dans le notebook, une fois dans l'API.

<Figure src="skew-entrainement-service" num="27.3" alt="En haut, le chemin d'entraînement met le titre en minuscules avant de le découper en mots, et le modèle reconnaît la catégorie courses avec une probabilité de 0,93. En bas, l'API a oublié l'étape des minuscules : les mots Acheter et LAIT sont inconnus du modèle, qui répond travail avec une probabilité de 0,41.">
  Le décalage entre l'entraînement et le service, sur un exemple de Listify. Une seule étape de prétraitement oubliée suffit à rendre le modèle presque aveugle, sans la moindre erreur.
</Figure>

:::exemple[Combien de mots le modèle reconnaît-il encore ?]
Le vocabulaire du modèle a été appris sur des titres mis en minuscules. En production, l'API transmet les titres tels que saisis. Sur un échantillon de titres réels, on mesure que 38 % des mots contiennent au moins une majuscule (le premier mot du titre, les sigles, les noms propres). Ces mots-là sont **inconnus** du modèle : pour lui, `Acheter` et `acheter` sont deux chaînes différentes.

- Pour « Acheter du LAIT », deux mots sur trois sont inconnus ; il ne reste que « du », un mot vide qui ne porte aucune information. Le modèle retombe sur ses probabilités **a priori** et répond « travail », la catégorie la plus fréquente, avec une confiance de 0,41.
- En moyenne, le modèle perd 38 % de ses mots, et presque toujours **le premier**, souvent le verbe qui porte l'essentiel du sens (« acheter », « appeler », « payer »).

La précision mesurée dans le notebook (94 %) ne dit rien de la précision en production : elle a été mesurée sur des données prétraitées d'une manière que la production n'applique pas. Le remède n'est pas « faire attention » : c'est de **partager le même code** de prétraitement entre l'entraînement et le service, idéalement en l'embarquant **dans** l'objet modèle (un pipeline scikit-learn, le format de modèle de MLflow au chapitre 31), pour qu'il soit impossible de l'oublier.
:::

[^zinkevich]: Martin Zinkevich, *Rules of Machine Learning: Best Practices for ML Engineering*, Google, 2016 (règles n° 29 à 37 sur le *training-serving skew*). [developers.google.com/machine-learning/guides/rules-of-ml](https://developers.google.com/machine-learning/guides/rules-of-ml).

## 7. Les boucles de rétroaction

Un système classique ne modifie pas ses propres entrées. Un modèle en production, si : ses prédictions influencent le comportement des utilisateurs, qui produit les données du prochain entraînement.

- Une boucle **directe** : le modèle choisit lui-même, en partie, les données sur lesquelles il sera réentraîné (un système de recommandation n'observe les clics que sur ce qu'il a déjà recommandé).
- Une boucle **cachée** : deux systèmes s'influencent par le monde réel, sans lien visible dans le code.

<Figure src="boucle-cachee" num="27.4" alt="Le modèle prédit une catégorie, affichée comme suggestion ; l'utilisateur l'accepte souvent sans la relire ; la suggestion acceptée devient l'étiquette des données d'entraînement de la version suivante, qui est réentraînée.">
  Une boucle de rétroaction dans Listify. Quand les suggestions acceptées deviennent des étiquettes, le modèle apprend peu à peu ses propres prédictions.
</Figure>

:::exemple[Une erreur qui se renforce d'elle-même]
Le modèle de Listify classe à tort en « travail » 5 % des tâches qui relèvent en réalité de « maison ». Les utilisateurs acceptent la suggestion **sans la corriger** dans 70 % des cas. Chaque mois, on réentraîne sur les catégories enregistrées, qui incluent ces suggestions acceptées.

Modélisons simplement. Notons $p_n$ la part des tâches « maison » classées « travail » par la version $n$ du modèle. Le mois suivant, une fraction $0{,}7\,p_n$ de ces tâches arrive dans les données avec la mauvaise étiquette ; le modèle réentraîné reproduit ces étiquettes, et ajoute sa propre erreur intrinsèque de 5 %. D'où la relation :

$$
p_{n+1} = 0{,}05 + 0{,}7\,p_n, \qquad p_0 = 0{,}05.
$$

On calcule : $p_1 = 0{,}085$, $p_2 = 0{,}110$, $p_3 = 0{,}127$, puis la suite converge vers le point fixe

$$
p^{*} = \frac{0{,}05}{1 - 0{,}7} \approx 0{,}167.
$$

Sans que personne ne modifie une ligne de code ni un hyperparamètre, l'erreur du modèle sur cette catégorie a été **multipliée par plus de trois**. Plus les utilisateurs font confiance aux suggestions (plus le coefficient 0,7 approche de 1), plus le point fixe est élevé : à 0,9, il atteint 50 %. Le modèle simplifie beaucoup la réalité, mais le mécanisme est exact, et c'est lui qu'on redoute dans les systèmes de recommandation et de modération.

Les remèdes sont connus : ne réentraîner que sur les étiquettes **explicitement confirmées** par un humain, garder une petite part de tâches pour lesquelles on n'affiche aucune suggestion (un groupe témoin), et surveiller la distribution des catégories prédites dans le temps.
:::

## 8. Les anti-motifs du système

Sculley et al. décrivent enfin des défauts d'architecture qui ne sont pas propres au ML, mais qu'il rend presque inévitables quand on passe trop vite du prototype à la production.

**Le code de glue.** On écrit des quantités de code pour faire entrer les données dans une bibliothèque de ML générale et en extraire les résultats. Ce code, fragile et spécifique, finit par figer le choix de la bibliothèque. Remède : envelopper les bibliothèques derrière des interfaces propres au projet.

**Les jungles de pipelines.** La préparation des données grandit par ajouts successifs (une jointure ici, un filtre là, un fichier intermédiaire ailleurs), jusqu'à devenir un enchevêtrement de scripts que personne ne sait plus exécuter dans l'ordre ni tester. C'est très exactement ce que vous vivrez au TP 22, et ce qu'Airflow permettra de reprendre en main au bloc 2.

**Les chemins de code expérimentaux morts.** Chaque expérience laisse une branche conditionnelle (« si `use_new_features` alors ... ») qui n'est jamais retirée. Les combinaisons non testées se multiplient ; l'article cite un incident de Knight Capital en 2012, où du code expérimental resté dormant, réactivé par erreur, a provoqué une perte de 465 millions de dollars en 45 minutes [^sculley2015].

**La dette de configuration.** Un système de ML a souvent plus de lignes de configuration que de code : quelles variables, quelles données, quels seuils, quels hyperparamètres, pour quelle version. Cette configuration est rarement revue ou testée comme du code, alors qu'une erreur y est tout aussi grave. C'est l'argument qui fera versionner la configuration de l'entraînement avec le code, au chapitre 28.

:::exemple[Un seuil qui ne veut plus rien dire]
Listify n'affiche la catégorie suggérée que si le modèle est confiant : probabilité supérieure au seuil de 0,70, choisi à la main lors du premier déploiement. Avec la première version du modèle, 60 % des tâches dépassaient ce seuil. On réentraîne le modèle sur des données plus récentes et plus variées ; il est globalement **meilleur**, mais ses probabilités sont plus prudentes. Avec le même seuil, seules 25 % des tâches reçoivent désormais une suggestion.

Le code n'a pas changé, le seuil non plus, et pourtant la fonctionnalité a été divisée par plus de deux. Un seuil fixe dans un système qui évolue est une configuration dont la **signification** change à chaque réentraînement. Il faut soit le recalculer automatiquement à chaque version (par exemple pour garder une précision cible sur les données de validation), soit surveiller la part des tâches qui le dépassent.
:::

## 9. Le monde change : surveiller ce qui ne lève pas d'erreur

La dernière famille de dette tient à ce que le monde extérieur change, et que le modèle, lui, reste figé sur les données de son entraînement. Les titres de tâches saisis à la rentrée scolaire (« inscription à la cantine », « acheter des cahiers ») ne ressemblent pas à ceux saisis avant les vacances (« réserver le camping ») ; un modèle entraîné sur l'une de ces périodes se trompe davantage sur l'autre. Ce phénomène, la **dérive** des données et des concepts, sera l'objet du chapitre 35. Retenons-en ici le coût, quand on ne le surveille pas.

:::exemple[Le prix d'une dégradation silencieuse]
Le service de catégorisation reçoit 10 000 demandes par jour. Sa précision passe, de façon à peu près linéaire, de 94 % au déploiement à 80 % au bout de 90 jours, sans qu'aucune alerte ne se déclenche.

Au jour 90, il commet $10\,000 \times (0{,}94 - 0{,}80) = 1\,400$ erreurs de plus par jour qu'au premier jour. La dégradation étant linéaire, le surplus d'erreurs croît de 0 à 1 400 et vaut en moyenne 700 par jour sur la période. Sur 90 jours :

$$
700 \times 90 = 63\,000 \text{ suggestions fausses de plus que prévu.}
$$

Si chaque erreur coûte à l'utilisateur quelques secondes de correction, et surtout un peu de confiance dans la fonctionnalité, le coût est réel. Une surveillance de la **qualité** des prédictions, qui aurait comparé chaque semaine les catégories suggérées aux catégories finalement retenues, aurait détecté la pente dès les premières semaines.
:::

Pour surveiller un modèle, Sculley et al. recommandent en particulier trois signaux, que vous mettrez en place au bloc 3 :

- le **biais de prédiction** : la distribution des catégories prédites doit rester proche de celle des catégories réelles ; un écart signale un problème, même si l'on ne sait pas encore lequel ;
- des **limites d'action** : un système qui agit automatiquement (appliquer la catégorie sans demander) doit être plafonné, pour qu'un modèle fou ne puisse pas tout reclasser ;
- la surveillance des **producteurs en amont** : les données d'entrée doivent être contrôlées à leur source, comme dans l'exemple des minutes devenues secondes.

## 10. Ce que le semestre met en place, famille par famille

Chaque famille de dette appelle une pratique et un outil. Le tableau suivant est la feuille de route du semestre.

| Dette | Symptôme | Réponse du semestre | Où |
|---|---|---|---|
| Irreproductibilité | « Je n'arrive plus à retrouver le modèle qu'on a déployé » | Versionner données, code et modèle ; graines aléatoires ; environnement figé | Ch. 28, TP 22 et 23 (DVC) |
| Jungle de pipelines | Scripts enchaînés à la main, dans un ordre connu d'une seule personne | Orchestration par DAG, tâches idempotentes | Ch. 32 (Airflow) |
| Expériences perdues | « Quels paramètres avaient donné 94 % ? » | Suivi des expériences, registre de modèles | Ch. 31 (MLflow) |
| Décalage entraînement-service | Précision en production inférieure au notebook | Prétraitement embarqué dans le modèle, format de modèle unique | Ch. 31 et 33 |
| Dépendances de données instables | Entrées modifiées en amont sans prévenir | Validation automatique des données | Ch. 32 (Great Expectations) |
| Dérive et boucles de rétroaction | Dégradation silencieuse | Surveillance des distributions et de la qualité | Ch. 35 (Evidently, Grafana) |
| Configuration non maîtrisée | Seuils et paramètres modifiés à la main | Configuration versionnée, promotion automatique conditionnée | Ch. 28, 29 et 31 |

On retrouve, appliqués aux données et aux modèles, les grands principes des semestres précédents : l'**immuabilité** et la **reproductibilité** du semestre 1, l'**état désiré** et la **réconciliation** du semestre 2, l'**observabilité** du bloc précédent. Le ML n'invente pas une nouvelle ingénierie ; il oblige à appliquer l'ingénierie existante à un objet de plus, les données, qui est de loin le plus difficile à maîtriser.

## Ce qu'il faut retenir

<div className="retenir">

1. En ML, le comportement du système est **appris à partir des données** : les données font partie du programme, sans en avoir les garde-fous (versionnement, revue, tests).
2. Un modèle **se dégrade sans qu'on y touche**, parce que le monde change, et sa panne est **silencieuse** : réponses plausibles mais fausses, aucun code d'erreur.
3. D'après **Sculley et al. (2015)**, le code d'apprentissage représente au plus 5 % d'un système de ML mature ; la dette s'accumule dans les 95 % restants, au niveau du système.
4. **Érosion des frontières** : principe **CACE** (changer une variable change tous les poids), cascades de corrections, consommateurs non déclarés.
5. Les **dépendances de données** sont plus dangereuses que les dépendances de code : instables (changement d'unité en amont), sous-utilisées (variables qui ne paient pas leur maintenance).
6. Le **décalage entre entraînement et service** vient souvent d'un prétraitement écrit deux fois ; le remède est de l'embarquer dans le modèle.
7. Les **boucles de rétroaction** font apprendre au modèle ses propres prédictions ; dans le modèle simple $p_{n+1} = e + a\,p_n$, l'erreur converge vers $e / (1 - a)$.
8. Anti-motifs : **code de glue**, **jungles de pipelines**, **chemins expérimentaux morts**, **dette de configuration**, **seuils fixes** dont le sens change à chaque réentraînement.

</div>

## Regard recherche

:::recherche
La mise en production du ML est devenue un champ de recherche à part entière, à la croisée du génie logiciel et de l'apprentissage automatique :

- **D. Sculley et al., « Hidden Technical Debt in Machine Learning Systems », NeurIPS, 2015.** L'article fondateur de ce chapitre, et le sujet de la fiche de lecture critique du semestre. Neuf pages, sans une équation : lisez-le en entier.
- **Eric Breck, Shanqing Cai, Eric Nielsen, Michael Salib, D. Sculley, « The ML Test Score: A Rubric for ML Production Readiness and Technical Debt Reduction », IEEE Big Data, 2017.** La suite pratique du précédent : 28 tests concrets (sur les données, le modèle, l'infrastructure, la surveillance) pour évaluer la maturité d'un système de ML. Vous vous en servirez pour noter votre projet final.
- **Saleema Amershi et al., « Software Engineering for Machine Learning: A Case Study », ICSE-SEIP, 2019.** Une étude menée auprès des équipes de Microsoft : en quoi le développement de ML diffère du développement logiciel, d'après ceux qui le pratiquent.
- **Andrei Paleyes, Raoul-Gabriel Urma, Neil D. Lawrence, « Challenges in Deploying Machine Learning: a Survey of Case Studies », *ACM Computing Surveys*, 2022.** Une synthèse des difficultés rapportées dans des dizaines de déploiements réels, organisée selon les étapes du cycle de vie.
- **Neoklis Polyzotis, Sudip Roy, Steven Euijong Whang, Martin Zinkevich, « Data Lifecycle Challenges in Production Machine Learning: A Survey », *SIGMOD Record*, 2018.** Le point de vue des données : validation, nettoyage, gestion des versions.

Piste d'innovation : **mesurer** la dette technique du ML reste un problème ouvert. On sait détecter automatiquement du code dupliqué ou des dépendances inutilisées ; on sait beaucoup moins bien détecter une variable sous-utilisée, un consommateur non déclaré ou une boucle de rétroaction cachée.
:::

## Bibliographie du chapitre

<div className="biblio">

### Sources primaires

- D. Sculley et al., « Hidden Technical Debt in Machine Learning Systems », NeurIPS, 2015.
- D. Sculley et al., « Machine Learning: The High-Interest Credit Card of Technical Debt », atelier SE4ML de NeurIPS, 2014.
- Martin Zinkevich, *Rules of Machine Learning: Best Practices for ML Engineering*, Google, 2016. En ligne et gratuit.

### Lectures recommandées

- Chip Huyen, *Designing Machine Learning Systems*, O'Reilly, 2022, chapitres 1 (« Overview of Machine Learning Systems ») et 8 (« Data Distribution Shifts and Monitoring »). Le livre de référence du semestre.
- Valliappa Lakshmanan, Sara Robinson, Michael Munn, *Machine Learning Design Patterns*, O'Reilly, 2020 : des solutions nommées aux problèmes de ce chapitre (par exemple *Transform* pour le décalage entre entraînement et service).
- Andrej Karpathy, « Software 2.0 », 2017. Court et stimulant.

### Pour aller plus loin

- Les articles de la rubrique « Regard recherche ».
- Eric Breck et al., « Data Validation for Machine Learning », *MLSys*, 2019 : comment Google valide automatiquement les données d'entraînement, le prolongement des sections 5 et 6.

</div>
