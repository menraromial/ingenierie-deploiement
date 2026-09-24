"""Outils communs du TP 30 : la session Spark, le schéma du journal, un chronomètre."""
import json
import os
import sys
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path

from pyspark.sql import SparkSession, types as T

ICI = Path(__file__).resolve().parent
DATA = ICI / "data"
EVENEMENTS = ICI / "evenements"          # journal d'événements de Spark, pour le serveur d'historique
TEMPORAIRE = ICI / "spark-tmp"           # fichiers de shuffle : sur disque, pas dans /tmp (souvent en mémoire)
MEMOIRE = os.environ.get("TP30_MEMOIRE", "3g")          # mémoire de la JVM de Spark
COEURS = os.environ.get("TP30_COEURS", "*")             # nombre de cœurs utilisés
# les processus Python lancés par Spark (mapInPandas, UDF) doivent utiliser le même Python que le script
os.environ.setdefault("PYSPARK_PYTHON", sys.executable)

SCHEMA = T.StructType([
    T.StructField("horodatage", T.TimestampType()), T.StructField("utilisateur", T.IntegerType()),
    T.StructField("tache", T.IntegerType()), T.StructField("action", T.StringType()),
    T.StructField("categorie", T.StringType()), T.StructField("client", T.StringType()),
    T.StructField("duree_ms", T.IntegerType()), T.StructField("titre", T.StringType())])


def session(nom: str, **reglages) -> SparkSession:
    EVENEMENTS.mkdir(exist_ok=True)
    TEMPORAIRE.mkdir(exist_ok=True)
    b = (SparkSession.builder.master(f"local[{COEURS}]").appName(nom)
         .config("spark.driver.memory", MEMOIRE)
         .config("spark.local.dir", str(TEMPORAIRE))
         .config("spark.ui.showConsoleProgress", "false")       # l'avancement se lit dans l'interface
         .config("spark.eventLog.enabled", "true")
         .config("spark.eventLog.dir", EVENEMENTS.as_uri()))
    for cle, valeur in reglages.items():
        b = b.config(cle, valeur)
    spark = b.getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")
    print(f"session {nom} : interface sur {spark.sparkContext.uiWebUrl}", flush=True)
    return spark


@contextmanager
def chrono(etiquette: str):
    debut = time.perf_counter()
    yield
    print(f"[{etiquette}] {time.perf_counter() - debut:.1f} s", flush=True)


def lignes_lues(spark: SparkSession) -> int:
    """Lignes produites par la lecture des fichiers lors de la dernière requête (onglet SQL de l'interface)."""
    base = f"{spark.sparkContext.uiWebUrl}/api/v1/applications/{spark.sparkContext.applicationId}"
    time.sleep(1)
    derniere = json.load(urllib.request.urlopen(f"{base}/sql?details=true&offset=0&length=1000"))[-1]
    for noeud in derniere["nodes"]:
        if noeud["nodeName"].startswith("Scan"):
            for m in noeud["metrics"]:
                if m["name"] == "number of output rows":
                    return int(m["value"].replace(",", "").replace("\u202f", "").replace(" ", ""))
    return -1


def shuffle_total(spark: SparkSession) -> int:
    """Octets écrits par tous les shuffles de la session jusqu'ici (onglet Stages de l'interface)."""
    base = f"{spark.sparkContext.uiWebUrl}/api/v1/applications/{spark.sparkContext.applicationId}"
    time.sleep(1)
    etapes = json.load(urllib.request.urlopen(f"{base}/stages?status=complete"))
    return sum(e["shuffleWriteBytes"] for e in etapes)


def etapes_lourdes(spark: SparkSession, depuis: int = 0):
    """Pour chaque étape qui lit un shuffle : nombre de tâches, durée médiane et maximale des tâches."""
    base = f"{spark.sparkContext.uiWebUrl}/api/v1/applications/{spark.sparkContext.applicationId}"
    time.sleep(1)
    for e in sorted(json.load(urllib.request.urlopen(f"{base}/stages?status=complete")), key=lambda e: e["stageId"]):
        if e["stageId"] >= depuis and e["shuffleReadBytes"] > 2**20:
            q = json.load(urllib.request.urlopen(
                f"{base}/stages/{e['stageId']}/{e['attemptId']}/taskSummary?quantiles=0.5,1.0"))
            med, maxi = (round(x / 1000, 1) for x in q["executorRunTime"])
            print(f"  étape {e['stageId']} : {e['numTasks']} tâches, lu du shuffle {e['shuffleReadBytes'] / 2**20:.0f} Mio, "
                  f"tâche médiane {med} s, tâche la plus longue {maxi} s")


def derniere_etape(spark: SparkSession) -> int:
    base = f"{spark.sparkContext.uiWebUrl}/api/v1/applications/{spark.sparkContext.applicationId}"
    etapes = json.load(urllib.request.urlopen(f"{base}/stages"))
    return max((e["stageId"] for e in etapes), default=-1) + 1


def pause(spark: SparkSession):
    """Garde l'interface ouverte si le script est lancé avec --pause."""
    if "--pause" in sys.argv:
        input(f"Interface : {spark.sparkContext.uiWebUrl} ; Entrée pour terminer. ")
    spark.stop()
