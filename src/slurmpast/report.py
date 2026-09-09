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
from .index import SORTS, History, sort_groups, sort_label
from .model import severity_rank
from .nodes import (
    compress_nodelist,
    dominant_workload,
    excluded_tail,
    node_table,
    suggest_exclude,
)
from .render import (
    ACTION_ARROW,
    ACTION_HANG,
    ACTION_INDENT,
    CAUTION_HANG,
    CAUTION_MARK,
    CI_COLUMN,
    DETAIL_BAR_GAP,
    DETAIL_BAR_WIDTH,
    HOURS_PAIR_LABEL,
    JOB_COLUMNS,
    NODE_COLUMNS,
    NOTHING_TO_FLAG,
    OVER_LIMIT_MARK,
    OVERVIEW_COLUMNS,
    PAIR_LABEL_WIDTH,
    PAIR_VALUE_WIDTH,
    PAIRED_LINE_WIDTH,
    STEP_COLUMNS,
    WORKLOAD_CONTROL_ASIDE,
    ascii_fold,
    bar,
    capped_label,
    ci_range,
    cores_text,
    cpu_only_columns,
    fit_columns,
    gpu_hours_equivalence,
    gpu_hours_total,
    held_back_note,
    hours_pair_text,
    hours_text,
    idle_hours_note,
    idle_workload_note,
    job_sections,
    log_inferred_note,
    log_miss_detail,
    nodes_baseline,
    nodes_correction_note,
    nodes_empty_reason,
    nodes_exclude_disclaimer,
    nodes_excluded_tail_note,
    nodes_nothing_to_exclude,
    nodes_title,
    nodes_workload_control,
    pair_rows,
    pair_value_budget,
    pair_value_lines,
    patterns_empty,
    resource_rows,
    severity_tag,
    stamp_short,
    text_table,
    wrap,
    wrap_or_clip,
)
from .sizing import MIN_RUNS, recommend, sbatch_lines

#: Parsed rows after which the window's memory footprint is worth a line.
#:
#: A job plus its steps is typically four rows, so this is a few thousand jobs --
#: comfortably past any ordinary week and comfortably short of the windows that
#: run into gigabytes.
_FOOTPRINT_NOTE_ROWS = 20_000

#: Bytes retained per parsed row, measured over 43,660 real rows (13,321 jobs and
#: 30,339 steps) after the parser began sharing one object per distinct string:
#: 44.5 MB, or 1,020 B/row -- down from 2,034 B/row, where `uid` and `account`
#: each had ONE distinct value held as 13,321 separate string objects.
_BYTES_PER_ROW = 1024

_CODES = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "red": "\033[31m",
    "yellow": "\033[33m",
    "green": "\033[32m",
    "cyan": "\033[36m",
    "grey": "\033[90m",
}
# Only the ANSI colour lives here now. The tag beside it was a second copy of
# `render.SEVERITY_TAG`, which the dashboard reads through `render.severity_chip`
# -- the same three words maintained in two files, agreeing by luck.
_SEV_COLOR = {"critical": "red", "warning": "yellow", "info": "cyan"}
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
# The narrowest layout prose is asked to fit. Wrapping a sentence tighter than
# this produces a column of three-word lines that is harder to read than an
# overrun, so below 60 the renderer stops shrinking.
#
# It is a floor on the *layout*, NOT a promise that every view fits 60 cells, and
# the two were being confused. A table cannot shrink past its never-dropped
# columns -- `render.table_floor` computes that per spec: 74 for the job list, 41
# for the node table -- so between 60 and those floors the tables overrun, and no
# clamp here can change it. (This comment said 67 for the node table for one round.
# That was the length of `render_nodes`' own unwrapped `baseline` line, measured off
# the view and filed as a property of the spec, which is the framing under which a
# wrappable sentence never gets wrapped. It now is.)
#
# What did change: everything that *is* prose (finding titles, the nodes workload
# line and its two empty-table sentences, the gauge details, a long single-pair
# value, the sizing headers) now wraps to the terminal, so a narrow terminal is one
# or two wide tables rather than a page of wrapped text. The one deliberate overrun
# left is a recorded log path, which must stay copyable whole.
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


def _emphasise(line, token, style, colour="bold"):
    """Re-apply emphasis to ``token`` inside an already-wrapped line.

    Wrapping has to run on the *plain* sentence -- an ANSI wrapper is nine
    characters the terminal never draws, so `wrap` counting them breaks the line
    at the wrong column -- which means any emphasis inside the sentence has to go
    back on afterwards, and only on the line where the wrap left the token whole.
    A token split across two lines simply keeps the paragraph's own styling; that
    is the price of measuring width honestly.
    """
    if not token or token not in line:
        return line
    return line.replace(token, style(token, colour), 1)


def _plain_layout(spec, content=None, indent=_PLAIN_INDENT):
    return fit_columns(spec, _plain_width() - len(indent), padding=_PLAIN_GAP, content=content)


def _pair_value_width():
    """``PAIR_VALUE_WIDTH``, or 0 to force one pair per line on a narrow terminal.

    pair_rows treats any value longer than this as needing its own line, so zero
    unpairs everything. The threshold lives in ``render`` now, because the dashboard
    draws the same block and was not applying it.
    """
    return PAIR_VALUE_WIDTH if _plain_width() >= PAIRED_LINE_WIDTH else 0


def _fold(text, ascii_mode):
    """``render.ascii_fold`` when ``--ascii`` asked for it, otherwise untouched.

    One call per view, on the finished text: the flag has to reach the sentences
    as well as the glyphs, and the sentences are assembled in a dozen places.
    Folding last is also what keeps it width-safe -- every substitution is one
    cell for one cell, applied after the wrapping and the column fitting that
    measured those cells.
    """
    return ascii_fold(text) if ascii_mode else text


class Style:
    def __init__(self, enabled=None, stream=None):
        stream = stream or sys.stdout
        if enabled is None:
            # TERM=dumb belongs next to NO_COLOR, not apart from it: an Emacs
            # shell buffer, a CI log and a serial console all set it, and all
            # three are a tty, so isatty() alone said "colour". This was the
            # only tool in the family that coloured a dumb terminal -- rapidu
            # and slurmate already pair the two checks, and rapidu's ui module
            # names both in its docstring.
            enabled = (
                hasattr(stream, "isatty")
                and stream.isatty()
                and not os.environ.get("NO_COLOR")
                and os.environ.get("TERM", "") != "dumb"
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
    no_logs=False,
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
    for line in resource_rows(job, ascii_mode=ascii_mode, flat=True, max_width=_plain_width()):
        out.append(line.plain)
    for title, rows in job_sections(job, summarized=True):
        out.append("")
        out.append(style("  " + title, "bold"))

        def cell(label, value, pad):
            flag = "red" if OVER_LIMIT_MARK in value else None
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
                continue
            label, value, gauge = group[0][0], group[0][1], group[0][2]
            # The gauge the dashboard has always drawn on this row, and the plain
            # renderer never did: it read `group[0][0]` and `[0][1]` and stopped, so
            # `row[2]` was not consumed anywhere in this module. `slowest task` came
            # out as a bar in the app and a bare percentage in a paste. `pair_rows`
            # already gives a gauged row a line of its own, so the space was
            # reserved for a bar this surface then declined to draw.
            #
            # Flat, like the three headline gauges at the top of this function: only
            # the characters survive here, and an eighth-block tip with no
            # background behind it reads as a notch rather than the end of a bar.
            # `ascii_mode` for the same reason those three take it -- a bar is the
            # one thing in this view `--ascii` was originally built for, and leaving
            # it off here put "█" and "░" back into output that had just been made
            # pure ASCII. Round eight's test caught it on the first run.
            prefix = ""
            if gauge is not None:
                prefix = bar(
                    gauge, "", width=DETAIL_BAR_WIDTH, ascii_mode=ascii_mode, flat=True
                ).plain
                prefix += " " * DETAIL_BAR_GAP
            # A value on its own line still has to fit the line. `pair_rows` only
            # decides how many pairs go on one; it makes no claim about the length
            # of the survivor, so a sentence-shaped value went out at its full
            # width -- "not gathered by this cluster (needs AutoDetect=nvml in
            # gres.conf)" put this row at 86 cells whatever the terminal was, and
            # the terminal then wrapped it to column 0, away from its label.
            # Continuation lines hang under the value column so the pair still
            # reads as one.
            # Both the budget and the wrapping live in `render` now: the dashboard
            # draws this row too and was measuring it differently -- clipping where
            # this wraps, and forgetting the bar entirely, which is what put a
            # gauged row past an 80-column terminal.
            #
            # `PATH_ROWS` keeps the documented exemption: "`--plain` exists to be
            # pasted, and a path you cannot copy whole is no use in a ticket", so
            # `workdir` overruns on purpose, as the log path below does.
            budget = pair_value_budget(_plain_width(), len(prefix))
            lines = pair_value_lines(label, value, budget)
            out.append("    %s" % cell(label, prefix + lines[0], 0))
            # Continuation hangs past the bar as well as the label, so the sentence
            # stays under itself instead of restarting beneath the gauge.
            for extra in lines[1:]:
                out.append("    %s %s%s" % (" " * PAIR_LABEL_WIDTH, " " * len(prefix), extra))

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
        # The path is never shortened -- `--plain` exists to be pasted, and a path
        # you cannot copy whole is no use in a ticket -- so a path longer than the
        # terminal is an accepted overrun rather than a defect, and the only one
        # left in this view. What did not have to overrun is the note beside it.
        #
        # Say when the path was inferred from timing rather than read off a name: a
        # wrong log invents a cause, so the basis has to travel with it.
        #
        # The words come from `render.log_inferred_note` -- the other branch of this
        # same if/elif has gone through `render.log_miss_detail` since round
        # thirty-three, and this half was left writing its own copy, which the
        # dashboard also wrote out at tui.py. The parentheses are layout, not
        # wording: they mark the note as an aside where it rides on the path's line,
        # and they come off where it gets a line of its own, which is the only
        # layout the dashboard has. So the sentence both surfaces draw is now
        # byte-identical, and the aside cue survives with colour off.
        sentence = log_inferred_note()
        note = "(%s)" % sentence
        inline = "  log %s  %s" % (log_path, note)
        # `yellow` is what this module spells the dashboard's `HEALTH_COLOR["warn"]`
        # as -- the pairing render_overview already makes for `idle_hours_note`.
        # This was `grey`, the hue used for bookkeeping and for the word `log` two
        # cells to its left, so the one line on the screen warning that the evidence
        # below it may belong to another job was the quietest thing on it, while the
        # dashboard shouted the same words. `logs.find_log_by_time` settles which is
        # right: "a wrong log invents a cause, which is worse than no log".
        if log_inferred and len(inline) <= _plain_width():
            # Unchanged where the pair fits, which is every short path on a wide
            # terminal.
            out.append("  %s %s  %s" % (style("log", "grey"), log_path, style(note, "yellow")))
        else:
            out.append("  %s %s" % (style("log", "grey"), log_path))
            # The note is prose, and riding on that line it added 58 cells to
            # whatever the path already cost -- 133 cells at every terminal width,
            # every one of them the note's fault rather than the path's. Its own
            # wrapped line, indented under the path, so what overruns above is the
            # path alone.
            if log_inferred:
                for line in wrap(sentence, _prose_width(6)):
                    out.append("      " + style(line, "yellow"))
    elif not no_logs:
        # Guarded, because both spellings below are claims about the filesystem and
        # under `--no-logs` nothing was stat'd. "none found" reported a search that
        # never ran; with a recorded StdOut the invented claim got stronger and was
        # simply false -- "none at /scratch/... — moved or deleted" about a file
        # nobody looked for. `--demo` forces `no_logs` (cli.main), so every
        # synthetic post-mortem shipped one. `tui.JobScreen` has guarded the
        # identical line all along; this is the same guard, so the two front ends
        # stop disagreeing about it.
        #
        # One line, but which line depends on whether the cluster recorded a path.
        # Where one was recorded -- StdOut/StdErr from Slurm 24.05, the -o inside
        # SubmitLine from 21.08, or a --comment on any version -- the miss is "the
        # file has moved or been deleted" and naming the expected path is
        # actionable. With none of the three there is no such record anywhere a
        # post-mortem can reach (slurmctld forgets a job after MinJobAge), so the
        # path is genuinely unknowable and saying more would explain a limitation
        # the reader cannot act on.
        #
        # Three spellings where there used to be one, because a stat that failed
        # is not the same as a stat that found nothing. "moved or deleted" is a
        # sound inference from ENOENT and an unsound one from EACCES, and on a
        # shared cluster the second is the common case: 104 of the 106 foreign
        # jobs naming a log path on the reporting cluster were unreadable rather
        # than absent. The owner is on the record, so the message can say who to
        # ask instead of asserting something about a file nobody could see.
        detail = log_miss_detail(job)
        # Wrapped: this one is a sentence built around a path, not a bare path, so
        # unlike the found case above there is nothing here that has to survive a
        # copy. It reached 122 cells at every terminal width.
        for index, line in enumerate(wrap(detail, _prose_width(6))):
            prefix = "  %s " % style("log", "grey") if index == 0 else " " * 6
            out.append("%s%s" % (prefix, style(line, "grey")))
    out.append("")
    findings = sorted(verdict.findings, key=lambda f: severity_rank(f.severity))
    if not findings:
        out.append(style("  " + NOTHING_TO_FLAG, "green"))
    else:
        out.append(style("  findings", "bold"))
        for finding in findings:
            colour = _SEV_COLOR.get(finding.severity, "bold")
            tag = severity_tag(finding.severity)
            out.append("")
            # Wrapped like the evidence and the action beneath it. A title is a
            # sentence -- "Peak memory reads above the limit, yet nothing was
            # killed" is 68 cells -- and this was the one line of the three going
            # out at whatever length it happened to be.
            for index, line in enumerate(wrap(finding.title, _prose_width(2 + len(tag) + 3))):
                out.append(
                    "  %s %s"
                    % (
                        style("[" + tag + "]", colour) if index == 0 else " " * (len(tag) + 2),
                        style(line, "bold"),
                    )
                )
            for line in wrap(finding.evidence, _prose_width(8)):
                out.append("        " + line)
            # Guarded, the way `tui._finding_lines` has always guarded it. `wrap("")`
            # is `[""]` -- one empty line, not none -- so a finding whose action is
            # deliberately empty drew an arrow pointing at nothing, with a trailing
            # space after it. Five findings are written that way on purpose
            # ("Cancelled, not failed", the traceback tail, the end-of-log tail, the
            # uneven-memory note) because the evidence IS the whole story, and the
            # dashboard renders them with no arrow. Only `--plain` drew one, which is
            # the drift `render` centralising the glyph did not catch: round fourteen
            # made both surfaces agree on WHICH arrow and left them disagreeing on
            # whether to draw one.
            if finding.action:
                for index, line in enumerate(wrap(finding.action, _prose_width(ACTION_INDENT))):
                    out.append(
                        "        %s%s"
                        % (style(ACTION_ARROW if index == 0 else ACTION_HANG, "grey"), line)
                    )
    out.append("")
    return _fold("\n".join(out), ascii_mode), verdict


# A label `GroupStats.label` marked as covering more than one raw job name, e.g.
# `20260822 +1`. Anchored at the end so a job genuinely named `run+1` is not
# mistaken for one.
_MERGED_LABEL = re.compile(r" \+\d+$")


def render_overview(history: History, style=None, limit=25, sort="cost", ascii_mode=False):
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
    # Both halves pluralised. Only `workload%s` was, so a one-job history read
    # "1 jobs in 1 workload" -- the two counts sit in one sentence and disagreed
    # about their own grammar. `TestSingularPlural` names this exact case and has
    # been green throughout, because it presses `a` first and then reads the JOB
    # LIST screen's sentence, which is a different one and was always right.
    line = "  %d job%s in %d workload%s · %s completed" % (
        stats["jobs"],
        "" if stats["jobs"] == 1 else "s",
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
        hours = " · " + gpu_hours_total(idle[1])
        hours += style(idle_hours_note(idle[0], idle[1]), "yellow")
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
    if stats.get("excluded_unparsed"):
        # Worth its own words rather than folding into either count above: these
        # are rows sacct returned that this tool could not read, which is a
        # different thing to tell a reader than "a job we could not rate".
        kinds.append("%d unreadable" % stats["excluded_unparsed"])
    if kinds:
        out.append(style("  %s, excluded" % " and ".join(kinds), "grey"))
    # What this window cost to hold, once it is large enough to matter.
    #
    # A history is fully materialised, so memory grows with the window: measured
    # at **~1 KB per parsed row** retained (a job plus its steps is typically
    # four rows), so 43,660 rows needed about 43 MB and a 30-day query on a busy
    # cluster runs into gigabytes. Nothing bounded it and nothing said so -- what
    # actually stopped users hitting it was `SLURMPAST_TIMEOUT`, at 300 s,
    # failing on time before it failed on memory. An undocumented memory cap.
    #
    # Said rather than left to the OOM killer, and it names the knob: `-S` is
    # what narrows the window, and the cost is proportional to it. Only above
    # the threshold, because on an ordinary window this is a line in the way.
    rows = stats.get("parsed_rows") or 0
    if rows >= _FOOTPRINT_NOTE_ROWS:
        # Wrapped, like every other paragraph here. This one is 109 cells on a real
        # history (`40,994 rows parsed, ...`) and went out at that length whatever
        # the terminal was, so on the 90- and 100-column terminals people actually
        # use it hard-broke mid-sentence -- the exact fault `_prose_width` exists to
        # stop, in the one note that was not using it.
        sentence = (
            "%s rows parsed, about %s held — a window ten times longer "
            "costs ten times that; narrow it with -S"
            % (
                f"{rows:,}",
                format_bytes(rows * _BYTES_PER_ROW),
            )
        )
        out.extend(style("  " + line, "grey") for line in wrap(sentence, _prose_width(2)))
    if stats.get("unclassified"):
        # Its own line, deliberately: these are NOT excluded. They are counted in
        # the job total and their core-hours are in the resource sums -- the only
        # figure they are missing from is the completion rate, and appending them
        # to the "excluded" line above would say the opposite.
        out.append(
            style(
                "  %d in no outcome state (REQUEUED and the like), so outside the "
                "completion rate" % stats["unclassified"],
                "grey",
            )
        )

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
        notes.append("%s (%s)" % (claim, gpu_hours_equivalence()))
    elif sort != SORTS[0][0]:
        notes.append("ordered by %s" % sort_label(sort))
    if any("#" in g.label for g in shown):
        notes.append('"#" stands for a name\'s digits')
    # Only when such a row is on screen. The name shown is one real name out of
    # several the fold merged, and without this the row claims a singularity it
    # does not have.
    if any(_MERGED_LABEL.search(g.label) for g in shown):
        notes.append('"+N" means the name shown covers N more')
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
    # Where the window's idle GPU-hours actually sit. The summary above says how
    # many never computed; FLAGGED counts the runs but not what they cost, so the
    # table cannot answer "which workload" -- and the figure that can,
    # `GroupStats.wasted_gpu_hours`, was summed on every walk and read by
    # nothing. Below the table rather than beside the total, because
    # `test_the_summary_is_brief` caps everything above it at four lines on
    # purpose; the dashboard puts the same sentence on its summary line, which is
    # the same split `gpu_hours_equivalence` already makes.
    #
    # Wrapped to the terminal rather than emitted as one line: a folded workload
    # label is site-controlled and unbounded, so the sentence is not, and an
    # unwrapped footer soft-wrapping to column 0 under a table that lines up
    # perfectly reads as a rendering fault. `wrap`, not `wrap_or_clip` -- the two
    # figures are the point of the sentence and they sit at the end of it.
    worst = history.idle_workload
    if worst is not None:
        note = idle_workload_note(worst[0].label, worst[1], worst[0].gpu_hours)
        out.extend(style("  " + line, "yellow") for line in wrap(note, _prose_width(2)))
    # Handed the list that was actually sliced. Left to slice `history.groups`
    # itself, this line described the cost-ranked tail under every sort: at
    # `--sort name -n 3` on the demo it said "23 runs holding 10.9% of the compute"
    # about a hidden set of 30 runs holding 86.4%. The caption above the table was
    # corrected for this once already; the footer below it was not.
    tail = history.tail_summary(limit, ordered=groups)
    if tail:
        # Hanging indent under the leader, so a continuation reads as part of the
        # same note rather than as a new row of the table above it. 63 cells on a
        # real history against `PLAIN_MIN_WIDTH`'s floor of 60.
        for index, line in enumerate(wrap(tail, _prose_width(4))):
            out.append(style(("  … " if index == 0 else "    ") + line, "grey"))
    out.append("")
    return _fold("\n".join(out), ascii_mode)


def render_list(jobs, style=None, limit=40, ascii_mode=False):
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
    if limit is not None and len(jobs) > limit:
        out.append(style("  … %d more (raise --limit)" % (len(jobs) - limit), "grey"))
    return _fold("\n".join(out), ascii_mode)


def render_patterns(history: History, style=None, ascii_mode=False):
    style = style or Style()
    body = [""]
    findings = history.patterns
    if not findings:
        body.append(style("  " + patterns_empty(), "green"))
        body.append("")
        return _fold("\n".join(_titled("cross-run patterns", body, style)), ascii_mode)
    for finding in sorted(findings, key=lambda f: severity_rank(f.severity)):
        colour = _SEV_COLOR.get(finding.severity, "bold")
        tag = severity_tag(finding.severity)
        for index, line in enumerate(wrap(finding.title, _prose_width(2 + len(tag) + 3))):
            body.append(
                "  %s %s"
                % (
                    style("[" + tag + "]", colour) if index == 0 else " " * (len(tag) + 2),
                    style(line, "bold"),
                )
            )
        for line in wrap(finding.evidence, _prose_width(8)):
            body.append("        " + line)
        # Same guard as the job report above, for the same reason: the
        # "%d further groups show the same repeat-failure pattern" tail and the
        # requeue tail both carry `action=""`, and this surface pointed an arrow at
        # the empty string on the last line of `--patterns`.
        if finding.action:
            for index, line in enumerate(wrap(finding.action, _prose_width(ACTION_INDENT))):
                body.append(
                    "        %s%s"
                    % (style(ACTION_ARROW if index == 0 else ACTION_HANG, "grey"), line)
                )
        body.append("")
    return _fold("\n".join(_titled("cross-run patterns", body, style)), ascii_mode)


def render_nodes(history: History, metric="hang", controlled=True, style=None, ascii_mode=False):
    style = style or Style()
    jobs = history.usable_jobs
    workload = dominant_workload(jobs, metric=metric) if controlled else None
    table = node_table(jobs, workload=workload, metric=metric)
    out: list[str] = []
    # Both wrapped, like every other prose line in this function. These two were
    # bare format strings, and the first carries a *folded workload name*: the
    # demo's is `cot-exp`, which is what let it pass `test_no_table_row_overruns_
    # the_terminal` through two audits, but a real one runs to
    # `nemotron-batch-h#-tokenize-shards-stage#-retry-#` and took the line to 114
    # cells on a 100-column terminal. Same shape as the node table of round three,
    # which survived for the same reason -- the demo's own values are short.
    if workload:
        aside = WORKLOAD_CONTROL_ASIDE
        sentence = nodes_workload_control(workload)
        out.extend(
            "  " + _emphasise(_emphasise(line, workload, style), aside, style, "grey")
            for line in wrap(sentence, _prose_width(2))
        )
    else:
        out.extend(
            style("  " + line, "yellow")
            for line in wrap(
                "UNCONTROLLED — mixes workloads; a node that hosted one bad campaign "
                "will look cursed",
                _prose_width(2),
            )
        )
    # The third of the three prose lines in this function, and the one round five
    # left bare after wrapping the two above it. Bounded by its own numbers rather
    # than by a name, so it overran only below 68 -- but it is also the line whose
    # 67 cells were measured off this view and recorded as `NODE_COLUMNS`' table
    # floor, which is 41. See render.table_floor.
    out.extend("  " + line for line in wrap(nodes_baseline(table), _prose_width(2)))
    out.append("")
    # Two ways this table has nothing to say. Printing a column header over no
    # rows -- or eight rows of "0/N, 0.0%, inconclusive" -- is what made this
    # screen read as useless. A sentence is the answer in both cases.
    #
    # Both sentences come from `render` now, and both are wrapped: they were the
    # longest lines on the screen at every terminal width -- 132 cells and 122 --
    # which is the sentence written to rescue an empty screen being the thing that
    # broke it. The first carries a folded workload name, so it is #6 of round five
    # in a branch that round's reproductions never reached.
    empty = nodes_empty_reason(table, metric, workload)
    if empty:
        out.extend("  " + line for line in wrap(empty, _prose_width(2)))
        out.append("")
        return _fold("\n".join(_titled(nodes_title(metric), out, style)), ascii_mode)
    tested = table["tested_nodes"]
    # Through the shared spec, like the other three plain tables. This one was
    # hand-formatted at `"  %-16s %9s %10s %20s  %s"`, so it was the only table here
    # that neither tracked the terminal nor dropped a column -- byte-identical at 60
    # and 200 columns, and overrunning an 80-column one outright -- and any node name
    # past 16 characters (`gpu-compute-node-a100-0001`, `queue1-dy-c5xlarge-1`) shoved
    # every following column out of line, on the row the reader came for.
    # render.NODE_COLUMNS was declared for exactly this and only the dashboard used
    # it, which is the drift render.py exists to prevent.
    layout = _plain_layout(
        NODE_COLUMNS,
        content={"NODE": max(len(r["node"]) for r in table["rows"])},
    )
    out.extend(
        text_table(
            layout,
            [
                {
                    "NODE": row["node"],
                    "N": "%d/%d" % (row["bad"], row["trials"]),
                    "RATE": "%.1f%%" % (100 * row["rate"]),
                    CI_COLUMN: ci_range(row["ci_low"], row["ci_high"]),
                    "VERDICT": (
                        row["verdict"],
                        {"worse": "red", "better": "green"}.get(row["verdict"]),
                    )
                    if row["verdict"] in ("worse", "better")
                    else row["verdict"],
                }
                for row in table["rows"]
            ],
            style=style,
        )
    )
    out.append("")
    excl = compress_nodelist(suggest_exclude(table))
    if excl:
        # Wrapped, like the tail note below it. These two were bare strings, and
        # the block they are in only renders when a node is actually worse than
        # the rest -- which the demo did not produce, so nothing measured them.
        for line in wrap(
            nodes_correction_note(tested),
            _prose_width(2),
        ):
            out.append("  " + line)
        # Not wrapped, deliberately: it is one #SBATCH line to copy, and a paste
        # broken across two lines is not a paste.
        out.append("    %s" % style("#SBATCH --exclude=" + excl, "bold"))
        for line in wrap(
            nodes_exclude_disclaimer(),
            _prose_width(4),
        ):
            out.append("    " + style(line, "grey"))
        # The line is capped, so it has to say when it is not the whole list.
        left_out = excluded_tail(table)
        if left_out:
            for line in wrap(
                nodes_excluded_tail_note(left_out),
                _prose_width(4),
            ):
                out.append("    " + style(line, "grey"))
    else:
        out.append(style("  " + nodes_nothing_to_exclude(), "grey"))
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
    return _fold("\n".join(_titled(nodes_title(metric), out, style)), ascii_mode)


def render_sizing(history, style=None, limit=12, sort="cost", ascii_mode=False):
    """Per-workload guidance for the next submission."""
    style = style or Style()
    intro = (
        "From how each workload actually ran. Over-requesting narrows which nodes "
        "can host it; under-requesting kills the run."
    )
    out = [style("  " + line, "grey") for line in wrap(intro, _prose_width(2))]
    # Named only when it is not the default, as on the overview. This list is
    # truncated and, until now, always in cost order -- so `--sort rate`, the
    # obvious remedy for the very problem the tail note below describes ("the
    # workload most worth re-sizing can sit at position 13"), was accepted and
    # silently discarded, in text and in --json alike.
    if sort != SORTS[0][0]:
        out.append(style("  ordered by %s" % sort_label(sort), "grey"))
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
    # Why a workload left, not just that it did. The filter below drops two states
    # that mean opposite things -- "correctly sized" and "I have no idea" -- and
    # the one sentence at the bottom offered them as equal possibilities. On the
    # cluster this was reported from, 61 of 69 workloads were dropped and *every
    # one* was for lack of runs; none was correctly sized. A screen whose only
    # output is an affirmative green pass, for a state that is actually no data,
    # is the first thing a new user sees on a new cluster.
    no_data_groups = 0
    no_data_runs = 0
    # Judged and left alone, as distinct from never judged. Kept so the empty
    # screen can tell the reader which of the two it is looking at.
    shown_judged = 0
    for group in sort_groups(history.groups, sort):
        advice = recommend(group.jobs)
        if not advice:
            continue
        actionable = [a for a in advice if a.actionable]
        if not actionable:
            # `unknown` means the runs were too few to infer anything;
            # `keep`/`capped` mean the request was judged and left alone.
            if all(a.verdict == "unknown" for a in advice):
                no_data_groups += 1
                no_data_runs += group.total
            else:
                shown_judged += 1
            continue
        shown += 1
        if limit is not None and shown > limit:
            hidden_groups += 1
            hidden_runs += group.total
            continue
        # Wrapped: a folded workload name and a partition are both site-controlled
        # and neither is bounded, so this header reached 86 cells on an 80-column
        # terminal. `_emphasise` puts the styling back on whichever line kept each
        # token whole, since the wrap has to run on the plain sentence.
        aside = "%s · %d run%s" % (group.partition, group.total, "" if group.total == 1 else "s")
        header = "%s  %s" % (group.label, aside)
        if len(header) + 2 <= _plain_width():
            # Unchanged where it fits, which is the ordinary case: `wrap` collapses
            # runs of whitespace, and the two spaces between the name and its aside
            # are the separator. Only a header too wide to hold pays for the wrap.
            out.append("  %s  %s" % (style(group.label, "bold"), style(aside, "grey")))
        else:
            # `wrap_or_clip`, not `wrap`: a folded workload name can be one word --
            # the longest on this cluster is 123 characters with no space in it --
            # and `wrap` hands a single word back whole.
            for line in wrap_or_clip(header, _prose_width(2)):
                line = _emphasise(line, group.label, style)
                out.append("  " + _emphasise(line, aside, style, "grey"))
        for a in advice:
            if a.verdict == "keep":
                out.append("    %-17s %s" % (a.flag, style("already about right", "green")))
                continue
            if a.verdict == "capped":
                # Not "already about right": the workload wants more and cannot
                # have it here. The basis line carries the measurement and the
                # caution names the way out, so both are printed rather than the
                # flag line alone.
                out.append("    %-17s %s" % (a.flag, style(capped_label(), "yellow")))
                for line in wrap(a.basis, _prose_width(8)):
                    out.append("        " + style(line, "grey"))
                for index, line in enumerate(wrap(a.caution, _prose_width(8 + len(CAUTION_MARK)))):
                    prefix = CAUTION_MARK if index == 0 else " " * len(CAUTION_MARK)
                    out.append("        " + style(prefix + line, "yellow"))
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
                for index, line in enumerate(wrap(a.caution, _prose_width(8 + len(CAUTION_MARK)))):
                    out.append(
                        "        %s%s"
                        % (
                            CAUTION_MARK if index == 0 else CAUTION_HANG,
                            style(line, "yellow"),
                        )
                    )
        for line in sbatch_lines(advice):
            out.append("    " + style(line, "bold"))
        out.append("")
    if not shown:
        # Wrapped for the same reason the nodes screen's two are: at 66 cells this
        # is the only line on the view, so a narrow terminal broke the one sentence
        # standing in for the whole screen.
        #
        # Green is reserved for the genuine all-clear. A no-data screen is grey,
        # like the `no advice` rows it is standing in for -- the least-informed
        # state should not be rendered in the most reassuring colour.
        if not (no_data_groups or shown_judged):
            # NOTHING was considered, which the green branch below also matched:
            # `no_data_groups` and `shown_judged` are both 0, so an empty result
            # set read as "every workload is already about right" -- the
            # least-informed state in the most reassuring colour, which is the
            # defect the other two branches were added to fix and which this one
            # walked straight past.
            #
            # Two ways in, and the second is the consequential one: an empty
            # window, and a **named RUNNING job**, which is filtered out before
            # the counting and so registers as neither category. A job at 94.5%
            # of its memory limit was told it was about right.
            # `history.jobs`, not `history.groups`: an unfinished record is
            # excluded from the groups before any of this counting -- which is
            # precisely why it registered as neither category -- so the groups
            # cannot say that a running job is the reason the screen is empty.
            loaded = list(getattr(history, "jobs", ()) or ())
            running = [j for j in loaded if j.in_progress]
            if len(running) == 1 and len(loaded) == 1:
                sentence = (
                    "job %s is still running — --sizing needs a finished run, "
                    "because it sizes from what a run actually used." % running[0].job_id
                )
            elif running:
                sentence = "no finished runs in this window to size from (%d still running)." % len(
                    running
                )
            else:
                sentence = "no finished runs in this window to size from."
            colour = "grey"
        elif no_data_groups and not shown_judged:
            sentence = (
                "no workload has the %d completed runs --sizing needs "
                "(%d workload%s, %d run%s)."
                % (
                    MIN_RUNS,
                    no_data_groups,
                    "" if no_data_groups == 1 else "s",
                    no_data_runs,
                    "" if no_data_runs == 1 else "s",
                )
            )
            colour = "grey"
        elif no_data_groups:
            sentence = (
                "every workload with enough runs is already about right; %d other%s "
                "(%d run%s) lack%s the %d runs --sizing needs."
                % (
                    no_data_groups,
                    "" if no_data_groups == 1 else "s",
                    no_data_runs,
                    "" if no_data_runs == 1 else "s",
                    "s" if no_data_groups == 1 else "",
                    MIN_RUNS,
                )
            )
            colour = "grey"
        else:
            sentence = "every workload is already about right."
            colour = "green"
        out.extend(style("  " + line, colour) for line in wrap(sentence, _prose_width(2)))
        out.append("")
    elif hidden_groups:
        tail = "… %d more workload%s (%d run%s) also ha%s advice, below the %d shown. " % (
            hidden_groups,
            "" if hidden_groups == 1 else "s",
            hidden_runs,
            "" if hidden_runs == 1 else "s",
            "s" if hidden_groups == 1 else "ve",
            limit,
        )
        tail += "Narrow --since, or ask about one with `slurmpast --sizing -p <partition>`."
        for line in wrap(tail, _prose_width(2)):
            out.append("  " + style(line, "grey"))
        out.append("")
    if shown and no_data_groups:
        # The other tail, and the one that was missing. `hidden_groups` counts only
        # workloads *with* advice pushed past the limit, so on a history where 8
        # workloads are shown and 61 were dropped for lack of runs, it never fires
        # and 61 leave with no tally at all. Naming a tail is this file's own
        # standard, stated two branches up; the filter above it did not meet it.
        note = "%d other workload%s (%d run%s) %s too few runs to judge — %s needs %d." % (
            no_data_groups,
            "" if no_data_groups == 1 else "s",
            no_data_runs,
            "" if no_data_runs == 1 else "s",
            "has" if no_data_groups == 1 else "have",
            "--sizing",
            MIN_RUNS,
        )
        for line in wrap(note, _prose_width(2)):
            out.append("  " + style(line, "grey"))
        out.append("")
    return _fold("\n".join(_titled("what to request next time", out, style)), ascii_mode)
