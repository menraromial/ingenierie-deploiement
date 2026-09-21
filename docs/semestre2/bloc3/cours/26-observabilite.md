---
title: "Ch. 26 : Observabilité"
sidebar_label: "Ch. 26 : Observabilité"
hide_title: true
---

import ChapterHead from '@site/src/components/ChapterHead';
import Figure from '@site/src/components/Figure';

<ChapterHead
  kicker="Semestre 2 · Bloc 3 · Chapitre 26"
  title="Observabilité : savoir ce que fait la production"
  lecture="45 min"
  competences={['C4', 'C5']}
/>

:::objectifs
À l'issue de ce chapitre, vous saurez :

- distinguer surveillance et observabilité, et les trois types de signaux : logs, métriques, traces ;
- choisir quoi mesurer sur un service (signaux dorés, méthodes RED et USE) ;
- expliquer le modèle de Prometheus : collecte par pull, séries temporelles, étiquettes, types de métriques, et le danger de la cardinalité ;
- écrire et calculer à la main des requêtes PromQL de base : débit, taux d'erreurs, quantile de latence ;
- instrumenter une application Flask servie par Gunicorn ;
- écrire une règle d'alerte fondée sur les symptômes ;
- définir un SLI, un SLO et un budget d'erreur, et raisonner en taux de consommation.
:::

## 1. « Est-ce que ça marche ? »

Listify tourne sur le cluster, déployé automatiquement par Argo CD. Le Deployment affiche 3 répliques prêtes, les *readiness probes* réussissent, Argo CD est vert. Et pourtant, un utilisateur se plaint : ajouter une tâche prend parfois cinq secondes, et une fois sur vingt l'interface affiche une erreur. Rien de ce que vous avez construit jusqu'ici ne permet de répondre aux questions qui se posent immédiatement : depuis quand ? Pour tous les utilisateurs ou certains seulement ? Sur toutes les répliques ou une seule ? Est-ce la base de données, le réseau, le code ? Est-ce lié au déploiement de 14 h ?

Les sondes du chapitre 22 répondent à une question binaire (« ce Pod peut-il recevoir du trafic ? ») et ne disent rien de la qualité du service rendu. Au S1, vous aviez les journaux de systemd, un par machine, qu'on lisait avec `journalctl` quand on savait déjà où chercher. Avec des dizaines de Pods éphémères, qui naissent et meurent au gré des déploiements, cette approche ne tient plus. Il faut des signaux **collectés en continu**, **agrégés** à l'échelle du système, **interrogeables** après coup.

## 2. Surveillance et observabilité

Les deux mots sont souvent employés l'un pour l'autre ; la distinction est pourtant utile.

La **surveillance** (*monitoring*) consiste à vérifier des conditions **connues à l'avance** : le disque est-il plein à plus de 90 % ? Le taux d'erreurs dépasse-t-il 5 % ? Elle répond aux questions qu'on a pensé à poser, les « inconnues connues ».

:::definition[Observabilité]
Propriété d'un système dont on peut **déduire l'état interne à partir de ses sorties**. Le terme vient de la théorie du contrôle, où Rudolf Kálmán l'a formalisé en 1960 [^kalman]. En informatique, un système est observable quand ses signaux (logs, métriques, traces) permettent de répondre à des questions **qu'on n'avait pas prévues**, sans modifier ni redéployer le code.
:::

La surveillance est une activité ; l'observabilité est une propriété, qu'on construit en instrumentant le code. La première dépend de la seconde : on ne peut surveiller que ce qu'on observe. Le symptôme de la section 1 est typique des problèmes qu'on ne sait pas anticiper, et c'est là que l'observabilité fait la différence.

[^kalman]: Rudolf E. Kálmán, « On the General Theory of Control Systems », *Proceedings of the First IFAC Congress*, 1960.

## 3. Trois types de signaux

<Figure src="trois-piliers" num="26.1" alt="Trois colonnes : les logs sont des événements horodatés individuels, les métriques des nombres agrégés dans le temps, les traces le parcours d'une requête entre services ; chacun répond à une question différente.">
  Logs, métriques, traces. Chaque type de signal répond à une question différente ; leur valeur est maximale quand on peut passer de l'un à l'autre grâce à un identifiant commun.
</Figure>

### 3.1 Les logs

Un **log** est un événement horodaté, émis par le code : une requête reçue, une erreur levée, une connexion perdue. C'est le signal le plus riche (il peut contenir tout le contexte) et le plus familier. Deux règles le rendent exploitable à l'échelle :

- **Structurer.** Une ligne `ERROR: could not connect` se lit bien à l'œil, mais s'interroge mal. Une ligne JSON `{"level": "error", "event": "db_connect_failed", "host": "db", "request_id": "a3f9"}` se filtre, s'agrège et se compte par un outil.
- **Écrire sur la sortie standard.** Dans un conteneur, l'application n'écrit pas dans des fichiers : elle écrit sur `stdout`, et c'est la plateforme qui collecte (c'est ce que lit `kubectl logs`). Le facteur XI des *Twelve-Factor Apps* le formule ainsi : traiter les logs comme un flux d'événements [^12factor-logs].

Le défaut des logs est leur **coût** : un service qui reçoit mille requêtes par seconde produit des centaines de millions de lignes par jour, qu'il faut transporter, indexer et stocker. On ne peut pas tout garder longtemps.

[^12factor-logs]: Adam Wiggins, *The Twelve-Factor App*, facteur XI « Logs », 2011. [12factor.net/fr/logs](https://12factor.net/fr/logs).

### 3.2 Les métriques

Une **métrique** est une mesure **numérique agrégée**, relevée à intervalles réguliers : le nombre total de requêtes reçues, la mémoire utilisée, la durée des requêtes répartie par tranches. Une métrique ne dit rien d'une requête particulière, mais elle est extraordinairement **économe** : que le service reçoive dix ou dix mille requêtes par seconde, le compteur de requêtes reste un seul nombre relevé toutes les quinze secondes. C'est ce qui permet de conserver des mois d'historique, de tracer des courbes et de déclencher des alertes. Les métriques sont le signal de la **surveillance** ; le reste de ce chapitre leur est largement consacré.

### 3.3 Les traces

Une **trace** suit le parcours d'**une** requête à travers tous les composants qu'elle traverse. Elle est formée de **spans** : chaque span représente une opération (la requête dans Nginx, son traitement par Gunicorn, la requête SQL), avec son début, sa durée et son span parent. La trace répond à la question que ni les logs ni les métriques n'éclairent directement : **où** le temps est-il passé ?

L'article fondateur est celui de **Dapper**, le système de traçage de Google, publié en 2010 [^dapper]. Il établit deux idées reprises depuis par tous les outils : propager un **identifiant de trace** d'un service à l'autre dans les en-têtes des requêtes, et **échantillonner** (ne tracer qu'une requête sur mille, par exemple) pour que le coût reste négligeable. Aujourd'hui, le standard ouvert est **OpenTelemetry**, né en 2019 de la fusion des projets OpenTracing et OpenCensus sous l'égide de la CNCF, qui unifie l'instrumentation des trois types de signaux.

Pour Listify, avec trois tiers seulement, les traces sont un luxe ; elles deviennent indispensables quand une requête traverse dix microservices, et qu'on cherche lequel la ralentit.

[^dapper]: Benjamin H. Sigelman, Luiz André Barroso, Mike Burrows, Pat Stephenson, Manoj Plakal, Donald Beaver, Saul Jaspan, Chandan Shanbhag, « Dapper, a Large-Scale Distributed Systems Tracing Infrastructure », Google Technical Report dapper-2010-1, 2010.

### 3.4 Relier les signaux

La puissance vient de la **corrélation**. Une alerte sur une métrique (le taux d'erreurs monte) conduit à filtrer les logs de la même période et de la même réplique, qui contiennent un `request_id` ; cet identifiant mène à la trace complète d'une requête fautive, qui montre que la requête SQL a attendu quatre secondes un verrou. Chaque signal restreint l'espace de recherche du suivant.

## 4. Que mesurer ?

On peut tout mesurer ; la difficulté est de mesurer **ce qui compte**. Trois grilles complémentaires se sont imposées.

**Les quatre signaux dorés** (*golden signals*), proposés dans le livre de Google sur l'ingénierie de fiabilité [^sre-book], pour tout service qui répond à des utilisateurs :

1. **Latence** : le temps de réponse, en distinguant celui des requêtes réussies et celui des échecs (une erreur rapide ne doit pas faire baisser la latence apparente) ;
2. **Trafic** : la demande, en requêtes par seconde ;
3. **Erreurs** : le taux de requêtes en échec, explicites (code 500) ou implicites (réponse 200 avec un contenu faux) ;
4. **Saturation** : à quel point le service est « plein » (CPU, mémoire, workers Gunicorn occupés), qui annonce souvent la dégradation.

**La méthode RED**, formulée par Tom Wilkie pour les microservices, en est une version resserrée : **R**ate (débit), **E**rrors (erreurs), **D**uration (durée) [^red]. **La méthode USE** de Brendan Gregg s'applique, elle, aux **ressources** (processeur, disque, réseau) : **U**tilization, **S**aturation, **E**rrors [^use].

| Composant de Listify | Grille | Ce qu'on mesure |
|---|---|---|
| API (backend Flask) | RED | Requêtes par seconde par route ; proportion de réponses 5xx ; distribution des durées |
| Nginx (frontend) | RED | Idem, vu de l'entrée du système |
| PostgreSQL | USE + spécifiques | Connexions utilisées sur le maximum ; requêtes lentes ; taille de la base |
| Nœuds du cluster | USE | CPU, mémoire, disque : utilisation et saturation |
| Pods | Spécifiques | Redémarrages, Pods non prêts, OOMKilled (chapitre 22) |

[^sre-book]: Betsy Beyer, Chris Jones, Jennifer Petoff, Niall Richard Murphy (dir.), *Site Reliability Engineering: How Google Runs Production Systems*, O'Reilly, 2016, chapitre 6, « Monitoring Distributed Systems ». Gratuit en ligne : [sre.google/sre-book](https://sre.google/sre-book/monitoring-distributed-systems/).

[^red]: Tom Wilkie, « The RED Method: How to Instrument Your Services », présentation, 2015, et billet de blog de Grafana Labs, 2018.

[^use]: Brendan Gregg, « Thinking Methodically about Performance », *ACM Queue*, vol. 10, n° 12, 2012 ; et [brendangregg.com/usemethod.html](https://www.brendangregg.com/usemethod.html).

## 5. Prometheus

### 5.1 Origine et architecture

**Prometheus** est né en 2012 chez SoundCloud, inspiré de Borgmon, le système de surveillance interne de Google décrit dans le livre SRE [^sre-borgmon]. Il est devenu en 2016 le deuxième projet hébergé par la CNCF, après Kubernetes, et le deuxième à en être diplômé, en 2018. C'est aujourd'hui la référence de la surveillance dans l'écosystème Kubernetes.

<Figure src="prometheus-architecture" num="26.2" alt="Prometheus interroge périodiquement les points /metrics des cibles (le backend de Listify, node-exporter, kube-state-metrics), stocke les séries temporelles et évalue les règles d'alerte ; Grafana l'interroge en PromQL pour les tableaux de bord, et Alertmanager reçoit les alertes pour les router vers des notifications.">
  L'architecture de Prometheus. Les cibles exposent leurs métriques, Prometheus vient les chercher ; les tableaux de bord et les alertes s'appuient sur ses données.
</Figure>

Quatre composants se partagent le travail :

- **Les cibles** exposent leurs métriques sur une URL HTTP, par convention `/metrics`, dans un format texte simple. Une application s'instrumente avec une bibliothèque cliente ; pour les systèmes qu'on ne modifie pas, un **exporteur** traduit (node-exporter pour les métriques d'une machine Linux, kube-state-metrics pour l'état des objets Kubernetes).
- **Le serveur Prometheus** interroge chaque cible à intervalle régulier (le *scrape*, typiquement toutes les 15 ou 30 secondes), stocke les valeurs dans sa base de séries temporelles et évalue les règles d'alerte. Il découvre ses cibles tout seul en interrogeant l'API Kubernetes : un nouveau Pod est surveillé dès sa création.
- **Alertmanager** reçoit les alertes de Prometheus, les regroupe, supprime les doublons et les route vers le bon canal (courriel, messagerie, système d'astreinte).
- **Grafana**, projet distinct, interroge Prometheus pour dessiner les tableaux de bord.

[^sre-borgmon]: Beyer et al., *Site Reliability Engineering*, 2016, chapitre 10, « Practical Alerting from Time-Series Data », qui décrit Borgmon et cite explicitement Prometheus comme son équivalent open source.

### 5.2 Pourquoi tirer plutôt que pousser ?

Prometheus **tire** les métriques (*pull*) au lieu de laisser les applications les pousser. Le choix a des conséquences pratiques :

- **Savoir qu'une cible est morte est gratuit** : si le scrape échoue, Prometheus le sait immédiatement (la série `up` passe à 0). Dans un modèle poussé, un service muet est indiscernable d'un service qui n'a rien à dire.
- **Le rythme est contrôlé par le collecteur**, qui ne peut pas être submergé par une application défaillante qui enverrait des milliers de points par seconde.
- **On peut interroger une cible à la main** avec `curl http://.../metrics` pour voir exactement ce que Prometheus verra.

La limite est symétrique : une tâche qui dure dix secondes (une sauvegarde nocturne) peut mourir avant d'avoir été interrogée. Pour ces cas, Prometheus fournit une passerelle, le **Pushgateway**, à laquelle la tâche pousse ses métriques avant de se terminer.

### 5.3 Le modèle de données

Une **série temporelle** est identifiée par un **nom de métrique** et un ensemble d'**étiquettes** (*labels*), paires clé-valeur. Chaque combinaison distincte d'étiquettes est une série à part. Voici un extrait de ce qu'expose le backend de Listify une fois instrumenté (section 7) :

```text title="GET /metrics (extrait)"
# HELP listify_http_requests_total Requêtes HTTP traitées
# TYPE listify_http_requests_total counter
listify_http_requests_total{method="GET",route="/api/tasks",status="200"} 1523
listify_http_requests_total{method="POST",route="/api/tasks",status="201"} 212
listify_http_requests_total{method="POST",route="/api/tasks",status="400"} 9
listify_http_requests_total{method="GET",route="/api/health",status="503"} 4
```

Quatre **types** de métriques existent, et le choix du type n'est pas décoratif, car il conditionne les calculs possibles :

| Type | Comportement | Exemple | Ce qu'on en calcule |
|---|---|---|---|
| **Counter** | Ne fait que croître (sauf remise à zéro au redémarrage) | Requêtes traitées | Un **débit**, avec `rate()` |
| **Gauge** | Monte et descend | Mémoire utilisée, connexions ouvertes | La valeur elle-même, des moyennes |
| **Histogram** | Compte les observations par tranches (*buckets*) cumulées | Durée des requêtes | Des **quantiles**, avec `histogram_quantile()` |
| **Summary** | Calcule des quantiles côté application | Durée des requêtes | Des quantiles, mais non agrégeables entre instances |

On préfère l'histogramme au summary dès qu'il y a plusieurs répliques : on ne peut pas faire la moyenne de trois quantiles 95 calculés séparément (le résultat n'est le quantile 95 de rien), alors qu'on peut additionner les tranches de trois histogrammes puis calculer le quantile global.

### 5.4 Le piège de la cardinalité

Chaque combinaison d'étiquettes crée une série, stockée et indexée séparément. Le nombre de séries, la **cardinalité**, est le premier facteur de coût de Prometheus, et une étiquette mal choisie peut le faire exploser.

:::exemple[Une étiquette de trop]
Le compteur de requêtes de Listify porte trois étiquettes. Comptons les séries dans le pire cas : 3 méthodes (GET, POST, DELETE), 3 routes (`/api/tasks`, `/api/tasks/<int:task_id>`, `/api/health`), 6 codes de statut rencontrés (200, 201, 204, 400, 404, 503), le tout sur 3 répliques (Prometheus ajoute l'étiquette `pod`) :

$$
3 \times 3 \times 6 \times 3 = 162 \text{ séries au plus.}
$$

C'est négligeable. Un développeur zélé ajoute maintenant une étiquette `user_id` pour « savoir qui fait quoi », avec 10 000 utilisateurs actifs :

$$
162 \times 10\,000 = 1\,620\,000 \text{ séries.}
$$

Avec quelques kilo-octets de mémoire par série active, Prometheus a besoin de plusieurs gigaoctets de plus, et les requêtes ralentissent. Même erreur, plus sournoise : utiliser le **chemin réel** (`/api/tasks/1`, `/api/tasks/2`, ...) au lieu du **modèle de route** (`/api/tasks/<int:task_id>`) crée une série par tâche jamais supprimée.

Règle : une étiquette doit prendre un **petit nombre de valeurs bornées**. Les identifiants d'utilisateur, de requête ou de session vont dans les **logs** et les **traces**, jamais dans les étiquettes des métriques.
:::

## 6. PromQL, le langage de requête

PromQL interroge les séries temporelles. Quelques constructions suffisent à couvrir l'essentiel des besoins.

### 6.1 Sélecteurs et vecteurs

- `listify_http_requests_total` sélectionne toutes les séries de ce nom : c'est un **vecteur instantané**, une valeur par série à l'instant de la requête.
- `listify_http_requests_total{route="/api/tasks", status=~"5.."}` filtre par étiquettes ; `=~` accepte une expression régulière, ici tous les codes 5xx.
- `listify_http_requests_total[5m]` est un **vecteur d'intervalle** : toutes les valeurs relevées sur les cinq dernières minutes, pour chaque série. On ne l'affiche pas directement ; on le passe à une fonction.

### 6.2 Du compteur au débit : `rate()`

Un compteur brut est inutilisable tel quel : qu'il vaille 1 523 ne dit rien, sinon depuis combien de temps le Pod tourne. Ce qui compte est sa **pente**. La fonction `rate()` calcule l'augmentation moyenne par seconde sur un intervalle.

:::exemple[Calculer un rate à la main]
Le compteur `listify_http_requests_total{route="/api/tasks", status="200", pod="backend-a"}` vaut 1 200 à 14 h 00 et 1 500 à 14 h 05. Alors :

$$
\text{rate}(\ldots[5\text{m}]) = \frac{1\,500 - 1\,200}{300 \text{ s}} = 1 \text{ requête par seconde.}
$$

Si le Pod redémarre à 14 h 03, son compteur repart de 0 : il passe par exemple de 1 380 à 0, puis monte à 120 à 14 h 05. `rate()` détecte la baisse, qui ne peut être qu'une remise à zéro, et la compense : l'augmentation vaut $(1\,380 - 1\,200) + 120 = 300$, et le débit reste 1 requête par seconde. C'est pourquoi on applique toujours `rate()` **avant** d'agréger, jamais l'inverse.
:::

### 6.3 Agréger : `sum by`

On additionne les séries en conservant certaines étiquettes :

```promql
# Débit total de l'API, toutes répliques confondues, par route
sum by (route) (rate(listify_http_requests_total[5m]))

# Taux d'erreurs : proportion des requêtes en 5xx
  sum(rate(listify_http_requests_total{status=~"5.."}[5m]))
/
  sum(rate(listify_http_requests_total[5m]))
```

La seconde requête est la plus importante du chapitre : c'est le **taux d'erreurs** des signaux dorés, un nombre entre 0 et 1 que l'alerte de la section 8 surveillera.

### 6.4 Quantiles de latence : `histogram_quantile()`

La **moyenne** de latence est un indicateur trompeur : si 95 % des requêtes prennent 50 ms et 5 % prennent 4 s, la moyenne vaut environ 250 ms, une valeur que personne n'a vécue. On raisonne en **quantiles** : le quantile 95 (p95) est la durée en dessous de laquelle se trouvent 95 % des requêtes. Un histogramme Prometheus stocke des compteurs cumulés par tranche (`le` signifie *less or equal*), et `histogram_quantile()` en déduit le quantile par interpolation linéaire à l'intérieur de la tranche concernée.

:::exemple[Calculer un p95 à la main]
Sur les cinq dernières minutes, l'histogramme de durée de Listify a enregistré 1 000 requêtes, réparties ainsi (compteurs **cumulés**) :

| Tranche `le` (secondes) | 0,1 | 0,25 | 0,5 | 1 | `+Inf` |
|---|---|---|---|---|---|
| Requêtes de durée inférieure ou égale | 600 | 900 | 980 | 995 | 1 000 |

Le p95 correspond au rang $0{,}95 \times 1\,000 = 950$. Il y a 900 requêtes sous 0,25 s et 980 sous 0,5 s : le rang 950 tombe dans la tranche $]0{,}25 ; 0{,}5]$, qui contient $980 - 900 = 80$ requêtes. En supposant ces 80 requêtes réparties uniformément dans la tranche, le rang 950 est la $950 - 900 = 50$ᵉ d'entre elles :

$$
p_{95} = 0{,}25 + \frac{50}{80} \times (0{,}5 - 0{,}25) = 0{,}25 + 0{,}156 \approx 0{,}41 \text{ s.}
$$

En PromQL, pour toutes les répliques :

```promql
histogram_quantile(0.95,
  sum by (le) (rate(listify_http_request_duration_seconds_bucket[5m])))
```

L'interpolation suppose une répartition uniforme dans la tranche : la précision dépend donc du choix des bornes, qu'on resserre autour des valeurs qui comptent (ici, autour de l'objectif de latence).
:::

## 7. Instrumenter Listify

La bibliothèque officielle `prometheus_client` fournit les types de métriques et la génération du format d'exposition. L'instrumentation de Listify tient en quelques lignes : on mesure chaque requête au moment où la réponse part.

```python title="backend/app.py (ajouts)"
import time

from flask import g
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

REQUESTS = Counter(
    "listify_http_requests_total", "Requêtes HTTP traitées",
    ["method", "route", "status"],
)
LATENCY = Histogram(
    "listify_http_request_duration_seconds", "Durée de traitement des requêtes",
    ["route"], buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5),
)

@app.before_request
def _start_timer():
    g.start = time.perf_counter()

@app.after_request
def _record(response):
    # le modèle de route, pas le chemin réel : cardinalité bornée (section 5.4)
    route = request.url_rule.rule if request.url_rule else "non_trouvee"
    REQUESTS.labels(request.method, route, str(response.status_code)).inc()
    LATENCY.labels(route).observe(time.perf_counter() - g.start)
    return response

@app.get("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}
```

:::warning[Gunicorn et ses workers]
Ce code fonctionne tel quel avec le serveur de développement de Flask, mais **pas** avec Gunicorn et ses trois workers (chapitre 4). Chaque worker est un processus distinct, avec **ses propres** compteurs en mémoire ; quand Prometheus interroge `/metrics`, c'est un worker au hasard qui répond, avec un tiers des requêtes seulement, et les compteurs semblent sauter d'un scrape à l'autre. `prometheus_client` prévoit un **mode multiprocessus** : chaque worker écrit ses valeurs dans des fichiers d'un répertoire partagé (variable `PROMETHEUS_MULTIPROC_DIR`), et `/metrics` agrège les fichiers de tous les workers. Vous le mettrez en place au TP 21 ; c'est un excellent exemple de ce que la connaissance des couches inférieures (ici le modèle de processus de Gunicorn) évite comme erreurs de mesure.
:::

Du côté du cluster, on n'écrit pas la configuration de Prometheus à la main. La pile **kube-prometheus-stack**, installée par Helm au TP 21, fournit un opérateur qui introduit une ressource **ServiceMonitor** : on déclare « surveille les Services qui portent l'étiquette `app: listify`, sur le port nommé `http`, au chemin `/metrics` », et l'opérateur génère la configuration de Prometheus. La surveillance devient elle-même un manifest déclaratif, versionné dans le dépôt de configuration et déployé par Argo CD.

## 8. Alerter

### 8.1 Des règles d'alerte

Une alerte Prometheus est une requête PromQL assortie d'une durée : si la condition reste vraie pendant toute la durée, l'alerte se déclenche.

```yaml title="Règle d'alerte (extrait d'une ressource PrometheusRule)"
- alert: ListifyTauxErreursEleve
  expr: |
      sum(rate(listify_http_requests_total{status=~"5.."}[5m]))
    / sum(rate(listify_http_requests_total[5m])) > 0.05
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "Plus de 5 % des requêtes de Listify échouent depuis 5 minutes"
```

La clause `for: 5m` évite de réveiller quelqu'un pour un pic isolé de quelques secondes : l'alerte passe d'abord à l'état `pending`, puis à `firing` si la condition persiste. Alertmanager se charge ensuite du reste : **regrouper** les alertes liées (cinquante Pods en erreur ne doivent pas produire cinquante notifications), **inhiber** les alertes secondaires quand une alerte principale est active (inutile d'alerter sur l'API si le nœud entier est tombé), **mettre en sourdine** pendant une maintenance, et **router** selon la gravité.

### 8.2 Alerter sur les symptômes

La règle la plus importante porte sur **ce qui** déclenche une alerte. Rob Ewaschuk, ingénieur de fiabilité chez Google, l'a formulée dans un texte devenu classique : alerter sur les **symptômes**, ce que les utilisateurs subissent, plutôt que sur les **causes** possibles [^ewaschuk].

| Alerte sur une cause | Alerte sur un symptôme |
|---|---|
| « Le CPU d'un nœud dépasse 90 % » | « Le p95 de latence dépasse 500 ms » |
| « Un Pod a redémarré » | « Plus de 5 % des requêtes échouent » |
| « La base a 80 connexions ouvertes » | « L'ajout de tâches échoue » |

Un CPU à 90 % qui ne dégrade rien pour personne ne justifie pas un réveil à 3 h du matin ; un Pod qui redémarre est précisément ce que Kubernetes gère tout seul. Les alertes sur les causes produisent une **fatigue d'alerte** : trop de notifications non actionnables, que l'équipe finit par ignorer, y compris la bonne. Toute alerte qui réveille un humain doit être **urgente**, **actionnable** et **liée à un impact utilisateur**. Les causes restent utiles, mais sur les tableaux de bord, pour le diagnostic.

[^ewaschuk]: Rob Ewaschuk, « My Philosophy on Alerting », 2014, repris dans Beyer et al., *Site Reliability Engineering*, 2016, chapitre 6.

## 9. SLI, SLO et budget d'erreur

### 9.1 Trois sigles à ne pas confondre

Le livre SRE de Google a donné un vocabulaire précis à une question essentielle : **quel niveau de fiabilité vise-t-on ?** [^sre-slo]

:::definition[SLI, SLO, SLA]
- Un **SLI** (*service level indicator*) est une **mesure** quantitative d'un aspect du service, idéalement exprimée en proportion de bons événements : « proportion des requêtes servies avec succès », « proportion des requêtes servies en moins de 300 ms ».
- Un **SLO** (*service level objective*) est une **cible** pour un SLI sur une période : « 99,9 % des requêtes réussies sur 30 jours glissants ».
- Un **SLA** (*service level agreement*) est un **contrat** avec des clients, assorti de conséquences (pénalités, remboursements) si l'objectif n'est pas tenu.
:::

On fixe toujours le SLO **plus exigeant** que le SLA : l'écart est une marge qui permet de réagir avant de payer des pénalités. Et l'on ne vise jamais 100 % : ce serait impossible à tenir (le réseau de l'utilisateur lui-même n'est pas fiable à 100 %), ruineux à approcher, et cela interdirait tout changement, puisque chaque déploiement comporte un risque.

[^sre-slo]: Beyer et al., *Site Reliability Engineering*, 2016, chapitre 4, « Service Level Objectives », et chapitre 3, « Embracing Risk ».

### 9.2 Le budget d'erreur

Si l'objectif est 99,9 % de requêtes réussies, alors 0,1 % d'échecs sont **acceptés**. Cette marge s'appelle le **budget d'erreur**, et c'est l'idée la plus féconde du chapitre : elle transforme la fiabilité, sujet de disputes entre développeurs (qui veulent déployer) et exploitants (qui veulent la stabilité), en une ressource commune qu'on **dépense**.

:::exemple[Ce que représente un budget d'erreur]
Sur une fenêtre de 30 jours, soit $30 \times 24 \times 60 = 43\,200$ minutes :

| SLO | Budget (proportion) | Indisponibilité totale équivalente sur 30 jours |
|---|---|---|
| 99 % | 1 % | $432$ min, soit 7 h 12 |
| 99,9 % | 0,1 % | $43{,}2$ min |
| 99,95 % | 0,05 % | $21{,}6$ min |
| 99,99 % | 0,01 % | $4{,}32$ min |

Chaque « 9 » supplémentaire divise le budget par dix, et coûte beaucoup plus cher à tenir. En raisonnant en requêtes plutôt qu'en temps : si Listify reçoit 10 millions de requêtes en 30 jours avec un SLO de 99,9 %, le budget vaut $10^7 \times 0{,}001 = 10\,000$ requêtes en échec.

Tant qu'il reste du budget, l'équipe déploie librement, expérimente, prend des risques mesurés. Quand le budget est épuisé, une **politique de budget d'erreur**, décidée à l'avance, s'applique : gel des nouvelles fonctionnalités, priorité aux corrections de fiabilité, jusqu'à ce que la fenêtre glissante redonne de la marge.
:::

<Figure src="slo-budget" num="26.3" alt="Courbe du budget d'erreur restant sur 30 jours : il décroît lentement, chute de 46 % au jour 12 lors d'un incident de 20 minutes, puis continue de décroître lentement ; un seuil de prudence à 25 % est indiqué.">
  Le budget d'erreur d'un SLO de 99,9 % sur 30 jours (illustration). Un seul incident de 20 minutes consomme près de la moitié du budget du mois ; le seuil de prudence déclenche un ralentissement des mises en production avant l'épuisement.
</Figure>

### 9.3 Alerter sur le taux de consommation

Le budget d'erreur fournit aussi la meilleure façon d'alerter. Plutôt qu'un seuil arbitraire (« plus de 5 % d'erreurs »), on surveille le **taux de consommation** (*burn rate*) : la vitesse à laquelle on dépense le budget, rapportée à la vitesse qui l'épuiserait exactement à la fin de la fenêtre. Un taux de consommation de 1 dépense tout le budget en 30 jours ; un taux de 10 le dépense en 3 jours.

:::exemple[Un seuil d'alerte déduit du SLO]
Le *Site Reliability Workbook* de Google propose de déclencher une alerte urgente quand **2 % du budget mensuel** est consommé en **une heure** [^sre-workbook]. Quel taux de consommation cela représente-t-il ? Une fenêtre de 30 jours compte 720 heures ; au rythme nominal (taux 1), une heure consomme $1/720 \approx 0{,}14\,\%$ du budget. Consommer 2 % en une heure, c'est donc aller :

$$
\frac{2\,\%}{1/720} = 0{,}02 \times 720 = 14{,}4 \text{ fois plus vite que le rythme nominal.}
$$

Pour un SLO de 99,9 %, un taux de consommation de 14,4 correspond à un taux d'erreurs de $14{,}4 \times 0{,}1\,\% = 1{,}44\,\%$. À ce rythme, le budget du mois serait épuisé en $720 / 14{,}4 = 50$ heures, un peu plus de deux jours : cela justifie de réveiller quelqu'un. Un taux d'erreurs de 0,2 % (taux de consommation 2) mérite en revanche un ticket, pas un réveil nocturne. Le seuil n'est plus arbitraire : il découle de l'objectif.
:::

[^sre-workbook]: Betsy Beyer, Niall Richard Murphy, David K. Rensin, Kent Kawahara, Stephen Thorne (dir.), *The Site Reliability Workbook*, O'Reilly, 2018, chapitre 5, « Alerting on SLOs ». Gratuit en ligne : [sre.google/workbook/alerting-on-slos](https://sre.google/workbook/alerting-on-slos/).

## 10. Grafana et le reste de la pile

**Grafana** est l'outil de visualisation qui accompagne presque toujours Prometheus. Un tableau de bord est un ensemble de panneaux, chacun alimenté par une requête PromQL : débit par route, taux d'erreurs, p50 et p95 de latence, Pods prêts, redémarrages. Un bon tableau de bord de service suit la méthode RED en haut (ce que vivent les utilisateurs) et les ressources en dessous (ce qui peut l'expliquer), et marque les déploiements par des annotations verticales : la question « est-ce lié au déploiement de 14 h ? » se tranche alors d'un coup d'œil.

La pile s'étend naturellement aux deux autres signaux : **Loki** agrège les logs avec les mêmes étiquettes que Prometheus, **Tempo** ou **Jaeger** stockent les traces, et Grafana permet de passer d'un pic sur une courbe aux logs puis aux traces de la même période. Ce cours s'en tient aux métriques ; le semestre 3 y ajoutera la surveillance propre aux modèles d'apprentissage automatique, dont la dégradation silencieuse (la dérive des données) ne produit aucune erreur HTTP.

## Ce qu'il faut retenir

<div className="retenir">

1. La **surveillance** vérifie des conditions connues ; l'**observabilité** est la propriété de pouvoir déduire l'état interne des sorties, et répondre à des questions imprévues.
2. **Logs** (événements riches, coûteux), **métriques** (nombres agrégés, économes, base de la surveillance), **traces** (parcours d'une requête, où passe le temps ; Dapper, OpenTelemetry). Leur valeur vient de leur corrélation.
3. Mesurer les **quatre signaux dorés** (latence, trafic, erreurs, saturation) ; **RED** pour les services, **USE** pour les ressources.
4. **Prometheus** tire (`/metrics`, scrape périodique) et stocke des séries identifiées par un nom et des **étiquettes**. Types : **counter**, **gauge**, **histogram**, summary. Une étiquette doit avoir **peu de valeurs** : la cardinalité est le premier coût.
5. **PromQL** : `rate()` sur les compteurs, **avant** d'agréger ; `sum by` ; `histogram_quantile()` pour les quantiles, par interpolation dans les tranches. La moyenne de latence ment, le p95 non.
6. Avec Gunicorn, activer le **mode multiprocessus** de `prometheus_client`, sinon chaque worker ne compte qu'une partie des requêtes.
7. **Alerter sur les symptômes**, pas sur les causes ; toute alerte doit être urgente, actionnable, liée à l'utilisateur.
8. **SLI** (mesure), **SLO** (cible), **SLA** (contrat). Le **budget d'erreur** (99,9 % sur 30 jours = 43,2 min) se dépense ; on alerte sur le **taux de consommation** (14,4 = 2 % du budget en une heure).

</div>

## Regard recherche

:::recherche
L'observabilité des systèmes distribués est un domaine de recherche actif, dont plusieurs articles fondateurs sont très accessibles :

- **Benjamin H. Sigelman et al., « Dapper, a Large-Scale Distributed Systems Tracing Infrastructure », Google Technical Report, 2010.** L'article fondateur du traçage distribué : propagation d'identifiants, échantillonnage, surcoût mesuré. Tous les outils actuels, jusqu'à OpenTelemetry, en descendent.
- **Tuomas Pelkonen et al., « Gorilla: A Fast, Scalable, In-Memory Time Series Database », *VLDB*, 2015.** La base de séries temporelles de Facebook et ses techniques de compression (valeurs successives codées par différences et par ou exclusif), dont s'est inspiré le moteur de stockage de Prometheus 2.
- **Jonathan Kaldor et al., « Canopy: An End-to-End Performance Tracing and Analysis System », *SOSP*, 2017.** Le traçage à l'échelle de Facebook, du navigateur jusqu'aux serveurs, et l'analyse de milliards de traces.
- **Jonathan Mace, Ryan Roelke, Rodrigo Fonseca, « Pivot Tracing: Dynamic Causal Monitoring for Distributed Systems », *SOSP*, 2015** (prix du meilleur article). Comment poser à un système en production des questions nouvelles sans le redéployer : l'idéal de l'observabilité, rendu opérationnel.

Piste d'innovation : la **détection d'anomalies** et l'**analyse de causes racines automatiques** sur des milliers de séries temporelles, sans noyer les équipes sous les faux positifs, sont des sujets de recherche très actifs, qui font dialoguer systèmes distribués, statistique et apprentissage automatique.
:::

## Bibliographie du chapitre

<div className="biblio">

### Sources primaires

- Betsy Beyer, Chris Jones, Jennifer Petoff, Niall Richard Murphy (dir.), *Site Reliability Engineering*, O'Reilly, 2016, chapitres 3, 4, 6 et 10. Gratuit en ligne : [sre.google/sre-book](https://sre.google/sre-book/table-of-contents/).
- Documentation de Prometheus : [prometheus.io/docs](https://prometheus.io/docs/introduction/overview/). En particulier « Data model », « Metric types », « Querying basics » et « Histograms and summaries ».
- Documentation OpenTelemetry, « Observability primer » : [opentelemetry.io/docs/concepts](https://opentelemetry.io/docs/concepts/observability-primer/).

### Lectures recommandées

- Betsy Beyer et al. (dir.), *The Site Reliability Workbook*, O'Reilly, 2018, chapitres 2 (« Implementing SLOs ») et 5 (« Alerting on SLOs »).
- Brian Brazil, *Prometheus: Up & Running*, O'Reilly, 2ᵉ éd. (avec Julien Pivotto), 2023.
- Charity Majors, Liz Fong-Jones, George Miranda, *Observability Engineering*, O'Reilly, 2022. Le point de vue « observabilité » au-delà des trois piliers.

### Pour aller plus loin

- Les articles de la rubrique « Regard recherche ».
- Brendan Gregg, *Systems Performance*, 2ᵉ éd., Addison-Wesley, 2020 : la référence sur l'analyse de performance, dont la méthode USE.

</div>
