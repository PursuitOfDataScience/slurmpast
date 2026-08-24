# Details

The long-form material behind the [README](../README.md): every trap that makes
`sacct` numbers wrong, every place clusters differ, and everything `slurmpast`
extracts. Each claim here corresponds to a regression test.

## Why the numbers differ from `seff`

Seven traps, each found on a real record, each with a test naming the job id:

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
| **`StdOut`/`StdErr`** exist from Slurm 24.05 | used, with `%j`/`%A`/`%a`/`%x`/`%N` expanded, before falling back to guessing a filename |
| **`--me`** needs Slurm 20.02 | falls back to `-u <you>`, not to an unfiltered `squeue` over the whole cluster — and is only asked when the account being reconciled *is* yours, so `-u alice` does not check alice's records against your queue |
| **Accounting can be slow.** A big site's `sacct` over a wide window can take minutes | one query budget, 300s by default and settable with **`SLURMPAST_TIMEOUT`** (seconds, must be positive). A value that is not a positive number is refused by name rather than quietly replaced by the default, because a setting that does not do what it says and does not say so is worse than one that is not offered |
| **`PrivateData=jobs`** hides other accounts | `-u alice` and `--all-users` are one flag either way; at such a site sacct returns an empty set with no error, so the "no jobs for alice" line names the scope it asked about rather than reading as your own quiet window |
| **Accounting may be off**, or `sacct` absent | a one-line explanation and exit 2, never a traceback; the query has a timeout so an unreachable `slurmdbd` cannot hang the dashboard |

`slurmpast --demo` pins a synthetic cluster config too, so the demo looks the
same on a login node and on a laptop.

Verified against the Slurm documentation and release notes from 17.11 to 26.05,
and against `scontrol show hostnames` for node-name expansion. CI covers Python
3.10–3.13, both Textual ends, and a no-Slurm machine.

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

`--json` emits all of it — 99 values per job, plus 40 for every step. Nothing is
captured and then hidden: a test reads `cli._job_json` itself and holds every
`Job` and `Step` value to it, so a measurement that does not reach the payload
has to be argued for by name in that test's exemption list rather than dropped.

GPU `utilization` is real wherever `gres.conf` sets `AutoDetect=nvml`. Where the
cluster does not gather it, the row says so and names the setting instead of
printing a zero.

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

## Also finds

**Repeated failure.** `seff` describes one job; `slurmwatch` describes one live
run. Neither can say *"you submitted this 115 times and it died 99 times."*

**Hand-searched memory.** One real series walked `48G → 32G → 32G → 17G → 12G →
12G → 14G → 16G → 18G`, then succeeded at 32G — a value that had already OOM'd,
proving `--mem` was never the variable.

**Nodes that eat jobs**, controlled for workload, with Wilson intervals and a
ready-to-paste `--exclude`. Uncontrolled, one node looked 25% bad almost entirely
because a buggy campaign landed there — so a node is only called `worse` when its
interval clears the baseline *and* the claim survives the fact that every other
node in the table was tested too. That second half was measured, not assumed: with
every node given one identical true failure rate, the interval test alone offered
an innocent node to `--exclude` in 54.8% of 20-node tables and 77.8% of 40-node
ones, because its error rate was a function of how many nodes were tested. A
Benjamini–Hochberg correction across the rows holds that near 2.7% and, more to
the point, flat as the table grows.

## Gauges

Three rows — time, CPU, memory — because a bar needs a ceiling to be a fraction
of. Kernel share, disk rate and GPU count have none, so they are printed as
numbers rather than as bars that can never fill; an unfillable `░░░░` reads as a
measured zero.

Same row idiom as `slurmwatch`, so a job you watched running looks like the same
object afterwards.

## Thresholds

What is *measured* is portable; what is *judged* is not. The thresholds — when a
CPU share is low, when kernel time is heavy, when a node counts as worse — are
heuristics from one cluster's history. They are conservative and each one is a
named constant, so recalibrating means editing a number rather than the logic.
`--nodes` is the piece most likely to need it.

## Copy and selection

Mouse capture is off by default, so your terminal handles text selection as it
does anywhere else. `M` hands the mouse to the app; `y`/`Y` copy via OSC 52 and
also write `~/.cache/slurmpast/clip.txt`.
