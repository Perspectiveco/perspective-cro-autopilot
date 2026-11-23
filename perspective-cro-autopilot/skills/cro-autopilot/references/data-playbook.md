# Data playbook: pulling and reading Perspective metrics

Every number in a run comes from these calls. Chart, KPI, funnel and contact shapes were captured from the live MCP in October 2026 and verified in two dry runs; the experiment tools arrived after that and their shapes are taken from the tools' own documentation. If a response looks different, trust the response and update this file.

## Discovery and eligibility

- `list_workspaces` → `{ data: [{ id, name }] }`
- `list_funnels { workspaceId, status?: "live", limit, page }` → `{ data: [{ id, name, status, isArchived, isHtmlFunnel }], meta: { count, totalCount, pageCount } }`
- **Eligibility gate, every run, before anything else:** a funnel is `edit_mode: "mcp"` only if `status: "live"` and `isHtmlFunnel: true`. A classic funnel (`isHtmlFunnel: false`) can be *measured* (charts, KPIs and contacts work) but every HTML and experiment tool returns `FUNNEL_NOT_FOUND`. Enroll classic funnels as `edit_mode: "measure_only"`: you diagnose, design, read and decide; the user makes the change and ends the test in the app.
- The metric subtypes are in the tool schemas; you do not need `list_available_metrics` in the loop.

## Windows

All metric calls take `from` / `to` as ISO 8601 and an optional `offset` (timezone, minutes). Use complete days: `from: YYYY-MM-DDT00:00:00.000Z`, `to: YYYY-MM-DDT23:59:59.000Z`. Today is never complete; end windows on yesterday. `elapsed_days` = number of complete days inside the window (from `started_at` through yesterday, inclusive).

Defaults: diagnosis = last 28 complete days (90 if under ~200 sessions a week); test read = `started_at` through yesterday; before/after = the N planned days after the change vs the N days immediately before.

## Experiments (AI/HTML funnels): the primary read

Perspective calls A/B tests experiments. On an `isHtmlFunnel: true` funnel use these; they replace all chart and contact arithmetic for the per-version numbers.

- `get_experiment { funnelId }` → `{ data: null, message }` when there is none (a normal answer, also right after an experiment ends), else the current experiment: `{ id, title, status: "draft" | "running", startedAt? (ISO, present once running), arms: [ { id, role: "control" | "challenger", version: "original" | "variant", weight, draftId } ] }`. With `experimentId` it returns a past one too, adding `endedAt` and `winnerArmId` (the arm `id` that was kept). Verified in testing. Call it at the start of every run and before any edit or publish.
- `list_experiments { funnelId, status? }` → `{ data: [ { id, title, status, startedAt?, endedAt?, winnerArmId? } ] }` newest first, any status (`draft`, `running`, `concluded`, `aborted`); `data: []` means never tested (verified). Use it to reconstruct history and to read an experiment that was ended in the app (`get_experiment_results` with its `experimentId`).
- `create_experiment { funnelId, title, hypothesis, weights? }` → `{ data: <experiment as above, status draft>, jobId, message }` (verified). Poll `get_funnel_job_status` with the `jobId`; on this build its `nextStep.kind` came back as the ordinary `offer_next_step`, not the documented `review_ab_test_edit`, so ignore its publish offer and follow this skill. The job `summary` describes the variant; verified in testing that a headline-only hypothesis produced a headline-only variant (confirmed by reading `get_funnel_html version: "variant"`). The AI writes the variant from the hypothesis; the original is untouched. If the AI job could not start, the variant is an exact copy and `message` says how to retry (`update_funnel version: "variant"`). Errors: `FUNNEL_GENERATION_IN_PROGRESS` (wait), `EXPERIMENT_ALREADY_EXISTS` (read it with `get_experiment`).
- `publish_funnel` starts a draft experiment. On success it returned `{ data: { funnelId, liveUrl, experiment: { id, status: "running", arms: [ { version, weight } ] } } }` and the live URL served one of the two versions (verified). The first call answers `{ errorType: "EXPERIMENT_START_NOT_CONFIRMED", experiment: { id, title, arms: [ { version, weight } ] }, hint, message }` (verified); resend with `confirmStartExperiment: true` under the trust rules. On success it returns `{ funnelId, liveUrl, experiment? }` plus a text block saying Started / Refreshed / Not started (the user's role may not be allowed to start tests); relay it. Any publish of the funnel starts the draft, so never publish for another reason without saying so. An edit to a running experiment's version or a new split reaches visitors only at the next publish.
- `update_experiment { funnelId, title?, weights? }` renames or re-splits a draft or running experiment and returns the full experiment (same shape as `get_experiment`). A new split on a running one is saved but applies only at the next publish; the response carried no note about that in testing, so say it yourself.
- `get_experiment_results { funnelId, experimentId? }` → per version: `sessions`, `conversions`, conversion rate, traffic weight, over `range` (lifetime so far); `significance: { progress, isSignificant, leadingVersion, visitorsNeeded }`; a one-sentence `message` to pass on verbatim. For a draft it returns `{ data: null, message: "This test has not started, so there are no results. …" }` (verified). The running-state field names above follow the tool documentation and still need confirming on the first live read; correct this file if they differ. If the results call fails on a run, say so, skip the verdict for that funnel, and never end an experiment that week.
  - Feed `sessions` → `--views-*` and `conversions` → `--conv-*` of `ab_decision.py`; pass `--expected-share-a` when weights are not 50/50.
  - `progress` is how far the test is from being able to tell, shown in the app as "Confidence". It is **not** the chance the variant is better; the script gives that. `isSignificant` true + `leadingVersion: "variant"` is a proven win; significant with the original leading means the change made things worse. `visitorsNeeded` is Perspective's estimate of total visitors needed if the gap holds; compare it with the script's power line and quote the larger.
  - Results are lifetime, so `elapsed_days` = complete days since the day after the publish that started it.
- `end_experiment { funnelId, winner }` ends it one-way and keeps `winner`. Returns `{ data: { …experiment, status: "concluded" | "aborted", endedAt, winnerArmId }, message }`; `aborted` means it ended before significance and proves nothing, which is the normal outcome of a lean call or a no-difference end, so log it as such and not as a failure. The `message` says what visitors see now and whether a publish is still needed; pass it on. Verified in testing: ending took effect immediately (`get_experiment` → `data: null`, the funnel served the kept version) even while the results endpoint was down. Errors: `NO_RUNNING_EXPERIMENT`, `EXPERIMENT_NOT_STARTED` (it is a draft: `discard_experiment`), `EXPERIMENT_RESULTS_UNAVAILABLE` (retry shortly).
- `discard_experiment { funnelId }` deletes a draft and its variant permanently; user's yes required; `NO_DRAFT_EXPERIMENT` otherwise.

## Classic funnels: the measure-only fallback

A classic funnel (`isHtmlFunnel: false`) can have an experiment created in the app, but every experiment tool answers `FUNNEL_NOT_FOUND` for it. You can still read the test:

- **Does a test exist:** `chart_page_to_page_conversion_rate` with `abTest: "all"`: the first row's `name` reads `"<page> (original) & <page> (variant)"` and its `key` carries both page ids.
- **Views per version:** the same chart with `abTest: original`, then `variant`; first row `value` each. Only the first row splits; every later row stays blended, so never derive conversions from it (measured: page-2 views were identical under all three filters, so per-version `relativeValue` was just blended ÷ arm views).
- **Leads per version:** each contact's `meta.ps_start_slug` names the first-page version it entered on. Page `list_contacts { limit: 100, page, sortField: "ps_converted_at", sortOrder: "-1" }` back past the window start (about one page per 100 leads; batches of up to 5 in parallel), save each page as `page<N>.json` by its `meta.page` (parallel spill files can collide and silently drop a page), and run:
  ```bash
  python3 <skill dir>/scripts/tally_contacts.py --from <started_at> --to <yesterday> \
    --variant-page-id <variant page id from the chart key> page0.json page1.json …
  ```
  It checks the pages are contiguous and full, de-duplicates, counts per slug, maps slugs to versions by the variant's creation time (first 8 hex chars of its page id as a unix timestamp; the original is the slug with contacts before that), and withholds the inputs on any gap. The variant gets a new slug every time it is recreated in the app, so redo the mapping each read. Verified on a live classic test: views summed to the blended total exactly and leads by slug matched `kpi_new_contacts` exactly.
- Ending the test and keeping a version is done by the user in the app; the run report says which version and why.

## Step-by-step drop-off (the diagnosis chart)

`get_chart_metrics { funnelId, subtype: "chart_page_to_page_conversion_rate", from, to, abTest?: "all"|"original"|"variant" }`

Example response (`abTest: all`, 28 days, funnel with a running test; ids and numbers are illustrative, the shape is real):

```json
{"data":[
 {"key":"6a00…a1 (original) & 6a00…a2 (variant)","value":12400,"name":"Landing Page (original) & Landing Page (variant)","relativeValue":22},
 {"key":"6a00…b1","value":2730,"name":"Job Title","relativeValue":95},
 {"key":"6a00…b2","value":2370,"name":"Verification","relativeValue":100},
 {"key":"6a00…b3","value":2510,"name":"Opt-in","relativeValue":79},
 {"key":"6a00…c1","value":2150,"name":"Thank-you Page","relativeValue":6}, …]}
```

- `value` = visitors who reached that page in the window; `relativeValue` = **whole-number percent** of them who continued to the next page.
- **Visitors lost at a step** = `value × (100 − relativeValue) / 100`.
- **Rows are not in flow order and include branches and post-lead pages.** Order the steps along the main path up to the step that captures the lead (the opt-in or contact form; `kpi_new_contacts` ≈ that step's continues) and rank only those. Pages after the lead (sales page, upsell, thank-you) are not leaks for a lead funnel unless the hypothesis is about the upsell; a low-volume page on an optional branch is not a leak either.
- `abTest: original | variant` splits **only the first row's views**; every later row stays blended. Never derive per-version conversions from this chart (see the classic-funnel fallback for the right way).
- A funnel with no traffic returns placeholder rows (`key: "000000000000000000000001"`, `value: 0`) once published, and `data: []` before publishing. Either way there is nothing to diagnose yet.

## Dwell time (and the only other per-arm chart)

`chart_time_on_page` → one row per page, `value` = average seconds. With a test running, the first page appears **twice with the same `name`** and different `key`s (the two page ids from the conversion chart), so dwell is available per arm; map by `key`. Pair each big drop with its dwell: 5–15 s plus a big drop is a message problem; 45 s+ plus a big drop is an objection problem. Same drop, opposite fix.

## Devices, clicks, sources, trend

- `chart_visitor_devices` → rows for mobile / desktop / tablet / other; `relativeValue` is a **fraction** (0.898 = 89.8%), unlike the conversion chart. On 70%+ mobile, read the page as a phone would and weight fixes toward above-the-fold.
- `chart_button_clicks` → clicks per button with opaque keys (`button_click_e76q71`), some without a name, and no page or arm attribution; several buttons often share one label. Do not use it for per-page or per-arm diagnosis. One reliable use: the opt-in submit button's clicks equal `kpi_new_contacts` for the window, which confirms which step captures the lead.
- `chart_top_utm_sources` → if sources are tagged, check whether a drop is source-specific before blaming the page.
- `chart_contacts_over_time` → the traffic trend; a collapse here is the headline, not a page problem.

## KPIs

`get_kpi_metrics { funnelId, subtype, from, to }` → `{"data":{"type":"kpiConversionRate","value":12.88,"count":2526}}` (`value` in percent, `count` = contacts). Also `kpi_total_sessions`, `kpi_new_contacts`, `kpi_completion_rate`, `kpi_average_time_on_page`, `kpi_time_to_completion`. KPIs are funnel-level, never per arm. Use `kpi_total_sessions` to pick the diagnosis window and to judge whether a test is feasible at the funnel's pace.

## Reading and editing pages (HTML funnels only)

- `get_funnel_html { funnelId, version?, offset?, limit? }` → numbered lines, 32 KB cap. Read the first page's section only.
- `update_funnel { funnelId, prompt, version? }` → `{ jobId, funnelId, editorUrl, status: "pending" }`; `version` is required while an experiment exists (newer builds refuse with `EXPERIMENT_VERSION_REQUIRED`). Poll `get_funnel_job_status { jobId }` (long-poll, ~20 s per call) until `completed` or `failed`. Read the `summary`: it says what the generator believes it did, and it is how you catch over-reach (in testing, a request to "set up an A/B test" produced an honest note that it could not, and edited the original instead).
- `publish_funnel { funnelId, confirmStartExperiment? }`. With a draft test it first returns `errorType: "EXPERIMENT_START_NOT_CONFIRMED"`; resend with `confirmStartExperiment: true` only with the user's yes (review mode) or the standing auto-mode approval in `config.json`. Re-publishing a live funnel keeps its domain; omit `data`.

## Environments

The plugin's `.mcp.json` points at production (`https://api.perspective.co/mcp`). If you connect a second Perspective environment, never mix the two: an id from one does not exist on the other.

## Sanity checks before trusting a read

- Sessions split as the experiment's weights say (the script's SRM gate). A lopsided split means a mid-window change or traffic sent to one version directly.
- The script's verdict and Perspective's `isSignificant` / `leadingVersion` agree on direction. If they disagree, quote both and do not end the experiment.
- On a classic funnel: `original + variant` first-row views ≈ `all`, and leads per slug sum ≈ `kpi_new_contacts` for the window.
- On a classic funnel: the tally reported no problems (contiguous pages, window coverage, mapping coverage).
