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

import functools
import getpass
import itertools
import math
import os
import re
import subprocess
import threading
from typing import Any

from . import cache
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

#: First characters any member of `_UNSET` can begin with, either case. A value
#: starting with anything else cannot be a sentinel, which answers the question
#: without allocating a lowered copy of the string -- see `get` inside `parse`,
#: where the leading-digit test already does the same job for the numeric fields
#: and left 2.2M `str.lower()` calls on the text ones.
_UNSET_LEAD = frozenset("unpUNP(")

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

# --- Splitting one window query across several sacct processes -------------
#
# A window query costs almost nothing in the database and almost everything in
# `sacct` itself formatting the rows. Measured on midway3 (Slurm 20.11.8) over
# one user's last seven days -- 29,624 jobs, 89,163 rows, the 80 fields this
# module asks for:
#
#     --format=JobID                        5.82 s      <- the database read
#     --format=<40 fields>                 11.14 s
#     --format=<80 fields>                 14.49 s      <- what slurmpast asked
#     --format=<80 fields> -X               1.52 s      <- allocations only
#
# So ~6 s is the fetch and ~9 s is one process laying out 7.1 million cells,
# single-threaded, on a login node with dozens of idle cores. The fix is to run
# several sacct processes at once. Splitting the *window* does not work: sacct
# filters step rows by the window too, so a job that spans a boundary comes back
# with only the steps that ran inside each half, and its MaxRSS is then read off
# a fragment (verified: 27 of 31,336 job/chunk pairs came back short).
#
# Splitting by job id does work, because `-j` returns a job's whole record. So
# the ids are fetched first with `-X --format=JobID` -- the cheap query above,
# 0.41 s for 29,627 ids and 0.07 s for 1,571 -- and the full read is partitioned
# across them. Every other filter is passed through to both halves unchanged, so
# what comes back is what the single query would have returned:
#
#     ids in the single query but not the partitioned one     0
#     ids in the partitioned query but not the single one     1   (a job that
#                                                                  started between
#                                                                  the two)
#
#     probe + 8 parallel `-j` reads          3.15 s   (vs 14.49 s)
#
#: Below this, the window query is already quick and one extra round trip is the
#: larger cost. 1,571 jobs -- a day here -- reads in 0.90 s undivided.
PARALLEL_MIN_JOBS = 400

#: Processes at once. Eight saturates the win (four gave 8.3 s where eight gave
#: 4.8 s on the window-split experiment) without turning a login node into a
#: fork bomb, and slurmdbd serialises enough that more buys little.
PARALLEL_MAX_WORKERS = 8

#: Ids per `-j`, and therefore MORE chunks than there are workers -- deliberately.
#: Parsing is Python and holds the GIL, so if every chunk returns at the same
#: moment the eight parses queue up behind each other and none of them overlaps a
#: query. Smaller chunks stagger the returns, so a thread is parsing chunk 9 while
#: another is still waiting on chunk 17. Measured over the same 22,359-job window,
#: end to end including the id listing:
#:
#:      8 chunks   5.46 s        48 chunks   4.27 s
#:     16 chunks   4.98 s        64 chunks   4.56 s
#:     32 chunks   4.94 s       128 chunks   4.98 s
#:
#: -- the far side is process-spawn overhead, so this sits at the bottom of the
#: curve rather than as low as it will go. It also keeps the id list, which is a
#: SINGLE argv entry, at a few KiB: Linux caps one entry at MAX_ARG_STRLEN
#: (128 KiB), which a history of this size would otherwise reach.
PARALLEL_IDS_PER_QUERY = 500

#: Never split so finely that the per-process overhead dominates. A window just
#: over PARALLEL_MIN_JOBS is three chunks, not thirty.
PARALLEL_MIN_IDS_PER_QUERY = 150

#: Budget for the LIVE (`sstat`) query specifically, which is an enrichment and
#: not the data. `DEFAULT_TIMEOUT` is for the accounting database; `sstat` is a
#: different cost with a different shape -- it contacts each job's `slurmstepd`,
#: so it scales with how many jobs the reader has RUNNING, not with the window.
#:
#: `merge_live_metrics` already names the number it was designed around: "the
#: 18-second call this exists to avoid". Measured on midway3 with 60 running
#: array tasks, the one batched call this module makes took **119.76s** for 2,160
#: rows -- 6.6x the cost the module calls out as unacceptable -- and nothing
#: bounded it but the 300s accounting budget. `slurmpast --plain` therefore sat
#: for two minutes before printing anything.
#:
#: A timeout here lands on the fallback `read_live_metrics` already documents as
#: "the correct answer and not a degradation": the field reads unmeasured. Waiting
#: two minutes to avoid saying "unmeasured" is the wrong trade.
#:
#: No new environment variable -- `SLURMPAST_TIMEOUT` is documented as "the
#: package's only environment variable". It is respected as a CEILING instead: a
#: site that lowers it lowers this too, while raising it does not extend an
#: enrichment, because that is not what the reader raised it for.
LIVE_METRICS_TIMEOUT_S = 15.0

#: The cap in force for the CURRENT thread's query, or unset for the full budget.
#: Thread-local because the dashboard runs its load in a Textual thread worker
#: while the main thread is live, so a module-level value would leak one view's
#: cap into another's.
_query_cap = threading.local()

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
    # `_timeout()` first either way, so a bad SLURMPAST_TIMEOUT is still refused
    # before any spawn (see the comment below), and so a cap can only ever SHORTEN
    # the wait -- never extend a budget the reader deliberately lowered.
    #
    # The cap arrives through `_query_cap`, NOT through this signature, and that is
    # deliberate. `site.py` does `from .sacct import _run`, and seven tests replace
    # `slurmpast.sacct._run` with a ONE-ARGUMENT double; adding a parameter here
    # broke `test_cli.py`'s `lambda args: ...` under mypy and would have handed those
    # doubles a keyword they cannot take. A caller-set cap keeps this funnel's
    # signature, and every existing double, exactly as they were.
    cap = getattr(_query_cap, "value", None)
    budget = _timeout() if cap is None else min(_timeout(), cap)
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
        # Two causes, and the advice used to name only the one that is wrong on a
        # compute node. Measured there: `sacct` said `Invalid user id: youzhi`
        # with no `-u` passed and `youzhi` being the login name -- the node simply
        # cannot resolve it (`getent passwd <uid>` fails, so `pwd.getpwuid` does
        # too), which is the ordinary state of a diskless compute node and not a
        # typo. Sending the reader to check an argument they did not give is a
        # dead end; the second sentence names the cause they can act on.
        "Check the -u argument if you passed one; sacct wants a login name, not a "
        "display name.\n  If you did not, this node may be unable to resolve your "
        "name at all \u2014 compute nodes often have no passwd entry for the user. "
        "Try `getent passwd $(id -u)`, and run this from a login node, or pass "
        "-u <login name> explicitly.",
    ),
    (
        ("invalid time specification",),
        # sacct's own text, passed straight through, reads
        # `Invalid time specification (pos=4): now-6months` -- a byte offset into
        # a string the user did not type in that form (`-6months` is rewritten to
        # `now-6months` by `normalize_time_spec`), and no word about which
        # spellings work. `-S` is this tool's most-used option, so that was the
        # cryptic message on the most-travelled failure path.
        #
        # The forms below are not guessed: they are the set this repo already
        # verified and recorded, re-checked here against Slurm 20.11.8 on the
        # reporting cluster. Months and years really are refused -- `now-6months`,
        # `now-2months` and `now-1year` all come back `Invalid time
        # specification` -- while every day and week spec returns rows. That is
        # why the advice names weeks for a long window instead of months.
        "sacct takes days and weeks but NOT months or years: `now-1day`, "
        "`now-7days`, `now-30days`, `now-12weeks`, `now-52weeks` (about a year) "
        "all work, and `now-6months` is rejected.\n  An absolute "
        "`YYYY-MM-DD` or `YYYY-MM-DDTHH:MM:SS` works too, and a bare "
        "`-7days` is accepted here and rewritten to `now-7days` for you.",
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


#: How many distinct strings one parse may share.  See `get` inside `parse`.
_SHARED_STRING_CAP = 100_000


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


#: Any whitespace character, for :func:`_looks_like_job_id`.
_WHITESPACE_RE = re.compile(r"\s")


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
    # One C-level scan, not a Python generator per character. This is called
    # once per output line -- 305,931 times for a 30-day window -- and the
    # `any(ch.isspace() for ch in value)` form spent 1.06s of a profiled parse
    # walking short strings one character at a time. `\s` is the same predicate
    # `str.isspace` applies, so the loose contract above is unchanged.
    return value[:1].isdigit() and _WHITESPACE_RE.search(value) is None


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

    # One object per distinct value, for the whole parse.
    #
    # A history is fully materialised, and the records are mostly repeated text:
    # over 13,321 real jobs, `uid` and `account` each had **one** distinct value
    # held as 13,321 separate string objects, `state` seven, `flags` three,
    # `work_dir` 35, `req_tres` 205. Measured across every string field of those
    # jobs: 19.4 MB of payload, of which ~10 MB in the top fourteen fields alone
    # was exact duplication -- before the 30,339 step rows, which repeat the same
    # states and node names again.
    #
    # `sys.intern` would do it in one call and is the wrong tool: its table is
    # global and never freed, so a long-lived process (the TUI reloading, or a
    # library caller) would accumulate every job id and timestamp it ever saw.
    # A dict scoped to this parse is dropped when the parse ends, and the strings
    # it shared stay shared for exactly as long as the records that hold them.
    #
    # Capped, because two fields are genuinely unique per row (`job_id`, and the
    # timestamps to a lesser degree) and caching those buys nothing but growth.
    # The cap is generous: a cluster has tens of partitions, a handful of states
    # and a few hundred TRES shapes, so the fields that benefit never approach it.
    shared: dict = {}

    # Each field name resolved ONCE, not once per access.
    #
    # `get` is the hot path of the whole parser: **1,975,028 calls** for a
    # 30-day window on one user, and it lowercased its `name` argument on every
    # one of them -- then handed the same string to `_clean`, which lowercased
    # it again to test `_FREE_TEXT`. The names are a fixed set of 85
    # compile-time constants, so all of that was recomputing a constant:
    # profiled at **7,095,157 `str.lower()` calls**, 2.53s in `get` and 1.77s
    # in `_clean` over 2,263,954 calls.
    #
    # `plan` maps the name to `(column, is_free_text)`. Filled lazily rather
    # than from `fields`, because callers pass literal names that a short
    # `--format` may not contain, and `index.get` returning None for those is
    # the existing contract.
    plan: dict = {}

    def get(row, name):
        entry = plan.get(name)
        if entry is None:
            low = name.lower()
            entry = plan[name] = (index.get(low), low in _FREE_TEXT)
        pos, free_text = entry
        if pos is None or pos >= len(row):
            return ""
        # `_clean` inlined, not reimplemented: strip, exempt the free-text
        # fields, blank a sentinel. Kept as a function for its other callers
        # (`_int`, `_seconds`, the sstat parser), which are not hot.
        value = row[pos].strip()
        if not value:
            return ""
        # The first character rules the sentinels out without lowering the string.
        # A leading digit did that for the numeric fields -- a large share of 85
        # sacct fields are numbers (`ElapsedRaw`, `ReqCPUS`, `Priority`, `UID`,
        # byte counts) -- and left every text one still being lowered: 2.2M
        # `str.lower()` calls over a seven-day window, for job names, partitions,
        # node lists and states that cannot be a sentinel because no sentinel
        # begins with their first letter. `_UNSET_LEAD` is the whole test now, and
        # it is a superset check, so `value.lower() in _UNSET` still decides.
        if not free_text and value[0] in _UNSET_LEAD and value.lower() in _UNSET:
            return ""
        seen = shared.get(value)
        if seen is not None:
            return seen
        if len(shared) < _SHARED_STRING_CAP:
            shared[value] = value
        return value

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
        # Both halves. `DerivedExitCode` is `code:signal` and the signal half is
        # where a killed step shows up -- slurmdbd rolls one up as `0:9`, code zero.
        derived_code, derived_signal = _parse_exit(get(row, "DerivedExitCode"))

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
            derived_signal=derived_signal,
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


def _in_parallel(work, workers):
    """Run ``work`` across at most ``workers`` daemon threads; results in order.

    ``concurrent.futures.ThreadPoolExecutor`` is the obvious tool and is the
    wrong one here, for one reason: its threads are non-daemon and joined at
    interpreter exit, so a Ctrl-C during the query would wait for every ``sacct``
    still in flight -- up to the 300 s accounting budget. :func:`main` treats
    Ctrl-C as an ordinary way to stop this tool, and says why: "its query timeout
    is 300 s by design (an accounting database can genuinely take minutes) ...
    Five minutes of silence is exactly when a user reaches for Ctrl-C." A query
    that cannot be interrupted takes that away, and would take it away precisely
    when the reader most wants it.

    ``Thread.join`` IS interruptible, and a daemon thread does not hold up
    interpreter exit, so a Ctrl-C here leaves the same orphaned ``sacct`` a
    single-process query always did -- several of them rather than one.

    The first exception raised by any item is re-raised here, and the remaining
    items are not started.
    """
    results: list = [None] * len(work)
    errors: list[BaseException] = []
    turn = itertools.count()  # `next` on a count is atomic, so this needs no lock

    def run():
        for at in turn:
            if at >= len(work) or errors:
                return
            try:
                results[at] = work[at]()
            except BaseException as exc:  # re-raised in the caller
                errors.append(exc)
                return

    threads = [
        threading.Thread(target=run, daemon=True, name="slurmpast-sacct-%d" % n)
        for n in range(min(workers, len(work)))
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    if errors:
        raise errors[0]
    return results


class Sacct:
    """Queries sacct, adapting the request to what the local Slurm accepts."""

    def __init__(self, runner=None, probe=None, delimiter=None, parallel=True, cache=True):
        self._run = runner or _run
        self._probe = probe
        self._supported = None
        self._delimiter = delimiter
        # Whether a finished job may be read back from disk instead of from
        # sacct -- see :mod:`slurmpast.cache`. Off for a caller with an injected
        # runner, set below: those records did not come from this cluster's
        # accounting database and must not be filed as though they had.
        self._cache = cache
        self._store_cache: Any = None
        # Whether a window query may be split across several sacct processes --
        # see PARALLEL_MIN_JOBS. Off makes `history` issue the one query it always
        # did, which is what the parser tests want and what a caller measuring the
        # scheduler rather than this tool wants.
        self._parallel = parallel
        # Filled by the last query. Read by `--json` so a cluster whose sacct
        # emits rows this parser refuses says so, instead of the rows simply not
        # being there.
        self.stats: dict = {}

    def _store(self):
        """The record cache, or None when it is off for this instance.

        Never for an injected ``runner``: a test double or a library caller
        feeding canned text is not this cluster's accounting database, and a
        record from one filed under the other is the one way this could hand back
        a job that does not exist. Never when the reader has switched it off.
        """
        if not self._cache or self._run is not _run or not cache.enabled():
            return None
        if self._store_cache is None:
            fields = self.fields
            # Scoped by cluster and account, so two clusters' records cannot meet
            # -- `Cluster` is in the field list precisely because a record does
            # not mean the same thing on another one.
            self._store_cache = cache.Store(("sacct", current_user()), fields)
        return self._store_cache

    @property
    def fields(self):
        if self._supported is None:
            try:
                available = supported_fields(self._probe, runner=self._run)
            except SacctError:
                available = None
            self._supported = resolve_fields(available)
        return self._supported

    def _fetch(self, extra, fields):
        """Raw sacct output for one query, negotiating ``--delimiter`` once.

        Split out of :meth:`_query` so the id listing and the partitioned reads go
        through the same option handling -- and so the delimiter is settled by the
        listing, before any thread starts, rather than negotiated concurrently by
        several of them.
        """
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
                return text
        args = base + list(extra)
        if self._delimiter != "|":
            args = base + ["--delimiter=" + self._delimiter] + list(extra)
        return self._run(args)

    def _query(self, extra):
        fields = self.fields
        text = self._fetch(extra, fields)
        return parse(text, fields=fields, delimiter=self._delimiter, stats=self.stats)

    def _window_listing(self, extra):
        """``[(job id, fingerprint)]`` for the window, in sacct's own order.

        ``-X`` drops the step rows, which is what makes this cheap: the same
        seven-day window costs 0.45 s here against 14.49 s for the full read.

        The fingerprint is every ``(State, End)`` sacct currently reports for that
        id, in order -- ``-D`` lists one row per incarnation, so a job requeued
        after it finished has a different one. It costs two more columns on the
        cheapest query this makes, and it is what lets :mod:`slurmpast.cache`
        reuse a stored record without believing a clock: see that module.

        The id is returned as sacct printed it, because that is what the record
        will be keyed by. Turning it into something ``-j`` accepts is
        :func:`queryable_job_id`'s job and happens at the point of asking --
        ``-j '49046820_[1-20%10]'`` is a fatal error in the very sacct that just
        printed that string.
        """
        listing = self._fetch(["-X", *extra], ["JobID", "State", "End"])
        delimiter = self._delimiter or "|"
        order = []
        marks: dict[str, list] = {}
        for line in listing.splitlines():
            row = line.split(delimiter)
            raw = row[0].strip() if row else ""
            if not raw or not _looks_like_job_id(raw):
                continue
            if raw not in marks:
                marks[raw] = []
                order.append(raw)
            marks[raw].append(
                (
                    _canonical_state(row[1].strip()) if len(row) > 1 else "",
                    row[2].strip() if len(row) > 2 else "",
                )
            )
        return [(raw, tuple(marks[raw])) for raw in order]

    def _query_partitioned(self, extra):
        """The window read by several sacct processes at once, or ``None``.

        ``None`` is "this is not worth splitting, or splitting is off" and the
        caller runs the ordinary single query -- which is also the path that
        reports an error, so nothing here has to produce a good message.

        The listing selects WHICH jobs; the reads then fetch each of those jobs
        **whole**, with no window filter of their own. That is a reversal, and it
        is load-bearing in two ways.

        The filters used to be passed to the reads as well, to make the result
        byte-identical to the single query. It is not identical any more, and the
        difference is a bug being fixed rather than introduced: sacct applies
        ``-S``/``-E``/``--state`` to STEP rows too, so a job that started before
        the window comes back with only the steps that ran inside it. Job
        57477255 on midway3 -- 41 hours, six work steps -- was returned with
        three, summing to **0.4 CPU-seconds against its real 21,383**, and
        `looks_like_noop` therefore called it idle and charged its 41.42
        GPU-hours to "never computed". That single job was the whole of one
        account's "41 of 116 GPU-hours never used" headline. A post-mortem of a
        job should see the job.

        It is also what makes :mod:`slurmpast.cache` sound. A record keyed by job
        id has to MEAN the same thing whichever window found it, and while the
        reads were windowed it did not: a record captured yesterday under
        ``now-7days`` held steps that today's ``now-7days`` excludes, so the same
        command answered differently depending on what was cached. Fetching the
        job whole removes the window from the record entirely.

        The job SET is unaffected -- verified against the live scheduler: the ids
        the listing names and the ids a single windowed query returns are the
        same, and dropping the filters adds 223 step rows across 5 long-running
        jobs and not one extra job.
        """
        if not self._parallel:
            return None
        fields = self.fields
        try:
            listing = self._window_listing(extra)
        except SacctError:
            # An sacct with no `-X`, or a query this site refuses. Either way the
            # single query below is the one that reports it, and it says something
            # a reader can act on -- so this stays silent and stops trying, rather
            # than paying for the same refusal on every reload.
            self._parallel = False
            return None
        if len(listing) < PARALLEL_MIN_JOBS:
            return None
        # Whatever the cache still describes correctly is not read again. `known`
        # keeps the listing's order so the result does not depend on what happened
        # to be cached; `wanted` is what is left to ask sacct for.
        store = self._store()
        known = {}
        wanted = []
        seen = set()
        for raw, fingerprint in listing:
            if store is not None:
                hit = store.get(raw, fingerprint)
                if hit is not None:
                    known[raw] = hit
                    continue
            queryable = queryable_job_id(raw)
            if queryable not in seen:
                seen.add(queryable)
                wanted.append(queryable)
        if not wanted:
            # Everything was already known. The listing was still made, so this is
            # as current as an uncached read of the same instant.
            self.stats["dropped_rows"] = {"shifted": 0}
            return [known[raw] for raw, _ in listing if raw in known]
        ids = wanted
        size = min(
            PARALLEL_IDS_PER_QUERY,
            max(PARALLEL_MIN_IDS_PER_QUERY, -(-len(ids) // PARALLEL_MAX_WORKERS)),
        )
        groups = [ids[at : at + size] for at in range(0, len(ids), size)]
        if len(groups) < 2 and not known:
            # One group and nothing cached is the single query with extra steps.
            # `and not known` is load-bearing: once the cache is warm `wanted` is
            # just the handful of jobs still running, which is ONE group -- and
            # bailing there threw away 22,354 valid records and re-read the whole
            # window, turning a 1.5 s warm start into 16 s.
            return None
        # One stats dict per group, merged below: `parse` writes into whatever it
        # is given, and several threads sharing one would race.
        collected: list[dict] = [{} for _ in groups]
        delimiter = self._delimiter
        # Query in parallel, parse one at a time. The queries are subprocesses and
        # overlap properly; the parse is Python and holds the GIL, so eight of them
        # running at once do not go eight times faster -- they take turns badly.
        # Measured over the same window: 4.38 s / 4.76 s unserialised against
        # 4.00 s / 3.99 s with this lock, and only one parse's intermediates are
        # alive at a time. A thread waiting here releases the GIL, so the one that
        # holds it runs at full speed while the others sit in sacct.
        parsing = threading.Lock()

        def read(at, group):
            # `-j` only: no window, no `--state`, no `-r`. See the docstring.
            text = self._fetch(["-j", ",".join(group)], fields)
            with parsing:
                return parse(text, fields=fields, delimiter=delimiter, stats=collected[at])

        try:
            batches = _in_parallel(
                [functools.partial(read, at, group) for at, group in enumerate(groups)],
                PARALLEL_MAX_WORKERS,
            )
        except SacctError:
            # A site that refuses a long `-j` list, or a scheduler that fell over
            # between the listing and the read. Fall back for this query AND every
            # later one on this instance, so a dashboard reloading in a loop does
            # not pay for the discovery each time.
            self._parallel = False
            return None
        shifted = sum((each.get("dropped_rows") or {}).get("shifted", 0) for each in collected)
        self.stats["dropped_rows"] = {"shifted": shifted}
        fetched = [job for batch in batches for job in batch]
        # Built ONCE. An earlier version rebuilt it inside the loop below, which
        # is O(jobs squared) and turned a warm 1.5 s read into 16 s.
        marks = dict(listing)
        if store is not None:
            for job in fetched:
                fingerprint = marks.get(job.job_id)
                # Only a job the LISTING named: an array element expanded out of a
                # master query was never described by the listing, so there is no
                # fingerprint to validate it against next time. `Store.put` refuses
                # anything that is not finished, which is what those are.
                if fingerprint is not None:
                    store.put(job, fingerprint)
            store.save()
        if not known:
            return fetched
        # Back into the listing's order, with anything sacct volunteered that the
        # listing did not name (an expanded pending array) kept on the end.
        by_id = {}
        extra_jobs = []
        for job in fetched:
            if job.job_id in marks:
                by_id[job.job_id] = job
            else:
                extra_jobs.append(job)
        out = []
        for raw, _fingerprint in listing:
            job = known.get(raw) or by_id.pop(raw, None)
            if job is not None:
                out.append(job)
        out.extend(by_id.values())
        out.extend(extra_jobs)
        return out

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
        # Split across several sacct processes when the window is big enough to
        # pay for the extra round trip; `None` means it was not, or could not be.
        # See PARALLEL_MIN_JOBS for what this costs and what it buys.
        partitioned = self._query_partitioned(extra)
        return self._query(extra) if partitioned is None else partitioned


#: What `sstat` is asked for, in this order.  Deliberately short: every field is
#: one a live step actually populates and one `Step` already has a home for.
_SSTAT_FIELDS = (
    "JobID",
    "MaxRSS",
    "MaxRSSNode",
    "MaxRSSTask",
    "AveRSS",
    "MaxVMSize",
    "MaxPages",
    "AveCPU",
    "MinCPU",
    "NTasks",
)

#: The parsed keys that are MEASUREMENTS, as opposed to labels for one
#: (`max_rss_node`, `max_rss_task`) or a description of the step's shape
#: (`ntasks`). A row with none of these carries no reading and is dropped.
#:
#: Named explicitly because the guard that used to do this -- `all(v in (None,
#: "") for v in measured.values())` -- did not do what its wording implied.
#: `NTasks=0` is neither `None` nor `""`, so a row whose only content was a zero
#: task count survived and was stored with every useful field empty. Real case,
#: job 53834744 on midway3:
#:
#:     53834744.extern|||||||213503982334-14:25:51||0
#:
#: -- an overflowed `AveCPU` that `_SSTAT_MAX_CPU_SECONDS` correctly discards, and
#: a `0` in the last column that kept the row alive. Harmless downstream, because
#: `_apply_live_metrics` only fills fields that are `None`, but it meant the
#: "nothing measured" test was passing rows that had measured nothing.
_SSTAT_MEASUREMENT_FIELDS = (
    "max_rss",
    "ave_rss",
    "max_vmsize",
    "max_pages",
    "ave_cpu",
)

#: Slurm writes an overflowed counter rather than an empty field, and `sstat` on
#: an `.extern` step produced `213503982334-14:25:51` -- 585 million years -- on
#: the first cluster this was tried against.  A CPU time longer than any job can
#: run is not a measurement, and `parse_duration` will happily return it.
_SSTAT_MAX_CPU_SECONDS = 366 * 24 * 3600


def read_live_metrics(job_ids, runner=None):
    """``{job_id: {step_id: Step-shaped dict}}`` from ``sstat``, for live steps.

    **`sacct` only flushes a step's accounting when the step ENDS.**  For a job
    that is still running the live rows carry no ``MaxRSS`` at all, and the only
    populated ones are whatever short-lived steps have already finished -- so a
    job holding 462 MiB against ``--mem=512M`` reported **2.2 MiB, 0.4%**, taken
    from a 1-second monitoring step, on the gauge whose entire purpose is to say
    whether memory was the problem.  A 210x understatement, published with
    ``peak_trustworthy: true``.

    What makes it likely rather than exotic: the finished step is often created
    *by watching the job*.  An `srun --overlap` monitor -- slurmwatch's own node
    hop, or an interactive probe -- leaves a ~2 MiB step behind, and that becomes
    the reported peak.  A job nobody watched reports ``n/a`` instead, which is
    honest only by luck of the draw.  So the two sibling tools interacted badly:
    using slurmwatch on a job made slurmpast's post-mortem of it worse.

    ``sstat`` has the right number at the same instant, it is available to the
    job's owner from a login node, and slurmwatch already uses it.  One call for
    every live job rather than one per job: ``-j`` takes a comma-separated list.

    Returns ``{}`` on any failure -- another user's job, a job that just ended, a
    site that does not run ``jobacct_gather`` -- because the caller's fallback is
    to report the field as unmeasured, which is the correct answer and not a
    degradation.
    """
    wanted = [str(j).split(".")[0] for j in job_ids if str(j).strip()]
    if not wanted:
        return {}
    argv = [
        "sstat",
        "--allsteps",
        "--noheader",
        "--parsable2",
        "--jobs=%s" % ",".join(dict.fromkeys(wanted)),
        "--format=%s" % ",".join(_SSTAT_FIELDS),
    ]
    # The cap is set around the call rather than passed to it, so `runner`'s
    # one-argument protocol is untouched and a patched `sacct._run` still
    # intercepts this query exactly as it did before.
    run = runner or _run
    previous = getattr(_query_cap, "value", None)
    _query_cap.value = LIVE_METRICS_TIMEOUT_S
    try:
        out = run(argv)
    except SacctError:
        return {}
    finally:
        _query_cap.value = previous
    return _parse_live_metrics(out)


def _parse_live_metrics(text):
    """Parse ``sstat --parsable2`` output into per-job, per-step measurements."""
    found = {}
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        fields = line.split("|")
        if len(fields) < len(_SSTAT_FIELDS):
            continue
        row = dict(zip(_SSTAT_FIELDS, fields, strict=False))
        step_id = _clean(row.get("JobID"))
        if not step_id or "." not in step_id:
            continue
        ave_cpu = parse_duration(_clean(row.get("AveCPU")))
        if ave_cpu is not None and (ave_cpu < 0 or ave_cpu > _SSTAT_MAX_CPU_SECONDS):
            # See `_SSTAT_MAX_CPU_SECONDS`: an overflowed counter, not a time.
            ave_cpu = None
        measured = {
            "max_rss": parse_bytes(_clean(row.get("MaxRSS"))),
            "max_rss_node": _clean(row.get("MaxRSSNode")),
            "max_rss_task": _clean(row.get("MaxRSSTask")),
            "ave_rss": parse_bytes(_clean(row.get("AveRSS"))),
            "max_vmsize": parse_bytes(_clean(row.get("MaxVMSize"))),
            # `parse_bytes`, matching the `sacct` row path rather than `_int`.
            # The two disagreed on a suffixed value -- `_int("2K")` is None where
            # `parse_bytes("2K")` is 2048 -- and the `sacct` site says in a
            # comment that the suffix handling is load-bearing because THIS
            # cluster emits bare values and others need not. One field, one rule:
            # otherwise `page_faults` reads null for a running job on any site
            # whose `sstat` suffixes it, and a row whose only measurement were a
            # suffixed MaxPages would be dropped as "nothing measured".
            "max_pages": parse_bytes(_clean(row.get("MaxPages"))),
            "ave_cpu": ave_cpu,
            "ntasks": _int(_clean(row.get("NTasks"))),
        }
        if all(measured[field] is None for field in _SSTAT_MEASUREMENT_FIELDS):
            continue
        found.setdefault(_base_job_id(step_id), {})[step_id] = measured
    return found


def _own_name_or_blank():
    """``current_user()``, or ``""`` when identity cannot be established.

    `current_user()` raises `SacctError` when every fallback fails, which is
    right for "whose history do I read?" -- the tool cannot proceed. It is wrong
    here: not knowing who we are makes one optimisation unavailable, not the
    report impossible, and letting it raise would turn a working query into a
    failure on exactly the nodes that motivated `current_user`'s own fallbacks.
    """
    try:
        return current_user()
    except SacctError:
        return ""


def merge_live_metrics(jobs, runner=None, user=None):
    """Fill in what ``sacct`` has not flushed for jobs that are still going.

    A no-op for a history of finished jobs, which is the common case: nothing is
    asked unless some job is in a non-terminal state.

    Also records WHY a live job has no live reading, which is two different facts
    wearing one label.  ``sstat`` is owner-only: asked about another user's step
    it answers ``Invalid user id`` on stderr with **exit 0 and empty stdout**, so
    the outcome is identical to "the job just ended" or "this site runs no
    ``jobacct_gather``" -- and only one of those clears if you wait.  Under
    ``--all-users`` that is the majority case, not an edge one.  ``user`` is the
    reader whose PERMISSIONS apply -- not the user being asked about. Those differ
    on every `-u <someone-else>` run, and passing `args.user` here would decide
    that a foreign job belongs to the reader and query it after all, which is the
    18-second call this exists to avoid. Resolved from the environment when not
    given, which is the only caller so far.
    """
    live = [j for j in jobs if j.in_progress]
    if not live:
        return jobs
    me = user or _own_name_or_blank()

    def _foreign(job):
        # Only when the owner is KNOWN to differ, and every uncertainty resolves
        # to "ask anyway". Three of them, all reachable:
        #
        # * a narrow `--format` carries no `User` at all;
        # * `current_user()` can fail outright, and now raises inside this call
        #   path where it did not before;
        # * on a cluster whose nodes have no passwd entry, `current_user()`
        #   deliberately falls back to the numeric uid while `sacct` reports a
        #   name -- so the two are not comparable and inequality means nothing.
        #
        # Treating any of those as "somebody else's" would silently drop the live
        # reading on the reader's OWN job, which is the whole point of
        # `read_live_metrics`. Losing a reading is a wrong number; asking and
        # getting nothing is only a slow one.
        if not me or not job.user:
            return False
        if me.isdigit() != str(job.user).isdigit():
            return False
        return job.user.lower() != me.lower()

    mine = [j for j in live if not _foreign(j)]
    # Not asked about at all, rather than asked and discarded. `sstat` is
    # owner-only, so the answer for somebody else's step is known before the call
    # -- and the call is not free: measured here, 20 of another user's running
    # jobs cost **18.1 s** and produced **7,840** `sstat: error: ... Invalid user
    # id` lines, because the client contacts every node of every step. A full
    # `--all-users` sweep of this cluster's 288 running jobs spent minutes on a
    # query that cannot succeed, and a `-u <someone-else>` report timed out
    # entirely. The stderr never reached the terminal (`_run` pipes it and drops
    # it on exit 0, which is how this failure exits), so the cost was wall-clock
    # and not noise -- but it was paid on every run.
    measured = read_live_metrics([j.job_id for j in mine], runner=runner) if mine else {}
    out = []
    for job in jobs:
        rows = measured.get(job.job_id.split(".")[0]) if job.in_progress else None
        if rows:
            out.append(_apply_live_metrics(job, rows))
        elif job.in_progress and _foreign(job):
            out.append(job._replace(foreign_owner=True))
        else:
            out.append(job)
    return out


def _apply_live_metrics(job, rows):
    """One job's steps, with ``sstat``'s figures written into the live ones.

    Only fields ``sacct`` left empty are filled: a step that has ended has real
    accounting and `sstat` has nothing to say about it.  ``sstat``'s own
    ``AveCPU`` is per task, so it is scaled by the step's task count to give the
    same quantity ``TotalCPU`` carries.
    """
    updated = []
    for step in job.steps:
        row = rows.get(step.step_id)
        if row is None or not step.in_progress:
            updated.append(step)
            continue
        changes = {}
        for field in ("max_rss", "ave_rss", "max_vmsize", "max_pages"):
            if getattr(step, field) is None and row.get(field) is not None:
                changes[field] = row[field]
        for field in ("max_rss_node", "max_rss_task"):
            if not getattr(step, field) and row.get(field):
                changes[field] = row[field]
        if step.total_cpu in (None, 0.0) and row.get("ave_cpu"):
            tasks = row.get("ntasks") or step.ntasks or 1
            changes["total_cpu"] = row["ave_cpu"] * max(1, tasks)
            changes["ave_cpu"] = row["ave_cpu"]
        updated.append(step._replace(**changes) if changes else step)
    return job._replace(steps=tuple(updated), live_metrics=True)


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
