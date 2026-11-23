# Test design: from leak to one testable change

## The shape of a good hypothesis

```
Leak:      Landing Page → page 2 loses 4,900 of 6,200 visitors (79%) in 28 days.
Diagnosis: dwell 8 s, 82% mobile → message problem: the promise is not landing above the fold.
Change:    rewrite the headline to lead with the concrete outcome ("Get your EV shortlist in 60 seconds") and move the CTA above the fold on mobile.  ← ONE lever, even if two edits serve it
Expect:    +15% relative on lead rate (12.9% → 14.8%).
Decide on: lead rate per arm, 14 days.
Because:   learnings.md: last cycle's proof-logo test was no difference; message, not trust, is the open question.
```

One lever per test. "Headline + CTA position" is one lever if both serve the same above-the-fold promise; "headline + price framing" is two levers and cannot be learned from.

## Prioritise with the loss number, then the lesson

1. Biggest visitors-lost step (from the data playbook).
2. Among fixes for it, the one the log hasn't tried and that a sibling funnel has evidence for.
3. Among those, the first-page one, because only first-page changes get a true A/B read.
4. Bold beats timid. The in-app guidance to "change only a button colour" is fine for learning the tool, but a funnel that is meant to grow every week needs tests sized to move the number. Size the swing to the leak: a 79% drop deserves a new promise, not a new colour.

## Hypothesis library by leak type

**Message leak on page 1 (short dwell, big drop)**
- Outcome-first headline: say what they get and how fast, in their words (reuse phrases from the funnel's own question steps and answers).
- Ad-to-page match: mirror the top ad's promise in the first screen (ask the user for the top ad's headline once if ads aren't connected).
- Above-the-fold CTA on mobile; a question or button that needs a scroll is invisible to most visitors.
- Remove the first-screen choice overload: one question, one button.
- Specific over generic: numbers, names, timeframes.

**Objection leak on page 1 (long dwell, big drop)**
- Risk reversal near the CTA (free, no card, cancel anytime, what happens next).
- Proof placed where the decision happens (one strong, specific proof element, not a logo wall).
- Price or effort framing: "60 seconds", "3 questions", "no sales call".
- Clarify who it is for (and not for); a wrong-fit visitor leaving early is fine, a right-fit visitor unsure whether it's for them is the leak.

**Deeper-page leaks (before/after changes, measured sequentially)**
- Form friction: fewer fields, optional fields marked, phone last, clearer CTA label.
- Qualification theatre: if 90%+ pick the same answer, the question filters nobody; sharpen it or drop it.
- Expectation gap: a page whose headline promises something the previous page didn't set up. Often the better fix is earlier, on page 1, which turns it back into an A/B test.
- Sales/offer page: lead with the outcome, one CTA, objections answered in order of the question-step answers.

**Trend problems (not page problems)**
- Contacts collapsing week over week with stable step rates → traffic, not page. Say so; don't start a test that can't be read.

## Writing the `create_experiment` hypothesis

The AI writes the variant from the hypothesis, so it is the test spec. Title ≤ 40 characters, dated so the log reads in order ("W43 Outcome headline"). The hypothesis names the one change, gives exact copy where copy is the change, fences everything else, and says why:

```
Rewrite only the main headline on the first page to exactly:
"Get your EV shortlist in 60 seconds. No sales calls."
and make sure the primary button is visible without scrolling on a phone.
Keep the subheadline, images, layout, colours and every other page identical to the original.
Why: 79% of visitors leave the first page within 8 seconds on mobile; the current headline
leads with features, this one leads with the outcome and removes the sales-call fear.
```

After the job completes, read the variant (`get_funnel_html version: variant`) and the original, and confirm the change landed and nothing else moved; fix over-reach with `update_funnel version: "variant"`. If the job could not start, the variant is a copy of the original; send the change with `update_funnel version: "variant"` instead.

## Writing the `update_funnel` prompt

The generator owns the HTML. Describe outcomes, not markup; give exact copy when copy is the change; and fence the change so the test stays clean.

```
On the first page, change only the main headline to exactly:
"Get your EV shortlist in 60 seconds. No sales calls."
Keep the subheadline, button, images, layout, colours and every other page identical
to the current version. Do not add, remove or restyle anything else.
```

Patterns:
- **Copy change:** quote the final copy verbatim; say which element; say "change only this".
- **Position change:** "On mobile, the primary button must be visible without scrolling, directly under the headline. Keep the desktop layout as it is."
- **Add an element:** "Directly above the primary button add one line of small text: '<copy>'. Nothing else changes."
- **Revert / match:** "Make this page's <element> identical to the original version's: <paste the original copy>. Change nothing else." (used when shipping a winner into the other arm or reverting a loser)
- Never prescribe fixes for bugs ("the button is broken, fix the CSS"); describe the symptom and let the generator diagnose.
- Images need a hosted URL; use the image upload tools, never a local path.

After the job completes, **verify**: read the variant (`get_funnel_html version: variant`) and the original, and check that (a) the change landed as written, (b) nothing else moved. The job's `summary` tells you what the generator believes it did; the HTML tells you what it did. One corrective edit is normal; if a second is needed, simplify the change.

## When the funnel is classic (measure-only)

You cannot create or edit the variant. Write the exact change (as above) into the run report for the user to make on the first page in the app, with the editor URL, park the funnel at `awaiting_manual_change`, and continue with the other funnels. Do not stall the whole run on it.
