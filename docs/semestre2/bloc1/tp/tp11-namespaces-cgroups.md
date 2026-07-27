# TP 11 : Construire un « conteneur » à la main

!!! abstract "Fiche du TP"
    - **Durée** : 4 h
    - **Prérequis** : chapitres 14 et 15 ; Podman installé (déjà présent sur les postes)
    - **Livrables** : le compte rendu des manipulations (namespaces isolés, cgroup limitant la mémoire, comparaison avec `podman`) ; runbook
    - **Compétences travaillées** : C3, C6

    Objectif : **démystifier le moteur de conteneurs**. Vous allez isoler un processus et le limiter en ressources avec les seules primitives du noyau, sans aucun moteur, puis vérifier que Podman ne fait rien de plus mystérieux. Après ce TP, un conteneur ne sera plus une boîte noire.

    Tout se fait **en rootless**, sans `sudo` : c'est possible grâce au namespace *user* (ch. 15, §2.2), et c'est le point le plus instructif du TP.

## Étape 1 : isoler la vue avec les namespaces (1 h 15)

### 1.1 Le namespace UTS : un hostname à soi

Le plus simple pour commencer. On crée un namespace *user* (indispensable en rootless pour obtenir les droits de créer les autres namespaces) et un namespace *UTS* :

```bash
unshare --user --map-root-user --uts sh
# Vous êtes dans un nouveau shell. Changez le hostname :
hostname conteneur-jouet
hostname                 # conteneur-jouet
exit
# De retour sur l'hôte :
hostname                 # INCHANGÉ : le namespace UTS a isolé le hostname
```

Consignez : le hostname changé *à l'intérieur* n'a pas affecté l'hôte. Vous venez d'isoler une ressource globale du noyau. C'est exactement ce que fait `podman run --hostname`.

### 1.2 Le namespace PID : devenir PID 1

Le plus spectaculaire. On isole la table des processus :

```bash
unshare --user --map-root-user --pid --fork --mount-proc sh
# Dans le nouveau shell :
echo $$                  # affiche 1 : vous êtes PID 1 de votre propre monde
ps -e                    # vous ne voyez QUE vos processus, pas ceux de l'hôte
exit
```

Points à comprendre et noter (ch. 15, §2.1) :

- `--fork` est nécessaire : c'est le processus **fils** qui devient PID 1 du nouveau namespace.
- `--mount-proc` remonte un `/proc` propre au namespace, sans quoi `ps` montrerait encore les processus de l'hôte (`/proc` reflète le namespace PID).
- Vous êtes **PID 1** : dans un vrai conteneur, cela a des conséquences (adoption des orphelins, gestion des signaux) qui justifient les init minimalistes comme `tini`.

??? question "Point de contrôle n° 1 : deux vues du même processus"
    Ouvrez **deux** terminaux. Dans le premier, lancez un processus isolé qui dure :

    ```bash
    unshare --user --map-root-user --pid --fork --mount-proc sh -c 'sleep 999'
    ```

    Dans le second (sur l'hôte), retrouvez ce `sleep` :

    ```bash
    ps aux | grep 'sleep 999'      # il a un PID "normal" côté hôte (ex. 34712)
    ```

    Le **même** processus est PID 1 dans son namespace et PID 34712 vu de l'hôte. Notez-le : le conteneur n'est pas *caché* à l'hôte, chacun a simplement sa numérotation. C'est la clé pour déboguer un conteneur depuis l'hôte.

### 1.3 Le namespace user : la magie du rootless

Regardez la correspondance d'identifiants qui rend tout cela possible sans privilèges. Podman expose la même primitive :

```bash
podman unshare cat /proc/self/uid_map
# exemple de sortie :
#          0       1000          1
#          1     100000      65536
```

Lecture (ch. 15, §2.2) : l'UID **0** (root) *dans* le namespace correspond à l'UID **1000** (vous) sur l'hôte ; puis une plage (UID 1 à 65536 dans le conteneur) correspond à `100000+` sur l'hôte (votre allocation `/etc/subuid`). Autrement dit : root dans le conteneur = vous, sans le moindre privilège réel. **C'est pour cela qu'aucun `sudo` n'est nécessaire** de tout ce TP, et pourquoi Podman est sûr en salle de TP.

## Étape 2 : limiter les ressources avec un cgroup (1 h 15)

### 2.1 Repérer la hiérarchie cgroup v2

```bash
# Votre cgroup courant :
cat /proc/self/cgroup
# La racine de la hiérarchie v2 :
ls /sys/fs/cgroup
# Vos contrôleurs délégués en rootless (via systemd user) :
cat /sys/fs/cgroup/user.slice/user-$(id -u).slice/user@$(id -u).service/cgroup.controllers
```

En rootless, systemd vous **délègue** un sous-arbre cgroup où vous pouvez créer vos propres groupes. C'est là que Podman crée les cgroups de vos conteneurs.

### 2.2 Créer un cgroup et limiter la mémoire

Le plus simple et robuste en rootless est de passer par `systemd-run`, qui crée un cgroup transitoire et y applique des limites :

```bash
# Lancer une commande dans un cgroup limité à 50 Mo de mémoire :
systemd-run --user --scope -p MemoryMax=50M \
  python3 -c "print('avant'); b = bytearray(200*1024*1024); print('après')"
```

La commande tente d'allouer 200 Mo alors que le cgroup en autorise 50 : le noyau invoque l'**OOM killer** (ch. 15, §3.3), le processus est tué avant d'afficher « après ». Consignez le comportement et le message (souvent `Killed` ou un code de sortie **137**). Ce **137** n'est pas arbitraire : c'est `128 + 9` (tué par le signal SIGKILL). La convention « lire un code de sortie » est détaillée dans l'encadré du chapitre 15, §3.3 ; gardez-la, elle resservira à chaque diagnostic.

!!! note "Le lien direct avec la suite"
    `systemd-run -p MemoryMax=50M` ↔ `podman run --memory=50m` ↔ le `limits.memory` d'un conteneur Kubernetes (bloc 2). **Trois abstractions, une seule primitive** : le contrôleur `memory` d'un cgroup v2. L'`OOMKilled` que vous diagnostiquerez au bloc 2 vient exactement d'ici. Vous venez d'en voir la source.

??? question "Point de contrôle n° 2 : comparer avec Podman"
    Faites la même expérience avec Podman et constatez le comportement identique :

    ```bash
    podman run --rm --memory=50m python:3.12-slim \
      python3 -c "b = bytearray(200*1024*1024); print('jamais atteint')"
    echo "code de sortie : $?"      # 137 = 128 + SIGKILL(9) : OOMKilled
    ```

    Podman n'a rien fait de plus que vous à l'étape 2.1 : il a créé un cgroup et fixé `memory.max`. Notez cette équivalence, c'est le cœur du TP.

## Étape 3 : assembler un « conteneur » minimal (1 h)

Combinons namespaces + un changement de racine pour approcher ce qu'est un conteneur. On utilise une petite image extraite comme système de fichiers racine :

```bash
# 1. Récupérer un système de fichiers racine minimal (via podman, sans le "lancer")
mkdir -p ~/rootfs-jouet
podman export "$(podman create docker.io/library/alpine:3.20)" | tar -C ~/rootfs-jouet -xf -
ls ~/rootfs-jouet        # bin, etc, usr... une mini-distribution

# 2. Entrer dans un environnement isolé, avec CE rootfs comme racine.
#    podman unshare crée déjà les namespaces (dont user) ; on change la racine.
#    NB : on utilise "$HOME" et non "~" car ~ ne se développe pas ici, et on
#    n'efface PAS l'environnement (pas de `env -i`, sinon HOME serait vide).
podman unshare sh -c 'cd "$HOME/rootfs-jouet" && exec chroot . /bin/sh'

# Dans le shell obtenu :
cat /etc/os-release      # Alpine ! ...alors que votre hôte est Ubuntu
ls /                     # l'arborescence d'Alpine, pas la vôtre
exit
```

Vous avez isolé la vue (namespaces), changé la racine (le rootfs de l'image), et obtenu... un conteneur rudimentaire. Il ne manque que les cgroups (étape 2) et un peu d'ergonomie pour être exactement ce que fait `podman run`. C'est **tout** ce qu'un moteur de conteneurs fait : le résumé de la séquence `podman run` du chapitre 15, §5, que vous venez de reconstituer à la main.

## Point de contrôle final

- [ ] Namespace UTS : hostname isolé, hôte inchangé (consigné)
- [ ] Namespace PID : PID 1 dans le namespace, même processus vu avec un autre PID depuis l'hôte
- [ ] `uid_map` lu et interprété (root dans le conteneur = votre UID sans privilège)
- [ ] cgroup mémoire : OOM kill provoqué et observé (code 137), comparé au `podman run --memory`
- [ ] « Conteneur » minimal assemblé (rootfs Alpine + chroot dans des namespaces)
- [ ] Runbook : pour chaque manipulation, la primitive du ch. 15 correspondante nommée

## Pour aller plus loin (bonus)

1. **Namespace réseau** : `unshare --user --map-root-user --net sh`, puis `ip addr` : vous n'avez qu'une interface `lo` isolée. Comment lui donner accès au réseau ? (Indice : `veth`, ce que Netavark fait pour Podman.)
2. **`podman inspect`** : lancez un conteneur (`podman run -d --name t alpine sleep 999`), puis `podman inspect t` : retrouvez, dans le JSON, les namespaces et les limites cgroup. Podman ne fait que remplir ce que vous avez fait à la main.
3. **Le problème du PID 1** : lancez `podman run --rm alpine sh -c 'sleep 5 & wait'` avec et sans `--init`. Documentez-vous sur les processus zombies et le rôle de `tini`.

## Questions de compréhension (à préparer pour le TD et l'examen)

1. Expliquez pourquoi, en rootless, il faut créer un namespace **user** *avant* de pouvoir créer un namespace PID ou réseau. Que change le namespace user aux yeux du noyau quant aux privilèges ?
2. Un collègue affirme : « un conteneur, c'est isolé comme une VM ». Réfutez précisément, en vous appuyant sur ce que vous avez vu (le processus visible depuis l'hôte, le noyau partagé).
3. Reliez les trois abstractions `systemd-run -p MemoryMax`, `podman run --memory`, et (à venir) `resources.limits.memory` de Kubernetes. Quelle est la primitive commune, et où vit-elle ?
4. Vous avez assemblé un conteneur avec namespaces + chroot + (potentiellement) cgroups. Qu'est-ce qu'un vrai moteur (Podman) ajoute que votre bricolage n'a pas ? (Pensez : gestion des images en couches, réseau, cycle de vie, sécurité seccomp.)
