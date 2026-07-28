"""Finding a finished job's stderr/stdout.

Slurm 20.11 does not expose ``StdOut``/``StdErr`` through sacct (they arrive in
later releases), so on this cluster the path has to be guessed. Guessing is done
explicitly and reported, because a wrong log attached to a post-mortem is worse
than no log: it invents a cause.

Only ``%j``-style default names and a few conventional layouts are tried. When
nothing matches, callers get ``None`` and the CUDA-OOM / traceback rules stay
silent rather than speculate.
"""

import os

# Ordered most- to least-specific. ``{jid}`` is the base job id.
_PATTERNS = (
    "slurm-{jid}.out",
    "slurm-{jid}.err",
    "{jid}.out",
    "{jid}.err",
    "slurm_{jid}.out",
    "job-{jid}.out",
)
_SUBDIRS = ("", "logs", "log", "report", "slurm_logs", "out", "outputs")

MAX_TAIL_BYTES = 256 * 1024


def base_job_id(job_id):
    return str(job_id).split(".")[0].split("+")[0]


def candidate_paths(job, extra_dirs=None):
    """Paths worth checking for this job's log, in priority order."""
    jid = base_job_id(job.job_id)
    array_base = jid.split("_")[0]
    roots = []
    for directory in extra_dirs or ():
        if directory:
            roots.append(directory)
    if job.work_dir:
        roots.append(job.work_dir)
    roots.append(os.getcwd())

    seen = set()
    out = []
    for root in roots:
        for sub in _SUBDIRS:
            base = os.path.join(root, sub) if sub else root
            for pattern in _PATTERNS:
                for ident in (jid, array_base):
                    path = os.path.normpath(os.path.join(base, pattern.format(jid=ident)))
                    if path not in seen:
                        seen.add(path)
                        out.append(path)
    return out


def find_log(job, extra_dirs=None, exists=os.path.isfile):
    """First existing candidate path, or None."""
    for path in candidate_paths(job, extra_dirs=extra_dirs):
        try:
            if exists(path):
                return path
        except OSError:
            continue
    return None


def read_tail(path, max_bytes=MAX_TAIL_BYTES):
    """Last ``max_bytes`` of a file as text, or None if unreadable.

    Job logs on this cluster are routinely megabytes of tqdm carriage-return
    spam, so only the tail is read and \\r is normalised to \\n so progress-bar
    lines do not collapse a traceback onto one unreadable row.
    """
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as handle:
            if size > max_bytes:
                handle.seek(size - max_bytes)
            raw = handle.read()
    except OSError:
        return None
    text = raw.decode("utf-8", "replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def load_for(job, extra_dirs=None):
    """Return (path, text). Either may be None."""
    path = find_log(job, extra_dirs=extra_dirs)
    if not path:
        return None, None
    return path, read_tail(path)
