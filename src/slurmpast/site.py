"""What this particular cluster records, asked rather than assumed.

Two of this tool's most-repeated sentences are only true on some clusters:

* *"MaxRSS sums RSS across the process tree and double-counts shared pages."*
  True under ``JobAcctGatherType=jobacct_gather/linux``, which is what produced
  the 51.25 GiB reading against a 40 GiB limit that this codebase cites. Under
  ``jobacct_gather/cgroup`` the figure comes from the cgroup's own peak counter
  and is not a sum over processes at all -- so on those sites the warning is
  false and the caution it attaches to sizing advice is unearned.

* *"GPU utilization is not recorded by Slurm."*  True here. But a site running
  ``AutoDetect=nvml`` in ``gres.conf`` gets ``gres/gpuutil`` and ``gres/gpumem``
  in the TRES usage automatically, and then Slurm records exactly that.

``scontrol show config`` answers both, so it is read once, lazily, and cached.
Every field degrades to None when the scheduler cannot be reached, and every
caller must treat None as "cannot say" rather than as a default -- the same rule
the rest of the codebase applies to a missing measurement.
"""

from __future__ import annotations

from typing import NamedTuple

from .sacct import SacctError, _run


class Site(NamedTuple):
    """Configuration facts that change what a measurement means."""

    slurm_version: str = ""
    jobacct_gather_type: str = ""
    accounting_storage_type: str = ""
    tres: tuple = ()
    jobacct_gather_frequency: str = ""

    @property
    def known(self) -> bool:
        """False when the scheduler could not be asked; callers then say nothing."""
        return bool(self.jobacct_gather_type or self.tres or self.slurm_version)

    @property
    def rss_from_cgroup(self) -> bool | None:
        """Whether MaxRSS is a cgroup peak rather than a sum over the process tree.

        None means unknown, which is not the same as False: the pessimistic
        wording is only justified when ``jobacct_gather/linux`` is confirmed.
        """
        if not self.jobacct_gather_type:
            return None
        return "cgroup" in self.jobacct_gather_type

    @property
    def sampling_seconds(self) -> int | None:
        """How often the accounting sampler looks, in seconds, or None.

        ``JobAcctGatherFrequency`` is either a bare integer or a per-type list --
        ``30``, or ``task=30,network=60``. Only ``task`` gathers RSS, so that is
        the one that decides whether a memory peak could have been missed; a bare
        integer applies to every type and therefore to ``task`` as well.

        ``0`` means the sampler is off entirely (Slurm gathers only at task exit),
        which is not a frequency and is returned as None -- a caller asking "how
        many samples fit in this job" gets no answer rather than a division by
        zero.
        """
        raw = (self.jobacct_gather_frequency or "").strip()
        if not raw:
            return None
        if "=" not in raw:
            candidate = raw
        else:
            candidate = ""
            for part in raw.split(","):
                name, sep, value = part.partition("=")
                if sep and name.strip().lower() == "task":
                    candidate = value.strip()
                    break
        try:
            seconds = int(candidate)
        except ValueError:
            return None
        return seconds if seconds > 0 else None

    @property
    def tracks_gpu(self) -> bool | None:
        """Whether GPU allocation reaches accounting at all.

        Without ``gres/gpu`` in ``AccountingStorageTRES`` no finished job has a
        device count, so every GPU figure here reads n/a -- and the honest reason
        is a site setting, not a missing job.
        """
        if not self.tres:
            return None
        return any(t == "gres/gpu" or t.startswith("gres/gpu:") for t in self.tres)

    @property
    def tracks_gpu_utilization(self) -> bool | None:
        """Whether ``gres/gpuutil`` is gathered, i.e. whether GPU busy-ness is known.

        Slurm configures it alongside ``gres/gpu``, but only actually gathers it
        with ``AutoDetect=nvml`` (NVIDIA) or ``rsmi`` (AMD), so its presence in
        the TRES list is necessary and not sufficient. The values themselves are
        the real test; this only decides how to word their absence.
        """
        if not self.tres:
            return None
        return "gres/gpuutil" in self.tres


_CACHE: list = []


def _parse_config(text):
    """Pull the handful of keys that matter out of ``scontrol show config``.

    The format is ``Key  = value`` per line, with keys that vary in case between
    releases (``SLURM_VERSION`` against ``JobAcctGatherType``), so lookup is
    case-insensitive.
    """
    values = {}
    for line in (text or "").splitlines():
        key, sep, value = line.partition("=")
        if not sep:
            continue
        values[key.strip().lower()] = value.strip()
    tres = values.get("accountingstoragetres", "")
    return Site(
        slurm_version=values.get("slurm_version", ""),
        jobacct_gather_type=values.get("jobacctgathertype", ""),
        accounting_storage_type=values.get("accountingstoragetype", ""),
        tres=tuple(t.strip() for t in tres.split(",") if t.strip()),
        jobacct_gather_frequency=values.get("jobacctgatherfrequency", ""),
    )


def site(runner=None, refresh=False):
    """The local cluster's configuration, read once per process.

    Never raises: a machine with no ``scontrol`` returns an empty :class:`Site`
    whose ``known`` is False, which is what the ``--demo`` path and a laptop both
    need.
    """
    if _CACHE and not refresh:
        return _CACHE[0]
    run = runner or _run
    try:
        found = _parse_config(run(["scontrol", "show", "config"]))
    except (SacctError, OSError):
        found = Site()
    # One branch. `_CACHE[:] = [found]` and `_CACHE[0] = found` do the same thing
    # to a list that is empty or holds exactly one element, which is the only two
    # shapes this list ever has, so the condition chose between two spellings of
    # one statement.
    _CACHE[:] = [found]
    return found


def reset_cache():
    """Forget the cached configuration. For tests, and for ``--demo``."""
    _CACHE.clear()
    _PARTITION_CEILING.clear()


def maxrss_caveat(known_site=None):
    """One clause explaining how far MaxRSS can be trusted, or "" when it cannot say.

    Phrased to be appended to a sentence, so callers do not have to know which of
    the two gather plugins is in play.
    """
    current = known_site if known_site is not None else site()
    from_cgroup = current.rss_from_cgroup
    if from_cgroup is None:
        return (
            "MaxRSS may over-report multi-process jobs depending on this cluster's "
            "JobAcctGatherType, so treat it as an upper bound"
        )
    if from_cgroup:
        return (
            "MaxRSS comes from the cgroup peak here (%s), so it is the step's real "
            "high-water mark rather than a sum over processes" % current.jobacct_gather_type
        )
    return (
        "MaxRSS sums RSS across the process tree under %s, double-counting shared "
        "pages, so treat it as an upper bound" % current.jobacct_gather_type
    )


# Below this many samples the peak is a coin flip rather than a measurement. The
# reporter suggested 3-5; 5 is the generous end, chosen because the cost of the
# note is one clause and the cost of omitting it is a reader sizing --mem from a
# figure that never saw the spike.
SPARSE_SAMPLE_COUNT = 5


def sample_count(elapsed_seconds, known_site=None):
    """How many times the accounting sampler could have looked at a job, or None.

    A sampler firing every ``f`` seconds over an ``e``-second job gets one look at
    the start and one per interval after, so ``floor(e / f) + 1`` -- 3 for the
    89-second job that prompted this, not 2. It is an upper bound on the looks:
    Slurm does not promise the first sample lands at t=0.
    """
    current = known_site if known_site is not None else site()
    interval = current.sampling_seconds
    if interval is None or elapsed_seconds is None:
        return None
    try:
        elapsed = float(elapsed_seconds)
    except (TypeError, ValueError):
        return None
    if elapsed < 0:
        return None
    return int(elapsed // interval) + 1


def maxrss_sampling_note(elapsed_seconds, known_site=None):
    """The clause saying MaxRSS is also a *floor*, when too few samples were taken.

    :func:`maxrss_caveat` words the direction MaxRSS overstates -- a sum over the
    process tree double-counts shared pages. This is the other direction, and the
    two are not symmetric. Over-counting inflates a figure that is still an
    observation; a missed sample means the figure is unrelated to the peak, and
    the reader has no way to tell from the number itself.

    Reported against a real ``OUT_OF_MEMORY`` job on a cluster with
    ``JobAcctGatherFrequency=30``: an 89-second job, at most three samples, and a
    sampled peak of 188.6 MiB against the 4.0 GiB limit the kernel killed it for
    reaching -- the figure understating by 21x while every sentence around it
    pointed the other way.

    Empty when the interval is unknown, when the sampler is off, or when the job
    ran long enough for the sample count to stop being the interesting fact --
    saying "this is a sample" about a 10-hour job with 1,200 of them is noise.

    Applies to both gather plugins. ``jobacct_gather/cgroup`` reads a truer number
    per sample, which is what :func:`maxrss_caveat` says; it does not read it any
    more often.
    """
    current = known_site if known_site is not None else site()
    samples = sample_count(elapsed_seconds, current)
    if samples is None or samples > SPARSE_SAMPLE_COUNT:
        return ""
    # No article before the figures: "a 89s job" and "an 89s job" are both wrong
    # for some interval, and the numbers read fine without one.
    return (
        "the sampler runs every %ds and the job ran %ds, so at most %d sample%s \u2014 "
        "a spike between polls is not recorded"
        % (
            current.sampling_seconds,
            int(float(elapsed_seconds)),
            samples,
            "" if samples == 1 else "s",
        )
    )


_PARTITION_CEILING: dict = {}


def pin_partition_ceilings(mapping):
    """Seed the ceiling cache so no ``sinfo`` runs for those partitions.

    The counterpart to passing ``site(runner=...)``: `--demo` pins the synthetic
    cluster's configuration that way, and this pins its node sizes, so the demo
    renders identically on a login node and a laptop. Without it `--demo --sizing`
    asked the real cluster how big its partitions are.
    """
    _PARTITION_CEILING.update(mapping)


def partition_ceiling(partition, runner=None):
    """``(max cores, max MB)`` on any single node of a partition, or ``(None, None)``.

    The ceiling an upward recommendation has to respect. `--sizing` read a
    saturated workload correctly -- "the busiest run used 27.9 of 28 cores per
    task" -- and advised `--cpus-per-task=34` on a partition whose nodes have 28,
    which `sbatch` refuses outright with *"Requested node configuration is not
    available"*. The reading was right; nothing checked it against the hardware.

    Per **node**, not per partition group: `sinfo -o "%c"` collapses a
    heterogeneous partition to one row and marks it `32+`, where the number is the
    minimum and the maximum is exactly what is wanted here. `-N` lists every node,
    so the maximum is real. Measured at ~40 ms for a 605-node partition.

    Never raises and never guesses. No `sinfo`, an unknown partition, or output
    that will not parse all give ``(None, None)``, and the caller then leaves the
    recommendation alone -- an unclamped number is the current behaviour, while a
    wrong clamp would suppress advice a user needs.
    """
    if not partition:
        return None, None
    if partition in _PARTITION_CEILING:
        return _PARTITION_CEILING[partition]
    run = runner or _run
    cores, mb = None, None
    try:
        text = run(["sinfo", "-h", "-p", partition, "-N", "-o", "%c %m"])
    except (SacctError, OSError):
        text = ""
    for line in (text or "").splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        # `%c`/`%m` can carry a trailing `+` even per node on some releases; the
        # digits are the value either way.
        got = []
        for token in parts:
            digits = token.rstrip("+")
            got.append(int(digits) if digits.isdigit() else None)
        if got[0] is not None:
            cores = got[0] if cores is None else max(cores, got[0])
        if got[1] is not None:
            mb = got[1] if mb is None else max(mb, got[1])
    _PARTITION_CEILING[partition] = (cores, mb)
    return cores, mb


def cpu_total_is_complete(known_site=None) -> bool | None:
    """Whether ``TotalCPU`` covers the whole job, or None when it cannot be said.

    The single question behind :func:`cpu_caveat`, exposed separately so a caller
    that must choose between two *sentences* asks the same thing the caveat does
    rather than re-deriving it. `_io_explains_idle_cpu` sets that discipline in
    `diagnose`: share the condition, do not pick a similar-looking one.

    True only for ``jobacct_gather/cgroup``, where a reparented process stays in
    the cgroup and is still counted. None is not False, per this module's rule --
    an unknown gather type does not license the pessimistic claim.
    """
    current = known_site if known_site is not None else site()
    return current.rss_from_cgroup


def cpu_caveat(known_site=None):
    """One clause on how far ``TotalCPU`` can be trusted, or "" when it cannot say.

    The missing third arm beside :func:`maxrss_caveat`. ``TotalCPU`` is summed over
    the *step's process tree*, and a whole class of parallel runtime leaves that
    tree deliberately: `parallelly::makeClusterPSOCK`, which backs R's
    `plan(multisession)` and is that ecosystem's default recommendation, reparents
    every worker to PID 1. Their CPU is then charged to nobody.

    Reported from a second cluster on a real job: eight workers genuinely running,
    a 24-minute wall time against ~4 hours of serial work, and slurmpast reporting
    `0.1 of 8 cores busy` with `→ Try --cpus-per-task=1`. Taking that advice
    serialises the fan-out. The number is not garbage — the master's CPU is real —
    it is a **lower bound presented as a measurement**, which is the same shape as
    the two lies this module already words for and the only one that points at
    *shrinking* an allocation being used.

    Why this is a cluster property and not a universal disclaimer: reparenting
    moves a process in the tree but not out of its cgroup, so a site gathering
    with ``jobacct_gather/cgroup`` charges those workers to the job correctly and
    has nothing to apologise for. Confirmed on the reporting cluster, which has no
    per-job ``cpuacct`` at all, so no user-side change could improve the figure —
    which is what makes saying how good it is the whole remedy.

    ``JobAcctGatherFrequency`` is deliberately not read: the poll interval is
    irrelevant here, and the reporter's own three-arm control disproved it as an
    explanation. Encoding it would put a wrong reason in the code.
    """
    current = known_site if known_site is not None else site()
    from_cgroup = cpu_total_is_complete(current)
    if from_cgroup is None:
        return (
            "TotalCPU may miss work done in processes reparented out of the step's "
            "tree, depending on this cluster's JobAcctGatherType, so treat it as a "
            "lower bound"
        )
    if from_cgroup:
        return (
            "TotalCPU is gathered from the cgroup here (%s), which a reparented "
            "process stays in, so detached worker pools are counted" % current.jobacct_gather_type
        )
    return (
        "TotalCPU is summed over the step's process tree under %s, so work in "
        "processes reparented away from it — PSOCK/multisession worker pools, "
        "nohup/setsid children, detached daemons — is not counted; treat it as a "
        "lower bound" % current.jobacct_gather_type
    )


def gpu_utilization_note(known_site=None):
    """Why no GPU utilization figure is shown, in terms of this cluster's config."""
    current = known_site if known_site is not None else site()
    if current.tracks_gpu_utilization:
        # Configured but absent from the record: MIG devices report no utilization
        # through NVML, and a step that ended before the first sample has none.
        return "not recorded for this job"
    if not current.known:
        return "not recorded by Slurm"
    return "not gathered by this cluster (needs AutoDetect=nvml in gres.conf)"
