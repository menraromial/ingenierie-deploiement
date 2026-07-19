# Parcours « Ingénierie du Déploiement et de la Mise en Production »

**Public :** Élèves ingénieurs en informatique (cycle ingénieur, niveau M1–M2)
**Durée :** 3 semestres — environ 60 h encadrées par semestre (CM 40 % / TD 10 % / TP 50 %)
**Fil conducteur pédagogique :** *reconstruire l'histoire du déploiement* — l'étudiant vit lui-même la douleur du déploiement manuel avant de découvrir les outils qui l'automatisent. Chaque outil est introduit comme **réponse à un problème vécu en TP**, jamais comme une recette.

---

## Philosophie générale du parcours

1. **La théorie d'abord, l'outil ensuite.** Chaque outil (Ansible, Docker, Kubernetes, Airflow…) est une implémentation de concepts durables (idempotence, isolation, réconciliation d'état, orchestration de DAG). Les outils meurent, les concepts restent : c'est sur eux que porte l'évaluation théorique.
2. **Apprendre par la friction.** On fait volontairement déployer « à la main » avant d'automatiser : l'étudiant comprend *pourquoi* l'outil existe et ce qu'il abstrait réellement.
3. **Tout en local.** Tous les TP tournent sur le poste de l'étudiant (VirtualBox/Vagrant, **Podman** comme moteur de conteneurs, minikube avec pilote Podman ou kind avec provider Podman, exécuteurs locaux d'Airflow/MLflow). Aucun compte cloud payant n'est requis ; le cloud est traité en théorie et via des émulateurs (LocalStack en démonstration). Podman est retenu plutôt que Docker : 100 % open source, sans démon, *rootless* par défaut — un choix à la fois pédagogique (architecture plus transparente) et pratique (pas de licence Docker Desktop, pas de droits administrateur nécessaires en salle de TP).
4. **Projet fil rouge.** Une même application 3-tiers (frontend + API + base de données), fournie ou développée en début de parcours, est redéployée à chaque étape avec la technologie du moment. L'étudiant mesure concrètement le gain de chaque abstraction.

### Compétences visées en fin de parcours (référentiel)

- **C1** — Concevoir et justifier une architecture de déploiement adaptée à un besoin (coût, disponibilité, sécurité, charge).
- **C2** — Provisionner et configurer une infrastructure de manière reproductible (IaC).
- **C3** — Conteneuriser, orchestrer et exposer des services applicatifs.
- **C4** — Concevoir des chaînes d'intégration et de livraison continues fiables.
- **C5** — Industrialiser le cycle de vie d'un produit d'IA (données, entraînement, serving, monitoring).
- **C6** — Diagnostiquer, observer et opérer un système en production.

---

# SEMESTRE 1 — Fondations : du serveur unique à l'Infrastructure as Code

**Objectif général :** comprendre ce qu'est *réellement* un déploiement — les couches système, réseau et applicatives — puis découvrir pourquoi et comment l'automatiser.

**Prérequis :** bases de Linux (shell), bases de réseau (IP, ports), développement web (une appli 3-tiers simple).

## Bloc 1 — Le déploiement « à l'ancienne » : tout sur une machine (semaines 1 à 5)

### Contenu théorique (CM)
- **Anatomie d'un serveur** : matériel vs machine virtuelle, hyperviseurs de type 1 et 2, notion d'hébergement (on-premise, mutualisé, dédié, cloud — panorama historique).
- **Le système d'exploitation serveur** : distributions, gestion de paquets, utilisateurs et permissions, systemd et gestion des services, journaux (journald, /var/log).
- **Réseau pour le déploiement** : modèle TCP/IP appliqué, ports et sockets, DNS, NAT, pare-feu (concepts + iptables/nftables/ufw), TLS et certificats (PKI, chaîne de confiance, Let's Encrypt en principe).
- **Architecture d'une application web déployée** : reverse proxy vs serveur d'application (pourquoi Nginx devant Gunicorn/Node), processus, workers, fichiers statiques, variables d'environnement et gestion de configuration (les « 12-factor apps », facteurs 1 à 5).
- **Sécurité de base** : SSH (clés, durcissement), principe du moindre privilège, surface d'attaque.

### TP (environnement : VirtualBox + une VM Debian/Ubuntu)
- **TP1** — Créer sa VM, installation minimale, connexion SSH par clés, durcissement de base (désactiver root login, ufw).
- **TP2** — Déployer la base de données (PostgreSQL) et le backend à la main : installation, création d'un utilisateur système dédié, service systemd écrit soi-même, variables d'environnement.
- **TP3** — Déployer le frontend + Nginx en reverse proxy, servir les statiques, certificat TLS auto-signé (puis discussion Let's Encrypt).
- **TP4** — « Jour 2 » : mise à jour applicative à la main, sauvegarde/restauration de la BD, lecture de logs pour diagnostiquer une panne injectée par l'enseignant.

> **Moment pédagogique clé (fin de bloc)** : l'enseignant demande de redéployer l'application identique sur une VM neuve en 30 minutes. Échec quasi garanti → prise de conscience : *le déploiement manuel n'est ni reproductible, ni documenté, ni scalable.*

## Bloc 2 — Architecture multi-machines : un service, une VM (semaines 6 à 8)

### Contenu théorique
- **Pourquoi séparer les services** : isolation des pannes, dimensionnement indépendant, sécurité par segmentation, montée en charge verticale vs horizontale.
- **Réseau privé entre machines** : réseaux host-only/internal, plan d'adressage, résolution de noms interne (/etc/hosts, DNS interne).
- **Répartition de charge** : Nginx/HAProxy comme load balancer, algorithmes (round-robin, least-conn), sessions et statelessness, health checks.
- **Le problème de la configuration distribuée** : dérive de configuration (*configuration drift*), « serveurs flocons de neige » vs « bétail » (*pets vs cattle*).

### TP (3 à 4 VM VirtualBox en réseau privé)
- **TP5** — Éclater l'application : VM-frontend, VM-backend, VM-BDD, toujours à la main ; câbler le réseau privé, pare-feu inter-VM (seul le backend accède à la BDD).
- **TP6** — Ajouter une 2ᵉ VM backend + un load balancer ; observer le comportement avec/sans health checks (on tue un backend en pleine charge).

## Bloc 3 — Infrastructure as Code (semaines 9 à 13)

### Contenu théorique
- **Les trois problèmes à résoudre** : provisionner (créer les machines), configurer (les mettre dans l'état voulu), orchestrer (dans le bon ordre). Cartographie des outils selon ces axes.
- **Concepts fondamentaux de l'IaC** : *déclaratif vs impératif*, **idempotence** (concept central du semestre), état désiré vs état réel, immutabilité de l'infrastructure, versionnement de l'infra dans Git.
- **Vagrant** : description déclarative de VM locales, boxes, provisioners — l'outil-pont idéal entre VirtualBox manuel et l'IaC.
- **Ansible** : architecture agentless sur SSH, inventaires, playbooks, rôles, variables, templates Jinja2, handlers ; pourquoi un module Ansible est idempotent là où un script shell ne l'est pas.
- **Terraform (théorie approfondie, TP en local)** : le graphe de ressources, le fichier d'état, plan/apply, providers ; démonstration avec le provider VirtualBox/libvirt ou Docker pour rester local ; discussion : Terraform *provisionne*, Ansible *configure* — complémentarité.

### TP
- **TP7** — Vagrantfile multi-machines reproduisant l'infra du Bloc 2 : `vagrant destroy && vagrant up` reconstruit tout le socle en minutes.
- **TP8** — Ansible : écrire les rôles `database`, `backend`, `frontend`, `loadbalancer` ; inventaire ; secrets avec ansible-vault ; prouver l'idempotence (2ᵉ exécution → 0 changement).
- **TP9** — Chaîne complète Vagrant + Ansible : *l'application entière se déploie en une commande depuis un dépôt Git vide de toute intervention manuelle.* Comparaison chronométrée avec le défi manuel du Bloc 1 — boucle pédagogique bouclée.
- **TP10 (découverte)** — Terraform avec le provider libvirt, ou le provider Docker pointé sur le socket Podman (compatible API) : décrire 2 ressources, observer le state, un `terraform plan` après modification manuelle (détection de dérive).

## Évaluation Semestre 1
- **Contrôle continu (30 %)** : comptes rendus de TP (journal de bord type « runbook »).
- **Projet (40 %)** : par binôme, déployer une application 3-tiers *différente de celle du cours* de manière 100 % automatisée (Vagrant + Ansible), avec README permettant à l'enseignant de tout reconstruire en une commande. Soutenance : injection d'une panne en direct, diagnostic commenté.
- **Examen théorique (30 %)** : questions de concepts (idempotence, drift, déclaratif/impératif, TLS, systemd…) + étude de cas d'architecture sur papier.

---

# SEMESTRE 2 — Conteneurs, orchestration et livraison continue

**Objectif général :** passer de « je déploie des machines » à « je déploie des applications » ; automatiser le chemin du commit à la production.

**Prérequis :** Semestre 1 validé (SSH, réseau, Ansible, notion d'idempotence).

## Bloc 1 — La conteneurisation (semaines 1 à 5)

### Contenu théorique
- **Pourquoi les conteneurs ?** Retour sur les limites des VM (lourdeur, temps de boot, densité) ; le problème du « ça marche sur ma machine » que même Ansible ne résout qu'à moitié.
- **Sous le capot** (cours exigeant, cœur théorique du semestre) : namespaces Linux (pid, net, mnt, uts, ipc, user), cgroups, systèmes de fichiers en couches (OverlayFS, union filesystems), différence fondamentale conteneur/VM (noyau partagé).
- **L'écosystème et les standards** : spécifications **OCI** (image, runtime, distribution) ; panorama Docker / Podman / containerd / runc / CRI-O — qui fait quoi dans la pile. **Architecture de Podman** : sans démon (*fork-exec*), *rootless* (user namespaces appliqués — lien direct avec le cours), intégration systemd (`podman generate systemd` / Quadlet : on retrouve les services du S1). Docker est présenté honnêtement comme le standard de fait en entreprise ; les commandes étant identiques (`alias docker=podman`), la compétence est transférable — c'est un point à expliciter aux étudiants.
- **Images** : Containerfile (syntaxe Dockerfile, portable), cache de build, layers, registres, tags et digests, images multi-stage, bonnes pratiques (taille, sécurité, utilisateur non-root — trivial en rootless, scan de vulnérabilités — notions avec Trivy) ; Buildah en survol.
- **Réseau et stockage des conteneurs** : bridge, port mapping, réseaux définis par l'utilisateur (Netavark), spécificités réseau du rootless (ports < 1024, pasta/slirp4netns en notions), volumes vs bind mounts, cycle de vie des données.
- **Composition** : `podman-compose` (spécification Compose) comme « IaC du poste de développeur », dépendances entre services, healthchecks, profils ; le **pod** comme unité de regroupement propre à Podman et `podman kube play` — passerelle conceptuelle idéale vers Kubernetes au bloc suivant.

### TP (Podman — tout en local, sans droits administrateur)
- **TP1** — Manipuler namespaces et cgroups à la main (unshare, cgcreate) : *construire un « conteneur » rudimentaire sans aucun moteur* pour démystifier la magie ; puis observer avec `podman unshare` et `podman inspect` que Podman fait exactement cela.
- **TP2** — Écrire les Containerfile des trois services du fil rouge, optimiser (multi-stage, ordre des layers, mesure des tailles) ; vérifier le mapping des UID en rootless.
- **TP3** — Composition complète avec `podman-compose` : réseaux, volumes, healthchecks, variables d'env ; puis regrouper les services dans un **pod** Podman et générer le YAML avec `podman kube generate` (premier contact concret avec le format Kubernetes).
- **TP4** — Registre local (image registry en conteneur), push/pull, tags, digest ; scan Trivy et correction d'une image vulnérable ; bonus : lancer le service de prédiction comme service utilisateur systemd via Quadlet (boucle avec le S1).

## Bloc 2 — Orchestration : Kubernetes (semaines 6 à 10)

### Contenu théorique
- **Le problème de l'orchestration** : que se passe-t-il quand on a 50 conteneurs sur 10 machines ? Placement, redémarrage, mise à l'échelle, découverte de services, rolling updates. Bref historique (Borg, Mesos, Swarm) et pourquoi Kubernetes a gagné.
- **Le modèle mental de Kubernetes** (insister lourdement) : API déclarative, **boucles de réconciliation** (on retrouve l'« état désiré » du S1 — continuité conceptuelle explicite), etcd, scheduler, kubelet, controllers.
- **Objets fondamentaux** : Pod, ReplicaSet, Deployment, Service (ClusterIP/NodePort/LoadBalancer), Ingress, ConfigMap, Secret, Namespace ; stockage (PV, PVC, StorageClass) ; StatefulSet pour la BDD (et discussion honnête : faut-il mettre sa BDD dans K8s ?).
- **Exploitation** : requests/limits, probes (liveness/readiness/startup), stratégies de déploiement (rolling, recreate ; blue-green et canary en concepts), RBAC en survol.
- **Helm** : templating et packaging, values, releases — « l'apt-get de Kubernetes ».

### TP (cluster local : minikube avec pilote Podman, ou kind avec `KIND_EXPERIMENTAL_PROVIDER=podman` ; k3s dans une VM Vagrant en solution de repli — à valider en amont sur les postes des salles)
- **TP5** — Premier déploiement : Deployment + Service pour le backend, scaling manuel, tuer des pods et observer l'auto-réparation (la boucle de réconciliation *vue en direct*).
- **TP6** — Application fil rouge complète : Ingress, ConfigMaps/Secrets, PVC pour la BDD, probes ; rolling update avec nouvelle image et rollback.
- **TP7** — Casser pour comprendre : série de pannes injectées (image inexistante, probe mal réglée, limites mémoire trop basses → OOMKill, service sans endpoints) ; diagnostic méthodique avec kubectl describe/logs/events.
- **TP8** — Packager le fil rouge en chart Helm avec values par environnement (dev/prod).

## Bloc 3 — CI/CD et observabilité (semaines 11 à 14)

### Contenu théorique
- **Intégration continue** : pourquoi (théorème « ce qui fait mal doit être fait souvent »), pipelines, étapes canoniques (lint, tests, build, scan), artefacts, runners.
- **Livraison vs déploiement continus** : définitions rigoureuses, environnements, promotion d'artefacts, gestion des versions (SemVer, tags d'images), stratégie de branches (trunk-based vs git-flow — débat).
- **GitOps** : le dépôt Git comme unique source de vérité de l'état désiré ; pull vs push deployment ; Argo CD/Flux en concepts, démonstration Argo CD sur cluster local.
- **Observabilité (introduction)** : logs / métriques / traces, Prometheus (modèle pull, PromQL de base), Grafana, alerting ; SLI/SLO en notions.

### TP (Gitea + Gitea Actions en conteneurs Podman, ou GitLab CE en conteneur — pas de dépendance à un SaaS ; le socket API de Podman étant compatible Docker, les runners fonctionnent en pointant `DOCKER_HOST` vers le socket Podman)
- **TP9** — Monter sa forge locale (Gitea en conteneur) + un runner ; premier pipeline : lint + tests sur le backend.
- **TP10** — Pipeline complet : build d'image → scan Trivy → push au registre local → mise à jour automatique du tag dans les manifests → déploiement sur le cluster kind. Un commit sur main déclenche la mise en production locale de bout en bout.
- **TP11** — Prometheus + Grafana sur le cluster (kube-prometheus-stack via Helm), dashboard pour le fil rouge, une alerte simple (taux d'erreurs HTTP).

## Évaluation Semestre 2
- **Contrôle continu (25 %)** : TP notés (en particulier TP7 « diagnostic de pannes », en temps limité).
- **Projet (45 %)** : par binôme — conteneuriser une application, la packager en chart Helm, pipeline CI/CD complet sur forge locale, monitoring de base. Soutenance : *live demo* d'un commit qui part en « production », puis panne surprise à diagnostiquer.
- **Examen théorique (30 %)** : namespaces/cgroups, modèle de réconciliation, objets K8s, conception d'un pipeline pour un cas donné, questions d'architecture (VM vs conteneurs vs les deux).

---

# SEMESTRE 3 — Mise en production des produits d'IA et de la donnée (MLOps & Big Data)

**Objectif général :** appliquer toute la stack des semestres 1–2 au cas particulier — et plus difficile — des produits pilotés par les données et les modèles.

**Prérequis :** S1 + S2 ; bases de Python et de machine learning (un modèle scikit-learn suffit ; ce n'est **pas** un cours de ML, c'est un cours d'industrialisation du ML).

## Bloc 1 — Pourquoi le ML en production est différent (semaines 1 à 3)

### Contenu théorique
- **Dette technique du ML** (lecture guidée du papier *« Hidden Technical Debt in Machine Learning Systems »*, Google) : le code du modèle est 5 % du système.
- **Les trois axes de versionnement** : code (Git), données (DVC — principes du stockage adressé par contenu), modèles (registres) ; reproductibilité d'une expérience.
- **Cycle de vie MLOps** : données → features → entraînement → évaluation → déploiement → monitoring → ré-entraînement ; niveaux de maturité MLOps (0/1/2 selon Google).
- **Patterns de serving** : batch vs temps réel vs streaming ; modèle embarqué vs modèle-service ; latence/débit/coût.

### TP (tout en local, Python + Podman)
- **TP1** — Chaos volontaire : l'enseignant fournit un notebook « recherche » désordonné qui produit un bon modèle ; les étudiants doivent le re-exécuter → échec (chemins en dur, données modifiées, seeds absents). Prise de conscience fondatrice du semestre.
- **TP2** — Restructurer : du notebook au projet Python propre (scripts paramétrés, config, seeds), versionner les données avec DVC (remote = dossier local ou MinIO en conteneur).

## Bloc 2 — Outillage du cycle de vie : MLflow et Airflow (semaines 4 à 8)

### Contenu théorique
- **Suivi d'expériences** : pourquoi tracker (params, métriques, artefacts), MLflow Tracking (architecture, backend store/artifact store), MLflow Models (le format pyfunc comme interface universelle), Model Registry (stades, promotion, lineage).
- **Orchestration de workflows de données** : le **DAG** comme abstraction centrale ; différence profonde entre orchestrateur de *services* (Kubernetes : processus longs, réconciliation) et orchestrateur de *tâches* (Airflow : exécutions finies, dépendances, reprises) — les étudiants doivent savoir articuler les deux.
- **Airflow** : scheduler, executor, tâches idempotentes (encore elle !), backfill, capteurs, XCom, bonnes pratiques (tâches atomiques, pas de calcul dans le scheduler).
- **Serving de modèles** : exposer un modèle en API (FastAPI), validation d'entrées (Pydantic), batching, versions de modèles côté API, tests de charge (locust) — et conteneurisation du service de prédiction.

### TP (MLflow en local, Airflow via podman-compose — le fichier Compose officiel d'Airflow fonctionne avec Podman moyennant quelques ajustements, à fournir prêts à l'emploi aux étudiants)
- **TP3** — Instrumenter l'entraînement avec MLflow, comparer 20 runs, enregistrer le meilleur modèle au registry, le promouvoir.
- **TP4** — Servir : API FastAPI qui charge le modèle depuis le registry, Dockerfile, tests, mesure de latence ; déploiement sur le cluster kind du S2 (réutilisation explicite des acquis).
- **TP5** — Airflow : DAG complet *ingestion → validation des données (Great Expectations en découverte) → entraînement → évaluation → promotion conditionnelle du modèle* ; test d'un backfill.
- **TP6** — Chaîne intégrée : un commit déclenche la CI (S2) qui reconstruit l'image de serving ; le DAG Airflow ré-entraîne chaque nuit ; le meilleur modèle est promu automatiquement si les métriques dépassent le champion. Le « CD du modèle ».

## Bloc 3 — Kubeflow, monitoring des modèles, et Big Data (semaines 9 à 13)

### Contenu théorique
- **ML sur Kubernetes** : pourquoi (GPU, isolation, scaling des entraînements) ; panorama Kubeflow (Pipelines, notebooks, KServe) — présenté honnêtement comme lourd, TP ciblé sur Kubeflow Pipelines local ou KServe sur kind ; comparaison critique Airflow vs Kubeflow Pipelines (quand choisir quoi).
- **Monitoring spécifique au ML** : dérive des données et des concepts (*data drift / concept drift*, tests statistiques en intuition), monitoring de performance différée (le label arrive après), boucles de feedback ; outil : Evidently en local, intégré à Grafana (S2).
- **Big Data — fondements** : pourquoi une machine ne suffit plus (les 3V), calcul distribué, MapReduce en concept, **Spark** (RDD → DataFrames, lazy evaluation, partitions, shuffle — comprendre le shuffle est l'objectif théorique), formats de données (Parquet vs CSV, columnar), architectures batch/streaming (Kafka en concepts + mini-TP), lakehouse en panorama (survol Delta/Iceberg).
- **Éthique et responsabilité de la mise en production d'IA** (1 séance) : biais amplifiés à l'échelle, monitoring d'équité, RGPD et données d'entraînement, documentation (model cards).

### TP
- **TP7** — Spark en local (mode standalone via pip ou conteneur) : traiter un dataset de plusieurs Go en Parquet, observer l'UI Spark, provoquer et diagnostiquer un shuffle coûteux, comparer CSV vs Parquet.
- **TP8** — Kafka (mode KRaft, un seul conteneur Podman) : producteur d'événements de prédiction → consommateur qui calcule des métriques glissantes.
- **TP9** — Drift : rejouer un jeu de données dérivé sur le modèle en production locale, détection avec Evidently, alerte Grafana, déclenchement automatique du DAG de ré-entraînement. *La boucle MLOps complète tourne sur le poste de l'étudiant.*
- **TP10 (découverte)** — KServe ou Kubeflow Pipelines sur kind : déployer le modèle du fil rouge via une InferenceService ; comparer avec l'approche FastAPI « maison » du TP4.

## Évaluation Semestre 3
- **Contrôle continu (20 %)** : TP notés + une fiche de lecture critique (papier « Hidden Technical Debt »).
- **Projet final de parcours (50 %)** : par trinôme, industrialiser de bout en bout un produit IA au choix (validation du sujet en semaine 4) : données versionnées, entraînement reproductible orchestré, tracking + registry, serving conteneurisé déployé sur Kubernetes via CI/CD, monitoring technique **et** monitoring de drift, ré-entraînement automatisé. Livrables : dépôt Git, architecture documentée (schéma + justification des choix — évalue C1), démo live, *post-mortem* d'une panne simulée.
- **Examen théorique (30 %)** : questions transversales aux 3 semestres (ex. : « comparez la boucle de réconciliation Kubernetes et le scheduling Airflow », « concevez l'architecture de déploiement complète de tel produit IA, justifiez chaque brique »).

---

## Annexes pour l'équipe pédagogique

### Matériel requis (poste étudiant)
16 Go de RAM recommandés (8 Go minimum avec adaptations : kind plutôt que minikube, datasets réduits). Moteur de conteneurs : **Podman** (natif sous Linux ; via `podman machine` sous Windows/macOS — dans ce cas prévoir la RAM de la VM Podman dans le budget mémoire). Tous les outils sont gratuits et open source, et le mode rootless évite d'accorder des droits administrateur aux étudiants sur les postes des salles. Prévoir un registre-miroir local des images de conteneurs et des boxes Vagrant pour économiser la bande passante. **Point de vigilance** : tester en amont la chaîne kind/minikube-sur-Podman et les fichiers Compose (Airflow, Gitea) sur l'image de poste des salles de TP, et figer les versions dans un guide d'installation distribué en semaine 1.

### Progression des concepts transversaux (à rendre explicite aux étudiants)
| Concept | S1 | S2 | S3 |
|---|---|---|---|
| Idempotence | Ansible | Manifests K8s, pipelines | Tâches Airflow |
| État désiré / réconciliation | Terraform (plan/state) | Boucles de contrôle K8s, GitOps | Promotion auto des modèles |
| Reproductibilité | Vagrant + Ansible | Images immuables | DVC + MLflow + seeds |
| Isolation | VM, segmentation réseau | Namespaces, cgroups, rootless | Environnements d'entraînement |
| Observabilité | Logs systemd | Prometheus/Grafana | Drift, métriques différées |

### Bibliographie de référence
- Kief Morris, *Infrastructure as Code* (O'Reilly)
- Nigel Poulton, *The Kubernetes Book* ; documentation officielle Kubernetes (« Concepts »)
- Jez Humble & David Farley, *Continuous Delivery*
- Google, *Site Reliability Engineering* (gratuit en ligne)
- Sculley et al., *Hidden Technical Debt in Machine Learning Systems* (NeurIPS 2015)
- Chip Huyen, *Designing Machine Learning Systems* (O'Reilly)
- Martin Kleppmann, *Designing Data-Intensive Applications* (O'Reilly) — pour le bloc Big Data

### Conseils de mise en œuvre
- **Les pannes injectées sont le meilleur outil pédagogique du parcours** : préparer pour chaque semestre une banque de pannes scénarisées (service down, certificat expiré, OOMKill, probe défaillante, drift de données) et les réutiliser en soutenance.
- Exiger dès le S1 que tout livrable soit un dépôt Git dont le README permet une reconstruction complète : c'est le critère d'évaluation le plus discriminant et le plus professionnalisant.
- Inviter si possible un·e SRE/MLOps engineer en activité une fois par semestre (retour d'expérience d'incident réel).