#!/usr/bin/env python3
"""Append a decided test to the autopilot's test log and regenerate the readable log.

The machine log is .cro-autopilot/tests.jsonl (one JSON object per line, append-only).
The human log is .cro-autopilot/learnings.md, regenerated from tests.jsonl every time:
a summary table of every test ever run, then one entry per test with the lesson.
Read learnings.md before designing a test; it is what makes test N+1 smarter.

Add:
  python3 log_test.py add --dir .cro-autopilot --funnel-id 6a1e… --funnel "Solar quote" \
     --client "Sunrise Solar" --industry solar --title "Outcome headline" \
     --leak "Landing → page 2 loses 79%, 8s dwell, 90% mobile" \
     --change "Outcome-first headline + CTA above the fold on mobile" \
     --mechanism ab --started 2026-10-21 --ended 2026-11-04 \
     --views-a 2100 --conv-a 310 --views-b 2050 --conv-b 400 \
     --verdict ship_b --chance-variant-better 99.9 --kept variant \
     --lesson "Speed + no-sales-call framing beats feature framing for this audience" \
     --next "Carry the framing into the opt-in CTA" [--rolled-out-from <funnelId>] [--override "user shipped variant at 78%"]

Rebuild only:  python3 log_test.py rebuild --dir .cro-autopilot
Query:         python3 log_test.py list --dir .cro-autopilot [--funnel-id …] [--industry …]
"""
import argparse
import json
import os
import sys
from datetime import date


def load(path):
    if not os.path.exists(path):
        return []
    with open(path) as fh:
        return [json.loads(l) for l in fh if l.strip()]


def pct(conv, views):
    return f"{conv / views * 100:.1f}%" if views else "–"


def outcome_word(rec):
    v = rec.get("verdict", "")
    kept = rec.get("kept")
    if v in ("ship_b", "ship_a"):
        return f"WINNER ({'variant' if v == 'ship_b' else 'original'})"
    if v == "no_difference":
        return f"no difference (kept {kept})" if kept else "no difference"
    if v in ("keep_change", "revert", "inconclusive"):
        return v.replace("_", " ")
    if v == "invalid":
        return "invalid"
    return v or "?"


def render(records):
    lines = ["# CRO Autopilot: every test so far", "",
             "Generated from `tests.jsonl` by `log_test.py`; do not edit by hand, add tests with `log_test.py add`.",
             "Read this before designing a test. A loser is never retested as-is, a sibling's winner is the first thing to try, "
             "two inconclusives on one lever mean the lever doesn't matter here.", "",
             "| # | Ended | Funnel | Client / industry | Tested | Result | Lift | Chance variant better | Kept |",
             "|--:|---|---|---|---|---|---:|---:|---|"]
    for i, r in enumerate(records, 1):
        ra, rb = r.get("views_a", 0), r.get("views_b", 0)
        lift = ""
        if ra and rb and r.get("conv_a") is not None and r.get("conv_b") is not None:
            pa, pb = r["conv_a"] / ra, r["conv_b"] / rb
            lift = f"{(pb - pa) * 100:+.1f} pp" + (f" ({(pb - pa) / pa * 100:+.0f}%)" if pa else "")
        chance = f"{r['chance_variant_better']:.0f}%" if r.get("chance_variant_better") is not None else "–"
        who = " / ".join(x for x in [r.get("client"), r.get("industry")] if x) or "–"
        lines.append(f"| {i} | {r.get('ended', '')} | {r.get('funnel', r.get('funnel_id', ''))} | {who} | "
                     f"{r.get('change', '')} | {outcome_word(r)} | {lift} | {chance} | {r.get('kept', '') or ''} |")
    lines.append("")
    lines.append("## Entries")
    for i, r in enumerate(records, 1):
        lines += ["", f"### {i}. {r.get('ended', '')} · {r.get('funnel', '')} · {r.get('title', '')} · {outcome_word(r)}"]
        if r.get("client") or r.get("industry"):
            lines.append(f"- Client / industry: {r.get('client', '')} / {r.get('industry', '')}")
        lines.append(f"- Leak: {r.get('leak', '')}")
        lines.append(f"- Tested: {r.get('change', '')} ({r.get('mechanism', 'ab')}, {r.get('started', '?')} → {r.get('ended', '?')})")
        if r.get("views_a") or r.get("views_b"):
            lines.append(f"- Result: original {r.get('conv_a')} of {r.get('views_a')} ({pct(r.get('conv_a', 0), r.get('views_a', 0))}) vs "
                         f"variant {r.get('conv_b')} of {r.get('views_b')} ({pct(r.get('conv_b', 0), r.get('views_b', 0))}); "
                         f"verdict {r.get('verdict')}; chance variant better {r.get('chance_variant_better', '–')}%")
        if r.get("kept"):
            lines.append(f"- Kept: {r['kept']}" + (f" (override: {r['override']})" if r.get("override") else ""))
        lines.append(f"- Lesson: {r.get('lesson', '')}")
        if r.get("next"):
            lines.append(f"- Next: {r['next']}")
        if r.get("rolled_out_from"):
            lines.append(f"- Rolled out from: {r['rolled_out_from']}")
        if r.get("notes"):
            lines.append(f"- Notes: {r['notes']}")
    return "\n".join(lines) + "\n"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add")
    add.add_argument("--dir", default=".cro-autopilot")
    for name, req in [("funnel-id", True), ("funnel", True), ("title", False), ("client", False), ("industry", False),
                      ("leak", True), ("change", True), ("mechanism", False), ("started", False), ("ended", False),
                      ("verdict", True), ("kept", False), ("lesson", True), ("next", False),
                      ("rolled-out-from", False), ("override", False), ("notes", False), ("experiment-id", False)]:
        add.add_argument("--" + name, required=req)
    for name in ("views-a", "conv-a", "views-b", "conv-b"):
        add.add_argument("--" + name, type=int)
    add.add_argument("--chance-variant-better", type=float)
    rb = sub.add_parser("rebuild"); rb.add_argument("--dir", default=".cro-autopilot")
    ls = sub.add_parser("list"); ls.add_argument("--dir", default=".cro-autopilot")
    ls.add_argument("--funnel-id"); ls.add_argument("--industry"); ls.add_argument("--client")
    a = p.parse_args(argv)

    os.makedirs(a.dir, exist_ok=True)
    jl = os.path.join(a.dir, "tests.jsonl")
    records = load(jl)
    if a.cmd == "add":
        rec = {k.replace("-", "_"): v for k, v in vars(a).items() if k not in ("cmd", "dir") and v is not None}
        rec.setdefault("mechanism", "ab")
        rec.setdefault("ended", date.today().isoformat())
        rec["logged_at"] = date.today().isoformat()
        with open(jl, "a") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        records.append(rec)
        print(f"logged test #{len(records)} for {rec['funnel']}")
    elif a.cmd == "list":
        sel = [r for r in records if (not a.funnel_id or r.get("funnel_id") == a.funnel_id)
               and (not a.industry or r.get("industry") == a.industry) and (not a.client or r.get("client") == a.client)]
        print(json.dumps(sel, indent=2, ensure_ascii=False))
        return 0
    with open(os.path.join(a.dir, "learnings.md"), "w") as fh:
        fh.write(render(records))
    print(f"learnings.md rebuilt with {len(records)} tests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
