import { motion, useReducedMotion } from "framer-motion";
import type { Criterion, Prospect } from "../../shared/data/report";
import { num, pct } from "../../shared/format";
import styles from "./scorecard.module.css";

const isShare = (key: string) => key.includes("escalated");
const fmt = (key: string, x: number) => (isShare(key) ? pct(x, 0) : num(x, 1));

function Mark({ c }: { c: Criterion }) {
  const all = c.met === c.of;
  return (
    <span className={all ? styles.met : styles.missed}>
      <span aria-hidden="true">{all ? "✓" : "✗"}</span> {all ? "met" : "missed"} in {c.met} of {c.of} runs
    </span>
  );
}

export function Scorecard({ prospect, labels }: { prospect: Prospect; labels: Record<string, string> }) {
  const reduce = useReducedMotion();
  const kit = prospect.designs.kit?.criteria ?? {};
  const asis = prospect.designs.as_is?.criteria ?? {};
  const keys = Object.keys(labels).filter((k) => kit[k]);
  if (!keys.length) return <p>This prospect has no success criteria in the report.</p>;
  return (
    <ol className={styles.list}>
      {keys.map((k, i) => {
        const c = kit[k]!;
        const a = asis[k];
        return (
          <motion.li
            key={k}
            className={styles.row}
            initial={reduce ? false : { opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, delay: 0.08 * i, ease: [0.2, 0.7, 0.2, 1] }}
          >
            <div className={styles.what}>
              <span className={styles.label}>{labels[k]}</span>
              <span className={styles.target}>
                Agreed in discovery: {c.kind === "min" ? "at least" : "at most"} {fmt(k, c.limit)}
              </span>
            </div>
            <div className={styles.cell}>
              <span className={styles.who}>As found</span>
              <span className={styles.asis}>{a ? fmt(k, a.value) : "–"}</span>
            </div>
            <div className={styles.cell}>
              <span className={styles.who}>Pilot kit</span>
              <span className={styles.kit}>{fmt(k, c.value)}</span>
            </div>
            <div className={styles.mark}>
              <Mark c={c} />
            </div>
          </motion.li>
        );
      })}
    </ol>
  );
}
