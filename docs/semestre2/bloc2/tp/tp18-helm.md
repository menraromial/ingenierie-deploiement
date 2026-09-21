---
title: "TP 18 : Packager en chart Helm"
sidebar_label: "TP 18 : Packager en chart Helm"
hide_title: true
---

import ChapterHead from '@site/src/components/ChapterHead';

<ChapterHead
  kicker="Semestre 2 · Bloc 2 · Travaux pratiques 18"
  title="Packager Listify en chart Helm"
  competences={['C3', 'C4']}
/>

:::fiche
- **Durée** : 4 h
- **Prérequis** : TP 16 (manifests Listify) ; chapitre 22, §5
- **Livrables** : le chart Helm `charts/listify/` committé ; deux installations (dev et prod) avec des valeurs différentes ; runbook
- **Compétences travaillées** : C3, C4

Vous transformez vos manifests figés en un **paquet paramétrable**. Un seul chart, déployable en dev (1 réplique, image de test) comme en prod (3 répliques, image versionnée), sans dupliquer un seul YAML. Commandes validées avec Helm 3.
:::

## Étape 1 : le problème, et la structure d'un chart (45 min)

Au TP 16, vos manifests étaient **figés** : le nombre de répliques, le tag d'image, le mot de passe y sont écrits en dur. Pour déployer une variante (un deuxième environnement, un autre client), il faudrait tout dupliquer et éditer : la duplication d'information du chapitre 9 du S1, au niveau des manifests. **Helm** (ch. 22, §5) résout cela : des **templates** remplis par des **valeurs**.

Créez le squelette du chart dans votre dépôt :

```bash
mkdir -p charts
cd charts
helm create listify        # génère un chart d'exemple
rm -rf listify/templates/* listify/charts   # on repart des NÔTRES
ls listify/                # Chart.yaml, values.yaml, templates/
```

Structure d'un chart (ch. 22, §5.2) :

| Élément | Rôle |
|---|---|
| `Chart.yaml` | Métadonnées du paquet (nom, version) |
| `values.yaml` | Les **valeurs par défaut** (les « trous » et leur contenu par défaut) |
| `templates/` | Les manifests **templatisés** (avec `{{ .Values.xxx }}`) |
| `templates/_helpers.tpl` | Des fonctions réutilisables (noms, labels) |

## Étape 2 : templatiser les manifests (1 h 30)

Le cœur du TP : reprendre chaque manifeste du TP 16 et remplacer ce qui **varie** par une référence à `.Values`. Les valeurs par défaut d'abord :

```yaml title="charts/listify/values.yaml"
backend:
  replicas: 2
  image: localhost/listify-backend
  tag: "1.0"

frontend:
  replicas: 1
  image: localhost/listify-frontend
  tag: "1.0"

db:
  password: changeme        # surchargé par environnement ; jamais la vraie valeur ici
  storage: 1Gi
```

Puis les templates. Exemple pour le backend (le reste sur le même modèle) :

```yaml title="charts/listify/templates/backend.yaml"
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ .Release.Name }}-backend
  labels:
    app: {{ .Release.Name }}
    tier: backend
spec:
  replicas: {{ .Values.backend.replicas }}
  selector:
    matchLabels: { app: {{ .Release.Name }}, tier: backend }
  template:
    metadata:
      labels: { app: {{ .Release.Name }}, tier: backend }
    spec:
      containers:
        - name: backend
          image: "{{ .Values.backend.image }}:{{ .Values.backend.tag }}"
          imagePullPolicy: IfNotPresent
          env:
            - { name: DB_HOST, value: {{ .Release.Name }}-db }
            - name: DB_PASSWORD
              valueFrom:
                secretKeyRef: { name: {{ .Release.Name }}-db, key: DB_PASSWORD }
          ports: [{ containerPort: 8000 }]
          readinessProbe:
            httpGet: { path: /api/health, port: 8000 }
            periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: {{ .Release.Name }}-backend
spec:
  selector: { app: {{ .Release.Name }}, tier: backend }
  ports: [{ port: 8000, targetPort: 8000 }]
```

Points à comprendre, exactement comme les templates Jinja2 + inventaire d'Ansible (S1, TP 8) :

- **`{{ .Values.backend.replicas }}`** : remplacé par la valeur (défaut 2, surchargeable).
- **`{{ .Release.Name }}`** : le nom donné à l'installation (`helm install <nom> ...`), qui préfixe tous les objets. Deux installations du même chart (`dev`, `prod`) ne se marchent donc pas dessus.
- La **configuration se calcule** ; l'information (nom, tag, répliques) n'existe qu'à un seul endroit, `values.yaml` ou la surcharge.

Templatisez de même le frontend, le Secret (`stringData.DB_PASSWORD: {{ .Values.db.password }}`) et la base (StatefulSet + Service + ConfigMap d'init). Vérifiez au fur et à mesure **sans rien déployer** :

```bash
helm lint listify                       # valide la structure du chart
helm template demo listify              # REND les manifests (dry-run local) : lisez-les
```

`helm template` affiche les YAML **rendus** (les trous remplis) sans toucher au cluster : c'est le `--check` d'Ansible, le `plan` de Terraform (S1), l'habitude « regarder avant d'agir » de tout le parcours. Vérifiez que `replicas: 2`, l'image, les noms sont corrects.

## Étape 3 : installer, en dev puis en prod (1 h)

Une **release** est une installation nommée d'un chart avec un jeu de valeurs (ch. 22, §5.2).

```bash
# Installation "dev" : valeurs par défaut
helm install dev ./listify --namespace dev --create-namespace
helm list -n dev
kubectl get all -n dev
```

Puis une installation **prod** dans un autre namespace, avec des **valeurs surchargées**, à partir du **même** chart :

```yaml title="charts/values-prod.yaml"
backend:
  replicas: 3
  tag: "1.0"
db:
  password: un-mot-de-passe-fort-de-prod
  storage: 5Gi
```

```bash
helm install prod ./listify -n prod --create-namespace -f values-prod.yaml
kubectl get deploy -n prod            # backend à 3 répliques, sans avoir touché aux templates
```

Le même chart a produit deux déploiements différents, isolés dans leurs namespaces. Comparez `kubectl get deploy -n dev` (2 répliques) et `-n prod` (3) : **un code, N environnements**, la promesse tenue au niveau Kubernetes. C'est aussi la base du CI/CD du bloc 3 (promouvoir la même image/le même chart de dev vers prod).

<details className="controle">
<summary>Point de contrôle n° 1 : la mise à jour et le rollback Helm</summary>

Modifiez une valeur (passez `backend.replicas` à 4) et **mettez à jour** la release, puis annulez :

```bash
helm upgrade dev ./listify -n dev --set backend.replicas=4
kubectl get deploy dev-backend -n dev          # 4 répliques
helm history dev -n dev                         # les révisions de la release
helm rollback dev 1 -n dev                      # retour à la révision 1
```

Helm **suit les révisions** de chaque release et permet le rollback, comme le `rollout undo` de Kubernetes mais au niveau du paquet entier. Vous retrouvez l'état désiré versionné du S1, appliqué au packaging.

</details>

## Étape 4 : nettoyage de fin de bloc, et bilan (30 min)

D'abord les releases Helm et leurs namespaces de ce TP :

```bash
helm uninstall dev -n dev; helm uninstall prod -n prod
kubectl delete namespace dev prod
```

**C'est le dernier TP du bloc Kubernetes** : vous pouvez maintenant **supprimer le cluster kind** pour libérer toutes les ressources (le nœud et tous les Pods).

```bash
export KIND_EXPERIMENTAL_PROVIDER=podman
# dans le scope délégué (create ET delete l'exigent en rootless, voir TP 15) :
systemd-run --user --scope --property=Delegate=yes kind delete cluster --name listify
kind get clusters                    # ne doit plus rien lister
```

Rien n'est perdu : votre `k8s/` et votre chart Helm sont dans Git. Recréer le cluster et redéployer Listify est, à tout moment, une affaire de trois commandes. L'infrastructure est du code, jusqu'au bout.

Rédigez au runbook la comparaison **manifests bruts (TP 16) vs chart Helm (TP 18)** : qu'est-ce que Helm apporte (paramétrage, releases suivies, rollback, réutilisation), qu'est-ce qu'il ajoute comme complexité (une couche de templating de plus, le risque de sur-templatiser) ? Comme tout outil du parcours, Helm résout un problème réel et en crée de plus petits : savoir quand un chart est justifié (plusieurs environnements, distribution) et quand des manifests bruts suffisent (une appli, un environnement) est une décision d'ingénieur.

## Point de contrôle final

- [ ] Chart `charts/listify/` : `helm lint` passe, `helm template` rend des manifests corrects
- [ ] Tous les tiers templatisés (backend, frontend, db, Secret, Service)
- [ ] Release `dev` (défaut) et `prod` (valeurs surchargées) installées, différentes et isolées
- [ ] `helm upgrade` + `helm rollback` prouvés (historique des révisions)
- [ ] Comparaison manifests vs Helm rédigée ; chart committé (`db.password` par défaut inoffensif)

## Pour aller plus loin (bonus)

1. **`_helpers.tpl`** : factorisez les labels communs (`app`, `tier`, les labels standard de Helm) dans un template nommé, réutilisé partout. Évitez la répétition dans les templates eux-mêmes.
2. **Dépendances de chart** : déclarez PostgreSQL comme une **dépendance** (un sous-chart Bitnami) plutôt que de le templatiser vous-même. Avantage (maintenu par d'autres) et inconvénient (moins de contrôle) ?
3. **Un chart public** : `helm install` de kube-prometheus-stack (que vous ferez au bloc 3). Explorez ses `values.yaml` : des centaines de paramètres. C'est l'échelle réelle d'un chart de production.

## Questions de compréhension (à préparer pour le TD et l'examen)

1. Comparez le rôle de `values.yaml` (Helm) à celui de l'inventaire + `group_vars` (Ansible, S1). Qu'est-ce qui joue le rôle des templates dans chaque cas ? La logique « code séparé des données » est-elle la même ?
2. Deux installations (`dev`, `prod`) du même chart coexistent sans conflit. Par quel mécanisme leurs objets ne se mélangent-ils pas ? (Indice : `.Release.Name` et les namespaces.)
3. `helm template` n'installe rien. Quel est son intérêt, et à quelles commandes des semestres précédents cela vous fait-il penser (S1) ? Pourquoi « regarder avant d'agir » est-il une constante du métier ?
4. Quand un chart Helm est-il justifié, et quand des manifests bruts suffisent-ils ? Donnez un critère de décision et un exemple pour chaque cas.
