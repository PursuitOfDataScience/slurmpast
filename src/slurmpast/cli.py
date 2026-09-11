"""Command line entry point.

Shape mirrors slurmwatch: bare invocation opens the dashboard, an argument
targets one thing, and every view is also reachable as plain text for pipes.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import json
import re
import signal
import sys

from . import report
from ._version import __version__
from .diagnose import diagnose
from .duration import humanize_window
from .index import History, filter_jobs, sort_groups
from .logs import assign_logs, read_tail
from .model import severity_rank
from .nodes import Workload, expand_nodelist, note_for_allocation
from .sacct import (
    Sacct,
    SacctError,
    controller_log_paths,
    current_user,
    live_job_ids,
    merge_live_metrics,
)

EPILOG = """\
examples:
  slurmpast                        dashboard over the last 7 days
  slurmpast -S now-30days          ... over the last 30 days
  slurmpast 51170455               post-mortem for one job
  slurmpast --failed --plain       everything that died, as text
  slurmpast --patterns             what keeps failing, across runs
  slurmpast --nodes                which nodes eat your jobs
  slurmpast -u alice,bob           someone else's history, or several
  slurmpast --all-users --nodes    every account on the cluster
  slurmpast 51170455 --json        machine readable

exit status:
  0  ran, and nothing it judges is critical
  1  a critical finding
  2  slurmpast or sacct could not answer (bad argument, no Slurm, query failed)

  What `1` means depends on how it was invoked, which is worth knowing before
  wrapping it: with job ids it is "one of these jobs has a critical finding";
  without them it is "a cross-run pattern is critical", and per-job findings in
  the same payload do not raise it. That default is deliberate — a scan over a
  whole cluster would exit 1 almost always, which makes the code useless as a
  signal — but it is not what `slurmpast --json || alert` assumes. Pass
  --strict to fold per-job findings back in.

  The reporting views always exit 0 — they report rather than judge:
  --overview --patterns --nodes --sizing

`sp` is a short alias for the same entry point.
"""


def _row_limit(value):
    """A row count for ``-n``, rejecting the ones that read as a silent bug.

    Every consumer slices ``[:limit]``, so ``-n -5`` -- a plausible typo for ``-n 5``,
    and one this tool invites by accepting ``-S -7days`` -- quietly drops the last
    five rows and prints "5 more" instead of failing.

    ``0`` means **unlimited**, returned as ``None`` so every ``[:limit]`` site gets
    it for free. It used to be refused on the grounds that it "renders a table with
    a header, no rows, and a footer saying everything was omitted" -- which is what
    ``[:0]`` does and is a good reason to reject 0 as a literal count. It is not a
    reason to reject this meaning: under it the table renders *everything*, so the
    objection no longer applies.

    The meaning is borrowed rather than invented. A sibling tool in this suite
    already spells "no limit" as ``-n 0``, and one flag meaning "unlimited" in one
    tool and "usage error" in another is a worse surface than either alone. It also
    gives `--json` consumers the explicit escape hatch they need, since the
    findings array is clipped by this same flag.
    """
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("not a number: %s" % value) from None
    if number == 0:
        return None
    if number < 1:
        raise argparse.ArgumentTypeError("must be 0 (unlimited) or more, got %s" % number)
    return number


# The order composed text sections print in, which is deliberately not the order
# the branches are written in: a reader wants the rollup before the findings, and
# the findings before the screens that attribute them to a node or a request.
SECTION_ORDER = ("overview", "patterns", "nodes", "sizing")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="slurmpast",
        description="Why did your Slurm jobs fail? A post-mortem for finished jobs.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("job_ids", nargs="*", help="job ids to examine")
    parser.add_argument(
        "-u",
        "--user",
        default=None,
        help="user to query, or a comma-separated list of them (default: you)",
    )
    parser.add_argument(
        "--all-users",
        action="store_true",
        help="every account on the cluster, not just yours",
    )
    parser.add_argument(
        "-S",
        "--since",
        default="now-7days",
        help="start of the window, sacct syntax (default: now-7days). "
        "'-7days' is accepted and rewritten for you",
    )
    parser.add_argument("-E", "--until", default=None, help="end of the window")
    parser.add_argument("-p", "--partition", default=None, help="restrict to a partition")
    parser.add_argument("--failed", action="store_true", help="only jobs that failed")
    parser.add_argument(
        "-n",
        "--limit",
        type=_row_limit,
        default=25,
        help="rows in plain output and entries in --json's findings array; 0 for no limit",
    )

    parser.add_argument(
        "--plain",
        action="store_true",
        help="text output, no dashboard (automatic when stdout is not a terminal)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 if any job has a critical finding, not just a cross-run pattern",
    )
    parser.add_argument("--overview", action="store_true", help="workload rollup as text")
    parser.add_argument("--patterns", action="store_true", help="cross-run patterns as text")
    parser.add_argument("--nodes", action="store_true", help="node reliability as text")
    parser.add_argument(
        "--sizing",
        action="store_true",
        help="what to request next time, per workload, from how it actually ran",
    )
    parser.add_argument(
        "--metric",
        choices=["failure", "hang"],
        default="hang",
        help="what --nodes measures (default: hang)",
    )
    parser.add_argument(
        "--all-workloads",
        action="store_true",
        help="skip the workload control in --nodes (confounded)",
    )
    parser.add_argument(
        "--sort",
        default="cost",
        choices=["cost", "failures", "rate", "recent", "runs", "name"],
        help="workload ordering (default: cost)",
    )

    parser.add_argument(
        "--log-dir", action="append", default=[], help="extra directory to search for job logs"
    )
    parser.add_argument("--no-logs", action="store_true", help="do not read job logs")
    # A finished job's accounting record cannot change, so it is kept and reused;
    # see `slurmpast.cache` for what makes that safe. This is the off switch, for
    # a reader who would rather spend the seconds than keep the file. The
    # environment variable does the same thing for every run.
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="re-read every job from sacct instead of reusing finished ones "
        "(same as SLURMPAST_NO_CACHE=1)",
    )
    # Names its scope, as `--metric`, `--all-workloads`, `-n` and `--sort` all do:
    # this one reaches exactly one view, and read as an unscoped "per-step
    # accounting" it invites `--plain --steps` over a list, where it is accepted
    # and does nothing.
    parser.add_argument("--steps", action="store_true", help="per-step accounting, on a named job")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument(
        "--mouse",
        action="store_true",
        help="let the app capture the mouse (enables clicking and wheel "
        "scrolling, but disables your terminal's text selection)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="synthetic history — try it without Slurm, and drive the demo tape",
    )
    parser.add_argument(
        "--ascii",
        action="store_true",
        # Says "text output" because that is what it can honestly promise: the
        # dashboard's frame is drawn by Textual in box characters whatever this
        # flag says, so only the piped surface can actually come out ASCII.
        help="ASCII instead of Unicode in text output (glyphs and punctuation)",
    )
    parser.add_argument("--no-color", action="store_true", help="disable ANSI colour")
    parser.add_argument("--version", action="version", version="slurmpast " + __version__)
    return parser


_VALUE_OPTS = ("-S", "--since", "-E", "--until", "-u", "--user", "-p", "--partition")


def _known_option_strings():
    """Every flag the parser accepts, asked of the parser rather than listed again.

    A second hand-maintained list would drift the moment a flag is added, and the
    drift would be silent -- which is the shape of the bug this guards.
    """
    known = set()
    for action in build_parser()._actions:
        known.update(action.option_strings)
    return known


# sacct's relative time syntax is `now-7days`. A bare `-7days` is REJECTED
# outright ("Invalid time specification"), but it is the obvious thing to type
# and what this tool's own help used to advertise -- so accept it and rewrite.
_RELATIVE_SPEC = re.compile(r"^-\s*\d+\s*(second|minute|hour|day|week|month)s?$", re.IGNORECASE)


def normalize_time_spec(value):
    """``-7days`` -> ``now-7days``. Anything sacct already understands is left alone."""
    if not value:
        return value
    text = value.strip()
    if _RELATIVE_SPEC.match(text):
        return "now" + text.replace(" ", "")
    return value


def _glue_negative_values(argv):
    """Let ``-S -7days`` work.

    sacct's own relative-time syntax starts with a dash, so that is what people
    type; argparse would treat it as an unknown option and exit 2 on the most
    natural spelling of the most common flag.

    A token that is itself an option is never a value. Only ``--`` was excluded, so
    a short flag got swallowed: ``slurmpast -u -p gpu`` -- which is what
    ``-u "$USER" -p gpu`` becomes when ``$USER`` is unset -- was rewritten to
    ``-u=-p gpu``, parsed as ``user="-p"`` with ``gpu`` as a job id, and reported
    "no job matches: gpu". The partition filter had silently vanished, and the error
    named something the user never typed. Argparse's own "expected one argument" is
    the right answer, so this now steps aside and lets it happen.
    """
    known = _known_option_strings()
    out, index = [], 0
    while index < len(argv):
        token = argv[index]
        if token in _VALUE_OPTS and index + 1 < len(argv):
            value = argv[index + 1]
            if value.startswith("-") and not value.startswith("--") and value not in known:
                out.append("%s=%s" % (token, value))
                index += 2
                continue
        out.append(token)
        index += 1
    return out


def _mark_open_records(jobs, runner=None, user=None, all_users=False):
    """Reconcile anything unfinished against squeue.

    sacct reports State=RUNNING with End=Unknown for jobs that died long ago;
    its Elapsed is then now-minus-start. One such record read as 62 days and was
    65% of a GPU-hour total. Both a live job and a dead-but-open record have an
    unusable elapsed, so both get flagged.

    ``runner`` is the same command runner the Sacct instance uses, so a caller
    that injected one is not silently bypassed here and made to shell out for
    real -- which is what a test or a replayed history would have done.

    The ids squeue returns are now *used*, not merely counted. This tested the
    answer for ``None`` and threw the set away, so the reconciliation this
    docstring describes -- "if sacct says RUNNING and squeue has never heard of
    it, the record is dead" -- was never actually performed: every open record was
    flagged identically whether the job was running this second or had died in
    March. Both are still excluded from aggregates, because both have an elapsed
    measured to *now* rather than to an end. What the set buys is the sentence the
    reader gets: the open-record finding said "Confirm against squeue" about a
    query the tool had already run and discarded the answer to.
    """
    if not any(j.base_state == "RUNNING" or j.open_ended for j in jobs):
        return jobs
    live = live_job_ids(runner=runner, user=user, all_users=all_users)
    if live is None:
        return jobs  # cannot tell -- do not guess
    return [
        j._replace(open_ended=True, live=j.job_id.split(".")[0] in live)
        if (j.base_state == "RUNNING" or j.open_ended)
        else j
        for j in jobs
    ]


def _load(args, sacct):
    if getattr(args, "demo", False):
        # Clearly synthetic; see demo.py. Never mixed with real records.
        from .demo import DEMO_PARTITIONS, DEMO_SITE, history
        from .site import pin_partition_ceilings, reset_cache, site

        # Pin the synthetic cluster's configuration too. Otherwise `--demo` on a
        # real cluster words its memory and GPU notes from *that* cluster's
        # scontrol output, so the demo differs by machine and the CI check of it
        # depends on the runner having no Slurm.
        reset_cache()
        site(runner=lambda _args: DEMO_SITE)
        # Node sizes too, for the same reason: `--sizing` clamps upward advice to
        # the partition ceiling and would otherwise run `sinfo` against whatever
        # cluster the demo happens to be launched from.
        pin_partition_ceilings(DEMO_PARTITIONS)

        jobs = history()
        if args.job_ids:
            # Honour the id rather than silently ignoring it and printing all 58
            # synthetic post-mortems, which is what `--demo <jobid>` used to do.
            # Nothing else applies here, matching the real path: `-j` goes straight
            # to sacct and ignores the window and the filters too.
            wanted = {str(j) for j in args.job_ids}
            picked = [j for j in jobs if j.job_id in wanted]
            if not picked:
                raise SacctError("no demo job matches: %s" % ", ".join(args.job_ids))
            return picked
        # Every narrowing flag the real path applies, applied here too. `--failed`
        # was fixed on its own once, for the reason that ignoring it "made
        # `--help`'s 'only jobs that failed' false in exactly the place someone
        # tries the flag first" -- and `-p` and `-u` sat in the same position,
        # unfixed. Every synthetic job is partition `test`, user `youzhi`, so
        # `--demo -p gpu` matched nothing and printed all 58 records anyway, exiting
        # 0 where the real path raises and exits 2.
        asked = []
        if args.partition:
            jobs = [j for j in jobs if j.partition == args.partition]
            asked.append("partition %s" % args.partition)
        if args.user:
            wanted_users = {u.strip() for u in args.user.split(",") if u.strip()}
            jobs = [j for j in jobs if j.user in wanted_users]
            asked.append("user %s" % args.user)
        if args.failed:
            # `--failed` narrows the real query through sacct's `--state`, so it
            # narrows the whole history, not just the job list at the bottom.
            jobs = [j for j in jobs if j.failed]
            asked.append("--failed")
        if not jobs:
            raise SacctError("no demo jobs match %s" % " and ".join(asked))
        return jobs
    runner = getattr(sacct, "_run", None)
    all_users = getattr(args, "all_users", False)
    if args.job_ids:
        jobs = sacct.jobs(args.job_ids)
        if not jobs:
            raise SacctError("no accounting records for: %s" % ", ".join(args.job_ids))
        # `all_users` forwarded here too. `-j` goes straight to sacct and ignores
        # every filter, so `--all-users <someone else's jobid>` returns their
        # record -- and then reconciled it against `squeue --me`, which has never
        # heard of their job, so a live job of theirs read as a stale record. Same
        # latent inconsistency round four fixed one level down in `live_job_ids`.
        return merge_live_metrics(
            _mark_open_records(jobs, runner=runner, user=args.user, all_users=all_users),
            runner=runner,
        )

    user = None if all_users else (args.user or current_user())
    # DEADLINE alongside the rest: `Job.failed` counts it, so leaving it out here
    # meant `--failed` quietly excluded a state the tool calls a failure everywhere
    # else.
    states = (
        ["FAILED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL", "BOOT_FAIL", "DEADLINE"]
        if args.failed
        else None
    )
    jobs = sacct.history(
        user=user,
        since=args.since,
        until=args.until,
        states=states,
        partition=args.partition,
        all_users=all_users,
    )
    if not jobs:
        # Name the scope. A site with `PrivateData=jobs` answers `-u alice` with an
        # empty set and no error, so "no jobs for alice" is the only thing telling
        # the reader they got someone else's window and not their own.
        # Every filter that could be responsible, not just `--failed`. A partition
        # name is the one argument that reliably does not survive being carried to
        # another cluster -- midway3 has `caslake`, mercury `standard`, pythia
        # `standard_hopper` -- so `-p` holding a name this site has never heard of
        # is the ordinary way to reach here, and reporting it as "no jobs since
        # now-30days" states something false about the window. Measured on mercury:
        # `-p nonexistent_xyz -S now-30days` said exactly that, with 18 jobs in the
        # window.
        narrowed = []
        if args.failed:
            narrowed.append("--failed")
        if args.partition:
            narrowed.append("--partition %s" % args.partition)
        raise SacctError(
            "no jobs for %s since %s%s%s"
            % (
                "any user" if all_users else user,
                args.since,
                # The window is two-sided whenever `-E` is given, and naming only
                # its start described a query nobody ran.
                " until %s" % args.until if args.until else "",
                " matching %s" % " and ".join(narrowed) if narrowed else "",
            )
        )
    # One `sstat` call, and only when some job is still going: `sacct` has not
    # flushed those, and every memory or CPU figure read from them is a
    # measurement of a different step. See `sacct.read_live_metrics`.
    return merge_live_metrics(
        _mark_open_records(jobs, runner=runner, user=user, all_users=all_users),
        runner=runner,
    )


def _with_controller_paths(targets, args):
    """Fill in ``StdOut``/``StdErr`` from the controller where sacct could not.

    `sacct` only learned those fields in 24.05, so on an older cluster the log
    ladder falls through to guessing by mtime -- and a guess can be wrong with
    confidence: a decoy file with a matching timestamp was attached to a job on a
    GPU-less partition and drew a *critical* "GPU ran out of memory". `scontrol`
    knows the real answer for as long as the controller remembers the job, which
    is the window a post-mortem run right after a failure sits in.

    **Only for ids the caller typed.** The list branches (`--failed`, `--problem`)
    can hold hundreds of jobs, mostly old enough that the controller has forgotten
    them, and one subprocess each to be told so is a cost with no return. The
    explicit-id branch is both small and the case that is usually recent.

    Jobs that already carry a recorded path are left alone -- 24.05 answered, and
    asking twice cannot improve on it.
    """
    if not args.job_ids:
        return targets
    out = []
    for job in targets:
        if job.std_out or job.std_err:
            out.append(job)
            continue
        std_out, std_err = controller_log_paths(job.job_id)
        out.append(job._replace(std_out=std_out, std_err=std_err) if (std_out or std_err) else job)
    return out


def _logs_for_all(targets, args):
    """``{job_id: (path, text, inferred)}`` for a whole list, resolved together.

    A timing match has to be settled across jobs: several runs of one workload have
    overlapping windows, so resolved one at a time they all claim the file nearest
    their End and the same log is attached to four different post-mortems. See
    :func:`slurmpast.logs.assign_logs`.
    """
    if args.no_logs:
        return {job.job_id: (None, None, False) for job in targets}
    targets = _with_controller_paths(targets, args)
    assigned = assign_logs(targets, extra_dirs=args.log_dir)
    out = {}
    for job in targets:
        path, inferred = assigned.get(job.job_id, (None, False))
        out[job.job_id] = (path, read_tail(path) if path else None, inferred)
    return out


def _node_note(job, history):
    if history is None:
        return ""
    # The whole allocation, not just its first node -- see note_for_allocation,
    # which also holds the MIN_HISTORY floor this used to spell for itself.
    # The job's OWN workload, user included: `history` may span users under
    # `-u alice,bob` or `--all-users`, and a bare name pools whoever shares it.
    return note_for_allocation(
        history.usable_jobs, job.node_list, workload=Workload(job.name, job.user)
    )


def _node_history(args, sacct, history, targets):
    """The population a node note is computed from: the window, on every branch.

    A node's reliability is a property of the WINDOW, not of the job asked about.
    Everywhere except `-j` that was already true -- `history` there is the whole
    query. On the explicit-id branch `_load` returns only the records asked for,
    so `slurmpast <one id>` computed the note from a history of one, where no node
    can reach `nodes.MIN_SAMPLES` and the answer is always "". The dashboard, which
    holds the window whichever screen is open, drew the sentence from the same
    function for the same id:

        $ slurmpast 53363721_35 --plain --no-logs -S now-30days   # before
          (no node finding)
        dashboard JobScreen(53363721_35), same 30-day window:
          INFO  Node has a history with your jobs
                midway3-0250 failed 32 of 33 placements there (97.0%, 95% CI
                84.7-99.5%) against 1.0% on every other node for caai-p10b_scan.

    Same `note_for_allocation`, same wording, different `jobs` argument -- which
    is the drift `render.py` exists to prevent, arriving through the one door it
    cannot watch: not what the sentence says but whether it is reached at all. The
    reader of `--plain` was told nothing about a node that had failed 32 of their
    33 runs there.

    **Widened, rather than lowering the floor.** Deleting the `len(history) > 20`
    gate fixes nothing: measured on this cluster, a one-record history yields ``''``
    with the gate gone, because `node_table` drops every node under MIN_SAMPLES and
    one placement is one. The population was the defect; the gate was downstream of
    it.

    **The job's own record still comes from `sacct -j`**, so `-j` keeps ignoring
    the window for the post-mortem itself and an id older than `-S` still reports.
    Only the comparison population is taken from the window -- and it is taken
    through `_load`, so `-p`, `-u`, `--all-users` and `--failed` narrow it exactly
    as they narrow the dashboard's. Agreeing with the other surface is the point;
    a second, differently-filtered population would just be new drift.

    Cost, measured rather than assumed (90-day history, 50,604 sacct rows):
    `sacct` for the default `now-7days` window is 0.26 s against the 0.20 s the id
    query already costs, and `-S now-30days` is 9.3 s for 13,075 rows -- the same
    query every other mode of the tool already runs for that window. So it is
    loaded lazily and once: nothing is queried unless some target job actually has
    an allocation to say something about, and an empty or failing window leaves the
    note "" rather than turning a post-mortem into an error.
    """
    if not args.job_ids:
        return history  # already the window
    if not any(expand_nodelist(job.node_list) for job in targets):
        return None
    scoped = copy.copy(args)
    scoped.job_ids = []
    try:
        return History(_load(scoped, sacct), window=history.window)
    except SacctError:
        # No jobs in the window is a reason to stay silent, not to fail: the
        # record the reader asked about was found, and that is what they asked
        # for. `_load` raises here for an empty window, a `-p` this site has
        # never heard of, and a `PrivateData=jobs` refusal alike.
        return None


def _parse_warnings(sacct):
    """``{"dropped_rows": …}`` when the parser refused any row, else ``{}``.

    Emitted only when non-zero, so a well-formed cluster sees no schema change at
    all and every existing consumer is unaffected. The report that asked for this
    count also pointed out that `--json` is a channel that already exists, which
    is right and is why nothing else had to move: `parse` fills an optional dict,
    `Sacct` holds it, this reads it.

    What it counts is the pipe-shifted row: a value containing the delimiter, so
    every column after it is misaligned and the row is refused. That is deliberate
    and documented; being silent about it was not. It is reachable on a cluster
    whose sacct predates `--delimiter` (17.11) and therefore uses `|`, which is
    precisely the kind of site nobody here can test on.
    """
    dropped = sacct.stats.get("dropped_rows") or {}
    return {"dropped_rows": dropped} if any(dropped.values()) else {}


def _log_miss(job, log_path, no_logs=False):
    """``{"log_expected": …}`` when a recorded path was tried and missed, else {}.

    Kept out of `log` rather than turned into an object there: `log` is a path or
    null in every existing consumer, and widening its type to carry a diagnosis
    would break readers to describe a case most of them never hit.

    Always present, both sub-keys, `null` where there is nothing to say. It first
    shipped conditionally -- absent when a log was found or none was recorded --
    which is the right instinct for a *root* key (`dropped_rows` above is emitted
    only when non-zero, so a well-formed cluster's payload is unchanged) and the
    wrong one here. Per-job keys are counted: `--json`'s value count is documented
    in the README and pinned by `TestTheJsonPayloadKeepsItsPromise`, and a key
    that comes and goes made that number 97 or 99 depending on the job, with the
    audit's sample never carrying it. A machine payload is easier to consume with
    one shape than with two.

    Silent under `--no-logs`, and that is not a nicety. The whole point of the
    flag is that the filesystem is not touched, and the text view already guards
    the equivalent sentence on exactly that basis -- "both spellings are claims
    about the filesystem and under `--no-logs` nothing was stat'd". Reporting a
    status here would stat the path to compute it, so the first version of this
    broke the guard while adding the field it was meant to complement.
    """
    empty = {"log_expected": {"path": None, "status": None}}
    if no_logs or log_path:
        return empty
    from .logs import probe_path, recorded_paths

    expected = recorded_paths(job)
    if not expected:
        return empty
    return {"log_expected": {"path": expected[0], "status": probe_path(expected[0])}}


def _job_json(job, log_path, verdict, no_logs=False):
    """Every extracted measurement, machine-readable.

    Deliberately exhaustive: if the tool read it, this emits it, so downstream
    analysis never has to re-run sacct with a wider --format. Values that could
    not be read are ``null``, never 0.
    """
    return {
        # Deliberately exhaustive. If the reader was captured, it is emitted --
        # a field extracted but never surfaced is dead weight, and the point of
        # the wide query was that nobody should have to re-run sacct.
        "identity": {
            "job_id": job.job_id,
            "job_id_raw": job.job_id_raw,
            "name": job.name,
            "user": job.user,
            "uid": job.uid,
            "group": job.group,
            "account": job.account,
            "cluster": job.cluster,
            "partition": job.partition,
            "qos": job.qos,
            "assoc_id": job.assoc_id,
            "wckey": job.wckey,
            "work_dir": job.work_dir,
            "reservation": job.reservation,
            "comment": job.comment or None,
            "admin_comment": job.admin_comment or None,
            "layout": job.layout or None,
            # Recorded from Slurm 24.05; null on any older cluster -- 21.08 is
            # when SubmitLine arrived, not these two. See the boundary table at
            # the top of logs.py. Patterns as stored, unexpanded -- see
            # logs.expand_pattern for the resolved form.
            "stdout_pattern": job.std_out or None,
            "stderr_pattern": job.std_err or None,
            "submit_line": job.submit_line or None,
        },
        "outcome": {
            "state": job.base_state,
            "state_raw": job.state,
            "exit_code": job.exit_code,
            "signal": job.signal,
            "derived_exit_code": job.derived_exit_code,
            # The signal half of `DerivedExitCode`, published because it is the
            # half that carries the finding: a job whose steps were killed is
            # `0:9`, so `derived_exit_code` alone is 0 on every one of them and a
            # consumer reading only that number cannot tell it from a clean run.
            # Not recoverable from `steps` either -- the roll-up is the job row's
            # own field and survives a step purge that empties that array.
            "derived_signal": job.derived_signal,
            "reason": job.reason,
            "failed": job.failed,
            "completed": job.completed,
            "cancelled": job.cancelled,
            "open_ended_record": job.open_ended,
            # What squeue answered about an open record, tri-state as the model
            # stores it: true = still queued or running, false = squeue has never
            # heard of it so the record is stale, null = not asked or unreachable.
            #
            # Emitted because it was measured. `cli._mark_open_records` runs the
            # query and writes the answer onto the job, both text surfaces spend it
            # on the finding's action sentence, and this payload -- whose whole
            # promise is "if the tool read it, this emits it" -- carried only
            # `open_ended_record`, which is `true` in all three cases. So the one
            # consumer that cannot read English had no way to tell a job running
            # right now from one that died in March, and `timing.elapsed_seconds`
            # is measured to *now* for both. Round six's headline defect was that
            # same distinction going the other way.
            "live": job.live,
        },
        "timing": {
            "submit": job.submit,
            "eligible": job.eligible,
            "start": job.start,
            "end": job.end,
            "elapsed_seconds": job.elapsed,
            "timelimit_seconds": job.timelimit,
            "walltime_used": job.walltime_used,
            "queue_wait_seconds": job.queue_wait,
            "suspended_seconds": job.suspended,
            "scheduled_by": job.scheduled_by,
            "flags": job.flags,
            "priority": job.priority,
            # Earlier incarnations of this id, oldest first, when Slurm requeued
            # it. Empty for the ordinary job. Each carries its own state and the
            # time it really consumed -- the whole point of surfacing them is
            # that a requeued allocation is allocated time that used to appear
            # nowhere, so a consumer summing `elapsed_seconds` alone still
            # understates the job. Not nested Job payloads: a requeued
            # incarnation has no steps of its own worth re-emitting here, and a
            # recursive structure would break every existing reader of this key.
            "earlier": [
                {
                    "state": earlier.state,
                    "base_state": earlier.base_state,
                    "exit_code": earlier.exit_code,
                    "submit": earlier.submit,
                    "start": earlier.start,
                    "end": earlier.end,
                    "elapsed_seconds": earlier.elapsed,
                    "node_list": earlier.node_list,
                }
                for earlier in job.earlier
            ],
        },
        "shape": {
            "nodes": job.node_count,
            "node_list": job.node_list,
            "cpus": job.cpu_count,
            # Per task, which is what --cpus-per-task sets; `cpus` is the total.
            "cpus_per_task": job.cpus_per_task,
            "tasks": job.task_count,
            "gpus": job.gpu_count,
            "req_cpus": job.req_cpus,
            "req_nodes": job.req_nodes,
            "alloc_tres": job.alloc_tres,
            "req_tres": job.req_tres,
            # Pre-20.11 spelling; null wherever TRES carries the GPUs instead.
            "alloc_gres": job.alloc_gres or None,
            "req_gres": job.req_gres or None,
            "constraints": job.constraints,
            "req_mem_scope": job.req_mem_scope,
            "req_cpu_freq_min": job.req_cpu_freq_min or None,
            "req_cpu_freq_max": job.req_cpu_freq_max or None,
            "req_cpu_freq_governor": job.req_cpu_freq_gov or None,
        },
        "cpu": {
            "total_seconds": job.total_cpu,
            "user_seconds": job.user_cpu,
            "system_seconds": job.system_cpu,
            "system_fraction": job.system_cpu_fraction,
            "allocated_core_seconds": job.cpu_time,
            "utilization": job.cpu_utilization,
            # Raw string and resolved number, for the reason stated below about
            # `req_mem_raw`: a consumer should never have to guess which
            # convention a figure is in. Here it could not even guess. Slurm
            # applies AveCPUFreq's magnitude suffix to a kHz base in some code
            # paths and a Hz base in others, so the string is ambiguous by a
            # factor of 1000 -- `duration.parse_cpu_freq` resolves it by taking
            # whichever reading lands in a plausible clock range, and drops the
            # value entirely when neither does.
            #
            # Both text surfaces spend `cpu_freq_hz` (render.py: "avg clock").
            # This payload emitted only the string, so of 20,550 real jobs
            # carrying the field, 17,503 published a figure that reads 1000x low
            # -- "3.00M" for a part running at 3.00 GHz -- and 2,061 published
            # one the tool itself refuses to display as uninterpretable. A
            # machine surface that hands back the ambiguity the tool resolved is
            # not exhaustive, whatever this docstring claims.
            "frequency": job.cpu_freq or None,
            "frequency_hz": job.cpu_freq_hz,
            "straggler_spread": job.straggler_spread,
            "slowest_task_node": job.slowest_task[0] or None,
            "slowest_task_id": job.slowest_task[1] or None,
            "core_hours": job.core_hours,
        },
        "memory": {
            # Per node, which is the ceiling a cgroup enforces and what --mem
            # sets. AllocTRES reports the allocation total; both are emitted so a
            # consumer never has to guess which convention a figure is in.
            "limit_bytes": job.mem_limit_bytes,
            "limit_total_bytes": job.mem_limit_total_bytes,
            "req_mem_raw": job.req_mem_raw,
            "peak_bytes": job.max_rss,
            "peak_node": job.max_rss_node or None,
            "peak_task": job.max_rss_task or None,
            "average_bytes": job.ave_rss,
            "task_imbalance": job.rss_task_imbalance,
            "step_spread": job.rss_step_spread,
            "utilization": job.mem_utilization,
            "virtual_bytes": job.max_vmsize,
            "virtual_to_resident": job.vmsize_to_rss,
            "page_faults": job.max_pages,
            # MaxRSS sums RSS across the process tree and can exceed the cgroup
            # limit; when it does, it is not a working set and must not be used
            # to size --mem.
            #
            # A running job is the second way this can be false, and it used to
            # read `true` on a figure that was 0.5% of the truth: `sacct` had not
            # flushed the live steps and the peak came from a 1-second monitoring
            # step. Now the figure comes from `sstat` where that is available --
            # and either way a job that is still going has not reached its peak,
            # so nothing here may call the reading final.
            "peak_trustworthy": bool(
                not job.in_progress
                and not (job.mem_limit_bytes and job.max_rss and job.max_rss > job.mem_limit_bytes)
            ),
            # Why, rather than only whether: three states, and only one of them
            # asks the reader to go and look elsewhere.
            # A fourth state, because three collapsed two different facts into
            # one word. `sstat` is owner-only, so for another user's running job
            # the live figure is not late -- it is unavailable to this reader,
            # permanently. Under --all-users that is the majority of live rows.
            "peak_source": (
                None
                if job.max_rss is None
                else "sstat (live)"
                if job.peak_is_live_reading
                else "sacct (final)"
                if not job.in_progress
                else "sacct (unflushed, sstat is owner-only)"
                if job.peak_unmeasurable_by_permission
                else "sacct (unflushed)"
            ),
            # `peak_source` names where a figure came FROM, so it is null when
            # there is no figure -- which for a running job is the ordinary case,
            # since its live steps carry no flushed MaxRSS. That left the reader a
            # null with no account of itself, so the reason is its own field
            # rather than an overload of the other one.
            "peak_unavailable_reason": (
                None
                if job.max_rss is not None
                else "foreign_owner_sstat_is_owner_only"
                if job.peak_unmeasurable_by_permission
                else "in_progress_unflushed"
                if job.in_progress
                else "not_gathered"
            ),
            "job_in_progress": job.in_progress,
        },
        "filesystem": {
            "read_bytes": job.read_bytes,
            "write_bytes": job.write_bytes,
            "total_bytes": job.io_bytes,
            "rate_bytes_per_second": job.io_rate,
        },
        "gpu": {
            "count": job.gpu_count,
            "gpu_hours": job.gpu_hours,
            # Real values wherever the site runs AutoDetect=nvml, which is what
            # makes Slurm gather gres/gpuutil and gres/gpumem; null otherwise,
            # never 0 -- an unmeasured card is not an idle one.
            "utilization": job.gpu_utilization,
            "memory_peak_bytes": job.gpu_mem_peak_bytes,
        },
        "energy_joules": job.energy_joules,
        "log": log_path,
        # What was tried and why it did not work, when nothing was found. The text
        # view has always printed the recorded path; the payload collapsed every
        # miss to `null`, so a consumer could not see which path was attempted let
        # alone whether it was absent or merely unreadable. Absent entirely when a
        # log *was* found -- `log` already answers that -- and when the cluster
        # recorded no path at all, since there is then nothing to report.
        **_log_miss(job, log_path, no_logs),
        "steps": [
            {
                "step_id": s.step_id,
                "state": s.state,
                "exit_code": s.exit_code,
                "signal": s.signal,
                "elapsed_seconds": s.elapsed,
                "total_cpu_seconds": s.total_cpu,
                "user_cpu_seconds": s.user_cpu,
                "system_cpu_seconds": s.system_cpu,
                "ave_cpu_seconds": s.ave_cpu,
                "min_cpu_seconds": s.min_cpu,
                "min_cpu_node": s.min_cpu_node or None,
                "min_cpu_task": s.min_cpu_task or None,
                "cpu_frequency": s.ave_cpu_freq or None,
                "max_rss_bytes": s.max_rss,
                "max_rss_node": s.max_rss_node or None,
                "max_rss_task": s.max_rss_task or None,
                "ave_rss_bytes": s.ave_rss,
                "max_vmsize_bytes": s.max_vmsize,
                "max_vmsize_node": s.max_vmsize_node or None,
                "ave_vmsize_bytes": s.ave_vmsize,
                "max_pages": s.max_pages,
                "max_pages_node": s.max_pages_node or None,
                "ave_pages": s.ave_pages,
                "read_bytes": s.read_bytes,
                "write_bytes": s.write_bytes,
                "max_disk_read_bytes": s.max_disk_read,
                "max_disk_read_node": s.max_disk_read_node or None,
                "ave_disk_read_bytes": s.ave_disk_read,
                "max_disk_write_bytes": s.max_disk_write,
                "max_disk_write_node": s.max_disk_write_node or None,
                "ave_disk_write_bytes": s.ave_disk_write,
                "tres_usage_in_max": s.tres_in_max or None,
                "tres_usage_in_max_node": s.tres_in_max_node or None,
                "tres_usage_in_ave": s.tres_in_ave or None,
                "gpu_utilization": s.gpu_utilization,
                "gpu_memory_bytes": s.gpu_mem_bytes,
                "consumed_energy": s.consumed_energy,
                "ntasks": s.ntasks,
                "nnodes": s.nnodes,
                "node_list": s.node_list or None,
            }
            for s in job.steps
        ],
        "findings": [
            {
                "severity": f.severity,
                "code": f.code,
                "title": f.title,
                "evidence": f.evidence,
                "action": f.action,
            }
            for f in sorted(verdict.findings, key=lambda f: severity_rank(f.severity))
        ],
    }


def _has_terminal(stdin=None, stdout=None) -> bool:
    """Whether both ends the dashboard needs are attached to a terminal.

    Both, not just stdout: Textual reads keys from stdin, so `slurmpast </dev/null`
    paints a screen nobody can drive or quit. Written defensively because this
    decides whether the process can hang -- a stream can be ``None`` under
    ``pythonw`` and a closed one raises ``ValueError`` from ``isatty()``, and
    either way the answer wanted here is "no terminal", not a traceback.

    The one pre-existing ``isatty`` call in this package (`report.Style`) only
    chooses colours, so nothing was guarding the decision to launch the app.
    """
    for stream in (sys.stdin if stdin is None else stdin, sys.stdout if stdout is None else stdout):
        try:
            if not stream.isatty():
                return False
        except (AttributeError, ValueError):
            return False
    return True


def _encoding_cannot_draw(stream=None) -> bool:
    """Whether this stdout can carry the glyphs the reports are drawn with.

    Not a question about the terminal's *font* -- that is what `--ascii` is for --
    but about its **encoding**, which is a different failure and a much louder one.
    Under a valid non-UTF-8 locale every box, block, arrow and em dash is
    unencodable, and Python raises rather than degrading: four of the five text
    modes exited 1 with **zero bytes** on stdout.

    Worth being exact about why `LC_ALL=C` is not the case that bites. PEP 538/540
    coerce `C`/`POSIX` to UTF-8, so the setting people type in job scripts is
    rescued automatically. A real 8-bit locale -- `en_US`, `en_US.iso88591`, three
    of the six on the reporting host, and `LANG=en_US` is an ordinary thing to
    find in a site profile -- gets no coercion, because it is a legitimate locale
    and Python honours it.
    """
    encoding = getattr(stream or sys.stdout, "encoding", None)
    if not encoding:
        return False
    try:
        # One glyph from each family the reports use: box drawing, block shading,
        # the arrow every action line starts with, and the em dash in the prose.
        "\u2502\u2588\u2192\u2014".encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return True
    return False


def _make_output_encode_safe():
    """Never let an unencodable character cost the whole report.

    `--ascii` fixes the *decoration*; it cannot fix the *data*. A job name is
    arbitrary user-controlled text arriving from Slurm, and one job named
    `\u30d5\u30a1\u30a4\u30eb` anywhere in the queried window took down every text mode
    for every user who queried that window -- including users who did not submit
    it, once `--all-users` is in play. There is no flag that can help, because the
    character is the answer rather than the chrome.

    `backslashreplace` over `replace`: a job name rendered `\\u30d5...` is ugly and
    reversible, where `????` is ugly and lossy, and the reader of a post-mortem is
    someone who may need to match the name against a submission script.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:  # pragma: no cover - a replaced stream in a test
            continue
        # A detached or closed stream cannot be reconfigured, and failing to make
        # output safer is not a reason to fail the run.
        with contextlib.suppress(OSError, ValueError):
            reconfigure(errors="backslashreplace")


def main(argv=None) -> int:
    """Entry point.

    A thin wrapper for one reason: Ctrl-C is a normal way to stop this, so it is
    reported as one. Without it a SIGINT during the `sacct` query escaped as a
    `KeyboardInterrupt` traceback out of `subprocess.communicate`'s selector poll
    -- and this tool is the likeliest of the family to be interrupted, because its
    query timeout is 300 s by design (an accounting database can genuinely take
    minutes) where its siblings bound a live-controller call at 30-45 s. Five
    minutes of silence is exactly when a user reaches for Ctrl-C.

    130 is the shell's convention for "terminated by SIGINT", so a wrapper script
    can tell a cancellation from a failure.

    SIGPIPE gets the same treatment for the same reason. `slurmpast --json | jq`
    and `slurmpast --plain | head` are how a long report actually gets read, and
    Python's default disposition turns that into noise: it ignores SIGPIPE, so
    the write raises, the interpreter flushes a closed stdout at shutdown and
    prints "Exception ignored in: <_io.TextIOWrapper name='<stdout>'>
    BrokenPipeError: [Errno 32] Broken pipe" *after* the output the reader
    wanted -- then exits 120, which is neither a convention nor a decision.
    Restoring the default makes this behave like every other Unix filter and
    like the rest of the family: nodetop restores it the same way, rapidu and
    slurmwatch catch the error and exit 0. This was the one tool of the four
    with no handling at all.
    """
    if hasattr(signal, "SIGPIPE"):  # POSIX only; Windows has no SIGPIPE
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    try:
        return _main(argv)
    except KeyboardInterrupt:
        # A newline first: the ^C is echoed at the cursor, so without it the next
        # shell prompt lands mid-line.
        sys.stderr.write("\n")
        return 130


def _main(argv=None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(_glue_negative_values(raw))
    if args.all_users and args.user:
        # Contradictory rather than ordered: silently letting one win means the
        # output is scoped to something the reader did not ask for, and nothing on
        # screen says which of the two flags was ignored.
        parser.error("--all-users and -u/--user ask for different things; pick one")
    # The same argument, for the spelling a shell produces by accident. `-u ''`
    # was accepted and fell through to the current user, so output identical to
    # passing no `-u` at all -- and a script doing `-u "$WHO"` with `WHO` unset
    # reported the caller's OWN history under someone else's name, confidently and
    # at rc=0. That is the failure the line above exists to prevent, arriving by a
    # different route: the report is scoped to something the reader did not ask
    # for and nothing on screen says so.
    for flag, value in (("-u/--user", args.user), ("-p/--partition", args.partition)):
        if value is not None and not str(value).strip():
            parser.error(
                '%s was given an empty value; drop the flag to mean "yours" '
                "(or --all-users for everyone), or check the variable you passed" % flag
            )
    args.since = normalize_time_spec(args.since)
    args.until = normalize_time_spec(args.until)
    if args.demo:
        # A synthetic job wrote no log, so anything the search turns up is a real
        # file belonging to a real run on this machine -- and its text feeds
        # `diagnose`, which then reports a stranger's NCCL fault or import error as
        # a finding on a fabricated job. Measured here: 39 of the 58 demo jobs were
        # handed a file out of the user's own work directory, four of them changing
        # the verdict, and a traceback dropped in the current directory turned up
        # under "GPU ran out of memory" on job 5100002. It also made `--demo`
        # machine-dependent again, which is the exact thing DEMO_SITE was added to
        # stop: the demo has to render the same on a login node and a laptop.
        args.no_logs = True

    # After the `--demo` assignment above, so `--demo --log-dir X` is covered by
    # the same line: either way `--log-dir` was asked for and will not be used.
    #
    # A warning rather than an error, matching how the sibling package words this
    # exact shape ("--append has no effect without --log; ignoring"): `--no-logs`
    # is an unambiguous off switch, so there is a clear winner and nothing to pick
    # between. And not silent, unlike the `--plain` degrade below: that one is
    # silent because `--plain` carries the same information, so the fallback did
    # what was wanted -- here a request for extra search directories is simply
    # dropped, which is not what was wanted at all.
    if args.no_logs and args.log_dir:
        why = "--demo" if args.demo else "--no-logs"
        sys.stderr.write(
            "slurmpast: --log-dir has no effect with %s (no logs are read); "
            "ignoring %s\n" % (why, ", ".join(args.log_dir))
        )

    # The same shape and the same wording, one flag over. `--demo` replaces the
    # window with the tape's own -- both render sites read
    # `"synthetic demo data" if args.demo` -- and nulls `since` on the way into
    # the query (`since=None if (args.demo or args.until)`), so a window asked
    # for here is dropped exactly as `--log-dir` was. Measured: `--demo
    # -S now-1days` and `--demo -S now-365days` render byte-identical output to
    # `--demo` alone. `--all-users` is the same by a different route: the tape is
    # 58 jobs belonging to one synthetic user, so there is nobody to widen to.
    #
    # Compared against the parser's OWN default rather than truthiness, because
    # `--since` defaults to `now-7days` and is always set -- so a truthiness test
    # would warn on every `--demo` run and say nothing about what the caller
    # typed. `args.since` is already normalised by the line above, so the
    # default is normalised too or the comparison fires on spelling alone.
    if args.demo:
        dropped = [
            flag
            for flag, value, default in (
                ("-S/--since", args.since, normalize_time_spec(parser.get_default("since"))),
                ("-E/--until", args.until, normalize_time_spec(parser.get_default("until"))),
            )
            if value != default
        ]
        if args.all_users:
            dropped.append("--all-users")
        if dropped:
            sys.stderr.write(
                "slurmpast: %s has no effect with --demo (a fixed tape of one "
                "user's jobs); ignoring\n" % ", ".join(dropped)
            )

    style = report.Style(enabled=False if args.no_color else None)
    sacct = Sacct(cache=not args.no_cache)

    # A dashboard needs a terminal on both ends, and without this the most
    # ordinary thing anyone does with a report -- redirect it to a file -- hung
    # forever. Measured on midway2: `slurmpast -S now-2days > report.txt` wrote
    # 26,514 bytes of escape sequences into the file, entered the alternate
    # screen, and then waited for a keypress a redirect can never deliver; killed
    # at 20 s with rc=137, and identical under `| cat`. Under cron or CI the job
    # simply never finishes.
    #
    # `--mouse` is consumed at exactly one place -- `tui.run(mouse=args.mouse)`
    # -- so in every text mode it is a flag that was typed and will not be used.
    # Same rule and same wording as `--log-dir` above; `--steps` a few lines
    # below takes the stricter remedy for the same class, and its comment says
    # why: "It used to evaporate, so a caller who forgot the id got the ordinary
    # overview and no hint that the flag they typed did nothing." A warning
    # rather than an error here because the report asked for is still exactly
    # what arrives -- only the mouse preference is moot.
    #
    # Read BEFORE the `_has_terminal()` degrade below, and placed above it for
    # that reason -- measured, because the first version sat AFTER it and a
    # plain pipe (`--demo --mouse | cat`) warned about a mouse the caller had
    # not asked to drop. That degrade
    # sets `args.plain` itself and is silent for a reason it states ("a note on
    # stdout would corrupt the very file being written, and one on stderr would
    # be noise in every CI log for a fallback that did what was wanted") -- so a
    # redirect must not start warning about a mouse nobody asked to drop. Only an
    # explicit text mode counts, which is what `args.plain` still means here.
    #
    # Components mirror `wants_text` below and take the section names from
    # `SECTION_ORDER`, so a sixth section reaches both or neither.
    if args.mouse and (
        args.plain
        or args.json
        or args.job_ids
        or any(getattr(args, name) for name in SECTION_ORDER)
    ):
        sys.stderr.write(
            "slurmpast: --mouse has no effect without the dashboard (it is a "
            "text mode here); ignoring\n"
        )

    # Degrading is right rather than erroring: `--plain` carries the same
    # information, so a redirect should just work. Silently, too -- a note on
    # stdout would corrupt the very file being written, and one on stderr would
    # be noise in every CI log for a fallback that did what was wanted.
    if not _has_terminal():
        args.plain = True

    # Before anything is rendered. Two separate problems with one cause: the
    # package's own glyphs, which `--ascii` already has a switch for, and the
    # job names Slurm hands back, which it does not.
    _make_output_encode_safe()
    if not args.ascii and _encoding_cannot_draw():
        args.ascii = True

    # Reading order for composed sections, not the order the branches happen to
    # sit in below: the rollup first, then what recurs across runs, then the two
    # screens that attribute it.
    sections: dict[str, str] = {}
    requested = [name for name in SECTION_ORDER if getattr(args, name)]

    # `--json` emits one document per section and there is no defined way to
    # concatenate two of them, so composing is a text-only affordance. Rejecting
    # is right here rather than picking one, which is the behaviour being fixed.
    if args.json and len(requested) > 1:
        parser.error(
            "--json takes one section at a time; %s ask for %d documents. "
            "Run them separately, or drop --json to get all of them as text."
            % (", ".join("--" + name for name in requested), len(requested))
        )
    # `--steps` is per-job accounting: `--help` says "on a named job", and without
    # one there is nothing to break down. It used to evaporate, so a caller who
    # forgot the id got the ordinary overview and no hint that the flag they typed
    # did nothing.
    if args.steps and not args.job_ids:
        parser.error(
            "--steps breaks a named job into its steps, so it needs a job id: "
            "try `slurmpast <jobid> --steps`."
        )

    wants_text = (
        args.plain
        or args.json
        or args.overview
        or args.patterns
        or args.nodes
        or args.sizing
        or args.job_ids
    )

    if not wants_text:
        # Dashboard. The loader runs inside the app's worker thread so the
        # window paints before the query returns.
        from . import tui

        window = "synthetic demo data" if args.demo else humanize_window(args.since, args.until)

        def load(since=None):
            """Query for one window. ``w`` in the app calls back with a new one.

            A copy of the parsed arguments rather than a mutation of them, so a
            re-query cannot leave the namespace describing a window other than
            the one on screen.
            """
            if since is None:
                return _load(args, sacct)
            scoped = copy.copy(args)
            scoped.since = since
            return _load(scoped, sacct)

        return tui.run(
            load,
            window=window,
            ascii_mode=args.ascii,
            no_logs=args.no_logs,
            log_dirs=args.log_dir,
            mouse=args.mouse,
            # No window to cycle over synthetic data, and an explicit -E pins the
            # range the user asked for -- overwriting it from a preset would
            # silently discard half of their request.
            since=None if (args.demo or args.until) else args.since,
        )

    try:
        jobs = _load(args, sacct)
    except SacctError as exc:
        sys.stderr.write("slurmpast: %s\n" % exc)
        return 2

    window = "synthetic demo data" if args.demo else humanize_window(args.since, args.until)
    history = History(jobs, window=window)

    if args.nodes:
        if args.json:
            from .nodes import dominant_workload, node_table

            workload = (
                None
                if args.all_workloads
                else dominant_workload(history.usable_jobs, metric=args.metric)
            )
            print(
                json.dumps(
                    {
                        "slurmpast": __version__,
                        **_parse_warnings(sacct),
                        "window": history.window,
                        "nodes": node_table(
                            history.usable_jobs, workload=workload, metric=args.metric
                        ),
                    },
                    indent=2,
                )
            )
            return 0
        else:
            sections["nodes"] = report.render_nodes(
                history,
                metric=args.metric,
                controlled=not args.all_workloads,
                style=style,
                ascii_mode=args.ascii,
            )

    if args.sizing:
        from .sizing import recommend

        if args.json:
            print(
                json.dumps(
                    {
                        "slurmpast": __version__,
                        **_parse_warnings(sacct),
                        "window": history.window,
                        "workloads": [
                            {
                                "name": g.name,
                                "partition": g.partition,
                                "runs": g.total,
                                "advice": [a._asdict() for a in recommend(g.jobs)],
                            }
                            # Through the same sort the text view now uses, for the
                            # reason `--overview --json` already goes through it: a
                            # script asking for one order must not silently get
                            # another.
                            for g in sort_groups(history.groups, args.sort)
                        ],
                    },
                    indent=2,
                )
            )
            return 0
        else:
            sections["sizing"] = report.render_sizing(
                history, style=style, limit=args.limit, sort=args.sort, ascii_mode=args.ascii
            )

    if args.patterns:
        if args.json:
            print(
                json.dumps(
                    {
                        "slurmpast": __version__,
                        **_parse_warnings(sacct),
                        "window": history.window,
                        "summary": history.stats,
                        "findings": [f._asdict() for f in history.patterns],
                    },
                    indent=2,
                )
            )
            return 0
        else:
            sections["patterns"] = report.render_patterns(
                history, style=style, ascii_mode=args.ascii
            )

    if args.overview:
        if args.json:
            print(
                json.dumps(
                    {
                        "slurmpast": __version__,
                        **_parse_warnings(sacct),
                        "window": history.window,
                        "summary": history.stats,
                        "workloads": [
                            {
                                "name": g.name,
                                "partition": g.partition,
                                # How many real job names the folded pattern
                                # covers. Off the table on purpose -- it read as
                                # clutter beside the name -- but it is a real
                                # measurement, so it is emitted rather than lost.
                                "distinct_names": g.distinct_names,
                                "runs": g.total,
                                "completed": g.completed,
                                # The overview shows only the union; the breakdown
                                # stays here so nothing measured is lost.
                                "problems": g.problems,
                                "failed": g.failed,
                                "cancelled": g.cancelled,
                                "noop": g.noop,
                                "gpu_hours": g.gpu_hours,
                                # The GPU-hours behind `problems`, on the same
                                # grounds as the breakdown above: FLAGGED is a run
                                # count and says nothing about what the runs cost,
                                # so two workloads whose flagged runs burned 2 and
                                # 90 GPU-hours emitted byte-identical objects here.
                                # This was the one measured field of `GroupStats`
                                # that reached no surface at all.
                                "wasted_gpu_hours": g.wasted_gpu_hours,
                                "core_hours": g.core_hours,
                                "severity": g.severity,
                                "last_seen": g.last_seen,
                            }
                            # Through the same sort the table uses. Iterating
                            # `history.groups` raw meant `--sort name` and `--sort
                            # cost` returned byte-identical JSON while the plain
                            # text visibly reordered -- a script asking for one
                            # order silently got the other.
                            for g in sort_groups(history.groups, args.sort)
                        ],
                    },
                    indent=2,
                )
            )
            return 0
        else:
            sections["overview"] = report.render_overview(
                history, style=style, limit=args.limit, sort=args.sort, ascii_mode=args.ascii
            )

    if sections:
        # Every section the caller asked for, in one fixed reading order --
        # summary, then the cross-run findings, then the two that attribute them.
        # Each `if` above used to `return 0`, so `--overview --patterns` printed
        # patterns alone and dropped the overview without a word, and which one
        # survived was an internal branch order nobody could see: `--patterns
        # --nodes` gave nodes, `--overview --sizing` gave sizing. Composing is
        # what the default plain report already does with its own sections, so
        # asking for two of them by name has an obvious meaning.
        print("\n\n".join(sections[name] for name in SECTION_ORDER if name in sections))
        return 0

    # Per-job. Explicit ids get full detail; a bare --plain/--failed gets a list
    # plus the overview, because 6,574 full post-mortems is not an answer.
    if args.job_ids:
        matches = jobs
    else:
        matches = filter_jobs(history.usable_jobs, "failed" if args.failed else "problem")
        matches.sort(key=lambda j: (j.start or j.submit or "", j.job_id), reverse=True)
    # Truncated for the work that costs something per job -- resolving logs and
    # diagnosing. `matches` stays whole so the renderer can say what it left out.
    #
    # Only on the *list* branch. `--limit` is documented as "rows in plain output",
    # and ids the caller typed out are not rows the tool chose to show them: `-n`
    # defaults to 25, so `slurmpast <30 ids>` printed 25 post-mortems, said nothing
    # about the other five, and -- because the exit code is computed only over what
    # was examined -- could not report a CRITICAL on ids 26-30 at all. Nor could
    # `--json`, which returned a 25-entry array for a 30-id query. Every other
    # truncation here names its tail (`History.tail_summary`, `nodes.excluded_tail`,
    # `render_list`'s "... N more"); on this branch no renderer ever does, because
    # a post-mortem block has nowhere to put such a line.
    targets = matches if args.job_ids else matches[: args.limit]
    # The node note's population, decided once for both renderings below --
    # see `_node_history`. On the `-j` branch this is a second `sacct` query;
    # everywhere else it is `history` itself and costs nothing.
    node_history = _node_history(args, sacct, history, targets)

    if args.json:
        payload = []
        resolved = _logs_for_all(targets, args)
        json_critical = False
        for job in targets:
            log_path, log_text, _inferred = resolved[job.job_id]
            verdict = diagnose(job, log_text=log_text, node_note=_node_note(job, node_history))
            payload.append(_job_json(job, log_path, verdict, no_logs=args.no_logs))
            json_critical |= any(f.severity == "critical" for f in verdict.findings)
        body = {
            "slurmpast": __version__,
            **_parse_warnings(sacct),
            "window": history.window,
            # `findings_jobs` beside the clipped array, because without it the clip
            # is undetectable: `summary.jobs` counts *every* job in the window, so
            # `len(jobs) < summary.jobs` is the normal state whether anything was
            # dropped or not. A monitoring consumer polling this payload would lose
            # older findings silently as an account accumulates more than `-n` of
            # them, and the JSON would look exactly as complete as before.
            #
            # The mirror image of the `--sizing` defect fixed above: there the text
            # view collapsed what the JSON carried in full, here the JSON is the
            # lossy one. Same cause -- a truncation decided at render time with no
            # field recording that it happened.
            "summary": {
                **history.stats,
                "findings_jobs": len(matches),
                "findings_jobs_shown": len(payload),
            },
            "jobs": payload,
        }
        if not args.job_ids:
            # The cross-run findings decide the exit code on this path, exactly as
            # they do for the text rendering below, so they have to be in the
            # payload: an exit code pointing at data the caller cannot see is worse
            # than no exit code. The --overview JSON has always carried them.
            body["patterns"] = [f._asdict() for f in history.patterns]
            # Overwrite, not `|=`, and that is the contract rather than a slip:
            # a scan across a whole cluster's jobs would exit 1 almost always,
            # which makes the code useless as a signal. The per-job accumulation
            # above is real work whose result is deliberately dropped here, so
            # `--strict` folds it back in for the caller who wants the other
            # reading -- `... --json || alert` is the obvious wrapper and it is
            # silent on exactly the mode anyone would automate.
            patterns_critical = any(f.severity == "critical" for f in history.patterns)
            json_critical = (json_critical and args.strict) or patterns_critical
        print(json.dumps(body, indent=2, default=str))
        # `--json` used to `return 0` unconditionally, so the one mode a script
        # actually checks `$?` from was the one that never reported severity, while
        # the same query rendered as text exited 1. (The --overview/--patterns/
        # --nodes/--sizing views do always exit 0, deliberately and by test -- they
        # report rather than judge. This path judges.)
        return 1 if json_critical else 0

    worst_critical = False
    if args.job_ids:
        resolved = _logs_for_all(targets, args)
        for job in targets:
            log_path, log_text, inferred = resolved[job.job_id]
            text, verdict = report.render_job(
                job,
                log_path=log_path,
                log_text=log_text,
                node_note=_node_note(job, node_history),
                style=style,
                show_steps=args.steps,
                ascii_mode=args.ascii,
                log_inferred=inferred,
                no_logs=args.no_logs,
            )
            print(text)
            worst_critical |= any(f.severity == "critical" for f in verdict.findings)
    else:
        print(
            report.render_overview(
                history, style=style, limit=args.limit, sort=args.sort, ascii_mode=args.ascii
            )
        )
        if matches:
            # The whole list, sliced by the renderer. Pre-slicing it here made
            # `render_list`'s own "… N more (raise --limit)" line unreachable, so
            # `-n 5` showed 5 of 28 problem jobs and said nothing about the other
            # 23 -- while the workload table directly above it named its own tail.
            print(report.render_list(matches, style=style, limit=args.limit, ascii_mode=args.ascii))
            print("")
        print(report.render_patterns(history, style=style, ascii_mode=args.ascii))
        # `worst_critical` is False here: the per-job loop above runs only on the
        # `args.job_ids` branch, so unlike the JSON path there is nothing to fold
        # in. `--strict` therefore reads the findings this branch actually
        # rendered -- the problem list it just printed -- so the two paths agree
        # under the flag exactly as they do without it.
        strict_jobs = args.strict and any(
            f.severity == "critical"
            for job in targets
            for f in diagnose(job, node_note=_node_note(job, node_history)).findings
        )
        worst_critical = strict_jobs or any(f.severity == "critical" for f in history.patterns)

    return 1 if worst_critical else 0


if __name__ == "__main__":
    sys.exit(main())
