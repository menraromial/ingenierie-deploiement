# Défi final du bloc 1 : le mur du déploiement manuel

!!! abstract "Fiche du défi"
    - **Durée** : 30 minutes, chronométrées, en fin de semaine 5
    - **Matériel autorisé** : votre dépôt Git (code + `RUNBOOK.md`). Rien d'autre : pas de snapshot, pas de copie de VM, pas d'internet au-delà des miroirs de paquets.
    - **Notation** : ce défi n'est **pas noté sur la réussite**. Il est noté sur le compte rendu que vous en ferez (voir plus bas). Échouer est le résultat attendu et assumé.

## L'énoncé

L'enseignant vous fournit une VM Debian 12 **neuve et vierge** (même image que le TP 1, seule la connexion SSH par mot de passe est prête). Vous avez 30 minutes pour y redéployer l'application Listify v1.1, à l'identique de votre VM des TP 1-4 :

- SSH par clés, durcissement, ufw ;
- PostgreSQL, base, rôle, schéma + migration ;
- backend en service systemd, venv, fichier d'environnement ;
- Nginx, statiques, TLS, redirection HTTP→HTTPS ;
- sauvegarde automatisée.

Au bout de 30 minutes : démonstration. `https://listify.local:8443` doit fonctionner au navigateur, et `sudo ss -tlnp` doit montrer la même surface d'exposition qu'au TP 3.

## Ce qui va se passer (on vous le dit d'avance)

Vous avez pourtant un runbook complet. Mais en 4 TP, vous avez exécuté **plus de 150 commandes**, sur des chemins précis, avec des propriétaires précis, dans un ordre précis dont une partie seulement est documentée. L'expérience des promotions précédentes :

- personne ne termine en 30 minutes (les meilleurs atteignent Nginx) ;
- les runbooks se révèlent incomplets exactement là où « c'était évident sur le moment » (le `daemon-reload` oublié, le `chown` après le `mv`, le `%%` du timer...) ;
- chacun découvre des étapes faites « en passant » au TP et jamais notées ;
- et surtout : deux étudiants avec le même runbook obtiennent deux serveurs différents.

Si vous terminez : bravo, votre runbook est exceptionnel. Chronométrez quand même, et répondez à la question : tiendriez-vous la cadence pour **dix** serveurs ? Pour cinquante ?

## Le compte rendu (noté, en binôme, à rendre sous une semaine)

Une page, quatre sections :

1. **Chronologie** : jusqu'où êtes-vous arrivés, où est parti le temps (estimation honnête par étape) ?
2. **Les trous du runbook** : la liste précise des étapes manquantes ou ambiguës découvertes pendant le défi. C'est la section la plus importante : elle prouve que vous avez compris ce qu'est une *documentation exécutable*... et pourquoi un document ne le sera jamais.
3. **Analyse** : en quoi ce résultat était-il structurel et non personnel ? Convoquez les concepts du bloc : quelles étapes sont non-idempotentes (relançables sans casse ?), où la configuration a-t-elle « dérivé » entre votre VM de TP et votre runbook ?
4. **Cahier des charges de la solution** : si vous deviez concevoir l'outil qui rend ce défi trivial, quelles propriétés devrait-il avoir ? Écrivez-les sans connaître les outils du bloc 3.

## Pourquoi ce défi existe

> *« Le déploiement manuel n'est ni reproductible, ni documenté, ni scalable. »*

Cette phrase, en cours, est une opinion. Après le défi, c'est votre expérience. Les propriétés que vous listerez en section 4 (exécutable plutôt que lisible, idempotent, versionné avec le code, déclaratif...) sont précisément la définition de l'**Infrastructure as Code** : vous venez d'écrire le programme du bloc 3 vous-mêmes.

Rendez-vous au TP 9 : même défi, même application, une commande, quelques minutes. Gardez précieusement vos chronos d'aujourd'hui : la comparaison chiffrée fait partie du compte rendu du TP 9, et c'est l'un des moments les plus satisfaisants du semestre.
