"""Finding a finished job's stderr/stdout.

Which sources exist depends entirely on the cluster's Slurm, so all of them are
tried, best first. Verified against SchedMD's archived man pages -- the boundaries
are later than they look, and a tool that assumes the newest one guesses on most
clusters in service:

1. **StdOut/StdErr, from Slurm 24.05.** Absent in 20.11, 21.08, 22.05, 23.02 and
   23.11; present in 24.05. (21.08 is the release that added ``SubmitLine`` and
   ``AccountingStoreFlags=job_script`` -- not these fields.) The value is the
   *pattern* the job was submitted with -- ``/scratch/me/slurm-%A_%a.out``,
   unexpanded -- so the ``%`` codes are substituted here rather than by re-invoking
   sacct with ``--expand-patterns``, which shipped in the same release.
   See :func:`expand_pattern`.

2. **The ``-o``/``-e`` inside SubmitLine, from Slurm 21.08.** Five releases and
   about three years earlier than (1), which is the difference between knowing and
   guessing on every 21.08-to-23.11 cluster. The recorded command line holds the
   options as typed. See :func:`submit_line_patterns`.

3. **A path the user stashed in ``--comment``, on any version.** The only route
   left below 21.08, where Slurm records nothing about where output went and
   slurmctld forgets the job after ``MinJobAge`` (120s on the cluster this was
   measured on). ``Comment`` is kept by the accounting database indefinitely.
   See :func:`comment_paths`.

4. **Conventional names.** With nothing recorded, the default ``slurm-<jobid>.out``
   and a few common layouts are tried.

5. **Timing.** When the name gives nothing away either, the file last written as
   the job ended is the best remaining evidence.

Every candidate from (1) to (4) is confirmed to exist before it is used, so an
aggressive expansion costs nothing: a wrong guess simply does not match. Only (5)
is an inference, and callers are told so -- a wrong log attached to a post-mortem
is worse than no log, because it invents a cause.
"""

import functools
import os
import re
import shlex
import stat

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

# What a job's output file is allowed to be called when the name is not known:
# whether a free-text ``--comment`` is a log path, and which files timing may
# consider at all.
_LOG_SUFFIXES = (".out", ".err", ".log")

MAX_TAIL_BYTES = 256 * 1024


def base_job_id(job_id):
    return str(job_id).split(".")[0].split("+")[0]


# Slurm's filename patterns, as documented for `sbatch --output`. The optional
# digits are a zero-pad width: `%4j` on job 128 gives `0128`.
_PATTERN_CODE = re.compile(r"%(\d*)([%AaJjNnstux])")

# Widest zero-pad worth honouring. The pattern comes out of the accounting
# database -- StdOut, StdErr, or the recorded submit line -- so the width is
# whatever the user typed, and `zfill` on it allocates that many bytes: a fat
# fingered `--output=o-%2000000000j.out` built a 2 GB string and took `find_log`
# down with an uncaught MemoryError, in a tool whose whole job is to explain a
# crash rather than add one. Same reasoning as nodes.MAX_EXPANSION, and the same
# shape of bound: far above any real filename, so nothing legitimate notices.
MAX_PAD_WIDTH = 64


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
    #
    # A heterogeneous component needs exactly the same substitution and was not
    # getting it: sacct displays `500+1` for one, JobIDRaw carries the plain `501`,
    # and gating on `array_task` alone sent the display form through, expanding
    # `slurm-%j.err` to `slurm-500+1.err`. `%j` is a job number, so Slurm never
    # wrote a `+` into that name and the recorded path could not match anything --
    # for a job whose output location was known exactly. Asking whether JobIDRaw
    # says something different covers both spellings without naming either.
    own_id = raw
    if job.job_id_raw and str(job.job_id_raw) != raw:
        own_id = str(job.job_id_raw)
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
            return value.zfill(min(int(width), MAX_PAD_WIDTH))
        return value

    try:
        return _PATTERN_CODE.sub(replace, pattern)
    except KeyError:
        return ""


# sbatch's spellings for the two paths worth reading, long form first.
_OUTPUT_OPTS = ("--output", "-o")
_ERROR_OPTS = ("--error", "-e")


def _option_values(tokens, long_name, short_name):
    """Every value given for one option in a tokenised command line, last first.

    sbatch lets a later ``-o`` override an earlier one, so the last occurrence is
    the one that took effect. The earlier ones are kept behind it rather than
    dropped, since each is existence-checked anyway and costs only a stat.
    """
    found = []
    for index, token in enumerate(tokens):
        value = ""
        if token.startswith(long_name + "="):
            value = token[len(long_name) + 1 :]
        elif token in (long_name, short_name):
            value = tokens[index + 1] if index + 1 < len(tokens) else ""
        elif len(token) > 2 and not token.startswith("--") and token.startswith(short_name):
            # getopt's attached short form, which sbatch accepts: ``-oslurm.out``.
            value = token[2:]
        # A value that is itself an option means the real one is missing -- a
        # truncated command line, not a file called ``--exclusive``.
        if value and not value.startswith("-"):
            found.append(value)
    return list(reversed(found))


def submit_line_patterns(job):
    """``--output``/``--error`` patterns parsed out of the recorded submit line.

    ``SubmitLine`` arrived in Slurm 21.08, five releases before ``StdOut``/``StdErr``
    (24.05), so on everything in between it is the only place the path Slurm actually
    used is written down. It holds the command as typed, so a value may be a pattern
    (``-o slurm-%j.out``) and may be relative to the work directory -- both handled
    by :func:`recorded_paths`, which is why this returns raw values.

    Only the option *name* before ``=`` is inspected, so an embedded command such as
    ``--wrap="gcc -o a.out a.c"`` stays one token that never looks like an output
    option. A ``-o`` among the *script's* own trailing arguments would still be read;
    every candidate is existence-checked, so a wrong one drops out silently instead
    of being presented as fact.

    stderr first: a traceback is what a post-mortem is looking for.
    """
    line = (job.submit_line or "").strip()
    if not line:
        return []
    try:
        tokens = shlex.split(line)
    except ValueError:
        # An unbalanced quote in a command line Slurm recorded verbatim is not
        # worth failing a post-mortem over.
        return []
    return _option_values(tokens, *_ERROR_OPTS) + _option_values(tokens, *_OUTPUT_OPTS)


def comment_paths(job):
    """A log path the user stashed in ``--comment``, if that is what it holds.

    Works on every Slurm, which is what makes it worth reading: below 21.08 nothing
    records where output went, and ``scontrol``, which does know, forgets the job
    after ``MinJobAge``. ``Comment`` is stored by the accounting database
    (``AccountingStoreJobComment=Yes``, or ``AccountingStoreFlags=job_comment`` from
    21.08) and kept indefinitely, so ``sbatch --comment="$PWD/logs/run.out"``
    preserves what Slurm itself will not.

    Absolute paths with a log suffix only. The field is free text used for all sorts
    of things, and resolving "rerun of 4412" against the work directory would invent
    a candidate out of a sentence.
    """
    value = (job.comment or "").strip()
    if value and os.path.isabs(value) and value.endswith(_LOG_SUFFIXES):
        return [value]
    return []


def recorded_paths(job):
    """Paths recorded for this job's output, expanded and absolute, best first.

    Three sources, each of them what the job was actually submitted with rather
    than a guess: ``StdOut``/``StdErr`` (Slurm 24.05+), the ``--output``/``--error``
    options inside ``SubmitLine`` (21.08+), and ``--comment`` (any version). Empty
    only when the cluster records none of them.

    ``StdErr`` defaults to ``StdOut`` when the job set only ``--output``, so the two
    are commonly identical; duplicates are dropped.
    """
    patterns = [job.std_err, job.std_out]
    patterns.extend(submit_line_patterns(job))
    patterns.extend(comment_paths(job))
    out = []
    for pattern in patterns:
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

    Exposed so a miss can say WHERE it looked. ``sacct`` before Slurm 24.05 has no
    StdOut/StdErr field at all -- requesting either is rejected outright with
    "Invalid field requested" -- so the path can only be guessed, and "not found"
    with nothing else is a dead end rather than something a reader can fix.
    """
    roots = [directory for directory in (extra_dirs or ()) if directory]
    if job.work_dir:
        roots.append(job.work_dir)
    roots.append(os.getcwd())
    return roots


#: How many distinct (work directory, --log-dir set, cwd) combinations to keep
#: the derived directory lists for. A history has a handful of work directories,
#: not thousands, so this never evicts in practice.
_DIR_CACHE = 256


@functools.lru_cache(maxsize=_DIR_CACHE)
def _searched_dirs(roots):
    """Each of ``roots`` crossed with :data:`_SUBDIRS`, normalised, in order.

    Cached because it is a pure derivation of the root strings and it was being
    rebuilt once per job. Over a 29,617-job history that was 6.8 million
    ``os.path.normpath`` calls to compute the same fourteen strings.

    Directory NAMES only. The cache the :class:`Scan` docstring rules out is one
    over directory *contents* -- "a long-lived dashboard that cached directory
    contents once would stop seeing logs written after it started". This holds
    nothing a later write could change, and the working directory arrives as one
    of ``roots``, so a ``chdir`` is a different key rather than a stale answer.
    """
    seen = set()
    out = []
    for root in roots:
        for sub in _SUBDIRS:
            base = os.path.normpath(os.path.join(root, sub) if sub else root)
            if base not in seen:
                seen.add(base)
                out.append(base)
    return tuple(out)


def _candidate_dirs(job, extra_dirs=None):
    return _searched_dirs(tuple(searched_roots(job, extra_dirs)))


def _candidate_names(job):
    """The conventional filenames this job's log could carry, in priority order.

    Pattern-major, identifier-minor -- the order :func:`candidate_paths` has
    always produced, kept here so the two cannot drift.
    """
    jid = base_job_id(job.job_id)
    array_base = jid.split("_")[0]
    idents = (jid,) if array_base == jid else (jid, array_base)
    return tuple(pattern.format(jid=ident) for pattern in _PATTERNS for ident in idents)


def _candidate_parts(job, extra_dirs=None):
    """``(directory, name)`` for every conventional candidate, in priority order.

    Split out of :func:`candidate_paths` because the caller that matters --
    :func:`find_log` behind a :class:`Scan` -- asks the directory listing about a
    NAME, and joining the two only to split them straight back apart was 6.9M
    ``os.path.join`` and 4.9M ``os.path.split`` calls over one history.
    """
    names = _candidate_names(job)
    for base in _candidate_dirs(job, extra_dirs):
        for name in names:
            yield base, name


def candidate_paths(job, extra_dirs=None):
    """Paths worth checking for this job's log, in priority order.

    What Slurm recorded comes first and is not a guess; the conventional names
    follow for the clusters that record nothing.
    """
    seen = set()
    out = []
    for path in recorded_paths(job):
        seen.add(path)
        out.append(path)
    for base, name in _candidate_parts(job, extra_dirs):
        # `base` is already normalised and `name` holds no separator, so `join`
        # alone yields a normal path -- the `normpath` this used to wrap it in
        # was 6.8M calls that could not change an answer.
        path = os.path.join(base, name)
        if path not in seen:
            seen.add(path)
            out.append(path)
    return out


def _is_null_device(path):
    """Whether ``path`` names the null device -- the idiom for throwing output away.

    Compared as a path rather than by ``os.path.samefile``, because the question is
    what the submitter *asked for*: ``--output=/dev/null`` is a statement of intent
    that survives the device being unstattable, and `samefile` needs two successful
    stats to answer at all. ``os.devnull`` rather than the literal, since that is
    the name the stdlib gives this concept.
    """
    return os.path.normpath(path or "") == os.path.normpath(os.devnull)


def probe_path(path):
    """``"found"``, ``"absent"``, ``"discarded"``, ``"special"``, ``"unreadable"``
    or ``"unknown"`` for one path.

    `os.path.isfile` answers False for ENOENT and EACCES alike -- it swallows the
    `OSError` -- so a caller holding only that boolean can say a file is missing
    when the truth is that it is behind a directory mode 700. On a shared cluster
    that is not a corner case: measured over 12 hours of other users' jobs, 104 of
    the 106 records naming a log path were unreadable rather than absent, so the
    "moved or deleted" wording was wrong 98% of the time it appeared about a
    foreign job. It is also impossible to see on a single-user machine, which is
    where the message was written.

    The errno is the answer and it is already being thrown away. Same shape as two
    findings elsewhere in this family -- a failed call's own explanation discarded
    and the gap filled with a guess -- so this returns the distinction rather than
    a boolean and lets the caller word it.

    ``discarded`` and ``special`` exist because the final line used to fold "exists
    but is not a regular file" into ``absent``, and ``/dev/null`` is a character
    device: ``os.path.isfile`` is False for it, so the single most common way to
    say "I do not want this output" was reported as a log that had been *moved or
    deleted*, with ``--log-dir points at it`` offering a recovery that cannot
    exist. Measured on pythia over three days, ``StdOut=/dev/null`` on 152 of 2,675
    records -- 5.7%, and the fourth most common log path on the cluster.

    That is the same error this function was written to stop making one branch up:
    a stat that succeeded is not a stat that found a file, just as a stat that
    failed is not a stat that found nothing.
    """
    # Before the stat, not after: the intent is in the path, and a site where
    # /dev/null is missing or unstattable should still not be told its log moved.
    if _is_null_device(path):
        return "discarded"
    try:
        info = os.stat(path)
    except FileNotFoundError:
        return "absent"
    except NotADirectoryError:
        # A component of the path is a file, so the target cannot exist either.
        return "absent"
    except PermissionError:
        return "unreadable"
    except OSError:
        return "unknown"
    if stat.S_ISREG(info.st_mode):
        return "found"
    # A directory, a fifo, another device. Rare next to /dev/null, but it is
    # present and unreadable-as-a-log, which is neither "found" nor "absent".
    return "special"


def find_log(job, extra_dirs=None, exists=os.path.isfile, scan=None):
    """First existing candidate path, or None. Matched by name, so it is certain.

    ``scan`` is an optimisation and nothing else: given one, a conventional name
    that the directory listing does not hold is ruled out without building a path
    at all. Every conventional spelling ends in ``.out`` or ``.err``, which is
    exactly the set :meth:`Scan.entries` keeps, so the listing settles absence
    here for the reason :meth:`Scan.exists` already gives. A name the listing DOES
    hold still goes through ``exists``, so a dangling symlink is still refused.

    Without a ``scan`` the loop is what it always was, one ``exists`` per
    candidate path.
    """
    for path in recorded_paths(job):
        try:
            if exists(path):
                return path
        except OSError:
            continue
    candidates = _candidate_names(job)
    for base in _candidate_dirs(job, extra_dirs=extra_dirs):
        # The listing fetched once per DIRECTORY, not once per candidate: there
        # are twelve conventional spellings behind each one, so asking the scan
        # inside the inner loop was 4.9M method calls over one history.
        here = scan.names(base) if scan is not None else None
        for name in candidates:
            if here is not None and name not in here:
                continue
            path = os.path.join(base, name)
            try:
                if exists(path):
                    return path
            except OSError:
                continue
    return None


def _log_dirs(job, extra_dirs=None):
    """``(directory, trusted)`` pairs to scan, in priority order.

    ``trusted`` says whether an mtime alone is decent evidence in that directory,
    and it is what separates a log directory from a home directory. A ``report/``
    or ``logs/`` subdirectory exists to hold job output, so the file written as the
    job ended is very likely the job's. The bare submit directory holds everything
    else the user owns: measured here, a recurring backup script's
    ``openclaw_backup_verify.log`` sat in ``$HOME`` being appended to every morning,
    so its mtime lands inside whichever job window it currently falls in and it was
    attached to a training post-mortem. A directory named with ``--log-dir`` is
    trusted, because the user just said that is where the logs are.
    """
    return _scanned_dirs(tuple(extra_dirs or ()), job.work_dir or "", os.getcwd())


@functools.lru_cache(maxsize=_DIR_CACHE)
def _scanned_dirs(extra, work_dir, cwd):
    """:func:`_log_dirs` for one (--log-dir set, work directory, cwd).

    Cached for the reason :func:`_searched_dirs` is, and it is the same saving:
    this was 116,006 calls over one 29,617-job history, each re-deriving the same
    fifteen strings. Keyed on all three because all three are inputs -- a
    ``chdir`` between two jobs changes the answer and must change the key.
    """
    seen = set()
    out = []
    for directory in extra:
        if not directory:
            continue
        directory = os.path.normpath(directory)
        if directory not in seen:
            seen.add(directory)
            out.append((directory, True))
    roots = []
    if work_dir:
        roots.append(work_dir)
    roots.append(cwd)
    for root in roots:
        for sub in _SUBDIRS:
            base = os.path.normpath(os.path.join(root, sub) if sub else root)
            if base in seen:
                continue
            seen.add(base)
            out.append((base, bool(sub)))
    return tuple(out)


class Scan:
    """One pass's view of the filesystem, so resolving many jobs stays one walk.

    Every job in a history shares a work directory, so resolving them one at a time
    re-``listdir``s the same handful of directories once per job -- 6,600 jobs by 15
    candidate directories is 100,000 syscalls to read the same few answers, which is
    what made a cross-job pass too slow to run behind an interactive keypress.

    Deliberately per-pass rather than a module-level cache: a long-lived dashboard
    that cached directory contents once would stop seeing logs written after it
    started.
    """

    def __init__(self):
        self._entries = {}
        self._names = {}
        self._by_digits = {}
        self._stat = {}
        self._size = {}

    def entries(self, directory):
        """Names in ``directory`` that could be a job log at all."""
        if directory not in self._entries:
            try:
                found = [e for e in os.listdir(directory) if e.endswith(_LOG_SUFFIXES)]
            except OSError:
                found = []
            self._entries[directory] = found
        return self._entries[directory]

    def names(self, directory):
        """:meth:`entries` as a set. The public spelling of :meth:`_names_in`.

        `find_log` asks this directly, so that ruling a conventional filename out
        costs one set lookup instead of a path built and split apart again.
        """
        return self._names_in(directory)

    def _names_in(self, directory):
        """:meth:`entries` as a set, cached alongside it.

        Cached for the same reason the listing is. :meth:`exists` asked
        ``name not in set(self.entries(directory))``, which rebuilds the set on
        every probe -- so the membership test this class exists to make O(1) was
        O(files in the directory) instead, ~84 times per job. Measured against a
        13,000-file log directory it cost 16.6 us per probe against 2.8 cached,
        which over the docstring's own 6,600-job history is ~9 s of pure rebuild
        behind an interactive keypress. :meth:`by_digits` already caches a derived
        index per directory; this is the one that did not.
        """
        if directory not in self._names:
            self._names[directory] = set(self.entries(directory))
        return self._names[directory]

    def by_digits(self, directory):
        """``{digit run: [names containing it]}`` for one directory.

        Turns "does any file here carry this job's id" from a regex over every name
        into a dict lookup, which is what makes a whole-history pass affordable.
        Keying on *maximal* runs of digits gives the delimiting for free: job 60 is
        absent from ``1060-train.out``, whose only run is ``1060``.
        """
        if directory not in self._by_digits:
            index = {}
            for entry in self.entries(directory):
                for run in set(_DIGIT_RUN.findall(entry)):
                    index.setdefault(run, []).append(entry)
            self._by_digits[directory] = index
        return self._by_digits[directory]

    def exists(self, path):
        """Whether ``path`` is a regular file, answered from the directory listing.

        ``find_log`` probes ~170 conventional spellings per job -- 7 subdirectories
        by 6 patterns by 2 identifiers by 2 roots -- which over a 6,600-job history
        is more than a million ``stat`` calls for questions one ``listdir`` per
        directory already answers. Only a name the listing cannot speak for (a
        recorded path with no log suffix) is stat'd, and that answer is cached too.

        The listing settles *absence*, which is what those million calls were
        asking about, but it cannot settle presence: a name appears in it whether or
        not it resolves. A dangling symlink -- routine once a scratch purge has been
        through -- was therefore reported as a confirmed log with ``inferred=False``,
        `read_tail` returned nothing from it, and the readable ``.out`` sitting
        beside it was never tried, so the report named a log path and said "no log
        was found" a few lines later. Confirming only the names the listing says are
        there costs one cached stat per hit rather than per probe, which leaves the
        reason for the fast path intact.
        """
        directory, name = os.path.split(path)
        if name.endswith(_LOG_SUFFIXES) and name not in self._names_in(directory):
            return False
        return self.mtime(path) is not None

    def mtime(self, path):
        """``mtime`` of a regular file, or None if it is neither."""
        if path not in self._stat:
            try:
                self._stat[path] = os.path.getmtime(path) if os.path.isfile(path) else None
            except OSError:
                self._stat[path] = None
        return self._stat[path]

    def size(self, path):
        """Byte size of a regular file, or 0 when it cannot be read.

        Cached beside ``mtime`` for the same reason: ``time_candidates`` asks
        about every entry in every candidate directory, and a scan that stats
        each one twice doubles the syscalls on a directory holding thousands of
        logs. Unreadable counts as 0 -- a file this process cannot open cannot
        explain a failure either.
        """
        if path not in self._size:
            try:
                self._size[path] = os.path.getsize(path) if os.path.isfile(path) else 0
            except OSError:
                self._size[path] = 0
        return self._size[path]

    def is_file(self, path):
        return self.exists(path)


# stderr before stdout: a post-mortem is looking for the traceback. ``.log`` last --
# it is the least conventional of the three for Slurm output.
_SUFFIX_RANK = {".err": 0, ".out": 1, ".log": 2}

# Maximal runs of digits in a filename; see :meth:`Scan.by_digits`.
_DIGIT_RUN = re.compile(r"\d+")


def _suffix_key(entry):
    return (_SUFFIX_RANK.get(os.path.splitext(entry)[1], 3), entry)


def job_identifiers(job):
    """The ids a filename could carry for this job, most specific first.

    An array element is ``60_4`` in ``JobID`` while ``%j`` expanded to its own
    allocation number, so both spellings have to be recognised -- and the array
    master's plain ``60`` last, since it is shared with every sibling element and so
    is the weakest of the three.

    That third one was missing. ``base_job_id`` strips ``.step`` and ``+het`` but
    not ``_task``, so asked for the master of ``60_4`` it returned ``60_4`` unchanged
    -- a duplicate of ``raw`` that the check below dropped, leaving two identifiers
    where the docstring promised three. An array submitted with
    ``--output=%x-%A.out``, which writes one shared file per array and no ``%a``,
    was reported as having no log at all while ``train-60.out`` sat in the directory.
    """
    raw = str(job.job_id)
    out = [raw]
    array_master = base_job_id(raw).split("_")[0]
    for ident in (job.job_id_raw, base_job_id(raw), array_master):
        if ident and ident not in out:
            out.append(str(ident))
    return out


def _carries_ident(name, ident):
    r"""Whether ``name`` holds ``ident`` delimited by non-digits.

    Exactly what ``re.search(r"(?<!\d)" + re.escape(ident) + r"(?!\d)", name)``
    answers, without the regex. The pattern is built from the JOB ID, so it is a
    different pattern for every job -- 29,617 of them on one history, which walks
    straight through `re`'s 512-entry cache and recompiles: 49,019 compilations,
    5.2 s of a 15.0 s profiled pass. A literal needs no engine.
    """
    width = len(ident)
    at = name.find(ident)
    while at != -1:
        if (at == 0 or not name[at - 1].isdigit()) and not name[
            at + width : at + width + 1
        ].isdigit():
            return True
        at = name.find(ident, at + 1)
    return False


def find_log_by_id(job, extra_dirs=None, scan=None):
    """A log whose *name* carries this job's id, whatever the rest of the name is.

    :func:`candidate_paths` knows six conventional spellings, and the commonest
    convention of all is not among them because it cannot be: ``--output=%x-%j.out``
    produces ``sft-h100-51554394.out``, where the id is right there but the rest is
    the job's name. Measured on a real history, that sent 20 jobs whose log sat in a
    searched directory carrying their own id onto the timing guess instead -- and
    handed two of those files to the wrong job, when a name containing ``51554394``
    can only belong to job 51554394.

    The id must be delimited by non-digits, so job 60 does not claim
    ``1060-train.out``.
    """
    scan = scan or Scan()
    for ident in job_identifiers(job):
        # A plain job id is a digit run, so the prebuilt index answers it outright.
        # An array element's own spelling (``60_4``) is not, so that falls back to a
        # scan of the names -- rare enough to be worth the difference.
        plain = ident.isdigit()
        for directory, _trusted in _log_dirs(job, extra_dirs):
            if plain:
                names = scan.by_digits(directory).get(ident, ())
            else:
                names = [e for e in scan.entries(directory) if _carries_ident(e, ident)]
            if not names:
                continue
            for entry in sorted(names, key=_suffix_key):
                path = os.path.normpath(os.path.join(directory, entry))
                if scan.is_file(path):
                    return path
    return None


# A job's output file is last written at the end of the run. Slack either side
# covers clock skew and a final flush after the step exits.
_MTIME_SLACK_BEFORE = 60
_MTIME_SLACK_AFTER = 600


def _job_marks(job):
    """What :func:`_relates_to_job` tests a name against, derived once per job.

    Split out because the test runs once per FILE in every untrusted directory --
    9.2 million times over one 29,617-job history against a 900-file tree -- and
    it was rebuilding the identifier list inside that loop.

    The name is returned already lowered, and empty when it is too short to be
    evidence: two characters would match almost anything, and a real job name is
    longer.
    """
    name = (job.name or "").strip().lower()
    return job_identifiers(job), (name if len(name) >= 3 else "")


def _relates(entry, idents, name):
    """:func:`_relates_to_job` against marks already derived. See :func:`_job_marks`."""
    # Five characters lowered rather than the whole filename: this is the test
    # that runs first and answers most often, and `entry.lower()` allocated a
    # copy of every name in the directory for every job.
    if entry[:5].lower() == "slurm":
        return True
    for ident in idents:
        if _carries_ident(entry, ident):
            return True
    return bool(name) and name in entry.lower()


def _relates_to_job(entry, job):
    """Whether a name in an *untrusted* directory has anything to do with this job.

    Only applied outside a log directory, where mtime on its own has been measured
    to attach unrelated files. ``slurm``-prefixed names are Slurm's own default, and
    a name carrying the job's name is the ``%x`` convention; anything else in a home
    directory is a stranger that happened to be written at the right moment.
    """
    idents, name = _job_marks(job)
    return _relates(entry, idents, name)


def time_candidates(job, extra_dirs=None, scan=None):
    """Every plausible timing match for one job as ``(key, path)``, best first.

    ``key`` sorts a trusted directory ahead of an untrusted one and, within a tier,
    the file written nearest the job's End first. Exposed as a list rather than just
    the winner so :func:`assign_logs` can resolve several jobs against each other
    instead of letting them all claim the same file.
    """
    if not (job.start and job.end):
        return []
    from datetime import datetime

    try:
        start = datetime.fromisoformat(job.start).timestamp()
        end = datetime.fromisoformat(job.end).timestamp()
    except ValueError:
        return []

    scan = scan or Scan()
    found = []
    seen = set()
    idents, job_name = _job_marks(job)
    for directory, trusted in _log_dirs(job, extra_dirs):
        # `directory` comes back normalised from `_log_dirs` and `entry` is a bare
        # name, so the prefix plus the name IS the joined path -- and `os.path.join`
        # was 9.2M calls, 12.2 s of a 52.9 s profiled pass, for a concatenation.
        prefix = directory if directory.endswith(os.sep) else directory + os.sep
        for entry in scan.entries(directory):
            if not trusted and not _relates(entry, idents, job_name):
                continue
            path = prefix + entry
            if path in seen:
                continue
            seen.add(path)
            mtime = scan.mtime(path)
            if mtime is None:
                continue
            if not (start - _MTIME_SLACK_BEFORE <= mtime <= end + _MTIME_SLACK_AFTER):
                continue
            # (tier, empty, distance, suffix, path)
            #
            # `empty` before the distance, because a zero-byte file explains
            # nothing whatever its mtime, and Slurm touches an unused `--output`
            # at job end -- so on a failed job the empty stdout is routinely
            # *closer* to End than the stderr holding the error, which was
            # written moments earlier. Reported from a second cluster: with both
            # real logs present the tool picked the 0-byte `.out` and then said
            # "no log was found to explain it", while the `.err` beside it read
            # `REAL CAUSE: disk quota exceeded`. The advice it gave was to pass
            # `--log-dir`, which the user had done.
            #
            # `suffix` *after* the distance, deliberately: only a tie-break. A
            # post-mortem wants stderr, but timing is the signal this function
            # exists for and the one measured to recover 135 of 148 runs on a
            # real history. Letting the suffix outrank it would re-pick a
            # different file for every job in a directory holding both streams.
            found.append(
                (
                    (
                        0 if trusted else 1,
                        1 if scan.size(path) == 0 else 0,
                        abs(mtime - end),
                        _SUFFIX_RANK.get(os.path.splitext(path)[1], 3),
                    ),
                    path,
                )
            )
    found.sort()
    return found


def find_log_by_time(job, extra_dirs=None, taken=None, scan=None):
    """The log this job most likely wrote, inferred from when it was written.

    Needed because a filename need not mention the job at all. Measured on a real
    history: output went to ``report/<INDEX>-train.out`` where INDEX is a shell
    counter -- no job id, no job name -- so every name-based pattern misses, and
    Slurm records no path (no StdOut field before 24.05, and slurmctld forgets a job
    after MinJobAge, 120s here).

    What *is* left is timing: a completed job's output file is last written when
    the job ends. Picking the candidate whose mtime is nearest the job's End,
    within its run window, recovered the submission order of 135 of 148
    consecutive runs on that history -- it reconstructed the user's own
    ``N-train.out`` numbering without being told the scheme.

    ``taken`` holds paths already given to another job, so a file cannot be handed
    to two runs at once. It is still an inference either way, so callers must label
    it as one: a wrong log invents a cause, which is worse than no log.
    """
    taken = taken or ()
    for _key, path in time_candidates(job, extra_dirs=extra_dirs, scan=scan):
        if path not in taken:
            return path
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


def find_log_by_name(job, extra_dirs=None, scan=None):
    """A log identified by its name, or None. Certain, so it needs no caveat.

    Two ways: a path Slurm or the user recorded, and a conventional name (either of
    the six fixed spellings or any file carrying the job id).
    """
    scan = scan or Scan()
    return find_log(job, extra_dirs=extra_dirs, exists=scan.exists, scan=scan) or find_log_by_id(
        job, extra_dirs=extra_dirs, scan=scan
    )


#: Jobs between two calls to ``assign_logs``'s ``pace`` hook. 500 is ~20 ms of
#: work at the measured 1.2 s for 29,617 jobs -- under the ~50 ms at which a
#: keypress starts to feel late -- and 59 pauses over that history, which is
#: 59 ms of added wall clock for a pass that runs in the background anyway.
PACE_EVERY = 500


def assign_logs(jobs, extra_dirs=None, pace=None):
    """Resolve logs for many jobs at once. ``{job_id: (path, inferred)}``.

    ``pace`` is called every :data:`PACE_EVERY` jobs and is how the dashboard
    stays answerable while this runs. It has to: this is Python, so it holds the
    GIL, and the dashboard starts it in a worker thread the moment a history
    lands. At 16.7 s (before the shortcuts above) that made every arrow key take
    between 0.85 s and 5.4 s; at 1.2 s it was still worth 180 ms spikes. A hook
    rather than a sleep of its own, because a library caller resolving logs in the
    foreground wants neither -- ``None`` is exactly the behaviour this always had.

    Timing has to be resolved across jobs, not one at a time. Measured on a real
    history: 51 of 296 timing matches pointed at a file that another job also
    claimed as its nearest -- one file was the best match for four separate runs of
    the same workload, and only one of them can have written it. A per-job search
    cannot see the conflict, so it confidently gave the same log to all four.

    Each contested file goes to the job whose End it is nearest; the others fall
    through to their next candidate and, failing that, get nothing. Nothing is
    better than a sibling run's log, which is the one wrong answer that looks right.

    Name matches are exempt *from each other*: two jobs legitimately share a file
    when they were submitted with the same ``--output``, and there the name is
    evidence rather than a coincidence of timing. They are not exempt from blocking
    a guess. ``report/a100-47321884.err`` carries job 47321884's id, so it is that
    job's log and cannot also be job 47321775's -- yet a guess claimed it, because
    reserving files only among the guessing jobs let better evidence lose to worse.
    """
    scan = Scan()
    resolved = {}
    pending = []
    for at, job in enumerate(jobs):
        if pace is not None and at and not at % PACE_EVERY:
            pace()
        path = find_log_by_name(job, extra_dirs=extra_dirs, scan=scan)
        if path:
            resolved[job.job_id] = (path, False)
        else:
            pending.append(job)

    ranked = []
    for at, job in enumerate(pending):
        if pace is not None and at and not at % PACE_EVERY:
            pace()
        for key, path in time_candidates(job, extra_dirs=extra_dirs, scan=scan):
            ranked.append((key, str(job.job_id), path))
    # Sorting by the candidate key puts the strongest claim on any file first, so
    # the greedy pass below settles every conflict the same way regardless of the
    # order jobs arrived in. The job id breaks exact ties so the result is stable.
    ranked.sort()

    # Seeded with everything a name already accounted for, so mtime never overrides
    # a filename.
    claimed = {path for path, _inferred in resolved.values()}
    for _key, job_id, path in ranked:
        if job_id in resolved or path in claimed:
            continue
        resolved[job_id] = (path, True)
        claimed.add(path)
    for job in pending:
        resolved.setdefault(job.job_id, (None, False))
    return resolved


def load_for(job, extra_dirs=None, taken=None):
    """Return ``(path, text, inferred)``. Path and text may be None.

    ``inferred`` is True when the file was matched by timing rather than by name,
    so callers can say so instead of presenting a guess as a fact. ``taken`` lets a
    caller resolving several jobs keep one file from being handed to two of them;
    :func:`assign_logs` does that properly for a whole list.
    """
    path = find_log_by_name(job, extra_dirs=extra_dirs)
    if path:
        return path, read_tail(path), False
    path = find_log_by_time(job, extra_dirs=extra_dirs, taken=taken)
    if not path:
        return None, None, False
    return path, read_tail(path), True
