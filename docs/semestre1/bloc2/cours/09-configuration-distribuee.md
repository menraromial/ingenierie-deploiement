# Chapitre 9 : Le problème de la configuration distribuée

!!! abstract "Objectifs du chapitre"
    À l'issue de ce chapitre, vous saurez :

    - définir le *configuration drift* et en citer les causes et les symptômes ;
    - expliquer les métaphores fondatrices du domaine : serveurs « flocons de neige », *pets vs cattle*, serveurs phénix ;
    - formuler le cahier des charges d'une gestion de configuration digne de ce nom, celui que le bloc 3 remplira.

    C'est le chapitre-charnière du semestre : court en pages, décisif en idées. Il donne des noms à ce que les TP 5 et 6 vous auront fait vivre.

## 1. L'inventaire honnête du bloc 2

Commençons par compter ce que la « simple » architecture des TP 5-6 vous a demandé d'entretenir à la main :

| Machine | Fichiers et états configurés à la main |
|---|---|
| Les 4 VM | hostname, netplan (IP statique), `/etc/hosts` (4 entrées), sshd durci, ufw, clés SSH |
| listify-db | `postgresql.conf` (listen_addresses), `pg_hba.conf` (une ligne **par backend**), rôle et base SQL, données restaurées, timer de sauvegarde |
| listify-app1 et app2 | utilisateur système, `/opt/listify`, venv + dépendances, `listify.env`, unité systemd, règle ufw vers la base |
| listify-lb | Nginx (site, upstream avec **une ligne par backend**), certificat TLS, statiques |
| Le poste hôte | `/etc/hosts`, `~/.ssh/config` (4 entrées) |

Deux observations, qui sont tout le chapitre :

1. **L'information est dupliquée.** L'adresse de app2 existe en au moins six endroits (netplan de app2, /etc/hosts × 5, pg_hba, upstream Nginx, ufw de la base, votre runbook). Toute duplication non synchronisée mécaniquement finira par diverger : c'est une loi, pas un pessimisme.
2. **Le coût est linéaire en machines, l'erreur est combinatoire.** Ajouter le backend 2 (TP 6) a exigé de toucher la base, le LB et tous les fichiers hosts ; en oublier **un seul** produit une panne qui ne touche qu'un chemin, la pire espèce à diagnostiquer.

## 2. Le configuration drift

### 2.1 Définition

**Dérive de configuration** (*configuration drift*)
:   Divergence progressive entre l'état réel des serveurs et leur état supposé (ce que dit la documentation, ce que croit l'équipe, ce qu'il y a sur les autres serveurs du même rôle). Terme popularisé par la littérature Infrastructure as Code, notamment Kief Morris.[^1]

[^1]: Kief Morris, *Infrastructure as Code*, 2ᵉ éd., O'Reilly, 2020, chapitre 1 ; la formule voisine de « snowflake server » vient de Martin Fowler (bliki, 2012).

### 2.2 D'où vient la dérive ? De gestes tous légitimes

Le drift n'est pas le produit de la négligence mais de l'exploitation **normale** :

- le correctif urgent appliqué à 2 h du matin directement sur app1 (« on documentera demain ») ;
- la mise à jour de paquets faite sur app1 un mardi, sur app2 « bientôt » ;
- le paramètre de debug activé « temporairement » pendant un diagnostic, jamais retiré ;
- le collègue qui configure app2 d'après un runbook légèrement périmé, celui d'avant le correctif de 2 h du matin ;
- et le temps qui passe : deux machines identiques au jour J divergent au jour J+180 par la seule accumulation de ces micro-écarts.

### 2.3 Ce que ça coûte

Le symptôme classique : **« ça marche sur app1, pas sur app2 »**, alors que les deux sont « pareilles ». Les conséquences s'enchaînent : les diagnostics s'allongent (il faut d'abord établir *en quoi* les machines diffèrent), les mises à jour deviennent risquées (chaque serveur réagit différemment), la répartition de charge perd son sens (les serveurs du pool ne sont plus interchangeables, hypothèse de **tous** les algorithmes du ch. 8), et surtout : plus personne ne sait reconstruire la machine, puisque son état ne correspond plus à aucune documentation. Vous avez déjà éprouvé ce dernier point en solo au défi du bloc 1 ; le drift en est la version continue et multi-machines.

## 3. Les métaphores qui ont structuré le métier

### 3.1 Le serveur flocon de neige

Un **serveur flocon de neige** (*snowflake server*, Fowler) est unique en son genre, comme un flocon : configuré à la main au fil des ans, impossible à reproduire, et que tout le monde a peur de toucher, précisément parce qu'il est irremplaçable. Le drift est le processus ; le flocon en est le résultat final. Votre `listify-s1` du bloc 1 était déjà, à petite échelle, un flocon : le défi des 30 minutes l'a prouvé.

### 3.2 Pets vs cattle

La métaphore la plus célèbre du domaine, popularisée au début des années 2010 (on l'attribue à Bill Baker, de Microsoft, puis Randy Bias l'a diffusée dans le monde du cloud, et les ingénieurs du CERN l'ont portée dans leurs présentations d'exploitation à grande échelle)[^2] :

[^2]: Randy Bias, « The History of Pets vs Cattle and How to Use the Analogy Properly », billet, 2016 : l'histoire de l'expression par celui qui l'a répandue.

**Animaux de compagnie** (*pets*)
:   Chaque serveur a un nom, une histoire, des soins individuels ; quand il est malade, **on le soigne**, aussi longtemps qu'il faut. C'est le mode d'exploitation du bloc 1... et encore du bloc 2.

**Bétail** (*cattle*)
:   Les serveurs sont numérotés, identiques, produits en série depuis une définition commune ; quand l'un est malade, **on le remplace** et le troupeau n'a rien senti. Soigner un individu n'a plus de sens économique : le reconstruire coûte moins cher que le diagnostiquer.

Le passage de l'un à l'autre n'est pas une question de goût mais de **nombre et d'exigence de disponibilité** : on ne soigne pas individuellement 200 machines. Et il a une condition d'entrée stricte : le mode bétail exige de savoir **reconstruire une machine à l'identique, vite, sans humain**. Ce que, précisément, vous ne savez pas encore faire.

### 3.3 Le serveur phénix

Corollaire opérationnel (Fowler encore) : le **serveur phénix** est reconstruit régulièrement depuis sa définition, *même sans panne*, pour empêcher le drift de s'accumuler : il renaît de ses cendres, d'où le nom. Poussée au bout, l'idée devient l'**infrastructure immuable** : on ne modifie plus jamais un serveur en place, toute modification est une reconstruction. Gardez ce fil : il mène droit aux images de conteneurs du S2, qui sont des phénix parfaits (on ne modifie pas un conteneur, on le remplace).

## 4. Le cahier des charges que vous venez d'écrire

Au défi du bloc 1, la section 4 de votre compte rendu esquissait l'outil idéal. Les TP 5-6 permettent de le formuler complètement. Pour dompter une infrastructure multi-machines, il faut que sa configuration soit :

1. **Écrite dans des fichiers**, pas dans des mémoires humaines ni des historiques shell : la source de vérité est lisible et partageable ;
2. **Versionnée** (Git) : qui a changé quoi, quand, pourquoi ; retour arrière possible ; le runbook cesse d'être un journal pour devenir du code relu ;
3. **Exécutable** : la documentation *est* le déploiement ; elle ne peut pas être périmée puisque c'est elle qui agit ;
4. **Idempotente** : rejouable à volonté ; l'exécuter sur une machine déjà conforme ne change rien, l'exécuter sur une machine déviante la **ramène à l'état voulu** : le drift se corrige en relançant ;
5. **Déclarative** autant que possible : on décrit l'état cible (« ce paquet présent, ce fichier avec ce contenu, ce service démarré »), l'outil calcule les actions ;
6. **Factorisée** : le rôle « backend » est écrit **une fois** et appliqué à N machines ; ajouter app3 = ajouter une ligne d'inventaire, pas une séance de TP.

Relisez la liste : chaque propriété répond à une douleur précise et datée de vos TP. C'est, terme à terme, la définition de l'**Infrastructure as Code**, et le programme exact du bloc 3 : Vagrant décrira les machines (provisionner), Ansible les rôles (configurer), et le TP 9 rejouera le défi du bloc 1 en une commande.

## Ce qu'il faut retenir

1. La configuration multi-machines duplique l'information ; toute duplication non synchronisée mécaniquement diverge : c'est le **configuration drift**, produit de l'exploitation normale, pas de la négligence.
2. Symptôme canonique : « ça marche sur app1, pas sur app2 » ; coût réel : serveurs non interchangeables, mises à jour risquées, reconstruction impossible.
3. Métaphores à connaître et savoir expliquer : **snowflake** (l'irreproductible qu'on n'ose plus toucher), **pets vs cattle** (soigner vs remplacer ; le mode bétail exige la reconstruction automatique), **phénix / infrastructure immuable** (reconstruire plutôt que modifier).
4. Le cahier des charges de la solution : configuration **écrite, versionnée, exécutable, idempotente, déclarative, factorisée**. C'est la définition de l'IaC et le programme du bloc 3.

## Bibliographie du chapitre

### Sources primaires

- Kief Morris, *Infrastructure as Code*, 2ᵉ éd., O'Reilly, 2020, chapitres 1 et 2 : le vocabulaire de ce chapitre y est défini formellement. Lecture obligatoire avant le bloc 3.
- Martin Fowler (bliki) : « SnowflakeServer » (2012), « PhoenixServer » (2012), « ImmutableServer » (2013) : trois billets courts, fondateurs. [martinfowler.com/bliki](https://martinfowler.com/bliki/SnowflakeServer.html).
- Randy Bias, « The History of Pets vs Cattle », 2016.

### Lectures recommandées

- Jez Humble, David Farley, *Continuous Delivery*, Addison-Wesley, 2010, chapitre 11 (« Managing Infrastructure and Environments ») : le même diagnostic, posé avant l'ère des outils modernes.
- CERN IT, présentations publiques « Agile Infrastructure » (2012-2013) : comment un centre de calcul scientifique de dizaines de milliers de machines a basculé pets → cattle ; instructif parce que les contraintes y sont concrètes.

### Pour aller plus loin

- Mark Burgess, *A Site Configuration Engine* (USENIX Computing Systems, 1995) : le papier de CFEngine, ancêtre de tous les gestionnaires de configuration ; l'idempotence et la convergence y sont déjà centrales, vingt ans avant vos TP.
- Chad Fowler, « Trash Your Servers and Burn Your Code: Immutable Infrastructure and Disposable Components », billet, 2013 : le manifeste de l'infrastructure immuable.
