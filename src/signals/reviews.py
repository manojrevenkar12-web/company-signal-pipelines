"""The review queues' answers as stored by people in ops.review_decision. A question nobody answered yet returns
None and stays in the queue."""

from __future__ import annotations

from typing import Any


class StoredDecisions:
    def __init__(self, conn: Any):
        rows = conn.execute("select kind, subject, answer from ops.review_decision").fetchall()
        self.answers = {(k, s): a for k, s, a in rows}

    def same_company(self, a: str, b: str) -> bool | None:
        ans = self.answers.get(("pair", f"{a}|{b}"))
        return None if ans is None else ans == "same"

    def relationship(self, url: str) -> str | None:
        return self.answers.get(("label", url))

    def which_company(self, url: str, candidates: dict[str, list[str]]) -> str | None:
        ans = self.answers.get(("link", url))
        return ans if ans in candidates else None
