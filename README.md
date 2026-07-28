<h1 align="center">slurmpast</h1>

<p align="center">
  <strong>Why did your Slurm jobs fail? A post-mortem dashboard for finished jobs.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT License">
  <img src="https://img.shields.io/badge/tests-308-brightgreen.svg" alt="308 tests">
  <img src="https://img.shields.io/badge/status-beta-orange.svg" alt="Beta">
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/PursuitOfDataScience/slurmpast/main/assets/demo.gif" width="900" alt="slurmpast dashboard: finished jobs rolled into workloads ranked by resources burned, drilling into one workload and then into a single job's full post-mortem — CPU split by user and kernel, memory peak with the node and task that hit it, disk read and write, each with a gauge — then the cross-run patterns and the workload-controlled node reliability table.">
</p>

**Before** the run, `slurmate` builds the request. **During** it, `slurmwatch`
watches. **After** it, `slurmpast` tells you what actually happened.

```bash
slurmpast                # dashboard over the last 7 days
slurmpast -S now-30days  # ... or a month
slurmpast 51170455       # one job, in detail
sp                       # short alias
```

`seff` will tell you a job used 92% of its memory. It is often wrong, and it
never tells you *why* the job died. `sacct` has the answer buried in 90 columns
of pipe-delimited text with four different time formats and at least five ways
to produce a confidently wrong number.

<details>
<summary><b>Screenshots</b> — exported from the running app (click to expand)</summary>

<p align="center">
  <img src="https://raw.githubusercontent.com/PursuitOfDataScience/slurmpast/main/assets/screenshot-overview.svg" width="860" alt="Overview: workloads ranked by resources burned, with outcome ribbons, failure rate, idle count and last run.">
  <br><em>Overview — 58 jobs rolled into workloads, ranked by cost, not count.</em>
</p>
<p align="center">
  <img src="https://raw.githubusercontent.com/PursuitOfDataScience/slurmpast/main/assets/screenshot-job.svg" width="860" alt="One job's post-mortem: timing, CPU with the user/system split, memory with peak node and task, filesystem read and write, each with a gauge, then the findings.">
  <br><em>One job — every field Slurm recorded, with the verdict underneath.</em>
</p>
<p align="center">
  <img src="https://raw.githubusercontent.com/PursuitOfDataScience/slurmpast/main/assets/screenshot-patterns.svg" width="860" alt="Cross-run patterns: a workload that failed repeatedly at an unchanged time limit, and a memory request being hand-searched.">
  <br><em>Cross-run patterns — what no single job can show you.</em>
</p>
<p align="center">
  <img src="https://raw.githubusercontent.com/PursuitOfDataScience/slurmpast/main/assets/screenshot-nodes.svg" width="860" alt="Node reliability controlled for workload, with Wilson confidence intervals and a ready-to-paste SBATCH exclude line.">
  <br><em>Node reliability — workload-controlled, with confidence intervals.</em>
</p>

Rendered from synthetic data (`slurmpast --demo`), which is why the header reads
<code>SYNTHETIC DEMO DATA</code>. Regenerate the GIF with
<code>vhs assets/demo.tape</code>.

</details>

## Built for a real history, not a demo

A working researcher accumulates **6,581 jobs in seven months**. Two facts
measured on exactly that history shape the whole design:

**A flat list of 6,581 jobs is not an interface.** It hands the selection
problem back to you. So the landing screen is not a job list — it is a
**workload rollup**, ranked by resources burned:

```
  #    WORKLOAD              PART     RUNS   FAILED   IDLE      BURNED  LAST RUN   VARIANTS
  1    node-evaluation       test     1101    14.6%    149  3089 gpu-h  2026-05-30
  2    node-testing          test       62    74.3%     27   785 gpu-h  2026-03-05
  3    midtrain              test      155     9.9%     13  1005 gpu-h  2026-07-03
  4    argonne#-pretrain     test       99     1.1%      8   830 gpu-h  2026-07-27  2 names
  5    amd_reserve           test       18   100.0%     15 12246 core-h 2026-07-21
  …  579 more workloads (4254 runs) holding 18.5% of the resource
```

Ranking is by **cost, not count** — a 5-run group that burned 400 GPU-hours
outranks 400 two-second probes. On real data the **top 20 rows cover 93.4% of
all weighted resource**, so truncation is the right default. What is below the
fold is stated, never silently dropped.

**Job names encode parameters, so raw names barely group.** 1,624 distinct names
across those 6,581 jobs rolls up to 1,687 groups — no better than the flat list.
Collapsing digit runs (`s1e20`, `s2e47` → `s#e#`) folds it to 592, and the
`VARIANTS` column tells you when a pattern is covering several real names.

**No cache, no store.** The full seven-month query is **1.54 s** and the index
builds in **0.04 s**, which does not justify a database — and a database buys
staleness bugs, a schema to version, and an invalidation policy to get wrong.
One query on a worker thread, everything else in memory. Cross-run patterns are
computed lazily (0.02 s) and job logs are read only when you open a job, because
scanning 6,581 logs eagerly would dominate startup for data you mostly never
look at.

## The interface

Same shape as `slurmwatch`: a dashboard you land on, drill-down on single keys,
`q`/`escape` to come back, digits to jump straight to a row.

```
  Overview  ──enter──▶  Workload  ──enter──▶  Job
     │                                        (post-mortem)
     └── n nodes   p patterns   / search   f filter   s sort   a all jobs   r reload
```

| key | |
|---|---|
| `enter` / `→` | open the selected row |
| `q` / `escape` / `←` | back, or quit from the overview |
| `1`-`9`… | jump to a row by number (multi-digit) |
| `/` | search name, job id, state or node |
| `f` `s` | cycle filter / sort |
| `y` `Y` | copy the selected row · copy the whole view |
| `n` `p` `a` | nodes · patterns · flat job list |
| `?` | help |

**Getting text out.** Dragging to select does not work — a TUI takes the
terminal's mouse, and Textual's in-app selection API only exists in 1.x. Three
ways out, in order of convenience:

- **`y` / `Y`** — copies via OSC 52, which reaches the clipboard on the machine
  you are *sitting at*, not the login node. On a job screen, `y` copies the
  entire post-mortem, paste-ready. Every copy is also written to
  `~/.cache/slurmpast/clip.txt`, because OSC 52 fails silently on some
  terminals and needs `set -g set-clipboard on` inside tmux — so the feature
  never half-works with no way to tell.
- **Hold `Shift`** (most terminals) or `Option` (macOS) and drag, to bypass
  mouse reporting and select natively.
- **`--plain` / `--json`** — for anything scripted, skip the question entirely.

Everything is also plain text, because a post-mortem you cannot paste into a
ticket is half a tool: `--plain`, `--overview`, `--patterns`, `--nodes`,
`--json`.

## What it actually catches

### A timeout is not evidence that the job needed more time

```
job 47865145  TIMEOUT
    walltime      30m26s of 30m00s   (101.4%)
    cpu time      0.54s of 3h02m42s   (0.0% over 6 cores)

  [FAIL] Hit the wall clock without ever running
        Held the allocation for 30m26s but consumed only 0.54s of CPU. A process
        that never accumulates CPU time is blocked, not slow.
        → Do NOT raise --time; a longer limit buys a longer hang.
```

That workload hit the same 30-minute wall **99 times out of 115 submissions**,
every one with an unchanged `--time`, for ~50 GPU-hours. The obvious advice —
raise the limit — would have bought 99 longer hangs. Only the CPU counter
separates a hang from a job that genuinely ran out of clock, and every walltime
tool that reads `Elapsed` alone gets this backwards.

### Failure repeated across runs

`seff` and `reportseff` describe one job; `slurmwatch` describes one live run.
Neither can say *"you have submitted this 115 times and it died 99 times."*

### A memory request being hand-searched

```
  [FAIL] Memory request is being hand-searched
        8 OOM kills with --mem walking 48G → 32G → 32G → 17G → 12G → 12G → 14G
        → 16G → 18G. Job 52139773 then COMPLETED at 32G — a value that had
        already OOM'd.
        → --mem is not the deciding variable: the same request both failed and
          succeeded. Something else changed.
```

### Which nodes eat your jobs

```
  controlled for workload: only node-evaluation counted (placement is not random)
  baseline 13.6% over 1098 placements

  NODE                     N       RATE            95% CI  VERDICT
  midway3-0432         12/30      40.0%    24.6 – 57.7%     worse
  midway3-0385         19/53      35.8%    24.3 – 49.3%     worse
  midway3-0602        36/403       8.9%     6.5 – 12.1%     better

  #SBATCH --exclude=midway3-[0385,0432,0601,0605]
```

Beyond the classic failure modes it also flags what the wide extraction makes
visible: kernel-heavy CPU, sustained I/O, page thrashing, memory reserved and
never touched, uneven memory across tasks, and — on multi-task steps — a
**straggler**, the rank that did far less work than its peers while every other
rank waited on it.

The confound is real and was measured: uncontrolled, one node looked 25% bad
almost entirely because a buggy campaign landed there. So the workload is held
fixed, a Wilson interval is always shown, and a node is only called `worse` when
its interval clears the baseline. Otherwise it says `inconclusive`.

## Everything it extracts

Slurm 20.11 exposes **107 accounting fields**; `slurmpast` reads every one that
carries a distinct measurement. The cost was measured before committing to it:
all 107 fields over seven months take **2.26 s** against 1.38 s for a minimal
27 — completeness is nearly free, and you never have to re-run with a wider
`--format` because the number you wanted was not collected.

```
  cpu
    total            ██████████────  5h31m39s of 7h31m16s allocated  (73.5% over 4 cores)
    user / system    █─────────────  5h16m03s / 15m36s   (kernel 4.7%)
    frequency        11K
    tasks            1
  memory
    limit            200.0 GiB
    peak (MaxRSS)    █████████████─  184.6 GiB   (92.3%)
    peak on          midway3-0600 task 0
    average          184.6 GiB
    virtual          1.7 TiB   (9x resident — address space, not memory used)
  filesystem
    read             105.0 GiB
    written          130.0 GiB
    rate             35.5 MiB/s sustained
```

| group | what is captured |
|---|---|
| **cpu** | total, **user vs system split**, utilization, allocated core-seconds, average frequency, per-task min/average, slowest task with its node and id |
| **memory** | limit, peak RSS with the **node and task that hit it**, average RSS, task imbalance, per-step spread, virtual size and its ratio to resident, page faults |
| **filesystem** | **read and write separately**, combined volume, sustained rate |
| **timing** | submit / eligible / start / end, elapsed, limit, **queue wait**, suspended time, **whether backfill or the main scheduler placed it**, priority |
| **shape** | nodes, cpus, tasks, gpus, requested vs allocated TRES, constraints |
| **outcome** | state, exit code and signal, **worst step exit code**, reason |
| **context** | cluster, account, QOS, association, reservation, workdir, comment |
| **per step** | every measurement above, for `.batch`, `.extern` and each srun step |

Two of those were entirely invisible before and change conclusions:

- **Disk writes.** Reading only `TRESUsageInTot` reports reads and silently
  drops writes. One real run read 112 GB and **wrote 139 GB** — more than half
  the traffic was missing.
- **The user/system CPU split.** A healthy run here sits at ~5% kernel time.
  **791 of 6,582 jobs exceed 30%**, which is syscall overhead — many small
  reads, metadata churn — and it is invisible in the single `TotalCPU` figure
  every other tool reports.

Where Slurm offers an integer-seconds field (`ElapsedRaw`, `CPUTimeRAW`) it is
preferred over parsing the formatted string, removing the `MM:SS.mmm` ambiguity
outright. `TimelimitRaw` is in *minutes* — the one exception, handled.

## Why the numbers differ from `seff`

Six traps, each found on a real record, each with a regression test naming the
job id:

| Trap | Reality | Consequence if naive |
|---|---|---|
| `ReqMem` reads `0n` on **2,130 of 6,574** jobs | the ceiling is in `AllocTRES` (`mem=80G`) | `seff` reports a 0-byte limit and every MaxRSS looks like an overrun |
| `MaxRSS` **51.25 GiB against a 40 GiB limit** that OOM-killed (43742638) | `jobacct_gather/linux` sums RSS across the process tree | you size `--mem` up from a number that is not a working set |
| `MaxRSS` differs **4000×** between steps of one job (51709094) | take the max across steps | reading one step is wrong by three orders of magnitude |
| `TotalCPU` exists **only on steps** | read it from `.batch` | utilization is `None` everywhere, so hangs stay invisible |
| `State=RUNNING, End=Unknown` months after death (50108238) | `Elapsed` becomes *now − start*: 62 days | one phantom record was **65%** of a GPU-hour total |
| `sacct --state=X` returns **zero rows** without `-E` | always pass an end time | `--failed` reports "no failures" and you believe it |

Plus `00:00.539` is `MM:SS.mmm` — half a second. Parsed as `HH:MM` it becomes 0
and the hang diagnosis inverts.

A value that cannot be read prints `n/a`, never `0`. A fabricated zero is
indistinguishable from a real measurement.

## Restraint

Thresholds were tuned against the full 6,582-job history, not guessed. Two rules
were caught firing as noise and fixed: the MaxRSS step-spread finding appeared on
**77% of jobs** because `.extern` is structurally tiny (now compared only between
steps that ran something → 5.5%), and page-fault detection fired at 15 faults,
which is ordinary startup (now 1,000).

The tool stays silent on a sound request. A job that used 94% of its walltime
gets no comment, because a tool that nags there gets ignored on the one that was
1,100× over. Jobs under two minutes are not judged on core usage — startup
dominates. Repeat-failure findings are capped at four, ranked by resources
burned, with the remainder counted. Cancellations are reported as ambiguous and
excluded from failure statistics: a deliberate kill and an abandoned run are
identical in accounting.

## Install

```bash
pip install slurmpast
```

No Slurm to hand? `slurmpast --demo` runs the whole dashboard against a synthetic
history built into the package, labelled as such throughout. It is also what the
demo tape records, so the GIF is reproducible on any machine.

Python 3.10+, Textual (same floor as `slurmwatch`, so they share one install).
The analysis modules — `sacct`, `diagnose`, `patterns`, `nodes`, `index` — import
no third-party package and are usable as a library without a UI:

```python
from slurmpast import Sacct, History, diagnose
history = History(Sacct().history(user="you", since="-30days"))
for group in history.groups[:5]:
    print(group.name, group.failed, group.gpu_hours)
```

## Portability

Field availability varies by Slurm version, and one unknown field makes `sacct`
reject the whole query — so fields are probed against `sacct --helpformat` and
unsupported ones dropped. Developed against **Slurm 20.11.8**, where
`StdOut`/`StdErr`/`SubmitLine` do not exist, which is why log discovery searches
`WorkDir` and conventional subdirectories and admits that it guessed. With no
log found, the CUDA-OOM and traceback rules stay silent rather than speculate.

## Status

Beta. 308 tests. The diagnosis thresholds are heuristics drawn from one
cluster's measured history — conservative (an allocation must run 5 minutes *and*
use under 10 CPU-seconds before it is called a hang, ~20× margin over the
observed median) but not validated elsewhere. `--nodes` is the piece most likely
to need recalibration, and the GPU-hour↔core-hour exchange rate used for ranking
is a stated convention (`GPU_CORE_EQUIVALENT`), not a measurement — this cluster
defines no `TRESBillingWeights` on any of its 86 partitions.

## License

MIT.
