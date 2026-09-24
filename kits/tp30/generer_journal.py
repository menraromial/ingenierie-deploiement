"""Fabrique un journal d'événements Listify de grande taille (CSV), pour le chapitre 36 et le TP 30.

Usage : python generer_journal.py <taches_completes.csv> <sortie.csv> <millions de lignes>

Chaque ligne est une action d'un utilisateur sur une tâche. Les titres et catégories viennent des
vraies tâches de Listify ; les utilisateurs ont une activité très inégale, et un compte robot
(la synchronisation d'un calendrier, utilisateur 42) produit à lui seul 10 % des événements.
Le fichier est trié par date, comme un vrai journal.
"""
import sys
import time

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.csv as pacsv

source, sortie, millions = sys.argv[1], sys.argv[2], int(sys.argv[3])
BLOC = 5_000_000
N_UTILISATEURS = 500_000
ROBOT = 42
debut = np.datetime64("2025-01-01T00:00:00", "s")
fin = np.datetime64("2026-07-01T00:00:00", "s")

rng = np.random.default_rng(36)
taches = pd.read_csv(source)
titres = taches["titre"].to_numpy(dtype=object)
categories = taches["categorie"].to_numpy(dtype=object)

activite = rng.lognormal(0, 1.2, N_UTILISATEURS)          # activité très inégale
cumul = np.cumsum(activite) / activite.sum()
ACTIONS = np.array(["consultation", "modification", "creation", "completion", "suppression"], dtype=object)
P_ACTIONS = [0.55, 0.20, 0.10, 0.10, 0.05]
CLIENTS = np.array(["web", "android", "ios"], dtype=object)
P_CLIENTS = [0.5, 0.3, 0.2]

n_total = millions * 1_000_000
n_blocs = n_total // BLOC
duree_bloc = (fin - debut) / n_blocs
t0 = time.perf_counter()
with pacsv.CSVWriter(sortie, pa.schema([
    ("horodatage", pa.string()), ("utilisateur", pa.int32()), ("tache", pa.int32()),
    ("action", pa.string()), ("categorie", pa.string()), ("client", pa.string()),
    ("duree_ms", pa.int32()), ("titre", pa.string())])) as ecrivain:
    for b in range(n_blocs):
        # des instants triés dans la tranche de temps de ce bloc : le fichier reste chronologique
        secondes = np.sort(rng.integers(0, int(duree_bloc / np.timedelta64(1, "s")), BLOC))
        instants = debut + b * duree_bloc + secondes.astype("timedelta64[s]")
        utilisateurs = np.searchsorted(cumul, rng.random(BLOC)).astype(np.int32) + 1
        utilisateurs[rng.random(BLOC) < 0.10] = ROBOT
        i = rng.integers(0, len(titres), BLOC)
        tableau = pa.table({
            "horodatage": pa.array(np.datetime_as_string(instants, unit="s")),
            "utilisateur": utilisateurs,
            "tache": rng.integers(1, 30_000_000, BLOC, dtype=np.int32),
            "action": ACTIONS[rng.choice(5, BLOC, p=P_ACTIONS)],
            "categorie": categories[i],
            "client": CLIENTS[rng.choice(3, BLOC, p=P_CLIENTS)],
            "duree_ms": np.clip(rng.lognormal(3.4, 0.6, BLOC), 1, 5000).astype(np.int32),
            "titre": titres[i],
        })
        ecrivain.write_table(tableau)
        print(f"bloc {b + 1}/{n_blocs} écrit ({time.perf_counter() - t0:.0f} s)", flush=True)
print(f"{n_total} lignes écrites dans {sortie} en {time.perf_counter() - t0:.0f} s")
