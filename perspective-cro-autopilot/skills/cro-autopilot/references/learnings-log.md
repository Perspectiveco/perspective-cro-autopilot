# State, config and the test log

All files live in `.cro-autopilot/` in the working directory. JSON for machine state, markdown for the log humans read.

## config.json

```json
{
  "trust": "review",
  "auto_approval": null,
  "auto_approved_on": null,
  "client_mode": false,
  "defaults": { "planned_days": 14, "diagnosis_days": 28, "mde_rel": 0.15, "weights": { "original": 50, "variant": 50 } },
  "funnels": [
    { "funnelId": "6a00000000000000000000a1", "name": "Webinar Landing Page", "workspaceId": "6a00000000000000000000f1",
      "isHtmlFunnel": true, "edit_mode": "mcp", "trust": null, "enrolled_at": "2026-10-21", "client": null },
    { "funnelId": "6a00000000000000000000a2", "name": "Webinar Funnel (classic)", "workspaceId": "6a00000000000000000000f1",
      "isHtmlFunnel": false, "edit_mode": "measure_only", "trust": null, "enrolled_at": "2026-10-21", "client": null }
  ]
}
```

- `trust`: `review` (ask before every start, end, ship and rollout) or `auto` (standing approval). Per-funnel `trust` overrides the default when set. Switching to `auto` requires the user's own sentence in `auto_approval`, with the date, e.g. `"Yes, start and end experiments and publish winners on the enrolled funnels without asking (2026-10-28)"`. That sentence is the standing go-ahead the publish and end tools' contracts ask for; without it, ask every time.
- `edit_mode`: `mcp` (AI/HTML funnel: experiments, edits, publishes) or `measure_only` (classic funnel: diagnose, design, read, decide; the user edits in the app). Re-derived from `isHtmlFunnel` every run.

## state/<funnelId>.json

```json
{
  "funnelId": "6a00000000000000000000a1",
  "phase": "running",
  "cycle": 3,
  "experiment": { "id": "6adf…", "title": "W43 Outcome headline", "weights": { "original": 50, "variant": 50 } },
  "hypothesis": {
    "leak": "Landing Page → page 2 loses 4,941 of 6,233 visitors (79%) in 28d",
    "diagnosis": "dwell 8s, 90% mobile: message problem",
    "change": "Outcome-first headline: 'Get your EV shortlist in 60 seconds. No sales calls.' CTA visible without scrolling on mobile.",
    "mechanism": "ab",
    "expected": "+15% relative on lead rate (12.9% → 14.8%)",
    "because": "cycle 2 proof-logo test was no difference (78%); message, not trust, is the open question",
    "inherited": false
  },
  "launched_at": "2026-10-21",
  "started_at": "2026-10-22",
  "planned_days": 14,
  "last_read": { "date": "2026-10-28", "views_a": 1890, "conv_a": 243, "views_b": 1902, "conv_b": 281,
                 "verdict": "keep_running", "chance_variant_better": 91.2, "ps_progress": 0.62, "ps_significant": false },
  "trust_used": "review",
  "editor_url": "https://app.perspective.co/funnel/6a00000000000000000000a1"
}
```

Phases: `no_test` → `draft` (experiment created, not started; review mode waits here) → `running` / `running_sequential` → `decided` → `no_test` once logged. `awaiting_manual_change` is the measure-only parking phase. `awaiting_user` marks a lean call the user has not answered. For an experiment the autopilot did not create, set `"inherited": true` and fill `change` from the user's answer or an HTML diff.

## tests.jsonl and learnings.md

`tests.jsonl` is the append-only machine log: one JSON object per decided test, written only by `scripts/log_test.py add`. `learnings.md` is regenerated from it on every add (or `log_test.py rebuild`), so it is always the complete, consistent record: a summary table of every test (date, funnel, client/industry, change, result, lift, chance the variant was better, kept version) followed by one entry per test with leak, numbers, lesson and next idea.

```bash
python3 <skill dir>/scripts/log_test.py add --dir .cro-autopilot \
  --funnel-id 6a1e… --funnel "Solar quote" --client "Sunrise Solar" --industry solar \
  --title "W43 Outcome headline" --experiment-id 6adf… \
  --leak "Landing → page 2 loses 79%, 8s dwell, 90% mobile" \
  --change "Outcome-first headline + CTA above the fold on mobile" --mechanism ab \
  --started 2026-10-22 --ended 2026-11-04 \
  --views-a 2100 --conv-a 310 --views-b 2050 --conv-b 400 \
  --verdict ship_b --chance-variant-better 99.9 --kept variant \
  --lesson "Speed + no-sales-call framing beats feature framing for this audience" \
  --next "Carry the framing into the opt-in CTA" \
  [--override "user shipped at 82% chance"] [--rolled-out-from <funnelId>] [--notes "trust: auto"]
```

Log every decided test, including no-difference ones (a "no difference" is a lesson about what does not matter) and tests ended outside the autopilot. Before designing a test, read `learnings.md`; in Client Mode also `log_test.py list --industry <industry>` for sibling evidence. Rules the log drives:

- A winner on a sibling funnel is the first thing to test on this one.
- A loser is never retested as-is; a bolder or opposite version may be.
- Two inconclusives on the same lever mean the lever doesn't matter here; move on.
- An override is recorded as the user's decision, so a later read of "what did we ship at 80%" is possible.

## reports/

`<date>-run.md` for every weekly run (template in SKILL.md). `<date>-<client>-<funnel>.md` (and `.html` when wanted) for Client Mode reports (template in `client-mode.md`).
