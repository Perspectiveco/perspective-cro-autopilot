#!/usr/bin/env python3
"""Tally Perspective contacts per A/B arm from saved list_contacts pages.

Usage:
  python3 tally_contacts.py --from 2026-10-06 --to 2026-10-19 \
      --variant-page-id 6a00000000000000000000b2 page0.json page1.json ...

Each file is one raw list_contacts response ({"data": [...], "meta": {...}}),
fetched newest-first (sortOrder "-1") with limit 100, saved under any name.
The script:
  * checks the pages form a contiguous run 0..N with full pages before the last
    (a missing or short page means a lost response: fix it before trusting counts),
  * de-duplicates by contact id,
  * counts contacts converted inside [from 00:00Z, to 23:59:59Z] per meta.ps_start_slug,
  * decodes the variant's creation time from its page id (first 8 hex chars = unix
    time) and tells you which slug is the original (has contacts before that time)
    and which is the variant (first seen after it),
  * refuses to emit decision inputs until you have paged back past the variant's
    creation, because the mapping cannot be trusted before that.

Pass --slug-original / --slug-variant to override the mapping (e.g. from the state).
Exit codes: 0 ok, 2 coverage or page-integrity problem (counts printed, inputs withheld).
"""
import argparse
import datetime as dt
import json
import sys
from collections import defaultdict


def decode_object_id_time(oid: str) -> str:
    return dt.datetime.fromtimestamp(int(oid[:8], 16), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("files", nargs="+")
    p.add_argument("--from", dest="date_from", required=True, help="YYYY-MM-DD inclusive, UTC")
    p.add_argument("--to", dest="date_to", required=True, help="YYYY-MM-DD inclusive, UTC")
    p.add_argument("--variant-page-id", help="variant page id from the chart's first-row key")
    p.add_argument("--variant-created-at", help="ISO time, alternative to --variant-page-id")
    p.add_argument("--slug-original")
    p.add_argument("--slug-variant")
    p.add_argument("--page-size", type=int, default=100)
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    lo, hi = a.date_from + "T00:00:00", a.date_to + "T23:59:59.999"
    problems = []

    # Load pages and check integrity.
    pages = {}
    seen, dupes, total_meta = {}, 0, None
    for f in a.files:
        with open(f) as fh:
            doc = json.load(fh)
        meta = doc.get("meta") or {}
        n = meta.get("page")
        if meta.get("total") is not None:
            total_meta = meta["total"]
        if n is None:
            problems.append(f"{f}: no meta.page; is this a list_contacts response?")
            n = f
        elif n in pages:
            problems.append(f"page {n} supplied twice ({pages[n]['file']} and {f}); using the first")
            continue
        pages[n] = {"file": f, "count": len(doc.get("data", [])), "hasNext": meta.get("hasNext")}
        for c in doc.get("data", []):
            if c["id"] in seen:
                dupes += 1
                continue
            seen[c["id"]] = c
    nums = sorted(k for k in pages if isinstance(k, int))
    if nums:
        expected = list(range(0, max(nums) + 1))
        missing = sorted(set(expected) - set(nums))
        if missing:
            problems.append(f"pages missing from the run 0..{max(nums)}: {missing} (lost or colliding spill files; re-fetch them)")
        for n in nums[:-1]:
            if pages[n]["count"] < a.page_size:
                problems.append(f"page {n} has {pages[n]['count']} contacts but is not the last page (truncated response?)")

    # Count per slug.
    in_window = defaultdict(int)
    earliest, latest, start_pages = {}, {}, defaultdict(set)
    oldest_loaded = None
    for c in seen.values():
        m = c.get("meta") or {}
        slug = m.get("ps_start_slug") or "(no slug)"
        ts = m.get("ps_converted_at") or ""
        start_pages[slug].add(m.get("ps_start_page") or "?")
        if ts:
            earliest[slug] = min(earliest.get(slug, ts), ts)
            latest[slug] = max(latest.get(slug, ts), ts)
            oldest_loaded = ts if oldest_loaded is None else min(oldest_loaded, ts)
        if lo <= ts <= hi:
            in_window[slug] += 1
    window_coverage_ok = oldest_loaded is not None and oldest_loaded <= lo
    if not window_coverage_ok:
        problems.append(f"oldest loaded contact is {oldest_loaded}; page further back past {lo}")

    # Variant creation and mapping.
    created = a.variant_created_at or (decode_object_id_time(a.variant_page_id) if a.variant_page_id else None)
    mapping_coverage_ok = None
    proposed = {}
    if created:
        mapping_coverage_ok = oldest_loaded is not None and oldest_loaded < created
        if not mapping_coverage_ok:
            problems.append(f"mapping needs contacts from before the variant was created ({created}); oldest loaded is {oldest_loaded}")
        before = [s for s in earliest if earliest[s] < created and s != "(no slug)"]
        after = [s for s in earliest if earliest[s] >= created and s != "(no slug)"]
        # Only slugs that enter on the first page matter; deeper-entry slugs are noise here.
        first_page_names = None
        if a.slug_original and a.slug_original in start_pages:
            first_page_names = start_pages[a.slug_original]
        cand_before, cand_after = list(before), list(after)
        if first_page_names:
            cand_before = [s for s in cand_before if start_pages[s] & first_page_names]
            cand_after = [s for s in cand_after if start_pages[s] & first_page_names]
        # Rank by in-window leads so a retired slug from an earlier variant (0 leads now) never wins.
        proposed = {"original_candidates": sorted(cand_before, key=lambda s: -in_window.get(s, 0)),
                    "variant_candidates": sorted(cand_after, key=lambda s: -in_window.get(s, 0))}

    slug_o = a.slug_original or (proposed.get("original_candidates") or [None])[0]
    slug_v = a.slug_variant or (proposed.get("variant_candidates") or [None])[0]

    out = {
        "window": [a.date_from, a.date_to],
        "pages_loaded": nums, "contacts_loaded": len(seen), "duplicates_skipped": dupes,
        "meta_total_reported": total_meta, "oldest_loaded_converted_at": oldest_loaded,
        "variant_created_at": created, "window_coverage_ok": window_coverage_ok,
        "mapping_coverage_ok": mapping_coverage_ok, "problems": problems,
        "per_slug": {s: {"leads_in_window": in_window.get(s, 0), "start_page": sorted(start_pages[s]),
                         "earliest_loaded": earliest.get(s), "latest_loaded": latest.get(s),
                         "has_contacts_before_variant_created": (earliest.get(s) < created) if created and earliest.get(s) else None}
                     for s in sorted(set(list(in_window) + list(earliest)), key=lambda s: -in_window.get(s, 0))},
        "proposed_mapping": {"original": slug_o, "variant": slug_v, **proposed},
    }
    if created and mapping_coverage_ok and (not slug_o or not slug_v):
        problems.append("could not identify both arms from the contacts; pass --slug-original and --slug-variant")
    ok = not problems
    if ok and slug_o and slug_v:
        out["for_ab_decision"] = {"conv_a": in_window.get(slug_o, 0), "conv_b": in_window.get(slug_v, 0),
                                  "slug_original": slug_o, "slug_variant": slug_v}

    if a.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"Window {a.date_from}..{a.date_to}: pages {nums[0] if nums else '?'}..{nums[-1] if nums else '?'} "
              f"({len(nums)} files), {len(seen)} contacts ({dupes} duplicates skipped), meta.total={total_meta}")
        print(f"Oldest loaded: {oldest_loaded}   Variant created: {created or 'unknown (pass --variant-page-id)'}")
        print()
        print("| start slug | start page | leads in window | earliest loaded | before variant created? |")
        print("|---|---|---:|---|---|")
        for s, v in out["per_slug"].items():
            flag = {True: "yes", False: "no", None: "?"}[v["has_contacts_before_variant_created"]]
            print(f"| {s} | {', '.join(v['start_page'])} | {v['leads_in_window']} | {v['earliest_loaded']} | {flag} |")
        print()
        print(f"Proposed mapping: original = {slug_o}, variant = {slug_v}")
        if problems:
            print("\nPROBLEMS (decision inputs withheld):")
            for pr in problems:
                print(" -", pr)
        elif "for_ab_decision" in out:
            d = out["for_ab_decision"]
            print(f"\nab_decision inputs: --conv-a {d['conv_a']} --conv-b {d['conv_b']}")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
