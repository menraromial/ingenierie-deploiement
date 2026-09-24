"""Ce que contient un jeu de fichiers Parquet : fichiers, groupes de lignes, taille par colonne, statistiques.

Usage : python inspecter_parquet.py <répertoire Parquet> [colonne dont on veut les min/max]
"""
import sys
from pathlib import Path

import pyarrow.parquet as pq

racine = Path(sys.argv[1])
colonne_stats = sys.argv[2] if len(sys.argv) > 2 else "horodatage"
fichiers = sorted(racine.rglob("*.parquet"))
groupes, lignes, par_colonne, stats = 0, 0, {}, []
for f in fichiers:
    meta = pq.ParquetFile(f).metadata
    for i in range(meta.num_row_groups):
        g = meta.row_group(i)
        groupes += 1
        lignes += g.num_rows
        for j in range(g.num_columns):
            c = g.column(j)
            par_colonne[c.path_in_schema] = par_colonne.get(c.path_in_schema, 0) + c.total_compressed_size
            if c.path_in_schema == colonne_stats:
                stats.append((c.physical_type, c.statistics.has_min_max,
                              c.statistics.min if c.statistics.has_min_max else None,
                              c.statistics.max if c.statistics.has_min_max else None))
total = sum(par_colonne.values())
print(f"{len(fichiers)} fichiers, {groupes} groupes de lignes, {lignes:,} lignes, "
      f"{total / 2**20:,.0f} Mio de données".replace(",", " "))
for nom, taille in sorted(par_colonne.items(), key=lambda x: -x[1]):
    print(f"  {nom:12s} {taille / 2**20:8.1f} Mio  {100 * taille / total:5.1f} %")
if stats:
    type_physique, a_stats, mini, maxi = stats[0]
    print(f"colonne {colonne_stats} : type {type_physique}, min/max présents : {a_stats}")
    if a_stats:
        print(f"  premier groupe : {mini} -> {maxi}")
