---
title: "Ch. 25 : GitOps"
sidebar_label: "Ch. 25 : GitOps"
hide_title: true
---

import ChapterHead from '@site/src/components/ChapterHead';
import Figure from '@site/src/components/Figure';

<ChapterHead
  kicker="Semestre 2 · Bloc 3 · Chapitre 25"
  title="GitOps : Git comme source de vérité de la production"
  lecture="35 min"
  competences={['C1', 'C2', 'C5']}
/>

:::objectifs
À l'issue de ce chapitre, vous saurez :

- énoncer les quatre principes du GitOps et les rattacher à la réconciliation du bloc 2 ;
- comparer déploiement poussé et déploiement tiré, notamment du point de vue de la sécurité ;
- décrire le fonctionnement d'Argo CD : état désiré, état réel, synchronisation, auto-réparation ;
- écrire une ressource `Application` d'Argo CD et justifier la séparation entre dépôt d'application et dépôt de configuration ;
- gérer les secrets dans une chaîne GitOps, et reconstruire un cluster depuis Git ;
- situer les limites du modèle.
:::

## 1. Ce qui reste fragile après le chapitre 24

Supposons que le pipeline de Listify aille jusqu'au bout de la façon la plus directe : après avoir construit et scanné l'image, sa dernière étape exécute `helm upgrade` ou `kubectl apply` contre le cluster de production. Tout est automatisé. Quatre problèmes subsistent pourtant, et ils sont sérieux.

1. **La CI détient les clés de la production.** Pour appliquer des manifests, le runner doit posséder des identifiants avec des droits d'écriture sur le cluster. Le chapitre 23 a montré que la chaîne de CI fait partie de la surface d'attaque ; ici, compromettre la CI, c'est compromettre la production.
2. **La réalité peut diverger silencieusement.** Rien n'empêche un administrateur pressé de taper `kubectl scale deployment backend --replicas=1` un soir d'incident, ou `kubectl edit` pour corriger une variable. Le cluster ne correspond plus à ce que décrivent les fichiers, et personne ne le sait jusqu'au prochain déploiement, qui écrase ou non la modification selon les cas. C'est la **dérive de configuration** du chapitre 9, revenue par la porte de derrière.
3. **La question « qu'est-ce qui tourne en production, et depuis quand ? » n'a pas de réponse simple.** Il faut interroger le cluster, fouiller les journaux de la CI, recouper.
4. **Reconstruire est difficile.** Si le cluster disparaît, il faut rejouer une série de pipelines dans le bon ordre, en espérant que chacun soit encore capable de s'exécuter.

Le **GitOps** répond aux quatre à la fois, avec une idée que vous connaissez déjà : l'état désiré décrit dans des fichiers, et une boucle de réconciliation qui fait converger la réalité. La nouveauté est **où** vit l'état désiré (dans Git) et **qui** fait converger (un agent dans le cluster, pas la CI).

## 2. Définition et principes

Le terme a été proposé en 2017 par Alexis Richardson, alors dirigeant de Weaveworks, pour décrire la façon dont son entreprise exploitait ses clusters Kubernetes : toute opération passe par une pull request [^richardson]. En 2021, le groupe de travail GitOps de la CNCF a publié une définition neutre en quatre principes, le projet **OpenGitOps** [^opengitops] :

:::definition[GitOps (OpenGitOps 1.0)]
Ensemble de principes pour exploiter un système dont l'état désiré est :

1. **déclaratif** : le système est décrit par un état voulu, pas par une suite de commandes ;
2. **versionné et immuable** : cet état est stocké de façon à conserver un historique complet et immuable des versions ;
3. **tiré automatiquement** : des agents logiciels récupèrent automatiquement les déclarations d'état désiré depuis la source ;
4. **réconcilié en continu** : des agents observent en permanence l'état réel du système et tentent de le faire correspondre à l'état désiré.
:::

Relisez ces quatre principes à la lumière du parcours. Le premier est celui de Terraform et des manifests Kubernetes. Le deuxième est ce que Git fait par construction : chaque commit est une version immuable, identifiée par son empreinte, avec son auteur, sa date et sa raison. Le quatrième est **exactement** la boucle de réconciliation du chapitre 20, appliquée non plus à un Deployment mais à l'ensemble de la production. Seul le troisième, le **pull**, est vraiment nouveau, et c'est lui qui change la sécurité.

Git n'est d'ailleurs pas exigé par la définition : le deuxième principe parle d'un stockage versionné et immuable. Mais Git s'est imposé, parce que les équipes y ont déjà leur code, leurs revues et leurs habitudes.

[^richardson]: Alexis Richardson, « GitOps: Operations by Pull Request », blog de Weaveworks, août 2017.

[^opengitops]: CNCF GitOps Working Group, *OpenGitOps Principles v1.0.0*, 2021. [opengitops.dev](https://opengitops.dev/).

## 3. Pousser ou tirer

<Figure src="push-vs-pull" num="25.1" alt="En haut, en mode push, le pipeline CI détient les identifiants du cluster et y applique les manifests ; le cluster doit accepter des connexions entrantes. En bas, en mode pull, la CI n'écrit que dans Git, et un agent GitOps installé dans le cluster observe Git et applique les changements.">
  Déploiement poussé contre déploiement tiré. En mode pull, aucun identifiant du cluster ne sort du cluster, et la CI n'a plus aucun droit sur la production.
</Figure>

Dans le **mode poussé** (*push*), un système extérieur au cluster (la CI) se connecte au cluster et y applique les changements. Dans le **mode tiré** (*pull*), un agent qui tourne **dans** le cluster va lui-même chercher l'état désiré dans Git et l'applique localement. La différence semble topologique ; elle est surtout une affaire de confiance.

| Critère | Push (CI applique) | Pull (agent GitOps) |
|---|---|---|
| Qui détient les droits d'écriture sur le cluster ? | La CI, hors du cluster | L'agent, dans le cluster |
| Le cluster accepte-t-il des connexions entrantes ? | Oui, depuis la CI | Non : l'agent sort vers Git, rien n'entre |
| Que donne une CI compromise ? | Un accès à la production | Un accès en écriture à Git, donc des commits visibles et relus |
| Détection de la dérive | Au prochain déploiement, au mieux | Continue |
| Déploiement vers plusieurs clusters | La CI doit joindre chacun | Chaque cluster tire lui-même |

Le troisième critère mérite qu'on s'y arrête. En mode pull, tout changement de la production **est** un commit. Même un attaquant qui aurait compromis la CI doit passer par Git, où son changement laisse une trace, peut être refusé en revue, et s'annule par `git revert`. La production n'est plus une cible qu'on attaque directement, mais le reflet d'un dépôt qu'on protège par les moyens habituels : revue obligatoire, branches protégées, commits signés.

## 4. La boucle GitOps, avec Argo CD

### 4.1 Argo CD

Deux agents GitOps dominent l'écosystème Kubernetes : **Argo CD**, créé chez Intuit en 2018, et **Flux**, créé chez Weaveworks. Tous deux sont des projets diplômés de la CNCF depuis 2022, le plus haut niveau de maturité de la fondation [^cncf-grad]. Ce cours utilise Argo CD, dont l'interface web rend la réconciliation particulièrement visible ; Flux repose sur les mêmes principes, avec des objets différents.

Argo CD est lui-même une application Kubernetes : un ensemble de contrôleurs installés dans le cluster (dans l'espace de noms `argocd`), avec une API, une interface web et une ligne de commande. On lui décrit ce qu'il doit surveiller par une ressource personnalisée, l'**Application**, qui relie une **source** (un dépôt Git, un chemin, une révision) à une **destination** (un cluster, un espace de noms).

[^cncf-grad]: CNCF, annonces de graduation de Flux (novembre 2022) et d'Argo (décembre 2022). [cncf.io/projects](https://www.cncf.io/projects/).

### 4.2 Désiré, réel, et ce qu'Argo CD en fait

<Figure src="gitops-boucle" num="25.2" alt="L'équipe modifie le dépôt Git par pull request ; Argo CD lit l'état désiré dans Git et l'état réel dans le cluster, puis applique la différence ; une modification manuelle par kubectl edit crée une dérive, qu'Argo CD annule automatiquement.">
  La boucle GitOps. Argo CD compare en permanence l'état désiré (Git) et l'état réel (le cluster) ; tout écart est soit une nouvelle version à appliquer, soit une dérive à annuler.
</Figure>

Pour chaque Application, Argo CD calcule deux états, qu'il affiche en permanence :

- **l'état de synchronisation** : `Synced` si les ressources du cluster correspondent aux manifests de Git, `OutOfSync` sinon ;
- **l'état de santé** : `Healthy` si les ressources fonctionnent (le Deployment a ses répliques prêtes), `Progressing` pendant un rolling update, `Degraded` si quelque chose ne va pas.

Les deux sont indépendants, et la distinction est précieuse en diagnostic : une Application peut être `Synced` et `Degraded` (on a fidèlement déployé une image qui plante), ou `OutOfSync` et `Healthy` (tout fonctionne, mais quelqu'un a modifié le cluster à la main).

Trois options de la politique de synchronisation déterminent le comportement de la boucle :

| Option | Effet | Sans elle |
|---|---|---|
| `automated` | Argo CD applique de lui-même tout nouveau commit | Il affiche `OutOfSync` et attend qu'un humain clique sur *Sync* : c'est de la **livraison** continue au sens du chapitre 24 |
| `prune: true` | Une ressource supprimée de Git est supprimée du cluster | Elle reste orpheline dans le cluster |
| `selfHeal: true` | Une modification manuelle du cluster est annulée | La dérive est signalée (`OutOfSync`) mais conservée |

Par défaut, Argo CD interroge le dépôt Git toutes les trois minutes ; on peut configurer la forge pour qu'elle le prévienne immédiatement par un *webhook* à chaque push. Côté cluster, en revanche, il observe les ressources en continu par le mécanisme de *watch* de l'API Kubernetes (chapitre 20) : une dérive est vue en quelques secondes.

:::exemple[Une dérive, annulée]
Listify est déployé par Argo CD avec `automated`, `prune` et `selfHeal`. Le manifest du dépôt de configuration déclare 3 répliques pour le backend. Un soir, pour « soulager » un nœud, un administrateur tape :

```bash
kubectl -n listify scale deployment backend --replicas=1
```

Voici ce qui se passe, et dans quel ordre :

1. L'API Kubernetes enregistre `replicas: 1` ; le contrôleur de ReplicaSet (chapitre 20) commence à supprimer deux Pods.
2. Argo CD, qui observe le Deployment, constate que son état réel (1 réplique) diffère de l'état désiré dans Git (3) : l'Application passe `OutOfSync`.
3. Comme `selfHeal` est actif, Argo CD réapplique le manifest de Git après un court délai : `replicas` revient à 3, et le contrôleur recrée les Pods.
4. L'historique d'Argo CD garde la trace de l'opération d'auto-réparation.

La modification manuelle aura vécu quelques secondes. La leçon n'est pas qu'il est impossible de changer le nombre de répliques, mais qu'il faut le faire **dans Git** : une pull request qui passe `replicas` à 1, relue, justifiée, et annulable par `git revert`. Le soir de l'incident, on peut aussi suspendre temporairement l'auto-réparation, mais c'est alors un acte explicite et visible.
:::

### 4.3 La ressource Application

Voici l'Application qui déploie Listify au TP 20. Argo CD sait lire directement un chart Helm, comme celui du TP 18 :

```yaml title="argocd/listify.yaml"
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: listify
  namespace: argocd                 # les Application vivent dans l'espace de noms d'Argo CD
spec:
  project: default
  source:
    repoURL: http://gitea.local:3000/equipe/listify-config.git
    targetRevision: main            # la branche qui fait foi
    path: chart                     # le chart Helm de Listify dans ce dépôt
    helm:
      valueFiles:
        - values-prod.yaml
  destination:
    server: https://kubernetes.default.svc   # le cluster où tourne Argo CD lui-même
    namespace: listify
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

On remarque que l'Application est elle-même un manifest déclaratif. On peut donc la versionner dans Git et la faire gérer par Argo CD, qui se gère alors en partie lui-même : c'est le motif dit **app of apps**, où une Application racine pointe vers un dossier contenant toutes les autres.

## 5. Deux dépôts : l'application et sa configuration

La figure d'architecture du bloc sépare deux dépôts, et ce choix, recommandé par la documentation d'Argo CD [^argo-bp], mérite d'être justifié.

- Le **dépôt d'application** contient le code de Listify, ses tests, ses Containerfile et son workflow de CI. Il change à chaque modification de code.
- Le **dépôt de configuration** contient les manifests ou le chart, avec les valeurs de chaque environnement, dont le **tag de l'image** à déployer. C'est lui qu'Argo CD observe.

Le lien entre les deux est la dernière étape du pipeline de CI : une fois l'image construite, scannée et poussée, le pipeline fait un commit dans le dépôt de configuration qui remplace l'ancien tag par le nouveau. C'est tout. La CI n'a aucun droit sur le cluster ; elle a seulement le droit d'écrire dans un dépôt.

Pourquoi ne pas tout mettre dans un seul dépôt ?

1. **Éviter les boucles.** Si la CI commitait le nouveau tag dans le dépôt du code, ce commit déclencherait à son tour la CI, qui reconstruirait une image, qui changerait le tag...
2. **Séparer les droits.** Tous les développeurs écrivent dans le dépôt d'application ; seuls quelques-uns, et le compte de la CI, devraient pouvoir modifier ce qui part en production.
3. **Un historique lisible de la production.** Le journal du dépôt de configuration **est** le journal des mises en production : chaque commit est un déploiement, avec sa date et sa raison.
4. **Des rythmes différents.** On peut modifier la configuration de production (passer de 3 à 5 répliques) sans toucher au code, et inversement.

:::exemple[Combien de temps entre le commit et la production ?]
Un développeur pousse une correction sur `main` à 14 h 00. Mesures sur la chaîne du TP 20 : le pipeline de CI dure 7 minutes et se termine par le commit du nouveau tag ; Argo CD interroge Git toutes les 3 minutes, sans webhook ; le rolling update de 3 répliques prend environ 1 minute.

- **Au mieux**, Argo CD interroge Git juste après le commit de la CI : $7 + 0 + 1 = 8$ minutes, mise en production à 14 h 08.
- **Au pire**, il vient de l'interroger juste avant : $7 + 3 + 1 = 11$ minutes, à 14 h 11.
- **En moyenne**, l'attente de la prochaine interrogation vaut la moitié de l'intervalle, $1{,}5$ minute : environ $9{,}5$ minutes.

Avec un webhook de la forge vers Argo CD, l'attente tombe à quelques secondes et le délai à environ 8 minutes : le terme dominant devient la CI, qu'on optimise avec les techniques du chapitre 23. En termes DORA (chapitre 24), c'est un délai de mise en production de l'ordre de dix minutes, sans aucune intervention humaine après la fusion.
:::

[^argo-bp]: Documentation d'Argo CD, « Best Practices », section « Separating Config Vs. Source Code Repositories » : [argo-cd.readthedocs.io/en/stable/user-guide/best_practices](https://argo-cd.readthedocs.io/en/stable/user-guide/best_practices/).

Des outils automatisent ce commit de tag sans passer par la CI (Argo CD Image Updater, l'automatisation d'images de Flux) : ils surveillent le registre et mettent à jour Git dès qu'une nouvelle image apparaît. Le principe est le même ; seul l'acteur qui écrit dans Git change.

## 6. Les secrets, point dur du GitOps

Si tout l'état désiré est dans Git, où mettre le mot de passe de PostgreSQL ? Certainement pas en clair dans le dépôt : un secret committé une fois reste dans l'historique pour toujours, et Git est fait pour être cloné. Rappel du bloc 2 : le champ `data` d'un Secret Kubernetes est encodé en base64, ce qui est un **encodage**, pas un **chiffrement** ; `echo Y2ktcGFzc3dvcmQ= | base64 -d` le décode instantanément.

Trois familles de solutions coexistent :

| Approche | Principe | Exemple |
|---|---|---|
| Chiffrer dans Git | Le secret est committé **chiffré** avec une clé publique ; seul un contrôleur dans le cluster possède la clé privée pour le déchiffrer | Sealed Secrets (Bitnami) |
| Chiffrer les valeurs d'un fichier | Les valeurs d'un fichier YAML sont chiffrées, les clés restent lisibles ; l'agent GitOps déchiffre au moment d'appliquer | SOPS (initialement Mozilla), avec age ou un KMS |
| Référencer un coffre externe | Git ne contient qu'une **référence** (« le secret `listify/db` du coffre ») ; un opérateur va chercher la valeur dans un gestionnaire de secrets | External Secrets Operator, avec Vault ou le gestionnaire d'un cloud |

La troisième approche est la plus répandue en entreprise : elle garde les secrets là où leur accès est contrôlé et audité, et Git ne contient que la description de ce qui doit exister. Au TP 20, on se contentera de créer le Secret de la base à la main, une seule fois, hors de Git, en le signalant comme une exception au modèle ; c'est honnête et suffisant pour un cluster de poste de travail.

## 7. Retour arrière et reconstruction

Deux propriétés découlent directement des principes, et elles valent à elles seules l'adoption du modèle.

**Le retour arrière est un `git revert`.** La version 1.6.0 de Listify pose problème ? On annule le commit du dépôt de configuration qui a introduit le tag `1.6.0`. Le dépôt redevient identique à l'état précédent, Argo CD voit la différence et déploie l'ancienne image. Le retour arrière est ainsi une opération ordinaire, relue et tracée, et non une manipulation d'urgence en ligne de commande.

**La reconstruction est un démarrage.** Puisque tout l'état désiré est dans Git, reconstruire la production consiste à créer un cluster neuf, à y installer Argo CD et à lui donner l'Application racine : il déploie tout le reste, dans l'état exact du dépôt.

:::warning[Git ne contient pas vos données]
La reconstruction depuis Git restaure la **configuration** : les Deployments, les Services, les StatefulSet, les volumes **déclarés**. Elle ne restaure pas le **contenu** des volumes. Les tâches enregistrées dans le PostgreSQL de Listify vivent dans un PersistentVolume ; si le cluster est perdu avec ses disques, elles sont perdues, et Argo CD recréera fidèlement une base... vide. Le GitOps ne dispense pas des sauvegardes du TP 4 ; il les rend au contraire plus faciles à tester, puisqu'on peut reconstruire un environnement complet pour vérifier qu'une restauration fonctionne.
:::

## 8. Limites et critiques

Le GitOps n'est pas une solution universelle, et un ingénieur doit en connaître les angles morts.

- **L'ordre des opérations.** Un état désiré n'a pas d'ordre, mais certaines opérations en ont : une migration de base doit précéder le déploiement du code qui l'utilise. Argo CD propose des mécanismes pour cela (les *sync waves* et les *hooks*), mais on réintroduit alors de l'impératif dans un modèle déclaratif.
- **Git n'est pas une base de données.** Des milliers d'environnements éphémères (un par pull request) ou des valeurs qui changent à chaque minute s'accommodent mal d'un historique Git. Le modèle convient à ce qui change à l'échelle humaine.
- **Le système doit être déclaratif.** Le GitOps s'applique naturellement à Kubernetes, dont toute l'API est déclarative et réconciliée. Pour des machines classiques, on retombe sur Terraform et Ansible lancés par une CI, c'est-à-dire sur un modèle poussé.
- **La complexité s'ajoute.** Argo CD est une application de plus à installer, mettre à jour, sécuriser et surveiller. Pour une petite équipe avec un seul cluster, un pipeline qui exécute `helm upgrade` peut rester un choix raisonnable, à condition de mesurer ce qu'on perd (dérive non détectée, droits de la CI).

## Ce qu'il faut retenir

<div className="retenir">

1. Un pipeline qui applique lui-même les manifests laisse quatre problèmes : **la CI détient les clés** de la production, la **dérive** passe inaperçue, l'état de la production est difficile à connaître, la **reconstruction** est laborieuse.
2. **OpenGitOps** : état désiré **déclaratif**, **versionné et immuable**, **tiré automatiquement**, **réconcilié en continu**. C'est la réconciliation du chapitre 20 appliquée à toute la production, avec Git pour source.
3. **Pull contre push** : en pull, aucun identifiant du cluster ne sort du cluster, rien n'y entre, et tout changement de la production est un commit relu et annulable.
4. **Argo CD** : ressource `Application` (source Git, destination cluster), états **Synced/OutOfSync** et **Healthy/Progressing/Degraded**, options `automated`, `prune`, `selfHeal`. Git interrogé toutes les 3 minutes par défaut, cluster observé en continu.
5. **Deux dépôts** : le code et sa CI d'un côté, la configuration de production de l'autre. La CI se termine par un commit du nouveau tag.
6. **Secrets** : jamais en clair dans Git (base64 n'est pas un chiffrement). Sealed Secrets, SOPS, ou référence à un coffre externe.
7. **Retour arrière = `git revert`** ; **reconstruction = démarrage d'Argo CD sur un cluster neuf**. Mais Git ne contient pas les données : les sauvegardes restent indispensables.

</div>

## Regard recherche

:::recherche
Le GitOps est une pratique récente et encore peu étudiée par la recherche académique ; les travaux les plus éclairants portent sur ses fondations, la gestion de configuration comme du code et les erreurs de configuration :

- **Chunqiang Tang et al., « Holistic Configuration Management at Facebook », *SOSP*, 2015.** Comment Facebook traite toute sa configuration comme du code : versionnée, relue, testée, déployée progressivement. Un « GitOps avant la lettre » à l'échelle de centaines de milliers de machines.
- **Ben Maurer, « Fail at Scale: Reliability in the Face of Rapid Change », *ACM Queue*, vol. 13, n° 8, 2015.** Chez Facebook, les changements de configuration sont une cause majeure d'incidents ; l'article explique les garde-fous mis en place. Court et très concret.
- **Tianyin Xu, Yuanyuan Zhou, « Systems Approaches to Tackling Configuration Errors: A Survey », *ACM Computing Surveys*, 2015.** L'état de l'art sur les erreurs de configuration, leurs causes et les moyens de les détecter.
- **Brendan Burns et al., « Borg, Omega, and Kubernetes », *ACM Queue*, 2016** (déjà cité au chapitre 19). La section sur la réconciliation explique pourquoi Kubernetes a été conçu autour d'état désiré et de contrôleurs, le socle sur lequel repose le GitOps.
- **Florian Beetz, Simon Harrer, « GitOps: The Evolution of DevOps? », *IEEE Software*, 2022.** Une mise en perspective du GitOps par rapport au DevOps, utile pour situer le discours et le distinguer du marketing.

Piste d'innovation : la **vérification des changements de configuration avant leur application** (détecter qu'une modification de valeurs Helm va casser la production, sans la déployer) est un problème ouvert, entre analyse statique, simulation et apprentissage à partir des incidents passés.
:::

## Bibliographie du chapitre

<div className="biblio">

### Sources primaires

- CNCF GitOps Working Group, *OpenGitOps Principles v1.0.0*, 2021 : [opengitops.dev](https://opengitops.dev/).
- Documentation d'Argo CD : [argo-cd.readthedocs.io](https://argo-cd.readthedocs.io/). En particulier « Core Concepts », « Automated Sync Policy » et « Best Practices ».
- Alexis Richardson, « GitOps: Operations by Pull Request », Weaveworks, 2017.

### Lectures recommandées

- Billy Yuen, Alexander Matyushentsev, Todd Ekenstam, Jesse Suen, *GitOps and Kubernetes*, Manning, 2021. Écrit en partie par des créateurs d'Argo CD.
- Documentation de Flux, « Core Concepts » : [fluxcd.io/flux/concepts](https://fluxcd.io/flux/concepts/). Pour comparer avec l'autre implémentation majeure.

### Pour aller plus loin

- Les articles de la rubrique « Regard recherche ».
- Documentation de Sealed Secrets, de SOPS et d'External Secrets Operator, pour approfondir la section 6.

</div>
