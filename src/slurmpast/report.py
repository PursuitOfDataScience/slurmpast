"""Plain-text output, for pipes, CI and terminals where a TUI is wrong.

Everything the dashboard shows is reachable here, because a post-mortem you
cannot paste into a ticket is half a tool.
"""

from __future__ import annotations

import os
import re
import shutil
import sys

from .diagnose import diagnose
from .duration import format_bytes, format_duration, format_percent
from .index import GPU_CORE_EQUIVALENT, SORTS, History, sort_groups, sort_label
from .model import severity_rank
from .nodes import (
    MIN_SAMPLES,
    compress_nodelist,
    dominant_workload,
    excluded_tail,
    node_table,
    suggest_exclude,
)
from .render import (
    HOURS_PAIR_LABEL,
    JOB_COLUMNS,
    OVERVIEW_COLUMNS,
    PAIR_LABEL_WIDTH,
    PAIR_VALUE_WIDTH,
    STEP_COLUMNS,
    cores_text,
    cpu_only_columns,
    fit_columns,
    held_back_note,
    hours_pair_text,
    hours_text,
    job_sections,
    pair_rows,
    resource_rows,
    stamp_short,
    text_table,
    wrap,
)
from .sizing import recommend, sbatch_lines

_CODES = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "red": "\033[31m",
    "yellow": "\033[33m",
    "green": "\033[32m",
    "cyan": "\033[36m",
    "grey": "\033[90m",
}
_SEV = {"critical": ("red", "FAIL"), "warning": ("yellow", "WARN"), "info": ("cyan", "INFO")}
_STATE_COLOR = {
    "COMPLETED": "green",
    "FAILED": "red",
    "TIMEOUT": "red",
    "OUT_OF_MEMORY": "red",
    "NODE_FAIL": "red",
    "BOOT_FAIL": "red",
    # Killed for exceeding a time it was given, exactly as TIMEOUT is.
    "DEADLINE": "red",
    "CANCELLED": "yellow",
    # Neither red nor absent: the scheduler took the allocation back, so the run is
    # over without the job having done anything wrong. Falling through to the
    # default rendered it as unremarkable next to a red finding blaming the user's
    # own code for the CPU time preemption cost them.
    "PREEMPTED": "yellow",
}


# How wide a plain table may be. Down a pipe there is no terminal to ask, and 100
# is what a pasted table has to survive in -- a ticket comment, a code review, a
# chat message. No upper cap: fit_columns leaves width no column needs unused, so
# a wide terminal gets more columns rather than a stretched table, and a cap would
# mean --plain could never show a column the dashboard does.
PLAIN_MIN_WIDTH = 60
PLAIN_FALLBACK_WIDTH = 100


_PLAIN_INDENT = "  "
# text_table puts a single space between cells; fit_columns charges its padding
# per column rather than per gap, so passing 1 leaves one cell spare. Passing the
# dashboard's 2 instead cost 13 cells on a 13-column table and dropped NODE off
# the job list for space that was never used.
_PLAIN_GAP = 1


def _plain_width():
    return max(PLAIN_MIN_WIDTH, shutil.get_terminal_size((PLAIN_FALLBACK_WIDTH, 24)).columns)


_ANSI = re.compile(r"\033\[[0-9;]*m")


def _visible_len(text):
    """Width on screen. An ANSI wrapper is nine characters the terminal does not
    draw, so len() is the wrong ruler for anything already styled."""
    return len(_ANSI.sub("", text))


def _titled(title, body, style):
    """A titled block whose rule spans its own widest line.

    The rules were hardcoded -- 78, 92, 114, 132 -- so each one was either short
    of its content or hanging past it, and the two widest overran a 100-column
    terminal outright.

    Measured per physical line: some entries carry their own newline, and taking
    len() of the whole entry made the sizing rule 121 cells over 88 of content.
    Capped at the terminal, because a rule that overruns it wraps to a stray
    second line of dashes -- the one thing on screen that cannot be read as
    anything but a rendering fault.
    """
    reach = max([_visible_len(part) for line in body for part in line.split("\n")] + [len(title)])
    return [style(title, "bold"), style("-" * min(reach, _plain_width()), "grey"), *body]


def _prose_width(indent):
    """Wrap width for an indented paragraph, from the actual terminal.

    These were hardcoded at 72, 82 and 84, so a finding hard-broke mid-sentence
    two thirds of the way across a wide terminal and overran a narrow one.
    """
    return max(40, _plain_width() - indent)


def _plain_layout(spec, content=None, indent=_PLAIN_INDENT):
    return fit_columns(spec, _plain_width() - len(indent), padding=_PLAIN_GAP, content=content)


# Two label/value pairs, four cells of indent and two between them.
_PAIRED_LINE_WIDTH = 4 + 2 * (PAIR_LABEL_WIDTH + 1 + PAIR_VALUE_WIDTH) + 2


def _pair_value_width():
    """``PAIR_VALUE_WIDTH``, or 0 to force one pair per line on a narrow terminal.

    pair_rows treats any value longer than this as needing its own line, so zero
    unpairs everything.
    """
    return PAIR_VALUE_WIDTH if _plain_width() >= _PAIRED_LINE_WIDTH else 0


class Style:
    def __init__(self, enabled=None, stream=None):
        stream = stream or sys.stdout
        if enabled is None:
            enabled = (
                hasattr(stream, "isatty") and stream.isatty() and not os.environ.get("NO_COLOR")
            )
        self.enabled = bool(enabled)

    def __call__(self, text, *names):
        if not self.enabled or not names:
            return text
        return "".join(_CODES.get(n, "") for n in names) + text + _CODES["reset"]


def render_job(
    job,
    log_path=None,
    log_text=None,
    node_note="",
    style=None,
    show_steps=False,
    ascii_mode=False,
    log_inferred=False,
):
    style = style or Style()
    verdict = diagnose(job, log_text=log_text, node_note=node_note)
    out = []
    state = job.base_state or "?"
    out.append(
        "%s %s  %s"
        % (
            style("job", "grey"),
            style(job.job_id, "bold"),
            style(state, _STATE_COLOR.get(state, "bold")),
        )
    )
    # The same at-a-glance block the dashboard leads with, so the two surfaces
    # read alike -- and so the sections below can drop these rows instead of
    # repeating every headline number a few lines later.
    out.append("")
    # flat=True: only the characters survive here, and an eighth-block tip with no
    # background behind it reads as a notch rather than as the end of a bar.
    for line in resource_rows(job, ascii_mode=ascii_mode, flat=True):
        out.append(line.plain)
    for title, rows in job_sections(job, summarized=True):
        out.append("")
        out.append(style("  " + title, "bold"))

        def cell(label, value, pad):
            flag = "red" if "ABOVE THE LIMIT" in value else None
            text = "%-*s" % (pad, value) if pad else value
            return "%-*s %s" % (PAIR_LABEL_WIDTH, label, style(text, flag) if flag else text)

        # Two pairs per line where both values are short -- same layout the
        # dashboard uses, so the two surfaces stay recognisable. On a terminal too
        # narrow to hold two, one per line: a paired row that wraps loses the
        # label/value alignment that made pairing readable in the first place.
        for group in pair_rows(rows, max_value=_pair_value_width()):
            if len(group) == 2:
                left = cell(group[0][0], group[0][1], PAIR_VALUE_WIDTH)
                out.append("    %s  %s" % (left, cell(group[1][0], group[1][1], 0)))
            else:
                out.append("    %s" % cell(group[0][0], group[0][1], 0))

    if show_steps and job.steps:
        out.append("")
        out.append(style("  steps", "bold"))
        indent = "    "
        layout = _plain_layout(
            STEP_COLUMNS,
            content={"STEP": max(len(s.step_id) for s in job.steps)},
            indent=indent,
        )
        out.extend(
            text_table(
                layout,
                [
                    {
                        "STEP": step.step_id,
                        "STATE": (step.state or "").split()[0] if step.state else "",
                        "ELAPSED": format_duration(step.elapsed),
                        "CPU": format_duration(step.total_cpu),
                        "MAXRSS": format_bytes(step.max_rss),
                        "READ": format_bytes(step.read_bytes),
                        "WROTE": format_bytes(step.write_bytes),
                    }
                    for step in job.steps
                ],
                style=style,
                indent=indent,
            )
        )

    out.append("")
    if log_path:
        # Say when the path was inferred from timing rather than read off a name:
        # a wrong log invents a cause, so the basis has to travel with it.
        note = (
            "  (matched by timing, not by name — verify before trusting it)" if log_inferred else ""
        )
        out.append("  %s %s%s" % (style("log", "grey"), log_path, style(note, "grey")))
    else:
        # One line, but which line depends on whether the cluster recorded a path.
        # Where one was recorded -- StdOut/StdErr from Slurm 24.05, the -o inside
        # SubmitLine from 21.08, or a --comment on any version -- the miss is "the
        # file has moved or been deleted" and naming the expected path is
        # actionable. With none of the three there is no such record anywhere a
        # post-mortem can reach (slurmctld forgets a job after MinJobAge), so the
        # path is genuinely unknowable and saying more would explain a limitation
        # the reader cannot act on.
        from .logs import recorded_paths

        expected = recorded_paths(job)
        if expected:
            detail = "none at %s — moved or deleted; --log-dir points at it" % expected[0]
        else:
            detail = "none found — --log-dir points at one"
        out.append("  %s %s" % (style("log", "grey"), style(detail, "grey")))
    out.append("")
    findings = sorted(verdict.findings, key=lambda f: severity_rank(f.severity))
    if not findings:
        out.append(style("  nothing to flag.", "green"))
    else:
        out.append(style("  findings", "bold"))
        for finding in findings:
            colour, tag = _SEV.get(finding.severity, ("bold", "----"))
            out.append("")
            out.append("  %s %s" % (style("[" + tag + "]", colour), style(finding.title, "bold")))
            for line in wrap(finding.evidence, _prose_width(8)):
                out.append("        " + line)
            for index, line in enumerate(wrap(finding.action, _prose_width(11))):
                out.append("        %s%s" % (style("-> " if index == 0 else "   ", "grey"), line))
    out.append("")
    return "\n".join(out), verdict


def render_overview(history: History, style=None, limit=25, sort="cost"):
    style = style or Style()
    stats = history.stats
    groups = sort_groups(history.groups, sort)
    shown = groups[:limit]

    out = []
    if history.window:
        # The window is the commonest explanation for "why are runs missing?",
        # so it belongs on screen rather than in the reader's memory.
        out.append("  window %s" % style(history.window, "bold"))
    # Both counts on one line: "233 jobs rolled up into 41 workloads" is one fact.
    line = "  %d jobs in %d workload%s · %s completed" % (
        stats["jobs"],
        len(history.groups),
        "" if len(history.groups) == 1 else "s",
        format_percent(stats["completion_rate"]),
    )
    # The total earns its place only as the denominator for the idle figure, and
    # only when that loss is material -- see History.idle_gpu_hours. A bare "783
    # GPU-hours" is a magnitude with nothing to compare it against; the
    # per-workload columns are where the resource numbers mean something.
    idle = history.idle_gpu_hours
    if idle is not None:
        # "total" and "of them" are both load-bearing: "783 GPU-hours" alone was
        # read as a per-job figure, and a bare "18 never computed" did not say 18
        # of what.
        hours = " · %.0f GPU-hours total" % idle[1]
        hours += style(", %.0f of them never used" % idle[0], "yellow")
        # Onto its own line when the pair will not fit. Three clauses joined
        # unconditionally reached 88 characters and wrapped on an 80-column
        # terminal, splitting the one figure this tool exists to report across a
        # fold. Dropping the leading separator is what makes the second line read
        # as a sentence rather than a fragment.
        if _visible_len(line + hours) <= _plain_width():
            line += hours
        else:
            out.append(line)
            line = "  " + hours.split("· ", 1)[1]
    out.append(line)
    # Both exclusions on one line. They are different -- an unterminated record
    # would report `now - start` as its elapsed, a record with no elapsed at all
    # cannot be rated -- and neither may be dropped silently, or the job count
    # goes unexplained. But two counts of skipped records do not earn two lines.
    kinds = []
    if stats["excluded_open_records"]:
        kinds.append("%d unterminated" % stats["excluded_open_records"])
    if stats.get("excluded_no_elapsed"):
        kinds.append("%d with no elapsed time" % stats["excluded_no_elapsed"])
    if kinds:
        out.append(style("  %s, excluded" % " and ".join(kinds), "grey"))

    spec = OVERVIEW_COLUMNS
    has_gpu = any(g.gpu_hours for g in history.groups)
    if not has_gpu:
        spec = cpu_only_columns(spec)
    # How to read the table, in one line, and only the halves that apply. This was
    # a bold title reading "workloads — ranked by resource use, one GPU-hour
    # counting as 16 CPU-hours" plus a third line explaining the "#". "By resource
    # use" was a phrase only this tool used, and the "#" line was three clauses
    # long. The facts are load-bearing -- without the exchange rate a row with
    # fewer CPU-hours outranking one with more looks arbitrary, and a bare
    # "att-speed-#" is the tool's private notation on screen -- so they stay, said
    # shorter. The dashboard puts the same two facts under `?`.
    notes = []
    if has_gpu:
        # "ordered by compute used" was appended whenever any workload had GPU
        # hours, without ever consulting `sort` -- so under `--sort name` it sat
        # above an alphabetical table and simply misdescribed it. The exchange rate
        # is load-bearing either way (a row with fewer CPU-hours outranking one with
        # more looks arbitrary without it), so under another sort the rate is kept
        # and only the ordering claim is corrected. The dashboard has always got
        # this right: tui.py appends "by <mode>" only when the mode is not the
        # default.
        if sort == SORTS[0][0]:
            claim = "ordered by compute used"
        else:
            claim = "ordered by %s" % sort_label(sort)
        notes.append("%s (1 GPU-hour = %d CPU-hours)" % (claim, GPU_CORE_EQUIVALENT))
    elif sort != SORTS[0][0]:
        notes.append("ordered by %s" % sort_label(sort))
    if any("#" in g.label for g in shown):
        notes.append('"#" stands for a name\'s digits')
    # RUNS, COMPLETED and FLAGGED read as a partition of the same runs and are not:
    # argonne35-pretrain showed 15 / 10 / 2 and was asked whether the math was
    # wrong. It was not -- the other 5 were cancelled, and 2 of those held GPUs
    # without computing, which is what FLAGGED counts. A clause explaining that was
    # tried here and reverted: test_the_summary_is_brief caps everything above the
    # table at four lines, deliberately, and this was a fifth. The count lives on
    # the workload screen instead, which is where a reader who is doing the
    # arithmetic goes next.
    if notes:
        # One line while it fits, one per line when it does not. Joined
        # unconditionally, the two clauses came to 86 characters and were the only
        # thing in the whole plain output that wrapped on an 80-column terminal --
        # and a wrapped grey caption reads as a rendering fault sitting directly
        # above a table that lines up perfectly.
        joined = "  " + " · ".join(notes)
        if _visible_len(joined) <= _plain_width():
            out.append(style(joined, "grey"))
        else:
            out.extend(style("  " + note, "grey") for note in notes)
    out.append("")
    layout = _plain_layout(
        spec, content={"JOB NAME": max((len(g.label) for g in shown), default=0)}
    )
    rows = []
    for index, group in enumerate(shown, start=1):
        colour = {"crit": "red", "warn": "yellow"}.get(group.severity)
        rows.append(
            {
                "#": str(index),
                "JOB NAME": (group.label, colour) if colour else group.label,
                "PARTITION": group.partition,
                "RUNS": str(group.total),
                "COMPLETED": str(group.completed or "-"),
                # One outcome column, and named for what it is -- runs this tool
                # flags -- rather than asserting they were problems. FAILED and
                # NEVER RAN overlapped, so two adjacent integers invited adding
                # them up.
                "FLAGGED": str(group.problems or "-"),
                # One cell, CPU first. Two adjacent hour columns read as more
                # separate than they are; the order and the header carry which is
                # which, so a piped or --no-color reading loses nothing.
                HOURS_PAIR_LABEL: hours_pair_text(group),
                "CPU-HOURS": hours_text(group.core_hours),
                "LAST RUN": (group.last_seen or "")[:10],
            }
        )
    out.extend(text_table(layout, rows, style=style))
    tail = history.tail_summary(limit)
    if tail:
        out.append(style("  … " + tail, "grey"))
    out.append("")
    return "\n".join(out)


def render_list(jobs, style=None, limit=40):
    """The same columns the dashboard's job list draws, sized to the terminal.

    This was laid out with hardcoded widths totalling 135 cells, so on a
    100-column terminal every row wrapped -- which is worse than dropping a
    column, because a wrapped table is not a table. The shared spec drops its
    least-load-bearing columns instead, in a declared order.
    """
    style = style or Style()
    shown = list(jobs)[:limit]
    layout = _plain_layout(
        JOB_COLUMNS,
        content={
            "NAME": max((len(j.name or "") for j in shown), default=0),
            "NODE": max((len(j.node_list or "") for j in shown), default=0),
        },
    )
    rows = []
    for index, job in enumerate(shown, start=1):
        state = job.base_state
        rows.append(
            {
                "#": str(index),
                "JOBID": job.job_id,
                "NAME": job.name or "",
                "STATE": (state, _STATE_COLOR.get(state, "bold")),
                # STARTED/ENDED matter here for the same reason they do in the
                # dashboard: a workload with hundreds of identically-named runs is
                # unnavigable without them.
                "STARTED": stamp_short(job.start) or "-",
                "ENDED": stamp_short(job.end) or "-",
                # "ELAPSED" beside "CPU TIME" did not say which was wall clock, and
                # a bare "CPU%" did not say what it was a percentage of -- it was
                # read as memory. Peak memory, the figure most post-mortems start
                # from, was absent entirely.
                "WALL TIME": format_duration(job.elapsed),
                "CPU TIME": format_duration(job.total_cpu),
                "CPUS BUSY": cores_text(job),
                "PEAK MEM": format_bytes(job.max_rss),
                "MEM%": format_percent(job.mem_utilization),
                "GPU": str(job.gpu_count or "-"),
                "NODE": job.node_list or "-",
            }
        )
    out = text_table(layout, rows, style=style)
    if len(jobs) > limit:
        out.append(style("  … %d more (raise --limit)" % (len(jobs) - limit), "grey"))
    return "\n".join(out)


def render_patterns(history: History, style=None):
    style = style or Style()
    body = [""]
    findings = history.patterns
    if not findings:
        body.append(style("  no cross-run pattern met its evidence threshold.", "green"))
        body.append("")
        return "\n".join(_titled("cross-run patterns", body, style))
    for finding in sorted(findings, key=lambda f: severity_rank(f.severity)):
        colour, tag = _SEV.get(finding.severity, ("bold", "----"))
        body.append("  %s %s" % (style("[" + tag + "]", colour), style(finding.title, "bold")))
        for line in wrap(finding.evidence, _prose_width(8)):
            body.append("        " + line)
        for index, line in enumerate(wrap(finding.action, _prose_width(11))):
            body.append("        %s%s" % (style("-> " if index == 0 else "   ", "grey"), line))
        body.append("")
    return "\n".join(_titled("cross-run patterns", body, style))


def render_nodes(history: History, metric="hang", controlled=True, style=None):
    style = style or Style()
    jobs = history.usable_jobs
    workload = dominant_workload(jobs, metric=metric) if controlled else None
    table = node_table(jobs, workload=workload, metric=metric)
    out = []
    if workload:
        out.append(
            "  controlled for workload: only %s counted %s"
            % (style(workload, "bold"), style("(placement is not random)", "grey"))
        )
    else:
        out.append(
            style(
                "  UNCONTROLLED — mixes workloads; a node that hosted one bad campaign "
                "will look cursed",
                "yellow",
            )
        )
    out.append(
        "  baseline %s over %d placements%s"
        % (
            format_percent(table["baseline"]),
            table["trials"],
            "; %d nodes below threshold omitted" % table["skipped_nodes"]
            if table["skipped_nodes"]
            else "",
        )
    )
    out.append("")
    # Two ways this table has nothing to say. Printing a column header over no
    # rows -- or eight rows of "0/N, 0.0%, inconclusive" -- is what made this
    # screen read as useless. A sentence is the answer in both cases.
    if not table["hits"]:
        out.append(
            "  No %s recorded%s in this window, so there is nothing to attribute to a node."
            % (metric + "s", " for %s" % workload if workload else "")
        )
        out.append("")
        return "\n".join(_titled("node reliability (%s rate)" % metric, out, style))
    if not table["rows"]:
        out.append(
            "  No node reached the %d placements a comparison needs — %d seen, all below it. "
            "A wider --since window is what fixes this." % (MIN_SAMPLES, table["skipped_nodes"])
        )
        out.append("")
        return "\n".join(_titled("node reliability (%s rate)" % metric, out, style))
    tested = table["tested_nodes"]
    out.append("  %-16s %9s %10s %20s  %s" % ("NODE", "N", "RATE", "95% CI", "VERDICT"))
    for row in table["rows"]:
        colour = {"worse": "red", "better": "green"}.get(row["verdict"])
        out.append(
            "  %-16s %9s %10s %20s  %s"
            % (
                row["node"],
                "%d/%d" % (row["bad"], row["trials"]),
                "%.1f%%" % (100 * row["rate"]),
                "%.1f - %.1f%%" % (100 * row["ci_low"], 100 * row["ci_high"]),
                style(row["verdict"], colour) if colour else row["verdict"],
            )
        )
    out.append("")
    excl = compress_nodelist(suggest_exclude(table))
    if excl:
        out.append("  worse than every other node, after correcting for %d tested:" % tested)
        out.append("    %s" % style("#SBATCH --exclude=" + excl, "bold"))
        out.append(
            style(
                "    not applied for you — excluding nodes trades availability for reliability.",
                "grey",
            )
        )
        # The line is capped, so it has to say when it is not the whole list.
        left_out = excluded_tail(table)
        if left_out:
            for line in wrap(
                "%d further node%s scored worse too, left off the line: excluding this many "
                "trades away more of the partition than a paste-ready suggestion should."
                % (left_out, "" if left_out == 1 else "s"),
                _prose_width(4),
            ):
                out.append("    " + style(line, "grey"))
    else:
        out.append(style("  no node is worse than the rest; nothing to exclude.", "grey"))
    # Said whenever an interval on screen disagrees with the verdict beside it.
    # About one row in twenty clears the baseline by chance, so in a table this size
    # such a row is expected -- and without this line it reads as the tool
    # contradicting its own CI column. Deliberately not a claim that these
    # particular intervals ARE chance: it says an interval alone is not enough when
    # this many nodes were tested, which is the part that is true of all of them.
    if table["held_back"]:
        for line in wrap(held_back_note(table["held_back"], tested), _prose_width(2)):
            out.append("  " + style(line, "grey"))
    out.append("")
    return "\n".join(_titled("node reliability (%s rate)" % metric, out, style))


def render_sizing(history, style=None, limit=12):
    """Per-workload guidance for the next submission."""
    style = style or Style()
    out = [
        style("  " + line, "grey")
        for line in wrap(
            "From how each workload actually ran. Over-requesting narrows which nodes "
            "can host it; under-requesting kills the run.",
            _prose_width(2),
        )
    ]
    out.append("")
    shown = 0
    # Groups with advice that the limit cut off, and the runs behind them. Counted
    # rather than just dropped: this list is ordered by compute burned, not by how
    # wrong the request is, so the workload most worth re-sizing can sit at
    # position 13 -- and every other truncated view here names its tail
    # (History.tail_summary, patterns.find_repeat_failures) while this one went
    # quiet. `tail_summary` cannot serve: what is shown here is the first N groups
    # *with actionable advice*, which is not a prefix of history.groups.
    hidden_groups = 0
    hidden_runs = 0
    for group in history.groups:
        advice = recommend(group.jobs)
        if not advice:
            continue
        actionable = [a for a in advice if a.actionable]
        if not actionable:
            continue
        shown += 1
        if shown > limit:
            hidden_groups += 1
            hidden_runs += group.total
            continue
        out.append(
            "  %s  %s"
            % (
                style(group.label, "bold"),
                style("%s · %d runs" % (group.partition, group.total), "grey"),
            )
        )
        for a in advice:
            if a.verdict == "keep":
                out.append("    %-17s %s" % (a.flag, style("already about right", "green")))
                continue
            if a.verdict == "unknown":
                out.append("    %-17s %s" % (a.flag, style("no advice", "grey")))
                # Wrapped, not appended to the flag line: "no advice — Needs at
                # least 3 completed runs before a limit can be inferred." ran to 97
                # cells and overran an 80-column terminal.
                for line in wrap(a.basis, _prose_width(8)):
                    out.append("        " + style(line, "grey"))
                continue
            arrow = "raise to" if a.verdict == "raise" else "lower to"
            # Only what was requested. The `observed` half read "observed 07:58:03
            # at p95, 07:58:23 longest" one line above a basis reading "p95 of 87
            # completed runs is 07:58:03 (longest 07:58:23)" -- the same two
            # figures, twice, on adjacent lines. The basis says it better because
            # it also names the sample size and the headroom, so the parenthetical
            # keeps only the number the basis does not carry: the old value.
            # `observed` is not dead -- it stays in the --json payload, which is
            # where a machine-readable copy of the measurement belongs.
            out.append(
                "    %-17s %s %s   %s"
                % (
                    a.flag,
                    arrow,
                    style(a.suggestion, "bold"),
                    style("(from %s)" % a.requested, "grey"),
                )
            )
            for line in wrap(a.basis, _prose_width(8)):
                out.append("        " + style(line, "grey"))
            if a.caution:
                for index, line in enumerate(wrap(a.caution, _prose_width(10))):
                    out.append(
                        "        %s%s" % ("! " if index == 0 else "  ", style(line, "yellow"))
                    )
        for line in sbatch_lines(advice):
            out.append("    " + style(line, "bold"))
        out.append("")
    if not shown:
        out.append(
            style("  every workload is already about right, or lacks the runs to say.", "green")
        )
        out.append("")
    elif hidden_groups:
        tail = "… %d more workload%s (%d runs) also have advice, below the %d shown. " % (
            hidden_groups,
            "" if hidden_groups == 1 else "s",
            hidden_runs,
            limit,
        )
        tail += "Narrow --since, or ask about one with `slurmpast --sizing -p <partition>`."
        for line in wrap(tail, _prose_width(2)):
            out.append("  " + style(line, "grey"))
        out.append("")
    return "\n".join(_titled("what to request next time", out, style))
