import { useState } from "react";
import type { Prospect } from "../../shared/data/report";
import { num, pct } from "../../shared/format";
import styles from "./funnel.module.css";

interface Row {
  label: string;
  asis: number;
  kit: number;
  max: number;
  fmt: (x: number) => string;
  better: "less" | "more";
}

function rows(p: Prospect): Row[] {
  const a = p.designs.as_is!;
  const k = p.designs.kit!;
  const cap = Math.max(a.analyst_capacity_per_day, a.analyst_minutes_per_day, k.analyst_minutes_per_day);
  return [
    {
      label: "Alerts a day",
      asis: a.alerts_per_day,
      kit: k.alerts_per_day,
      max: Math.max(a.alerts_per_day, k.alerts_per_day),
      fmt: (x) => num(x, 1),
      better: "less",
    },
    { label: "Alerts on customers who were really reportable", asis: a.alert_precision, kit: k.alert_precision, max: 1, fmt: (x) => pct(x, 0), better: "more" },
    {
      label: "Reportable customers escalated in time",
      asis: a.reportable_escalated_share,
      kit: k.reportable_escalated_share,
      max: 1,
      fmt: (x) => pct(x, 1),
      better: "more",
    },
    { label: "Analyst minutes a day on alerts", asis: a.analyst_minutes_per_day, kit: k.analyst_minutes_per_day, max: cap, fmt: (x) => num(x), better: "less" },
    {
      label: "Alerts waiting at the end of the pilot",
      asis: a.backlog_at_end,
      kit: k.backlog_at_end,
      max: Math.max(a.backlog_at_end, k.backlog_at_end, 1),
      fmt: (x) => num(x),
      better: "less",
    },
  ];
}

export function Funnel({ prospect }: { prospect: Prospect }) {
  const [tip, setTip] = useState<string>("");
  if (!prospect.designs.as_is || !prospect.designs.kit) return <p>No comparison in this report.</p>;
  return (
    <div className={styles.wrap}>
      <ul className={styles.legend} aria-label="Legend">
        <li>
          <span className={`${styles.swatch} ${styles.asis}`} aria-hidden="true" /> As found
        </li>
        <li>
          <span className={`${styles.swatch} ${styles.kit}`} aria-hidden="true" /> Pilot kit
        </li>
      </ul>
      {rows(prospect).map((r) => (
        <div key={r.label} className={styles.row}>
          <span className={styles.label}>
            {r.label} <span className={styles.hint}>({r.better} is better)</span>
          </span>
          <div className={styles.bars}>
            {(["asis", "kit"] as const).map((w) => {
              const v = r[w];
              const text = `${w === "kit" ? "Pilot kit" : "As found"}: ${r.fmt(v)}`;
              return (
                <div key={w} className={styles.line}>
                  <span
                    className={`${styles.bar} ${styles[w]}`}
                    style={{ width: `${Math.max(0.5, (80 * v) / (r.max || 1))}%` }}
                    tabIndex={0}
                    role="img"
                    aria-label={`${r.label}, ${text}`}
                    onMouseEnter={() => setTip(`${r.label}, ${text}`)}
                    onFocus={() => setTip(`${r.label}, ${text}`)}
                    onMouseLeave={() => setTip("")}
                    onBlur={() => setTip("")}
                  />
                  <span className={styles.value}>{r.fmt(v)}</span>
                </div>
              );
            })}
          </div>
        </div>
      ))}
      <p className={styles.tip} aria-live="polite">
        {tip || " "}
      </p>
    </div>
  );
}
