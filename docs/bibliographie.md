# Bibliographie générale du parcours

Chaque chapitre du cours se termine par sa propre bibliographie commentée, précise et directement exploitable. Cette page recense les **ouvrages socles**, ceux qui couvrent plusieurs blocs et que la bibliothèque de l'école devrait posséder.

## Ouvrages socles

1. **Kief Morris, *Infrastructure as Code: Dynamic Systems for the Cloud Age*, 2ᵉ édition, O'Reilly, 2020.**
   La référence conceptuelle du semestre 1, bloc 3. Morris a formalisé le vocabulaire du domaine : *configuration drift*, *snowflake servers*, *cattle vs pets*, pipelines d'infrastructure. Lire en priorité les chapitres 1 à 4 (principes) ; le reste sert de référence.

2. **Nigel Poulton, *The Kubernetes Book*, édition 2024 (auto-publié, mise à jour annuelle).**
   L'introduction la plus pédagogique à Kubernetes, semestre 2, bloc 2. À compléter systématiquement par la section « Concepts » de la documentation officielle ([kubernetes.io/docs/concepts](https://kubernetes.io/docs/concepts/)), qui fait autorité.

3. **Jez Humble et David Farley, *Continuous Delivery: Reliable Software Releases through Build, Test, and Deployment Automation*, Addison-Wesley, 2010.**
   L'ouvrage fondateur du CI/CD (semestre 2, bloc 3). Antérieur aux conteneurs, donc certains exemples ont vieilli, mais les principes (pipeline de déploiement, « if it hurts, do it more often », promotion d'artefacts) sont intemporels et tombent à l'examen.

4. **Betsy Beyer, Chris Jones, Jennifer Petoff, Niall Murphy (dir.), *Site Reliability Engineering: How Google Runs Production Systems*, O'Reilly, 2016.**
   Gratuit en ligne : [sre.google/sre-book](https://sre.google/sre-book/table-of-contents/). Référence pour l'exploitation, les SLI/SLO et la culture du post-mortem (semestres 2 et 3). Chapitres recommandés : 1 (Introduction), 4 (Service Level Objectives), 15 (Postmortem Culture).

5. **D. Sculley et al., « Hidden Technical Debt in Machine Learning Systems », *Advances in Neural Information Processing Systems 28* (NeurIPS), 2015.**
   Le papier fondateur du MLOps, lecture obligatoire et fiche de lecture notée au semestre 3. Disponible : [papers.nips.cc](https://papers.nips.cc/paper_files/paper/2015/hash/86df7dcfd896fcaf2674f757a2463eba-Abstract.html).

6. **Chip Huyen, *Designing Machine Learning Systems*, O'Reilly, 2022.**
   Le manuel de référence du semestre 3 : serving, monitoring, drift, boucles de feedback. Écriture claire, exemples industriels réels.

7. **Martin Kleppmann, *Designing Data-Intensive Applications*, O'Reilly, 2017.**
   Pour le bloc Big Data du semestre 3 (et bien au-delà). Les chapitres 1 à 3 (fondations) et 10 à 11 (batch et streaming) sont ceux exploités par le cours.

## Références en ligne permanentes

| Ressource | URL | Usage dans le parcours |
|---|---|---|
| The Twelve-Factor App (Adam Wiggins, Heroku, 2011) | [12factor.net/fr](https://12factor.net/fr/) | S1 bloc 1 (facteurs 1 à 5), puis relecture complète au S2 |
| Documentation Debian (Administration) | [debian.org/doc](https://www.debian.org/doc/) | S1, système de référence des TP |
| Documentation Ansible | [docs.ansible.com](https://docs.ansible.com/) | S1 bloc 3 |
| Documentation Podman | [docs.podman.io](https://docs.podman.io/) | S2 bloc 1 |
| Documentation Kubernetes (Concepts) | [kubernetes.io/docs/concepts](https://kubernetes.io/docs/concepts/) | S2 bloc 2 |
| Documentation MLflow | [mlflow.org/docs](https://mlflow.org/docs/latest/index.html) | S3 bloc 2 |
| Documentation Apache Airflow | [airflow.apache.org/docs](https://airflow.apache.org/docs/) | S3 bloc 2 |
| Google Cloud, « MLOps: Continuous delivery and automation pipelines in machine learning » | [cloud.google.com/architecture/mlops-continuous-delivery-and-automation-pipelines-in-machine-learning](https://cloud.google.com/architecture/mlops-continuous-delivery-and-automation-pipelines-in-machine-learning) | S3, niveaux de maturité MLOps |

## Comment lire une bibliographie de chapitre

Chaque chapitre distingue trois niveaux :

- **Sources primaires** : documentation officielle, RFC, papiers de recherche. C'est ce qui fait foi en cas de doute, et ce que cite l'examen.
- **Lectures recommandées** : chapitres précis d'ouvrages, articles de fond. Pour consolider après le cours.
- **Pour aller plus loin** : approfondissements facultatifs, souvent historiques ou techniques, pour les curieux.

Une compétence d'ingénieur à part entière : **remonter à la source**. Quand un billet de blog contredit la documentation officielle, la documentation gagne ; quand la documentation contredit la RFC, la RFC gagne.
