---
title: "Ch. 29 : Le cycle de vie MLOps et ses niveaux de maturité"
sidebar_label: "Ch. 29 : Le cycle de vie MLOps"
hide_title: true
---

import ChapterHead from '@site/src/components/ChapterHead';
import Figure from '@site/src/components/Figure';

<ChapterHead
  kicker="Semestre 3 · Bloc 1 · Chapitre 29"
  title="Le cycle de vie MLOps et ses niveaux de maturité"
  lecture="45 min"
  competences={['C1', 'C2']}
/>

:::objectifs
À l'issue de ce chapitre, vous saurez :

- définir le MLOps et décrire le cycle de vie d'un modèle, avec ses deux boucles (expérimentation et production) ;
- expliquer ce que deviennent l'intégration, la livraison et le déploiement continus en ML, et ce qu'ajoute l'entraînement continu ;
- décrire les trois niveaux de maturité MLOps de Google et situer une équipe sur cette échelle ;
- choisir un déclencheur de réentraînement et calculer un intervalle de réentraînement optimal ;
- décider, avec un test statistique simple, si un modèle candidat mérite de remplacer celui en production ;
- relier chaque TP du semestre au niveau de maturité qu'il fait atteindre.
:::

## 1. Un modèle n'est pas un livrable, c'est un processus

Au semestre 2, un livrable était une **image** : on la construisait, la testait, la déployait, et elle se comportait de la même façon jusqu'à la version suivante. Le chapitre 27 a montré qu'un modèle, lui, **vieillit** même quand personne n'y touche, parce que le monde qu'il décrit change. Le chapitre 28 a montré qu'on ne pouvait le refaire que si l'on avait figé ses cinq entrées.

Ces deux constats changent la nature de ce qu'on met en production. Déployer **un** modèle ne suffit pas : il faudra le **remplacer**, régulièrement, par un modèle entraîné sur des données plus récentes, et vérifier à chaque fois que le remplaçant est meilleur. Ce qu'on doit mettre en production, c'est donc le **processus** qui produit, valide et remplace les modèles. La discipline qui organise ce processus s'appelle le **MLOps**.

:::definition[MLOps]
Ensemble de pratiques, d'outils et d'organisation qui vise à mettre en production et à maintenir des modèles d'apprentissage automatique de façon fiable et efficace, en appliquant au cycle de vie complet des modèles (données, entraînement, évaluation, déploiement, surveillance, réentraînement) les principes de l'intégration et de la livraison continues [^kreuzberger].
:::

Le terme combine *machine learning* et *operations*, sur le modèle de DevOps. Il n'introduit pas une ingénierie nouvelle : il étend le DevOps des semestres 1 et 2 à deux objets qu'il ne savait pas gérer, **les données** et **les modèles**.

[^kreuzberger]: D'après Dominik Kreuzberger, Niklas Kühl, Sebastian Hirschl, « Machine Learning Operations (MLOps): Overview, Definition, and Architecture », *IEEE Access*, vol. 11, 2023, qui propose une définition synthétique à partir d'une revue de la littérature et d'entretiens avec des praticiens.

## 2. Le cycle de vie d'un modèle

### 2.1 Deux boucles

Le cycle de vie d'un modèle se compose de deux boucles, qui ne tournent ni au même rythme ni avec les mêmes acteurs.

<Figure src="cycle-mlops" num="29.1" alt="À gauche, la boucle d'expérimentation : données, validation des données, préparation, entraînement, évaluation contre le champion, et retour aux données pour une nouvelle idée. À droite, la boucle de production : promotion au registre, service des prédictions, surveillance, déclencheur ; le déclencheur relance l'entraînement à partir de la préparation.">
  Le cycle de vie d'un modèle. La boucle d'expérimentation cherche un meilleur modèle ; la boucle de production le sert, le surveille et déclenche son remplacement. Le passage de l'une à l'autre, la promotion, est la décision critique.
</Figure>

La **boucle d'expérimentation**, à gauche, est celle de la data scientist : collecter un instantané des données, le valider, préparer les variables, entraîner, évaluer. Elle tourne vite, avec beaucoup d'essais ratés, et chaque « nouvelle idée » (une variable, un algorithme, un paramètre) relance un tour.

La **boucle de production**, à droite, est celle de l'exploitation : un modèle **promu** au registre de modèles est servi, ses prédictions sont surveillées, et un **déclencheur** (une dérive détectée, une date, l'arrivée de nouvelles données) relance l'entraînement. Cette boucle doit tourner sans intervention humaine pour chaque tour, ce qui suppose que la boucle d'expérimentation ait été transformée en **pipeline** automatique.

La flèche centrale, « meilleur ? », est la plus importante : c'est la **promotion**, la décision de remplacer le modèle en production (le **champion**) par un nouveau modèle (le **challenger**). La section 6 montre comment la prendre avec rigueur.

### 2.2 Des étapes connues depuis longtemps

Le découpage en étapes n'est pas propre au MLOps. Dès 2000, la méthode **CRISP-DM**, issue d'un consortium industriel, décrivait la fouille de données en six phases cycliques : compréhension du métier, compréhension des données, préparation, modélisation, évaluation, déploiement [^crisp]. En 2019, une étude menée chez Microsoft décrivait le flux de travail des équipes de ML en neuf étapes, de l'expression du besoin à la surveillance du modèle, en insistant sur les **retours en arrière** entre étapes [^amershi]. Ce qui change avec le MLOps n'est pas la liste des étapes, mais l'exigence de les **automatiser** et de les **enchaîner en boucle** en production.

[^crisp]: Pete Chapman et al., *CRISP-DM 1.0: Step-by-step data mining guide*, consortium CRISP-DM (NCR, SPSS, DaimlerChrysler, OHRA), 2000.

[^amershi]: Saleema Amershi et al., « Software Engineering for Machine Learning: A Case Study », *ICSE-SEIP*, 2019.

## 3. Ce que « continu » veut dire en ML

Le semestre 2 a défini l'intégration continue (ch. 23), la livraison continue et le déploiement continu (ch. 24). En ML, ces trois pratiques changent de contenu, et une quatrième apparaît [^google-mlops].

| Pratique | Logiciel classique (S2) | Système de ML |
|---|---|---|
| **Intégration continue** (CI) | Tester le code : lint, tests unitaires et d'intégration | Tester le code, **et** valider les données (schéma, valeurs) **et** les modèles (qualité minimale) |
| **Livraison continue** (CD) | Livrer une image de l'application | Livrer **un pipeline d'entraînement**, qui produira lui-même des modèles, et le service qui les expose |
| **Déploiement continu** | Mettre en production chaque version qui passe les tests | Mettre en production chaque **modèle** qui passe la validation, automatiquement |
| **Entraînement continu** (CT) | N'existe pas | **Réentraîner automatiquement** le modèle quand un déclencheur le demande, puis le valider et le servir |

La deuxième ligne est la plus déroutante, et la plus importante : en ML mature, on ne livre plus un modèle mais **la machine à fabriquer des modèles**. Le modèle devient une sortie du pipeline, produite en production, sur les données de production. La quatrième ligne, l'**entraînement continu**, est la propriété que Google présente comme propre aux systèmes de ML [^google-mlops].

[^google-mlops]: Google Cloud, « MLOps: Continuous delivery and automation pipelines in machine learning », *Cloud Architecture Center*, publié en 2020 et mis à jour depuis. [cloud.google.com/architecture/mlops-continuous-delivery-and-automation-pipelines-in-machine-learning](https://cloud.google.com/architecture/mlops-continuous-delivery-and-automation-pipelines-in-machine-learning).

## 4. Les trois niveaux de maturité selon Google

Le document de Google cité ci-dessus propose une échelle en trois niveaux, devenue la référence du domaine [^google-mlops]. Elle permet de situer une équipe, et surtout de savoir **quoi** automatiser ensuite.

<Figure src="maturite-mlops" num="29.2" alt="Niveau 0 : un notebook exécuté à la main produit un fichier modèle, transmis puis déployé dans un service ; on livre un modèle quelques fois par an. Niveau 1 : le code du pipeline, dans Git, est déployé ; le pipeline d'entraînement produit un modèle validé servi en production, et un déclencheur le relance. Niveau 2 : une chaîne CI/CD teste, construit et déploie le pipeline lui-même à chaque commit.">
  Les trois niveaux de maturité MLOps, d'après Google. Au niveau 0 on livre un modèle ; au niveau 1, un pipeline qui réentraîne ; au niveau 2, le pipeline lui-même est testé et livré automatiquement.
</Figure>

### 4.1 Niveau 0 : le processus manuel

C'est le point de départ de la plupart des équipes, et celui de Listify au chapitre 27. Google le caractérise par sept traits :

- chaque étape est **manuelle**, exécutée par des scripts ou dans des notebooks interactifs ;
- la data scientist et l'équipe d'exploitation sont **séparées** : la première transmet un fichier de modèle, la seconde le déploie ;
- les nouvelles versions sont **rares**, quelques fois par an ;
- il n'y a **pas d'intégration continue** : les notebooks ne sont pas testés ;
- il n'y a **pas de livraison continue** : le déploiement est un événement ;
- ce qu'on déploie, c'est **le service de prédiction** avec un modèle dedans, pas le processus qui l'a produit ;
- il n'y a **pas de surveillance active** de la qualité des prédictions.

:::exemple[Ce que coûte une mise à jour au niveau 0]
Chaque fois que l'équipe de Listify veut mettre à jour le modèle de catégorisation, une personne, la seule qui connaisse la procédure, doit :

| Étape | Durée |
|---|---|
| Exporter les tâches depuis la base, nettoyer à la main les lignes aberrantes | 30 min |
| Relancer le notebook, corriger les chemins qui ont changé | 45 min |
| Évaluer, comparer à l'ancien modèle « de mémoire » | 15 min |
| Copier le fichier modèle dans le dépôt de l'API, ouvrir une demande de fusion | 30 min |
| Suivre le déploiement, vérifier quelques prédictions à la main | 20 min |
| **Total** | **2 h 20** |

À ces 2 h 20 s'ajoute un risque à chaque étape (un nettoyage oublié, un prétraitement différent, un modèle moins bon mais pas vérifié), et une dépendance totale à une personne. Le résultat est prévisible : on ne met à jour le modèle que tous les trois mois, et le modèle vieillit entre deux mises à jour. C'est exactement le phénomène de l'intégration tardive du chapitre 23, appliqué aux modèles.
:::

### 4.2 Niveau 1 : l'automatisation du pipeline

Le niveau 1 automatise la boucle d'expérimentation pour en faire un **pipeline** exécutable sans humain. Ses traits distinctifs, toujours d'après Google :

- **l'entraînement continu** : le modèle est réentraîné en production, automatiquement, sur des données fraîches ;
- **la symétrie entre expérimentation et production** : le même pipeline tourne en développement et en production, ce qui supprime le décalage entre entraînement et service du chapitre 27 ;
- **un code modulaire** : chaque étape (validation, préparation, entraînement, évaluation) est un composant séparé, réutilisable, idéalement conteneurisé ;
- **la livraison continue des modèles** : chaque modèle produit par le pipeline et validé est servi sans intervention ;
- **on déploie le pipeline**, pas seulement le modèle.

Ce niveau exige des briques supplémentaires : la **validation automatique des données et des modèles** (sans elle, un pipeline automatique mettrait en production n'importe quoi), un **magasin de métadonnées** qui enregistre le lignage de chaque exécution (ch. 28, §8), un **registre de modèles**, et des **déclencheurs** (section 5).

### 4.3 Niveau 2 : la CI/CD du pipeline

Au niveau 1, le pipeline lui-même reste modifié et redéployé à la main : quand la data scientist a une nouvelle idée (une variable, un algorithme), quelqu'un doit mettre à jour le pipeline de production. Le niveau 2 applique à **ce code-là** la CI/CD du semestre 2 : chaque modification du pipeline est testée (tests unitaires des composants, test d'intégration du pipeline sur un petit jeu de données), construite en images, et déployée automatiquement. Le niveau 2 comporte ainsi six étapes enchaînées : développement et expérimentation, intégration continue du pipeline, livraison continue du pipeline, déclenchement automatique, livraison continue du modèle, surveillance.

Le niveau 2 est celui des équipes qui gèrent des dizaines de modèles et les font évoluer chaque semaine. Pour un modèle unique comme celui de Listify, il est l'aboutissement du semestre, pas un prérequis.

### 4.4 D'autres échelles

L'échelle de Google n'est pas la seule. Microsoft propose un modèle de maturité en cinq niveaux, numérotés de 0 à 4 : aucune pratique MLOps, DevOps sans MLOps, entraînement automatisé, déploiement automatisé des modèles, et opérations entièrement automatisées [^microsoft]. Les deux échelles décrivent la même progression, avec un découpage plus fin chez Microsoft entre l'automatisation de l'entraînement et celle du déploiement. Retenez l'idée commune plutôt que les numéros : on automatise d'abord ce qui est **répété** et **risqué**, dans l'ordre où la douleur apparaît.

[^microsoft]: Microsoft, « Machine Learning operations maturity model », *Azure Architecture Center*. [learn.microsoft.com/azure/architecture/ai-ml/guide/mlops-maturity-model](https://learn.microsoft.com/azure/architecture/ai-ml/guide/mlops-maturity-model).

## 5. Quand réentraîner ?

### 5.1 Les déclencheurs

Un pipeline de niveau 1 se déclenche sur un événement. Google en énumère cinq [^google-mlops] :

| Déclencheur | Principe | Avantage | Limite |
|---|---|---|---|
| **À la demande** | Un humain lance le pipeline | Contrôle total | Retombe dans le manuel si c'est le seul |
| **Calendrier** | Chaque jour, chaque semaine | Simple, prévisible, facile à planifier | Réentraîne même si rien n'a changé, ou trop tard si tout a changé |
| **Nouvelles données** | Dès qu'un volume suffisant de données étiquetées est disponible | Suit le rythme réel des données | Nécessite de savoir compter les nouvelles étiquettes |
| **Dégradation de la performance** | Quand la qualité mesurée passe sous un seuil | Réentraîne quand c'est utile | Suppose d'avoir les étiquettes réelles, souvent avec retard |
| **Changement de distribution** | Quand une dérive des données d'entrée est détectée | Réagit avant de connaître les étiquettes | Une dérive n'implique pas toujours une baisse de qualité |

En pratique, on combine un calendrier (le filet de sécurité) et un déclencheur sur dérive ou sur performance (la réactivité). Les deux derniers seront mis en œuvre au chapitre 35 ; au bloc 2, Airflow fournira le calendrier.

### 5.2 Un intervalle optimal

Réentraîner souvent coûte cher (calcul, vérification humaine, risque de chaque mise en production) ; réentraîner rarement laisse le modèle se dégrader. Il existe donc un intervalle optimal, qu'un modèle simple permet de calculer.

:::exemple[Tous les combien réentraîner le modèle de Listify ?]
Hypothèses, tirées des mesures de la production :

- le service reçoit $N = 10\,000$ demandes par jour ;
- après chaque réentraînement, la précision baisse d'environ 1,5 point par mois, soit $r = 0{,}0005$ par jour (0,05 point) ;
- chaque suggestion fausse coûte $c = 0{,}02$ € (temps de correction, perte de confiance, estimation de l'équipe produit) ;
- chaque réentraînement coûte $C = 30$ € : le calcul, et surtout l'heure de vérification humaine avant la mise en production.

Si l'on réentraîne tous les $T$ jours, la précision perdue croît linéairement de 0 à $rT$ pendant l'intervalle, soit $rT/2$ en moyenne. Le coût quotidien vaut donc :

$$
\text{coût}(T) = \underbrace{c \cdot N \cdot \frac{r\,T}{2}}_{\text{erreurs en plus}} + \underbrace{\frac{C}{T}}_{\text{réentraînements}} = 0{,}05\,T + \frac{30}{T}.
$$

Le premier terme croît avec $T$, le second décroît : c'est le compromis classique du réapprovisionnement en recherche opérationnelle. En annulant la dérivée, $0{,}05 - 30/T^2 = 0$, on obtient :

$$
T^{*} = \sqrt{\frac{2C}{c\,N\,r}} = \sqrt{\frac{30}{0{,}05}} = \sqrt{600} \approx 24{,}5 \text{ jours},
$$

pour un coût minimal de

$$
\text{coût}(T^{*}) = 2\sqrt{0{,}05 \times 30} \approx 2{,}45 \text{ € par jour.}
$$

À titre de comparaison, réentraîner chaque semaine coûte $0{,}05 \times 7 + 30/7 \approx 4{,}64$ € par jour, et tous les trois mois $0{,}05 \times 90 + 30/90 \approx 4{,}83$ € par jour, près de deux fois plus que l'optimum dans les deux cas.
:::

<Figure src="cout-reentrainement" num="29.3" alt="Courbes du coût quotidien en fonction de l'intervalle de réentraînement T : le coût des réentraînements, 30/T, décroît ; le coût des erreurs supplémentaires, 0,05 T, croît ; leur somme est minimale vers T égal à 24,5 jours, pour 2,45 euros par jour.">
  Le coût quotidien en fonction de l'intervalle de réentraînement, pour les hypothèses de l'exemple. Le minimum est plat : entre 15 et 40 jours, le coût reste proche de l'optimum.
</Figure>

La formule dit surtout **comment** l'optimum bouge, et c'est l'argument central du niveau 1. Le coût $C$ d'un réentraînement est dominé par le travail humain de vérification. Si l'on automatise cette vérification (validation des données et du modèle, promotion conditionnelle), $C$ tombe par exemple de 30 € à 3 €. Alors :

$$
T^{*} = \sqrt{\frac{3}{0{,}05}} \approx 7{,}7 \text{ jours}, \qquad \text{coût}(T^{*}) = 2\sqrt{0{,}05 \times 3} \approx 0{,}77 \text{ € par jour.}
$$

L'automatisation permet de réentraîner **trois fois plus souvent** pour un coût total **trois fois plus faible**. C'est la même logique que le déploiement continu du chapitre 24 : ce qui est automatisé devient bon marché, donc fréquent, donc moins risqué.

## 6. Promouvoir un modèle : champion et challenger

Un pipeline automatique produit un nouveau modèle, le **challenger**. Faut-il remplacer le modèle en production, le **champion** ? Au niveau 0, on décide « à l'œil ». Au niveau 1, la décision doit être automatique, donc explicite et rigoureuse, sinon le pipeline mettra en production des modèles qui ne sont pas meilleurs, voire pires.

### 6.1 Une différence peut n'être que du bruit

:::exemple[94,1 % contre 93,8 % : faut-il promouvoir ?]
Le champion et le challenger sont évalués sur le **même** jeu de test de $n = 2\,000$ tâches, jamais vu à l'entraînement. Le champion obtient 93,8 %, le challenger 94,1 %. Le challenger a-t-il gagné ?

**Un premier ordre de grandeur.** L'incertitude sur une précision $p$ mesurée sur $n$ exemples est de l'ordre de l'écart-type $\sqrt{p(1-p)/n}$ :

$$
\sqrt{\frac{0{,}94 \times 0{,}06}{2\,000}} \approx 0{,}0053, \text{ soit environ 0,5 point.}
$$

L'écart observé, 0,3 point, soit 6 tâches sur 2 000, est inférieur à cette incertitude. On se souvient aussi (ch. 28, §4.1) que le seul changement de graine faisait varier la précision de plusieurs points.

**Un test adapté : McNemar.** Comme les deux modèles sont évalués sur les mêmes tâches, on ne compare pas deux précisions indépendantes : on regarde les tâches sur lesquelles ils **ne sont pas d'accord**. Supposons que sur 40 tâches, un seul des deux modèles ait raison : le challenger a raison sur $b = 23$ d'entre elles, le champion sur $c = 17$ (d'où l'écart de 6). Le test de McNemar, avec correction de continuité, calcule [^mcnemar] :

$$
\chi^2 = \frac{(|b - c| - 1)^2}{b + c} = \frac{(6 - 1)^2}{40} = 0{,}625.
$$

Sous l'hypothèse que les deux modèles se valent, cette statistique suit une loi du $\chi^2$ à un degré de liberté, dont le seuil à 5 % vaut 3,84. Comme $0{,}625 < 3{,}84$, **on ne peut pas conclure** que le challenger est meilleur. Promouvoir sur cette base, c'est remplacer un modèle par un autre sur un tirage au sort, avec tous les risques d'une mise en production, pour rien.
:::

[^mcnemar]: Quinn McNemar, « Note on the sampling error of the difference between correlated proportions or percentages », *Psychometrika*, vol. 12, n° 2, 1947. Pour son usage en comparaison de classifieurs : Thomas G. Dietterich, « Approximate Statistical Tests for Comparing Supervised Classification Learning Algorithms », *Neural Computation*, vol. 10, n° 7, 1998.

### 6.2 Une règle de promotion complète

Une règle de promotion automatique combine donc plusieurs critères, tous écrits dans la configuration du pipeline et versionnés :

1. **La qualité globale** : le challenger est significativement meilleur que le champion sur le même jeu de test, ou au moins **pas significativement pire** si l'objectif est de rafraîchir un modèle sur des données récentes.
2. **La non-régression par sous-groupe** : aucune catégorie ne perd plus de, par exemple, 2 points. Un modèle meilleur en moyenne peut être bien pire sur « administratif », la catégorie la plus rare ; la moyenne masque ces régressions, et le chapitre 38 montrera qu'elles posent aussi des questions d'équité.
3. **Les contraintes d'exploitation** : la latence de prédiction et la taille du modèle restent sous leurs plafonds.
4. **La validation des données** : le challenger n'a pas été entraîné sur des données qui ont échoué aux contrôles (§4.2).

Si tous les critères passent, le pipeline enregistre le challenger au registre et le promeut ; sinon, il le garde pour analyse et laisse le champion en place. Au niveau 1, cette promotion peut elle-même passer par un déploiement progressif : le challenger reçoit d'abord une petite part du trafic, comme le canary du chapitre 24.

## 7. Qui fait quoi

Le cycle de vie traverse plusieurs métiers, et c'est aux frontières entre eux que naît la dette du niveau 0.

| Rôle | Responsabilité principale | Au niveau 0 | Au niveau 1 et au-delà |
|---|---|---|---|
| Data scientist | Explorer les données, concevoir le modèle | Livre un notebook et un fichier modèle | Écrit des composants de pipeline testés |
| Ingénieur des données | Collecter, nettoyer, valider les données | Fournit des exports ponctuels | Maintient des jeux de données versionnés et validés |
| Ingénieur ML | Industrialiser l'entraînement et le service | Réécrit le notebook dans l'API | Construit et maintient le pipeline et la plateforme |
| Exploitation (SRE) | Faire tourner le service, surveiller | Déploie un fichier qu'il ne comprend pas | Surveille aussi la qualité et la dérive, reçoit des alertes |

La colonne « niveau 0 » montre le motif du « par-dessus le mur » que le DevOps a combattu dans le logiciel classique : chacun transmet son travail au suivant sans en partager la responsabilité. Le MLOps y répond de la même façon que le DevOps : des artefacts communs (le pipeline, le registre, les tableaux de bord) et une responsabilité partagée du modèle en production.

## 8. La progression du semestre

Le semestre fait parcourir cette échelle à Listify, dans l'ordre :

| Étape du semestre | Niveau atteint | Ce qui change |
|---|---|---|
| TP 22 : le notebook irreproductible | 0 | On vit le processus manuel et ses échecs |
| TP 23 : projet reproductible avec DVC | 0, maîtrisé | Le processus reste manuel, mais il est reproductible |
| TP 24 : suivi des expériences et registre (MLflow) | vers 1 | Les expériences sont tracées, les modèles enregistrés et promus |
| TP 25 : servir le modèle depuis le registre | vers 1 | Le service charge le modèle promu ; le prétraitement voyage avec le modèle |
| TP 26 : DAG Airflow avec promotion conditionnelle | 1 | Entraînement continu sur calendrier, validation et promotion automatiques |
| TP 27 : chaîne intégrée | 2 | Le pipeline et le service sont eux-mêmes testés et livrés par la CI/CD du semestre 2 |
| TP 30 : dérive et réentraînement automatique | 2, avec surveillance | Le déclencheur devient la dérive détectée |

:::warning[La maturité n'est pas un objectif en soi]
Une échelle de maturité incite à viser le dernier niveau. C'est une erreur d'ingénierie. Chaque niveau a un coût (outils à installer et à maintenir, compétences, complexité), qui ne se justifie que si le problème qu'il résout se pose réellement. Un modèle réentraîné deux fois par an sur des données stables peut rester, en toute rationalité, à un niveau 0 bien maîtrisé : reproductible, documenté, versionné. Le calcul du §5.2 donne le bon réflexe : chiffrer ce que coûte la situation actuelle, et ce que coûterait l'automatisation.
:::

## Ce qu'il faut retenir

<div className="retenir">

1. En ML, on ne met pas en production un modèle mais le **processus** qui produit, valide et remplace les modèles. Le **MLOps** applique à ce processus les principes du DevOps, étendus aux données et aux modèles.
2. Le cycle de vie a **deux boucles** : l'**expérimentation** (chercher un meilleur modèle) et la **production** (servir, surveiller, déclencher). La **promotion** relie les deux.
3. En ML, la **CI** valide aussi les données et les modèles, la **CD** livre un **pipeline**, et l'**entraînement continu** (CT) réentraîne automatiquement.
4. Google distingue trois niveaux : **0**, processus manuel, on livre un modèle ; **1**, pipeline automatisé et entraînement continu, on livre le pipeline ; **2**, le pipeline lui-même est testé et livré par CI/CD.
5. Cinq **déclencheurs** : à la demande, calendrier, nouvelles données, dégradation de la performance, changement de distribution. On combine un calendrier et un déclencheur réactif.
6. L'intervalle de réentraînement optimal vaut $T^{*} = \sqrt{2C / (c\,N\,r)}$ ; **automatiser** la vérification fait baisser $C$, donc permet de réentraîner plus souvent pour moins cher.
7. Une différence de précision peut n'être que du bruit : sur les mêmes données de test, le **test de McNemar** tranche. Une règle de promotion combine qualité globale, **non-régression par sous-groupe**, contraintes d'exploitation et validation des données.
8. La maturité se choisit selon le coût du problème, pas pour elle-même.

</div>

## Regard recherche

:::recherche
Le MLOps est un domaine jeune, où les articles d'expérience industrielle et les études empiriques auprès des praticiens pèsent autant que les contributions théoriques :

- **Dominik Kreuzberger, Niklas Kühl, Sebastian Hirschl, « Machine Learning Operations (MLOps): Overview, Definition, and Architecture », *IEEE Access*, 2023.** Une revue de la littérature et des outils, complétée d'entretiens, qui propose une définition et une architecture de référence. Le meilleur point d'entrée académique.
- **Shreya Shankar, Rolando Garcia, Joseph M. Hellerstein, Aditya G. Parameswaran, « Operationalizing Machine Learning: An Interview Study », 2022 (prépublication arXiv).** Des entretiens avec des ingénieurs ML de plusieurs entreprises : ce qu'ils font réellement, et les trois exigences qui structurent leur travail (vitesse, validation, versionnement).
- **Denis Baylor et al., « TFX: A TensorFlow-Based Production-Scale Machine Learning Platform », *KDD*, 2017.** La plateforme de Google qui a concrétisé le niveau 1 : validation des données, transformation partagée entre entraînement et service, validation des modèles avant promotion.
- **Stefan Studer et al., « Towards CRISP-ML(Q): A Machine Learning Process Model with Quality Assurance Methodology », *Machine Learning and Knowledge Extraction*, 2021.** Une mise à jour de CRISP-DM qui ajoute une étape de surveillance et de maintenance et des exigences de qualité à chaque phase.
- **Saleema Amershi et al., « Software Engineering for Machine Learning: A Case Study », *ICSE-SEIP*, 2019.** Le flux de travail en neuf étapes observé chez Microsoft.

Piste d'innovation : décider **automatiquement et sûrement** quand réentraîner et quand promouvoir, avec peu d'étiquettes et des données qui dérivent, relève de la décision statistique séquentielle. C'est un problème ouvert, à la frontière entre apprentissage automatique et recherche opérationnelle.
:::

## Bibliographie du chapitre

<div className="biblio">

### Sources primaires

- Google Cloud, « MLOps: Continuous delivery and automation pipelines in machine learning », *Cloud Architecture Center*. La source des niveaux 0, 1 et 2 et des déclencheurs.
- Microsoft, « Machine Learning operations maturity model », *Azure Architecture Center*.
- Pete Chapman et al., *CRISP-DM 1.0: Step-by-step data mining guide*, 2000.

### Lectures recommandées

- Chip Huyen, *Designing Machine Learning Systems*, O'Reilly, 2022, chapitre 9 (« Continual Learning and Test in Production ») : fréquence de mise à jour, évaluation en production.
- Mark Treveil et al., *Introducing MLOps*, O'Reilly, 2020 : une présentation courte et organisationnelle du cycle de vie et des rôles.

### Pour aller plus loin

- Les articles de la rubrique « Regard recherche ».
- Thomas G. Dietterich, « Approximate Statistical Tests for Comparing Supervised Classification Learning Algorithms », *Neural Computation*, 1998 : la référence sur les tests de comparaison de modèles, dont McNemar.

</div>
