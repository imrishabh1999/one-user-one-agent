# Impact report

## How impact is measured
Viewers are assigned to **treatment** or **holdout** by a salted hash of their viewer id before the replay
(90/10 split). The population is every viewer who opened the app (fresh, in-session) during the replay;
opening the app does not depend on the arm, so the two groups are comparable. For holdout viewers the agent
makes the full decision (goal, content, checks) but does not publish it, so both arms get the same goals
and the same judging.

The headline is **intent-to-treat (ITT)**: all treatment viewers against all holdout viewers, *including*
treatment viewers the agent chose not to act on. That is the effect of switching the agent on.

**Balance check (pre-replay events per viewer):** treatment 15.68, holdout
16.43: the arms look alike, as randomization should make them. Served viewers
13.82 vs unserved 21.18: these groups differ *before*
the agent did anything, which is why comparing them misleads.

## Results (replay, judged 1791 goals)
Population 2192 viewers: 1966 treatment, 226 holdout.
The agent acted on 82% of treatment viewers.

| Metric (ITT, treatment vs holdout) | Result |
|---|---|
| First full episode (watch ≥ 90%) within 3 days | 8.2% vs 6.6% (n=1966 / 226); difference **+1.6 pp**, 95% CI [-2.6, +4.4], p=0.4161 |
| First goal judged SUCCEEDED (shadow goals for holdout) | 7.8% vs 5.8% (n=1609 / 174); difference **+2.0 pp**, 95% CI [-2.6, +5.0], p=0.3383 |
| Purchase within 7 days, viewers never paid at start | 3.2% vs 2.0% (n=1331 / 149); difference **+1.2 pp**, 95% CI [-2.6, +2.9], p=0.4168 |

First goals left INCONCLUSIVE (not counted either way): 6.

Per goal (first goal per viewer, successes / judged):
- G01: treatment 16/255, holdout 2/42
- G02: treatment 49/323, holdout 3/28
- G03: treatment 18/118, holdout 0/10
- G04: treatment 0/3, holdout 0/0
- G05: treatment 36/815, holdout 3/85
- G06: treatment 0/26, holdout 0/2
- G07: treatment 5/5, holdout 2/2
- G08: treatment 1/9, holdout 0/0
- G10: treatment 0/55, holdout 0/5

The holdout is small (about 10%), so confidence intervals are wide; per-goal splits are descriptive only.

## Why simpler comparisons mislead
**Served vs unserved in this replay:** 7.6% vs 9.2% (n=1614 / 578); difference **-1.6 pp**, 95% CI [-4.4, +1.0], p=0.2397.
"Unserved" mixes the holdout with viewers the agent *chose* to skip (no eligible goal, stale trigger,
already-paid). Those choices depend on the viewer, so the groups differed before any action.

**The earlier pilot.** The internal summary says:
> Viewers served by the pilot agent converted at 18.7% versus 7.2% for everyone else, an uplift of 160%. We recommend full rollout.

That compares *served* viewers with *everyone else*. Only viewers who open the app can be served, and app
openers convert more anyway. Re-analysed against the pilot's own randomized holdout:

| Comparison | Result |
|---|---|
| Internal report: served vs everyone else | 18.7% vs 7.2% (n=2106 / 1894); difference **+11.5 pp**, 95% CI [+9.4, +13.5], p=0.0 |
| Openers only, treatment vs holdout | 18.7% vs 12.8% (n=2106 / 250); difference **+5.9 pp**, 95% CI [+0.9, +9.8], p=0.0227 |
| **ITT: treatment arm vs holdout arm** | 13.5% vs 10.5% (n=3602 / 398); difference **+3.0 pp**, 95% CI [-0.6, +5.9], p=0.0972 |

Only 58% of the treatment arm was served, so the implied effect on
those served is about ITT / share = **+5.1 pp** (95% CI roughly
[-1.0, +10.0]), nowhere near the claimed uplift.
Because we generated this pilot, we can check: the true effect built into it is **+2.0 pp** on served viewers,
inside that interval. The internal headline mostly measures *who opens the app*, not what the agent did.

In this replay the naive comparison happens to point the *other* way: viewers the agent skipped are heavier
watchers (often already paid, so no goal applies). Selection bias has no fixed sign, which is exactly why
only the randomized comparison is reported as impact.

## Honest caveats
- The outcome simulator and its effect sizes were written by us (see `simulate.py`). The replay shows the
  measurement code recovers an effect without bias; it says nothing about real viewers.
- One evening of triggers and a 10% holdout give limited power. In production, pre-register the primary
  metric and run until the CI excludes the minimum effect worth shipping.
- Goals are judged per viewer, but the business metric (completion, paid conversion) is what the ITT
  rows use; goal success alone could be gamed by choosing easy goals.
