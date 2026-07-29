# slurmpast — problems found

**Date:** 2026-07-29 · **Version audited:** `d656765` (main, CI green) · **No code changed.**

**Audit scope, stated up front so this isn't read as a clean bill of health.** I read
`nodes.py` and `sizing.py` closely and ran simulations against the real code; I skimmed
`patterns.py`, `diagnose.py`, `index.py`, `model.py`. I did **not** audit `tui.py` (1,868 lines),
`render.py`, `sacct.py`, `logs.py`, or `cli.py` in any depth. The sacct/data layer appears
well-covered already — `docs/details.md` documents seven parsing traps, each with a named
regression test.

Two problems are confirmed by measurement. One is a design tension I flagged but did not
quantify. One is a characteristic worth knowing rather than a defect.

---

## 1. The node table runs many tests and corrects for none of them

**Severity: the only item here that hands a user a wrong answer they will act on.**

`nodes.py:node_table()` walks every node with ≥ `MIN_SAMPLES` (10) jobs and independently asks
whether that node's Wilson interval sits above the rate on every *other* node, at `Z = 1.96`
(`nodes.py:23`). Each test in isolation is correct. Twenty of them run together and roughly one
should trip by chance — and `suggest_exclude()` passes whatever tripped to the user as a
paste-ready `--exclude` string.

### Measured, not estimated

Null simulation against the real `node_table` / `suggest_exclude`: **every node given the
identical true failure rate**, so any flag is a false positive by construction. 30 jobs/node,
p = 0.20, 400 tables per row.

| nodes in the table | tables flagging ≥1 innocent node | mean nodes flagged |
|---|---|---|
| 10 | 31.8% | 0.45 |
| 20 | **58.8%** | 0.78 |
| 40 | **76.8%** | 1.41 |

For a user whose history spans 20 nodes, **more than half the time** the tool offers at least one
node to exclude that is not actually worse than the rest. The error rate climbs with the size of
the table, which is the signature of the defect: it is a function of how many tests were run, not
of the evidence.

### Which fix, with the cost of each

Same simulation for false positives; power measured with node 0 truly bad (0.55 vs 0.20
elsewhere), 20 nodes.

| | FP rate (10 / 20 / 40 nodes) | power (20 / 30 / 50 jobs per node) |
|---|---|---|
| `Z = 1.96` (today) | 31.8% / 58.8% / 76.8% | 95.5% / 98.5% / 100% |
| `Z = 2.576` | 11.2% / 25.5% / 29.5% | 87.5% / 95.2% / 100% |
| **Benjamini–Hochberg** | **5.8% / 6.0% / 1.8%** | 65.2% / 88.5% / 98.8% |

**Benjamini–Hochberg is the right fix.** It is the only option whose error rate stays flat as the
table grows — raising `Z` to 2.576 still leaves 29.5% at 40 nodes, because it treats the symptom
rather than the cause. BH's power cost is concentrated where evidence is thin (20 jobs/node),
which is precisely where the module's own stated philosophy says it should hold back:

> *"A node is only called out when its interval excludes the baseline; otherwise the honest
> answer is 'not enough evidence', which is what it says."*

### Where it would go

One helper computing one-sided binomial p-values against the existing leave-one-out `comparison`,
BH-adjusted across the rows of a table, applied where `verdict` is assigned. `wilson_interval`
stays for the displayed interval. Regression test: the null simulation above, asserting the
flag rate stays near 5% as the node count grows.

### What is explicitly *not* wrong here

Worth recording, because I previously claimed this module was broken and had to retract it. The
module already handles the hard part correctly:

- **It controls for workload by default** — `node_table(jobs, workload=…)` restricts to one job
  name, and `tests/test_nodes.py` has 34 tests including one named *"the confound is real: a node
  hosting one bad campaign looks cursed."*
- **It compares leave-one-out**, against every *other* node rather than a pooled rate that
  includes the node under test. This is better than the cluster-wide `sacct -a` analysis I
  originally proposed to "correct" it with, which used the pooled baseline.
- Thin evidence renders `inconclusive`, not an accusation.

The multiple-comparison gap is the residual after all of that, not evidence of a careless module.

---

## 2. "Requested" is the largest limit in the window, not the one the next job will use

**Severity: misleading display, and a spurious verdict on an already-correct setup. Not dangerous.**

`sizing.py:walltime_advice()` builds `limits = sorted({j.timelimit …})` and then takes
`limits[-1]` — the **maximum** over the whole window — as both the `requested` figure shown to the
user and the `current` value the raise/lower/keep verdict is measured against.
`memory_advice()` does the same with `max(limits)`.

This interacts with a deliberate design decision. `patterns.py:group_key()` folds in name,
partition and GPU-or-CPU but **deliberately excludes resource magnitudes**:

> *"Resource magnitudes are deliberately excluded: raising --mem must not fork the history you are
> trying to learn from."*

That is the right call — but it guarantees a group spans every limit the user has tried, so
`max()` is reaching across exactly the history the grouping was designed to unify.

### Demonstrated against the real code

```
2 old runs at --time=08:00:00, then 20 recent at 00:40:00; every run takes 25m
   → requested=08:00:00   verdict=lower   suggestion=00:35:00

20 runs at 08:00:00, then 2 recent at 00:30:00 (user just tightened it); runs take 25m
   → requested=08:00:00   verdict=lower   suggestion=00:35:00

control — all 20 runs at 00:40:00, runs take 25m
   → requested=00:40:00   verdict=keep    suggestion=—
```

The control is the same workload without the stale rows, and it correctly says **keep**. So a user
who already fixed their walltime is told they are over-requesting by eight hours, above a
`requested` figure that does not match their script.

### Why it is not dangerous

`target` is derived from observed runtimes plus the timeout floor, never from `current` — so the
*number suggested* stays sound. Only the framing is wrong: the stated current request, and the
raise/lower/keep verdict computed against it. Impact is bounded by the window (7 days by default)
and grows with longer `--since`.

**Fix direction:** use the limit from the most recent run in the group rather than the maximum,
and say so in the basis text. Keeping `max()` for the *floor* logic is still correct.

---

## 3. `dominant_workload` selects on the outcome — flagged, not quantified

`nodes.py:dominant_workload()` deliberately picks the job name with the most failure *events*
rather than the most runs, so the node screen has something to say. The docstring is candid about
this and argues the case: the confound being held fixed is still the workload, and the comparison
is still strictly between nodes inside it.

That argument is largely right for the *confound* question. It remains true that choosing the
densest-failure stratum before testing pushes in the same direction as problem 1 — you are
selecting the slice most likely to contain an extreme node, then testing every node in it without
correction.

**I did not measure this separately**, and the numbers in problem 1 do not include it. If BH is
implemented, this is worth re-measuring on top of it before deciding whether it needs anything.

---

## 4. Sizing from the longest completed run — a characteristic, not a defect

`walltime_advice` sizes from `max(elapsed)` × 1.25, not from p95, and the code explains why at
length: p95 told the `software` workload to "lower to 03:00:00" on the same screen that showed
"longest 07:57:12", which would have timed out its slowest runs by design.

That reasoning is sound and the choice is right. Two consequences to be aware of rather than fix:

- One atypically long run inflates the recommendation for the rest of the window. The no-CPU hang
  branch catches pathological hangs before they reach here, but a genuinely slow-but-real outlier
  is included by design.
- A workload whose runtime is *growing* run over run gets a lagging estimate, since the basis is
  the longest run already observed.

Neither is worth changing without evidence that it bites in practice.

---

## Summary

| # | Problem | Confirmed | User-facing wrong answer? |
|---|---|---|---|
| 1 | No multiple-comparison correction in the node table | measured | **Yes** — spurious nodes in `--exclude` |
| 2 | `requested` / `current` is max-over-window, not current | measured | Misleading display + spurious verdict |
| 3 | `dominant_workload` selects on the outcome | flagged, unquantified | Compounds #1 |
| 4 | Sizing from the longest run | by design | No |

Only **#1** produces advice a user would act on and be wrong to. It is also the most contained
change.
