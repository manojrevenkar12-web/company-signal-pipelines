import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { get, post, type Pair, type ReviewResponse } from "../../shared/api";
import { Empty, Failed, Loading } from "../../shared/States";
import { useResource } from "../../shared/useResource";
import "./review.css";

const LABELS = ["mention", "partnership", "poc", "implementation", "investment", "acquisition", "none"];
const FEED: Record<string, string> = {
  vendor_profiles: "Vendor", register_notices: "Register", job_posts: "Job board", crm: "CRM",
};

function Field({ label, a, b }: { label: string; a: string; b: string }) {
  const differ = a && b && a !== b;
  return (
    <div className={`field ${differ ? "field-differ" : ""}`}>
      <span className="field-label">{label}</span>
      <span><span className="value">{a || <span className="muted">not given</span>}</span></span>
      <span><span className="value">{b || <span className="muted">not given</span>}</span></span>
    </div>
  );
}

function PairCard({ pair, onAnswer, busy }: { pair: Pair; onAnswer: (a: "same" | "different") => void; busy: boolean }) {
  return (
    <motion.article
      className="pair"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, x: -40 }}
      transition={{ duration: 0.22 }}
    >
      <div className="field field-head">
        <span className="field-label">Score {Number(pair.score).toFixed(3)}</span>
        <span>{FEED[pair.feed_a] ?? pair.feed_a}</span>
        <span>{FEED[pair.feed_b] ?? pair.feed_b}</span>
      </div>
      <Field label="Name" a={pair.names_a.join(" / ")} b={pair.names_b.join(" / ")} />
      <Field label="Domain" a={pair.domain_a ?? ""} b={pair.domain_b ?? ""} />
      <Field label="City" a={pair.city_a ?? ""} b={pair.city_b ?? ""} />
      <Field label="Founded" a={pair.founded_a ? String(pair.founded_a) : ""} b={pair.founded_b ? String(pair.founded_b) : ""} />
      <p className="muted reason">Why it is here: {pair.reason}</p>
      <div className="actions">
        <button className="btn btn-primary" disabled={busy} onClick={() => onAnswer("same")}>Same company</button>
        <button className="btn" disabled={busy} onClick={() => onAnswer("different")}>Different companies</button>
      </div>
    </motion.article>
  );
}

export function ReviewPage() {
  const res = useResource(() => get<ReviewResponse>("/review?limit=100"));
  const [reviewer, setReviewer] = useState("analyst");
  const [done, setDone] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [answered, setAnswered] = useState<Record<string, string>>({});

  if (res.state === "loading") return <Loading what="the review queues" />;
  if (res.state === "error") return <Failed what="the review queues" message={res.message} retry={res.retry} />;
  const pairs = res.data.pairs.filter((p) => !done.has(p.record_a + p.record_b));
  const articles = res.data.articles;
  const open = { pairs: res.data.totals.pairs - done.size, articles: res.data.totals.articles };

  async function answer(p: Pair, a: "same" | "different") {
    setBusy(true);
    setError(null);
    try {
      await post("/review/pairs", { record_a: p.record_a, record_b: p.record_b, answer: a }, reviewer);
      setDone(new Set(done).add(p.record_a + p.record_b));
    } catch (e) {
      setError(`Not saved: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  async function label(url: string, l: string) {
    setError(null);
    try {
      await post("/review/labels", { url, label: l }, reviewer);
      setAnswered({ ...answered, [url]: l });
    } catch (e) {
      setError(`Not saved: ${(e as Error).message}`);
    }
  }

  async function link(url: string, entity: string) {
    setError(null);
    try {
      await post("/review/links", { url, entity_id: entity }, reviewer);
      setAnswered({ ...answered, [url]: entity });
    } catch (e) {
      setError(`Not saved: ${(e as Error).message}`);
    }
  }

  return (
    <section>
      <header className="page-head">
        <h1>{open.pairs} company pairs and {open.articles} articles wait for a person</h1>
        <p className="muted">
          These are the cases code would not decide alone. Answers are saved now and applied on the next run; a
          register number or CRM id is never merged with another, whatever the answer.
        </p>
        <label className="reviewer">
          Answering as <input value={reviewer} onChange={(e) => setReviewer(e.target.value)} minLength={2} />
        </label>
      </header>
      {error && <p className="state-error" role="alert">{error}</p>}
      <div className="review-grid">
        <div>
          <h2>Is this one company?</h2>
          {pairs.length === 0 ? (
            <Empty>The pair queue is empty. New doubtful pairs appear after the next run.</Empty>
          ) : (
            <AnimatePresence mode="popLayout">
              <PairCard key={pairs[0].record_a + pairs[0].record_b} pair={pairs[0]} busy={busy}
                        onAnswer={(a) => answer(pairs[0], a)} />
            </AnimatePresence>
          )}
          {open.pairs > 1 && <p className="muted note">{open.pairs - 1} more after this one.</p>}
        </div>
        <div>
          <h2>Articles</h2>
          {articles.length === 0 ? (
            <Empty>No article needs a person.</Empty>
          ) : (
            <ul className="articles">
              {articles.slice(0, 8).map((a) => (
                <li key={a.url}>
                  <p className="article-title">{a.title}</p>
                  {a.decided_by === "review" ? (
                    <>
                      <p className="muted small">
                        Both models were unsure ({a.steps.replaceAll(">", " then ")}, last confidence{" "}
                        {Number(a.confidence).toFixed(2)}). Which relationship does it describe?
                      </p>
                      <div className="labels" role="group" aria-label="Relationship">
                        {LABELS.map((l) => (
                          <button key={l} className={`chip ${answered[a.url] === l ? "chip-on" : ""}`}
                                  onClick={() => label(a.url, l)}>
                            {l}
                          </button>
                        ))}
                      </div>
                    </>
                  ) : (
                    <>
                      <p className="muted small">
                        Labelled {a.label}, but {a.candidates.length} startups share this name. Which one is it?
                      </p>
                      <div className="labels" role="group" aria-label="Startup">
                        {a.candidates.map((c) => (
                          <button key={c.entity_id}
                                  className={`chip ${answered[a.url] === c.entity_id ? "chip-on" : ""}`}
                                  onClick={() => link(a.url, c.entity_id)}>
                            {c.name ?? c.entity_id}, {c.city ?? "?"}
                          </button>
                        ))}
                      </div>
                    </>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}
