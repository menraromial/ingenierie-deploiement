# Chapitre 8 : Répartition de charge

!!! abstract "Objectifs du chapitre"
    À l'issue de ce chapitre, vous saurez :

    - expliquer ce qu'est un répartiteur de charge, en distinguant niveau 4 et niveau 7 ;
    - choisir un algorithme de répartition en connaissant les hypothèses de chacun ;
    - expliquer pourquoi l'horizontal exige le *stateless*, et où mettre l'état sinon ;
    - distinguer health checks passifs et actifs, configurer les premiers dans Nginx, et raisonner les *retries* (et leur lien avec l'idempotence) ;
    - lire une configuration équivalente en Nginx et en HAProxy.

## 1. Le problème et l'abstraction

Le TP 6 ajoute un deuxième backend. Immédiatement, une question sans réponse évidente : le frontend appelle `/api/...`, mais **vers laquelle des deux machines** ? On ne va pas mettre deux URL dans le JavaScript : le client ne doit pas connaître la topologie (il ne la connaît déjà pas, grâce au chemin relatif du ch. 4, décision qui paie aujourd'hui).

La réponse est le **répartiteur de charge** (*load balancer*, LB) : un composant qui expose **une** adresse et distribue les requêtes reçues vers un **pool** de serveurs interchangeables. C'est l'abstraction qui rend la montée en charge horizontale invisible aux clients ; c'est aussi elle qui rend la **panne** d'un membre du pool invisible, et cette seconde vertu est en pratique la plus précieuse.

### 1.1 Niveau 4 ou niveau 7 : que voit le répartiteur ?

| | LB de **niveau 4** (transport) | LB de **niveau 7** (application) |
|---|---|---|
| Il voit | Des connexions TCP/UDP : adresses et ports | Des **requêtes HTTP** : chemins, en-têtes, cookies |
| Il peut donc | Répartir des connexions, très vite | Router par URL (`/api/` vs `/`), réécrire des en-têtes, terminer TLS, réessayer une requête ailleurs |
| Exemples | HAProxy en mode `tcp`, LVS/IPVS, NLB d'AWS | **Nginx**, HAProxy en mode `http`, Traefik, ALB d'AWS |

Notre Nginx travaille au niveau 7 : il fait déjà du routage par chemin depuis le TP 3 ; au TP 6, son bloc `location /api/` cessera de pointer vers *un* serveur pour pointer vers un *pool*. Un LB de niveau 4 réapparaîtra au S2 : le `Service` de Kubernetes est, conceptuellement, un LB de niveau 4 distribué.

### 1.2 Et qui répartit vers les répartiteurs ?

Question à toujours poser : notre LB est lui-même **un point de défaillance unique**. Réponses de l'industrie, à connaître en notions : une **adresse IP virtuelle** partagée entre deux LB (protocole VRRP, outil keepalived : le survivant reprend l'adresse), la répartition **DNS** (plusieurs enregistrements A), et l'**anycast** aux très grandes échelles. Le TP assume son LB unique : à notre niveau de disponibilité, c'est un choix documenté, pas un oubli, et savoir *écrire cette phrase* dans un dossier d'architecture fait partie de la compétence C1.

## 2. Les algorithmes de répartition

L'algorithme décide « quelle requête va où ». Chacun optimise sous une hypothèse ; l'examen attend l'hypothèse autant que la définition.

| Algorithme | Principe | Hypothèse implicite | Quand il se trompe |
|---|---|---|---|
| **Round-robin** | Chacun son tour, en boucle | Requêtes de coût comparable, serveurs identiques | Une requête lente « bouche » un serveur qui continue pourtant de recevoir sa part |
| **Round-robin pondéré** | Chacun son tour, proportionnellement à un poids | Serveurs de capacités inégales mais connues | Les poids sont statiques, la réalité non |
| **Least connections** | Vers le serveur ayant le moins de connexions en cours | Le nombre de connexions reflète la charge | Connexions nombreuses mais légères (keep-alive) faussent la mesure |
| **Hachage d'IP** (`ip_hash`) | La même IP client va toujours au même serveur | Le client doit « retrouver » son serveur (sessions locales) | Des clients derrière un même NAT s'entassent sur un serveur ; la panne d'un serveur redistribue son segment |

Round-robin est le défaut de Nginx et le choix du TP : sans information sur le coût des requêtes, c'est le moins mauvais des choix simples. `least_conn` (une directive à ajouter) devient pertinent quand les temps de réponse varient beaucoup. Quant à `ip_hash`, c'est presque toujours le symptôme d'un problème plus profond : des sessions stockées au mauvais endroit. Voyons cela.

## 3. Sessions et statelessness : la condition de l'horizontal

### 3.1 Le scénario catastrophe

Imaginez Listify avec des comptes utilisateurs, dont les sessions (qui est connecté) seraient stockées **en mémoire du backend**. Round-robin : la requête de connexion arrive sur app1, qui mémorise la session ; la requête suivante part sur app2... qui ne connaît pas l'utilisateur. Déconnexion aléatoire une fois sur deux. Les « solutions » de contournement (coller chaque client à son serveur : `ip_hash`, cookies d'affinité, *sticky sessions*) fonctionnent, mais ruinent les deux promesses du LB : la charge ne se répartit plus uniformément, et la panne d'un serveur emporte ses sessions.

### 3.2 La vraie solution : externaliser l'état

Le principe, qui est le **facteur VI** des 12-factor apps (« Processes : exécuter l'application comme un ou plusieurs processus *sans état* ») : un backend ne doit rien retenir entre deux requêtes ; tout état durable vit dans un **service externe** partagé, la base de données, un cache (Redis), ou chez le client (cookie signé, jetons type JWT). Alors n'importe quelle requête peut aller sur n'importe quel backend, et ajouter ou perdre un backend est un non-événement.

Listify est *déjà* stateless : chaque requête ouvre sa transaction PostgreSQL, rien ne vit en mémoire entre deux appels. Ce n'était pas un hasard mais une décision de conception du fil rouge : au TP 6, le deuxième backend fonctionnera **sans modifier une ligne de code**. Mesurez la portée de la règle : le *stateless* est la propriété qui rend possibles, en cascade, la répartition de charge (ce chapitre), les remplacements de conteneurs (S2) et l'autoscaling (S2-S3).

## 4. Health checks : ne pas envoyer de clients dans un mur

### 4.1 Passif ou actif

Un LB qui répartit « en aveugle » enverra une requête sur deux vers un backend mort. Deux stratégies pour l'éviter :

Vérification **passive**
:   Le LB observe le trafic réel : les requêtes qui échouent (connexion refusée, timeout, 5xx) comptent contre le serveur ; au-delà d'un seuil, il est **exclu temporairement** du pool, puis retenté après un délai. Aucun trafic supplémentaire, mais il faut « sacrifier » quelques vraies requêtes pour détecter la panne. C'est le mécanisme de Nginx open source : `max_fails` et `fail_timeout`.

Vérification **active**
:   Le LB sonde lui-même chaque serveur à intervalle régulier (une connexion TCP, ou une requête HTTP sur une URL de santé, votre `/api/health` du TP 2 trouve ici sa vraie vocation), et sort du pool quiconque échoue N fois. Détection plus rapide et sans sacrifier de clients, au prix d'un trafic de sonde. C'est le mode standard de HAProxy (`check inter 2s fall 3 rise 2`) ; dans Nginx, les sondes actives sont réservées à la version commerciale.

Les deux se combinent en production. Retenez aussi la nuance du TP 4 : une sonde `/api/health` ne vaut que ce qu'elle vérifie réellement (la vôtre teste la connexion à la base, pas l'existence des tables...).

### 4.2 Les retries, et le retour de l'idempotence

Exclure un serveur, c'est bien ; que faire de la requête qui **vient d'échouer** ? Nginx sait la **rejouer** sur le serveur suivant (`proxy_next_upstream`) : l'utilisateur ne voit rien du tout. Mais attention, question d'examen garantie : peut-on rejouer *n'importe quelle* requête ?

Non, et le critère a un nom que vous connaissez : l'**idempotence**. Rejouer un `GET /api/tasks` est sans risque. Rejouer un `POST /api/tasks` dont on n'a jamais reçu la réponse peut créer la tâche **deux fois** : le premier serveur l'avait peut-être insérée avant de mourir. C'est pourquoi, par défaut, Nginx ne rejoue pas les requêtes « non idempotentes » (POST, PATCH...) sur erreur en cours de traitement : il faut l'autoriser explicitement (`non_idempotent`), en sachant ce qu'on fait. L'idempotence, rencontrée au TP 2 comme propriété d'un script SQL, se révèle ici propriété **de protocole** ; au bloc 3, elle deviendra propriété d'outil (Ansible). Même concept, trois échelles.

## 5. Nginx et HAProxy : la configuration de référence

Les deux outils dominants, sur le même besoin (notre TP 6), pour apprendre à lire l'un et l'autre :

=== "Nginx (utilisé au TP 6)"

    ```nginx
    # Dans /etc/nginx/sites-available/listify
    upstream listify_backend {
        # round-robin par défaut ; décommenter pour least connections :
        # least_conn;
        server 192.168.56.21:8000 max_fails=3 fail_timeout=10s;
        server 192.168.56.22:8000 max_fails=3 fail_timeout=10s;
    }

    server {
        # ... (TLS et statiques inchangés)
        location /api/ {
            proxy_pass http://listify_backend;
            # rejouer sur le serveur suivant si échec de connexion/5xx :
            proxy_next_upstream error timeout http_502 http_503;
            # diagnostic TP : savoir QUI a répondu
            add_header X-Upstream $upstream_addr always;
            proxy_set_header Host              $host;
            proxy_set_header X-Real-IP         $remote_addr;
            proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
    ```

    `max_fails=3 fail_timeout=10s` se lit : 3 échecs dans une fenêtre de 10 s → serveur exclu 10 s, puis retenté. C'est la vérification passive du §4.1.

=== "HAProxy (équivalent, bonus du TP 6)"

    ```text
    # /etc/haproxy/haproxy.cfg (extrait)
    defaults
        mode http
        timeout connect 5s
        timeout client  30s
        timeout server  30s

    frontend listify_front
        bind *:8000
        default_backend listify_backend

    backend listify_backend
        balance roundrobin
        option httpchk GET /api/health        # sonde ACTIVE sur notre endpoint
        server app1 192.168.56.21:8000 check inter 2s fall 3 rise 2
        server app2 192.168.56.22:8000 check inter 2s fall 3 rise 2

    listen stats                               # tableau de bord intégré
        bind *:8404
        stats enable
        stats uri /
    ```

    `check inter 2s fall 3 rise 2` : sonde toutes les 2 s, exclu après 3 échecs, réintégré après 2 succès. La page `stats` montre l'état du pool en direct : le meilleur outil pédagogique du bonus TP 6.

Comment choisir, en une règle : **Nginx** quand on a déjà Nginx (TLS + statiques + un peu de LB : notre cas exactement) ; **HAProxy** quand la répartition est le métier principal du composant (finesse des checks, observabilité intégrée, niveau 4 et 7). Les deux se rencontrent partout en production, souvent ensemble.

## Ce qu'il faut retenir

1. Le LB expose une adresse pour un pool ; il rend l'échelle **et les pannes** invisibles. Niveau 4 = connexions ; niveau 7 = requêtes HTTP (routage, TLS, retries). Le LB lui-même est un SPOF : VRRP/keepalived, DNS, anycast en notions.
2. Algorithmes = hypothèses : round-robin (coûts homogènes), pondéré (capacités connues), least_conn (connexions ≈ charge), ip_hash (affinité, presque toujours un pis-aller).
3. **Pas d'horizontal sans stateless** (facteur VI) : l'état vit dans les services externes ou chez le client, jamais en mémoire d'un backend. Listify l'est par conception : le TP 6 ne change pas le code.
4. Health checks passifs (Nginx : `max_fails`/`fail_timeout`, sacrifie quelques requêtes) vs actifs (HAProxy : `check`, sonde `/api/health`). Les retries (`proxy_next_upstream`) ne sont sûrs que pour les requêtes **idempotentes** : l'idempotence est ici une propriété de protocole.
5. Savoir lire les deux configurations de référence ; Nginx si le LB est accessoire, HAProxy s'il est central.

## Bibliographie du chapitre

### Sources primaires

- Documentation Nginx : module `ngx_http_upstream_module` (directives `upstream`, `server`, `max_fails`, `least_conn`) et `proxy_next_upstream`. [nginx.org/en/docs](https://nginx.org/en/docs/http/ngx_http_upstream_module.html).
- HAProxy, *Configuration Manual* (sections `balance`, `option httpchk`, `check`) : [docs.haproxy.org](https://docs.haproxy.org/). Dense mais faisant autorité.
- RFC 9110, *HTTP Semantics*, section 9.2.2 « Idempotent Methods » : la base normative du §4.2.
- Adam Wiggins, *The Twelve-Factor App*, facteur VI « Processes » : [12factor.net/fr/processes](https://12factor.net/fr/processes).

### Lectures recommandées

- Betsy Beyer et al., *Site Reliability Engineering*, chapitres 19 (« Load Balancing at the Frontend ») et 20 (« Load Balancing in the Datacenter ») : du DNS mondial au sous-ensemble de connexions, la version grande échelle de ce chapitre. [Gratuit en ligne](https://sre.google/sre-book/load-balancing-frontend/).
- Willy Tarreau (auteur de HAProxy), « Make applications scalable with load balancing » : article de fond du créateur de l'outil.

### Pour aller plus loin

- Le *consistent hashing* (hachage cohérent) : l'algorithme qui corrige le défaut de redistribution d'`ip_hash` ; papier d'origine Karger et al., STOC 1997, et son usage dans les caches distribués.
- keepalived et VRRP (RFC 5798) : montez en bonus une IP virtuelle entre deux Nginx et tuez le maître.
