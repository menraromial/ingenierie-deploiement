# Évaluation du Semestre 1

L'évaluation du semestre pèse trois choses distinctes : la **régularité** (contrôle continu), la **capacité à produire** un déploiement automatisé de bout en bout (projet), et la **maîtrise des concepts** durables (examen théorique). Aucune ne remplace les autres : on peut réussir un `deploy.sh` sans comprendre l'idempotence, et réciter l'idempotence sans savoir déboguer une VM. Le métier exige les deux.

## Répartition

| Épreuve | Poids | Ce qui est évalué |
|---|---|---|
| Contrôle continu | 30 % | Comptes rendus de TP en « journal de bord » (runbook) : commandes, erreurs, diagnostics |
| Projet | 40 % | Déploiement 100 % automatisé d'une application 3-tiers, par binôme |
| Examen théorique | 30 % | Concepts et étude de cas d'architecture sur papier |

## Contrôle continu (30 %)

La note agrège vos runbooks de TP. Ce qui est valorisé, dans l'ordre :

1. **La reproductibilité** : un camarade peut-il refaire le TP avec votre seul runbook ?
2. **Les diagnostics** : les impasses documentées (« j'ai essayé X, échec parce que Y, corrigé par Z ») valent plus que les réussites lisses. Le TP 4 (diagnostic de pannes) et les pannes des TP 6 et 8 sont des moments notés en priorité.
3. **La rigueur des tests négatifs** : prouver qu'une porte est fermée (segmentation, ufw, permissions) autant que prouver qu'elle est ouverte.

## Projet (40 %)

**Par binôme, une application 3-tiers _différente de Listify_** (fournie par l'enseignant ou proposée et validée en semaine 3), déployée de manière **100 % automatisée** avec Vagrant + Ansible.

Livrables :

- un **dépôt Git** dont le `README` permet à l'enseignant de tout reconstruire, en une commande si l'outillage le permet (le protocole du TP 9) ;
- une **architecture** au moins équivalente à celle du bloc 2 (multi-machines, réseau segmenté, load balancer) ;
- la **preuve d'idempotence** du playbook (`changed=0` au second passage).

Soutenance : démonstration d'une reconstruction, puis **injection d'une panne en direct** (tirée de la banque de pannes du parcours) à **diagnostiquer et corriger commentée**. C'est là que le contrôle continu paie : ceux qui ont tenu un vrai runbook diagnostiquent vite.

Critères de notation (grille indicative) :

| Critère | Poids indicatif |
|---|---|
| Reconstruction en une commande réellement fonctionnelle | 30 % |
| Idempotence et qualité des rôles Ansible (pas de `shell` gratuit, secrets en vault, configuration calculée depuis l'inventaire) | 25 % |
| Architecture justifiée (segmentation, choix, limites assumées : C1) | 20 % |
| Diagnostic de la panne en soutenance (C6) | 15 % |
| Qualité du README et du dépôt (propreté, `.gitignore`, historique) | 10 % |

## Examen théorique (30 %)

Sur papier, sans machine. Deux types de questions :

**Questions de concepts** (définir, distinguer, illustrer) :

- idempotence (définition formelle + une illustration par bloc) ;
- déclaratif vs impératif ; état désiré / état réel / convergence ;
- configuration drift, pets vs cattle, serveur immuable ;
- provisionner / configurer / orchestrer, et la place de chaque outil ;
- TLS (chiffrement vs authentification, chaîne de certification) ; systemd (unité, `Restart`, handlers/notify) ; le reverse proxy (les raisons de Nginx devant Gunicorn) ; la segmentation réseau et la défense en profondeur.

**Étude de cas d'architecture** : on vous décrit un besoin (charge, budget, contraintes de données, disponibilité) et vous **concevez et justifiez** une architecture de déploiement : machines, réseau, segmentation, choix vertical/horizontal, points de défaillance et parades, et vous **motivez** l'automatisation. C'est la compétence C1, et elle se prépare en refaisant, sur des cas variés, le raisonnement des chapitres 1, 6 et 10.

## Conseil de méthode pour réviser

Le fil rouge de révision le plus efficace : prenez **un** concept transversal (l'idempotence, ou l'état désiré) et suivez-le à travers les trois blocs (le `CREATE TABLE IF NOT EXISTS` du TP 2, le module Ansible du TP 8, le `plan` de Terraform du TP 10). Si vous savez raconter cette continuité, vous avez compris le semestre : les outils ne sont que des incarnations successives d'un petit nombre d'idées, et c'est sur ces idées que porte l'évaluation.
