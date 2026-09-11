"""A record a job cannot change any more, kept so the next run does not re-read it.

Almost everything ``slurmpast`` does at startup is spent turning ``sacct`` text
into :class:`~slurmpast.model.Job` objects, and almost all of that work is
repeated verbatim on the next run: **a job that has finished cannot change.**
Measured on midway3 (Slurm 20.11.8) over one user's last seven days -- 29,624
jobs, 89,163 rows:

    the whole read, parallel and uncached        5.19 s
    the listing this validates against           0.45 s
    reading 29,624 cached jobs back (22.9 MB)    0.73 s

So a second run inside the same window costs about a fifth of the first.

What makes it safe is the *fingerprint*, not a timestamp. Every run asks sacct
for ``JobID,State,End`` over the window it was given -- one cheap ``-X`` query it
was already making to partition the read -- and a cached job is reused only when
what sacct says about it right now is exactly what it said when the job was
stored. Anything else and the job is re-read:

* a job still RUNNING, or with no ``End``, is never stored at all, so the
  window's live jobs are always fresh;
* a job that was requeued after it finished comes back with a different
  ``(state, end)`` sequence -- ``-D`` lists every incarnation -- and misses;
* a state edited in the accounting database misses for the same reason;
* an unexpanded pending array (``49046820_[1-20%10]``) is not terminal, so it is
  never stored.

The cost of a wrong answer here is a post-mortem of a job that is not the job on
screen, so the checks are deliberately conservative: the file is keyed by the
package version AND the exact field list the records were parsed from, and any
mismatch, unreadable file or unpickleable payload is treated as an empty cache
rather than as something to salvage.

What the fingerprint does NOT cover, stated rather than left to be discovered: a
field edited in slurmdbd on an already-finished job without moving its state or
its End -- in practice ``AdminComment`` or ``Comment``, which ``sacctmgr``/
``scontrol update`` can rewrite after the fact. Such a record keeps its stored
value until the job leaves the window or the cache is discarded. Nothing this tool
*diagnoses* is read from those two fields, and `--no-cache` re-reads everything for
a caller who needs the very latest of them.

Nothing here imports a third-party package, matching the rest of the analysis
side of this codebase.
"""

from __future__ import annotations

import contextlib
import os
import pickle
import tempfile

from ._version import __version__

#: Bumped when the shape of the payload below changes in a way an older or newer
#: slurmpast could misread. The package version is checked too -- this is for the
#: case where the version did not move but the record did.
FORMAT = 3

#: Jobs kept across all windows ever asked for. A cache is only worth having if
#: it survives switching between `-S now-7days` and `-S now-30days`, so entries
#: are not pruned to the current window -- they are evicted oldest-End-first once
#: there are more than this. 200,000 jobs is ~150 MB at the 22.9 MB / 29,624
#: measured above, which is more than any single history and still bounded.
MAX_ENTRIES = 200_000

#: Environment variable that turns the whole thing off, for a reader who would
#: rather spend the seconds than keep a file. `--no-cache` does the same thing
#: for one run.
DISABLE_ENV = "SLURMPAST_NO_CACHE"


def enabled(environ=None):
    """Whether caching is on. Any non-empty ``SLURMPAST_NO_CACHE`` turns it off."""
    env = os.environ if environ is None else environ
    return not (env.get(DISABLE_ENV) or "").strip()


def directory(environ=None):
    """Where the cache file lives -- ``$XDG_CACHE_HOME/slurmpast``, or ``~/.cache``.

    The XDG variable first because that is what a site pointing caches at local
    disk sets, and a login node's home is often NFS.
    """
    env = os.environ if environ is None else environ
    root = (env.get("XDG_CACHE_HOME") or "").strip()
    if not root:
        root = os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(root, "slurmpast")


def _path(scope, environ=None):
    # `scope` identifies whose records these are -- see `Store.__init__`. Kept out
    # of the filename's meaning: it is hashed to a fixed, filesystem-safe string
    # so a user name with a slash or a cluster with a space cannot escape the
    # directory.
    import hashlib

    digest = hashlib.sha1(repr(scope).encode("utf-8", "replace")).hexdigest()[:16]
    return os.path.join(directory(environ), "records-%s.pickle" % digest)


def is_storable(job):
    """Whether ``job``'s record is final, and so worth keeping.

    Terminal state and an End sacct actually printed. `Job.open_ended` is the
    module's own name for the third trap at the top of `sacct.py` -- a record
    stuck in RUNNING with ``End=Unknown`` months after it died -- and such a
    record is exactly the one that must never be frozen: it is not finished, it
    is unreadable, and its Elapsed grows every time anybody asks.
    """
    return bool(job.end) and not job.open_ended and not job.in_progress


class Store:
    """The cache file for one (cluster, user, field list), read and written whole.

    Whole rather than per-record because it is one 23 MB pickle read in 0.73 s
    against the 5.19 s it saves, and because a partial write is the one failure
    mode that could hand back a job that never existed. Writes go through a
    temporary file in the same directory and `os.replace`, which is the atomic
    swap the training scripts in this family already use.
    """

    def __init__(self, scope, fields, environ=None):
        #: Anything that changes what a record MEANS belongs here: the cluster it
        #: came from and the account it was read under. The window does not --
        #: a job is the same job whichever window found it.
        self._scope = scope
        self._fields = tuple(fields)
        self._environ = environ
        self._path = _path(scope, environ)
        self._records: dict = {}
        self._loaded = False
        self._dirty = False

    # -- reading -----------------------------------------------------------

    def load(self):
        """Read the file, or leave the cache empty. Never raises."""
        if self._loaded:
            return self._records
        self._loaded = True
        try:
            with open(self._path, "rb") as handle:
                payload = pickle.load(handle)
        except (OSError, EOFError, pickle.UnpicklingError, AttributeError, ValueError):
            # Missing, truncated, or written by a slurmpast whose classes this
            # one cannot reconstruct. All of them mean the same thing: no cache.
            return self._records
        if not isinstance(payload, dict):
            return self._records
        if payload.get("format") != FORMAT or payload.get("version") != __version__:
            return self._records
        if tuple(payload.get("fields") or ()) != self._fields:
            # A different `--format` was in force when these were parsed, so the
            # columns behind them are not the columns this run reads.
            return self._records
        records = payload.get("records")
        if isinstance(records, dict):
            self._records = records
        return self._records

    def get(self, job_id, fingerprint):
        """The cached job for ``job_id`` when sacct still describes it that way."""
        entry = self.load().get(job_id)
        if entry is None:
            return None
        stored, job = entry
        return job if stored == fingerprint else None

    # -- writing -----------------------------------------------------------

    def put(self, job, fingerprint):
        if not is_storable(job):
            return
        self.load()
        self._records[job.job_id] = (fingerprint, job)
        self._dirty = True

    def _evict(self):
        if len(self._records) <= MAX_ENTRIES:
            return
        # Oldest End first: the records most likely to be outside every window
        # anybody still asks about. `End` is an ISO timestamp, so it sorts.
        ordered = sorted(self._records.items(), key=lambda kv: (kv[1][1].end or "", kv[0]))
        for job_id, _entry in ordered[: len(self._records) - MAX_ENTRIES]:
            del self._records[job_id]

    def save(self):
        """Write the file if anything changed. Never raises: this is an optimisation.

        A cache that cannot be written -- a full quota, a read-only home, a
        directory somebody else owns -- must cost the reader nothing but the
        seconds they were already spending.

        Written to a temporary file in the same directory and then `os.replace`d,
        so a run interrupted mid-write leaves the previous cache intact rather
        than a truncated one. A truncated pickle would be caught by `load` and
        discarded, but "caught and discarded" means the reader silently pays full
        price for every run afterwards, which is the failure this exists to avoid.
        """
        if not self._dirty:
            return False
        self._evict()
        payload = {
            "format": FORMAT,
            "version": __version__,
            "fields": self._fields,
            "scope": self._scope,
            "records": self._records,
        }
        where = directory(self._environ)
        temporary = None
        try:
            os.makedirs(where, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(dir=where, prefix="records-", suffix=".tmp")
            with os.fdopen(descriptor, "wb") as handle:
                pickle.dump(payload, handle, pickle.HIGHEST_PROTOCOL)
            os.replace(temporary, self._path)
            temporary = None
        except (OSError, pickle.PicklingError, RecursionError):
            if temporary is not None:
                with contextlib.suppress(OSError):
                    os.unlink(temporary)
            return False
        self._dirty = False
        return True
