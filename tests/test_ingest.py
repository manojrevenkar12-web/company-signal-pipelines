from signals.config import design
from signals.ingest.lake import MemoryLake
from signals.ingest.runner import Ingestor, run_ingest


class Fixed:
    """A feed that delivers the same rows every day except the days it is told to skip or reshape."""

    def __init__(self, rows, stop=(), drift=(), thin=()):
        self.rows, self.stop, self.drift, self.thin = rows, set(stop), set(drift), set(thin)

    def fetch(self, feed, day):
        if feed != "news_mentions":
            return None if feed != "job_posts" or day % 7 else []
        if day in self.stop:
            return None
        rows = [dict(r, url=f"{r['url']}-{day}") for r in self.rows]
        if day in self.thin:
            rows = rows[:2]
        if day in self.drift:
            rows = [{("body" if k == "text" else k): v for k, v in r.items()} for r in rows]
        return rows

    def backfill(self, feed, day, today):
        if feed != "news_mentions":
            return None
        return [dict(r, url=f"{r['url']}-{day}") for r in self.rows]


ROWS = [{"url": f"u{i}", "published_on": "2026-06-01", "language": "en", "title": "t", "text": "x"}
        for i in range(30)]


def test_a_redelivered_row_adds_nothing():
    lake = MemoryLake()
    run = lake.load("news_mentions", "url", 0, ROWS, "scheduled", 6, idempotent=True)
    again = lake.load("news_mentions", "url", 0, ROWS, "backfill", 30, idempotent=True)
    assert (run.new, again.new) == (30, 0)
    assert len(lake.rows("news_mentions")) == 30
    lake.load("news_mentions", "url", 0, ROWS, "backfill", 31, idempotent=False)
    assert len(lake.rows("news_mentions")) == 60


def test_a_stopped_feed_alerts_within_its_sla_and_is_backfilled():
    res = run_ingest(Fixed(ROWS, stop={12, 13}), MemoryLake(), 20, design())
    fresh = [a for a in res.alerts if a.kind == "freshness" and a.feed == "news_mentions"]
    assert fresh and fresh[0].hour - (12 * 24 + 6) == 7       # last load day 11 06:00, SLA 30 h
    assert res.backfilled_days["news_mentions"] == [12, 13]
    assert res.missing_days["news_mentions"] == []


def test_a_renamed_field_is_quarantined_then_redelivered():
    lake = MemoryLake()
    res = run_ingest(Fixed(ROWS, drift={10}), lake, 14, design())
    assert any(a.kind == "schema" and a.day == 10 for a in res.alerts)
    assert all("text" in r.payload for r in lake.rows("news_mentions"))
    assert 10 in res.backfilled_days["news_mentions"]


def test_a_thin_delivery_raises_a_volume_alert():
    res = run_ingest(Fixed(ROWS, thin={15}), MemoryLake(), 17, design())
    assert [a.day for a in res.alerts if a.kind == "volume"] == [15]


def test_without_monitors_a_stop_is_seen_at_the_weekly_look():
    d = design({"monitors": False, "backfill": False})
    res = run_ingest(Fixed(ROWS, stop={8}), MemoryLake(), 16, d)
    looks = [a for a in res.alerts if a.feed == "news_mentions"]
    assert [a.kind for a in looks] == ["weekly_look"] and looks[0].hour == 14 * 24 + 9


def test_the_ingestor_resumes_from_stored_state():
    lake = MemoryLake()
    a = Ingestor(Fixed(ROWS, stop={5}), lake, design())
    for d in range(4):
        a.day(d)
    b = Ingestor(Fixed(ROWS, stop={5}), lake, design(), a.to_state())
    for d in range(4, 9):
        b.day(d)
    whole = run_ingest(Fixed(ROWS, stop={5}), MemoryLake(), 9, design())
    assert [(x.kind, x.hour) for x in b.result().alerts] == [(x.kind, x.hour) for x in whole.alerts]
