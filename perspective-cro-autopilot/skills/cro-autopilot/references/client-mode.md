# Client Mode

For agencies and freelancers running funnels for clients. Two additions to the weekly loop: a client-facing report whenever a test is decided, and a rollout of winners across a client's (or an industry's) other funnels.

## clients.json

```json
{
  "clients": [
    {
      "name": "Sunrise Solar",
      "industry": "solar",
      "workspaceIds": ["6a00000000000000000000c1"],
      "funnelIds": ["6ad7…", "6ac6…"],
      "report": { "format": "html", "recipients": ["anna@sunrise-solar.example"], "language": "en", "tone": "plain" },
      "rollout_policy": "test"
    }
  ]
}
```

`rollout_policy`: `test` (default: a winner becomes a new experiment on each target funnel) or `ship` (apply directly, only if the client has said so; record their sentence like the auto-mode approval). The trust mode still applies on top: in review mode each target's start is asked; in auto mode the batch confirmation covers the starts.

## The win report

Generate one whenever a funnel's test is decided (winner, loser or no difference; clients should see the discipline, not only the wins). Save to `.cro-autopilot/reports/<date>-<client>-<funnel>.md`. If the client wants a page, build an HTML artifact from the same content (load the `artifact-design` skill first); give the user the link to pass on. Never send anything to the client yourself unless the user asks and an email or Slack tool is connected; even then, draft, show, and send only on their yes.

Structure, in the client's language, no analytics jargon:

```
# <Funnel name>: what we tested this week

**The short version.** We tested <one change in plain words>. <It won / It didn't move the needle / The original was better>. <One sentence on what this means for leads.>

## What we tested and why
<The leak in the client's terms: "79 of every 100 visitors left the first page within 8 seconds."> So we tested <change>.

## What happened
| | Before (original) | New version |
|---|---:|---:|
| Visitors | 2,100 | 2,050 |
| Became leads | 310 (14.8%) | 400 (19.5%) |

<Verdict sentence with confidence in words: "We're 95%+ confident this is real, not luck." If it was a lean call: "Not proven, but an 85% chance it is better, so we shipped it rather than wait three more weeks.">

## What it means for your leads
<Translate the lift into monthly leads at current traffic: "At last month's traffic that's about +95 leads a month from the same ad spend.">
<If no difference: "Nothing lost; we now know <lever> isn't what holds this page back.">

## What's live now
<What visitors see from today.>

## Next test
<One sentence: the next hypothesis and when it reads.>

## Everything tested so far on this funnel
| Date | Tested | Result |
|---|---|---|
| … | … | … |
```

Lead-impact math: last-28-day `kpi_new_contacts` × the measured relative lift in lead rate; say it is an estimate at current traffic.

## Rollout of a winner

Trigger: `/cro-rollout`, or the user says "roll this out". Targets: the same client's other enrolled funnels in the same industry, or across clients in that industry if the user says so. Industry comes from `clients.json`; never infer it from funnel names alone.

Procedure:
1. Show the winner (the learnings entry) and the candidate target funnels in one table: funnel, client, industry, current first-page continue rate, whether a variant slot exists, and what would change. Ask for one confirmation for the whole batch (`AskUserQuestion` when available, otherwise a lettered list). This is the "one click".
2. For each confirmed target:
   - If the target already has a running test, skip it and say so; a funnel runs one test at a time.
   - `rollout_policy: test` → treat the winner as the next hypothesis for that funnel: write its state, `create_experiment` with the adapted hypothesis (the target's own offer and audience, never another client's specifics), verify the variant, start it per the trust rules, and when it is decided log it with `log_test.py add --rolled-out-from <source funnelId>`.
   - `rollout_policy: ship` → apply to the original with `update_funnel`, verify, publish, and still measure it as a before/after change next cycle.
   - Classic target → park it at `awaiting_manual_change` with the exact change for the user to make in the app.
3. Report the batch: started, skipped, parked, with editor URLs.

Safety: never roll out across clients without naming each client in the confirmation, never ship directly unless the policy says so, and always adapt copy; a solar client's headline numbers must not appear on another solar client's page.
