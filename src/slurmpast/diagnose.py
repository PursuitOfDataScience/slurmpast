"""What actually killed the job.

Rule thresholds are grounded in measured Midway3 records, cited inline. Two
principles, both learned the hard way:

* **A TIMEOUT is not evidence that the job needed more time.** 99 of 115
  ``cot-exp`` runs hit a 30-minute wall having burned a *median of 0.56 CPU
  seconds*. They hung. Raising ``--time`` would have bought longer hangs. The
  CPU counter is what separates the two cases, and no walltime tool that reads
  only Elapsed can tell them apart.

* **Stay quiet when the request was sound.** A tool that comments on a job which
  used 94% of its walltime trains you to ignore it, and then it is also ignored
  on the job that was 1,100x over.
"""

from .duration import format_bytes, format_duration, format_mem_flag, format_percent
from .model import CRITICAL, INFO, WARNING, Finding, Verdict

# An allocation running longer than this with less than NOOP_CPU_SECONDS of CPU
# cannot have been computing. 300s/10s is deliberately conservative: the median
# hung cot-exp run used 0.56s over 1815s, so the gap to the threshold is ~20x.
NOOP_MIN_ELAPSED = 300.0
NOOP_CPU_SECONDS = 10.0

# Below this CPU utilization a multi-core allocation is mostly idle cores.
LOW_CPU_UTIL = 0.15
# Below this, a job is too short to judge core usage: interpreter startup,
# module loads and conda activation dominate, so low utilization says nothing
# about the request. Observed live -- 2- to 43-second jobs were being told their
# cores were idle, which is noise that trains you to ignore the tool.
MIN_ELAPSED_FOR_CPU_JUDGEMENT = 120.0
# Report walltime slack only below this. Above it the request was reasonable.
WALLTIME_SLACK = 0.5
# MaxRSS spread across steps beyond this means the metric is unusable.
RSS_SPREAD_SUSPECT = 100.0

# Share of CPU time in the kernel above which the job is paying for syscalls
# rather than computing. A healthy training run measures ~4.7% (job 51170455:
# 15m36s system against 5h31m total), so 30% is far outside normal.
SYSTEM_CPU_HEAVY = 0.30
# Sustained I/O above this is worth naming: it is the rate at which the shared
# capacity-tier filesystem, not the GPU, sets the pace.
IO_RATE_LOUD = 100 * 1024**2  # 100 MiB/s
# Minimum bytes before commenting on I/O at all -- a short job moving a little
# data is not interesting.
IO_VOLUME_FLOOR = 10 * 1024**3  # 10 GiB
# Fraction by which the slowest task may lag the average before it is a
# straggler. In a synchronous collective every other rank waits on this one.
STRAGGLER_SPREAD = 0.25
# One task holding this many times the average RSS is an imbalance, not noise.
RSS_IMBALANCE = 2.0
# Major page faults below this are ordinary process startup, not thrashing.
# Firing at >0 flagged real jobs with 15 faults -- pure noise.
PAGING_FLOOR = 1000
# Only mention unused memory when a COMPLETED job left this much on the table,
# and only when the absolute waste is material (see MEM_SLACK_FLOOR).
MEM_SLACK = 0.35
MEM_SLACK_FLOOR = 32 * 1024**3  # 32 GiB unused

# Recorded GPU utilization below which a card was not being driven at all, and
# below which it was driven but not filled. Only reachable on a site running
# AutoDetect=nvml; where Slurm gathers nothing these stay unused and the
# host-CPU proxy speaks instead. 5% is generous -- an idle card that still
# services memory copies reads a few percent.
GPU_IDLE = 0.05
GPU_UNDERUSED = 0.40

_CUDA_OOM_MARKERS = (
    "cuda out of memory",
    "cuda error: out of memory",
    "torch.cuda.outofmemoryerror",
    "hip out of memory",
    "cublas_status_alloc_failed",
)
_NCCL_MARKERS = ("nccl", "watchdog caught collective operation timeout", "ncclinternalerror")
_IMPORT_MARKERS = ("modulenotfounderror", "importerror", "no module named")


def diagnose(job, log_text=None, node_note=None):
    """Return a Verdict for one job.

    ``log_text`` is the tail of the job's stderr/stdout when it could be found;
    without it the CUDA-OOM and traceback rules stay silent rather than guess.
    ``node_note`` is an optional pre-computed reliability string for the node.
    """
    findings = []
    add = findings.append

    if job.open_ended:
        # Three actions, because the tool knows three different things here.
        # `cli._mark_open_records` asks squeue and records the answer on the job,
        # so telling every reader to "confirm against squeue" was sending them to
        # re-run a query the tool had already run -- and, where the answer was
        # that squeue has never heard of the job, withholding the finding's whole
        # point: the record is stale, and its 62-day elapsed is an artefact.
        if job.live is True:
            action = (
                "squeue confirms it is still there — a live job, not a stale record. "
                "Excluded from aggregate totals until it ends."
            )
        elif job.live is False:
            action = (
                "squeue has never heard of it, so the job is long gone and the record was "
                "never closed. The elapsed above is an artefact. Excluded from aggregate "
                "totals."
            )
        else:
            action = "Confirm against squeue. Excluded from aggregate totals."
        add(
            Finding(
                INFO,
                "open-record",
                "Accounting record is not closed",
                "State=%s with End=Unknown. Elapsed (%s) is measured from start to *now*, "
                "not a duration this job spent working."
                % (job.state or "?", format_duration(job.elapsed)),
                action,
            )
        )

    _walltime_rules(job, add)
    _memory_rules(job, add)
    _cpu_rules(job, add)
    _kernel_time_rules(job, add)
    _io_rules(job, add)
    _parallel_rules(job, add)
    _paging_rules(job, add)
    _exit_rules(job, log_text, add)
    _gpu_rules(job, add)

    if node_note:
        add(
            Finding(
                INFO,
                "node-history",
                "Node has a history with your jobs",
                node_note,
                "Consider --exclude if the pattern holds.",
            )
        )

    return Verdict(job=job, findings=tuple(findings))


def looks_like_noop(job):
    """True when the allocation ran a while and consumed almost no CPU."""
    if job.open_ended or job.elapsed is None:
        return False
    total = job.total_cpu
    if total is None:
        return False
    return job.elapsed > NOOP_MIN_ELAPSED and total < NOOP_CPU_SECONDS


def _walltime_rules(job, add):
    state = job.base_state

    if state == "TIMEOUT":
        if looks_like_noop(job):
            add(
                Finding(
                    CRITICAL,
                    "timeout-hang",
                    "Hit the wall clock without ever running",
                    "Held the allocation %s but used only %s of CPU — blocked, not slow."
                    % (format_duration(job.elapsed), format_duration(job.total_cpu)),
                    "Do NOT raise --time; a longer limit buys a longer hang. Find the "
                    "blocking wait — a dataset read, a lock, a rendezvous, a prompt.",
                )
            )
        else:
            used = job.total_cpu
            add(
                Finding(
                    CRITICAL,
                    "timeout-real",
                    "Ran out of wall clock while working",
                    "Hit the %s limit having used %s of CPU (%s) — it was making progress."
                    % (
                        format_duration(job.timelimit),
                        format_duration(used),
                        format_percent(job.cpu_utilization),
                    ),
                    "Raise --time well above the limit that cut it off: Elapsed is "
                    "truncated at the limit, so it bounds the true runtime only from below.",
                )
            )
        return

    if state == "COMPLETED" and not looks_like_noop(job):
        used = job.walltime_used
        if used is not None and used < WALLTIME_SLACK:
            add(
                Finding(
                    INFO,
                    "walltime-slack",
                    "Walltime request much larger than needed",
                    "Used %s of the %s limit (%s)."
                    % (
                        format_duration(job.elapsed),
                        format_duration(job.timelimit),
                        format_percent(used),
                    ),
                    "A tighter --time reaches backfill windows a long request cannot enter.",
                )
            )


def _memory_rules(job, add):
    state = job.base_state
    rss = job.max_rss
    limit = job.mem_limit_bytes

    if state == "OUT_OF_MEMORY":
        detail = "Killed by the cgroup OOM handler (this state is event-driven, so it is reliable)."
        if rss is not None and limit is not None and rss > limit:
            from .site import maxrss_caveat

            detail += (
                " Note MaxRSS reports %s against a %s per-node limit -- above the hard limit, "
                "which is impossible for a working set: %s. Do not size --mem from it."
                % (format_bytes(rss), format_bytes(limit), maxrss_caveat())
            )
        add(
            Finding(
                CRITICAL,
                "host-oom",
                "Host memory exhausted",
                detail,
                "Raise --mem, or cut what multiplies per-worker footprint — workers, "
                "prefetch depth, cache size.",
            )
        )
        return

    if rss is not None and limit is not None and rss > limit:
        from .site import maxrss_caveat

        add(
            Finding(
                WARNING,
                "rss-above-limit",
                "Peak memory reads above the limit, yet nothing was OOM-killed",
                "%s against a %s per-node limit, so it is not this job's footprint: %s."
                % (format_bytes(rss), format_bytes(limit), maxrss_caveat()),
                "Measure the cgroup working set live (slurmwatch) before sizing --mem.",
            )
        )

    if state == "COMPLETED" and rss is not None and limit and not looks_like_noop(job):
        used = rss / float(limit)
        unused = limit - rss
        # Two gates, both required: a large *fraction* left unused AND a large
        # absolute amount. A 90%-unused 2 GiB request is not worth a word.
        if used < MEM_SLACK and unused >= MEM_SLACK_FLOOR:
            add(
                Finding(
                    INFO,
                    "memory-slack",
                    "Reserved far more memory than it touched",
                    "Peak %s of a %s limit (%s) — %s never used."
                    % (
                        format_bytes(rss),
                        format_bytes(limit),
                        format_percent(used),
                        format_bytes(unused),
                    ),
                    # `format_mem_flag`, not `format_bytes`: the display formatter
                    # spelled this "--mem=52.0 GiB", which sbatch rejects.
                    "Try --mem=%s (peak plus ~30%%). MaxRSS over-reports "
                    "multi-process jobs, so treat it as an upper bound."
                    % format_mem_flag(int(rss * 1.3)),
                )
            )

    # No finding for a wide MaxRSS spread between steps. It said "Any tool reading
    # a single step is wrong by that factor" -- a remark about other tools, with no
    # action, about a hazard this one already avoids: Job.max_rss takes the maximum
    # across steps, and the MEM gauge shows that against the limit. Reported as
    # "what does this message mean here?", fairly.


# States whose own outcome already accounts for a near-zero CPU total, so that
# "the allocation did nothing, find the blocking call" would be a second, wrong
# story told on top of the right one. See _cpu_rules.
_NOOP_ALREADY_EXPLAINED = frozenset(["OUT_OF_MEMORY", "NODE_FAIL", "PREEMPTED"])


def _cpu_rules(job, add):
    if job.base_state == "TIMEOUT" or job.open_ended:
        return  # already covered, or not measurable

    # "Find the blocking call" is advice about the user's own code, and it is only
    # honest when nothing else already explains the missing CPU time. For these
    # three states something does, so the finding is suppressed rather than shown
    # beside an explanation that contradicts it:
    #
    #   OUT_OF_MEMORY  the kill IS the explanation, and pairing "raise --mem" with
    #                  "this is not a resource problem" left the user two
    #                  incompatible remedies for one event.
    #   NODE_FAIL      the node died, so the final accounting sample was never
    #                  taken -- a TotalCPU near zero is missing data, not evidence.
    #   PREEMPTED      the scheduler evicted it, often during setup. Real, and not
    #                  a hang in the user's code.
    #
    # Each of the three gets a finding of its own in _exit_rules that names what
    # actually happened. TIMEOUT is handled by the wholesale return above.
    if looks_like_noop(job) and job.base_state not in _NOOP_ALREADY_EXPLAINED:
        add(
            Finding(
                CRITICAL,
                "noop-allocation",
                "Allocation did essentially nothing",
                "%s of wall clock, %s of CPU%s. Nothing was computed."
                % (
                    format_duration(job.elapsed),
                    format_duration(job.total_cpu),
                    (", holding %d GPU(s)" % job.gpu_count) if job.gpu_count else "",
                ),
                "Find the blocking call. If this allocation is a deliberate reservation, "
                "mark it so and this rule will stay quiet.",
            )
        )
        return

    if job.elapsed is None or job.elapsed < MIN_ELAPSED_FOR_CPU_JUDGEMENT:
        return

    util = job.cpu_utilization
    cores = job.cpu_count
    if util is not None and cores and cores > 1 and util < LOW_CPU_UTIL:
        effective = util * cores
        # --cpus-per-task is per task, while every CPU figure sacct reports is a
        # total over the allocation. Suggesting the total told a 90-core, 15-node
        # job to ask for 90 cores per task.
        per_task = job.cpus_per_task or cores
        busy_per_task = util * per_task
        shape = ""
        if job.task_count > 1:
            shape = " across %d tasks" % job.task_count
        add(
            Finding(
                WARNING,
                "cpu-overrequest",
                "Most allocated cores were idle",
                "Utilization %s of %d cores%s, i.e. about %.1f cores of real work."
                % (format_percent(util), cores, shape, effective),
                "Try --cpus-per-task=%d, unless those cores feed dataloader workers."
                % max(1, int(busy_per_task + 0.999)),
            )
        )


# States that are themselves the explanation for a signal 9, so that "look for a
# wrapper or watchdog killing it" would send the reader hunting for a phantom
# alongside the finding that already names the real killer. Slurm reaches for
# SIGKILL on every one of these once KillWait expires -- `scancel`, the wall
# clock, an eviction, a cgroup OOM -- so the signal carries no information the
# state has not already given, and the *action* was the whole value of the rule.
#
# Severity is the other half. CANCELLED, PREEMPTED and NODE_FAIL are not graded as
# failures anywhere else in the tool (`theme.STATE_HEALTH` grades CANCELLED "none"
# because "colouring it red asserts a judgement the data does not support"), yet a
# CRITICAL finding here made `slurmpast <jobid>` exit 1 on a run the tool had just
# called not a failure -- asserting through the exit code what the palette
# deliberately declines to assert in colour. Same suppression, same reason, as
# _NOOP_ALREADY_EXPLAINED above.
_SIGKILL_ALREADY_EXPLAINED = frozenset(
    ["OUT_OF_MEMORY", "TIMEOUT", "CANCELLED", "PREEMPTED", "NODE_FAIL"]
)


def _exit_rules(job, log_text, add):
    code, signal = job.exit_code, job.signal
    state = job.base_state
    lowered = (log_text or "").lower()

    if state == "CANCELLED":
        add(
            Finding(
                INFO,
                "cancelled",
                "Cancelled, not failed",
                "A deliberate kill and an abandoned run are identical in accounting, so this "
                "is excluded from failure statistics.",
                "",
            )
        )

    # NODE_FAIL and PREEMPTED get named for the same reason CANCELLED does: the
    # state is the whole explanation, and without a finding to say so the only
    # plain-English guidance on the screen was the noop rule's "find the blocking
    # call" -- sending the user to debug their own code for a dead node or for the
    # scheduler's own eviction. Both are now suppressed there and explained here.
    if state == "NODE_FAIL":
        add(
            Finding(
                WARNING,
                "node-failed",
                "The node failed under this job",
                "Slurm ended this as NODE_FAIL, so the job did not choose to stop and its "
                "last accounting sample may never have been taken -- a CPU or memory total "
                "near zero here is missing data, not a measurement.",
                "Not your code: resubmit. If one node keeps doing this, the nodes screen "
                "tests whether it fails more than the rest.",
            )
        )

    if state == "PREEMPTED":
        add(
            Finding(
                INFO,
                "preempted",
                "Preempted, not failed",
                "The scheduler reclaimed this allocation for higher-priority work, so how "
                "far it got says nothing about whether the job was healthy.",
                "Requeue it. If this keeps happening, a higher-priority QOS or a partition "
                "with less contention will hold onto the allocation.",
            )
        )

    if code == 127:
        add(
            Finding(
                CRITICAL,
                "command-not-found",
                "A command in the script was not found (exit 127)",
                "The shell could not locate an executable.",
                "Check `module load` / conda activation ordering, and that the env is "
                "activated before the interpreter is invoked.",
            )
        )
    if (signal == 9 or code == 137) and state not in _SIGKILL_ALREADY_EXPLAINED:
        add(
            Finding(
                CRITICAL,
                "sigkill",
                "Killed by SIGKILL",
                "Exit signal 9, and nothing in the accounting record accounts for it: the "
                "state is %s, not OUT_OF_MEMORY, TIMEOUT, CANCELLED, PREEMPTED or NODE_FAIL, "
                "each of which would name its own killer." % (state or "unrecorded"),
                "Look for a wrapper or watchdog killing it — a queue system layered over "
                "Slurm, a `timeout` in the batch script, or the node's own OOM killer "
                "reaping a process Slurm was not accounting for.",
            )
        )

    if not lowered:
        if code not in (None, 0) and state == "FAILED":
            # Named for the code actually recorded. Hardcoding "Exit 1" put a
            # finding on screen whose title said "Exited 3" and whose evidence
            # discussed exit 1 -- self-contradictory in the same paragraph.
            if code == 1:
                detail = (
                    "Exit 1 is the generic Python-exception status and is "
                    "indistinguishable from a CUDA OOM without the stderr text."
                )
            else:
                detail = (
                    "An exit status does not name a cause: exit %d is indistinguishable "
                    "from a CUDA OOM, a killed worker or a bad argument without the "
                    "stderr text." % code
                )
            add(
                Finding(
                    WARNING,
                    "exit-nonzero-nolog",
                    "Exited %d, but no log was found to explain it" % code,
                    detail,
                    "Pass --log-dir, or set a predictable --error= path.",
                )
            )
        return

    if any(marker in lowered for marker in _CUDA_OOM_MARKERS):
        add(
            Finding(
                CRITICAL,
                "cuda-oom",
                "GPU ran out of memory",
                "Device-side allocation failure in the log. This is NOT host memory -- "
                "raising --mem changes nothing.",
                "Lower batch size, enable gradient checkpointing, or shard the model. "
                "Consider a card with more HBM.",
            )
        )
    if any(marker in lowered for marker in _NCCL_MARKERS):
        add(
            Finding(
                CRITICAL,
                "nccl",
                "Collective communication fault",
                "NCCL markers in the log. A collective timeout is usually a symptom: one rank "
                "diverged, died, or is slow, and the others block on it.",
                "Compare ranks rather than trusting the reported rank -- the one that reports "
                "the timeout is typically the victim, not the cause.",
            )
        )
    if any(marker in lowered for marker in _IMPORT_MARKERS):
        add(
            Finding(
                CRITICAL,
                "import-error",
                "Python could not import a dependency",
                "Import failure in the log -- the environment differs from where it was tested.",
                "Pin the environment: record the conda env and a pip freeze hash with the run.",
            )
        )

    tail = _traceback_tail(log_text)
    if tail:
        add(Finding(INFO, "traceback", "Traceback tail from the log", tail, ""))


def _traceback_tail(log_text, max_lines=6):
    """Last Python traceback in the log, trimmed."""
    if not log_text:
        return ""
    lines = log_text.splitlines()
    start = None
    for idx in range(len(lines) - 1, -1, -1):
        if lines[idx].strip().startswith("Traceback (most recent call last)"):
            start = idx
            break
    if start is None:
        return ""
    chunk = [ln.rstrip() for ln in lines[start:] if ln.strip()]
    if len(chunk) > max_lines:
        chunk = [chunk[0], "  ..."] + chunk[-(max_lines - 2) :]
    return "\n".join(chunk)


def _gpu_rules(job, add):
    if not job.gpu_count or job.open_ended:
        return
    if looks_like_noop(job):
        return

    # Where the site runs AutoDetect=nvml, Slurm gathered gres/gpuutil and there
    # is nothing to infer. Prefer the measurement over the proxy: the CPU-based
    # hint below exists only because most clusters record no such thing.
    measured = job.gpu_utilization
    if measured is not None:
        if measured < GPU_IDLE:
            add(
                Finding(
                    CRITICAL,
                    "gpu-idle",
                    "GPUs were held but barely used",
                    "%d GPU(s) held for %s at %s average utilization, as recorded by Slurm."
                    % (job.gpu_count, format_duration(job.elapsed), format_percent(measured)),
                    "This is a measurement, not an inference. Either the work is not on the "
                    "device or the device is waiting on input -- check the dataloader before "
                    "asking for more cards.",
                )
            )
        elif measured < GPU_UNDERUSED:
            add(
                Finding(
                    WARNING,
                    "gpu-underused",
                    "GPUs were only partly busy",
                    "%s average utilization across %d device(s) over %s."
                    % (format_percent(measured), job.gpu_count, format_duration(job.elapsed)),
                    "Raise the work per step -- batch size, sequence length, or fewer "
                    "grad-accumulation micro-steps -- until the card is the bottleneck.",
                )
            )
        return

    util = job.cpu_utilization
    if util is None:
        return
    # A CUDA process must burn host CPU to launch kernels. Very low CPU with GPUs
    # held is a strong hint the GPUs were never driven -- but it is a hint, so
    # this is a WARNING with the evidence shown, not a verdict.
    if util < 0.02:
        add(
            Finding(
                WARNING,
                "gpu-suspect-idle",
                "GPUs allocated but host CPU barely moved",
                "%d GPU(s) held for %s at %s CPU utilization; kernel launches consume host "
                "CPU, so this suggests the GPUs were mostly unused."
                % (job.gpu_count, format_duration(job.elapsed), format_percent(util)),
                "Confirm with live telemetry (slurmwatch): this cluster does not record "
                "post-hoc GPU utilization, so the reading above is a proxy.",
            )
        )


def _kernel_time_rules(job, add):
    """CPU spent in the kernel rather than in your code.

    ``UserCPU`` and ``SystemCPU`` are recorded separately and nothing reports
    the split. A healthy training run sits near 5%; a job well above that is
    paying for syscalls -- many small reads, filesystem metadata traffic,
    process churn -- and the single TotalCPU figure hides it completely.
    """
    if job.open_ended or looks_like_noop(job):
        return
    fraction = job.system_cpu_fraction
    if fraction is None or fraction < SYSTEM_CPU_HEAVY:
        return
    if (job.total_cpu or 0) < 60:
        return  # too little CPU for the ratio to mean anything
    add(
        Finding(
            WARNING,
            "system-cpu-heavy",
            "Most CPU time went to the kernel, not your code",
            # The percentage leads. "1h05m21s of 2h54m17s" is a duration divided by
            # a duration, and the denominator is core-time -- a synthetic figure the
            # reader has to reconstruct. The raw split is in the cpu section.
            # "~5%" was wrong and the comparison it invited was misleading: measured
            # across 5,343 real jobs on this cluster the kernel share runs 6.2% at
            # the first quartile and 16.7% at the median, so a reader at 20% was
            # being told they were 4x off a healthy figure when they were below
            # average. The threshold is the third quartile, so that is what it says.
            "%s of CPU time went to the kernel, against a median of ~17%% here."
            % format_percent(fraction),
            "That is syscall overhead: batch small reads, or pack many small files into shards.",
        )
    )


def _io_rules(job, add):
    """Disk read and write, kept apart.

    ``TRESUsageInTot`` is reads and ``TRESUsageOutTot`` is writes. Reading only
    the ``In`` direction -- as the first version of this tool did -- misses
    writes entirely: one real run read 112 GB and wrote 139 GB, and half the
    traffic was invisible.
    """
    if job.open_ended:
        return
    total = job.io_bytes
    if not total or total < IO_VOLUME_FLOOR:
        return
    read, write = job.read_bytes or 0, job.write_bytes or 0
    rate = job.io_rate
    detail = "read %s, wrote %s" % (format_bytes(read), format_bytes(write))
    if rate:
        detail += " -- %s/s sustained over %s" % (format_bytes(rate), format_duration(job.elapsed))

    if rate and rate >= IO_RATE_LOUD:
        add(
            Finding(
                WARNING,
                "io-heavy",
                "Filesystem may be setting the pace, not the GPU",
                detail + ".",
                "Check whether the input sits on the capacity tier; stage it to a "
                "performance tier once it is reused enough to repay the copy.",
            )
        )
    # No INFO for merely moving a lot of data. It restated the DISK row above it
    # verbatim -- same bytes, same rate -- and carried no action, so it was two
    # lines of a finding list saying what the reader had just read.


def _parallel_rules(job, add):
    """Signals that only exist once a step has more than one task."""
    if job.open_ended or job.task_count <= 1:
        return

    spread = job.straggler_spread
    if spread is not None and spread >= STRAGGLER_SPREAD:
        node, task = job.slowest_task
        where = ""
        if node:
            where = " The laggard was task %s on %s." % (task or "?", node)
        add(
            Finding(
                WARNING,
                "straggler",
                "One task did far less work than its peers",
                "The slowest task consumed %s less CPU than the average across %d "
                "tasks.%s In a synchronous collective every other rank waits on it."
                % (format_percent(spread), job.task_count, where),
                "Compare ranks rather than trusting whichever one reported an error: "
                "the rank that times out is usually the victim, not the cause.",
            )
        )

    imbalance = job.rss_task_imbalance
    if imbalance is not None and imbalance >= RSS_IMBALANCE:
        add(
            Finding(
                INFO,
                "task-memory-imbalance",
                "Memory use is uneven across tasks",
                "Peak task held %s against a %s average (%.1fx). The job's memory "
                "ceiling has to cover the largest task, not the mean."
                % (format_bytes(job.max_rss), format_bytes(job.ave_rss), imbalance),
                "",
            )
        )


def _paging_rules(job, add):
    """Page faults mean the job was thrashing, which no other tool surfaces."""
    if job.open_ended:
        return
    pages = job.max_pages
    # A few dozen major faults is ordinary process startup. Only sustained
    # faulting says the job was thrashing -- firing at >0 flagged jobs with 15
    # faults, which is noise.
    if not pages or pages < PAGING_FLOOR:
        return
    add(
        Finding(
            WARNING,
            "paging",
            "The job was paging",
            "%s major page faults recorded. Memory pressure forced the kernel to "
            "fetch pages from disk, which is orders of magnitude slower than RAM "
            "and does not show up as a failure." % f"{int(pages):,}",
            "Raise --mem, or cut the working set. A job that pages can finish and "
            "still have run many times slower than it needed to.",
        )
    )
