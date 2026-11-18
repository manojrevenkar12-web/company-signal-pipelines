from datetime import date

from signals.config import design, settings
from signals.events.detect import Evidence, dark_evidence, headcount_evidence, merge, register_evidence
from signals.golden import Observation, golden
from signals.ingest.lake import RawRow

START = date(2026, 6, 1)


def test_a_register_notice_is_dated_by_the_contract_it_quotes():
    row = RawRow("register_notices", "HR-1", "h", {
        "court": "Amtsgericht Köln", "register_no": "HRB 1", "kind": "verschmelzung",
        "text": "Verschmelzung. Die Gesellschaft Nova GmbH ist auf Grund des Verschmelzungsvertrages vom "
                "03.06.2026 mit der Elbtal AG verschmolzen."}, 30, 30 * 24 + 6, 1)
    ev = register_evidence([row], {"register_notices:Amtsgericht Köln|HRB 1": "E1"}, START)
    assert ev[0].stated == date(2026, 6, 3) and ev[0].seen == date(2026, 7, 1)
    assert merge(ev, design(), settings())[0].on == date(2026, 6, 3)
    assert merge(ev, design({"event_dates": "ingestion"}), settings())[0].on == date(2026, 7, 1)


def test_evidence_from_several_sources_is_one_event():
    ev = [Evidence("E1", "acquisition", date(2026, 6, 3), date(2026, 6, 4), "news_mentions", "u"),
          Evidence("E1", "acquisition", date(2026, 6, 3), date(2026, 7, 1), "register_notices", "n"),
          Evidence("E1", "acquisition", None, date(2026, 7, 3), "vendor_profiles", "s")]
    events = merge(ev, design(), settings())
    assert len(events) == 1 and events[0].sources == ["news_mentions", "register_notices", "vendor_profiles"]
    assert len(merge(ev, design({"dedupe_events": False}), settings())) == 3


def test_a_missing_week_is_unknown_not_zero():
    series = {"E1": {w: 20 for w in range(12) if w not in (5, 6)}}
    assert headcount_evidence(series, 12, START, design(), settings(), {5, 6}) == []
    zero = headcount_evidence(series, 12, START, design({"missing_weeks": "zero"}), settings(), {5, 6})
    assert len(zero) == 1


def test_a_company_gone_from_the_jobs_feed_is_a_shutdown_signal():
    series = {"E1": {w: 5 for w in range(8)}, "E2": {w: 5 for w in range(12)}}
    ev = dark_evidence(series, 12, START, settings(), set())
    assert [(e.entity, e.kind, e.stated) for e in ev] == [("E1", "shutdown", date(2026, 7, 27))]
    assert dark_evidence(series, 12, START, settings(), {9, 10, 11}) == []   # the feed was down, not the company


def test_a_terminal_status_beats_a_fresher_active():
    obs = [Observation("E1", "status", "active", "vendor_profiles", date(2026, 8, 20)),
           Observation("E1", "status", "acquired", "news_mentions", date(2026, 8, 1)),
           Observation("E1", "name", "Old Name", "vendor_profiles", date(2026, 8, 20)),
           Observation("E1", "name", "New Name GmbH", "register_notices", date(2026, 7, 1))]
    g = golden(obs, design(), settings(), date(2026, 8, 24))["E1"]
    assert g["status"].value == "acquired" and g["name"].value == "New Name GmbH"
    lw = golden(obs, design({"provenance": "last_write"}), settings(), date(2026, 8, 24))["E1"]
    assert lw["status"].value == "active" and lw["name"].value == "Old Name"
