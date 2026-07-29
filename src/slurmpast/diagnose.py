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

from .duration import format_bytes, format_duration, format_percent
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
        add(
            Finding(
                INFO,
                "open-record",
                "Accounting record is not closed",
                "State=%s with End=Unknown. Elapsed (%s) is measured from start to *now*, "
                "not a duration this job spent working."
                % (job.state or "?", format_duration(job.elapsed)),
                "Confirm against squeue. Excluded from aggregate totals.",
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
                    "Raise --time with real headroom: Elapsed is truncated at the limit, "
                    "so it bounds the true runtime only from below.",
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
            detail += (
                " Note MaxRSS reports %s against a %s limit -- above the hard limit, which is "
                "impossible for a working set. jobacct_gather/linux sums RSS over the process "
                "tree and double-counts shared pages, so do not size --mem from it."
                % (format_bytes(rss), format_bytes(limit))
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
        add(
            Finding(
                WARNING,
                "rss-above-limit",
                "Peak memory reads above the limit, yet nothing was OOM-killed",
                "%s against a %s limit: MaxRSS sums shared pages across the process "
                "tree, so it is not this job's footprint."
                % (format_bytes(rss), format_bytes(limit)),
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
                    "Try --mem=%s (peak plus ~30%%). MaxRSS over-reports "
                    "multi-process jobs, so treat it as an upper bound."
                    % format_bytes(int(rss * 1.3)),
                )
            )

    # No finding for a wide MaxRSS spread between steps. It said "Any tool reading
    # a single step is wrong by that factor" -- a remark about other tools, with no
    # action, about a hazard this one already avoids: Job.max_rss takes the maximum
    # across steps, and the MEM gauge shows that against the limit. Reported as
    # "what does this message mean here?", fairly.


def _cpu_rules(job, add):
    if job.base_state == "TIMEOUT" or job.open_ended:
        return  # already covered, or not measurable

    if looks_like_noop(job):
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
        add(
            Finding(
                WARNING,
                "cpu-overrequest",
                "Most allocated cores were idle",
                "Utilization %s of %d cores, i.e. about %.1f cores of real work."
                % (format_percent(util), cores, effective),
                "Try --cpus-per-task=%d, unless those cores feed dataloader workers."
                % max(1, int(effective + 0.999)),
            )
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
    if signal == 9 or code == 137:
        add(
            Finding(
                CRITICAL,
                "sigkill",
                "Killed by SIGKILL",
                "Exit signal 9. Either an out-of-memory kill or an external cancellation; "
                "Slurm records a cgroup OOM as OUT_OF_MEMORY, and this job is %s." % (state or "?"),
                "If state is not OUT_OF_MEMORY, look for a wrapper or watchdog killing it.",
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
    util = job.cpu_utilization
    if util is None or looks_like_noop(job):
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
                "Confirm with live telemetry (slurmwatch): post-hoc GPU utilization is not "
                "recorded here.",
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
            "%s of CPU time went to the kernel; a healthy run here is ~5%%."
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
