---
title: "Ch. 30 : Les modes de mise à disposition d'un modèle"
sidebar_label: "Ch. 30 : Mettre un modèle à disposition"
hide_title: true
---

import ChapterHead from '@site/src/components/ChapterHead';
import Figure from '@site/src/components/Figure';

<ChapterHead
  kicker="Semestre 3 · Bloc 1 · Chapitre 30"
  title="Les modes de mise à disposition d'un modèle"
  lecture="50 min"
  competences={['C1', 'C2']}
/>

:::objectifs
À l'issue de ce chapitre, vous saurez :

- distinguer la prédiction **par lots**, la prédiction **à la demande** et la prédiction **sur un flux**, et dire pour chacune quand la prédiction est calculée et combien de temps elle reste valable ;
- établir un **budget de latence** et raisonner en percentiles plutôt qu'en moyenne ;
- dimensionner un service de prédiction avec la loi de Little et expliquer pourquoi la latence explose quand le taux d'occupation approche 100 % ;
- choisir entre un modèle **embarqué** dans l'application et un modèle exposé comme un **service**, chiffres à l'appui (mémoire, latence, fréquence de déploiement) ;
- expliquer le **regroupement dynamique** des requêtes et le compromis entre latence et débit qu'il réalise ;
- choisir un mode de mise à disposition adapté à chaque besoin de Listify.
:::

## 1. Quand la prédiction est-elle calculée ?

Le chapitre 29 s'est arrêté à la flèche « servir » du cycle de vie : un modèle validé est promu, il faut maintenant que l'application puisse s'en servir. Derrière ce mot se cachent des architectures très différentes, qui ne se distinguent pas par le modèle (le même fichier peut servir dans les trois cas) mais par la réponse à une seule question : **à quel moment la prédiction est-elle calculée, par rapport au moment où l'on en a besoin ?**

Il y a trois réponses possibles.

- **Avant**, pour toutes les entrées d'un coup : c'est la prédiction **par lots**. Une tâche planifiée applique le modèle à un grand ensemble de données, range les résultats dans une table, et l'application lit la table quand elle en a besoin.
- **Au moment même**, pour une entrée à la fois : c'est la prédiction **à la demande**. L'application envoie une entrée, attend, et reçoit la prédiction dans la même interaction.
- **Dès que l'entrée apparaît**, sans que personne ne la demande : c'est la prédiction **sur un flux**. Chaque événement qui arrive sur un bus de messages est traité par le modèle quelques secondes plus tard, et la prédiction déclenche une réaction.

<Figure src="modes-prediction" num="30.1" alt="Trois bandeaux. Par lots : une tâche planifiée chaque nuit envoie toutes les tâches au modèle, qui écrit dans une table de prédictions ; l'application lit la table. À la demande : l'application envoie un titre au service de prédiction, qui répond une catégorie en quelques millisecondes. Sur un flux : des événements passent par un bus d'événements, sont traités par le modèle, qui déclenche une réaction comme une alerte ou une notification.">
Les trois modes de prédiction. Le modèle est le même ; ce qui change, c'est le moment où il est appelé et ce qui l'appelle.
</Figure>

La littérature emploie plusieurs vocabulaires pour les mêmes idées. Chip Huyen parle de *batch prediction* et d'*online prediction*, et distingue au sein de la seconde celle qui n'utilise que des caractéristiques calculées à l'avance de celle qui utilise aussi des caractéristiques calculées sur un flux [^huyen]. On rencontre aussi « hors ligne » et « en ligne », « asynchrone » et « synchrone ». Retenez le critère plutôt que les mots : **quand** la prédiction est calculée, et **qui** en déclenche le calcul.

:::definition[Fraîcheur et latence d'une prédiction]
La **latence** d'une prédiction est le temps qui sépare le moment où l'on en a besoin du moment où l'on dispose du résultat. Sa **fraîcheur** (ou, à l'inverse, son âge) est le temps écoulé depuis que les données qu'elle utilise ont été lues. Une prédiction par lots a une latence quasi nulle (on lit une table) mais peut être vieille de plusieurs heures ; une prédiction à la demande est parfaitement fraîche, mais il faut attendre le calcul.
:::

Tout le chapitre tourne autour de ce compromis : on paie soit en **latence**, soit en **fraîcheur**, soit en **complexité d'infrastructure** pour avoir les deux.

[^huyen]: Chip Huyen, *Designing Machine Learning Systems*, O'Reilly, 2022, chapitre 7, « Model Deployment and Prediction Service », section « Batch Prediction Versus Online Prediction ».

## 2. Deux besoins de Listify pour fixer les idées

Pour ne pas raisonner dans le vide, prenons deux besoins de Listify que le modèle du semestre peut servir.

- **La suggestion de catégorie.** Quand l'utilisateur tape le titre d'une nouvelle tâche, Listify propose une catégorie (travail, courses, maison, administratif, loisirs). L'entrée, le titre, n'existe pas avant que l'utilisateur l'ait tapé.
- **Le récapitulatif du matin.** Chaque jour, Listify affiche en tête de liste les tâches qu'il estime probablement en retard, à partir de leur ancienneté, de leur catégorie et des habitudes de l'utilisateur. L'entrée, l'ensemble des tâches ouvertes, existe déjà la veille au soir.

Ces deux besoins vont nous conduire à deux modes différents, et c'est tout l'enjeu : **le mode se choisit par besoin, pas par modèle ni par entreprise**. Une même application en combine souvent plusieurs.

Les chiffres des exemples qui suivent viennent d'une mesure réelle : un classifieur TF-IDF suivi d'une régression logistique (scikit-learn 1.7.2), entraîné sur 20 000 titres synthétiques, chronométré sur un processeur de portable.

| Appel | Temps mesuré |
|---|---|
| Une prédiction isolée, dans le même processus (médiane) | 0,37 ms |
| Une prédiction isolée, dans le même processus (99ᵉ percentile) | 0,75 ms |
| Un lot de 1 000 prédictions | 5,2 ms, soit 5,2 µs par prédiction |
| Un lot de 100 000 prédictions | 386 ms, soit 3,9 µs par prédiction |

La première et la dernière ligne diffèrent d'un facteur 95 par prédiction. Ce n'est pas un détail : c'est la raison d'être de la prédiction par lots, et du regroupement dynamique du §8.

## 3. La prédiction par lots

### 3.1 Le principe

Une tâche planifiée (au bloc 2, un DAG Airflow) lit toutes les entrées, appelle le modèle sur de gros lots, et écrit les prédictions dans un stockage que l'application sait lire : une table de la base PostgreSQL, un cache clé-valeur, un fichier. Au moment où l'utilisateur ouvre l'application, il n'y a **plus rien à calculer**.

C'est le mode historique, et il reste le plus simple : pas de service à maintenir en vie, pas de latence à surveiller, un échec se rattrape en relançant la tâche. On retrouve exactement les tâches idempotentes et le rattrapage (*backfill*) que le chapitre 32 présentera.

:::exemple[Exemple 30.1 : le récapitulatif du matin, calculé chaque nuit]
Listify compte 50 000 utilisateurs et 200 000 tâches ouvertes. Chaque nuit à 3 h, une tâche planifiée calcule pour chacune la probabilité d'être en retard.

**Temps de calcul du modèle.** Au rythme mesuré de 3,9 µs par prédiction sur un lot :

$$
200\,000 \times 3{,}9\ \mu\text{s} = 0{,}78\ \text{s}.
$$

Moins d'une seconde. En pratique, la tâche est dominée par la lecture des tâches dans la base et l'écriture des résultats, pas par le modèle.

**Le même calcul, prédiction par prédiction.** Si l'on appelait le modèle une tâche à la fois, au rythme de 0,37 ms :

$$
200\,000 \times 0{,}37\ \text{ms} = 74\ \text{s}.
$$

Toujours supportable pour une tâche de nuit, mais 95 fois plus lent. Avec un modèle cent fois plus lourd, l'écart séparerait une tâche de 1 min 18 s d'une tâche de deux heures.

**Âge des prédictions.** Le récapitulatif affiché à 8 h utilise des données lues à 3 h : il a 5 heures. Affiché à 22 h, il en a 19. Sur une journée d'utilisation uniforme, l'âge moyen est de 12 heures, et l'âge maximal de 24 heures. Pour un récapitulatif quotidien, c'est parfaitement acceptable : c'est le besoin qui définit la fraîcheur tolérable.
:::

### 3.2 Ce que la prédiction par lots ne sait pas faire

Deux limites structurelles en découlent.

**Elle ne connaît que les entrées qui existent au moment du calcul.** La suggestion de catégorie porte sur un titre qui n'existe pas encore ; aucune tâche de nuit ne peut la précalculer. Plus généralement, la prédiction par lots exige un **espace d'entrées fini et connu à l'avance** : les utilisateurs, les produits d'un catalogue, les tâches ouvertes. Dès que l'entrée est libre (un texte saisi, une image envoyée, une transaction en cours), elle ne s'applique plus, sauf astuce (§6.3).

**Elle calcule pour tout le monde, y compris pour ceux qui ne liront rien.**

:::exemple[Exemple 30.2 : les prédictions que personne ne lit]
Sur les 50 000 utilisateurs de Listify, 20 % ouvrent l'application un jour donné. Les tâches ouvertes sont réparties à peu près uniformément entre les utilisateurs.

**Prédictions utiles.** Seules les tâches des utilisateurs actifs seront affichées :

$$
0{,}20 \times 200\,000 = 40\,000 \text{ prédictions lues sur } 200\,000 \text{ calculées}.
$$

80 % du calcul est perdu. Avec notre classifieur, peu importe : on perd 0,6 seconde de processeur par nuit.

**Avec un modèle lourd.** Remplaçons le classifieur par un modèle de langage qui demande 20 ms de GPU par tâche. Le calcul nocturne coûte alors :

$$
200\,000 \times 20\ \text{ms} = 4\,000\ \text{s} \approx 1{,}1 \text{ heure de GPU},
$$

dont 53 minutes pour des prédictions jamais affichées. À 2 € l'heure de GPU, cela fait environ 650 € par an de calcul inutile, contre environ 160 € si l'on ne calculait que pour les utilisateurs actifs. Le gaspillage croît avec le coût du modèle et avec la proportion d'utilisateurs inactifs : c'est l'argument le plus fréquent pour passer à la prédiction à la demande.
:::

Huyen résume ces deux limites : la prédiction par lots est adaptée quand on a besoin de beaucoup de prédictions sans avoir besoin de leurs résultats immédiatement, et elle cesse de l'être quand les préférences des utilisateurs changent vite ou que les entrées ne sont pas connues à l'avance [^huyen].

## 4. La prédiction à la demande

### 4.1 Le principe et le budget de latence

L'application envoie une entrée et **attend** la réponse. C'est le seul mode possible pour la suggestion de catégorie : le titre n'existe qu'à l'instant où il est tapé, et la suggestion n'a de valeur que si elle apparaît avant que l'utilisateur n'ait choisi lui-même.

Ce mode transforme le modèle en composant **sur le chemin critique** d'une interaction : sa lenteur devient celle de l'application, et sa panne aussi. La première question n'est donc plus « quelle précision ? » mais « **combien de temps ai-je ?** ».

Les études d'ergonomie donnent un ordre de grandeur classique, repris par Jakob Nielsen : en dessous de 0,1 seconde, l'utilisateur perçoit la réaction comme instantanée ; jusqu'à 1 seconde, il remarque l'attente mais garde le fil de sa pensée ; au-delà de 10 secondes, il décroche [^nielsen]. Une suggestion qui accompagne la frappe doit viser la première limite.

:::exemple[Exemple 30.3 : le budget de latence de la suggestion]
On fixe l'objectif : la suggestion doit s'afficher moins de 100 ms après que l'utilisateur a cessé de taper. On répartit ce budget entre les étapes, en prenant des valeurs typiques :

| Étape | Budget |
|---|---|
| Attente de fin de frappe dans le navigateur (anti-rebond) | 0 ms, comptée à part |
| Aller-retour réseau navigateur ↔ serveur (même pays) | 40 ms |
| Traversée du répartiteur de charge et du backend Flask | 10 ms |
| Lecture de l'historique de l'utilisateur dans PostgreSQL | 15 ms |
| Prétraitement et prédiction | 5 ms |
| Affichage dans le navigateur | 10 ms |
| **Marge** | 20 ms |
| **Total** | 100 ms |

Deux enseignements. D'abord, **le modèle n'est pas le poste principal** : 5 ms sur 100. Le réseau et la base pèsent dix fois plus. Optimiser le modèle au-delà ne sert à rien tant que les autres postes n'ont pas été traités. Ensuite, le budget laisse 5 ms au modèle : notre classifieur (0,37 ms) tient très largement ; un modèle de langage à 20 ms de GPU le ferait dépasser de 15 ms, et il faudrait soit un modèle plus petit, soit reprendre de la marge ailleurs.
:::

Le budget de latence est un contrat d'ingénierie : il se négocie une fois, s'écrit, et chaque composant doit le respecter. C'est l'équivalent, pour la latence, des objectifs de niveau de service (SLO) du chapitre 26.

[^nielsen]: Jakob Nielsen, *Usability Engineering*, Academic Press, 1993, chapitre 5 ; les trois limites s'appuient sur les travaux de Robert B. Miller, « Response time in man-computer conversational transactions », *AFIPS Fall Joint Computer Conference*, 1968.

### 4.2 Raisonner en percentiles

Un budget de 100 ms ne veut rien dire s'il est respecté **en moyenne** : un utilisateur ne vit pas la moyenne, il vit chaque requête. Le chapitre 26 a introduit les percentiles ; ils prennent ici toute leur importance. Notre classifieur a une médiane de 0,37 ms et un 99ᵉ percentile de 0,75 ms : une requête sur cent est deux fois plus lente que la médiane, à cause du ramasse-miettes de Python, d'une interruption du système, d'un cache processeur froid.

Ce 1 % paraît négligeable. Il ne l'est plus dès qu'une page déclenche **plusieurs** prédictions.

:::exemple[Exemple 30.4 : la queue de latence d'une page qui fait vingt appels]
La vue « toutes mes tâches » affiche 20 tâches, et pour chacune une icône de catégorie calculée par le service de prédiction. La page n'est complète que lorsque les 20 réponses sont arrivées : sa latence est celle de la **plus lente**.

Chaque appel a une probabilité 0,99 d'être plus rapide que son 99ᵉ percentile. Si les appels sont indépendants, la probabilité que les 20 le soient tous vaut :

$$
0{,}99^{20} \approx 0{,}818.
$$

Donc **18 %** des affichages de la page subissent au moins un appel lent, alors que chaque appel n'est lent qu'une fois sur cent. Avec 100 appels par page, ce serait $1 - 0{,}99^{100} \approx 63\ \%$ des affichages.

Deux remèdes simples : **grouper** les 20 prédictions en un seul appel (une requête, un lot de 20, une seule queue de latence à subir) ; ou, si les appels restent séparés, fixer l'objectif sur un percentile beaucoup plus haut (99,9ᵉ) pour chaque appel.
:::

Ce phénomène, que Jeffrey Dean et Luiz André Barroso ont décrit sous le nom de *tail at scale*, gouverne la conception des grands services : plus une requête dépend de composants en parallèle, plus la queue de distribution de chacun domine la latence de l'ensemble [^dean]. C'est la raison pour laquelle les services de prédiction sérieux publient leurs 99ᵉ et 99,9ᵉ percentiles, jamais leur moyenne.

[^dean]: Jeffrey Dean, Luiz André Barroso, « The Tail at Scale », *Communications of the ACM*, vol. 56, n° 2, 2013.

### 4.3 Dimensionner : la loi de Little et le prix de l'occupation

Combien de copies du modèle faut-il pour tenir la charge ? Deux outils suffisent pour un premier dimensionnement.

La **loi de Little** relie, pour tout système stable, le nombre moyen de requêtes en cours $L$, le débit d'arrivée $\lambda$ et le temps moyen passé dans le système $W$ [^little] :

$$
L = \lambda \, W.
$$

Elle ne suppose rien sur la distribution des arrivées ni des temps de service, ce qui la rend universelle.

Le second outil décrit ce qui se passe quand les requêtes **attendent**. Pour un serveur unique qui traite une requête à la fois, avec un temps de service moyen $S$ et un taux d'occupation $\rho = \lambda S$ (la fraction du temps où il est occupé), le modèle de file d'attente le plus simple, dit M/M/1, donne le temps moyen passé dans le système [^kleinrock] :

$$
W = \frac{S}{1 - \rho}.
$$

Le modèle suppose des arrivées et des temps de service aléatoires sans mémoire ; la réalité s'en écarte, mais la forme de la courbe, elle, est universelle : **la latence explose quand $\rho$ approche 1**.

:::exemple[Exemple 30.5 : combien de workers pour la suggestion ?]
Le service de prédiction est un processus Python qui répond en $S = 1{,}3$ ms par requête (mesuré au §6.2, protocole HTTP compris). À l'heure de pointe, Listify reçoit $\lambda = 600$ suggestions par seconde.

**Un seul worker.** Taux d'occupation : $\rho = 600 \times 0{,}0013 = 0{,}78$. Temps moyen dans le système :

$$
W = \frac{1{,}3}{1 - 0{,}78} \approx 5{,}9\ \text{ms}.
$$

Le service tient, mais les requêtes attendent en moyenne 4,6 ms dans la file pour 1,3 ms de travail utile. Par la loi de Little, il y a en moyenne $L = 600 \times 0{,}0059 \approx 3{,}5$ requêtes en cours.

**Un jour de forte affluence, 740 requêtes par seconde.** $\rho = 0{,}96$ et $W = 1{,}3 / 0{,}038 \approx 34$ ms. La charge n'a augmenté que de 23 %, la latence a été multipliée par 5,8. À 770 requêtes par seconde, $\rho$ atteint 1 : la file grossit sans limite.

**Deux workers, chacun recevant la moitié du trafic.** À 600 requêtes par seconde, $\rho = 0{,}39$ et $W \approx 2{,}1$ ms ; à 740, $\rho = 0{,}48$ et $W \approx 2{,}5$ ms. Le doublement de capacité ne divise pas la latence par deux : il la fait sortir de la zone où elle explose.

**La règle pratique qui en découle** : dimensionner pour que le taux d'occupation reste sous 60 à 70 % à la pointe, et déclencher la mise à l'échelle automatique (HPA, chapitre 22) bien avant 100 %.
:::

[^little]: John D. C. Little, « A Proof for the Queuing Formula: L = λW », *Operations Research*, vol. 9, n° 3, 1961.

[^kleinrock]: Leonard Kleinrock, *Queueing Systems, Volume 1: Theory*, Wiley, 1975, chapitre 3 (file M/M/1).

### 4.4 Ce que coûte la prédiction à la demande

En échange de la fraîcheur, ce mode impose ce que le semestre 2 a appris à gérer pour toute application : un service **toujours en marche**, dimensionné pour la **pointe** et non pour la moyenne, surveillé (latence, erreurs), redondant pour survivre à la perte d'une réplique. Il impose aussi une contrainte propre au ML : les caractéristiques utilisées par le modèle doivent être **disponibles au moment de la requête**, dans le budget de latence. Une caractéristique qui demande de parcourir tout l'historique de l'utilisateur (« nombre de tâches de travail créées ces six derniers mois ») est triviale à calculer la nuit, et trop lente à calculer à chaque frappe. On la précalcule donc par lots et on la lit au moment de la requête : c'est la combinaison que décrit Huyen, prédiction en ligne sur des caractéristiques calculées par lots [^huyen].

## 5. La prédiction sur un flux

### 5.1 Le principe

Dans les deux premiers modes, quelqu'un **demande** la prédiction : une tâche planifiée ou une requête d'utilisateur. Dans le troisième, c'est **l'arrivée de la donnée** qui la déclenche. Chaque événement (une tâche créée, cochée, supprimée) est publié sur un bus de messages comme Kafka (chapitre 37). Un consommateur lit ce flux en continu, met à jour des caractéristiques calculées sur des fenêtres de temps récentes, appelle le modèle, et publie le résultat ou déclenche une action.

La latence typique se compte en secondes : moins qu'un lot quotidien, plus qu'une requête synchrone. Mais le vrai gain n'est pas la latence, c'est l'accès à des **caractéristiques fraîches** qu'aucun autre mode ne calcule à temps : « nombre de tâches créées dans les cinq dernières minutes », « temps écoulé depuis la dernière tâche cochée ».

:::exemple[Exemple 30.6 : détecter un utilisateur débordé]
Listify veut proposer, au bon moment, de reporter des tâches à un utilisateur qui en accumule trop. Le signal est la **rafale** : beaucoup de tâches créées, aucune cochée, en peu de temps.

**Volume du flux.** Chaque utilisateur actif produit en moyenne 8 événements par jour. Avec 50 000 utilisateurs, dont 20 % actifs chaque jour, cela fait $10\,000 \times 8 = 80\,000$ événements par jour, soit :

$$
\frac{80\,000}{86\,400} \approx 0{,}93 \text{ événement par seconde en moyenne}.
$$

Même avec une pointe dix fois supérieure, un seul consommateur suffit largement. Le flux n'est pas choisi ici pour absorber un gros volume, mais pour la **fraîcheur** des caractéristiques.

**Pourquoi pas par lots ?** Un calcul nocturne verrait la rafale de 14 h le lendemain à 3 h : trop tard, l'utilisateur a abandonné.

**Pourquoi pas à la demande ?** Il n'y a pas de requête à laquelle accrocher la prédiction : l'utilisateur ne demande rien, c'est au système de réagir. On pourrait calculer la caractéristique à chaque création de tâche, mais c'est déjà un traitement de flux, simplement mal rangé dans le backend.
:::

### 5.2 Le prix du flux

Le flux est le mode le plus exigeant. Il ajoute un **bus de messages** à exploiter (Kafka et son stockage répliqué), des **consommateurs** qui doivent reprendre là où ils se sont arrêtés après une panne sans perdre ni doubler d'événements, et surtout une difficulté de fond : **calculer la même caractéristique de la même façon** sur le flux (en production) et sur l'historique (à l'entraînement). Si l'entraînement calcule « tâches créées en cinq minutes » avec une requête SQL sur l'historique et la production avec un compteur en mémoire, la moindre différence (fuseau horaire, bornes de fenêtre, événements arrivés en retard) recrée exactement le décalage entraînement-service du chapitre 27.

Deux architectures ont été proposées pour vivre avec les deux mondes. L'**architecture lambda** maintient deux chaînes parallèles, une par lots (exacte, lente) et une sur le flux (approchée, rapide), et fusionne leurs résultats [^marz]. Jay Kreps, l'un des créateurs de Kafka, a critiqué la duplication de code qu'elle impose et proposé l'**architecture kappa** : une seule chaîne de flux, et l'historique retraité en rejouant le journal des événements depuis le début [^kreps]. Le chapitre 37 y reviendra.

:::warning[Ne pas choisir le flux par effet de mode]
« Temps réel » sonne mieux que « chaque nuit ». Mais le flux multiplie les composants à exploiter et les occasions de décalage entre entraînement et service. Il se justifie quand une **caractéristique fraîche** change réellement la qualité de la décision, ou quand la **réaction** doit suivre l'événement de quelques secondes. Si un lot horaire suffit au besoin, c'est le lot horaire qu'il faut construire.
:::

[^marz]: Nathan Marz, James Warren, *Big Data: Principles and best practices of scalable realtime data systems*, Manning, 2015.

[^kreps]: Jay Kreps, « Questioning the Lambda Architecture », *O'Reilly Radar*, 2014.

## 6. Comparer et combiner

### 6.1 Le tableau de synthèse

| Critère | Par lots | À la demande | Sur un flux |
|---|---|---|---|
| Déclencheur | Calendrier | Requête d'un utilisateur | Arrivée d'un événement |
| Latence vue par l'application | Lecture d'une table (ms) | Calcul complet (ms à centaines de ms) | Secondes |
| Âge de la prédiction | Jusqu'à la période du lot (heures) | Nul | Secondes |
| Entrées | Connues à l'avance, finies | Quelconques | Événements |
| Calcul inutile | Élevé (tout est calculé) | Nul | Faible |
| Dimensionnement | Débit du lot | Pointe de trafic, latence de queue | Débit du flux |
| Panne | Données d'hier, rattrapable | Fonction indisponible | Retard, rattrapable |
| Complexité d'exploitation | Faible | Moyenne | Élevée |
| Exemple Listify | Récapitulatif du matin | Suggestion de catégorie | Détection de rafale |

La ligne « panne » mérite une attention particulière. Si la tâche de nuit échoue, Listify affiche le récapitulatif de la veille : dégradé, mais utilisable, et la relance répare tout. Si le service de prédiction à la demande tombe, la suggestion disparaît : il faut que l'application le **supporte** (un délai d'attente court, pas de suggestion plutôt qu'une page bloquée). C'est le principe de dégradation gracieuse : **une fonctionnalité de ML ne doit jamais pouvoir faire tomber la fonctionnalité principale**.

### 6.2 Le coût d'un aller-retour réseau

Avant de combiner, il faut savoir ce que coûte le fait d'appeler le modèle **à travers le réseau** plutôt que dans le même processus. On a enveloppé le classifieur dans un petit serveur HTTP (bibliothèque standard de Python) et mesuré 3 000 appels successifs depuis la même machine.

:::exemple[Exemple 30.7 : 0,37 ms, 1,3 ms ou 43 ms]
**Dans le processus** : 0,37 ms en médiane (tableau du §2).

**Par HTTP, sur la même machine** : 1,29 ms en médiane, 2,04 ms au 99ᵉ percentile. L'aller-retour ajoute donc environ 0,9 ms : sérialisation JSON, analyse de la requête HTTP, passage par la pile TCP du noyau. Entre deux nœuds d'un même cluster, il faut ajouter la traversée du réseau, souvent quelques centaines de microsecondes, parfois quelques millisecondes.

**Par HTTP, premier essai** : 43,0 ms en médiane. Trente fois plus ! Le client comme le serveur envoyaient les en-têtes et le corps de leurs messages en **deux écritures** successives. L'algorithme de Nagle retient la seconde tant que la première n'a pas été acquittée [^nagle], et le serveur **retarde** son acquittement jusqu'à 40 ms sous Linux dans l'espoir de le joindre à une réponse [^rfc1122]. Chacun attend l'autre. Activer l'option `TCP_NODELAY` des deux côtés a ramené la médiane à 1,29 ms.

La leçon dépasse l'anecdote : **le coût d'un appel distant se mesure, il ne se suppose pas**. Un service de prédiction dont la médiane vaut 40 ms « sans raison » doit faire penser à ce piège, que les serveurs fondés sur `asyncio`, comme Uvicorn, évitent en activant `TCP_NODELAY` par défaut ; avec tout autre serveur ou client, cela se vérifie.
:::

[^nagle]: John Nagle, « Congestion Control in IP/TCP Internetworks », RFC 896, 1984.

[^rfc1122]: Robert Braden (éd.), « Requirements for Internet Hosts: Communication Layers », RFC 1122, 1989, section 4.2.3.2 (acquittement retardé, au plus 0,5 s ; Linux l'applique avec un délai de l'ordre de 40 ms).

### 6.3 Les combinaisons

Les trois modes se combinent souvent, et les architectures réelles sont presque toujours hybrides.

**Précalcul et repli.** On précalcule par lots les prédictions des entrées les plus fréquentes, et l'on n'appelle le modèle à la demande que pour les autres. Cela contourne la première limite de la prédiction par lots (l'espace d'entrées doit être connu) pour la partie de l'espace qui concentre le trafic.

:::exemple[Exemple 30.8 : précalculer les titres fréquents]
Les titres de tâches suivent, comme la plupart des textes, une distribution très concentrée : quelques titres (« acheter du pain », « appeler maman », « payer le loyer ») reviennent constamment. Supposons qu'une analyse de l'historique montre que les 10 000 titres les plus fréquents, une fois normalisés (minuscules, espaces), représentent 45 % des saisies.

**Précalcul.** Une tâche de nuit calcule les 10 000 suggestions : $10\,000 \times 3{,}9\ \mu\text{s} \approx 40$ ms de modèle, stockées dans un cache clé-valeur.

**Charge résiduelle du service à la demande.** À la pointe de 600 requêtes par seconde, seules 55 % arrivent au modèle, soit 330 par seconde. Avec un seul worker, $\rho = 330 \times 0{,}0013 \approx 0{,}43$ au lieu de 0,78, et le temps moyen passe de 5,9 ms à 2,3 ms (formule du §4.3).

**Le prix.** Deux chemins à maintenir, et un risque nouveau : si le modèle change, le cache doit être **reconstruit en même temps**, sinon les titres fréquents reçoivent les prédictions de l'ancien modèle et les autres celles du nouveau. Le cache devient un artefact versionné avec le modèle, au même titre que le prétraitement.
:::

**Lots pour les caractéristiques, demande pour la prédiction.** C'est le cas du §4.4 : l'historique est résumé chaque nuit, la prédiction est faite à la demande avec ces résumés et l'entrée fraîche.

**Flux pour les caractéristiques, demande pour la prédiction.** La suggestion de catégorie pourrait tenir compte de « la catégorie des trois dernières tâches créées », mise à jour par un consommateur du flux et lue au moment de la requête. C'est le niveau le plus riche, et le plus coûteux.

Ces combinaisons partagent un besoin : que la **même** caractéristique soit disponible, calculée de la même façon, à l'entraînement et au service. Les *feature stores*, que nous ne traiterons qu'en panorama, sont nés de ce besoin : un catalogue de caractéristiques calculées une fois, servies à la fois à l'entraînement (historique) et à la prédiction (valeur courante).

## 7. Où vit le modèle : embarqué ou service

La première moitié du chapitre répondait à « quand ». Reste une question orthogonale, qui se pose surtout pour la prédiction à la demande : **dans quel processus** le modèle s'exécute-t-il ?

<Figure src="embarque-service" num="30.2" alt="En haut, modèle embarqué : trois répliques du backend Flask contiennent chacune le code et une copie du modèle de 150 Mo ; changer de modèle impose de redéployer le backend. En bas, modèle exposé comme un service : trois répliques du backend Flask, sans modèle, appellent un service de prédiction à deux répliques, versionné à part ; un saut réseau de plus, mais un déploiement, un dimensionnement et une version propres au modèle.">
Deux emplacements pour le même modèle. Le premier évite un appel réseau ; le second découple le cycle de vie du modèle de celui de l'application.
</Figure>

### 7.1 Le modèle embarqué

Le backend Flask de Listify charge le fichier du modèle au démarrage et appelle `modele.predict(...)` comme n'importe quelle fonction. C'est l'option la plus simple : aucun composant supplémentaire, aucun appel réseau, aucune sérialisation. Pour un petit modèle et une petite équipe, c'est souvent le bon choix, et c'est par là que la plupart des projets commencent.

Ses inconvénients apparaissent quand le modèle grossit ou que son rythme de vie diverge de celui de l'application.

:::exemple[Exemple 30.9 : la mémoire d'un modèle embarqué]
Notre classifieur pèse 4 Kio sérialisé : son vocabulaire synthétique est minuscule. Supposons qu'on le remplace par un petit modèle de langage de 150 Mo, plus précis sur les titres ambigus.

**Embarqué.** Le backend tourne en 3 répliques de 4 workers Gunicorn chacune. Chaque worker est un processus distinct qui charge son propre exemplaire :

$$
3 \times 4 \times 150\ \text{Mo} = 1{,}8\ \text{Go}
$$

de mémoire consacrés au modèle, pour un backend qui n'en demandait que quelques centaines de mégaoctets. Chaque nouvelle réplique ajoutée par l'autoscaler coûte 600 Mo de plus, même si la charge supplémentaire concerne des routes qui n'utilisent pas le modèle.

**L'option `--preload`.** Gunicorn peut charger l'application **avant** de créer les workers, qui partagent alors les pages mémoire du modèle tant qu'elles ne sont pas modifiées (copie à l'écriture). Le gain est réel mais s'érode : le compteur de références de Python modifie les objets qu'il touche, ce qui force la copie des pages correspondantes. Instagram a documenté ce phénomène, au point de désactiver le ramasse-miettes de Python pour préserver le partage [^instagram].

**En service.** Le service de prédiction tourne en 2 répliques de 2 workers : $2 \times 2 \times 150 = 600$ Mo. Les répliques du backend redeviennent légères, et chacun des deux composants se met à l'échelle selon **sa** charge.
:::

Deux autres couplages pèsent souvent plus lourd que la mémoire.

- **Le cycle de déploiement.** Changer de modèle, c'est reconstruire et redéployer le backend. Si le modèle est réentraîné chaque semaine (chapitre 29) et le backend livré plusieurs fois par jour, chacun des deux rythmes perturbe l'autre : une régression du modèle impose d'annuler une version du backend, et inversement.
- **Les dépendances.** Le modèle impose ses bibliothèques (une version précise de scikit-learn, parfois PyTorch et ses 2 Go) à l'image du backend. Le chapitre 28 a rangé la version des bibliothèques parmi les entrées d'un modèle, et la documentation de scikit-learn prévient qu'un modèle sérialisé avec une version n'est pas garanti de se charger, ni de se comporter à l'identique, avec une autre [^sklearn-persist] : une simple mise à jour du backend peut alors casser le modèle.

[^sklearn-persist]: Documentation de scikit-learn, « Model persistence », section sur les limites de sécurité et de maintenabilité. [scikit-learn.org/stable/model_persistence.html](https://scikit-learn.org/stable/model_persistence.html).

[^instagram]: Chenyang Wu, Min Ni, « Dismissing Python Garbage Collection at Instagram », *Instagram Engineering*, 2017.

### 7.2 Le modèle exposé comme un service

Le modèle vit dans son propre service, derrière une API (REST ou gRPC), avec son image, son déploiement Kubernetes, ses répliques et sa version. Le backend l'appelle comme n'importe quelle autre dépendance. C'est l'application directe de l'architecture en microservices du semestre 2, et c'est l'option que construiront les TP 25 et 27 : une API FastAPI qui charge le modèle promu dans le registre MLflow.

Ce qu'on y gagne :

- **un cycle de vie propre** : le modèle se déploie, s'annule et se teste (déploiement canari, chapitre 24) indépendamment du backend ;
- **un dimensionnement propre** : on peut placer le service sur des nœuds avec GPU sans y placer le backend, et le mettre à l'échelle sur sa propre métrique ;
- **un contrat explicite** : l'API du service définit exactement les entrées attendues, ce qui oblige à écrire le prétraitement **une fois**, dans le service, au lieu de le laisser dériver dans chaque client ;
- **le partage** : plusieurs applications (le backend web, une future application mobile, la tâche de nuit) peuvent utiliser le même modèle.

Ce qu'on y perd : un saut réseau (environ 1 ms mesurée, §6.2), un composant de plus à surveiller, et une nouvelle cause de panne qu'il faut prévoir côté client (délai d'attente, repli sans suggestion).

:::exemple[Exemple 30.10 : ce que coûte le saut réseau dans le budget]
Reprenons le budget de l'exemple 30.3 : 5 ms pour « prétraitement et prédiction », 20 ms de marge.

**Embarqué** : 0,37 ms de prédiction, soit 7 % du poste.

**En service** : 1,3 ms mesurée en local, plus environ 0,5 ms de traversée réseau intra-cluster, soit 1,8 ms, 36 % du poste. Le budget reste respecté avec une large marge.

**Le vrai risque n'est pas la médiane mais la queue.** Un appel distant ajoute des causes de lenteur rares (retransmission TCP, réplique en cours de redémarrage, file d'attente pleine) qui touchent le 99,9ᵉ percentile. D'où deux règles : fixer côté backend un **délai d'attente** égal au budget du poste (5 ms ici, au-delà on renonce à la suggestion), et **surveiller** le service de prédiction avec les mêmes indicateurs RED que le chapitre 26 appliquait à Listify.
:::

### 7.3 Et dans le navigateur ?

Une troisième option existe : exécuter le modèle **sur l'appareil de l'utilisateur**, dans le navigateur ou l'application mobile, grâce à des environnements d'exécution comme ONNX Runtime Web ou TensorFlow Lite. La latence réseau disparaît, les données ne quittent pas l'appareil (un argument fort au regard du RGPD, chapitre 38), et le calcul ne coûte rien au serveur. En contrepartie, le modèle doit être petit (il est téléchargé), on ne maîtrise pas la puissance de l'appareil, et une mise à jour du modèle dépend du rafraîchissement du client. Pour la suggestion de catégorie, ce serait envisageable avec le classifieur de 4 Kio ; ce ne le serait plus avec un modèle de 150 Mo. Le cours n'ira pas plus loin sur cette voie.

## 8. Servir plus avec la même machine : le regroupement dynamique

Le §2 a mesuré un facteur 95 entre une prédiction isolée et une prédiction dans un grand lot. Sur un GPU, l'écart est encore plus marqué : lancer un calcul a un coût fixe important, et la puce n'est efficace que sur de gros tableaux. La prédiction à la demande, qui traite une requête à la fois, se prive de ce gain. Le **regroupement dynamique** (*dynamic batching*) le récupère : le serveur retient brièvement les requêtes qui arrivent, puis les envoie ensemble au modèle.

<Figure src="batching-dynamique" num="30.3" alt="Axe du temps de 0 à 40 millisecondes. Huit requêtes arrivent entre 0 et 10 ms pendant une fenêtre d'attente d'au plus 10 ms ; elles sont envoyées ensemble au modèle, qui les traite en un seul appel de 5 plus 8 fois 0,2, soit 6,6 ms ; les huit réponses repartent ensemble vers 16,6 ms.">
Le regroupement dynamique : on échange quelques millisecondes d'attente contre un seul appel au modèle pour plusieurs requêtes.
</Figure>

Le serveur a deux paramètres : la **taille maximale** d'un lot, et le **délai d'attente maximal** avant d'envoyer un lot incomplet. Le lot part dès que l'un des deux seuils est atteint.

:::exemple[Exemple 30.11 : le regroupement sur GPU]
Un modèle de langage sur GPU coûte $5$ ms par appel, plus $0{,}2$ ms par élément du lot (valeurs d'ordre de grandeur pour un petit modèle).

**Sans regroupement.** Chaque requête coûte $5{,}2$ ms. Débit maximal d'un GPU :

$$
\frac{1}{5{,}2\ \text{ms}} \approx 192 \text{ requêtes par seconde}.
$$

**Avec des lots de 8.** Un appel coûte $5 + 8 \times 0{,}2 = 6{,}6$ ms pour 8 requêtes :

$$
\frac{8}{6{,}6\ \text{ms}} \approx 1\,212 \text{ requêtes par seconde},
$$

soit 6,3 fois plus avec le même GPU. À la pointe de 600 requêtes par seconde, on passe de 4 GPU (au moins, et bien plus pour garder un taux d'occupation raisonnable) à un seul.

**Le prix en latence.** La première requête du lot attend jusqu'à 10 ms que le lot se remplisse, puis 6,6 ms de calcul : au pire 16,6 ms au lieu de 5,2 ms. À 600 requêtes par seconde, 8 requêtes arrivent en 13 ms en moyenne, donc le délai de 10 ms déclenche souvent avant que le lot ne soit plein ; il faut ajuster les deux paramètres **à la charge réelle**.

**Et à faible trafic ?** À 20 requêtes par seconde, une fenêtre de 10 ms ne contient en moyenne que 0,2 requête : les lots sont presque toujours de taille 1, et chaque requête subit 10 ms d'attente pour rien. Le regroupement dynamique n'est rentable qu'à fort trafic.
:::

Le regroupement dynamique est proposé en standard par les serveurs de modèles : TensorFlow Serving, NVIDIA Triton, TorchServe, KServe. Le système Clipper, présenté en 2017, en a fait une contribution de recherche en ajustant **automatiquement** la taille des lots pour respecter un objectif de latence [^clipper]. Pour notre classifieur sur processeur, l'enjeu est faible ; il devient central dès qu'un modèle tourne sur GPU, et il est au cœur du service des grands modèles de langage (§ « Regard recherche »).

[^clipper]: Daniel Crankshaw, Xin Wang, Giulio Zhou, Michael J. Franklin, Joseph E. Gonzalez, Ion Stoica, « Clipper: A Low-Latency Online Prediction Serving System », *NSDI*, 2017.

## 9. Choisir pour Listify

On peut maintenant répondre, besoin par besoin. La démarche tient en quatre questions, à poser dans l'ordre.

1. **L'entrée est-elle connue à l'avance ?** Si non, la prédiction par lots est exclue (sauf précalcul partiel des entrées fréquentes).
2. **Quel âge de prédiction le besoin tolère-t-il ?** Des heures : lots. Des secondes : flux ou demande. Aucun : demande.
3. **Qui déclenche ?** Un calendrier : lots. Un utilisateur qui attend : demande. Un événement auquel il faut réagir : flux.
4. **Le modèle a-t-il un cycle de vie propre ?** S'il est réentraîné plus souvent ou moins souvent que l'application, s'il est lourd, ou s'il sert plusieurs clients : service. Sinon, l'embarquer est un choix légitime.

| Besoin | Q1 | Q2 | Q3 | Mode retenu | Emplacement |
|---|---|---|---|---|---|
| Suggestion de catégorie | Non | Aucun | Utilisateur | À la demande | Service (TP 25), avec repli sans suggestion |
| Récapitulatif du matin | Oui | Une journée | Calendrier | Par lots, chaque nuit (DAG Airflow) | Tâche de lot qui appelle le même modèle |
| Détection de rafale | Non | Secondes | Événement | Sur un flux (chapitre 37) | Consommateur Kafka |

Pour la suggestion, rien n'empêche d'embarquer d'abord le classifieur dans le backend (c'est le plus simple, et il est léger) ; le TP 25 l'en extrait pour en faire un service, quand le registre MLflow permet de le réentraîner et de le promouvoir indépendamment de l'application. Ce passage de l'un à l'autre est typique : on **commence** par embarquer, et l'on **extrait** le modèle quand l'un des couplages du §7.1 commence à coûter.

:::exemple[Exemple 30.12 : chiffrer une décision complète]
Un stagiaire propose de calculer **aussi** la suggestion de catégorie par lots : « chaque nuit, on précalcule la catégorie de toutes les tâches, comme ça on n'a pas besoin de service ». Évaluons.

**Q1** : la suggestion porte sur une tâche **en cours de saisie**. Les tâches existantes ont déjà une catégorie, choisie par l'utilisateur. Précalculer leur catégorie ne sert à rien pour la suggestion : la proposition échoue à la première question.

**Ce que la proposition sait faire.** Précalculer la catégorie des tâches existantes peut servir à **autre chose** : détecter les tâches probablement mal catégorisées (celles où le modèle et l'utilisateur ne sont pas d'accord), pour un écran de rangement. Pour 200 000 tâches, 0,78 s de modèle par nuit (exemple 30.1) : aucun obstacle de coût.

**Conclusion.** La suggestion reste à la demande ; l'idée du stagiaire devient un **second** besoin, servi par lots. Deux besoins, deux modes, un même modèle : c'est le cas général.
:::

## Ce qu'il faut retenir

<div className="retenir">

1. Un mode de mise à disposition répond à une question : **quand** la prédiction est-elle calculée, et **qui** en déclenche le calcul. Le modèle peut être le même dans les trois modes.
2. **Par lots** : calculée à l'avance pour toutes les entrées connues ; latence nulle, prédictions qui vieillissent, calcul souvent gaspillé, exploitation simple, panne rattrapable.
3. **À la demande** : calculée pendant la requête ; parfaitement fraîche, mais sur le chemin critique. On raisonne avec un **budget de latence** et en **percentiles** : une page qui fait 20 appels subit le 99ᵉ percentile de l'un d'eux 18 % du temps.
4. **Loi de Little** $L = \lambda W$ et file d'attente : $W = S/(1-\rho)$. La latence explose quand l'occupation approche 100 % ; on dimensionne pour rester sous 60 à 70 % à la pointe.
5. **Sur un flux** : calculée à l'arrivée de chaque événement ; son véritable apport est l'accès à des **caractéristiques fraîches**, au prix d'une infrastructure lourde et d'un risque accru de décalage entre entraînement et service.
6. Les architectures réelles sont **hybrides** : précalcul des entrées fréquentes, caractéristiques par lots ou sur flux et prédiction à la demande.
7. **Embarqué** : simple, sans saut réseau, mais le modèle partage la mémoire, les dépendances et le cycle de déploiement de l'application. **Service** : environ 1 ms de plus, un composant à exploiter, mais un cycle de vie, un dimensionnement et un contrat propres. On commence souvent embarqué et l'on extrait quand le couplage coûte.
8. Le **regroupement dynamique** échange quelques millisecondes d'attente contre un débit multiplié ; il est rentable à fort trafic et sur GPU.
9. Une fonctionnalité de ML ne doit **jamais** faire tomber la fonctionnalité principale : délai d'attente court et repli sans prédiction.

</div>

## Regard recherche

:::recherche
Le service de modèles (*model serving*) est devenu un champ de recherche en systèmes à part entière, à la croisée des systèmes distribués, de l'ordonnancement et de l'apprentissage automatique :

- **Daniel Crankshaw et al., « Clipper: A Low-Latency Online Prediction Serving System », *NSDI*, 2017.** Une couche intermédiaire entre applications et modèles, qui ajuste la taille des lots pour respecter un objectif de latence et met en cache les prédictions fréquentes.
- **Christopher Olston et al., « TensorFlow-Serving: Flexible, High-Performance ML Serving », *Workshop on ML Systems at NIPS*, 2017.** La conception du serveur de modèles de Google : chargement et remplacement de versions sans interruption, regroupement des requêtes.
- **Arpan Gujarati et al., « Serving DNNs like Clockwork: Performance Predictability from the Bottom Up », *OSDI*, 2020.** Part du constat que l'inférence d'un réseau de neurones a une durée presque déterministe, et en tire un ordonnanceur qui tient des objectifs de latence serrés au 99,99ᵉ percentile.
- **Francisco Romero et al., « INFaaS: Automated Model-less Inference Serving », *USENIX ATC*, 2021.** Le client exprime un besoin (latence, précision) plutôt qu'un modèle ; le système choisit la variante de modèle et le matériel.
- **Gyeong-In Yu et al., « Orca: A Distributed Serving System for Transformer-Based Generative Models », *OSDI*, 2022**, et **Woosuk Kwon et al., « Efficient Memory Management for Large Language Model Serving with PagedAttention », *SOSP*, 2023.** Le regroupement dynamique repensé pour les modèles génératifs, où chaque requête produit un nombre variable de jetons : le lot se recompose à chaque itération (*continuous batching*), et la mémoire du GPU est gérée par pages comme celle d'un système d'exploitation. Ce dernier article est à l'origine du serveur vLLM.

Piste d'innovation : le coût énergétique de l'inférence dépasse désormais celui de l'entraînement pour les modèles très utilisés. Choisir dynamiquement le modèle, la taille des lots et le matériel pour respecter une latence **au moindre coût énergétique** est un problème ouvert, qui rejoint les travaux sur la gestion de l'énergie dans les centres de données.
:::

## Bibliographie du chapitre

<div className="biblio">

### Sources primaires

- Chip Huyen, *Designing Machine Learning Systems*, O'Reilly, 2022, chapitre 7 (« Model Deployment and Prediction Service ») : la référence de ce chapitre pour les modes de prédiction et leurs combinaisons.
- Jeffrey Dean, Luiz André Barroso, « The Tail at Scale », *Communications of the ACM*, 2013.
- John D. C. Little, « A Proof for the Queuing Formula: L = λW », *Operations Research*, 1961.
- Jay Kreps, « Questioning the Lambda Architecture », *O'Reilly Radar*, 2014.

### Lectures recommandées

- Chip Huyen, *Designing Machine Learning Systems*, chapitre 7, section « Model Compression » : réduire la taille et la latence d'un modèle avant de le servir.
- Betsy Beyer et al. (dir.), *Site Reliability Engineering*, O'Reilly, 2016, chapitre 4 (« Service Level Objectives ») : fixer et suivre un objectif de latence en percentiles.
- Martin Kleppmann, *Designing Data-Intensive Applications*, O'Reilly, 2017, chapitres 10 et 11 : traitements par lots et traitements de flux, en profondeur.

### Pour aller plus loin

- Les articles de la rubrique « Regard recherche ».
- Leonard Kleinrock, *Queueing Systems, Volume 1: Theory*, Wiley, 1975 : la théorie des files d'attente dont le §4.3 n'utilise que la formule la plus simple.

</div>
