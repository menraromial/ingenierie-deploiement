---
title: "TP 17 : Casser pour comprendre (diagnostic)"
sidebar_label: "TP 17 : Casser pour comprendre (diagnostic)"
hide_title: true
---

import ChapterHead from '@site/src/components/ChapterHead';
import Figure from '@site/src/components/Figure';

<ChapterHead
  kicker="Semestre 2 · Bloc 2 · Travaux pratiques 17"
  title="Casser pour comprendre, le diagnostic de pannes"
  competences={['C3', 'C6']}
/>

:::fiche
- **Durée** : 4 h, dont une partie **en temps limité et notée** (contrôle continu)
- **Prérequis** : TP 16 (Listify tourne sur le cluster) ; chapitres 20 à 22
- **Livrables** : pour chaque panne, un mini-post-mortem (symptôme, méthode, cause racine, correction, prévention) ; runbook
- **Compétences travaillées** : C6 (cœur du TP), C3

C'est le TP le plus formateur du bloc, et le plus évalué. On injecte des pannes Kubernetes réalistes ; vous les diagnostiquez **méthodiquement**. Diagnostiquer un cluster n'est pas deviner : c'est appliquer une méthode, celle du modèle de réconciliation (ch. 20).
:::

## La méthode de diagnostic Kubernetes

Avant les pannes, la méthode. Elle découle du chapitre 20 : une panne, c'est un endroit où le **réel diverge du désiré** et où un contrôleur **n'arrive pas à corriger**. Quatre commandes, dans cet ordre, répondent à presque tout :

<Figure src="diagnostic-k8s" num="TP17.1" alt="Quatre étapes enchaînées : kubectl get pods (quel état), kubectl describe pod (pourquoi), kubectl logs (que dit l'application), kubectl get events (dans quel ordre).">
  La méthode de diagnostic en quatre questions. On passe à l'étape suivante seulement quand la précédente n'a pas suffi.
</Figure>

| Commande | Ce qu'elle révèle |
|---|---|
| `kubectl get pods -n listify` | L'**état** de chaque Pod : le statut nomme souvent déjà la panne |
| `kubectl describe pod <nom> -n listify` | Les **Events** (en bas) : ce que le kubelet/scheduler ont tenté et **pourquoi ça échoue** |
| `kubectl logs <nom> -n listify [--previous]` | Ce que dit l'**application** ; `--previous` pour un conteneur qui a redémarré |
| `kubectl get events -n listify --sort-by=.lastTimestamp` | La **chronologie** des événements du namespace |

Apprenez à **lire le statut** d'un Pod, il nomme la panne :

| Statut | Signification | Piste |
|---|---|---|
| `Pending` | Pas encore placé/démarré | Ressources insuffisantes (scheduler), PVC non lié, image en cours de pull |
| `ImagePullBackOff` / `ErrImagePull` | Image introuvable | Nom/tag erroné, image non chargée dans kind, registre inaccessible |
| `CrashLoopBackOff` | Le conteneur démarre et **meurt en boucle** | Erreur applicative, mauvaise config, liveness trop stricte |
| `OOMKilled` | Tué pour dépassement mémoire | `limits.memory` trop basse (code de sortie **137**, ch. 15 !) |
| `Running` mais `0/1 READY` | Vivant mais **pas prêt** | La **readiness** échoue (une dépendance manque) |

## Partie A : les pannes injectées (2 h)

L'enseignant applique une panne (vous ne savez pas laquelle). Pour **chacune**, produisez un post-mortem au runbook :

1. **Symptôme** : ce que voit l'utilisateur / ce que montre `kubectl get pods`.
2. **Méthode** : les commandes lancées, dans l'ordre, et ce qu'elles ont montré.
3. **Cause racine** : la phrase précise.
4. **Correction** : la commande, et la preuve que c'est réparé.
5. **Prévention** : qu'est-ce qui aurait évité, détecté plus tôt, ou auto-corrigé ?

:::exemple[Exemple travaillé : une image inexistante]
**Symptôme** : `kubectl get pods -n listify` montre `backend-xxx  0/1  ImagePullBackOff`.

**Méthode** :
```bash
kubectl describe pod backend-xxx -n listify | grep -A6 Events:
# → Failed to pull image "localhost/listify-backend:2.0": ... not found
```
Les Events nomment la cause : le tag `2.0` n'existe pas (on a déployé une image jamais construite/chargée).

**Cause racine** : le Deployment référence `listify-backend:2.0`, absent du cluster kind.

**Correction** : remettre le bon tag (`kubectl set image deployment/backend backend=localhost/listify-backend:1.0 -n listify`), ou charger l'image `2.0` dans kind. Le Pod passe `Running`.

**Prévention** : déployer par **digest** (ch. 16) ou vérifier la présence de l'image dans le pipeline de CI (bloc 3) ; un scan/lint des manifests attraperait un tag douteux.
:::

<details className="enseignant">
<summary>Banque de pannes du bloc 2 (réservé enseignant, ne pas lire si vous jouez le jeu)</summary>

Chaque panne s'injecte en une commande, sur le Listify du TP 16. À rejouer en soutenance.

1. **Image inexistante** : `kubectl set image deployment/backend backend=localhost/listify-backend:2.0 -n listify`. → `ImagePullBackOff`. Les Events le disent. (L'exemple travaillé ci-dessus.)
2. **Probe readiness cassée** : porter la readiness sur un mauvais chemin (`/nope`) ou un mauvais port. → Pods `Running` mais `0/1 READY`, retirés du Service `backend` → l'appli répond 502/503. `describe` : `Readiness probe failed`. Piège pédagogique : le Pod n'est PAS malade, il est juste jugé « pas prêt ».
3. **Limite mémoire trop basse** : `resources.limits.memory: 16Mi` sur le backend. → `OOMKilled`, `CrashLoopBackOff`, code **137**. Relie au cgroup `memory` du bloc 1.
4. **Service sans endpoints** : casser le `selector` du Service `backend` (`tier: backendd`). → le Service n'a plus d'Endpoints (`kubectl get endpoints backend -n listify` est vide), l'appli tombe, mais **tous les Pods sont sains** ! Diagnostic le plus subtil : le problème est le *lien* label/selector, pas les Pods. Leçon centrale du chapitre 21.
5. **Secret manquant** : supprimer le Secret `listify-db`. → nouveaux Pods backend en `CreateContainerConfigError` (`describe` : `secret "listify-db" not found`). La config référencée n'existe pas.
6. **PVC / base** : `kubectl delete pod db-0 -n listify` pendant une écriture, ou saturer le stockage. → réapparition de db-0, données intactes (PVC) ; vérifier que le backend revient via readiness.
7. **Requests trop hautes** : `resources.requests.memory: 100Gi`. → Pod `Pending` indéfiniment ; `describe` : `Insufficient memory`, le **scheduler** ne trouve aucun nœud. Relie requests ↔ placement (ch. 22).

</details>

## Partie B : l'épreuve chronométrée (1 h, notée)

En temps limité, l'enseignant injecte **deux pannes simultanées** sur votre cluster. Vous devez, en 30 minutes : les identifier, les corriger, et remettre Listify en marche, en **commentant votre démarche à voix haute** (comme en soutenance). La note porte sur la **méthode** (avez-vous suivi get → describe → logs → events ?), pas seulement sur le résultat. Un diagnostic juste mais chanceux vaut moins qu'une méthode rigoureuse qui converge.

## Partie C : rendre le système plus diagnosticable (1 h)

Un bon opérateur ne fait pas que réparer : il rend les pannes **plus lisibles pour la prochaine fois**. Améliorez votre Listify :

1. **Des probes justes** : vérifiez que readiness et liveness testent la bonne chose (readiness = dépendances, liveness = soi-même). Une mauvaise probe *crée* des pannes.
2. **Des ressources déclarées** : sans requests/limits, le scheduler place mal et l'OOM frappe au hasard. Ajoutez-les partout et justifiez les valeurs.
3. **Des messages clairs** : votre `/api/health` renvoie-t-il un message utile quand la base manque (rappel du TP 4 du S1) ? Un health check bavard accélère le diagnostic.

## Point de contrôle final

- [ ] La méthode get → describe → logs → events appliquée systématiquement (au runbook)
- [ ] Au moins **quatre** pannes de la partie A diagnostiquées avec post-mortem complet
- [ ] Épreuve chronométrée réussie, méthode commentée
- [ ] Chaque statut de Pod (Pending, ImagePullBackOff, CrashLoop, OOMKilled, 0/1 Ready) rencontré et compris
- [ ] Partie C : probes et ressources améliorées, justifiées

## Pour aller plus loin (bonus)

1. **`kubectl debug`** : attachez un conteneur éphémère de débogage à un Pod problématique pour l'inspecter de l'intérieur, sans le modifier. Un outil moderne puissant.
2. **Les événements en continu** : `kubectl get events -A --watch` pendant que vous cassez et réparez : vous voyez les contrôleurs réagir en temps réel. La réconciliation, filmée.
3. **k9s** : installez ce tableau de bord terminal ; il rend `get/describe/logs` interactifs. Comparez le confort au `kubectl` brut (mais maîtrisez `kubectl` d'abord : c'est lui qui est à l'examen).

## Questions de compréhension (à préparer pour le TD et l'examen)

1. Un Service « sans endpoints » alors que tous les Pods sont `Running` : expliquez la cause (label/selector) et pourquoi c'est le diagnostic le plus trompeur. Quelle commande le révèle immédiatement ?
2. Distinguez `CrashLoopBackOff` (le conteneur meurt en boucle) et `0/1 Running` (vivant mais pas prêt). Quelle probe est en cause dans chaque cas, et quelle est la bonne correction ?
3. Un Pod reste `Pending` indéfiniment. Donnez trois causes possibles et la commande qui départage. Reliez au rôle du scheduler (ch. 20) et aux requests (ch. 22).
4. Pourquoi la **méthode** (get → describe → logs → events) est-elle plus fiable que l'intuition ? Reliez au modèle de réconciliation : que cherche-t-on, exactement, à chaque étape ?
