"""Typed records for a finished job.

Slurm 20.11 offers 107 accounting fields; :data:`slurmpast.sacct._FIELDS` asks for
the 85 that carry a distinct measurement -- CPU split by user and kernel, memory
peak *and* average with the node and task that hit it, disk read and write
separately, paging, CPU frequency, per-task minima for straggler detection, queue
wait, and how the scheduler placed the job. Pure redundancy (``DBIndex``,
``BlockID``, ``McsLabel``, duplicate spellings of the same TRES) is left out. Some
of the 85 exist only on newer releases and are dropped where they do not; see
``sacct``.

The cost of the wide query was measured before committing to it: the full list
over a seven-month history takes 2.26 s against 1.38 s for a minimal 27. Being
thorough is nearly free, and it means a user never has to re-run with a bigger
``--format`` because the number they wanted was not collected.

``typing.NamedTuple`` rather than ``dataclasses`` keeps the analysis layer light
and hashable; only the dashboard needs a modern Python.
"""

from __future__ import annotations

from typing import NamedTuple

CRITICAL = "critical"
WARNING = "warning"
INFO = "info"
_SEVERITY_RANK = {CRITICAL: 0, WARNING: 1, INFO: 2}

# Below this much total CPU, the user/system split is not a ratio worth reporting.
# One second: interpreter startup alone spends more than that, so anything under it
# is a job that did not run rather than one that ran badly.
MIN_CPU_FOR_A_SHARE = 1.0


def severity_rank(severity: str) -> int:
    return _SEVERITY_RANK.get(severity, 99)


class Step(NamedTuple):
    """One accounting step: ``.batch``, ``.extern``, or an srun step.

    Steps are where the measurements live -- the allocation row carries none of
    the CPU or memory counters on this Slurm version.
    """

    step_id: str
    name: str = ""
    state: str = ""
    exit_code: int | None = None
    signal: int | None = None
    elapsed: float | None = None

    # -- cpu ----------------------------------------------------------------
    total_cpu: float | None = None
    user_cpu: float | None = None
    system_cpu: float | None = None
    cpu_time: float | None = None
    ave_cpu: float | None = None
    min_cpu: float | None = None
    min_cpu_node: str = ""
    min_cpu_task: str = ""
    ave_cpu_freq: str = ""

    # -- memory --------------------------------------------------------------
    max_rss: int | None = None
    max_rss_node: str = ""
    max_rss_task: str = ""
    ave_rss: int | None = None
    max_vmsize: int | None = None
    max_vmsize_node: str = ""
    ave_vmsize: int | None = None

    # -- paging --------------------------------------------------------------
    max_pages: int | None = None
    max_pages_node: str = ""
    ave_pages: int | None = None

    # -- disk ----------------------------------------------------------------
    max_disk_read: int | None = None
    max_disk_read_node: str = ""
    ave_disk_read: int | None = None
    max_disk_write: int | None = None
    max_disk_write_node: str = ""
    ave_disk_write: int | None = None

    # -- shape and raw TRES ----------------------------------------------------
    ntasks: int | None = None
    nnodes: int | None = None
    node_list: str = ""
    tres_in_tot: str = ""
    tres_out_tot: str = ""
    tres_in_max: str = ""
    tres_in_max_node: str = ""
    tres_in_ave: str = ""
    consumed_energy: int | None = None

    @property
    def is_batch(self) -> bool:
        return self.step_id.endswith(".batch")

    @property
    def is_extern(self) -> bool:
        return self.step_id.endswith(".extern")

    @property
    def read_bytes(self) -> int | None:
        """Bytes read. ``TRESUsageInTot`` is authoritative; MaxDiskRead is a fallback."""
        value = _tres_bytes(self.tres_in_tot, "fs/disk")
        return value if value is not None else self.max_disk_read

    @property
    def write_bytes(self) -> int | None:
        """Bytes written -- the ``Out`` direction, which the ``In`` totals omit entirely.

        Reading only ``TRESUsageInTot`` (as the first version of this tool did)
        misses writes completely: one real run read 112 GB and wrote 139 GB, and
        only the read half was being reported.
        """
        value = _tres_bytes(self.tres_out_tot, "fs/disk")
        return value if value is not None else self.max_disk_write

    @property
    def gpu_utilization(self) -> float | None:
        """Average GPU busy-ness over the step, as a fraction, or None.

        ``gres/gpuutil`` is a percentage Slurm gathers per rank when the site runs
        ``AutoDetect=nvml``; ``TRESUsageInAve`` is its mean across the ranks of
        this step. Absent on any cluster that does not autodetect -- including the
        one this tool was written on -- which is why every other GPU figure here
        is careful to say it was not measured rather than that it was zero.
        """
        percent = _tres_float(self.tres_in_ave, "gres/gpuutil")
        if percent is None:
            percent = _tres_float(self.tres_in_max, "gres/gpuutil")
        if percent is None:
            return None
        return percent / 100.0

    @property
    def gpu_mem_bytes(self) -> int | None:
        """Peak GPU memory across the step's ranks, from ``gres/gpumem``."""
        return _tres_bytes(self.tres_in_max, "gres/gpumem") or _tres_bytes(
            self.tres_in_ave, "gres/gpumem"
        )


class Job(NamedTuple):
    """One job allocation plus its steps."""

    job_id: str
    job_id_raw: str = ""
    name: str = ""
    user: str = ""
    uid: str = ""
    group: str = ""
    account: str = ""
    cluster: str = ""
    partition: str = ""
    qos: str = ""
    assoc_id: str = ""
    wckey: str = ""

    # -- outcome --------------------------------------------------------------
    state: str = ""
    exit_code: int | None = None
    signal: int | None = None
    derived_exit_code: int | None = None
    reason: str = ""
    flags: str = ""

    # -- timing ---------------------------------------------------------------
    submit: str | None = None
    eligible: str | None = None
    start: str | None = None
    end: str | None = None
    elapsed: float | None = None
    timelimit: float | None = None
    queue_wait: float | None = None
    suspended: float | None = None

    # -- requested -------------------------------------------------------------
    req_mem_raw: str = ""
    req_mem_bytes: int | None = None
    req_mem_scope: str | None = None
    req_cpus: int | None = None
    req_nodes: int | None = None
    req_tres: str = ""
    # Pre-20.11 spelling of the GPU request. Slurm removed these fields in 20.11
    # in favour of TRES, so they are only ever populated on an older cluster --
    # where they are the only place the GPU count exists.
    req_gres: str = ""
    alloc_gres: str = ""
    constraints: str = ""
    req_cpu_freq_min: str = ""
    req_cpu_freq_max: str = ""
    req_cpu_freq_gov: str = ""

    # -- allocated --------------------------------------------------------------
    alloc_tres: str = ""
    alloc_cpus: int | None = None
    alloc_nodes: int | None = None
    ncpus: int | None = None
    nnodes: int | None = None
    ntasks: int | None = None
    node_list: str = ""

    # -- cpu recorded at the allocation row --------------------------------------
    total_cpu_alloc: float | None = None
    user_cpu_alloc: float | None = None
    system_cpu_alloc: float | None = None
    cpu_time_alloc: float | None = None

    # -- scheduling and context ----------------------------------------------------
    priority: int | None = None
    reservation: str = ""
    work_dir: str = ""
    comment: str = ""
    admin_comment: str = ""
    layout: str = ""
    # Recorded output paths, present from Slurm 21.08. Still *patterns*: sacct
    # stores them as written, so ``%j`` and friends are unexpanded (until
    # --expand-patterns in 24.05). See logs.expand_pattern.
    std_out: str = ""
    std_err: str = ""
    submit_line: str = ""

    steps: tuple = ()
    open_ended: bool = False

    # ------------------------------------------------------------------- state

    @property
    def base_state(self) -> str:
        """State without the ``by <uid>`` suffix sacct appends to CANCELLED."""
        return (self.state or "").split()[0] if self.state else ""

    @property
    def failed(self) -> bool:
        return self.base_state in ("FAILED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL", "BOOT_FAIL")

    @property
    def completed(self) -> bool:
        return self.base_state == "COMPLETED"

    @property
    def cancelled(self) -> bool:
        return self.base_state == "CANCELLED"

    @property
    def scheduled_by(self) -> str:
        """How the scheduler placed it: ``backfill``, ``main``, ``submit`` or "".

        Worth surfacing: 813 of 6,574 real jobs here got in via backfill, which
        is only visible in ``Flags`` and is reported by nothing else.
        """
        flags = (self.flags or "").lower()
        if "backfill" in flags:
            return "backfill"
        if "schedmain" in flags:
            return "main"
        if "schedsubmit" in flags:
            return "submit"
        return ""

    # ------------------------------------------------------------------- shape

    @property
    def gpu_count(self) -> int:
        """Devices held by the whole allocation, however this cluster records them.

        Three spellings, because sites differ in ways a post-mortem cannot ask
        about. ``gres/gpu=4`` is the modern untyped form. ``gres/gpu:a100=4``
        appears when the request named a model; Slurm normally emits the untyped
        total alongside it, but not on every release, so the typed entries are
        summed as a fallback. ``AllocGRES=gpu:4`` is the pre-20.11 field, which is
        the only place the count exists on a cluster old enough to have it.
        """
        for tres in (self.alloc_tres, self.req_tres):
            count = _tres_int(tres, "gres/gpu")
            if count:
                return count
            count = _typed_tres_total(tres, "gres/gpu")
            if count:
                return count
        for gres in (self.alloc_gres, self.req_gres):
            count = _gres_int(gres, "gpu")
            if count:
                return count
        return 0

    @property
    def cpu_count(self) -> int:
        return (
            self.alloc_cpus or self.ncpus or _tres_int(self.alloc_tres, "cpu") or self.req_cpus or 0
        )

    @property
    def node_count(self) -> int:
        return self.nnodes or self.alloc_nodes or _tres_int(self.alloc_tres, "node") or 1

    @property
    def task_count(self) -> int:
        if self.ntasks:
            return self.ntasks
        counts = [s.ntasks for s in self.steps if s.ntasks]
        return max(counts) if counts else 0

    @property
    def cpus_per_task(self) -> float | None:
        """Cores behind one task -- the quantity ``--cpus-per-task`` actually sets.

        Every CPU field sacct reports is a total over the allocation, so on a
        single-task job this is just :attr:`cpu_count` and nothing changes. On a
        15-node, 90-core job it is the difference between advising
        ``--cpus-per-task=6`` and advising ``--cpus-per-task=90``.
        """
        cpus = self.cpu_count
        if not cpus:
            return None
        # Tasks first; a job that recorded none still ran at least one per node.
        divisor = self.task_count or self.node_count or 1
        return cpus / float(divisor)

    @property
    def batch_step(self) -> Step | None:
        for step in self.steps:
            if step.is_batch:
                return step
        return None

    @property
    def work_steps(self) -> list:
        """Steps that could have done work -- everything but ``.extern``."""
        return [s for s in self.steps if not s.is_extern]

    # --------------------------------------------------------------------- cpu

    def _from_steps(self, attr: str):
        """Sum of ``attr`` across work steps -- the job's CPU, however it was launched.

        A sum, because Slurm's steps are disjoint sets of processes: the batch step
        is the script, each srun step is its own launch, and no process is counted
        twice. Verified against Slurm's own aggregate: ``TotalCPU`` on the allocation
        row divided by this sum is 1.000 at the 5th percentile, the median and the
        95th across 3,930 real jobs.

        Reading the *batch step alone* was wrong, and wrong in the most damaging
        direction. An ``sbatch`` script whose work is one ``srun`` line has a batch
        step of a few hundredths of a second, so job 51554217 -- 16 cores over 4
        nodes, ``04:47:33`` of CPU in step ``.0`` -- reported 0.037s, a utilization of
        0.0009%, and was flagged as having done nothing. 15 jobs here were written
        off that way. Falling back to the *largest* step was wrong too: it drops
        every step but one.

        The allocation row is not the answer either, despite carrying ``TotalCPU``
        on all 6,609 jobs here -- which is itself contrary to what this method used
        to claim. Slurm folds ``.extern`` into that total, and where extern's
        accounting is polluted so is the row: job 49842638 reads 538 core-hours
        against work steps that all report zero, for a reservation holder that
        genuinely did nothing. See :attr:`max_rss` for the same artefact in memory.
        """
        values = [getattr(s, attr) for s in self.work_steps if getattr(s, attr) is not None]
        return sum(values) if values else None

    @property
    def total_cpu(self) -> float | None:
        value = self._from_steps("total_cpu")
        return value if value is not None else self.total_cpu_alloc

    @property
    def user_cpu(self) -> float | None:
        value = self._from_steps("user_cpu")
        return value if value is not None else self.user_cpu_alloc

    @property
    def system_cpu(self) -> float | None:
        value = self._from_steps("system_cpu")
        return value if value is not None else self.system_cpu_alloc

    @property
    def system_cpu_fraction(self) -> float | None:
        """Share of CPU time spent in the kernel rather than in your code.

        A high value means the job is paying for syscalls -- small reads, heavy
        filesystem metadata traffic, process churn -- instead of computing. It is
        invisible in the single TotalCPU figure that every other tool reports.
        """
        total, system = self.total_cpu, self.system_cpu
        if not total or system is None:
            return None
        if system > total:
            # TotalCPU is user + system by definition, so this cannot happen from
            # one measurement -- it means the two figures came from different
            # steps (each is resolved independently: batch if present, else the
            # largest work step). The ratio is then meaningless, and it rendered
            # as "KERNEL 200.0%" -- a share of CPU time exceeding all of it.
            # Unmeasurable is the honest answer.
            return None
        if total < MIN_CPU_FOR_A_SHARE:
            # A ratio needs a denominator worth dividing by. Observed on real
            # records: TotalCPU 0.01s, all of it system, rendered as "kernel share
            # 100.0%" beside "user / system  0.00s / 0.01s" -- a headline
            # percentage computed from one hundredth of a second, which reads as a
            # syscall-bound job when it is a job that barely ran.
            return None
        return system / total

    @property
    def cpu_time(self) -> float | None:
        """Core-seconds allocated (elapsed x cores): the utilization denominator.

        The allocation row first, because that is the only row that covers the whole
        allocation. The *batch step's* ``CPUTime`` counts one node -- the one the
        script ran on -- so on job 51554217, 16 cores over 4 nodes, it reads
        ``01:12:04`` where the allocation reads ``04:48:16``. Dividing the job's real
        CPU by a quarter of its allocation reported 399% utilization, which is
        16 cores' work measured against 4 cores' entitlement.

        Unlike ``TotalCPU``, this figure cannot be polluted by ``.extern``: Slurm
        computes it as elapsed x allocated cores, so it is arithmetic on the
        allocation rather than anything jobacct_gather sampled.

        A work step can outlive the allocation record, and then the allocation row
        alone is too small a denominator. Job 51554394 was cancelled after 5s while
        step ``.0`` ran 8s and burned ``00:44.686`` on 8 cores, so sacct's own
        ``TotalCPU`` exceeds its own ``CPUTime`` (40s) and any tool dividing one by
        the other reports 111.7% -- 8.9 of 8 cores busy. The cores were genuinely
        held for the step's longer span, so the widest allocated span any work row
        reports is the honest denominator. Extern is excluded, as in the numerator.
        """
        # Filtered into a NEW name: reassigning `candidates` would leave its
        # declared type as `float | None` and `max` cannot order that.
        candidates = [self.cpu_time_alloc]
        if self.elapsed is not None and self.cpu_count:
            candidates.append(self.elapsed * self.cpu_count)
        candidates.extend(s.cpu_time for s in self.work_steps)
        spans = [value for value in candidates if value is not None]
        return max(spans) if spans else None

    @property
    def cpu_utilization(self) -> float | None:
        total, allocated = self.total_cpu, self.cpu_time
        if total is None or not allocated:
            return None
        return total / allocated

    @property
    def cores_busy(self) -> float | None:
        """Average number of cores actually working.

        A bare "74.7%" does not say what it is a percentage of -- it was read as
        memory. "3.0 of 4 cores" names the quantity and is also the number you
        act on when choosing ``--cpus-per-task``.
        """
        util = self.cpu_utilization
        if util is None or not self.cpu_count:
            return None
        return util * self.cpu_count

    @property
    def cpu_freq(self) -> str:
        """Raw ``AveCPUFreq`` string, kept for the JSON payload."""
        for step in self.work_steps:
            if step.ave_cpu_freq:
                return step.ave_cpu_freq
        return ""

    @property
    def cpu_freq_hz(self) -> float | None:
        """Average clock in hertz, or None when the record is not interpretable.

        See duration.parse_cpu_freq: Slurm reports this field with an ambiguous
        unit base, so a value that resolves to no plausible clock is dropped
        rather than displayed.
        """
        from .duration import parse_cpu_freq

        for step in self.work_steps:
            hz = parse_cpu_freq(step.ave_cpu_freq)
            if hz is not None:
                return hz
        return None

    @property
    def straggler_spread(self) -> float | None:
        """How far the slowest task lags the average within a multi-task step.

        ``(AveCPU - MinCPU) / AveCPU``. With more than one task, a large value
        means one rank did far less work than its peers -- the straggler that
        makes every other rank block at the next collective. None for
        single-task jobs, where the comparison is meaningless.
        """
        for step in self.work_steps:
            if (step.ntasks or 0) > 1 and step.ave_cpu and step.min_cpu is not None:
                if step.ave_cpu <= 0:
                    continue
                return max(0.0, (step.ave_cpu - step.min_cpu) / step.ave_cpu)
        return None

    @property
    def slowest_task(self) -> tuple:
        """``(node, task)`` that recorded the least CPU, when known."""
        for step in self.work_steps:
            if (step.ntasks or 0) > 1 and step.min_cpu is not None:
                return (step.min_cpu_node, step.min_cpu_task)
        return ("", "")

    # ------------------------------------------------------------------ memory

    @property
    def max_rss(self) -> int | None:
        """Largest MaxRSS across steps, less an ``.extern`` the allocation rules out.

        Must be a max, not a pick: job 51709094 reports batch=4108K against
        extern=16439052K -- a 4000x spread on one job -- so reading a single step
        is wrong by three orders of magnitude in either direction. That extern
        figure is real, and is why extern is included: 15.7 GiB against a 50 GiB
        limit, the job's own processes accounted to the container step.

        But ``.extern`` is also where Slurm's accounting goes wrong. Eight jobs in a
        6,417-job history report an extern MaxRSS *above the whole allocation* while
        a work step sits comfortably inside it: job 49455391 reads 2.81 TiB against
        ``mem=50G`` -- on a cluster whose largest node has 2.21 TiB of RAM, so the
        figure is not merely wrong but impossible -- for a job whose batch step used
        3.8 MiB and 0.004s of CPU. Reporting that as a 5757% MEM% is a phantom
        measurement, which is the one thing this module exists to avoid.

        So extern is dropped exactly when the allocation proves it impossible and a
        work step does not. With no limit to judge against, or with the work steps
        over the limit too -- genuine shared-page double counting, see
        :attr:`mem_utilization` -- the plain max stands and the caller is told the
        figure is an upper bound.
        """
        values = [s.max_rss for s in self.steps if s.max_rss is not None]
        if not values:
            return None
        peak = max(values)
        limit = self.mem_limit_bytes
        if not limit or peak <= limit:
            return peak
        work = [s.max_rss for s in self.work_steps if s.max_rss is not None]
        if not work or max(work) > limit:
            return peak
        extern = [s.max_rss for s in self.steps if s.is_extern and s.max_rss is not None]
        return max(work) if extern and max(extern) == peak else peak

    @property
    def max_rss_node(self) -> str:
        peak = self.max_rss
        for step in self.steps:
            if step.max_rss == peak and step.max_rss_node:
                return step.max_rss_node
        return ""

    @property
    def max_rss_task(self) -> str:
        peak = self.max_rss
        for step in self.steps:
            if step.max_rss == peak and step.max_rss_task:
                return step.max_rss_task
        return ""

    @property
    def ave_rss(self) -> int | None:
        values = [s.ave_rss for s in self.work_steps if s.ave_rss is not None]
        return max(values) if values else None

    @property
    def rss_task_imbalance(self) -> float | None:
        """``MaxRSS / AveRSS``. Above 1 means one task holds far more than its peers."""
        peak, average = self.max_rss, self.ave_rss
        if not peak or not average:
            return None
        return peak / float(average)

    @property
    def max_vmsize(self) -> int | None:
        values = [s.max_vmsize for s in self.steps if s.max_vmsize is not None]
        return max(values) if values else None

    @property
    def vmsize_to_rss(self) -> float | None:
        """Virtual size over resident size.

        Enormous on any CUDA job -- 1.7 TB of address space against 185 GiB
        resident on one real run -- which is exactly why ``vmem`` must never be
        used for sizing. Surfaced so the number is explained rather than alarming.
        """
        vmem, rss = self.max_vmsize, self.max_rss
        if not vmem or not rss:
            return None
        return vmem / float(rss)

    @property
    def rss_step_spread(self) -> float | None:
        """MaxRSS spread across *work* steps, excluding ``.extern``.

        ``.extern`` is a bookkeeping step that holds a couple of megabytes on
        every job, so including it reports a huge spread for 77% of a real
        history -- structural noise, not a signal. The spread is only
        interesting between steps that actually ran something.

        (Taking the *max* across all steps, including extern, remains correct
        and is what :attr:`max_rss` does -- that is a different question.)
        """
        values = [s.max_rss for s in self.work_steps if s.max_rss]
        if len(values) < 2:
            return None
        low = min(values)
        return (max(values) / float(low)) if low else None

    @property
    def mem_limit_total_bytes(self) -> int | None:
        """Memory granted to the whole allocation, summed over its nodes.

        ``ReqMem`` is NOT authoritative: it reads ``0n`` for 2,130 of 6,574 real
        jobs here -- the most common value in the whole history -- while
        ``AllocTRES`` carries the truth (``mem=80G``). Reading ReqMem alone
        yields a 0 that makes every MaxRSS look like an overrun, and ``seff``
        reads ReqMem. ``ReqTRES`` is wrong too: for that same job it reports
        ``22860M``, which is DefMemPerCPU x cores -- the default that would have
        applied, not the 80G granted.
        """
        allocated = _tres_bytes(self.alloc_tres, "mem")
        if allocated:
            return allocated
        if self.req_mem_bytes:
            scope = self.req_mem_scope
            if scope == "node":
                return self.req_mem_bytes * self.node_count
            if scope == "cpu":
                return self.req_mem_bytes * (self.cpu_count or 1)
            # Slurm 21.08 changed ReqMem to mirror ReqTRES: no n/c suffix, and
            # the figure is already the allocation total.
            return self.req_mem_bytes
        return _tres_bytes(self.req_tres, "mem") or None

    @property
    def mem_limit_bytes(self) -> int | None:
        """The ceiling **one node** had, which is what MaxRSS must be judged against.

        ``AllocTRES`` reports ``mem=`` for the whole allocation: a 2-node job
        submitted with ``--mem=8G`` records ``mem=16G`` (verified on job
        51553906). ``MaxRSS`` is the peak of a single task, so dividing one by the
        other understated memory use by exactly the node count -- and on a 15-node
        job it produced "Peak 40 GiB of a 750 GiB limit, 710 GiB never used" about
        a job that was running at 80% of its real ceiling.

        ``--mem`` is per node too, so this is also the number the sizing advice
        has to be built from. Single-node jobs are unaffected, which is why the
        error stayed invisible on a history that is almost entirely single-node.
        """
        if self.req_mem_scope == "node" and self.req_mem_bytes:
            # An explicit per-node request, on Slurm 20.11 and older. No division
            # to get wrong: this is already the per-node figure.
            return self.req_mem_bytes
        total = self.mem_limit_total_bytes
        if not total:
            return None
        nodes = self.node_count or 1
        return int(total // nodes) or None

    @property
    def mem_utilization(self) -> float | None:
        """Peak resident memory on one node against that node's ceiling.

        Both halves are per node -- see :attr:`mem_limit_bytes`. Still an
        underestimate when several tasks share a node, since MaxRSS is one task's
        peak rather than the node's; that is a limit of what Slurm records, not a
        choice made here.
        """
        rss, limit = self.max_rss, self.mem_limit_bytes
        if rss is None or not limit:
            return None
        return rss / limit

    # ------------------------------------------------------------------ paging

    @property
    def max_pages(self) -> int | None:
        values = [s.max_pages for s in self.steps if s.max_pages is not None]
        return max(values) if values else None

    # -------------------------------------------------------------------- disk

    @property
    def read_bytes(self) -> int | None:
        values = [s.read_bytes for s in self.steps if s.read_bytes is not None]
        return max(values) if values else None

    @property
    def write_bytes(self) -> int | None:
        values = [s.write_bytes for s in self.steps if s.write_bytes is not None]
        return max(values) if values else None

    @property
    def io_bytes(self) -> int | None:
        read, write = self.read_bytes, self.write_bytes
        if read is None and write is None:
            return None
        return (read or 0) + (write or 0)

    @property
    def io_rate(self) -> float | None:
        """Average bytes per second of wall clock, read and write combined."""
        total = self.io_bytes
        if total is None or not self.elapsed:
            return None
        return total / self.elapsed

    @property
    def fs_disk_bytes(self) -> int | None:
        """Deprecated alias for :attr:`read_bytes`, kept for older callers."""
        return self.read_bytes

    # -------------------------------------------------------------------- time

    @property
    def walltime_used(self) -> float | None:
        if self.elapsed is None or not self.timelimit:
            return None
        return self.elapsed / self.timelimit

    @property
    def gpu_hours(self) -> float | None:
        if self.elapsed is None or not self.gpu_count:
            return None
        return self.elapsed * self.gpu_count / 3600.0

    @property
    def gpu_utilization(self) -> float | None:
        """How busy the GPUs were, when the cluster gathered it.

        The measurement no post-mortem tool has on most clusters, and the one this
        codebase spent a warning inferring from host CPU time. Where
        ``AutoDetect=nvml`` is configured it is simply recorded, so the inference
        can stand down. Highest across work steps: a job whose training step ran
        the cards hot is not idle because its setup step was.
        """
        values = [s.gpu_utilization for s in self.work_steps if s.gpu_utilization is not None]
        return max(values) if values else None

    @property
    def gpu_mem_peak_bytes(self) -> int | None:
        """Peak GPU memory used, when recorded. The HBM figure for right-sizing."""
        values = [s.gpu_mem_bytes for s in self.steps if s.gpu_mem_bytes]
        return max(values) if values else None

    @property
    def core_hours(self) -> float | None:
        if self.elapsed is None or not self.cpu_count:
            return None
        return self.elapsed * self.cpu_count / 3600.0

    @property
    def energy_joules(self) -> int | None:
        """Always None where ``AcctGatherEnergyType=none``, as on this cluster.

        Kept because other sites populate it; here it reports unavailable rather
        than zero, which is a different claim.
        """
        values = [s.consumed_energy for s in self.steps if s.consumed_energy]
        return max(values) if values else None


class Finding(NamedTuple):
    severity: str
    code: str
    title: str
    evidence: str
    action: str = ""


class Verdict(NamedTuple):
    job: Job
    findings: tuple

    @property
    def worst(self) -> Finding | None:
        if not self.findings:
            return None
        return sorted(self.findings, key=lambda f: severity_rank(f.severity))[0]


def _leading_int(value: str) -> int | None:
    digits = ""
    for char in value.strip():
        if char.isdigit():
            digits += char
        else:
            break
    return int(digits) if digits else None


def _tres_int(tres: str, key: str) -> int | None:
    """Integer out of ``cpu=6,gres/gpu=1,mem=80G``. None when absent."""
    if not tres:
        return None
    for field in tres.split(","):
        name, _, value = field.partition("=")
        if name.strip() != key:
            continue
        count = _leading_int(value)
        if count is not None:
            return count
    return None


def _typed_tres_total(tres: str, key: str) -> int | None:
    """Sum of the model-qualified entries for ``key``: ``gres/gpu:a100=4`` -> 4.

    Slurm usually emits the untyped total beside the typed ones, so this is a
    fallback for the releases and configurations where it does not. Summing is
    right rather than taking a max: a node can hold two models at once, and both
    were allocated.
    """
    if not tres:
        return None
    prefix = key + ":"
    total = 0
    for field in tres.split(","):
        name, _, value = field.partition("=")
        if not name.strip().startswith(prefix):
            continue
        count = _leading_int(value)
        if count is not None:
            total += count
    return total or None


def _gres_int(gres: str, key: str) -> int | None:
    """Count out of the pre-20.11 ``AllocGRES``/``ReqGRES`` form.

    Colon-separated rather than TRES-shaped: ``gpu:4``, or ``gpu:tesla:4`` when
    the request named a model. A bare ``gpu`` with no count means one device.
    """
    if not gres:
        return None
    total = 0
    for field in gres.split(","):
        parts = [p.strip() for p in field.strip().split(":") if p.strip()]
        if not parts or parts[0].lower() != key:
            continue
        count = _leading_int(parts[-1]) if len(parts) > 1 else None
        total += count if count is not None else 1
    return total or None


def _tres_float(tres: str, key: str) -> float | None:
    """Decimal value out of a TRES string. Used for percentages, not sizes."""
    if not tres:
        return None
    for field in tres.split(","):
        name, _, value = field.partition("=")
        if name.strip() != key:
            continue
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _tres_bytes(tres: str, key: str) -> int | None:
    """Byte quantity out of a TRES string, honouring unit suffixes.

    Returns None for zero: a 0-byte memory ceiling does not exist, and
    conflating "not recorded" with "zero" invents overruns.
    """
    if not tres:
        return None
    from .duration import parse_bytes

    for field in tres.split(","):
        name, _, value = field.partition("=")
        if name.strip() != key:
            continue
        return parse_bytes(value.strip()) or None
    return None
