import styles from './styles.module.css';

type Props = {
  kicker: string;              // ex. « Semestre 1 · Bloc 1 · Chapitre 1 »
  title: string;
  lecture?: string;            // durée de lecture indicative
  competences?: string[];      // codes du référentiel (C1…C6)
  tp?: string;                 // TP associé
};

/** En-tête de chapitre : surtitre, titre, métadonnées pédagogiques. */
export default function ChapterHead({kicker, title, lecture, competences, tp}: Props) {
  return (
    <header className={styles.head}>
      <div className={styles.kicker}>{kicker}</div>
      <h1 className={styles.title}>{title}</h1>
      <dl className={styles.meta}>
        {lecture && (<div><dt>Lecture</dt><dd>{lecture}</dd></div>)}
        {competences && (<div><dt>Compétences</dt><dd>{competences.join(', ')}</dd></div>)}
        {tp && (<div><dt>Mise en pratique</dt><dd>{tp}</dd></div>)}
      </dl>
    </header>
  );
}
