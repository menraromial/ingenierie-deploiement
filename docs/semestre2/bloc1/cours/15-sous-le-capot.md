---
title: "Ch. 15 : Sous le capot (namespaces, cgroups)"
sidebar_label: "Ch. 15 : Sous le capot (namespaces, cgroups)"
hide_title: true
---

import ChapterHead from '@site/src/components/ChapterHead';
import Figure from '@site/src/components/Figure';

<ChapterHead
  kicker="Semestre 2 · Bloc 1 · Chapitre 15"
  title="Sous le capot, namespaces, cgroups, systèmes de fichiers en couches"
  lecture="10 min"
/>

:::objectifs
À l'issue de ce chapitre, vous saurez :

- énumérer les namespaces Linux et expliquer ce que chacun isole ;
- expliquer les cgroups (v2), la hiérarchie, les contrôleurs, et le mécanisme de l'OOM killer ;
- expliquer un système de fichiers en couches (OverlayFS) : lowerdir, upperdir, copy-on-write ;
- relier ces trois primitives à ce qu'un moteur de conteneurs fait réellement quand il lance un conteneur.

**C'est le cœur théorique du semestre**, et la matière la plus dense de l'examen. Le [TP 11](../tp/tp11-namespaces-cgroups.md) en est l'illustration directe : vous manipulerez chaque primitive à la main.
:::

## 1. Le principe général : restreindre un processus, pas en créer un spécial

Répétons-le, car tout découle de là : un conteneur n'est pas un type d'objet nouveau. Le noyau Linux sait, depuis un appel système (`clone`, `unshare`, `setns`), placer un processus dans un environnement restreint selon trois axes indépendants. Un « conteneur » est simplement un processus pour lequel un moteur a activé ces trois restrictions d'un coup :

| Axe | Primitive | Question à laquelle il répond |
|---|---|---|
| Ce que le processus **voit** | **Namespaces** | « Quels autres processus, quelles interfaces réseau, quels fichiers existent, de mon point de vue ? » |
| Ce que le processus **peut consommer** | **cgroups** | « Combien de CPU, de RAM, d'I/O ai-je le droit d'utiliser ? » |
| Ce que le processus voit comme **racine `/`** | **Systèmes de fichiers en couches** | « À quoi ressemble mon arborescence de fichiers ? » |

## 2. Les namespaces : isoler la vue

Un **namespace** est une partition d'une ressource globale du noyau, telle que les processus d'un namespace en voient une instance isolée. Créé en plusieurs vagues entre 2002 et 2013, il en existe aujourd'hui plusieurs types ; les connaître est exigé à l'examen :

| Namespace | Isole | Effet concret |
|---|---|---|
| **PID** | Les identifiants de processus | Dans le conteneur, votre application est **PID 1** ; elle ne voit pas les processus de l'hôte |
| **NET** (net) | La pile réseau | Interfaces, adresses IP, tables de routage, ports **propres** au conteneur |
| **MNT** (mount) | Les points de montage | Le conteneur a son arborescence de fichiers, invisible à l'hôte |
| **UTS** | hostname et domainname | `hostname` renvoie le nom du conteneur, pas celui de l'hôte |
| **IPC** | Communication inter-processus | Files de messages, sémaphores, mémoire partagée isolées |
| **USER** | Les identifiants d'utilisateurs (UID/GID) | root **dans** le conteneur peut être un utilisateur **non privilégié** sur l'hôte : la clé du *rootless* |
| **CGROUP** | La vue de la hiérarchie cgroup | Le conteneur ne voit pas la hiérarchie cgroup de l'hôte |
| **TIME** | Les horloges (monotonic/boottime) | Plus rare ; décalage d'horloge par conteneur |

### 2.1 Le namespace PID, vu de près

C'est le plus parlant. Quand un moteur crée un conteneur, il place le processus principal dans un **nouveau namespace PID** : ce processus devient **PID 1** de ce namespace. Conséquences majeures, qui reviendront tout le semestre :

- Le conteneur ne voit **que ses propres processus** (`ps` dans le conteneur ne montre pas l'hôte).
- L'hôte, lui, voit ces processus avec **d'autres PID** (le conteneur n'est pas caché *à l'hôte* : simplement chacun a sa numérotation). Au TP 11, vous verrez le même processus avec deux PID différents selon l'endroit d'où on regarde.
- **PID 1 a des responsabilités spéciales** : c'est lui qui doit « adopter » et nettoyer les processus orphelins (*reaping*). Une application écrite pour tourner sous systemd, lancée telle quelle comme PID 1 d'un conteneur, peut laisser des processus zombies : c'est le fameux problème du « PID 1 » des conteneurs, résolu par des init minimalistes (`tini`, `--init`).

### 2.2 Le namespace USER : le fondement du rootless

Le namespace **user** est le plus important pour la sécurité, et la raison technique pour laquelle Podman peut fonctionner **sans droits administrateur**. Il permet une **correspondance d'identifiants** (*UID mapping*) : l'UID 0 (root) *à l'intérieur* du conteneur est mappé vers un UID **non privilégié** *sur l'hôte* (par exemple votre UID 1000, ou une plage `/etc/subuid` qui vous est allouée).

<Figure src="user-namespace" num="15.1" alt="Dans le conteneur, le processus est root, UID 0 ; sur l'hôte, le namespace user le fait correspondre à l'UID 100000, un utilisateur sans privilège.">
  Le mapping du namespace user, fondement du mode rootless. Être root dans le conteneur ne donne aucun droit sur l'hôte : une évasion ne livre qu'un utilisateur non privilégié.
</Figure>

Résultat : à l'intérieur, l'application croit être root et peut faire ce qu'elle veut *de son environnement* ; mais si elle s'échappe, elle n'est sur l'hôte qu'un utilisateur ordinaire sans pouvoir. C'est le **principe du moindre privilège** (chapitre 5 du S1) porté par le noyau. Vous mesurerez ce mapping au TP 11 et au TP 12 (`podman unshare cat /proc/self/uid_map`).

:::note[Le lien direct avec le S1]
Le rootless de Podman *est* une application du moindre privilège que vous avez pratiqué au S1 : un service ne tourne qu'avec les droits strictement nécessaires. Ici, la nouveauté est que l'illusion de root est fournie **par le noyau**, sans jamais accorder de vrais privilèges.
:::

### 2.3 Créer un namespace à la main

Les moteurs utilisent les appels systèmes `clone()`/`unshare()`. En ligne de commande, `unshare` les expose. Aperçu (détaillé au TP 11) :

```bash
# Nouveau namespace UTS : changer le hostname sans affecter l'hôte
sudo unshare --uts sh -c 'hostname conteneur-jouet; hostname'
hostname     # sur l'hôte : inchangé

# Nouveau namespace PID : le shell devient PID 1 de sa propre vue
sudo unshare --pid --fork --mount-proc sh -c 'echo "je suis PID $$"; ps aux'
```

## 3. Les cgroups : limiter et comptabiliser les ressources

### 3.1 Le principe

Les **control groups** (cgroups) organisent les processus en une **hiérarchie arborescente** et permettent, pour chaque groupe, de **limiter**, **prioriser** et **mesurer** l'usage des ressources via des **contrôleurs** (*controllers*). Là où les namespaces répondent à « que vois-tu ? », les cgroups répondent à « combien peux-tu consommer ? ». Les principaux contrôleurs :

| Contrôleur | Limite / mesure |
|---|---|
| **cpu** | Temps CPU (parts relatives, quotas absolus) |
| **memory** | Mémoire vive maximale ; déclenche l'OOM killer au dépassement |
| **io** | Débit et IOPS sur les disques |
| **pids** | Nombre maximal de processus (anti *fork bomb*) |

### 3.2 cgroups v2 : la hiérarchie unifiée

Depuis quelques années, Linux utilise **cgroups v2**, qui remplace la v1 par une **hiérarchie unique** exposée dans le pseudo-système de fichiers `/sys/fs/cgroup`. On crée un groupe en créant un répertoire, on y place un processus en écrivant son PID, on fixe une limite en écrivant dans un fichier :

```bash
# (schéma conceptuel ; le TP 11 donne la version rootless exacte)
# Créer un groupe
sudo mkdir /sys/fs/cgroup/demo
# Limiter sa mémoire à 100 Mo
echo 100M | sudo tee /sys/fs/cgroup/demo/memory.max
# Y placer le shell courant
echo $$ | sudo tee /sys/fs/cgroup/demo/cgroup.procs
```

Tout processus de ce groupe (et ses enfants) est désormais borné à 100 Mo. C'est **exactement** ce que fait `podman run --memory=100m`, et ce que Kubernetes fera avec ses `limits` au bloc 2 : la même primitive, à trois niveaux d'abstraction.

### 3.3 L'OOM killer, que vous rencontrerez souvent

Quand un cgroup atteint sa limite `memory.max` et qu'aucune mémoire ne peut être libérée, le noyau invoque l'**OOM killer** (*Out Of Memory killer*) : il **tue** un processus du groupe pour protéger le système. Dans un conteneur limité en mémoire, c'est votre application qui meurt, avec le code de sortie **137**. Retenez ce nombre : au bloc 2, une des pannes injectées les plus fréquentes de Kubernetes est l'**OOMKilled**, et elle vient exactement d'ici, du contrôleur `memory` d'un cgroup. Vous en avez déjà eu un avant-goût au TP 2 du S1 (bonus `MemoryMax=` d'une unité systemd) : systemd, lui aussi, pilote des cgroups.

:::note[Lire un code de sortie : la convention `128 + signal`]
Pourquoi 137 et pas 9 ? Parce qu'un code de sortie tient sur un octet (0-255) et doit distinguer deux situations : un programme qui **choisit** de sortir avec un code (`exit(9)`, erreur applicative), et un programme **tué par un signal** sur lequel il n'a aucun contrôle. La convention (issue du shell, normalisée par POSIX) est : **`code de sortie = 128 + numéro du signal`** qui a tué le processus.

SIGKILL porte le numéro 9, d'où 128 + 9 = **137**. Dès qu'un code est ≥ 128, lisez-le « tué par le signal (code − 128) ». Les cas les plus fréquents :

| Signal | Numéro | Code | Situation typique |
|---|---|---|---|
| SIGINT | 2 | **130** | vous faites <kbd>Ctrl</kbd>+<kbd>C</kbd> |
| SIGKILL | 9 | **137** | tué de force : **OOM killer**, `kill -9` |
| SIGSEGV | 11 | **139** | erreur de segmentation (bug mémoire) |
| SIGTERM | 15 | **143** | arrêt **propre** demandé (`podman stop`, `kubectl delete`) |

Retenez le couple **137 / 143** : au bloc 2, un Pod **OOMKilled** sort en 137, un Pod arrêté normalement en 143. Le code de sortie dit la *cause* de la mort d'un coup d'œil.
:::

:::note[systemd et cgroups : une vieille connaissance]
Chaque service systemd du S1 tournait déjà dans son propre cgroup (c'est ainsi que `systemctl status` affiche la mémoire et le CPU d'un service). Les conteneurs et systemd s'appuient sur la **même** primitive du noyau ; Podman peut d'ailleurs déléguer la gestion des cgroups à systemd. Rien de tout cela n'est nouveau : c'est réassemblé.
:::

## 4. Les systèmes de fichiers en couches : l'image et le copy-on-write

### 4.1 Le problème résolu

Une image de conteneur doit être **partageable** (des dizaines de conteneurs partant de la même image `python:3.12` ne doivent pas dupliquer des centaines de Mo) et **immuable** (l'image ne doit jamais être modifiée par un conteneur en cours d'exécution). La solution est un **système de fichiers en couches** (*union filesystem*), sous Linux principalement **OverlayFS**.

### 4.2 Le mécanisme : lowerdir, upperdir, copy-on-write

OverlayFS **superpose** des répertoires et présente une vue fusionnée :

<Figure src="overlayfs" num="15.2" alt="Trois couches en lecture seule (image de base, dépendances, code) surmontées d'une couche inscriptible propre au conteneur ; OverlayFS présente leur superposition comme la racine du conteneur.">
  La superposition d'OverlayFS. Les couches de l'image sont partagées par tous les conteneurs qui en dérivent ; seule la couche du haut, inscriptible, leur est propre.
</Figure>

- Les **lowerdir** sont les couches de l'**image**, en **lecture seule**, **partagées** entre tous les conteneurs qui en dérivent.
- L'**upperdir** est une couche **inscriptible**, **propre à chaque conteneur**, vide à son démarrage.
- La lecture d'un fichier remonte les couches de haut en bas jusqu'à le trouver.
- L'écriture déclenche un **copy-on-write** (CoW) : le fichier est d'abord **copié** de la couche image (lecture seule) vers l'upperdir, puis modifié là. L'image d'origine reste intacte.

### 4.3 Les conséquences, décisives pour toute la suite

1. **Les images sont faites de couches empilées et partagées.** Deux images qui partent de `debian-slim` partagent physiquement cette couche sur le disque : on ne la stocke qu'une fois. C'est pourquoi la taille cumulée des images est bien inférieure à la somme de leurs tailles.
2. **Un conteneur est éphémère par nature.** Tout ce qu'il écrit va dans son upperdir, **détruit avec lui**. Redémarrer un conteneur depuis l'image, c'est repartir de l'upperdir vide : l'état est perdu. D'où la nécessité des **volumes** pour les données à conserver (la base de données !), sujet du chapitre 18. C'est l'incarnation, au niveau du stockage, de la distinction *stateless/stateful* du S1.
3. **L'ordre des couches gouverne le cache de build.** Comme chaque instruction d'un `Containerfile` crée une couche, placer ce qui change rarement (les dépendances) *avant* ce qui change souvent (votre code) permet de réutiliser les couches inchangées. C'est le nerf de l'optimisation des images (chapitre 17).

## 5. Le bilan : ce que fait vraiment `podman run`

Rassemblons tout. Quand vous taperez `podman run debian sleep 100`, voici ce que le moteur orchestre, et vous savez désormais nommer chaque étape :

<Figure src="podman-run" num="15.3" alt="Diagramme de séquence entre vous, Podman et le noyau Linux : récupération de l'image, montage OverlayFS, création des namespaces et du cgroup, lancement du processus.">
  Ce que fait <code>podman run</code>, étape par étape. Chaque appel au noyau correspond à une primitive du chapitre : le moteur n'est qu'un chef d'orchestre.
</Figure>

Il n'y a **aucune magie** : trois primitives du noyau, configurées par un programme en espace utilisateur. Un ingénieur qui tient cette séquence peut déboguer n'importe quel comportement de conteneur, parce qu'il sait *où* regarder. C'est précisément ce que le TP 11 vous fera faire de vos mains.

## Ce qu'il faut retenir

<div className="retenir">

1. Un conteneur = un **processus Linux** restreint sur trois axes indépendants : **namespaces** (ce qu'il voit), **cgroups** (ce qu'il consomme), **overlay** (sa racine).
2. **Namespaces** : pid (PID 1 dans le conteneur), net, mnt, uts, ipc, **user** (fondement du rootless : root dans le conteneur = utilisateur sans privilège sur l'hôte), cgroup, time.
3. **cgroups v2** : hiérarchie unifiée dans `/sys/fs/cgroup` ; contrôleurs cpu/memory/io/pids ; dépassement mémoire → **OOM killer**, code de sortie **137** (l'OOMKilled de Kubernetes). systemd utilise déjà les cgroups.
4. **OverlayFS** : lowerdir (couches image, lecture seule, partagées) + upperdir (inscriptible, par conteneur) + **copy-on-write**. Conséquences : images en couches partagées, conteneur **éphémère** (d'où les volumes), l'**ordre des couches** gouverne le cache de build.
5. `podman run` = récupérer l'image → monter l'overlay → créer namespaces → appliquer cgroup → lancer le processus. Pas de magie, trois primitives.

</div>

## Regard recherche

:::recherche
- **Paul Menage, « Adding Generic Process Containers to the Linux Kernel », Ottawa Linux Symposium, 2007.** Le papier par lequel les *process containers* (futurs cgroups), développés chez Google, sont proposés au noyau Linux. Lire l'introduction : les motivations (isoler les ressources de milliers de services partageant des machines) sont exactement celles qui mèneront à Borg puis Kubernetes.
- **Eric Biederman, « Multiple Instances of the Global Linux Namespaces », Ottawa Linux Symposium, 2006.** La conception des namespaces, par leur principal auteur. Technique, mais fondateur.
- **Rami Rosen, « Namespaces and Cgroups, the basis of Linux containers », NetDev, 2016** (transparents et article). Une synthèse claire et citable des deux primitives par un contributeur du noyau ; excellent pont entre la documentation et la recherche.

Piste d'innovation : les namespaces et cgroups n'ont pas dit leur dernier mot. Cherchez les travaux récents sur l'isolation renforcée (**gVisor**, un noyau en espace utilisateur, papier « The True Cost of Containing », et **Kata Containers**) : comment regagner l'isolation d'une VM sans en payer tout le coût ? Un sujet de recherche actuel, idéal pour un projet.
:::

## Bibliographie du chapitre

<div className="biblio">

### Sources primaires

- Pages de manuel du noyau : `man 7 namespaces`, `man 7 user_namespaces`, `man 7 cgroups`, `man 1 unshare`. **La** référence, précise et à jour.
- Documentation du noyau Linux, `Documentation/admin-guide/cgroup-v2.rst` : la spécification de cgroups v2, à consulter pour le TP 11. [kernel.org](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html).
- Documentation OverlayFS du noyau : `Documentation/filesystems/overlayfs.rst`.

### Lectures recommandées

- Liz Rice, *Container Security*, O'Reilly, 2020, chapitres 2 à 4 : namespaces, cgroups et l'écriture d'un conteneur « à la main » en Go, dans l'esprit exact du TP 11.
- Michael Kerrisk, *The Linux Programming Interface*, No Starch Press : chapitres sur les namespaces (l'auteur mainteneur des man-pages Linux), pour qui veut la profondeur système.
- La série d'articles de Michael Kerrisk sur LWN.net, « Namespaces in operation » (7 parties) : la meilleure explication détaillée et gratuite qui existe.

### Pour aller plus loin

- Jérôme Petazzoni, « Containers From Scratch » : construire un conteneur en quelques dizaines de lignes, en direct.
- Le code source de `runc` (le runtime OCI de référence, ch. 16) : `libcontainer` montre les appels systèmes réels ; lecture ardue mais définitive.

</div>
