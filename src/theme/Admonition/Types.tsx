/**
 * Encadrés du cours : remplace le rendu par défaut des admonitions
 * Docusaurus par des encadrés de manuel (filet coloré, étiquette en
 * petites capitales, pas d'emoji). Syntaxe Markdown inchangée :
 *   :::definition[Hyperviseur]
 *   ...
 *   :::
 */
import type {ComponentProps, ReactNode} from 'react';
import clsx from 'clsx';
import styles from './styles.module.css';

type Kind = {label: string; tone: 'enc' | 'sea' | 'ocre' | 'brick' | 'plum' | 'ink'};

const KINDS: Record<string, Kind> = {
  objectifs: {label: 'Objectifs du chapitre', tone: 'enc'},
  fiche: {label: 'Fiche du TP', tone: 'ocre'},
  definition: {label: 'Définition', tone: 'plum'},
  exemple: {label: 'Exemple travaillé', tone: 'sea'},
  recherche: {label: 'Regard recherche', tone: 'plum'},
  citation: {label: 'Citation', tone: 'ink'},
  question: {label: 'Question', tone: 'enc'},
  note: {label: 'Remarque', tone: 'ink'},
  info: {label: 'À savoir', tone: 'enc'},
  tip: {label: 'Conseil pratique', tone: 'sea'},
  warning: {label: 'Attention', tone: 'ocre'},
  danger: {label: 'Piège classique', tone: 'brick'},
  caution: {label: 'Attention', tone: 'ocre'},
};

type Props = {type?: string; title?: ReactNode; className?: string; children: ReactNode};

function Encadre({type = 'note', title, className, children}: Props) {
  const kind = KINDS[type] ?? KINDS.note;
  // un titre explicite devient le titre ; l'étiquette de type reste au-dessus
  return (
    <aside className={clsx(styles.box, styles[kind.tone], className)} data-kind={type}>
      <div className={styles.kicker}>{kind.label}</div>
      {title && title !== type && <div className={styles.title}>{title}</div>}
      <div className={styles.body}>{children}</div>
    </aside>
  );
}

const make = (type: string) => (p: ComponentProps<typeof Encadre>) => <Encadre {...p} type={type} />;

export default Object.fromEntries(Object.keys(KINDS).map((k) => [k, make(k)]));
