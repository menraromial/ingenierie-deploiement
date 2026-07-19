# Ingénierie du Déploiement et de la Mise en Production

Site de cours (3 semestres, élèves ingénieurs M1-M2) : du serveur unique à l'Infrastructure as Code, des conteneurs à Kubernetes, du CI/CD au MLOps.

**Site publié :** https://menraromial.github.io/ingenierie-deploiement/

## Construire le site en local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
mkdocs serve          # aperçu sur http://127.0.0.1:8000
mkdocs build --strict # build de vérification (celui de la CI)
```

## Déploiement

Chaque push sur `main` déclenche le workflow [.github/workflows/deploy.yml](.github/workflows/deploy.yml) : build strict puis publication sur GitHub Pages. Aucune action manuelle.

## Structure

- `mkdocs.yml` : configuration et navigation du site
- `docs/` : le contenu (cours, TP, bibliographies), organisé par semestre puis par bloc
- `docs/fil-rouge.md` : l'application 3-tiers « Listify » utilisée dans tous les TP
