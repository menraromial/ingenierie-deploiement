---
title: "Présentation du bloc"
sidebar_label: "Présentation du bloc"
hide_title: true
---

import ChapterHead from '@site/src/components/ChapterHead';

<ChapterHead
  kicker="Semestre 3 · Bloc 1"
  title="Bloc 1 : pourquoi le ML en production est différent"
  lecture="5 min"
  competences={['C1', 'C2', 'C4']}
/>

**Semaines 1 à 3.** Vous savez déployer, automatiser et observer une application classique. Ce bloc montre pourquoi cela ne suffit plus dès qu'une partie du comportement est **apprise à partir des données** : un modèle se dégrade sans que personne n'y touche, sa panne ne lève aucune erreur, et le résultat d'un entraînement dépend de données, de paramètres et d'aléas qu'il faut savoir figer pour le reproduire.

## Le fil conducteur : reproduire avant d'automatiser

Au semestre 1, on déployait à la main avant d'automatiser, pour savoir ce que l'outil remplace. Le semestre 3 suit la même logique. Au TP 22, vous recevrez un notebook de « recherche » qui produit un excellent modèle... et que vous ne parviendrez pas à ré-exécuter. Ce n'est qu'après avoir vécu cette impuissance que vous restructurerez le projet et versionnerez ses données, au TP 23. On ne peut ni orchestrer, ni déployer, ni surveiller un entraînement qu'on ne sait pas reproduire.

## Organisation du bloc

| Semaine | CM | TP |
|---|---|---|
| 1 | [Ch. 27 : Pourquoi le ML en production est différent](cours/27-dette-technique-ml.md) | [TP 22 : le notebook irreproductible (chaos volontaire)](tp/tp22-notebook-irreproductible.md) |
| 2 | [Ch. 28 : Versionner le code, les données et le modèle](cours/28-versionner-donnees-modeles.md) | TP 23 : du notebook au projet reproductible, avec DVC |
| 3 | [Ch. 29 : Le cycle de vie MLOps](cours/29-cycle-vie-mlops.md) ; [Ch. 30 : Les modes de mise à disposition d'un modèle](cours/30-modes-mise-a-disposition.md) | TP 23 (fin) |

## Ce que vous saurez faire à la fin du bloc

- Expliquer, exemples chiffrés à l'appui, pourquoi un système de ML accumule une dette technique propre (Sculley et al., 2015).
- Identifier sur un projet réel l'intrication des variables, les dépendances de données instables, le décalage entre entraînement et service et les boucles de rétroaction.
- Rendre un entraînement reproductible : code, données, configuration, graines aléatoires, environnement.
- Situer une équipe sur l'échelle de maturité MLOps et choisir un mode de mise à disposition adapté à un besoin.
