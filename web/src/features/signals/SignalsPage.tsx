import { useState } from "react";
import { get, type Signal } from "../../shared/api";
import { Empty, Failed, Loading } from "../../shared/States";
import { useResource } from "../../shared/useResource";
import "./signals.css";

const KINDS = [
  ["", "All"], ["funding", "Funding"], ["acquisition", "Acquisitions"], ["shutdown", "Shutdowns"],
  ["headcount", "Hiring changes"],
] as const;
const SOURCE: Record<string, string> = {
  vendor_profiles: "vendor", register_notices: "register", news_mentions: "press", job_posts: "job boards",
};

export function SignalsPage() {
  const [kind, setKind] = useState("");
  const res = useResource(() => get<Signal[]>(`/signals?limit=200${kind ? `&kind=${kind}` : ""}`), [kind]);
  return (
    <section>
      <header className="page-head">
        <h1>Signals, dated by the evidence</h1>
        <p className="muted">
          Each signal carries the date its evidence states, a contract date in a register notice or the day a round
          was announced, and how long it took the market to tell us.
        </p>
        <div className="tabs" role="tablist">
          {KINDS.map(([k, label]) => (
            <button key={k} role="tab" aria-selected={kind === k} className={`tab ${kind === k ? "tab-on" : ""}`}
                    onClick={() => setKind(k)}>
              {label}
            </button>
          ))}
        </div>
      </header>
      {res.state === "loading" && <Loading what="signals" />}
      {res.state === "error" && <Failed what="signals" message={res.message} retry={res.retry} />}
      {res.state === "ready" && res.data.length === 0 && (
        <Empty>No {kind || ""} signals yet. They appear once evidence from any feed arrives.</Empty>
      )}
      {res.state === "ready" && res.data.length > 0 && (
        <table className="signals">
          <thead>
            <tr><th>Date</th><th>Company</th><th>Signal</th><th>Evidence</th><th>Known after</th></tr>
          </thead>
          <tbody>
            {res.data.map((s) => (
              <tr key={s.event_id}>
                <td className="num">{s.event_date}</td>
                <td>{s.name ?? s.domain ?? s.entity_id}</td>
                <td>{s.kind === "headcount" ? "hiring change" : s.kind}</td>
                <td className="muted">{s.sources.map((x) => SOURCE[x] ?? x).join(", ")}</td>
                <td>
                  <span className="lag">
                    <span className="lag-bar" style={{ width: `${Math.min(100, (s.days_until_known / 45) * 100)}%` }} />
                    <span className="num">{s.days_until_known} d</span>
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
