# TP 16 : Listify complet sur Kubernetes

!!! abstract "Fiche du TP"
    - **Durée** : 4 h
    - **Prérequis** : TP 15 ; chapitre 21
    - **Livrables** : le dossier `k8s/` de manifests committé ; Listify fonctionnel sur le cluster ; un rolling update et un rollback prouvés ; runbook
    - **Compétences travaillées** : C3 (cœur), C6

    Vous reconstruisez Listify **entièrement en objets Kubernetes** : Namespace, Secret, base en StatefulSet avec stockage persistant, backend et frontend en Deployments, exposition par Services. Tous les manifests de ce TP ont été appliqués et validés sur kind + Podman.

## Étape 0 : le cluster est-il là ? (5 min)

Ce TP réutilise le cluster kind du TP 15.

```bash
export KIND_EXPERIMENTAL_PROVIDER=podman
kind get clusters                  # 'listify' doit apparaître
kubectl get nodes                  # le nœud doit être Ready
```

Si le cluster n'existe plus (vous l'aviez supprimé en fin de TP 15, ou après un redémarrage du poste), recréez-le, comme au TP 15 :

```bash
systemd-run --user --scope --property=Delegate=yes kind create cluster --name listify
```

## Étape 1 : charger les images dans le cluster (30 min)

kind ne voit **pas** les images de votre Podman local : ses nœuds sont des conteneurs isolés. Il faut donc **charger** vos images Listify (construites au TP 12) dans le cluster :

```bash
export KIND_EXPERIMENTAL_PROVIDER=podman
# Exporter chaque image en archive, puis la charger dans kind (provider podman)
podman save -o /tmp/lb.tar localhost/listify-backend:1.0
podman save -o /tmp/lf.tar localhost/listify-frontend:1.0
kind load image-archive /tmp/lb.tar --name listify
kind load image-archive /tmp/lf.tar --name listify
rm -f /tmp/lb.tar /tmp/lf.tar
```

C'est le pendant local du `push` vers un registre (TP 14) : en production, les nœuds tireraient les images d'un registre ; ici, on les injecte directement. Le manifeste utilisera `imagePullPolicy: IfNotPresent` pour que Kubernetes se serve de l'image locale au lieu de tenter un `pull` distant.

## Étape 2 : le socle, Namespace et Secret (30 min)

Créez un dossier `k8s/` dans votre dépôt. Chaque objet est un fichier numéroté (l'ordre aide à la lecture ; `kubectl apply -f k8s/` les applique tous).

```yaml title="k8s/00-namespace.yaml"
apiVersion: v1
kind: Namespace
metadata:
  name: listify
```

```yaml title="k8s/10-secret.yaml"
apiVersion: v1
kind: Secret
metadata:
  name: listify-db
  namespace: listify
type: Opaque
stringData:
  DB_PASSWORD: "un-mot-de-passe-fort"
```

Le **Namespace** cloisonne tous nos objets (ch. 21, §6). Le **Secret** porte le mot de passe (ch. 21, §5 ; rappelez-vous : base64, pas chiffré, ne jamais le committer avec une vraie valeur : en production, on le génère hors du dépôt).

## Étape 3 : la base en StatefulSet (1 h)

La base a besoin d'une **identité stable** et d'un **stockage persistant** : c'est le cas d'usage du **StatefulSet** (ch. 21, §7). Le schéma et la migration sont chargés au premier démarrage via une **ConfigMap** montée dans le répertoire d'init de l'image postgres (l'équivalent Kubernetes du montage du TP 13).

```bash
# ConfigMap contenant schéma + migration (ordonnés), depuis vos fichiers
kubectl create configmap db-init --namespace listify \
  --from-file=00-schema.sql=db/schema.sql \
  --from-file=01-add-done.sql=db/migrations/001-add-done.sql \
  --dry-run=client -o yaml > k8s/20-db-init-configmap.yaml
```

```yaml title="k8s/30-db.yaml"
apiVersion: v1
kind: Service
metadata:
  name: db
  namespace: listify
spec:
  clusterIP: None          # Service "headless" : DNS direct vers le Pod db-0
  selector: { app: listify, tier: db }
  ports: [{ port: 5432 }]
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: db
  namespace: listify
spec:
  serviceName: db
  replicas: 1
  selector:
    matchLabels: { app: listify, tier: db }
  template:
    metadata:
      labels: { app: listify, tier: db }
    spec:
      containers:
        - name: postgres
          image: docker.io/library/postgres:16-alpine
          env:
            - { name: POSTGRES_DB, value: listify }
            - { name: POSTGRES_USER, value: listify }
            - name: POSTGRES_PASSWORD
              valueFrom: { secretKeyRef: { name: listify-db, key: DB_PASSWORD } }
            - { name: PGDATA, value: /var/lib/postgresql/data/pgdata }
          ports: [{ containerPort: 5432 }]
          volumeMounts:
            - { name: data, mountPath: /var/lib/postgresql/data }
            - { name: init, mountPath: /docker-entrypoint-initdb.d }
      volumes:
        - name: init
          configMap: { name: db-init }
  volumeClaimTemplates:            # chaque réplique reçoit SON PVC persistant
    - metadata: { name: data }
      spec:
        accessModes: ["ReadWriteOnce"]
        resources: { requests: { storage: 1Gi } }
```

Points à comprendre et noter :

- Le **`volumeClaimTemplates`** crée automatiquement un **PVC** (donc un PV via la StorageClass de kind, ch. 21, §7) pour le Pod `db-0`. Ses données survivent à la destruction du Pod : c'est la persistance du bloc 1, orchestrée.
- Le Service **headless** (`clusterIP: None`) donne au Pod un nom DNS stable (`db-0.db`), spécificité des StatefulSets. Pour nous, le nom `db` suffit à joindre la base.
- On assume (ch. 21, §7.2) que mettre une *vraie* base critique ainsi demanderait un opérateur ; ici, c'est pour **apprendre le mécanisme**.

## Étape 4 : le backend en Deployment, avec probes (1 h)

Le backend est **sans état** : un **Deployment** (ch. 21, §2) convient, avec les **probes** du chapitre 22.

```yaml title="k8s/40-backend.yaml"
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
  namespace: listify
spec:
  replicas: 2
  selector:
    matchLabels: { app: listify, tier: backend }
  template:
    metadata:
      labels: { app: listify, tier: backend }
    spec:
      containers:
        - name: backend
          image: localhost/listify-backend:1.0
          imagePullPolicy: IfNotPresent
          env:
            - { name: DB_HOST, value: db }        # le nom du Service de la base
            - name: DB_PASSWORD
              valueFrom: { secretKeyRef: { name: listify-db, key: DB_PASSWORD } }
          ports: [{ containerPort: 8000 }]
          readinessProbe:                          # prêt = base joignable
            httpGet: { path: /api/health, port: 8000 }
            periodSeconds: 5
          livenessProbe:                           # vivant = le process répond
            httpGet: { path: /api/health, port: 8000 }
            initialDelaySeconds: 10
            periodSeconds: 10
          resources:
            requests: { cpu: "50m", memory: "96Mi" }
            limits:   { cpu: "500m", memory: "256Mi" }
---
apiVersion: v1
kind: Service
metadata:
  name: backend
  namespace: listify
spec:
  selector: { app: listify, tier: backend }
  ports: [{ port: 8000, targetPort: 8000 }]
```

`DB_HOST: db` : le backend joint la base par le **nom du Service** (ch. 21, §3), exactement comme `DB_HOST=db` du bloc 1, mais résolu par le DNS du cluster. La **readiness** teste `/api/health` (qui vérifie la base) : tant que la base est absente, le Pod est **retiré du Service** sans être tué (ch. 22, §2). La **liveness** ne redémarre que si le process est vraiment bloqué.

## Étape 5 : le frontend, et l'application entière (45 min)

```yaml title="k8s/50-frontend.yaml"
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
  namespace: listify
spec:
  replicas: 1
  selector:
    matchLabels: { app: listify, tier: frontend }
  template:
    metadata:
      labels: { app: listify, tier: frontend }
    spec:
      containers:
        - name: frontend
          image: localhost/listify-frontend:1.0
          imagePullPolicy: IfNotPresent
          ports: [{ containerPort: 80 }]
---
apiVersion: v1
kind: Service
metadata:
  name: frontend
  namespace: listify
spec:
  selector: { app: listify, tier: frontend }
  ports: [{ port: 80, targetPort: 80 }]
```

Le frontend (Nginx) proxifie `/api/` vers le Service `backend` (sa configuration du TP 12 pointe déjà vers `backend:8000`). Appliquez **tout** et attendez :

```bash
kubectl apply -f k8s/
kubectl get pods -n listify --watch          # attendre backend et db en Running/Ready
```

Testez la chaîne complète, d'abord **dans** le cluster, puis via un tunnel depuis votre poste :

```bash
# Depuis un Pod éphémère :
kubectl run t --rm -it --restart=Never -n listify --image=curlimages/curl -- \
  sh -c 'curl -s http://frontend/api/health'      # {"api":"ok","database":"ok"}

# Depuis votre poste :
kubectl port-forward -n listify service/frontend 8088:80
# autre terminal : navigateur sur http://localhost:8088 → Listify fonctionne
```

??? question "Point de contrôle n° 1 : l'auto-réparation de bout en bout"
    Tuez le Pod backend : `kubectl delete pod -n listify -l tier=backend --field-selector ...` (ou un nom). Observez qu'un nouveau démarre, passe la readiness (base joignable), et réintègre le Service `backend` : l'application n'a pas eu d'interruption visible (l'autre réplique servait). Puis tuez `db-0` : il redémarre, **retrouve ses données** (le PVC a persisté), et le backend, un instant en 503 (readiness), revient tout seul. Consignez : c'est la résilience du chapitre 20, sur une vraie application.

## Étape 6 : l'exposition par Ingress (30 min)

En production, on n'utilise pas `port-forward` mais un **Ingress** (ch. 21, §4), le reverse proxy déclaratif. Sur kind, il faut d'abord installer un contrôleur d'Ingress (une fois) ; le détail dépend de la configuration du cluster.

```yaml title="k8s/60-ingress.yaml"
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: listify
  namespace: listify
spec:
  rules:
    - host: listify.local
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service: { name: frontend, port: { number: 80 } }
```

!!! note "Ingress sur kind : une étape d'infrastructure"
    Pour que l'Ingress fonctionne sur kind, le cluster doit être créé avec des ports mappés vers l'hôte, puis un contrôleur installé (`kubectl apply -f` du manifeste ingress-nginx pour kind). C'est documenté dans le guide de TP (kind + ingress-nginx). Si vous préférez rester simple, `port-forward` suffit pour ce semestre ; l'Ingress est surtout à **comprendre** comme l'équivalent Kubernetes du reverse proxy S1. Retenez le concept, l'installation est un détail d'environnement.

## Étape 7 : rolling update et rollback (30 min)

Le déploiement sans coupure du chapitre 22, en vrai. Simulez une nouvelle version (ici, un simple changement de variable d'environnement suffit à déclencher un nouveau ReplicaSet ; en réalité ce serait une nouvelle image) :

```bash
# Déclencher une mise à jour progressive
kubectl set env deployment/backend -n listify APP_VERSION=v2
kubectl rollout status deployment/backend -n listify          # suit la progression

# Observer : un NOUVEAU ReplicaSet monte, l'ANCIEN descend
kubectl get rs -n listify -l tier=backend

# Retour arrière instantané (l'ancien ReplicaSet est conservé à zéro)
kubectl rollout undo deployment/backend -n listify
kubectl rollout history deployment/backend -n listify
```

Observez `kubectl get pods --watch` pendant le rolling update : les Pods sont remplacés **un par un**, le nouveau devant passer la readiness avant que l'ancien ne parte. Zéro coupure, exactement la promesse du chapitre 22. Le `rollout undo` ramène la version précédente en secondes.

## Étape 8 : fin de séance (5 min)

**Gardez le cluster et le namespace `listify`** : les TP 17 (diagnostic de pannes) et 18 (Helm) réutilisent ce déploiement. Ne nettoyez rien si vous enchaînez.

Si vous arrêtez pour un moment (extinction du poste), rappelez-vous qu'un cluster kind survit mal à un redémarrage : le plus propre est de le supprimer et de le recréer à la prochaine séance.

```bash
# Uniquement si vous arrêtez et voulez libérer les ressources
# (dans le scope délégué, comme pour create/delete au TP 15) :
systemd-run --user --scope --property=Delegate=yes kind delete cluster --name listify
```

Comme votre `k8s/` est committé dans Git, tout se reconstruit d'une commande : recréer le cluster (TP 15), recharger les images (étape 1), `kubectl apply -f k8s/`. L'infrastructure est du code : perdre le cluster n'est plus une catastrophe, c'est un `apply` de distance.

## Point de contrôle final

- [ ] Images chargées dans kind ; `k8s/` appliqué sans erreur
- [ ] Listify fonctionnel : `/api/health` ok/ok, création de tâches au navigateur (port-forward)
- [ ] db en StatefulSet avec PVC : données survivant à la destruction de `db-0`
- [ ] backend avec readiness (retiré du trafic si base absente) et liveness
- [ ] Auto-réparation de bout en bout observée (backend et db)
- [ ] Rolling update (nouveau RS monte, ancien descend) et rollback prouvés
- [ ] Dossier `k8s/` committé (Secret **sans** vraie valeur)

## Pour aller plus loin (bonus)

1. **Deux répliques de frontend + anti-affinité** : passez le frontend à 2 répliques et ajoutez une règle d'anti-affinité pour qu'elles évitent le même nœud (sur un cluster multi-nœuds). Le placement du chapitre 19, piloté.
2. **HorizontalPodAutoscaler** : créez un HPA sur le backend (`kubectl autoscale deployment/backend --min=2 --max=6 --cpu-percent=70`). Générez de la charge (`kubectl run -it load ... ab/hey`) et regardez le nombre de répliques monter.
3. **ConfigMap pour le frontend** : externalisez la `nginx.conf` dans une ConfigMap montée, au lieu de la cuire dans l'image. Avantage et inconvénient ?

## Questions de compréhension (à préparer pour le TD et l'examen)

1. Pourquoi la base est-elle un **StatefulSet** et le backend un **Deployment** ? Qu'est-ce qui, dans chaque tier, justifie l'un ou l'autre ? (stateless/stateful, identité, stockage.)
2. La readiness du backend teste `/api/health` (qui vérifie la base). Décrivez ce qui se passe, étape par étape, quand la base tombe puis revient : quel Pod est retiré, de quoi, est-il redémarré ? Pourquoi ne PAS mettre ce test en liveness ?
3. Le backend joint la base par `DB_HOST: db`. Que se cache-t-il derrière ce nom (quel objet, quel mécanisme de résolution) ? Comparez au `DB_HOST=db` du bloc 1 (réseau Podman).
4. Pendant un rolling update, v1 et v2 coexistent brièvement. Quel problème cela pose-t-il si v2 attend une colonne de base absente en v1, et comment le résout-on ? (Reliez aux migrations compatibles du TP 4 du S1.)
