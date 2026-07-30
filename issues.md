# slurmpast — audit and resolution

> **Second round, 2026-07-30, at `92a88e6`.** The modules the first round left
> unaudited — `tui.py`, `render.py`, `sacct.py`, `logs.py`, `cli.py`, `report.py` —
> were covered this time, by an independent review panel rather than one reader.
> See [Round two](#round-two-2026-07-30) at the end. Everything above it is the
> first round and is unchanged.

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

---

## Round two, 2026-07-30

**Method.** Twenty-three candidate defects were raised by independent readers, one
per module or cross-cutting lens, and each was then put to a panel of three further
readers who judged it separately — one asked to verify, one briefed to *refute*, one
asked only whether any user-visible output was actually wrong. A candidate had to
carry a majority of its panel to count as a defect. Every panellist worked from the
running code, not from the claim: the ones that survived were reproduced end to end,
and the ones that did not were dropped on evidence.

That procedure earned its keep. **Seven of the twenty-three were rejected**, four of
them unanimously, and several were plausible enough on paper that a single reader
would likely have "fixed" them.

**Scope this time.** `sacct.py`, `logs.py`, `cli.py`, `report.py`, `tui.py`,
`theme.py`, `model.py`, `index.py`, `patterns.py`, `diagnose.py`, `nodes.py`,
`sizing.py`, and the test suite itself. `render.py` was the one module whose reader
did not finish, so its width and truncation arithmetic remains as unexamined as it
was before — the tests around it (`test_layout.py`, `test_readability.py`) are the
only thing speaking for it.

### Fixed

| # | Problem | Where |
|---|---|---|
| 5 | An OOM floor was announced as "raise" beside a number *below* the current request | `sizing.memory_advice` |
| 6 | `DEADLINE` counted as neither failed nor completed, so it left the failure rate entirely | `model.Job.failed` |
| 7 | An explicit `fs/disk=0` was discarded as "unrecorded", so a stale fallback reported I/O that never happened | `model._tres_bytes` |
| 8 | The "failed runs" sort summed `failed + noop`, double-counting every hung timeout | `index._SORT_KEYS` |
| 9 | `build_groups` walked a one-shot iterator twice and silently reported `excluded=0` | `index.build_groups` |
| 10 | "Find the blocking call" was told to OOM-killed, NODE_FAIL and PREEMPTED jobs, over the top of the real cause | `diagnose._cpu_rules` |
| 11 | A dangling symlink counted as a confirmed log and shadowed the readable file beside it | `logs.Scan.exists` |
| 12 | `%j` expanded to `500+1` for a heterogeneous component, a filename Slurm never writes | `logs.expand_pattern` |
| 13 | The array master's bare id was promised as a third identifier and never produced | `logs.job_identifiers` |
| 14 | Two users' identically-named scripts merged into one fabricated workload | `patterns.group_key` |
| 15 | A run that finished *before* any OOM was reported as having succeeded "at a value that had already OOM'd" | `patterns.find_memory_search` |
| 16 | A job genuinely named `None` — an f-string over an unset variable — had its name blanked | `sacct._clean` |
| 17 | The hang veto asserted "blocked, not slow" of timeouts that burned nearly their whole limit | `sizing.walltime_advice` |
| 18 | "the busiest run used 12.0 of 2 cores per task": numerator and denominator from different runs | `sizing.cpu_advice` |
| 19 | The job list hid jobs in silence; its own "N more" line was unreachable | `cli.main` / `report.render_list` |
| 20 | `--overview --json` ignored `--sort` while the text view honoured it | `cli.main` |
| 21 | "ordered by compute used" was printed above an alphabetically-sorted table | `report.render_overview` |
| 22 | `--json` always exited 0, so the one mode a script checks `$?` from never reported severity | `cli.main` |
| 23 | `-u -p gpu` silently parsed as `user="-p"` with `gpu` as a job id | `cli._glue_negative_values` |
| 24 | `--demo --failed` returned the whole synthetic history | `cli._load` |
| 25 | `--nodes` keyed a workload by raw job name, so a parameter sweep fragmented below MIN_SAMPLES and its bad node went untested | `nodes.dominant_workload` / `node_table` |
| 26 | The paste-ready `--exclude` capped at 8 nodes without saying so | `nodes.suggest_exclude` |
| 27 | An exception building the history escaped a Textual worker and killed the dashboard | `tui._load` |

Numbers 5, 8, 14, 15, 17, 18 and 22 are all one shape: **a figure measured against
something other than what it was presented as.** Number 5 is issues.md #2 in the one
branch that fix did not reach, and the pattern for getting it right was already in
the file — `walltime_advice` folds its TIMEOUT floor into the same target everything
else is judged against instead of short-circuiting past the comparison.

Two items were found where a *test* was the problem. `test_short_rows_do_not_crash`
was `assert parse(text) == parse(text)` — a call compared with itself, which can only
fail if `parse` raises — and it is the only test feeding a row shorter than the field
list, so `get`'s bounds check had nothing holding it: turning it into a wraparound
read corrupted every field past the row's end and the suite stayed green. Its panel
did not survive the session, so it is fixed on the strength of a reproduced mutation
rather than a vote, and recorded here as such. `test_a_log_suffixed_name_is_answered
_without_a_stat` asserted that a *hit* skipped its stat, which is precisely what let
number 11 through; it now pins the sharper contract — misses stay free, hits are
confirmed once and cached.

### Rejected

| Claim | Why not |
|---|---|
| `parse()` drops one of two jobs sharing a reused job id | Unreachable: `sacct` shows only the most recent job per id unless `-D` is passed, which slurmpast never does. Verified against real requeued jobs on Slurm 20.11.8 — the duplicate is collapsed before `parse` sees it. **3-0.** |
| `cpus_per_task` assumes one task per node when `NTasks` is blank | A documented best-effort default with a named regression test, and no better signal exists across Slurm versions. Dividing by the node count beats not dividing at all. **1-2.** |
| `host-oom` and `cuda-oom` firing together contradict each other | They describe two different memory pools, either of which can genuinely be exhausted on one multi-rank job, and `cuda-oom`'s text disambiguates rather than negating. **1-2.** |
| `normalize_name` should fold hex/uuid run-ids, not just digit runs | The docstring considered folding beyond digits and rejected it, with a worked example and a regression test. Over-collapsing blames one workload for another's failures. **1-2.** |
| `sacct._run`'s subprocess-failure paths are untested | Panel lost to the session limit; the missing-binary half is already covered end to end by CI's `no-slurm` job. Left open rather than counted either way. |
| `cli.py`'s dashboard-reload closure is untested | Same panel. The behaviour itself is tested in `test_tui.py` against a loader stub. |

The two "untested path" items are the only candidates this round that were neither
fixed nor decided. Naming them beats implying the sweep was complete.

**Consequence for the numbers.** Fixing 6 changes what `failure_rate` reports for any
workload containing a DEADLINE run — upward, correctly. Fixing 14 splits workloads
that a multi-user query previously merged, so `-u alice,bob` now yields more groups
than before. Fixing 25 changes which workload the node screen controls on for any
history whose names carry digits, which is most of them; the recorded headline result
is untouched, because `node-evaluation` has no digits to fold.
