# Perspective CRO Autopilot

A Claude Code plugin that does the job of a conversion-rate service for your Perspective funnels, every week:

1. reads your real results and finds the step where you lose the most people,
2. creates an experiment (Perspective's A/B test) with an AI-written variant of the first page and starts it,
3. reads it every week and decides it with a deterministic script: the verdict, the **chance the variant is better**, and an **informed suggestion** when the result is not statistically significant,
4. ends the experiment keeping the winner,
5. logs every test to one clean file (`learnings.md`) so the next test builds on what was learned,
6. moves straight on to the next test.

**Two trust modes.** `review`: the plugin prepares everything and asks before starting or ending an experiment, with the numbers and its recommendation. `auto`: it starts, decides and ends experiments on its own and reports what it did; proven results only, an unproven leader is always your call.

**Client Mode** adds a client-facing report every time a test is decided, and a one-confirmation rollout of a winner across a client's funnels in the same industry.

## Install

```
/plugin marketplace add Perspectiveco/perspective-cro-autopilot
/plugin install perspective-cro-autopilot@perspective-cro-autopilot
```

(Or copy this folder into a marketplace of your own; it is a standard Claude Code plugin: `.claude-plugin/plugin.json`, `skills/`, `commands/`, `.mcp.json`.)

The plugin declares the Perspective MCP (`https://api.perspective.co/mcp`). On first use Claude Code asks you to authorize it with your Perspective login. If you already connected Perspective in claude.ai, it is picked up automatically; see the [setup article](https://intercom.help/perspective-funnels/en/articles/15374243-how-to-connect-perspective-mcp-with-claude).

## Use

| Command | What it does |
|---|---|
| `/cro-setup` | enroll funnels, choose review or auto, Client Mode on/off, then run the first pass |
| `/cro-weekly` | the weekly pass: read experiments, decide, end, start the next, log, report |
| `/cro-report <funnel>` | Client Mode win report (markdown + optional shareable page) |
| `/cro-rollout <winner>` | roll a winner out across same-industry funnels as new experiments |

Or just talk: "optimize my funnel", "is the test done?", "should we ship it?", "what should we test next?", "roll this out to my other solar clients".

Run it from a dedicated folder (or repo). The plugin keeps its memory in `.cro-autopilot/` there: config, per-funnel state, `tests.jsonl` + `learnings.md`, and reports.

## Make it weekly

Schedule `/cro-weekly` once a week with Claude Code's scheduled tasks (`/schedule`), or a routine in claude.ai, pointed at that folder. In `auto` mode the run needs nobody; in `review` mode the report lists what is waiting for your yes.

## How a test is decided

`scripts/ab_decision.py` takes each version's sessions and conversions from Perspective's experiment results and returns:

- a verdict from a two-proportion z-test with a sample-ratio check, a pre-declared runtime (default 14 days) and an early stop only at |z| ≥ 2.4;
- the chance the variant is better than the original (not the same thing as Perspective's "Confidence", which is progress toward an answer; the report shows both and says which is which);
- an informed suggestion when the result is not significant: 80%+ chance with a bounded downside is a reasonable "ship and move on" call for you to make, 65–80% is keep running or coin-flip-plus, under 65% is a lesson that the lever does not matter.

## The test log

Every decided test goes through `scripts/log_test.py`, which appends to `tests.jsonl` and regenerates `learnings.md`: a table of every test ever run (funnel, client, change, result, lift, chance the variant was better, what was kept) followed by one entry per test with the lesson and the next idea. The skill reads it before designing anything, so a loser is never retested as-is and a sibling funnel's winner is the first thing tried.

## Limits

- Perspective experiments cover the **first page only**. Leaks deeper in the funnel are fixed as before/after changes, measured with a stricter rule, and always labeled as such.
- Classic (non-AI) funnels have no experiment tools in the MCP. They are enrolled as measure-only: the plugin finds the leak, designs the test, reads it (views per version from the charts, leads per version from the contacts' start page) and calls it; you make the change and end the test in the app.

## Layout

```
perspective-cro-autopilot/
  .claude-plugin/plugin.json
  .mcp.json                      Perspective MCP
  commands/                      /cro-setup /cro-weekly /cro-report /cro-rollout
  skills/cro-autopilot/
    SKILL.md                     the weekly loop, trust modes, report format
    references/
      data-playbook.md           experiment + metric calls with response shapes; classic-funnel fallback
      test-design.md             leak → hypothesis → create_experiment / update_funnel wording
      decision-rules.md          gates, chance-variant-better, informed suggestions, trust rules
      learnings-log.md           config, state, tests.jsonl and learnings.md schemas
      client-mode.md             win report template, rollout procedure
    scripts/
      ab_decision.py             the only place verdicts are computed
      log_test.py                appends to tests.jsonl, rebuilds learnings.md
      tally_contacts.py          leads per version on classic funnels (fallback)
    evals/evals.json             test prompts for the skill-creator loop
```
