"""Fabrique le kit du TP 22 : le projet « recherche » irreproductible.

Réservé à l'enseignant. À exécuter avec scikit-learn 1.7.2 (la version « de Claire ») :

    python fabriquer_kit.py            # produit ../../static/kits/tp22-kit.tar.gz

Le script rejoue l'exécution d'origine du notebook, avec l'état caché qui a
ensuite disparu (fonction nettoyer, seuil, C_best, graine), et en conserve les
sorties réelles. Les réponses aux énigmes sont dans SOLUTIONS ci-dessous.
"""
import io
import json
import pickle
import random
import shutil
import tarfile
import warnings
from contextlib import redirect_stderr
from pathlib import Path

import pandas as pd
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split

import donnees

assert sklearn.__version__ == "1.7.2", "le kit doit être fabriqué avec scikit-learn 1.7.2"

# État caché de l'exécution d'origine : rien de tout cela ne figure dans le notebook distribué.
SOLUTIONS = {
    "fichier": "export_taches_final.csv",
    "seuil": 3,          # min_df
    "C_best": 5,
    "graine": 12,        # le split n'avait pas de random_state : on fige ici celui qui a « eu lieu »
}


def nettoyer(titre):
    return titre.strip().lower()


ICI = Path(__file__).parent
SORTIE = ICI / "build" / "tp22-kit"
ARCHIVE = ICI.parent.parent / "static" / "kits" / "tp22-kit.tar.gz"


def fabriquer_donnees():
    rng = random.Random(99)
    brut = pd.DataFrame(donnees.generer(20000, 2024), columns=["cree_le", "titre", "categorie"])

    # « final » : l'export brut retouché à la main (catégories vides, majuscules).
    final = brut.copy()
    vides = rng.sample(range(len(final)), 147)
    final.loc[vides, "categorie"] = None
    maj = [i for i in rng.sample(range(len(final)), 1600) if i not in set(vides)]
    final.loc[maj, "categorie"] = final.loc[maj, "categorie"].str.capitalize()

    # « v2 » : ré-export ultérieur, plus long ; une autre équipe a renommé une catégorie.
    v2 = pd.DataFrame(donnees.generer(24000, 2025, jours=440), columns=["cree_le", "titre", "categorie"])
    v2["categorie"] = v2["categorie"].replace({"administratif": "admin"})

    (SORTIE / "data").mkdir(parents=True)
    brut.to_csv(SORTIE / "data" / "export_taches.csv", index=False)
    final.to_csv(SORTIE / "data" / "export_taches_final.csv", index=False)
    v2.to_csv(SORTIE / "data" / "export_taches_final_v2.csv", index=False)
    return final


def texte(s):
    return [l + "\n" for l in s.rstrip("\n").split("\n")[:-1]] + [s.rstrip("\n").split("\n")[-1]]


def code(n, source, sortie=None, flux=None, html=None):
    outputs = []
    if flux:
        outputs.append({"name": "stderr", "output_type": "stream", "text": texte(flux)})
    if sortie is not None:
        data = {"text/plain": texte(sortie)}
        if html:
            data["text/html"] = texte(html)
        outputs.append({"data": data, "execution_count": n, "metadata": {}, "output_type": "execute_result"})
    return {"cell_type": "code", "execution_count": n, "metadata": {}, "outputs": outputs, "source": texte(source)}


def md(source):
    return {"cell_type": "markdown", "metadata": {}, "source": texte(source)}


def executer_origine(final):
    """Rejoue l'exécution d'origine et renvoie les sorties à placer dans le notebook."""
    s = SOLUTIONS
    df = final.copy()
    forme_brute = df.shape
    df = df.dropna(subset=["categorie"])
    df["categorie"] = df.categorie.str.lower()
    df["titre"] = df.titre.apply(nettoyer)
    forme_nettoyee = df.shape
    tete = df.head()
    n_df2 = len(df[df.titre.str.len() > 3])
    vec = TfidfVectorizer(min_df=s["seuil"], ngram_range=(1, 2))
    X = vec.fit_transform(df.titre)
    y = df.categorie
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=s["graine"])
    err = io.StringIO()
    with redirect_stderr(err), warnings.catch_warnings():
        warnings.simplefilter("always")
        warnings.showwarning = lambda msg, cat, fn, ln, file=None, line=None: err.write(
            warnings.formatwarning(msg, cat, "/home/claire/.venv/lib/python3.12/site-packages/sklearn/linear_model/_logistic.py", 1272))
        clf = LogisticRegression(C=s["C_best"], multi_class="multinomial", max_iter=500)
        clf.fit(X_train, y_train)
    acc = accuracy_score(y_test, clf.predict(X_test))
    return dict(forme_brute=forme_brute, forme_nettoyee=forme_nettoyee, tete=tete,
                forme_X=X.shape, n_df2=n_df2, avertissement=err.getvalue(), clf=clf, acc=acc)


def fabriquer_notebook(r):
    tete = r["tete"]
    cellules = [
        md("# Catégorisation automatique des tâches\n\n"
           "Essais de Claire. Données : export de la base Listify (demander à Julien s'il faut le refaire)."),
        code(1, "import pandas as pd\nimport numpy as np\nimport pickle\nfrom tqdm import tqdm\n"
                "from sklearn.feature_extraction.text import TfidfVectorizer\n"
                "from sklearn.linear_model import LogisticRegression\n"
                "from sklearn.model_selection import train_test_split\n"
                "from sklearn.metrics import accuracy_score"),
        code(14, 'df = pd.read_csv("/home/claire/Téléchargements/export_final.csv")\ndf.shape',
             sortie=str(r["forme_brute"])),
        code(3, 'df = df.dropna(subset=["categorie"])\n'
                'df["categorie"] = df.categorie.str.lower()\n'
                'df["titre"] = df.titre.apply(nettoyer)\n'
                "df.shape", sortie=str(r["forme_nettoyee"])),
        code(4, "df.head()", sortie=tete.to_string(), html=tete.to_html()),
        code(9, "df2 = df[df.titre.str.len() > 3]\nlen(df2)", sortie=str(r["n_df2"])),
        md("## Modèle\n\nTF-IDF + régression logistique. Le seuil de fréquence enlève les mots trop rares."),
        code(16, "vec = TfidfVectorizer(min_df=seuil, ngram_range=(1, 2))\n"
                 "X = vec.fit_transform(df.titre)\ny = df.categorie\nX.shape", sortie=str(r["forme_X"])),
        code(17, "X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)"),
        code(18, 'clf = LogisticRegression(C=C_best, multi_class="multinomial", max_iter=500)\n'
                 "clf.fit(X_train, y_train)",
             flux=r["avertissement"],
             sortie=f"LogisticRegression(C={SOLUTIONS['C_best']}, max_iter=500, multi_class='multinomial')"),
        code(19, "accuracy_score(y_test, clf.predict(X_test))", sortie=repr(round(r["acc"], 16))),
        code(20, 'pickle.dump(clf, open("modele_final.pkl", "wb"))'),
        md(f"**{r['acc']:.1%}** de précision !!! On peut mettre ça en prod.\n\n"
           "(C=10 marchait mieux que C=1 dans la grid search, j'ai aussi essayé 5.)"),
    ]
    nb = {
        "cells": cellules,
        "metadata": {
            "kernelspec": {"display_name": "Python 3 (ipykernel)", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.12.3"},
        },
        "nbformat": 4, "nbformat_minor": 5,
    }
    for i, c in enumerate(cellules):
        c["id"] = f"c{i:02d}"
    (SORTIE / "recherche_categories.ipynb").write_text(json.dumps(nb, ensure_ascii=False, indent=1) + "\n")


def main():
    if SORTIE.exists():
        shutil.rmtree(SORTIE)
    final = fabriquer_donnees()
    r = executer_origine(final)
    fabriquer_notebook(r)
    with open(SORTIE / "modele_final.pkl", "wb") as f:
        pickle.dump(r["clf"], f)
    (SORTIE / "LISEZMOI.txt").write_text(
        "Salut !\n\n"
        "Voici mon notebook pour la suggestion de catégorie. Il marche très bien chez moi : 94 % !\n"
        "Il faut juste pandas et scikit-learn. Le modèle entraîné est dans modele_final.pkl,\n"
        "il n'y a plus qu'à le brancher dans l'API.\n\n"
        "Les données sont dans data/ (j'ai mis toutes les versions au cas où).\n\n"
        "Bon courage, je pars sur le projet de recommandation lundi.\n"
        "Claire\n")
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(ARCHIVE, "w:gz") as tar:
        tar.add(SORTIE, arcname="tp22-kit")
    print(f"précision d'origine : {r['acc']:.4f} ; X : {r['forme_X']} ; archive : {ARCHIVE}")


if __name__ == "__main__":
    main()
