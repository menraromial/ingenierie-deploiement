"""Génère des exports de tâches Listify réalistes (titre, catégorie).

Réservé à l'enseignant : le kit distribué aux étudiants ne contient que les CSV.
Les titres suivent une distribution très concentrée (quelques titres reviennent
très souvent), comme dans une vraie application de listes de tâches.
"""
import datetime
import random

CATEGORIES = {
    "travail": {
        "verbes": ["préparer", "envoyer", "relire", "finir", "corriger", "présenter", "planifier", "valider", "rédiger", "mettre à jour"],
        "objets": ["le rapport", "la présentation", "le compte rendu", "le budget", "le planning", "la réunion d'équipe", "le mail au client", "la revue de code", "le devis", "les slides", "le point hebdo", "le dossier projet", "la démo", "le contrat fournisseur"],
        "suffixes": ["", "", "", " pour lundi", " avant la réunion", " du trimestre", " pour le client", " avec l'équipe"],
    },
    "courses": {
        "verbes": ["acheter", "prendre", "racheter", "commander", "penser à acheter", "aller chercher"],
        "objets": ["du pain", "du lait", "des oeufs", "du fromage", "des pommes", "du café", "des pâtes", "du riz", "des yaourts", "du beurre", "de l'eau", "des tomates", "du papier toilette", "de la lessive", "du shampoing", "des croquettes"],
        "suffixes": ["", "", "", " au marché", " au supermarché", " pour ce soir", " en promo"],
    },
    "maison": {
        "verbes": ["ranger", "nettoyer", "réparer", "laver", "aspirer", "repeindre", "vider", "changer", "arroser", "trier"],
        "objets": ["la cuisine", "le salon", "la salle de bain", "le frigo", "le garage", "les vitres", "le lave-vaisselle", "la chambre", "les plantes", "la poubelle", "l'ampoule du couloir", "le robinet qui fuit", "les placards", "le linge"],
        "suffixes": ["", "", "", " ce week-end", " à fond", " avant les invités"],
    },
    "administratif": {
        "verbes": ["payer", "déclarer", "renouveler", "envoyer", "remplir", "résilier", "scanner", "appeler", "imprimer", "signer"],
        "objets": ["les impôts", "la facture d'électricité", "le loyer", "l'assurance habitation", "le passeport", "la carte d'identité", "le formulaire CAF", "la mutuelle", "l'abonnement internet", "la banque", "la mairie", "la déclaration de revenus", "l'attestation employeur", "la carte grise"],
        "suffixes": ["", "", "", " avant la date limite", " en ligne", " cette semaine"],
    },
    "loisirs": {
        "verbes": ["réserver", "regarder", "lire", "organiser", "aller à", "préparer", "inviter les amis pour", "acheter les billets pour", "écouter", "planifier"],
        "objets": ["le cinéma", "le concert", "la randonnée", "le match", "le dernier roman", "la série", "le week-end à la mer", "la soirée jeux", "le resto", "la piscine", "le festival", "l'expo au musée", "le nouvel album", "les vacances"],
        "suffixes": ["", "", "", " samedi", " avec les amis", " en famille"],
    },
}

# Titres ambigus : plausibles dans deux catégories, l'utilisateur tranche au hasard.
AMBIGUS = [
    ("appeler le plombier", ["maison", "administratif"]),
    ("acheter un cadeau pour Léa", ["courses", "loisirs"]),
    ("imprimer les billets de train", ["administratif", "loisirs"]),
    ("répondre aux mails", ["travail", "administratif"]),
    ("commander une imprimante", ["travail", "courses"]),
    ("préparer le repas de dimanche", ["maison", "courses"]),
    ("prendre rendez-vous chez le dentiste", ["administratif", "maison"]),
    ("acheter de la peinture", ["maison", "courses"]),
    ("réserver la salle pour le séminaire", ["travail", "loisirs"]),
    ("payer le cours de yoga", ["administratif", "loisirs"]),
    ("trier les papiers", ["administratif", "maison"]),
    ("organiser le pot de départ", ["travail", "loisirs"]),
]


# Titres personnels : ils reviennent souvent chez un même utilisateur, mais leurs
# mots (noms propres, codes) ne disent rien de la catégorie choisie.
DEBUTS = ["voir", "rappeler", "point avec", "relancer", "passer chez", "écrire à", "truc pour", "check", "rdv", "suivi"]
NOMS = ["Mme Durand", "Kévin", "M. Ngo", "Sophie", "le dossier 4521", "Hélios", "Mamadou", "Tante Rose", "le ticket 88",
        "Bertrand", "l'agence", "Inès", "le syndic", "Paul", "Nadia", "le projet Orion", "Yann", "Fatou", "le 3B", "Marc",
        "Chloé", "M. Kamga", "le dossier 7730", "Lucas", "Aïcha", "le projet Vega", "Mme Lemoine", "Thomas", "le ticket 412",
        "Élodie", "Oumar", "le cabinet Roy", "Julie", "Hugo", "Mme Bensaïd", "le projet Atlas", "Samuel", "Awa", "le 5C", "Léon"]


def personnels(rng):
    return [(f"{d} {n}", rng.choice(list(CATEGORIES))) for d in DEBUTS for n in NOMS]


def catalogue(rng):
    """Liste de (titre, catégorie) distincts, dans un ordre qui fixe leur popularité."""
    titres = []
    for cat, v in CATEGORIES.items():
        for verbe in v["verbes"]:
            for objet in v["objets"]:
                for suffixe in v["suffixes"]:
                    titres.append((f"{verbe} {objet}{suffixe}", cat))
    rng.shuffle(titres)
    return titres


def generer(n, graine, debut=datetime.date(2025, 1, 6), jours=365,
            bruit=0.03, part_ambigus=0.06, part_personnels=0.22):
    """n lignes (date de création, titre, catégorie), dans l'ordre chronologique.

    Popularité en loi de Zipf sur le catalogue. Les titres personnels « tournent »
    lentement : ceux de la fin de période sont en partie absents du début.
    """
    rng = random.Random(graine)
    cat_liste = list(CATEGORIES)
    titres = catalogue(rng)
    perso = personnels(rng)
    fenetre = 80                                      # titres personnels « en cours » à un instant donné
    ambigus = [(t, rng.choice(c)) for t, c in AMBIGUS]   # chaque titre ambigu a sa catégorie majoritaire
    poids = [1 / (rang + 1) ** 0.9 for rang in range(len(titres))]
    lignes = []
    for i, (titre, cat) in enumerate(rng.choices(titres, weights=poids, k=n)):
        u = rng.random()
        if u < part_personnels:
            debut_fenetre = int((len(perso) - fenetre) * i / n)
            titre, cat = rng.choice(perso[debut_fenetre:debut_fenetre + fenetre])
        elif u < part_personnels + part_ambigus:
            titre, cat = rng.choice(ambigus)
        if rng.random() < bruit:                  # l'utilisateur s'est trompé de catégorie
            cat = rng.choice([c for c in cat_liste if c != cat])
        if rng.random() < 0.3:                      # majuscule initiale, comme au clavier
            titre = titre[0].upper() + titre[1:]
        date = debut + datetime.timedelta(days=int(jours * i / n))
        lignes.append((date.isoformat(), titre, cat))
    return lignes
