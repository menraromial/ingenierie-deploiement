---
title: "Vue d'ensemble"
sidebar_label: "Vue d'ensemble"
hide_title: true
---

import ChapterHead from '@site/src/components/ChapterHead';
import Figure from '@site/src/components/Figure';

<ChapterHead
  kicker="Semestre 2 · Conteneurs, orchestration, CI/CD"
  title="Semestre 2 : Conteneurs, orchestration et livraison continue"
  lecture="5 min"
/>

**Objectif général :** passer de « je déploie des machines » à « je déploie des applications » ; automatiser le chemin du commit à la production.

**Prérequis :** Semestre 1 validé (SSH, réseau, Ansible, notion d'idempotence, état désiré / réconciliation).

## Là où le semestre 1 s'est arrêté

Au bloc 3 du S1, une commande reconstruisait quatre machines et y déployait Listify. Mais vous avez vous-mêmes listé ce qui restait fragile (TP 9, étape 3, point 4) : l'orchestration était un script, la reconstruction détruisait tout au lieu de faire évoluer en douceur, et surtout **l'unité de déploiement restait la machine**. Ce semestre change d'unité : on ne déploie plus des machines, on déploie des **applications empaquetées** (des conteneurs), et on confie leur cycle de vie à un **orchestrateur** qui les place, les redémarre, les met à l'échelle et les remplace sans coupure. Le fil rouge Listify est repris et conteneurisé.

<Figure src="s2-parcours" alt="Trois blocs de gauche à droite : conteneurisation avec Podman, orchestration avec Kubernetes, puis CI/CD et observabilité.">
  Les trois blocs du semestre 2. Chacun s'appuie sur le précédent : on n'orchestre bien que ce qu'on sait conteneuriser, on n'automatise bien que ce qu'on sait orchestrer.
</Figure>

## La continuité conceptuelle avec le S1 (à rendre explicite)

Ce semestre n'introduit pas des idées neuves : il **incarne à une autre échelle** les concepts du S1. Gardez cette table sous les yeux, elle est le fil de révision et une source d'exercices d'examen.

| Concept du S1 | Sa forme au S2 |
|---|---|
| Isolation (VM, utilisateurs système) | **Namespaces et cgroups** Linux (bloc 1) : l'isolation *dans* un noyau partagé |
| Immutabilité (« phénix », `destroy && up`) | L'**image de conteneur** : artefact immuable par construction (bloc 1) |
| État désiré / réconciliation (Terraform, Ansible) | Les **boucles de contrôle** de Kubernetes, en continu (bloc 2) |
| Idempotence (modules Ansible) | Les **manifests** déclaratifs `kubectl apply` (bloc 2) |
| Auto-réparation (systemd `Restart=`, master Gunicorn) | Les **contrôleurs** qui recréent les Pods morts (bloc 2) |
| Reverse proxy, load balancer (Nginx du S1) | **Service** et **Ingress** (bloc 2) |
| Le `deploy.sh` (orchestration écrite) | Le **pipeline CI/CD** et le **GitOps** (bloc 3) |
| Observabilité (journaux systemd) | **Prometheus / Grafana**, métriques et SLO (bloc 3) |

## Un semestre plus exigeant en théorie

Le S1 était surtout pratique. Le S2 a un **cœur théorique** revendiqué (namespaces/cgroups au bloc 1, modèle de réconciliation au bloc 2) sur lequel porte l'examen. Pour nourrir votre esprit critique et vous ouvrir à la recherche, chaque chapitre comporte une rubrique **« Regard recherche »** qui pointe vers les articles scientifiques fondateurs : les papiers Google sur Borg et Omega, la comparaison IBM entre machines virtuelles et conteneurs, Dapper sur le traçage distribué, la recherche empirique DORA sur la performance des équipes... Ces lectures ne sont pas obligatoires, mais un ingénieur qui veut innover doit savoir remonter aux sources primaires, et non se contenter de tutoriels.

## Organisation

- **[Bloc 1](bloc1/index.md) (semaines 1 à 5) : la conteneurisation.** Ce qu'est *réellement* un conteneur (on en construit un à la main, sans moteur), les standards OCI, les images, le réseau et la composition, avec Podman.
- **Bloc 2 (semaines 6 à 10) : orchestration, Kubernetes.** Le problème de l'orchestration, le modèle mental de la réconciliation, les objets fondamentaux, Helm.
- **Bloc 3 (semaines 11 à 14) : CI/CD et observabilité.** Du commit à la production, GitOps, monitoring.

## Environnement de travail

- **Moteur de conteneurs : Podman** (sans démon, *rootless*), déjà présent sur les postes ; aucun droit administrateur requis.
- **Cluster Kubernetes local** (bloc 2) : minikube (pilote Podman) ou kind ; k3s dans une VM Vagrant en repli.
- **Forge locale** (bloc 3) : Gitea + runner en conteneurs. Aucune dépendance à un service en ligne payant.

## Évaluation du semestre

| Épreuve | Poids | Modalités |
|---|---|---|
| Contrôle continu | 25 % | TP notés, en particulier le TP de diagnostic de pannes Kubernetes en temps limité |
| Projet | 45 % | Par binôme : conteneuriser une application, la packager en chart Helm, pipeline CI/CD complet sur forge locale, monitoring de base. Soutenance : live demo d'un commit qui part en production, puis panne surprise à diagnostiquer |
| Examen théorique | 30 % | Namespaces/cgroups, modèle de réconciliation, objets K8s, conception d'un pipeline, questions d'architecture (VM vs conteneurs vs les deux) |
