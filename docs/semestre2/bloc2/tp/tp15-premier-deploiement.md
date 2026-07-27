# TP 15 : Premier déploiement et auto-réparation en direct

!!! abstract "Fiche du TP"
    - **Durée** : 4 h
    - **Prérequis** : bloc 1 du S2 ; chapitres 19 et 20
    - **Livrables** : un cluster kind fonctionnel ; un Deployment + Service ; le compte rendu de l'auto-réparation et du scaling observés ; runbook
    - **Compétences travaillées** : C3 (cœur), C6

    Vous montez votre premier cluster Kubernetes local et vous **voyez la boucle de réconciliation (ch. 20) fonctionner en direct** : vous tuez des Pods, le cluster les recrée. C'est le TP qui rend le modèle mental concret. Commandes validées sur kind + Podman.

## Étape 0 : faire de la place (10 min)

Un cluster Kubernetes local consomme de la RAM (le nœud kind, plus les Pods du plan de contrôle). Avant de commencer, **libérez les conteneurs du bloc 1** que vous n'utilisez plus (ils ne servent plus ici) :

```bash
# Arrêter la composition et le pod du fil rouge (bloc 1), si encore actifs
podman-compose down 2>/dev/null    # depuis ~/Github/edu/listify, si vous l'aviez lancé
podman pod rm -f listify-pod 2>/dev/null
# Arrêter le service systemd du TP 14, s'il tourne encore
systemctl --user stop listify-backend.service 2>/dev/null
# Vue d'ensemble de ce qui reste
podman ps
```

Vos **images** Listify (`listify-backend:1.0`, `listify-frontend:1.0`), elles, restent : on les réutilisera au TP 16. On ne libère que les conteneurs *en marche*.

## Étape 1 : monter un cluster kind (45 min)

**kind** (*Kubernetes IN Docker*) crée un cluster Kubernetes dont les nœuds sont des **conteneurs** : léger, jetable, parfait pour apprendre.

Une précision sur la première ligne ci-dessous : par défaut, kind cherche à piloter **Docker**. Comme tout notre parcours utilise **Podman**, on le lui indique par une variable d'environnement, `KIND_EXPERIMENTAL_PROVIDER=podman`. On la **`export`** pour qu'elle vaille dans tout le shell (toutes les commandes `kind` de la session la liront) ; sans elle, `kind` tenterait de joindre un démon Docker inexistant et échouerait.

```bash
# 1. Dire à kind d'utiliser Podman (et non Docker), pour toute la session
export KIND_EXPERIMENTAL_PROVIDER=podman

# 2. Créer un cluster (télécharge l'image de nœud la première fois : ~1 min).
#    On lance kind dans un scope systemd utilisateur DÉLÉGUÉ (voir l'encadré) :
systemd-run --user --scope --property=Delegate=yes kind create cluster --name listify

# 3. kubectl est automatiquement configuré vers ce cluster
kubectl cluster-info
kubectl get nodes
```

!!! danger "kind rootless : `requires setting systemd property Delegate=yes`"
    En **rootless**, kind a besoin que les contrôleurs cgroup (cpu, memory, pids) soient **délégués** à votre utilisateur par systemd. Votre terminal interactif tourne dans une `session.scope` qui **n'hérite pas** de cette délégation, d'où l'erreur `running kind with rootless provider requires setting systemd property "Delegate=yes"`. Deux remèdes :

    - **Immédiat, sans droits root** (recommandé) : lancez la création dans un scope délégué, comme ci-dessus :

        ```bash
        systemd-run --user --scope --property=Delegate=yes kind create cluster --name listify
        ```

        Seule la **création** du cluster l'exige ; ensuite, `kubectl` fonctionne normalement.

    - **Permanent, une fois pour toutes (droits root)** : déléguer explicitement au gestionnaire utilisateur, puis se reconnecter :

        ```bash
        sudo mkdir -p /etc/systemd/system/user@.service.d
        printf '[Service]\nDelegate=cpu cpuset io memory pids\n' | \
          sudo tee /etc/systemd/system/user@.service.d/delegate.conf
        sudo systemctl daemon-reload
        # puis DÉCONNEXION/RECONNEXION (ou reboot) ; ensuite `kind create` marche seul
        ```

    **Attention : c'est valable pour `create` ET `delete`.** Le processus réseau du nœud est lancé dans le scope délégué à la création ; une `kind delete cluster` depuis un shell non délégué échouera sur `rootless netns: kill network process: permission denied`. Préfixez donc **toute** commande `kind` par `systemd-run --user --scope --property=Delegate=yes`. Le remède permanent (le drop-in ci-dessus), lui, fait fonctionner `kind` nu dans n'importe quel shell après reconnexion, sans `systemd-run` : sur les postes de TP, le guide d'installation l'applique en amont ; sinon, `systemd-run` dépanne à tout moment.

Vous obtenez un nœud `listify-control-plane` en `Ready`. Ce nœud est un conteneur Podman (`podman ps` le montre) qui fait tourner un Kubernetes complet à l'intérieur. Kubernetes **dans** un conteneur **dans** votre poste : l'emboîtement des abstractions du parcours.

!!! note "kubectl : votre nouvelle ligne de commande"
    `kubectl` (prononcé « cube-ceu-t-l » ou « cube-control ») parle à l'**API server** (ch. 20). Chaque commande est une interaction avec l'unique porte d'entrée du cluster. Les verbes de base : `get` (lister), `describe` (détailler + événements), `apply` (soumettre un état désiré), `delete`, `logs`. Ajoutez `alias k=kubectl` à votre shell, vous le taperez des centaines de fois.

??? question "Point de contrôle n° 1"
    - `kubectl get nodes` : un nœud `Ready`.
    - `podman ps | grep listify` : le nœud est bien un conteneur Podman.
    - `kubectl get pods -A` : les Pods du **plan de contrôle** (api-server, etcd, scheduler, controller-manager, coredns...) tournent dans le namespace `kube-system`. Retrouvez chaque composant du chapitre 20 dans cette liste, et notez-les au runbook.

## Étape 2 : le premier Deployment, la réconciliation vue en direct (1 h 30)

### 2.1 Créer un Deployment

```bash
kubectl create deployment web --image=nginx:1.27-alpine --replicas=3
kubectl rollout status deployment/web          # attend que les 3 Pods soient prêts
kubectl get pods -l app=web -o wide
```

Trois Pods `web-...` apparaissent, chacun avec sa propre IP. Vous venez de déclarer un **état désiré** (« 3 répliques de nginx ») ; le Deployment controller, via un ReplicaSet, l'a réalisé (ch. 21).

### 2.2 L'expérience fondatrice : tuer un Pod

Le moment que tout le chapitre 20 préparait. Dans un terminal, observez en continu :

```bash
kubectl get pods -l app=web --watch          # laisse défiler les changements
```

Dans un **second** terminal, tuez un Pod :

```bash
kubectl delete pod <un-nom-de-pod-web>
```

Regardez le premier terminal : le Pod passe en `Terminating`, et **presque instantanément un nouveau Pod apparaît** et démarre. Vous n'avez rien demandé de tel. Le ReplicaSet controller a **observé** l'écart (2 réels ≠ 3 désirés) et **agi** (créer 1 Pod), exactement la boucle du chapitre 20, §2. Consignez au runbook : le nom du Pod détruit, le nom du nouveau (différent), le délai. C'est l'**auto-réparation**, et elle est *gratuite* : conséquence directe de la réconciliation, pas un mécanisme ajouté.

!!! tip "Poussez l'expérience"
    Essayez `kubectl delete pod -l app=web` (le sélecteur suffit pour tuer les trois d'un coup ; ne pas y ajouter `--all`, incompatible avec un sélecteur) : le cluster en recrée trois. Puis `kubectl scale deployment/web --replicas=0` : là, ils disparaissent et **ne reviennent pas**, car l'état désiré est maintenant zéro. La différence est capitale : supprimer un Pod ne change pas l'état désiré (le Deployment le recrée) ; changer `replicas` **change l'état désiré**. Notez cette distinction, elle est au cœur du modèle.

## Étape 3 : le Service, une adresse stable (45 min)

Les Pods ont des IP éphémères. Exposons-les derrière un **Service** (ch. 21) :

```bash
kubectl expose deployment web --port=80 --name=web
kubectl get service web            # une CLUSTER-IP stable apparaît
kubectl describe service web       # les "Endpoints" listent les IP des 3 Pods
```

Vérifiez la découverte + répartition depuis un Pod éphémère **dans** le cluster (le Service n'est pas exposé à l'hôte, il est interne, c'est un ClusterIP) :

```bash
kubectl run test --rm -it --restart=Never --image=curlimages/curl -- \
  sh -c 'for i in 1 2 3 4; do curl -s -o /dev/null -w "%{http_code}\n" http://web; done'
```

Puis la preuve que le Service **suit les labels** : tuez un Pod, et `kubectl describe service web` montre que la liste des Endpoints s'est mise à jour toute seule (le mort retiré, le nouveau ajouté). Le Service est stable ; les Pods derrière lui vont et viennent. C'est la découverte de services + load balancing natifs du chapitre 21.

Pour y accéder **depuis votre poste** (le Service étant interne), utilisez un tunnel :

```bash
kubectl port-forward service/web 8088:80
# dans un autre terminal : curl http://localhost:8088 → la page nginx
```

## Étape 4 : lire l'état comme un opérateur (30 min)

Prenez le réflexe des commandes de lecture, qui seront votre quotidien au TP 17 :

```bash
kubectl get all                          # vue d'ensemble du namespace
kubectl get pods -o wide                 # Pods + nœuds + IP
kubectl describe deployment web          # l'état désiré, la stratégie, les événements
kubectl logs -l app=web --tail=20        # les logs des Pods
kubectl get events --sort-by=.lastTimestamp   # ce que les contrôleurs ont fait, dans l'ordre
```

`get` montre le **réel**, `describe` montre le désiré **et les événements** (ce que les contrôleurs ont tenté). Cette distinction est la base du diagnostic (ch. 20, §4).

## Étape 5 : nettoyage de fin de séance (10 min)

Supprimez les objets de démonstration (le Deployment `web` et son Service), qui n'ont servi qu'à ce TP :

```bash
kubectl delete service web
kubectl delete deployment web
kubectl get all                 # ne doit plus rien montrer d'autre que 'service/kubernetes'
```

En revanche, **gardez le cluster kind** : les TP 16, 17 et 18 le réutilisent. Deux cas de figure :

- **Vous enchaînez bientôt sur le TP 16** : ne touchez à rien, le cluster reste prêt.
- **Vous arrêtez pour un moment** (fin de journée, extinction du poste) : un cluster kind survit mal à un redémarrage de la machine. Le plus propre est alors de le **supprimer** et de le **recréer** au début du TP 16 :

    ```bash
    # DANS le scope délégué, comme la création (voir l'encadré de l'étape 1) :
    systemd-run --user --scope --property=Delegate=yes kind delete cluster --name listify
    # (au TP 16, on recrée le cluster avec la même commande systemd-run qu'à l'étape 1)
    ```

Retenez la règle générale, valable pour tout le bloc : **un cluster kind est jetable**. Le supprimer et le recréer coûte une minute et garantit un état propre, exactement l'esprit « bétail » du S1.

## Point de contrôle final

- [ ] Cluster kind `Ready` ; composants du plan de contrôle identifiés dans `kube-system`
- [ ] Deployment web à 3 répliques ; les 3 Pods `Running`
- [ ] **Auto-réparation observée** : Pod tué → recréé (noms et délai au runbook)
- [ ] Distinction comprise : supprimer un Pod (recréé) vs `scale --replicas=0` (état désiré changé)
- [ ] Service créé ; Endpoints suivant les labels (prouvé après suppression d'un Pod)
- [ ] Accès via `port-forward` ; commandes de lecture maîtrisées

## Pour aller plus loin (bonus)

1. **Le YAML derrière la commande** : `kubectl get deployment web -o yaml`. Retrouvez `spec.replicas`, le `selector` de labels, le `template` de Pod. Toute commande `kubectl create` produit un objet YAML : au TP 16, vous les écrirez directement.
2. **Deux nœuds** : recréez le cluster avec un fichier de config kind à 1 control-plane + 2 workers. Observez sur quels nœuds le scheduler place les Pods (`kubectl get pods -o wide`). Le placement du chapitre 19, en vrai.
3. **La réconciliation contre vous** : essayez de supprimer le ReplicaSet créé par le Deployment (`kubectl delete rs ...`). Que se passe-t-il ? (Le Deployment controller en recrée un : la réconciliation opère à *tous* les niveaux.)

## Questions de compréhension (à préparer pour le TD et l'examen)

1. Décrivez, en termes de boucle de réconciliation (ch. 20), ce qui se passe exactement entre le moment où vous tapez `kubectl delete pod` et l'apparition d'un nouveau Pod. Nommez le contrôleur responsable et son observation/comparaison/action.
2. Pourquoi supprimer un Pod le fait-il revenir, alors que `scale --replicas=0` le fait disparaître définitivement ? Qu'est-ce qui distingue les deux au regard de l'« état désiré » ?
3. Un Service a une IP stable alors que les Pods derrière lui changent d'IP. Par quel mécanisme le Service sait-il toujours quels Pods viser ? (Indice : ce n'est pas par leur nom.)
4. Vous n'avez à aucun moment dit « recrée le Pod » ni « répare ». D'où vient alors l'auto-réparation ? Reliez à la nature *level-triggered* du système (ch. 20).
