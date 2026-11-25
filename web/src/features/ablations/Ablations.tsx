import type { Split } from "../../shared/data/report";
import { num, pct } from "../../shared/format";
import t from "../../shared/ui/table.module.css";

export function Ablations({ split, prospect }: { split: Split; prospect: string }) {
  const p = split.prospects[prospect];
  if (!p) return null;
  const names = Object.keys(split.labels).filter((n) => p.designs[n]);
  return (
    <div className={t.wrap}>
      <table className={t.table}>
        <thead>
          <tr>
            <th scope="col">Design</th>
            <th scope="col">Alerts a day</th>
            <th scope="col">Reportable customers with no alert</th>
            <th scope="col">Escalated in time</th>
            <th scope="col">Waiting at the end</th>
            <th scope="col">Success criteria met (of 5)</th>
          </tr>
        </thead>
        <tbody>
          {names.map((n) => {
            const m = p.designs[n]!;
            return (
              <tr key={n} className={n === "kit" ? t.us : undefined} title={split.descriptions[n]}>
                <th scope="row">{split.labels[n]}</th>
                <td>{num(m.alerts_per_day, 1)}</td>
                <td>{num(m.reportable_customers - m.reportable_alerted, 1)}</td>
                <td>{pct(m.reportable_escalated_share, 1)}</td>
                <td>{num(m.backlog_at_end)}</td>
                <td>{num(m.criteria_met, 1)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
