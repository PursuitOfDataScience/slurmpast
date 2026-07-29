<h1 align="center">slurmpast</h1>

<p align="center">
  <strong>How your finished Slurm jobs actually ran — and what the next one should ask for.</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/slurmpast/"><img src="https://img.shields.io/pypi/v/slurmpast.svg" alt="PyPI"></a>
  <a href="https://github.com/PursuitOfDataScience/slurmpast/actions/workflows/ci.yml"><img src="https://github.com/PursuitOfDataScience/slurmpast/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/tests-791-brightgreen.svg" alt="791 tests">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT License">
</p>

<p align="center">
  <img src="assets/screenshot-overview.svg" width="900" alt="slurmpast overview: finished jobs rolled into workloads, ranked by resource use.">
</p>

```bash
pip install slurmpast
```

```bash
slurmpast              # dashboard, last 7 days
slurmpast --sizing     # what to request next time, per workload
slurmpast 51170455     # one job, every field Slurm recorded
slurmpast --demo       # no Slurm to hand? synthetic cluster
sp                     # short alias
```

`enter` open · `q` back · digits jump to a row · `/` search · `f` filter · `s` sort ·
`n` nodes · `p` patterns · `y` copy · `?` help

**Before** the run, [`slurmate`](https://github.com/PursuitOfDataScience/slurmate)
builds the request. **During** it,
[`slurmwatch`](https://github.com/PursuitOfDataScience/slurmwatch) watches.
**After** it, `slurmpast` tells you what happened and what to change.

---

## What to request next time

Over-requesting reserves capacity nobody else can use; under-requesting kills the
run. Your own history settles both.

```
argonne35-pretrain   test · 101 runs
  --time            raise to 10:00:00   (requested 8h05m, observed 7h58m03s at p95)
      p95 of 90 completed runs is 7h58m03s (longest 7h58m23s); +25% headroom.
  --mem             already about right
  --cpus-per-task   already about right
  #SBATCH --time=10:00:00
```

That workload was running on a **seven-minute margin**. Four rules keep the advice
honest: a TIMEOUT never sizes walltime *down*, a hung run is not evidence of
needing more time, an OOM kill outranks `MaxRSS`, and below three usable runs it
says *not enough evidence* rather than guessing.

## One job

<p align="center">
  <img src="assets/screenshot-job.svg" width="900" alt="One finished job: time, CPU and memory as gauges, then every field Slurm recorded.">
</p>

Three gauges, because a bar needs a ceiling to be a fraction of. Kernel share,
disk rate and GPU count have none, so they print as numbers — an unfillable
`░░░░` reads as a measured zero. Below that: every field Slurm kept, the log
excerpts if the paths are still on disk, then the findings.

Same row idiom as `slurmwatch`, so a job you watched running looks like the same
object afterwards.

## Failure, across runs

<p align="center">
  <img src="assets/screenshot-nodes.svg" width="900" alt="Per-node failure rates with Wilson intervals and a ready-to-paste --exclude.">
</p>

`seff` describes one job and `slurmwatch` one live run. Neither can say *"you
submitted this 115 times and it died 99 times."*

- **Hand-searched memory.** One real series walked `48G → 32G → 32G → 17G → 12G →
  12G → 14G → 16G → 18G`, then succeeded at 32G — a value that had already OOM'd,
  proving `--mem` was never the variable.
- **Nodes that eat jobs**, controlled for workload. Uncontrolled, one node looked
  25% bad almost entirely because a buggy campaign landed there — so a node is
  called `worse` only when its Wilson interval clears the baseline.

## Numbers you can trust

Three places `seff` and a naive `sacct --format` go wrong — each found on a real
record, each pinned by a test naming the job id:

- `ReqMem` is `0n` on **2,130 of 6,574** jobs — the real ceiling is in `AllocTRES`.
- `AllocTRES` `mem=` is the **allocation total**, while `--mem` and the cgroup are
  per *node*, so dividing `MaxRSS` by it understates memory by the node count.
- `State=RUNNING, End=Unknown` months after death makes `Elapsed` *now − start*;
  one such record was 65% of a GPU-hour total.

A value that cannot be read prints `n/a`, never `0`. Four more traps, and the
full 85-field extraction table, are in **[docs/details.md](docs/details.md)**.

## Any Slurm cluster

Developed against Slurm 20.11.8, calibrated to no single site. Renamed fields
(`Reserved` → `Planned` in 23.02), `SLURM_TIME_FORMAT`, pipes in `--constraint`,
hostlists like `unit[0-31]rack[0-41]`, three GPU spellings, a missing `--me` —
each negotiated rather than assumed, each a test in `tests/test_portability.py`.
[Details](docs/details.md#any-slurm-cluster).

What is *measured* is portable; what is *judged* is not. The thresholds are
conservative heuristics from one cluster's history, each a named constant.

## As a library

The analysis modules import no third-party package.

```python
from slurmpast import History, Sacct
from slurmpast.sizing import recommend

history = History(Sacct().history(user="you", since="now-30days"))
for advice in recommend(history.groups[0].jobs):
    print(advice.flag, advice.verdict, advice.suggestion)
```

`--json` emits all 174 values per job; a test fails if a field is read but never
surfaced.

---

Python 3.10–3.13 · Textual 0.89–8.2 · no Slurm needed to run the tests · MIT.
Mouse capture is off by default, so text selection works as it does anywhere else.
