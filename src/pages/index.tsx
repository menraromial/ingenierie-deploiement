import type {ReactNode} from 'react';
import Link from '@docusaurus/Link';
import Layout from '@theme/Layout';
import useBaseUrl from '@docusaurus/useBaseUrl';
import styles from './index.module.css';

const SEMESTRES = [
  {
    tone: 'ocre',
    num: 'Semestre 1',
    titre: 'Fondations',
    resume: "Déployer à la main, souffrir de la configuration distribuée, puis automatiser.",
    blocs: ["Le déploiement à l'ancienne", 'Architecture multi-machines', 'Infrastructure as Code'],
    volume: '13 chapitres · 10 TP',
    to: '/cours/semestre1',
  },
  {
    tone: 'enc',
    num: 'Semestre 2',
    titre: 'Conteneurs et orchestration',
    resume: 'Comprendre le conteneur sous le capot, puis confier la réconciliation à Kubernetes.',
    blocs: ['La conteneurisation', 'Orchestration, Kubernetes', 'CI/CD, GitOps, observabilité'],
    volume: '9 chapitres · 8 TP (en cours)',
    to: '/cours',
  },
  {
    tone: 'sea',
    num: 'Semestre 3',
    titre: 'MLOps et données',
    resume: "Rendre reproductibles les données et les modèles, industrialiser l'entraînement.",
    blocs: ['Reproductibilité, DVC', 'MLflow et Airflow', 'Dérive, Spark, Kafka'],
    volume: 'en préparation',
    to: '/cours',
  },
];

const PRINCIPES = [
  ['La théorie d’abord, l’outil ensuite', "Les outils meurent, les concepts restent : idempotence, isolation, réconciliation d'état. L'évaluation porte sur les concepts."],
  ['Apprendre par la friction', "On déploie à la main avant d'automatiser, pour savoir précisément ce que l'outil abstrait, et où chercher quand il casse."],
  ['Tout en local', 'VirtualBox, Vagrant, Podman, kind : aucun compte cloud payant, tout tourne sur votre poste.'],
  ['Un fil rouge unique', "L'application Listify est redéployée à chaque étape ; on mesure, chronomètre en main, le gain de chaque abstraction."],
];

function Hero() {
  return (
    <header className={styles.hero}>
      <div className="container">
        <div className={styles.kicker}>Cycle ingénieur · M1-M2 · trois semestres</div>
        <h1 className={styles.title}>
          Ingénierie du Déploiement
          <br />
          <span>et de la Mise en Production</span>
        </h1>
        <p className={styles.lead}>
          Un parcours qui reconstruit l'histoire du déploiement : du serveur configuré à la main
          jusqu'aux pipelines de MLOps, chaque outil est introduit comme la réponse à un problème
          que vous aurez vécu en TP.
        </p>
        <div className={styles.actions}>
          <Link className="button button--primary button--lg" to="/cours">
            Commencer le parcours
          </Link>
          <Link className="button button--outline button--secondary button--lg" to="/enseignant">
            L'enseignant
          </Link>
        </div>
      </div>
    </header>
  );
}

function Semestres() {
  return (
    <section className={styles.section}>
      <div className="container">
        <h2 className={styles.h2}>Trois semestres, un fil conducteur</h2>
        <div className={styles.grid3}>
          {SEMESTRES.map((s) => (
            <Link key={s.num} to={s.to} className={`${styles.card} ${styles[s.tone]}`}>
              <div className={styles.cardNum}>{s.num}</div>
              <h3>{s.titre}</h3>
              <p>{s.resume}</p>
              <ol>
                {s.blocs.map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ol>
              <div className={styles.cardFoot}>{s.volume}</div>
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}

function Principes() {
  return (
    <section className={`${styles.section} ${styles.alt}`}>
      <div className="container">
        <h2 className={styles.h2}>Philosophie du cours</h2>
        <div className={styles.grid2}>
          {PRINCIPES.map(([t, d], i) => (
            <div key={t} className={styles.principe}>
              <span className={styles.pnum}>{i + 1}</span>
              <div>
                <h3>{t}</h3>
                <p>{d}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Enseignant() {
  const photo = useBaseUrl('/img/romial-menra.jpg');
  return (
    <section className={styles.section}>
      <div className={`container ${styles.teacher}`}>
        <img src={photo} alt="Portrait de Romial Menra" className={styles.teacherPhoto} />
        <div>
          <div className={styles.kicker}>Responsable du cours</div>
          <h2 className={styles.teacherName}>Romial Menra</h2>
          <p className={styles.teacherRole}>Doctorant en informatique, Inria Rennes et IMT Atlantique</p>
          <p>
            Ses recherches portent sur la gestion de la puissance dans les infrastructures cloud et
            l'orchestration Kubernetes consciente de l'énergie. Ce parcours
            est conçu pour que chaque notion de déploiement soit vécue avant d'être automatisée.
          </p>
          <Link to="/enseignant">Voir le profil complet →</Link>
        </div>
      </div>
    </section>
  );
}

export default function Home(): ReactNode {
  return (
    <Layout
      title="Accueil"
      description="Parcours en trois semestres : du serveur unique à l'Infrastructure as Code, des conteneurs à Kubernetes, du CI/CD au MLOps.">
      <Hero />
      <main>
        <Semestres />
        <Principes />
        <Enseignant />
      </main>
    </Layout>
  );
}
