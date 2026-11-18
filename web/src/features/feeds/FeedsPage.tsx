import { motion, useReducedMotion } from "framer-motion";
import { useState } from "react";
import { get, type Alert, type FeedsResponse, type Run } from "../../shared/api";
import { Empty, Failed, Loading } from "../../shared/States";
import { useResource } from "../../shared/useResource";
import "./feeds.css";

type Cell = "loaded" | "backfill" | "quarantined" | "missing" | "off";

const NAMES: Record<string, string> = {
  vendor_profiles: "Vendor profiles",
  register_notices: "Register notices",
  news_mentions: "Press mentions",
  job_posts: "Job boards",
};

const ALERT_TEXT: Record<string, string> = {
  freshness: "stopped delivering",
  volume: "delivered far fewer rows than usual",
  schema: "changed its shape",
  null_rate: "sent empty fields",
  duplicates: "repeated rows inside one file",
  weekly_look: "was missing files at the weekly look",
};

function cells(feed: string, cadence: number, last: number, runs: Run[]): Cell[] {
  const mine = runs.filter((r) => r.feed === feed);
  return Array.from({ length: last + 1 }, (_, d) => {
    if (d % cadence !== 0) return "off";
    const day = mine.filter((r) => r.delivery_day === d);
    if (day.some((r) => r.kind === "backfill" && r.status === "loaded")) return "backfill";
    if (day.some((r) => r.kind === "scheduled" && r.status === "loaded")) return "loaded";
    if (day.some((r) => r.status === "quarantined")) return "quarantined";
    return "missing";
  });
}

function clock(hour: number) {
  const d = Math.floor(hour / 24);
  return `day ${d}, ${String(hour % 24).padStart(2, "0")}:00`;
}

export function FeedsPage() {
  const res = useResource(() => get<FeedsResponse>("/feeds"));
  const reduce = useReducedMotion();
  const [hover, setHover] = useState<{ feed: string; day: number; cell: Cell } | null>(null);
  if (res.state === "loading") return <Loading what="feed health" />;
  if (res.state === "error") return <Failed what="feed health" message={res.message} retry={res.retry} />;
  const { feeds, alerts, runs } = res.data;
  if (!runs.length) return <Empty>No delivery has been loaded yet. Run the demo or wait for the 06:00 files.</Empty>;
  const last = Math.max(...runs.map((r) => r.delivery_day));
  const patched = runs.filter((r) => r.kind === "backfill").length;
  const real = alerts.filter((a) => a.kind !== "duplicates");
  const tapes = feeds.map((f) => ({ ...f, cells: cells(f.feed, f.cadence_days, last, runs) }));

  return (
    <section className="feeds">
      <header className="page-head">
        <h1>
          {real.length} alerts in {last + 1} days, {patched} days backfilled
        </h1>
        <p className="muted">
          Each mark is one day&rsquo;s delivery. A gap is a file that never came, a plum mark a file that broke its
          contract, ochre a day the provider redelivered after the alert.
        </p>
      </header>

      <div className="tapes" onMouseLeave={() => setHover(null)}>
        {tapes.map((t, row) => (
          <div className="tape-row" key={t.feed}>
            <div className="tape-label">
              <h3>{NAMES[t.feed] ?? t.feed}</h3>
              <span className="muted">
                {t.cadence_days === 1 ? "daily" : "weekly"}, alert after {t.sla_hours} h
              </span>
            </div>
            <div className="tape" style={{ gridTemplateColumns: `repeat(${last + 1}, 1fr)` }}>
              {t.cells.map((c, d) => (
                <motion.span
                  key={d}
                  className={`cell cell-${c}`}
                  initial={reduce ? false : { scaleY: 0 }}
                  animate={{ scaleY: 1 }}
                  transition={{ delay: reduce ? 0 : row * 0.12 + d * 0.006, duration: 0.18 }}
                  onMouseEnter={() => setHover({ feed: t.feed, day: d, cell: c })}
                  aria-label={`${NAMES[t.feed]} day ${d}: ${c}`}
                />
              ))}
              {alerts
                .filter((a) => a.feed === t.feed && a.kind !== "duplicates")
                .map((a) => (
                  <span
                    key={`${a.kind}-${a.hour}`}
                    className="alert-pin"
                    style={{ left: `${((a.hour / 24) / (last + 1)) * 100}%` }}
                    title={`${a.kind}: ${a.detail}`}
                  />
                ))}
            </div>
          </div>
        ))}
        <div className="tape-axis">
          <span />
          <div className="axis">
            {Array.from({ length: Math.floor(last / 7) + 1 }, (_, w) => (
              <span key={w} style={{ left: `${((w * 7) / (last + 1)) * 100}%` }}>
                week {w + 1}
              </span>
            ))}
          </div>
        </div>
        <p className="hover-line" aria-live="polite">
          {hover
            ? `${NAMES[hover.feed]}, day ${hover.day}: ${
                {
                  loaded: "loaded on schedule",
                  backfill: "loaded from the provider's redelivery",
                  quarantined: "quarantined, nothing replaced it",
                  missing: "no file",
                  off: "no delivery expected",
                }[hover.cell]
              }`
            : "Point at a day to see what happened."}
        </p>
      </div>

      <div className="two-col">
        <div>
          <h2>Alerts</h2>
          {real.length === 0 ? (
            <Empty>No alerts. Every feed arrived on time and in shape.</Empty>
          ) : (
            <ol className="alert-log">
              {real.map((a: Alert) => (
                <li key={`${a.feed}-${a.kind}-${a.hour}`}>
                  <span className="num">{clock(a.hour)}</span>
                  <span>
                    {NAMES[a.feed]} {ALERT_TEXT[a.kind] ?? a.kind}
                    <span className="muted"> ({a.detail})</span>
                  </span>
                </li>
              ))}
            </ol>
          )}
        </div>
        <div>
          <h2>Rows</h2>
          <table className="figures">
            <thead>
              <tr>
                <th>Feed</th>
                <th>Delivered</th>
                <th>Kept</th>
                <th>Repeats</th>
                <th>Backfills</th>
              </tr>
            </thead>
            <tbody>
              {feeds.map((f) => (
                <tr key={f.feed}>
                  <td>{NAMES[f.feed]}</td>
                  <td className="num">{(f.rows_delivered ?? 0).toLocaleString("en")}</td>
                  <td className="num">{(f.rows_kept ?? 0).toLocaleString("en")}</td>
                  <td className="num">{(100 * Number(f.redelivered_share ?? 0)).toFixed(1)}%</td>
                  <td className="num">{f.backfills ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted note">Repeats are rows the provider sent again; the raw layer keeps each once.</p>
        </div>
      </div>
    </section>
  );
}
