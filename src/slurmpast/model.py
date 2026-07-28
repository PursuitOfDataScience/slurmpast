"""Typed records for a finished job.

Slurm 20.11 exposes 107 accounting fields. This captures every one that carries
a distinct measurement -- CPU split by user and kernel, memory peak *and*
average with the node and task that hit it, disk read and write separately,
paging, CPU frequency, per-task minima for straggler detection, queue wait, and
how the scheduler placed the job. Pure redundancy (``DBIndex``, ``BlockID``,
``McsLabel``, duplicate spellings of the same TRES) is left out.

The cost of the wide query was measured before committing to it: all 107 fields
over a seven-month history take 2.26 s against 1.38 s for a minimal 27. Being
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
        return _tres_int(self.alloc_tres, "gres/gpu") or _tres_int(self.req_tres, "gres/gpu") or 0

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
        """Batch-step value for ``attr``, else the largest work step.

        The allocation row carries no CPU counters on Slurm 20.11, so reading it
        there yields None for every job and silently disables all utilization
        analysis -- which is how a fleet of hung jobs stays invisible.
        """
        batch = self.batch_step
        if batch is not None and getattr(batch, attr) is not None:
            return getattr(batch, attr)
        values = [getattr(s, attr) for s in self.work_steps if getattr(s, attr) is not None]
        return max(values) if values else None

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
        return system / total

    @property
    def cpu_time(self) -> float | None:
        """Core-seconds allocated (elapsed x cores): the utilization denominator."""
        batch = self.batch_step
        if batch is not None and batch.cpu_time is not None:
            return batch.cpu_time
        if self.cpu_time_alloc is not None:
            return self.cpu_time_alloc
        if self.elapsed is not None and self.cpu_count:
            return self.elapsed * self.cpu_count
        return None

    @property
    def cpu_utilization(self) -> float | None:
        total, allocated = self.total_cpu, self.cpu_time
        if total is None or not allocated:
            return None
        return total / allocated

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
        """Largest MaxRSS across steps.

        Must be a max, not a pick: job 51709094 reports batch=4108K against
        extern=16439052K -- a 4000x spread on one job -- so reading a single step
        is wrong by three orders of magnitude in either direction.
        """
        values = [s.max_rss for s in self.steps if s.max_rss is not None]
        return max(values) if values else None

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
    def mem_limit_bytes(self) -> int | None:
        """The memory ceiling the job actually had, or None.

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
            return self.req_mem_bytes
        return _tres_bytes(self.req_tres, "mem") or None

    @property
    def mem_utilization(self) -> float | None:
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


def _tres_int(tres: str, key: str) -> int | None:
    """Integer out of ``cpu=6,gres/gpu=1,mem=80G``. None when absent."""
    if not tres:
        return None
    for field in tres.split(","):
        name, _, value = field.partition("=")
        if name.strip() != key:
            continue
        digits = ""
        for char in value.strip():
            if char.isdigit():
                digits += char
            else:
                break
        if digits:
            return int(digits)
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
