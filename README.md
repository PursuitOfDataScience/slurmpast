<div align="center">

# 📉 slurmpast

**Why your Slurm jobs failed, and what to ask for next time.**

<a href="https://github.com/PursuitOfDataScience/slurmpast/actions/workflows/ci.yml"><img src="https://github.com/PursuitOfDataScience/slurmpast/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
<a href="https://pypi.org/project/slurmpast/"><img src="https://img.shields.io/pypi/v/slurmpast.svg" alt="PyPI"></a>
<a href="https://pypi.org/project/slurmpast/"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/PursuitOfDataScience/slurmpast/badges/downloads.json" alt="PyPI downloads per month"></a>

<img src="assets/demo.gif" width="900" alt="The slurmpast dashboard: finished jobs grouped into workloads, filtered to failures, then one job's report showing it used all its time at 0% CPU, meaning it hung rather than ran out of time, then per-node failure rates.">

</div>

## ✨ Install

```bash
pip install slurmpast
```

## 🧰 Use

```bash
slurmpast              # dashboard, last 7 days
slurmpast --sizing     # what to request next time
slurmpast 51170455     # one job, every field Slurm recorded
slurmpast --demo       # no Slurm? try a synthetic cluster
slurmpast -u alice     # someone else's history
slurmpast --all-users  # every account on the cluster
sp                     # short alias
```

`enter` opens · `q` goes back · `/` searches · `f` filters · `s` sorts · `?` lists every key

## 🎯 What to request next time

```
argonne35-pretrain   test · 101 runs
  --time            raise to 10:00:00   (from 08:05:00)
      longest of 90 completed runs took 07:58:23.
  --mem             already about right
  #SBATCH --time=10:00:00
```

That job had seven minutes to spare. With fewer than three usable runs, it says *not enough
evidence* instead of guessing.

<details>
<summary><b>More screens</b></summary>

<img src="assets/screenshot-overview.svg" width="860" alt="Overview: finished jobs grouped into workloads, ranked by resource use, each with its failure count and last run.">
<img src="assets/screenshot-workload.svg" width="860" alt="One workload: every run of it, with a repeat-failure warning and sizing advice.">
<img src="assets/screenshot-patterns.svg" width="860" alt="Patterns across runs: repeated failures at an unchanged time limit, and a memory request being hand-tuned.">
<img src="assets/screenshot-job.svg" width="900" alt="One finished job: time, CPU and memory against their limits, then every field Slurm recorded.">
<img src="assets/screenshot-nodes.svg" width="900" alt="Failure rate per node, with a ready-to-paste --exclude.">

</details>

## 📌 Good to know

🚫 **A node is blamed only when it is really worse.** Tested one at a time, twenty equally
reliable nodes produce a false culprit more than half the time.

🩹 **`sacct` often misreports memory and limits.** These are handled, and anything unreadable
shows as `n/a`, never a fake `0`.

🔁 **Before, during, after:** [slurmate](https://github.com/PursuitOfDataScience/slurmate)
writes the job, [slurmwatch](https://github.com/PursuitOfDataScience/slurmwatch) watches it,
and this reviews it.

📦 `--json` emits everything: 103 values per job, plus 40 for every step.
[All 85 fields, and every `sacct` trap](docs/details.md).

<sub>The demo is recorded against <code>slurmpast --demo</code>. Regenerate it with <code>pip install -e ".[assets]" &amp;&amp; python tools/demo_gif.py</code>.</sub>

---

Slurm 20.11.8 · Python 3.10-3.13 · Textual 0.86-8.2 · MIT
