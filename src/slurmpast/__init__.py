"""slurmpast — why did your Slurm jobs fail?

A post-mortem for finished jobs. ``slurmate`` builds the request, ``slurmwatch``
watches the run, this reads the wreckage.

The analysis modules (``sacct``, ``diagnose``, ``patterns``, ``nodes``,
``index``) import no third-party package, so they are usable as a library on a
login node without a UI framework. Textual is only pulled in by ``tui``.
"""

from ._version import __version__
from .diagnose import diagnose, looks_like_noop
from .index import GroupStats, History, build_groups
from .model import CRITICAL, INFO, WARNING, Finding, Job, Step, Verdict
from .sacct import Sacct, SacctError

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
    "build_groups",
    "diagnose",
    "looks_like_noop",
    "CRITICAL",
    "WARNING",
    "INFO",
]
