import type {ReactNode} from 'react';
import useBaseUrl from '@docusaurus/useBaseUrl';
import styles from './styles.module.css';

type Props = {
  /** nom du fichier dans static/figures (sans extension), figure TikZ */
  src?: string;
  /** chemin d'une photographie dans static/ (ex. « /img/photo.jpg ») */
  photo?: string;
  /** numéro affiché, ex. « 1.1 » */
  num?: string;
  alt: string;
  /** largeur maximale relative à la colonne (ex. « 80% ») */
  width?: string;
  /** source ou crédit, affiché après la légende */
  source?: ReactNode;
  children: ReactNode; // la légende
};

/** Figure numérotée, dessinée en LaTeX/TikZ (figures/src/<src>.tex). */
export default function Figure({src, photo, num, alt, width, source, children}: Props) {
  const svg = useBaseUrl(photo ?? `/figures/${src}.svg`);
  const pdf = useBaseUrl(`/figures/${src}.pdf`);
  return (
    <figure className={styles.figure} id={num ? `fig-${num}` : undefined}>
      <div className={photo ? styles.photo : styles.plate}>
        <img src={svg} alt={alt} style={{maxWidth: width ?? '100%'}} loading="lazy" />
      </div>
      <figcaption className={styles.caption}>
        {num && <span className={styles.label}>Figure {num}.</span>} {children}
        {source && <span className={styles.source}> Source : {source}</span>}
        {!photo && (
          <a className={styles.pdf} href={pdf} target="_blank" rel="noopener">
            PDF vectoriel
          </a>
        )}
      </figcaption>
    </figure>
  );
}
