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
# Fault signatures, not the word "NCCL". The bare substring was in this tuple, and
# every distributed PyTorch job prints NCCL at startup and at shutdown -- so a
# CRITICAL "Collective communication fault" was manufactured out of, among others:
#
#     [rank0]:[W818 12:54] ProcessGroupNCCL.cpp:1524] Warning: WARNING:
#         destroy_process_group() was not called before program exit
#     INFO [parallel_state.py:1208] ... distributed_init_method=... backend=nccl
#     NCCL version 2.19.3+cuda12.1
#
# Measured on 400 real log files: ten mention NCCL, none of them faulted, and every
# one of the ten drew the finding. Two of those jobs had a genuine CUDA OOM, so the
# reader got two CRITICALs -- one real, one sending them to debug an interconnect
# that was fine.
#
# Every marker below is a string a healthy run does not print, and the set is
# checked both ways: zero hits across those ten logs, and hits on all five real
# fault shapes -- the watchdog timeout, `DistBackendError: NCCL error`,
# `ncclUnhandledCudaError`, `ncclInternalError`, and NCCL's own `NCCL WARN`
# channel, which it uses for trouble rather than for chatter.
_NCCL_MARKERS = (
    "watchdog caught collective operation timeout",
    "ncclinternalerror",
    "ncclunhandledcudaerror",
    "ncclsystemerror",
    "ncclremoteerror",
    "nccl error",
    "nccl timeout",
    "nccl warn",
    "distbackenderror",
)
_IMPORT_MARKERS = ("modulenotfounderror", "importerror", "no module named")


def _slack_sampling_warning(job):
    """The floor caveat for advice that says to ask for *less* memory.

    SP-22 was fixed on the OUT_OF_MEMORY path, where the kill proves the peak. The
    reporter's next round supplied the other half without meaning to: a 20-second
    chain job that allocated 40 MiB recorded ``MaxRSS 2484K``, and called it
    "another instance of SP-22, not a new finding" -- correctly, because it is the
    same sparse sampler. But that job is COMPLETED, so nothing on the OOM path
    covers it, and this is the finding that fires there.

    It is the more dangerous direction of the two. Over-reporting inflates a
    number a reader might leave alone; a missed spike here becomes "Try --mem=3G"
    against a 64 GiB request, and taking that advice under-provisions a job that
    then gets killed for it.
    """
    from .site import maxrss_sampling_note

    note = maxrss_sampling_note(job.elapsed)
    if not note:
        return ""
    return "  Thinly sampled (%s), so the peak may be a floor." % note


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
                "squeue has never heard of it: long gone, record never closed. The "
                "elapsed is an artefact. Excluded from totals."
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
                    "Raise --time well above it: Elapsed is truncated at the limit, so "
                    "it only bounds the true runtime from below.",
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
        detail = "OOM-killed by the cgroup."
        if rss is not None and limit is not None and rss > limit:
            from .site import maxrss_caveat

            detail += (
                " MaxRSS reads %s over a %s limit — impossible for a working set, so do not "
                "size --mem from it: %s."
                % (format_bytes(rss), format_bytes(limit), maxrss_caveat())
            )
        elif rss is not None and limit is not None:
            # The understating direction, and the one the reader cannot spot from
            # the number. Every other sentence this tool has about MaxRSS explains
            # how it *over*-reports; here the kill proves the peak reached the
            # limit while the sample sat 21x below it, so repeating the
            # over-report caveat would be the one reading the evidence rules out.
            from .site import maxrss_sampling_note

            detail += (
                " MaxRSS sampled %s of the %s limit, but the peak reached it — that "
                "sample is a floor, not the footprint." % (format_bytes(rss), format_bytes(limit))
            )
            note = maxrss_sampling_note(job.elapsed)
            if note:
                detail += " (%s)" % note
        add(
            Finding(
                CRITICAL,
                "host-oom",
                "Host memory exhausted",
                detail,
                "Raise --mem, or cut workers, prefetch depth, cache size.",
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
            # Deferred like the two `maxrss_caveat` calls above, and for the same
            # reason: `site` shells out to `scontrol`.
            from .site import maxrss_caveat

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
                    #
                    # The caveat is asked of `site` rather than written out here.
                    # Hardcoded, it said MaxRSS "over-reports multi-process jobs"
                    # unconditionally -- true under `jobacct_gather/linux`, false
                    # under `jobacct_gather/cgroup`, where the number is the
                    # cgroup's own peak. On Mercury that put this sentence in
                    # direct contradiction with the one `--sizing` prints about
                    # the same figure in the same run.
                    "Try --mem=%s (peak plus ~30%%). %s.%s"
                    % (
                        format_mem_flag(int(rss * 1.3)),
                        maxrss_caveat(),
                        _slack_sampling_warning(job),
                    ),
                )
            )

    # No finding for a wide MaxRSS spread between steps. It said "Any tool reading
    # a single step is wrong by that factor" -- a remark about other tools, with no
    # action, about a hazard this one already avoids: Job.max_rss takes the maximum
    # across steps, and the MEM gauge shows that against the limit. Reported as
    # "what does this message mean here?", fairly.


# States whose own outcome already accounts for a near-zero CPU total, so that any
# reading of that total is a second, wrong story told on top of the right one.
#
# This governed one rule and needed to govern three. Suppressing the noop finding
# alone did not remove the wrong advice -- it moved it: `_cpu_rules` returns only
# on the branch that *fires*, so a NODE_FAIL fell straight through to
# `cpu-overrequest` and got "Most allocated cores were idle. Try --cpus-per-task=1"
# printed two findings above "a CPU or memory total near zero here is missing data,
# not a measurement". `gpu-suspect-idle` infers from the same figure and did the
# same. The guard now covers every rule that reads CPU utilization, which is what
# the sentence above always meant.
#
# BOOT_FAIL and DEADLINE are here because they were in neither this set nor
# `_exit_rules`: the node never came up, or the scheduler enforced --deadline, and
# the only thing on screen was "Allocation did essentially nothing -- find the
# blocking call". Both are counted by `Job.failed`, graded "crit" by
# `theme.STATE_HEALTH` and queried by `--failed`; `diagnose` was the one module
# that had never heard of them. Each now gets a finding of its own below, the same
# way CANCELLED, NODE_FAIL and PREEMPTED do.
#
# CANCELLED is deliberately NOT here. Its own finding says the *outcome* is
# ambiguous, not that the CPU total is unreadable, so a cancelled run that used one
# of sixteen cores is still evidence about the request.
_CPU_TIME_ALREADY_EXPLAINED = frozenset(
    ["OUT_OF_MEMORY", "NODE_FAIL", "PREEMPTED", "BOOT_FAIL", "DEADLINE"]
)


def _io_explains_idle_cpu(job):
    """True when the filesystem already accounts for the missing CPU time.

    Exactly the condition `_io_rules` uses to raise `io-heavy`, so this is true
    precisely when that finding is about to appear beside this one. Sharing the
    test rather than picking a second threshold is deliberate: the defect being
    fixed is two findings on one screen disagreeing, so the guard has to fire on
    the same jobs the other rule does, not on a similar-looking set.
    """
    total, rate = job.io_bytes, job.io_rate
    return bool(total and total >= IO_VOLUME_FLOOR and rate and rate >= IO_RATE_LOUD)


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
    if job.base_state in _CPU_TIME_ALREADY_EXPLAINED:
        # Every rule below reads the same CPU total, so the whole function stops
        # here rather than only the noop branch. See the note on the set.
        return

    if looks_like_noop(job):
        held = (", holding %d GPU(s)" % job.gpu_count) if job.gpu_count else ""
        if _io_explains_idle_cpu(job):
            # The same honesty test the three states above get, applied to a
            # measurement instead of a state. "Nothing was computed" sat directly
            # above `io-heavy` reporting 18.4 TiB read at 284.4 MiB/s sustained
            # over the same 18:52:05 -- the tool naming the blocking call one line
            # under an action telling the reader to go find it. Across 20,905 real
            # jobs, 986 were told nothing was computed and 287 of those had moved
            # at least the 10 GiB floor, 419.3 TiB between them.
            #
            # Still CRITICAL, and still raised: an allocation that holds GPUs for
            # nineteen hours to feed a filesystem is wasting them whatever the
            # cause. What changes is that the finding no longer denies the traffic
            # the next line reports, and no longer sends the reader into their own
            # code after a hang that is not there.
            add(
                Finding(
                    CRITICAL,
                    "noop-allocation",
                    "Allocation computed almost nothing — it was moving data",
                    "%s of wall clock, %s of CPU%s, and %s of filesystem traffic at "
                    "%s/s. The time went to I/O, not to compute."
                    % (
                        format_duration(job.elapsed),
                        format_duration(job.total_cpu),
                        held,
                        format_bytes(job.io_bytes or 0),
                        format_bytes(job.io_rate or 0),
                    ),
                    "Not a hang, an I/O problem: stage the input somewhere faster, or "
                    "overlap the transfer with compute.",
                )
            )
            return
        # Same validity problem as `cpu-overrequest` below, one rule over and a
        # severity higher. "Nothing was computed" is an absolute claim read off
        # `TotalCPU`, which under `jobacct_gather/linux` cannot see a reparented
        # worker pool -- so a `multisession` job whose master idles while eight
        # detached workers burn hundreds of core-seconds lands here and is sent to
        # "find the blocking call" that does not exist. The reported job cleared
        # the floor by 13x and escaped; the reporter's arm C, 3.08 CPU-seconds
        # over 31s, is the shape that does not.
        #
        # The threshold is *not* re-keyed: separating "idle" from "counted
        # elsewhere" needs evidence `sacct` does not carry, and moving the floor
        # without it trades a wrong CRITICAL for a missed one. What is fixed is
        # the honesty -- the sentence now states what was recorded rather than
        # what happened, and the caveat says which of those two this cluster can
        # tell apart.
        from .site import cpu_caveat, cpu_total_is_complete

        # "Nothing was computed" is a claim about the *job*; the record only
        # supports a claim about what was *attributed*. Where the cluster gathers
        # from the cgroup the two are the same thing and the original sentence
        # stands. Where it does not, they are not, and the softer sentence plus
        # the caveat is the most the record will carry.
        if cpu_total_is_complete():
            outcome = "Nothing was computed."
        else:
            outcome = "No CPU time was attributed to it. %s." % cpu_caveat()
        add(
            Finding(
                CRITICAL,
                "noop-allocation",
                "Allocation did essentially nothing",
                "%s of wall clock, %s of CPU%s. %s"
                % (
                    format_duration(job.elapsed),
                    format_duration(job.total_cpu),
                    held,
                    outcome,
                ),
                "Find the blocking call — or the work, if a detached pool ran it where "
                "this cluster cannot see it.",
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
        # Imported here rather than at module scope, matching the two
        # `maxrss_caveat` call sites above: `site` shells out to `scontrol` on
        # first use, and `diagnose` is imported by paths that never need it.
        from .site import cpu_caveat

        # The evidence carries the cluster's own caveat, exactly as the memory
        # finding carries `maxrss_caveat()`. `TotalCPU` cannot see work in
        # processes reparented out of the step's tree, so on a
        # `jobacct_gather/linux` site this utilisation is a lower bound. Reported
        # from a second cluster on an eight-worker R `multisession` job that ran
        # in 24 minutes what would take four hours serially, and was told to ask
        # for one core.
        #
        # Caveated, not suppressed. The reporter is right that
        # `_CPU_TIME_ALREADY_EXPLAINED` is the wrong instrument here: that set is
        # for states where the number is garbage, and this number is real work
        # really done — it is just not all of it.
        add(
            Finding(
                WARNING,
                "cpu-overrequest",
                "Most allocated cores were idle",
                "Utilization %s of %d cores%s, i.e. about %.1f cores of real work. %s."
                % (format_percent(util), cores, shape, effective, cpu_caveat()),
                "Try --cpus-per-task=%d — unless the cores feed dataloader workers, or "
                "a detached worker pool this cluster cannot attribute."
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
# _CPU_TIME_ALREADY_EXPLAINED above.
_SIGKILL_ALREADY_EXPLAINED = frozenset(
    ["OUT_OF_MEMORY", "TIMEOUT", "CANCELLED", "PREEMPTED", "NODE_FAIL"]
)


#: What to tell a user whose job died because the NODE did, not their code.
#:
#: One sentence for both `NODE_FAIL` and `BOOT_FAIL`: the cause differs (a node
#: that fell over mid-job against one that never came up) but the remedy does
#: not, and it was written out at each. Two copies of a remedy is how the same
#: advice comes to be worded two ways for two findings a reader sees side by side.
_NODE_FAULT_REMEDY = (
    "Not your code: resubmit. If one node keeps doing this, the nodes screen "
    "tests whether it fails more than the rest."
)


#: Signal numbers spelled out, for the finding that names the killer.
#:
#: A table rather than ``signal.Signals(n).name``: that raises ``ValueError`` for
#: a number the running platform does not define, and this cluster's accounting
#: carries a record with signal 40. Anything the table does not hold still
#: reports as a number, which is what ``sacct`` itself prints.
_SIGNAL_NAMES = {
    1: "SIGHUP",
    2: "SIGINT",
    3: "SIGQUIT",
    6: "SIGABRT",
    9: "SIGKILL",
    11: "SIGSEGV",
    13: "SIGPIPE",
    15: "SIGTERM",
    24: "SIGXCPU",
    25: "SIGXFSZ",
}


def _signal_name(number):
    """``15`` -> ``"SIGTERM"``; a number with no name -> ``"signal 40"``."""
    return _SIGNAL_NAMES.get(number) or "signal %d" % number


def _cancelled_by(state):
    """The uid out of ``sacct``'s ``CANCELLED by <uid>``, or ``""``.

    ``_canonical_state`` preserves that suffix on purpose -- "`Job.state` carries
    it, `Job.base_state` drops it, and **both are read**" -- and this is the
    reader. Only the exact three-token numeric shape counts: a bare ``CANCELLED``,
    or a name where the uid should be, returns ``""`` so the caller says nothing
    rather than guessing at a canceller.
    """
    parts = (state or "").split()
    if len(parts) == 3 and parts[0] == "CANCELLED" and parts[1] == "by" and parts[2].isdigit():
        return parts[2]
    return ""


def _exit_rules(job, log_text, add):
    code, signal = job.exit_code, job.signal
    state = job.base_state
    lowered = (log_text or "").lower()

    if state == "CANCELLED":
        # WHO cancelled it, when the record says and it was not the submitter.
        # The single sentence below offers a reader two possibilities -- "a
        # deliberate kill" and "an abandoned run" -- and both of them are the
        # submitter's own, so on a job somebody else cancelled neither is true.
        # Three jobs in this cluster's 90-day history are `CANCELLED by 0`,
        # including a 3-day reservation, and each was reported as though the owner
        # had killed it.
        #
        # Claimed only when BOTH uids are on the record and they differ. An empty
        # `UID` means the comparison cannot be made, not that it came back False
        # -- the same rule `site` states for a missing configuration fact -- and
        # the ordinary self-cancellation keeps the wording, the code and the empty
        # action it has always had.
        canceller = _cancelled_by(job.state)
        if canceller and job.uid and canceller != job.uid:
            if canceller == "0":
                title = "Cancelled by root, not by you"
                detail = (
                    "CANCELLED by root, not by uid %s — an admin or the scheduler ended it, "
                    "so how far it got says nothing about its health." % job.uid
                )
                action = (
                    "Check for a maintenance window, a QOS limit, or an unsatisfiable "
                    "dependency before resubmitting."
                )
            else:
                title = "Cancelled by another user, not by you"
                detail = (
                    "CANCELLED by %s, not by uid %s — somebody you share an account or "
                    "reservation with ran the scancel." % (canceller, job.uid)
                )
                action = "Find out who holds uid %s before resubmitting." % canceller
            add(Finding(INFO, "cancelled-by-other", title, detail, action))
        else:
            add(
                Finding(
                    INFO,
                    "cancelled",
                    "Cancelled, not failed",
                    "Excluded from failure stats: a deliberate kill and an abandoned run "
                    "are identical in accounting.",
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
                "NODE_FAIL: the node died, not the job. A near-zero CPU or memory total "
                "here is missing data, not a measurement.",
                _NODE_FAULT_REMEDY,
            )
        )

    if state == "BOOT_FAIL":
        add(
            Finding(
                WARNING,
                "boot-failed",
                "The node never came up for this job",
                "BOOT_FAIL: the allocation was made and the node failed to boot into it. "
                "None of your work ran, so nothing here measures it.",
                _NODE_FAULT_REMEDY,
            )
        )

    if state == "DEADLINE":
        add(
            Finding(
                # CRITICAL, like both TIMEOUT findings: the job was cut off by a
                # limit before it finished, and `model.py` already groups the two
                # ("DEADLINE belongs here for the same reason TIMEOUT does").
                # BOOT_FAIL above is a WARNING, like NODE_FAIL, for the opposite
                # reason -- nothing the submitter did caused it.
                CRITICAL,
                "deadline",
                "Killed at its --deadline, not its time limit",
                "DEADLINE: the --deadline moment arrived. That is a different limit from "
                "--time, and raising --time does not extend it.",
                "Move or drop --deadline, or submit earlier. A longer --time changes nothing here.",
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
    # ANY terminating signal, not only 9. `sacct` spells a signal kill
    # `0:<signal>` -- the number before the colon is 0 -- so `signal == 9` named
    # SIGKILL and nothing else, and SIGTERM is the signal every supervisor sends
    # *first*: `timeout`, a shell trap, a watchdog, a queue system layered over
    # Slurm. Over this cluster's 90-day history the FAILED jobs whose kill came
    # from outside are `0:15`, and each produced no finding at all -- the only
    # thing on screen was the noop rule's "Allocation did essentially nothing ->
    # Find the blocking call", about a job something else had terminated. That is
    # the identical defect NODE_FAIL, BOOT_FAIL and DEADLINE were each given a
    # finding for above.
    #
    # `code == 137` stays as its own arm: that is the shell's 128+9, which a
    # wrapper can propagate as the exit status with no signal recorded beside it.
    #
    # The suppression set and the action carry over unaltered, because their
    # reasoning does: Slurm sends SIGTERM *before* SIGKILL on scancel, the wall
    # clock, an eviction and a cgroup OOM, so on those states neither signal
    # carries anything the state has not already given.
    #
    # `sigkill` keeps its finding code for signal 9 so no `--json` consumer sees a
    # rename; the signals it never covered get `signal-kill`.
    killer = signal if signal else (9 if code == 137 else None)
    if killer and state not in _SIGKILL_ALREADY_EXPLAINED:
        add(
            Finding(
                CRITICAL,
                "sigkill" if killer == 9 else "signal-kill",
                "Killed by %s" % _signal_name(killer),
                "Exit signal %d, and the state (%s) does not account for it — no Slurm "
                "limit names this killer." % (killer, state or "unrecorded"),
                "Look for a wrapper or watchdog: a queue layered over Slurm, a `timeout` "
                "in the script, or the node's own OOM killer.",
            )
        )

    if not lowered:
        if code not in (None, 0) and state == "FAILED":
            # Whether a rule above has already named this exact status. 127 is the
            # shell's "command not found" and 137 is 128+9, and each has a finding
            # of its own a few lines up -- so the generic sentence below, which says
            # the status names nothing, contradicted the finding directly above it
            # in the same report:
            #
            #   [FAIL] A command in the script was not found (exit 127)
            #   [WARN] An exit status does not name a cause: exit 127 is
            #          indistinguishable from a CUDA OOM ...
            #
            # That is the same self-contradiction the note below records fixing
            # *within* one finding, reappearing between two. The log is still worth
            # asking for on these -- it says which command, and where -- so the
            # finding stays and only its claim changes.
            # `bool(signal)`, not `signal == 9`: the rule above now fires for any
            # signal, so this has to agree with it or the report contradicts
            # itself again -- "Killed by SIGTERM" over "an exit status does not
            # name a cause" is the same pair of lines the comment above records.
            named_above = code in (127, 137) or bool(signal)
            # Named for the code actually recorded. Hardcoding "Exit 1" put a
            # finding on screen whose title said "Exited 3" and whose evidence
            # discussed exit 1 -- self-contradictory in the same paragraph.
            if named_above:
                title = "Exited %d, and no log to confirm it" % code
                detail = (
                    "The status is named above. What it does not say is which command "
                    "produced it or how far the run got, and that is in the stderr text."
                )
            elif code == 1:
                title = "Exited 1, but no log was found to explain it"
                detail = (
                    "Exit 1 is the generic Python-exception status and is "
                    "indistinguishable from a CUDA OOM without the stderr text."
                )
            else:
                title = "Exited %d, but no log was found to explain it" % code
                detail = (
                    "An exit status does not name a cause: exit %d is indistinguishable "
                    "from a CUDA OOM, a killed worker or a bad argument without the "
                    "stderr text." % code
                )
            add(
                Finding(
                    WARNING,
                    "exit-nonzero-nolog",
                    title,
                    detail,
                    "Pass --log-dir, or set a predictable --error= path.",
                )
            )
        return

    # A GPU cause cannot belong to a job that was never given a GPU. The job
    # record already says so -- `AllocTRES` carries no `gres` entry -- and not
    # checking it let a mis-attached log produce a *critical* "GPU ran out of
    # memory" for a job on a GPU-less partition: reported from a second cluster,
    # where a decoy file with the same mtime was matched by timing and the real
    # cause (`disk quota exceeded`) never appeared. The log-matching hedge was
    # printed, but one dim line of caveat does not balance the loudest severity
    # the tool emits, stated as fact and followed by four remediations.
    #
    # This does not make the wrong log right -- it is still the wrong log. It
    # stops the tool from asserting, on evidence it holds, a cause it can rule
    # out. Only the GPU rules are gated: a traceback or an import error in a
    # mis-attached log is still a possible cause for any job.
    # `job.gpu_count`, the *identical* test `_gpu_rules` uses at its own top --
    # not a similar one. A looser spelling here (say, "gres" appearing anywhere in
    # AllocTRES) would let `cuda-oom` fire on a job where the GPU-utilisation
    # findings stay silent, which is two findings on one screen disagreeing about
    # whether the job had a GPU at all. `_io_explains_idle_cpu` sets that standard
    # explicitly a few hundred lines up: share the condition rather than pick a
    # second threshold, "so the guard has to fire on the same jobs the other rule
    # does, not on a similar-looking set."
    if job.gpu_count and any(marker in lowered for marker in _CUDA_OOM_MARKERS):
        add(
            Finding(
                CRITICAL,
                "cuda-oom",
                "GPU ran out of memory",
                "Device-side allocation failure in the log. This is NOT host memory — "
                "raising --mem changes nothing.",
                "Lower batch size, enable gradient checkpointing, or shard the model. "
                "Consider a card with more HBM.",
            )
        )
    # Two preconditions, because a collective fault needs both a device and a peer.
    # NCCL is NVIDIA-only, so no GPU means nothing was running it; and with a
    # single rank there is nobody to block on, which is what this finding's own
    # explanation describes -- "one rank diverged, died, or is slow, and the
    # others block on it". Reported for a job whose entire allocation read
    # `billing=1,cpu=1,mem=200M,node=1` and which drew this at CRITICAL.
    #
    # A rank is not a task. The report proposed `nodes > 1 or ntasks > 1`, and
    # that is wrong here: the suite's own `healthy_job` is `gres/gpu=3` on
    # `node=1` with no NTasks recorded, and three GPUs on one node do collectives
    # across each other all day. Testing tasks and nodes alone would have
    # suppressed five real fault shapes this suite already pins -- it caught it
    # immediately. Whichever of the three is largest is the rank count.
    collective_possible = job.gpu_count and (
        job.gpu_count > 1 or job.task_count > 1 or job.node_count > 1
    )
    if collective_possible and any(marker in lowered for marker in _NCCL_MARKERS):
        add(
            Finding(
                CRITICAL,
                "nccl",
                "Collective communication fault",
                "NCCL markers in the log. A collective timeout is usually a symptom: one rank "
                "diverged, died, or is slow, and the others block on it.",
                "Compare ranks rather than trusting the reported rank — the one that reports "
                "the timeout is typically the victim, not the cause.",
            )
        )
    if any(marker in lowered for marker in _IMPORT_MARKERS):
        add(
            Finding(
                CRITICAL,
                "import-error",
                "Python could not import a dependency",
                "Import failure in the log — the environment differs from where it was tested.",
                "Pin the environment: record the conda env and a pip freeze hash with the run.",
            )
        )

    tail = _traceback_tail(log_text)
    if tail:
        add(Finding(INFO, "traceback", "Traceback tail from the log", tail, ""))
        return

    # A failed job whose log matched no rule used to produce no finding at all,
    # so the screen read "nothing to flag" -- about a job that failed, with its
    # log sitting on the line above. That was masked while the log-matching
    # heuristic preferred an empty `--output`: the empty file took the "no log
    # was found" branch, which at least said something. Routing the real stderr
    # in exposed it.
    #
    # The tool cannot name a cause it has no rule for, and should not invent one.
    # It can show the reader the last lines of the file it found, which is what
    # they would do next anyway. Held to INFO and phrased as an excerpt rather
    # than a diagnosis, because that is exactly what it is.
    if job.failed:
        excerpt = _last_lines(log_text)
        if excerpt:
            add(
                Finding(
                    INFO,
                    "log-tail",
                    "End of the log, which names no cause this tool recognises",
                    excerpt,
                    "",
                )
            )


def _last_lines(log_text, max_lines=6):
    """The final non-blank lines of a log, for a failure nothing else explains.

    Deliberately not `_traceback_tail`: that one finds a Python traceback and
    returns nothing when there is not one, which is the case this exists for.
    Whatever wrote the last line is usually what stopped the job -- a quota
    message, an MPI abort, a shell error -- and none of those is a shape this
    tool has a rule for.
    """
    lines = [line.rstrip() for line in (log_text or "").splitlines()]
    kept = [line for line in lines if line.strip()][-max_lines:]
    return "\n".join(kept)


def _strip_rank(line):
    """``[rank0]: File "x.py"`` -> ``File "x.py"``.

    torchrun prefixes every line of every worker's output, so indentation -- which
    is how a traceback's frames are told from its exception line -- is behind the
    prefix rather than at the start of the line.
    """
    head, sep, tail = line.partition("]:")
    return tail[1:] if sep and head.lstrip().startswith("[rank") and tail.startswith(" ") else line


def _traceback_tail(log_text, max_lines=6):
    """Last Python traceback in the log, trimmed -- and ending where it ends.

    Scanning backwards for the last ``Traceback`` header is right: a log can hold
    several, and the one that killed the job is the last. Taking ``lines[start:]``
    was not, because a traceback is frequently *not* the last thing in the file --
    a wrapper retries, torchrun prints its own summary, slurmstepd adds a line. The
    trim then kept the header, an ellipsis, and the last four lines **of the file**,
    so a finding titled "Traceback tail from the log" showed:

        Traceback (most recent call last):
          ...
        Validation data: disabled (no held-out file provided)
        Wall time: 999999s, will save checkpoint at 999819s
        ------------------------------------------------------------

    -- the startup banner of a later retry, under a heading promising a traceback.
    Measured on this machine: of 27,435 readable logs, 486 hold a traceback and
    **173 of those (36%) rendered a tail that was not it**. One ended on
    ``slurmstepd: error: Detected 1 oom-kill event(s)`` where the traceback's own
    last line was ``ChildFailedError:``.

    A traceback ends at its exception line: the first line after the header that
    carries no leading whitespace. Frames are indented, ``[rank0]:`` prefixes are
    stripped first so that test still works under torchrun, and a chained
    ``During handling of the above exception`` block is not reached because the
    backward scan already landed on the final segment.

    The header is matched through the same strip, which is load-bearing separately:
    three of those logs carry *only* a prefixed traceback, and before this the rule
    did not fire on them at all -- no finding, from a file whose last line reads
    ``[rank0]: AttributeError: '_OpNamespace' '_moe_C' object has no attribute
    'grouped_topk'``. Stripping in one of the two tests and not the other is the
    shape that has produced eight defects in this record; both cost one call.
    """
    if not log_text:
        return ""
    lines = log_text.splitlines()
    start = None
    for idx in range(len(lines) - 1, -1, -1):
        if _strip_rank(lines[idx]).strip().startswith("Traceback (most recent call last)"):
            start = idx
            break
    if start is None:
        return ""
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        body = _strip_rank(lines[idx])
        if body.strip() and not body[:1].isspace():
            end = idx + 1  # the exception line closes the traceback
            break
    chunk = [ln.rstrip() for ln in lines[start:end] if ln.strip()]
    if len(chunk) > max_lines:
        chunk = [chunk[0], "  ..."] + chunk[-(max_lines - 2) :]
    return "\n".join(chunk)


def _gpu_rules(job, add):
    if not job.gpu_count or job.open_ended:
        return
    if looks_like_noop(job):
        return
    # `gpu-suspect-idle` below infers idleness from `cpu_utilization`, so it is
    # subject to the same states that make that figure unreadable. The *measured*
    # branch above it is not -- `gres/gpuutil` is sampled while the job runs and
    # says what the cards actually did, however the run ended -- so this guard sits
    # here rather than at the top.
    cpu_readable = job.base_state not in _CPU_TIME_ALREADY_EXPLAINED

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
                    "Measured, not inferred: the work is off the device, or waiting on "
                    "input. Check the dataloader before asking for more cards.",
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
                    "Raise the work per step — batch size, sequence length, or fewer "
                    "grad-accumulation micro-steps — until the card is the bottleneck.",
                )
            )
        return

    util = job.cpu_utilization
    if util is None or not cpu_readable:
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
        detail += " — %s/s sustained over %s" % (format_bytes(rate), format_duration(job.elapsed))

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
                # The two byte figures this used to print came from the job-level
                # peak and the job-level average, which `rss_task_imbalance` no
                # longer divides -- see its docstring. Quoting the ratio alone
                # keeps the evidence and the number it is evidence for measured
                # over the same tasks, as the `straggler` finding above already
                # does with its percentage.
                "One task held %.1fx its peers' mean, across %d tasks — the ceiling has "
                "to cover the largest, not the mean." % (imbalance, job.task_count),
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
            "%s major page faults — the kernel fetched pages from disk, orders of "
            "magnitude slower than RAM and never visible as a failure." % f"{int(pages):,}",
            "Raise --mem, or cut the working set: a paging job finishes, just far "
            "slower than it needed to.",
        )
    )
