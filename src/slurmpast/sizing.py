"""What to request next time, from how this workload actually ran.

This is the point of reading finished jobs: a workload with a history tells you
what its next submission needs, and the two ways to get that wrong -- over- and
under-requesting -- have different costs. Over-requesting narrows which nodes can
host the job and reserves capacity nobody else can use. Under-requesting kills
the run.

Four rules keep the advice honest, each from something measured on real records:

* **Never size walltime down from a TIMEOUT.** Its ``Elapsed`` is truncated at
  the limit, so it bounds the true runtime only from *below*.
* **Never treat a hung run as evidence of needing more time.** 99 of 115
  ``cot-exp`` runs hit a 30-minute wall on a median of 0.56 CPU-seconds. Raising
  the limit buys a longer hang.
* **Never size memory from MaxRSS when it exceeded the cgroup limit.** Job
  43742638 reports 51.25 GiB against a 40 GiB limit that OOM-killed;
  ``jobacct_gather/linux`` sums RSS across the process tree and double-counts
  shared pages, so the figure is an upper bound at best and nonsense at worst.
* **Say "not enough evidence" rather than guess.** Below MIN_RUNS successful
  observations there is no distribution to reason about, and a confident wrong
  number is worse than an admission.
"""

from __future__ import annotations

import math
from typing import NamedTuple

from .diagnose import looks_like_noop
from .duration import format_bytes, format_duration

# Below this many usable observations there is no distribution to reason about.
MIN_RUNS = 3
# Headroom over the observed peak. Enough to absorb run-to-run variation without
# drifting back into over-request.
WALLTIME_MARGIN = 1.25
MEMORY_MARGIN = 1.30
CPU_MARGIN = 1.20
# Only speak up when the change is worth making.
MIN_RELATIVE_CHANGE = 0.20
# A veto needs to be earned. One bad run in 155 is an outlier to exclude, not
# grounds to refuse advice for the other 154 -- the first version of these rules
# let a single hung run silence a workload with 154 clean ones.
VETO_MIN_COUNT = 3
VETO_MIN_SHARE = 0.20


class Advice(NamedTuple):
    """One directive's worth of guidance for the next submission."""

    flag: str  # "--time", "--mem", "--cpus-per-task"
    verdict: str  # "raise" | "lower" | "keep" | "unknown"
    requested: str  # what was typically asked for
    observed: str  # what the runs actually used
    suggestion: str  # what to ask for next, or ""
    basis: str  # the evidence, in words
    caution: str = ""  # what would make this advice wrong

    @property
    def actionable(self) -> bool:
        return self.verdict in ("raise", "lower") and bool(self.suggestion)


def _percentile(values, fraction):
    """Nearest-rank percentile. Small samples make interpolation false precision."""
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(math.ceil(fraction * len(ordered)) - 1)))
    return ordered[index]


def _round_walltime(seconds):
    """Round up to a tidy limit: 5-minute steps under an hour, 15 above."""
    step = 300 if seconds < 3600 else 900
    return int(math.ceil(seconds / step) * step)


def _fmt_walltime(seconds):
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours >= 24:
        days, hours = divmod(hours, 24)
        return "%d-%02d:%02d:%02d" % (days, hours, minutes, secs)
    return "%02d:%02d:%02d" % (hours, minutes, secs)


def _round_gib(byte_count):
    return int(math.ceil(byte_count / float(1024**3)))


def walltime_advice(jobs) -> Advice:
    """How long the next run should be allowed."""
    completed = [j for j in jobs if j.completed and j.elapsed and not looks_like_noop(j)]
    timeouts = [j for j in jobs if j.base_state == "TIMEOUT"]
    hung = [j for j in timeouts if looks_like_noop(j)]
    limits = sorted({j.timelimit for j in jobs if j.timelimit})
    requested = format_duration(limits[-1]) if limits else "n/a"

    # A workload whose timeouts never computed does not need more time -- but
    # only when the hangs are the story, not a stray outlier.
    hangs_dominate = (
        len(hung) >= VETO_MIN_COUNT
        and len(hung) >= 0.5 * len(timeouts)
        and len(hung) >= VETO_MIN_SHARE * len(jobs)
    )
    if hangs_dominate:
        return Advice(
            flag="--time",
            verdict="unknown",
            requested=requested,
            observed="%d run%s hit the wall having consumed almost no CPU"
            % (len(hung), "" if len(hung) == 1 else "s"),
            suggestion="",
            basis="These runs were blocked, not slow -- a longer limit buys a longer hang.",
            caution="Fix the blocking call before changing --time.",
        )

    if len(completed) < MIN_RUNS:
        return Advice(
            flag="--time",
            verdict="unknown",
            requested=requested,
            observed="%d completed run%s" % (len(completed), "" if len(completed) == 1 else "s"),
            suggestion="",
            basis="Needs at least %d completed runs before a limit can be inferred." % MIN_RUNS,
        )

    elapsed = [j.elapsed for j in completed]
    peak = _percentile(elapsed, 0.95)
    target = _round_walltime(peak * WALLTIME_MARGIN)

    # Any timeout means the true requirement is above the limit that truncated
    # it, so the floor is that limit -- never below.
    floor = max((j.timelimit for j in timeouts if j.timelimit), default=0)
    if floor:
        target = max(target, _round_walltime(floor * WALLTIME_MARGIN))

    current = limits[-1] if limits else None
    basis = "p95 of %d completed runs is %s (longest %s); +%d%% headroom." % (
        len(completed),
        format_duration(peak),
        format_duration(max(elapsed)),
        round((WALLTIME_MARGIN - 1) * 100),
    )
    caution = ""
    if timeouts:
        caution = (
            "%d run%s timed out, so the requirement is at least the limit that cut "
            "them off -- this is a floor, not a fit."
            % (len(timeouts), "" if len(timeouts) == 1 else "s")
        )

    if current is None or target > current * (1 + MIN_RELATIVE_CHANGE):
        verdict = "raise"
    elif target < current * (1 - MIN_RELATIVE_CHANGE):
        verdict = "lower"
    else:
        verdict = "keep"

    return Advice(
        flag="--time",
        verdict=verdict,
        requested=requested,
        observed="%s at p95, %s longest" % (format_duration(peak), format_duration(max(elapsed))),
        suggestion=_fmt_walltime(target) if verdict != "keep" else "",
        basis=basis,
        caution=caution,
    )


def memory_advice(jobs) -> Advice:
    """How much memory the next run should ask for."""
    limits = [j.mem_limit_bytes for j in jobs if j.mem_limit_bytes]
    requested = format_bytes(max(limits)) if limits else "n/a"
    ooms = [j for j in jobs if j.base_state == "OUT_OF_MEMORY"]

    # Checked FIRST: a cgroup OOM kill is an event, not a sample, so it is the
    # most reliable thing here. Ordering this after the MaxRSS-trust check let an
    # unreliable metric veto advice that an authoritative one had already settled.
    if ooms:
        floor = max((j.mem_limit_bytes for j in ooms if j.mem_limit_bytes), default=0)
        target = _round_gib(floor * MEMORY_MARGIN) if floor else None
        return Advice(
            flag="--mem",
            verdict="raise" if target else "unknown",
            requested=requested,
            observed="%d OOM kill%s, the largest at %s"
            % (len(ooms), "" if len(ooms) == 1 else "s", format_bytes(floor) if floor else "n/a"),
            suggestion="%dG" % target if target else "",
            basis="A request that OOM'd is a floor: the requirement is above it.",
            caution=(
                "If the same request both failed and succeeded, --mem is not the "
                "deciding variable -- look for what else changed."
            ),
        )

    measured = [j for j in jobs if j.max_rss and j.mem_limit_bytes and not looks_like_noop(j)]
    # MaxRSS above the cgroup limit is definitionally not a working set. Those
    # runs are excluded; only when they dominate is the metric unusable outright.
    untrustworthy = [j for j in measured if j.max_rss > j.mem_limit_bytes]
    trustworthy = [j for j in measured if j.max_rss <= j.mem_limit_bytes]
    if untrustworthy and (
        len(untrustworthy) >= VETO_MIN_SHARE * max(1, len(measured)) and len(trustworthy) < MIN_RUNS
    ):
        return Advice(
            flag="--mem",
            verdict="unknown",
            requested=requested,
            observed="MaxRSS exceeds the limit on %d of %d runs"
            % (len(untrustworthy), len(measured)),
            suggestion="",
            basis=(
                "MaxRSS sums RSS across the process tree and double-counts shared "
                "pages, so on this workload it is not a footprint at all."
            ),
            caution="Measure the cgroup working set live (slurmwatch) to size this.",
        )

    usable = trustworthy
    if len(usable) < MIN_RUNS:
        return Advice(
            flag="--mem",
            verdict="unknown",
            requested=requested,
            observed="%d run%s with a usable memory reading"
            % (len(usable), "" if len(usable) == 1 else "s"),
            suggestion="",
            basis="Needs at least %d before a footprint can be inferred." % MIN_RUNS,
        )

    peaks = [j.max_rss for j in usable]
    peak = max(peaks)
    target = _round_gib(peak * MEMORY_MARGIN)
    current = max(limits) if limits else None

    if current is None:
        verdict = "raise"
    elif target * 1024**3 < current * (1 - MIN_RELATIVE_CHANGE):
        verdict = "lower"
    elif target * 1024**3 > current * (1 + MIN_RELATIVE_CHANGE):
        verdict = "raise"
    else:
        verdict = "keep"

    return Advice(
        flag="--mem",
        verdict=verdict,
        requested=requested,
        observed="%s peak across %d runs" % (format_bytes(peak), len(usable)),
        suggestion="%dG" % target if verdict != "keep" else "",
        basis="Highest observed peak %s, +%d%% headroom."
        % (format_bytes(peak), round((MEMORY_MARGIN - 1) * 100)),
        caution=(
            "MaxRSS over-reports for multi-process jobs, so treat this as an "
            "upper bound rather than the true footprint."
            + (
                "  %d run%s excluded: MaxRSS above the limit there, which cannot "
                "be a working set." % (len(untrustworthy), "" if len(untrustworthy) == 1 else "s")
                if untrustworthy
                else ""
            )
        ),
    )


def cpu_advice(jobs) -> Advice:
    """How many cores the next run should ask for."""
    allocated = sorted({j.cpu_count for j in jobs if j.cpu_count})
    requested = str(allocated[-1]) if allocated else "n/a"

    usable = [
        j for j in jobs if j.cpu_utilization is not None and j.cpu_count and not looks_like_noop(j)
    ]
    if len(usable) < MIN_RUNS:
        return Advice(
            flag="--cpus-per-task",
            verdict="unknown",
            requested=requested,
            observed="%d run%s with CPU accounting"
            % (len(usable), "" if len(usable) == 1 else "s"),
            suggestion="",
            basis="Needs at least %d before core use can be inferred." % MIN_RUNS,
        )

    effective = [j.cpu_utilization * j.cpu_count for j in usable]
    peak = max(effective)
    target = max(1, int(math.ceil(peak * CPU_MARGIN)))
    current = allocated[-1] if allocated else None

    if current is None:
        verdict = "unknown"
    elif target < current * (1 - MIN_RELATIVE_CHANGE):
        verdict = "lower"
    elif target > current * (1 + MIN_RELATIVE_CHANGE):
        verdict = "raise"
    else:
        verdict = "keep"

    gpu = any(j.gpu_count for j in usable)
    caution = ""
    if gpu and verdict == "lower":
        caution = (
            "This is a GPU workload: cores may be there to feed dataloader "
            "workers, and cutting them can starve the GPU even though they look idle."
        )

    return Advice(
        flag="--cpus-per-task",
        verdict=verdict,
        requested=requested,
        observed="%.1f cores busy at peak across %d runs" % (peak, len(usable)),
        suggestion=str(target) if verdict != "keep" else "",
        basis="Busiest run used %.1f of %s cores; +%d%% headroom."
        % (peak, requested, round((CPU_MARGIN - 1) * 100)),
        caution=caution,
    )


def recommend(jobs) -> list:
    """All three directives for one workload, in the order they bite."""
    records = [j for j in jobs if not j.open_ended]
    if not records:
        return []
    return [walltime_advice(records), memory_advice(records), cpu_advice(records)]


def sbatch_lines(advice_list) -> list:
    """The ``#SBATCH`` lines worth changing, ready to paste."""
    return ["#SBATCH %s=%s" % (a.flag, a.suggestion) for a in advice_list if a.actionable]
