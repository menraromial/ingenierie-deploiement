---
title: "TP 13 : Composer l'application et générer un manifeste K8s"
sidebar_label: "TP 13 : Composer l'application et générer un manifeste K8s"
hide_title: true
---

import ChapterHead from '@site/src/components/ChapterHead';

<ChapterHead
  kicker="Semestre 2 · Bloc 1 · Travaux pratiques 13"
  title="Composer l'application, et générer un manifeste Kubernetes"
  competences={['C3']}
/>

:::fiche
- **Durée** : 4 h
- **Prérequis** : TP 12 (images construites) ; chapitre 18
- **Livrables** : le `compose.yaml` de Listify committé ; le manifeste Kubernetes généré depuis un pod ; runbook
- **Compétences travaillées** : C3 (cœur)

Vous passez des `podman run` manuels à une **description déclarative** de l'application entière, puis vous découvrirez le **pod** et générerez votre premier fichier au format Kubernetes. Toutes les commandes ont été validées sous Podman 5 et podman-compose.
:::

## Étape 1 : la composition déclarative (1 h 30)

### 1.0 Préparer le répertoire d'initialisation de la base

L'image PostgreSQL exécute, au **premier** démarrage, tous les scripts `*.sql` trouvés dans `/docker-entrypoint-initdb.d/`, **par ordre alphabétique**. Votre code étant en v1.1 (colonne `done`, migration du TP 4 du S1), la base doit charger le **schéma** puis la **migration**. On rassemble ces deux scripts, préfixés pour l'ordre, dans un répertoire dédié `db/initdb/` (qu'on montera en bloc, voir l'encadré plus bas sur le pourquoi) :

```bash
cd ~/Github/edu/listify        # adaptez à votre chemin
mkdir -p db/initdb
cp db/schema.sql                 db/initdb/00-schema.sql
cp db/migrations/001-add-done.sql db/initdb/01-add-done.sql
ls db/initdb/                    # 00-schema.sql  01-add-done.sql
```

On garde les fichiers d'origine (`db/schema.sql`, `db/migrations/…`) inchangés : ils servent au déploiement Ansible du S1. `db/initdb/` est la version « ordonnée pour l'init conteneur ».

### 1.1 Le fichier Compose

Lancer trois `podman run` avec les bons réseaux, volumes et variables, dans le bon ordre, c'est la douleur impérative du S1 qui revient. La réponse est la même : **décrire l'état voulu**. Créez `compose.yaml` à la racine du dépôt :

```yaml title="compose.yaml"
services:
  db:
    image: docker.io/library/postgres:16-alpine
    environment:
      POSTGRES_DB: listify
      POSTGRES_USER: listify
      POSTGRES_PASSWORD: ${DB_PASSWORD:-secret}
    volumes:
      - listify-data:/var/lib/postgresql/data
      # On monte un RÉPERTOIRE d'init (et non des fichiers un par un) : plus robuste,
      # et les scripts s'y exécutent par ordre alphabétique (00- avant 01-).
      - ./db/initdb:/docker-entrypoint-initdb.d:ro,z
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "listify"]
      interval: 5s
      timeout: 3s
      retries: 5

  backend:
    build: ./backend
    image: listify-backend:1.0
    environment:
      DB_HOST: db
      DB_PASSWORD: ${DB_PASSWORD:-secret}
    depends_on:
      db:
        condition: service_healthy

  frontend:
    build: ./frontend
    image: listify-frontend:1.0
    ports:
      - "8080:80"
    depends_on:
      - backend

volumes:
  listify-data:
```

Chaque ligne fait écho au parcours (ch. 18 §3.2) : les services se joignent **par nom** (`DB_HOST: db`), le **volume** persiste la base, `${DB_PASSWORD}` porte la **configuration** (facteur III), le **schéma** est chargé automatiquement au premier démarrage via le répertoire d'init de l'image postgres, et surtout `depends_on: condition: service_healthy` résout **déclarativement** l'ordre de démarrage qui nous poursuit depuis le S1.

:::danger[Pourquoi monter un répertoire et non des fichiers un par un]
On aurait pu monter chaque script séparément (`./db/schema.sql:/docker-entrypoint-initdb.d/00-schema.sql`). **Évitez-le** : bind-monter **un fichier seul** est un piège classique de Podman/Docker. Si le fichier source est introuvable au moment de créer le conteneur (par exemple si vous lancez `podman-compose` depuis le **mauvais répertoire**, ou après un montage raté), Podman ne renvoie **pas** d'erreur : il crée un **répertoire vide** à la place du fichier. La cascade est vicieuse :

- PostgreSQL tente d'exécuter un script qui est devenu un dossier → `could not read from input file: Is a directory` → l'**init échoue** → la base n'atteint **jamais** `healthy` ;
- comme le backend attend `depends_on: condition: service_healthy`, `podman-compose up` **se bloque indéfiniment** (le symptôme « ça reste figé »).

Monter un **répertoire** (`./db/initdb`) évite ce piège : si le dossier manque, Podman crée un dossier vide, PostgreSQL démarre sans script (base saine mais sans table) et vous obtenez un 500 clair, jamais un blocage.

**Règles d'or associées :** lancez toujours `podman-compose` **depuis la racine du dépôt** (pour que `./db/initdb` se résolve), et si un fichier a déjà été transformé en dossier parasite, réparez-le : `rm -rf db/le-fichier && git checkout db/le-fichier`. Enfin, quand un `up` se fige, le réflexe est `podman logs <projet>_db_1 | tail` : un `service_healthy` qui ne se satisfait jamais est **toujours** un problème de la base, pas du backend.
:::

### 1.2 Lancer toute l'application en une commande

```bash
cd ~/Github/edu/listify
export DB_PASSWORD=un-mot-de-passe-fort
podman-compose up -d           # ou : podman compose up -d
podman-compose ps              # les trois services
```

Testez la chaîne complète depuis votre poste :

```bash
curl -s http://localhost:8080/api/health         # {"api":"ok","database":"ok"}
curl -s -X POST http://localhost:8080/api/tasks \
     -H 'Content-Type: application/json' -d '{"title":"composé"}'
curl -s http://localhost:8080/api/tasks
```

:::warning[`/api/tasks` renvoie 500 alors que `/api/health` dit ok/ok ?]
Deux causes possibles, toutes deux liées au **chargement du schéma** :

- **Volume déjà existant.** Les scripts de `/docker-entrypoint-initdb.d/` ne s'exécutent qu'au **premier** démarrage, quand le volume est vide. Si vous aviez déjà un volume `listify-data` (d'un essai précédent ou du TP 12), le schéma n'a pas été chargé. Repartez propre : `podman-compose down -v` (le `-v` supprime le volume) puis `podman-compose up -d`.
- **Migration oubliée.** Si l'erreur exacte est `column "done" does not exist` (visible dans `podman-compose logs backend`), c'est que la migration n'a pas été jouée. Vérifiez que `db/initdb/` contient bien **les deux** fichiers (`00-schema.sql` ET `01-add-done.sql`, voir §1.0). Le code déployé est en v1.1 (colonne `done`, TP 4 du S1) ; la base doit l'être aussi.

Si le port **8080** est déjà pris sur votre poste (`address already in use`), changez le mapping du frontend dans `compose.yaml` (`"8090:80"`) et adaptez l'URL.
:::

Ouvrez `http://localhost:8080` au navigateur : Listify fonctionne, entièrement conteneurisé, **sans une seule VM**, décrit par un fichier de trente lignes. Comparez au S1 : quatre machines, des dizaines de fichiers Ansible, pour la même application. Mesurez le chemin parcouru.

:::warning[Le `:z` sur le montage du schéma]
Le suffixe `:ro,z` sur le montage de `db/initdb` gère les étiquettes SELinux (systèmes Fedora/RHEL) et rend le contenu lisible par le conteneur ; `ro` le monte en lecture seule. Sur un système sans SELinux (Ubuntu par défaut), le `z` est inoffensif. Notez ce genre de détail : la portabilité des montages entre distributions est un vrai sujet.
:::

### 1.3 Arrêter, et observer la persistance

```bash
podman-compose down            # arrête et supprime les conteneurs ET le réseau
podman volume ls | grep listify   # MAIS le volume persiste
podman-compose up -d           # tout revient, avec les données
```

`down` détruit les conteneurs (jetables) mais **pas le volume** (précieux) : la distinction stateless/stateful, opérationnalisée. Pour tout supprimer, volume compris : `podman-compose down -v`.

<details className="controle">
<summary>Point de contrôle n° 1 : l'ordre de démarrage géré déclarativement</summary>

Regardez les logs au démarrage : le backend **attend** que la base soit `healthy` avant de démarrer (grâce à `depends_on: condition: service_healthy`). Au S1, cet ordre reposait sur la discipline (le play `db` avant le play `backend`) et sur la tolérance de l'application (503 propre). Ici, il est **déclaré**. Notez la progression, elle mène droit aux *probes* de Kubernetes (bloc 2).

</details>

## Étape 2 : le pod, unité de Kubernetes (1 h)

### 2.1 Regrouper dans un pod

Le **pod** (ch. 18 §4) groupe des conteneurs qui partagent le **namespace réseau** : ils ont la même adresse IP et se joignent par `localhost`. Reconstruisons Listify en pod pour découvrir ce concept, central au bloc 2 :

```bash
# Un pod qui publie le port 80 (du frontend) sur le 8081 de l'hôte
podman pod create --name listify-pod -p 8081:80

# La base, DANS le pod
podman run -d --pod listify-pod --name db \
  -e POSTGRES_DB=listify -e POSTGRES_USER=listify -e POSTGRES_PASSWORD=secret \
  docker.io/library/postgres:16-alpine
# attendre la disponibilité, puis charger le schéma ET la migration (code v1.1)
for i in $(seq 1 20); do podman exec db pg_isready -U listify >/dev/null 2>&1 && break; sleep 1; done
podman exec -i db psql -U listify -d listify < db/schema.sql
podman exec -i db psql -U listify -d listify < db/migrations/001-add-done.sql

# Le backend : il joint la base par 127.0.0.1 (réseau PARTAGÉ dans le pod !)
podman run -d --pod listify-pod --name backend \
  -e DB_HOST=127.0.0.1 -e DB_PASSWORD=secret listify-backend:1.0
```

Point remarquable, à consigner : dans un pod, `DB_HOST=127.0.0.1` fonctionne, parce que les conteneurs **partagent la même pile réseau** (ch. 18 §4.1). C'est différent du réseau nommé de l'étape 1 (où l'on utilisait `DB_HOST=db`). Vérifiez :

```bash
podman exec backend python3 -c "import urllib.request as u; print(u.urlopen('http://127.0.0.1:8000/api/health').read().decode())"
# {"api":"ok","database":"ok"}
```

### 2.2 Générer le manifeste Kubernetes

Le geste-passerelle du bloc. Podman traduit votre pod en YAML au **format Kubernetes** :

```bash
podman kube generate listify-pod -f listify-pod.yaml
cat listify-pod.yaml
```

Lisez ce fichier attentivement (c'est un livrable et un objet d'étude) : `apiVersion: v1`, `kind: Pod`, une liste de `containers` avec leurs `image`, `env`, `ports`. **C'est votre premier objet Kubernetes**, produit à partir de conteneurs que vous maîtrisez. Vous n'avez pas encore installé Kubernetes, et vous avez déjà écrit (fait écrire) un de ses manifestes.

### 2.3 Rejouer un manifeste

L'opération inverse fonctionne aussi : Podman sait *exécuter* un manifeste Kubernetes localement.

```bash
podman pod rm -f listify-pod                 # on repart de zéro
podman kube play listify-pod.yaml            # recrée tout depuis le YAML
podman pod ps
```

`podman kube play` lit le même format que `kubectl apply` consommera au bloc 2. Vous tenez la continuité : le YAML que vous venez de générer se rejouera, presque tel quel, sur un vrai cluster Kubernetes.

<details className="controle">
<summary>Point de contrôle n° 2 : lire l'objet Pod</summary>

Dans `listify-pod.yaml`, identifiez et notez : le `kind`, le nombre de `containers`, comment le port est publié (`hostPort`/`containerPort`), où sont les variables d'environnement. Comparez mentalement avec le `compose.yaml` de l'étape 1 : qu'est-ce qui se ressemble, qu'est-ce qui diffère ? (Le pod ne gère pas le *build* des images ni les `depends_on` : Kubernetes a d'autres mécanismes pour cela, au bloc 2.)

</details>

## Étape 3 : nettoyage et synthèse (30 min)

```bash
podman pod rm -f listify-pod
podman-compose down -v
podman network rm listify-net 2>/dev/null
```

Rédigez au runbook la comparaison **compose vs pod** : quand utiliser l'un, quand l'autre ? (Indice : Compose orchestre des services indépendants reliés par un réseau ; le pod regroupe des conteneurs *inséparables* partageant le réseau. Kubernetes utilise les deux idées : le Pod comme unité, et des objets de plus haut niveau pour relier les Pods entre eux, au bloc 2.)

## Point de contrôle final

- [ ] `compose.yaml` : les trois services démarrent en une commande, chaîne complète fonctionnelle au navigateur
- [ ] `depends_on: service_healthy` : ordre de démarrage géré déclarativement (observé dans les logs)
- [ ] Persistance : `down` puis `up` conserve les données (volume)
- [ ] Pod : backend joignant la base par `127.0.0.1` (réseau partagé), health ok/ok
- [ ] `listify-pod.yaml` généré, lu et commenté ; rejoué avec `podman kube play`
- [ ] Comparaison compose/pod rédigée ; `compose.yaml` **et** `db/initdb/` committés

## Pour aller plus loin (bonus)

1. **Profils Compose** : ajoutez un service `adminer` (interface web pour PostgreSQL) sous un profil `debug` (`profiles: [debug]`), lancé seulement avec `podman-compose --profile debug up`. À quoi servent les profils ?
2. **Healthcheck du backend** : ajoutez un `healthcheck` au service `backend` dans `compose.yaml` (une requête sur `/api/health`). Le frontend peut-il alors `depends_on: backend: condition: service_healthy` ?
3. **Volume nommé vs bind mount** : montez le code du backend en bind mount (`./backend:/app`) pour l'éditer à chaud sans reconstruire l'image. Quand ce mode est-il utile, et pourquoi ne l'utilise-t-on jamais en production ?

## Questions de compréhension (à préparer pour le TD et l'examen)

1. Dans le `compose.yaml`, le backend joint la base par `DB_HOST: db` ; dans le pod, par `DB_HOST: 127.0.0.1`. Expliquez la différence en termes de namespaces réseau (ch. 15 et 18).
2. `depends_on: condition: service_healthy` résout un problème qui nous suit depuis le S1. Lequel, et comment le résolviez-vous avant (systemd, health check applicatif) ?
3. Vous avez généré un `kind: Pod`. En quoi le Pod est-il l'unité de déploiement de Kubernetes, et pourquoi Podman propose-t-il exactement ce concept ?
4. Comparez le rôle du fichier `compose.yaml` (S2) à celui du `Vagrantfile` + rôles Ansible (S1) : que décrivent-ils chacun, et à quelle échelle ?
