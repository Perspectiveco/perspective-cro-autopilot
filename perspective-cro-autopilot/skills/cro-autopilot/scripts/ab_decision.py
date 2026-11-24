#!/usr/bin/env python3
"""Decide a Perspective first-page A/B test (or a before/after change) deterministically.

Never hand-derive these numbers. Gather the inputs from the Perspective MCP, run
this script, and report what it prints.

A/B mode (two arms served at the same time):
  python3 ab_decision.py ab --views-a 2100 --conv-a 310 --views-b 2050 --conv-b 358 \
      --planned-days 14 --elapsed-days 9 [--json]

Sequential mode (a change shipped on a later page, measured as after vs before):
  python3 ab_decision.py seq --views-before 1800 --conv-before 240 \
      --views-after 1750 --conv-after 275 --planned-days 7 --elapsed-days 7 [--json]

Inputs come from get_experiment_results (per version: sessions -> --views, conversions
-> --conv) on an AI/HTML funnel, or, on a classic funnel, from the chart's per-arm
first-page views plus leads per arm from tally_contacts.py.

Every verdict comes with "chance the variant is better" and, when the test is not
significant, an informed suggestion so the user can still make a call.
"""
import argparse
import json
import math
import sys


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    # Acklam's rational approximation, good to ~1e-9.
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def two_proportion(views_a, conv_a, views_b, conv_b):
    pa, pb = conv_a / views_a, conv_b / views_b
    pooled = (conv_a + conv_b) / (views_a + views_b)
    se_pooled = math.sqrt(pooled * (1 - pooled) * (1 / views_a + 1 / views_b)) if 0 < pooled < 1 else 0.0
    z = (pb - pa) / se_pooled if se_pooled else 0.0
    p_two = 2 * (1 - _norm_cdf(abs(z)))
    se_diff = math.sqrt(pa * (1 - pa) / views_a + pb * (1 - pb) / views_b)
    ci = ((pb - pa) - 1.96 * se_diff, (pb - pa) + 1.96 * se_diff)
    rel = (pb - pa) / pa if pa else None  # no relative lift when the original has converted nobody
    return dict(rate_a=pa, rate_b=pb, abs_diff=pb - pa, rel_lift=rel, z=z, p_value=p_two,
                ci95_abs=ci, prob_b_better=_norm_cdf(z))


def _pct(x, nd=1):
    """A fraction as a rounded percent; None stays None."""
    return None if x is None else round(x * 100, nd)


def _share(value):
    """--expected-share-a: Perspective reports weights in percent (70); a fraction (0.7) works too."""
    share = float(value)
    share = share / 100 if share > 1 else share
    if not 0 < share < 1:
        raise argparse.ArgumentTypeError("must be between 0 and 1, or 0 and 100 as a percent")
    return share


def srm(views_a, views_b, expected_share_a=0.5):
    n = views_a + views_b
    exp_a, exp_b = n * expected_share_a, n * (1 - expected_share_a)
    chi2 = (views_a - exp_a) ** 2 / exp_a + (views_b - exp_b) ** 2 / exp_b
    # 1 degree of freedom: p = P(chi2_1 > x) = 2 * (1 - Phi(sqrt(x)))
    p = 2 * (1 - _norm_cdf(math.sqrt(chi2)))
    return dict(chi2=chi2, p_value=p, failed=p < 0.001)


def sample_needed_per_arm(base_rate, mde_rel, alpha=0.05, power=0.8):
    """Visitors per arm to detect a relative lift of mde_rel at the given alpha/power."""
    p1 = base_rate
    p2 = base_rate * (1 + mde_rel)
    if p1 <= 0 or p2 >= 1:
        return float("inf")
    za, zb = _norm_ppf(1 - alpha / 2), _norm_ppf(power)
    pbar = (p1 + p2) / 2
    num = (za * math.sqrt(2 * pbar * (1 - pbar)) + zb * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2
    return math.ceil(num / (p2 - p1) ** 2)


def informed_suggestion(verdict, r, args, at_end, days_needed_total, too_few):
    """A plain-language call for the user when the stats alone do not settle it.

    The chance figure is P(variant > original) from the normal approximation of the
    difference in rates. It is honest about uncertainty without hiding behind
    "not significant": a 78% chance with a tiny downside is a decision, not a shrug.
    """
    pb = r["prob_b_better"]
    pct = round(pb * 100)
    lo_pp, hi_pp = r["ci95_abs"][0] * 100, r["ci95_abs"][1] * 100
    if verdict == "invalid":
        return {"call": "fix_setup", "text": "Not a readable test until the traffic split is fixed."}
    if too_few:  # below the minimum volume no call is offered, not even a lean one
        return {"call": "too_early",
                "text": f"Too few visitors to call either way (under {args.min_views_per_arm} per version). Keep running."}
    leader = "variant" if pb >= 0.5 else "original"  # a ship verdict always picks this side too
    lead_pct = pct if leader == "variant" else 100 - pct
    if verdict in ("ship_a", "ship_b"):
        return {"call": "ship_" + leader, "leader": leader, "chance_leader_better_pct": lead_pct,
                "text": f"Proven: {lead_pct}% chance the {leader} is better; ship the {leader}."}
    downside = (-lo_pp) if leader == "variant" else hi_pp  # worst plausible loss if the leader is actually worse
    powered = days_needed_total is not None and days_needed_total <= args.elapsed_days
    more = None if powered or not days_needed_total else max(days_needed_total - args.elapsed_days, 1)
    wait = (f" than wait ~{more} more days for proof" if more else
            " than keep waiting (the test already had enough traffic to show a 15% lift, so the true effect is smaller than that)")
    if lead_pct >= 80:
        call = f"lean_ship_{leader}"
        risk = (f"worst plausible downside about {downside:.1f} points" if downside > 0 else
                f"even the worst plausible case is {abs(downside):.1f} points better")
        text = (f"Not proven, but {lead_pct}% chance the {leader} is better; {risk}. "
                f"Reasonable to ship the {leader} now if you would rather move on to the next test{wait}.")
    elif lead_pct >= 65:
        call = "keep_running_or_lean_" + leader
        if not at_end:
            text = (f"{lead_pct}% chance the {leader} is better. Keep running to the planned end; "
                    f"if you must decide now, the {leader} is the better bet, but the gap could easily be luck.")
        elif powered:
            text = (f"{lead_pct}% chance the {leader} is better after the planned runtime, and the test had enough "
                    f"traffic to show a 15% lift, so any real effect is smaller than that. Take the {leader} as a "
                    f"coin-flip-plus if it costs nothing, and spend the next cycle on a bolder change.")
        else:
            text = (f"{lead_pct}% chance the {leader} is better after the planned runtime. Either extend "
                    f"~{more} days for a clean answer, or take the {leader} as a coin-flip-plus and spend the next "
                    f"cycle on a bolder change.")
    else:
        call = "no_difference_move_on"
        text = (f"About a coin flip ({pct}% chance the variant is better). This lever does not move the number; "
                f"keep the original and test something bolder on the same leak.")
    return {"call": call, "leader": leader, "chance_leader_better_pct": lead_pct, "text": text}


def decide_ab(args):
    r = two_proportion(args.views_a, args.conv_a, args.views_b, args.conv_b)
    s = srm(args.views_a, args.views_b, args.expected_share_a)
    at_end = args.elapsed_days >= args.planned_days
    min_per_arm = args.min_views_per_arm
    too_few = min(args.views_a, args.views_b) < min_per_arm
    needed = sample_needed_per_arm(r["rate_a"], args.mde_rel) if r["rate_a"] > 0 else float("inf")
    views_per_day = (args.views_a + args.views_b) / max(args.elapsed_days, 1) / 2
    days_needed_total = math.ceil(needed / views_per_day) if views_per_day > 0 and needed != float("inf") else None

    if s["failed"]:
        verdict, action = "invalid", "Sample ratio mismatch: the arms are not being served evenly. Check the test setup in Perspective before reading anything else."
    elif too_few:
        verdict, action = "keep_running", f"Under {min_per_arm} views per arm; any difference is still noise."
    elif not at_end and abs(r["z"]) >= args.early_z:
        verdict = "ship_b" if r["z"] > 0 else "ship_a"
        action = "Strong early result (|z| >= %.1f). Safe to call before the planned end." % args.early_z
    elif not at_end:
        verdict, action = "keep_running", f"Planned end not reached ({args.elapsed_days}/{args.planned_days} days). Only |z| >= {args.early_z} ends a test early."
    elif abs(r["z"]) >= 1.96:
        verdict = "ship_b" if r["z"] > 0 else "ship_a"
        action = "Planned runtime complete and the difference is significant at 95%."
    else:
        verdict, action = "no_difference", "Planned runtime complete, no significant difference. Keep the original and test a bolder change next."

    winner = {"ship_a": "original", "ship_b": "variant"}.get(verdict)
    suggestion = informed_suggestion(verdict, r, args, at_end, days_needed_total, too_few)
    out = dict(mode="ab", verdict=verdict, winner=winner, action=action,
               chance_variant_better_pct=round(r["prob_b_better"] * 100, 1),
               suggestion=suggestion,
               original=dict(views=args.views_a, conversions=args.conv_a, rate=round(r["rate_a"], 4)),
               variant=dict(views=args.views_b, conversions=args.conv_b, rate=round(r["rate_b"], 4)),
               abs_diff_pp=round(r["abs_diff"] * 100, 2), rel_lift_pct=_pct(r["rel_lift"]),
               ci95_abs_pp=[round(x * 100, 2) for x in r["ci95_abs"]], z=round(r["z"], 3),
               p_value=round(r["p_value"], 4), prob_variant_better=round(r["prob_b_better"], 3),
               srm=dict(chi2=round(s["chi2"], 2), p_value=round(s["p_value"], 4), failed=s["failed"]),
               runtime=dict(planned_days=args.planned_days, elapsed_days=args.elapsed_days, at_planned_end=at_end),
               power=dict(mde_rel=args.mde_rel, views_needed_per_arm=needed if needed != float("inf") else None,
                          days_needed_total=days_needed_total))
    return out


def decide_seq(args):
    r = two_proportion(args.views_before, args.conv_before, args.views_after, args.conv_after)
    at_end = args.elapsed_days >= args.planned_days
    # Before/after is confounded by traffic mix and time, so demand more than an A/B test would.
    if min(args.views_before, args.views_after) < args.min_views_per_arm:
        verdict, action = "keep_running", f"Under {args.min_views_per_arm} views in one of the windows; wait."
    elif not at_end:
        verdict, action = "keep_running", f"Comparison window not complete ({args.elapsed_days}/{args.planned_days} days)."
    elif r["z"] >= args.seq_z and (r["rel_lift"] is None or r["rel_lift"] >= args.seq_min_rel_lift):
        verdict, action = "keep_change", "After-window clearly better than before. Keep the change, but record it as a before/after read, not an A/B result."
    elif r["z"] <= -args.seq_z:
        verdict, action = "revert", "After-window clearly worse. Revert the change."
    else:
        verdict, action = "inconclusive", "No clear difference. Keep whichever version is live, log it as inconclusive, and prefer a first-page A/B test next."
    return dict(mode="sequential", verdict=verdict, action=action,
                before=dict(views=args.views_before, conversions=args.conv_before, rate=round(r["rate_a"], 4)),
                after=dict(views=args.views_after, conversions=args.conv_after, rate=round(r["rate_b"], 4)),
                abs_diff_pp=round(r["abs_diff"] * 100, 2), rel_lift_pct=_pct(r["rel_lift"]),
                ci95_abs_pp=[round(x * 100, 2) for x in r["ci95_abs"]], z=round(r["z"], 3),
                p_value=round(r["p_value"], 4),
                runtime=dict(planned_days=args.planned_days, elapsed_days=args.elapsed_days, at_planned_end=at_end),
                caveat="Before/after reads are confounded by traffic mix, ads and seasonality. Treat as directional.")


def fmt_table(out):
    if out["mode"] == "ab":
        a, b = out["original"], out["variant"]
        rows = [("", "Original", "Variant"),
                ("Views", a["views"], b["views"]),
                ("Conversions", a["conversions"], b["conversions"]),
                ("Rate", f'{a["rate"]*100:.2f}%', f'{b["rate"]*100:.2f}%')]
    else:
        a, b = out["before"], out["after"]
        rows = [("", "Before", "After"),
                ("Views", a["views"], b["views"]),
                ("Conversions", a["conversions"], b["conversions"]),
                ("Rate", f'{a["rate"]*100:.2f}%', f'{b["rate"]*100:.2f}%')]
    lines = ["| " + " | ".join(str(c) for c in rows[0]) + " |", "|---|---:|---:|"]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows[1:]]
    lines.append("")
    rel = "n/a" if out["rel_lift_pct"] is None else f"{out['rel_lift_pct']:+.1f}%"
    lines.append(f"Difference: {out['abs_diff_pp']:+.2f} pp ({rel} relative), "
                 f"95% CI {out['ci95_abs_pp'][0]:+.2f} to {out['ci95_abs_pp'][1]:+.2f} pp, z = {out['z']}, p = {out['p_value']}")
    if out["mode"] == "ab":
        lines.append(f"SRM: chi2 = {out['srm']['chi2']}, p = {out['srm']['p_value']} ({'FAILED' if out['srm']['failed'] else 'ok'})")
        pw = out["power"]
        if pw["views_needed_per_arm"]:
            lines.append(f"To detect a {pw['mde_rel']*100:.0f}% relative lift: ~{pw['views_needed_per_arm']} views per arm"
                         + (f", about {pw['days_needed_total']} days total at the current pace" if pw["days_needed_total"] else ""))
    lines.append(f"Runtime: day {out['runtime']['elapsed_days']} of {out['runtime']['planned_days']}")
    lines.append("")
    lines.append(f"VERDICT: {out['verdict'].upper()} — {out['action']}")
    if out["mode"] == "ab":
        lines.append(f"Chance the variant is better than the original: {out['chance_variant_better_pct']:.0f}%")
        lines.append(f"SUGGESTION ({out['suggestion']['call']}): {out['suggestion']['text']}")
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="mode", required=True)
    ab = sub.add_parser("ab")
    ab.add_argument("--views-a", type=int, required=True)
    ab.add_argument("--conv-a", type=int, required=True)
    ab.add_argument("--views-b", type=int, required=True)
    ab.add_argument("--conv-b", type=int, required=True)
    ab.add_argument("--planned-days", type=int, required=True)
    ab.add_argument("--elapsed-days", type=int, required=True)
    ab.add_argument("--expected-share-a", type=_share, default=0.5)
    ab.add_argument("--min-views-per-arm", type=int, default=200)
    ab.add_argument("--early-z", type=float, default=2.4)
    ab.add_argument("--mde-rel", type=float, default=0.15, help="relative lift the test is sized for (0.15 = 15%%)")
    ab.add_argument("--json", action="store_true")
    sq = sub.add_parser("seq")
    sq.add_argument("--views-before", type=int, required=True)
    sq.add_argument("--conv-before", type=int, required=True)
    sq.add_argument("--views-after", type=int, required=True)
    sq.add_argument("--conv-after", type=int, required=True)
    sq.add_argument("--planned-days", type=int, required=True)
    sq.add_argument("--elapsed-days", type=int, required=True)
    sq.add_argument("--min-views-per-arm", type=int, default=200)
    sq.add_argument("--seq-z", type=float, default=2.4)
    sq.add_argument("--seq-min-rel-lift", type=float, default=0.10)
    sq.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    for name in ("views_a", "views_b", "views_before", "views_after"):
        if getattr(args, name, None) is not None and getattr(args, name) <= 0:
            sys.exit(f"{name} must be > 0")
    out = decide_ab(args) if args.mode == "ab" else decide_seq(args)
    print(json.dumps(out, indent=2) if args.json else fmt_table(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
