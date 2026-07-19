# TP 10 : Terraform en découverte, le state et la dérive

!!! abstract "Fiche du TP"
    - **Durée** : 3 h (TP de découverte : l'objectif est de *voir tourner* les concepts du chapitre 13, pas de maîtriser Terraform)
    - **Prérequis** : chapitre 13 ; Podman installé (S2 le généralisera ; ici on n'utilise que son socket)
    - **Livrables** : la configuration `.tf`, l'observation commentée d'un cycle plan/apply, la **capture d'une dérive détectée** ; runbook
    - **Compétences travaillées** : C2

    On reste 100 % local : le provider Docker de Terraform pilote le socket Podman (compatible API Docker). Aucun compte cloud, aucune installation de Docker. Le cloud reste au tableau (chapitre 13).

## Pourquoi ce TP, après Ansible ?

Ansible vous a montré **configurer** ; Terraform montre **provisionner** avec sa pièce originale, le **state** et la **détection de dérive** (ch. 13). On ne va pas reconstruire Listify avec : on va isoler ces deux mécanismes sur un exemple minimal (un conteneur Nginx), pour les *voir* fonctionner. C'est un TP de concepts, court et dense.

## Étape 0 : installer Terraform et activer le socket Podman (30 min)

```bash
# Terraform (dépôt HashiCorp, comme Vagrant au TP 7) OU OpenTofu (ch. 13)
sudo apt install -y terraform      # ou : suivez le guide pour opentofu (commande 'tofu')
terraform version

# Le socket Podman, compatible API Docker, en mode utilisateur (rootless)
systemctl --user enable --now podman.socket
systemctl --user status podman.socket        # active (listening)
echo "$XDG_RUNTIME_DIR/podman/podman.sock"    # notez ce chemin, il ira dans le provider
```

## Étape 1 : la configuration (30 min)

Dans un répertoire de travail, hors du dépôt Listify (c'est un exercice séparé) :

```bash
mkdir ~/tp10-terraform && cd ~/tp10-terraform
```

```terraform title="main.tf"
terraform {
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }
  }
}

provider "docker" {
  # Adaptez au chemin affiché à l'étape 0 (souvent /run/user/1000/podman/podman.sock)
  host = "unix:///run/user/1000/podman/podman.sock"
}

resource "docker_image" "web" {
  name = "docker.io/library/nginx:1.27-alpine"
}

resource "docker_container" "web" {
  name  = "tf-demo"
  image = docker_image.web.image_id
  ports {
    internal = 80
    external = 8088
  }
}
```

## Étape 2 : le cycle init / plan / apply (45 min)

```bash
terraform init      # télécharge le provider docker ; crée .terraform/ et le lock
```

Regardez ce qu'`init` a créé (`.terraform/`, `.terraform.lock.hcl`), puis le geste central du chapitre 13, **plan avant apply** :

```bash
terraform plan
```

Lisez le plan attentivement (il va au runbook) : `2 to add, 0 to change, 0 to destroy`, avec le détail de l'image et du conteneur, et les `(known after apply)` pour les valeurs que seul le fournisseur connaîtra (l'ID de l'image). Rien n'a encore été fait : c'est une **prévision**. Puis :

```bash
terraform apply     # ré-affiche le plan, demande confirmation : tapez 'yes'
podman ps           # le conteneur tf-demo tourne
curl -s localhost:8088 | head -5      # la page nginx
```

Ouvrez maintenant le **state** (sans jamais l'éditer à la main) :

```bash
terraform show                        # l'état lisible
ls -l terraform.tfstate               # le fichier ; NE VA PAS dans Git (ch. 13, §3.3)
```

??? question "Point de contrôle n° 1 : le graphe et l'ordre"
    Vous n'avez écrit aucun ordre, pourtant l'image a été créée avant le conteneur. Retrouvez, dans la sortie de `plan` ou avec `terraform graph`, la dépendance qui l'a imposé (la ligne `image = docker_image.web.image_id`). Reliez au chapitre 13, §2.1 : l'ordre est **calculé** depuis les références.

## Étape 3 : la détection de dérive (l'expérience clé, 45 min)

Le cœur du TP. On modifie la réalité **dans le dos de Terraform**, puis on regarde comment il réagit.

```bash
# Détruire le conteneur À LA MAIN (comme un collègue pressé, ou un incident)
podman rm -f tf-demo
podman ps -a | grep tf-demo || echo "tf-demo n'existe plus"

# Terraform ne le sait pas encore. Demandons-lui de comparer :
terraform plan
```

Lisez la sortie : Terraform a **rafraîchi** son state face à la réalité, constaté que le conteneur déclaré n'existe plus, et propose `1 to add` pour le recréer. **C'est la détection de dérive** (ch. 13, §3.2) : l'écart entre la configuration (le conteneur doit exister) et la réalité (il n'existe plus) est détecté et corrigible.

```bash
terraform apply      # 'yes' : le conteneur renaît, conforme à la configuration
podman ps            # tf-demo est de retour
```

Faites la variante « modification » : changez le port externe à `8089` dans `main.tf`, `terraform plan` (il montre un `-/+`, remplacement : le conteneur doit être détruit puis recréé, car le port n'est pas modifiable à chaud), puis `apply`. Observez le `~`/`-/+` : Terraform distingue ce qui se modifie en place de ce qui exige un remplacement.

??? question "Point de contrôle n° 2 : les trois termes"
    Remplissez le tableau du chapitre 13 (§3.2) avec CE que vous venez de voir : dans le cas « `podman rm -f` », quelle était la **configuration**, quel était le **state avant refresh**, quelle était la **réalité**, et qu'a proposé le `plan` ? Ce tableau est une question d'examen quasi certaine.

## Étape 4 : destruction et nettoyage (15 min)

```bash
terraform destroy    # 'yes' : détruit tout ce qui est dans le state (ordre inverse)
podman ps -a | grep tf-demo || echo "propre"
```

Notez le principe : `destroy` détruit **ce que le state connaît**, dans l'ordre inverse de création (conteneur puis image). Ce que Terraform n'a pas créé, il n'y touche pas : le state est sa **frontière de propriété** (ch. 13, §3.1).

## Étape 5 : la synthèse comparative (15 min)

Rédigez au runbook, en un paragraphe : qu'est-ce que Terraform fait que Ansible ne fait pas (le state, la détection qu'une ressource déclarée a **disparu**, la destruction du non-déclaré) ? Et qu'est-ce qu'Ansible fait que ce Terraform ne fait pas (configurer *l'intérieur* d'une machine : paquets, fichiers, services) ? Concluez par la phrase du chapitre 13 : **Terraform provisionne, Ansible configure**, et notre TP 9 (Vagrant + Ansible) est la maquette locale de ce couple.

## Point de contrôle final

- [ ] `terraform apply` crée le conteneur ; `curl localhost:8088` répond
- [ ] Le rôle du plan (prévision avant action) compris et consigné
- [ ] **Dérive provoquée (`podman rm -f`) et détectée par `terraform plan`** : la capture au runbook
- [ ] La distinction `~` (modif en place) / `-/+` (remplacement) observée
- [ ] `terraform destroy` nettoie ; synthèse Terraform vs Ansible rédigée
- [ ] `terraform.tfstate` **non commité** (vérifié dans `.gitignore` si vous versionnez cet exercice)

## Pour aller plus loin (bonus)

1. **Le graphe** : `terraform graph | dot -Tsvg > graph.svg` (paquet `graphviz`) ; visualisez le DAG de deux ressources. Gardez cette image : au S3, les DAG d'Airflow lui ressembleront comme des frères.
2. **Une variable et une sortie** : ajoutez une `variable "external_port"` et un bloc `output "url"` ; `terraform apply -var external_port=9090` puis `terraform output`. Vous retrouvez la séparation code/données de tout le semestre.
3. **Deux conteneurs et un réseau** : déclarez un `docker_network` et deux conteneurs dessus ; observez comment le graphe ordonne le réseau avant les conteneurs. Vous provisionnez une mini-infra.
4. **Simuler le cloud sans cloud** : explorez le provider `local` (fichiers) ou lisez la configuration d'un module AWS de la documentation ; identifiez ce qui change (types de ressources) et ce qui ne change **pas** (init/plan/apply, state, graphe). C'est tout l'intérêt du modèle.

## Questions de compréhension (à préparer pour le TD et l'examen)

1. Pourquoi Terraform a-t-il besoin d'un state alors qu'Ansible n'en a pas ? Répondez par la nature de leur interlocuteur (une API vaste vs un OS qu'on relit intégralement).
2. Vous supprimez une ressource de `main.tf` (vous cessez de la déclarer) puis `apply`. Que se passe-t-il, et pourquoi est-ce parfois une **mauvaise surprise** en production ? Quelle pratique (revue du `plan`) l'évite ?
3. Le state contient des secrets en clair et ne va pas dans Git. Où le met-on quand on travaille à plusieurs, et quel nouveau problème (accès concurrent) cela crée-t-il ? (Cherchez « remote backend » et « state locking ».)
4. Terraform et le `deploy.sh` du TP 9 gèrent tous deux un « ordre ». Comparez : l'ordre de Terraform est **calculé** (graphe de dépendances), celui du script est **écrit** (deux lignes). Lequel passe mieux à l'échelle de 200 ressources, et pourquoi ?
