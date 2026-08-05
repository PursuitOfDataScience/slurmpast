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
