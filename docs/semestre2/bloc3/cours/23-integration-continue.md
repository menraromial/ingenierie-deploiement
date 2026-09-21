---
title: "Ch. 23 : L'intégration continue"
sidebar_label: "Ch. 23 : L'intégration continue"
hide_title: true
---

import ChapterHead from '@site/src/components/ChapterHead';
import Figure from '@site/src/components/Figure';

<ChapterHead
  kicker="Semestre 2 · Bloc 3 · Chapitre 23"
  title="L'intégration continue"
  lecture="35 min"
  competences={['C2', 'C4']}
/>

:::objectifs
À l'issue de ce chapitre, vous saurez :

- expliquer pourquoi l'intégration tardive coûte cher, et pourquoi l'intégrer souvent la rend presque gratuite ;
- définir rigoureusement l'intégration continue et énumérer les pratiques sans lesquelles elle n'existe pas ;
- concevoir un pipeline dont l'ordre des étapes minimise le temps de retour vers le développeur, en le justifiant par un calcul ;
- lire et écrire un workflow au format GitHub Actions, exécutable par la forge Gitea du TP 19 ;
- reconnaître les pathologies classiques d'une CI (build lent, tests instables, build cassé toléré) et leurs remèdes.
:::

## 1. Le problème : l'enfer de l'intégration

Imaginez deux binômes qui font évoluer Listify pendant trois semaines, chacun sur sa branche. Le premier ajoute des dates d'échéance aux tâches : il modifie le schéma SQL, les requêtes de `app.py`, le JavaScript qui affiche la liste. Le second ajoute la pagination de `GET /api/tasks` : il modifie les mêmes requêtes, le même JavaScript, et ajoute un paramètre d'URL. Chacun teste soigneusement **sa** branche, qui fonctionne. Le vendredi de la troisième semaine, on fusionne.

Ce qui se passe alors porte un nom dans l'industrie : l'**enfer de l'intégration** (*integration hell*). Les conflits textuels, que Git signale, ne sont que la partie visible. Les plus coûteux sont les conflits **sémantiques**, que Git ne voit pas : le code fusionne sans erreur, compile, mais la requête paginée ne sélectionne pas la nouvelle colonne `due_date`, et le frontend affiche `undefined` sur la deuxième page. Personne ne sait plus quelle modification a cassé quoi, parce que trois semaines de changements arrivent d'un seul coup. On passe la journée, parfois la semaine, à démêler.

Le phénomène n'a rien d'anecdotique. Avant la diffusion de l'intégration continue, il était courant qu'un projet prévoie une **phase d'intégration** de plusieurs semaines à la fin de chaque cycle, pendant laquelle personne ne développait de fonctionnalité : on assemblait, on réparait, on assemblait encore. Cette phase était notoirement imprévisible, parce qu'on ne peut pas estimer la durée d'une tâche dont on ne connaît pas encore les problèmes.

## 2. Définition

L'expression apparaît chez Grady Booch au début des années 1990, mais c'est l'**Extreme Programming** de Kent Beck qui en fait une pratique centrale à la fin de la décennie [^beck], et l'article de Martin Fowler, publié en 2000 puis révisé en 2006 et en 2024, qui la popularise [^fowler-ci]. La définition de Fowler reste la référence :

:::definition[Intégration continue]
Pratique de développement dans laquelle chaque membre d'une équipe intègre son travail dans la branche principale partagée **au moins une fois par jour**, chaque intégration étant **vérifiée par un build automatisé** (tests compris) qui détecte les erreurs d'intégration le plus tôt possible.
:::

Deux éléments de cette définition sont indissociables, et l'on confond souvent la pratique avec l'outil qui la sert :

- **La fréquence** : intégrer au moins quotidiennement dans la branche principale. Une équipe qui fait tourner un serveur de CI sur des branches vivant trois semaines ne fait **pas** d'intégration continue ; elle fait de la vérification automatique de branches isolées, ce qui est utile mais ne résout pas le problème de la section 1.
- **La vérification automatique** : chaque intégration déclenche un build et une suite de tests sans intervention humaine. Intégrer souvent sans vérifier, c'est intégrer souvent des erreurs.

Retenez la distinction, elle tombe régulièrement à l'examen : **un serveur Jenkins, GitLab CI ou Gitea Actions est un outil ; l'intégration continue est une pratique d'équipe**. On peut avoir l'outil sans la pratique, et, en théorie du moins, la pratique avec un outil rudimentaire.

[^beck]: Kent Beck, *Extreme Programming Explained: Embrace Change*, Addison-Wesley, 1999 (2ᵉ éd. 2004, avec Cynthia Andres). L'intégration continue y figure parmi les douze pratiques de la méthode.

[^fowler-ci]: Martin Fowler, « Continuous Integration », martinfowler.com, première version en 2000 avec Matthew Foemmel, réécriture en 2006, révision majeure en 2024. [martinfowler.com/articles/continuousIntegration.html](https://martinfowler.com/articles/continuousIntegration.html).

## 3. Pourquoi intégrer souvent change tout

### 3.1 « Si ça fait mal, faites-le plus souvent »

L'intuition contraire est tenace : si fusionner est pénible, fusionnons le moins souvent possible. Fowler résume l'argument inverse par une maxime devenue célèbre, *« if it hurts, do it more often »* [^fowler-freq]. Trois mécanismes l'expliquent :

1. **La difficulté croît plus vite que la taille.** Deux petites modifications ont peu de chances de se toucher ; deux grosses modifications se touchent presque toujours, et leurs interactions se combinent.
2. **La localisation de la cause devient triviale.** Si le build casse après une intégration de vingt lignes, la cause est dans ces vingt lignes. Après trois semaines de changements, elle est quelque part dans des milliers de lignes, écrites par plusieurs personnes qui ne se souviennent plus de leurs raisons.
3. **La répétition crée la compétence et l'outillage.** Une opération faite une fois par mois reste manuelle et fragile ; faite dix fois par jour, elle est forcément automatisée, et bien automatisée.

Le troisième point est le plus profond, et il reviendra au chapitre 24 pour le déploiement : c'est la même logique qui pousse à déployer souvent.

[^fowler-freq]: Martin Fowler, « Frequency Reduces Difficulty », martinfowler.com/bliki, 2011. Jez Humble et David Farley en font un principe de *Continuous Delivery* (voir chapitre 24).

<Figure src="integration-frequence" num="23.1" alt="En haut, une branche vit trois semaines à l'écart de main et sa fusion produit un conflit géant ; en bas, des branches de quelques heures sont fusionnées plusieurs fois par jour, avec de petits conflits détectés le jour même.">
  Branche de longue durée contre intégration fréquente. Le volume total de changements est le même dans les deux cas ; ce qui change, c'est la taille de chaque fusion, donc la probabilité et le coût des conflits.
</Figure>

### 3.2 Un modèle chiffré

Donnons une forme quantitative au premier mécanisme, avec un modèle volontairement simple : il sous-estime la réalité, mais il suffit à montrer l'effet.

:::exemple[Combien de fichiers en conflit ?]
Hypothèses : le code de Listify, une fois enrichi, compte 300 fichiers ; chaque binôme modifie 2 fichiers par jour ouvré, choisis au hasard et indépendamment ; le projet dure 15 jours ouvrés (trois semaines). On compte un « conflit » chaque fois que les deux binômes ont touché le même fichier entre deux intégrations.

**Scénario A, fusion unique en fin de période.** Chaque binôme a modifié environ 30 fichiers. Pour un fichier donné, la probabilité qu'il ait été touché par le binôme 1 est $30/300 = 0{,}1$, idem pour le binôme 2. Le nombre attendu de fichiers touchés par les deux est donc :

$$
300 \times 0{,}1 \times 0{,}1 = 3 \text{ fichiers en conflit, à démêler d'un seul coup.}
$$

**Scénario B, intégration quotidienne.** Chaque jour, chacun touche 2 fichiers. Le nombre attendu de fichiers en conflit par jour vaut :

$$
300 \times \frac{2}{300} \times \frac{2}{300} = \frac{4}{300} \approx 0{,}013,
$$

soit environ $15 \times 0{,}013 = 0{,}2$ conflit sur toute la période.

Le scénario B divise le nombre de conflits par 15, et c'est la moindre partie du gain : chacun de ces rares conflits porte sur **une demi-journée** de travail récent, dont les deux auteurs se souviennent, au lieu de trois semaines de modifications accumulées. Dans la réalité, les modifications ne sont pas indépendantes (les deux binômes travaillent sur les mêmes zones chaudes du code, comme `app.py`), ce qui aggrave encore le scénario A.
:::

Plus généralement, dans ce modèle, le nombre attendu de conflits sur la période est proportionnel à $n^2 / k$, où $n$ est le nombre de fichiers modifiés par personne sur toute la période et $k$ le nombre d'intégrations : multiplier la fréquence d'intégration par $k$ divise les conflits par $k$.

## 4. Les pratiques qui rendent la CI possible

Intégrer quotidiennement n'est tenable que si un ensemble de pratiques le soutient. La liste suivante reprend celle de Fowler [^fowler-ci], regroupée en trois familles. Chacune répond à une question concrète.

### 4.1 Un point d'intégration unique et reconstructible

- **Un seul dépôt de référence**, qui contient **tout** ce qu'il faut pour construire le logiciel : code, schéma de base, scripts de build, configuration de la CI elle-même. Le fichier de pipeline est versionné avec le code qu'il vérifie : c'est de l'Infrastructure as Code appliquée à la chaîne de build.
- **Un build entièrement automatisé**, lançable par une seule commande. Si construire Listify demande de lire un wiki et de taper douze commandes, la CI ne peut pas le faire.
- **Des dépendances épinglées.** Le `requirements.txt` de Listify fige les versions (`flask==3.0.3`). Sans cela, le build de lundi et celui de mardi n'utilisent pas le même code, et un échec peut venir d'une bibliothèque qui a changé la nuit. On retrouve la reproductibilité du chapitre 2.

### 4.2 Un build qui vérifie vraiment

- **Un build auto-testant** : la compilation ne suffit pas, surtout en Python où rien ne se compile vraiment. Le build exécute une suite de tests automatiques et échoue si l'un d'eux échoue.
- **Chaque intégration est construite sur une machine neutre**, pas sur le poste du développeur. C'est ce qui démasque le célèbre « ça marche chez moi » : une variable d'environnement oubliée, un fichier non versionné, une bibliothèque installée globalement.
- **Un environnement de test proche de la production** : même version de Python, même PostgreSQL 16. Les conteneurs du bloc 1 rendent cela presque gratuit : le runner exécute les tests dans une image qui ressemble à celle de production.

### 4.3 Une discipline d'équipe

- **Un build rapide.** Le seuil classique, venu de l'Extreme Programming, est la **règle des dix minutes** [^beck] : au-delà, les développeurs cessent d'attendre le résultat, empilent d'autres modifications, et le retour arrive trop tard pour être utile.
- **Un build cassé se répare immédiatement.** C'est la règle la plus exigeante et la plus importante. Quand la branche principale ne passe plus la CI, la réparer devient la priorité de l'équipe, avant toute nouvelle fonctionnalité ; si la réparation tarde, on annule le commit fautif (`git revert`). L'analogie usuelle est le cordon *andon* des usines Toyota, que tout ouvrier peut tirer pour arrêter la chaîne dès qu'il voit un défaut [^ohno]. Une branche principale cassée qu'on tolère est pire que pas de CI du tout : chacun s'habitue au rouge, et plus personne ne remarque les nouvelles erreurs.
- **L'état du build est visible par tous**, en permanence : badge dans le README, notification dans le canal de l'équipe.

[^ohno]: Taiichi Ohno, *Toyota Production System: Beyond Large-Scale Production*, Productivity Press, 1988 (éd. japonaise 1978). Le principe de *jidoka*, arrêter la production dès qu'une anomalie apparaît, est l'ancêtre direct de la règle du build cassé.

:::danger[Commenter le test qui échoue]
Le réflexe le plus destructeur face à un build rouge est de désactiver le test qui échoue « en attendant ». Un test désactivé ne revient presque jamais, et il protégeait probablement contre une vraie régression. Si un test est faux, on le corrige ; s'il est instable (section 7), on le met en quarantaine **avec un ticket et une échéance**, jamais en silence.
:::

## 5. Anatomie d'un pipeline

### 5.1 Les étapes canoniques

Un **pipeline** est la suite automatisée d'étapes qu'exécute la CI à chaque intégration. Leur contenu varie selon les projets, mais quatre familles reviennent partout, et l'ordre compte :

<Figure src="ci-pipeline" num="23.2" alt="Du git push à l'artefact publié : lint, tests, build de l'image, scan des vulnérabilités ; si une étape échoue, le pipeline s'arrête et le développeur est prévenu.">
  Les étapes canoniques d'un pipeline d'intégration continue, de la plus rapide à la plus lente. Un échec arrête la chaîne : il est inutile de construire une image à partir d'un code qui ne passe pas ses tests.
</Figure>

**Lint (analyse statique).** Un outil lit le code sans l'exécuter et signale les erreurs évidentes et les écarts de style : variable non définie, import inutilisé, comparaison suspecte. Pour Python, **ruff** a largement remplacé la combinaison historique flake8, isort et pyflakes, en s'exécutant en quelques dixièmes de seconde sur un projet entier. Le lint est bon marché et attrape une part étonnante des erreurs : c'est la première étape.

**Tests.** On distingue classiquement trois niveaux, que Mike Cohn a popularisés sous le nom de **pyramide des tests** [^cohn] :

| Niveau | Ce qu'il vérifie | Exemple pour Listify | Coût |
|---|---|---|---|
| Unitaire | Une fonction ou un point d'API, isolé du reste | `POST /api/tasks` sans titre renvoie 400 | Millisecondes, aucun service externe |
| Intégration | Le code avec ses vraies dépendances | créer une tâche puis la retrouver dans `GET /api/tasks`, avec un vrai PostgreSQL | Secondes, un conteneur de base |
| Bout en bout | Le système complet, du point de vue de l'utilisateur | un navigateur automatisé ajoute une tâche dans l'interface | Minutes, tout l'environnement |

La pyramide recommande **beaucoup** de tests unitaires, **un peu moins** de tests d'intégration et **peu** de tests de bout en bout, parce que le coût et l'instabilité croissent quand on monte. Une suite « en cône de glace », faite surtout de tests de bout en bout, est lente et fragile.

**Build de l'artefact.** Une fois le code vérifié, on produit ce qui sera déployé : pour Listify, les images de conteneur du backend et du frontend, construites à partir des Containerfile du TP 12.

**Scan.** On analyse l'artefact : vulnérabilités connues des paquets de l'image (Trivy, vu au TP 14), secrets committés par erreur, licences incompatibles. Un scan qui trouve une vulnérabilité critique fait échouer le pipeline.

**Publication.** Si tout passe, l'artefact est poussé dans un registre, avec un identifiant qui permet de le retrouver sans ambiguïté (chapitre 24).

[^cohn]: Mike Cohn, *Succeeding with Agile: Software Development Using Scrum*, Addison-Wesley, 2009, chapitre 16. Martin Fowler en donne une présentation critique dans « The Practical Test Pyramid » (Ham Vocke, martinfowler.com, 2018).

### 5.2 L'ordre des étapes n'est pas arbitraire

Pourquoi le lint d'abord et le build ensuite ? Parce qu'un pipeline est un **filtre** : chaque étape peut arrêter la chaîne, et l'on veut que les échecs fréquents et bon marché à détecter tombent le plus tôt possible. Un petit calcul le montre.

:::exemple[Durée moyenne d'un pipeline selon l'ordre des étapes]
Mesures relevées sur un projet : le lint dure 0,5 min, les tests 3 min, le build 4 min, le scan 2 min. Parmi les exécutions, 10 % échouent au lint ; parmi celles qui passent le lint, 15 % échouent aux tests ; puis 3 % au build et 5 % au scan. On suppose ces échecs indépendants. Une étape n'est exécutée que si les précédentes ont réussi.

**Ordre rapide d'abord (lint, tests, build, scan).** Durée moyenne :

$$
0{,}5 + 0{,}90 \times 3 + 0{,}90 \times 0{,}85 \times 4 + 0{,}90 \times 0{,}85 \times 0{,}97 \times 2 \approx 7{,}74 \text{ min.}
$$

**Ordre lent d'abord (build, scan, tests, lint).** Durée moyenne :

$$
4 + 0{,}97 \times 2 + 0{,}97 \times 0{,}95 \times 3 + 0{,}97 \times 0{,}95 \times 0{,}85 \times 0{,}5 \approx 9{,}10 \text{ min.}
$$

Le gain moyen, 1,4 minute par exécution, paraît modeste. Regardez plutôt le **temps de retour** dans le cas le plus fréquent, une faute de style : 0,5 minute dans le premier ordre, 9,5 minutes dans le second, soit dix-neuf fois plus. Sur une équipe de dix personnes qui intègrent chacune cinq fois par jour, les 1,4 minute moyennes représentent environ 70 minutes de machine économisées chaque jour, et surtout des développeurs qui restent concentrés au lieu d'attendre.
:::

La règle générale : on classe les étapes par rapport « probabilité d'échec / durée » décroissant. Deux compléments pratiques :

- **Paralléliser ce qui est indépendant.** Le lint et les tests unitaires ne dépendent pas l'un de l'autre : on peut les lancer en même temps sur deux runners. La durée devient celle du plus long, pas la somme.
- **Tester avant de construire, mais tester ce qu'on construit.** Il existe une tension : on teste le code source avant le build pour aller vite, mais ce qui part en production est l'image. Les équipes mûres ajoutent donc, après le build, quelques tests de fumée (*smoke tests*) sur l'image elle-même : on la démarre et on interroge `/api/health`.

## 6. Runners et workflows : la mécanique

### 6.1 Le vocabulaire

Toutes les forges modernes (GitHub, GitLab, Gitea, Forgejo) reposent sur le même modèle :

- Un **workflow** est un fichier versionné dans le dépôt, qui décrit **quand** déclencher (un `push` sur `main`, une pull request, une étiquette) et **quoi** exécuter.
- Un workflow contient des **jobs** : des unités d'exécution indépendantes, qui tournent chacune sur une machine propre et peuvent dépendre les unes des autres (`needs`).
- Un job est une suite de **steps** : des commandes shell (`run`) ou des actions réutilisables (`uses`), comme la récupération du code.
- Un **runner** est le programme qui exécute les jobs. Il interroge la forge, récupère un job en attente, le lance (en général dans un conteneur jetable) et renvoie les journaux et le résultat.

La séparation entre forge et runner est importante : la forge stocke le code et orchestre, les runners exécutent. On peut ajouter des runners pour absorber la charge, ou dédier un runner à une machine particulière (un runner avec GPU pour le semestre 3).

:::info[Gitea Actions et GitHub Actions]
Gitea, la forge que vous installerez au TP 19, implémente depuis sa version 1.19 un système d'actions **compatible avec la syntaxe de GitHub Actions** : les workflows se placent dans `.gitea/workflows/` (ou `.github/workflows/`), et le runner **act_runner** les exécute dans des conteneurs. La compétence est donc directement transférable vers GitHub, qui domine l'hébergement de code, et les concepts vers GitLab CI, dont la syntaxe diffère mais dont le modèle est identique.
:::

### 6.2 Le workflow de Listify

Voici le premier pipeline de Listify, celui que vous mettrez en place au TP 19. Il comporte deux jobs : le lint, puis les tests, qui ont besoin d'un vrai PostgreSQL.

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
    env:
      DB_HOST: db                  # le service est joignable par son nom
      DB_PASSWORD: ci-password
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r backend/requirements.txt pytest==8.3.3
      - run: pytest -v backend/tests/
```

Quatre points à comprendre :

- **Le déclencheur** couvre deux cas : chaque `push` sur `main` (l'intégration elle-même) et chaque pull request (vérifier **avant** d'intégrer).
- **`needs: lint`** crée la dépendance de la section 5.2 : les tests ne démarrent que si le lint est passé.
- **Le bloc `services`** démarre un conteneur PostgreSQL à côté du job et le détruit à la fin. Chaque exécution part d'une base vide : aucun test ne dépend des restes du précédent.
- **Le mot de passe est en clair**, et c'est acceptable **ici** parce qu'il ne protège qu'une base jetable qui n'existe que pendant le job. Un vrai secret (le mot de passe du registre au TP 20) se stocke dans les **secrets** de la forge et se lit par `${{ secrets.NOM }}` ; il n'apparaît jamais dans le dépôt.

### 6.3 Les tests correspondants

Listify n'a pas encore de tests : vous les écrirez au TP 19. Voici leur forme, qui illustre les deux premiers niveaux de la pyramide. Le client de test de Flask envoie des requêtes à l'application sans démarrer de serveur :

```python title="backend/tests/test_api.py"
import pytest

from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_create_task_requires_title(client):
    # Test unitaire : la validation a lieu avant tout accès à la base.
    resp = client.post("/api/tasks", json={"title": "   "})
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "title is required"}


def test_create_then_list(client):
    # Test d'intégration : il faut un vrai PostgreSQL (le service « db »).
    created = client.post("/api/tasks", json={"title": "écrire les tests"})
    assert created.status_code == 201
    titles = [t["title"] for t in client.get("/api/tasks").get_json()]
    assert "écrire les tests" in titles
```

Le premier test ne touche pas la base, parce que `create_task` rejette le titre vide avant d'ouvrir une connexion ; il tournerait en quelques millisecondes sur n'importe quel poste. Le second a besoin du schéma de la base, qu'un fichier `conftest.py` charge avant la suite (vous l'écrirez au TP). Ce découpage n'est pas un détail : c'est parce que la validation de `create_task` est faite **avant** l'accès à la base qu'on peut la tester unitairement. Du code testable est souvent du code mieux structuré.

## 7. Pathologies d'une CI, et remèdes

Une CI se dégrade lentement si l'on n'y prend pas garde. Quatre pathologies reviennent dans toutes les équipes.

**Le build lent.** Au-delà de dix minutes, la pratique s'effrite. Remèdes, dans l'ordre : mettre en **cache** les dépendances (ne pas retélécharger les paquets pip à chaque exécution), **paralléliser** les jobs indépendants, **découper** la suite de tests en un premier étage rapide sur chaque commit et un second étage complet plus rare, et bien sûr traquer les tests anormalement lents.

**Les tests instables** (*flaky tests*). Un test instable échoue parfois sans que le code ait changé : dépendance à l'heure, ordre d'exécution, attente réseau trop courte, ressource partagée entre tests. Le phénomène est massif. En 2016, John Micco, qui pilotait l'infrastructure de tests de Google, rapportait qu'environ 1,5 % des exécutions de tests y produisaient un résultat instable et que près de 16 % des tests présentaient une instabilité à un moment ou un autre [^micco]. Une étude empirique de référence sur des projets libres classe les causes : l'asynchronisme (attentes mal gérées) et la concurrence arrivent en tête [^luo]. Le danger est culturel : quand les tests échouent « pour rien », l'équipe apprend à relancer sans regarder, et les vrais échecs passent inaperçus.

**Le build cassé toléré.** Voir la section 4.3 : c'est la pathologie qui tue la pratique.

**La CI comme porte d'entrée.** Le runner exécute du code venu du dépôt, avec parfois des secrets à portée de main (identifiants du registre, du cluster). Une pull request malveillante qui modifie le workflow peut tenter de les exfiltrer ; c'est pourquoi les forges n'exposent pas les secrets aux pull requests venant de dépôts forkés. L'attaque de la chaîne de build de SolarWinds, découverte fin 2020, a montré jusqu'où peut aller la compromission d'un système de build : un code malveillant inséré **pendant la construction** a été distribué, signé, à des milliers de clients [^solarwinds]. La chaîne de CI fait partie de la surface d'attaque, et se protège comme la production.

[^micco]: John Micco, « Flaky Tests at Google and How We Mitigate Them », Google Testing Blog, 27 mai 2016. [testing.googleblog.com](https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html).

[^luo]: Qingzhou Luo, Farah Hariri, Lamyaa Eloussi, Darko Marinov, « An Empirical Analysis of Flaky Tests », *FSE*, 2014.

[^solarwinds]: CISA, *Emergency Directive 21-01: Mitigate SolarWinds Orion Code Compromise*, décembre 2020 ; et le rapport technique de FireEye (Mandiant) sur SUNBURST, 13 décembre 2020.

:::tip[Le réflexe à prendre dès le TP 19]
Devant un pipeline rouge, lisez le journal de l'étape qui a échoué **avant** de relancer. Si vous relancez et que ça passe, vous n'avez rien réparé : vous avez un test instable de plus, qu'il faut signaler.
:::

## Ce qu'il faut retenir

<div className="retenir">

1. L'**intégration tardive** coûte cher : conflits textuels et surtout sémantiques, cause introuvable, durée imprévisible.
2. L'**intégration continue** est une **pratique** : intégrer dans la branche principale au moins une fois par jour, chaque intégration étant vérifiée par un build automatisé avec tests. L'outil (Gitea Actions, GitLab CI, Jenkins) ne suffit pas.
3. « **Si ça fait mal, faites-le plus souvent** » : les petites intégrations se touchent rarement, localisent la cause, et forcent l'automatisation. Dans un modèle simple, multiplier la fréquence par $k$ divise les conflits par $k$.
4. Pratiques indispensables : dépôt unique et reconstructible, dépendances épinglées, build auto-testant sur machine neutre, **build en moins de dix minutes**, **build cassé réparé immédiatement**.
5. Pipeline canonique : **lint, tests, build, scan, publication**, ordonné pour que les échecs fréquents et bon marché tombent tôt. On parallélise ce qui est indépendant.
6. **Workflow** (fichier versionné), **job** (unité sur une machine), **step** (commande ou action), **runner** (exécutant). Gitea Actions reprend la syntaxe de GitHub Actions.
7. Pathologies : build lent, **tests instables**, build cassé toléré, CI vulnérable. La chaîne de build fait partie de la surface d'attaque.

</div>

## Regard recherche

:::recherche
L'intégration continue a fait l'objet d'études empiriques à grande échelle, qui permettent de dépasser les opinions :

- **Michael Hilton, Timothy Tunnell, Kai Huang, Darko Marinov, Danny Dig, « Usage, Costs, and Benefits of Continuous Integration in Open-Source Projects », *ASE*, 2016.** Une étude sur des dizaines de milliers de projets GitHub, complétée par un sondage de développeurs : qui utilise la CI, pourquoi, et ce qu'elle change au rythme des publications. Le meilleur point d'entrée.
- **Bogdan Vasilescu, Yue Yu, Huaimin Wang, Premkumar Devanbu, Vladimir Filkov, « Quality and Productivity Outcomes Relating to Continuous Integration in GitHub », *ESEC/FSE*, 2015.** Mesure l'association entre l'adoption de la CI et la productivité (pull requests intégrées) ainsi que la qualité (défauts détectés).
- **Atif Memon et al., « Taming Google-Scale Continuous Testing », *ICSE-SEIP*, 2017.** Comment Google décide quels tests exécuter quand la suite complète est trop grande pour être lancée à chaque changement : la CI à l'échelle d'un dépôt de plusieurs milliards de lignes.
- **Qingzhou Luo et al., « An Empirical Analysis of Flaky Tests », *FSE*, 2014.** La taxonomie de référence des causes d'instabilité des tests.

Piste d'innovation : la **sélection et la priorisation des tests** (n'exécuter que les tests concernés par un changement, dans le meilleur ordre) et la **détection automatique des tests instables** sont des sujets de recherche très actifs, à la croisée du génie logiciel et de l'apprentissage automatique.
:::

## Bibliographie du chapitre

<div className="biblio">

### Sources primaires

- Martin Fowler, « Continuous Integration », martinfowler.com, 2000, révisé en 2006 et 2024. La définition de référence et la liste des pratiques.
- Kent Beck, *Extreme Programming Explained*, Addison-Wesley, 1999. L'origine de la pratique et de la règle des dix minutes.
- Documentation de Gitea, « Gitea Actions » : [docs.gitea.com/usage/actions/overview](https://docs.gitea.com/usage/actions/overview). La référence pour le TP 19.

### Lectures recommandées

- Jez Humble, David Farley, *Continuous Delivery*, Addison-Wesley, 2010, chapitre 3 (« Continuous Integration »). Le prolongement naturel de ce chapitre vers le suivant.
- Ham Vocke, « The Practical Test Pyramid », martinfowler.com, 2018. Une présentation concrète et nuancée des niveaux de tests.
- Documentation GitHub, « Understanding GitHub Actions » : la syntaxe des workflows, identique pour Gitea.

### Pour aller plus loin

- Les articles de recherche de la rubrique « Regard recherche ».
- Titus Winters, Tom Manshreck, Hyrum Wright (dir.), *Software Engineering at Google*, O'Reilly, 2020, chapitres 11 à 14 (tests) et 23 (« Continuous Integration »). Gratuit en ligne : [abseil.io/resources/swe-book](https://abseil.io/resources/swe-book).

</div>
