import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useState } from "react";
import { Ablations } from "../features/ablations/Ablations";
import { Funnel } from "../features/funnel/Funnel";
import { Gates } from "../features/gates/Gates";
import { Rules } from "../features/rules/Rules";
import { Scorecard } from "../features/scorecard/Scorecard";
import { Triage } from "../features/triage/Triage";
import { Webhooks } from "../features/webhooks/Webhooks";
import { useReport, type Report } from "../shared/data/report";
import { num } from "../shared/format";
import { Section } from "../shared/ui/Section";
import { EmptyState, ErrorState, Skeleton } from "../shared/ui/States";
import styles from "./App.module.css";

function Body({ report }: { report: Report }) {
  const reduce = useReducedMotion();
  const [which, setWhich] = useState<"dev" | "heldout">("dev");
  const split = which === "heldout" && report.heldout ? report.heldout : report.dev;
  const names = Object.keys(split.prospects);
  const [picked, setPicked] = useState<string>(names[0] ?? "");
  const name = split.prospects[picked] ? picked : (names[0] ?? "");
  const p = split.prospects[name];
  if (!p) return <EmptyState title="No prospects in this report.">Add discovery notes under config/prospects and run python -m ocp.cli dev.</EmptyState>;
  const k = p.designs.kit;
  const met = k ? k.criteria_met : 0;
  return (
    <>
      <header className={styles.hero}>
        <p className={styles.kicker}>Onchain compliance pilot room</p>
        <div className={styles.splits} role="group" aria-label="Which prospects">
          <button type="button" aria-pressed={which === "dev"} onClick={() => setWhich("dev")}>
            Development prospects
          </button>
          <button type="button" aria-pressed={which === "heldout"} disabled={!report.heldout} onClick={() => setWhich("heldout")}>
            Held-out prospect, run once
          </button>
        </div>
        <nav className={styles.tabs} aria-label="Prospect">
          {names.map((n) => (
            <button key={n} type="button" aria-current={n === name ? "page" : undefined} onClick={() => setPicked(n)}>
              <span className={styles.tabName}>{split.prospects[n]!.discovery.name.replace(" (fictional)", "")}</span>
              <span className={styles.tabMeta}>{split.prospects[n]!.discovery.jurisdiction}</span>
            </button>
          ))}
        </nav>
        <AnimatePresence mode="wait">
          <motion.div
            key={`${which}-${name}`}
            initial={reduce ? false : { opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={reduce ? undefined : { opacity: 0 }}
            transition={{ duration: 0.2 }}
            className={styles.heroBody}
          >
            <h1 className={styles.title}>
              {num(met, 1)} of 5 success criteria met for {p.discovery.name.replace(" (fictional)", "")}
            </h1>
            <p className={styles.lede}>
              {p.discovery.kind.charAt(0).toUpperCase() + p.discovery.kind.slice(1)}, about {num(p.discovery.customers)} customers,{" "}
              {p.discovery.review.analysts} analysts. Criteria agreed in discovery, measured over a {split.windows.pilot_days}-day simulated pilot after{" "}
              {split.windows.calibration_days} days of shared history; mean of {split.seeds.length} runs. The names are fictional.
            </p>
            <Scorecard prospect={p} labels={report.criteria_labels} />
          </motion.div>
        </AnimatePresence>
      </header>
      <main>
        <Section
          id="funnel"
          title="From alerts to escalations"
          intro="Vendor default rules against rules compiled from discovery, tuned on the shared history and triaged with evidence packs."
        >
          <Funnel prospect={p} />
        </Section>
        <Section
          id="rules"
          title="Rules compiled from discovery"
          intro="What the customer's risk appetite turns into, in words their MLRO can sign off. Tuning then moves the thresholds within the team's capacity."
        >
          <Rules prospect={p} />
        </Section>
        <Section
          id="triage"
          title="AI triage, with and without its guard rails"
          intro="Hard rules come before the score: prohibited categories, behavioural alerts and amounts of EUR 10,000 or more always get a full human review, and 10% of the fast lane is sampled."
        >
          <Triage prospect={p} />
        </Section>
        <Section id="ablations" title="What each part is worth" intro="Every design on the same customers and the same luck. Hover a row for what it changes.">
          <Ablations split={split} prospect={name} />
        </Section>
        <Section
          id="webhooks"
          title="Alert webhooks into case management"
          intro="Deliveries duplicated, reordered and retried; a receiver that dies after committing; forged and replayed events. Each row removes one safeguard."
        >
          <Webhooks split={split} report={report} />
        </Section>
        <Section id="gates" title="Release gates" intro="Set on the development prospects before the held-out run, across all prospects.">
          <Gates split={split} />
        </Section>
      </main>
      <footer className={styles.footer}>
        Simulated customers, transfers and attributions; no vendor API or data. The rules engine, tuner, triage checks and webhook receiver are real code. See
        the README for the limits.
      </footer>
    </>
  );
}

export function App() {
  const { load, retry } = useReport();
  return (
    <div className={styles.page}>
      {load.state === "loading" && <Skeleton lines={6} label="Loading the pilot report" />}
      {load.state === "error" && <ErrorState message={load.message} onRetry={retry} />}
      {load.state === "ready" && <Body report={load.report} />}
    </div>
  );
}
