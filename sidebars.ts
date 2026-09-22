import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const b1 = 'semestre1/bloc1';
const b2 = 'semestre1/bloc2';
const b3 = 'semestre1/bloc3';
const s2b1 = 'semestre2/bloc1';
const s2b2 = 'semestre2/bloc2';
const s2b3 = 'semestre2/bloc3';

const sidebars: SidebarsConfig = {
  cours: [
    {
      type: 'category',
      label: 'Accueil',
      collapsed: false,
      items: ['index', 'fil-rouge', 'bibliographie'],
    },
    {
      type: 'category',
      label: 'Semestre 1',
      link: {type: 'doc', id: 'semestre1/index'},
      items: [
        {
          type: 'category',
          label: "Bloc 1 : le déploiement à l'ancienne",
          link: {type: 'doc', id: `${b1}/index`},
          items: [
            `${b1}/cours/anatomie-serveur`,
            `${b1}/cours/systeme-exploitation-serveur`,
            `${b1}/cours/reseau-deploiement`,
            `${b1}/cours/architecture-application-web`,
            `${b1}/cours/securite-de-base`,
            `${b1}/tp/tp1-vm-ssh-durcissement`,
            `${b1}/tp/tp2-backend-bdd`,
            `${b1}/tp/tp3-frontend-nginx-tls`,
            `${b1}/tp/tp4-jour2`,
            `${b1}/defi-final`,
          ],
        },
        {
          type: 'category',
          label: 'Bloc 2 : architecture multi-machines',
          link: {type: 'doc', id: `${b2}/index`},
          items: [
            `${b2}/cours/pourquoi-separer-les-services`,
            `${b2}/cours/reseau-prive-entre-machines`,
            `${b2}/cours/repartition-de-charge`,
            `${b2}/cours/configuration-distribuee`,
            `${b2}/tp/tp5-eclater-application`,
            `${b2}/tp/tp6-load-balancer`,
          ],
        },
        {
          type: 'category',
          label: 'Bloc 3 : Infrastructure as Code',
          link: {type: 'doc', id: `${b3}/index`},
          items: [
            `${b3}/cours/infrastructure-as-code`,
            `${b3}/cours/vagrant`,
            `${b3}/cours/ansible`,
            `${b3}/cours/terraform`,
            `${b3}/tp/tp7-vagrant`,
            `${b3}/tp/tp8-ansible`,
            `${b3}/tp/tp9-chaine-complete`,
            `${b3}/tp/tp10-terraform`,
          ],
        },
        'semestre1/evaluation',
      ],
    },
    {
      type: 'category',
      label: 'Semestre 2',
      link: {type: 'doc', id: 'semestre2/index'},
      items: [
        {
          type: 'category',
          label: 'Bloc 1 : la conteneurisation',
          link: {type: 'doc', id: `${s2b1}/index`},
          items: [
            `${s2b1}/cours/pourquoi-les-conteneurs`,
            `${s2b1}/cours/sous-le-capot`,
            `${s2b1}/cours/oci-ecosysteme`,
            `${s2b1}/cours/images`,
            `${s2b1}/cours/reseau-stockage-composition`,
            `${s2b1}/tp/tp11-namespaces-cgroups`,
            `${s2b1}/tp/tp12-images-containerfile`,
            `${s2b1}/tp/tp13-composition-pod`,
            `${s2b1}/tp/tp14-registre-scan`,
          ],
        },
        {
          type: 'category',
          label: 'Bloc 2 : orchestration, Kubernetes',
          link: {type: 'doc', id: `${s2b2}/index`},
          items: [
            `${s2b2}/cours/probleme-orchestration`,
            `${s2b2}/cours/modele-mental`,
            `${s2b2}/cours/objets-fondamentaux`,
            `${s2b2}/cours/exploitation-helm`,
            `${s2b2}/tp/tp15-premier-deploiement`,
            `${s2b2}/tp/tp16-fil-rouge-complet`,
            `${s2b2}/tp/tp17-diagnostic-pannes`,
            `${s2b2}/tp/tp18-helm`,
          ],
        },
        {
          type: 'category',
          label: 'Bloc 3 : CI/CD et observabilité',
          link: {type: 'doc', id: `${s2b3}/index`},
          items: [
            `${s2b3}/cours/integration-continue`,
            `${s2b3}/cours/livraison-deploiement-continus`,
            `${s2b3}/cours/gitops`,
            `${s2b3}/cours/observabilite`,
            `${s2b3}/tp/tp19-forge-premier-pipeline`,
            `${s2b3}/tp/tp20-livraison-gitops`,
            `${s2b3}/tp/tp21-observabilite`,
          ],
        },
      ],
    },
    {
      type: 'category',
      label: 'Semestre 3',
      link: {type: 'doc', id: 'semestre3/index'},
      items: [
        {
          type: 'category',
          label: 'Bloc 1 : pourquoi le ML en production est différent',
          link: {type: 'doc', id: 'semestre3/bloc1/index'},
          items: ['semestre3/bloc1/cours/dette-technique-ml', 'semestre3/bloc1/cours/versionner-donnees-modeles', 'semestre3/bloc1/cours/cycle-vie-mlops', 'semestre3/bloc1/cours/modes-mise-a-disposition', 'semestre3/bloc1/tp/tp22-notebook-irreproductible', 'semestre3/bloc1/tp/tp23-projet-reproductible-dvc'],
        },
        {
          type: 'category',
          label: 'Bloc 2 : outiller le cycle de vie, MLflow et Airflow',
          link: {type: 'doc', id: 'semestre3/bloc2/index'},
          items: ['semestre3/bloc2/cours/suivi-experiences-mlflow'],
        },
      ],
    },
  ],
};

export default sidebars;
