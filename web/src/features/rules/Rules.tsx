import type { Prospect } from "../../shared/data/report";
import t from "../../shared/ui/table.module.css";
import styles from "./rules.module.css";

export function Rules({ prospect }: { prospect: Prospect }) {
  if (!prospect.rules.length) return <p>No rules compiled for this prospect.</p>;
  return (
    <div className={styles.wrap}>
      {prospect.notes.length > 0 && (
        <ul className={styles.notes} aria-label="To confirm with the customer">
          {prospect.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
      <div className={t.wrap}>
        <table className={t.table}>
          <thead>
            <tr>
              <th scope="col">Rule</th>
              <th scope="col" className={styles.left}>
                Fires on
              </th>
              <th scope="col" className={styles.left}>
                Threshold before tuning
              </th>
              <th scope="col">Severity</th>
            </tr>
          </thead>
          <tbody>
            {prospect.rules.map((r) => (
              <tr key={r.rule}>
                <th scope="row" className={styles.rule}>
                  {r.rule}
                </th>
                <td className={styles.left}>{r.fires}</td>
                <td className={styles.left}>{r.threshold}</td>
                <td>{r.severity}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
