import type {ReactNode} from 'react';
import Link from '@docusaurus/Link';
import Layout from '@theme/Layout';
import useBaseUrl from '@docusaurus/useBaseUrl';
import styles from './enseignant.module.css';

const LIENS: [string, string][] = [
  ['ORCID', 'https://orcid.org/0009-0007-0943-8593'],
  ['Google Scholar', 'https://scholar.google.com/citations?user=M2nDshIAAAAJ'],
  ['GitHub', 'https://github.com/menraromial'],
  ['LinkedIn', 'https://www.linkedin.com/in/menraromial'],
  ['ResearchGate', 'https://www.researchgate.net/profile/Romial-Menra'],
];

export default function Enseignant(): ReactNode {
  const photo = useBaseUrl('/img/romial-menra.jpg');
  return (
    <Layout title="L'enseignant" description="Profil de Romial Menra, responsable du cours.">
      <main className={`container ${styles.page}`}>
        <aside className={styles.side}>
          <img src={photo} alt="Portrait de Romial Menra" className={styles.photo} />
          <dl className={styles.facts}>
            <dt>Affiliation</dt>
            <dd>Inria Rennes · IMT Atlantique (Nantes)</dd>
            <dt>Statut</dt>
            <dd>Doctorant depuis novembre 2024, chargé de TD/TP</dd>
            <dt>Contact</dt>
            <dd>itsme [at] menraromial [dot] com</dd>
            <dt>Site personnel</dt>
            <dd><a href="https://menraromial.com/">menraromial.com</a></dd>
            <dt>Profils</dt>
            <dd className={styles.links}>
              {LIENS.map(([label, href]) => (
                <a key={label} href={href} target="_blank" rel="noopener">{label}</a>
              ))}
            </dd>
          </dl>
        </aside>

        <article className={styles.main}>
          <div className={styles.kicker}>Responsable du cours</div>
          <h1 className={styles.name}>Romial Menra</h1>
          <p className={styles.role}>Doctorant en informatique · Inria Rennes · IMT Atlantique</p>

          <h2>Présentation</h2>
          <p>
            Romial Menra prépare depuis novembre 2024 un doctorat en informatique à Inria et IMT
            Atlantique. Ses recherches portent sur la gestion de la puissance dans les infrastructures
            cloud, les systèmes de calcul conscients de l'énergie et les systèmes distribués durables,
            avec un intérêt particulier pour l'orchestration Kubernetes et la gestion énergétique des
            serveurs.
          </p>
          <p>
            Ingénieur de formation (diplôme d'ingénieur en informatique de l'École nationale supérieure
            polytechnique de Yaoundé, ENSPY, spécialité systèmes distribués et génie logiciel), Romial Menra a
            auparavant dirigé une équipe de dix développeurs sur des plateformes d'apprentissage en
            ligne et de gestion scolaire. Ce passage par la production nourrit directement ce cours.
          </p>

          <h2>Thèmes de recherche</h2>
          <ul>
            <li>Gestion de la puissance dans les infrastructures cloud (plafonnement, RAPL, Turbo Boost).</li>
            <li>Orchestration Kubernetes consciente de l'énergie et optimisation guidée par la charge.</li>
            <li>Systèmes distribués durables.</li>
          </ul>

          <h2>Publications choisies</h2>
          <ol className={styles.pubs}>
            <li>
              <strong>R. Menra</strong>, G. Rosinosky, R.-A. Koutsiamanis, S. Bolle, J.-M. Menaud.
              « Understanding Power Limiting Mechanisms in Modern Processors: A Deep Dive into Intel
              RAPL and Turbo Boost Dynamics ». <em>Euro-Par 2026</em>, LNCS, Springer, p. 135-149.{' '}
              <a href="https://doi.org/10.1007/978-3-032-35251-4_10">DOI</a>.{' '}
              <span className={styles.award}>Nommé pour le prix du meilleur article</span>
            </li>
            <li>
              <strong>R. Menra</strong>, R.-A. Koutsiamanis, J.-M. Menaud. « Intégration de l'aspect
              énergétique dans Kubernetes ». <em>COMPAS 2024</em>, Nantes.{' '}
              <a href="https://hal.science/hal-05638939">HAL</a>.
            </li>
          </ol>

          <h2>Enseignements</h2>
          <ul>
            <li>
              <Link to="/cours">Ingénierie du Déploiement et de la Mise en Production</Link> : conception
              et rédaction du parcours (cycle ingénieur, trois semestres).
            </li>
            <li><strong>Algorithmique et théorie des graphes</strong> : TD/TP.</li>
            <li>
              <strong>Bases de données</strong> (IMT Atlantique, FISE 1A, 2025) : TD/TP sur le modèle
              relationnel, SQL et transactions, normalisation, modélisation UML.
            </li>
            <li>
              <strong>Cloud Computing</strong> (IMT Atlantique, 2025) : TP sur VMware vSphere et vCenter,
              provisionnement et administration de machines virtuelles.
            </li>
          </ul>

          <h2>Pourquoi ce cours</h2>
          <blockquote className={styles.quote}>
            « Un ingénieur qui a compris la boucle de réconciliation apprendra le successeur de
            Kubernetes en une semaine ; un ingénieur qui a appris Kubernetes par cœur devra tout
            recommencer. »
          </blockquote>
          <p>
            Le parcours fait revivre, dans l'ordre où l'industrie les a rencontrés, les problèmes qui
            ont fait naître les outils du déploiement moderne. Chaque TP a été exécuté et vérifié de
            bout en bout sur une machine réelle avant d'être publié.
          </p>
        </article>
      </main>
    </Layout>
  );
}
