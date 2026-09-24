---
title: "Vue d'ensemble"
sidebar_label: "Vue d'ensemble"
hide_title: true
---

import ChapterHead from '@site/src/components/ChapterHead';

<ChapterHead
  kicker="Semestre 3 · MLOps et big data"
  title="Semestre 3 : Mise en production des produits d'IA et de la donnée (MLOps & Big Data)"
  lecture="5 min"
/>

**Objectif général :** appliquer toute la stack des semestres 1-2 au cas particulier, et plus difficile, des produits pilotés par les données et les modèles.

**Prérequis :** S1 + S2 ; bases de Python et de machine learning (un modèle scikit-learn suffit ; ce n'est **pas** un cours de ML, c'est un cours d'industrialisation du ML).

:::info[Contenu en cours de rédaction]
Le semestre est publié chapitre par chapitre, dans l'ordre du parcours. La numérotation poursuit celle des semestres précédents : chapitres 27 à 38, TP 22 à 31. Le plan ci-dessous est contractuel.
:::

## Le fil rouge : Listify apprend à suggérer une catégorie

Listify reste l'application déployée depuis le semestre 1. On lui ajoute un modèle d'apprentissage automatique qui, à la saisie d'une tâche, **suggère une catégorie** (travail, courses, maison, administratif, loisirs). Ce modèle simple, un classifieur de textes, suffit à faire surgir tous les problèmes du semestre : reproductibilité, suivi des expériences, orchestration de l'entraînement, service des prédictions, dérive des données. Le chapitre 27 raconte comment il se dégrade en silence quand on le déploie sans précaution.

## Plan du semestre

### [Bloc 1](bloc1/index.md) : pourquoi le ML en production est différent (semaines 1 à 3)

- [Ch. 27](bloc1/cours/27-dette-technique-ml.md) : pourquoi le ML en production est différent, la dette technique cachée (Sculley et al., NeurIPS 2015).
- [Ch. 28](bloc1/cours/28-versionner-donnees-modeles.md) : versionner le code, les données et le modèle ; reproductibilité d'une expérience (DVC).
- [Ch. 29](bloc1/cours/29-cycle-vie-mlops.md) : le cycle de vie MLOps et ses niveaux de maturité 0, 1 et 2 (Google).
- [Ch. 30](bloc1/cours/30-modes-mise-a-disposition.md) : les modes de mise à disposition d'un modèle (batch, temps réel, flux ; modèle embarqué ou modèle-service).
- **[TP 22](bloc1/tp/tp22-notebook-irreproductible.md) et [TP 23](bloc1/tp/tp23-projet-reproductible-dvc.md)** : le notebook « recherche » irreproductible (chaos volontaire), puis restructuration en projet propre versionné avec DVC.

### [Bloc 2](bloc2/index.md) : outillage du cycle de vie, MLflow et Airflow (semaines 4 à 8)

- [Ch. 31](bloc2/cours/31-suivi-experiences-mlflow.md) : suivi d'expériences et registre de modèles (MLflow Tracking, Models, Model Registry).
- [Ch. 32](bloc2/cours/32-orchestrer-dag-airflow.md) : orchestrer des tâches, le DAG et Airflow (scheduler, executor, tâches idempotentes, backfill, capteurs, XCom) ; orchestrateur de *services* contre orchestrateur de *tâches*.
- [Ch. 33](bloc2/cours/33-servir-un-modele.md) : servir un modèle (FastAPI, validation Pydantic, tests de charge, conteneurisation).
- **[TP 24](bloc2/tp/tp24-suivi-mlflow.md), [TP 25](bloc2/tp/tp25-servir-modele-cluster.md), [TP 26](bloc2/tp/tp26-dag-airflow.md) et [TP 27](bloc2/tp/tp27-chaine-integree.md)** : instrumentation MLflow, API de serving déployée sur le cluster du S2, DAG complet d'entraînement, chaîne intégrée « CD du modèle ».

### [Bloc 3](bloc3/index.md) : Kubeflow, monitoring des modèles et Big Data (semaines 9 à 13)

- [Ch. 34](bloc3/cours/34-ml-sur-kubernetes.md) : le ML sur Kubernetes (Kubeflow Pipelines, KServe), comparaison critique avec Airflow.
- [Ch. 35](bloc3/cours/35-surveiller-derive.md) : surveiller un modèle, dérive des données et des concepts, performance différée (Evidently).
- [Ch. 36](bloc3/cours/36-big-data-calcul-distribue.md) : big data et calcul distribué (les 3V, MapReduce, Spark et le shuffle, Parquet contre CSV, lakehouse en panorama).
- Ch. 37 : les flux de données (Kafka, traitements en continu).
- Ch. 38 : éthique et responsabilité de la mise en production d'IA (biais à l'échelle, équité, RGPD, model cards).
- **TP 28 à 31** : KServe en découverte ([TP 28](bloc3/tp/tp28-kserve.md)), boucle de dérive complète avec réentraînement automatique ([TP 29](bloc3/tp/tp29-boucle-derive.md)), Spark en local sur plusieurs Go ([TP 30](bloc3/tp/tp30-spark-local.md)), Kafka en mode KRaft (TP 31).

## Évaluation du semestre

| Épreuve | Poids | Modalités |
|---|---|---|
| Contrôle continu | 20 % | TP notés + fiche de lecture critique (*Hidden Technical Debt*) |
| Projet final de parcours | 50 % | Par trinôme : industrialiser de bout en bout un produit IA au choix. Données versionnées, entraînement reproductible orchestré, tracking + registry, serving conteneurisé déployé via CI/CD, monitoring technique et de drift, ré-entraînement automatisé. Livrables : dépôt Git, architecture documentée, démo live, post-mortem d'une panne simulée |
| Examen théorique | 30 % | Questions transversales aux 3 semestres |
