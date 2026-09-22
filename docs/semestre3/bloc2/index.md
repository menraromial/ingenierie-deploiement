---
title: "Présentation du bloc"
sidebar_label: "Présentation du bloc"
hide_title: true
---

import ChapterHead from '@site/src/components/ChapterHead';

<ChapterHead
  kicker="Semestre 3 · Bloc 2"
  title="Bloc 2 : outiller le cycle de vie, MLflow et Airflow"
  lecture="5 min"
  competences={['C3', 'C4', 'C5']}
/>

**Semaines 4 à 8.** À la fin du bloc 1, Listify dispose d'un entraînement reproductible : un dépôt, des données versionnées, un pipeline que `dvc repro` rejoue au bit près. Mais tout reste manuel. Les essais d'hyperparamètres ne laissent de trace que si on les commite, personne ne sait quel modèle est « le bon », le réentraînement attend qu'un humain lance une commande, et le modèle n'est servi par rien. Ce bloc outille chacun de ces maillons, pour atteindre le niveau 1 de maturité du chapitre 29, puis le niveau 2.

## Le fil conducteur : du dépôt reproductible à la livraison continue du modèle

Chaque chapitre ajoute une pièce au dépôt `listify-ml` du TP 23, sans rien jeter. MLflow garde la trace de chaque expérience et désigne, dans un registre, le modèle promu. Airflow réentraîne à intervalle régulier et ne promeut un candidat que s'il bat le champion. Une API FastAPI charge le modèle promu et le sert sur le cluster Kubernetes du semestre 2. À la fin du bloc, une modification du code ou des données produit, sans intervention humaine, un modèle évalué, promu s'il le mérite, et servi.

## Organisation du bloc

| Semaine | CM | TP |
|---|---|---|
| 4 | [Ch. 31 : Suivre les expériences et gérer les modèles avec MLflow](cours/31-suivi-experiences-mlflow.md) | TP 24 : instrumenter l'entraînement avec MLflow |
| 5 | [Ch. 32 : Orchestrer des tâches, le DAG et Airflow](cours/32-orchestrer-dag-airflow.md) | TP 24 (fin) |
| 6 | [Ch. 33 : Servir un modèle](cours/33-servir-un-modele.md) | TP 25 : servir le modèle promu, sur le cluster du semestre 2 |
| 7 |  | TP 26 : le DAG d'entraînement complet, avec promotion conditionnelle |
| 8 |  | TP 27 : la chaîne intégrée, livraison continue du modèle |

## Ce que vous saurez faire à la fin du bloc

- Tracer chaque expérience (paramètres, métriques, artefacts), comparer des dizaines d'essais et choisir un modèle sans vous laisser tromper par le bruit.
- Enregistrer un modèle avec sa signature et son environnement, le promouvoir par un alias, et revenir en arrière en une commande.
- Décrire un entraînement comme un DAG de tâches idempotentes, l'ordonnancer, le rattraper après une panne.
- Servir un modèle derrière une API validée, la tester en charge, la conteneuriser et la déployer.
- Relier ces outils en une chaîne qui livre le modèle comme la CI/CD du semestre 2 livrait l'application.
