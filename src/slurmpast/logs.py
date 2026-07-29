"""Finding a finished job's stderr/stdout.

Three sources, best first, and which one applies depends entirely on the cluster:

1. **What Slurm recorded.** From Slurm 21.08 sacct exposes ``StdOut``/``StdErr``,
   so the path is known rather than guessed. It is stored as the *pattern* the
   job was submitted with -- ``/scratch/me/slurm-%A_%a.out``, unexpanded, since
   ``--expand-patterns`` only arrived in 24.05 -- so the ``%`` codes are
   substituted here. See :func:`expand_pattern`.

2. **Conventional names.** Slurm 20.11 and older have no such field at all:
   requesting either is rejected outright with "Invalid field requested". There
   the default ``slurm-<jobid>.out`` and a few common layouts are tried.

3. **Timing.** When the name gives nothing away, the file last written as the job
   ended is the best remaining evidence.

Every candidate from (1) and (2) is confirmed to exist before it is used, so an
aggressive expansion costs nothing: a wrong guess simply does not match. Only (3)
is an inference, and callers are told so -- a wrong log attached to a post-mortem
is worse than no log, because it invents a cause.
"""

import os
import re

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


# Slurm's filename patterns, as documented for `sbatch --output`. The optional
# digits are a zero-pad width: `%4j` on job 128 gives `0128`.
_PATTERN_CODE = re.compile(r"%(\d*)([%AaJjNnstux])")


def expand_pattern(pattern, job):
    """Substitute Slurm's ``%`` filename codes for one job.

    Codes that identify the job are resolved exactly. The per-node and per-task
    ones (``%N``, ``%n``, ``%t``) cannot be -- a job with four tasks wrote four
    files -- so they resolve to the first node and rank zero, which is the file a
    reader wants first anyway. Nothing is trusted on the strength of this: the
    caller checks the path exists.

    Returns ``""`` when the pattern still holds a code that could not be resolved,
    rather than a path with a stray ``%`` in it.
    """
    if not pattern:
        return ""
    raw = str(job.job_id)
    array_master, _, array_task = raw.partition("_")
    # For an array element sacct shows `123_4` in JobID while `%j` is that
    # element's own allocation number, which is what JobIDRaw carries.
    own_id = (job.job_id_raw or raw) if array_task else raw
    first_node = ""
    if job.node_list:
        from .nodes import expand_nodelist

        nodes = expand_nodelist(job.node_list)
        first_node = nodes[0] if nodes else ""

    values = {
        "%": "%",
        "A": array_master,
        "a": array_task or "0",
        "j": own_id,
        "J": own_id,
        "s": "batch",
        "u": job.user,
        "x": job.name,
        "N": first_node,
        "n": "0",
        "t": "0",
    }

    def replace(match):
        width, code = match.group(1), match.group(2)
        value = values.get(code, "")
        if value == "":
            raise KeyError(code)
        if width and value.isdigit():
            return value.zfill(int(width))
        return value

    try:
        return _PATTERN_CODE.sub(replace, pattern)
    except KeyError:
        return ""


def recorded_paths(job):
    """Paths Slurm itself recorded for this job's output, expanded and absolute.

    Empty on any cluster running Slurm 20.11 or older, which has no such field.
    ``StdErr`` defaults to ``StdOut`` when the job set only ``--output``, so the
    two are commonly identical; duplicates are dropped.
    """
    out = []
    for pattern in (job.std_err, job.std_out):
        path = expand_pattern(pattern, job)
        if not path:
            continue
        if not os.path.isabs(path) and job.work_dir:
            path = os.path.join(job.work_dir, path)
        path = os.path.normpath(path)
        if path not in out:
            out.append(path)
    return out


def searched_roots(job, extra_dirs=None):
    """Directories the search walks, in priority order.

    Exposed so a miss can say WHERE it looked. ``sacct`` on Slurm 20.11 has no
    StdOut/StdErr field at all -- requesting either is rejected outright with
    "Invalid field requested" -- so the path can only be guessed, and "not found"
    with nothing else is a dead end rather than something a reader can fix.
    """
    roots = [directory for directory in (extra_dirs or ()) if directory]
    if job.work_dir:
        roots.append(job.work_dir)
    roots.append(os.getcwd())
    return roots


def candidate_paths(job, extra_dirs=None):
    """Paths worth checking for this job's log, in priority order.

    What Slurm recorded comes first and is not a guess; the conventional names
    follow for the clusters that record nothing.
    """
    jid = base_job_id(job.job_id)
    array_base = jid.split("_")[0]
    roots = searched_roots(job, extra_dirs)

    seen = set()
    out = []
    for path in recorded_paths(job):
        seen.add(path)
        out.append(path)
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
    """First existing candidate path, or None. Matched by name, so it is certain."""
    for path in candidate_paths(job, extra_dirs=extra_dirs):
        try:
            if exists(path):
                return path
        except OSError:
            continue
    return None


# Files worth considering as a job's output when the name gives nothing away.
_LOG_SUFFIXES = (".out", ".err", ".log")
# A job's output file is last written at the end of the run. Slack either side
# covers clock skew and a final flush after the step exits.
_MTIME_SLACK_BEFORE = 60
_MTIME_SLACK_AFTER = 600


def find_log_by_time(job, extra_dirs=None):
    """The log this job most likely wrote, inferred from when it was written.

    Needed because a filename need not mention the job at all. Measured on a real
    history: output went to ``report/<INDEX>-train.out`` where INDEX is a shell
    counter -- no job id, no job name -- so every name-based pattern misses, and
    Slurm records no path (no StdOut field on 20.11, and slurmctld forgets a job
    after MinJobAge, 120s here).

    What *is* left is timing: a completed job's output file is last written when
    the job ends. Picking the candidate whose mtime is nearest the job's End,
    within its run window, recovered the submission order of 135 of 148
    consecutive runs on that history -- it reconstructed the user's own
    ``N-train.out`` numbering without being told the scheme.

    It is still an inference, so callers must label it as one: a wrong log invents
    a cause, which is worse than no log.
    """
    if not (job.start and job.end):
        return None
    from datetime import datetime

    try:
        start = datetime.fromisoformat(job.start).timestamp()
        end = datetime.fromisoformat(job.end).timestamp()
    except ValueError:
        return None

    best = None
    for directory in searched_roots(job, extra_dirs):
        for sub in _SUBDIRS:
            base = os.path.join(directory, sub) if sub else directory
            try:
                entries = os.listdir(base)
            except OSError:
                continue
            for entry in entries:
                if not entry.endswith(_LOG_SUFFIXES):
                    continue
                path = os.path.join(base, entry)
                try:
                    if not os.path.isfile(path):
                        continue
                    mtime = os.path.getmtime(path)
                except OSError:
                    continue
                if not (start - _MTIME_SLACK_BEFORE <= mtime <= end + _MTIME_SLACK_AFTER):
                    continue
                distance = abs(mtime - end)
                if best is None or distance < best[0]:
                    best = (distance, path)
    return best[1] if best else None


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
    """Return ``(path, text, inferred)``. Path and text may be None.

    ``inferred`` is True when the file was matched by timing rather than by name,
    so callers can say so instead of presenting a guess as a fact.
    """
    path = find_log(job, extra_dirs=extra_dirs)
    if path:
        return path, read_tail(path), False
    path = find_log_by_time(job, extra_dirs=extra_dirs)
    if not path:
        return None, None, False
    return path, read_tail(path), True
