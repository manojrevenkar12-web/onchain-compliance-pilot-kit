import type { Prospect } from "../../shared/data/report";
import { num, pct } from "../../shared/format";
import t from "../../shared/ui/table.module.css";

const DESIGNS: [string, string][] = [
  ["no_triage", "Manual review, same rules"],
  ["kit", "Governed AI triage"],
  ["ungoverned_triage", "AI closes low scores on its own"],
];

export function Triage({ prospect }: { prospect: Prospect }) {
  return (
    <div className={t.wrap}>
      <table className={t.table}>
        <thead>
          <tr>
            <th scope="col">Triage</th>
            <th scope="col">Analyst minutes a day</th>
            <th scope="col">Working hours to a decision, p90</th>
            <th scope="col">Closed in the fast lane</th>
            <th scope="col">Reportable alerts closed without a full review</th>
            <th scope="col">Reportable customers lost that way</th>
            <th scope="col">Reportable customers escalated in time</th>
          </tr>
        </thead>
        <tbody>
          {DESIGNS.map(([n, label]) => {
            const m = prospect.designs[n];
            if (!m) return null;
            return (
              <tr key={n} className={n === "kit" ? t.us : undefined}>
                <th scope="row">{label}</th>
                <td>{num(m.analyst_minutes_per_day)}</td>
                <td>{num(m.working_hours_to_decision_p90, 1)}</td>
                <td>{num(m.fast_lane, 1)}</td>
                <td>{num(m.reportable_alerts_closed_without_review, 1)}</td>
                <td className={m.reportable_missed_after_machine_close > 0 ? t.fail : t.zero}>{num(m.reportable_missed_after_machine_close, 1)}</td>
                <td>{pct(m.reportable_escalated_share, 1)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
