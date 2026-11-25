import type { Report, Split } from "../../shared/data/report";
import { num } from "../../shared/format";
import styles from "./webhooks.module.css";

const ORDER = ["kit", "no_signature", "no_dedupe", "no_versioning", "no_retries"];

export function Webhooks({ split, report }: { split: Split; report: Report }) {
  const w = split.webhooks;
  const kinds = Object.keys(report.webhook_kinds).filter((k) => Object.values(w.variants).some((v) => v.by_kind[k]));
  return (
    <div className={styles.wrap}>
      <table className={styles.table}>
        <caption className={styles.caption}>{num(w.scenarios)} scenarios per receiver; a cell counts the scenarios where that went wrong.</caption>
        <thead>
          <tr>
            <th scope="col">Receiver</th>
            <th scope="col">Broken</th>
            {kinds.map((k) => (
              <th scope="col" key={k} className={styles.kind}>
                {report.webhook_kinds[k]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ORDER.filter((v) => w.variants[v]).map((v) => {
            const row = w.variants[v]!;
            return (
              <tr key={v} className={v === "kit" ? styles.us : undefined}>
                <th scope="row">{report.webhook_labels[v] ?? v}</th>
                <td className={styles.total}>{num(row.scenarios_broken)}</td>
                {kinds.map((k) => {
                  const n = row.by_kind[k] ?? 0;
                  return (
                    <td key={k} className={styles.cell} style={{ ["--w" as string]: `${Math.min(100, Math.round((n / w.scenarios) * 120))}%` }}>
                      {n ? num(n) : <span className={styles.none}>0</span>}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
