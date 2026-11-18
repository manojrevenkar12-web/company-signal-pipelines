const BASE = import.meta.env.VITE_API ?? "/api";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function get<T>(path: string): Promise<T> {
  const r = await fetch(BASE + path);
  if (!r.ok) throw new ApiError(r.status, (await r.text()) || r.statusText);
  return (await r.json()) as T;
}

export async function post<T>(path: string, body: unknown, reviewer: string): Promise<T> {
  const r = await fetch(BASE + path, {
    method: "POST",
    headers: { "content-type": "application/json", "x-reviewer": reviewer },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new ApiError(r.status, (await r.text()) || r.statusText);
  return (await r.json()) as T;
}

export type Feed = {
  feed: string; description: string; sla_hours: number; cadence_days: number; loads?: number;
  quarantined?: number; backfills?: number; rows_delivered?: number; rows_kept?: number; alerts?: number;
  redelivered_share?: string;
};
export type Alert = { feed: string; kind: string; hour: number; day: number; detail: string };
export type Run = { feed: string; delivery_day: number; kind: string; status: string; rows: number; new_rows: number };
export type FeedsResponse = { feeds: Feed[]; alerts: Alert[]; runs: Run[] };

export type Pair = {
  record_a: string; record_b: string; score: string; reason: string;
  feed_a: string; names_a: string[]; domain_a: string | null; city_a: string | null; founded_a: number | null;
  feed_b: string; names_b: string[]; domain_b: string | null; city_b: string | null; founded_b: number | null;
};
export type Candidate = { entity_id: string; name: string | null; city: string | null; country: string | null };
export type ReviewArticle = {
  url: string; title: string; label: string; confidence: string; steps: string; link_status: string;
  decided_by: string; candidates: Candidate[];
};
export type ReviewResponse = { pairs: Pair[]; articles: ReviewArticle[]; totals: { pairs: number; articles: number } };

export type Signal = {
  event_id: string; entity_id: string; name: string | null; domain: string | null; kind: string; event_date: string;
  source_count: number; sources: string[]; first_seen: string; days_until_known: number;
};
export type Column = { table_name: string; column_name: string; data_type: string; description: string | null };
