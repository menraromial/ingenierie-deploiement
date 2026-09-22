---
title: "TP 20 : Livraison continue et GitOps"
sidebar_label: "TP 20 : Livraison continue et GitOps"
hide_title: true
---

import ChapterHead from '@site/src/components/ChapterHead';
import Figure from '@site/src/components/Figure';

<ChapterHead
  kicker="Semestre 2 · Bloc 3 · Travaux pratiques 20"
  title="Du commit à la production : livraison continue et GitOps"
  competences={['C2', 'C3', 'C5']}
/>

:::fiche
- **Durée** : 8 h, en deux séances (partie A : la livraison ; partie B : le GitOps)
- **Prérequis** : TP 19 (forge et runner en service) ; TP 15 (kind rootless) ; chapitres 24 et 25
- **Livrables** : un pipeline qui construit, pousse, scanne et livre ; le dépôt `listify-config` ; un cluster kind où Argo CD déploie Listify depuis Git ; la preuve d'une auto-réparation et d'un retour arrière par `git revert` ; runbook
- **Compétences travaillées** : C2 (automatiser), C3 (conteneuriser et orchestrer), C5 (exploiter)

À la fin de ce TP, un `git push` sur `main` suffit à mettre une nouvelle version de Listify en production locale, sans aucune commande tapée contre le cluster. Toutes les commandes et tous les fichiers ont été exécutés et validés sur un poste Linux avec Podman 5.7 rootless, Gitea 1.27.3, act_runner 0.6.1, kind 0.32 (Kubernetes 1.36), Argo CD 3.5.3 et Trivy 0.72. Les incidents rencontrés pendant cette validation sont intégrés au déroulé : ils sont instructifs.
:::

## Ce que vous allez construire

<Figure src="tp20-architecture" num="TP20.1" alt="Un push sur le dépôt listify déclenche le job de livraison, qui construit les images avec le Podman de l'hôte, les pousse dans le registre intégré à Gitea, les scanne, puis commit le nouveau tag dans le dépôt listify-config. Dans le cluster kind, Argo CD lit ce dépôt grâce à une entrée CoreDNS et réconcilie le namespace listify, dont containerd tire les images depuis le registre de Gitea.">
  Ce que vous allez construire. Gitea joue trois rôles (dépôt de code, registre d'images, dépôt de configuration) ; la CI n'a aucun droit sur le cluster, elle écrit seulement dans Git et dans le registre.
</Figure>

Vous allez retrouver, à chaque étape, la question des points de vue réseau du TP 19, avec un acteur de plus : le cluster. Gardez ce tableau sous les yeux, il résume comment chacun joint Gitea.

| Qui | Adresse de Gitea | Pourquoi |
|---|---|---|
| Vous (navigateur, `git`, `podman push`) | `localhost:3300` | Le port est publié sur votre poste |
| Les conteneurs (runner, jobs, Trivy) | `host.containers.internal:3300` | Nom ajouté par Podman dans chaque conteneur |
| Le nœud kind (containerd, qui tire les images) | `host.containers.internal:3300` | Le nœud est un conteneur Podman |
| Les pods du cluster (Argo CD) | `host.containers.internal:3300` | À condition de l'apprendre au DNS du cluster (étape 7) |

## Partie A : la livraison continue

Première séance : du `git push` au commit de configuration. Le cluster n'intervient pas encore.

## Étape 0 : la forge est-elle prête ? (10 min)

```bash
podman start gitea act-runner 2>/dev/null     # si vous les aviez arrêtés au TP 19
curl -s http://localhost:3300/api/healthz | grep -o '"status": *"[a-z]*"' | head -1   # "status": "pass"
podman logs --tail 1 act-runner               # ... declare successfully
free -g                                       # comptez 6 Go disponibles pour la partie B
```

## Étape 1 : le registre intégré à Gitea (30 min)

Gitea n'est pas qu'une forge : il contient un **registre de conteneurs** conforme à la *distribution spec* de l'OCI (ch. 16), comme GitHub avec GHCR. Une image `localhost:3300/etudiant/listify-backend` y est rangée sous votre compte. On s'en sert à la place du registre `registry:2` du TP 14 : un service de moins, et les images apparaissent à côté du code, dans l'onglet **Paquets**.

Le registre est servi en HTTP, sans TLS. Il faut le déclarer à Podman comme registre non sécurisé, dans votre configuration utilisateur. **Attention** : si le fichier `~/.config/containers/registries.conf` n'existe pas encore, il **remplace** entièrement le fichier système ; on part donc d'une copie de celui-ci :

```bash
mkdir -p ~/.config/containers
[ -f ~/.config/containers/registries.conf ] || cp /etc/containers/registries.conf ~/.config/containers/
cat >> ~/.config/containers/registries.conf <<'EOF'

# Registre intégré à la forge Gitea locale (bloc 3 du S2) : HTTP, donc « insecure »
[[registry]]
location = "localhost:3300"
insecure = true
EOF
```

Vérifiez à la main que le registre accepte une image, avant de confier ce travail à la CI :

```bash
podman login localhost:3300 --username etudiant          # votre mot de passe Gitea
cd ~/Github/edu/listify
podman build -t localhost:3300/etudiant/listify-backend:manuel backend
podman push localhost:3300/etudiant/listify-backend:manuel
```

L'image apparaît dans votre profil Gitea, onglet **Paquets**. Elle est publique, comme votre compte : on peut la tirer **sans identifiants**, ce qui évitera d'en fournir au cluster.

## Étape 2 : un jeton pour la CI (20 min)

La CI va pousser des images et écrire dans un dépôt : elle a besoin d'un jeton d'accès, qu'on ne met surtout pas dans le workflow (ch. 23, §6.2).

1. Dans Gitea, menu de votre avatar, **Paramètres**, **Applications**, section **Gérer les jetons d'accès** : nom `ci-listify`, permissions **repository : lecture et écriture** et **package : lecture et écriture**. Copiez le jeton affiché : il ne sera plus jamais montré.
2. Dans le dépôt `listify`, **Paramètres**, **Actions**, **Secrets**, **Ajouter un secret** : nom `CI_TOKEN`, valeur le jeton.

Le workflow lira `${{ secrets.CI_TOKEN }}` ; Gitea masque sa valeur dans les journaux (`***`).

:::tip[La même chose en ligne de commande]
L'API de Gitea permet d'automatiser ces deux gestes, utile pour votre runbook :

```bash
TOKEN=$(curl -s -u etudiant:VOTRE_MOT_DE_PASSE -H 'Content-Type: application/json' \
  -d '{"name":"ci-listify","scopes":["write:repository","write:package"]}' \
  http://localhost:3300/api/v1/users/etudiant/tokens | jq -r .sha1)
curl -s -u etudiant:VOTRE_MOT_DE_PASSE -H 'Content-Type: application/json' -X PUT \
  -d "{\"data\":\"$TOKEN\"}" http://localhost:3300/api/v1/repos/etudiant/listify/actions/secrets/CI_TOKEN
```
:::

## Étape 3 : le dépôt de configuration (1 h)

Le chapitre 25 (§5) sépare le code de sa configuration de production. Créez dans Gitea un second dépôt, **vide**, nommé `listify-config`, puis sa copie locale, à côté de `listify` :

```bash
mkdir -p ~/Github/edu/listify-config/chart/templates ~/Github/edu/listify-config/chart/files
cd ~/Github/edu/listify-config
git init -b main
cp ../listify/db/schema.sql chart/files/00-schema.sql
cp ../listify/db/migrations/001-add-done.sql chart/files/01-add-done.sql
```

On y met un chart Helm complet de Listify, dérivé des manifests du TP 16. Il diffère de votre chart du TP 18 sur trois points, qu'il faut comprendre :

- les images viennent du **registre de Gitea**, et leur tag est une valeur que le pipeline réécrira ;
- les objets gardent des **noms fixes** (`backend`, `db`, `frontend`) : la configuration Nginx du frontend proxifie vers `backend:8000`, et un seul déploiement vit dans l'espace de noms `listify` ;
- le **mot de passe** de la base n'est pas dans le chart : il reste dans un Secret créé à la main (étape 9), puisqu'on ne met jamais de secret en clair dans Git (ch. 25, §6).

```yaml title="chart/Chart.yaml"
apiVersion: v2
name: listify
description: Listify, l'application fil rouge (frontend, backend, PostgreSQL)
type: application
version: 1.0.0
```

```yaml title="chart/values.yaml"
# Valeurs par défaut du chart Listify. Chaque environnement les surcharge
# dans son propre fichier (values-prod.yaml pour la production).
registry: localhost:3300/etudiant   # le registre de conteneurs intégré à Gitea

backend:
  replicas: 2
  tag: "latest"          # toujours surchargé : le pipeline écrit un tag unique

frontend:
  replicas: 1
  tag: "latest"

db:
  storage: 1Gi
  # Le mot de passe n'est PAS dans Git : il vit dans le Secret « listify-db »,
  # créé une fois à la main (voir ch. 25, §6).
  secretName: listify-db
```

```yaml title="chart/templates/db.yaml"
apiVersion: v1
kind: ConfigMap
metadata:
  name: db-init
data:
{{ (.Files.Glob "files/*.sql").AsConfig | indent 2 }}
---
apiVersion: v1
kind: Service
metadata:
  name: db
spec:
  clusterIP: None
  selector: { app: listify, tier: db }
  ports: [{ port: 5432 }]
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: db
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
              valueFrom: { secretKeyRef: { name: {{ .Values.db.secretName }}, key: DB_PASSWORD } }
            - { name: PGDATA, value: /var/lib/postgresql/data/pgdata }
          ports: [{ containerPort: 5432 }]
          readinessProbe:
            exec: { command: ["pg_isready", "-U", "listify"] }
            periodSeconds: 5
          volumeMounts:
            - { name: data, mountPath: /var/lib/postgresql/data }
            - { name: init, mountPath: /docker-entrypoint-initdb.d }
      volumes:
        - name: init
          configMap: { name: db-init }
  volumeClaimTemplates:
    - metadata: { name: data }
      spec:
        accessModes: ["ReadWriteOnce"]
        resources: { requests: { storage: {{ .Values.db.storage }} } }
```

La première ligne de `data` mérite un regard : `.Files.Glob "files/*.sql"` lit les fichiers SQL rangés dans le chart, et `.AsConfig` les transforme en entrées de ConfigMap. Le schéma et la migration voyagent donc **avec** le chart, versionnés dans Git.

```yaml title="chart/templates/backend.yaml"
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
spec:
  replicas: {{ .Values.backend.replicas }}
  selector:
    matchLabels: { app: listify, tier: backend }
  template:
    metadata:
      labels: { app: listify, tier: backend }
    spec:
      containers:
        - name: backend
          image: "{{ .Values.registry }}/listify-backend:{{ .Values.backend.tag }}"
          env:
            - { name: DB_HOST, value: db }
            - name: DB_PASSWORD
              valueFrom: { secretKeyRef: { name: {{ .Values.db.secretName }}, key: DB_PASSWORD } }
          ports: [{ name: http, containerPort: 8000 }]
          readinessProbe:
            httpGet: { path: /api/health, port: 8000 }
            periodSeconds: 5
          livenessProbe:
            httpGet: { path: /api/health, port: 8000 }
            initialDelaySeconds: 10
            periodSeconds: 10
          resources:
            requests: { cpu: "50m", memory: "96Mi" }
            limits: { cpu: "500m", memory: "256Mi" }
---
apiVersion: v1
kind: Service
metadata:
  name: backend
  labels: { app: listify, tier: backend }
spec:
  selector: { app: listify, tier: backend }
  ports: [{ name: http, port: 8000, targetPort: 8000 }]
```

```yaml title="chart/templates/frontend.yaml"
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
spec:
  replicas: {{ .Values.frontend.replicas }}
  selector:
    matchLabels: { app: listify, tier: frontend }
  template:
    metadata:
      labels: { app: listify, tier: frontend }
    spec:
      containers:
        - name: frontend
          image: "{{ .Values.registry }}/listify-frontend:{{ .Values.frontend.tag }}"
          ports: [{ containerPort: 80 }]
          readinessProbe:
            httpGet: { path: /, port: 80 }
            periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: frontend
spec:
  selector: { app: listify, tier: frontend }
  ports: [{ port: 80, targetPort: 80 }]
```

Enfin, les valeurs de production, à la racine du dépôt. C'est **le** fichier que la CI modifiera :

```yaml title="values-prod.yaml"
# Production de Listify. Les deux tags sont mis à jour par le pipeline de CI
# (dernière étape du workflow du dépôt listify) : ne pas les modifier à la main.
backend:
  replicas: 3
  tag: "initial"
frontend:
  replicas: 1
  tag: "initial"
```

Vérifiez sans rien déployer, puis poussez :

```bash
helm lint chart -f values-prod.yaml          # 1 chart(s) linted, 0 chart(s) failed
helm template listify chart -f values-prod.yaml | grep -E 'image:|replicas:'
git add -A && git commit -m "Chart de Listify et valeurs de production"
git remote add origin http://localhost:3300/etudiant/listify-config.git
git push origin main
```

## Étape 4 : le job de livraison (1 h)

Ajoutez ce troisième job à la fin de `.gitea/workflows/ci.yaml`, dans le dépôt `listify`. Lisez-le entièrement avant de le commiter : chaque étape est expliquée ensuite.

```yaml title=".gitea/workflows/ci.yaml (suite)"
  livraison:
    runs-on: ubuntu-latest
    needs: tests
    if: gitea.event_name == 'push'   # pas pour les pull requests : on ne livre que main
    env:
      REGISTRY: localhost:3300/etudiant
      TAG: ${{ gitea.sha }}          # tag unique et traçable : l'empreinte du commit
      DOCKER_BUILDKIT: "0"           # constructeur classique : c'est Podman qui construit, et garde l'image
    steps:
      - uses: actions/checkout@v4

      - name: Fournir les identifiants du registre
        # Pas de « docker login » : il testerait localhost:3300 DEPUIS le conteneur du job,
        # où localhost n'est pas Gitea. On écrit directement le fichier d'identifiants ;
        # c'est le Podman de l'hôte qui poussera, et pour lui localhost:3300 est bien Gitea.
        env:
          CI_TOKEN: ${{ secrets.CI_TOKEN }}
        run: |
          mkdir -p ~/.docker
          AUTH=$(printf 'etudiant:%s' "$CI_TOKEN" | base64 -w0)
          printf '{"auths":{"localhost:3300":{"auth":"%s"}}}' "$AUTH" > ~/.docker/config.json

      - name: Construire les deux images, sur une image de base à jour (--pull)
        run: |
          docker build --pull -f backend/Containerfile -t "$REGISTRY/listify-backend:$TAG" backend
          docker build --pull -f frontend/Containerfile -t "$REGISTRY/listify-frontend:$TAG" frontend

      - name: Pousser les images
        run: |
          docker push "$REGISTRY/listify-backend:$TAG"
          docker push "$REGISTRY/listify-frontend:$TAG"

      - name: Scanner les images (vulnérabilités critiques corrigibles)
        run: |
          for img in listify-backend listify-frontend; do
            docker run --rm -v trivy-cache:/root/.cache/trivy docker.io/aquasec/trivy:0.72.0 \
              image --insecure --severity CRITICAL --ignore-unfixed --exit-code 1 \
              "host.containers.internal:3300/etudiant/$img:$TAG"
          done

      - name: Mettre à jour le tag dans le dépôt de configuration
        run: |
          git clone "http://etudiant:${{ secrets.CI_TOKEN }}@host.containers.internal:3300/etudiant/listify-config.git" config
          cd config
          sed -i "s/^  tag: .*/  tag: \"$TAG\"/" values-prod.yaml
          git -c user.name="ci" -c user.email="ci@listify.local" commit -am "Déployer listify ${TAG:0:7}"
          git push
```

### 4.1 Où s'exécutent vraiment ces commandes ?

C'est la question centrale du job, et la clé de toutes ses pannes. Le job tourne dans un conteneur, mais les commandes `docker` qu'il lance **ne construisent rien elles-mêmes** : elles envoient des requêtes au Podman de votre poste, par le socket monté au TP 19. C'est donc le Podman de l'hôte qui construit, stocke et pousse. On appelle ce montage *Docker-outside-of-Docker*. Trois lignes du job en découlent, et chacune a été ajoutée après un échec réel pendant la préparation du TP :

| Ligne | Échec observé sans elle | Explication |
|---|---|---|
| Fichier `~/.docker/config.json` écrit à la main | `docker login localhost:3300` : `dial tcp [::1]:3300: connect: connection refused` | Le client `docker` récent vérifie les identifiants **depuis le conteneur du job**, où `localhost` n'est pas Gitea. Le push, lui, est fait par Podman sur l'hôte, pour qui `localhost:3300` est bien Gitea. On fournit donc les identifiants sans vérification préalable. |
| `-f backend/Containerfile` | `open Dockerfile: no such file or directory` | Le client `docker` cherche un fichier nommé `Dockerfile` ; nos fichiers s'appellent `Containerfile` (TP 12). |
| `DOCKER_BUILDKIT: "0"` | `docker push` : `failed to find image` | Sans elle, le client `docker` construit avec **BuildKit**, dans un conteneur à part, et l'image n'arrive jamais dans le stockage de Podman. Le constructeur classique, lui, est implémenté par Podman. Si vous avez eu cet échec, supprimez le conteneur laissé derrière : `podman rm -f buildx_buildkit_default`. |

### 4.2 Pourquoi pousser avant de scanner ?

L'ordre du chapitre 23 est « build, scan, publication ». Ici, on pousse d'abord, parce que Trivy tourne dans son propre conteneur et lit l'image **dans le registre**. Est-ce une entorse ? Non, à condition de comprendre où se trouve la vraie porte : une image poussée mais non scannée existe dans le registre, **sans être déployée**. Ce qui déploie, c'est la dernière étape, le commit du tag dans `listify-config`, et elle n'est exécutée que si le scan réussit. Dans une chaîne GitOps, le commit de configuration **est** la décision de mise en production.

Deux détails du scan : `--ignore-unfixed` ne retient que les vulnérabilités pour lesquelles un correctif existe (celles qu'on peut réellement traiter), et le volume `trivy-cache` conserve la base de vulnérabilités d'une exécution à l'autre, au lieu de la retélécharger à chaque fois.

### 4.3 Premier passage

```bash
cd ~/Github/edu/listify
git add .gitea/workflows/ci.yaml
git commit -m "CI : construire, scanner, livrer"
git push forge main
```

Suivez l'exécution dans l'onglet **Actions**. Temps mesurés lors de la validation : environ 3 minutes pour `lint`, 3 pour `tests` et 4 à 5 pour `livraison`, soit une dizaine de minutes du push au commit de configuration.

## Étape 5 : le scan bloque la livraison (45 min)

Lors de la validation de ce TP, en septembre 2026, le premier passage a **échoué au scan**, et c'est une excellente nouvelle : la porte a fonctionné. Selon la date à laquelle vous faites le TP, vous observerez l'un de ces deux cas, ou les deux, ou aucun.

**Cas 1 : une image de base périmée dans votre cache.** Sans `--pull`, Podman réutilise la copie de `python:3.12-slim` téléchargée il y a des mois. Trivy y a trouvé trois vulnérabilités critiques **déjà corrigées** dans le paquet `perl-base` :

```text
Total: 3 (CRITICAL: 3)
│ perl-base │ CVE-2026-13221 │ CRITICAL │ fixed  │ 5.40.1-6 │ 5.40.1-6+deb13u1 │ perl: Incorrect regular expression processing...
```

C'est l'exemple du chapitre 24, §3.1, vécu à l'envers : le **même** tag `python:3.12-slim` désigne aujourd'hui une image corrigée, que votre cache ignorait. L'option `--pull`, présente dans le job ci-dessus, force Podman à vérifier qu'il a bien la dernière version du tag avant de construire. Avec elle, le backend est passé à zéro vulnérabilité critique.

**Cas 2 : une version en fin de vie.** Le frontend part de `nginx:1.27-alpine`. Or la branche 1.27 de Nginx n'est plus maintenue : son image n'a plus été reconstruite depuis dix-sept mois, et `--pull` ne peut rien y faire. Trivy y a trouvé deux vulnérabilités critiques corrigées dans les versions actuelles. Le remède est une modification du **code** : passer à la branche stable maintenue, dont les versions mineures sont paires.

```dockerfile title="frontend/Containerfile (première ligne)"
FROM nginx:1.30-alpine
```

```bash
git commit -am "Frontend : nginx 1.30 (1.27 n'est plus maintenue)"
git push forge main
```

Retenez la leçon au runbook : **une image de base se choisit aussi selon son cycle de vie**, et un scan automatique est ce qui transforme cette règle en garde-fou plutôt qu'en vœu pieux.

<details className="controle">
<summary>Point de contrôle n° 1 : le pipeline livre</summary>

- Les trois jobs sont verts.
- Dans le dépôt `listify-config`, un commit de l'auteur `ci`, intitulé « Déployer listify » suivi des sept premiers caractères de l'empreinte, a remplacé les deux tags de `values-prod.yaml`.
- Les images `listify-backend` et `listify-frontend`, taguées par cette empreinte, sont dans l'onglet **Paquets**.
- Au runbook : le tableau de la section 4.1 dans vos mots, et le résultat du scan.

</details>

## Partie B : le GitOps avec Argo CD

Seconde séance : un cluster qui se met à jour tout seul à partir du dépôt de configuration.

## Étape 6 : un cluster qui sait tirer depuis Gitea (45 min)

Les nœuds kind doivent tirer les images `localhost:3300/...`. Or, pour containerd dans le nœud, `localhost` est le nœud lui-même. On déclare donc un **miroir** : « pour le registre `localhost:3300`, va en réalité chercher les images sur `host.containers.internal:3300` ». containerd lit ces règles dans un dossier par registre, `/etc/containerd/certs.d/`, qu'on active à la création du cluster.

Supprimez l'ancien cluster s'il existe, puis créez le nouveau (dans le scope délégué, voir TP 15) :

```yaml title="~/forge/kind-config.yaml"
# Cluster kind du TP 20 : containerd lira la configuration des registres
# dans /etc/containerd/certs.d (un dossier par registre).
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: listify
containerdConfigPatches:
  - |-
    [plugins."io.containerd.grpc.v1.cri".registry]
      config_path = "/etc/containerd/certs.d"
```

```bash
export KIND_EXPERIMENTAL_PROVIDER=podman
systemd-run --user --scope --property=Delegate=yes kind delete cluster --name listify   # si besoin
systemd-run --user --scope --property=Delegate=yes kind create cluster --config ~/forge/kind-config.yaml
kubectl wait --for=condition=Ready node --all --timeout=180s   # le nœud est NotReady quelques secondes
kubectl get nodes          # listify-control-plane   Ready
```

Déclarez le miroir **dans** le nœud, puis vérifiez que containerd tire bien votre image manuelle de l'étape 1 :

```bash
podman exec listify-control-plane sh -c 'mkdir -p "/etc/containerd/certs.d/localhost:3300" && cat > "/etc/containerd/certs.d/localhost:3300/hosts.toml" <<EOF
server = "http://localhost:3300"

[host."http://host.containers.internal:3300"]
  capabilities = ["pull", "resolve"]
EOF
crictl pull localhost:3300/etudiant/listify-backend:manuel'
# Image is up to date for sha256:...
```

Aucun identifiant n'a été nécessaire : les paquets de votre compte public sont lisibles anonymement. Notez aussi que ce fichier vit dans le conteneur du nœud : **si vous recréez le cluster, il faut refaire cette commande**. Consignez-la au runbook.

## Étape 7 : apprendre au DNS du cluster le nom de l'hôte (20 min)

Le nœud connaît `host.containers.internal` (Podman l'a écrit dans son `/etc/hosts`), mais les **pods** passent par CoreDNS, le DNS du cluster, qui l'ignore. Argo CD, qui tourne dans des pods, ne pourrait donc pas lire votre dépôt. On ajoute une entrée à la configuration de CoreDNS, avec l'adresse que le nœud associe à ce nom :

```bash
IP=$(podman exec listify-control-plane getent hosts host.containers.internal | awk '{print $1}')
echo "$IP"                                  # 169.254.1.2 lors de la validation
kubectl -n kube-system get configmap coredns -o yaml \
  | sed "s/^        ready$/        ready\n        hosts {\n          $IP host.containers.internal\n          fallthrough\n        }/" \
  | kubectl apply -f -
kubectl -n kube-system rollout restart deployment coredns
kubectl -n kube-system rollout status deployment coredns
```

Le bloc `hosts` sert le nom demandé, et `fallthrough` passe toutes les autres requêtes aux étapes suivantes (les noms du cluster, puis l'extérieur). Vérifiez depuis un pod :

```bash
kubectl run dnstest --rm -i --restart=Never --pod-running-timeout=5m \
  --image=docker.io/curlimages/curl:8.10.1 -- \
  curl -s -o /dev/null -w "%{http_code}\n" http://host.containers.internal:3300/api/healthz
# 200
```

## Étape 8 : installer Argo CD (40 min)

```bash
kubectl create namespace argocd
kubectl apply -n argocd --server-side --force-conflicts \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/v3.5.3/manifests/install.yaml
kubectl -n argocd get pods --watch          # attendre 7 pods Running (quelques minutes)
```

`--server-side` confie la fusion des manifests au serveur d'API : les définitions de ressources d'Argo CD sont trop volumineuses pour le mode par défaut de `kubectl apply`. Ouvrez l'interface web :

```bash
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d; echo
kubectl -n argocd port-forward service/argocd-server 8443:443
# navigateur : https://localhost:8443 (certificat auto-signé à accepter), utilisateur admin
```

## Étape 9 : le Secret, seule exception au modèle (10 min)

```bash
kubectl create namespace listify
kubectl -n listify create secret generic listify-db --from-literal=DB_PASSWORD='un-mot-de-passe-fort'
```

C'est la **seule** commande qui touche l'état de l'application sans passer par Git, et c'est volontaire : un secret ne va pas dans le dépôt (ch. 25, §6). Notez-la au runbook comme une exception assumée ; le bonus 2 la supprime.

## Étape 10 : confier Listify à Argo CD (40 min)

Rangez la définition de l'Application dans le dépôt de configuration, puis appliquez-la **une fois** :

```yaml title="argocd/listify.yaml (dans listify-config)"
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: listify
  namespace: argocd
spec:
  project: default
  source:
    repoURL: http://host.containers.internal:3300/etudiant/listify-config.git
    targetRevision: main
    path: chart
    helm:
      valueFiles:
        - ../values-prod.yaml          # à la racine du dépôt, un niveau au-dessus du chart
  destination:
    server: https://kubernetes.default.svc
    namespace: listify
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

```bash
cd ~/Github/edu/listify-config
git pull                                   # récupérer le commit de la CI
git add argocd/listify.yaml && git commit -m "Application Argo CD de Listify" && git push
kubectl apply -f argocd/listify.yaml
kubectl -n argocd get application listify --watch     # Synced, puis Healthy
```

Dans l'interface d'Argo CD, l'application `listify` déroule l'arbre de ses ressources : le StatefulSet `db` et son volume, les Deployments, leurs ReplicaSets, les Pods. Vérifiez que les images sont bien celles du dernier commit de la CI :

```bash
kubectl -n listify get deploy backend -o jsonpath='{.spec.template.spec.containers[0].image}'; echo
# localhost:3300/etudiant/listify-backend:<empreinte du commit>
kubectl -n listify port-forward service/frontend 8088:80
# navigateur : http://localhost:8088, Listify fonctionne ; ajoutez une tâche
```

:::note[Des Pods en `ErrImagePull` ?]
Si vous appliquez l'Application **avant** qu'un pipeline ait réussi, les Pods tentent de tirer le tag `initial`, qui n'existe pas : `ErrImagePull`, puis `ImagePullBackOff`. C'est ce qui s'est produit lors de la validation, et c'est normal : dès que la CI commitera un vrai tag, Argo CD corrigera tout seul. Le symptôme illustre la distinction du chapitre 25 : l'application est `Synced` (le cluster reflète fidèlement Git) mais pas `Healthy` (ce que Git décrit ne fonctionne pas).
:::

<details className="controle">
<summary>Point de contrôle n° 2 : Listify déployé par Git</summary>

- `kubectl -n argocd get application listify` : `Synced` et `Healthy`.
- 3 Pods `backend`, 1 `frontend`, `db-0`, tous prêts, sur les images taguées par l'empreinte du dernier commit.
- Listify répond sur `http://localhost:8088` et enregistre des tâches.

</details>

## Étape 11 : la boucle complète (45 min)

Faites un changement visible dans Listify, par exemple le titre de la page dans `frontend/index.html`, puis :

```bash
cd ~/Github/edu/listify
git commit -am "Frontend : nouveau titre"
git push forge main
```

Et **ne tapez plus rien** contre le cluster. Suivez : le pipeline (onglet Actions), puis le commit de la CI dans `listify-config`, puis Argo CD qui détecte la nouvelle révision et lance un rolling update. Chronométrez le délai entre votre push et le nouveau titre dans le navigateur : c'est votre **délai de mise en production** au sens de DORA (ch. 24, §8).

Argo CD interroge Git périodiquement, par défaut de l'ordre de trois minutes, avec une part d'aléa : lors de la validation, la synchronisation est arrivée environ six minutes après le commit de la CI. Pour ne pas attendre, demandez une actualisation immédiate :

```bash
kubectl -n argocd annotate application listify argocd.argoproj.io/refresh=normal --overwrite
```

Avec cette annotation, il s'est écoulé **11 secondes** entre le commit de configuration et le changement d'image. Le bonus 1 remplace ce geste manuel par un webhook.

:::warning[Le `port-forward` s'interrompt pendant la mise à jour]
`kubectl port-forward service/frontend` s'attache à **un** Pod choisi au démarrage. Quand le rolling update remplace ce Pod, le tunnel meurt (`curl` renvoie une réponse vide). Relancez-le : ce n'est pas une panne de Listify, c'est une limite du tunnel, qui n'est pas un vrai répartiteur (un Ingress le serait).
:::

## Étape 12 : dérive et retour arrière (40 min)

**La dérive est annulée.** Simulez l'administrateur pressé du chapitre 25 :

```bash
kubectl -n listify scale deployment backend --replicas=1
kubectl -n listify get deploy backend --watch
```

Lors de la validation, le nombre de répliques était revenu à 3 **en moins de trois secondes** : Argo CD observe le cluster en continu et l'option `selfHeal` réapplique l'état de Git. Pour changer le nombre de répliques, il faut passer par un commit de `values-prod.yaml`.

**Le retour arrière est un `git revert`.** Dans `listify-config`, annulez le dernier commit de la CI :

```bash
cd ~/Github/edu/listify-config
git pull
git log --oneline | head -3                # repérez le dernier « Déployer listify ... »
git revert --no-edit HEAD
git push
kubectl -n argocd annotate application listify argocd.argoproj.io/refresh=normal --overwrite
kubectl -n listify get deploy backend -o jsonpath='{.spec.template.spec.containers[0].image}'; echo
```

L'image revient à celle du commit précédent : lors de la validation, en quinze secondes. Vérifiez enfin que la tâche créée à l'étape 10 est toujours là : le retour arrière a changé le **code** déployé, pas les **données**, qui vivent dans le volume de `db-0`.

## Étape 13 : fin de séance (10 min)

**Gardez tout** : le TP 21 ajoute la surveillance à ce déploiement. Entre deux séances, vous pouvez arrêter le runner et Gitea (`podman stop act-runner gitea`) ; le cluster kind, lui, survit mal à un redémarrage du poste. Si vous devez le recréer, refaites dans l'ordre : l'étape 6 (cluster et miroir), l'étape 7 (CoreDNS), l'étape 8 (Argo CD), l'étape 9 (Secret), puis `kubectl apply -f argocd/listify.yaml`. Argo CD reconstruit Listify tout seul, à l'identique de Git, mais avec une base **vide** (ch. 25, §7).

## Point de contrôle final

- [ ] Registre de Gitea déclaré à Podman ; une image manuelle poussée
- [ ] Secret `CI_TOKEN` en place ; le job `livraison` construit, pousse, scanne et commit le tag
- [ ] Un échec de scan analysé et corrigé (ou, à défaut, expliqué à partir de l'étape 5)
- [ ] Cluster avec miroir de registre et entrée CoreDNS ; Argo CD installé
- [ ] Application `listify` `Synced` et `Healthy`, déployée sans `kubectl apply` de manifests Listify
- [ ] Délai de mise en production mesuré ; dérive annulée ; retour arrière par `git revert`
- [ ] Runbook à jour, avec la liste complète des commandes de reconstruction

<details className="enseignant">
<summary>Banque de pannes du TP 20 (réservé enseignant : ne lisez pas si vous jouez le jeu)</summary>

**Vécue** : rencontrée lors de la validation. **Prévisible** : déduite de l'architecture, évitée par l'énoncé.

| Symptôme | Cause | Remède | Origine |
|---|---|---|---|
| `docker login` : `dial tcp [::1]:3300: connect: connection refused` | La vérification a lieu dans le conteneur du job | Fichier `~/.docker/config.json` (§4.1) | vécue |
| `docker build` : `permission denied while trying to connect to the docker API at unix:///var/run/docker.sock` | Montage automatique d'act_runner : sur l'hôte, ce chemin désignait le socket d'un démon Docker réservé à root | `docker_host: "-"` et montage explicite du socket Podman (TP 19, §4.2) | vécue |
| `docker build` : `no such file or directory` sur `/var/run/docker.sock` | Montage demandé par `options` mais absent de `valid_volumes` | Ajouter le chemin à `valid_volumes` | vécue |
| `open Dockerfile: no such file or directory` | Fichier nommé `Containerfile` | `-f backend/Containerfile` | vécue |
| `docker push` : `failed to find image` ; conteneur `buildx_buildkit_default` apparu | Construction par BuildKit, hors du stockage de Podman | `DOCKER_BUILDKIT: "0"` ; supprimer le conteneur buildx | vécue |
| Push sans exécution de workflow | YAML invalide (`: ` dans un nom d'étape) | Valider le YAML | vécue |
| Scan en échec : `CRITICAL` corrigés | Image de base périmée, ou branche en fin de vie | `--pull` ; `nginx:1.30-alpine` | vécue |
| Pods `ErrImagePull` sur le tag `initial` | Application appliquée avant le premier pipeline réussi | Attendre le commit de la CI | vécue |
| Argo CD met plusieurs minutes à voir le commit | Interrogation périodique de Git | Annotation `refresh=normal`, ou webhook | vécue |
| `curl` : réponse vide sur `localhost:8088` après une mise à jour | Le `port-forward` visait un Pod remplacé | Relancer le tunnel | vécue |
| `podman push` : `http: server gave HTTP response to HTTPS client` | Registre non déclaré `insecure` | `registries.conf` (étape 1) | prévisible |
| Pods `ErrImagePull` même avec un bon tag, `connection refused` vers `localhost:3300` | Fichier `hosts.toml` absent du nœud (cluster recréé) | Refaire l'étape 6 | prévisible |
| Application en erreur : `lookup host.containers.internal ... no such host` | Entrée CoreDNS absente | Étape 7 | prévisible |
| Pods `CreateContainerConfigError` | Secret `listify-db` absent | Étape 9 | prévisible |

Panne à injecter en temps limité : désactiver `selfHeal` dans l'Application, modifier une variable d'environnement du backend par `kubectl edit`, et demander de retrouver la dérive à partir de l'interface d'Argo CD (état `OutOfSync`, onglet *Diff*), puis de la faire disparaître **proprement**.

</details>

## Pour aller plus loin (bonus)

1. **Un webhook plutôt qu'une attente.** Dans les paramètres du dépôt `listify-config`, ajoutez un webhook de type Gitea vers `https://argocd-server.argocd.svc/api/webhook`. Quel problème de joignabilité faut-il résoudre (qui appelle qui, et d'où) ? Mesurez le nouveau délai de mise en production.
2. **Le Secret dans Git, chiffré.** Installez Sealed Secrets, chiffrez le mot de passe de la base avec `kubeseal` et versionnez le `SealedSecret` dans `listify-config`. L'étape 9 disparaît : la reconstruction depuis Git devient complète.
3. **App of apps.** Créez une Application racine qui pointe vers le dossier `argocd/` du dépôt de configuration : Argo CD gère alors l'Application `listify` elle-même. Que reste-t-il à appliquer à la main pour reconstruire tout le cluster ?
4. **Épingler le digest.** Faites écrire au pipeline le **digest** de l'image (sortie de `docker push`) plutôt que son tag (ch. 24, §4.2). Qu'y gagne-t-on, et que devient la lisibilité de `values-prod.yaml` ?

## Questions de compréhension (à préparer pour le TD et l'examen)

1. Dans ce TP, la CI n'a **aucun** identifiant du cluster. Qu'aurait-il fallu lui donner pour déployer en mode poussé (ch. 25, §3), et que risquerait-on si le runner était compromis ?
2. Le job pousse l'image **avant** de la scanner. Expliquez pourquoi cela ne contredit pas la règle « on ne déploie pas une image non scannée ». Où est la vraie porte ?
3. Pourquoi le **même** tag `python:3.12-slim` a-t-il produit une image vulnérable puis une image saine ? Reliez à la règle « construire une fois, promouvoir ensuite » du chapitre 24.
4. Argo CD a affiché `Synced` alors que les Pods étaient en `ErrImagePull`. Expliquez la différence entre état de synchronisation et état de santé, avec un autre exemple de chaque combinaison.
5. Le retour arrière par `git revert` a rétabli l'ancienne image en quinze secondes. Dans quelle situation ce retour arrière serait-il **dangereux** (indice : ch. 24, §7) ?
6. Recopiez le tableau des points de vue réseau du début du TP et, pour chaque ligne, citez la commande ou le fichier qui rend la communication possible.
