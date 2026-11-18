"""signals: operate the pipelines.

    signals migrate                  apply numbered SQL migrations
    signals redact --days 30         remove personal fields from raw rows older than the retention window
    signals review-queue             print the open review items
    signals classify FILE.json       classify articles with Claude (needs ANTHROPIC_API_KEY)
"""

from __future__ import annotations

import argparse
import json
import sys

from signals import db
from signals.config import design, settings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="signals")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    r = sub.add_parser("redact")
    r.add_argument("--days", type=int, default=int(settings()["privacy"]["raw_retention_days"]))
    sub.add_parser("review-queue")
    c = sub.add_parser("classify")
    c.add_argument("file")
    args = ap.parse_args(argv)
    if args.cmd == "migrate":
        print("applied:", db.migrate(db.connect()) or "nothing new")
    elif args.cmd == "redact":
        row = db.connect().execute("select raw.redact_personal(%s)", (args.days,)).fetchone()
        n = row[0] if row else 0
        print(f"redacted personal fields in {n} raw rows older than {args.days} days")
    elif args.cmd == "review-queue":
        conn = db.connect()
        for row in conn.execute("select record_a, record_b, score, reason from core.review_pair order by score desc"):
            print(*row, sep="\t")
    elif args.cmd == "classify":
        from signals.classify.cascade import classify
        from signals.classify.claude import ClaudeModel

        articles = json.loads(open(args.file).read())
        cheap, expensive = ClaudeModel("cheap"), ClaudeModel("expensive")
        for a in articles:
            d = classify(a, design(), settings(), cheap, expensive)
            print(json.dumps(d.__dict__))
    return 0


if __name__ == "__main__":
    sys.exit(main())
