import { useEffect, useState } from "react";
import { DictionaryPage } from "./features/dictionary/DictionaryPage";
import { FeedsPage } from "./features/feeds/FeedsPage";
import { ReviewPage } from "./features/review/ReviewPage";
import { SignalsPage } from "./features/signals/SignalsPage";
import "./app.css";

const PAGES = [
  ["feeds", "Feed health", FeedsPage],
  ["review", "Review queue", ReviewPage],
  ["signals", "Signals", SignalsPage],
  ["dictionary", "Data dictionary", DictionaryPage],
] as const;

type Page = (typeof PAGES)[number][0];

function current(): Page {
  const h = window.location.hash.replace("#", "");
  return (PAGES.find(([k]) => k === h)?.[0] ?? "feeds") as Page;
}

export function App() {
  const [page, setPage] = useState<Page>(current());
  useEffect(() => {
    const on = () => setPage(current());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const View = PAGES.find(([k]) => k === page)![2];
  return (
    <div className="shell">
      <nav className="rail" aria-label="Sections">
        <p className="brand">Signal pipelines</p>
        {PAGES.map(([k, label]) => (
          <a key={k} href={`#${k}`} aria-current={page === k ? "page" : undefined}>{label}</a>
        ))}
        <p className="rail-foot muted">Vendor, register, press and job-board feeds into one company record.</p>
      </nav>
      <main className="main">
        <View />
      </main>
    </div>
  );
}
