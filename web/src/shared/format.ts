export const pct = (x: number | null | undefined, d = 1) => (x == null ? "–" : `${(100 * x).toFixed(d)}%`);
export const num = (x: number | null | undefined, d = 0) =>
  x == null ? "–" : x.toLocaleString("en-GB", { minimumFractionDigits: d, maximumFractionDigits: d });
