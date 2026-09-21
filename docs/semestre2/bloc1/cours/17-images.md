---
title: "Ch. 17 : Les images de conteneurs"
sidebar_label: "Ch. 17 : Les images de conteneurs"
hide_title: true
---

import ChapterHead from '@site/src/components/ChapterHead';
import Figure from '@site/src/components/Figure';

<ChapterHead
  kicker="Semestre 2 · Bloc 1 · Chapitre 17"
  title="Les images de conteneurs"
  lecture="10 min"
/>

:::objectifs
À l'issue de ce chapitre, vous saurez :

- lire et écrire un `Containerfile` (syntaxe Dockerfile) et expliquer comment chaque instruction crée une couche ;
- exploiter le **cache de build** en ordonnant les instructions, et expliquer l'invalidation de cache ;
- concevoir une image **multi-stage** pour séparer la construction de l'exécution ;
- appliquer les bonnes pratiques de taille et de sécurité (utilisateur non-root, image de base minimale, scan de vulnérabilités).

Ce chapitre outille les [TP 12](../tp/tp12-images-containerfile.md) et [TP 14](../tp/tp14-registre-scan.md), où vous construirez et scannerez les images de Listify.
:::

## 1. Le Containerfile : une recette qui produit un artefact

Une image se construit à partir d'un fichier texte, le **Containerfile** (la syntaxe est celle du Dockerfile ; le nom `Containerfile` est le terme neutre OCI, Podman lit les deux). Chaque **instruction** produit une **couche** (ch. 15) empilée sur la précédente. Exemple minimal pour le backend Listify :

```dockerfile title="backend/Containerfile (version naïve, à améliorer)"
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "wsgi:app"]
```

Les instructions essentielles, à connaître :

| Instruction | Rôle |
|---|---|
| `FROM` | L'image de base (le premier lowerdir). Point de départ obligatoire |
| `WORKDIR` | Le répertoire de travail dans l'image |
| `COPY` / `ADD` | Copier des fichiers de l'hôte (contexte de build) vers l'image |
| `RUN` | Exécuter une commande **au moment du build** (installer des paquets...) |
| `ENV` | Définir une variable d'environnement persistante |
| `EXPOSE` | Documenter le port écouté (informatif) |
| `USER` | L'utilisateur sous lequel s'exécutera le conteneur |
| `CMD` / `ENTRYPOINT` | La commande lancée **au démarrage** du conteneur |

:::note[`RUN` vs `CMD` : le piège fondamental]
`RUN` s'exécute **pendant la construction** de l'image (et fige son résultat dans une couche). `CMD` définit ce qui s'exécutera **au lancement** du conteneur. Confondre les deux est l'erreur n° 1 des débutants. Règle : tout ce qui prépare l'environnement (installer, compiler) est un `RUN` ; l'unique processus applicatif est un `CMD`.
:::

### 1.1 Build et exécution

```bash
podman build -t listify-backend:1.0 ./backend      # construire l'image (lit le Containerfile)
podman run --rm -p 8000:8000 listify-backend:1.0    # lancer un conteneur depuis l'image
podman image inspect listify-backend:1.0            # voir les couches, la config, le digest
```

Le point qui rejoint tout le parcours : cette image est un **artefact immuable**. Construite une fois, elle contient l'application et son environnement figés. Le conteneur lancé sur votre poste, dans la CI (bloc 3) et en production est **le même artefact**, identifié par le même digest. Le « ça marche sur ma machine » du chapitre 14 disparaît, non par discipline, mais par construction.

## 2. Le cache de build : pourquoi l'ordre des instructions compte

À chaque `build`, le moteur réutilise les couches déjà construites tant que **rien n'a changé** en amont. Dès qu'une instruction change (ou qu'un fichier qu'elle copie change), cette couche **et toutes les suivantes** sont reconstruites : le cache est invalidé en cascade.

De là, une règle d'or : **placer ce qui change rarement avant ce qui change souvent.** Comparez la version naïve ci-dessus (correcte) à sa logique optimisée :

```dockerfile
# BIEN : les dépendances (rarement modifiées) sont installées AVANT de copier le code
COPY requirements.txt .
RUN pip install -r requirements.txt   # cette couche est réutilisée tant que requirements.txt ne change pas
COPY . .                              # seul le changement de code invalide À PARTIR d'ici
```

```dockerfile
# MAL : tout le code copié avant l'installation
COPY . .                              # le moindre changement de code...
RUN pip install -r requirements.txt   # ...force à réinstaller TOUTES les dépendances
```

Dans le premier cas, modifier une ligne de `app.py` reconstruit une couche en une seconde ; dans le second, cela réinstalle Flask, Gunicorn et psycopg2 à chaque fois. Sur des projets réels (des centaines de dépendances), l'écart se compte en minutes à chaque build, donc à chaque itération de CI. **L'ordre des couches est une décision de performance**, directement issue du copy-on-write du chapitre 15.

:::tip[Le fichier `.containerignore`]
Comme `.gitignore`, un `.containerignore` exclut du **contexte de build** ce qui n'a rien à y faire (`.git/`, `.venv/`, `__pycache__/`, les tests...). Cela réduit ce qui est envoyé au moteur, accélère le build, et évite d'invalider le cache pour un fichier non pertinent. À fournir dès le TP 12.
:::

## 3. Les images multi-stage : construire ici, exécuter là

### 3.1 Le problème

Beaucoup d'applications ont besoin d'**outils de construction** (compilateurs, `node`+`npm`, en-têtes de développement) qui sont **inutiles et dangereux à l'exécution** : ils gonflent l'image (des centaines de Mo) et augmentent la surface d'attaque (plus d'outils = plus de failles potentielles). Le frontend de Listify au S2 en est l'exemple parfait : il faut Node.js pour *construire* les fichiers statiques, mais l'image finale ne doit contenir que Nginx et les fichiers produits.

### 3.2 La solution : plusieurs étapes, une seule conservée

Un **build multi-stage** définit plusieurs `FROM` dans un même Containerfile. Chaque `FROM` ouvre une **étape** ; on **copie sélectivement** le résultat d'une étape vers la suivante, et **seule la dernière étape** devient l'image finale. Tout le reste (les outils de build) est jeté.

```dockerfile title="frontend/Containerfile (multi-stage)"
# --- Étape 1 : build (avec Node, lourd) ---
FROM node:20-slim AS build
WORKDIR /src
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build          # produit /src/dist (les fichiers statiques)

# --- Étape 2 : runtime (Nginx seul, léger) ---
FROM nginx:1.27-alpine
COPY --from=build /src/dist /usr/share/nginx/html   # on ne prend QUE le résultat
```

<Figure src="multi-stage" num="17.1" alt="Une étape de build basée sur node produit le dossier dist ; seule cette sortie est copiée dans l'étape finale basée sur nginx, qui donne une image légère sans outils de build.">
  Construction multi-étapes. L'étape de build, avec ses centaines de Mo d'outillage, est jetée ; l'image livrée ne contient que le résultat.
</Figure>

L'image finale ne contient **ni Node, ni npm, ni le code source**, seulement Nginx et les fichiers produits : plus petite, plus sûre, plus rapide à distribuer. Le multi-stage est la technique la plus rentable de tout le chapitre, et une question d'examen quasi certaine.

## 4. Bonnes pratiques : taille et sécurité

### 4.1 La taille

Une image plus petite se télécharge plus vite (donc déploie et *scale* plus vite au bloc 2), consomme moins de disque et de bande passante, et expose moins. Les leviers :

- **Une image de base minimale** : `python:3.12-slim` (≈ 50 Mo) plutôt que `python:3.12` (≈ 350 Mo) ; `alpine` (≈ 5 Mo, mais bibliothèque C `musl` au lieu de `glibc`, parfois source d'incompatibilités : à connaître) ; et à l'extrême, les images `distroless` de Google (aucun shell, aucun gestionnaire de paquets).
- **Le multi-stage** (section 3).
- **Regrouper les `RUN`** et nettoyer dans la même couche : `RUN apt-get update && apt-get install -y X && rm -rf /var/lib/apt/lists/*`. Nettoyer dans une couche *ultérieure* ne réduit rien (la couche précédente garde les fichiers : conséquence directe de l'empilement du ch. 15).

### 4.2 La sécurité : l'utilisateur non-root

Par défaut, le processus d'un conteneur tourne en **root** (dans le namespace du conteneur). Même si le rootless de Podman en limite la portée (ch. 15-16), la bonne pratique universelle est de **créer et utiliser un utilisateur non privilégié** dans l'image, avec l'instruction `USER`. C'est le principe du moindre privilège du S1, appliqué à l'image :

```dockerfile
RUN useradd --system --no-create-home listify
USER listify
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "wsgi:app"]
```

En rootless, c'est presque « gratuit » à mettre en place et cela ferme une classe entière de problèmes. Kubernetes, au bloc 2, permettra même d'*interdire* au niveau du cluster les conteneurs tournant en root.

### 4.3 Le scan de vulnérabilités

Une image agrège des dizaines de bibliothèques, chacune susceptible d'avoir des vulnérabilités connues (des **CVE**). Un **scanner** comme **Trivy** compare les paquets de l'image à des bases de données publiques de CVE et signale les failles, avec leur gravité :

```bash
trivy image listify-backend:1.0
# liste les CVE par gravité (LOW/MEDIUM/HIGH/CRITICAL), avec versions corrigées
```

Le réflexe professionnel, que vous adopterez au TP 14 : **scanner dans le pipeline de CI** (bloc 3) et refuser de déployer une image porteuse de failles critiques. C'est la face « sécurité de la chaîne d'approvisionnement logicielle » (*supply chain security*), un sujet brûlant depuis les attaques SolarWinds (2020) et Log4Shell (2021). Un scan ne rend pas une image sûre, mais une image jamais scannée est un pari aveugle.

:::note[Buildah et les alternatives de construction]
Podman délègue en réalité la construction à **Buildah**, un outil dédié qui sait construire des images *sans* Containerfile (par script) et *sans privilèges*. Vous n'en aurez pas besoin directement (Podman l'appelle pour vous), mais sachez qu'il existe : construire une image et exécuter un conteneur sont deux métiers séparés dans le monde rootless.
:::

## Ce qu'il faut retenir

<div className="retenir">

1. Un **Containerfile** décrit la construction d'une image ; **chaque instruction crée une couche**. `RUN` s'exécute au **build**, `CMD` au **lancement** : ne jamais confondre.
2. Le **cache de build** réutilise les couches inchangées et invalide tout **à partir** du premier changement : placer les dépendances (stables) **avant** le code (volatil). `.containerignore` allège le contexte.
3. Les images **multi-stage** séparent construction (outils lourds, jetés) et exécution (image finale minimale) via plusieurs `FROM` et `COPY --from=`. Technique la plus rentable.
4. Sécurité et taille : **image de base minimale** (slim/alpine/distroless), `RUN` regroupés et nettoyés dans la même couche, **utilisateur non-root** (`USER`), **scan Trivy** des CVE (supply chain).
5. L'image est l'**artefact immuable** identifié par son digest : le même du poste à la production. C'est la fin structurelle du « ça marche sur ma machine ».

</div>

## Regard recherche

:::recherche
- **Rui Shu, Xiaohui Gu, William Enck, « A Study of Security Vulnerabilities on Docker Hub », ACM CODASPY, 2017.** Une analyse empirique à grande échelle des vulnérabilités dans les images publiques de Docker Hub. Édifiant : la majorité des images, y compris officielles, portent des CVE. C'est *la* justification chiffrée du scan, et un modèle d'étude de sécurité empirique reproductible.
- **Sur la reproductibilité des builds** : le projet **Reproducible Builds** ([reproducible-builds.org](https://reproducible-builds.org/)) et la littérature associée posent une question de recherche profonde : deux constructions du même code produisent-elles le *même* binaire, au bit près ? Les images de conteneurs, malgré leur digest, ne sont pas toujours reproductibles (horodatages, ordre de fichiers). Un excellent sujet d'exploration.
- **Supply chain security** : cherchez les travaux autour de **SLSA** (Supply-chain Levels for Software Artifacts, Google/OpenSSF) et **Sigstore** (signature d'artefacts). Après SolarWinds, sécuriser la *provenance* des images est un domaine de recherche et d'ingénierie en pleine expansion.
:::

## Bibliographie du chapitre

<div className="biblio">

### Sources primaires

- Documentation Docker/Podman, référence du Dockerfile/Containerfile : [docs.docker.com/reference/dockerfile](https://docs.docker.com/reference/dockerfile/). La liste normative des instructions.
- Documentation Buildah : [buildah.io](https://buildah.io/).
- Documentation Trivy : [trivy.dev](https://trivy.dev/) (installation, scan d'images, intégration CI).

### Lectures recommandées

- « Best practices for writing Dockerfiles », documentation Docker : la synthèse officielle des bonnes pratiques de ce chapitre.
- Google, « Distroless container images » ([github.com/GoogleContainerTools/distroless](https://github.com/GoogleContainerTools/distroless)) : le README explique la philosophie « le moins possible dans l'image ».

### Pour aller plus loin

- L'outil `dive` : explorer une image couche par couche pour traquer le gaspillage d'espace ; très instructif après le TP 12.
- Chainguard Images et les images « zero-CVE » : l'état de l'art actuel des images minimales et durcies ; comparez leur approche à `distroless`.

</div>
