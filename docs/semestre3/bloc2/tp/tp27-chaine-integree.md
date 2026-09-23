---
title: "TP 27 : La chaîne intégrée"
sidebar_label: "TP 27 : La chaîne intégrée"
hide_title: true
---

import ChapterHead from '@site/src/components/ChapterHead';
import Figure from '@site/src/components/Figure';

<ChapterHead
  kicker="Semestre 3 · Bloc 2 · Travaux pratiques 27"
  title="La chaîne intégrée : livrer le code et le modèle en continu"
  competences={['C4', 'C5']}
/>

:::fiche
- **Durée** : 4 h
- **Prérequis** : TP 19 et 20 (forge Gitea, runner, registre, Argo CD) ; TP 24 à 26 ; chapitres 24, 25 et 29
- **Livrables** : un cluster qui tire le service depuis le registre de la forge ; un dépôt `listify-ml-config` surveillé par Argo CD ; un workflow qui teste, construit, pousse et déclare chaque version du service ; la démonstration chronométrée des deux trains de livraison ; runbook
- **Compétences travaillées** : C4 (chaînes d'intégration et de livraison continues), C5 (industrialiser le cycle de vie d'un produit d'IA)

Le bloc 2 a construit les pièces une à une : le suivi et le registre (TP 24), le service sur le cluster (TP 25), l'entraînement continu (TP 26). Il reste à les assembler avec la chaîne du semestre 2, pour qu'aucune mise en production ne passe plus par une commande tapée à la main. C'est le niveau 2 de maturité du chapitre 29 : le code du pipeline et du service est lui-même testé et livré par la CI/CD. Toutes les commandes et tous les résultats de ce TP ont été exécutés sur un poste Linux avec Gitea 1.27.3, act_runner 0.6.1, kind (Kubernetes 1.36), Argo CD 3.5.3, MLflow 3.16.1 et Airflow 3.3.2.
:::

## Ce que vous allez construire

<Figure src="tp27-deux-trains" num="TP27.1" alt="Deux trains de livraison mènent au même service en production. Train du code, à chaque commit : git push sur listify-ml, puis la CI Gitea (tests, image), puis le dépôt listify-ml-config (tag de l'image), puis Argo CD, qui synchronise. Train du modèle, chaque lundi : le DAG Airflow réentraîne, McNemar décide de la promotion, le registre déplace l'alias champion, puis un rollout restart fait recharger le modèle. Le service en production affiche l'image du commit 45e34bb et le modèle de la version 4. Changer le code ne change pas le modèle, et promouvoir un modèle ne reconstruit pas l'image : /sante affiche les deux versions.">
  Deux trains de livraison pour un même service. C'est la spécificité d'un système de ML (chapitre 29) : le code et le modèle ont chacun leur rythme, leurs tests et leur décision de mise en production.
</Figure>

Retenez l'idée directrice avant de commencer : **on ne livre pas le modèle dans l'image**. Si le modèle était copié dans l'image, chaque promotion obligerait à reconstruire et à redéployer le service, et chaque correction du code risquerait d'embarquer un modèle non validé. En séparant les deux, chaque train garde sa propre porte : les tests pour le code, le test de McNemar pour le modèle.

## Étape 0 : la forge, le runner et la pile MLflow (20 min)

```bash
podman start gitea act-runner mlflow-db mlflow-minio mlflow-serveur
curl -s http://localhost:3300/api/healthz | grep -o '"status": *"[a-z]*"'      # "status": "pass"
podman logs --tail 1 act-runner                                              # ... declare successfully
```

:::warning[Un runner qui ne redémarre pas]
Lors de la préparation, `podman start act-runner` a échoué avec `failed to fulfil mount request: open .../runner-config.yaml: no such file or directory` : le fichier de configuration monté au TP 19 avait été déplacé. Un conteneur mémorise les chemins de ses montages **à sa création**. On recrée alors le conteneur, sans réenregistrer le runner : son identité est dans le volume `runner-data`, qui n'a pas bougé.

```bash
podman rm act-runner
podman run -d --name act-runner \
  -e GITEA_INSTANCE_URL=http://host.containers.internal:3300 \
  -e GITEA_RUNNER_NAME=poste-etudiant -e CONFIG_FILE=/config.yaml \
  -v ~/forge/runner-config.yaml:/config.yaml:Z,ro \
  -v runner-data:/data \
  -v /run/user/$(id -u)/podman/podman.sock:/var/run/docker.sock \
  docker.io/gitea/act_runner:0.6.1
```
:::

## Étape 1 : un cluster qui tire depuis la forge (45 min)

Le cluster du TP 25 recevait son image par une archive. Celui-ci doit la tirer du registre de la forge, comme au TP 20, **et** publier le port du service, comme au TP 25. On le recrée avec les deux réglages :

```yaml title="~/forge/kind-config.yaml"
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: listify
containerdConfigPatches:
  - |-
    [plugins."io.containerd.grpc.v1.cri".registry]
      config_path = "/etc/containerd/certs.d"
nodes:
  - role: control-plane
    extraPortMappings:
      - containerPort: 30080
        hostPort: 30080
        protocol: TCP
```

```bash
export KIND_EXPERIMENTAL_PROVIDER=podman
kind delete cluster --name listify
kind create cluster --config ~/forge/kind-config.yaml
kubectl wait --for=condition=Ready node --all --timeout=180s
```

Le miroir du registre, dans le nœud (TP 20, étape 6) :

```bash
podman exec listify-control-plane sh -c 'mkdir -p "/etc/containerd/certs.d/localhost:3300" && cat > "/etc/containerd/certs.d/localhost:3300/hosts.toml" <<EOF
server = "http://localhost:3300"

[host."http://host.containers.internal:3300"]
  capabilities = ["pull", "resolve"]
EOF'
```

Le nom de l'hôte, pour les pods (TP 20, étape 7) :

```bash
IP=$(podman exec listify-control-plane getent hosts host.containers.internal | awk '{print $1}')
echo "$IP"                                  # 169.254.1.2 lors de la préparation
kubectl -n kube-system get configmap coredns -o yaml \
  | sed "s/^        ready$/        ready\n        hosts {\n          $IP host.containers.internal\n          fallthrough\n        }/" \
  | kubectl apply -f -
kubectl -n kube-system rollout restart deployment coredns
kubectl -n kube-system rollout status deployment coredns
```

Vérifiez que les pods atteignent les **trois** services de l'hôte dont la chaîne dépend :

```bash
kubectl run dnstest --rm -i --restart=Never --pod-running-timeout=5m \
  --image=docker.io/curlimages/curl:8.10.1 -- sh -c '
for u in http://host.containers.internal:3300/api/healthz \
         http://host.containers.internal:5001/health \
         http://host.containers.internal:9000/minio/health/live; do
  curl -s -o /dev/null -w "%{http_code} $u\n" $u
done'
```

```text
200 http://host.containers.internal:3300/api/healthz
200 http://host.containers.internal:5001/health
200 http://host.containers.internal:9000/minio/health/live
```

Enfin, Argo CD (TP 20, étape 8) :

```bash
kubectl create namespace argocd
kubectl apply -n argocd --server-side --force-conflicts \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/v3.5.3/manifests/install.yaml
kubectl -n argocd wait --for=condition=Ready pods --all --timeout=480s
```

## Étape 2 : le dépôt de configuration (30 min)

Comme au TP 20, ce qui tourne en production est décrit dans un dépôt **à part**, que seule la CI modifie pour y inscrire les versions. Créez sur la forge un dépôt vide `listify-ml-config`, puis localement :

```bash
mkdir -p ~/tp27/listify-ml-config/k8s && cd ~/tp27/listify-ml-config
cp ~/tp23/listify-ml/k8s/00-namespace.yaml ~/tp23/listify-ml/k8s/30-service.yaml k8s/
```

La configuration reprend celle du TP 25, **sans le Secret** :

```yaml title="k8s/10-configuration.yaml"
apiVersion: v1
kind: ConfigMap
metadata:
  name: modele-config
  namespace: listify-ml
data:
  MLFLOW_TRACKING_URI: "http://host.containers.internal:5001"
  MLFLOW_S3_ENDPOINT_URL: "http://host.containers.internal:9000"
  MODELE_URI: "models:/listify-categorie@champion"
```

Copiez `k8s/20-deployment.yaml` du TP 25 et changez une seule ligne, celle de l'image : elle désigne désormais le registre de la forge, avec un tag que la CI remplira.

```yaml
          image: localhost:3300/etudiant/listify-modele:a-definir
```

```bash
git init -b main && git add -A && git commit -m "Manifestes du service de prédiction"
git push http://localhost:3300/etudiant/listify-ml-config.git main
```

Le Secret des identifiants de MinIO est créé **à la main**, une fois, dans le cluster : c'est l'exception au modèle GitOps que le TP 20 a discutée (étape 9).

```bash
kubectl create namespace listify-ml
kubectl -n listify-ml create secret generic modele-stockage \
  --from-literal=AWS_ACCESS_KEY_ID=minio --from-literal=AWS_SECRET_ACCESS_KEY=minio12345
```

## Étape 3 : la CI du dépôt `listify-ml` (1 h)

### 3.1 Le workflow

Créez dans la forge un dépôt vide `listify-ml`, un jeton `CI_TOKEN` en secret du dépôt (TP 20, étape 2, avec les permissions dépôt et paquets), puis le workflow :

```yaml title=".gitea/workflows/ci.yaml"
name: CI listify-ml

on:
  push:
    branches: [main]

jobs:
  tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"

      - name: Installer les dépendances du projet
        run: pip install -r requirements.txt

      - name: Tests
        run: python -m pytest -q

  livraison:
    runs-on: ubuntu-latest
    needs: tests
    env:
      IMAGE: localhost:3300/etudiant/listify-modele
      TAG: ${{ gitea.sha }}            # tag unique et traçable : l'empreinte du commit
      DOCKER_BUILDKIT: "0"             # c'est Podman qui construit, et garde l'image (TP 20)
    steps:
      - uses: actions/checkout@v4

      - name: Fournir les identifiants du registre
        env:
          CI_TOKEN: ${{ secrets.CI_TOKEN }}
        run: |
          mkdir -p ~/.docker
          AUTH=$(printf 'etudiant:%s' "$CI_TOKEN" | base64 -w0)
          printf '{"auths":{"localhost:3300":{"auth":"%s"}}}' "$AUTH" > ~/.docker/config.json

      - name: Construire et pousser l'image du service
        run: |
          docker build --pull -f service/Containerfile -t "$IMAGE:$TAG" service
          docker push "$IMAGE:$TAG"

      - name: Déclarer la nouvelle version dans le dépôt de configuration
        run: |
          git clone "http://etudiant:${{ secrets.CI_TOKEN }}@host.containers.internal:3300/etudiant/listify-ml-config.git" config
          cd config
          sed -i "s#image: localhost:3300/etudiant/listify-modele:.*#image: $IMAGE:$TAG#" k8s/20-deployment.yaml
          git -c user.name="ci" -c user.email="ci@listify.local" commit -am "Déployer le service ${TAG:0:7}"
          git push
```

Ce workflow reprend la structure du TP 20, avec ses trois lignes durement acquises (identifiants écrits à la main, `-f` pour le Containerfile, `DOCKER_BUILDKIT: "0"`). Trois choix sont propres au ML :

- **La CI ne réentraîne pas.** Elle teste le code (dont le test du pipeline qui vérifie qu'on obtient deux prédictions pour deux titres) et livre le **service**. L'entraînement appartient au DAG du TP 26, avec ses données et son calendrier.
- **L'image ne contient pas le modèle.** Elle ne contient que le code capable de charger `@champion`. C'est ce qui rend les deux trains indépendants.
- **Le tag est le commit.** La même empreinte relie le commit, l'image, la ligne du dépôt de configuration et la réponse de `/sante`.

### 3.2 Premier passage

```bash
cd ~/tp23/listify-ml
git remote add forge http://localhost:3300/etudiant/listify-ml.git
git add .gitea && git commit -m "CI : tests, image du service, déclaration dans la configuration"
git push forge main
```

Suivez l'exécution dans l'onglet **Actions**. Lors de la préparation :

| Job | Durée, premier passage | Durée, passages suivants |
|---|---|---|
| `tests` | 5 min 15 s | 3 min 10 s |
| `livraison` | 4 min 08 s | 2 min 54 s |

L'essentiel du temps de `tests` est l'installation des dépendances (MLflow, DVC, scikit-learn) ; celui de `livraison`, la construction de l'image, plus rapide ensuite grâce au cache des couches. Vérifiez le résultat dans le dépôt de configuration :

```text
8627d7a Déployer le service 4f479f3
b599acd Manifestes du service de prédiction
```

## Étape 4 : confier le service à Argo CD (20 min)

```yaml title="argocd/listify-ml.yaml (dans listify-ml-config)"
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: listify-ml
  namespace: argocd
spec:
  project: default
  source:
    repoURL: http://host.containers.internal:3300/etudiant/listify-ml-config.git
    targetRevision: main
    path: k8s
  destination:
    server: https://kubernetes.default.svc
    namespace: listify-ml
  syncPolicy:
    automated:
      prune: true        # ce qui disparaît du dépôt disparaît du cluster
      selfHeal: true     # une modification manuelle est annulée
```

```bash
kubectl apply -f argocd/listify-ml.yaml
kubectl -n argocd get application listify-ml          # Synced / Healthy au bout d'une minute
kubectl -n listify-ml get pods
curl -s localhost:30080/sante
```

```text
modele-categorie-57d7d9b775-qk9qr   1/1   Running   0     39s
modele-categorie-57d7d9b775-zgdrh   1/1   Running   0     39s
{"etat":"ok","modele":"m-94a7dc9db50c4f13ac3815f0734dea3e","chargement_s":13.783}
```

Le service tourne à partir d'une image que personne n'a construite ni chargée à la main.

## Étape 5 : le train du modèle (30 min)

Une promotion de modèle ne passe **pas** par la CI. C'est le DAG du TP 26 qui, après le test de McNemar, déplace l'alias et lance `kubectl rollout restart`. Reproduisez ce geste à la main (ou lancez le DAG) :

```bash
cd ~/tp23/listify-ml && source .venv/bin/activate && source .env-mlflow
python -c "
from mlflow import MlflowClient
MlflowClient().set_registered_model_alias('listify-categorie', 'champion', '4')"
kubectl -n listify-ml rollout restart deploy/modele-categorie
kubectl -n listify-ml rollout status deploy/modele-categorie
curl -s localhost:30080/sante
kubectl -n argocd get application listify-ml -o jsonpath='{.status.sync.status}/{.status.health.status}'
```

```text
{"etat":"ok","modele":"m-d200a41b44814684b1d5df2727464e33","chargement_s":14.435}
Synced/Healthy
```

Le modèle a changé, l'image non. Une question se posait : Argo CD, avec `selfHeal`, allait-il annuler ce redémarrage, puisqu'il n'est pas dans Git ? La réponse observée est **non**. `rollout restart` ajoute une annotation (`kubectl.kubernetes.io/restartedAt`) que le dépôt ne déclare pas ; Argo CD compare ce que le dépôt **déclare**, et ne réclame pas la suppression de ce qu'il ne gère pas. L'application reste `Synced`. À vérifier dans votre runbook avec `kubectl get deploy -o jsonpath='{.spec.template.metadata.annotations}'`.

## Étape 6 : le train du code, chronométré (30 min)

Livrez une vraie modification du service : pour vérifier en production **quel code** tourne, le service va afficher le commit dont son image est issue. Dans `service/Containerfile`, après `COPY service.py .` :

```dockerfile
# la version du code, visible dans /sante
ARG VERSION=dev
ENV VERSION_SERVICE=$VERSION
```

Le commentaire est sur sa propre ligne à dessein : dans un Containerfile, un `#` en fin de ligne `ENV` ne serait **pas** un commentaire, mais une partie de la valeur. Dans `service/service.py`, la route de santé expose les deux versions :

```python
@app.get("/sante")
def sante():
    return {"etat": "ok", "service": os.environ.get("VERSION_SERVICE", "inconnue"),
            "modele": etat.get("version"), "chargement_s": etat.get("chargement_s")}
```

Et dans le workflow, la construction transmet le commit :

```yaml
          docker build --pull --build-arg VERSION="${TAG:0:7}" -f service/Containerfile -t "$IMAGE:$TAG" service
```

Commitez, notez l'heure, poussez, et interrogez le service jusqu'à voir apparaître le nouveau commit :

```bash
git add service .gitea && git commit -m "Service : la version du code apparaît dans /sante"
date +%T && git push forge main
# puis, toutes les 15 secondes :
curl -s localhost:30080/sante
```

```text
11:25:40
...
{"etat":"ok","service":"45e34bb","modele":"m-d200a41b44814684b1d5df2727464e33","chargement_s":13.834}
```

Première réponse portant le nouveau commit : **11 h 32 min 41 s**, soit **7 minutes** entre le `git push` et la production, sans aucune commande manuelle. Et le modèle servi est **resté le même** : `m-d200…`, celui de l'étape 5. Les deux trains sont indépendants : `/sante` affiche désormais la version du code **et** celle du modèle.

Décomposez ces 7 minutes au runbook : tests (3 min 10 s), livraison (2 min 54 s), détection du commit par Argo CD, démarrage des pods et chargement du modèle (environ 14 s). Lequel de ces postes réduiriez-vous en premier, et comment ?

<details className="controle">
<summary>Point de contrôle 6</summary>

- Le dépôt de configuration contient un commit « Déployer le service … » par exécution réussie de la CI.
- `/sante` affiche le commit du dernier `git push` et l'identifiant du modèle champion.
- Une promotion de modèle (étape 5) n'a produit **aucun** commit dans le dépôt de configuration ; une modification du code (étape 6) n'a produit **aucune** nouvelle version au registre.

</details>

## Étape 7 : la porte des tests (20 min)

Une chaîne de livraison n'a de valeur que si elle **refuse** ce qui ne doit pas partir. Cassez volontairement le pipeline de ML : dans `src/train.py`, remplacez le `ColumnTransformer` par un appel direct au vectoriseur, comme au TP 23 :

```python
        ("tfidf", TfidfVectorizer(min_df=p["min_df"], ngram_range=(1, p["ngram_max"]))),
```

Lancez d'abord les tests en local, puis poussez :

```text
FAILED tests/test_prepare.py::test_pipeline_accepte_un_tableau_de_titres
E           ValueError: Found input variables with inconsistent numbers of samples: [1, 12]
```

Le vectoriseur, qui parcourt le tableau reçu, n'y voit qu'**une** entrée, le nom de la colonne, face à 12 étiquettes (chapitre 31, §5.3). Dans la forge, l'exécution s'est terminée ainsi lors de la préparation :

```text
tests      completed  failure
livraison  completed  skipped
config :   d6e3c44 Déployer le service 45e34bb        (inchangé)
/sante :   {"etat":"ok","service":"45e34bb", ...}    (la production n'a pas bougé)
```

Aucune image poussée, aucun commit dans le dépôt de configuration, et la production continue de servir la version précédente. Annulez la panne comme au TP 19, par une annulation tracée :

```bash
git revert --no-edit HEAD
git push forge main
```

## Étape 8 : fin de séance (10 min)

```bash
podman stop act-runner gitea mlflow-serveur mlflow-minio mlflow-db
# le cluster peut rester : il sera réutilisé au bloc 3
```

Complétez le runbook : le schéma des deux trains avec, pour chacun, ce qui le déclenche, ce qui le teste, ce qui décide de la mise en production et comment on revient en arrière.

## Point de contrôle final

- [ ] Le cluster tire l'image du service depuis `localhost:3300`, et ses pods joignent la forge, MLflow et MinIO
- [ ] Argo CD synchronise `listify-ml-config` (`Synced / Healthy`)
- [ ] Un `git push` sur `listify-ml` aboutit en production sans commande manuelle, en quelques minutes
- [ ] Une promotion de modèle aboutit en production sans reconstruire l'image, et Argo CD reste `Synced`
- [ ] `/sante` affiche la version du code et celle du modèle
- [ ] Un test en échec bloque la livraison
- [ ] Runbook à jour

<details className="enseignant">
<summary>Banque de pannes du TP 27 (réservé enseignant : ne lisez pas si vous jouez le jeu)</summary>

Colonne « Origine » : **vécue** signifie rencontrée lors de la validation du TP ; **prévisible** signifie déduite de l'architecture ou des TP 19 à 26.

| Symptôme | Cause | Remède | Origine |
|---|---|---|---|
| `podman start act-runner` : `failed to fulfil mount request: open .../runner-config.yaml: no such file or directory` | Le fichier de configuration monté à la création du conteneur a été déplacé ou supprimé | Recréer le conteneur (encadré de l'étape 0) ; l'identité reste dans `runner-data` | vécue |
| Pods en `ErrImagePull` sur `localhost:3300/...` | Cluster recréé sans le fichier `hosts.toml` du miroir (il vit dans le nœud) | Refaire la commande de l'étape 1 | prévisible (TP 20) |
| Pods en `ErrImagePull` sur le tag `a-definir` | Application Argo CD créée avant le premier passage de la CI | Attendre le commit de la CI, ou créer l'application après | prévisible (TP 20) |
| Pods en `CrashLoopBackOff`, `Invalid Host header - possible DNS rebinding attack detected` | Serveur MLflow sans `--allowed-hosts` | TP 25, point de contrôle 3 | prévisible (TP 25) |
| Pods en `CreateContainerConfigError` | Secret `modele-stockage` absent : il n'est pas dans le dépôt | Étape 2 | prévisible |
| `/sante` affiche `"service": "inconnue"` | Image construite sans `--build-arg VERSION`, ou `ENV` absent | Étape 6 | prévisible |
| La valeur de `VERSION_SERVICE` contient `# la version…` | Commentaire placé en fin de ligne `ENV` | Commentaire sur sa propre ligne (étape 6) | prévisible (évitée de justesse) |
| `livraison` : `failed to find image` ou `open Dockerfile` | `DOCKER_BUILDKIT` absent ou `-f` oublié | TP 20, §4.1 | prévisible |
| `git commit` refusé par un crochet de sécurité du poste quand la commande contient d'autres options courtes (`-q`, `-n`) | Crochet qui interdit `--no-verify` et ses abréviations | Séparer les commandes, utiliser des options longues | vécue (poste de préparation) |

Panne à injecter en temps limité : supprimer `selfHeal` de l'application, faire un `kubectl scale --replicas=5` à la main, puis demander d'expliquer pourquoi Argo CD affiche `OutOfSync` sans rien corriger, et ce que `selfHeal` change.

</details>

## Pour aller plus loin (bonus)

1. **Le scan des vulnérabilités.** Ajoutez au job `livraison` l'étape Trivy du TP 20, avant la déclaration dans le dépôt de configuration. L'image du service (python, scikit-learn, MLflow) passe-t-elle le filtre des vulnérabilités critiques corrigibles ?
2. **Ne livrer que ce qui change.** Le job `livraison` reconstruit l'image même quand seul `params.yaml` a changé. Utilisez un filtre de chemins (`on.push.paths`) pour ne livrer le service que si `service/` change, et mesurez le gain.
3. **Un canari du modèle.** Déclarez dans `listify-ml-config` un second déploiement qui sert `@challenger`, avec une seule réplique, et routez-lui une partie du trafic. Quelle métrique surveilleriez-vous avant de promouvoir (chapitre 35) ?
4. **Tout dans Git.** Le train du modèle échappe au dépôt de configuration : la promotion déplace un alias, pas un commit. Proposez une variante où la promotion inscrit la **version** du modèle dans `listify-ml-config` (`MODELE_URI: models:/listify-categorie/7`). Que gagne-t-on en traçabilité, et que perd-on ?

## Questions de compréhension (à préparer pour le TD et l'examen)

1. Pourquoi l'image du service ne contient-elle pas le modèle ? Décrivez ce qui se passerait, dans les deux trains, si elle le contenait.
2. Un `git push` a mis 7 minutes à atteindre la production. Décomposez ce délai, et proposez deux façons de le réduire, avec leur contrepartie.
3. Argo CD, avec `selfHeal`, n'a pas annulé le `rollout restart`. Expliquez pourquoi, et donnez un exemple de modification manuelle qu'il **aurait** annulée.
4. Qu'est-ce qui garantit, dans cette chaîne, qu'un modèle moins bon ne partira pas en production ? Et qu'un code défectueux ne partira pas ?
5. Le Secret de MinIO n'est pas dans le dépôt de configuration. Quelles solutions permettraient de l'y mettre sans l'exposer (chapitre 9) ?
6. Situez la chaîne finale sur l'échelle de maturité du chapitre 29. Que manque-t-il encore, et à quel chapitre du bloc 3 cela correspond-il ?
