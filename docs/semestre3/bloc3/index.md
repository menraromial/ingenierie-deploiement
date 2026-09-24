---
title: "Présentation du bloc"
sidebar_label: "Présentation du bloc"
hide_title: true
---

import ChapterHead from '@site/src/components/ChapterHead';

<ChapterHead
  kicker="Semestre 3 · Bloc 3"
  title="Bloc 3 : le ML à l'échelle, surveillé et responsable"
  lecture="5 min"
  competences={['C1', 'C5', 'C6']}
/>

**Semaines 9 à 13.** À la fin du bloc 2, Listify dispose d'une chaîne complète : un modèle réentraîné chaque semaine, promu s'il le mérite, servi par une API sur Kubernetes, et un code livré en continu. Ce dernier bloc pose les questions qui viennent **après** la mise en production : peut-on confier toute cette chaîne à Kubernetes lui-même ? Comment savoir qu'un modèle se dégrade, alors que sa panne ne lève aucune erreur ? Que faire quand les données ne tiennent plus sur une machine, ou quand elles arrivent en flux continu ? Et que doit-on aux personnes dont le modèle décide ?

## Le fil conducteur : du modèle qui marche au système qui dure

Les chapitres 34 à 37 élargissent la chaîne dans quatre directions : l'orchestration native de Kubernetes (Kubeflow, KServe), la surveillance de la qualité des prédictions et de la dérive des données, le calcul distribué pour les gros volumes (Spark), et le traitement en continu (Kafka). Le chapitre 38 revient sur ce que le semestre a construit, sous l'angle de la responsabilité : biais, équité, données personnelles, documentation des modèles.

## Organisation du bloc

| Semaine | CM | TP |
|---|---|---|
| 9 | [Ch. 34 : Le ML sur Kubernetes, Kubeflow Pipelines et KServe](cours/34-ml-sur-kubernetes.md) | [TP 28 : servir le modèle avec KServe](tp/tp28-kserve.md) |
| 10 | [Ch. 35 : Surveiller un modèle, la dérive](cours/35-surveiller-derive.md) | [TP 29 : la boucle de dérive complète, avec réentraînement automatique](tp/tp29-boucle-derive.md) |
| 11 | Ch. 36 : Big data et calcul distribué | TP 30 : Spark en local sur plusieurs gigaoctets |
| 12 | Ch. 37 : Les flux de données | TP 31 : Kafka en mode KRaft |
| 13 | Ch. 38 : Éthique et responsabilité de la mise en production d'IA | Soutenances |

## Ce que vous saurez faire à la fin du bloc

- Décrire un pipeline d'entraînement comme un ensemble de conteneurs sur Kubernetes, et le comparer honnêtement à un DAG Airflow.
- Surveiller un modèle en production : dérive des données, dérive des concepts, performance mesurée avec retard.
- Traiter des volumes qui ne tiennent pas en mémoire, en comprenant où le calcul distribué coûte cher.
- Consommer et produire des flux d'événements, et relier leurs garanties de livraison aux besoins d'un modèle.
- Évaluer les biais d'un modèle, documenter ses limites, et identifier ce que le RGPD impose à un système de ML.
