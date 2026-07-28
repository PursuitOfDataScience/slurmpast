"""Reading Slurm accounting without producing phantom numbers.

Five traps this module exists to close, each measured on a live Midway3 record:

1. **Field availability varies by Slurm version.** This cluster runs 20.11.8,
   where ``StdOut``/``StdErr``/``SubmitLine`` do not exist -- requesting one
   unknown field makes sacct reject the *entire* query with ``Invalid field
   requested`` and you get nothing. So fields are probed against
   ``sacct --helpformat`` and unsupported ones dropped.

2. **Steps must be reconciled, not sampled.** ``TotalCPU`` lives only on steps;
   ``MaxRSS`` differs 4000x between steps of job 51709094.

3. **Open-ended records look like enormous jobs.** Job 50108238 reports
   ``State=RUNNING, End=Unknown`` months after it died, so sacct computes
   ``Elapsed`` as *now minus start* -- 62 days. Summed into a GPU-hour total it
   was 65% of the figure.

4. **``--state`` silently returns zero rows without ``-E``.** Verified:
   ``-S 2026-07-01 --state=TIMEOUT`` yields nothing while 15 such jobs exist;
   adding ``-E now`` returns all 15. No error, no warning.

5. **Formatted durations are ambiguous.** ``00:00.539`` is ``MM:SS.mmm``. Where
   Slurm offers a ``*Raw`` field in integer seconds (``ElapsedRaw``,
   ``CPUTimeRAW``, ``TimelimitRaw``) it is preferred outright, removing the
   guess entirely for the three values it matters most for.
"""

from __future__ import annotations

import subprocess

from .duration import mem_scope, parse_bytes, parse_duration
from .model import Job, Step

# Every field carrying a distinct measurement. Deliberately wide: all 107 fields
# cost 2.26 s over a seven-month history against 1.38 s for a minimal 27, so
# there is no reason to make a user re-run because the number they wanted was
# never collected. Pure redundancy (DBIndex, BlockID, McsLabel, duplicate
# spellings of the same TRES) is omitted.
# fmt: off
_FIELDS = [
    # identity
    "JobID", "JobIDRaw", "JobName", "User", "UID", "Group", "Account", "Cluster",
    "Partition", "QOS", "AssocID", "WCKey",
    # outcome
    "State", "ExitCode", "DerivedExitCode", "Reason", "Flags",
    # timing
    "Submit", "Eligible", "Start", "End", "Elapsed", "ElapsedRaw",
    "Timelimit", "TimelimitRaw", "Reserved", "Suspended",
    # requested
    "ReqMem", "ReqCPUS", "ReqNodes", "ReqTRES", "Constraints",
    "ReqCPUFreqMin", "ReqCPUFreqMax", "ReqCPUFreqGov",
    # allocated
    "AllocTRES", "AllocCPUS", "AllocNodes", "NCPUS", "NNodes", "NTasks", "NodeList",
    # cpu
    "TotalCPU", "UserCPU", "SystemCPU", "CPUTime", "CPUTimeRAW",
    "AveCPU", "MinCPU", "MinCPUNode", "MinCPUTask", "AveCPUFreq",
    # memory
    "MaxRSS", "MaxRSSNode", "MaxRSSTask", "AveRSS",
    "MaxVMSize", "MaxVMSizeNode", "AveVMSize",
    # paging
    "MaxPages", "MaxPagesNode", "AvePages",
    # disk, read and write kept separate
    "MaxDiskRead", "MaxDiskReadNode", "AveDiskRead",
    "MaxDiskWrite", "MaxDiskWriteNode", "AveDiskWrite",
    # raw TRES: the In/Out directions plus per-node attribution
    "TRESUsageInTot", "TRESUsageOutTot", "TRESUsageInMax", "TRESUsageInMaxNode",
    "ConsumedEnergy",
    # scheduling and context
    "Priority", "Reservation", "WorkDir", "Comment", "AdminComment", "Layout",
]
# fmt: on

# Dropped silently when the local Slurm is too old to know them. Everything not
# listed is load-bearing and kept even if unrecognised, so a genuinely broken
# field list fails loudly instead of quietly degrading.
# fmt: off
_OPTIONAL = frozenset(
    [
        "WorkDir", "Constraints", "Reason", "MaxRSSNode", "MaxRSSTask", "TRESUsageInTot",
        "TRESUsageOutTot", "TRESUsageInMax", "TRESUsageInMaxNode", "QOS", "Flags",
        "DerivedExitCode", "Reserved", "Suspended", "AssocID", "WCKey", "Cluster",
        "ReqCPUFreqMin", "ReqCPUFreqMax", "ReqCPUFreqGov", "AveCPU", "MinCPU",
        "MinCPUNode", "MinCPUTask", "AveCPUFreq", "AveRSS", "MaxVMSize", "MaxVMSizeNode",
        "AveVMSize", "MaxPages", "MaxPagesNode", "AvePages", "MaxDiskRead",
        "MaxDiskReadNode", "AveDiskRead", "MaxDiskWrite", "MaxDiskWriteNode",
        "AveDiskWrite", "ConsumedEnergy", "Priority", "Reservation", "Comment",
        "AdminComment", "Layout", "UID", "Group", "NTasks", "AllocNodes", "AllocCPUS",
        "ReqNodes", "ElapsedRaw", "TimelimitRaw", "CPUTimeRAW", "JobIDRaw", "UserCPU",
        "SystemCPU",
    ]
)
# fmt: on

_UNSET = frozenset(["", "Unknown", "None", "N/A", "none", "Unlimited"])

# A terminal job is over even if the End timestamp is missing; inferring "still
# running" from a blank End would suppress every diagnosis on such a record. The
# stale-record signal is specifically a NON-terminal state with no end.
# fmt: off
_TERMINAL_STATES = frozenset(
    [
        "COMPLETED", "FAILED", "TIMEOUT", "OUT_OF_MEMORY", "CANCELLED", "NODE_FAIL",
        "BOOT_FAIL", "DEADLINE", "PREEMPTED", "REVOKED", "SPECIAL_EXIT", "OUT_OF_ME+",
    ]
)
# fmt: on


class SacctError(RuntimeError):
    pass


def _run(args):
    try:
        proc = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True
        )
    except OSError as exc:
        raise SacctError("cannot execute %s: %s" % (args[0], exc))
    out, err = proc.communicate()
    if proc.returncode != 0:
        raise SacctError((err or "").strip() or "%s exited %d" % (args[0], proc.returncode))
    return out


def supported_fields(probe=None):
    """Field names this Slurm's sacct will accept, lowercased."""
    text = probe if probe is not None else _run(["sacct", "--helpformat"])
    names = set()
    for token in text.replace("\n", " ").replace(",", " ").split():
        token = token.strip()
        if token:
            names.add(token.lower())
    return names


def _clean(value):
    value = (value or "").strip()
    return "" if value in _UNSET else value


def _int(value):
    value = _clean(value)
    if not value:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _seconds(raw, formatted):
    """Prefer an integer-seconds ``*Raw`` field over parsing a formatted duration.

    ``ElapsedRaw`` and ``CPUTimeRAW`` remove the ``MM:SS.mmm`` vs ``HH:MM:SS``
    ambiguity outright. (``TimelimitRaw`` is in *minutes* and is handled
    separately by the caller.)
    """
    value = _int(raw)
    if value is not None:
        return float(value)
    return parse_duration(formatted)


def _parse_exit(text):
    """``ExitCode`` is ``code:signal``. Returns (code, signal), either may be None."""
    text = _clean(text)
    if not text:
        return None, None
    code, _, signal = text.partition(":")
    try:
        code_val = int(code)
    except ValueError:
        code_val = None
    try:
        signal_val = int(signal) if signal else None
    except ValueError:
        signal_val = None
    return code_val, signal_val


def _base_job_id(step_id):
    """``123.batch`` -> ``123``; ``123_4.batch`` -> ``123_4``; ``123+0.0`` -> ``123+0``."""
    return step_id.split(".")[0]


def parse(text, fields=None):
    """Parse ``sacct --parsable2`` output into Jobs with their steps attached."""
    fields = list(fields or _FIELDS)
    index = {name.lower(): pos for pos, name in enumerate(fields)}

    def get(row, name):
        pos = index.get(name.lower())
        if pos is None or pos >= len(row):
            return ""
        return _clean(row[pos])

    allocations = {}
    order = []
    pending_steps = {}

    for line in text.splitlines():
        if not line.strip():
            continue
        row = line.split("|")
        raw_id = (row[index["jobid"]] if index.get("jobid", 0) < len(row) else "").strip()
        if not raw_id or raw_id.lower() == "jobid":
            continue

        exit_code, signal = _parse_exit(get(row, "ExitCode"))

        if "." in raw_id:
            pending_steps.setdefault(_base_job_id(raw_id), []).append(
                Step(
                    step_id=raw_id,
                    name=get(row, "JobName"),
                    state=get(row, "State"),
                    exit_code=exit_code,
                    signal=signal,
                    elapsed=_seconds(get(row, "ElapsedRaw"), get(row, "Elapsed")),
                    total_cpu=parse_duration(get(row, "TotalCPU")),
                    user_cpu=parse_duration(get(row, "UserCPU")),
                    system_cpu=parse_duration(get(row, "SystemCPU")),
                    cpu_time=_seconds(get(row, "CPUTimeRAW"), get(row, "CPUTime")),
                    ave_cpu=parse_duration(get(row, "AveCPU")),
                    min_cpu=parse_duration(get(row, "MinCPU")),
                    min_cpu_node=get(row, "MinCPUNode"),
                    min_cpu_task=get(row, "MinCPUTask"),
                    ave_cpu_freq=get(row, "AveCPUFreq"),
                    max_rss=parse_bytes(get(row, "MaxRSS")),
                    max_rss_node=get(row, "MaxRSSNode"),
                    max_rss_task=get(row, "MaxRSSTask"),
                    ave_rss=parse_bytes(get(row, "AveRSS")),
                    max_vmsize=parse_bytes(get(row, "MaxVMSize")),
                    max_vmsize_node=get(row, "MaxVMSizeNode"),
                    ave_vmsize=parse_bytes(get(row, "AveVMSize")),
                    max_pages=parse_bytes(get(row, "MaxPages")),
                    max_pages_node=get(row, "MaxPagesNode"),
                    ave_pages=parse_bytes(get(row, "AvePages")),
                    max_disk_read=parse_bytes(get(row, "MaxDiskRead")),
                    max_disk_read_node=get(row, "MaxDiskReadNode"),
                    ave_disk_read=parse_bytes(get(row, "AveDiskRead")),
                    max_disk_write=parse_bytes(get(row, "MaxDiskWrite")),
                    max_disk_write_node=get(row, "MaxDiskWriteNode"),
                    ave_disk_write=parse_bytes(get(row, "AveDiskWrite")),
                    ntasks=_int(get(row, "NTasks")),
                    nnodes=_int(get(row, "NNodes")),
                    node_list=get(row, "NodeList"),
                    tres_in_tot=get(row, "TRESUsageInTot"),
                    tres_out_tot=get(row, "TRESUsageOutTot"),
                    tres_in_max=get(row, "TRESUsageInMax"),
                    tres_in_max_node=get(row, "TRESUsageInMaxNode"),
                    consumed_energy=_int(get(row, "ConsumedEnergy")),
                )
            )
            continue

        req_mem = get(row, "ReqMem")
        end_raw = get(row, "End")
        state = get(row, "State")
        derived_code, _ = _parse_exit(get(row, "DerivedExitCode"))

        # TimelimitRaw is in MINUTES, unlike every other *Raw field.
        timelimit_raw = _int(get(row, "TimelimitRaw"))
        timelimit = (
            float(timelimit_raw) * 60.0
            if timelimit_raw is not None
            else parse_duration(get(row, "Timelimit"))
        )

        job = Job(
            job_id=raw_id,
            job_id_raw=get(row, "JobIDRaw"),
            name=get(row, "JobName"),
            user=get(row, "User"),
            uid=get(row, "UID"),
            group=get(row, "Group"),
            account=get(row, "Account"),
            cluster=get(row, "Cluster"),
            partition=get(row, "Partition"),
            qos=get(row, "QOS"),
            assoc_id=get(row, "AssocID"),
            wckey=get(row, "WCKey"),
            state=state,
            exit_code=exit_code,
            signal=signal,
            derived_exit_code=derived_code,
            reason=get(row, "Reason"),
            flags=get(row, "Flags"),
            submit=get(row, "Submit") or None,
            eligible=get(row, "Eligible") or None,
            start=get(row, "Start") or None,
            end=end_raw or None,
            elapsed=_seconds(get(row, "ElapsedRaw"), get(row, "Elapsed")),
            timelimit=timelimit,
            queue_wait=parse_duration(get(row, "Reserved")),
            suspended=parse_duration(get(row, "Suspended")),
            req_mem_raw=req_mem,
            # "0n" means not recorded, not zero bytes. See Job.mem_limit_bytes.
            req_mem_bytes=(parse_bytes(req_mem) or None),
            req_mem_scope=mem_scope(req_mem),
            req_cpus=_int(get(row, "ReqCPUS")),
            req_nodes=_int(get(row, "ReqNodes")),
            req_tres=get(row, "ReqTRES"),
            constraints=get(row, "Constraints"),
            req_cpu_freq_min=get(row, "ReqCPUFreqMin"),
            req_cpu_freq_max=get(row, "ReqCPUFreqMax"),
            req_cpu_freq_gov=get(row, "ReqCPUFreqGov"),
            alloc_tres=get(row, "AllocTRES"),
            alloc_cpus=_int(get(row, "AllocCPUS")),
            alloc_nodes=_int(get(row, "AllocNodes")),
            ncpus=_int(get(row, "NCPUS")),
            nnodes=_int(get(row, "NNodes")),
            ntasks=_int(get(row, "NTasks")),
            node_list=get(row, "NodeList"),
            total_cpu_alloc=parse_duration(get(row, "TotalCPU")),
            user_cpu_alloc=parse_duration(get(row, "UserCPU")),
            system_cpu_alloc=parse_duration(get(row, "SystemCPU")),
            cpu_time_alloc=_seconds(get(row, "CPUTimeRAW"), get(row, "CPUTime")),
            priority=_int(get(row, "Priority")),
            reservation=get(row, "Reservation"),
            work_dir=get(row, "WorkDir"),
            comment=get(row, "Comment"),
            admin_comment=get(row, "AdminComment"),
            layout=get(row, "Layout"),
            open_ended=(not end_raw)
            and (state.split()[0] if state else "") not in _TERMINAL_STATES,
        )
        allocations[raw_id] = job
        order.append(raw_id)

    return [
        allocations[job_id]._replace(steps=tuple(pending_steps.get(job_id, ()))) for job_id in order
    ]


class Sacct(object):
    """Queries sacct, dropping fields the local Slurm rejects."""

    def __init__(self, runner=None, probe=None):
        self._run = runner or _run
        self._probe = probe
        self._supported = None

    @property
    def fields(self):
        if self._supported is None:
            try:
                available = supported_fields(self._probe)
            except SacctError:
                available = None
            if available is None:
                self._supported = list(_FIELDS)
            else:
                self._supported = [
                    f for f in _FIELDS if f.lower() in available or f not in _OPTIONAL
                ]
        return self._supported

    def _query(self, extra):
        fields = self.fields
        args = ["sacct", "--parsable2", "--noheader", "--format=" + ",".join(fields)] + list(extra)
        return parse(self._run(args), fields=fields)

    def jobs(self, job_ids):
        ids = [str(j) for j in job_ids if str(j).strip()]
        if not ids:
            return []
        return self._query(["-j", ",".join(ids)])

    def history(self, user=None, since=None, until=None, states=None, partition=None):
        extra = []
        if user:
            extra += ["-u", user]
        elif user == "":
            extra += ["--allusers"]
        if since:
            extra += ["-S", since]
        if states:
            # `--state` silently returns ZERO rows unless an end time is also
            # given -- verified on Slurm 20.11.8: `-S 2026-07-01 --state=TIMEOUT`
            # yields nothing while 15 such jobs exist, and `-E now` returns all
            # 15. No error, no warning. For a post-mortem tool that is the worst
            # possible failure: it reports "no failures" and you believe it.
            extra += ["--state", ",".join(states)]
            extra += ["-E", until or "now"]
        elif until:
            extra += ["-E", until]
        if partition:
            extra += ["-r", partition]
        return self._query(extra)


def live_job_ids(runner=None):
    """Job IDs squeue currently reports for this user.

    Distinguishes a genuinely running job from a stale accounting record: if
    sacct says RUNNING and squeue has never heard of it, the record is dead.
    Returns None (not an empty set) when squeue cannot be reached, so callers
    can refrain from guessing.
    """
    run = runner or _run
    try:
        out = run(["squeue", "--noheader", "--me", "--format=%i"])
    except SacctError:
        try:
            out = run(["squeue", "--noheader", "--format=%i"])
        except SacctError:
            return None
    return set(line.strip() for line in out.splitlines() if line.strip())
