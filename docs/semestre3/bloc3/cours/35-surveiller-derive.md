---
title: "Ch. 35 : Surveiller un modèle, la dérive"
sidebar_label: "Ch. 35 : Surveiller un modèle"
hide_title: true
---

import ChapterHead from '@site/src/components/ChapterHead';
import Figure from '@site/src/components/Figure';

<ChapterHead
  kicker="Semestre 3 · Bloc 3 · Chapitre 35"
  title="Surveiller un modèle : dérive des données, dérive des concepts"
  lecture="55 min"
  competences={['C5', 'C6']}
/>

:::objectifs
À l'issue de ce chapitre, vous saurez distinguer les trois façons dont le monde peut changer sous un modèle, et dire lesquelles se voient sans étiquettes. Vous saurez choisir des signaux de surveillance, calculer un indice de stabilité et en interpréter la valeur, éviter les fausses alertes des tests répétés, et juger ce qu'un outil comme Evidently vous dit, et ce qu'il ne vous dit pas.
:::

## 1. Un modèle qui vieillit sans bruit

Au chapitre 27, on avait raconté l'histoire d'un modèle de Listify qui, trois mois après sa mise en production, ne donnait plus la bonne catégorie qu'une fois sur cinq, sans qu'aucune alerte ne se déclenche. C'était un récit. Pour ce chapitre, on l'a rejoué pour de bon.

On a entraîné le classifieur habituel (TF-IDF et régression logistique) sur les tâches créées pendant les trois premiers mois, 4 964 au total, puis on l'a laissé « en production » pendant cinquante semaines, en calculant chaque lundi ce qu'une équipe pourrait mesurer. La précision de la première semaine était de 92,1 %. Celle des quatre dernières tourne autour de 81 %, avec des creux à 74 %. Pendant tout ce temps, le service a répondu en quelques millisecondes, sans une seule erreur HTTP. Les tableaux de bord du chapitre 26, qui surveillent le débit, les erreurs et la latence, sont restés au vert.

C'est la particularité qui justifie un chapitre entier. Un service web qui casse le fait en général bruyamment : une exception, un code 500, un délai dépassé. Un modèle qui se trompe renvoie une réponse parfaitement formée, simplement fausse. Pour le voir, il faut surveiller autre chose que le service : ce qui entre dans le modèle, ce qui en sort, et, quand on peut l'obtenir, la vérité.

<Figure src="surveillance-derive" num="35.1" alt="Deux graphiques sur cinquante semaines après la mise en production. En haut, la précision mesurée avec les étiquettes part de 92 % et descend vers 75 à 80 % à partir de la semaine 14 ; la confiance moyenne du modèle baisse légèrement, de 90 % vers 86 à 88 %. En bas, la part de mots inconnus du modèle passe de 0 à environ 5 % vers la semaine 14 et y reste ; l'indice de stabilité de la répartition des catégories prédites oscille entre 0 et 5 sans tendance. Une ligne verticale marque la semaine 21, où une dérive de concept a été injectée.">
  Cinquante semaines de surveillance, mesurées. La précision chute au moment même où la part de mots inconnus bondit ; la répartition des catégories prédites, elle, ne raconte presque rien.
</Figure>

## 2. Trois façons pour le monde de changer

Un modèle de classification apprend, en simplifiant, une relation entre des entrées $x$ (ici, un titre de tâche) et une sortie $y$ (la catégorie). On peut décomposer ce qu'il a appris en deux morceaux : la façon dont les entrées se répartissent, $P(x)$, et la règle qui relie une entrée à sa catégorie, $P(y \mid x)$. La littérature parle de *dataset shift* pour l'ensemble des situations où ces lois changent entre l'entraînement et la production, et en distingue plusieurs formes [^quinonero][^moreno].

<Figure src="types-derive" num="35.2" alt="Trois cadres. Dérive des entrées : P(x) change, la règle P(y|x) non ; par exemple de nouveaux collègues et de nouveaux dossiers, des titres jamais vus ; visible sans étiquettes. Dérive des classes : P(y) change ; à la rentrée scolaire, la part des tâches administratives double ; visible sur la répartition des prédictions, si le modèle suit. Dérive de concept : P(y|x) change ; « répondre aux mails » passe d'administratif à travail ; invisible dans les entrées, il faut les étiquettes.">
  Les trois formes de dérive, illustrées sur Listify. Seule la première se voit sans connaître la bonne réponse.
</Figure>

La **dérive des entrées** (*covariate shift*) est la plus fréquente : les utilisateurs écrivent des choses que le modèle n'a jamais vues. Dans nos données, ce sont les titres personnels (« voir Mme Durand », « relancer le dossier 7730 ») qui se renouvellent au fil des mois, parce que les collègues, les clients et les projets changent. La règle, elle, n'a pas bougé : « acheter du pain » reste une course. Mais le modèle n'a aucune règle pour ce qu'il ne connaît pas.

La **dérive des classes** (*prior shift*, ou *label shift*) touche les proportions : il y a davantage de tâches administratives en période de déclaration d'impôts, davantage de loisirs avant les vacances. Un modèle bien calibré s'en accommode souvent, mais ses erreurs changent de place, et une règle de décision réglée sur les anciennes proportions peut devenir mauvaise.

La **dérive de concept** est la plus sournoise : pour une même entrée, la bonne réponse change. Rien dans les données d'entrée ne la trahit, puisque ce sont les mêmes titres qu'avant. Gama et ses collègues, dans la synthèse de référence sur le sujet, en distinguent les formes brutales, graduelles et récurrentes [^gama].

Deux épisodes réels permettent de mesurer l'enjeu. Au printemps 2020, le confinement a modifié du jour au lendemain les achats en ligne, et de nombreux modèles de recommandation, de détection de fraude ou de gestion des stocks, entraînés sur les habitudes d'avant, ont cessé de fonctionner correctement ; des entreprises ont dû les recaler à la main [^heaven]. En 2021, Zillow a mis fin à son activité d'achat-revente de maisons, dont les prix d'achat reposaient sur ses modèles d'estimation, après avoir déprécié environ 304 millions de dollars de stock en un trimestre : les prix du marché avaient évolué autrement que les modèles ne l'anticipaient [^zillow]. Dans les deux cas, le code n'avait pas changé. Le monde, si.

[^quinonero]: Joaquin Quiñonero-Candela, Masashi Sugiyama, Anton Schwaighofer, Neil D. Lawrence (dir.), *Dataset Shift in Machine Learning*, MIT Press, 2009.

[^moreno]: Jose G. Moreno-Torres et al., « A unifying view on dataset shift in classification », *Pattern Recognition*, vol. 45, n° 1, 2012.

[^gama]: João Gama, Indrė Žliobaitė, Albert Bifet, Mykola Pechenizkiy, Abdelhamid Bouchachia, « A survey on concept drift adaptation », *ACM Computing Surveys*, vol. 46, n° 4, 2014.

[^heaven]: Will Douglas Heaven, « Our weird behavior during the pandemic is messing with AI models », *MIT Technology Review*, 2020.

[^zillow]: Zillow Group, lettre aux actionnaires du troisième trimestre 2021, et communiqué annonçant l'arrêt de Zillow Offers, novembre 2021.

## 3. La vérité arrive en retard

La mesure qui compte, c'est la précision. Encore faut-il connaître la bonne réponse, et elle n'arrive jamais au moment de la prédiction.

<Figure src="delai-etiquettes" num="35.3" alt="Une ligne de temps depuis la prédiction. Immédiatement : les entrées, la confiance, les mots inconnus. À partir d'un jour : les corrections explicites de l'utilisateur, une partie des étiquettes. À partir de sept jours : les tâches cochées sans correction, étiquettes implicites. À partir de trente jours : l'audit manuel d'un échantillon.">
  Ce que l'on sait, et quand. Les signaux sur les entrées sont disponibles tout de suite ; les étiquettes arrivent par morceaux, et certaines jamais.
</Figure>

Dans Listify, on apprend la vérité de trois façons. Quand l'utilisateur corrige la catégorie proposée, on sait que le modèle s'est trompé, et l'on connaît la bonne réponse. Quand il coche sa tâche sans avoir rien corrigé, on peut supposer que la suggestion était bonne, mais c'est une supposition : beaucoup d'utilisateurs ne regardent pas la catégorie. Et l'on peut, de temps en temps, demander à quelqu'un de vérifier un échantillon à la main. Aucune de ces sources n'est immédiate, aucune n'est complète, et la deuxième est biaisée d'une façon que le chapitre 27 a décrite : si les utilisateurs acceptent la suggestion sans la lire, le modèle se voit confirmé dans ses erreurs.

:::exemple[Exemple 35.1 : ce que vaut une précision hebdomadaire]
Chaque semaine de notre simulation compte environ 382 tâches. Si la vraie précision vaut 80 %, la précision mesurée sur 382 tâches fluctue autour de cette valeur avec un écart-type de

$$
\sqrt{\frac{0{,}8 \times 0{,}2}{382}} \approx 0{,}020,
$$

soit deux points. Un écart de deux points d'une semaine à l'autre ne signifie donc rien. Dans la figure 35.1, la précision passe sous 85 % dès la sixième semaine, puis remonte : c'est du bruit.

Et ce calcul suppose qu'on connaît la bonne réponse pour **toutes** les tâches de la semaine. Si seules 20 % reçoivent une étiquette fiable, on mesure sur 76 tâches, et l'écart-type monte à $\sqrt{0{,}16 / 76} \approx 4{,}6$ points. Pour distinguer une vraie baisse de cinq points, il faudrait alors agréger plusieurs semaines, et donc attendre. Voilà pourquoi on ne peut pas se contenter de surveiller la précision : elle arrive tard, et quand elle arrive, elle est bruitée.
:::

## 4. Surveiller sans connaître la réponse

Il reste ce qu'on mesure immédiatement, sans étiquette. Trois familles de signaux sont possibles pour Listify, et la simulation permet de dire lesquelles auraient servi.

La première regarde les **entrées**. Pour un modèle de texte, la plus parlante est la part de mots que le modèle ne connaît pas : un mot absent du vocabulaire appris ne pèse rien dans la décision. Pendant les trois premiers mois, cette part vaut 0 % par construction ; dans la figure 35.1, elle grimpe à partir de la semaine 10 et se stabilise autour de 5 %. Sur les cinquante semaines, sa corrélation avec la précision vaut **-0,89**. C'est de loin le meilleur signal de cette simulation.

La deuxième regarde la **confiance** du modèle, la probabilité qu'il attribue à la catégorie choisie. Quand il rencontre des titres qu'il ne comprend pas, il hésite davantage. Sa moyenne hebdomadaire passe de 90 % à 86-88 %, et sa corrélation avec la précision vaut 0,85. C'est un signal utile, à une réserve près : un modèle mal calibré peut rester très confiant en se trompant.

La troisième regarde les **sorties** : la répartition des catégories prédites. C'est le signal qu'on installe en premier, parce qu'il est simple et vaut pour n'importe quel modèle. Ici, il n'a presque rien vu : sa corrélation avec la précision est de 0,17. Le modèle continue de répartir ses réponses à peu près comme avant ; il se trompe simplement davantage à l'intérieur de chaque catégorie.

On mesure l'écart entre deux répartitions avec l'**indice de stabilité de la population** (PSI), venu de la notation du crédit, où l'on surveille depuis longtemps que la clientèle notée ressemble à celle sur laquelle le modèle a été construit [^siddiqi]. Pour des proportions de référence $a_i$ et observées $o_i$ :

$$
\mathrm{PSI} = \sum_i (o_i - a_i)\,\ln\frac{o_i}{a_i}.
$$

L'usage, dans ce domaine, est de considérer qu'un PSI inférieur à 0,1 ne signale rien, qu'entre 0,1 et 0,25 il faut regarder, et qu'au-delà la population a changé.

:::exemple[Exemple 35.2 : un PSI calculé à la main]
Semaine du 14 juillet, quinzième semaine de production. La précision réelle y vaut 74,8 %, dix-sept points de moins qu'au départ. Voici la répartition des catégories prédites :

| Catégorie | Référence $a_i$ | Semaine $o_i$ | $(o_i - a_i)\ln(o_i/a_i)$ |
|---|---|---|---|
| administratif | 0,252 | 0,239 | 0,0007 |
| courses | 0,157 | 0,139 | 0,0022 |
| loisirs | 0,160 | 0,157 | 0,0000 |
| maison | 0,172 | 0,231 | 0,0175 |
| travail | 0,259 | 0,234 | 0,0026 |
| **Total** | | | **0,023** |

Un PSI de 0,023, très loin du seuil de 0,1 : d'après cet indicateur, tout va bien. Seule la catégorie « maison » bouge un peu, parce que le modèle y range à tort des titres qu'il ne connaît pas (la vraie part de « maison » cette semaine-là est de 15,2 %). Un indicateur sur les sorties peut rester calme pendant qu'un modèle perd dix-sept points.
:::

[^siddiqi]: Naeem Siddiqi, *Credit Risk Scorecards: Developing and Implementing Intelligent Credit Scoring*, Wiley, 2006, chapitre sur la surveillance des grilles de score. Les seuils 0,1 et 0,25 sont des conventions d'usage, pas des résultats statistiques.

### 4.1 Les tests statistiques, et leurs fausses alertes

Plutôt qu'un indice et un seuil conventionnel, on peut utiliser un test : chaque semaine, on se demande si la répartition observée est compatible avec celle de référence. C'est ce que font la plupart des outils. Le test du khi deux, par exemple, renvoie une valeur $p$, et l'on alerte quand elle passe sous 5 %.

:::exemple[Exemple 35.3 : cinquante tests, huit alertes]
Sur nos cinquante semaines, le test du khi deux sur la répartition des catégories prédites a passé huit fois sous 5 %. Or, même si rien ne changeait, un test au seuil de 5 % se trompe une fois sur vingt : sur cinquante semaines, on attend $50 \times 0{,}05 = 2{,}5$ fausses alertes. Huit alertes, c'est un peu plus que le hasard, mais elles ne tombent pas au moment où la précision chute, et rien ne permet, semaine par semaine, de distinguer les vraies des fausses.

Le problème s'aggrave avec le nombre de signaux. Une équipe qui surveille vingt caractéristiques avec un test chacune, chaque jour, reçoit en moyenne une fausse alerte par jour. Au bout d'une semaine, plus personne ne les lit. Les remèdes sont connus : relever le seuil (corriger pour les tests multiples, à la manière de Bonferroni), exiger que l'alerte persiste plusieurs périodes, et surtout choisir peu de signaux, ceux dont on a vérifié qu'ils suivent la qualité. Rabanser et ses collègues, qui ont comparé systématiquement les méthodes de détection, concluent d'ailleurs qu'un test simple sur une bonne représentation des données vaut souvent mieux qu'une batterie de tests sophistiqués [^rabanser].
:::

[^rabanser]: Stephan Rabanser, Stephan Günnemann, Zachary C. Lipton, « Failing Loudly: An Empirical Study of Methods for Detecting Dataset Shift », *NeurIPS*, 2019.

## 5. La dérive que rien ne trahit

On a injecté dans la simulation, à la semaine 21, une vraie dérive de concept : à partir de ce moment, les utilisateurs rangent « répondre aux mails » et « trier les papiers » dans la catégorie travail, alors qu'ils les rangeaient auparavant ailleurs. C'est le genre de changement qui arrive quand une entreprise généralise le télétravail, ou quand une nouvelle fonctionnalité de l'application modifie les habitudes.

:::exemple[Exemple 35.4 : invisible dans les entrées]
Avant la semaine 21, le modèle donnait la bonne catégorie pour ces deux titres dans 99 % des cas. Après, dans 47 % des cas. Pendant les huit semaines qui précèdent le changement, la part de mots inconnus valait 4,9 % ; pendant les huit qui suivent, 5,0 %. La confiance n'a pas bougé non plus : le modèle est aussi sûr de lui qu'avant, il a simplement tort.

Aucun signal calculé sur les entrées ou les sorties ne pouvait voir ce changement, puisque les titres sont exactement les mêmes. Seules les étiquettes le révèlent, et seulement sur les tâches concernées, qui sont peu nombreuses : dans la précision globale de la semaine, l'effet se noie dans le bruit de deux points de l'exemple 35.1. Il faut suivre la précision **par titre fréquent** ou **par catégorie** pour le voir apparaître.
:::

Il en découle une règle d'architecture : une surveillance sans étiquettes détecte certaines dérives, jamais toutes. Tôt ou tard, il faut une boucle qui ramène la vérité, même partielle, même en retard : les corrections des utilisateurs, et un audit régulier d'un petit échantillon tiré au hasard. L'échantillon aléatoire compte, parce que les corrections spontanées ne sont pas représentatives.

## 6. Evidently, et le choix de la référence

Evidently est une bibliothèque libre qui automatise ces comparaisons : on lui donne une fenêtre de **référence** et une fenêtre **courante**, elle choisit un test ou une distance adaptés à chaque colonne, et produit un rapport [^evidently]. Pour la tester, on a construit, pour chaque tâche, quatre caractéristiques calculables sans étiquette : la longueur du titre, sa part de mots inconnus, la confiance du modèle et la catégorie prédite.

```python
from evidently import Report, Dataset, DataDefinition
from evidently.presets import DataDriftPreset

definition = DataDefinition(numerical_columns=["longueur", "part_inconnus", "confiance"],
                            categorical_columns=["categorie_predite"])
rapport = Report([DataDriftPreset()]).run(
    reference_data=Dataset.from_pandas(reference, data_definition=definition),
    current_data=Dataset.from_pandas(courant, data_definition=definition))
rapport.save_html("rapport_derive.html")
```

:::exemple[Exemple 35.5 : ce qu'Evidently a dit, et une fausse alerte instructive]
Sur une semaine tardive (début mars 2026), Evidently 0.7.23 conclut que trois colonnes sur quatre ont dérivé :

| Colonne | Méthode choisie | Valeur | Seuil |
|---|---|---|---|
| longueur | distance de Wasserstein normalisée | 0,171 | 0,1 |
| part_inconnus | distance de Jensen-Shannon | 0,298 | 0,1 |
| confiance | distance de Wasserstein normalisée | 0,514 | 0,1 |
| categorie_predite | distance de Jensen-Shannon | 0,072 | 0,1 |

C'est la même conclusion que les sections précédentes : les entrées et la confiance ont bougé, la répartition des prédictions non.

Sur la toute **première** semaine de production, en revanche, on s'attendait à ne rien trouver. Evidently a pourtant signalé une dérive de la confiance (0,152). La cause n'est pas dans la production, elle est dans la référence : on lui avait donné les **données d'entraînement**, sur lesquelles le modèle est plus sûr de lui que sur n'importe quelle donnée nouvelle (confiance moyenne de 91,9 % contre 90,3 % la première semaine). La référence d'une surveillance doit être un jeu que le modèle n'a pas vu pendant l'apprentissage, typiquement le jeu de validation ou les premières semaines de production. Sinon, l'outil compare la production à un monde où le modèle récitait sa leçon.
:::

[^evidently]: Documentation d'Evidently, « Data Drift » et « Presets ». [docs.evidentlyai.com](https://docs.evidentlyai.com/). Les exemples de ce chapitre ont été exécutés avec la version 0.7.23.

Evidently ne remplace pas le raisonnement des sections précédentes. Il calcule très bien des écarts de distribution ; il ne sait pas lesquels comptent pour votre modèle, il ne voit pas la dérive de concept, et ses seuils par défaut sont des conventions. Son intérêt est ailleurs : produire, pour chaque période, un rapport lisible et versionnable, et des chiffres qu'on peut exporter vers Prometheus pour les suivre comme les signaux du chapitre 26.

## 7. De l'alerte à l'action

Une alerte qui ne déclenche rien est une alerte de trop. Pour Listify, la simulation suggère un dispositif simple. On suit chaque jour deux signaux sans étiquette, la part de mots inconnus et la confiance moyenne, exportés comme métriques Prometheus par le service du chapitre 33, avec des seuils calés sur les premières semaines de production et une condition de persistance (trois jours consécutifs), pour ne pas réagir au bruit. On suit chaque semaine la précision sur les étiquettes disponibles, globale et par catégorie, en sachant qu'elle est bruitée et en retard. Et l'on tire chaque mois un échantillon aléatoire à faire vérifier, la seule source qui voit la dérive de concept.

:::exemple[Exemple 35.6 : combien de temps pour réagir ?]
Dans la figure 35.1, la chute durable de la précision commence vers la semaine 14. Le signal des mots inconnus passe au-dessus de 2 % à la semaine 11, donc un peu avant ; avec une condition de persistance de trois semaines, l'alerte tombe vers la semaine 13, juste avant la chute. La précision elle-même, étiquettes comprises, ne permet d'affirmer la baisse qu'après avoir agrégé plusieurs semaines, soit vers la semaine 16 ou 17.

Trois semaines d'avance, dans ce cas précis. Ce n'est pas une loi : sur d'autres données, les mots inconnus pourraient augmenter sans que la précision baisse, si les nouveaux mots n'apportent rien à la décision. C'est pourquoi on valide ses signaux sur l'historique, comme ici, avant de leur confier une alerte.
:::

Quand l'alerte est fondée, les réponses se rangent sur l'échelle du chapitre 29. La plus simple consiste à réentraîner sur des données récentes, déclenché par la dérive plutôt que par le calendrier : c'est ce que fera le TP 29, en branchant ce chapitre sur le DAG du TP 26. D'autres fois, il faut revoir les caractéristiques, parce qu'un modèle qui ignore les noms propres ne s'améliorera pas en les voyant davantage ; ou encore rétablir une étiquette fiable, quand la boucle de rétroaction du chapitre 27 a pollué les données d'entraînement. Et parfois, il faut désactiver la suggestion en attendant, plutôt que d'afficher des catégories fausses avec assurance.

## Ce qu'il faut retenir

<div className="retenir">

1. Un modèle qui se dégrade ne lève aucune erreur : la surveillance du service (chapitre 26) ne le voit pas. Dans notre simulation, la précision est passée de 92 % à environ 80 % sans une seule erreur HTTP.
2. Le monde peut changer de trois façons : les entrées ($P(x)$), les proportions de classes ($P(y)$), ou la règle elle-même ($P(y \mid x)$). Seule la première se voit sans étiquettes.
3. Les étiquettes arrivent tard, partiellement, et parfois biaisées. Une précision hebdomadaire sur 382 tâches fluctue de deux points : on ne la lit pas semaine par semaine.
4. Tous les signaux ne se valent pas. Ici, la part de mots inconnus suivait la précision (corrélation -0,89), la confiance aussi (0,85) ; la répartition des catégories prédites presque pas (0,17, et un PSI de 0,023 une semaine où la précision avait perdu dix-sept points). On valide ses signaux sur l'historique avant d'y brancher des alertes.
5. Des tests répétés produisent des fausses alertes : 2,5 attendues sur cinquante semaines au seuil de 5 %. Peu de signaux, une condition de persistance, un seuil corrigé.
6. La dérive de concept est invisible dans les entrées : il faut une source de vérité, dont un échantillon tiré au hasard.
7. La référence d'une surveillance ne doit pas être le jeu d'entraînement, sur lequel le modèle est trop sûr de lui.

</div>

## Regard recherche

:::recherche
La détection de la dérive est un domaine ancien de l'apprentissage statistique, renouvelé par le déploiement massif des modèles :

- **João Gama et al., « A survey on concept drift adaptation », *ACM Computing Surveys*, 2014.** La synthèse de référence : typologie des dérives, détecteurs, stratégies d'adaptation.
- **Stephan Rabanser, Stephan Günnemann, Zachary C. Lipton, « Failing Loudly », *NeurIPS*, 2019.** Une comparaison systématique des méthodes de détection, qui montre l'intérêt de réduire d'abord la dimension, et la difficulté propre aux données de grande dimension comme le texte.
- **Zachary C. Lipton, Yu-Xiang Wang, Alexander J. Smola, « Detecting and Correcting for Label Shift with Black Box Predictors », *ICML*, 2018.** Estimer la dérive des classes à partir des seules prédictions d'un modèle existant, puis la corriger.
- **Eric Breck et al., « The ML Test Score: A Rubric for ML Production Readiness and Technical Debt Reduction », *IEEE Big Data*, 2017.** La grille de Google, dont une partie entière porte sur la surveillance en production.
- **Shreya Shankar et al., « Operationalizing Machine Learning: An Interview Study », 2022.** Ce que font vraiment les équipes : peu d'entre elles surveillent la dérive de façon systématique, et la fatigue des alertes revient dans presque tous les entretiens.

Piste d'innovation : estimer la précision d'un modèle **sans étiquettes**, à partir de sa confiance et des écarts de distribution, est un problème ouvert. Les méthodes existantes marchent dans certains cas et échouent dans d'autres, précisément quand la dérive touche la règle plutôt que les entrées.
:::

## Bibliographie du chapitre

<div className="biblio">

### Sources primaires

- Joaquin Quiñonero-Candela et al. (dir.), *Dataset Shift in Machine Learning*, MIT Press, 2009.
- João Gama et al., « A survey on concept drift adaptation », *ACM Computing Surveys*, 2014.
- Documentation d'Evidently. [docs.evidentlyai.com](https://docs.evidentlyai.com/)

### Lectures recommandées

- Chip Huyen, *Designing Machine Learning Systems*, O'Reilly, 2022, chapitre 8 (« Data Distribution Shifts and Monitoring ») : le chapitre le plus complet sur la question dans un ouvrage d'ingénierie.
- Naeem Siddiqi, *Credit Risk Scorecards*, Wiley, 2006 : l'origine de l'indice de stabilité, dans un domaine qui surveille ses modèles depuis des décennies.

### Pour aller plus loin

- Les articles de la rubrique « Regard recherche ».
- Jose G. Moreno-Torres et al., « A unifying view on dataset shift in classification », *Pattern Recognition*, 2012 : un vocabulaire commun pour des dérives décrites sous des noms différents.

</div>
