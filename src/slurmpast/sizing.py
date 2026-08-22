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
  How far to distrust it is a property of the *cluster*, so the caution attached
  to this advice is worded from ``JobAcctGatherType`` -- see :mod:`slurmpast.site`.
* **Say "not enough evidence" rather than guess.** Below MIN_RUNS successful
  observations there is no distribution to reason about, and a confident wrong
  number is worse than an admission.

Both quantities are stated in the unit the flag takes, which is not the unit
sacct reports: ``--mem`` is per node while ``AllocTRES`` totals the allocation,
and ``--cpus-per-task`` is per task while every CPU counter totals it too.
"""

from __future__ import annotations

import math
from typing import NamedTuple

from .diagnose import looks_like_noop
from .duration import format_bytes, format_duration
from .patterns import hung_split_note, numeric_job_id
from .site import maxrss_caveat

# Below this many usable observations there is no distribution to reason about.
MIN_RUNS = 3
# Added on top of the observed peak, to absorb run-to-run variation without
# drifting back into over-request. Called "headroom" here and nowhere a reader
# sees: on screen it was "+30% headroom", which said neither what the 30% was of
# nor that it had already been applied to the figure beside it.
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
    requested: str  # what the LAST run asked for -- see _latest
    observed: str  # what the runs actually used
    suggestion: str  # what to ask for next, or ""
    basis: str  # the evidence, in words
    caution: str = ""  # what would make this advice wrong

    @property
    def actionable(self) -> bool:
        return self.verdict in ("raise", "lower") and bool(self.suggestion)


def _latest(jobs, attribute):
    """``attribute`` on the most recently run job that has one, or ``None``.

    What the *next* submission will ask for is what the *last* one asked for, and
    the two are not the same as the largest thing ever asked for in the window.
    ``patterns.group_key`` deliberately excludes resource magnitudes -- "raising
    --mem must not fork the history you are trying to learn from" -- which is the
    right call and guarantees a group spans every limit the user has tried. Taking
    ``max()`` over that reaches back across exactly the history the grouping exists
    to unify, and it does not degrade gracefully: one stale 8-hour run among twenty
    tightened 40-minute ones was reported as ``requested 08:00:00`` and turned
    "raise to 02:30:00" into "lower", which is the opposite instruction. Where the
    same stale limit happened to sit near the target the verdict became ``keep``,
    and ``keep`` suppresses the suggestion -- so the tool went silent about a
    40-minute limit that every recent run needed 01:52:49 to finish.

    Ordered by ``start or submit``, matching :func:`index._stamp`, so this agrees
    with the ordering the rest of the tool already presents a workload in. Ties and
    missing stamps fall back to ``patterns.numeric_job_id``, which is monotonic per
    cluster and orders array elements correctly -- ``123_4`` before ``123_5``, which
    reading the leading digits alone does not.
    """
    stamped = [j for j in jobs if getattr(j, attribute, None)]
    if not stamped:
        return None
    newest = max(stamped, key=lambda j: (j.start or j.submit or "", numeric_job_id(j)))
    return getattr(newest, attribute)


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


def _cores_text(cores):
    """A core count a reader can put back into the sum beside it.

    "%.1f" turned 0.04 into "0.0" and two decimals turn 0.003 into "0.00", and both
    read as zero -- from which the advice of 1 core cannot be derived, since
    rounding zero up is still zero. What is true of any nonzero fraction of a core
    is that rounding it up gives exactly one, so that is what it says.
    """
    if cores <= 0:
        return "0"
    if cores < 0.05:
        return "under 0.05"
    return ("%.2f" if cores < 0.1 else "%.1f") % cores


def _round_gib(byte_count):
    return int(math.ceil(byte_count / float(1024**3)))


def _memory_verdict(target_gib, current_bytes):
    """raise/lower/keep for a GiB target against the bytes the last run asked for.

    Shared by both halves of :func:`memory_advice` so that a target derived from an
    OOM floor is judged the same way as one derived from measured peaks. It was
    only ever applied to the second, which is how the OOM branch came to announce
    "raise" beside a number below the current request.
    """
    if current_bytes is None:
        return "raise"
    if target_gib * 1024**3 < current_bytes * (1 - MIN_RELATIVE_CHANGE):
        return "lower"
    if target_gib * 1024**3 > current_bytes * (1 + MIN_RELATIVE_CHANGE):
        return "raise"
    return "keep"


def walltime_advice(jobs) -> Advice:
    """How long the next run should be allowed."""
    completed = [j for j in jobs if j.completed and j.elapsed and not looks_like_noop(j)]
    timeouts = [j for j in jobs if j.base_state == "TIMEOUT"]
    hung = [j for j in timeouts if looks_like_noop(j)]
    # The split every claim about a timeout has to be made against, so it is made
    # once, here, rather than inside the one branch that used to need it.
    computing = [j for j in timeouts if not looks_like_noop(j)]
    # The limit the last run asked for, not the largest in the window. See _latest.
    current = _latest(jobs, "timelimit")
    requested = format_duration(current) if current else "n/a"

    # A workload whose timeouts never computed does not need more time -- but
    # only when the hangs are the story, not a stray outlier.
    hangs_dominate = (
        len(hung) >= VETO_MIN_COUNT
        and len(hung) >= 0.5 * len(timeouts)
        and len(hung) >= VETO_MIN_SHARE * len(jobs)
    )
    if hangs_dominate:
        # The veto stands -- while hangs dominate, a longer limit mostly buys a
        # longer hang -- but it may not speak for every timeout in the group. The
        # threshold is half, so four hangs among eight timeouts fired it, and
        # "These runs were blocked, not slow" was then asserted of the other four
        # as well: runs that had burned 29:50 of a 30:00 limit doing real work.
        # `looks_like_noop` needs CPU under 10s, so those are never hangs by this
        # module's own definition. Name the split, and keep what they proved.
        basis = (
            "%d of %d timed-out run%s consumed almost no CPU before hitting the wall: "
            "blocked, not slow — a longer limit buys a longer hang."
            % (len(hung), len(timeouts), "" if len(timeouts) == 1 else "s")
        )
        caution = "Fix the blocking call before changing --time."
        # The same clause the patterns screen appends to the same conclusion. It
        # lives in `patterns` because this module already imports from there and
        # the reverse would be a cycle -- and because both were making the claim
        # and only this one qualified it.
        split = hung_split_note(len(computing), [j.timelimit for j in computing])
        if split:
            caution += "  " + split
        return Advice(
            flag="--time",
            verdict="unknown",
            requested=requested,
            observed="%d run%s hit the wall having consumed almost no CPU"
            % (len(hung), "" if len(hung) == 1 else "s"),
            suggestion="",
            basis=basis,
            caution=caution,
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
    p95 = _percentile(elapsed, 0.95)
    longest = max(elapsed)
    # The longest run that COMPLETED, not p95, because exceeding --time kills the
    # job exactly as exceeding --mem does, and :func:`memory_advice` sizes from the
    # highest observed peak for that reason. Sizing walltime from p95 instead told
    # the `software` workload to "lower to 03:00:00" on the same screen as "longest
    # 07:57:12" -- advice that would have timed out its slowest runs by design,
    # since p95 excludes the top 5% and there is no headroom multiplier that
    # recovers a 2.9x gap. A single pathological run cannot inflate this: a hang
    # long enough to matter is caught by the no-CPU branch above and never reaches
    # here. p95 stays in the basis as the shape of the distribution.
    target = _round_walltime(longest * WALLTIME_MARGIN)

    # A timeout that was COMPUTING means the true requirement is above the limit
    # that truncated it, so the floor is that limit -- never below. Still max(),
    # and still right: a floor is a claim about the requirement, which no later run
    # retracts, unlike a claim about what the script currently says.
    #
    # Hung runs are excluded, which is this module's own rule 2: a hang's Elapsed
    # measures how long it waited, not how long the work takes, so a longer limit
    # buys a longer hang. The veto above makes that split when hangs dominate -- but
    # a MINORITY of hangs never reaches the veto, and used to set this floor
    # unopposed. Two hung runs carrying a stale `--time=24:00:00` turned "raise to
    # 02:30:00" into "raise to 1-06:00:00" for a workload whose longest completed
    # run took an hour: a 12x over-request, printed above a basis line still
    # reading "longest of 10 completed runs took 01:00:00".
    floor = max((j.timelimit for j in computing if j.timelimit), default=0)
    if floor:
        target = max(target, _round_walltime(floor * WALLTIME_MARGIN))

    # p95 only when it says something the longest run does not. On a workload whose
    # runs are all alike the two are the same number, and "longest of 8 completed
    # runs is 00:30:18 (p95 00:30:18)" printed it twice in one clause -- noise
    # dressed as evidence, which is worse than no evidence. It earns the space where
    # the distribution has a tail: 07:57:12 longest against 02:12:15 at p95 is the
    # difference between a workload with one slow run and one that is slow.
    spread = ""
    if abs(longest - p95) > max(1.0, 0.01 * longest):
        spread = " (p95 %s)" % format_duration(p95)
    # The evidence, and nothing else. Three attempts at saying more all failed:
    # "+25% headroom" ("what does headroom mean in this context?"), then the recipe
    # "+25%, rounded up to the next 15 minutes" ("you are making things far more
    # confusing even further"), then "the rest is room to spare" ("why do we need
    # this sentence here?"). It was not needed: the block's own header already says
    # why a request sits above the observation -- over-requesting narrows which
    # nodes can host the job, under-requesting kills the run -- so repeating it per
    # flag, three times per workload, was the header again in smaller type. What
    # only the line can supply is the measurement the number came from.
    basis = "longest of %d completed runs took %s%s." % (
        len(completed),
        format_duration(longest),
        spread,
    )
    # Counted over the runs the floor was actually taken from. Saying "8 runs timed
    # out, so the requirement is at least the limit that cut them off" of a set that
    # included two hangs asserted of them the one thing this module says a hang
    # never shows.
    caution = ""
    if computing:
        caution = (
            "%d run%s timed out while computing, so the requirement is at least the "
            "limit that cut them off — this is a floor, not a fit."
            % (len(computing), "" if len(computing) == 1 else "s")
        )
    if hung:
        # "further ... that floor" only parses after the sentence above has
        # established one. Below VETO_MIN_COUNT there are hung timeouts and no
        # computing ones, so `caution` is empty and the reader got "2 further
        # timeouts are left out of that floor" with no floor anywhere in sight.
        caution += (
            "%s%d %stimeout%s consumed almost no CPU and %s left out%s: a run that hung "
            "says nothing about how long the work takes."
            % (
                "  " if caution else "",
                len(hung),
                "further " if caution else "",
                "" if len(hung) == 1 else "s",
                "is" if len(hung) == 1 else "are",
                " of that floor" if caution else " of the figure above",
            )
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
        observed="%s longest, %s at p95" % (format_duration(longest), format_duration(p95)),
        suggestion=_fmt_walltime(target) if verdict != "keep" else "",
        basis=basis,
        caution=caution,
    )


def memory_advice(jobs) -> Advice:
    """How much memory the next run should ask for, per node.

    ``--mem`` is per node, and so is :attr:`Job.mem_limit_bytes` -- ``AllocTRES``
    reports the allocation total, which on a multi-node job is the ceiling
    multiplied by the node count. Comparing MaxRSS (one task's peak) against the
    total understated use by exactly that factor.
    """
    # The ceiling the last run asked for, not the largest in the window. On the
    # recorded rc-tok-github_code history this is the difference between "48.0 GiB"
    # -- a cancelled run five submissions back -- and the 17 GiB the script actually
    # says. See _latest.
    current = _latest(jobs, "mem_limit_bytes")
    requested = format_bytes(current) if current else "n/a"
    ooms = [j for j in jobs if j.base_state == "OUT_OF_MEMORY"]

    measured = [j for j in jobs if j.max_rss and j.mem_limit_bytes and not looks_like_noop(j)]
    # MaxRSS above the cgroup limit is definitionally not a working set. Those
    # runs are excluded; only when they dominate is the metric unusable outright.
    untrustworthy = [j for j in measured if j.max_rss > j.mem_limit_bytes]
    trustworthy = [j for j in measured if j.max_rss <= j.mem_limit_bytes]

    # Checked FIRST: a cgroup OOM kill is an event, not a sample, so it is the
    # most reliable thing here. Ordering this after the MaxRSS-trust check let an
    # unreliable metric veto advice that an authoritative one had already settled.
    if ooms:
        floor = max((j.mem_limit_bytes for j in ooms if j.mem_limit_bytes), default=0)
        target = _round_gib(floor * MEMORY_MARGIN) if floor else None
        # A floor is a lower bound on the requirement, not the whole answer, and
        # it says nothing about whether the request has since been fixed. This
        # branch used to return here with verdict hard-coded to "raise", so a
        # workload that OOM'd at 16 GiB and was then raised to 64 GiB was told to
        # "raise to 21G" -- a two-thirds cut, announced as an increase, and
        # emitted as a paste-ready `#SBATCH --mem=21G` that walks straight back
        # into the OOM the user had already fixed. Both halves of that are the
        # defect issues.md #2 describes: a verdict measured against something
        # other than what the last run asked for. `walltime_advice` had it right
        # all along -- it folds its TIMEOUT floor into the same target everything
        # else is judged against, rather than short-circuiting past the
        # comparison -- so this now does the same.
        peak_floor = None
        if target and len(trustworthy) >= MIN_RUNS:
            peak_floor = max(j.max_rss for j in trustworthy)
            target = max(target, _round_gib(peak_floor * MEMORY_MARGIN))
        verdict = _memory_verdict(target, current) if target else "unknown"
        basis = "A request that OOM'd is a floor: the requirement is above it."
        if peak_floor is not None and _round_gib(peak_floor * MEMORY_MARGIN) > _round_gib(
            floor * MEMORY_MARGIN
        ):
            # Say which measurement is actually binding. Reporting the floor alone
            # while sizing from something larger is how the old text came to
            # disagree with its own number.
            basis += "  The runs that did not OOM peaked higher still, at %s." % format_bytes(
                peak_floor
            )
        return Advice(
            flag="--mem",
            verdict=verdict,
            requested=requested,
            observed="%d OOM kill%s, the largest at %s"
            % (len(ooms), "" if len(ooms) == 1 else "s", format_bytes(floor) if floor else "n/a"),
            suggestion="%dG" % target if target and verdict != "keep" else "",
            basis=basis,
            caution=(
                "If the same request both failed and succeeded, --mem is not the "
                "deciding variable — look for what else changed."
            ),
        )

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
                "MaxRSS reads above the ceiling that was enforced, so on this workload "
                "it is not a footprint at all (%s)." % maxrss_caveat()
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

    verdict = _memory_verdict(target, current)

    caution = maxrss_caveat() + "."
    if untrustworthy:
        caution += "  %d run%s excluded: MaxRSS above the limit there, which cannot be a " % (
            len(untrustworthy),
            "" if len(untrustworthy) == 1 else "s",
        )
        caution += "working set."
    if any((j.node_count or 1) > 1 for j in usable):
        caution += "  Per node, which is what --mem sets; the allocation total is larger."

    return Advice(
        flag="--mem",
        verdict=verdict,
        requested=requested,
        observed="%s peak across %d runs" % (format_bytes(peak), len(usable)),
        suggestion="%dG" % target if verdict != "keep" else "",
        basis="the most any run used was %s." % format_bytes(peak),
        caution=caution,
    )


def cpu_advice(jobs) -> Advice:
    """How many cores the next run should ask for, per task.

    ``--cpus-per-task`` is per task; every CPU number sacct reports is a total
    over the allocation. Comparing the two directly is right for the single-task
    job that dominates most histories and badly wrong otherwise -- it told a
    15-node, 90-core job to request 90 cores for each of its tasks.
    """
    # Cores per task, which is the quantity the flag sets. Identical to cpu_count
    # whenever there is one task, so single-task advice is unchanged. From the last
    # run rather than the largest in the window, for the reason in _latest -- and
    # here the stale figure was also printed as the denominator of the basis text,
    # so "used 1.2 of 16 cores per task" named a 16 the script had already left
    # behind.
    current = _latest(jobs, "cpus_per_task")
    requested = ("%g" % current) if current else "n/a"

    usable = [
        j
        for j in jobs
        if j.cpu_utilization is not None and j.cpus_per_task and not looks_like_noop(j)
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

    # The busiest run, kept rather than just its number, because the basis sentence
    # has to name the ceiling that run itself was measured against. Pairing its
    # usage with `requested` -- the LAST run's ceiling -- printed "the busiest run
    # used 12.0 of 2 cores per task" for a group whose oldest run asked for 16 and
    # whose recent ones ask for 2: a run using six times its own allocation, which
    # cannot happen. Both numbers were right; they came from different runs.
    busiest = max(usable, key=lambda j: j.cpu_utilization * j.cpus_per_task)
    peak = busiest.cpu_utilization * busiest.cpus_per_task
    target = max(1, int(math.ceil(peak * CPU_MARGIN)))

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
    tasks = max((j.task_count for j in usable), default=1)
    if tasks > 1:
        caution = (
            (caution + "  " if caution else "")
            + "Per task: this workload runs %d, so the allocation total is that many times larger."
            % (tasks)
        )

    # Singular only for exactly one, because the figure is printed to one decimal:
    # `peak < 2` made every value from 1.0 to 1.9 read "1.5 core busy per task".
    # 0.9 is plural too -- English pluralises everything but one, including zero.
    per_task_label = "core" if abs(peak - 1.0) < 0.05 else "cores"
    return Advice(
        flag="--cpus-per-task",
        verdict=verdict,
        requested=requested,
        observed="%.1f %s busy per task at peak across %d runs"
        % (peak, per_task_label, len(usable)),
        suggestion=str(target) if verdict != "keep" else "",
        # Against the ceiling that run itself had, which is not necessarily the one
        # the last run asked for. `requested` is deliberately the latest ask (see
        # _latest) and it is already on screen as "(from X)"; borrowing it here as
        # the denominator too produced "used 12.0 of 2 cores per task", a run using
        # six times its own allocation. One sentence, one run.
        basis="the busiest run used %s of %s core%s per task."
        % (
            _cores_text(peak),
            "%g" % busiest.cpus_per_task,
            "" if busiest.cpus_per_task == 1 else "s",
        ),
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
