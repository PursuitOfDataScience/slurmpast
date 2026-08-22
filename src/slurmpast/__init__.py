"""slurmpast — why did your Slurm jobs fail?

A post-mortem for finished jobs. ``slurmate`` builds the request, ``slurmwatch``
watches the run, this reads the wreckage.

The analysis modules -- ``sacct``, ``model``, ``diagnose``, ``patterns``,
``nodes``, ``index``, ``sizing``, ``logs``, ``site`` and ``duration`` -- import no
third-party package, so they are usable as a library on a login node without a UI
framework. ``rich`` and ``textual`` are reached for only by ``render``, ``report``,
``theme`` and ``tui``, which is what
``test_the_analysis_layer_needs_no_third_party_package`` enforces.

Four of the ten were missing from this list, ``sizing`` among them -- the module
the README's own library example imports. The guarantee always covered them; only
the sentence promising it was short.

Nothing here is specific to one cluster. Field names, output delimiters and
timestamp formats are negotiated with the local ``sacct``; what a measurement
means where sites differ (``JobAcctGatherType``, whether GPUs reach accounting at
all) is read from ``scontrol show config`` by ``site``. See that module and the
traps listed in ``sacct``.
"""

from ._version import __version__
from .diagnose import diagnose, looks_like_noop
from .index import GroupStats, History, build_groups
from .model import CRITICAL, INFO, WARNING, Finding, Job, Step, Verdict
from .sacct import Sacct, SacctError

# Only the type, deliberately. Re-exporting the `site()` accessor here would bind
# the name `slurmpast.site` to a function and shadow the submodule of the same
# name, so `slurmpast.site.reset_cache` would stop resolving. Import it as
# `from slurmpast.site import site`.
from .site import Site

__all__ = [
    "__version__",
    "Sacct",
    "SacctError",
    "Job",
    "Step",
    "Finding",
    "Verdict",
    "History",
    "GroupStats",
    "Site",
    "build_groups",
    "diagnose",
    "looks_like_noop",
    "CRITICAL",
    "WARNING",
    "INFO",
]
