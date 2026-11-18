"""Writes the results section of README.md and the charts in docs/charts from reports/*.json. Never edit those
numbers by hand: run `make report`."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
INK, MUTED, ACCENT, BAD, GRID = "#1d2433", "#6b7385", "#0b6e4f", "#b4442c", "#e4e7ec"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": MUTED,
                     "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": INK, "svg.fonttype": "none"})


def v(row: dict[str, Any], k: str) -> float:
    x = row[k]
    if "rate" in x:
        return float(x["rate"])
    return float("inf") if x["mean"] is None else float(x["mean"])


def ci(row: dict[str, Any], k: str, digits: int = 3, pct: bool = True) -> str:
    x = row[k]
    if "rate" in x:
        if x["n"] == 0:
            return "–"
        f = (lambda y: f"{100 * y:.1f}%") if pct else (lambda y: f"{y:.{digits}f}")
        return f"{f(x['rate'])} ({f(x['low'])}–{f(x['high'])})"
    if x["mean"] is None:
        return "not detected"
    if x.get("ci") and x["ci"][1] != x["ci"][2]:
        return f"{x['mean']:.{digits}f} (±{(x['ci'][2] - x['ci'][1]) / 2:.{digits}f})"
    return f"{x['mean']:.{digits}f}"


def hours(row: dict[str, Any]) -> str:
    x = row["max_hours_to_detect_outage"]
    return "an outage missed" if x["mean"] is None else f"{x['mean']:.0f} h"


def table(head: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def chart_designs(d: dict[str, Any], path: Path) -> None:
    names = ["status_quo", "cheap_model_alone", "model_alone", "platform"]
    labels = ["Status quo", "Small model alone", "Large model alone", "Platform"]
    panels = [("er_pair_precision", "Entity-resolution precision", "%"),
              ("rel_precision", "Relationship-label precision", "%"),
              ("rel_cost_per_record_eur", "Classification cost per article", "€"),
              ("event_date_mae_days", "Signal date error", "days")]
    fig, axes = plt.subplots(1, 4, figsize=(12, 2.8))
    for ax, (k, title, unit) in zip(axes, panels):
        vals = [v(d[n], k) for n in names]
        colors = [ACCENT if n == "platform" else "#9aa3b2" for n in names]
        ax.barh(range(len(names)), [0 if not math.isfinite(x) else x for x in vals], color=colors, height=0.6)
        for i, x in enumerate(vals):
            txt = f"{100 * x:.1f}%" if unit == "%" else (f"€{x:.4f}" if unit == "€" else f"{x:.1f} d")
            ax.text(x, i, " " + txt, va="center", fontsize=9, color=INK)
        ax.set_yticks(range(len(names)), labels if ax is axes[0] else [""] * len(names))
        ax.invert_yaxis()
        ax.set_title(title, fontsize=10, color=INK, loc="left")
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_xticks([])
        if unit == "%":
            ax.set_xlim(0, 1.25)
        else:
            ax.set_xlim(0, max(x for x in vals if math.isfinite(x)) * 1.45)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def chart_cost_precision(d: dict[str, Any], path: Path) -> None:
    pts = [("status_quo", "Keyword rules"), ("cheap_model_alone", "Small model"), ("model_alone", "Large model"),
           ("no_rules", "Cascade without rules"), ("no_review", "Cascade without review"),
           ("platform", "Cascade (platform)")]
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    for n, label in pts:
        x, y = 1000 * v(d[n], "rel_cost_per_record_eur"), 100 * v(d[n], "rel_precision")
        lo, hi = 100 * d[n]["rel_precision"]["low"], 100 * d[n]["rel_precision"]["high"]
        c = ACCENT if n == "platform" else INK
        ax.errorbar([x], [y], yerr=[[y - lo], [hi - y]], fmt="o", color=c, ms=6, capsize=3)
        ax.annotate(label, (x, y), xytext=(6, -3), textcoords="offset points", fontsize=9, color=c)
    ax.axvline(4.0, color=BAD, lw=1, ls="--")
    ax.set_xlim(-0.2, 5.6)
    ax.text(4.05, ax.get_ylim()[0] + 0.3, "cost gate €4 per 1,000", color=BAD, fontsize=8)
    ax.axhline(90, color=BAD, lw=1, ls="--")
    ax.set_xlabel("€ per 1,000 articles")
    ax.set_ylabel("precision of accepted labels, %")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color=GRID)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def chart_outages(d: dict[str, Any], path: Path) -> None:
    feeds = ["vendor_profiles", "register_notices", "news_mentions", "job_posts"]
    plat, sq = d["platform"]["outages"][0], d["status_quo"]["outages"][0]
    fig, ax = plt.subplots(figsize=(9, 2.6))
    for i, f in enumerate(feeds):
        for o, s in zip(plat, sq):
            if o["feed"] != f:
                continue
            ax.broken_barh([(o["start_day"], o["days"])], (i - 0.3, 0.6), color="#f1d5ce")
            ax.text(o["start_day"] + o["days"] + 0.6, i, f"{o['kind']}: platform {o['hours_to_detect']} h, "
                    f"status quo {'never' if s['hours_to_detect'] is None else str(s['hours_to_detect']) + ' h'}",
                    va="center", fontsize=8.5, color=INK)
    ax.set_yticks(range(len(feeds)), [f.replace("_", " ") for f in feeds])
    ax.set_xlim(0, 112)
    ax.set_xlabel("day of the dev run (seed 11); shaded: outage")
    ax.invert_yaxis()
    ax.spines[["top", "right", "left"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def section(dev: dict[str, Any], held: dict[str, Any] | None) -> str:
    d = dev["designs"]
    p = d["platform"]
    out = [f"Generated by `make report` from `reports/dev.json` (dev seeds {', '.join(map(str, dev['seeds']))}, "
           f"pooled; 95% intervals in brackets)" + (" and `reports/heldout.json` (held-out world, run once)." if held
                                                    else ". The held-out world has not been run yet.")]
    gate_rows = []
    hg = {g["gate"]: g for g in held["gates"]} if held else {}
    for g in dev["gates"]:
        def fmt(x: dict[str, Any]) -> str:
            val = x["value"]
            if val is None or (isinstance(val, float) and not math.isfinite(val)):
                return "never"
            if x["metric"] in ("rel_cost_per_record_eur",):
                return f"€{val:.5f}"
            if x["metric"] in ("max_hours_to_detect_outage",):
                return f"{val:.0f} h"
            if x["metric"] in ("event_date_mae_days",):
                return f"{val:.1f} d"
            if x["metric"] in ("gone_recommended",):
                return f"{val:.1f}"
            return f"{100 * val:.2f}%"
        h = hg.get(g["gate"])
        gate_rows.append([g["gate"].replace("_", " "), f"{'≥' if g['direction'] == 'min' else '≤'} {g['threshold']}",
                          f"{fmt(g)} {'✅' if g['passed'] else '❌'}",
                          (f"{fmt(h)} {'✅' if h['passed'] else '❌'}") if h else "not run"])
    out += ["", "### Release gates (platform; rates judged on the worse end of the interval)", "",
            table(["gate", "threshold", "dev", "held-out"], gate_rows)]
    out += ["", "![Designs on the same luck](docs/charts/designs.svg)", ""]
    head = ["design", "ER precision", "ER recall", "label precision", "€ / 1k articles", "signal date error",
            "gone still recommended", "worst outage detection"]
    rows = []
    for name in ("status_quo", "cheap_model_alone", "model_alone", "platform"):
        r = d[name]
        rows.append([r["label"].split(":")[0], ci(r, "er_pair_precision"), ci(r, "er_pair_recall"),
                     ci(r, "rel_precision"), f"€{1000 * v(r, 'rel_cost_per_record_eur'):.2f}",
                     f"{v(r, 'event_date_mae_days'):.1f} d", f"{v(r, 'gone_recommended'):.1f}", hours(r)])
    out += ["### Designs on the same luck (dev)", "", table(head, rows), "",
            "The two model-alone designs change only the classification step; everything else is the platform."]
    abl = []
    for name, r in d.items():
        if name in ("status_quo", "cheap_model_alone", "model_alone", "platform"):
            continue
        abl.append([r["label"].replace("Platform ", ""), ci(r, "er_pair_recall"), ci(r, "rel_precision"),
                    f"€{1000 * v(r, 'rel_cost_per_record_eur'):.2f}", ci(r, "event_precision"),
                    ci(r, "event_recall"), f"{v(r, 'event_date_mae_days'):.1f} d", f"{v(r, 'gone_recommended'):.1f}"])
    out += ["", "### Ablations: the platform with one part removed (dev)", "",
            table(["removed", "ER recall", "label precision", "€ / 1k", "signal precision", "signal recall",
                   "date error", "gone recommended"],
                  [["nothing (platform)", ci(p, "er_pair_recall"), ci(p, "rel_precision"),
                    f"€{1000 * v(p, 'rel_cost_per_record_eur'):.2f}", ci(p, "event_precision"),
                    ci(p, "event_recall"), f"{v(p, 'event_date_mae_days'):.1f} d",
                    f"{v(p, 'gone_recommended'):.1f}"]] + abl)]
    out += ["", "![Cost against precision](docs/charts/cost_precision.svg)", ""]
    outs = []
    for o, s in zip(p["outages"][0], d["status_quo"]["outages"][0]):
        outs.append([o["feed"].replace("_", " "), o["kind"], f"day {o['start_day']}, {o['days']} d",
                     f"{o['hours_to_detect']} h by {o['by']}",
                     "never" if s["hours_to_detect"] is None else f"{s['hours_to_detect']} h (weekly look)"])
    out += ["### Feed outages (dev seed 11)", "", table(["feed", "kind", "when", "platform", "status quo"], outs),
            "", f"False alerts over three 84-day runs: {sum(p['false_alerts']['per_seed']):.0f}. "
                f"Rows kept after backfills: " + ", ".join(f"{k.replace('_', ' ')} {100 * x:.1f}%"
                                                         for k, x in p["completeness"].items())
            + f". Duplicate raw rows: platform {v(p, 'raw_duplicates'):.0f}, status quo "
              f"{v(d['status_quo'], 'raw_duplicates'):.0f} per run.",
            "", "![Outages](docs/charts/outages.svg)", ""]
    ven = [[x["feed"].replace("_", " "), f"{x['records_billed']:,}", f"€{x['spend_eur']:.2f}", f"{x['companies']:,}",
            f"{x['only_here']:,}", f"{x['correct_datapoints']:,}",
            f"€{x['eur_per_correct_datapoint']:.4f}" if x["eur_per_correct_datapoint"] else "–"] for x in p["vendors"]]
    out += ["### What each feed costs per correct datapoint (dev seed 11)", "",
            table(["feed", "records billed", "spend", "companies", "only in this feed", "correct datapoints",
                   "€ per correct datapoint"], ven)]
    s = p["search"]
    out += ["", "### Company search (dev, " + f"{s['fuzzy']['recall_at_1']['n']} queries written the way the press "
            "writes names)", "",
            table(["method", "right company first", "right company in top 5"],
                  [[m, ci({"x": s[m]["recall_at_1"]}, "x"), ci({"x": s[m]["recall_at_5"]}, "x")]
                   for m in ("exact", "normalised", "fuzzy")])]
    ri = p["review_items"]
    out += ["", f"People in the loop per 84-day run: {ri['pairs']:.0f} doubtful company pairs, "
                f"{ri['articles']:.0f} relationship labels and {ri['links']:.0f} articles whose startup could be "
                f"one of up to five companies. Golden-record field accuracy: "
            + ", ".join(f"{k} {100 * x:.1f}%" for k, x in p["golden_accuracy"].items()) + "."]
    if held:
        hp = held["designs"]["platform"]
        hs = held["designs"]["status_quo"]
        out += ["", "### Held-out world (run once)", "",
                "Different seed, more typos and rebrands, a third more vague and German wording, 30% of clear "
                "wording in phrasings no rule was written for, and a different outage plan.", "",
                table(["design", "ER precision", "ER recall", "label precision", "€ / 1k", "signal precision",
                       "signal recall", "date error", "gone recommended", "worst detection"],
                      [[r["label"].split(":")[0], ci(r, "er_pair_precision"), ci(r, "er_pair_recall"),
                        ci(r, "rel_precision"), f"€{1000 * v(r, 'rel_cost_per_record_eur'):.2f}",
                        ci(r, "event_precision"), ci(r, "event_recall"), f"{v(r, 'event_date_mae_days'):.1f} d",
                        f"{v(r, 'gone_recommended'):.0f}", hours(r)]
                       for r in (hs, held["designs"]["model_alone"], hp)])]
        hout = [[o["feed"].replace("_", " "), o["kind"], f"day {o['start_day']}, {o['days']} d",
                 "missed" if o["hours_to_detect"] is None else f"{o['hours_to_detect']} h by {o['by']}"]
                for o in hp["outages"][0]]
        out += ["", table(["feed", "kind", "when", "platform"], hout)]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    import sys

    args = sys.argv[1:] if argv is None else argv
    dev = json.loads((ROOT / "reports" / "dev.json").read_text())
    hp = ROOT / "reports" / "heldout.json"
    held = json.loads(hp.read_text()) if hp.exists() else None
    readme = (ROOT / "README.md").read_text()
    a, b = readme.index("<!-- results:start -->"), readme.index("<!-- results:end -->")
    fresh = readme[:a] + "<!-- results:start -->\n" + section(dev, held) + "\n" + readme[b:]
    if "--check" in args:
        if fresh != readme:
            print("README results are stale: run `make report`")
            return 1
        print("README results match the reports")
        return 0
    charts = ROOT / "docs" / "charts"
    charts.mkdir(parents=True, exist_ok=True)
    chart_designs(dev["designs"], charts / "designs.svg")
    chart_cost_precision(dev["designs"], charts / "cost_precision.svg")
    chart_outages(dev["designs"], charts / "outages.svg")
    (ROOT / "README.md").write_text(fresh)
    print("README results and charts written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
