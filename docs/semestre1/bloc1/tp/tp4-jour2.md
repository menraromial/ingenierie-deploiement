# TP 4 : Le « jour 2 » : mise à jour, sauvegarde, diagnostic

!!! abstract "Fiche du TP"
    - **Durée** : 4 h
    - **Prérequis** : TP 3 terminé (application complète en HTTPS)
    - **Livrables** : application en v1.1 ; sauvegardes automatiques quotidiennes + une restauration prouvée ; diagnostic rédigé d'au moins une panne injectée ; runbook à jour
    - **Compétences travaillées** : C6 (cœur du TP), C1

    Dans le jargon de l'exploitation, le **jour 1** est l'installation ; le **jour 2**, c'est tout le reste : mettre à jour, sauvegarder, diagnostiquer, réparer. Un système passe un jour en installation et des années en jour 2 : c'est là que se joue le métier.

## Partie A : la mise à jour applicative (1 h 15)

La version 1.1 de Listify ajoute la fonctionnalité « tâche terminée ». Elle touche **les trois tiers** : c'est le scénario de mise à jour le plus complet (et le plus risqué) qui soit.

### A.1 : les changements de la v1.1

**Base de données** : une migration (fournie dans `db/migrations/001-add-done.sql`) :

```sql title="db/migrations/001-add-done.sql"
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS done BOOLEAN NOT NULL DEFAULT FALSE;
```

**Backend** : dans `app.py`, la requête de `list_tasks` devient `SELECT id, title, done, created_at ...`, et une route apparaît :

```python title="backend/app.py (ajout v1.1)"
@app.patch("/api/tasks/<int:task_id>")
def toggle_task(task_id: int):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "UPDATE tasks SET done = NOT done WHERE id = %s "
                "RETURNING id, title, done, created_at",
                (task_id,),
            )
            row = cur.fetchone()
            if row is None:
                return jsonify({"error": "not found"}), 404
            return jsonify(row)
```

**Frontend** : dans `app.js`, la boucle d'affichage ajoute une case à cocher avant le titre :

```javascript title="frontend/app.js (ajout v1.1, dans la boucle for)"
const box = document.createElement("input");
box.type = "checkbox";
box.checked = task.done;
box.onchange = async () => {
  await fetch(`${API}/tasks/${task.id}`, { method: "PATCH" });
  refresh();
};
li.prepend(box);
```

Appliquez ces changements dans votre dépôt Git local, committez (`git commit -m "v1.1 : tâches terminées"`), et taguez : `git tag v1.1`.

### A.2 : dérouler la mise à jour... et noter chaque friction

Déroulez, dans cet ordre, en notant au runbook le **pourquoi de l'ordre** :

```bash
# 1. La migration de schéma D'ABORD (le nouveau code exige la colonne ;
#    l'ancien code, lui, tolère une colonne en trop : ordre non symétrique !)
scp db/migrations/001-add-done.sql listify-s1:/tmp/
ssh listify-s1 'psql "postgresql://listify@127.0.0.1:5432/listify" -f /tmp/001-add-done.sql'

# 2. Le nouveau code backend
scp backend/app.py listify-s1:/tmp/app.py
ssh listify-s1 'sudo mv /tmp/app.py /opt/listify/backend/app.py &&
                sudo chown listify:listify /opt/listify/backend/app.py'

# 3. Redémarrer le service (le code Python chargé en mémoire ne change pas tout seul)
ssh listify-s1 'sudo systemctl restart listify'

# 4. Le frontend
scp frontend/app.js listify-s1:/tmp/app.js
ssh listify-s1 'sudo mv /tmp/app.js /opt/listify/frontend/app.js &&
                sudo chown root:root /opt/listify/frontend/app.js &&
                sudo chmod a+r /opt/listify/frontend/app.js'
```

Testez au navigateur (`Ctrl+Maj+R` pour contourner le cache) : les cases à cocher fonctionnent et l'état persiste après rechargement.

!!! warning "Prenez la mesure de ce que vous venez de faire"
    Pendant `systemctl restart`, l'API était **indisponible** (mesurez : `curl` en boucle pendant un restart : combien de requêtes échouent ?). Vous avez copié des fichiers un par un, avec les bons propriétaires, dans le bon ordre, sans trace automatique de « quelle version tourne ». Si l'étape 2 avait réussi et l'étape 3 échoué, quel état aurait le système ? Ce malaise a des noms : déploiement non atomique, non répétable, avec interruption. Tout le reste du parcours (Ansible au bloc 3, rolling updates de Kubernetes au S2) répond à ce paragraphe précis. Consignez vos mesures.

## Partie B : sauvegarde et restauration (1 h 15)

Règle absolue du métier : **une sauvegarde qui n'a jamais été restaurée n'est pas une sauvegarde**, c'est un espoir. Nous allons donc faire les deux.

### B.1 : la sauvegarde logique avec pg_dump

```bash
# Sur la VM : un répertoire de sauvegardes appartenant à postgres
sudo mkdir -p /var/backups/listify
sudo chown postgres:postgres /var/backups/listify

# Test manuel : un dump "custom format" (compressé, restauration sélective possible)
sudo -u postgres pg_dump -Fc -f /var/backups/listify/manual.dump listify
sudo -u postgres pg_restore --list /var/backups/listify/manual.dump | head
```

### B.2 : l'automatisation avec un timer systemd

Le remplaçant moderne de cron (ch. 2, bibliographie) : une unité de **service** qui fait le travail, une unité **timer** qui la déclenche.

```bash
sudo tee /etc/systemd/system/listify-backup.service > /dev/null <<'EOF'
[Unit]
Description=Sauvegarde quotidienne de la base Listify

[Service]
Type=oneshot
User=postgres
ExecStart=/bin/sh -c 'pg_dump -Fc -f /var/backups/listify/listify-$(date +%%F).dump listify'
# Rétention : supprimer les dumps de plus de 7 jours
ExecStartPost=/usr/bin/find /var/backups/listify -name "*.dump" -mtime +7 -delete
EOF

sudo tee /etc/systemd/system/listify-backup.timer > /dev/null <<'EOF'
[Unit]
Description=Déclenche la sauvegarde Listify chaque nuit

[Timer]
OnCalendar=*-*-* 03:00:00
# Si la machine était éteinte à 3h, rattraper au prochain démarrage :
Persistent=true

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now listify-backup.timer
systemctl list-timers | grep listify      # prochaine exécution planifiée

# Ne pas attendre 3h du matin : déclencher le service à la main
sudo systemctl start listify-backup.service
ls -lh /var/backups/listify/
```

Notez le `%%` dans `$(date +%%F)` : dans une unité systemd, `%` est un caractère spécial (spécificateurs `%i`, `%n`...), il se double pour être littéral. Piège classique, offert par le cours.

### B.3 : l'exercice de restauration (le vrai test)

Scénario catastrophe volontaire, à dérouler complètement :

```bash
# 1. Constater l'état : combien de tâches ?
curl -sk https://127.0.0.1/api/tasks | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))'

# 2. LA CATASTROPHE (assumée : nous avons un dump)
psql "postgresql://listify@127.0.0.1:5432/listify" -c 'DROP TABLE tasks;'
curl -sk https://127.0.0.1/api/health     # {"api":"ok","database":"ok"}... tiens ?
curl -sk https://127.0.0.1/api/tasks      # 500 : à quoi sert un health check qui dit "ok" ?

# 3. LA RESTAURATION
sudo -u postgres pg_restore -d listify --clean --if-exists \
     /var/backups/listify/manual.dump

# 4. Preuve : le même comptage qu'en 1
curl -sk https://127.0.0.1/api/tasks | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))'
```

Au runbook : le temps de restauration mesuré (c'est votre **RTO**, *Recovery Time Objective*, à l'échelle 1) et la quantité de données perdables entre deux sauvegardes nocturnes (votre **RPO**, *Recovery Point Objective* : jusqu'à 24 h ici). Discussion de séance : pour quelles applications 24 h de RPO sont-elles inacceptables, et qu'est-ce que cela implique (archivage WAL, réplication : hors périmètre, mais nommons les solutions) ?

!!! danger "Où est le trou béant de notre stratégie ?"
    Les dumps sont **sur le même disque** que la base. Panne du disque = perte des données ET des sauvegardes. La règle professionnelle est **3-2-1** : 3 copies, 2 supports, 1 hors site. En TP, faites au minimum la copie hors-VM : `scp listify-s1:/var/backups/listify/manual.dump ./backups/` depuis le poste hôte. Question bonus : pourquoi ce scp échoue-t-il tel quel, et quelle est la façon propre de le régler ? (Indice : permissions du répertoire, groupe.)

## Partie C : les pannes injectées (1 h 30)

L'enseignant passe sur votre VM injecter une panne (vous fermez les yeux, au sens propre : l'intérêt est de diagnostiquer sans savoir). Votre travail, pour **chaque** panne : un mini-rapport au format post-mortem dans le runbook :

1. **Symptôme** : ce que voit l'utilisateur (message, code HTTP, comportement).
2. **Localisation** : quelle couche ? Déroulez la méthode ascendante (ch. 3) et la checklist services (ch. 2, §4.5) ; citez les commandes dans l'ordre où vous les avez lancées et ce qu'elles ont montré.
3. **Cause racine** : la phrase précise (« le service X ne démarre pas parce que... »).
4. **Correction** : la commande, et la preuve que c'est réparé.
5. **Prévention** : qu'est-ce qui aurait empêché, détecté plus tôt, ou réparé tout seul ?

Boîte à outils du diagnostic, en un tableau à garder sous la main :

| Question | Commande |
|---|---|
| Les services tournent-ils ? | `systemctl status nginx listify postgresql` : `systemctl --failed` |
| Que disent les logs du service ? | `journalctl -u <svc> -n 50` ; `--since "10 min ago"` |
| Qui écoute sur quoi ? | `sudo ss -tlnp` |
| Nginx dit quoi ? | `/var/log/nginx/error.log` et `access.log` (codes 502/504 !) |
| La chaîne répond-elle, maillon par maillon ? | `curl 127.0.0.1:8000/api/health` (Gunicorn direct), puis `curl -k https://127.0.0.1/api/health` (via Nginx) |
| La base répond-elle ? | `psql "postgresql://listify@127.0.0.1:5432/listify" -c 'SELECT 1;'` |
| Le disque, la RAM ? | `df -h`, `free -m`, `journalctl -k | grep -i oom` |
| Qu'est-ce qui a changé récemment ? | `ls -lt /etc/... ` ; historique du runbook ! |

??? note "Banque de pannes du bloc 1 (réservé enseignant : ne lisez pas si vous jouez le jeu)"
    Chaque panne s'injecte en ~1 minute ; remettre en état avant la panne suivante. Par difficulté croissante :

    1. **Service arrêté et désactivé** : `systemctl disable --now listify`. Symptôme : 502 sur /api/. Piège : `start` sans `enable` = re-panne au reboot (rebooter pour vérifier s'ils y ont pensé).
    2. **Mot de passe BD faux** : éditer `DB_PASSWORD` dans `/etc/listify/listify.env` + `systemctl restart listify`. Symptôme : /api/health → `database: error`, tasks → 500. Chemin attendu : journalctl montre l'`OperationalError`.
    3. **Pare-feu trop zélé** : `ufw deny 443/tcp` (règle insérée avant l'allow). Symptôme : timeout au navigateur, mais tout marche depuis la VM. Distinction refused/timeout du ch. 3 à l'œuvre.
    4. **PostgreSQL éteint** : `systemctl stop postgresql`. Facile en apparence ; la valeur est dans la prévention (pourquoi `Wants=` n'a-t-il pas suffi ? parce qu'il ne s'applique qu'au démarrage de listify : première limite de systemd face à une vraie supervision).
    5. **Disque plein** : `fallocate -l <presque tout> /var/fill`. Symptôme : POST → 500 (PostgreSQL ne peut plus écrire), GET fonctionne. `df -h` doit venir tôt dans leur checklist.
    6. **Nginx mal configuré au reload** : remplacer `proxy_pass http://127.0.0.1:8000;` par le port 8001 + reload. Symptôme : 502 immédiat, error.log parle (`connect() failed ... 8001`). Vérifie qu'ils lisent error.log et pas seulement journalctl.
    7. **Permission cassée** : `chmod 600 /etc/listify/listify.env` (root:root). Symptôme : listify en boucle de redémarrage (`status` : activating/auto-restart), journalctl : `Failed to load environment file: Permission denied`. La plus fine : erreur *avant* l'application (ch. 2, §4.5, étape 3).

## Point de contrôle final

- [ ] v1.1 en service (cases à cocher persistantes), avec mesure de l'indisponibilité pendant le restart
- [ ] Timer de sauvegarde actif (`systemctl list-timers`), un dump produit cette séance
- [ ] Restauration complète prouvée (comptage avant/après identique), RTO et RPO chiffrés au runbook
- [ ] Une copie de dump hors de la VM
- [ ] Au moins un rapport de panne complet aux 5 sections
- [ ] Snapshot `tp4-jour2` ; runbook committé

## Questions de compréhension (à préparer pour le TD)

1. Justifiez l'ordre migration → backend → restart → frontend. Pour quelle modification de schéma l'ordre inverse (code d'abord) serait-il obligatoire ? Vous venez de toucher du doigt les **migrations compatibles** (expand/contract) : cherchez ce terme.
2. Notre `/api/health` disait « ok » avec une table détruite. Proposez (en pseudo-code) un health check qui l'aurait détecté, et expliquez le compromis coût/fidélité d'un health check trop complet.
3. Différence entre sauvegarde **logique** (pg_dump) et **physique** (copie de `/var/lib/postgresql`) : avantages, inconvénients, et pourquoi copier le répertoire d'une base *en marche* produit une sauvegarde probablement corrompue.
4. Pour chaque panne que vous avez subie : laquelle des lignes de défense du parcours (Ansible, conteneurs, orchestrateur, monitoring) l'aurait empêchée, détectée ou auto-réparée ? Ce tableau est exactement le programme des semestres à venir.
