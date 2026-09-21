---
title: "Ch. 24 : Livraison et déploiement continus"
sidebar_label: "Ch. 24 : Livraison et déploiement continus"
hide_title: true
---

import ChapterHead from '@site/src/components/ChapterHead';
import Figure from '@site/src/components/Figure';

<ChapterHead
  kicker="Semestre 2 · Bloc 3 · Chapitre 24"
  title="Livraison et déploiement continus"
  lecture="40 min"
  competences={['C1', 'C2', 'C4']}
/>

:::objectifs
À l'issue de ce chapitre, vous saurez :

- distinguer rigoureusement intégration, livraison et déploiement continus, et choisir entre les deux derniers selon le contexte ;
- expliquer pourquoi on construit un artefact **une seule fois** et on le **promeut** d'un environnement à l'autre ;
- versionner une API selon SemVer, et identifier une image sans ambiguïté (tag ou digest) ;
- argumenter le choix entre trunk-based development et git-flow ;
- comparer rolling update, blue-green et canary, et calculer le comportement d'un rolling update Kubernetes ;
- mener une migration de schéma sans coupure (expand/contract) ;
- calculer les quatre indicateurs DORA à partir d'un journal de déploiements.
:::

## 1. Un artefact testé n'est pas un logiciel en production

Au chapitre 23, le pipeline s'arrêtait à la publication d'une image vérifiée dans un registre. C'est un progrès considérable, mais l'utilisateur de Listify n'en voit rien : pour lui, rien n'a changé tant que la nouvelle version ne tourne pas en production. Et le chemin qui reste à parcourir est justement le plus risqué. Déployer, c'est toucher au système qui sert les utilisateurs, avec ses données réelles, sa charge réelle, ses configurations propres. C'est là que se produisent la plupart des incidents.

La réponse traditionnelle à ce risque était de déployer **rarement** : une grosse version par trimestre, préparée pendant des semaines, installée un week-end par une équipe d'exploitation distincte, avec un plan de retour arrière rarement testé. Ce chapitre applique au déploiement le raisonnement que le chapitre 23 appliquait à l'intégration : si déployer fait mal, il faut le faire **plus souvent**, jusqu'à ce que ce soit un non-événement.

## 2. Définitions

La terminologie est confuse dans l'industrie, où « CD » désigne indifféremment deux pratiques différentes. Les définitions suivantes, issues de Jez Humble et David Farley [^humble] et reprises par Martin Fowler [^fowler-cd], sont celles qu'on attend à l'examen.

:::definition[Livraison continue (continuous delivery)]
Discipline dans laquelle le logiciel est construit de telle sorte qu'il peut être **mis en production à tout moment**. Chaque changement qui passe le pipeline produit une version candidate déployable ; le déploiement en production lui-même reste une **décision**, prise par un humain, qui se réduit à appuyer sur un bouton.
:::

:::definition[Déploiement continu (continuous deployment)]
Extension de la livraison continue dans laquelle **chaque changement** qui passe toutes les étapes du pipeline est **déployé automatiquement** en production, sans décision humaine.
:::

<Figure src="livraison-deploiement" num="24.1" alt="Trois lignes : l'intégration continue s'arrête à l'artefact testé ; la livraison continue le déploie en préproduction puis attend une décision humaine pour la production ; le déploiement continu va jusqu'en production automatiquement.">
  Intégration, livraison et déploiement continus. Les trois partagent le début du pipeline ; ils diffèrent par l'endroit où la chaîne automatique s'arrête.
</Figure>

La différence entre livraison et déploiement continus n'est **pas technique** : le pipeline est le même, seule la dernière porte change. Elle est **organisationnelle et contextuelle**. Le déploiement continu a été popularisé par des entreprises du web grand public ; Timothy Fitz décrivait dès 2009 comment IMVU déployait cinquante fois par jour [^fitz]. Mais il n'est pas toujours souhaitable, ni possible :

| Contexte | Choix raisonnable | Pourquoi |
|---|---|---|
| Service web interne, comme Listify | Déploiement continu | Le coût d'un incident est faible et le retour arrière rapide |
| Application mobile | Livraison continue | La publication passe par la validation d'un magasin d'applications, et les utilisateurs mettent à jour quand ils veulent |
| Logiciel médical, bancaire, embarqué | Livraison continue | Une validation humaine, parfois réglementaire, doit précéder la mise en production |
| Lancement coordonné avec le marketing | Livraison continue, ou déploiement continu avec fonctionnalité masquée (section 5.3) | La date de mise à disposition est une décision commerciale |

Dans les deux cas, l'essentiel est la **capacité** : le logiciel est toujours déployable. Une équipe en livraison continue qui décide de ne déployer qu'une fois par semaine peut le faire n'importe quel jour, sans préparation ; c'est cette propriété, pas la fréquence, qui définit la pratique.

[^humble]: Jez Humble, David Farley, *Continuous Delivery: Reliable Software Releases through Build, Test, and Deployment Automation*, Addison-Wesley, 2010. Le livre fondateur, qui introduit la notion de *deployment pipeline*.

[^fowler-cd]: Martin Fowler, « Continuous Delivery », martinfowler.com/bliki, 2013, qui explicite la distinction avec le déploiement continu.

[^fitz]: Timothy Fitz, « Continuous Deployment at IMVU: Doing the impossible fifty times a day », billet de blog, février 2009.

## 3. Le pipeline de déploiement

### 3.1 Construire une fois, promouvoir ensuite

Humble et Farley appellent **pipeline de déploiement** la chaîne complète qui mène du commit à la production, à travers plusieurs environnements. Son premier principe est contre-intuitif pour qui débute : **on ne reconstruit jamais l'artefact** d'un environnement à l'autre. On le construit une fois, au début, et c'est **exactement le même** binaire ou la même image qui est testé en développement, validé en préproduction, puis déployé en production. Passer d'un environnement au suivant s'appelle une **promotion**.

<Figure src="promotion-artefact" num="24.2" alt="Une seule image, identifiée par son digest, est déployée successivement en dev, en préproduction et en production ; seule la configuration change : nombre de répliques, base de données.">
  La promotion d'un artefact unique. Ce qui est validé en préproduction est ce qui part en production, au bit près ; seule la configuration diffère.
</Figure>

Pourquoi tant d'insistance ? Parce qu'un artefact reconstruit n'est **pas** le même artefact, même à partir du même commit.

:::exemple[Deux builds du même commit, deux images différentes]
Le Containerfile du backend de Listify commence par `FROM python:3.12-slim`. Le lundi, la CI construit l'image pour la préproduction ; les tests passent. Le jeudi, on reconstruit le même commit pour la production. Entre-temps, les mainteneurs de l'image officielle Python ont publié une mise à jour de sécurité : le tag `python:3.12-slim` pointe désormais vers une autre image, avec un Debian et une OpenSSL plus récents. L'image de production est donc construite sur une base **que personne n'a testée**. Si la nouvelle OpenSSL change un comportement, l'incident arrive en production alors que la préproduction était verte.

Avec la promotion, la question ne se pose pas : l'image testée lundi, identifiée par son digest `sha256:4f2c…`, est celle qui part jeudi. La mise à jour de sécurité de Python entrera par un nouveau build, qui repassera tout le pipeline.
:::

### 3.2 Séparer l'artefact de sa configuration

Si l'image est la même partout, ce qui distingue la production de la préproduction doit vivre **ailleurs** : dans la configuration injectée au démarrage. C'est ce que vous faites depuis le bloc 2 avec les ConfigMap, les Secret et les fichiers de valeurs Helm, et c'est ce qu'exigent deux facteurs de la méthode des *Twelve-Factor Apps* [^12factor] :

- **facteur III, configuration** : tout ce qui varie entre les déploiements (adresse de la base, identifiants, nombre de workers) est lu dans l'environnement, jamais codé en dur ;
- **facteur V, build, release, run** : trois étapes strictement séparées. Le *build* produit l'artefact ; la *release* combine l'artefact et une configuration ; le *run* exécute la release. Une release est immuable et identifiée : on ne modifie pas une release en place, on en crée une nouvelle.

Listify respecte le facteur III depuis le premier jour : toute sa configuration passe par les variables `DB_*`. C'est ce qui rend la promotion possible.

[^12factor]: Adam Wiggins, *The Twelve-Factor App*, 2011. [12factor.net](https://12factor.net/). Texte court, écrit à partir de l'expérience de la plateforme Heroku, devenu la référence des applications « cloud natives ».

### 3.3 Les environnements

Le nombre d'environnements varie, mais le schéma classique en compte trois :

| Environnement | Rôle | Ressemblance avec la production |
|---|---|---|
| **Développement** (*dev*) | Intégration continue de la branche principale, tests automatiques, essais libres | Faible : données fictives, une réplique |
| **Préproduction** (*staging*) | Dernière validation : tests de bout en bout, tests de charge, recette humaine | Élevée : même topologie, données anonymisées |
| **Production** | Sert les utilisateurs | Totale, par définition |

La préproduction n'a de valeur que si elle ressemble **vraiment** à la production. Une préproduction avec une base vide, une seule réplique et une autre version de PostgreSQL rassure sans protéger. C'est une des raisons pour lesquelles les techniques de déploiement progressif de la section 6 sont devenues si populaires : elles valident la nouvelle version **dans** la production, sur une petite fraction du trafic réel.

## 4. Versionner les artefacts

### 4.1 Le versionnage sémantique

Une version est un contrat avec ceux qui dépendent de votre logiciel. Le **versionnage sémantique** (SemVer), formalisé par Tom Preston-Werner [^semver], donne à chaque partie d'un numéro `MAJEUR.MINEUR.CORRECTIF` une signification précise :

- **MAJEUR** s'incrémente quand on fait un changement **incompatible** de l'interface publique ;
- **MINEUR** s'incrémente quand on **ajoute** une fonctionnalité de façon rétrocompatible ;
- **CORRECTIF** s'incrémente pour une correction de bogue rétrocompatible.

Des suffixes marquent les préversions (`2.0.0-rc.1`), qui précèdent la version finale dans l'ordre de précédence. Pour une API comme celle de Listify, l'interface publique est l'ensemble de ses routes, de leurs paramètres et de la forme de leurs réponses.

:::exemple[Quelle version pour chaque changement de Listify ?]
Listify est en version `1.4.2`. Pour chaque changement, on détermine la version suivante.

1. On corrige un bogue : `DELETE /api/tasks/<id>` renvoyait 500 au lieu de 404 pour un identifiant négatif. Aucun client correct ne dépendait du 500. **Correctif : `1.4.3`.**
2. On ajoute un champ optionnel `due_date` dans les réponses de `GET /api/tasks`, et on l'accepte, sans l'exiger, dans `POST /api/tasks`. Un ancien client ignore le nouveau champ et continue de fonctionner. **Mineur : `1.5.0`** (le correctif revient à 0).
3. On ajoute la pagination à `GET /api/tasks`, qui renvoie désormais un objet `{"items": [...], "next": ...}` au lieu d'une liste. Tout client existant, dont le frontend actuel, casse. **Majeur : `2.0.0`.**
4. Pour éviter la rupture du point 3, on ajoute plutôt une **nouvelle** route `GET /api/v2/tasks` paginée, en conservant l'ancienne. C'est un ajout rétrocompatible : **mineur, `1.6.0`**. L'ancienne route pourra être supprimée plus tard, dans une version `2.0.0` annoncée à l'avance.

Le point 4 illustre une conséquence importante : SemVer rend **visible** le coût d'une rupture, ce qui pousse à concevoir des évolutions compatibles.
:::

[^semver]: Tom Preston-Werner, *Semantic Versioning 2.0.0*, [semver.org](https://semver.org/lang/fr/). La spécification tient en une page et se lit en dix minutes.

### 4.2 Tags et digests d'images

Au TP 14, vous avez vu qu'une image de conteneur a deux sortes d'identifiants :

- un **tag**, lisible (`listify-backend:1.5.0`), mais **mobile** : c'est une étiquette qu'on peut déplacer vers une autre image à tout moment ;
- un **digest** (`listify-backend@sha256:4f2c…`), l'empreinte cryptographique du manifeste de l'image, **immuable** par construction : s'il change un seul octet, le digest change.

La règle professionnelle en découle. Pour **désigner** une version, on utilise un tag informatif ; pour **déployer** et tracer, on s'appuie sur une référence qu'on ne peut pas déplacer. Deux conventions courantes, cumulables :

- tagger chaque image avec l'**empreinte du commit** qui l'a produite (`listify-backend:3f9a1c2`), en plus du numéro SemVer quand il y en a un. On sait alors toujours de quel code vient ce qui tourne ;
- dans les manifests de production, épingler le **digest**, ou au minimum un tag qu'on s'interdit de réutiliser.

:::danger[Le tag `latest` en production]
`latest` n'a rien de spécial : c'est le tag par défaut, qui désigne la dernière image poussée sans tag explicite. En production, il cumule les défauts. Deux nœuds Kubernetes qui tirent `latest` à une heure d'intervalle peuvent exécuter **deux versions différentes** du même Deployment ; un retour arrière est impossible puisque « la version précédente » n'a pas de nom ; et le manifest `image: listify-backend:latest` ne change pas quand l'image change, donc Kubernetes ne déclenche aucun rolling update. C'est la raison pour laquelle, au TP 20, le pipeline écrira dans le manifest un tag unique à chaque build.
:::

## 5. Stratégies de branches

### 5.1 Deux philosophies

La façon d'organiser les branches Git conditionne directement la capacité à intégrer et livrer en continu. Deux modèles s'opposent.

<Figure src="branches-strategies" num="24.3" alt="En haut, le trunk-based development : une seule branche main et des branches de quelques heures fusionnées au moins chaque jour. En bas, git-flow : branches main, develop, feature, release et hotfix, avec des fonctionnalités qui vivent des semaines.">
  Trunk-based development et git-flow. Le premier minimise la divergence ; le second structure des versions planifiées au prix d'une divergence longue.
</Figure>

**Git-flow**, proposé par Vincent Driessen en 2010 [^driessen], organise le travail autour de cinq types de branches : `main` ne contient que des versions publiées, `develop` accumule les fonctionnalités terminées, chaque fonctionnalité vit sur une branche `feature/...`, une branche `release/...` stabilise une version avant publication, et une branche `hotfix/...` corrige la production en urgence. Le modèle est clair, et il a été extrêmement populaire.

Le **trunk-based development** [^tbd] fait l'inverse : tout le monde intègre dans une branche unique, le tronc (`main`). Les branches, s'il y en a, sont très courtes (quelques heures, au pire deux jours) et servent seulement à la revue de code par pull request. On livre depuis le tronc, qui doit donc être en permanence dans un état publiable.

[^driessen]: Vincent Driessen, « A successful Git branching model », nvie.com, janvier 2010. En mars 2020, l'auteur a ajouté en tête de l'article une note de réflexion recommandant un flux plus simple, comme GitHub Flow, pour les logiciels livrés en continu, et réservant git-flow aux logiciels explicitement versionnés, dont plusieurs versions coexistent chez les utilisateurs.

[^tbd]: Paul Hammant et al., *Trunk Based Development*, [trunkbaseddevelopment.com](https://trunkbaseddevelopment.com/). Voir aussi Forsgren, Humble, Kim, *Accelerate*, 2018, chapitre 4, qui associe empiriquement cette pratique à de meilleures performances de livraison.

### 5.2 Le débat, argumenté

| Critère | Trunk-based development | Git-flow |
|---|---|---|
| Divergence entre développeurs | Heures | Semaines |
| Compatibilité avec l'intégration continue | Totale (c'est sa définition) | Faible : les branches `feature` ne sont pas intégrées quotidiennement |
| Livraison continue | Naturelle, depuis le tronc | Lourde : chaque version passe par `release` |
| Plusieurs versions maintenues en parallèle (logiciel installé chez des clients) | Difficile | Adapté |
| Exigence de discipline | Élevée : tronc toujours vert, tests solides, travail inachevé masqué | Moindre au quotidien, mais intégrations coûteuses |

Le trunk-based development est devenu la recommandation dominante pour les services déployés en continu, et c'est le modèle de ce bloc. Git-flow garde sa pertinence pour les logiciels dont plusieurs versions vivent en même temps chez des utilisateurs (une bibliothèque, un logiciel installé sur site), ce que son auteur a lui-même reconnu [^driessen].

### 5.3 Intégrer du travail inachevé : les drapeaux de fonctionnalité

Une objection vient immédiatement : si l'on intègre chaque jour dans le tronc livrable, que faire d'une fonctionnalité qui demande trois semaines ? La réponse est de **séparer le déploiement du code de l'activation de la fonctionnalité**. Le code de la pagination est intégré et déployé progressivement, mais il reste inactif derrière un **drapeau de fonctionnalité** (*feature flag*, ou *feature toggle*) [^hodgson] :

```python title="backend/app.py (extrait)"
PAGINATION = os.environ.get("FEATURE_PAGINATION", "off") == "on"

@app.get("/api/tasks")
def list_tasks():
    if PAGINATION:
        return list_tasks_paginated()   # nouveau code, déployé mais éteint
    ...                                 # comportement actuel, inchangé
```

Le jour venu, on active le drapeau par la configuration (une variable d'environnement, puis un vrai service de drapeaux quand leur nombre grandit), sans nouveau déploiement ; et on le désactive en quelques secondes en cas de problème. La contrepartie est une dette : chaque drapeau double les chemins à tester, et un drapeau oublié devient du code mort. On les supprime dès que la fonctionnalité est stabilisée.

[^hodgson]: Pete Hodgson, « Feature Toggles (aka Feature Flags) », martinfowler.com, 2017. La taxonomie de référence des drapeaux (de livraison, d'expérimentation, d'exploitation, de permission) et de leur coût.

## 6. Stratégies de déploiement

Reste à remplacer la version en production par la nouvelle. Plusieurs stratégies existent, qui arbitrent entre la simplicité, le coût en ressources et la maîtrise du risque.

<Figure src="strategies-deploiement" num="24.4" alt="Trois stratégies : le rolling update remplace les Pods v1 par des v2 un par un ; le blue-green maintient deux environnements complets et bascule le trafic d'un coup ; le canary envoie une petite part du trafic à v2 avant d'élargir.">
  Trois stratégies de déploiement sans coupure. Elles diffèrent par la durée de coexistence des deux versions, les ressources supplémentaires nécessaires et la part d'utilisateurs exposés à une version défectueuse.
</Figure>

### 6.1 Recreate et rolling update

La stratégie la plus simple, **recreate**, arrête toutes les instances de v1 puis démarre celles de v2. Elle provoque une coupure, mais elle garantit que les deux versions ne coexistent jamais, ce qui est parfois nécessaire (une migration de base incompatible avec l'ancienne version).

Le **rolling update**, stratégie par défaut des Deployments Kubernetes (chapitre 22), remplace les instances progressivement. Deux paramètres le gouvernent : `maxSurge`, le nombre de Pods qu'on peut créer **au-dessus** du nombre voulu, et `maxUnavailable`, le nombre de Pods qui peuvent manquer **en dessous**. Tous deux valent 25 % par défaut ; en valeur absolue, `maxSurge` s'arrondit à l'entier supérieur et `maxUnavailable` à l'entier inférieur [^k8s-rolling].

:::exemple[Un rolling update Kubernetes, étape par étape]
Le Deployment du backend de Listify a 3 répliques, avec les valeurs par défaut. On calcule : $\text{maxSurge} = \lceil 0{,}25 \times 3 \rceil = \lceil 0{,}75 \rceil = 1$ et $\text{maxUnavailable} = \lfloor 0{,}25 \times 3 \rfloor = \lfloor 0{,}75 \rfloor = 0$.

Donc, pendant toute la mise à jour, il y a **au plus 4 Pods** et **au moins 3 Pods disponibles**. Le déroulé :

1. Kubernetes crée 1 Pod v2 (total 4 : trois v1, un v2 en démarrage).
2. Dès que le Pod v2 est prêt (sa *readiness probe* réussit), il supprime 1 Pod v1 (total 3 disponibles : deux v1, un v2).
3. Il recommence : un v2 de plus, puis un v1 de moins, jusqu'à trois v2.

Avec 4 répliques, on aurait $\text{maxSurge} = 1$ et $\text{maxUnavailable} = 1$ : Kubernetes peut alors créer un Pod v2 **et** en supprimer un v1 en même temps, et la mise à jour va plus vite, au prix d'une capacité réduite d'un quart pendant la transition. On voit pourquoi la *readiness probe* du chapitre 22 est vitale : sans elle, Kubernetes considérerait un Pod v2 comme prêt dès son démarrage et supprimerait les v1 avant que les v2 puissent servir.
:::

Le rolling update est économe (un seul Pod supplémentaire), mais pendant quelques minutes **les deux versions servent le trafic en même temps**, ce qui impose qu'elles soient compatibles (section 7) ; et un retour arrière est un nouveau rolling update, pas une bascule instantanée.

[^k8s-rolling]: Documentation Kubernetes, « Deployments », section « Rolling Update Deployment » : [kubernetes.io/docs/concepts/workloads/controllers/deployment](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/#rolling-update-deployment).

### 6.2 Blue-green

Le déploiement **blue-green** [^fowler-bg] maintient **deux environnements de production complets**. L'un (disons le bleu) sert le trafic ; on déploie la nouvelle version sur l'autre (le vert), on la teste à loisir, puis on bascule **tout le trafic d'un coup** en changeant le routage (dans Kubernetes, le sélecteur d'un Service ou la règle d'un Ingress). Le bleu reste en place : en cas de problème, on rebascule en quelques secondes. Le prix est le double de ressources pendant la transition, et la base de données, généralement partagée, reste le point délicat.

[^fowler-bg]: Martin Fowler, « BlueGreenDeployment », martinfowler.com/bliki, 2010, d'après la pratique décrite par Humble et Farley.

### 6.3 Canary

Le déploiement **canary** [^sato] tire son nom des canaris qu'on descendait dans les mines de charbon pour détecter les gaz toxiques avant les mineurs. On déploie la nouvelle version sur une petite fraction de l'infrastructure, qui reçoit une petite part du trafic réel (1 %, 5 %) ; on compare ses métriques (taux d'erreurs, latence) à celles de l'ancienne version ; si elles restent bonnes, on élargit progressivement (25 %, 50 %, 100 %) ; sinon, on retire le canari. C'est la seule des trois stratégies qui **valide la nouvelle version sur du trafic réel en limitant le nombre d'utilisateurs exposés**.

:::exemple[Le rayon d'explosion d'un canary]
Listify reçoit 10 000 requêtes par minute. La version v2 contient un bogue qui fait échouer 10 % des requêtes qu'elle traite. L'alerte sur le taux d'erreurs (chapitre 26) met 10 minutes à se déclencher et à provoquer le retrait.

- **Déploiement complet** (rolling update jusqu'au bout avant détection) : $10\,000 \times 0{,}10 \times 10 = 10\,000$ requêtes en erreur.
- **Canary à 5 %** : v2 ne reçoit que $500$ requêtes par minute, d'où $500 \times 0{,}10 \times 10 = 500$ requêtes en erreur, vingt fois moins.

Il y a une contrepartie : avec 5 % du trafic, le signal est plus faible. Le taux d'erreurs **global** ne passe que de la valeur habituelle à $0{,}05 \times 10\,\% = 0{,}5$ point de plus, ce qui peut rester sous un seuil d'alerte global. C'est pourquoi on compare le canari **à lui-même** : son taux d'erreurs propre (10 %) contre celui des instances v1. L'analyse canary est donc indissociable d'une bonne observabilité, que les métriques soient étiquetées par version.
:::

[^sato]: Danilo Sato, « CanaryRelease », martinfowler.com/bliki, 2014.

### 6.4 Synthèse

| Stratégie | Coupure | Coexistence des versions | Ressources en plus | Retour arrière | Exposition à une version défectueuse |
|---|---|---|---|---|---|
| Recreate | Oui | Non | Aucune | Redéploiement | Tous, pendant la coupure puis après |
| Rolling update | Non | Oui, pendant la transition | Faibles (`maxSurge`) | Nouveau rolling update | Croissante, jusqu'à tous |
| Blue-green | Non | Non (bascule franche) | Doubles, temporairement | Instantané (rebascule) | Tous, dès la bascule |
| Canary | Non | Oui, volontairement | Faibles | Rapide (retrait du canari) | Une petite fraction, maîtrisée |

## 7. Changer sans casser : compatibilité et migrations

Dès que deux versions coexistent, même quelques minutes pendant un rolling update, elles partagent la même base de données. Toute migration de schéma doit donc être **compatible avec les deux versions à la fois**. La technique standard s'appelle **expand/contract** (ou *parallel change*) [^parallel] : on élargit d'abord le schéma pour accueillir l'ancienne et la nouvelle version, on migre, puis on le resserre.

:::exemple[Renommer une colonne sans coupure]
On veut renommer la colonne `title` de la table `tasks` en `label`. Le faire en une seule étape (`ALTER TABLE tasks RENAME COLUMN title TO label`) casse immédiatement toutes les instances v1 encore en service pendant le rolling update, qui interrogent `title`. En expand/contract, on procède en trois déploiements :

1. **Expand.** On ajoute la colonne `label`, nullable, et on la remplit à partir de `title`. On déploie une version v1.1 qui **écrit dans les deux colonnes** et lit toujours `title`. L'ancienne v1 et la v1.1 cohabitent sans problème.
2. **Migrate.** On déploie une version v2 qui **lit `label`** et écrit toujours dans les deux. Si v2 pose problème, revenir à v1.1 est sans danger : `title` est à jour.
3. **Contract.** Une fois v2 stabilisée, on déploie une version v2.1 qui n'écrit plus que `label`, puis on supprime la colonne `title`.

Trois déploiements au lieu d'un : c'est le prix de l'absence de coupure, et c'est une des raisons pour lesquelles les équipes qui déploient souvent préfèrent les petits changements.
:::

La même logique s'applique aux API entre services (on ajoute un champ avant de l'exiger, on cesse de l'utiliser avant de le supprimer) et justifie la distinction entre **retour arrière** (*rollback*, revenir à la version précédente) et **correction en avant** (*roll forward*, déployer vite une version corrigée). Le retour arrière n'est sûr que si la base est restée compatible avec l'ancienne version ; sinon, seule la correction en avant est possible.

[^parallel]: Danilo Sato, « ParallelChange », martinfowler.com/bliki, 2014. Voir aussi Scott Ambler, Pramod Sadalage, *Refactoring Databases: Evolutionary Database Design*, Addison-Wesley, 2006.

## 8. Mesurer la performance de livraison

Comment savoir si une équipe livre bien ? Le programme de recherche **DORA** (*DevOps Research and Assessment*), mené par Nicole Forsgren, Jez Humble et Gene Kim sur les enquêtes annuelles *State of DevOps* de 2014 à 2017, a identifié quatre indicateurs qui prédisent la performance des équipes [^accelerate] :

| Indicateur | Question | Famille |
|---|---|---|
| **Fréquence de déploiement** | À quelle fréquence déploie-t-on en production ? | Débit |
| **Délai de mise en production des changements** (*lead time for changes*) | Combien de temps entre un commit et sa mise en production ? | Débit |
| **Taux d'échec des changements** (*change failure rate*) | Quelle proportion des déploiements provoque un incident ou exige une correction ? | Stabilité |
| **Délai de rétablissement** (*time to restore service*) | Combien de temps faut-il pour rétablir le service après un incident ? | Stabilité |

Le résultat central de ces travaux contredit une intuition répandue : le débit et la stabilité ne s'opposent **pas**. Les équipes les plus performantes déploient à la fois **plus souvent** et avec **moins d'échecs**, et rétablissent le service plus vite. Dans le rapport 2019, la catégorie « élite » déployait à la demande, plusieurs fois par jour, avec un délai de mise en production inférieur à un jour, un rétablissement en moins d'une heure et un taux d'échec compris entre 0 et 15 % [^sodo2019]. L'explication rejoint le chapitre 23 : de petits changements fréquents sont plus faciles à tester, à comprendre et à annuler.

:::exemple[Calculer les indicateurs DORA de Listify]
Journal de production de Listify sur 10 jours ouvrés : 20 déploiements. Pour les délais de mise en production, on a mesuré, pour chaque déploiement, le temps entre le commit le plus ancien qu'il contenait et sa mise en production ; triés, les 20 délais (en heures) sont :

$$
1,\ 1,\ 2,\ 2,\ 2,\ 3,\ 3,\ 3,\ 4,\ 4,\ 5,\ 5,\ 6,\ 6,\ 8,\ 10,\ 12,\ 20,\ 26,\ 50.
$$

Deux déploiements ont provoqué un incident : le premier a été rétabli en 25 minutes (retour arrière), le second en 95 minutes (correction en avant).

- **Fréquence de déploiement** : $20 / 10 = 2$ déploiements par jour ouvré.
- **Délai de mise en production** : on prend la **médiane**, peu sensible aux valeurs extrêmes comme le déploiement à 50 h. Avec 20 valeurs, c'est la moyenne des 10ᵉ et 11ᵉ : $(4 + 5)/2 = 4{,}5$ heures. La moyenne, elle, vaudrait $173/20 = 8{,}65$ heures, tirée vers le haut par deux ou trois changements restés bloqués en revue.
- **Taux d'échec des changements** : $2 / 20 = 10\,\%$.
- **Délai de rétablissement** : médiane de $\{25, 95\}$, soit 60 minutes. Avec si peu d'incidents, l'indicateur est fragile : on le suit sur plusieurs mois.

Listify serait donc classé très haut : délai inférieur à un jour, taux d'échec dans la fourchette de l'élite. Le chiffre le plus instructif est pourtant l'écart entre médiane et moyenne du délai : il signale que quelques changements restent coincés, ce qui mérite une enquête (revues de code trop lentes ?).
:::

Deux précautions s'imposent. D'abord, ces indicateurs mesurent un **système**, pas des individus : les utiliser pour noter des personnes les corrompt immédiatement, selon la loi de Goodhart (« quand une mesure devient un objectif, elle cesse d'être une bonne mesure »). Ensuite, ils évoluent : le rapport 2023 a par exemple précisé le quatrième indicateur en « délai de rétablissement après un déploiement en échec ». Retenez les quatre questions plutôt que les seuils d'une année donnée.

[^accelerate]: Nicole Forsgren, Jez Humble, Gene Kim, *Accelerate: The Science of Lean Software and DevOps*, IT Revolution, 2018, chapitres 2 et suivants, et annexe méthodologique.

[^sodo2019]: DORA, Google Cloud, *Accelerate State of DevOps Report 2019*, 2019.

## Ce qu'il faut retenir

<div className="retenir">

1. **Livraison continue** : le logiciel est déployable à tout moment, le déploiement en production reste une décision humaine. **Déploiement continu** : tout changement qui passe le pipeline part en production automatiquement. Le pipeline est le même ; seule la dernière porte change, selon le contexte.
2. **Construire une fois, promouvoir ensuite** : c'est la même image, identifiée par son digest, qui traverse dev, préproduction et production. Seule la **configuration** change (Twelve-Factor, facteurs III et V).
3. **SemVer** : MAJEUR pour une rupture, MINEUR pour un ajout compatible, CORRECTIF pour une correction. **Tag** mobile et lisible, **digest** immuable ; jamais `latest` en production.
4. **Trunk-based development** (branches de quelques heures, tronc toujours livrable, drapeaux de fonctionnalité) contre **git-flow** (branches longues, versions planifiées). Le premier est la norme pour les services livrés en continu.
5. **Recreate** (coupure), **rolling update** (progressif, économe, versions qui coexistent), **blue-green** (bascule franche, ressources doubles), **canary** (petite fraction du trafic réel, exposition maîtrisée). Rolling update Kubernetes : `maxSurge` arrondi au-dessus, `maxUnavailable` en dessous.
6. Quand deux versions coexistent, la base doit convenir aux deux : migrations **expand/contract**. Un retour arrière n'est sûr que si le schéma est resté compatible.
7. Indicateurs **DORA** : fréquence de déploiement, délai de mise en production, taux d'échec, délai de rétablissement. Débit et stabilité vont ensemble chez les meilleures équipes.

</div>

## Regard recherche

:::recherche
La livraison continue est l'un des rares domaines de l'ingénierie logicielle où l'on dispose d'une recherche empirique à grande échelle, et de retours d'expérience industriels publiés :

- **Nicole Forsgren, Jez Humble, Gene Kim, *Accelerate*, IT Revolution, 2018.** La synthèse de quatre années d'enquêtes *State of DevOps*, avec une annexe qui expose la méthode statistique (modélisation par équations structurelles). Lisez la partie II, consacrée à la méthode, avant de citer les résultats : c'est un modèle de rigueur en recherche par enquête, et une leçon sur ce qu'on peut et ne peut pas conclure d'une corrélation.
- **Tony Savor, Mitchell Douglas, Michael Gentili, Laurie Williams, Kent Beck, Michael Stumm, « Continuous Deployment at Facebook and OANDA », *FSE (Industry Track)*, 2016.** Comment deux entreprises très différentes pratiquent le déploiement continu, et ce que cela change à la productivité et à la qualité.
- **Ze Li et al., « Gandalf: An Intelligent, End-To-End Analytics Service for Safe Deployment in Cloud-Scale Infrastructure », *NSDI*, 2020.** Chez Microsoft Azure, un système qui surveille chaque déploiement progressif et décide automatiquement de l'arrêter : l'analyse canary à l'échelle d'un cloud.

Piste d'innovation : l'**analyse canary automatique**, qui doit décider avec peu de données et vite si une nouvelle version est dégradée, est un problème de tests statistiques séquentiels encore ouvert, notamment pour les métriques bruitées comme la latence.
:::

## Bibliographie du chapitre

<div className="biblio">

### Sources primaires

- Jez Humble, David Farley, *Continuous Delivery*, Addison-Wesley, 2010. Le livre fondateur ; les chapitres 1, 5 (pipeline de déploiement) et 10 (déploiement et publication) couvrent ce chapitre.
- Tom Preston-Werner, *Semantic Versioning 2.0.0* : [semver.org](https://semver.org/lang/fr/).
- Adam Wiggins, *The Twelve-Factor App* : [12factor.net](https://12factor.net/fr/).
- Documentation Kubernetes, « Deployments » : stratégies et paramètres du rolling update.

### Lectures recommandées

- Nicole Forsgren, Jez Humble, Gene Kim, *Accelerate*, IT Revolution, 2018.
- Les articles de Martin Fowler et de ses coauteurs cités dans le chapitre : « BlueGreenDeployment », « CanaryRelease », « ParallelChange », « Feature Toggles ».
- Vincent Driessen, « A successful Git branching model », 2010, **avec** sa note de 2020 : un bel exemple d'auteur qui révise publiquement sa recommandation.

### Pour aller plus loin

- Les rapports annuels *Accelerate State of DevOps* : [dora.dev](https://dora.dev/).
- Betsy Beyer et al. (dir.), *The Site Reliability Workbook*, O'Reilly, 2018, chapitre 16 (« Canarying Releases »). Gratuit en ligne : [sre.google/workbook](https://sre.google/workbook/table-of-contents/).

</div>
