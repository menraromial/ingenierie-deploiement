---
title: "Ch. 33 : Servir un modèle"
sidebar_label: "Ch. 33 : Servir un modèle"
hide_title: true
---

import ChapterHead from '@site/src/components/ChapterHead';
import Figure from '@site/src/components/Figure';

<ChapterHead
  kicker="Semestre 3 · Bloc 2 · Chapitre 33"
  title="Servir un modèle : API, validation, charge et conteneur"
  lecture="55 min"
  competences={['C3', 'C5']}
/>

:::objectifs
À l'issue de ce chapitre, vous saurez :

- exposer un modèle derrière une API dont le **contrat** d'entrée et de sortie est validé et documenté ;
- charger le modèle **au démarrage** depuis le registre, et régler les sondes en conséquence ;
- mesurer un service de prédiction (débit, percentiles) et interpréter ce que la mesure révèle sur la file d'attente ;
- dimensionner le nombre de workers et de répliques pour un objectif de latence ;
- protéger le service : limites de taille, délais d'attente, rejet, dégradation gracieuse ;
- conteneuriser le service, expliquer pourquoi son image est grosse et son démarrage lent, et éviter les pièges du modèle chargé depuis un registre.
:::

## 1. Du fichier de modèle au service

Le TP 23 a laissé un modèle utilisable en ligne de commande (`predire.py`), et le chapitre 31 l'a enregistré au registre sous l'alias `champion`. Il manque la dernière marche : un **service** que l'application interroge, celui que le chapitre 30 a décrit comme le mode « à la demande » et le « modèle-service ».

Servir un modèle, ce n'est pas « charger un `joblib` dans une route ». C'est publier un **contrat** et le tenir :

| Le contrat dit | Concrètement |
|---|---|
| Ce que le client envoie | Un titre de tâche, texte non vide, au plus 200 caractères |
| Ce qu'il reçoit | Une catégorie parmi cinq, et une confiance entre 0 et 1 |
| Ce qui se passe en cas d'entrée invalide | Une erreur **400/422** explicite, pas une erreur 500 ni une prédiction absurde |
| Ce qui se passe en cas de panne du modèle | Une erreur **503**, que le client sait traiter en se passant de suggestion |
| Combien de temps cela prend | Un objectif de latence, tenu à un percentile donné |
| Quel modèle a répondu | Une version, exposée et journalisée |

<Figure src="service-modele" num="33.1" alt="Le backend Listify envoie POST /suggestion à un Ingress (TLS, routage), qui répartit vers trois répliques du service. Chaque réplique valide l'entrée avec Pydantic puis interroge le modèle chargé en mémoire. Au démarrage, les répliques lisent le registre MLflow (alias champion) et téléchargent le modèle depuis le stockage d'artefacts (S3 ou MinIO). La requête, elle, ne lit ni le registre ni le stockage.">
  L'architecture visée. Le registre et le stockage d'artefacts sont sollicités **au démarrage**, jamais pendant une requête : c'est ce qui rend le service rapide et insensible à une panne du registre.
</Figure>

## 2. L'API avec FastAPI

FastAPI convient bien à ce rôle : il valide les entrées et les sorties à partir de types Python (via Pydantic), produit une documentation OpenAPI sans effort, et s'exécute sur un serveur asynchrone (Uvicorn). Voici le service complet, celui qui a servi à toutes les mesures de ce chapitre :

```python title="service.py"
"""Service de prédiction de catégorie pour Listify."""
import os
import time
from contextlib import asynccontextmanager

import mlflow
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

MODELE_URI = os.environ.get("MODELE_URI", "models:/listify-categorie@champion")
etat: dict = {}


@asynccontextmanager
async def cycle_de_vie(app: FastAPI):
    debut = time.perf_counter()
    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "sqlite:///mlflow.db"))
    etat["modele"] = mlflow.sklearn.load_model(MODELE_URI)          # saveur native : donne predict_proba
    etat["version"] = mlflow.models.get_model_info(MODELE_URI).model_id
    etat["chargement_s"] = round(time.perf_counter() - debut, 3)
    yield
    etat.clear()


app = FastAPI(title="Listify, suggestion de catégorie", lifespan=cycle_de_vie)


class Tache(BaseModel):
    titre: str = Field(min_length=1, max_length=200, examples=["acheter du pain"])


class Suggestion(BaseModel):
    titre: str
    categorie: str
    confiance: float


class Lot(BaseModel):
    titres: list[str] = Field(min_length=1, max_length=256)


@app.get("/sante")
def sante():
    return {"etat": "ok", "modele": etat.get("version"), "chargement_s": etat.get("chargement_s")}


@app.post("/suggestion", response_model=Suggestion)
def suggestion(tache: Tache):
    modele = etat.get("modele")
    if modele is None:
        raise HTTPException(status_code=503, detail="modèle non chargé")
    probas = modele.predict_proba(pd.DataFrame({"titre": [tache.titre]}))[0]
    meilleure = probas.argmax()
    return Suggestion(titre=tache.titre, categorie=modele.classes_[meilleure], confiance=float(probas[meilleure]))


@app.post("/suggestions")
def suggestions(lot: Lot):
    predictions = etat["modele"].predict(pd.DataFrame({"titre": lot.titres}))
    return {"categories": list(predictions)}
```

Quatre décisions de conception méritent d'être discutées.

**Le modèle est chargé dans le cycle de vie**, pas au premier appel ni à chaque requête (§3).

**L'entrée et la sortie sont des classes**, pas des dictionnaires. `Tache` décrit ce qui est accepté ; `Suggestion`, déclarée en `response_model`, garantit que le service ne renverra jamais autre chose que ces trois champs. Le contrat du §1 devient du code exécutable, et la documentation OpenAPI en découle.

**Les limites sont explicites** : un titre d'au plus 200 caractères, un lot d'au plus 256 titres. Ces bornes ne sont pas cosmétiques : elles protègent le service (§5).

**On charge la saveur native plutôt que `pyfunc`.** Le chapitre 31 a présenté `pyfunc` comme l'interface universelle ; elle n'expose que `predict`. Ici, le service veut aussi la **confiance**, donc `predict_proba`, qui n'existe que sur l'objet scikit-learn. On paie cette richesse par un couplage : le service sait qu'il sert un modèle scikit-learn. C'est un arbitrage assumé, à documenter.

:::exemple[Exemple 33.1 : ce que la validation renvoie vraiment]
Trois requêtes envoyées au service, et ses réponses exactes :

```bash
curl -X POST localhost:8000/suggestion -H 'Content-Type: application/json' \
     -d '{"titre":"  Acheter du PAIN "}'
```
```json
{"titre":"  Acheter du PAIN ","categorie":"courses","confiance":0.9967693161966668}
```

```bash
curl -X POST localhost:8000/suggestion -H 'Content-Type: application/json' -d '{"titre":""}'
```
```json
{"detail":[{"type":"string_too_short","loc":["body","titre"],
            "msg":"String should have at least 1 character","input":"","ctx":{"min_length":1}}]}
```

```bash
curl -X POST localhost:8000/suggestion -H 'Content-Type: application/json' \
     -d '{"title":"acheter du pain"}'
```
```json
{"detail":[{"type":"missing","loc":["body","titre"],
            "msg":"Field required","input":{"title":"acheter du pain"}}]}
```

Les deux dernières réponses sont des **422**, avec la position exacte du problème. Sans validation, le premier cas aurait produit une prédiction sur une chaîne vide, et le second une erreur 500 au fond de pandas. C'est le même service rendu que la signature MLflow du chapitre 31, mais **au bord** du système, là où arrive l'entrée inconnue.

Remarquez enfin la première réponse : le titre brut, avec ses majuscules et ses espaces, donne la bonne catégorie. Le prétraitement voyage dans le modèle (chapitre 31, §5.3) ; le service n'en réimplémente aucune partie.
:::

## 3. Charger le modèle une fois

Le chargement du modèle depuis le registre a été mesuré à **5,0 s** sur le poste de préparation (téléchargement des artefacts, désérialisation, initialisation de scikit-learn). Deux conséquences.

**Charger par requête est exclu.** Une latence de 5 s par prédiction, contre quelques millisecondes une fois chargé : le rapport est de mille. C'est l'erreur la plus fréquente des premiers services de ML.

**Une réplique n'est pas prête dès qu'elle démarre.** Il faut donc distinguer deux sondes, comme au semestre 2 :

<Figure src="cycle-service" num="33.2" alt="Ligne de temps de 0 à 20 secondes. De 0 à 2,5 s, démarrage du conteneur. De 2,5 à 8,5 s, chargement du modèle, 6 secondes. À partir de 8,5 s, la réplique est prête et reçoit du trafic ; c'est le moment où la sonde de disponibilité passe au vert. Une sonde de vivacité trop impatiente tuerait la réplique pendant le chargement : son délai initial doit dépasser ce temps.">
  Démarrage réel d'une réplique conteneurisée, mesuré au §7 : le service répond 8,5 s après le lancement du conteneur, dont 6 s de chargement du modèle.
</Figure>

- La sonde de **disponibilité** (*readiness*) interroge `/sante` : tant que le modèle n'est pas chargé, la réplique ne reçoit aucun trafic.
- La sonde de **vivacité** (*liveness*) redémarre une réplique bloquée. Son délai initial doit **dépasser** le temps de chargement, sans quoi Kubernetes tuerait la réplique en plein chargement, indéfiniment.

:::exemple[Exemple 33.2 : le coût d'une mise à l'échelle]
Le service tourne en 3 répliques. Un pic de trafic déclenche l'autoscaler, qui en demande 3 de plus.

**Délai avant que le trafic soit absorbé** : téléchargement de l'image si elle n'est pas en cache sur le nœud (§7), puis 8,5 s de démarrage. La mise à l'échelle ne répond donc pas à une pointe de quelques secondes : elle répond à une montée de quelques minutes. Pour absorber les pointes brèves, il faut **de la marge** dans les répliques existantes (chapitre 30, §4.3), pas un autoscaler plus nerveux.

**Mémoire** : les mesures du §4 donnent environ 220 Mio par worker pour ce petit modèle. Six répliques de 2 workers demandent donc environ 2,6 Gio, à réserver dans les `requests` des pods.
:::

## 4. Mesurer le service

Un service de prédiction se mesure comme n'importe quel service : avec un **tir de charge**, et en lisant des **percentiles** (chapitre 26). Les mesures ci-dessous ont été obtenues avec l'outil `hey`, sur le service ci-dessus, modèle de Listify chargé, sur un poste Linux à 22 cœurs.

```bash
hey -n 3000 -c 10 -m POST -T application/json \
    -d '{"titre":"acheter du pain"}' http://localhost:8000/suggestion
```

| Configuration | Concurrence | Débit (req/s) | Médiane | 95ᵉ pct | 99ᵉ pct |
|---|---|---|---|---|---|
| 1 worker | 1 | 286 | 3,3 ms | 4,3 ms | 5,5 ms |
| 1 worker | 10 | 291 | 32,6 ms | 55,7 ms | 69,4 ms |
| 1 worker | 50 | 268 | 176,7 ms | 278,3 ms | 373,2 ms |
| 4 workers | 10 | 952 | 8,4 ms | 20,0 ms | 26,7 ms |
| 4 workers | 50 | 804 | 45,4 ms | 87,1 ms | 134,5 ms |
| 4 workers | 100 | 861 | 105,2 ms | 153,5 ms | 209,6 ms |

<Figure src="latence-debit" num="33.3" alt="Deux graphiques. À gauche, le débit en requêtes par seconde selon la concurrence : avec 1 worker, il reste plat autour de 270 à 290 ; avec 4 workers, il monte à environ 950 puis oscille entre 800 et 860. À droite, la latence médiane selon la concurrence : avec 1 worker, elle croît de 3 ms à 177 ms ; avec 4 workers, de 8 ms à 105 ms.">
  Débit et latence mesurés. Passé le point de saturation, **le débit n'augmente plus** : seule la latence croît, proportionnellement au nombre de requêtes en vol.
</Figure>

:::exemple[Exemple 33.3 : la loi de Little, vérifiée au banc d'essai]
Avec un worker, le débit plafonne autour de 280 requêtes par seconde dès la concurrence 10. La loi de Little (chapitre 30, §4.3) prédit alors la latence : si $L$ requêtes sont en vol et que le service en traite $\lambda$ par seconde, chacune passe $W = L / \lambda$ dans le système.

- Concurrence 10 : $W = 10 / 291 \approx 34$ ms. **Mesuré : 32,6 ms.**
- Concurrence 50 : $W = 50 / 268 \approx 187$ ms. **Mesuré : 176,7 ms.**

L'accord est à quelques pour cent. La leçon est importante : au-delà de la saturation, **augmenter la charge n'augmente plus le débit**, elle ne fait qu'allonger la file. Un service qui répond en 3 ms à vide et en 177 ms sous charge n'est pas « devenu lent » : il est saturé, et la seule issue est d'ajouter de la capacité ou de refuser du trafic (§5).
:::

:::exemple[Exemple 33.4 : quatre workers, mais pas quatre fois plus de débit]
Passer de 1 à 4 workers fait passer le débit de 291 à 952 requêtes par seconde, soit un facteur **3,3** pour 4 fois plus de processus. L'écart vient de ce que les workers partagent la machine (mémoire, caches, ordonnanceur) et que scikit-learn utilise lui-même plusieurs fils d'exécution pour l'algèbre linéaire.

Côté mémoire, les 6 processus mesurés (un maître, quatre workers, un superviseur) occupaient **1,3 Gio** au total, soit environ 220 Mio par worker pour un modèle qui pèse moins de 1 Mio sur le disque : l'essentiel, ce sont NumPy, SciPy, pandas, scikit-learn et MLflow chargés en mémoire. C'est le chiffre à retenir quand on dimensionne les `requests` d'un pod (chapitre 21).

**Règle pratique** : mesurez avec **votre** modèle avant de choisir le nombre de workers. Un worker par cœur est un point de départ, pas une réponse.
:::

:::exemple[Exemple 33.5 : le lot, encore une fois]
Le service expose aussi `/suggestions`, qui traite un lot de titres. Mesures à concurrence 10, 4 workers :

| Requêtes | Débit (req/s) | Prédictions par seconde | Médiane |
|---|---|---|---|
| 1 titre par requête | 952 | **952** | 8,4 ms |
| 32 titres par requête | 757 | **24 224** | 10,3 ms |
| 256 titres par requête | 358 | **91 648** | 19,5 ms |

Passer de 1 à 32 titres par requête multiplie le nombre de prédictions par seconde par **25**, en n'augmentant la latence que de 2 ms. C'est la même économie qu'au chapitre 30, §8 : le coût fixe d'une requête (réseau, HTTP, JSON, appel du modèle) est amorti sur tout le lot.

**Ce que cela change en pratique.** Une page qui affiche 20 tâches doit demander **une** requête de 20 titres, et non 20 requêtes : elle divise par vingt le travail du service et échappe à la queue de latence de l'exemple 30.4. La tâche nocturne du chapitre 30, elle, appellera `/suggestions` par lots de 256.
:::

## 5. Protéger le service

Un service de prédiction est un composant sur le chemin critique d'une application. Il doit se défendre.

- **Limiter les tailles.** `max_length=200` sur le titre, 256 titres par lot : sans cela, un client peut envoyer un lot de 100 000 titres et bloquer un worker pendant des minutes. C'est une limite de **contrat**, pas une optimisation.
- **Fixer des délais d'attente.** Côté client (le backend Listify), un délai court : au-delà, on renonce à la suggestion (chapitre 30, §6.1). Côté serveur, l'option `--timeout` de Gunicorn tue un worker bloqué.
- **Refuser plutôt que subir.** Quand la file dépasse un seuil, mieux vaut répondre **429** ou **503** immédiatement que d'accepter des requêtes dont la réponse arrivera trop tard : c'est le délestage (*load shedding*) décrit par le livre SRE de Google, qui évite l'effondrement en cascade [^sre].
- **Isoler les ressources.** Un service de prédiction qui partage son pod avec le backend fait de la lenteur du modèle la lenteur de l'application : c'est l'argument du chapitre 30, §7.

:::exemple[Exemple 33.6 : dimensionner pour une pointe]
Objectif : absorber 600 requêtes par seconde à la pointe, avec une médiane sous 20 ms.

**Avec les mesures du §4.** Un worker sature vers 290 requêtes par seconde ; 4 workers tiennent 950. À 600 requêtes par seconde sur 4 workers, le taux d'occupation vaut :

$$
\rho = \frac{600}{950} \approx 0{,}63,
$$

dans la zone recommandée au chapitre 30 (rester sous 60 à 70 %). La latence médiane mesurée à concurrence 10 est de 8,4 ms : l'objectif est tenu avec de la marge.

**Combien de répliques ?** Une réplique de 4 workers suffit au débit, mais pas à la disponibilité : la perte d'une réplique enlèverait 100 % de la capacité. On déploie **3 répliques de 2 workers** (environ 1 400 requêtes par seconde de capacité théorique), ce qui laisse survivre à la perte d'une réplique tout en restant sous 65 % d'occupation. Coût mémoire : $3 \times 2 \times 220 \text{ Mio} \approx 1{,}3$ Gio.
:::

[^sre]: Betsy Beyer et al. (dir.), *Site Reliability Engineering*, O'Reilly, 2016, chapitre 22, « Addressing Cascading Failures ».

## 6. Observer le service

Le chapitre 26 a instrumenté Listify avec les signaux RED (débit, erreurs, durée). Un service de modèle a besoin des mêmes, **plus** de signaux propres au ML :

| Signal | Exemple de métrique | Ce qu'il détecte |
|---|---|---|
| Débit, erreurs, durée (RED) | `http_requests_total`, histogramme des durées | Saturation, panne, régression de performance |
| Version servie | `modele_version_info{version="..."}` | Une réplique qui sert encore l'ancien modèle après une promotion |
| Distribution des classes prédites | `predictions_total{categorie="courses"}` | Un modèle qui se met à tout classer pareil (chapitre 27) |
| Confiance moyenne | Histogramme de la confiance | Une entrée qui s'éloigne de l'entraînement |
| Taux de rejet à la validation | `erreurs_422_total` | Un client qui change de format sans prévenir |

Les trois dernières lignes sont la matière première du chapitre 35 : la surveillance de la **dérive**. Une pratique s'impose dès maintenant : **journaliser un échantillon des prédictions** (entrée, sortie, confiance, version du modèle, horodatage). Sans ce journal, aucune détection de dérive ni réentraînement supervisé n'est possible plus tard. Avec lui, attention aux données personnelles : un titre de tâche en est une (chapitre 38).

## 7. Conteneuriser

Le service devient une image OCI, construite par la chaîne du semestre 2 :

```dockerfile title="Containerfile"
FROM docker.io/library/python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY service.py .

RUN useradd --create-home --uid 10001 service
USER service

EXPOSE 8000
CMD ["gunicorn", "service:app", "-k", "uvicorn.workers.UvicornWorker", \
     "-w", "2", "-b", "0.0.0.0:8000", "--timeout", "60"]
```

:::exemple[Exemple 33.7 : une image six fois plus grosse que l'application]
Mesures relevées lors de la préparation :

| Image | Taille | Construction |
|---|---|---|
| Backend Listify (semestre 2) | 151 Mo | quelques dizaines de secondes |
| Service de prédiction | **922 Mo** | 4 min 19 s |

Les 770 Mo d'écart sont presque entièrement des bibliothèques scientifiques : NumPy, SciPy, pandas, scikit-learn, MLflow et leurs dépendances. Conséquences très concrètes :

- **Le premier démarrage sur un nœud** doit télécharger 922 Mo. Sur un lien à 100 Mbit/s, c'est environ 75 s avant même que le conteneur ne commence à démarrer.
- **Chaque mise à jour du service** repousse cette image dans le registre et sur les nœuds ; d'où l'importance de l'ordre des couches (les dépendances avant le code, comme ci-dessus : changer `service.py` ne reconstruit que la dernière couche).
- **Les pistes de réduction** : n'installer que ce qui sert (`mlflow-skinny` plutôt que `mlflow` si l'on ne charge le modèle que depuis un chemin), construire en plusieurs étapes, ou embarquer le modèle et se passer du client MLflow.

**Le démarrage mesuré** : 8,5 s entre `podman run` et la première réponse de `/sante`, dont 6,0 s de chargement du modèle. C'est la figure 33.2.
:::

:::danger[Deux pièges rencontrés en préparant ce chapitre]
**Le chemin absolu des artefacts.** Le service, lancé dans un conteneur, a d'abord échoué avec `MlflowException: No such artifact: ''`. En base, MLflow avait enregistré le chemin **absolu** des artefacts sur la machine d'entraînement ; ce chemin n'existe pas dans le conteneur. C'est la raison d'être d'un stockage d'artefacts **partagé** (S3, MinIO) plutôt qu'un dossier local : le service, l'entraînement et le registre doivent désigner les artefacts de la même façon, où qu'ils tournent.

**Les droits sur les fichiers montés.** Le conteneur tourne sous un utilisateur non privilégié (`uid 10001`), bonne pratique de sécurité du chapitre 17. Un dossier monté depuis l'hôte, appartenant à un autre utilisateur, a donné `PermissionError` au chargement du modèle. Le remède n'est pas de repasser en `root`, mais de servir les artefacts par le réseau (stockage objet) plutôt que par un montage.
:::

## 8. Changer de modèle sans changer de code

Le service charge `models:/listify-categorie@champion` **au démarrage**. Que se passe-t-il quand le chapitre 31 déplace l'alias vers une nouvelle version ?

- **Rien**, tant que les répliques tournent : elles servent le modèle chargé. C'est un avantage (la promotion ne casse rien) et une contrainte (il faut agir pour qu'elle prenne effet).
- **Le déclenchement le plus simple** est un redéploiement (`kubectl rollout restart`), qui recrée les répliques une à une : chacune recharge l'alias, le déploiement progressif du chapitre 24 s'applique tel quel, et le retour arrière consiste à remettre l'alias puis à redéployer.
- **Une alternative** est une route d'administration `POST /recharger`, ou un rechargement périodique. Elle évite le redéploiement, mais introduit deux difficultés : des répliques qui servent des modèles différents pendant quelques secondes, et une route qui change le comportement du service en production, donc à protéger.
- **La version servie doit être exposée** (`/sante`) et **journalisée** avec chaque prédiction. Sans cela, on ne peut pas relier un incident à un modèle, ni vérifier qu'une promotion a bien pris effet partout.

Le TP 25 déploiera ce service sur le cluster du semestre 2, et le TP 27 reliera promotion et déploiement dans une seule chaîne.

## Ce qu'il faut retenir

<div className="retenir">

1. Servir un modèle, c'est publier et tenir un **contrat** : entrées validées, sorties typées, erreurs distinctes (422 pour une entrée invalide, 503 pour un modèle absent), objectif de latence, version exposée.
2. **FastAPI + Pydantic** transforment ce contrat en code : la validation renvoie l'emplacement exact du problème, et le `response_model` garantit la forme de la réponse.
3. Le modèle se charge **au démarrage** (5 à 6 s mesurées), jamais par requête. La sonde de **disponibilité** attend ce chargement ; la sonde de **vivacité** doit être plus patiente que lui.
4. Un service se mesure avec un tir de charge et des **percentiles**. Passé la saturation, le débit plafonne et seule la latence croît : $W = L/\lambda$, vérifié à quelques pour cent (34 ms prédites, 32,6 mesurées).
5. Le parallélisme rend moins que promis : 4 workers ont donné **3,3 fois** le débit d'un seul, pour environ 220 Mio de mémoire chacun.
6. Le **traitement par lot** est la plus grande économie disponible : 25 fois plus de prédictions par seconde avec des lots de 32, pour 2 ms de latence en plus.
7. Un service se **protège** : tailles bornées, délais d'attente, délestage (429/503) plutôt qu'effondrement, isolation des ressources.
8. On observe RED **plus** des signaux de ML (version servie, distribution des classes, confiance, rejets), et l'on journalise un échantillon des prédictions : c'est la matière du chapitre 35.
9. L'image d'un service de ML est **grosse** (922 Mo mesurés contre 151 Mo pour l'application) et lente à démarrer : ordonner les couches, alléger les dépendances, prévoir le téléchargement dans les délais de mise à l'échelle.
10. Les artefacts du modèle doivent être accessibles **de la même façon** depuis l'entraînement et le service : stockage objet partagé, pas de chemin local ni de montage.
11. Promouvoir un modèle ne change rien tant que les répliques n'ont pas rechargé : le redéploiement progressif est le déclencheur le plus simple et le plus sûr.

</div>

## Regard recherche

:::recherche
Servir des modèles efficacement est un champ actif, qui recoupe le service sans serveur et l'ordonnancement :

- **Yanan Yang et al. et les travaux sur le démarrage à froid**, en particulier **Mohammad Shahrad et al., « Serverless in the Wild: Characterizing and Optimizing the Serverless Workload at a Large Cloud Provider », *USENIX ATC*, 2020.** Une caractérisation des charges sans serveur et des politiques pour éviter le démarrage à froid : c'est exactement le problème des 6 secondes de chargement du §3, à l'échelle d'un fournisseur.
- **Vatche Ishakian, Vinod Muthusamy, Aleksander Slominski, « Serving Deep Learning Models in a Serverless Platform », *IC2E*, 2018.** Une évaluation des plateformes sans serveur pour l'inférence, et de leurs limites (taille des modèles, démarrage).
- **Chengliang Zhang et al., « MArk: Exploiting Cloud Services for Cost-Effective, SLO-Aware Machine Learning Inference Serving », *USENIX ATC*, 2019.** Comment tenir un objectif de latence au moindre coût en combinant machines réservées et exécution sans serveur pour les pointes.
- **Yunseong Lee et al., « PRETZEL: Opening the Black Box of Machine Learning Prediction Serving Systems », *OSDI*, 2018.** Au lieu de servir chaque modèle comme une boîte noire, décomposer les pipelines pour partager les opérateurs entre modèles : gains d'un ordre de grandeur en mémoire et en latence.
- **Daniel Crankshaw et al., « Clipper », *NSDI*, 2017** (chapitre 30) pour le regroupement adaptatif, dont le §4 mesure ici l'effet le plus simple.

Piste d'innovation : le §4 montre qu'un service de prédiction passe l'essentiel de son temps **hors** du modèle (HTTP, JSON, pandas). Réduire ce coût fixe, par des formats binaires, du regroupement automatique ou des runtimes compilés, rapporte plus que d'optimiser le modèle lui-même. Peu d'équipes le mesurent avant d'optimiser.
:::

## Bibliographie du chapitre

<div className="biblio">

### Sources primaires

- Documentation de FastAPI et de Pydantic (validation, `response_model`, cycle de vie). [fastapi.tiangolo.com](https://fastapi.tiangolo.com/)
- Documentation de MLflow, « Deploy MLflow Model as a Local Inference Server » et « MLflow Models ».
- Betsy Beyer et al. (dir.), *Site Reliability Engineering*, O'Reilly, 2016, chapitres 21 et 22 (gestion de la surcharge, pannes en cascade).

### Lectures recommandées

- Chip Huyen, *Designing Machine Learning Systems*, O'Reilly, 2022, chapitre 7 : service de prédiction, compression de modèles, matériel.
- Documentation de KServe et de BentoML, deux façons d'automatiser ce que ce chapitre construit à la main (chapitre 34).

### Pour aller plus loin

- Les articles de la rubrique « Regard recherche ».
- Documentation de Gunicorn et d'Uvicorn : modèle de processus, `--timeout`, `--preload`, signaux d'arrêt.

</div>
