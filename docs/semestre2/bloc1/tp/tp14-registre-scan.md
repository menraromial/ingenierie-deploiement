# TP 14 : Registre local, scan de vulnérabilités et service systemd

!!! abstract "Fiche du TP"
    - **Durée** : 4 h
    - **Prérequis** : TP 12 et 13 (images construites, composition maîtrisée) ; chapitres 16 et 17
    - **Livrables** : un registre local fonctionnel avec les images poussées ; un rapport Trivy et la correction d'une image ; un service utilisateur systemd via Quadlet ; runbook
    - **Compétences travaillées** : C3, C6

    Vous complétez la chaîne : **distribuer** les images (registre), les **sécuriser** (scan Trivy), et les **superviser** (Quadlet + systemd, la boucle avec le S1). Commandes validées sous Podman 5.

## Étape 1 : monter un registre local (1 h)

### 1.1 Le registre en un conteneur

Un **registre** est le serveur qui stocke et distribue les images (la *distribution spec* de l'OCI, ch. 16 §2). En entreprise, c'est Harbor, GitLab Registry, ou le registre d'un cloud. En local, l'image officielle `registry:2` suffit :

```bash
podman run -d --name registry -p 5000:5000 docker.io/library/registry:2
```

!!! warning "Si le port 5000 est déjà pris"
    `Address already in use` : un autre service occupe le 5000 (fréquent). Utilisez un autre port, par exemple `-p 5001:5000`, et adaptez les commandes suivantes (`localhost:5001`). Savoir diagnostiquer un port occupé (`ss -tlnp | grep 5000`) est un réflexe du S1 qui resert ici.

### 1.2 Pousser et tirer

Le cycle **tag → push → pull**, le vocabulaire de la distribution d'images :

```bash
# 1. Taguer l'image avec l'adresse du registre
podman tag listify-backend:1.0 localhost:5000/listify-backend:1.0

# 2. Pousser (--tls-verify=false : notre registre local est en HTTP, sans TLS)
podman push --tls-verify=false localhost:5000/listify-backend:1.0

# 3. Interroger le registre par son API HTTP (la distribution spec en action)
curl -s http://localhost:5000/v2/_catalog
# {"repositories":["listify-backend"]}
curl -s http://localhost:5000/v2/listify-backend/tags/list
# {"name":"listify-backend","tags":["1.0"]}

# 4. Tirer (après avoir supprimé la copie locale, pour prouver que ça vient du registre)
podman rmi localhost:5000/listify-backend:1.0
podman pull --tls-verify=false localhost:5000/listify-backend:1.0
```

Consignez la sortie de `_catalog` et `tags/list` : vous parlez directement à l'API du registre, sans passer par le moteur. C'est la *distribution spec* de l'OCI, celle que le pipeline de CI/CD du bloc 3 utilisera pour publier les images automatiquement.

??? question "Point de contrôle n° 1 : le digest, identité immuable"
    ```bash
    podman image inspect localhost:5000/listify-backend:1.0 --format '{{.Digest}}'
    ```

    Notez ce `sha256:...`. C'est l'**empreinte immuable** de l'image (ch. 16 §2) : deux images de même digest sont bit à bit identiques. Le tag `1.0` peut être réaffecté ; le digest, jamais. En production, on déploie souvent par digest pour une reproductibilité absolue. Poussez la **même** image sous un second tag (`:latest`) et vérifiez que le digest est **identique** : le contenu n'a pas changé, seul le nom.

## Étape 2 : scanner les vulnérabilités avec Trivy (1 h 30)

### 2.1 Installer Trivy et scanner

**Trivy** compare les paquets d'une image aux bases publiques de CVE (ch. 17 §4.3). Installation (sans droits admin, via le binaire, ou selon le guide du poste) :

```bash
# Voie simple : le binaire officiel dans ~/.local/bin (à adapter au guide du poste)
mkdir -p ~/.local/bin
curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh \
  | sh -s -- -b ~/.local/bin
export PATH="$HOME/.local/bin:$PATH"
trivy --version
```

Scannez votre image backend. En **rootless sans démon**, Trivy ne peut pas « voir » les images de Podman directement (il cherche un socket Docker/Podman absent, d'où l'erreur `no podman socket found`). La méthode la plus fiable, et la plus fidèle à l'esprit du cours, est d'**exporter l'image en archive** et de scanner l'archive :

```bash
podman save -o /tmp/listify-backend.tar listify-backend:1.0
trivy image --input /tmp/listify-backend.tar
```

Lisez le rapport : chaque vulnérabilité est listée avec son identifiant **CVE**, le paquet touché, la **gravité** (LOW / MEDIUM / HIGH / CRITICAL) et, quand elle existe, la **version corrigée**. Concentrez-vous sur les HIGH et CRITICAL :

```bash
trivy image --severity HIGH,CRITICAL --input /tmp/listify-backend.tar
```

!!! tip "Alternative : le socket Podman (comme en CI)"
    Plutôt que l'archive, on peut activer le socket Podman et laisser Trivy interroger le moteur, exactement comme le fera un runner de CI au bloc 3 :

    ```bash
    systemctl --user enable --now podman.socket
    export DOCKER_HOST="unix://$XDG_RUNTIME_DIR/podman/podman.sock"
    trivy image localhost/listify-backend:1.0     # nom complet : voir `podman images`
    ```

    Les deux méthodes donnent le même rapport. L'archive (`--input`) est plus simple et sans dépendance ; le socket prépare l'intégration en pipeline.

### 2.2 Corriger une image vulnérable

L'exercice qui fait comprendre le cycle. La plupart des vulnérabilités viennent de l'**image de base** (ici `python:3.12-slim`) : la corriger, c'est souvent la **reconstruire sur une base à jour**.

```bash
# 1. Mettre à jour la base et reconstruire
podman pull docker.io/library/python:3.12-slim      # récupère la dernière révision
podman build -t listify-backend:1.1 ./backend
# 2. Re-scanner (même méthode par archive) : le nombre de CVE a-t-il baissé ?
podman save -o /tmp/listify-backend-1.1.tar listify-backend:1.1
trivy image --severity HIGH,CRITICAL --input /tmp/listify-backend-1.1.tar
```

Consignez le nombre de CVE HIGH/CRITICAL **avant** et **après**. Discussion à mener au runbook : une image n'est jamais « sûre » définitivement (de nouvelles CVE sont publiées chaque jour) ; ce qui compte, c'est de **scanner régulièrement** et de **reconstruire** quand la base est corrigée. C'est pourquoi le scan sera **automatisé dans le pipeline de CI** au bloc 3 : un humain ne peut pas suivre ce rythme.

!!! note "Ce qu'un scan ne dit pas"
    Trivy détecte les CVE **connues** des paquets installés. Il ne détecte pas les failles de *votre* code, ni les erreurs de configuration, ni les CVE non encore publiées (*zero-day*). C'est une couche de défense, pas une garantie. Un ingénieur honnête connaît les limites de ses outils (esprit du S1, chapitre 5).

## Étape 3 : superviser un conteneur avec systemd (Quadlet) (1 h)

### 3.1 La boucle avec le S1

Podman n'a pas de démon (ch. 16 §4.2) : qui garantit alors qu'un conteneur redémarre au boot et après un crash ? **systemd**, exactement comme au S1. La méthode moderne est **Quadlet** : un fichier `.container` que systemd transforme en service.

Créez le fichier (en mode utilisateur, sans droits admin) :

```ini title="~/.config/containers/systemd/listify-backend.container"
[Unit]
Description=Listify backend (conteneurisé)

[Container]
Image=localhost/listify-backend:1.0
PublishPort=8001:8000
Environment=DB_HOST=host.containers.internal
Environment=DB_PASSWORD=secret

[Service]
Restart=on-failure

[Install]
WantedBy=default.target
```

Rechargez systemd (utilisateur) et démarrez le service :

```bash
systemctl --user daemon-reload
systemctl --user start listify-backend.service
systemctl --user status listify-backend.service      # doit être active (running)
```

!!! warning "Le service échoue avec `status=126` et `Address already in use` ?"
    C'est un **conflit de port** : le `PublishPort` (8001 ici) est déjà occupé sur votre poste (un autre conteneur, un serveur de dev, `mkdocs serve`...). Vérifiez avec `ss -tlnp | grep 8001` et changez le port publié dans le fichier `.container` si besoin. Piège associé : après plusieurs échecs rapides, systemd refuse de redémarrer (`Start request repeated too quickly`) ; il faut alors **effacer l'état d'échec** avant de réessayer :

    ```bash
    systemctl --user reset-failed listify-backend.service
    systemctl --user daemon-reload
    systemctl --user start listify-backend.service
    ```

    Rappel du journal, votre meilleur allié : `journalctl --user -u listify-backend.service -n 20` donne le message exact de `podman` (ici, `pasta: Listen failed ... Address already in use`).

Vous **retrouvez mot pour mot** le chapitre 2 du S1 : `Restart=on-failure`, `systemctl status`, `WantedBy=`. La différence ? Ce n'est plus Gunicorn dans un venv, c'est un **conteneur**. L'unité de déploiement a changé ; l'outil de supervision est le même. La boucle S1 → S2 est bouclée.

### 3.2 Éprouver l'auto-réparation

```bash
# Tuer le conteneur : systemd doit le relancer (Restart=on-failure)
podman rm -f systemd-listify-backend 2>/dev/null || \
  systemctl --user status listify-backend.service   # voir le nom exact du conteneur géré
# Observer la relance dans le journal utilisateur :
journalctl --user -u listify-backend.service -n 20
```

C'est l'auto-réparation du S1 (systemd relance un service mort), appliquée à un conteneur. Au bloc 2, Kubernetes généralisera cette idée à l'échelle d'un cluster : même concept, autre portée. Vous avez maintenant vu la progression complète : master Gunicorn → systemd → (bientôt) contrôleur Kubernetes.

### 3.3 Nettoyage

```bash
systemctl --user stop listify-backend.service
rm ~/.config/containers/systemd/listify-backend.container
systemctl --user daemon-reload
podman rm -f registry
```

## Point de contrôle final

- [ ] Registre local fonctionnel : push, `_catalog`/`tags/list` interrogés, pull prouvé
- [ ] Digest noté ; second tag de même digest (immutabilité comprise)
- [ ] Scan Trivy réalisé ; nombre de CVE HIGH/CRITICAL avant/après reconstruction consigné
- [ ] Limites du scan comprises et notées
- [ ] Service systemd (Quadlet) démarré ; auto-réparation observée dans le journal
- [ ] Le parallèle explicite avec le S1 (systemd, `Restart=`) rédigé au runbook

## Pour aller plus loin (bonus)

1. **Registre avec authentification** : configurez le registre `registry:2` avec un fichier `htpasswd` et exigez un `podman login`. Quelle partie de la *distribution spec* gère l'authentification ?
2. **Trivy en config** : `trivy config ./backend/Containerfile` : Trivy sait aussi auditer un Containerfile (mauvaises pratiques : root, absence de version épinglée...). Que trouve-t-il sur le vôtre ?
3. **Quadlet complet** : écrivez les trois `.container` (db, backend, frontend) + un `.network`, pour lancer **tout** Listify via systemd utilisateur. Comparez à `compose.yaml` : quand préférer l'un ou l'autre ?

## Questions de compréhension (à préparer pour le TD et l'examen)

1. Décrivez le cycle complet d'une image, du `build` au `run` en production, en nommant à chaque étape la spécification OCI mobilisée (image, distribution, runtime).
2. Pourquoi le scan de vulnérabilités doit-il être **répété** et **automatisé**, plutôt que fait une fois à la main ? Reliez à la nature mouvante des CVE et au pipeline de CI du bloc 3.
3. Expliquez pourquoi superviser un conteneur avec systemd est *possible* avec Podman mais pas naturel avec Docker. (Indice : le démon.)
4. Un conteneur supervisé par systemd (`Restart=on-failure`) et un Pod supervisé par Kubernetes réalisent la même idée. Laquelle, et quelle est la différence de **portée** entre les deux ? (Une machine vs un cluster.)
