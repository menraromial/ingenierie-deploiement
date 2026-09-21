---
title: "TP 12 : Conteneuriser les trois services"
sidebar_label: "TP 12 : Conteneuriser les trois services"
hide_title: true
---

import ChapterHead from '@site/src/components/ChapterHead';

<ChapterHead
  kicker="Semestre 2 · Bloc 1 · Travaux pratiques 12"
  title="Conteneuriser les trois services de Listify"
  competences={['C3']}
/>

:::fiche
- **Durée** : 4 h
- **Prérequis** : TP 11 ; chapitres 16 et 17
- **Livrables** : les `Containerfile` des trois tiers dans le dépôt `listify`, les images construites, la mesure des tailles avant/après optimisation ; runbook
- **Compétences travaillées** : C3 (cœur)

Vous emballez le code de Listify (inchangé) en **images immuables**. À la fin, chaque tier est une image lancée par un simple `podman run`. Toutes les commandes de ce TP ont été validées sous Podman 5.
:::

## Étape 1 : le backend, et la découverte du cache (1 h 30)

### 1.1 Un premier Containerfile

Dans votre dépôt, créez `backend/Containerfile` :

```dockerfile title="backend/Containerfile"
FROM python:3.12-slim

# Un utilisateur non-root (moindre privilège, ch. 17 §4.2)
RUN useradd --system --no-create-home --shell /usr/sbin/nologin listify

WORKDIR /app

# Dépendances AVANT le code : le cache de build (ch. 17 §2)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Le code applicatif ensuite
COPY app.py wsgi.py ./

# Exécution en non-root, sur toutes les interfaces DU CONTENEUR
USER listify
EXPOSE 8000
CMD ["gunicorn", "--workers", "3", "--bind", "0.0.0.0:8000", "wsgi:app"]
```

Et un `backend/.containerignore` pour ne pas polluer le contexte de build (ch. 17 §2) :

```text title="backend/.containerignore"
.venv/
__pycache__/
*.pyc
```

Construisez et lisez la sortie couche par couche :

```bash
cd ~/Github/edu/listify        # adaptez à votre chemin
podman build -t listify-backend:1.0 ./backend
podman images | grep listify-backend        # ~150 Mo
```

### 1.2 Éprouver le cache

Le cœur pédagogique de l'étape. Faites une modification **dans le code** (`backend/app.py`, ajoutez un commentaire), puis reconstruisez :

```bash
podman build -t listify-backend:1.1 ./backend
```

Observez : les couches `pip install` sont marquées **`Using cache`** ; seule la couche `COPY app.py` et les suivantes sont refaites. Le build est quasi instantané. Maintenant, modifiez `requirements.txt` (même trivialement) et reconstruisez : cette fois `pip install` **est** refait. Vous venez de vérifier de vos yeux la règle « dépendances avant code » (ch. 17 §2). Consignez les deux durées : l'écart est l'argument.

<details className="controle">
<summary>Point de contrôle n° 1 : le backend tourne, isolé</summary>

Le backend a besoin d'une base. Lancez un PostgreSQL jetable et testez :

```bash
podman network create listify-net
podman run -d --name db --network listify-net \
  -e POSTGRES_DB=listify -e POSTGRES_USER=listify -e POSTGRES_PASSWORD=secret \
  docker.io/library/postgres:16-alpine

# ATTENDRE que la base soit prête (au 1er démarrage, initdb prend quelques
# secondes ; sans cette attente, le health renverrait 503 "database error").
for i in $(seq 1 20); do podman exec db pg_isready -U listify >/dev/null 2>&1 && break; sleep 1; done

# charger le schéma :
podman exec -i db psql -U listify -d listify < db/schema.sql

# lancer le backend, qui joint "db" PAR SON NOM (DNS de réseau, ch. 18) :
podman run -d --name backend --network listify-net \
  -e DB_HOST=db -e DB_PASSWORD=secret listify-backend:1.0
sleep 2
podman exec backend python3 -c "import urllib.request as u; print(u.urlopen('http://127.0.0.1:8000/api/health').read().decode())"
# {"api":"ok","database":"ok"}
```

Notez : `DB_HOST=db` fonctionne sans connaître d'adresse IP, c'est le DNS interne du réseau Podman (ch. 18 §1.2). Et si le health renvoie **503** (`database error`), ce n'est pas un bug : c'est que la base n'était pas encore prête, exactement le problème d'ordre de démarrage que le `depends_on: condition: service_healthy` du TP 13 résout **déclarativement**. Nettoyez ensuite les conteneurs **et le réseau** (sinon `network create` échouera au prochain passage avec « network already exists ») :

```bash
podman rm -f db backend
podman network rm listify-net
```

</details>

## Étape 2 : le frontend et Nginx (1 h)

Le frontend sert les fichiers statiques et fait office de reverse proxy vers le backend (exactement le rôle de Nginx au S1). Créez `frontend/Containerfile` :

```dockerfile title="frontend/Containerfile"
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html app.js style.css /usr/share/nginx/html/
EXPOSE 80
```

Et la configuration Nginx `frontend/nginx.conf`, où le proxy pointe vers le service `backend` (résolu par le DNS du réseau) :

```nginx title="frontend/nginx.conf"
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ =404;
    }
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host              $host;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
podman build -t listify-frontend:1.0 ./frontend
podman images | grep listify-frontend       # ~50 Mo, grâce à la base alpine
```

:::note[Pourquoi le proxy pointe vers `backend` et non une adresse IP]
Comme au S1 avec `/etc/hosts`, le frontend doit joindre le backend par un **nom stable**, pas par une IP qui changera. Sur le réseau Podman, le nom du conteneur/service (`backend`) est résolu automatiquement. C'est la même idée qu'au S1, fournie nativement (ch. 18 §1.2). Attention : Nginx résout ce nom au **démarrage** ; le conteneur `backend` doit donc exister quand le frontend démarre (l'ordre sera géré déclarativement au TP 13 avec `depends_on`).
:::

## Étape 3 : la base et le volume (45 min)

La base n'a pas de Containerfile : on utilise l'image officielle `postgres:16-alpine`. Ce qui compte, c'est de **persister ses données** dans un volume (ch. 18 §2), sans quoi elles disparaîtraient avec le conteneur :

```bash
podman volume create listify-data
podman run -d --name db \
  -e POSTGRES_DB=listify -e POSTGRES_USER=listify -e POSTGRES_PASSWORD=secret \
  -v listify-data:/var/lib/postgresql/data \
  docker.io/library/postgres:16-alpine
# attendre la disponibilité avant de charger le schéma
for i in $(seq 1 20); do podman exec db pg_isready -U listify >/dev/null 2>&1 && break; sleep 1; done
podman exec -i db psql -U listify -d listify < db/schema.sql
```

(Cette étape isole la base : pas besoin du réseau nommé, aucun autre conteneur ne la joint par son nom ici.)

<details className="controle">
<summary>Point de contrôle n° 2 : la persistance</summary>

Prouvez que le volume survit au conteneur :

```bash
podman exec db psql -U listify -d listify -c "INSERT INTO tasks (title) VALUES ('survivra');"
podman rm -f db                                   # le conteneur MEURT
podman run -d --name db \
  -e POSTGRES_DB=listify -e POSTGRES_USER=listify -e POSTGRES_PASSWORD=secret \
  -v listify-data:/var/lib/postgresql/data docker.io/library/postgres:16-alpine
for i in $(seq 1 20); do podman exec db pg_isready -U listify >/dev/null 2>&1 && break; sleep 1; done
podman exec db psql -U listify -d listify -c "SELECT title FROM tasks;"   # 'survivra' est là
```

Le conteneur est jetable ; le **volume** garde les données. C'est la distinction stateless/stateful du S1, au niveau du stockage (ch. 18 §2). Nettoyez : `podman rm -f db && podman volume rm listify-data`.

</details>

## Étape 4 : mesurer et optimiser (45 min)

Inspectez ce que contiennent vos images et leur poids :

```bash
podman images --format "table {{.Repository}} {{.Tag}} {{.Size}}"
podman history listify-backend:1.0        # la taille de CHAQUE couche
```

Expérimentez une optimisation et **mesurez** :

- Comparez `python:3.12` (base complète) et `python:3.12-slim` (notre choix) : changez le `FROM`, reconstruisez, comparez les tailles. L'écart (~300 Mo) justifie le `-slim`.
- Bonus : l'outil `dive` (s'il est disponible) explore une image couche par couche et signale le gaspillage.

Consignez le tableau des tailles : c'est un livrable, et l'argument concret des bonnes pratiques du chapitre 17.

## Point de contrôle final

- [ ] Les trois tiers conteneurisés : `listify-backend`, `listify-frontend` construits ; `postgres` avec volume
- [ ] Cache de build éprouvé (modif code = rapide ; modif requirements = pip refait), durées consignées
- [ ] Backend joignant la base par le **nom** `db` (DNS de réseau)
- [ ] Persistance prouvée : donnée survivant à la destruction du conteneur (volume)
- [ ] Tableau des tailles d'images ; effet du `-slim` mesuré
- [ ] Containerfile + `.containerignore` committés dans le dépôt

## Pour aller plus loin (bonus)

1. **Utilisateur non-root vérifié** : `podman run --rm listify-backend:1.0 id` : le processus tourne-t-il bien en `listify` et non en root ? Et en rootless, à quel UID cela correspond-il sur l'hôte (`podman top`) ?
2. **Multi-stage anticipé** : le frontend deviendra multi-stage quand il aura un build (Vite). Écrivez dès maintenant un Containerfile multi-stage fictif (étape `node` qui « build », étape `nginx` qui sert) pour vous entraîner à la syntaxe `COPY --from=` (ch. 17 §3).
3. **Digest vs tag** : `podman image inspect listify-backend:1.0 --format '{{.Digest}}'` : notez le digest. Reconstruisez à l'identique : le digest change-t-il ? (Découverte de la non-reproductibilité des builds, ch. 17, Regard recherche.)

## Questions de compréhension (à préparer pour le TD et l'examen)

1. Expliquez, couche par couche, pourquoi modifier `app.py` reconstruit beaucoup moins que modifier `requirements.txt`, dans notre Containerfile. Reliez au copy-on-write du chapitre 15.
2. Le code de Listify n'a pas changé depuis le S1. Qu'est-ce qui a changé, alors, et en quoi cela règle-t-il le « ça marche sur ma machine » ? (Réponse attendue : l'artefact, l'immutabilité.)
3. Pourquoi la base de données a-t-elle besoin d'un volume alors que le backend n'en a pas ? Généralisez à la distinction stateless/stateful.
4. `EXPOSE 8000` ne « publie » aucun port. À quoi sert cette instruction, alors, et quelle commande publie réellement le port ?
