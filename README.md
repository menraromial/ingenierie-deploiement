# Ingénierie du Déploiement et de la Mise en Production

Site de cours (3 semestres, élèves ingénieurs M1-M2) : du serveur unique à l'Infrastructure as Code, des conteneurs à Kubernetes, du CI/CD au MLOps.

**Site publié :** https://menraromial.com/ingenierie-deploiement/

## Construire le site en local

Prérequis : Node.js 20 ou plus récent.

```bash
npm ci            # installe les dépendances figées du package-lock.json
npm start         # aperçu avec rechargement à chaud
npm run build     # build de vérification (celui de la CI : un lien cassé fait échouer)
npm run serve     # sert le build produit
```

## Les figures

Toutes les figures sont dessinées en LaTeX/TikZ, dans le style défini par `figures/lib/coursfig.sty` (palette identique à celle du site).

```bash
make -C figures            # compile figures/src/*.tex en SVG + PDF dans static/figures/
make -C figures <nom>      # une seule figure
make -C figures clean      # supprime le build intermédiaire
```

Prérequis : TeX Live avec LuaLaTeX, `latexmk`, `fontawesome5`, la police Source Sans Pro, et `pdftocairo` (poppler-utils). Les SVG et PDF produits sont versionnés : la CI n'a pas besoin de LaTeX.

## Déploiement

Chaque push sur `main` déclenche le workflow [.github/workflows/deploy.yml](.github/workflows/deploy.yml) : `npm ci`, build Docusaurus, puis publication sur GitHub Pages. Aucune action manuelle.

## Structure

- `docusaurus.config.ts`, `sidebars.ts` : configuration et navigation du site
- `docs/` : le contenu (cours, TP, bibliographies), organisé par semestre puis par bloc
- `docs/fil-rouge.md` : l'application 3-tiers « Listify » utilisée dans tous les TP
- `figures/` : sources TikZ des figures et leur Makefile
- `src/` : charte graphique (`css/custom.css`), composants (`Figure`, `ChapterHead`), encadrés (`theme/Admonition`), pages d'accueil et de l'enseignant
- `static/` : figures compilées, images, logo
- `plan.md` : le plan pédagogique des trois semestres

## Licence

Contenu sous licence [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/deed.fr).
