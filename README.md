<h1 align="center">slurmpast</h1>

<p align="center">
  <strong>How your finished Slurm jobs actually ran — and what the next one should ask for.</strong>
</p>

<p align="center">
  <a href="https://github.com/PursuitOfDataScience/slurmpast/actions/workflows/ci.yml"><img src="https://github.com/PursuitOfDataScience/slurmpast/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT License">
  <img src="https://img.shields.io/badge/tests-473-brightgreen.svg" alt="473 tests">
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
  ● TIME   ████████████████▉░    94.0%   · 1h52m49s of 2h00m00s
  ● CPU    █████████████▎░░░░    73.5%   · 5h31m39s of 7h31m16s over 4 cores
  ● KERNEL ▉░░░░░░░░░░░░░░░░░     4.7%   · 15m36s of 5h31m39s in the kernel
  ● MEM    ████████████████▋░    92.3%   · 184.6 GiB of 200.0 GiB, peak on midway3-0600
  ● GPU    ░░░░░░░░░░░░░░░░░░      n/a   · 3 devices, 5.6 GPU-hours — not recorded by Slurm
  ● DISK   ░░░░░░░░░░░░░░░░░░  35.5 MiB/s  · read 105.0 GiB, wrote 130.0 GiB
```

Below that: every field Slurm recorded, then the findings.

## Why the numbers differ from `seff`

Six traps, each found on a real record, each with a regression test naming the
job id:

| Trap | Reality |
|---|---|
| `ReqMem` is `0n` on **2,130 of 6,574** jobs | the real ceiling is in `AllocTRES` |
| `MaxRSS` reports **51.25 GiB against a 40 GiB limit** that OOM-killed | it sums RSS across the process tree, double-counting shared pages |
| `MaxRSS` differs **4000×** between steps of one job | take the max, not a step |
| `TotalCPU` exists **only on steps** | read it from `.batch` |
| `State=RUNNING, End=Unknown` months after death | `Elapsed` becomes *now − start*; one record was 65% of a GPU-hour total |
| `sacct --state=X` returns **zero rows** without `-E` | always pass an end time |

A value that cannot be read prints `n/a`, never `0`.

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

All 107 `sacct` fields that carry a distinct measurement — 2.26s over seven
months, against 1.38s for a minimal 27.

| group | captured |
|---|---|
| **cpu** | total, **user vs kernel split**, utilization, frequency, per-task min/average, slowest task with its node |
| **memory** | limit, peak with the **node and task that hit it**, average, task imbalance, virtual size, page faults |
| **filesystem** | **read and write separately**, rate |
| **timing** | submit/start/end, elapsed, limit, queue wait, **backfill vs main scheduler**, priority |
| **outcome** | state, exit code and signal, worst step exit, reason |
| per step | all of the above, for `.batch`, `.extern` and each srun step |

Two were entirely invisible with a narrow `--format`: **disk writes** (one run
read 112 GB and wrote 139 GB) and the **user/kernel CPU split** (791 of 6,582
jobs exceed 30% kernel time — syscall overhead no other tool surfaces).

`--json` emits all of it — 165 values per job. Nothing is captured and then hidden; a test fails if a field is read but never surfaced.

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

Developed against Slurm 20.11.8 and Textual 0.89–8.2; CI covers Python 3.10–3.13,
both Textual ends, and a no-Slurm machine. Field availability varies by Slurm
version, so fields are probed and unsupported ones dropped.

Thresholds are heuristics tuned against one cluster's history — conservative, but
not validated elsewhere. `--nodes` is the piece most likely to need recalibration.

MIT.
