# Semestre 3 : Mise en production des produits d'IA et de la donnée (MLOps & Big Data)

**Objectif général :** appliquer toute la stack des semestres 1-2 au cas particulier, et plus difficile, des produits pilotés par les données et les modèles.

**Prérequis :** S1 + S2 ; bases de Python et de machine learning (un modèle scikit-learn suffit ; ce n'est **pas** un cours de ML, c'est un cours d'industrialisation du ML).

!!! info "Contenu en cours de rédaction"
    Le contenu détaillé de ce semestre sera publié bloc par bloc, dans l'ordre du parcours. Le plan ci-dessous est contractuel.

## Plan du semestre

### Bloc 1 : pourquoi le ML en production est différent (semaines 1 à 3)

- Dette technique du ML : lecture guidée du papier *Hidden Technical Debt in Machine Learning Systems* (Google, NeurIPS 2015).
- Les trois axes de versionnement : code (Git), données (DVC), modèles (registres) ; reproductibilité d'une expérience.
- Cycle de vie MLOps et niveaux de maturité 0/1/2 (Google) ; patterns de serving (batch, temps réel, streaming).
- **TP 1 et 2** : le notebook « recherche » irreproductible (chaos volontaire), puis restructuration en projet propre versionné avec DVC.

### Bloc 2 : outillage du cycle de vie, MLflow et Airflow (semaines 4 à 8)

- Suivi d'expériences : MLflow Tracking, Models (pyfunc), Model Registry.
- Orchestration de workflows : le DAG ; orchestrateur de *services* (Kubernetes) vs orchestrateur de *tâches* (Airflow).
- Airflow : scheduler, executor, tâches idempotentes, backfill, capteurs, XCom.
- Serving : FastAPI, validation Pydantic, tests de charge, conteneurisation.
- **TP 3 à 6** : instrumentation MLflow, API de serving déployée sur le cluster du S2, DAG complet d'entraînement, chaîne intégrée « CD du modèle ».

### Bloc 3 : Kubeflow, monitoring des modèles et Big Data (semaines 9 à 13)

- ML sur Kubernetes : Kubeflow Pipelines, KServe ; comparaison critique avec Airflow.
- Monitoring spécifique au ML : data drift, concept drift, performance différée, Evidently.
- Big Data : les 3V, MapReduce, Spark (comprendre le shuffle), Parquet vs CSV, Kafka, lakehouse en panorama.
- Éthique et responsabilité de la mise en production d'IA : biais à l'échelle, équité, RGPD, model cards.
- **TP 7 à 10** : Spark en local sur plusieurs Go, Kafka KRaft, boucle de drift complète avec ré-entraînement automatique, KServe en découverte.

## Évaluation du semestre

| Épreuve | Poids | Modalités |
|---|---|---|
| Contrôle continu | 20 % | TP notés + fiche de lecture critique (*Hidden Technical Debt*) |
| Projet final de parcours | 50 % | Par trinôme : industrialiser de bout en bout un produit IA au choix. Données versionnées, entraînement reproductible orchestré, tracking + registry, serving conteneurisé déployé via CI/CD, monitoring technique et de drift, ré-entraînement automatisé. Livrables : dépôt Git, architecture documentée, démo live, post-mortem d'une panne simulée |
| Examen théorique | 30 % | Questions transversales aux 3 semestres |
