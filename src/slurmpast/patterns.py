"""Patterns that only appear across runs.

Every existing tool is momentary: ``seff`` and ``reportseff`` describe one job,
``slurmwatch`` describes one live run. Neither can say "you have submitted this
115 times and it died 99 times", which is the single largest measured loss in a
real seven-month history.

Two detectors here, both from observed sequences:

* **repeat-failure** -- ``cot-exp``: 115 submissions, every one at
  ``--time=00:30:00``, 99 TIMEOUT / 13 CANCELLED / 3 COMPLETED.
* **memory bisection** -- ``rc-tok-github_code``: ReqMem walked
  48G, 32G, 32G, 17G, 12G, 12G, 14G, 16G, 18G and then *succeeded at 32G*, the
  value that had already failed twice. A monotone-search assumption would have
  proposed the next increment forever; the useful output is "you are searching
  blind and --mem is not the variable".
"""

import re

from .diagnose import looks_like_noop
from .duration import format_bytes, format_duration
from .model import CRITICAL, INFO, WARNING, Finding

REPEAT_MIN = 5
REPEAT_FAIL_FRACTION = 0.5
BISECTION_MIN_OOM = 3
# How many repeat-failure groups to print before summarising the rest.
REPEAT_REPORT_LIMIT = 4


_DIGIT_RUN = re.compile(r"\d+")


def normalize_name(name):
    """Collapse the varying part of a job name so a sweep reads as one workload.

    Job names encode parameters, so raw names barely group at all: a real
    seven-month history has **1,624 distinct names across 6,576 jobs**, which
    rolls up to 1,687 groups -- no better than the flat list it was meant to
    replace. Replacing digit runs with ``#`` folds that to 557:

        s1e20, s2e47, s3e83          -> s#e#
        att-speed-23, att-speed-40   -> att-speed-#
        mid85_059, mid85_067         -> mid#_#
        node-evaluation              -> node-evaluation   (untouched)

    Adjacent placeholders are deliberately NOT merged: folding ``#_#`` to ``#``
    would put ``mid85_059`` and an unrelated ``mid42`` in one group.

    Only digits are collapsed. It is tempting to also fold single-letter
    suffixes (``nemotron-batch-h200-x`` / ``-y``) but that starts merging
    workloads that differ meaningfully, and the cost of over-collapsing -- two
    unrelated failures blamed on one workload -- is worse than a slightly longer
    list. The raw names remain visible once you open a group.
    """
    if not name:
        return "?"
    return _DIGIT_RUN.sub("#", name)


def group_key(job):
    """Identity for "the same piece of work".

    JobName alone is far too coarse -- ``test`` covers 362 unrelated jobs and
    ``node-test`` four different things -- so the shape of the request is folded
    in. Resource *magnitudes* are deliberately excluded: raising --mem must not
    fork the history you are trying to learn from.

    The owner is part of that identity. ``-u`` takes a comma-separated list and
    ``--all-users`` spans the cluster, so a multi-user query is one flag away --
    and without the user in the key, two people's unrelated ``run.sh`` on one
    partition became a single fabricated workload. That is not a cosmetic merge:
    the pattern detector then reported "18 of 18 runs of run.sh failed; stop
    resubmitting, the failure is deterministic" about a workload nobody ran
    eighteen times, and nothing in the output names a user for the reader to catch
    it. Last in the tuple because ``key[0..2]`` are read positionally as name,
    partition and kind. For the single-user query that is the default, the value is
    constant and nothing regroups.
    """
    gpus = job.gpu_count
    return (
        normalize_name(job.name),
        job.partition or "?",
        "gpu" if gpus else "cpu",
        job.user or "?",
    )


def numeric_job_id(job):
    """Sort key that orders by submission, tolerating ``123_4`` array ids.

    Shared rather than private: :mod:`slurmpast.sizing` needs the same ordering to
    break a tie between records with no usable timestamp, and a second copy there
    got array elements wrong -- reading the leading digits alone makes ``123_4``
    and ``123_5`` compare equal.
    """
    raw = job.job_id.split("+")[0]
    base, _, task = raw.partition("_")
    try:
        primary = int(base)
    except ValueError:
        primary = 0
    try:
        secondary = int(task) if task else -1
    except ValueError:
        secondary = -1
    return (primary, secondary)


def usable(jobs):
    """Records safe to aggregate: closed, and with a real elapsed time."""
    return [j for j in jobs if not j.open_ended and j.elapsed is not None]


def find_repeat_failures(jobs, min_runs=REPEAT_MIN, limit=REPEAT_REPORT_LIMIT):
    """Groups that keep dying the same way.

    Ranked by resource burned, then capped. A seven-month history yields seven of
    these at once, and an uncapped list is the failure mode where volume replaces
    judgement -- so the tail is counted and named rather than printed in full.
    """
    groups = {}
    for job in usable(jobs):
        groups.setdefault(group_key(job), []).append(job)

    findings = []
    for key, members in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        if len(members) < min_runs:
            continue
        failures = [j for j in members if j.failed]
        if len(failures) < min_runs:
            continue
        fraction = len(failures) / float(len(members))
        if fraction < REPEAT_FAIL_FRACTION:
            continue

        states = {}
        for job in failures:
            states[job.base_state] = states.get(job.base_state, 0) + 1
        dominant, count = max(states.items(), key=lambda kv: kv[1])

        limits = {format_duration(j.timelimit) for j in failures if j.timelimit is not None}
        hung = [j for j in failures if looks_like_noop(j)]
        wasted = sum(j.gpu_hours or 0.0 for j in failures)

        evidence = "%d of %d runs of %s in %s failed; %d were %s." % (
            len(failures),
            len(members),
            key[0],
            key[1],
            count,
            dominant,
        )
        if dominant == "TIMEOUT" and len(limits) == 1:
            evidence += " Every one used the same --time=%s." % limits.pop()
        if wasted > 1.0:
            evidence += " %.0f GPU-hours consumed by the failures." % wasted

        if hung and len(hung) >= 0.5 * len(failures):
            action = (
                "%d of these consumed under 10 CPU-seconds -- they hung rather than ran out "
                "of time. Raising the limit will not help; fix the blocking call." % len(hung)
            )
        elif dominant == "TIMEOUT":
            action = (
                "Raise --time above that limit; a timeout's Elapsed only bounds runtime from below."
            )
        elif dominant == "OUT_OF_MEMORY":
            action = "See the memory-search check -- the next increment is probably not the fix."
        else:
            action = "Stop resubmitting; the failure is deterministic. Reproduce interactively."

        findings.append(
            (
                wasted,
                len(failures),
                Finding(
                    CRITICAL if fraction > 0.8 else WARNING,
                    "repeat-failure",
                    "This work has failed repeatedly in the same way",
                    evidence,
                    action,
                ),
            )
        )

    # Worst first: resources burned, then run count for the CPU-only groups.
    findings.sort(key=lambda row: (-row[0], -row[1]))
    kept = [row[2] for row in findings[:limit]]
    hidden = findings[limit:]
    if hidden:
        kept.append(
            Finding(
                INFO,
                "repeat-failure-more",
                "%d further groups show the same repeat-failure pattern" % len(hidden),
                "Together they account for %d more failed runs. Shown in full with a "
                "narrower --since window, or per job with `slurmpast <jobid>`."
                % sum(row[1] for row in hidden),
                "",
            )
        )
    return kept


def find_memory_search(jobs, min_oom=BISECTION_MIN_OOM):
    """Hand-bisection of --mem, visible as a non-monotone walk across OOMs."""
    groups = {}
    for job in usable(jobs):
        groups.setdefault(group_key(job), []).append(job)

    findings = []
    for key, members in groups.items():
        members.sort(key=numeric_job_id)
        ooms = [j for j in members if j.base_state == "OUT_OF_MEMORY"]
        if len(ooms) < min_oom:
            continue

        # mem_limit_bytes, NOT req_mem_bytes: ReqMem reads "0n" on 2,130 of 6,574
        # real jobs, so keying off it makes this detector blind on a third of the
        # history. The limit actually in force comes from AllocTRES first.
        requests = [j.mem_limit_bytes for j in ooms if j.mem_limit_bytes is not None]
        if len(requests) < min_oom:
            continue

        # strict=False on purpose: this pairs a list with its own tail, so the
        # lengths differ by one by construction.
        monotone = all(b >= a for a, b in zip(requests, requests[1:], strict=False))
        walk = " -> ".join(format_bytes(v) for v in requests)

        # Did a later run succeed at a value that had already OOM'd? That proves
        # --mem was never the deciding variable.
        #
        # Accumulated while walking forward, which is what makes "already" true.
        # Testing against the finished set of every OOM'd value ignored order, so
        # the EARLIEST run in a group -- one that completed before anything had
        # OOM'd at all -- was reported as having "then COMPLETED at a value that
        # had already OOM'd". That inverts the story: the real history was a run
        # that worked and a request that degraded afterwards. `members` is already
        # sorted by numeric_job_id above, which is submission order.
        contradiction = None
        oomed_so_far: set = set()
        for job in members:
            if job.base_state == "OUT_OF_MEMORY":
                if job.mem_limit_bytes is not None:
                    oomed_so_far.add(job.mem_limit_bytes)
            elif job.completed and job.mem_limit_bytes in oomed_so_far:
                contradiction = job
                break

        evidence = "%d OOM kills for %s with --mem walking %s." % (len(ooms), key[0], walk)
        if contradiction is not None:
            evidence += " Job %s then COMPLETED at %s -- a value that had already OOM'd." % (
                contradiction.job_id,
                format_bytes(contradiction.mem_limit_bytes),
            )

        if contradiction is not None:
            action = (
                "--mem is not the deciding variable: the same request both failed and "
                "succeeded. Something else changed (worker count, batch size, input shard). "
                "Find that before tuning memory again."
            )
        elif not monotone:
            action = (
                "The search is not converging -- it moves both directions. Measure the real "
                "working set once instead of bisecting, then request that plus a margin."
            )
        else:
            biggest = max(requests)
            action = (
                "Stop stepping. Jump well past the largest failed request (%s) to bound the "
                "requirement, then tighten once from a measurement." % format_bytes(biggest)
            )

        findings.append(
            Finding(
                CRITICAL if contradiction is not None else WARNING,
                "memory-search",
                "Memory request is being hand-searched",
                evidence,
                action,
            )
        )
    return findings


def find_noop_allocations(jobs, top=10):
    """Allocations that held resources and computed nothing, worst first."""
    dead = [j for j in usable(jobs) if looks_like_noop(j)]
    dead.sort(key=lambda j: -(j.gpu_hours or (j.elapsed or 0) / 3600.0))
    return dead[:top], dead


def goodput(jobs):
    """Allocated vs productive resource time.

    The ratio nothing on a stock cluster computes. Cancellations are counted
    separately because they are ambiguous -- deliberate kills and abandoned runs
    are indistinguishable in accounting.
    """
    records = usable(jobs)
    # Two different reasons a record is dropped, reported separately because the
    # UI names one of them: an unterminated record has an Elapsed measured to
    # *now*, while a closed record with no Elapsed at all was simply never
    # accounted. Counting both as "unterminated" made the report state something
    # false about the second kind.
    open_ended = sum(1 for job in jobs if job.open_ended)
    stats = {
        "jobs": len(records),
        "completed": 0,
        "failed": 0,
        "cancelled": 0,
        "gpu_hours_total": 0.0,
        "gpu_hours_completed": 0.0,
        "gpu_hours_noop": 0.0,
        "core_hours_total": 0.0,
        "noop_jobs": 0,
        "excluded_open_records": open_ended,
        "excluded_no_elapsed": len(jobs) - len(records) - open_ended,
    }
    for job in records:
        gpu_h = job.gpu_hours or 0.0
        stats["gpu_hours_total"] += gpu_h
        if job.elapsed and job.cpu_count:
            stats["core_hours_total"] += job.elapsed * job.cpu_count / 3600.0
        if job.completed:
            stats["completed"] += 1
            stats["gpu_hours_completed"] += gpu_h
        elif job.cancelled:
            stats["cancelled"] += 1
        elif job.failed:
            stats["failed"] += 1
        if looks_like_noop(job):
            stats["noop_jobs"] += 1
            stats["gpu_hours_noop"] += gpu_h

    total = stats["gpu_hours_total"]
    stats["gpu_goodput"] = (stats["gpu_hours_completed"] / total) if total else None
    stats["gpu_noop_fraction"] = (stats["gpu_hours_noop"] / total) if total else None
    stats["completion_rate"] = stats["completed"] / float(stats["jobs"]) if stats["jobs"] else None
    return stats


def summarize(jobs):
    """All cross-job findings, most severe first."""
    findings = []
    findings.extend(find_repeat_failures(jobs))
    findings.extend(find_memory_search(jobs))

    top, dead = find_noop_allocations(jobs)
    if dead:
        gpu_h = sum(j.gpu_hours or 0.0 for j in dead)
        detail = "%d allocations ran over %s while consuming under 10 CPU-seconds." % (
            len(dead),
            format_duration(300),
        )
        if gpu_h > 1.0:
            detail += " Together they held %.0f GPU-hours." % gpu_h
        quick = [j for j in dead if (j.elapsed or 0) <= 900]
        if quick:
            detail += (
                " %d were killed within 15 minutes, so those were already noticed; the "
                "cost is concentrated in the long ones." % len(quick)
            )
        findings.append(
            Finding(
                WARNING,
                "noop-allocations",
                "Resources held without computing",
                detail,
                "The long tail is what matters: alert when CPU time stops advancing while a "
                "GPU is held, rather than waiting to notice by hand.",
            )
        )
    return findings
