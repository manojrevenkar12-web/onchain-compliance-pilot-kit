import type { Split } from "../../shared/data/report";
import t from "../../shared/ui/table.module.css";

const fmt = (x: number) => (Math.abs(x) >= 100 ? x.toFixed(0) : Math.abs(x) >= 1 ? x.toFixed(2) : x.toFixed(4));

export function Gates({ split }: { split: Split }) {
  const g = split.gates.kit;
  const passed = g.filter((x) => x.pass).length;
  return (
    <div className={t.wrap}>
      <p className={split.gates.kit_pass ? t.pass : t.fail}>
        {passed} of {g.length} gates pass
      </p>
      <table className={t.table}>
        <thead>
          <tr>
            <th scope="col">Gate</th>
            <th scope="col">Measured</th>
            <th scope="col">Limit</th>
            <th scope="col">Result</th>
          </tr>
        </thead>
        <tbody>
          {g.map((x) => (
            <tr key={x.gate}>
              <th scope="row">{x.gate}</th>
              <td>{fmt(x.value)}</td>
              <td>
                {x.kind === "min" ? "at least" : "at most"} {fmt(x.limit)}
              </td>
              <td className={x.pass ? t.pass : t.fail}>{x.pass ? "✓ pass" : "✗ fail"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
