---
title: "Ch. 20 : Le modèle mental de Kubernetes"
sidebar_label: "Ch. 20 : Le modèle mental de Kubernetes"
hide_title: true
---

import ChapterHead from '@site/src/components/ChapterHead';
import Figure from '@site/src/components/Figure';

<ChapterHead
  kicker="Semestre 2 · Bloc 2 · Chapitre 20"
  title="Le modèle mental de Kubernetes, la réconciliation"
  lecture="10 min"
/>

:::objectifs
À l'issue de ce chapitre, vous saurez :

- expliquer l'API déclarative de Kubernetes et le principe « on décrit l'état désiré » ;
- décrire précisément une **boucle de réconciliation** (observer, comparer, agir) et l'exécuter mentalement ;
- nommer et situer les composants du plan de contrôle (API server, etcd, scheduler, controller manager) et des nœuds (kubelet, kube-proxy, runtime) ;
- suivre le trajet complet d'un `kubectl apply`, du clavier au conteneur en marche.

**C'est le chapitre le plus important du bloc.** Qui tient le modèle de réconciliation comprend *tout* le reste de Kubernetes ; qui l'ignore apprend des commandes par cœur et se perd à la première panne.
:::

## 1. L'API déclarative : décrire, pas commander

Toute interaction avec Kubernetes passe par la même idée, que vous connaissez depuis le S1 : vous **décrivez l'état voulu** dans un objet (un fichier YAML), et vous le soumettez. Vous ne dites jamais *comment* faire ; vous dites *ce que vous voulez*.

```yaml title="Exemple : je veux 3 répliques de nginx"
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  replicas: 3               # ← l'état DÉSIRÉ : 3, en permanence
  selector:
    matchLabels: { app: web }
  template:
    metadata:
      labels: { app: web }
    spec:
      containers:
        - name: nginx
          image: nginx:1.27
```

`kubectl apply -f web.yaml` soumet cet objet. Vous n'avez pas dit « crée 3 conteneurs » ; vous avez déclaré « l'état correct de ce système comporte 3 répliques ». Kubernetes va s'employer, **en permanence**, à ce que ce soit vrai. Si un Pod meurt, il en recrée un ; si une machine tombe, il replace les Pods ailleurs ; si vous éditez `replicas: 5`, il en ajoute deux. Vous n'intervenez plus.

C'est le facteur commun avec Terraform (`.tf` = état désiré) et Ansible (playbook = état désiré) du S1. **La nouveauté de Kubernetes est que la convergence n'a pas lieu une fois, à la commande, mais _en boucle, sans fin_.**

## 2. La boucle de réconciliation, cœur de tout

### 2.1 Le mécanisme

Kubernetes est fait de dizaines de **contrôleurs** (*controllers*), chacun responsable d'un type d'objet. Tous suivent la **même boucle**, tournée en continu :

<Figure src="reconciliation" num="20.1" alt="Boucle : observer l'état réel, le comparer à l'état désiré ; s'il est conforme ne rien faire, sinon agir ; puis observer à nouveau, indéfiniment.">
  La boucle de réconciliation, commune à tous les contrôleurs. Elle ne s'arrête jamais : c'est ce qui rend le système auto-réparateur.
</Figure>

Prenons le contrôleur de ReplicaSet, avec notre exemple `replicas: 3` :

1. **Observer** : combien de Pods `app=web` existent réellement ? Disons 2 (un a planté).
2. **Comparer** : désiré = 3, réel = 2. Écart.
3. **Agir** : créer 1 Pod. Puis la boucle recommence.

Quand un Pod meurt, l'écart réapparaît, le contrôleur agit à nouveau. **Personne ne lui a dit « recrée le Pod »** : il maintient un invariant, indéfiniment. C'est exactement la promesse « je veux 3 répliques » tenue mécaniquement.

### 2.2 Pourquoi c'est si robuste

Ce modèle a des propriétés remarquables, qui expliquent la fiabilité de Kubernetes et sont des points d'examen :

- **Auto-réparation gratuite** : la réparation n'est pas un mécanisme *en plus*, c'est la conséquence directe de la boucle. Tout écart (panne, suppression accidentelle) est corrigé au tour suivant.
- **Robustesse aux redémarrages** : si un contrôleur redémarre, il **ré-observe** l'état réel et repart de là. Il n'a pas besoin de mémoire de ce qu'il « était en train de faire » : l'état désiré (dans etcd) et l'état réel suffisent. Le système est **sans état** dans son pilotage.
- **Convergence, pas transition** : on ne décrit jamais « passe de 2 à 3 » ; on décrit « 3 », et la boucle trouve le chemin depuis n'importe quel point de départ. C'est le déclaratif du chapitre 10, poussé à sa forme la plus pure.

:::note[Le niveau de déclenchement (*level-triggered*), pas le front (*edge-triggered*)]
Concept d'ingénierie important, emprunté à l'électronique : Kubernetes réagit à un **état** (« il manque un Pod »), pas à un **événement** (« un Pod vient de mourir »). Si l'événement est manqué (contrôleur redémarré au mauvais moment), aucune importance : l'état, lui, est toujours là à la prochaine observation. C'est ce qui rend le système tolérant aux pannes de ses propres composants. Retenez la formule : *level-triggered beats edge-triggered* pour la robustesse.
:::

## 3. L'anatomie d'un cluster

Un cluster Kubernetes se divise en deux : le **plan de contrôle** (le cerveau, qui décide) et les **nœuds de travail** (les muscles, qui exécutent les conteneurs).

<Figure src="plan-controle" num="20.2" alt="Le plan de contrôle regroupe l'API Server, etcd, le scheduler et le controller manager ; chaque nœud de travail porte un kubelet, un kube-proxy et un runtime, et le kubelet dialogue avec l'API Server.">
  Anatomie d'un cluster. Aucun composant ne parle directement à un autre : tous passent par l'API Server, seul à écrire dans etcd.
</Figure>

### 3.1 Le plan de contrôle

<dl>
<dt><strong>API Server</strong> (<code>kube-apiserver</code>)</dt>
<dd>

La **seule** porte d'entrée du cluster. Toute action (`kubectl`, les contrôleurs, les kubelets) passe par lui. Il valide les objets, gère l'authentification et l'autorisation (RBAC, ch. 22), et les écrit dans etcd. Rien ne parle jamais directement à etcd, sauf l'API server : c'est le **point de sérialisation** de toute décision.

</dd>
<dt><strong>etcd</strong></dt>
<dd>

Une base de données clé-valeur distribuée et cohérente. Elle contient **tout l'état** du cluster : les objets désirés *et* l'état observé. C'est **la** source de vérité. Perdre etcd, c'est perdre le cluster : d'où l'importance de le sauvegarder (culture d'exploitation du S1, TP 4).

</dd>
<dt><strong>Scheduler</strong> (<code>kube-scheduler</code>)</dt>
<dd>

Quand un Pod est créé sans nœud assigné, le scheduler lui en **choisit un**, selon les ressources disponibles (requests, ch. 22), les contraintes (affinités, taints) et la charge. C'est le « placement » du chapitre 19, incarné. C'est aussi un contrôleur : il observe les Pods non placés, décide, écrit sa décision.

</dd>
<dt><strong>Controller Manager</strong> (<code>kube-controller-manager</code>)</dt>
<dd>

Le processus qui fait tourner la plupart des boucles de réconciliation (Deployment, ReplicaSet, Node, Job...). C'est ici que vit la section 2 de ce chapitre.

</dd>
</dl>

### 3.2 Les nœuds de travail

<dl>
<dt><strong>kubelet</strong></dt>
<dd>

L'agent présent sur **chaque** nœud. Il demande à l'API server « quels Pods dois-je faire tourner ici ? », les lance via le runtime (containerd/CRI-O, ch. 16), surveille leur santé (probes, ch. 22) et **rapporte l'état réel** à l'API server. Le kubelet est le pont entre le désir (le plan de contrôle) et la réalité (les conteneurs).

</dd>
<dt><strong>kube-proxy</strong></dt>
<dd>

Programme les règles réseau du nœud pour que les **Services** (ch. 21) fonctionnent : le trafic vers une adresse virtuelle de Service est redirigé vers les bons Pods.

</dd>
<dt><strong>Le runtime de conteneurs</strong></dt>
<dd>

containerd ou CRI-O (ch. 16), qui exécute réellement les conteneurs via les primitives du noyau (ch. 15). La boucle est bouclée avec le bloc 1 : tout en bas, ce sont toujours des namespaces et des cgroups.

</dd>
</dl>

## 4. Le trajet d'un `kubectl apply`, de bout en bout

Rassemblons tout en suivant une commande, du clavier au conteneur. C'est le schéma-synthèse à savoir raconter de mémoire (question d'examen quasi certaine) :

<Figure src="kubectl-apply" num="20.3" alt="Diagramme de séquence entre kubectl, l'API Server, etcd, les contrôleurs, le scheduler et le kubelet, depuis l'application d'un Deployment jusqu'au Pod en état Running.">
  Du clavier au conteneur : ce que déclenche <code>kubectl apply</code>. Personne ne donne d'ordre à personne ; chaque composant observe l'API et réagit à ce qui le concerne.
</Figure>

Observez la beauté du système : **aucun composant ne donne d'ordre direct à un autre.** Chacun **observe** l'état via l'API server et **agit** sur sa part. Le Deployment controller ne « commande » pas le scheduler ; il crée des Pods, que le scheduler, de son côté, remarque et place. Ce découplage par l'état partagé (dans etcd, via l'API server) est ce qui rend Kubernetes extensible et résilient. C'est une architecture par **réconciliation coopérative**, pas par chaîne de commandement.

:::tip[Le réflexe de diagnostic que ce modèle offre]
Quand quelque chose ne va pas, la question n'est jamais « qu'est-ce qui a planté ? » mais « **où le réel diverge-t-il du désiré, et quel contrôleur devrait corriger, mais n'y arrive pas ?** ». `kubectl get` montre le réel, `kubectl describe` montre les **événements** (ce que les contrôleurs ont tenté et pourquoi ils échouent). Le TP 17 en fera une méthode. Tenir le modèle de réconciliation, c'est déjà savoir déboguer.
:::

## Ce qu'il faut retenir

<div className="retenir">

1. API **déclarative** : on décrit l'**état désiré** (YAML), jamais les actions. La convergence a lieu **en continu**, pas une fois (différence clé avec Terraform/Ansible).
2. **Boucle de réconciliation** = observer l'état réel, comparer au désiré, agir sur l'écart, recommencer. L'**auto-réparation** en découle gratuitement. **Level-triggered** (réagit à un état) et non edge-triggered (un événement) : d'où la robustesse aux pannes des composants eux-mêmes.
3. **Plan de contrôle** : API Server (seule porte, valide et stocke), **etcd** (source de vérité, à sauvegarder), Scheduler (placement), Controller Manager (les boucles).
4. **Nœuds** : kubelet (lance les Pods, rapporte l'état), kube-proxy (réseau des Services), runtime (containerd/CRI-O → namespaces/cgroups du bloc 1).
5. Trajet d'un `apply` : personne ne commande personne ; chacun **observe et agit** via l'API server. Découplage par l'état partagé = extensibilité + résilience. Déboguer = trouver où le réel diverge du désiré et quel contrôleur bloque.

</div>

## Regard recherche

:::recherche
- **« Borg, Omega, and Kubernetes » (Burns et al., ACM Queue, 2016)** : relisez-le après ce chapitre. La section sur la **réconciliation** et sur le choix du *level-triggered* y est expliquée par les concepteurs. Vous comprendrez que ces choix ne sont pas arbitraires mais tirés de dix ans d'exploitation de Borg.
- **Le modèle de cohérence d'etcd** repose sur l'algorithme de consensus **Raft** : Diego Ongaro, John Ousterhout, « In Search of an Understandable Consensus Algorithm (Raft) », USENIX ATC, 2014. Un des articles de systèmes les plus lisibles jamais écrits, et le fondement de la fiabilité du plan de contrôle. Comprendre Raft, c'est comprendre pourquoi etcd (et donc Kubernetes) survit à la perte d'une machine du plan de contrôle.
- Piste : la **théorie du contrôle** (control theory) éclaire les boucles de réconciliation. Le rapprochement entre systèmes distribués et automatique est un champ de recherche fécond ; cherchez « control theory for computing systems ».
:::

## Bibliographie du chapitre

<div className="biblio">

### Sources primaires

- Documentation Kubernetes : « Kubernetes Components », « Controllers », « The Kubernetes API » : [kubernetes.io/docs/concepts/architecture](https://kubernetes.io/docs/concepts/architecture/). Lecture de référence, à garder ouverte pendant les TP.
- La documentation etcd et le papier Raft (ci-dessus) pour le stockage.

### Lectures recommandées

- Nigel Poulton, *The Kubernetes Book*, chapitres sur l'architecture et le « declarative model ».
- Marko Lukša, *Kubernetes in Action*, 2ᵉ éd., Manning : le chapitre 11 (« Understanding Kubernetes internals ») est la meilleure explication détaillée du plan de contrôle et des boucles.

### Pour aller plus loin

- « A deep dive into Kubernetes controllers » (série de billets de blog, bitnami/engineering) : écrire son propre contrôleur pour vraiment intérioriser la boucle.
- Le code source de `kube-controller-manager` : ardue mais définitive, la boucle `syncHandler` de chaque contrôleur incarne la section 2.

</div>
