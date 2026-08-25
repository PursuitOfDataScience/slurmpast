"""Reading Slurm accounting without producing phantom numbers.

Nine traps this module exists to close. The first five were measured on a live
Midway3 record (Slurm 20.11.8); the last four are what it takes for the same code
to be right on a cluster nobody here has seen.

1. **Field availability varies by Slurm version.** On 20.11
   ``StdOut``/``StdErr``/``SubmitLine`` do not exist -- requesting one unknown
   field makes sacct reject the *entire* query with ``Invalid field requested``
   and you get nothing. So fields are probed against ``sacct --helpformat`` and
   unsupported ones dropped.

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

6. **A field can be renamed rather than removed.** Slurm 23.02 renamed
   ``Reserved`` to ``Planned``. Treating it as merely optional means every
   cluster from 23.02 onwards silently reports no queue wait at all -- a
   measurement lost with no error. Renamed fields are therefore asked for under
   whichever spelling the local sacct accepts, and read back under one name.

7. **``|`` occurs inside field values, and ``--parsable2`` does not escape it.**
   ``--constraint="v100|a100"`` is Slurm's documented OR syntax, and it lands
   verbatim in ``Constraints`` -- field 32 of the 85 asked for below, so a single
   pipe shifts every memory, CPU and disk column after it. Slurm has offered
   ``--delimiter`` since at least 17.11, so the separator is an ASCII control
   character no shell would put in an argument.

8. **``SLURM_TIME_FORMAT`` rewrites every timestamp sacct prints.** With
   ``relative`` the same record reads ``29 Apr 14:55`` instead of
   ``2026-04-29T14:55:48``; a strftime value gives whatever it says, and sites
   do export it from a login profile. Everything downstream here -- date
   parsing, chronological sort, the STARTED column -- assumes ISO 8601, so the
   format is pinned for the child process rather than trusted.

9. **A wedged accounting database must not wedge the tool.** The query gets a
   timeout, and its output is decoded as UTF-8 with replacement rather than in
   whatever the ambient locale happens to be.
"""

from __future__ import annotations

import getpass
import math
import os
import re
import subprocess

from .duration import mem_scope, parse_bytes, parse_duration, parse_mem_limit
from .model import Job, Step

# Every field carrying a distinct measurement -- 85 of the 107 Slurm 20.11 offers.
# Deliberately wide: the full list costs 2.26 s over a seven-month history against
# 1.38 s for a minimal 27, so there is no reason to make a user re-run because the
# number they wanted was never collected. Pure redundancy (DBIndex, BlockID,
# McsLabel, duplicate spellings of the same TRES) is omitted. Names that only some
# releases know are listed in _OPTIONAL and dropped where absent.
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
    # raw TRES: the In/Out directions plus per-node attribution. TRESUsageInAve
    # carries gres/gpuutil on any site running AutoDetect=nvml -- the one place
    # Slurm records how busy the GPUs actually were.
    "TRESUsageInTot", "TRESUsageOutTot", "TRESUsageInMax", "TRESUsageInMaxNode",
    "TRESUsageInAve", "ConsumedEnergy",
    # gres, for clusters too old to carry GPUs in TRES (removed in Slurm 20.11)
    "ReqGRES", "AllocGRES",
    # scheduling and context
    "Priority", "Reservation", "WorkDir", "Comment", "AdminComment", "Layout",
    # where the job's output went, and how it was submitted. Three different
    # boundaries: SubmitLine from 21.08, StdOut/StdErr only from 24.05, Comment
    # (above) on every version. Where present they replace guessing a log path with
    # knowing it, so all three are asked for and logs.py reads whichever arrived.
    "StdOut", "StdErr", "SubmitLine",
]
# fmt: on

# Fields Slurm renamed between releases, canonical name first. The query asks for
# the first spelling the local sacct accepts and the parser reads it back under
# the canonical name, so the rest of the codebase never learns that Slurm 23.02
# renamed queue wait from ``Reserved`` to ``Planned``.
_ALIASES = {
    "Reserved": ("Reserved", "Planned"),
}

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
        "SystemCPU", "StdOut", "StdErr", "SubmitLine", "ReqGRES", "AllocGRES",
        "TRESUsageInAve",
    ]
)
# fmt: on

# Values sacct prints in place of a measurement. Matched case-insensitively:
# ``Unlimited`` and ``UNLIMITED`` are the same claim, and which one appears varies
# by field and by release.
_UNSET = frozenset(["", "unknown", "none", "n/a", "unlimited", "(null)", "partition_limit"])

# Fields whose value a *person* chose, where those same words are ordinary text
# rather than sacct speaking for itself. `Reason` really does read "none" on every
# clean job, `Timelimit` really does read "UNLIMITED", `End` really does read
# "Unknown" -- but nothing stops a job being named `None`, which is what an
# f-string over an unset variable produces, or a partition being called `unknown`.
# Blanking those threw away the only thing identifying the record: `job.name` feeds
# `patterns.group_key`, so such a job stopped being itself and joined the bucket of
# jobs that never had a name at all. A sentinel is a claim about a measurement, and
# these are not measurements.
# fmt: off
_FREE_TEXT = frozenset(
    [
        "jobname", "partition", "account", "user", "group", "qos", "comment",
        "admincomment", "reservation", "wckey", "cluster", "workdir", "submitline",
        "constraints", "stdout", "stderr",
    ]
)
# NodeList is deliberately absent: the scheduler writes it, not a person, so a
# sentinel there is sacct speaking -- and it feeds `nodes.expand_nodelist`, which
# should not be handed "(null)" to parse.
# fmt: on

# Separator asked of sacct instead of the default ``|``, which occurs inside real
# values (see trap 7). ASCII unit separator: legal in ``--delimiter``, and not
# something a shell can hand to ``--constraint`` or ``--job-name``.
SAFE_DELIMITER = "\x1f"

# How long to wait on the accounting database before giving up. A seven-month
# query takes 2.26 s here, so this is not a performance bound -- it is there so an
# unreachable slurmdbd reports a timeout instead of hanging the dashboard forever.
DEFAULT_TIMEOUT = 300.0

# A terminal job is over even if the End timestamp is missing; inferring "still
# running" from a blank End would suppress every diagnosis on such a record. The
# stale-record signal is specifically a NON-terminal state with no end.
# fmt: off
_TERMINAL_STATES = frozenset(
    [
        "COMPLETED", "FAILED", "TIMEOUT", "OUT_OF_MEMORY", "CANCELLED", "NODE_FAIL",
        "BOOT_FAIL", "DEADLINE", "PREEMPTED", "REVOKED", "SPECIAL_EXIT",
    ]
)
# fmt: on

# sacct cuts a state name to its column width and marks the cut with `+`, so
# OUT_OF_MEMORY can arrive as OUT_OF_ME+. Folded back here, at the parse boundary,
# because this list is where sacct's spellings stop being sacct's problem -- the
# same job `_ALIASES` does for a renamed field.
#
# It used to be recognised in exactly one place: `OUT_OF_ME+` sat in
# `_TERMINAL_STATES` above and appeared nowhere else in the codebase, so a record
# carrying it was correctly treated as closed and then mis-handled by everything
# downstream. Verified by running the parser on one:
#
#     OUT_OF_MEMORY  failed=True   findings=['host-oom']  memory-search=True
#     OUT_OF_ME+     failed=False  findings=[]            memory-search=False
#
# -- so the kill counted as neither a failure nor a completion, drew no finding,
# and was invisible to both the memory-bisection detector and the --mem floor in
# `sizing.memory_advice`. Whichever query produced the truncation, one spelling of
# one state cannot mean two things in one codebase.
_TRUNCATED_STATES = {"OUT_OF_ME+": "OUT_OF_MEMORY"}

# sacct writes this into NodeList for a job that never held an allocation -- one
# cancelled while still pending, which is 38 of a real 15,085-job history, all of
# them CANCELLED at elapsed 0. It is a sentence meaning "no nodes", not a node name,
# and it was carried through as though it were one:
#
#     nodes            None assigned  (1 node)
#
# -- a node called "None assigned", and a count of 1 asserted about a job that got
# zero. `expand_nodelist` already returned [] for it, so the node-reliability table
# was never polluted; what leaked was the display and `--json`'s `shape.node_list`,
# where a consumer would read it as a hostname.
#
# Folded here for the reason `_TRUNCATED_STATES` is: this is where sacct's spellings
# stop being sacct's problem. Empty is what the rest of the codebase already means
# by "no nodes" -- `render.job_sections` omits the row on a falsy `node_list`, so
# the contradiction disappears rather than being papered over.
#
# `NNodes` is left alone: for a job cancelled while pending it is what was
# *requested*, which is a real reading and the only one sacct has.
_NO_NODES = "None assigned"


def _canonical_nodelist(value):
    """``None assigned`` -> ``""``. Any real node list passes through untouched."""
    return "" if (value or "").strip() == _NO_NODES else value


def _canonical_state(value):
    """A state with sacct's column truncation undone. Other spellings pass through.

    The ``by <uid>`` suffix sacct appends to CANCELLED is preserved: `Job.state`
    carries it, `Job.base_state` drops it, and both are read.
    """
    if not value:
        return value
    head, separator, tail = value.partition(" ")
    canonical = _TRUNCATED_STATES.get(head)
    if canonical is None:
        return value
    return canonical + separator + tail


class SacctError(RuntimeError):
    pass


def child_env(environ=None):
    """Environment for a Slurm client, with the output-shaping variables pinned.

    ``SLURM_TIME_FORMAT`` is the dangerous one: it rewrites every timestamp sacct
    prints, and a site that exports ``relative`` from ``/etc/profile.d`` turns
    ``2026-04-29T14:55:48`` into ``29 Apr 14:55`` for every user on the cluster.
    Nothing downstream here can read that -- dates stop parsing, and the
    chronological sort silently becomes alphabetical on a month name. So the
    child is told which format to use rather than asked.

    ``SACCT_FORMAT`` and the ``SQUEUE_FORMAT`` pair are dropped for the same
    reason one step further out: they change which columns come back, and this
    code addresses columns by position.
    """
    env = dict(os.environ if environ is None else environ)
    env["SLURM_TIME_FORMAT"] = "standard"
    for name in ("SACCT_FORMAT", "SQUEUE_FORMAT", "SQUEUE_FORMAT2"):
        env.pop(name, None)
    # Keeps numbers and any date the scheduler formats itself in one known
    # locale, rather than the one the user's shell happens to be in.
    env["LC_ALL"] = "C"
    return env


def _timeout():
    """Query timeout, overridable for a site whose accounting is genuinely slow.

    Raises on a value it cannot use rather than falling back to the default.
    This is the package's only environment variable, so it is the whole of that
    surface, and it used to accept anything: ``garbage`` was indistinguishable
    from leaving it unset, and ``0`` -- which a reader naturally writes meaning
    *no timeout* -- silently became 300 seconds with nothing said. A setting that
    does not do what it says and does not complain is worse than one that is not
    offered. The sibling package rejects the same class of input by name
    (``Invalid value for SLURMWATCH_HEADLESS_INTERVAL: 'garbage'``).

    A large value is honoured, not capped: the variable exists precisely so a site
    whose accounting takes an hour can say so, and silently overriding that would
    be the same fault in the other direction. Zero and negative are refused rather
    than read as "wait forever" because unbounded is what this tool already had to
    be fixed for once -- a redirect that hung until killed -- and a query with no
    ceiling under cron is the same failure again.
    """
    raw = os.environ.get("SLURMPAST_TIMEOUT", "").strip()
    if not raw:
        return DEFAULT_TIMEOUT
    try:
        value = float(raw)
    except ValueError:
        raise SacctError(
            "SLURMPAST_TIMEOUT is not a number: %r. Give it a count of seconds, "
            "for example SLURMPAST_TIMEOUT=600, or unset it for the default of %gs."
            % (raw, DEFAULT_TIMEOUT)
        ) from None
    if not math.isfinite(value) or value <= 0:
        raise SacctError(
            "SLURMPAST_TIMEOUT must be a positive number of seconds, not %r. "
            "There is no way to wait forever: a query with no ceiling never "
            "returns under cron. Unset it for the default of %gs." % (raw, DEFAULT_TIMEOUT)
        )
    return value


def _run(args):
    # Before the spawn, not after. `_timeout` raises on a value it cannot use,
    # and reading it once the child is already running left `sacct` orphaned --
    # nothing kills it on that path, because the only cleanup is in the
    # TimeoutExpired branch below. It also costs nothing to refuse a bad setting
    # without starting a query first.
    budget = _timeout()
    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            # Explicit, not the locale's: a job name or work directory holding
            # bytes that are not valid in the ambient encoding used to raise
            # UnicodeDecodeError out of the middle of a query.
            encoding="utf-8",
            errors="replace",
            env=child_env(),
        )
    except OSError as exc:
        raise SacctError(
            "cannot execute %s: %s. Slurm's client commands must be on PATH "
            "(try `module load slurm`), or use --demo to see the tool without a scheduler."
            % (args[0], exc)
        ) from exc
    try:
        out, err = proc.communicate(timeout=budget)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        # `%g`, not `%.0f`: a sub-second budget printed as "within 0s", which
        # reads as this tool having used a zero timeout -- its own bug -- rather
        # than as the 50 ms the caller asked for. The advice below is to raise the
        # variable, and the reader cannot act on it without seeing what it is.
        # Read once, before the spawn, so the message quotes the budget actually
        # used rather than re-deriving it from an environment that may have moved.
        raise SacctError(
            "%s did not answer within %gs — the accounting database may be "
            "unreachable. Narrow the window with -S, or raise SLURMPAST_TIMEOUT."
            % (args[0], budget)
        ) from None
    if proc.returncode != 0:
        message = (err or "").strip() or "%s exited %d" % (args[0], proc.returncode)
        raise SacctError(_explain(message))
    return out


# Failures a user can act on, and what the raw scheduler message does not say.
_HINTS = (
    (
        ("accounting_storage/none", "accounting storage is disabled", "storage is not"),
        "This cluster is not storing job accounting, so there is no history to read. "
        "Ask the administrators about AccountingStorageType.",
    ),
    (
        ("invalid user", "unknown user", "no such user"),
        "Check the -u argument; sacct wants a login name, not a display name.",
    ),
)


def _explain(message):
    lowered = message.lower()
    for markers, hint in _HINTS:
        if any(marker in lowered for marker in markers):
            return "%s\n  %s" % (message, hint)
    return message


def _is_unknown_option(message):
    """True when the scheduler rejected an *option*, not the data asked for.

    Distinguishes "this sacct predates ``--delimiter``" -- worth retrying without
    it -- from "no such job", which retrying cannot fix.
    """
    lowered = str(message).lower()
    return "unrecognized option" in lowered or "invalid option" in lowered


def supported_fields(probe=None, runner=None):
    """Field names this Slurm's sacct will accept, lowercased.

    ``probe`` short-circuits with canned ``--helpformat`` text; ``runner`` says
    *how* to ask when there is none. Both matter to the same caller. This shelled
    out to the module-level ``_run`` unconditionally, so ``Sacct(runner=...)`` --
    a recorded history being replayed, or a remote cluster reached over ssh --
    negotiated its field list against whatever sacct happened to be on the local
    ``PATH`` while every real query went to the injected runner. That is trap 1 at
    the top of this module in its own words: one unknown field makes sacct reject
    the *entire* query, so probing the wrong Slurm is not a degraded answer but no
    answer. ``_mark_open_records`` makes exactly this argument for ``live_job_ids``
    ("a caller that injected one is not silently bypassed here and made to shell
    out for real"); the hole was still open one level up.
    """
    run = runner or _run
    text = probe if probe is not None else run(["sacct", "--helpformat"])
    names = set()
    for token in text.replace("\n", " ").replace(",", " ").split():
        token = token.strip()
        if token:
            names.add(token.lower())
    return names


def resolve_fields(available=None):
    """The field list to ask this sacct for.

    Two transformations, in order. Renamed fields collapse to whichever spelling
    is accepted (``Reserved`` before Slurm 23.02, ``Planned`` after), and fields
    this release has never heard of are dropped -- but only the ones marked
    optional, so a genuinely broken field list still fails loudly instead of
    quietly returning a narrower record than the caller believes it has.

    ``available`` of None means the probe could not be run; then everything is
    requested and sacct is left to complain, which is better than guessing a
    version and dropping a measurement that was there all along.
    """
    out = []
    for name in _FIELDS:
        spellings = _ALIASES.get(name, (name,))
        if available is None:
            out.append(spellings[0])
            continue
        accepted = next((s for s in spellings if s.lower() in available), None)
        if accepted is not None:
            out.append(accepted)
        elif name not in _OPTIONAL:
            out.append(spellings[0])
    return out


def _field_index(fields):
    """Map every canonical field name to its column, following aliases."""
    index = {name.lower(): pos for pos, name in enumerate(fields)}
    for canonical, spellings in _ALIASES.items():
        if canonical.lower() in index:
            continue
        for spelling in spellings:
            if spelling.lower() in index:
                index[canonical.lower()] = index[spelling.lower()]
                break
    return index


def _clean(value, field=None):
    """Strip, and blank the words sacct prints in place of a measurement.

    ``field`` exempts the free-text ones -- see :data:`_FREE_TEXT`. Optional so the
    numeric helpers can go on calling this without naming a field: for them the
    sentinel table is exactly right, since a number is never a name.
    """
    value = (value or "").strip()
    if field is not None and field.lower() in _FREE_TEXT:
        return value
    return "" if value.lower() in _UNSET else value


def _int(value):
    value = _clean(value)
    if not value:
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    # `int(float("inf"))` raises OverflowError, which `except ValueError` does not
    # catch -- so an "inf" or a "1e999" in ReqCPUS, Priority, NNodes or any other
    # counted field came out of the parser as a traceback. Trap 9 at the top of
    # this module is the rule it broke: a wedged accounting database must not wedge
    # the tool.
    return int(number) if math.isfinite(number) else None


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


def _records(text, delimiter, width):
    """Physical lines reassembled into records, because a field may contain one.

    ``--parsable2`` separates *fields* with the delimiter and *records* with a
    newline, and it does not escape a newline occurring inside a value -- while
    several of the fields asked for above legitimately hold one. ``SubmitLine`` is
    the common case: ``sbatch --wrap=$'echo one\\necho two'`` records the whole
    multi-line script, and Slurm has stored SubmitLine since 21.08, so this is
    live on any current site. ``Comment``, ``AdminComment`` and ``WorkDir`` can
    carry one too.

    Splitting on newlines therefore shatters such a record into fragments, and
    every fragment is then read as a fresh row whose JobID is a piece of shell.
    Measured on midway2 (Slurm 23.02) against a real 60-day history: 41 records
    arrived as 123 physical lines and parsed as 56 "jobs", 45 of them fragments
    with ids like ``module use /project/rcc/youzhi/modulefiles``. None of the 45
    had an ``End``, so each counted as an unterminated record and the overview
    reported ``47 unterminated, excluded`` where the true number was 2 -- the one
    line whose whole purpose is to explain a low job count was manufacturing the
    discrepancy it was explaining.

    A physical line therefore opens a new record only when it *looks* like one:
    it carries the delimiter, and the text before the first one is shaped like a
    JobID. Anything else continues the record above it, newline and all -- which
    is also what a reader wants, since ``SubmitLine`` really is multi-line and the
    job screen should show it that way.

    Counting delimiters instead was tried and is wrong in the case that matters.
    ``SubmitLine`` is the *last* field asked for, so the first physical line of a
    shattered record already holds every delimiter a complete one has; a rule that
    closes on the count closes there and silently truncates the script at its
    first newline. The boundary test does not depend on where the multi-line field
    sits.
    """
    # One field means no delimiter to find, so every line is its own record --
    # the boundary test below would treat all of them as continuations.
    if width <= 1 or not delimiter:
        return [line for line in text.split("\n") if line.strip()]
    records = []
    buf = None
    for line in text.split("\n"):
        if _starts_record(line, delimiter):
            if buf is not None:
                records.append(buf)
            buf = line
        elif buf is not None:
            # Blank lines included: one *between* records never reaches here,
            # while one inside a multi-line script is part of the script.
            buf = buf + "\n" + line
        # Otherwise there is no open record to attach it to -- a `--noheader`
        # query that returned a header anyway, or a line of noise before the
        # first record. Dropped here rather than parsed into a phantom job.
    if buf is not None:
        records.append(buf)
    return records


def _starts_record(line, delimiter):
    """Whether a physical line begins a record rather than continuing one."""
    head, found, _ = line.partition(delimiter)
    return bool(found) and _looks_like_job_id(head.strip())


def _looks_like_job_id(value):
    """Whether a first field could be a JobID sacct printed.

    Deliberately loose. Every JobID Slurm emits begins with the numeric job id
    and contains no whitespace -- ``123``, ``123_4``, ``123_[1-20%10]``,
    ``123+0``, and any of those with a ``.batch``/``.extern``/``.0`` step suffix
    -- while nothing else about the spelling is guaranteed across releases, so
    matching an exact shape risks discarding real rows on a site nobody here has
    seen. Those two properties are enough: the shell fragments that used to reach
    this point (``echo "--- $m ---"``, ``2>&1 | tail -1``) fail one or the other.
    """
    return value[:1].isdigit() and not any(ch.isspace() for ch in value)


def parse(text, fields=None, delimiter="|", stats=None):
    """Parse ``sacct --parsable2`` output into Jobs with their steps attached.

    ``delimiter`` must match what the query asked for. When it is the default
    ``|`` a value containing a pipe cannot be told apart from a field boundary,
    so such rows are dropped rather than silently misread -- every column after
    the offending one would be shifted, which on this field list means reporting
    another job's memory and CPU figures as this job's.

    Records are reassembled rather than split blindly (see :func:`_records`), and
    a row still not keyed by something shaped like a JobID is dropped under that
    same rule: one the parser cannot trust is worth less than no row at all.
    """
    fields = list(fields or _FIELDS)
    index = _field_index(fields)
    job_id_at = index.get("jobid")
    if job_id_at is None:
        # Every row is keyed by JobID, so without it there is nothing to build.
        # This used to surface as a bare KeyError from inside the row loop.
        raise SacctError("JobID must be among the requested fields; got: %s" % ", ".join(fields))

    def get(row, name):
        pos = index.get(name.lower())
        if pos is None or pos >= len(row):
            return ""
        return _clean(row[pos], field=name)

    # Optional and mutated in place, so no existing caller's signature or return
    # type changes -- the report's own suggestion for how to carry this without
    # touching `parse`'s contract.
    #
    # One counter, not two. A second for "first field is not a JobID" was written
    # and removed: it cannot fire. `_records` only opens a record on a line whose
    # head is already JobID-shaped, and JobID is field 0 of the query, so the test
    # below re-asks a question that was answered upstream. A counter that always
    # reads 0 is worse than no counter -- it reads as evidence of soundness.
    dropped = {"shifted": 0}
    if stats is not None:
        stats["dropped_rows"] = dropped

    allocations = {}
    order = []
    seen = set()
    pending_steps = {}
    # Which incarnation a step row belongs to, positionally: sacct emits an
    # allocation row and then its steps, so the open allocation for a base id is
    # the one a step attaches to. NOT by matching Submit -- a step's Submit is its
    # own start, not the job's, which the requeued 53432121 shows plainly:
    #
    #   53432121        |2026-08-17T10:08:59|NODE_FAIL
    #   53432121.batch  |2026-08-17T10:20:46|CANCELLED   <- the *step's* start
    #   53432121        |2026-08-17T10:48:35|COMPLETED
    #   53432121.batch  |2026-08-17T10:50:37|COMPLETED
    #
    # Keying steps on Submit therefore matched nothing and silently emptied every
    # job's step list, which reads as `MaxRSS n/a` rather than as an error.
    open_key = {}
    orphan_steps = {}

    for line in _records(text, delimiter, len(fields)):
        row = line.split(delimiter)
        # A row with more fields than were asked for has a delimiter inside a
        # value, so every column after it is shifted and reading it would report
        # another job's memory as this one's. Dropping is right and is what this
        # module has always documented -- what was missing is saying so. Reachable
        # in practice only on the `|` fallback, which is a cluster whose sacct
        # predates `--delimiter` (17.11): exactly the kind of site nobody here can
        # see, and exactly where a user should be told rows went missing rather
        # than left to wonder why a job is absent.
        if len(row) > len(fields):
            dropped["shifted"] += 1
            continue
        raw_id = (row[job_id_at] if job_id_at < len(row) else "").strip()
        if not raw_id or raw_id.lower() == "jobid":
            # A header line or a blank id: not a row, and not a loss.
            continue
        if not _looks_like_job_id(raw_id):
            # Unreachable through `_records`, which already made this test; kept
            # as the guard for a caller passing `parse` hand-built text, and
            # deliberately not counted -- see the note above.
            continue

        exit_code, signal = _parse_exit(get(row, "ExitCode"))

        if "." in raw_id:
            base = _base_job_id(raw_id)
            # A step ahead of its allocation row keeps the old behaviour: held
            # aside and given to that id's first incarnation below.
            bucket = (
                pending_steps.setdefault(open_key[base], [])
                if base in open_key
                else (orphan_steps.setdefault(base, []))
            )
            bucket.append(
                Step(
                    step_id=raw_id,
                    name=get(row, "JobName"),
                    state=_canonical_state(get(row, "State")),
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
                    node_list=_canonical_nodelist(get(row, "NodeList")),
                    tres_in_tot=get(row, "TRESUsageInTot"),
                    tres_out_tot=get(row, "TRESUsageOutTot"),
                    tres_in_max=get(row, "TRESUsageInMax"),
                    tres_in_max_node=get(row, "TRESUsageInMaxNode"),
                    tres_in_ave=get(row, "TRESUsageInAve"),
                    consumed_energy=_int(get(row, "ConsumedEnergy")),
                )
            )
            continue

        req_mem = get(row, "ReqMem")
        end_raw = get(row, "End")
        state = _canonical_state(get(row, "State"))
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
            #
            # `parse_mem_limit`, not `parse_bytes`: this is the one field where a
            # unit-less number means MiB rather than bytes, and the two cannot be
            # merged because the byte counters above (MaxPages especially, which
            # this cluster emits bare) would then be read a million times too big.
            req_mem_bytes=(parse_mem_limit(req_mem) or None),
            req_mem_scope=mem_scope(req_mem),
            req_cpus=_int(get(row, "ReqCPUS")),
            req_nodes=_int(get(row, "ReqNodes")),
            req_tres=get(row, "ReqTRES"),
            req_gres=get(row, "ReqGRES"),
            alloc_gres=get(row, "AllocGRES"),
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
            node_list=_canonical_nodelist(get(row, "NodeList")),
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
            std_out=get(row, "StdOut"),
            std_err=get(row, "StdErr"),
            submit_line=get(row, "SubmitLine"),
            # A *state* is required, not merely a missing End. Without the
            # `bool(state)` guard an empty state is "not terminal", so any row the
            # parser could not make sense of -- no state, no name, no fields --
            # was reported to the reader as an unterminated job. Measured on the
            # reporting cluster: "137 unterminated, excluded" against 0 running
            # and 0 records lacking an End, every one of the 137 a shell fragment
            # with `state == ""`.
            #
            # PENDING is why the test is emptiness rather than the reporter's
            # suggested `elapsed is not None and end is None`: a queued job has
            # neither an elapsed nor an end and is still genuinely open, and the
            # throttled-array meta-record depends on being counted here.
            open_ended=bool(state) and (not end_raw) and state.split()[0] not in _TERMINAL_STATES,
        )
        key = (raw_id, get(row, "Submit"))
        allocations[key] = job
        open_key[raw_id] = key
        if key not in seen:
            seen.add(key)
            order.append(key)
            # The first incarnation of an id inherits any steps that arrived
            # before it.
            early = orphan_steps.pop(raw_id, None)
            if early:
                pending_steps.setdefault(key, [])[:0] = early

    return _fold_incarnations(
        [allocations[key]._replace(steps=tuple(pending_steps.get(key, ()))) for key in order]
    )


def _same_job(candidate, newest):
    """Whether two rows sharing a job id are one job requeued, or two jobs.

    ``sacct -D -j <id>`` carries no window, so on a cluster whose slurmdbd has
    outlived a job-id counter reset it answers with every job that has *ever*
    held the id. Measured on Mercury (Slurm 25.11.3), where all 40 ids sampled
    from three recent days came back with a second row::

        509531|mercury|aranda   |standard|dsa-3-20                          |2019-03-03
        509531|mercury|cmbrennan|highmem |did_bigquery_priority_general_2026|2026-08-19

    Folding those together reported "requeued 1x" on every per-job view on that
    cluster, and the incarnation it attributed to the reader was a stranger's
    job from seven years earlier. Passing ``-S`` does not help: the per-job path
    has no window to pass.

    The discriminator is identity, not time. A requeue cannot change whose job
    it is -- Slurm re-queues the same submission, so uid, user and cluster all
    survive it -- whereas a recycled id is a different submission by whoever
    happened to draw the number next. A gap threshold was the obvious
    alternative and is worse: the normal requeue shape *is* "previous attempt
    ended before this one was submitted", so the sign carries no signal, and any
    cutoff would eventually reject a job that sat requeued and held.

    Conservative on missing data: sacct leaves these blank often enough that a
    blank must not split a genuine requeue, so an absent field defers to the
    next one and a group with nothing to compare on folds as it did before.
    """
    if candidate.cluster and newest.cluster and candidate.cluster != newest.cluster:
        return False
    for field in ("uid", "user"):
        mine, theirs = getattr(candidate, field), getattr(newest, field)
        if mine and theirs:
            return mine == theirs
    return True


def _fold_incarnations(jobs):
    """Collapse a requeued job's incarnations onto the latest one.

    ``sacct -D`` reports every incarnation of a job id: a job requeued on
    ``NODE_FAIL``, on preemption, or by ``scontrol requeue`` comes back as two or
    more rows sharing the id and differing in ``Submit``. Without ``-D`` Slurm
    shows only the last of them, which is why this tool used to answer *"what
    happened to my job?"* with the final attempt and no sign there had been
    others. Measured on Midway3, job 53432121::

        53432121|NODE_FAIL|2026-08-17T10:08:59|...|00:27:49
        53432121|COMPLETED|2026-08-17T10:48:35|...|03:41:52

    -- 27m49s of real allocation on a failed node, invisible.

    One ``Job`` per id still comes out, so nothing downstream starts counting a
    requeued job twice: the newest incarnation is the job, and the ones before it
    hang off it in ``earlier``, oldest first. That keeps job counts, rankings and
    the single-job view exactly as they were for the overwhelming majority of jobs
    -- 773 rows in 7 cluster-days here are requeues, out of 922,534 -- while
    making the ones that were requeued able to say so.

    Ordering is by ``Submit``, because that is the field Slurm actually advances
    on requeue and the only one guaranteed present: a requeued incarnation may
    never have started, so ``Start`` can be empty on either side. Rows with no
    ``Submit`` at all keep the order sacct emitted them in, which is chronological.
    """
    by_id = {}
    for job in jobs:
        by_id.setdefault(job.job_id, []).append(job)
    if len(by_id) == len(jobs):
        # The ordinary case, and worth not rebuilding the list for: no id occurs
        # twice, so nothing was requeued and every Job is already its own latest.
        return jobs

    folded = {}
    for job_id, group in by_id.items():
        if len(group) == 1:
            folded[job_id] = group[0]
            continue
        # `or ""` so a missing Submit sorts first rather than raising against a
        # string, and the index keeps the sort stable on ties.
        ordered = [j for _, _, j in sorted((j.submit or "", i, j) for i, j in enumerate(group))]
        newest = ordered[-1]
        # Only the trailing run that is still the *same job* is this job's
        # history. Walking back and stopping at the first stranger, rather than
        # filtering the whole group, is what makes "the newest incarnation is
        # the job" hold: anything behind a stranger belongs to the stranger.
        kept = []
        for earlier_run in reversed(ordered[:-1]):
            if not _same_job(earlier_run, newest):
                break
            kept.append(earlier_run)
        kept.reverse()
        folded[job_id] = newest._replace(earlier=tuple(kept))

    out, emitted = [], set()
    for job in jobs:
        if job.job_id in emitted:
            continue
        emitted.add(job.job_id)
        out.append(folded[job.job_id])
    return out


# An array that has not been expanded yet: `49046820_[1-20%10]`, or `_[0-4]` without
# a throttle. Anchored, and the brackets are required -- `49046820_4` is a real
# element and sacct takes it.
_UNEXPANDED_ARRAY = re.compile(r"^(\d+)_\[")


def current_user() -> str:
    """Who to ask sacct about, or raise :class:`SacctError` saying why not.

    `getpass.getuser()` reads ``$LOGNAME``/``$USER``/``$LNAME``/``$USERNAME`` and
    then `pwd`, and raises ``OSError`` when all of them fail. That is reachable
    with a documented, unmodified Slurm flag: ``sbatch --export=NONE`` clears the
    environment, and some sites set ``SBATCH_EXPORT=NONE`` cluster-wide. On a
    cluster whose compute nodes carry no passwd entry for the user -- reported
    from one where ``id -un`` answers *"cannot find name for user ID 940740146"*
    -- the `pwd` fallback fails too, and the whole class of failure is invisible
    on the login node where these tools are written.

    Two fallbacks past that, in order of how much they are worth trusting:

    * ``SLURM_JOB_USER``, which Slurm sets and which survives ``--export=NONE``
      because it re-exports its own ``SLURM_*`` variables.
    * the bare numeric uid, which ``sacct -u`` accepts. Less readable, and it is
      the right answer rather than a guess -- it is the identity the accounting
      database keyed the rows on.

    `SacctError` rather than `OSError` at the end, so the existing handler in
    `cli.main` prints one line. Broadening that `except` instead would stop the
    traceback and still leave the tool unable to say whose history to read, when
    the uid is sitting there and is a usable argument.
    """
    try:
        return getpass.getuser()
    except (OSError, KeyError):
        pass
    from_slurm = os.environ.get("SLURM_JOB_USER", "").strip()
    if from_slurm:
        return from_slurm
    try:
        return str(os.getuid())
    except AttributeError:  # pragma: no cover - not POSIX
        raise SacctError(
            "cannot tell which user to query: no USER or LOGNAME in the "
            "environment, no passwd entry, and no SLURM_JOB_USER. Pass -u <name> "
            "explicitly, or --all-users."
        ) from None


def controller_log_paths(job_id, runner=None):
    """``(StdOut, StdErr)`` from ``scontrol show job``, or ``("", "")``.

    The authoritative answer to "where did this job's output go", and available on
    every Slurm -- unlike ``sacct``'s ``StdOut``/``StdErr``, which arrived in 24.05
    and are simply refused before it::

        $ sacct -o StdErr        sacct: error: Invalid field requested: "StdErr"
        $ scontrol show job N    StdErr=/scratch/.../realname-A.err

    Only for as long as the controller remembers the job -- ``MinJobAge``, often
    a couple of minutes -- which is exactly the window a post-mortem run right
    after a job dies falls into. Past it this returns nothing and the existing
    ladder (SubmitLine, --comment, conventional names, timing) takes over
    unchanged.

    Worth asking because the alternative is a guess that can be wrong with
    confidence: a decoy file with a matching mtime was attached to a job on a
    GPU-less partition and produced a *critical* "GPU ran out of memory". The
    heuristic is a reasonable answer to a real constraint; it is not the best
    answer available when the controller is still holding the real one.

    Never raises. No scontrol, no such job, a controller that will not answer --
    all of them mean "nothing recorded", which is the state this already handles.
    """
    run = runner or _run
    try:
        text = run(["scontrol", "show", "job", str(job_id)])
    except (SacctError, OSError):
        return "", ""
    found = {}
    for match in re.finditer(r"\b(StdOut|StdErr)=(\S+)", text or ""):
        found.setdefault(match.group(1), match.group(2))
    return found.get("StdOut", ""), found.get("StdErr", "")


def queryable_job_id(value: str) -> str:
    """A job id ``sacct -j`` will actually accept.

    sacct prints an unexpanded array as ``49046820_[1-20%10]`` -- in its own JobID
    column under ``--parsable2``, and squeue prints the same, which is where anyone
    copies it from -- and then refuses that exact string:

        $ sacct -j '49046820_[1-20%10]' -X -o JobID
        sacct: fatal: Bad job array element specified: 49046820
        $ sacct -j 49046820 -X -o JobID
        49046820_[1-20%10]

    So the tool handed straight through what sacct had just printed and got a fatal
    error on it. Verified against the live scheduler: it is the brackets, not the
    ``%throttle`` -- ``_[1-20]`` fails the same way -- and everything else passes,
    including ``.batch`` and ``.extern`` step ids and a plain ``_4`` element.

    Reduced to the master, which is the only spelling sacct answers. For a pending
    array that returns the one unexpanded row the caller asked about; the bracketed
    form does not survive expansion, so there is no completed array to over-fetch.
    """
    match = _UNEXPANDED_ARRAY.match(value)
    return match.group(1) if match else value


class Sacct:
    """Queries sacct, adapting the request to what the local Slurm accepts."""

    def __init__(self, runner=None, probe=None, delimiter=None):
        self._run = runner or _run
        self._probe = probe
        self._supported = None
        self._delimiter = delimiter
        # Filled by the last query. Read by `--json` so a cluster whose sacct
        # emits rows this parser refuses says so, instead of the rows simply not
        # being there.
        self.stats: dict = {}

    @property
    def fields(self):
        if self._supported is None:
            try:
                available = supported_fields(self._probe, runner=self._run)
            except SacctError:
                available = None
            self._supported = resolve_fields(available)
        return self._supported

    def _query(self, extra):
        fields = self.fields
        # `-D` because without it sacct reports only a job's *latest* incarnation,
        # so a job requeued on NODE_FAIL, on preemption, or by `scontrol requeue`
        # loses every attempt but the last -- including the time those attempts
        # really consumed. `_fold_incarnations` puts the id back to one Job, so
        # this widens what is known without changing what is counted. Present in
        # sacct far longer than `--delimiter`, which this negotiates against
        # anyway, so it needs no probe of its own.
        base = ["sacct", "-D", "--parsable2", "--noheader", "--format=" + ",".join(fields)]
        if self._delimiter is None:
            # Negotiated once per instance, on the first real query rather than
            # by a second probe. ``--delimiter`` has been in sacct since at least
            # 17.11, so the fallback is for a scheduler older than that -- and an
            # unknown *option* is distinguishable from a bad job id, so retrying
            # cannot mask a real failure.
            try:
                text = self._run(base + ["--delimiter=" + SAFE_DELIMITER] + list(extra))
            except SacctError as exc:
                if not _is_unknown_option(exc):
                    raise
                self._delimiter = "|"
            else:
                self._delimiter = SAFE_DELIMITER
                return parse(text, fields=fields, delimiter=SAFE_DELIMITER, stats=self.stats)
        args = base + list(extra)
        if self._delimiter != "|":
            args = base + ["--delimiter=" + self._delimiter] + list(extra)
        return parse(self._run(args), fields=fields, delimiter=self._delimiter, stats=self.stats)

    def jobs(self, job_ids):
        ids = [str(j) for j in job_ids if str(j).strip()]
        if not ids:
            return []
        return self._query(["-j", ",".join(queryable_job_id(i) for i in ids)])

    def history(
        self, user=None, since=None, until=None, states=None, partition=None, all_users=False
    ):
        """History for one user, a comma-separated list of them, or the cluster.

        ``-u`` takes a list, so ``user="alice,bob"`` is handed straight through.
        ``all_users=True`` spans the cluster; ``user=""`` is the older spelling of
        the same request and still honoured. Whether you can actually *see* another
        account's jobs is the site's call, not ours: with ``PrivateData=jobs`` in
        slurm.conf sacct returns an empty set rather than an error, which is why
        the CLI names the user it asked about when it reports nothing found.
        """
        extra = []
        if all_users or user == "":
            extra += ["--allusers"]
        elif user:
            extra += ["-u", user]
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


def live_job_ids(runner=None, user=None, all_users=False):
    """Job IDs squeue currently reports for the account being reconciled.

    Distinguishes a genuinely running job from a stale accounting record: if
    sacct says RUNNING and squeue has never heard of it, the record is dead.
    Returns None (not an empty set) when squeue cannot be reached, so callers
    can refrain from guessing.

    ``--me`` arrived in Slurm 20.02, so the fallback spells the same request out
    as ``-u <user>``. It used to fall back to an unfiltered ``squeue``, which on a
    busy cluster is tens of thousands of rows to answer a question about one
    user's jobs.

    ``--me`` is only asked when the account being reconciled *is* mine. It used to
    be tried first unconditionally, so on every Slurm since 20.02 -- which is to
    say all of them -- ``-u alice`` checked alice's RUNNING records against *my*
    queue and the ``user`` argument was silently dead. Only the fallback branch was
    covered by a test, which is why it read as working.
    """
    run = runner or _run
    me = current_user()
    who = user or me
    attempts = []
    if all_users or user == "":
        # Deliberately unfiltered, unlike the accident above: the caller asked
        # about every account, so a cluster-wide queue is the honest answer.
        attempts.append(["squeue", "--noheader", "--format=%i"])
    else:
        if who == me:
            attempts.append(["squeue", "--noheader", "--me", "--format=%i"])
        attempts.append(["squeue", "--noheader", "-u", who, "--format=%i"])
    for args in attempts:
        try:
            out = run(args)
        except SacctError:
            continue
        return _expand_job_ids(out)
    return None


# The `%N` simultaneous-task throttle Slurm writes back into a pending array's id:
# `--array=0-9%2` comes out of squeue as `900_[0-9%2]`. Stripped before expansion --
# see _expand_job_ids.
_ARRAY_THROTTLE = re.compile(r"%\d+")


def _expand_job_ids(text):
    """squeue's ``%i`` column as a set of individual job ids.

    ``%i`` does not print one id per pending array task -- it prints the *range*:
    ``900_[5-10]``, the same bracketed grammar Slurm uses for hostlists and
    :func:`slurmpast.nodes.expand_nodelist` already parses (differential-tested
    against ``scontrol show hostnames``). A running element appears as its own
    ``900_5``, so a queue holding both spellings at once is the ordinary case.

    Without expansion the membership test in ``cli._mark_open_records`` misses
    every pending element, and since round five *uses* that answer rather than
    discarding it, the miss became an assertion: a task sitting in the queue right
    now was reported as "squeue has never heard of it, so the job is long gone and
    the record was never closed". Inventing a claim about a job that is plainly
    queued is the one thing this codebase's rules are written to prevent, and it
    was one parse away.

    The ``%N`` array throttle is dropped before expanding. Slurm writes
    ``--array=0-9%2`` back *inside* the brackets -- ``900_[0-9%2]`` -- and left in
    place it defeats the expansion silently rather than loudly: ``0-9%2`` is not a
    numeric range, so the range parser keeps it verbatim as one unmatched name and
    every element of a throttled array goes on being called dead.

    Anything that is not a bracketed range passes through unchanged, so a plain
    id, a heterogeneous ``500+1`` and an unfamiliar spelling all still match
    themselves. The raw token is kept either way, so nothing is lost by failing to
    understand a spelling -- the id simply matches only itself, which is what the
    whole set did before.
    """
    from .nodes import expand_nodelist

    ids = set()
    for line in text.splitlines():
        token = line.strip()
        if not token:
            continue
        ids.add(token)
        if "[" in token:
            ids.update(expand_nodelist(_ARRAY_THROTTLE.sub("", token)))
    return ids
