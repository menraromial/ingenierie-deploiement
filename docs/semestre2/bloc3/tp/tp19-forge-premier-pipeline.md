---
title: "TP 19 : Forge locale et premier pipeline"
sidebar_label: "TP 19 : Forge locale et premier pipeline"
hide_title: true
---

import ChapterHead from '@site/src/components/ChapterHead';
import Figure from '@site/src/components/Figure';

<ChapterHead
  kicker="Semestre 2 · Bloc 3 · Travaux pratiques 19"
  title="Monter sa forge locale et son premier pipeline"
  competences={['C2', 'C4']}
/>

:::fiche
- **Durée** : 4 h
- **Prérequis** : bloc 1 du S2 (Podman), TP 18 (dépôt `listify` à jour) ; chapitre 23
- **Livrables** : une forge Gitea locale hébergeant `listify` ; un runner enregistré ; les tests pytest de Listify ; un workflow `ci.yaml` vert ; la trace d'un pipeline rouge puis réparé ; runbook
- **Compétences travaillées** : C2 (automatiser), C4 (qualité)

Vous installez sur votre poste l'équivalent d'un GitHub privé : une forge **Gitea** avec son système d'actions, et un **runner** qui exécute les pipelines dans des conteneurs. Vous écrivez les premiers tests automatiques de Listify, puis le pipeline du chapitre 23, qui les exécute à chaque `git push`. Toutes les commandes et tous les fichiers de ce TP ont été exécutés et validés sur un poste Linux avec Podman 5.7 rootless, Gitea 1.27.3 et act_runner 0.6.1.
:::

## Ce que vous allez construire

<Figure src="tp19-architecture" num="TP19.1" alt="Vous poussez sur Gitea (localhost:3300) ; le runner act_runner récupère les jobs et demande au Podman de l'hôte de créer, dans un réseau propre au job, le conteneur du job et un service PostgreSQL ; le job clone le dépôt par host.containers.internal:3300 et joint la base par le nom db.">
  Ce que vous allez construire. Trois conteneurs longue durée (Gitea, le runner, et plus tard votre cluster) et des conteneurs jetables, créés pour chaque job puis détruits. Le runner ne fait rien lui-même : il demande au Podman de votre poste de créer les conteneurs.
</Figure>

Retenez dès maintenant la particularité de cette architecture, source de la plupart des pannes du bloc : **plusieurs points de vue réseau coexistent**. Pour votre navigateur, Gitea est à `localhost:3300`. Pour un conteneur, `localhost` désigne le conteneur lui-même ; il atteint votre poste, et donc Gitea, par le nom spécial `host.containers.internal`, que Podman ajoute automatiquement dans tous les conteneurs.

## Étape 0 : préparer le poste (15 min)

Ce TP télécharge environ 2,2 Go d'images, dont **1,66 Go** pour la seule image dans laquelle s'exécutent les jobs. Lancez les téléchargements **dès le début**, pendant que vous lisez la suite :

```bash
podman pull docker.io/gitea/gitea:1.27.3
podman pull docker.io/gitea/act_runner:0.6.1
podman pull docker.io/library/postgres:16-alpine
podman pull docker.gitea.com/runner-images:ubuntu-latest     # 1,66 Go : le plus long
```

Vérifiez que le port 3300, celui de la forge, est libre :

```bash
ss -tln | grep ':3300 '          # aucune ligne = libre
```

S'il est occupé, choisissez un autre port (par exemple 3400) et remplacez `3300` partout dans le TP, **y compris dans les adresses `host.containers.internal:3300`**.

:::note[Le cluster kind n'est pas nécessaire aujourd'hui]
Le TP 19 n'utilise pas Kubernetes. Si votre cluster kind du bloc 2 tourne encore, vous pouvez le supprimer pour libérer de la mémoire ; le TP 20 en recrée un, configuré différemment.
:::

## Étape 1 : la forge Gitea (40 min)

### 1.1 Lancer Gitea

Gitea est un conteneur unique, avec une base SQLite intégrée : idéal pour un poste de travail.

```bash
podman volume create gitea-data

podman run -d --name gitea -p 3300:3300 -v gitea-data:/data \
  -e GITEA__server__HTTP_PORT=3300 \
  -e GITEA__database__DB_TYPE=sqlite3 \
  -e GITEA__server__ROOT_URL=http://host.containers.internal:3300/ \
  -e GITEA__server__PUBLIC_URL_DETECTION=auto \
  -e GITEA__server__DISABLE_SSH=true \
  -e GITEA__security__INSTALL_LOCK=true \
  -e GITEA__service__DISABLE_REGISTRATION=true \
  docker.io/gitea/gitea:1.27.3

# attendre que la forge réponde (une vingtaine de secondes au premier démarrage)
until curl -sf http://localhost:3300/api/healthz >/dev/null; do sleep 2; done; echo "Gitea prête"
```

Chaque variable `GITEA__section__CLE` remplace la clé `CLE` de la section `[section]` du fichier de configuration de Gitea : c'est la configuration par l'environnement du facteur III des *Twelve-Factor Apps* (ch. 24), appliquée à un logiciel tiers. Les lignes de `server` méritent une explication, car elles résolvent le problème des points de vue réseau :

| Variable | Rôle |
|---|---|
| `HTTP_PORT=3300` | Le port d'écoute de Gitea **dans** son conteneur. Par défaut 3000 ; on le fait coïncider avec le port publié sur le poste, pour n'avoir qu'un seul numéro en tête. |
| `ROOT_URL=http://host.containers.internal:3300/` | L'adresse « officielle » de la forge. Gitea la transmet aux jobs, qui s'en servent pour cloner le dépôt. Elle doit donc être joignable **depuis un conteneur**. |
| `PUBLIC_URL_DETECTION=auto` | Pour les liens de l'interface web, Gitea utilise l'adresse par laquelle **vous** l'avez contactée (`localhost:3300`). Sans elle, les liens de l'interface pointeraient vers `host.containers.internal`, que votre navigateur ne sait pas résoudre. |
| `INSTALL_LOCK=true` | Saute l'assistant d'installation web : la configuration est entièrement déclarée. |
| `DISABLE_REGISTRATION=true` | Personne ne peut créer de compte : c'est votre forge privée. |

### 1.2 Créer votre compte administrateur

L'inscription étant fermée, on crée le premier compte en ligne de commande, **dans** le conteneur :

```bash
podman exec -u git gitea gitea admin user create --admin \
  --username etudiant --password 'Choisissez-un-mot-de-passe' \
  --email etudiant@listify.local --must-change-password=false
# New user 'etudiant' has been successfully created!
```

Ouvrez **http://localhost:3300** dans votre navigateur et connectez-vous. Le reste du TP utilise le nom d'utilisateur `etudiant` ; si vous en choisissez un autre, adaptez les chemins (`etudiant/listify`).

<details className="controle">
<summary>Point de contrôle n° 1 : la forge répond</summary>

- `curl -s http://localhost:3300/api/healthz` renvoie `"status": "pass"`.
- Vous êtes connecté dans l'interface web, et le menu de votre avatar propose « Administration du site ».
- Au runbook : la commande de lancement, et la raison des deux variables `ROOT_URL` et `PUBLIC_URL_DETECTION`, dans vos mots.

</details>

## Étape 2 : héberger Listify sur la forge (20 min)

Dans l'interface, cliquez sur **+** puis **Nouveau dépôt** : nom `listify`, dépôt **vide** (ne cochez pas « Initialiser le dépôt »), branche par défaut `main`. Puis, depuis votre dépôt local :

```bash
cd ~/Github/edu/listify                  # adaptez à votre chemin
git remote add forge http://localhost:3300/etudiant/listify.git
git push forge main                      # identifiants : etudiant et votre mot de passe
```

Rafraîchissez la page du dépôt : votre code, votre historique et vos Containerfile y sont. Vous gardez votre dépôt d'origine (`origin`) ; `forge` est un second dépôt distant, celui qui fait tourner la CI.

## Étape 3 : écrire les tests de Listify (1 h)

Un pipeline qui n'exécute aucun test ne vérifie rien (ch. 23, §4.2). Listify n'en a pas encore : écrivons-les, sur les deux premiers niveaux de la pyramide (ch. 23, §5.1).

### 3.1 La configuration de pytest

```ini title="backend/pytest.ini"
[pytest]
# « from app import app » fonctionne où que l'on lance pytest
pythonpath = .
testpaths = tests
markers =
    integration: test qui a besoin d'un vrai PostgreSQL (variables DB_HOST, DB_PASSWORD)
```

`pythonpath = .` ajoute le dossier `backend/` au chemin d'import, pour que les tests puissent faire `from app import app` sans manipulation. Le **marqueur** `integration` distingue les tests qui ont besoin d'une base : on pourra lancer les autres seuls, en quelques millisecondes, sans aucun service.

### 3.2 Les fixtures communes

```python title="backend/tests/conftest.py"
"""Fixtures communes aux tests de Listify."""
import pathlib

import pytest

from app import app as flask_app
from app import get_conn

DB_DIR = pathlib.Path(__file__).resolve().parents[2] / "db"


@pytest.fixture
def client():
    """Client HTTP de test : envoie des requêtes à l'application sans serveur."""
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


@pytest.fixture(scope="session")
def schema():
    """Charge le schéma puis les migrations, une seule fois pour toute la suite."""
    scripts = [DB_DIR / "schema.sql", *sorted((DB_DIR / "migrations").glob("*.sql"))]
    with get_conn() as conn, conn.cursor() as cur:
        for script in scripts:
            cur.execute(script.read_text(encoding="utf-8"))


@pytest.fixture
def db(schema):
    """Base vide avant chaque test d'intégration : les tests restent indépendants."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE tasks RESTART IDENTITY")
```

Trois idées à noter au runbook :

- `client` utilise le **client de test de Flask** : les requêtes sont traitées par l'application sans démarrer Gunicorn ni ouvrir de port.
- `schema` a une portée **de session** : le schéma et les migrations (celle du TP 4 comprise) ne sont chargés qu'une fois. Comme `schema.sql` et la migration sont idempotents (`IF NOT EXISTS`), relancer la suite ne pose aucun problème.
- `db` vide la table avant **chaque** test d'intégration. Un test qui dépendrait des restes du précédent passerait ou échouerait selon l'ordre d'exécution : c'est l'une des causes classiques de tests instables (ch. 23, §7).

### 3.3 Les tests

```python title="backend/tests/test_api.py"
"""Tests de l'API Listify.

Deux niveaux de la pyramide (ch. 23, §5.1) :
- tests unitaires : aucun accès à la base, ils tournent partout en quelques ms ;
- tests d'intégration (marqueur « integration ») : il faut un vrai PostgreSQL.
"""
import pytest

# ---------- Tests unitaires ----------


def test_create_task_rejects_blank_title(client):
    resp = client.post("/api/tasks", json={"title": "   "})
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "title is required"}


def test_create_task_rejects_missing_body(client):
    resp = client.post("/api/tasks")
    assert resp.status_code == 400


def test_health_reports_unreachable_database(client, monkeypatch):
    # Port 1 : personne n'y écoute, la connexion est refusée immédiatement.
    monkeypatch.setenv("DB_HOST", "127.0.0.1")
    monkeypatch.setenv("DB_PORT", "1")
    monkeypatch.setenv("DB_PASSWORD", "sans-importance")
    resp = client.get("/api/health")
    assert resp.status_code == 503
    body = resp.get_json()
    assert body["api"] == "ok"
    assert body["database"].startswith("error")


# ---------- Tests d'intégration ----------


@pytest.mark.integration
def test_health_ok_with_database(client, db):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"api": "ok", "database": "ok"}


@pytest.mark.integration
def test_create_then_list(client, db):
    created = client.post("/api/tasks", json={"title": "écrire les tests"})
    assert created.status_code == 201
    task = created.get_json()
    assert task["title"] == "écrire les tests"
    assert task["done"] is False
    titles = [t["title"] for t in client.get("/api/tasks").get_json()]
    assert titles == ["écrire les tests"]


@pytest.mark.integration
def test_toggle_task(client, db):
    task_id = client.post("/api/tasks", json={"title": "à cocher"}).get_json()["id"]
    assert client.patch(f"/api/tasks/{task_id}").get_json()["done"] is True
    assert client.patch(f"/api/tasks/{task_id}").get_json()["done"] is False


@pytest.mark.integration
def test_delete_unknown_task_returns_404(client, db):
    assert client.delete("/api/tasks/9999").status_code == 404
```

Le troisième test unitaire est instructif : il vérifie que `/api/health` **signale** une base injoignable au lieu de planter, en pointant l'application vers le port 1 où personne n'écoute. `monkeypatch` modifie les variables d'environnement le temps du test seulement, puis les restaure.

### 3.4 Les exécuter sur votre poste

D'abord les tests unitaires, qui n'ont besoin de rien :

```bash
cd ~/Github/edu/listify
python3 -m venv .venv                     # .venv/ est déjà dans le .gitignore
. .venv/bin/activate
pip install -r backend/requirements.txt pytest==8.3.3 ruff==0.6.9
cd backend
ruff check .                              # All checks passed!
pytest -m "not integration"               # 3 passed, 4 deselected
```

Puis la suite complète, avec un PostgreSQL jetable. On le publie sur le port **55432** et non 5432, souvent occupé par un PostgreSQL installé sur le poste :

```bash
podman run -d --rm --name tpdb -p 55432:5432 \
  -e POSTGRES_USER=listify -e POSTGRES_PASSWORD=ci-password -e POSTGRES_DB=listify \
  docker.io/library/postgres:16-alpine
until podman exec tpdb pg_isready -U listify >/dev/null 2>&1; do sleep 1; done; sleep 2

DB_HOST=127.0.0.1 DB_PORT=55432 DB_PASSWORD=ci-password pytest -v     # 7 passed
podman rm -f tpdb
cd ..
```

<details className="controle">
<summary>Point de contrôle n° 2 : sept tests verts</summary>

- `pytest -m "not integration"` : 3 tests passent, sans aucune base.
- La suite complète avec la base jetable : `7 passed`.
- Commitez les trois fichiers (`pytest.ini`, `tests/conftest.py`, `tests/test_api.py`) et poussez vers **les deux** dépôts distants : `git push origin main` et `git push forge main`.

</details>

## Étape 4 : le runner (45 min)

### 4.1 Le socket de Podman

Le runner doit pouvoir créer des conteneurs. Il le fait par l'**API** de Podman, compatible avec celle de Docker, exposée par un socket Unix que systemd active à la demande :

```bash
systemctl --user enable --now podman.socket
ls -l /run/user/$(id -u)/podman/podman.sock          # le socket existe
curl -s --unix-socket /run/user/$(id -u)/podman/podman.sock http://d/_ping; echo    # OK
```

:::danger[Le socket, c'est votre Podman tout entier]
Quiconque peut écrire dans ce socket peut créer, lire et détruire **tous** vos conteneurs, et monter vos fichiers dans l'un d'eux. En le confiant au runner, vous autorisez n'importe quel workflow du dépôt à le faire. C'est acceptable sur votre poste, pour vos propres dépôts ; sur une forge partagée, ce serait une faille grave, et c'est pourquoi les runners d'entreprise isolent les jobs dans des machines virtuelles jetables (ch. 23, §7).
:::

### 4.2 La configuration du runner

Créez un dossier de travail hors de votre dépôt, puis la configuration. Attention : le `EOF` n'est **pas** entre guillemets, pour que `$(id -u)` soit remplacé par votre identifiant d'utilisateur :

```bash
mkdir -p ~/forge
cat > ~/forge/runner-config.yaml <<EOF
# Configuration d'act_runner (générée par « act_runner generate-config », puis réduite)
log:
  level: info

runner:
  file: /data/.runner          # identité du runner, conservée dans le volume
  capacity: 1                  # un job à la fois : le poste de TP est modeste
  timeout: 1h
  labels:
    # « runs-on: ubuntu-latest » => le job s'exécute dans cette image
    - "ubuntu-latest:docker://docker.gitea.com/runner-images:ubuntu-latest"

cache:
  enabled: false               # pas de serveur de cache (voir le bonus)

container:
  network: ""                  # un réseau neuf par job : les « services » y sont joignables par leur nom
  force_pull: false            # ne pas retélécharger l'image du job à chaque exécution
  valid_volumes:               # liste blanche : tout montage doit y figurer
    - /run/user/$(id -u)/podman/podman.sock
  # Les jobs pilotent le Podman de l'hôte (docker build, docker push, au TP 20) :
  # on monte le socket Podman DE L'UTILISATEUR, avec son chemin réel sur l'hôte.
  docker_host: "-"             # « - » : ne pas monter automatiquement un socket deviné
  options: "-v /run/user/$(id -u)/podman/podman.sock:/var/run/docker.sock"
EOF
grep podman.sock ~/forge/runner-config.yaml       # vérifiez : votre UID apparaît, pas « $(id -u) »
```

Les quatre dernières lignes ne servent qu'au TP 20, mais on les met en place dès maintenant pour ne plus toucher au runner. Elles méritent d'être comprises, parce qu'elles corrigent deux pièges constatés en préparant ce TP :

- Par défaut, act_runner monte dans les jobs le socket **tel qu'il le voit dans son propre conteneur** (`/var/run/docker.sock`). Mais c'est le Podman de l'**hôte** qui interprète ce chemin, et sur l'hôte il ne désigne pas votre socket : il n'existe pas, ou pire, il désigne le socket d'un démon Docker installé à côté, réservé à root (`permission denied`). D'où `docker_host: "-"` et le montage explicite du **vrai** chemin par `options`.
- Un montage demandé par `options` est **ignoré en silence** s'il ne figure pas dans la liste blanche `valid_volumes`. Le job démarre alors sans socket, et échoue plus loin sur `no such file or directory`.

### 4.3 Enregistrer et démarrer le runner

Un runner s'enregistre auprès de la forge avec un **jeton d'enregistrement** à usage unique, qu'on obtient dans l'interface (Administration du site, Actions, Runners, « Créer un nouveau runner ») ou en ligne de commande :

```bash
TOKEN=$(podman exec -u git gitea gitea actions generate-runner-token | tail -1)

podman volume create runner-data
podman run -d --name act-runner \
  -e GITEA_INSTANCE_URL=http://host.containers.internal:3300 \
  -e GITEA_RUNNER_REGISTRATION_TOKEN=$TOKEN \
  -e GITEA_RUNNER_NAME=poste-etudiant \
  -e CONFIG_FILE=/config.yaml \
  -v ~/forge/runner-config.yaml:/config.yaml:Z,ro \
  -v runner-data:/data \
  -v /run/user/$(id -u)/podman/podman.sock:/var/run/docker.sock \
  docker.io/gitea/act_runner:0.6.1

podman logs act-runner | tail -3
# ... Runner registered successfully.
# ... runner: poste-etudiant, with version: v0.6.1, with labels: [ubuntu-latest], declare successfully
```

Notez que le runner, lui aussi dans un conteneur, joint Gitea par `host.containers.internal` et non par `localhost`. Dans l'interface (Administration du site, Actions, Runners), `poste-etudiant` apparaît avec l'état **En ligne**.

:::warning[`act_runner generate-config` ne rend pas la main ?]
Si vous voulez voir la configuration complète par défaut, n'écrivez pas `podman run --rm docker.io/gitea/act_runner:0.6.1 act_runner generate-config` : le script d'entrée de l'image ignore la commande et lance le runner, qui attend indéfiniment un enregistrement. Il faut remplacer le point d'entrée : `podman run --rm --entrypoint act_runner docker.io/gitea/act_runner:0.6.1 generate-config`.
:::

## Étape 5 : le premier pipeline (45 min)

Créez le workflow du chapitre 23, complété par une sonde de santé sur le service de base de données :

```yaml title=".gitea/workflows/ci.yaml"
name: ci

on:
  push:
    branches: [main]
  pull_request:

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install ruff==0.6.9
      - run: ruff check backend/

  tests:
    runs-on: ubuntu-latest
    needs: lint                    # inutile de tester un code qui ne passe pas le lint
    services:
      db:                          # un PostgreSQL jetable, le temps du job
        image: postgres:16-alpine
        env:
          POSTGRES_USER: listify
          POSTGRES_PASSWORD: ci-password
          POSTGRES_DB: listify
        options: >-              # le job attend que la base réponde avant de démarrer
          --health-cmd "pg_isready -U listify"
          --health-interval 2s
          --health-timeout 5s
          --health-retries 15
    env:
      DB_HOST: db                  # le service est joignable par son nom
      DB_PASSWORD: ci-password
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r backend/requirements.txt pytest==8.3.3
      - run: pytest -v backend
```

```bash
git add .gitea/workflows/ci.yaml
git commit -m "CI : lint et tests"
git push forge main
```

Dans l'interface, ouvrez l'onglet **Actions** du dépôt : une exécution « CI : lint et tests » apparaît, avec ses deux jobs. Cliquez sur un job pour suivre son journal en direct. Vous y lirez, dans l'ordre : le démarrage du conteneur du job, le clone du dépôt depuis `http://host.containers.internal:3300/etudiant/listify`, l'installation de Python 3.12, puis les commandes du workflow. Pour le job `tests`, le service `db` démarre d'abord ; le job ne commence qu'une fois la sonde `pg_isready` réussie.

Temps mesurés lors de la validation du TP, image de job déjà téléchargée : environ 3 minutes par job, dont l'essentiel en téléchargements (actions depuis github.com, paquets pip). Sur une bonne connexion, c'est nettement moins. **Sans** le téléchargement préalable de l'étape 0, le premier job attend en plus l'image de 1,66 Go : comptez plus de dix minutes.

<details className="controle">
<summary>Point de contrôle n° 3 : le pipeline est vert</summary>

- Les deux jobs sont verts ; `tests` n'a démarré qu'après `lint` (c'est l'effet de `needs`).
- Le journal de `tests` montre `7 passed` : les tests d'intégration ont tourné contre le PostgreSQL du service, joint par le nom `db`.
- Au runbook : la durée de chaque job, et la liste des étapes lues dans le journal.

</details>

## Étape 6 : casser, observer, réparer (30 min)

Un pipeline n'a de valeur que s'il **échoue** quand il le doit. Introduisez une faute que le lint doit attraper : ajoutez une ligne `import sys` inutilisée en tête de `backend/app.py`, puis :

```bash
git commit -am "Import inutile (panne volontaire)"
git push forge main
```

Résultat attendu, vérifié lors de la préparation : le job `lint` échoue sur

```text
backend/app.py:3:8: F401 [*] `sys` imported but unused
Found 1 error.
```

et le job `tests` est marqué **ignoré** (*skipped*) : il n'a même pas démarré. C'est l'ordre du chapitre 23, §5.2, vu en vrai : l'échec le moins cher arrête la chaîne avant les étapes coûteuses.

Réparez comme on le fait dans une équipe, par une **annulation** tracée plutôt que par une correction discrète :

```bash
git revert --no-edit HEAD
git push forge main          # nouvelle exécution, entièrement verte
```

À vous ensuite : cassez un **test**, par exemple en faisant renvoyer `422` au lieu de `400` pour un titre vide dans `create_task`. Le lint passe, les tests échouent : notez au runbook comment le journal désigne le test fautif et la valeur obtenue, puis annulez.

## Étape 7 : fin de séance (10 min)

**Gardez la forge et le runner** : le TP 20 les réutilise tels quels. Pour libérer la mémoire entre deux séances, arrêtez-les simplement ; leurs données sont dans des volumes :

```bash
podman stop act-runner gitea          # en fin de séance
podman start gitea act-runner         # à la séance suivante (le socket reste activé)
```

Complétez le runbook : les commandes de lancement de Gitea et du runner, la configuration du runner commentée, et les trois pièges rencontrés (ou lus) avec leur symptôme.

## Point de contrôle final

- [ ] Gitea répond sur `localhost:3300`, le dépôt `listify` y est poussé
- [ ] Le runner `poste-etudiant` est « En ligne »
- [ ] Les tests : 3 unitaires et 4 d'intégration, verts en local et dans le pipeline
- [ ] Le workflow `ci.yaml` (lint puis tests) est vert sur `main`
- [ ] Un pipeline rouge provoqué, lu, puis réparé par `git revert`
- [ ] Runbook à jour

<details className="enseignant">
<summary>Banque de pannes du TP 19 (réservé enseignant : ne lisez pas si vous jouez le jeu)</summary>

Colonne « Origine » : **vécue** signifie rencontrée lors de la validation du TP ; **prévisible** signifie déduite de l'architecture et évitée par construction dans l'énoncé (c'est ce qu'un étudiant obtient s'il s'en écarte).

| Symptôme | Cause | Remède | Origine |
|---|---|---|---|
| Le premier job reste des minutes sur « Downloading » | L'image de job (1,66 Go) n'était pas téléchargée | Étape 0 ; ou patienter, le téléchargement n'a lieu qu'une fois | vécue |
| `podman run ... act_runner generate-config` ne rend jamais la main | Le script d'entrée de l'image ignore la commande | `--entrypoint act_runner` (encadré de l'étape 4.3) | vécue |
| Le runner ne s'enregistre pas : `connection refused` | `GITEA_INSTANCE_URL=http://localhost:3300` : dans le conteneur du runner, `localhost` est le runner | Utiliser `host.containers.internal:3300` | prévisible |
| Le job échoue au clone : impossible de joindre l'hôte | `ROOT_URL` de Gitea laissé à `http://localhost:3300/` | `ROOT_URL=http://host.containers.internal:3300/` avec `PUBLIC_URL_DETECTION=auto` | prévisible |
| Après un push, **aucune** exécution n'apparaît dans Actions | Le workflow est un YAML invalide ; Gitea l'ignore sans message. Cas vécu : un nom d'étape contenant « `: ` » (`name: Construire (--pull : image à jour)`) | Valider le YAML (`python3 -c "import yaml; yaml.safe_load(open('.gitea/workflows/ci.yaml'))"`), mettre la valeur entre guillemets | vécue |
| `ModuleNotFoundError: No module named 'app'` dans pytest | `pytest.ini` absent ou mal placé | `backend/pytest.ini` avec `pythonpath = .` | prévisible |
| Tests d'intégration en erreur de connexion, de façon intermittente | Le service `db` n'était pas encore prêt | Les `options` de sonde de santé du service | prévisible |
| Le PostgreSQL de test local ne démarre pas : `address already in use` | Un PostgreSQL du poste occupe 5432 | Publier sur 55432, comme dans le TP | vécue (port 5432 occupé sur le poste de validation) |

Panne à injecter en temps limité : supprimer la ligne `needs: lint` et demander d'expliquer pourquoi les deux jobs démarrent désormais ensemble, et ce que cela change à la durée et au coût du pipeline.

</details>

## Pour aller plus loin (bonus)

1. **Protéger `main`.** Dans les paramètres du dépôt, créez une règle de protection de branche qui exige le succès du workflow avant toute fusion, puis travaillez par pull request depuis une branche. Vous obtenez la discipline du trunk-based development (ch. 24, §5) : le tronc ne peut plus devenir rouge.
2. **Le cache.** Activez le serveur de cache d'act_runner et l'option `cache: pip` de `setup-python`. Mesurez le gain sur la durée des jobs. Attention : le cache doit être joignable depuis les conteneurs des jobs, ce qui repose le problème des points de vue réseau.
3. **Paralléliser.** Séparez tests unitaires et tests d'intégration en deux jobs (`pytest -m "not integration"` et `pytest -m integration`), et faites dépendre du lint le premier seulement. Qu'y gagne-t-on ? Que faudrait-il pour que les deux s'exécutent vraiment en même temps (indice : `capacity`) ?

## Questions de compréhension (à préparer pour le TD et l'examen)

1. Pourquoi le runner et les jobs joignent-ils Gitea par `host.containers.internal`, alors que vous utilisez `localhost` ? Qu'est-ce que `localhost` désigne dans un conteneur ?
2. Le job `tests` a été marqué « ignoré » quand le lint a échoué. Justifiez ce comportement par un calcul de durée moyenne, comme au chapitre 23, §5.2.
3. Le mot de passe `ci-password` figure en clair dans le workflow. Pourquoi est-ce acceptable ici, et dans quel cas ne le serait-ce plus ?
4. Monter le socket de Podman dans les jobs revient à leur donner les pleins pouvoirs sur votre moteur de conteneurs. Proposez deux mesures qui réduiraient ce risque sur une forge partagée par plusieurs équipes.
5. Relancer un pipeline rouge « pour voir » et obtenir du vert : qu'avez-vous appris, et que devez-vous faire ensuite (ch. 23, §7) ?
