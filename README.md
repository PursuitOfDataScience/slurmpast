<h1 align="center">slurmpast</h1>

<p align="center">
  <strong>How your finished Slurm jobs actually ran — and what the next one should ask for.</strong>
</p>

<p align="center">
  <a href="https://github.com/PursuitOfDataScience/slurmpast/actions/workflows/ci.yml"><img src="https://github.com/PursuitOfDataScience/slurmpast/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT License">
  <img src="https://img.shields.io/badge/tests-785-brightgreen.svg" alt="785 tests">
</p>

<p align="center">
  <img src="assets/screenshot-overview.svg" width="900" alt="slurmpast overview: finished jobs rolled into workloads, ranked by resource use.">
</p>

**Before** the run, [`slurmate`](https://github.com/PursuitOfDataScience/slurmate)
builds the request. **During** it,
[`slurmwatch`](https://github.com/PursuitOfDataScience/slurmwatch) watches.
**After** it, `slurmpast` tells you what happened and what to change.

```bash
pip install slurmpast
```

```bash
slurmpast                  # dashboard, last 7 days
slurmpast --sizing         # what to request next time, per workload
slurmpast 51170455         # one job, every field Slurm recorded
sp                         # short alias
```

Keys: `enter` open · `q` back · digits jump to a row · `/` search · `f` filter ·
`s` sort · `n` nodes · `p` patterns · `y` copy · `?` help.
No Slurm to hand? `slurmpast --demo`.

---

## What to request next time

The reason to read finished jobs. Over-requesting narrows which nodes can host a
job and reserves capacity nobody else can use; under-requesting kills the run.
Your own history settles both.

```
argonne35-pretrain   test · 101 runs
  --time            raise to 10:00:00   (requested 8h05m, observed 7h58m03s at p95)
      p95 of 90 completed runs is 7h58m03s (longest 7h58m23s); +25% headroom.
  --mem             already about right
  --cpus-per-task   already about right
  #SBATCH --time=10:00:00
```

That workload was running on a **seven-minute margin**. Four rules keep the
advice honest:

- A **TIMEOUT never sizes walltime down** — its elapsed is truncated at the
  limit, so it bounds the true runtime only from below.
- A **hung run is not evidence of needing more time.** One real workload hit a
  30-minute wall 99 times on a median of 0.56 CPU-seconds; a longer limit buys a
  longer hang.
- An **OOM kill outranks MaxRSS.** It is an event, not a sample.
- Below three usable runs it says **"not enough evidence"** rather than guessing.

## One job

Same row idiom as `slurmwatch`, so a job you watched running looks like the same
object afterwards. The marker carries the resource's identity, the bar and the
number carry the magnitude, and the verdict lives in the findings below.

```
  ● TIME   ████████████████▉░        94.0%   · 01:52:49 of the 02:00:00 limit
  ● CPU    █████████████▎░░░░        73.5%   · 2.9 of 4 cores busy
  ● MEM    ████████████████▋░        92.3%   · 184.6 GiB of the 200.0 GiB limit
```

Three rows, because a gauge needs a ceiling to be a fraction of. Kernel share,
disk rate and GPU count have none, so they are printed as numbers below rather
than as bars that can never fill — an unfillable `░░░░` reads as a measured zero.

Below that: every field Slurm recorded, then the findings.

```
  gpu
    devices          3                       gpu-hours        5.6
    utilization      87.4%
    device memory    35.4 GiB peak
```

That `utilization` is real wherever `gres.conf` sets `AutoDetect=nvml`. Where the
cluster does not gather it, the row says so and names the setting instead of
printing a zero.

## Why the numbers differ from `seff`

Seven traps, each found on a real record, each with a regression test naming the
job id:

| Trap | Reality |
|---|---|
| `ReqMem` is `0n` on **2,130 of 6,574** jobs | the real ceiling is in `AllocTRES` |
| `AllocTRES` `mem=` is the **allocation total** | `--mem` and the cgroup are per *node*; a 2-node `--mem=8G` job records `mem=16G`, so dividing MaxRSS by it understates memory by the node count |
| `MaxRSS` reports **51.25 GiB against a 40 GiB limit** that OOM-killed | under `jobacct_gather/linux` it sums RSS across the process tree, double-counting shared pages — so the caveat is read from your `JobAcctGatherType`, not assumed |
| `MaxRSS` differs **4000×** between steps of one job | take the max, not a step |
| `TotalCPU` exists **only on steps** | read it from `.batch` |
| `State=RUNNING, End=Unknown` months after death | `Elapsed` becomes *now − start*; one record was 65% of a GPU-hour total |
| `sacct --state=X` returns **zero rows** without `-E` | always pass an end time |

A value that cannot be read prints `n/a`, never `0`.

## Any Slurm cluster

Developed on one cluster, but nothing here is calibrated to it. Every place the
scheduler differs between sites is negotiated rather than assumed, and each of
these is a regression test in `tests/test_portability.py`:

| What varies | What it does about it |
|---|---|
| **Field names change.** Slurm 23.02 renamed `Reserved` → `Planned` | asks for whichever spelling your `sacct` accepts and reads it back under one name. Treating it as merely *optional* silently dropped queue wait on every cluster from 23.02 on |
| **`SLURM_TIME_FORMAT`** rewrites every timestamp | pinned to `standard` for the child process. A site exporting `relative` turns `2026-04-29T14:55:48` into `29 Apr 14:55`, which stops dates parsing and makes the chronological sort alphabetical on a month name |
| **`--constraint="v100\|a100"`** puts a pipe in a column, and `--parsable2` does not escape it | asks for an ASCII unit separator via `--delimiter` (in sacct since 17.11), falling back if absent. A pipe in field 32 shifted every memory, CPU and disk column after it |
| **Hostlists** can be `unit[0-31]rack[0-41]`, `node[0001-0010]-int`, `cn_[01-02]` | full expansion, differential-tested against `scontrol show hostnames`. The multi-range form used to yield `unit0rack[0-2]` *as a node name*, hiding every node in such an allocation |
| **GPUs** appear as `gres/gpu=4`, `gres/gpu:a100=4`, or pre-20.11 `AllocGRES=gpu:4` | all three read; typed entries summed |
| **`gres/gpuutil`** is gathered wherever `gres.conf` sets `AutoDetect=nvml` | real GPU utilization and peak HBM where recorded — and the idle-GPU finding becomes a measurement instead of an inference from host CPU |
| **`JobAcctGatherType`** decides what MaxRSS *is* | `jobacct_gather/cgroup` gives a genuine high-water mark, so the "double-counts shared pages" warning is withheld there rather than repeated |
| **`StdOut`/`StdErr`** exist from Slurm 21.08 | used, with `%j`/`%A`/`%a`/`%x`/`%N` expanded, before falling back to guessing a filename |
| **`--me`** needs Slurm 20.02 | falls back to `-u <you>`, not to an unfiltered `squeue` over the whole cluster |
| **Accounting may be off**, or `sacct` absent | a one-line explanation and exit 2, never a traceback; the query has a timeout so an unreachable `slurmdbd` cannot hang the dashboard |

`slurmpast --demo` pins a synthetic cluster config too, so the demo looks the
same on a login node and on a laptop.

## Built for a real history

6,581 jobs in seven months. A flat list of that is not an interface, so the
landing screen is a **workload rollup ranked by resource use** — a 5-run group
that cost 400 GPU-hours outranks 400 two-second probes. The top 20 rows carry
93.4% of it, and what is below the fold is stated rather than dropped.

Job names encode parameters, so raw names barely group: 1,624 distinct names roll
up to 1,687 groups. Collapsing digit runs (`s1e20`, `s2e47` → `s#e#`) folds that
to 592, and a `NAMES` column says how many real names a pattern covers.

No cache: the full seven-month query is 1.54s and the index builds in 0.04s,
which does not justify a database. Logs are read only when you open a job.

## Everything it extracts

85 `sacct` fields — every one of the 107 this Slurm offers that carries a
distinct measurement, with pure redundancy (`DBIndex`, `BlockID`, duplicate
spellings of the same TRES) left out. The wide query costs 2.26s over seven
months against 1.38s for a minimal 27, so nobody has to re-run it because the
number they wanted was never collected.

| group | captured |
|---|---|
| **cpu** | total, **user vs kernel split**, utilization, frequency, per-task min/average, slowest task with its node |
| **memory** | ceiling **per node and per allocation**, peak with the node and task that hit it, average, task imbalance, virtual size, page faults |
| **filesystem** | **read and write separately**, rate |
| **gpu** | devices, GPU-hours, and **utilization and peak HBM where the site gathers them** |
| **timing** | submit/start/end, elapsed, limit, queue wait, **backfill vs main scheduler**, priority |
| **outcome** | state, exit code and signal, worst step exit, reason |
| **provenance** | work directory, recorded stdout/stderr paths, **the submit line itself** |
| per step | all of the above, for `.batch`, `.extern` and each srun step |

Two were entirely invisible with a narrow `--format`: **disk writes** (one run
read 112 GB and wrote 139 GB) and the **user/kernel CPU split** (791 of 6,582
jobs exceed 30% kernel time — syscall overhead no other tool surfaces).

`--json` emits all of it — 174 values per job. Nothing is captured and then hidden; a test fails if a field is read but never surfaced.

## Also finds

**Repeated failure.** `seff` describes one job; `slurmwatch` describes one live
run. Neither can say *"you submitted this 115 times and it died 99 times."*

**Hand-searched memory.** One real series walked `48G → 32G → 32G → 17G → 12G →
12G → 14G → 16G → 18G`, then succeeded at 32G — a value that had already OOM'd,
proving `--mem` was never the variable.

**Nodes that eat jobs**, controlled for workload, with Wilson intervals and a
ready-to-paste `--exclude`. Uncontrolled, one node looked 25% bad almost entirely
because a buggy campaign landed there — so a node is only called `worse` when its
interval clears the baseline.

## Notes

Selecting text just works: mouse capture is off by default, so your terminal
handles selection as it does anywhere else. `M` hands the mouse to the app;
`y`/`Y` copy via OSC 52 and also write `~/.cache/slurmpast/clip.txt`.

The analysis modules import no third-party package and work as a library:

```python
from slurmpast import History, Sacct
from slurmpast.sizing import recommend

history = History(Sacct().history(user="you", since="now-30days"))
for advice in recommend(history.groups[0].jobs):
    print(advice.flag, advice.verdict, advice.suggestion)
```

Developed against Slurm 20.11.8 and Textual 0.89–8.2; verified against the Slurm
documentation and release notes from 17.11 to 26.05, and against `scontrol show
hostnames` for node-name expansion. CI covers Python 3.10–3.13, both Textual
ends, and a no-Slurm machine.

What is *measured* is portable; what is *judged* is not. The thresholds — when a
CPU share is low, when kernel time is heavy, when a node counts as worse — are
heuristics from one cluster's history. They are conservative and each one is a
named constant, so recalibrating means editing a number rather than the logic.
`--nodes` is the piece most likely to need it.

MIT.
