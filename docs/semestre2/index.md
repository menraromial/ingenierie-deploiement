# Semestre 2 : Conteneurs, orchestration et livraison continue

**Objectif général :** passer de « je déploie des machines » à « je déploie des applications » ; automatiser le chemin du commit à la production.

**Prérequis :** Semestre 1 validé (SSH, réseau, Ansible, notion d'idempotence).

!!! info "Contenu en cours de rédaction"
    Le contenu détaillé de ce semestre sera publié bloc par bloc, dans l'ordre du parcours. Le plan ci-dessous est contractuel.

## Plan du semestre

### Bloc 1 : la conteneurisation (semaines 1 à 5)

- Pourquoi les conteneurs : limites des VM, le problème du « ça marche sur ma machine ».
- Sous le capot (cœur théorique du semestre) : namespaces Linux, cgroups, systèmes de fichiers en couches (OverlayFS), différence fondamentale conteneur/VM.
- L'écosystème et les standards OCI : Docker / Podman / containerd / runc / CRI-O ; architecture sans démon et rootless de Podman.
- Images : Containerfile, cache de build, layers, registres, multi-stage, scan Trivy.
- Réseau et stockage des conteneurs ; composition avec `podman-compose` ; le pod et `podman kube play` comme passerelle vers Kubernetes.
- **TP 1 à 4** : construire un conteneur sans moteur (unshare, cgroups), Containerfile du fil rouge, composition complète, registre local et scan de vulnérabilités.

### Bloc 2 : orchestration, Kubernetes (semaines 6 à 10)

- Le problème de l'orchestration ; historique (Borg, Mesos, Swarm) et pourquoi Kubernetes a gagné.
- Le modèle mental : API déclarative, boucles de réconciliation, etcd, scheduler, kubelet.
- Objets fondamentaux : Pod, Deployment, Service, Ingress, ConfigMap, Secret, PV/PVC, StatefulSet.
- Exploitation : requests/limits, probes, stratégies de déploiement, RBAC en survol ; Helm.
- **TP 5 à 8** : premier déploiement et auto-réparation vue en direct, fil rouge complet sur cluster local, diagnostic de pannes injectées, packaging Helm.

### Bloc 3 : CI/CD et observabilité (semaines 11 à 14)

- Intégration continue, livraison vs déploiement continus, promotion d'artefacts, stratégies de branches.
- GitOps : le dépôt Git comme unique source de vérité ; Argo CD en démonstration.
- Observabilité : logs / métriques / traces, Prometheus, Grafana, SLI/SLO en notions.
- **TP 9 à 11** : forge locale Gitea + runner, pipeline complet du commit au déploiement sur cluster, monitoring kube-prometheus-stack.

## Évaluation du semestre

| Épreuve | Poids | Modalités |
|---|---|---|
| Contrôle continu | 25 % | TP notés, en particulier le TP 7 « diagnostic de pannes » en temps limité |
| Projet | 45 % | Par binôme : conteneuriser une application, chart Helm, pipeline CI/CD sur forge locale, monitoring. Soutenance : live demo d'un commit qui part en production, panne surprise à diagnostiquer |
| Examen théorique | 30 % | Namespaces/cgroups, modèle de réconciliation, objets K8s, conception de pipeline, VM vs conteneurs |
