---
title: "Ch. 21 : Les objets fondamentaux"
sidebar_label: "Ch. 21 : Les objets fondamentaux"
hide_title: true
---

import ChapterHead from '@site/src/components/ChapterHead';
import Figure from '@site/src/components/Figure';

<ChapterHead
  kicker="Semestre 2 · Bloc 2 · Chapitre 21"
  title="Les objets fondamentaux de Kubernetes"
  lecture="10 min"
  competences={['C1']}
/>

:::objectifs
À l'issue de ce chapitre, vous saurez :

- définir et relier les objets de charge : Pod, ReplicaSet, Deployment ;
- exposer des Pods avec un Service (ClusterIP/NodePort/LoadBalancer) et un Ingress ;
- injecter configuration et secrets (ConfigMap, Secret) et cloisonner avec les Namespaces ;
- gérer le stockage persistant (PV, PVC, StorageClass) et l'état avec un StatefulSet ;
- trancher, avec des arguments, le débat « faut-il mettre sa base de données dans Kubernetes ? ».

Chaque objet de ce chapitre deviendra un manifeste concret au [TP 16](../tp/tp16-fil-rouge-complet.md), où Listify sera reconstruit sur le cluster.
:::

## 1. Le Pod : l'unité atomique

Vous connaissez déjà le **Pod** (bloc 1, ch. 18) : un groupe d'un ou plusieurs conteneurs qui **partagent le réseau** (même adresse IP, communication par `localhost`) et un cycle de vie. C'est la **plus petite unité déployable** de Kubernetes : on ne déploie jamais un conteneur seul, toujours un Pod.

```yaml title="Un Pod (rarement écrit tel quel, voir §2)"
apiVersion: v1
kind: Pod
metadata:
  name: backend
  labels:
    app: listify
    tier: backend
spec:
  containers:
    - name: backend
      image: listify-backend:1.0
      ports:
        - containerPort: 8000
```

Point capital : **un Pod est mortel et jetable.** Il n'est jamais « réparé » : s'il meurt, il est **remplacé** par un nouveau, avec une **nouvelle adresse IP**. C'est le « bétail » du chapitre 9 du S1, appliqué aux conteneurs. Cette impermanence a deux conséquences qui structurent tout le reste :

1. On ne s'adresse jamais à un Pod par son IP (elle change) : d'où les **Services** (§3).
2. Un Pod ne conserve rien : d'où les **volumes persistants** (§5).

### 1.1 Les labels : le liant de tout Kubernetes

Remarquez les `labels` (`app: listify`, `tier: backend`). Ce sont de simples paires clé-valeur, mais elles sont le **mécanisme central** par lequel les objets se retrouvent. Un Service ne connaît pas les Pods par leur nom ; il les **sélectionne par label** (`selector: app=listify`). Quand un Pod meurt et qu'un autre naît avec les mêmes labels, le Service le trouve automatiquement. Les labels sont le tissu conjonctif de Kubernetes : hérités de Borg, ils remplacent tout couplage rigide par une correspondance souple. Retenez-les, ils sont partout.

## 2. ReplicaSet et Deployment : maintenir des répliques

### 2.1 Le ReplicaSet

Un **ReplicaSet** maintient un **nombre donné de Pods identiques** vivants. C'est le contrôleur de la boucle de réconciliation du chapitre 20 (« 3 voulus, combien de réels ? »). Il garantit qu'il y a toujours exactement N Pods correspondant à son sélecteur de labels.

### 2.2 Le Deployment, l'objet que vous utiliserez vraiment

On n'écrit presque jamais un ReplicaSet directement. On écrit un **Deployment**, qui gère des ReplicaSets pour vous et ajoute la brique décisive : les **mises à jour progressives**. Un Deployment est l'objet de charge standard pour une application **sans état** (backend, frontend).

<Figure src="deployment-replicaset" num="21.1" alt="Un Deployment gère un ReplicaSet, qui maintient trois Pods identiques.">
  La hiérarchie Deployment, ReplicaSet, Pods. Le ReplicaSet maintient le nombre ; le Deployment ajoute la stratégie de mise à jour, en créant un nouveau ReplicaSet à chaque version.
</Figure>

Quand vous changez l'image dans le Deployment (v1 → v2), il crée un **nouveau** ReplicaSet (v2) et fait décroître l'ancien tout en faisant croître le nouveau, Pod par Pod : c'est le **rolling update** (ch. 22). Et il garde l'ancien ReplicaSet à zéro réplique, prêt pour un **rollback** instantané. Vous retrouvez le « déploiement sans coupure » du reverse proxy du S1, désormais natif et généralisé.

## 3. Les Services : une adresse stable pour des Pods mortels

### 3.1 Le problème et la solution

Les Pods vont et viennent, changent d'IP. Comment un frontend joint-il « le backend » de façon stable ? Le **Service** est la réponse : une **adresse IP virtuelle et stable** (et un nom DNS) qui **répartit** le trafic vers l'ensemble des Pods correspondant à son sélecteur de labels.

<Figure src="service-selector" num="21.2" alt="Le Pod frontend joint le Service backend par un nom stable ; le Service répartit vers les Pods backend et suit par leurs labels ceux qui naissent.">
  Le Service, point d'accès stable devant des Pods éphémères. Il ne connaît pas les Pods par leur nom mais par leurs labels.
</Figure>

Le Service, c'est **à la fois** la découverte de services et l'équilibrage de charge du chapitre 19, fournis nativement. C'est le DNS interne du bloc 1 (`DB_HOST=db`) et le load balancer du S1 (TP 6), unifiés et automatiques. Le kube-proxy (ch. 20) programme le réseau pour que l'IP du Service atteigne les bons Pods.

### 3.2 Les types de Service

| Type | Exposition | Usage |
|---|---|---|
| **ClusterIP** (défaut) | Interne au cluster uniquement | Communication service-à-service (frontend → backend → db) |
| **NodePort** | Un port sur chaque nœud | Accès externe rudimentaire, surtout pour tester |
| **LoadBalancer** | Un équilibreur externe (fourni par le cloud) | Exposition publique en production cloud ; sans effet en local sans add-on |

En interne, on utilise **ClusterIP** partout (c'est le défaut). Pour l'exposition externe propre, on ne multiplie pas les NodePort/LoadBalancer : on met un **Ingress** devant.

## 4. L'Ingress : la porte d'entrée HTTP

Un **Ingress** est une règle de routage HTTP/HTTPS **de niveau 7** (ch. 8 du S1) : il expose plusieurs services derrière une seule entrée, route selon le chemin ou le nom d'hôte, et gère le TLS. C'est **exactement le rôle de Nginx** au S1 (reverse proxy), promu au rang d'objet Kubernetes.

```yaml title="Ingress : / vers le frontend, /api vers le backend"
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: listify
spec:
  rules:
    - host: listify.local
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service: { name: frontend, port: { number: 80 } }
          - path: /api
            pathType: Prefix
            backend:
              service: { name: backend, port: { number: 8000 } }
```

Un Ingress n'est qu'une **déclaration de règles** ; c'est un **contrôleur d'Ingress** (souvent ingress-nginx, littéralement Nginx piloté par Kubernetes) qui les applique. La boucle avec le S1 est totale : le reverse proxy que vous configuriez à la main est devenu un objet déclaratif, appliqué par un contrôleur, mais c'est le **même Nginx** en dessous.

## 5. Configuration et secrets : ConfigMap et Secret

Le facteur III des 12-factor (config dans l'environnement, S1 ch. 4) a ses objets dédiés :

- **ConfigMap** : des données de configuration non sensibles (variables, fichiers de conf), injectées dans les Pods comme variables d'environnement ou fichiers montés.
- **Secret** : idem, pour les données **sensibles** (mots de passe, clés). Même mécanisme d'injection.

```yaml title="Secret pour le mot de passe de la base"
apiVersion: v1
kind: Secret
metadata:
  name: listify-db
type: Opaque
stringData:
  DB_PASSWORD: "un-mot-de-passe-fort"
```

:::danger[Un Secret Kubernetes n'est PAS chiffré par défaut]
Piège classique et question d'examen : un Secret est seulement encodé en **base64**, pas chiffré. N'importe qui ayant accès à l'objet (ou à etcd) le lit en clair. La base64 empêche l'affichage accidentel, pas le vol. Pour une vraie protection : chiffrement d'etcd au repos, RBAC strict (ch. 22), et des outils dédiés (Sealed Secrets, un gestionnaire externe type Vault). Le Secret **sépare** le sensible du reste (mieux que le coder en dur, comme l'anti-pattern du S1), mais ne le **protège** pas seul. Le dire honnêtement fait partie de la compétence.
:::

## 6. Les Namespaces : cloisonner un cluster

Un **Namespace** partitionne un cluster en espaces logiques isolés (noms, quotas, droits RBAC). On y sépare des environnements (`dev`, `prod`), des équipes, des applications. C'est la segmentation du S1 (chapitre 6), au niveau logique du cluster. Vos objets Listify vivront dans un namespace `listify` dédié.

## 7. Le stockage persistant : PV, PVC, StorageClass

### 7.1 Le découplage demande/offre

Un Pod jetable ne peut pas garder de données. Pour la base, il faut du **stockage persistant**, découplé du cycle de vie du Pod. Kubernetes sépare la **demande** de l'**offre** :

- **PersistentVolume (PV)** : un morceau de stockage réel (un disque, un volume cloud). L'**offre**.
- **PersistentVolumeClaim (PVC)** : une **demande** de stockage par une application (« je veux 1 Gio »). Le Pod monte le PVC, pas le PV.
- **StorageClass** : décrit *comment* provisionner un PV à la demande (quel type de disque), pour l'automatiser (*dynamic provisioning*).

<Figure src="pvc-pv" num="21.3" alt="Le Pod de base de données monte un PVC qui demande 1 Gio ; le PVC est lié à un PV, disque réel, provisionné automatiquement par une StorageClass.">
  Stockage persistant : le Pod demande (PVC), l'administrateur ou la StorageClass fournit (PV). La demande est découplée de la réalisation.
</Figure>

Ce découplage (l'application demande, l'infrastructure fournit) est le même esprit que le PVC/PV et l'IaC du S1 : l'application ne connaît pas le disque physique, seulement sa demande. C'est aussi la **Container Storage Interface (CSI)**, pendant de la CNI réseau, entrevue au bloc 1.

### 7.2 Le StatefulSet et le grand débat

Un Deployment convient au *stateless*. Pour une application **avec état** et une **identité stable** (une base de données, chaque réplique ayant son propre stockage et un nom fixe), Kubernetes offre le **StatefulSet** : des Pods numérotés (`db-0`, `db-1`), chacun avec son PVC propre et persistant, dans un ordre de démarrage garanti.

:::question[Faut-il mettre sa base de données dans Kubernetes ? (question d'architecture, C1)]
Débat majeur, attendu à l'examen, sans réponse unique mais avec des arguments à maîtriser :

**Contre** : Kubernetes est conçu pour le jetable et le mobile ; une base est précieuse et sédentaire. Gérer la persistance, les sauvegardes, la réplication, les basculements d'une base *dans* Kubernetes est complexe et risqué. Beaucoup d'équipes préfèrent une **base managée** (RDS, Cloud SQL) ou une VM dédiée, *hors* du cluster : le cluster orchestre le stateless, la base vit à côté.

**Pour** : les StatefulSets et les **opérateurs** (des contrôleurs spécialisés qui encodent le savoir-faire d'exploitation d'une base : CloudNativePG, l'opérateur PostgreSQL...) ont beaucoup mûri. Pour l'homogénéité (tout décrit en YAML, tout dans le même plan de contrôle) et sur site (pas de base managée disponible), c'est devenu viable.

**La position mûre** : ce n'est pas « toujours » ni « jamais », mais « selon ». Sans opérateur éprouvé et sans expertise, on garde la base dehors. En TP, on met une base *simple* dans un StatefulSet pour **apprendre le mécanisme**, en assumant que ce n'est pas ce qu'on ferait pour une base critique en production. Savoir énoncer ce « selon » avec ses critères, c'est la compétence C1.
:::

## Ce qu'il faut retenir

<div className="retenir">

1. **Pod** : plus petite unité, conteneurs à réseau partagé, **mortel et jetable** (remplacé, jamais réparé ; IP éphémère). Les **labels** relient tout (sélection souple).
2. **Deployment** (via ReplicaSet) : maintient N répliques d'une app **sans état**, gère **rolling update** et **rollback**. On écrit des Deployments, pas des Pods ni des ReplicaSets.
3. **Service** : IP/nom **stable** + répartition vers les Pods sélectionnés par label = découverte + load balancing natifs. **ClusterIP** (interne, défaut), NodePort, LoadBalancer.
4. **Ingress** : routage HTTP niveau 7 (le reverse proxy Nginx du S1, en objet déclaratif appliqué par un contrôleur d'Ingress).
5. **ConfigMap / Secret** : config et secrets injectés (facteur III). Un Secret est **base64, pas chiffré** : il sépare, il ne protège pas seul.
6. **Namespace** : cloisonnement logique du cluster (environnements, équipes).
7. **PVC/PV/StorageClass** : stockage persistant, demande découplée de l'offre. **StatefulSet** pour l'état + identité stable. Le débat « base dans K8s ? » se tranche « selon », avec des critères (opérateur, expertise, criticité).

</div>

## Regard recherche

:::recherche
- **Brendan Burns, David Oppenheimer, « Design Patterns for Container-based Distributed Systems », HotCloud, 2016** (déjà cité au bloc 1) : la justification théorique du Pod et des patterns multi-conteneurs (sidecar, ambassador, adapter). À relire ici, il éclaire *pourquoi* le Pod, et non le conteneur, est l'unité.
- **Le pattern « opérateur »** (encoder l'expertise d'exploitation dans un contrôleur) est une idée forte issue de la pratique : cherchez l'« Operator pattern » (CoreOS, 2016) et les **Custom Resource Definitions**. C'est un domaine où recherche et industrie se rejoignent : comment automatiser le savoir d'un expert humain ? Un excellent sujet de projet ou de mémoire.
- Sur le **stockage distribué** sous-jacent aux PV (le vrai problème dur) : Kleppmann, *Designing Data-Intensive Applications* (chapitres réplication et cohérence, vus au S3) est la porte d'entrée.
:::

## Bibliographie du chapitre

<div className="biblio">

### Sources primaires

- Documentation Kubernetes, section « Concepts » → « Workloads » (Pod, Deployment, StatefulSet), « Services, Load Balancing, and Networking » (Service, Ingress), « Storage » (PV, PVC, StorageClass), « Configuration » (ConfigMap, Secret). [kubernetes.io/docs/concepts](https://kubernetes.io/docs/concepts/). La référence absolue de tout le TP 16.

### Lectures recommandées

- Nigel Poulton, *The Kubernetes Book* : un chapitre par objet, exactement au niveau du cours.
- Marko Lukša, *Kubernetes in Action*, 2ᵉ éd. : chapitres 4 (Deployment), 5 (Service), 7 (ConfigMap/Secret), 10 (StatefulSet). Le plus complet.

### Pour aller plus loin

- Les **opérateurs** : la documentation d'un opérateur PostgreSQL (CloudNativePG, Zalando) pour voir concrètement comment on met une base « pour de vrai » dans Kubernetes.
- Le projet **kube-prometheus-stack** (bloc 3) : un exemple massif d'objets combinés, à explorer une fois les fondamentaux acquis.

</div>
