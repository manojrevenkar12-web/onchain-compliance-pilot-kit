import { useCallback, useEffect, useState } from "react";

export interface Criterion {
  met: number;
  of: number;
  value: number;
  limit: number;
  kind: "min" | "max";
}

export interface Metrics {
  [key: string]: number | Record<string, Criterion>;
  alerts_per_day: number;
  alert_precision: number;
  reportable_escalated_share: number;
  sanctions_escalated_share: number;
  reportable_customers: number;
  reportable_alerted: number;
  wrong_escalations: number;
  working_hours_to_decision_p90: number;
  backlog_at_end: number;
  analyst_minutes_per_day: number;
  analyst_capacity_per_day: number;
  fast_lane: number;
  reportable_alerts_closed_without_review: number;
  reportable_missed_after_machine_close: number;
  travel_rule_holds: number;
  criteria_met: number;
  criteria: Record<string, Criterion>;
}

export interface Rule {
  rule: string;
  fires: string;
  threshold: string;
  severity: string;
}

export interface Prospect {
  discovery: { name: string; kind: string; jurisdiction: string; customers: number; review: { analysts: number; minutes_per_day_each: number } };
  rules: Rule[];
  notes: string[];
  designs: Record<string, Metrics>;
}

export interface Gate {
  gate: string;
  value: number;
  limit: number;
  kind: "max" | "min";
  pass: boolean;
}

export interface WebhookVariant {
  scenarios_broken: number;
  by_kind: Record<string, number>;
}

export interface Split {
  windows: { calibration_days: number; pilot_days: number };
  seeds: number[];
  labels: Record<string, string>;
  descriptions: Record<string, string>;
  prospects: Record<string, Prospect>;
  webhooks: { scenarios: number; variants: Record<string, WebhookVariant> };
  gates: { kit: Gate[]; kit_pass: boolean };
}

export interface Report {
  dev: Split;
  heldout: Split | null;
  criteria_labels: Record<string, string>;
  webhook_labels: Record<string, string>;
  webhook_kinds: Record<string, string>;
}

export type Load = { state: "loading" } | { state: "error"; message: string } | { state: "ready"; report: Report };

export function isReport(x: unknown): x is Report {
  const r = x as Report;
  return !!r && typeof r === "object" && !!r.dev && typeof r.dev.prospects === "object" && Object.keys(r.dev.prospects).length > 0 && !!r.criteria_labels;
}

export function useReport(url = "data/report.json"): { load: Load; retry: () => void } {
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let live = true;
    setLoad({ state: "loading" });
    fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error(`The pilot report could not be loaded (HTTP ${r.status}).`);
        return r.json();
      })
      .then((j: unknown) => {
        if (!live) return;
        if (!isReport(j)) throw new Error("The report file is not in the expected shape. Regenerate it with python -m ocp.cli report.");
        setLoad({ state: "ready", report: j });
      })
      .catch((e: Error) => live && setLoad({ state: "error", message: e.message }));
    return () => {
      live = false;
    };
  }, [url, attempt]);
  const retry = useCallback(() => setAttempt((a) => a + 1), []);
  return { load, retry };
}
