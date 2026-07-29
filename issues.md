# slurmpast — audit and resolution

**Audited:** 2026-07-29 at `d656765`. **Resolved:** 2026-07-29 at `7b7da8c`.

Two defects were found by measurement and both are fixed. One item flagged as a
possible third was measured afterwards and is not a defect. One is a documented
design choice, left alone.

**Audit scope, stated up front so this is not read as a clean bill of health.**
`nodes.py` and `sizing.py` were read closely and simulated against the real code;
`patterns.py`, `diagnose.py`, `index.py` and `model.py` were skimmed. `tui.py`,
`render.py`, `sacct.py`, `logs.py` and `cli.py` were **not** audited in any depth.
The sacct/data layer appears well covered already — `docs/details.md` documents
seven parsing traps, each with a named regression test.

| # | Problem | Status |
|---|---|---|
| 1 | The node table ran a test per node and corrected for none of them | **fixed** |
| 2 | `requested` was the largest limit in the window, not the next run's | **fixed** |
| 3 | `dominant_workload` selects on the outcome | measured, not a defect |
| 4 | Walltime sized from the longest completed run | by design, unchanged |

---

## 1. The node table ran many tests and corrected for none of them

`node_table()` asked, for each node with ≥ `MIN_SAMPLES` placements, whether its
Wilson interval sat above the rate on every *other* node, at `Z = 1.96`. Each test
was right in isolation. Twenty run together and about one trips by chance — and
`suggest_exclude()` passed whatever tripped to the user as a paste-ready
`--exclude` string. This was the one output a user acts on directly.

**Measured, not estimated.** Null simulation against the real `node_table` /
`suggest_exclude`, every node given the identical true failure rate so any flag is
a false positive by construction. 30 jobs/node, p = 0.20:

| nodes in the table | before | after |
|---|---|---|
| 10 | 36.5% | 2.7% |
| 20 | **54.8%** | 2.8% |
| 40 | **77.8%** | 2.4% |

The error rate climbing with the size of the table is the signature of the defect:
it was a function of how many tests were run, not of the evidence. What matters
about the corrected column is not that it is smaller but that it is **flat**.

**Fix.** One-sided Fisher exact p-value per row against the existing leave-one-out
comparison, Benjamini–Hochberg adjusted across the rows of the table, in
`nodes.py:node_p_value` / `_bh_reject`. Raising `Z` to 2.576 was rejected as an
alternative: it only slows the growth (13.5% / 21.3% / 33.8% across the same three
sizes), because a wider interval treats the symptom and the cause is the number of
tests.

Fisher rather than a binomial tail against the leave-one-out rate, because that
rate is *estimated*. Against an estimated 0% a binomial test scores one bad run at
exactly p = 0, which no correction can ever withhold; Fisher conditions on the
margins and leaves it borderline, so the size of the table still gets a say. The
implementation agrees with `scipy.stats.fisher_exact` to 1.4e-12 relative error
over 4,000 random tables in both tails.

**Cost.** Power against one truly bad node (0.55 against 0.20 elsewhere, 20
nodes): 63% at 20 placements per node, 87% at 30, 98% at 50. Concentrated where
evidence is thin, which is where the module already said it wanted to hold back.
The recorded headline signal — `midway3-0385` at 19/36 against 12/218 — is
untouched, and still lands buried among 39 innocent nodes.

**Consequence for the display.** The table shows the interval the verdict no
longer rests on alone, so a row can read `inconclusive` beside a CI clear of the
baseline. Both front ends now say why (`render.held_back_note`), phrased as "an
interval alone is not enough when this many nodes were tested" rather than as a
claim that those particular intervals are chance — one of them may be the
genuinely bad node the correction cost us.

## 2. "Requested" was the largest limit in the window

`walltime_advice()` took `max()` over every `Timelimit` in the window as both the
`requested` figure shown and the `current` value the raise/lower/keep verdict was
measured against. `memory_advice()` and `cpu_advice()` did the same. It is rendered
as "raise to X (from Y)", so Y has to be the value the script currently holds.

This collided with a deliberate decision. `patterns.group_key()` excludes resource
magnitudes — *"raising `--mem` must not fork the history you are trying to learn
from"* — which is the right call and guarantees a group spans every limit the user
has tried. `max()` reached back across exactly the history the grouping exists to
unify.

**Worse than first reported.** The original note called this "misleading display,
not dangerous", on the grounds that `target` never derives from `current`. The
*number* is indeed sound, but the verdict computed against `current` is not:

```
midtrain, longest run 01:52:49, so the right answer is "raise to 02:30:00"

 2 stale runs @08:00:00 + 20 recent @00:40:00   before: requested 08:00:00, LOWER
 1 stale run  @02:30:00 + 13 recent @00:40:00   before: requested 02:30:00, KEEP
                                                        → and keep suppresses the
                                                          suggestion, so the tool
                                                          emitted nothing at all
```

The first inverts the instruction. The second silences it: a single stale run near
the target made the verdict `keep`, and `keep` withholds the suggestion, so the
tool said nothing about a 40-minute limit that every recent run needed 01:52:49 to
finish. Both now report `requested 00:40:00` and `raise to 02:30:00`.

On the recorded `rc-tok-github_code` history the memory figure was **48.0 GiB** —
a *cancelled* run five submissions back — against the 17 GiB the script actually
asked for.

**Fix.** `sizing._latest` takes the limit from the most recent run, ordered by
`start or submit` to match `index._stamp`. Timeout and OOM **floors** still use
`max()`, and that is still right: a floor is a claim about the requirement, which
no later, smaller request retracts.

## 3. `dominant_workload` selects on the outcome — measured, not a defect

`dominant_workload()` picks the job name with the most failure *events* rather than
the most runs, so the node screen has something to say. Choosing the densest-failure
stratum and then testing every node in it reads like it should push the same way as
problem 1. Measured once problem 1 was fixed, it does not, and the reason is
structural: the Fisher test **conditions on** the total number of failures in the
table, and that total is precisely what this function selects on. Selecting on a
statistic the test conditions away cannot bias it.

Paired against a workload chosen at random on the same 3,000 simulated histories,
all nodes null within each workload: 3.73% against 3.03% at 10 nodes, 3.17% against
2.97% at 20 (SE ~0.35%). At most a fraction of a point, and under the 5% target
either way. No change made.

## 4. Sizing from the longest completed run — by design

`walltime_advice` sizes from `max(elapsed) × 1.25`, not p95, and the code explains
why at length: p95 told the `software` workload to "lower to 03:00:00" on the same
screen that showed "longest 07:57:12", which would have timed out its slowest runs
by design. That reasoning is sound and the choice is right. Two consequences to be
aware of rather than fix — one atypically long run inflates the recommendation for
the rest of the window, and a workload whose runtime is *growing* gets a lagging
estimate. Neither is worth changing without evidence that it bites in practice.
