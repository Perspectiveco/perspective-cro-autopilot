# Decision rules

`scripts/ab_decision.py` encodes these; this file explains them so you can defend a verdict. Never override the script silently. If the user overrides it, log the override as theirs (`log_test.py add --override`).

## Pre-declare, then read

Write `planned_days` into the state **before** the experiment starts. Default 14 days (two weekly cycles, which also averages weekday/weekend mix). If the script's power line says the funnel needs longer to see a 15% relative lift, set the plan to that and tell the user, or test a bolder change. If it says 3 days would do, keep 14 anyway. `elapsed_days` = complete days from `started_at` through yesterday.

Reading early and stopping when it looks good is the easiest way to ship noise. The only early stop is `|z| ≥ 2.4`.

## Gates, in order

1. **Sample ratio mismatch** (chi-square on sessions, p < 0.001): the versions are not served as weighted; invalid until fixed. Pass `--expected-share-a` when the experiment's weights are not 50/50.
2. **Minimum volume:** under 200 sessions per version, keep running whatever the rates say. The suggestion is `too_early` then: no ship call, not even a lean one.
3. **Early stop:** before the planned end, only `|z| ≥ 2.4`.
4. **Planned end:** `|z| ≥ 1.96` ships the leader; otherwise no difference.

## Two numbers the user always gets

- **Chance the variant is better** = P(variant rate > original rate) from the normal approximation of the difference. 50% is a coin flip, 95%+ is what "significant at 95%" roughly means. Perspective's `progress` ("Confidence" in the app) is *not* this; it is how far the test is from being able to tell. Say both, and say which is which.
- **Informed suggestion** when the verdict is not a clean ship:

| Chance the leader is better | Call | What to tell the user |
|---|---|---|
| ≥ 95% (and `|z| ≥ 1.96` at the end, or ≥ 2.4 early) | `ship_*` | Proven. Ship. |
| 80–95% | `lean_ship_<leader>` | Not proven, but a good bet; show the worst plausible downside (the far end of the 95% interval) and the days left to proof. The user chooses: ship now and move on, or wait. |
| 65–80% | `keep_running_or_lean_<leader>` | Keep running to the planned end. At the end: extend for a clean answer, or take the leader as a coin-flip-plus and spend the next cycle on a bolder change. If the test was already powered for a 15% lift, say the real effect is smaller than that. |
| < 65% | `no_difference_move_on` | Coin flip. This lever does not move the number; keep the original, test something bolder on the same leak. |

Why this exists: a 14-day test that ends at 82% chance with a bounded downside is a decision, not a failure. Teams that only ship "significant" results ship a fraction of their real wins and wait weeks for proof of tiny effects. Teams that ship everything at 60% fool themselves. The table is the middle: proven ships itself, 80%+ is the user's informed call, under 65% is a lesson about what does not matter.

## Trust-mode rules for ending

- **review:** every `end_experiment` is asked, with the results table, the chance figure, the suggestion, and the plain sentence about what ending does. Wait for a yes and an explicit version.
- **auto:** `ship_a` / `ship_b` ends the experiment keeping the winner; `no_difference_move_on` at the planned end ends it keeping the original; every `lean_*` or `keep_running_or_lean_*` call is put to the user and the experiment keeps running meanwhile. Never end on a lean call unasked.

## Verdict table (A/B)

| Verdict | Do |
|---|---|
| `ship_b` | end keeping the variant; log; next test builds on the win |
| `ship_a` | end keeping the original; log the loser and why; next test uses a different lever |
| `no_difference` | see the suggestion table; at the planned end and under 65%: end keeping the original, log as a lesson, go bolder |
| `keep_running` | one-line status; if `days_needed_total` is far beyond the plan, say the test is under-powered and propose a bolder swing |
| `invalid` | report the split, check `get_experiment` weights, do not quote rates |

## Before/after (sequential) rule

Changes on later pages cannot be split-tested in Perspective, so they are measured as the N days after vs the N days before. That comparison is confounded by traffic mix, ad changes and seasonality, so the bar is higher: keep at `z ≥ 2.4` **and** at least +10% relative; revert at `z ≤ −2.4`; otherwise inconclusive. Always label these reads "before/after" in reports and the log.

## Confidence language

- Ship it: "The new headline won: 14.8% → 19.5% of visitors became leads (+32%), 95% confident."
- Lean: "Not proven, but an 87% chance the new headline is better, and the worst plausible downside is under one point. Your call: ship and move on, or run 9 more days for proof."
- No difference: "A coin flip after 14 days (58% chance the variant is better). Keeping the original and testing a bigger change."
- Never quote a rate without its visitors, and never a lift without its interval.
