import styles from "./section.module.css";

export function Section({ id, title, intro, children }: { id: string; title: string; intro?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className={styles.section} aria-labelledby={`${id}-title`} id={id}>
      <header className={styles.head}>
        <h2 id={`${id}-title`} className={styles.title}>
          {title}
        </h2>
        {intro && <p className={styles.intro}>{intro}</p>}
      </header>
      {children}
    </section>
  );
}
