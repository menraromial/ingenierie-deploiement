import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';

// Types d'encadrés propres au cours (en plus de note/tip/info/warning/danger)
const encadres = ['objectifs', 'fiche', 'definition', 'exemple', 'recherche', 'citation', 'question'];

const config: Config = {
  title: 'Ingénierie du Déploiement',
  tagline:
    "Du serveur unique à l'Infrastructure as Code, des conteneurs à Kubernetes, du CI/CD au MLOps.",
  favicon: 'img/favicon.svg',
  future: {v4: true},
  url: 'https://menraromial.com',
  baseUrl: '/ingenierie-deploiement/',
  onBrokenLinks: 'throw',
  i18n: {defaultLocale: 'fr', locales: ['fr']},
  markdown: {hooks: {onBrokenMarkdownLinks: 'throw'}},

  presets: [
    [
      'classic',
      {
        docs: {
          routeBasePath: 'cours',
          sidebarPath: './sidebars.ts',
          remarkPlugins: [remarkMath],
          rehypePlugins: [rehypeKatex],
          admonitions: {keywords: encadres, extendDefaults: true},
          showLastUpdateTime: false,
        },
        blog: false,
        theme: {customCss: './src/css/custom.css'},
      } satisfies Preset.Options,
    ],
  ],

  stylesheets: [
    {
      href: 'https://cdn.jsdelivr.net/npm/katex@0.16.22/dist/katex.min.css',
      type: 'text/css',
      crossorigin: 'anonymous',
    },
  ],

  themeConfig: {
    colorMode: {respectPrefersColorScheme: true},
    docs: {sidebar: {hideable: true, autoCollapseCategories: true}},
    tableOfContents: {minHeadingLevel: 2, maxHeadingLevel: 3},
    navbar: {
      title: 'Ingénierie du Déploiement',
      logo: {alt: 'Monogramme du cours', src: 'img/logo.svg'},
      items: [
        {type: 'docSidebar', sidebarId: 'cours', position: 'left', label: 'Le cours'},
        {to: '/cours/semestre1', label: 'Semestre 1', position: 'left'},
        {to: '/cours/semestre2', label: 'Semestre 2', position: 'left'},
        {to: '/cours/semestre3', label: 'Semestre 3', position: 'left'},
        {to: '/cours/fil-rouge', label: 'Fil rouge', position: 'left'},
        {to: '/enseignant', label: "L'enseignant", position: 'right'},
      ],
    },
    footer: {
      style: 'light',
      links: [
        {
          title: 'Le parcours',
          items: [
            {label: 'Présentation', to: '/cours'},
            {label: 'Semestre 1 : fondations', to: '/cours/semestre1'},
            {label: 'Application fil rouge', to: '/cours/fil-rouge'},
            {label: 'Bibliographie générale', to: '/cours/bibliographie'},
          ],
        },
        {
          title: 'Enseignant',
          items: [{label: 'Romial Menra', to: '/enseignant'}],
        },
      ],
      copyright:
        `© ${new Date().getFullYear()} Romial Menra · Contenu sous licence ` +
        `<a href="https://creativecommons.org/licenses/by-nc-sa/4.0/deed.fr" rel="license noopener" target="_blank">CC BY-NC-SA 4.0</a>` +
        ` (attribution, pas d'usage commercial, partage dans les mêmes conditions)`,
    },
    prism: {
      theme: prismThemes.oneLight,
      darkTheme: prismThemes.oneDark,
      additionalLanguages: ['bash', 'nginx', 'ini', 'yaml', 'docker', 'hcl'],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
