"""Rich renderables shared by the TUI and the plain-text output.

Kept apart from ``tui.py`` so the same bar, chip and verdict look identical
whether you are inside the app or piping ``--plain`` into a file.
"""

from __future__ import annotations

import math
from typing import NamedTuple

from rich.text import Text

from . import theme
from .duration import (
    format_bytes,
    format_cpu_freq,
    format_duration,
    format_percent,
    plural,
)
from .model import Job, severity_rank
from .nodes import MIN_SAMPLES


def bar_cells(percent: float | None, width: int) -> int:
    """Whole filled cells for a magnitude bar.

    Rounds rather than floors, and anything that *prints* as >=1% keeps at least
    one lit cell, so the bar never contradicts the number beside it. (A bare
    floor is what made a 4% row draw an empty gauge next to its own "4%".)

    "Prints as" means at the one decimal the labels carry, which is the same test
    :func:`bar` applies. Using a bare ``>= 0.5`` here instead made the ASCII and
    Unicode bars disagree over 0.5-0.94%: one lit a cell beside a label reading
    "0.7%", the other did not.
    """
    if width <= 0 or percent is None:
        return 0
    if math.isnan(percent):
        return 0
    percent = min(max(percent, 0.0), 100.0)
    cells = min(width, round(percent / 100.0 * width))
    if cells == 0 and round(percent, 1) >= 1.0:
        cells = 1
    return int(cells)


# Partial-cell caps, so a bar lands on its true position instead of snapping to
# the nearest whole cell. Same glyph set slurmwatch uses.
_EIGHTHS = "▏▎▍▌▋▊▉"


def bar(
    percent: float | None,
    color: str,
    width: int = theme.BAR_WIDTH,
    ascii_mode: bool = False,
    flat: bool = False,
):
    """A magnitude bar, matching slurmwatch's.

    The empty track is a shaded block (``░``) in a faint neutral, NOT a line
    glyph -- ``─`` renders as a string of dashes, which reads as punctuation
    rather than as the unfilled remainder of a gauge.

    The fill is drawn to one-eighth-of-a-cell precision. Two rules keep the bar
    honest against the number printed beside it: the last eighth is withheld
    until the percentage *rounds* to 100, so a visually full bar always means
    100%; and anything that displays as >=1% keeps at least a sliver, so a bar
    never reads empty next to a non-zero figure.

    ``None`` draws an empty track -- never a full or a zero bar.

    ``flat`` is for a caller that throws the styles away and keeps only the
    characters -- the plain report does, appending ``line.plain``. The eighth-block
    tip needs a background behind it to read as anything but a notch, so without
    styles it rounds to whole cells instead, exactly as ``ascii_mode`` does. The
    percentage is printed beside it either way.
    """
    if width <= 0:
        return Text()
    if percent is None or math.isnan(percent):
        return Text(("-" if ascii_mode else "░") * width, style=theme.FAINT)

    percent = min(max(percent, 0.0), 100.0)
    text = Text()
    if ascii_mode:
        full = bar_cells(percent, width)
        text.append("#" * full, style=color)
        text.append("-" * (width - full), style=theme.FAINT)
        return text
    if flat:
        full = bar_cells(percent, width)
        text.append("█" * full, style=color)
        text.append("░" * (width - full), style=theme.FAINT)
        return text

    eighths = min(width * 8, round(percent / 100.0 * width * 8))
    if round(percent, 1) < 100.0:
        # Reserve the whole final cell, not merely its last eighth. Withholding an
        # eighth was not a gap anyone could see: at 96.6% of 18 cells the fill took
        # 3/8 of the last cell and left 5/8 of dark behind it, and the tip read as
        # the bar simply stopping -- reported twice, the second time after the tip
        # was given a track background, which was not enough on its own.
        #
        # So anything short of 100% now ends against a FULL cell of track, and a
        # bar reaching the end means full and nothing else. The cost is real and
        # accepted: 94.5% and 99.9% draw alike. What that range has to distinguish
        # is "at the limit" from "not at the limit", the exact figure is printed
        # beside the bar, and a gauge whose last 5% is invisible was distinguishing
        # nothing at all.
        eighths = min((width - 1) * 8, eighths)
    eighths = 0 if round(percent, 1) < 1.0 else max(1, eighths)
    full, rem = divmod(int(eighths), 8)
    if full:
        text.append("█" * full, style=color)
    if rem:
        # The partial cell paints only its filled fraction, so whatever is behind
        # it has to read as track -- otherwise the bar ends in a notch of bare
        # background. Reported as "there is nothing at the end of the final tip":
        # at 95.9% of 18 cells the fill lands in the last cell with no "░" left to
        # follow it, so the same bar looked complete at 94.4% and at 100% but
        # unfinished in between. The stipple cannot be used for this one cell --
        # it is already carrying the fill -- so it gets the colour the stipple
        # averages to.
        text.append(_EIGHTHS[rem - 1], style="%s on %s" % (color, theme.TRACK_BG))
    empty = width - full - (1 if rem else 0)
    if empty > 0:
        text.append("░" * empty, style=theme.FAINT)
    return text


def log_miss_detail(job) -> str:
    """The one line saying why no log is on screen, for whichever surface asks.

    Both front ends draw this and they had drifted badly. ``--plain`` grew four
    spellings keyed on :func:`logs.probe_path` -- naming the recorded path, and
    distinguishing a file that is absent from one that is merely unreadable --
    while the dashboard still printed a single unconditional "none found", on a
    stale comment claiming "the path is unknowable". It has been knowable since
    Slurm 24.05 recorded ``StdOut``, and on a shared cluster the two surfaces were
    telling the same reader different things about the same job.

    So the rule lives here, which is what this module is for. Callers get the
    sentence and keep their own wrapping and styling: the plain renderer wraps it
    to the prose width, the app hands it to a Textual span.

    The caller is responsible for not asking under ``--no-logs`` -- every branch
    below is a claim about the filesystem, and nothing was stat'd in that mode.
    """
    from .logs import probe_path, recorded_paths

    expected = recorded_paths(job)
    if not expected:
        # No StdOut/StdErr (below Slurm 24.05), no `-o` in a recorded SubmitLine
        # (below 21.08), no path in a --comment. Nothing a post-mortem can reach
        # knows where the output went, and slurmctld has long forgotten the job.
        return "none found — --log-dir points at one"
    path = expected[0]
    state = probe_path(path)
    if state == "discarded":
        # Not a miss at all: the job asked for this. Naming --log-dir here offered
        # a recovery for a file that was never written, and "moved or deleted" said
        # something had gone wrong with a decision the submitter made on purpose.
        # 152 of 2,675 records on pythia over three days.
        return (
            "discarded — this job sent its output to %s, so there is none to read. "
            "Re-run with --output=<path> to keep it." % path
        )
    if state == "special":
        return (
            "not a regular file at %s — there is nothing to read there; --log-dir "
            "points at a real one" % path
        )
    if state == "unreadable":
        # On a shared cluster this is the common case, not the corner: 104 of the
        # 106 foreign jobs naming a log path were unreadable rather than absent.
        # The owner is on the record, so say who to ask.
        whose = ("%s's" % job.user) if job.user else "its owner's"
        return (
            "none readable at %s — it may well be there, but %s directory is not "
            "readable by you; ask them, or point --log-dir at a copy" % (path, whose)
        )
    if state == "unknown":
        return (
            "could not be checked at %s — the filesystem refused the question; "
            "--log-dir points somewhere reachable" % path
        )
    return "none at %s — moved or deleted; --log-dir points at it" % path


def health_dot(grade: str, ascii_mode: bool = False):
    glyphs = theme.HEALTH_GLYPH_ASCII if ascii_mode else theme.HEALTH_GLYPH
    return Text(glyphs.get(grade, glyphs["none"]), style=theme.HEALTH_COLOR.get(grade, theme.FAINT))


def state_text(state: str, ascii_mode: bool = False):
    grade = theme.STATE_HEALTH.get(state, "none")
    text = Text()
    text.append_text(health_dot(grade, ascii_mode))
    text.append(" ")
    text.append(state or "?", style=theme.HEALTH_COLOR.get(grade, theme.DIM))
    return text


# The four-cell tag a finding is announced with, and the one place it is spelled.
# `report._SEV` carried a second copy of these three labels beside its ANSI colour
# names, so "FAIL"/"WARN"/"INFO" were written twice in two files -- agreeing today,
# with nothing to keep them agreeing tomorrow. Four cells exactly, including the
# `----` fallback, because the plain renderer indents a wrapped title by
# ``len(tag) + 2`` and a five-cell tag would step that hang out of line.
SEVERITY_TAG = {"critical": "FAIL", "warning": "WARN", "info": "INFO"}
SEVERITY_TAG_UNKNOWN = "----"


def severity_tag(severity: str) -> str:
    """``FAIL`` / ``WARN`` / ``INFO``, or ``----`` for a severity neither knows."""
    return SEVERITY_TAG.get(severity, SEVERITY_TAG_UNKNOWN)


def severity_chip(severity: str):
    grade = theme.SEVERITY_HEALTH.get(severity, "none")
    return Text(
        severity_tag(severity), style="bold %s" % theme.HEALTH_COLOR.get(grade, theme.FAINT)
    )


# What a finding's action line is introduced with, and how far its continuations
# hang so they sit under the text rather than under the arrow.
#
# Written out four times before this -- twice in `report.py`, twice in `tui.py` --
# and the two files had drifted to different glyphs: the dashboard drew "→ " and
# `--plain` drew "-> ", for the same element of the same finding. Nothing on
# either screen could show a reader that, because only one of the two is ever in
# front of them. Worse, the plain spelling was already ASCII, so `--ascii` -- the
# flag whose entire job is choosing between these two alphabets -- had nothing to
# change and `ascii_fold` never saw it.
#
# Two cells, so the fold stays one-cell-for-one-cell: "→ " becomes "> ".
ACTION_ARROW = "→ "
ACTION_HANG = "  "
# Cells an action line spends before its text: eight of indent plus the arrow.
ACTION_INDENT = 8 + len(ACTION_ARROW)

# And the same pair for a sizing caveat -- `Advice.caution`, "what would make this
# advice wrong". Here for the reason the arrow is: two surfaces draw this block, and
# until now only one of them drew this part of it at all.
CAUTION_MARK = "! "
CAUTION_HANG = "  "


class Column(NamedTuple):
    """One table column, and how it behaves when the terminal is not 94 wide.

    ``flex`` columns absorb whatever width is left over once the fixed ones are
    placed, so a table reaches the right edge instead of stopping at a hard-coded
    width and leaving a third of a wide terminal blank. Slack goes only to
    columns whose content is genuinely variable-length and is otherwise
    truncated -- a job name, a node list -- never to a column of short codes,
    where extra width is just a bigger gap.

    ``drop`` orders the sacrifices when even the minimum does not fit: the lowest
    number goes first, and ``drop=0`` means never dropped.
    """

    label: str
    width: int  # exact width; for a flex column, the minimum
    flex: bool = False
    drop: int = 0
    grow_to: int = 0  # cap on a flex column's width; 0 means unbounded
    # Read by the plain-text renderer only. Textual's DataTable takes alignment
    # from each cell's own Rich justify, so the dashboard ignores this field.
    align: str = "left"


def fit_columns(
    columns,
    available: int,
    padding: int = 2,
    content: dict[str, int] | None = None,
    fill_to: int = 0,
) -> list[tuple[str, int]]:
    """Choose which columns fit in ``available`` cells, and how wide each gets.

    Textual's DataTable sizes columns exactly as told and never redistributes the
    remainder, so fixed widths meant the overview stopped dead at 94 columns on
    every terminal wider than that.

    ``content`` maps a label to the longest cell that column will actually show. A
    flex column never grows past what its content needs: growing to a fixed cap
    regardless produced a 44-wide JOB NAME holding 18-character names, which is a
    canyon rather than use of space.

    ``fill_to`` is the total width to spread whatever is still spare across, and
    zero leaves it unused. Both behaviours are wanted: a pasted table should be as
    wide as its content so it survives a ticket comment, while a 100-cell table
    sitting in the middle of a 150-column terminal reads as thin. The spread is
    round-robin over EVERY column, a cell at a time -- pouring it into one flex
    column is exactly the canyon above, and giving it only to the text columns
    leaves the numbers huddled together at one end.

    Returns ``(label, width)`` in display order. Callers must emit row cells in
    that same order, which is why the row builders key their cells by label.
    """
    # A column is never narrower than its own header: a truncated "WALL TIM" is
    # the same defect as a cryptic abbreviation, just self-inflicted.
    columns = [c._replace(width=max(c.width, len(c.label))) for c in columns]

    chosen = list(columns)
    while len(chosen) > 1:
        cost = sum(c.width for c in chosen) + padding * len(chosen)
        droppable = [c for c in chosen if c.drop]
        if cost <= available or not droppable:
            break
        chosen.remove(min(droppable, key=lambda c: c.drop))

    widths = [c.width for c in chosen]
    slack = available - (sum(widths) + padding * len(chosen))

    # The variable-length columns take the leftover space, but only as far as
    # their content actually reaches. Anything still spare is left unused.
    def ceiling(index: int) -> int:
        column = chosen[index]
        limit = column.grow_to or available
        if content is not None and column.label in content:
            # Never past the longest real cell -- and never below the declared
            # minimum, so a table of short values does not look cramped.
            limit = min(limit, max(content[column.label], column.width))
        return limit

    flex = [index for index, c in enumerate(chosen) if c.flex]
    while slack > 0:
        room = [index for index in flex if widths[index] < ceiling(index)]
        if not room:
            break
        for index in room:
            if slack <= 0:
                break
            widths[index] += 1
            slack -= 1

    # Whatever the content-capped growth above did not want, spread in proportion
    # to what each column already is. Equal shares were tried and are wrong in a
    # way that is obvious on screen: a 3-cell "#" holding one digit became 13 cells
    # wide while JOB NAME gained the same 10, so the table expanded without looking
    # expanded -- every gap grew and the columns stopped reading as a row. Weighting
    # by width keeps the rhythm the table already has.
    spare = min(slack, fill_to - (sum(widths) + padding * len(chosen))) if fill_to else 0
    if spare > 0:
        total = sum(widths) or 1
        share = [spare * width // total for width in widths]
        for index, extra in enumerate(share):
            widths[index] += extra
        # The rounding remainder to the widest columns first, so the table lands on
        # exactly ``fill_to`` and the leftover cells go where they show least.
        order = sorted(range(len(widths)), key=lambda i: -widths[i])
        remainder = spare - sum(share)
        for step in range(remainder):
            widths[order[step % len(order)]] += 1

    return [(column.label, max(1, widths[index])) for index, column in enumerate(chosen)]


def _uncoloured(text: str, *_names: str) -> str:
    """The no-op stand-in for report.Style, for callers that want no colour."""
    return text


def clip(value: str, width: int) -> str:
    """``value`` in ``width`` cells, saying so when it did not fit.

    A bare ``value[:width]`` is fine for a job name, which stays recognisable
    truncated, and wrong for anything with syntax. ``midway3-[0600-0607,0611]`` came
    out as ``midway3-[0600`` -- and at a column width of 12,
    ``midway3-0600,midway3-0611`` came out as ``midway3-0600``: a complete, valid,
    real node name for a job that ran on two, with nothing on screen to say a second
    was dropped. Truncating the column is deliberate (see :class:`Column`); doing it
    without a marker was not, and every other truncation in this codebase announces
    itself -- ``... N more``, ``excluded_tail``, ``tui._elide``.
    """
    if len(value) <= width:
        return value
    if width <= 1:
        return value[:width]
    return value[: width - 1] + "…"


def table_floor(spec, indent: int = 2, gap: int = 1) -> int:
    """The narrowest terminal ``spec`` can be drawn in without a row overrunning.

    ``fit_columns`` drops columns until the table fits, but it can only drop the
    ones marked droppable -- so every spec has a width below which it stops
    shrinking and starts overrunning instead, and that width is a property of the
    spec rather than a number anyone can keep up to date by hand. ``JOB_COLUMNS``
    bottoms out at 74 cells and ``NODE_COLUMNS`` at 41, and the overrun between 74
    and the 60 that ``report.PLAIN_MIN_WIDTH`` clamps the layout to went unnoticed
    because the width tests were parametrized over 80, 100 and 120 only.

    The node figure was recorded here as 67 for one round, which was not a table
    floor at all: it was the length of ``render_nodes``' unwrapped ``baseline …``
    line, measured off the rendered view and attributed to the spec. That is worth
    naming rather than quietly correcting, because filing a wrappable sentence as a
    property of the column set is the one framing under which nobody fixes it --
    and nobody did. Take this number from the spec, never from a screenshot.

    Kept honest by ``TestPlainOutputFitsATerminal``, which asserts each view
    against ``max(terminal, table_floor(its spec))`` rather than against a
    constant -- so adding a never-dropped column moves the floor and the test
    follows it, instead of the promise quietly becoming false.
    """
    keep = [max(c.width, len(c.label)) for c in spec if not c.drop]
    return indent + sum(keep) + gap * max(0, len(keep) - 1)


def text_table(layout, rows, style=None, indent: str = "  ", gap: int = 1):
    """A fit_columns layout drawn as plain text: header, rule, rows.

    Exists so ``--plain`` draws the same tables the dashboard does. It used
    hardcoded ``%`` widths instead, and the two drifted apart in both directions:
    the plain overview kept printing labels and explanatory lines the dashboard
    had already dropped as clutter, and its rows were 135 cells wide -- so on a
    100-column terminal all 42 of them wrapped, which is not a table.

    A row is ``{label: value}`` or ``{label: (value, colour)}``. Padding is
    applied BEFORE colouring: an ANSI wrapper is nine invisible characters that
    ``%-30s`` counts anyway, which shifts every following cell on the line.
    """
    style = style or _uncoloured
    separator = " " * gap

    def cell(label: str, width: int, value: str, colour=None) -> tuple[str, str]:
        align = _COLUMN_ALIGN.get(label, "left")
        padded = ("%*s" if align == "right" else "%-*s") % (width, clip(value, width))
        return (style(padded, colour) if colour else padded), padded

    def line(cells) -> tuple[str, int]:
        painted = separator.join(c[0] for c in cells)
        # Measured on the unpainted copy: an ANSI wrapper is nine characters that
        # len() counts and the terminal does not.
        return indent + painted, len(indent + separator.join(c[1] for c in cells).rstrip())

    header, extent = line([cell(label, width, label) for label, width in layout])
    body = []
    for row in rows:
        cells = []
        for label, width in layout:
            value = row.get(label, "")
            colour = None
            if isinstance(value, tuple):
                value, colour = value
            cells.append(cell(label, width, value, colour))
        text, reach = line(cells)
        extent = max(extent, reach)
        body.append(text.rstrip())
    # The rule spans the table's real extent, not the columns' nominal total. A
    # right-aligned last column leaves the nominal width unreached, and a rule
    # hanging three cells past the widest row reads as a rendering fault.
    return [header.rstrip(), indent + style("-" * (extent - len(indent)), "grey"), *body]


# Filled in below, once the specs exist: text_table is handed a (label, width)
# layout rather than the Column objects, so alignment is looked up by label.
_COLUMN_ALIGN: dict[str, str] = {}


def register_alignment(*specs) -> None:
    for spec in specs:
        for column in spec:
            _COLUMN_ALIGN[column.label] = column.align


# Geometry for the two-column detail layout. A value longer than this keeps its
# own line rather than being truncated or wrapped mid-pair.
PAIR_LABEL_WIDTH = 16
PAIR_VALUE_WIDTH = 30
# Bar width for a detail row that carries a gauge, and the gap after it. Narrower
# than the three headline gauges (`theme.BAR_WIDTH`), because this one shares its
# line with a label and a sentence rather than leading a block of its own.
#
# Named here because both surfaces draw the row and only one of them was: the
# dashboard hardcoded `width=14` and the plain renderer never read `row[2]` at all,
# so `slowest task` came out as a gauge in the app and a bare number in a paste.
# `pair_rows` below already gives a gauged row a line of its own -- the plain
# layout was reserving room for a bar it then did not draw.
DETAIL_BAR_WIDTH = 14
DETAIL_BAR_GAP = 2
# What a line holding two pairs costs: four cells of indent and two between them.
# Below it, pair one per line -- a paired row that wraps loses the label/value
# alignment that made pairing readable. Shared, because both front ends draw this
# block and only the plain one was checking.
PAIRED_LINE_WIDTH = 4 + 2 * (PAIR_LABEL_WIDTH + 1 + PAIR_VALUE_WIDTH) + 2


def pair_rows(rows, max_value: int = PAIR_VALUE_WIDTH):
    """Group ``(label, value, bar)`` rows two per line where both are short.

    The detail sections used one row per line and about 40 of 120 columns, so a
    job screen ran off the bottom of the terminal with two thirds of every line
    empty. Rows whose value is long -- a path, a node list, an explanation -- or
    which carry a gauge still take a line to themselves, because truncating a
    workdir to fit a column would trade one defect for a worse one.

    Returns a list of 1- or 2-tuples of rows, in display order.
    """
    out: list[tuple] = []
    pending = None
    for row in rows:
        short = row[2] is None and len(str(row[1])) <= max_value
        if not short:
            if pending is not None:
                out.append((pending,))
                pending = None
            out.append((row,))
            continue
        if pending is None:
            pending = row
        else:
            out.append((pending, row))
            pending = None
    if pending is not None:
        out.append((pending,))
    return out


def cores_text(job) -> str:
    """``3.0 of 4`` -- cores busy against cores allocated.

    A bare "74.7%" was read as memory use. Naming both numbers says what the
    quantity is and doubles as the answer to "what should --cpus-per-task be".
    """
    busy = job.cores_busy
    if busy is None:
        return "n/a"
    return "%.1f of %d" % (busy, job.cpu_count)


def hours_text(value) -> str:
    """An hour count for a table cell. ``-`` for none, ``<1`` for a sliver.

    One unit per column, so GPU-hours and CPU-hours get a column each. A single
    "resource used" column that printed GPU-hours for GPU rows and CPU-hours for
    the rest was two faults at once: a GPU job burns CPU-hours as well, so half
    of its cost was hidden, and with the unit changing row to row no two rows
    could be compared down the column at all.

    ``-`` and ``<1`` rather than a rounded ``0``: a row that held GPUs for twenty
    minutes did not use zero GPU-hours.
    """
    if not value:
        return "-"
    if value < 1:
        return "<1"
    return f"{value:,.0f}"


# Sub-widths inside the combined hours cell. The CPU side is right-aligned INTO
# the slash and the GPU side left-aligned OUT of it, so the separator sits in a
# fixed column and both series stay scannable -- a plain "670 / 503" per row would
# put no two numbers under each other.
_CPU_HOURS_WIDTH = 7
_GPU_HOURS_WIDTH = 5
HOURS_PAIR_LABEL = "CPU / GPU-HOURS"


def hours_pair_text(group) -> str:
    """``    670 / 503`` -- CPU-hours and GPU-hours in one cell.

    The colours reinforce which is which, but they are never the only signal:
    ``--no-color``, a pipe, and a colour-blind reader all still have the fixed
    order and the ``CPU / GPU-HOURS`` header. A cell distinguishable only by hue
    would be unreadable in half the places this output goes.
    """
    return "%*s / %-*s" % (
        _CPU_HOURS_WIDTH,
        hours_text(group.core_hours),
        _GPU_HOURS_WIDTH,
        hours_text(group.gpu_hours),
    )


def hours_pair(group) -> Text:
    """The same cell for the dashboard, with each side in its resource's hue."""
    text = Text()
    text.append(
        "%*s" % (_CPU_HOURS_WIDTH, hours_text(group.core_hours)),
        style=theme.CPU_COLOR if group.core_hours else theme.FAINT,
    )
    text.append(" / ", style=theme.FAINT)
    text.append(
        "%-*s" % (_GPU_HOURS_WIDTH, hours_text(group.gpu_hours)),
        style=theme.GPU_COLOR if group.gpu_hours else theme.FAINT,
    )
    return text


# The overview's columns. Three things this encodes:
#
# * Every label is a phrase a reader already knows. "WORKLOAD" prompted "what
#   does workload mean?" and "NAMES" prompted "what does names mean?" -- both
#   were the tool's internal vocabulary on screen. A row is a job name with its
#   digits folded, so the column is JOB NAME and the fold is explained under `?`.
# * One unit per column. A single "resource used" column showed GPU-hours for GPU
#   rows and CPU-hours for the rest, which hid the CPU-hours a GPU job also burns
#   and left no two rows comparable down the column.
# * "CPU-HOURS" rather than "core-hours": it is the unit of the `--cpus-per-task`
#   the reader actually sets, and of Slurm's own AllocCPUS / CPUTime.
#
# Annotated as variable-length: a bare literal infers a fixed-arity tuple type,
# and both front ends drop a column from it when the history has no GPU work.
OVERVIEW_COLUMNS: tuple[Column, ...] = (
    Column("#", 4),
    Column("JOB NAME", 22, flex=True, grow_to=44),
    Column("PARTITION", 9, drop=2),
    Column("RUNS", 5, align="right"),
    Column("COMPLETED", 9, drop=1, align="right"),
    # One outcome column, not FAILED plus NEVER RAN. The two overlapped -- a hung
    # TIMEOUT is both -- so two adjacent integers invited a reader to add them and
    # get 36 problems out of 20 runs. Which kind of wrong it was is a drill-down
    # question, and the workload screen answers it in a sentence.
    Column("FLAGGED", 8, align="right"),
    # One cell, CPU first: they are the same quantity in two units, and as two
    # adjacent columns they read as more separate than they are. Colour reinforces
    # which side is which; the fixed order and the header carry it without colour.
    # A CPU-only history drops the GPU half entirely rather than printing "/ -" on
    # every row -- see cpu_only_columns.
    Column(HOURS_PAIR_LABEL, 15),
    Column("LAST RUN", 10, drop=4),
)

# The job list's columns. Three complaints shaped these labels:
#
# * "CPU TIME" -- "what is it?". It is core-seconds consumed, which only means
#   something next to the CPUs it was spread over, so CPUS BUSY ("3.0 of 4") now
#   carries the interpretation and CPU TIME is the raw evidence beside it.
# * "CPU%" -- "is it memory usage or cpu core usage?". A percent with no named
#   denominator. Gone; CPUS BUSY names both numbers.
# * Peak memory was missing outright, which is the number most post-mortems
#   start from.
JOB_COLUMNS: tuple[Column, ...] = (
    # 3, not 4, and the one cell matters in the dashboard: at the 2-cell padding
    # Textual's DataTable is given, the columns that are never dropped cost 81 at
    # width 4 -- one over a canonical 80-column terminal, so the table could not fit
    # the narrowest width it has to work at. (The plain renderer pads by 1 and fit
    # either way.) 3 numbers 999 rows against a default `-n 25`; beyond that the
    # index clips rather than widening the table, and JOBID is the identifier that
    # matters anyway.
    Column("#", 3),
    Column("JOBID", 10),
    Column("NAME", 8, flex=True, grow_to=20, drop=3),
    # Wide enough for OUT_OF_MEMORY in full. Clipping the one state a reader most
    # needs to recognise down to "OUT_OF_ME" defeats the column.
    Column("STATE", 13),
    Column("STARTED", 11),
    # ENDED yields first: STARTED plus WALL TIME already imply it, whereas
    # nothing else on the row recovers a peak memory figure or a node name.
    Column("ENDED", 11, drop=1),
    Column("WALL TIME", 10, align="right"),
    Column("CPU TIME", 10, drop=2, align="right"),
    Column("CPUS BUSY", 10, align="right"),
    Column("PEAK MEM", 9, align="right"),
    Column("MEM%", 6, drop=5, align="right"),
    Column("GPU", 3, drop=6, align="right"),
    Column("NODE", 12, flex=True, grow_to=26, drop=4),
)

# A plain CPU-HOURS column, narrower than the pair it replaces.
CPU_HOURS_COLUMN = Column("CPU-HOURS", 11, align="right")

# `--steps`, the per-step breakdown. Widest first in drop order: the I/O counters
# are the reason to open this view least often, and STEP plus MAXRSS are the
# reason to open it at all (a step-by-step MaxRSS is how you find which phase
# peaked).
STEP_COLUMNS: tuple[Column, ...] = (
    Column("STEP", 18, flex=True, grow_to=26),
    Column("STATE", 11),
    Column("ELAPSED", 11, align="right"),
    Column("CPU", 10, align="right"),
    Column("MAXRSS", 9, align="right"),
    Column("READ", 9, drop=1, align="right"),
    Column("WROTE", 9, drop=2, align="right"),
)

# Node reliability. Declared here with the others rather than hardcoded at the
# widget, so this table drops columns, tracks the terminal and spends the leftover
# exactly as the other two do -- hardcoding them left it as the one screen that
# stayed narrow while its neighbours filled, which reads as a broken layout.
NODE_COLUMNS: tuple[Column, ...] = (
    Column("NODE", 18, flex=True, grow_to=26),
    Column("N", 11, align="right"),
    Column("RATE", 8, align="right"),
    # The interval before the verdict: the verdict is one word and recoverable
    # from the numbers, while the interval is the evidence for it.
    Column("95% CI", 18, drop=1, align="right"),
    Column("VERDICT", 14, drop=2),
)

register_alignment(OVERVIEW_COLUMNS, JOB_COLUMNS, STEP_COLUMNS, NODE_COLUMNS, (CPU_HOURS_COLUMN,))


def nodes_baseline(table) -> str:
    """``baseline 70.0% over 20 placements; 1 node below threshold omitted``.

    One sentence, unindented and unwrapped, for a caller to wrap to its own width.
    Here rather than in either front end for the reason this module exists: both
    screens draw it, and while each spelled it out for itself the two drifted --
    ``report`` said "below threshold" and ``tui`` said "below sample threshold",
    and when round five wrapped the two prose lines above this one it wrapped them
    in ``report`` only. A sentence both surfaces show is a shared renderable.
    """
    skipped = table["skipped_nodes"]
    tail = ""
    # Not when nothing was recorded to attribute. The two lines then contradicted
    # each other on any sparse history -- "2 nodes below threshold omitted" says
    # nodes were evaluated and withheld, directly above `nodes_empty_reason`
    # saying "No hangs recorded ... so there is nothing to attribute to a node".
    # Only one of them can be the answer, and it is the second: with no events
    # the sample threshold is not what is standing between the reader and a
    # verdict, so naming it points at a fix that would not produce one.
    if skipped and table["hits"]:
        tail = "; %d node%s below threshold omitted" % (skipped, "" if skipped == 1 else "s")
    # `placement%s` for the same reason `node%s` beside it already does: a window
    # holding one job printed "baseline 100.0% over 1 placements" out of a sentence
    # that pluralises its other count correctly.
    trials = table["trials"]
    return "baseline %s over %d placement%s%s" % (
        format_percent(table["baseline"]),
        trials,
        "" if trials == 1 else "s",
        tail,
    )


def nodes_empty_reason(table, metric: str, workload: str | None, widen: str = "--since") -> str:
    """Why the node table has no rows, or ``""`` when it has some.

    Two ways it can have nothing to say, and round three added these sentences
    because an empty grid answered neither: "printing a column header over no rows
    -- or eight rows of 0/N, 0.0%, inconclusive -- is what made this screen read as
    useless. A sentence is the answer in both cases."

    Both were then left unwrapped in both front ends for two more rounds, so the
    sentence written to rescue an empty screen was itself the longest line on it --
    132 cells at every terminal width, because the first interpolates a *folded
    workload name* (``cot-exp`` in the demo, which is what hid it;
    ``nemotron-batch-h#-tokenize-shards-stage#-retry-#`` on a real cluster) and the
    second is a fixed 121-character literal. Returned plain so each caller wraps it
    to the width it actually has.

    ``widen`` is how the reader widens the window *on this surface* -- ``--since``
    for the plain report, pressing ``w`` for the dashboard. Sharing the sentence
    without it collapsed the two into a bare "A wider window is what fixes this.",
    dropping the only clause the reader can act on and the only one that
    legitimately differs between the front ends. This module exists to stop them
    drifting, not to average them: the wording is shared, the keystroke is passed
    in. Naming the thing you actually type is the same rule ``format_duration``'s
    ``HH:MM:SS`` and ``format_mem_flag``'s ``52G`` were written for.
    """
    if not table["hits"]:
        return "No %s recorded%s in this window, so there is nothing to attribute to a node." % (
            metric + "s",
            " for %s" % workload if workload else "",
        )
    if not table["rows"]:
        # A degenerate baseline first, because the sample-size sentence is a true
        # statement that prescribes a useless action. At 100% no node can be worse
        # than the baseline, so the comparison is unavailable for a reason no
        # window can fix: the reader widens `--since`, waits for a bigger query,
        # and gets the same non-answer. Reported from a real screen where a
        # workload's every decided run had failed across 44 nodes.
        #
        # The conclusion is already in the data, and it is the answer to what the
        # reader actually asked -- "is a node hurting me?" -- so it is said
        # instead of the threshold.
        #
        # Only here, in the branch that has no table to show. A 100% baseline with
        # rows is a real table of rows all at the baseline, and this sentence
        # would replace it: `render_nodes` returns early on any non-empty reason.
        # Gated on having enough placements to support the claim, which the
        # reported fix sketch did not ask for and which the suite's own fixtures
        # showed is needed: four all-hung runs give a 100% baseline too, and
        # asserting "this is a workload failure" from four is the same
        # over-reading in the other direction. The reported screen had 53
        # placements across 44 nodes. Below the threshold the sample size really
        # is an obstacle as well, so the existing sentence stays.
        baseline = table.get("baseline")
        trials = table.get("trials") or 0
        if baseline is not None and baseline >= 1.0 and trials >= MIN_SAMPLES:
            # Read inside the branch, and with `.get`: this function takes a plain
            # mapping rather than the `node_table` return type, so a caller that
            # builds one by hand need only carry the keys its case reaches.
            touched = table.get("tested_nodes", 0) + table.get("skipped_nodes", 0)
            return (
                "Every decided run of %s failed, on all %d node%s it touched — no node is "
                "an outlier because none succeeded. This is a workload failure, not a node "
                "failure." % (workload or "this workload", touched, "" if touched == 1 else "s")
            )
        # "%d seen, all below it" reads as a plural claim, and one node below the
        # threshold is the ordinary way to reach this branch on a short window.
        skipped = table["skipped_nodes"]
        seen = "1 seen, and it is below it" if skipped == 1 else "%d seen, all below it" % skipped
        return (
            "No node reached the %d placements a comparison needs — %s. "
            "A wider window (%s) is what fixes this." % (MIN_SAMPLES, seen, widen)
        )
    return ""


def held_back_note(count: int, tested: int) -> str:
    """Why the CI column can disagree with the verdict beside it.

    The node table shows one interval per node and the verdict is corrected across
    all of them, so an interval that clears the baseline can sit next to
    "inconclusive". Unexplained that reads as the tool contradicting its own
    evidence column, which is worse than either answer alone.

    Careful about what it claims. It does *not* say these particular intervals are
    chance -- one of them may well be the genuinely bad node the correction cost us.
    It says an interval on its own is not enough when this many nodes were tested,
    which is true of every one of them. Shared by both front ends so the two screens
    cannot explain the same number differently.
    """
    subject = (
        "1 interval clears the baseline on its own"
        if count == 1
        else "%d intervals clear the baseline on their own" % count
    )
    return (
        "%s — but about one in twenty does that by chance and %s tested, "
        "so on its own that is not yet evidence." % (subject, _nodes_tested(tested))
    )


def _nodes_tested(tested: int) -> str:
    """``1 node was`` / ``20 nodes were``, for a sentence ending in "tested".

    The count of nodes in the table is 1 whenever one node cleared MIN_SAMPLES and
    the rest did not, which is the ordinary shape of a short window -- so "1 nodes
    were tested" was reachable in both front ends, in the same sentence that takes
    care to write "1 interval" rather than "1 intervals".
    """
    return "1 node was" if tested == 1 else "%d nodes were" % tested


# --- sentences both front ends draw ---------------------------------------
# Everything below is one sentence the dashboard and ``--plain`` both put on
# screen, kept here for the reason this module exists: while each surface spelled
# them out for itself the two drifted, and the drift is invisible from either side
# alone. It had already happened -- ``--plain`` ended the exclude disclaimer at
# "trades availability for reliability." and the dashboard went on ", and that is
# your call.", one sentence rendered two ways in the same block of the same view.
# The shorter wording is kept: "not applied for you" has already said whose call
# it is.
#
# The pattern is the one ``nodes_baseline`` and ``held_back_note`` set above --
# return the plain sentence, let each caller wrap it and colour it, since the wrap
# width and the styling are the parts that legitimately differ.

WORKLOAD_CONTROL_ASIDE = "(placement is not random)"


def nodes_workload_control(workload: str) -> str:
    """``controlled for workload: only cot-exp counted (placement is not random)``.

    Both surfaces emphasise :data:`WORKLOAD_CONTROL_ASIDE` separately from the
    rest, so it is exported rather than buried, and each front end still finds it
    in the returned line to style it.
    """
    return "controlled for workload: only %s counted %s" % (workload, WORKLOAD_CONTROL_ASIDE)


def nodes_title(metric: str) -> str:
    """The heading over the node table, on both surfaces.

    ``report`` wrote "node reliability (hang rate)" and the dashboard wrote
    "node reliability — hang rate", which is the same heading over the same table
    in two spellings; the parenthesis reads as an aside where the metric is the
    subject. One string, and the em dash folds under ``--ascii`` like every other.
    """
    return "node reliability — %s rate" % metric


def ci_range(low: float, high: float) -> str:
    """The ``95% CI`` cell: two rates as a percentage range.

    Both surfaces draw this column of this table and each formatted it itself --
    ``"%.1f - %.1f%%"`` in `report`, ``"%.1f – %.1f%%"`` in `tui` -- so a hyphen
    and an en dash stood in the same cell depending on which one you were looking
    at. An en dash is what a numeric range takes, and it folds to the hyphen under
    ``--ascii``, so the piped output is byte-identical to what it always was.
    """
    return "%.1f – %.1f%%" % (100 * low, 100 * high)


def nodes_correction_note(tested: int) -> str:
    """Why the ``--exclude`` line beneath it is offered at all.

    "after correcting for %d tested" was the wording on both screens, which reads
    as an unfinished clause at every count and as plainly wrong at one -- "after
    correcting for 1 tested", which is what the demo prints. The noun was the
    missing word, and :func:`held_back_note` two lines further down the same
    screen already supplies it.
    """
    return "worse than every other node, after correcting for %s tested:" % (
        "1 node" if tested == 1 else "%d nodes" % tested
    )


def nodes_exclude_disclaimer() -> str:
    """The grey line under the paste-ready ``#SBATCH --exclude=``."""
    return "not applied for you — excluding nodes trades availability for reliability."


def nodes_excluded_tail_note(count: int) -> str:
    """What the capped ``--exclude`` line left off, when it left anything off."""
    return (
        "%d further node%s scored worse too, left off the line: excluding this many "
        "trades away more of the partition than a paste-ready suggestion should."
        % (count, "" if count == 1 else "s")
    )


def nodes_nothing_to_exclude() -> str:
    """The answer when no node is worse than the rest -- which is the good outcome."""
    return "no node is worse than the rest; nothing to exclude."


def nothing_matches(noun: str, filter_label: str = "", search: str = "") -> str:
    """Why a table came out empty, and which key undoes it.

    A table screen that filters to nothing drew its column header over blank space
    and said nothing at all -- and on the overview it could not even say "showing
    0", because that clause was guarded by ``if shown and ...``. The one count that
    explains an empty screen was the one count suppressed.

    `PatternsScreen` has had the right treatment all along ("That is a real answer,
    not an empty screen") and `filter_jobs` states the rule in its own comment,
    about the date search that was added because a user hit it: "Typing what you can
    plainly see and getting an empty list is the worst kind of empty result -- it
    reads as missing data."

    Shared so the overview and the job list cannot word it differently, and so a
    third screen that grows a filter inherits it.
    """
    reasons, keys = [], []
    if search:
        reasons.append('the search "%s"' % search)
        keys.append("escape clears it")
    if filter_label:
        reasons.append("the %s filter" % filter_label)
        keys.append("f widens it")
    if not reasons:
        # Nothing was narrowed, so there is genuinely nothing here. No key to
        # offer: `w` is on the footer and is about the window, not this table.
        return "no %s in this window." % noun
    return "no %s matches %s — %s." % (noun, " and ".join(reasons), ", ".join(keys))


def patterns_empty() -> str:
    """Why the cross-run screen is empty. A real answer, not a blank."""
    return "no cross-run pattern met its evidence threshold."


def gpu_hours_total(hours: float) -> str:
    """``184 GPU-hours total`` -- the denominator the idle figure is a share of.

    "total" is load-bearing and measured: "783 GPU-hours" alone was read as a
    per-job figure.

    Here rather than in each front end because both wrote ``"%.0f GPU-hours total"``
    themselves, which is below the 25-character floor of the sweep that catches
    duplicated sentences -- and neither guarded the plural, so a history whose whole
    GPU spend rounds to one hour said "1 GPU-hours total" on both. Round seven fixed
    nine of these; this pair was in the one clause that only appears when the idle
    share is material.
    """
    return "%.0f %s total" % (hours, plural(hours, "GPU-hour"))


def idle_hours_note(idle_hours: float, total_hours: float) -> str:
    """``, 91 of them never used`` -- the clause after :func:`gpu_hours_total`.

    "of them" is load-bearing and measured: a bare "18 never computed" did not say
    18 of what. Kept as a fragment, leading comma and all, because both surfaces
    append it to a total they have already written.

    The pronoun agrees with the *total*, not with the idle count, because that is
    what it refers back to: one GPU-hour of which one was wasted is "1 of it never
    used", not "1 of them".
    """
    pronoun = "it" if round(total_hours) == 1 else "them"
    return ", %.0f of %s never used" % (idle_hours, pronoun)


# The prose punctuation this codebase uses, and a one-cell ASCII stand-in for
# each. One cell exactly, never two: these are folded after a line has been
# wrapped and after `clip` has reserved its marker cell, so a two-character
# replacement would push a fitted table row back over the width it was just
# measured to.
_ASCII_FOLD = {
    "\u2014": "-",  # em dash
    "\u2013": "-",  # en dash
    "\u00b7": "|",  # middle dot, used as a separator between summary clauses
    "\u2026": ".",  # ellipsis -- `clip`'s cut marker, which must stay one cell
    "\u2192": ">",  # rightwards arrow
    "\u2190": "<",  # leftwards arrow
    "\u00d7": "x",  # multiplication sign, as in `patterns._mem_walk`'s "6.0 GiB x2"
}
_ASCII_TABLE = str.maketrans(_ASCII_FOLD)


def ascii_fold(text: str) -> str:
    """Prose punctuation to its ASCII stand-in, one cell for one cell.

    ``--ascii`` says "ASCII glyphs instead of Unicode", and it was only ever wired
    to the bar and the health dot -- so a terminal that cannot draw ``\u25cf`` got the
    fallback for that and then an em dash and a middle dot anyway. Worse, the flag
    reached exactly one of the six plain renderers: `cli` passed `ascii_mode` to
    `render_job` and to `tui.run` and to nothing else, so ``--ascii --overview``
    and ``--overview`` were byte-identical. That is round five's #7 and #8 again --
    "Two flags that were accepted and thrown away" -- on a third flag.

    Applied to the finished text of a plain view rather than at each call site,
    because it has to catch the sentences too, not just the glyphs, and there is
    exactly one place per view where the text is complete.

    Deliberately NOT applied to the dashboard. Textual draws its own frame in box
    characters whatever this flag says, so folding our prose there would buy a
    reader nothing they could see -- the screen is Unicode either way. ``--plain``
    is the surface that gets piped somewhere with an opinion about encoding, and it
    is the one this makes good on.
    """
    return text.translate(_ASCII_TABLE)


def search_hint(fields) -> str:
    """``name, job id, state, partition, node or date`` -- an Oxford-free list.

    One phrasing for the search box's placeholder and the help screen's ``/`` row,
    built from `index.JOB_SEARCH_FIELDS` or `GROUP_SEARCH_FIELDS` rather than
    written out. Three hand-maintained descriptions of one feature had drifted from
    it and from each other, and the overview's was the expensive one: it invited a
    job id, a state and a node on a screen that matches none of the three, so
    typing one returned an empty list. That is the same failure `filter_jobs`
    already names -- "typing what you can plainly see and getting an empty list is
    the worst kind of empty result -- it reads as missing data."
    """
    items = list(fields)
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return "%s or %s" % (", ".join(items[:-1]), items[-1])


def cpu_only_columns(columns):
    """The overview spec with the paired hours cell collapsed to CPU-hours.

    A history with no GPU work should not carry a GPU half that reads "/ -" on
    every row. Shared by both front ends so they cannot disagree about when the
    column appears.
    """
    return tuple(CPU_HOURS_COLUMN if c.label == HOURS_PAIR_LABEL else c for c in columns)


def wrap(text: str, width: int) -> list[str]:
    """Word wrap that preserves explicit newlines."""
    lines: list[str] = []
    for paragraph in (text or "").split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = ""
        for word in words:
            if current and len(current) + 1 + len(word) > width:
                lines.append(current)
                current = word
            else:
                current = f"{current} {word}".strip()
        if current:
            lines.append(current)
    return lines


def mem_text(job: Job) -> str:
    """Memory ceiling per node, saying where the figure came from and over how many.

    Two notes, each only when it has something to say. The provenance quotes the
    ReqMem value actually seen rather than the literal ``0n`` -- that is the Slurm
    20.11 spelling of "not recorded", and 21.08 onwards writes something else, so
    hardcoding it printed a value the record did not contain.

    The per-node note appears only on a multi-node job, where the figure here and
    the ``mem=`` in AllocTRES differ by the node count and a reader comparing them
    would otherwise think one of the two was wrong.
    """
    limit = job.mem_limit_bytes
    if limit is None:
        return "n/a"
    text = format_bytes(limit)
    nodes = job.node_count
    if nodes > 1:
        text += " per node (%s over %d)" % (format_bytes(job.mem_limit_total_bytes), nodes)
    if not job.req_mem_bytes:
        text += " (from AllocTRES; ReqMem read %s)" % (job.req_mem_raw or "empty")
    return text


def sort_findings(findings):
    return sorted(findings, key=lambda f: severity_rank(f.severity))


# --- the full job detail, shared by the dashboard and the plain renderer ----
# One source of truth so the two never drift: both consume these sections.


def _matches(value, other, tolerance: float = 0.005) -> bool:
    """Same figure to within half a percent, so a rounding difference in the last
    displayed digit does not count as new information."""
    if value is None or other is None:
        return False
    return abs(value - other) <= max(1.0, tolerance * abs(other))


def _pct_of(value, whole):
    if value is None or not whole:
        return None
    return 100.0 * value / whole


# Rows that :func:`resource_rows` already draws as a gauge. Passing
# ``summarized=True`` to :func:`job_sections` leaves them out, because printing
# both put every headline number on screen twice a few lines apart, each with its
# own differently-sized bar -- so a reader could not tell whether the lower block
# was new information. Keyed by (section, label) so a rename cannot silently
# reintroduce the duplicate.
_COVERED_BY_GAUGES = frozenset(
    [
        ("timing", "walltime"),
        ("cpu", "total"),
        # NOT ("memory", "limit"): the gauge shows the bare ceiling, and this row
        # is where the "(AllocTRES; ReqMem was 0n)" provenance has room to live.
        ("memory", "peak (MaxRSS)"),
    ]
)


# The :func:`job_sections` rows whose value is a filesystem path, and so the only
# ones a caller may shorten middle-out into ``first/…/last``. Declared beside the
# rows rather than inferred from the value, because the dashboard inferred it --
# ``"/" in value`` -- and caught ``submitted as`` in the net: a SubmitLine is a
# command, and `sbatch --output=/scratch/midway3/youzhi/logs/%x-%j.out train.sh`
# came out as `sbatch --output=/…/%x-%j.out train.sh`, throwing away the
# directory on the one row that records where the output went.
PATH_ROWS = frozenset(["workdir"])


def wrap_or_clip(text: str, width: int) -> list[str]:
    """``text`` wrapped to ``width``, with anything that would not break clipped.

    ``wrap`` breaks at spaces, so a single long word comes back unchanged and the
    caller emits a line wider than it asked for. `report` learned this once, for a
    detail value -- "a 68-character job name is one word, so it came out of the
    wrapper unchanged and the row went to 89 cells on an 80-column terminal" -- and
    fixed it there; two other places do the same wrap without the clip.

    A real cluster has the names to prove it: over two days of cluster-wide history
    the longest job name is 123 characters and contains no space at all
    (``nf-NFCORE_RNASEQ_..._SALMON_INDEX_(genome.transcripts.fa)``), which put the
    `--sizing` workload header at 125 cells on every terminal from 60 to 120.

    Named here so the rule has one home and a fourth caller inherits it.
    """
    lines = wrap(text, width)
    return [line if len(line) <= width else clip(line, width) for line in lines] or [text]


def pair_value_budget(width: int, bar_cells: int = 0) -> int:
    """Cells a single-pair value has, on a line of ``width`` carrying ``bar_cells``.

    Four of indent, the label column and the space after it, then whatever a gauge
    on the row took. The floor of 20 keeps a value legible on a terminal narrower
    than the sum of its own chrome.
    """
    return max(20, width - 4 - PAIR_LABEL_WIDTH - 1 - bar_cells)


def pair_value_lines(label: str, value: str, budget: int) -> list[str]:
    """A row's value, wrapped to ``budget`` and hard-clipped where it cannot wrap.

    ``wrap`` breaks at spaces and a value can have none -- a 68-character job name
    is one word -- so anything still over budget afterwards is clipped. ``PATH_ROWS``
    is the documented exemption: ``--plain`` exists to be pasted and a path you
    cannot copy whole is no use in a ticket.

    Here rather than in `report`, because the dashboard draws the same rows and did
    something else with them: it clipped every over-long value to a single line, so
    ``utilization  not gathered by this cluster (needs AutoDetect=nvml in g…`` lost
    the half of the sentence naming the fix, while the same row under ``--plain``
    wrapped and kept it. Neither surface should be deciding that on its own.
    """
    if label in PATH_ROWS:
        return wrap(value, budget) or [value]
    return wrap_or_clip(value, budget)


def requeue_summary(job) -> str:
    """How many times a job was requeued and what each earlier attempt did.

    Slurm reports only a job's latest incarnation unless `sacct -D` is asked for,
    so a job requeued on NODE_FAIL, on preemption, or by `scontrol requeue` used
    to render as its final attempt with no sign there had been others. That is the
    one case where the answer to *"what happened to my job?"* is precisely the
    thing not shown: "why is it still pending when I watched it start" is a
    requeue, every time.

    The elapsed time is the point, not just the count. On Midway3, job 53432121
    reads `COMPLETED` after 03:41:52 -- and burned another 27m49s on a node that
    failed under it first. A count alone would not say that.
    """
    if not job.earlier:
        return ""
    attempts = ", ".join(
        "%s after %s" % (job_earlier.base_state or "?", format_duration(job_earlier.elapsed))
        for job_earlier in job.earlier
    )
    n = len(job.earlier)
    return "%dx · %s" % (n, attempts)


def job_sections(job, summarized: bool = False):
    """Everything known about a finished job, as ``(title, [(label, value, bar)])``.

    ``bar`` is a percentage for rows worth drawing a gauge for, else None. Rows
    whose value could not be read are omitted entirely rather than printed as
    zero -- a fabricated 0 is indistinguishable from a measurement.

    ``summarized`` drops the rows :func:`resource_rows` already shows, for callers
    that render both. Nothing is lost: those rows ARE the gauge block.
    """
    sections = []

    # -- identity ------------------------------------------------------------
    ident = [("name", job.name or "n/a", None)]
    # Three separate things, each with its own label. Joined as "test / test /
    # rcc-staff" under a label reading "account" they looked like one value
    # repeated -- reported as "account only has 1, why did you output 3 separated
    # by /?". Nothing said which slash-separated field was which.
    if job.partition:
        ident.append(("partition", job.partition, None))
    if job.qos:
        ident.append(("qos", job.qos, None))
    if job.account:
        ident.append(("account", job.account, None))
    if job.node_list:
        ident.append(
            (
                "nodes",
                "%s  (%d node%s)"
                % (job.node_list, job.node_count, "" if job.node_count == 1 else "s"),
                None,
            )
        )
    if job.constraints:
        ident.append(("constraint", job.constraints, None))
    if job.reservation:
        ident.append(("reservation", job.reservation, None))
    if job.work_dir:
        ident.append(("workdir", job.work_dir, None))  # the only path row -- see PATH_ROWS
    if job.submit_line:
        # Recorded from Slurm 21.08. The one row that answers "what did I actually
        # ask for" without the reader reconstructing it from the numbers below.
        ident.append(("submitted as", job.submit_line, None))
    sections.append(("job", ident))

    # -- timing --------------------------------------------------------------
    timing = []
    if job.submit:
        timing.append(("submitted", job.submit, None))
    if job.start:
        timing.append(("started", job.start, None))
    if job.end:
        timing.append(("ended", job.end, None))
    if job.queue_wait is not None:
        timing.append(("queued for", format_duration(job.queue_wait), None))
    if job.earlier:
        # Above the walltime row on purpose: the walltime below is this
        # incarnation's, and a reader who has not been told the job ran before
        # will take it for the whole story.
        timing.append(("requeued", requeue_summary(job), None))
    timing.append(
        (
            "walltime",
            "%s of %s   (%s)"
            % (
                format_duration(job.elapsed),
                format_duration(job.timelimit),
                format_percent(job.walltime_used),
            ),
            _pct_of(job.walltime_used, 1.0),
        )
    )
    if job.suspended:
        timing.append(("suspended", format_duration(job.suspended), None))
    if job.scheduled_by == "backfill":
        # Only backfill. "main"/"submit" are the ordinary scheduling passes and
        # naming them told the reader nothing; backfill is worth a word because it
        # means the job fitted a gap, which is what a tighter --time buys you.
        timing.append(("scheduled", "backfill — fitted a gap in the queue", None))
    # NOT priority: a raw site-weighted integer with no relative context is not
    # something a reader can act on or even interpret. It stays in the JSON.
    sections.append(("timing", timing))

    # -- cpu -----------------------------------------------------------------
    cpu = [
        (
            "total",
            "%s of %s allocated   (%s over %s core%s)"
            % (
                format_duration(job.total_cpu),
                format_duration(job.cpu_time),
                format_percent(job.cpu_utilization),
                job.cpu_count or "?",
                "" if job.cpu_count == 1 else "s",
            ),
            _pct_of(job.cpu_utilization, 1.0),
        )
    ]
    if job.system_cpu_fraction is not None:
        # No gauge: on every other row a full bar means "more of what you asked
        # for", and here it would mean "worse". The number carries it, and the
        # findings speak up past SYSTEM_CPU_HEAVY.
        cpu.append(("kernel share", format_percent(job.system_cpu_fraction), None))
    if job.user_cpu is not None or job.system_cpu is not None:
        cpu.append(
            (
                "user / system",
                "%s / %s" % (format_duration(job.user_cpu), format_duration(job.system_cpu)),
                None,
            )
        )
    freq_hz = job.cpu_freq_hz
    if freq_hz is not None:
        note = ""
        if freq_hz < 1.5e9:
            note = "   (downclocked)"
        cpu.append(("avg clock", format_cpu_freq(freq_hz) + note, None))
    if job.task_count > 1:
        cpu.append(("tasks", str(job.task_count), None))
    spread = job.straggler_spread
    if spread is not None:
        node, task = job.slowest_task
        where = " (task %s on %s)" % (task or "?", node) if node else ""
        cpu.append(
            (
                "slowest task",
                "%s below average%s" % (format_percent(spread), where),
                _pct_of(spread, 1.0),
            )
        )
    sections.append(("cpu", cpu))

    # -- memory --------------------------------------------------------------
    mem = []
    if job.mem_limit_bytes and (not job.req_mem_bytes or job.node_count > 1):
        # Only when there is something to explain. Either ReqMem was unusable and
        # the ceiling came from AllocTRES, or the job spans several nodes -- where
        # the gauge shows the per-node ceiling and AllocTRES shows the total, so
        # without this row the two figures look like a contradiction. On an
        # ordinary single-node job the MEM gauge already said it.
        mem.append(("limit", mem_text(job), None))
    if job.max_rss is not None:
        note = ""
        if job.mem_limit_bytes and job.max_rss > job.mem_limit_bytes:
            note = "   ABOVE THE LIMIT - not a working set"
        mem.append(
            (
                "peak (MaxRSS)",
                "%s   (%s)%s"
                % (format_bytes(job.max_rss), format_percent(job.mem_utilization), note),
                _pct_of(job.mem_utilization, 1.0),
            )
        )
    # Only when "where" is a question with more than one answer. On 6,416 of the
    # 6,440 real jobs here -- 99.6% -- there was one node and one task, so the row
    # said "the peak was on the only node, in the only task". It earns its place on
    # a multi-node or multi-task run, where which rank peaked is the thing you came
    # to find.
    if job.max_rss_node and (job.node_count > 1 or job.task_count > 1):
        mem.append(
            (
                "peak on",
                "%s%s"
                % (job.max_rss_node, " task %s" % job.max_rss_task if job.max_rss_task else ""),
                None,
            )
        )
    # Only when it differs from the peak the MEM gauge already shows. AveRSS
    # equals MaxRSS on 1,318 of 1,341 real records here -- single-task jobs, where
    # there is nothing to average over -- so on 98% of job screens this row was a
    # second copy of a figure three lines above it. It earns its place on the other
    # 2%, where a footprint that grew is the thing you came to find.
    if job.ave_rss is not None and not _matches(job.ave_rss, job.max_rss):
        imbalance = job.rss_task_imbalance
        extra = "   (%.1fx the average)" % imbalance if imbalance and imbalance >= 1.5 else ""
        mem.append(("average", "%s%s" % (format_bytes(job.ave_rss), extra), None))
    # MaxVMSize is deliberately NOT here. It was shown to explain the figure rather
    # than let it alarm, and it did the opposite: on this history it runs at a median
    # of 44x the resident figure, has reached 5,449,406x, and has printed 43.2 TiB --
    # so the row put an enormous number on screen and then spent its own text arguing
    # that the number means nothing. "virtual 1.9 TiB (38x resident - address space,
    # not memory used)" was read exactly that way and reported as making no sense.
    #
    # Nothing consumes it: no finding, no sizing rule. A CUDA process reserves that
    # address space whether or not it touches any of it, so it says nothing about
    # this job that this job did. It stays in --json (virtual_bytes,
    # virtual_to_resident) and in --steps for anyone who has a reason to want it, and
    # if a vmem-enforcing cluster ever needs it on screen, the finding that fires
    # there can carry the number and the reason together.
    if job.max_pages:
        mem.append(("page faults", f"{int(job.max_pages):,}", None))
    sections.append(("memory", mem))

    # -- io ------------------------------------------------------------------
    io = []
    if job.read_bytes is not None:
        io.append(("read", format_bytes(job.read_bytes), None))
    if job.write_bytes is not None:
        io.append(("written", format_bytes(job.write_bytes), None))
    if job.io_rate is not None:
        io.append(("rate", "%s/s sustained" % format_bytes(job.io_rate), None))
    if io:
        sections.append(("filesystem", io))

    # -- gpu -----------------------------------------------------------------
    if job.gpu_count:
        util = job.gpu_utilization
        if util is None:
            # Why it is missing is a property of the cluster, not of the job: a
            # site running AutoDetect=nvml records gres/gpuutil and this row shows
            # a real number. Saying "not recorded by Slurm" everywhere was true
            # here and wrong there.
            from .site import gpu_utilization_note

            util_cell = (gpu_utilization_note(), None)
        else:
            util_cell = (format_percent(util), _pct_of(util, 1.0))
        gpu = [
            ("devices", str(job.gpu_count), None),
            ("utilization", util_cell[0], util_cell[1]),
        ]
        if job.gpu_mem_peak_bytes:
            gpu.append(("device memory", "%s peak" % format_bytes(job.gpu_mem_peak_bytes), None))
        # gpu-hours is devices x elapsed, so on an unterminated record it is
        # devices x (now - start): job 50108238 read "gpu-hours 4615.9" from a
        # RUNNING record 64 days old. Every other consumer already suppresses
        # elapsed-derived claims for these (diagnose drops its resource verdicts,
        # History excludes them from the totals); this row did not.
        if not job.open_ended:
            gpu.insert(1, ("gpu-hours", "%.1f" % (job.gpu_hours or 0.0), None))
        sections.append(("gpu", gpu))

    # -- outcome -------------------------------------------------------------
    outcome = []
    if job.exit_code:
        # Only when non-zero. "exit code 0" on a COMPLETED job restates the state
        # in the header line, and for a clean run it was the entire `outcome`
        # section -- a heading over one line that said nothing.
        text = str(job.exit_code)
        if job.signal:
            text += " (signal %d)" % job.signal
        outcome.append(("exit code", text, None))
    if job.derived_exit_code not in (None, job.exit_code):
        outcome.append(("worst step exit", str(job.derived_exit_code), None))
    if job.reason:
        outcome.append(("reason", job.reason, None))
    if job.energy_joules is not None:
        outcome.append(("energy", "%d J" % job.energy_joules, None))
    if job.comment:
        outcome.append(("comment", job.comment, None))
    sections.append(("outcome", outcome))

    if summarized:
        # Drop the duplicated rows, then any section left with nothing in it.
        trimmed = []
        for title, rows in sections:
            kept = [row for row in rows if (title, row[0]) not in _COVERED_BY_GAUGES]
            if kept:
                trimmed.append((title, kept))
        return trimmed
    return sections


def stamp_short(iso, with_date=True):
    """``2026-06-27T08:12:50`` -> ``06-27 08:12``, for dense table columns.

    Returns ``""`` for a missing timestamp rather than a placeholder date, so an
    absent value never looks like a real one.
    """
    if not iso:
        return ""
    text = str(iso)
    if "T" not in text:
        return text[:11]
    date, _, clock = text.partition("T")
    hhmm = clock[:5]
    if not with_date:
        return hhmm
    return "%s %s" % (date[5:10], hhmm)


# --- slurmwatch-style resource rows ---------------------------------------

_MARKER = "●"
_MARKER_ASCII = "*"


# Everything a gauge row spends outside the bar itself: 2 cells of indent, the
# marker and its space, the 6-cell label and its space, two cells before the
# value and the 11-cell value column.
GAUGE_ROW_OVERHEAD = 2 + 1 + 1 + 6 + 1 + 2 + 11
# What the "   · " between value and detail costs.
_GAUGE_DETAIL_GAP = 5
# Indent of a detail that had to leave its row.
_GAUGE_DETAIL_INDENT = "      "


def resource_rows(
    job,
    ascii_mode: bool = False,
    width: int = 18,
    flat: bool = False,
    max_width: int | None = None,
):
    """The job's resources in slurmwatch's row idiom: ``● LABEL bar value · detail``.

    Deliberately the same shape as the live view. The two tools sit either side of
    one job, and someone who watched it run should recognise the shape of what they
    are reading afterwards. As in slurmwatch the marker is decorative -- it carries
    the resource's identity hue, never a health grade; the bar and the number carry
    the magnitude, and the verdict lives in the findings below.

    A row whose value could not be measured prints ``n/a`` rather than a zero.

    Three rows only -- TIME, CPU, MEM -- because a gauge needs a ceiling to be a
    fraction of. Kernel share, disk rate and GPU count have none, and drawing them
    as bars that can never fill made an unfillable ``░░░░`` read as a measured
    zero; they live in :func:`job_sections` instead, where they are numbers rather
    than proportions. The one case here that still drops its gauge is a MaxRSS
    above the limit: the findings below say that figure is not a working set, so a
    101%-full bar would have the summary contradicting the diagnosis.

    ``max_width`` is the terminal to fit, and only the *detail* answers to it. The
    row up to the value column is a fixed 42 cells and stays that way: a
    width-adaptive bar is a change to the idiom this tool shares with slurmwatch,
    and the one thing every reader of both is entitled to is that a 60%% bar looks
    the same in each. What overran was the tail -- ``● MEM  no percentage  48.5
    GiB   · an upper bound, over the 48.0 GiB limit`` is 86 cells, so the block
    broke on an 80-column terminal, not merely a narrow one, and broke by
    soft-wrapping to column 0 where it lost the marker and the alignment that make
    it read as a block at all. Past the budget the detail moves to its own
    indented line instead, which keeps every figure and costs only a line. Leaving
    ``max_width`` unset keeps the single-line form unconditionally, and at 100
    cells and up the two are identical anyway.
    """
    marker = _MARKER_ASCII if ascii_mode else _MARKER
    rows = []
    detail_budget = None if max_width is None else max_width - GAUGE_ROW_OVERHEAD - width

    def row(label, color, fraction, value, detail="", instead=""):
        """One gauge row. ``instead`` replaces the bar with a phrase.

        Three renderings, and the third exists because the other two both lie when
        there is no fraction to draw. Blanking the cells left a hole where the rows
        above had bars -- "why does mem sometimes have the progress bar and
        sometimes not? it looks very inconsistent". Drawing an empty track instead
        was worse: a track IS the picture of 0%, so the row then read as no memory
        used beside a figure of 58.5 GiB -- "which one should users trust?".

        Neither. So the gauge column says, in words, that it has nothing to show.
        The row keeps its shape and claims no magnitude at all.
        """
        text = Text()
        text.append("  %s " % marker, style=color)
        text.append("%-6s " % label, style=color)
        if instead:
            # Sliced before centring: a phrase wider than the gauge would push the
            # value column out of line with every row above it, which is the
            # alignment the marker/label/gauge/value shape depends on.
            text.append(instead[:width].center(width), style=theme.FAINT)
        else:
            text.append_text(
                bar(
                    None if fraction is None else fraction * 100.0,
                    color,
                    width=width,
                    ascii_mode=ascii_mode,
                    flat=flat,
                )
            )
        text.append("  ")
        # 11 is the widest cell measured over 1,342 real jobs ("123.4 MiB/s");
        # anything narrower lets the DISK rate overrun and shifts its "·" one cell
        # out of line with every row above it.
        text.append("%11s" % value, style=theme.INK)
        bullet = "-" if ascii_mode else "·"
        if detail and (detail_budget is None or len(detail) + _GAUGE_DETAIL_GAP <= detail_budget):
            text.append("   %s %s" % (bullet, detail), style=theme.DIM)
            rows.append(text)
        elif detail:
            # Off the row rather than clipped. The detail is where "over the 48.0
            # GiB limit" lives -- the figure that says the gauge above it is a
            # ceiling and not a measurement -- so dropping or truncating it to fit
            # would take the interpretation and leave the number.
            rows.append(text)
            assert max_width is not None
            for index, line in enumerate(
                wrap(detail, max(20, max_width - len(_GAUGE_DETAIL_INDENT) - 2))
            ):
                rows.append(
                    Text(
                        "%s%s %s" % (_GAUGE_DETAIL_INDENT, bullet if index == 0 else " ", line),
                        style=theme.DIM,
                    )
                )
        else:
            rows.append(text)

    row(
        "TIME",
        theme.ACCENT,
        job.walltime_used,
        format_percent(job.walltime_used),
        "%s of the %s limit" % (format_duration(job.elapsed), format_duration(job.timelimit)),
    )
    row(
        "CPU",
        theme.CPU_COLOR,
        job.cpu_utilization,
        format_percent(job.cpu_utilization),
        # "3.0 of 4 cores busy" -- the same figure the job list shows, and the one
        # that answers "what should --cpus-per-task be".
        "%s cores busy" % cores_text(job),
    )
    if job.mem_limit_bytes and job.max_rss and job.max_rss > job.mem_limit_bytes:
        # A figure above the limit cannot be a working set -- the job would have been
        # killed -- so there is no fraction of the limit to draw and no bar that
        # would not misstate it. "so not a real footprint" was asked what it meant;
        # what it means is that the number bounds the truth from above rather than
        # measuring it, which is what the reader has to know before acting on it.
        row(
            "MEM",
            theme.MEM_COLOR,
            None,
            format_bytes(job.max_rss),
            # Short enough that the row still fits 100 cells: a wrapped gauge row
            # loses its marker and its alignment and stops reading as part of the
            # block. Interpretation first, evidence second -- what the reader needs
            # is that the figure is a ceiling, not that it is 2.5 GiB over one.
            "an upper bound, over the %s limit" % format_bytes(job.mem_limit_bytes),
            instead="no percentage",
        )
    elif job.base_state == "OUT_OF_MEMORY" and job.mem_limit_bytes:
        # The kill is the measurement here, and it outranks the sample. An OOM job
        # whose sampled peak sits *under* the limit is the one case where the
        # gauge actively misleads: job 48850414 on the reporting cluster drew a
        # 4.6% bar -- 188.6 MiB of 4.0 GiB -- on a job the kernel had just killed
        # for exhausting that 4.0 GiB, understating by 21x with nothing on screen
        # connecting the two. `MaxRSS` is sampled every `JobAcctGatherFrequency`
        # seconds and a spike between polls is never recorded, so on a short job
        # the figure is a floor; the OOM state, being event-driven, is not.
        #
        # No fraction is drawn for the same reason the branch above draws none:
        # the honest value is "at least the limit", and any bar short of full
        # would restate the number the findings are about to contradict.
        row(
            "MEM",
            theme.MEM_COLOR,
            None,
            format_bytes(job.mem_limit_bytes),
            "OOM kill — the peak reached this limit; MaxRSS sampled only %s"
            % format_bytes(job.max_rss),
            instead="limit reached",
        )
    else:
        row(
            "MEM",
            theme.MEM_COLOR,
            job.mem_utilization,
            format_percent(job.mem_utilization),
            "%s of the %s limit" % (format_bytes(job.max_rss), format_bytes(job.mem_limit_bytes)),
        )
    return rows
