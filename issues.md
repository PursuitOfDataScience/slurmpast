# slurmpast — audit and resolution

> **Round four, 2026-08-03, from `4d47d4d`.** Not a sweep — two defects, both
> surfaced by one user question ("does slurmpast support me looking at other users'
> past jobs?"). The answer was yes, and asking it found that the multi-user path
> was half-built: a `--allusers` branch nothing could reach, and a `user` argument
> that every modern Slurm ignored. 1,083 tests before, **1,098 after**. `ruff`,
> `ruff format` and `mypy` clean.
>
> **Round three, 2026-07-31, from `7f32b1a`.** Thirteen defects found, thirteen
> upheld by a three-reviewer panel, thirteen fixed, plus one the panel found that
> was not on the list. 1,029 tests before, **1,083 after** — 54 new, one per fix
> and its control. `ruff`, `ruff format` and `mypy` clean.

---

## Round four — the multi-user path

| # | Problem | Where | Test |
|---|---|---|---|
| 1 | `--allusers` existed but nothing could reach it, and no flag offered it | `cli._load` / `cli.build_parser` | `TestWhoTheQueryIsAbout` (`test_cli.py`) |
| 2 | `live_job_ids` ignored its `user` argument on every Slurm since 20.02 | `sacct.live_job_ids` | `TestSqueueReconciliation` (`test_portability.py`) |

### 1. `--all-users` reaches the branch that was already written

`Sacct.history` had `elif user == "": extra += ["--allusers"]`. `_load` then scoped
the query with `args.user or getpass.getuser()`, so the empty-string sentinel became
your own name before it ever arrived: `-u ""` reported **your** jobs while reading as
a request for everyone's. There was no flag for it either — while `patterns.group_key`
carried the user in the key specifically because "`--allusers` spans the cluster, so a
multi-user query is one flag away". The flag did not exist.

`--all-users` now exists and routes to that branch; `--all-users` together with `-u`
exits 2 rather than letting one win silently and scoping the output to something the
reader did not ask for. Verified on Midway3: 80,027 jobs across 1,612 workloads in a
two-day window, against 1,730 in 100 workloads for a single other account.

The empty-string spelling still works, since 0.4.0 shipped it as public API.

### 2. `--me` is only asked about me

`live_job_ids` tried `squeue --me` first **unconditionally** and fell back to
`-u <who>` only when that raised. `--me` has been in Slurm since 20.02, so on every
release anyone runs, the fallback never fired and the `user` argument was dead code:
`-u alice` reconciled alice's RUNNING records against *my* queue.

It read as working because the only test covered the fallback — it stubbed a runner
that **raises on `--me`**, which is the one condition under which the argument was
honoured. The `--me` attempt is now made only when the account being reconciled is
the caller's own; `--all-users` asks an unfiltered `squeue` on purpose, which is the
same command the docstring warns about as an accident.

Contained rather than harmless today: `_mark_open_records` only tests the result for
`None`, so a wrong-account answer changed no output. It was one caller away from
mattering, and three new tests pin each branch.

### Consequence for the numbers

None for a single-user query, which is the default and what every previous round
measured. `--all-users` is new surface: `patterns.group_key` already carried the
owner, so cross-account queries group per user rather than fabricating one shared
workload out of two people's `run.sh`.

---

# Round three — everything below this line

## Rounds one and two — verified closed before anything new was looked for

Every fix from the first two rounds is present at the site issues.md named for
it, checked by reading the code rather than by trusting the entry:

`nodes.node_p_value` / `_bh_reject` (1) · `sizing._latest` (2) ·
`sizing._memory_verdict` (5) · `model.Job.failed` carrying DEADLINE (6) ·
`model._tres_bytes(zero_is_missing=)` (7) · `index._SORT_KEYS["failures"]` on
`problems` (8) · `index.build_groups` materialising its input (9) ·
`diagnose._NOOP_ALREADY_EXPLAINED` (10) · `logs.Scan.exists` confirming a hit
(11) · `logs.expand_pattern`'s `own_id` (12) · `logs.job_identifiers`' array
master (13) · `patterns.group_key` carrying the user (14) ·
`patterns.find_memory_search`'s forward walk (15) · `sacct._FREE_TEXT` (16) ·
the hang veto's computing/hung split (17) · `sizing.cpu_advice`'s `busiest`
(18) · `cli.main` handing `render_list` the whole list (19) ·
`--overview --json` through `sort_groups` (20) · `render_overview`'s ordering
claim (21) · `--json`'s exit code (22) · `cli._glue_negative_values` (23) ·
`--demo --failed` (24) · `nodes` folding names before it strata (25) ·
`nodes.excluded_tail` (26) · `tui._load`'s guard around `History` (27).

Items 3 and 4 were decided "not a defect" and "by design"; both are unchanged
and both still read correctly. Nothing from those rounds regressed.

**Two of them turn out to have been fixed only on one side**, which is the
strongest pattern in this round. #21 corrected the *caption* above the workload
table for `--sort` and left the *footer* below it wrong (new #2). #24 fixed
`--demo --failed` and left `--demo -p` / `--demo -u` in the same state for the
same stated reason (new #8). Round two named this shape itself — "#5 is
issues.md #2 in the one branch that fix did not reach" — and it recurred twice.

---

## Method

Every module read in full, including `render.py`, which neither previous round
finished. Thirteen candidates were raised and each was reproduced by running the
code before being written down. All thirteen then went to **three independent
reviewers**, working from the running code, told to default to NOT-A-DEFECT on
thin evidence and to weigh the codebase's own documented intent.

**The panel returned 13/13 DEFECT, unanimous.** No candidate drew a 1-of-3 split,
so no second round of evaluation was needed. That is a weaker result for the
procedure than round two's (which rejected 7 of 23) and it is worth saying why
rather than claiming a clean sweep: this round's candidates were all reproduced
end-to-end before being listed, where round two's were raised from reading. The
panel's value here was in the **corrections** it made, not the rejections —

* **#5 was overstated.** Textual soft-wraps, so nothing clipped. The real harm is
  an inert width argument and a hanging indent lost on continuation lines. Two of
  three reviewers flagged this independently, and one warned the naive fix
  (dropping the `join`, keeping the `100`) would have introduced #10 there.
* **#11 was understated.** `read_bytes` also iterates `self.steps` rather than
  `work_steps`, so `.extern` pollution — the artefact `_from_steps` documents and
  excludes — reaches the I/O figures. Two of three reproduced it; a job whose
  extern step claimed 500 GiB against 1 GiB of real work reported 500. Fixed with
  #11, since it survives the `max`→`sum` change.
* **#6's worst case is worse than described.** At a 12-cell column
  `midway3-0600,midway3-0611` truncates to `midway3-0600` — not a visibly broken
  string but a **complete, valid, real node name** for a job that ran on two.
* **#9's payoff is smaller than claimed.** 2.2–5.9× on the function, ~4% of the
  whole log pass end-to-end, and unmeasurable on a small log directory.

One reviewer also found a **test-coverage gap** that let #4 survive two audits;
it is fixed below. All three confirmed the repo was untouched during review.

---

## Fixed

| # | Problem | Where | Test |
|---|---|---|---|
| 1 | A hung run's `--time` became the walltime floor for the whole workload | `sizing.walltime_advice` | `TestAHungRunIsNotEvidenceOfNeedingMoreTime` |
| 2 | "… N more workloads" described the cost-ranked tail whatever `--sort` said | `index.tail_summary` | `TestTheTruncationNoteDescribesWhatWasTruncated` |
| 3 | `--demo` attached real log files off the local disk to synthetic jobs | `cli.main` | `TestTheDemoStaysSynthetic` |
| 4 | The plain node table hardcoded its widths and ignored the shared spec | `report.render_nodes` | `TestTheNodeTableGoesThroughTheSharedSpec` |
| 5 | `" ".join(wrap(...))` made the workload banner's wrap a no-op | `tui.WorkloadScreen` | `TestTheWorkloadBannerWrapsAtAll` |
| 6 | A truncated node list read as a shorter, real, wrong node | `render.text_table` | `TestTruncationSaysSoInATable` |
| 7 | `--sizing` accepted `--sort` and discarded it | `cli.main` / `report.render_sizing` | `TestSizingHonoursTheSort` |
| 8 | `--demo` ignored `-p` and `-u` | `cli._load` | `TestTheDemoHonoursEveryNarrowingFlag` |
| 9 | The log scan rebuilt a membership set on every probe | `logs.Scan.exists` | `TestTheListingIsIndexedOnceNotPerProbe` |
| 10 | Dashboard findings wrapped to a fixed 86 cells | `tui.JobScreen` / `PatternsScreen` | `TestTheDashboardWrapsToTheTerminalItIsOn` |
| 11 | Disk I/O took the max across steps where CPU sums — and read `.extern` | `model.Job.read_bytes` / `write_bytes` | `TestDiskTotalsSumTheStepsThatMovedTheData` |
| 12 | `--sort recent` broke ties Z→A while every other sort broke them A→Z | `index.sort_groups` | `TestSortTieBreaksRunTheSameWayInEveryMode` |
| 13 | "1 nodes below threshold omitted" | `report` / `tui` | `TestCountsAreSpelledForTheirNumber` |
| — | A layout test built five views and asserted over two, exempting #4 | `tests/test_layout.py` | *(the test itself)* |

### 1. The walltime floor now comes from the timeouts that computed

`floor = max(...)` ran over every TIMEOUT. `hangs_dominate` needs three hangs AND
half the timeouts AND a fifth of the workload, so a *minority* of hangs never
reached the veto and set the floor unopposed — breaking rule 2 of the module's own
header, with the split it needed already computed fifty lines above.

`computing = [j for j in timeouts if not looks_like_noop(j)]` is now hoisted to the
top of the function and used by both the veto and the floor. Reproduced before and
after, on ten completed runs of an hour, six real timeouts at a 2-hour limit, and
two hung runs carrying a stale 24-hour one:

```
before  raise to 1-06:00:00   basis: longest of 10 completed runs took 01:00:00.
after   raise to 02:30:00     basis: longest of 10 completed runs took 01:00:00.
```

A 12× over-request, gone, and the basis and the number now agree. The caution was
counting the same set: it said "8 runs timed out, so the requirement is at least
the limit that cut them off" of two runs that provably never computed. It now reads
"6 runs timed out while computing … 2 further timeouts consumed almost no CPU and
are left out of that floor". The existing test pinning `max()` for the floor
(`test_a_timeout_floor_is_still_taken_from_the_largest`) uses a computing timeout
and is untouched, which is the control that matters.

### 2. The truncation note is told which list was sliced

`tail_summary(shown, ordered=None)` now takes the ordered list the caller actually
cut, instead of slicing `self.groups` behind its back. Measured on the demo at
`-n 3`:

```
             before                          after
--sort cost  23 runs / 10.9%   (correct)     23 runs / 10.9%
--sort name  23 runs / 10.9%                 30 runs / 86.4%
--sort rate  23 runs / 10.9%                 27 runs / 88.6%
```

The 86.4% and 88.6% were independently computed by two reviewers before the fix and
match. The old line told a reader that the hidden bulk of their history was a
negligible remainder — worse than silent truncation, which is the one thing this
line exists to prevent.

### 3. `--demo` no longer touches the filesystem for logs

A synthetic job wrote no log, so anything a search turns up is a real file
belonging to a real run — and its text feeds `diagnose`. Measured: **39 of 58** demo
jobs were handed a file out of the user's own work directory, and four gained
findings (`nccl`, `import-error`) read out of somebody else's training run. One
reviewer went further and dropped a fabricated traceback into the current
directory, which produced "GPU ran out of memory" and a verbatim traceback on
synthetic job 5100002.

`cli.main` now sets `args.no_logs = True` under `--demo`. That is not a workaround:
for synthetic records it is the *correct* answer, since no log exists to find. It
also restores what `DEMO_SITE` was added for — the demo renders identically on a
login node and a laptop.

### 4. The plain node table goes through `render.NODE_COLUMNS`

It was the one plain table still hand-formatted at `"  %-16s %9s %10s %20s  %s"`,
while the spec written for it sat unused and the dashboard used it. Now it goes
through `_plain_layout` + `text_table` like the other three:

```
before, any width          after, COLUMNS=80              after, COLUMNS=140
NODE          N   RATE     NODE               N   RATE    NODE                   N   RATE
gpu-compute-node-a100-0001     10/14          gpu-compute-node-a100…  10/14      gpu-compute-node-a100-0001  10/14
cn2       0/14                 cn2             0/14                   cn2         0/14
   (every column shifted 10 cells)      (aligned, 72 cells)      (aligned, name in full, 76 cells)
```

It drops columns on a narrow terminal, grows the name column on a wide one, and
lines up whatever the names are.

### 5. The workload banner wraps for real

`" ".join(render.wrap(evidence, 100))` puts the wrapped lines straight back
together — the width was dead code, and the evidence went out as one 138-cell line
at every terminal size. Now one `append` per wrapped line, each carrying the
two-space indent, at `_prose_width(self, 4)`. On an 80-column dashboard:

```
before  138 | 18 of 20 runs of cot-exp in test failed; 18 were TIMEOUT. Every one used the same …
after    74 |   18 of 20 runs of cot-exp in test failed; 18 were TIMEOUT. Every one used
         65 |   the same --time=00:30:00. 9 GPU-hours consumed by the failures.
```

Taking the panel's warning: the fix is a width-aware wrap, not merely dropping the
`join`, which would have reproduced #10 here.

### 6. A cut cell says it was cut

`render.clip` replaces the bare `value[:width]`, marking a truncated cell with `…`.
The case that made this worth doing is not the visibly-broken one:

```
node_list = midway3-0600,midway3-0611     column width 12
before    midway3-0600      a complete, valid, real name — for a job that ran on two
after     midway3-0600…
```

Truncating the column stays deliberate, as `Column`'s docstring says; doing it
without a marker was not, and every other truncation here announces itself.

### 7 & 8. Two flags that were accepted and thrown away

`render_sizing` takes a `sort` and iterates `sort_groups(...)`; the `--sizing
--json` branch does the same, so text and JSON cannot disagree. A non-default order
is now named on screen (`ordered by failure rate`), as the overview does — the
screen never said what order it was in, and its own note warns that "the workload
most worth re-sizing can sit at position 13", for which `--sort rate` is the
remedy.

`cli._load`'s demo branch applies `-p`, `-u` and `--failed`, and raises when
nothing matches. `--demo -p gpu` exited 0 printing all 58 records; it now exits 2
with "no demo jobs match partition gpu", matching the real path. An explicit job id
still bypasses the filters, as `-j` does against sacct.

### 9. The listing is indexed once, not per probe

`Scan._names_in` caches the membership set beside the listing `entries` already
caches. The set was being rebuilt on each of ~84 probes per job, so the test this
class exists to make constant-time was linear in the directory:

```
                 before        after
 1,000 files     2.7 us       0.4 us  per probe
13,000 files    16.6 us       0.9 us  per probe   (flat, as it should be)
```

Honest about scale, per the panel: unmeasurable on a small log directory, ~4% of
the whole log pass end-to-end, and worth it because it is three lines in the one
function whose entire docstring is a performance argument.

### 10. The dashboard measures the terminal, like the plain renderer does

New `tui._prose_width(screen, indent)`, used by `JobScreen` and `PatternsScreen` in
place of the fixed 86 and 82. `report._prose_width` had already solved this and
said why; `JobScreen._path_budget` had already solved it for paths on the same
screen.

```
terminal  70 -> widest line 67    (was 94, soft-wrapped to column 0)
terminal  80 -> widest line 78    (was 94)
terminal 120 -> widest line 118   (was 94 — refusing the room it had)
```

The narrow-terminal pair layout goes with it: `JobScreen` now passes
`render.PAIRED_LINE_WIDTH`-aware `max_value` to `pair_rows`, the threshold
`report` has applied all along. That was raised by one reviewer only, so it is
recorded as a partial fix — see **Open** below.

### 11. Disk I/O sums the steps that moved the data

`Job._io_from_steps` sums `read_bytes` / `write_bytes` over `work_steps`, for the
same reason `_from_steps` sums CPU, and against the same rejected alternative in
its own words: "Falling back to the largest step was wrong too: it drops every step
but one." Four `srun` steps each reading 30 GiB and writing 10:

```
              before        after      truth
read           30.0 GiB    120.0 GiB   120.0 GiB
write          10.0 GiB     40.0 GiB    40.0 GiB
io_rate      11.4 MiB/s   45.5 MiB/s
```

`io-heavy` was suppressed by this: four steps of 120 GiB in an hour is 136 MiB/s
against a 100 MiB/s threshold, reported as 34, so the finding whose whole purpose
is to say when the filesystem set the pace stayed silent. It now fires.

The panel's addition is folded in: `work_steps`, not `steps`, so a polluted
`.extern` claiming 500 GiB against 1 GiB of real work reports 1. Where **no** work
step recorded anything, extern is the only reading there is and the old `max`
stands as a fallback — the same shape `total_cpu` uses. The caveat both reviewers
raised is documented at the property: `TRESUsage*Tot` is a per-step total and sums
exactly, while the `MaxDiskRead` fallback beneath it is a per-task maximum and does
not — summing those still under-reports a multi-task step, by less than `max`,
which discarded every step but one.

### 12 & 13. Two small ones

`sort_groups` runs two stable passes for a descending mode instead of
`reverse=True`, which reversed the tie-break along with the primary. `recent` now
gives newest-first, then A→Z, like every other sort. And both node screens
pluralise: "1 node below threshold omitted".

### The test that let #4 through

`test_no_table_row_overruns_the_terminal` built five views in its helper and then
asserted over `("overview", "list")` — so the node table was exempt from the
invariant it was breaking, while the sibling rule test iterated all five and could
not catch it (a rule is drawn from the widest *row*). It now iterates every view,
and the helper carries a `nodes-long-names` view whose node names are 26
characters, because the demo's are 12 and that is what let a fixed `%-16s` survive
two audits.

This is the third round in which a *test* was the problem — after
`test_short_rows_do_not_crash` (a call compared with itself) and
`test_a_log_suffixed_name_is_answered_without_a_stat` (which asserted the very
behaviour that caused defect #11 of round two). Worth naming as a pattern: this
suite's failures are not missing tests but tests that assert less than they
appear to.

---

## Open

Two things are deliberately not fixed, named rather than left implied.

**The job screen's gauges and detail rows below ~96 columns.** One reviewer
reproduced `JobScreen`'s `resource_rows` gauges (fixed at 18 cells plus label and
detail) and its pair rows soft-wrapping to column 0 at a 60-column terminal. The
pair-row half shares a mechanism with #10 and was fixed with it. The gauge half
needs a width-adaptive bar and is a real change to the row idiom this tool shares
with slurmwatch, so it wants its own decision, not a drive-by. It was raised by one
reviewer of three and never put to a second panel.

**`--demo` still ignores `-S` and `-E`.** Unlike `-p` and `-u`, the window is not
silently discarded: the screen says "synthetic demo data" instead of a date range,
so the output does not claim a filter it did not apply. Left alone.

---

## Consequence for the numbers

Fixing 1 lowers `--time` advice for any workload holding a hung timeout at a
larger limit than its real ones. Fixing 11 raises `read_bytes`, `write_bytes`,
`io_bytes` and `io_rate` for any multi-step job — most `sbatch` scripts with more
than one `srun` — and will make `io-heavy` fire where it previously did not; it
also *lowers* them for any job whose `.extern` was over-reporting. Fixing 12
reorders same-day groups under `--sort recent`. The rest change presentation, exit
codes, or how long a log scan takes.
