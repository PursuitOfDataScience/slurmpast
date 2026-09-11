"""The dashboard.

Navigation mirrors slurmwatch: a dashboard you land on, drill-down screens on
single keys, ``q``/``escape`` to come back, digits to jump straight to a row.

The structure is dictated by scale. A real history is 6,574 jobs, and a flat
list of 6,574 anything is not an interface -- it hands the selection problem
back to the reader. So the landing screen shows ~60 *workload groups* ranked by
resources burned, and jobs only appear once you have chosen one.

    Overview  ──enter──>  Workload  ──enter──>  Job
       │                                         (post-mortem)
       └── n: nodes   p: patterns   /: search   f: filter   s: sort

Loading happens in a worker thread: the sacct query is ~1.3 s for seven months
and blocking the first paint on it would feel broken.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import time
from collections.abc import Generator
from typing import Any, ClassVar, cast

from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.screen import ModalScreen, Screen
from textual.widgets import DataTable, Footer, Header, Input, Static

from . import render, theme
from .diagnose import diagnose, looks_like_noop
from .duration import format_bytes, format_duration, format_percent, humanize_window, plural
from .index import (
    FILTERS,
    GROUP_SEARCH_FIELDS,
    JOB_SEARCH_FIELDS,
    SORTS,
    GroupStats,
    History,
    filter_groups,
    filter_jobs,
    next_sort,
    sort_groups,
    sort_label,
)
from .logs import assign_logs, load_for, read_tail
from .nodes import compress_nodelist, excluded_tail, node_table, suggest_exclude

BASE_CSS = """
Screen { background: $surface; align-horizontal: center; }
/* Banner, stats and table centred as ONE block so they keep a common left edge.
   Width is set from Python -- see CentredContent. Header and Footer are 1fr bars
   and span the terminal, which is what a bar should do. */
#content { height: 1fr; }
#banner { height: auto; padding: 0 1; color: $text-muted; }
/* A blank line above and below. Header bar, stats and column headings on three
   consecutive rows read as one squeezed block. */
#summary { height: auto; padding: 1 1 1 1; }
DataTable { height: 1fr; }
DataTable > .datatable--cursor { background: $primary 30%; }
#detail { padding: 0 1; height: 1fr; }
#searchbar { height: auto; padding: 0 1; display: none; }
#searchbar.visible { display: block; }
.pane-title { text-style: bold; padding: 1 1 0 1; }
"""


# Explicit copy keys, because selection support depends on the Textual version:
# 0.89 (what a cluster conda env is likely to have) has no in-app text-selection
# API at all, while 8.x does. Not capturing the mouse gives terminal-native
# selection on every version, and these keys work regardless.
#
# copy_to_clipboard emits OSC 52, which is the better mechanism over SSH -- it
# reaches the clipboard on the machine you are sitting at, not the login node --
# but it fails silently on some terminals and needs `set -g set-clipboard on`
# inside tmux. So every copy is ALSO written to a file and the notification names
# it; that way the feature never half-works with no way to tell.
_SCREEN_BINDINGS = [
    # All three hidden from the footer, listed under `?`. Ten entries do not fit an
    # 80-column footer and Textual truncates the tail, so every label that earns a
    # slot costs a later one its place: with "Copy row" shown, `r Reload` and
    # `w Time range` fell off the end at 100 columns entirely. Copying is a power
    # move you go looking for; a time range is something you need told.
    Binding("y", "copy_row", "Copy row", show=False),
    Binding("Y", "copy_view", "Copy view", show=False),
    # `?` belongs here, with the pair every screen shares, and not repeated on each
    # screen -- which is how two of the five came to be without it. `HelpScreen`
    # documents `m` and `c` as "on the nodes screen: ...", and the nodes screen was
    # one of the two that could not open it.
    Binding("question_mark", "help", "Help", show=False),
]


# Windows `w` cycles through, shortest first. Only day and week specs appear
# because sacct rejects anything coarser -- verified against Slurm 20.11.8:
# `-S now-6months` and `-S now-1year` both fail with "Invalid time specification
# (pos=4)", while every spec below returns rows. The labels are not written out
# here: humanize_window derives them, so the cycle and the title bar cannot drift.
WINDOWS = ("now-1day", "now-7days", "now-30days", "now-12weeks", "now-52weeks")


def _loader_accepts_since(loader) -> bool:
    """Whether this loader can be re-run for a different window.

    The CLI passes a loader taking a sacct time spec; ``--demo`` and the tests
    pass a zero-argument one, and there is no window to cycle in those cases.
    Decided by signature rather than by catching TypeError from the call, which
    would swallow a TypeError raised *inside* the loader and misreport it as
    "cannot change the window".
    """
    import inspect

    try:
        inspect.signature(loader).bind("now-7days")
    except (TypeError, ValueError):
        return False
    return True


def _clip_path() -> str:
    """Where the clipboard fallback is written, created private to the user.

    The contents are whatever row or view was on screen -- job names, partitions,
    workdirs, run counts -- so this file is not public even though nothing in it
    is a secret in the credential sense.

    ``mode=0o700`` on :func:`os.makedirs` applies only when the directory is
    *created*, and the ``chmod`` is what closes an existing one. Every install
    predating this had it at whatever the umask gave -- ``drwxrwxr-x`` under the
    common ``umask 002`` -- and a fix that only sets the mode on first creation
    leaves exactly the users who already have the problem still having it.
    """
    import os

    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    directory = os.path.join(base, "slurmpast")
    try:
        os.makedirs(directory, mode=0o700, exist_ok=True)
    except OSError:
        return ""
    # Best effort: a directory we cannot chmod is still usable, and the file
    # below carries its own mode regardless.
    with contextlib.suppress(OSError):
        os.chmod(directory, 0o700)
    return os.path.join(directory, "clip.txt")


def _write_clip(path: str, text: str) -> None:
    """Write the fallback file 0600, whatever the umask says.

    ``os.open`` with an explicit mode is umask-independent for the bits it clears,
    but the mode argument is honoured *only on creation* -- reopening a file that
    already exists leaves its permissions alone. The ``fchmod`` is therefore the
    part that matters for anyone upgrading: without it a ``clip.txt`` already on
    disk at ``0644`` or ``0664`` keeps those bits forever.

    ``fchmod`` on the descriptor rather than ``chmod`` on the path, so there is no
    window between opening and tightening in which the name could point somewhere
    else.
    """
    import os

    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    # The close is guarded to the window in which the descriptor is still OURS.
    # It used to wrap the write as well, and `os.fdopen` takes ownership -- so a
    # write that failed was closed once by the `with` and again here, and the
    # second close raised `EBADF`, which then REPLACED the real error. Measured
    # under `RLIMIT_FSIZE`:
    #
    #     raised:  OSError: [Errno 9] Bad file descriptor
    #     masking: OSError: [Errno 27] File too large
    #
    # A full filesystem or an exceeded quota -- the two reasons this actually
    # fails -- both arrived as "Bad file descriptor", which points nowhere.
    try:
        os.fchmod(fd, 0o600)
        handle = os.fdopen(fd, "w", encoding="utf-8")
    except BaseException:
        os.close(fd)
        raise
    with handle:
        handle.write(text if text.endswith("\n") else text + "\n")


def _discard_clip() -> None:
    """Remove the fallback file. A copy buffer has no reason to outlive the app.

    Called from :func:`run`'s ``finally`` rather than a Textual unmount hook, so
    it also runs when the app exits by exception -- which is when a stale file is
    least likely to be noticed.
    """
    import os

    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    with contextlib.suppress(OSError):
        os.unlink(os.path.join(base, "slurmpast", "clip.txt"))


class ScreenChrome:
    """What every screen does identically: copy, and open the help.

    ``y`` copies the focused row, ``Y`` the whole view -- subclasses provide the
    text and this handles delivery and the notification. ``?`` opens
    :class:`HelpScreen`.

    ``action_help`` lives here because it was written out on three screens and
    omitted from the other two, so `?` was dead on the patterns and nodes screens
    while `HelpScreen` carried two rows explaining the nodes screen's own keys.
    Paired with ``_SCREEN_BINDINGS``: one list, one action, five screens.
    """

    @property
    def sp(self) -> SlurmpastApp:
        """This screen's app, narrowed to our concrete type.

        Deliberately NOT an ``app: SlurmpastApp`` annotation. That overrides
        ``MessagePump.app``, and mypy reports the clash once per subclass -- the
        error lands on the ``class X(ScreenChrome, Screen)`` line, not on the
        annotation, so it cannot even be suppressed where it is written. A
        separate accessor narrows the type with no override and no suppression,
        and reads explicitly at each use.

        The mixin has no base class, so it cannot know it will be combined with a
        Screen that supplies ``app``. That single assumption is asserted here --
        one ignore, on the one line that makes it -- rather than spread across
        thirty call sites or hidden behind a Protocol shim.
        """
        return cast(SlurmpastApp, self.app)  # type: ignore[attr-defined]

    def clipboard_row(self) -> str:
        return ""

    def clipboard_view(self) -> str:
        return ""

    def action_copy_row(self) -> None:
        self._deliver(self.clipboard_row(), "row")

    def action_copy_view(self) -> None:
        self._deliver(self.clipboard_view(), "view")

    def action_help(self) -> None:
        self.sp.push_screen(HelpScreen())

    def _deliver(self, text: str, what: str) -> None:
        if not text:
            self.sp.notify("nothing to copy here", severity="warning", timeout=3)
            return
        self.sp.copy_to_clipboard(text)
        path = _clip_path()
        written = False
        if path:
            try:
                # Explicit UTF-8, not the locale's encoding. What gets copied always
                # contains ``●``, ``·`` and box drawing, so on a Python whose
                # preferred encoding resolves to ASCII this raised UnicodeEncodeError
                # -- which is a ValueError, so the OSError handler below would not
                # have caught it and `y` would have thrown out of a UI action.
                _write_clip(path, text)
                written = True
            except (OSError, UnicodeError):
                written = False
        lines = text.count("\n") + 1
        message = "copied %s (%d line%s) to the clipboard" % (
            what,
            lines,
            "" if lines == 1 else "s",
        )
        if written:
            message += "\nalso written to %s" % path
        self.sp.notify(message, timeout=6)


def _header() -> Header:
    """A header with no icon.

    Textual's default "⭘" is a clickable shortcut to its command palette. Two
    reasons it does not belong here: mouse capture is off by default so it cannot
    be clicked at all, and we expose no customised palette behind it. A
    non-functional control in the top-left of every screen is worse than none.

    The kwarg is passed defensively -- CI exercises Textual 0.86 through 8.x, and
    a signature change should degrade to the default rather than crash the app.
    """
    try:
        return Header(show_clock=False, icon="")
    except TypeError:  # pragma: no cover - only on a Textual without `icon`
        return Header(show_clock=False)


# Width of the table before the first layout pass has run, and the floor below
# which shrinking columns stops helping. A vertical scrollbar takes a couple of
# cells once the rows overflow, so the layout leaves room for one rather than
# spilling into a horizontal scrollbar.
# Floor for an inline path on a job screen: below this, eliding stops buying
# anything and only hides the filename. The real budget comes from the width there
# actually is -- see JobScreen._path_budget. `p` toggles the full value, and
# --plain never elides, so a pasted report keeps the whole path.
# Share of a workload's runs a qualifier must reach before the summary names it.
# One idle run in 132 is 0.8% and not a fact anyone acts on; five cancelled in 15
# is a third of the workload and is why its numbers do not add up.
QUALIFIER_SHARE = 0.10

# A floor and deliberately no ceiling: `_elide_budget` measures against the width
# there is, because whether a path wraps is a function of the width there is. A
# `_MAX_PATH_WIDTH` was carried here unused; it would elide a path that fits.
_MIN_PATH_WIDTH = 28
_DEFAULT_TABLE_WIDTH = 96
_MIN_TABLE_WIDTH = 40
_SCROLLBAR = 2
# Below this a wrapped sentence stops being a sentence, so narrower terminals get
# an overrun rather than one word per line.
_MIN_PROSE_WIDTH = 32


def _text_width(screen) -> int:
    """Cells the text on ``screen`` actually gets.

    Not to be confused with ``_content_width`` below, which sizes a *table* from
    its column layout. This one measures a screen for prose.

    Measured on the *widget the text goes into*, not on the screen. Screen width
    minus a constant ``_SCROLLBAR`` is what both callers below used to do, and it
    is two cells optimistic on ``JobScreen``, whose ``#body`` is 96 wide inside a
    100-cell screen. Two cells is enough: a finding wrapped to 90 was drawn at
    8 + 90 = 98, Textual soft-wrapped the overflow, and the reader got

        midway3-0385 failed 12 of 12 placements there (100.0%, ...) against 25.0%
    on
        every other node for cot-exp.

    -- the orphan at column 0 that ``_prose_width`` exists to prevent, surviving
    inside it because the chrome was guessed rather than read.

    The screen is the *ceiling*, not merely a fallback, and that is load-bearing: a
    Static can be sized to its content rather than to its container, in which case
    it reports a width WIDER than the terminal and trusting it wraps text off the
    right-hand edge. Textual 0.89 does exactly that with ``WorkloadScreen``'s
    ``#summary`` -- caught by CI's oldest-supported-Textual job, which had the
    banner going out at 83 cells on a 70-cell screen. So: the narrower of what the
    widget claims and what the terminal has.

    It is also the fallback for the two moments there is nothing to measure -- before
    the first layout pass, when the widget has no size at all, and before *mount*,
    when querying the screen raises because it is not in the DOM yet (which
    ``WorkloadScreen`` reaches: its ``on_mount`` builds the banner). Callers render
    again after the first layout pass, see ``JobScreen.on_mount``, so neither guess
    survives to the screen.
    """
    screen_width = screen.size.width or screen.app.size.width or _DEFAULT_TABLE_WIDTH
    ceiling = max(0, screen_width - _SCROLLBAR)
    try:
        for widget in screen.query("#body, #summary"):
            if widget.size.width:
                return min(widget.size.width, ceiling)
    except Exception:  # not mounted yet; the ceiling is the honest answer
        pass
    return ceiling


def _prose_width(screen, indent: int) -> int:
    """Wrap width for indented prose on ``screen``, from the terminal there is.

    The plain renderer solved this and said why (``report._prose_width``): "These
    were hardcoded at 72, 82 and 84, so a finding hard-broke mid-sentence two thirds
    of the way across a wide terminal and overran a narrow one." The dashboard kept
    the constants -- findings wrapped at 86 and actions at 82 under an 8-cell indent,
    up to 94 cells whatever the terminal was -- so below ~96 columns Textual
    re-wrapped the already-wrapped text and the orphan landed at column 0, with the
    indent that separates evidence from its heading gone.
    """
    return max(_MIN_PROSE_WIDTH, _text_width(screen) - indent)


# Cells before a finding's title: two of indent, the four-cell severity tag and
# the two spaces after it. The plain renderer reserves the same, spelled from the
# tag it drew (``2 + len(tag) + 3``) -- one space either side of the brackets it
# adds and this one does not.
_FINDING_TITLE_INDENT = 2 + 4 + 2


def _empty_reason(screen, noun: str) -> str:
    """:func:`render.nothing_matches`, filled in from what this screen narrowed by.

    A screen knows its own filter and search; the wording is shared so the overview
    and the job list cannot explain the same empty table differently.
    """
    mode = getattr(screen, "filter_mode", "all")
    label = "" if mode == "all" else dict(FILTERS).get(mode, mode)
    return render.nothing_matches(
        noun, filter_label=label, search=getattr(screen, "search_text", "")
    )


def _finding_lines(screen, body, finding) -> None:
    """One finding appended to ``body``: chip, title, evidence, action.

    Written out twice here and twice in `report.py`, and the four copies had come
    apart in two places. The arrow was "→ " on this side and "-> " on that, for the
    same line of the same finding -- now `render.ACTION_ARROW`, so ``--ascii`` is
    what chooses between the two alphabets rather than which file the code is in.

    And the title was the one line of the three that nothing wrapped. `report` had
    learned to ("A title is a sentence -- 'Peak memory reads above the limit, yet
    nothing was OOM-killed' is 61 cells"); this had not, so Textual soft-wrapped it
    and dropped ``OOM-killed`` to column 1, out from under the tag, on any terminal
    below 74 columns. The continuation hangs under the title instead, which is what
    the tag width is reserved for.
    """
    body.append("  ")
    body.append_text(render.severity_chip(finding.severity))
    body.append("  ")
    for index, line in enumerate(
        render.wrap(finding.title, _prose_width(screen, _FINDING_TITLE_INDENT))
    ):
        prefix = "" if index == 0 else " " * _FINDING_TITLE_INDENT
        body.append("%s%s\n" % (prefix, line), style="bold %s" % theme.INK)
    # Measured against the terminal, not the old fixed 86 / 82. See _prose_width:
    # 8 cells of indent over an 86-cell wrap is 94, so below ~96 columns every
    # finding was hard-wrapped and then soft-wrapped again, dropping its tail to
    # column 0.
    for line in render.wrap(finding.evidence, _prose_width(screen, 8)):
        body.append("        %s\n" % line, style=theme.DIM)
    if finding.action:
        for index, line in enumerate(
            render.wrap(finding.action, _prose_width(screen, render.ACTION_INDENT))
        ):
            body.append(
                "        %s%s\n"
                % (render.ACTION_ARROW if index == 0 else render.ACTION_HANG, line),
                style=theme.ACCENT if index == 0 else theme.DIM,
            )
    body.append("\n")


def indent_room(screen, indent: int) -> int:
    """Cells left for text on ``screen`` after ``indent`` of leading space."""
    return _prose_width(screen, indent)


def _sync_columns(table: DataTable, spec, current, content=None, available=None):
    """Give ``table`` exactly the columns its current width calls for.

    Rebuilding is the only way to resize a DataTable's columns, and it drops the
    rows along with them, so it happens only when the layout actually changed --
    not on every search keystroke.

    ``content`` is the longest real cell per column, so a flexible column stops
    growing once its content fits instead of stretching into empty space.

    ``available`` is the SCREEN's width, passed in rather than read off the table.
    The table now sits inside a container sized to the columns this function picks,
    so asking the table how wide it is would be asking about its own output: the
    column set would freeze at _DEFAULT_TABLE_WIDTH and never track the terminal.
    """
    # `size` is zero until the first layout pass; on_resize calls back after it.
    width = available or table.size.width or _DEFAULT_TABLE_WIDTH
    room = max(_MIN_TABLE_WIDTH, width - _SCROLLBAR)
    # Spend the leftover here, unlike the plain renderer: a table that has to
    # survive being pasted into a ticket should be as narrow as its content, but a
    # dashboard owns the terminal and a 100-cell table centred in 150 reads as thin.
    layout = render.fit_columns(spec, room, content=content, fill_to=room)
    if layout != current or not table.columns:
        table.clear(columns=True)
        for label, column_width in layout:
            table.add_column(label, width=column_width)
    return layout


def _rows_already_drawn(screen, layout, key) -> bool:
    """Whether the table already holds exactly this layout and these rows.

    `on_mount` populates the table and the first resize populates it again -- with
    the *same* layout and the *same* rows, because a screen pushed onto a laid-out
    app already has its size. On the demo that is invisible. On a real 30-day
    history it is 13,363 rows built twice, and `a` -- the flat job list -- took
    **6.8 seconds** to open, of which none was slurmpast's own arithmetic: the cell
    values for all 13,363 rows compute in 0.32s, and the rest is Textual laying out
    a table it is about to discard.

    Deferring the mount build to `call_after_refresh` was tried and measured at
    3.64s against this guard's 3.55s -- it buys nothing, because the guard already
    catches the second call, so it is not here. Measured rather than reasoned: the
    first account of this bug blamed a provisional mount-time width, and the trace
    that was supposed to confirm it showed both calls computing an identical
    layout.

    ``key`` is the caller's fingerprint of the row set -- the job ids, or the
    workload labels. NOT ``id(rows)``, which was the first attempt and never
    matched: every caller builds a fresh list, so its identity differs on every
    call and the guard silently never fired. Caught by tracing rather than by
    reasoning -- the trace showed two builds at an *identical* layout, which is
    what gave it away.

    Building the tuple costs microseconds against the seconds it saves, and unlike
    a cheaper fingerprint it cannot miss a filter that changes the middle of the
    list while preserving its length and its ends.
    """
    signature = (tuple(layout), key)
    if getattr(screen, "_drawn", None) == signature:
        return True
    screen._drawn = signature
    return False


def _resize_changed_anything(screen) -> bool:
    """Whether this ``on_resize`` is a real resize.

    Textual sends `Resize` when a screen is first laid out, so `on_mount`'s
    build was immediately followed by a second one at the SAME size -- and while
    `_rows_already_drawn` stops the rows being drawn twice, everything around
    them still ran twice: the filter, the sort, the summary's per-job counts.
    On a 29,617-job list that second pass was 122 ms of the 391 ms `a` took, for
    a layout that could not have changed.

    Recorded on the screen rather than compared against the table, because two
    of the three callers here rebuild their columns from `self.size.width` and
    that is the input this is guarding.
    """
    size = screen.size
    if getattr(screen, "_sized_at", None) == size:
        return False
    screen._sized_at = size
    return True


def _content_width(layout, padding: int = 2) -> int:
    """Cells a table of ``layout`` occupies: columns, DataTable's cell padding, a
    scrollbar. This is what the centring container is sized to."""
    return sum(width for _, width in layout) + padding * len(layout) + _SCROLLBAR


class CentredContent:
    """Sizes ``#content`` to what is in it, so the Screen can centre the block.

    fit_columns leaves width no column needs UNUSED -- deliberately, because
    stretching a table into empty space makes canyons between its columns -- and
    the leftover then sat entirely on the right, which reads as the layout having
    given up half the terminal. Centring spends it evenly instead.

    An explicit width rather than `width: auto`: the children are `1fr` so they
    fill the block, and a 1fr child inside an auto parent is circular -- the parent
    asks the child how wide it is while the child asks the parent.
    """

    def fit_content(self, layout) -> None:
        try:
            content = self.query_one("#content")  # type: ignore[attr-defined]
        except Exception:
            return  # a screen composed without the container centres nothing
        # Never wider than the terminal. The never-dropped columns have a floor of
        # their own, so on a very narrow terminal the table wants more room than
        # there is; asking for it would hand the Screen a horizontal scrollbar
        # where it used to simply clip.
        screen_width = self.size.width  # type: ignore[attr-defined]
        wanted = _content_width(layout)
        content.styles.width = min(wanted, screen_width) if screen_width else wanted


def _breathe():
    """Hand the GIL back, so a keypress is answered while a worker is thinking.

    Python's thread switch interval is 5 ms, which is enough while a worker is
    short and not while it is long: at `assign_logs`'s original 16.7 s an arrow
    key took between 0.85 s and 5.4 s to redraw. The pass is 1.2 s now and this
    keeps what is left of it out of the way -- see `logs.PACE_EVERY` for how often
    it is called and what that costs.

    `sleep(0)` is NOT enough: CPython treats it as a no-op yield that the same
    thread usually wins straight back. A millisecond is the smallest interval that
    reliably lets the UI thread run, and 59 of them over a whole history is 59 ms.
    """
    time.sleep(0.001)


class FastDataTable(DataTable):
    """A DataTable that does not re-measure cells whose column width is fixed.

    Textual's ``_update_dimensions`` walks every new row and calls ``measure()``
    on every cell in it, to grow each column's ``content_width``. That figure is
    read back in exactly one place -- ``Column.get_render_width``, as
    ``self.content_width if self.auto_width else self.width`` -- and every column
    in this app is added with an explicit ``width=`` by :func:`_sync_columns`. So
    on these tables the entire pass computes a number nothing will read.

    It is not a small number of cells. Measured on a real seven-day history of
    29,624 jobs, pressing ``a`` for the flat job list:

        add_row x29,617                 0.70 s
        _update_dimensions              4.12 s   <- 355,404 measure() calls
        _update_dimensions, skipped     0.15 s

    and the same pass ran again on every filter change and every search
    keystroke, which is why typing one letter into the search box on that screen
    cost 9.6 s.

    The skip is expressed as ``super()._update_dimensions(())`` rather than as a
    reimplementation, because the tail of that method is load-bearing -- it sets
    ``virtual_size``, which is what the scrollbar and the scroll extent come from.
    Handing it an empty row set runs the tail and skips only the loop.

    Conditions, checked rather than assumed, because being wrong here means
    columns silently sized to nothing:

    * every column has a fixed width (``auto_width`` false),
    * no row carries a label -- ``_label_column`` IS auto-width, and a labelled
      row is the one case where the loop's result is read,
    * no row is of auto height, which the loop is also what measures,
    * ``fixed_cell_sizes`` has not been turned off by the caller.

    The last two are noticed in :meth:`add_row` rather than looked for in the
    loop being skipped, because looking for them there is the O(rows) walk this
    exists to avoid. No screen in this package passes either, so in practice the
    switch never flips -- it is here so that a screen which starts to cannot get
    a silently wrong layout for it.
    """

    #: Set False to get stock Textual behaviour back on one table.
    fixed_cell_sizes: bool = True

    def add_row(self, *cells, height=1, key=None, label=None):
        if height is None or label is not None:
            # An auto-height row has to be rendered to find out how tall it is,
            # and a labelled row grows `_label_column`, which is auto-width.
            # Both are what the skipped loop does. One row of either kind and
            # this table goes back to stock behaviour for good.
            self.fixed_cell_sizes = False
        return super().add_row(*cells, height=height, key=key, label=label)

    def _update_dimensions(self, new_rows) -> None:
        if (
            self.fixed_cell_sizes
            and not self._labelled_row_exists
            and not any(column.auto_width for column in self.columns.values())
        ):
            new_rows = ()
        super()._update_dimensions(new_rows)


def _digit_bindings(action: str):
    """Type a row number to jump to it, exactly as slurmwatch does for nodes."""
    return [Binding(str(d), f"{action}('{d}')", show=False) for d in range(10)]


class _RowJump:
    """Multi-digit row jumping shared by the table screens.

    Digits accumulate so "12" reaches row 12 rather than row 1 then row 2, and
    the buffer clears on any other key. Committing eagerly on each digit is what
    makes a two-digit jump impossible.
    """

    def __init__(self) -> None:
        self._buffer = ""

    def on_key_pressed(self, key: str) -> None:
        """End a pending jump on anything that is not a digit.

        Without this the buffer outlives the jump: press ``3`` to reach row 3,
        navigate elsewhere, press ``7`` later and the accumulated "37" lands on a
        row neither key asked for. Nothing was calling ``clear``.
        """
        if not (len(key) == 1 and key.isdigit()):
            self.clear()

    def push(self, digit: str, limit: int) -> int | None:
        self._buffer += digit
        try:
            value = int(self._buffer)
        except ValueError:
            self._buffer = ""
            return None
        if value == 0 or value > limit:
            self._buffer = digit
            value = int(digit)
        if value * 10 > limit:  # no longer number can exist -- commit now
            self._buffer = ""
        return value if 1 <= value <= limit else None

    def clear(self) -> None:
        self._buffer = ""


# Keys that should still drive the table while the search box has focus. An Input
# swallows the arrows (left/right move its caret, up/down do nothing at all), so
# once you had typed a query the highlight could not be moved AT ALL until you
# pressed enter -- and nothing on screen said so.
_TABLE_KEYS = frozenset(["up", "down", "pageup", "pagedown", "home", "end"])


def _steer_table(screen, table_id: str, key: str) -> bool:
    """Send a navigation key to the table even when the search box has focus.

    Type to filter, arrow to choose, enter to commit -- the behaviour of every
    other filter box. Returns whether the key was handled.
    """
    if key not in _TABLE_KEYS:
        return False
    if not screen.query_one("#search", Input).has_focus:
        return False
    table = screen.query_one(table_id, DataTable)
    if not table.row_count:
        return True
    if key in ("up", "down"):
        table.move_cursor(row=table.cursor_row + (1 if key == "down" else -1))
    elif key in ("pageup", "pagedown"):
        step = max(1, table.size.height - 2)
        table.move_cursor(row=table.cursor_row + (step if key == "pagedown" else -step))
    else:
        if key == "end":
            # `end` means the LAST row, and on a screen still streaming its rows
            # in the table's idea of the last one is wherever the fill has got
            # to. Finish it, so the key lands where the reader expects.
            ensure = getattr(screen, "ensure_all_rows", None)
            if ensure is not None:
                ensure()
        table.move_cursor(row=0 if key == "home" else table.row_count - 1)
    return True


#: How long the search box waits for the next keystroke before re-filtering.
#: Rebuilding the flat job list is 100-311 ms at 29,617 jobs -- `DataTable.clear`
#: alone is 139 ms of it, and that is Textual's, not ours -- so typing "test" was
#: four of those back to back. One rebuild when the typing stops is what every
#: other search box does, and 150 ms is short enough that it still reads as
#: immediate. Enter commits without waiting, and escape cancels without waiting,
#: so nothing that ends a search is delayed by this.
_SEARCH_SETTLE = 0.15


def _debounce_search(screen, value: str) -> None:
    """Apply ``value`` to ``screen.search_text`` once the keystrokes stop."""
    _cancel_search_debounce(screen)
    screen._search_timer = screen.set_timer(
        _SEARCH_SETTLE, lambda: setattr(screen, "search_text", value)
    )


def _cancel_search_debounce(screen) -> None:
    timer = getattr(screen, "_search_timer", None)
    if timer is not None:
        timer.stop()
        screen._search_timer = None


def _dismiss_search(screen, table_id: str) -> bool:
    """Cancel an open search: clear it, hide the box, hand focus back.

    Returns whether there was a search to cancel, so the caller knows to stop the
    key event. Without this, `escape` reached the screen binding while the input
    had focus -- which on the overview is Quit, so cancelling a search ended the
    session, and on a job list popped the screen. Escape is the universal "cancel
    this"; enter commits the filter and closes the box, escape discards it.
    """
    if not screen.query_one("#search", Input).has_focus:
        return False
    # Before the reset, or a debounce still in flight would put the cancelled
    # query straight back a moment later.
    _cancel_search_debounce(screen)
    screen.query_one("#searchbar").remove_class("visible")
    screen.query_one("#search", Input).value = ""
    screen.search_text = ""
    screen.query_one(table_id, DataTable).focus()
    return True


class SearchBar(Input):
    """The free-text filter, told what its own screen can match.

    The placeholder was one fixed string on both screens and promised more than
    either delivered: on the overview a job id, a state and a node all returned
    nothing, because a workload rollup has none of the three to match against.
    Built from the screen's field list now, so the invitation and the behaviour
    cannot part again. See render.search_hint.
    """

    def __init__(self, fields=JOB_SEARCH_FIELDS) -> None:
        super().__init__(placeholder="filter by %s…" % render.search_hint(fields), id="search")


# The help box, and the chrome CSS charges it: a round border either side and
# `padding: 1 2`. Named rather than counted at the call site so the wrap width and
# the CSS cannot say different numbers.
_HELP_BOX_WIDTH = 78
_HELP_BOX_CHROME = 6
# Cells the key column occupies, indent included: `"  %-14s "`. A wrapped
# description hangs to this so it stays under the text it continues rather than
# restarting in the key column.
_HELP_KEY_WIDTH = 17

# One row per key, in the order a reader meets them. Two of these are the reason
# this screen had to be wrapped at all: at 72 cells of content the `a` row ran 3
# over and the `Y` row 2, so Textual soft-wrapped both and dropped the orphan at
# column 2 -- the two-column layout broken on the one screen whose whole job is
# explaining the app.
_HELP_KEYS = (
    ("enter / →", "open the selected row"),
    ("q / escape / ←", "back, or quit from the overview"),
    ("1-9…", "jump straight to a row by number"),
    # Both sets, because one help screen covers every screen and they differ: a
    # workload rollup has no single job id, state or node to match on.
    (
        "/",
        "search — the overview matches %s; a job list also matches %s"
        % (
            render.search_hint(GROUP_SEARCH_FIELDS),
            render.search_hint(tuple(f for f in JOB_SEARCH_FIELDS if f not in GROUP_SEARCH_FIELDS)),
        ),
    ),
    ("f", "cycle filter: all → problems → failed → idle"),
    ("s", "cycle sort"),
    ("n", "which nodes your jobs fail on, controlled for workload"),
    # Both shown in the nodes screen's own footer and, until now, in no help at
    # all -- the only two visible bindings this list left out, and the pair that
    # undoes the control the `n` line above advertises.
    ("m", "on the nodes screen: measure hangs or failures"),
    ("c", "on the nodes screen: drop the workload control (confounded)"),
    # `p` means something else entirely on a job screen, where this help is also
    # reachable: JobScreen binds it to `toggle_paths`, and it is `show=False`, so a
    # reader pressing it there got neither the patterns screen this line promised
    # nor any hint of what they had actually done.
    (
        "p",
        "what keeps failing the same way, across runs — on a job screen, "
        "the full log paths instead",
    ),
    ("a", "every job in one flat list, ignoring the workload grouping"),
    ("y", "copy the selected row to the clipboard"),
    ("Y", "copy the whole view (a job screen copies the full report)"),
    ("w", "how far back to look: 1 day → 7 → 30 → 12 weeks → 52"),
    ("r", "reload the same window from sacct"),
    ("?", "this help"),
)

_HELP_NOTES = (
    "A row on the overview is one workload: every run whose job name matches once "
    'digits are folded to "#", so cot-exp1 and cot-exp2 share a row. Its counts and '
    "hour totals cover all of those runs. Open a row to see the real job names.",
    "FLAGGED counts runs this tool marks for a look: they failed, or they held the "
    "allocation without computing. One number, because those two overlap — open the "
    "row to see which. It says what was flagged, not that it was your mistake; a "
    "failure can be expected. COMPLETED plus FLAGGED can be less than RUNS: a "
    "cancelled run is neither, since a deliberate kill and an abandoned one are "
    "identical in accounting.",
    # The rate is not decoration: the CPU / GPU-HOURS column pair is on screen
    # here, so a row with fewer CPU-hours ranked above one with more looks
    # arbitrary without it. `--plain` has always printed it in the caption above
    # the same table, and `report.py` asserted in a comment that "the dashboard
    # puts the same two facts under `?`" -- the digit fold was, the rate never
    # was. Read from `render`, so the two surfaces cannot quote different rates.
    "Groups are ranked by resources burned, not run count: a 5-run group that cost "
    "400 GPU-hours outranks 400 two-second probes. Weighted at %s."
    % render.gpu_hours_equivalence(),
    "Selecting text: just drag. Mouse capture is off by default, so your terminal "
    "handles selection exactly as it does elsewhere. Press M to hand the mouse to "
    "the app instead (enables clicking and wheel scrolling, disables drag-select), "
    "or start --mouse.",
)


class HelpScreen(ModalScreen[None]):
    """The keys, wrapped to the box they are drawn in.

    Every other surface learned this in rounds five to seven -- `report._prose_width`
    ("These were hardcoded at 72, 82 and 84, so a finding hard-broke mid-sentence"),
    then `tui._prose_width`, then the node screen's last two `render.wrap` calls.
    This screen was missed by all three, and it had all three symptoms at once:

    * two key rows overran the 72 cells the box actually offers and Textual dropped
      the continuation at column 2, out from under the description it continues;
    * the clip-path line is built from `_clip_path()`, so its length is site
      controlled -- 78 cells on the machine this was found on and unbounded in
      general, which is round six's folded-workload-name trap in a new place;
    * `width: 78` is a floor as well as a ceiling in Textual, so below an
      80-column terminal the box was drawn wider than the screen and simply cut,
      with no marker -- the one thing `render.clip` exists to prevent.

    So the width is measured, not assumed, and the body is rebuilt on resize.
    """

    BINDINGS: ClassVar = [
        Binding("escape", "dismiss", "Back"),
        Binding("q", "dismiss", "Back"),
        Binding("question_mark", "dismiss", "Back", show=False),
    ]
    CSS = (
        BASE_CSS
        + """
    HelpScreen { align: center middle; }
    #help-box { height: auto; border: round $primary; background: $panel; padding: 1 2; }
    """
    )

    def __init__(self) -> None:
        super().__init__()
        # Retained so tests read what was composed rather than the widget, as
        # NodesScreen does: `Static.renderable` exists in textual 0.89 and not 8.x.
        self.help_text = Text()

    def compose(self) -> ComposeResult:
        with Vertical(id="help-box"):
            yield Static(Text("slurmpast — keys", style="bold %s" % theme.ACCENT), id="help-title")
            yield Static(id="help-body")

    def on_mount(self) -> None:
        self.render_body()

    def on_resize(self) -> None:
        if self.is_mounted:
            self.render_body()

    def box_width(self) -> int:
        """The box's width: what it asks for, or the terminal if that is narrower.

        Less ``_SCROLLBAR``, for the reason ``_text_width`` gives: the help is
        taller than a short terminal, so the modal grows a scrollbar, and a box
        sized to the full width then loses its right border to it. Above 80 columns
        the cap binds first and the box is unchanged.
        """
        screen = self.size.width or self.app.size.width or _HELP_BOX_WIDTH
        return max(_MIN_PROSE_WIDTH, min(_HELP_BOX_WIDTH, screen - _SCROLLBAR))

    def render_body(self) -> None:
        width = self.box_width()
        self.query_one("#help-box", Vertical).styles.width = width
        text = Text()
        inner = max(_MIN_PROSE_WIDTH, width - _HELP_BOX_CHROME)
        # The description column, or the whole line on a terminal too narrow to
        # hold a two-column layout at all -- below that the hanging indent costs
        # more than the alignment buys.
        hanging = _HELP_KEY_WIDTH if inner > _HELP_KEY_WIDTH + 20 else 0
        for key, description in _HELP_KEYS:
            lines = render.wrap(description, max(_MIN_PROSE_WIDTH, inner - hanging))
            text.append(
                "  %-14s " % key if hanging else "  %s\n    " % key, style="bold %s" % theme.ACCENT
            )
            text.append(lines[0] + "\n", style=theme.INK)
            for line in lines[1:]:
                text.append(" " * hanging + line + "\n", style=theme.INK)
        for note in _HELP_NOTES:
            text.append("\n")
            for line in render.wrap(note, inner - 2):
                text.append("  " + line + "\n", style=theme.FAINT)
        # The path gets its own line rather than being appended to the sentence.
        # It is interpolated from `_clip_path()`, so its length is site controlled
        # -- 78 cells on the machine this was found on, and unbounded in general --
        # and a path has no spaces to wrap at, so leaving it inline broke the
        # sentence around it. On its own line the sentence always reads whole, and
        # the path is the same deliberate overrun `report.py` already accepts for
        # one: "a path you cannot copy whole is no use in a ticket."
        text.append("\n")
        path = _clip_path()
        for line in render.wrap(
            "y / Y also copy via OSC 52, and write the same text to:"
            if path
            else "y / Y copy via OSC 52. No cache directory could be created, so nothing "
            "is written to disk.",
            inner - 2,
        ):
            text.append("  " + line + "\n", style=theme.FAINT)
        if path:
            text.append("  " + path + "\n", style=theme.FAINT)
        self.help_text = text
        self.query_one("#help-body", Static).update(text)


# Both table specs live in render.py, because --plain draws these same two tables
# and a spec kept next to only one renderer drifted: the dashboard's overview had
# already lost its NEVER RAN column and its "(2 names)" suffix while --plain was
# still printing both.
_OVERVIEW_COLUMNS = render.OVERVIEW_COLUMNS


class OverviewScreen(ScreenChrome, CentredContent, Screen[Any]):
    """Workload groups, ranked. The landing screen."""

    BINDINGS: ClassVar = [
        *_SCREEN_BINDINGS,
        Binding("q", "app.quit", "Quit"),
        Binding("escape", "app.quit", "Quit", show=False),
        Binding("enter", "open", "Open"),
        Binding("right", "open", "Open", show=False),
        Binding("slash", "search", "Search"),
        Binding("f", "cycle_filter", "Filter"),
        Binding("s", "cycle_sort", "Sort"),
        Binding("n", "nodes", "Nodes"),
        Binding("p", "patterns", "Repeat failures"),
        # Off the footer, still bound and still under `?`. The overview groups by
        # workload because a flat list of 6,600 jobs is not an interface; the flat
        # list is the deliberate escape hatch from that, not a headline action --
        # asked directly, "why does all jobs deserve a button?". Its slot is what
        # let `w Time range` fall off the end at 100 columns.
        Binding("a", "all_jobs", "All jobs", show=False),
        Binding("r", "app.reload", "Reload"),
        *_digit_bindings("digit"),
    ]
    CSS = BASE_CSS

    # The search Input is first in the DOM, so Textual would auto-focus it and
    # swallow every letter key into an invisible text box. Focus the table.
    AUTO_FOCUS = "DataTable"

    filter_mode: reactive[str] = reactive("all")
    sort_mode: reactive[str] = reactive("cost")
    # NOT `query`: that name shadows Screen.query(), Textual's DOM lookup,
    # and breaks auto-focus on any screen declaring it.
    search_text: reactive[str] = reactive("")

    def __init__(self) -> None:
        super().__init__()
        self._jump = _RowJump()
        self._rows: list[GroupStats] = []
        self._layout: list[tuple[str, int]] = []
        # Retained so tests and callers read what was composed, never the widget.
        self.summary_text = Text()

    def compose(self) -> ComposeResult:
        yield _header()
        with Vertical(id="content"):
            yield Static(id="summary")
            with Horizontal(id="searchbar"):
                yield SearchBar(GROUP_SEARCH_FIELDS)
            yield FastDataTable(
                id="groups",
                cursor_type="row",
                zebra_stripes=False,
                cell_padding=1,
                # Without this the cursor's own foreground wins and every coloured
                # glyph in the highlighted row turns solid white.
                cursor_foreground_priority="renderable",
            )
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_rows()
        # The size this build used, so the `Resize` Textual sends right after a
        # screen is laid out does not rebuild it at the same size. See
        # `_resize_changed_anything`.
        self._sized_at = self.size
        self.query_one("#groups", DataTable).focus()

    def on_resize(self) -> None:
        """Columns are sized to the terminal, so a resize is a relayout.

        The row set is unchanged, so the selection is carried across it -- a
        relayout that silently returned you to row 1 would be its own annoyance.

        A resize that did not change the size is not a relayout; see
        :func:`_resize_changed_anything`.
        """
        if self.is_mounted and _resize_changed_anything(self):
            self.refresh_rows(keep_cursor=True)

    # -- data ------------------------------------------------------------

    def refresh_rows(self, keep_cursor: bool = False) -> None:
        history: History | None = self.sp.history
        table = self.query_one("#groups", DataTable)
        summary = self.query_one("#summary", Static)
        cursor = table.cursor_row if keep_cursor else 0
        # A CPU-only history should not carry a GPU half that is "-" on every row:
        # the paired cell collapses to a plain CPU-HOURS column instead.
        spec = _OVERVIEW_COLUMNS
        if history is not None and not any(g.gpu_hours for g in history.groups):
            spec = render.cpu_only_columns(spec)
        # The longest real name, so JOB NAME stops growing once it fits rather
        # than stretching to a cap over empty space.
        names = [g.label for g in history.groups] if history is not None else []
        layout = _sync_columns(
            table,
            spec,
            self._layout,
            content={"JOB NAME": max(map(len, names), default=0)},
            available=self.size.width,
        )
        self._layout = layout
        self.fit_content(layout)
        if history is None:
            summary.update(Text("loading…", style=theme.DIM))
            return

        groups = sort_groups(
            filter_groups(history.groups, self.filter_mode, self.search_text), self.sort_mode
        )
        self._rows = groups
        drawn = _rows_already_drawn(self, layout, tuple((g.label, g.partition) for g in groups))
        self.summary_text = self._summary(history, shown=len(groups))
        # An empty grid is not an answer. See render.nothing_matches, and the node
        # screen, which learned the same thing one round earlier: a column header
        # over blank space reads as a table that failed to load.
        if not groups:
            self.summary_text.append("\n")
            for line in render.wrap(_empty_reason(self, "workload"), _prose_width(self, 2)):
                self.summary_text.append("  %s\n" % line, style=theme.HEALTH_COLOR["ok"])
        table.display = bool(groups)
        summary.update(self.summary_text)
        if drawn:
            return
        table.clear()
        ascii_mode = self.sp.ascii_mode
        for index, group in enumerate(groups, start=1):
            # The dot rides in the row-number cell: as its own column it paid for
            # a width plus padding on both sides to show one glyph.
            marker = Text()
            marker.append("%-2d " % index, style=theme.FAINT)
            marker.append_text(render.health_dot(group.severity, ascii_mode))
            cells = {
                "#": marker,
                # Just the name. The count of distinct spellings folded into it was
                # here as a "NAMES" column and then as a "(2 names)" suffix, and
                # both read as clutter hanging off an identifier: the "#" already
                # says digits were folded, and the real names are one keypress away
                # in this workload's own NAME column. It stays in the JSON payload.
                "JOB NAME": Text(group.label, style=theme.INK),
                "PARTITION": Text(group.partition, style=theme.DIM),
                "RUNS": Text(str(group.total), style=theme.DIM),
                "COMPLETED": Text(
                    str(group.completed) if group.completed else "-",
                    style=theme.HEALTH_COLOR["ok"] if group.completed else theme.FAINT,
                ),
                # A count, not a rate: the rate's denominator excludes
                # cancellations while RUNS counts them, so "RUNS 20 / FAILED 20%"
                # invited the reader to compute 4 failures where there were 2.
                "FLAGGED": Text(
                    str(group.problems) if group.problems else "-",
                    style=theme.HEALTH_COLOR["crit"] if group.problems else theme.FAINT,
                ),
                render.HOURS_PAIR_LABEL: render.hours_pair(group),
                "CPU-HOURS": Text(
                    render.hours_text(group.core_hours),
                    style=theme.CPU_COLOR if group.core_hours else theme.FAINT,
                    justify="right",
                ),
                "LAST RUN": Text((group.last_seen or "")[:10], style=theme.FAINT),
            }
            table.add_row(*(cells[label] for label, _ in layout), key=str(index))
        if cursor and cursor < len(groups):
            table.move_cursor(row=cursor)
        # The WINDOW, and nothing that belongs next to a number. Counts live on
        # the summary line: "41 workloads" up here with "233 jobs" down there split
        # one fact across two rows, and the job list said "58 jobs" in both places.
        #
        # The filter and the sort are named only when they are actually doing
        # something. A bare "everything" is noise, and so is "by resource use" on
        # the default ordering -- it named the sort without saying what it meant,
        # and the reader has not chosen anything yet. Press `s` and it appears.
        parts = [self.sp.window]
        if self.filter_mode != "all":
            parts.append(dict(FILTERS).get(self.filter_mode, self.filter_mode))
        if self.sort_mode != SORTS[0][0]:
            parts.append("by %s" % sort_label(self.sort_mode))
        self.sub_title = "  ·  ".join(parts)

    def _summary(self, history: History, shown: int = 0) -> Text:
        """One line: how much work, how much of it worked, where the waste is.

        This was four lines. The GPU-hour total does not deserve a sentence of
        its own -- it earns its place only as the denominator that makes the idle
        figure legible ("17 of 778"), which is the number worth acting on. The
        completed-hours line was redundant with the completion rate, and the
        concurrency framing was explanation for a number that should not have
        needed explaining at a glance.

        ``shown`` is the row count after filtering, named only when it differs
        from the total -- the two counts belong together on one line, but the
        header count has to stay honest when a filter narrows the table.
        """
        stats = history.stats
        total_groups = len(history.groups)
        text = Text()
        # "233 jobs rolled up into 41 workloads" is one fact and was split between
        # the header bar and this line, so neither read as a whole thought.
        # The range leads, in the accent: after the toast fades the only other place
        # it appears is the title bar, which is exactly where a change goes unseen.
        text.append(self.sp.window, style="bold %s" % theme.ACCENT)
        text.append("  ·  ", style=theme.FAINT)
        # Pluralised, like the `workload%s` beside it: a one-job history read
        # "1 jobs in 1 workload" on the landing screen. See report.render_overview.
        text.append(
            "%d job%s" % (stats["jobs"], "" if stats["jobs"] == 1 else "s"),
            style="bold %s" % theme.INK,
        )
        text.append(
            " in %d workload%s" % (total_groups, "" if total_groups == 1 else "s"),
            style=theme.DIM,
        )
        text.append("  ·  ", style=theme.FAINT)
        text.append("%s completed" % format_percent(stats["completion_rate"]), style=theme.DIM)

        # The total appears ONLY as the denominator for the idle figure, and only
        # when that loss is material. On its own "783 GPU-hours" is a magnitude
        # with nothing to compare it against and nothing to do about it -- the
        # per-workload columns are where the resource numbers are comparable. So
        # there is no `elif` printing a bare total: no numerator, no line.
        #
        # Deliberately NOT here either: the excluded-record count and an
        # explanation of the "#" name folding. Both were true and both were
        # clutter -- three dense lines stacked under the header bar with no air
        # between them. The exclusion count is on the workload screen, which is
        # where "why is a run missing?" gets asked, and in --plain; the "#" is
        # explained under `?`.
        idle = history.idle_gpu_hours
        if idle is not None:
            text.append("  ·  ", style=theme.FAINT)
            # "total" and "of them" are both load-bearing: "783 GPU-hours" alone
            # was read as a per-job figure, and a bare "18 never computed" did not
            # say 18 of what.
            text.append(render.gpu_hours_total(idle[1]), style=theme.GPU_COLOR)
            text.append(
                render.idle_hours_note(idle[0], idle[1]),
                style=theme.HEALTH_COLOR["warn"],
            )

        # Which workload those idle hours are in. The clause above is the whole
        # Last: the facts about the history come first, then what the view is
        # currently doing to them.
        # `shown != total_groups`, not `shown and shown != total_groups`. Zero is
        # the count that most needs saying -- it is the one an empty table cannot
        # speak for -- and the truthiness guard suppressed exactly that one.
        if shown != total_groups:
            text.append("  ·  ", style=theme.FAINT)
            text.append("showing %d" % shown, style=theme.ACCENT)

        # Which workload those idle hours are in. The clause above is the whole
        # window; FLAGGED counts runs and cannot say what they cost, so the one
        # figure that answers "which one" is `GroupStats.wasted_gpu_hours` --
        # summed on every walk and, before this, read by nothing. `--plain` prints
        # the same sentence under the table, from `render`, so the two cannot word
        # it differently.
        #
        # Its own line rather than another `·` clause, and BELOW the clauses
        # above rather than among them: this row already carries four, the
        # sentence names a site-controlled workload label so its length is
        # unbounded, and inserting it mid-row pushed `showing %d` onto a second
        # line -- which `test_a_narrowed_table_still_reports_the_true_total` reads
        # off line one, and which contradicts the ordering rule stated directly
        # above (the facts, then what the view is doing to them).
        worst = history.idle_workload
        if worst is not None:
            text.append("\n")
            text.append(
                render.idle_workload_note(worst[0].label, worst[1], worst[0].gpu_hours),
                style=theme.HEALTH_COLOR["warn"],
            )

        if self.search_text:
            text.append("\nsearch: ", style=theme.FAINT)
            text.append(self.search_text, style=theme.ACCENT)
        return text

    # -- actions ---------------------------------------------------------

    def _selected(self) -> GroupStats | None:
        table = self.query_one("#groups", DataTable)
        if not self._rows or table.cursor_row < 0:
            return None
        if table.cursor_row >= len(self._rows):
            return None
        return self._rows[table.cursor_row]

    def clipboard_row(self) -> str:
        group = self._selected()
        if group is None:
            return ""
        return "\t".join(
            [
                # What the row said on screen, not the internal pattern.
                group.label,
                group.partition,
                str(group.total),
                "%d completed" % group.completed,
                # The breakdown too: a pasted row has no width limit and no
                # drill-down, so it carries what the table sends you elsewhere for.
                # Guarded, like every other count this codebase prints: a
                # single-run workload pasted "1 problems ... 1 GPU-hours".
                "%d %s" % (group.problems, plural(group.problems, "problem")),
                "%d failed" % group.failed,
                "%d never ran" % group.noop,
                # Units named here: a pasted row has no column header above it.
                "%s %s"
                % (render.hours_text(group.core_hours), plural(group.core_hours, "CPU-hour")),
                "%s %s" % (render.hours_text(group.gpu_hours), plural(group.gpu_hours, "GPU-hour")),
                group.last_seen or "",
            ]
        )

    def clipboard_view(self) -> str:
        history: History | None = self.sp.history
        if history is None:
            return ""
        from .report import Style, render_overview

        return render_overview(
            history, style=Style(enabled=False), limit=len(self._rows), sort=self.sort_mode
        )

    def action_open(self) -> None:
        group = self._selected()
        if group is not None:
            self.sp.push_screen(WorkloadScreen(group))

    def action_digit(self, digit: str) -> None:
        row = self._jump.push(digit, len(self._rows))
        if row is not None:
            self.query_one("#groups", DataTable).move_cursor(row=row - 1)

    def on_key(self, event: events.Key) -> None:
        self._jump.on_key_pressed(event.key)
        handled = (event.key == "escape" and _dismiss_search(self, "#groups")) or _steer_table(
            self, "#groups", event.key
        )
        if handled:
            event.stop()
            event.prevent_default()

    def action_cycle_filter(self) -> None:
        names = [name for name, _ in FILTERS]
        self.filter_mode = names[(names.index(self.filter_mode) + 1) % len(names)]

    def action_cycle_sort(self) -> None:
        self.sort_mode = next_sort(self.sort_mode)

    def action_search(self) -> None:
        bar = self.query_one("#searchbar")
        bar.add_class("visible")
        self.query_one("#search", Input).focus()

    def action_nodes(self) -> None:
        self.sp.push_screen(NodesScreen())

    def action_patterns(self) -> None:
        self.sp.push_screen(PatternsScreen())

    def action_all_jobs(self) -> None:
        history: History | None = self.sp.history
        if history is not None:
            self.sp.push_screen(JobListScreen(history.usable_jobs, "all jobs"))

    # Reactive watchers fire when the initial value is set, which happens before
    # on_mount has added the columns; refreshing then writes N values into a
    # zero-column table. Every watcher that touches the table needs this guard.
    def watch_filter_mode(self) -> None:
        if self.is_mounted:
            self.refresh_rows()

    def watch_sort_mode(self) -> None:
        if self.is_mounted:
            self.refresh_rows()

    def watch_search_text(self) -> None:
        if self.is_mounted:
            self.refresh_rows()

    def on_input_changed(self, event: Input.Changed) -> None:
        _debounce_search(self, event.value)

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        _cancel_search_debounce(self)
        self.search_text = self.query_one("#search", Input).value
        self.query_one("#searchbar").remove_class("visible")
        self.query_one("#groups", DataTable).focus()

    def on_data_table_row_selected(self, _event: DataTable.RowSelected) -> None:
        self.action_open()


_JOB_COLUMNS = render.JOB_COLUMNS

#: Rows :meth:`JobListScreen.refresh_rows` draws before it returns. Comfortably
#: more than any terminal shows, so what the reader is looking at is there
#: immediately; the rest follows from a timer. See `JobListScreen._draw_rows`.
_FIRST_ROWS = 200

#: A slice of the background fill is bounded by TIME, not by a row count: a row
#: costs ~120 us the first time it is drawn and ~60 us once its cells are cached,
#: so any fixed count is either a stall on the cold pass or a crawl on the warm
#: one. A first attempt used 2,500 rows and blocked the event loop for 519 ms.
#:
#: The budget and the interval together are a DUTY CYCLE, and that is the number
#: that decides how the app feels. 25 ms every 5 ms is four fifths of the idle
#: time, which fills 29,617 rows in about three seconds and -- measured in a real
#: pty -- made an arrow key during those three seconds take **110 ms, worst 350
#: ms**. 8 ms every 24 ms is a third of it: the fill takes longer and nothing else
#: waits on it, because everything that needs the whole table calls
#: `ensure_all_rows` instead of hoping.
_FILL_BUDGET = 0.008
_FILL_EVERY = 0.024
#: Rows between clock reads. Small enough that one granule cannot overrun the
#: budget, large enough that the clock is not the cost.
_FILL_STEP = 100

#: How long after a keypress the fill stays out of the way entirely. Typing and
#: holding an arrow key are exactly when the reader is watching the screen, and
#: exactly when rows arriving below the fold are worth nothing to them. The fill
#: is not cancelled, only deferred -- it resumes the moment the keyboard goes
#: quiet, which is when the rows are wanted and nobody is waiting.
_FILL_YIELD_AFTER_KEY = 0.15

# A copy is a paste-ready artefact, so it carries every column regardless of how
# narrow the terminal was when the rows were drawn, and uses the same labels.
_JOB_CLIPBOARD_HEADER = (
    "JOBID",
    "NAME",
    "STATE",
    "STARTED",
    "ENDED",
    "WALL TIME",
    "CPU TIME",
    "CPUS BUSY",
    "PEAK MEM",
    "MEM%",
    "GPU",
    "NODE",
)


def _noop(app, job) -> bool:
    """:func:`~slurmpast.diagnose.looks_like_noop`, remembered for this history.

    It walks the job's steps through `Job.total_cpu`, and the job list asks it
    about every matching job twice over -- once for the row's colour and once for
    the summary's count -- on every filter change, every search keystroke and
    every resize. The answer cannot change while a history is loaded.
    """
    cache = app.noop_jobs
    answer = cache.get(job.job_id)
    if answer is None:
        answer = cache[job.job_id] = looks_like_noop(job)
    return answer


def _job_cells(job, noop) -> dict[str, Text]:
    """One job's row, by column label, with the row number left out.

    Split out of ``JobListScreen.refresh_rows`` and cached by job id on the app
    (:attr:`SlurmpastApp.job_cells`) because that method runs again on every
    filter change, every search keystroke and every resize, over the SAME jobs.
    None of these values can change while a history is loaded -- a `Job` is a
    NamedTuple and the styles come from the theme -- so recomputing them was
    pure repetition, and not a cheap one: on a 29,617-job flat list the derived
    properties alone (`total_cpu` and `cpu_utilization`, both of which walk the
    job's steps, plus `gpu_count` and `looks_like_noop`) were 5.0 s of the
    12.3 s a profiled search keystroke took.

    The `#` column is deliberately absent: it numbers the ROW, so it changes
    when a filter changes even though the job did not. `refresh_rows` splices it
    in at whatever position the layout gives it.
    """
    grade = theme.STATE_HEALTH.get(job.base_state, "none")
    if noop:
        grade = "crit"
    util = job.cpu_utilization
    # MaxRSS above the ceiling is not a working set (it sums shared pages
    # across the process tree), so it is flagged rather than read as 103%.
    over_limit = bool(job.mem_limit_bytes and job.max_rss and job.max_rss > job.mem_limit_bytes)
    return {
        "JOBID": Text(job.job_id, style=theme.INK),
        "NAME": Text(job.name or "", style=theme.DIM),
        "STATE": Text(job.base_state, style=theme.HEALTH_COLOR.get(grade, theme.DIM)),
        "STARTED": Text(render.stamp_short(job.start) or "-", style=theme.ACCENT),
        "ENDED": Text(render.stamp_short(job.end) or "-", style=theme.FAINT),
        "WALL TIME": Text(format_duration(job.elapsed), style=theme.DIM),
        "CPU TIME": Text(format_duration(job.total_cpu), style=theme.CPU_COLOR),
        "CPUS BUSY": Text(
            render.cores_text(job),
            style=theme.HEALTH_COLOR["crit"]
            if (util is not None and util < 0.02)
            else theme.CPU_COLOR,
        ),
        "PEAK MEM": Text(format_bytes(job.max_rss), style=theme.MEM_COLOR),
        "MEM%": Text(
            format_percent(job.mem_utilization),
            style=theme.HEALTH_COLOR["crit"] if over_limit else theme.DIM,
        ),
        "GPU": Text(str(job.gpu_count or "-"), style=theme.GPU_COLOR),
        # `"-"`, matching `report.py`'s job table. This was the ONE cell
        # of the twelve where the two surfaces disagreed about how to say
        # "absent": the plain report writes `job.node_list or "-"` while
        # this wrote `or ""`. STARTED, ENDED and GPU all use `-` on both
        # sides, and NAME uses `""` on both, so the convention was settled
        # everywhere except here -- and `render.py` exists precisely so
        # "the dashboard and `--plain` cannot drift" (CLAUDE.md).
        #
        # An empty cell reads as a column that does not apply to this row;
        # `-` is this tool's marker for a value it does not have. A job
        # with no node list is a real state (pending, or cancelled before
        # it was ever allocated), so the reader is told that rather than
        # shown a blank.
        "NODE": Text(job.node_list or "-", style=theme.FAINT),
    }


def _job_clipboard_cells(job) -> list[str]:
    return [
        job.job_id,
        job.name or "",
        job.base_state,
        job.start or "",
        job.end or "",
        format_duration(job.elapsed),
        format_duration(job.total_cpu),
        render.cores_text(job),
        format_bytes(job.max_rss),
        format_percent(job.mem_utilization),
        str(job.gpu_count or 0),
        job.node_list or "",
    ]


class JobListScreen(ScreenChrome, CentredContent, Screen[Any]):
    """A list of jobs -- inside one workload, or flat across everything."""

    BINDINGS: ClassVar = [
        *_SCREEN_BINDINGS,
        Binding("q", "app.pop_screen", "Back"),
        Binding("escape", "app.pop_screen", "Back", show=False),
        Binding("left", "app.pop_screen", "Back", show=False),
        Binding("enter", "open", "Open"),
        Binding("right", "open", "Open", show=False),
        Binding("slash", "search", "Search"),
        Binding("f", "cycle_filter", "Filter"),
        *_digit_bindings("digit"),
    ]
    CSS = BASE_CSS
    # The search Input is first in the DOM, so Textual would auto-focus it and
    # swallow every letter key into an invisible text box. Focus the table.
    AUTO_FOCUS = "DataTable"

    filter_mode: reactive[str] = reactive("all")
    # NOT `query`: that name shadows Screen.query(), Textual's DOM lookup.
    search_text: reactive[str] = reactive("")

    def __init__(self, jobs, title: str, initial_filter: str = "all") -> None:
        super().__init__()
        self._all = list(jobs)
        self._rows: list = []
        self._layout: list[tuple[str, int]] = []
        # Rows of `_rows` already in the table, and the timer putting the rest
        # there. See `_draw_rows`.
        self._filled = 0
        self._fill_timer: Any = None
        self._fill_labels: list[str] = []
        self._fill_marker_at: int | None = None
        # When the reader last touched the keyboard; see `_FILL_YIELD_AFTER_KEY`.
        self._last_key = 0.0
        self._title = title
        self.summary_text = Text()
        self.filter_mode = initial_filter
        self._jump = _RowJump()

    def compose(self) -> ComposeResult:
        yield _header()
        with Vertical(id="content"):
            yield Static(id="summary")
            with Horizontal(id="searchbar"):
                yield SearchBar()
            yield FastDataTable(
                id="jobs",
                cursor_type="row",
                cell_padding=1,
                cursor_foreground_priority="renderable",
            )
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_rows()
        # The size this build used, so the `Resize` Textual sends right after a
        # screen is laid out does not rebuild it at the same size. See
        # `_resize_changed_anything`.
        self._sized_at = self.size
        self.query_one("#jobs", DataTable).focus()

    def on_resize(self) -> None:
        """Columns are sized to the terminal, so a resize is a relayout.

        The row set is unchanged, so the selection is carried across it -- a
        relayout that silently returned you to row 1 would be its own annoyance.

        A resize that did not change the size is not a relayout; see
        :func:`_resize_changed_anything`.
        """
        if self.is_mounted and _resize_changed_anything(self):
            self.refresh_rows(keep_cursor=True)

    def refresh_rows(self, keep_cursor: bool = False) -> None:
        table = self.query_one("#jobs", DataTable)
        cursor = table.cursor_row if keep_cursor else 0
        jobs = filter_jobs(self._all, self.filter_mode, self.search_text)
        layout = _sync_columns(
            table,
            _JOB_COLUMNS,
            self._layout,
            content={
                "NAME": max((len(j.name or "") for j in jobs), default=0),
                "NODE": max((len(j.node_list or "") for j in jobs), default=0),
            },
            available=self.size.width,
        )
        self._layout = layout
        self.fit_content(layout)
        # Newest first: after a failed run you look at the most recent attempt.
        jobs.sort(key=lambda j: (j.start or j.submit or "", j.job_id), reverse=True)
        self._rows = jobs
        # Only the row loop is skipped -- the summary below is rebuilt either way,
        # because it reports counts a caller may have just changed.
        drawn = _rows_already_drawn(self, layout, tuple(j.job_id for j in jobs))
        if not drawn:
            self._stop_filling()
            table.clear()
            labels = [label for label, _ in layout]
            # The row number is the one cell that depends on the row rather than
            # the job, so it is spliced in at whatever position the layout gives
            # it rather than assumed to lead. The placeholder keeps the per-row
            # lookup a flat list comprehension.
            marker_at = labels.index("#") if "#" in labels else None
            if marker_at is not None:
                labels[marker_at] = "JOBID"
            self._fill_labels = labels
            self._fill_marker_at = marker_at
            self._filled = 0
            # A screenful now, the rest between keystrokes. See `_draw_rows`.
            self._draw_rows(max(_FIRST_ROWS, cursor + 1))
            if self._filled < len(jobs):
                self._fill_timer = self.set_interval(_FILL_EVERY, self._fill_slice)
        if not drawn and cursor and cursor < len(jobs):
            table.move_cursor(row=cursor)

        table.display = bool(jobs)

        summary = Text()
        # Clipped, not wrapped: this is the head of a one-line summary that goes on
        # to carry the counts, so a title that wrapped would push them onto a line
        # of their own. A folded workload name can be one word -- the longest on a
        # real cluster is 123 characters with no space in it -- and `wrap` hands a
        # single word back whole, which is what put it past the edge. The plain
        # renderer's twin takes the same rule through `render.wrap_or_clip`.
        summary.append(render.clip(self._title, _prose_width(self, 2)), style="bold %s" % theme.INK)
        summary.append(
            "  ·  %d job%s" % (len(jobs), "" if len(jobs) == 1 else "s"), style=theme.DIM
        )

        # Each qualifier only when it is a material share of the runs, not merely
        # nonzero. "software · test · 132 jobs · 1 of them never computed · 1
        # cancelled · 1 unterminated, excluded" is three separate ones out of 132 --
        # 0.8% each -- taking three quarters of the line to report nothing anybody
        # would act on. The same restraint index.IDLE_SHARE_WORTH_NAMING applies to
        # the overview's idle figure, for the same reason: a headline that fires at
        # every magnitude is how a headline turns into noise.
        #
        # On the workload this was asked about -- 5 of 15 cancelled -- every one of
        # them clears the bar and the line says so, which is where they earn it.
        def qualifier(count, text, style):
            if count and count >= QUALIFIER_SHARE * len(jobs):
                summary.append("  ·  %s" % (text % count), style=style)

        # "of them" ties the count to the job count beside it. A bare "3 never
        # computed" next to a GPU-hours figure elsewhere read as hours.
        qualifier(
            sum(1 for j in jobs if _noop(self.sp, j)),
            "%d of them never computed",
            theme.HEALTH_COLOR["warn"],
        )
        # Cancellations close the arithmetic: the overview showed one workload as 15
        # runs / 10 completed / 2 flagged and was asked whether the math was wrong.
        # The missing 5 were cancelled, and a cancellation is deliberately neither a
        # success nor a problem, so it appears in no column. Dim: bookkeeping, not a
        # finding.
        qualifier(sum(1 for j in jobs if j.cancelled), "%d cancelled", theme.DIM)
        # Terse, and the overview reports the fleet-wide count anyway.
        qualifier(getattr(self, "_excluded", 0), "%d unterminated, excluded", theme.FAINT)
        if self.search_text:
            summary.append("  ·  search: ", style=theme.FAINT)
            summary.append(self.search_text, style=theme.ACCENT)
        if not jobs:
            # Same treatment as the overview and the node table: say why, and do
            # not leave a column header standing over nothing.
            summary.append("\n")
            for line in render.wrap(_empty_reason(self, "job"), _prose_width(self, 2)):
                summary.append("  %s\n" % line, style=theme.HEALTH_COLOR["ok"])
        extra = self.extra_summary()
        if extra is not None:
            summary.append("\n")
            summary.append_text(extra)
        # Retained deliberately: reading it back off the Static means depending on
        # widget internals, and `Static.renderable` exists in textual 0.89 but not
        # in 8.x -- which is exactly how CI caught this.
        self.summary_text = summary
        self.query_one("#summary", Static).update(summary)
        # No count here -- the summary line above already carries it, and printing
        # "58 jobs" in both places was the same duplication as the overview's split
        # workload/job counts.
        parts = [self.sp.window]
        if self.filter_mode != "all":
            parts.append(dict(FILTERS).get(self.filter_mode, self.filter_mode))
        self.sub_title = "  ·  ".join(parts)

    def _draw_rows(self, stop: int) -> None:
        """Draw rows up to ``stop`` into the table, continuing where it left off.

        The flat job list is 29,617 rows on a real seven-day history and the
        terminal shows about forty of them. Drawing all of them before handing
        the screen back cost 5.0 s for ``a`` and 1.7 s for every search
        keystroke -- a freeze, during which nothing on screen moves.

        So the first screenful is drawn here and the rest arrives in slices from
        :meth:`_fill_slice` between keystrokes. Nothing is dropped and nothing is
        paged: the table still ends up holding every row, so `end`, a digit jump
        and the scrollbar all mean what they meant. What changed is only when the
        rows land -- and anything that needs the whole table before then says so
        by calling :meth:`ensure_all_rows`.

        Cells come from `SlurmpastApp.job_cells`, so a filter keystroke over jobs
        already drawn once pays for the DataTable and nothing else.
        """
        jobs = self._rows
        stop = min(stop, len(jobs))
        start = self._filled
        if start >= stop:
            return
        table = self.query_one("#jobs", DataTable)
        cache = self.sp.job_cells
        add_row = table.add_row
        labels = self._fill_labels
        marker_at = self._fill_marker_at
        marker_style = theme.FAINT
        for index in range(start, stop):
            job = jobs[index]
            cells = cache.get(job.job_id)
            if cells is None:
                cells = cache[job.job_id] = _job_cells(job, _noop(self.sp, job))
            row = [cells[label] for label in labels]
            if marker_at is not None:
                row[marker_at] = Text("%-2d" % (index + 1), style=marker_style)
            add_row(*row, key=str(index + 1))
        self._filled = stop

    def _fill_slice(self) -> None:
        now = time.perf_counter()
        if now - self._last_key < _FILL_YIELD_AFTER_KEY:
            # Somebody is navigating. See `_FILL_YIELD_AFTER_KEY`.
            return
        deadline = now + _FILL_BUDGET
        total = len(self._rows)
        while self._filled < total:
            self._draw_rows(self._filled + _FILL_STEP)
            if time.perf_counter() >= deadline:
                break
        if self._filled >= total:
            self._stop_filling()

    def _stop_filling(self) -> None:
        if self._fill_timer is not None:
            self._fill_timer.stop()
            self._fill_timer = None

    def ensure_all_rows(self) -> None:
        """Finish the background fill now.

        For the two things that ask the TABLE rather than ``self._rows`` where
        the end is: `end`, and a digit jump past what has been drawn.
        """
        self._stop_filling()
        self._draw_rows(len(self._rows))

    def on_unmount(self) -> None:
        self._stop_filling()
        _cancel_search_debounce(self)

    def _selected(self):
        table = self.query_one("#jobs", DataTable)
        if not self._rows or not (0 <= table.cursor_row < len(self._rows)):
            return None
        return self._rows[table.cursor_row]

    def extra_summary(self) -> Text | None:
        """Extra summary content a subclass wants appended. None by default.

        A hook rather than a post-hoc patch: ``refresh_rows`` rewrites #summary on
        every filter and search keystroke, so anything written into that widget
        from ``on_mount`` was destroyed by the first ``f`` press.
        """
        return None

    def clipboard_row(self) -> str:
        job = self._selected()
        if job is None:
            return ""
        return "\t".join(_job_clipboard_cells(job))

    def clipboard_view(self) -> str:
        header = "\t".join(_JOB_CLIPBOARD_HEADER)
        return "\n".join([header] + ["\t".join(_job_clipboard_cells(j)) for j in self._rows])

    def action_open(self) -> None:
        job = self._selected()
        if job is not None:
            self.sp.push_screen(JobScreen(job))

    def action_digit(self, digit: str) -> None:
        row = self._jump.push(digit, len(self._rows))
        if row is not None:
            # The target may be past what the background fill has reached; the
            # jump is bounded by `len(self._rows)`, so draw up to it first.
            self._draw_rows(row)
            self.query_one("#jobs", DataTable).move_cursor(row=row - 1)

    def on_key(self, event: events.Key) -> None:
        # Stamped before anything else, so a slice already queued behind this key
        # sees it. Screen-level, so it catches the arrows the DataTable acts on as
        # well as the keys handled here.
        self._last_key = time.perf_counter()
        self._jump.on_key_pressed(event.key)
        handled = (event.key == "escape" and _dismiss_search(self, "#jobs")) or _steer_table(
            self, "#jobs", event.key
        )
        if handled:
            event.stop()
            event.prevent_default()

    def action_cycle_filter(self) -> None:
        names = [name for name, _ in FILTERS]
        self.filter_mode = names[(names.index(self.filter_mode) + 1) % len(names)]

    def action_search(self) -> None:
        self.query_one("#searchbar").add_class("visible")
        self.query_one("#search", Input).focus()

    def watch_filter_mode(self) -> None:
        if self.is_mounted:
            self.refresh_rows()

    def watch_search_text(self) -> None:
        if self.is_mounted:
            self.refresh_rows()

    def on_input_changed(self, event: Input.Changed) -> None:
        _debounce_search(self, event.value)

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        _cancel_search_debounce(self)
        self.search_text = self.query_one("#search", Input).value
        self.query_one("#searchbar").remove_class("visible")
        self.query_one("#jobs", DataTable).focus()

    def on_data_table_row_selected(self, _event: DataTable.RowSelected) -> None:
        self.action_open()


class WorkloadScreen(JobListScreen):
    """One workload: its jobs, plus the patterns only visible across them."""

    BINDINGS: ClassVar = [
        *JobListScreen.BINDINGS,
        Binding("p", "patterns", "Repeat failures"),
    ]

    def __init__(self, group: GroupStats) -> None:
        super().__init__(group.jobs, "%s · %s" % (group.label, group.partition))
        self._group = group
        self._excluded = group.excluded

    def extra_summary(self) -> Text | None:
        """Surface the single worst cross-run pattern for this workload.

        The point of the workload screen is that these findings are invisible
        per-job; `p` shows them all.
        """
        history: History | None = self.sp.history
        if history is None:
            return None
        findings = history.group_patterns(self._group)
        worst = render.sort_findings(findings)[0] if findings else None
        banner = Text()
        if worst is not None:
            banner.append_text(render.severity_chip(worst.severity))
            banner.append("  ")
            banner.append(worst.title, style="bold %s" % theme.INK)
            # One append per wrapped line, so every line gets the two-space indent.
            # This was `" ".join(render.wrap(evidence, 100))`, which puts the wrapped
            # lines straight back together -- the width argument did nothing at all,
            # the evidence went out as one 138-cell line at every terminal size, and
            # only the first of Textual's soft-wrapped lines kept the indent. The
            # advice block directly below has wrapped to the real width since round
            # two; this half was missed.
            for line in render.wrap(worst.evidence, _prose_width(self, 4)):
                banner.append("\n  " + line, style=theme.DIM)

        # The point of reading finished jobs: what the next one should ask for.
        from .sizing import recommend

        # Each directive with the evidence behind it, on screen. It used to assert
        # "--time=09:45:00  --mem=72G" and point at `slurmpast --sizing for why` --
        # a bare number with no basis, and for the reason a different command in a
        # different program. The reason belongs where the number is.
        # `capped` as well as actionable. `Advice.actionable` is
        # `verdict in ("raise", "lower")`, so a saturated workload -- one whose
        # target exceeds what a node in this partition HAS, and which is already
        # asking for all of it -- was filtered out here and appeared on no screen
        # at all, while `--sizing` gave it a flag line, its basis and the caution
        # that names the way out ("a larger request here cannot be scheduled --
        # this workload needs a bigger partition"). `sizing` gives `capped` its own
        # verdict precisely because it is "Not 'already about right': the workload
        # wants more and cannot have it here", and the dashboard was the surface
        # that said nothing. Measured with the demo history against a pinned
        # 2-core ceiling: three workloads capped, `--sizing` naming all three and
        # this banner none.
        advice = [a for a in recommend(self._group.jobs) if a.actionable or a.verdict == "capped"]
        # 10 cells of "next run  " plus the 22-cell flag column: what the basis has
        # to start after when it shares the line.
        basis_column = 32
        # Below this the basis is a column of three-word lines, and putting it
        # under the flag instead buys 22 cells back.
        room = self.size.width - basis_column - 2
        for index, item in enumerate(advice):
            banner.append("\n" if banner.plain else "")
            banner.append("next run  " if index == 0 else "          ", style=theme.FAINT)
            # A capped item has a `suggestion` (the clamped ceiling) and must NOT
            # print it as `--cpus-per-task=2`: that reads as advice to lower the
            # request, which is the "different wrong answer" the verdict exists to
            # avoid. The label comes from `render` so this and `--sizing` cannot
            # word it differently.
            if item.verdict == "capped":
                banner.append("%-22s" % item.flag, style=theme.ACCENT)
                banner.append(render.capped_label() + "  ", style=theme.HEALTH_COLOR["warn"])
            else:
                banner.append(
                    "%-22s" % ("%s=%s" % (item.flag, item.suggestion)), style=theme.ACCENT
                )
            # Every line of it, not just the first. `[:1]` silently cut the basis
            # mid-sentence -- "the rest is room to" -- which reads as the app having
            # broken rather than as a sentence that did not fit. Wrapped to the
            # width there is, and continuation lines indent under the text rather
            # than under the flag.
            #
            # `max(40, width - 34)` was the wrong floor: it guaranteed 40 cells of
            # basis whatever the terminal, so below 74 columns the line ran past
            # the edge -- 72 cells on a 70-cell screen -- which is the soft-wrap to
            # column 0 this whole block was rewritten to stop. Where 40 will not
            # fit beside the flag, the basis drops to the next line and indents
            # under it.
            if room >= 40:
                lines = render.wrap(item.basis, room)
                banner.append(lines[0], style=theme.DIM)
                rest, indent = lines[1:], basis_column
            else:
                lines = render.wrap(item.basis, _prose_width(self, 12))
                rest, indent = lines, 12
            for extra in rest:
                banner.append("\n" + " " * indent + extra, style=theme.DIM)
            # `Advice.caution` -- "what would make this advice wrong" -- which this
            # screen did not read at all. `--sizing` has printed it since it was
            # added and `--sizing --json` carries it, so the dashboard was the one
            # surface of three handing over a directive with the caveat removed:
            # six of the demo's ten actionable lines have one, including both
            # "cut --cpus-per-task on a GPU workload" recommendations, whose caveat
            # is that doing so can starve the card. Under the basis, in the warning
            # hue, because the reason belongs where the number is -- the same call
            # this block already made about the basis itself.
            if item.caution:
                mark = render.CAUTION_MARK
                for offset, line in enumerate(
                    render.wrap(item.caution, max(20, indent_room(self, indent) - len(mark)))
                ):
                    banner.append(
                        "\n" + " " * indent + (mark if offset == 0 else render.CAUTION_HANG) + line,
                        style=theme.HEALTH_COLOR["warn"],
                    )
        return banner if banner.plain else None

    def action_patterns(self) -> None:
        self.sp.push_screen(PatternsScreen(self._group))


class JobScreen(ScreenChrome, Screen[Any]):
    """The post-mortem for one job."""

    BINDINGS: ClassVar = [
        *_SCREEN_BINDINGS,
        Binding("q", "app.pop_screen", "Back"),
        Binding("escape", "app.pop_screen", "Back", show=False),
        Binding("left", "app.pop_screen", "Back", show=False),
        Binding("p", "toggle_paths", "Full path", show=False),
    ]
    CSS = BASE_CSS

    def __init__(self, job) -> None:
        super().__init__()
        self._job = job
        self._show_paths = False
        self._log_path = None
        self._log_text = None

    def compose(self) -> ComposeResult:
        yield _header()
        with VerticalScroll(id="detail"):
            yield Static(id="body")
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = "job %s" % self._job.job_id
        self.render_body()
        # Again once there has been a layout pass. `#body` has *no size at all*
        # during on_mount -- "size is zero until the first layout pass", as
        # `_sync_columns` puts it -- so the first render can only guess the chrome
        # from the screen width, guessed it two cells too wide, and Textual
        # soft-wrapped the overflow to column 0: `... against 25.0%` / `on` /
        # `every other node for cot-exp.` This is what makes `_prose_width`'s
        # measurement actually reach the screen. The table screens have always got
        # this for free from their own on_resize.
        self.call_after_refresh(self.render_body)

    def on_resize(self) -> None:
        """Re-wrap for the width there now is.

        Without this, resizing the terminal left the prose wrapped to the width it
        had when the screen was opened -- the same staleness every table screen
        here avoids with its own ``on_resize``.

        A resize that did not change the size re-wraps to the width it already
        had; see :func:`_resize_changed_anything`.
        """
        if _resize_changed_anything(self):
            self.render_body()

    def clipboard_row(self) -> str:
        """The whole post-mortem, rendered plain -- the paste-ready artefact."""
        from .report import Style, render_job

        text, _ = render_job(
            self._job,
            log_path=self._log_path,
            log_text=self._log_text,
            style=Style(enabled=False),
            show_steps=True,
        )
        return text

    clipboard_view = clipboard_row

    def action_toggle_paths(self) -> None:
        self._show_paths = not self._show_paths
        self.render_body()

    def _path_budget(self, prefix: int) -> int:
        """Cells a path may fill on a full-width line before it has to be elided.

        Fixed budgets were the defect. The log line called :func:`_elide` with its
        default 46 while the workdir two rows above used 62, so the one path a
        reader actually wants to copy was cut sixteen cells shorter than the one
        above it -- and a 47-character path came out as ``/home/…/145-train.err``
        on a 150-column terminal with a hundred cells to spare, throwing away the
        two directories that were the only reason to print a path at all.

        Eliding exists to stop a path wrapping to column 0, and whether it wraps is
        a function of the width there is. So that is what it is measured against --
        through `_text_width`, which measures the widget rather than the screen.
        Subtracting a guessed two cells of chrome from the screen was two too few,
        and left `utilization  not gathered by this cluster (needs AutoDetect=nvml
        in gres.conf)` clipped to exactly two cells past the edge, so `g…` wrapped
        to a line of its own.
        """
        return max(_MIN_PATH_WIDTH, _text_width(self) - prefix)

    def render_body(self) -> None:
        job = self._job
        ascii_mode = self.sp.ascii_mode
        # Logs are read here and only here -- eagerly scanning logs for 6,574
        # jobs at load time would dominate startup for data most of them never
        # need.
        log_path, log_text, inferred = self.sp.log_for(job)
        self._log_path, self._log_text = log_path, log_text

        history: History | None = self.sp.history
        note = ""
        if history is not None:
            from .nodes import Workload, note_for_allocation

            # The whole allocation, not just its first node -- a multi-node job's
            # bad node is rarely the one Slurm happened to list first.
            # The job's own workload, user included -- see nodes.Workload.
            # No `len(history) > 20` here any more: this screen and `cli._node_note`
            # each held their own copy of that floor, which is how the two surfaces
            # came to disagree about whether the note exists at all. It is
            # `nodes.MIN_HISTORY`, applied inside `note_for_allocation`, so there is
            # one place to read it from and one place to change it.
            note = note_for_allocation(
                history.usable_jobs, job.node_list, workload=Workload(job.name, job.user)
            )

        verdict = diagnose(job, log_text=log_text, node_note=note)

        body = Text()
        body.append("%s  " % job.job_id, style="bold %s" % theme.INK)
        body.append_text(render.state_text(job.base_state, ascii_mode))
        # No identity lines here: the "job" section below carries them, and
        # printing both put the name, account and node on screen twice.
        body.append("\n\n")

        # Lead with slurmwatch's row idiom, so a job you watched running looks
        # like the same object afterwards. Bounded by the terminal for the same
        # reason the plain renderer is: the MEM row runs to 86 cells with its
        # detail inline, and Textual soft-wrapping it puts the tail at column 0,
        # where it no longer reads as part of the block.
        for line in render.resource_rows(
            job, ascii_mode=ascii_mode, max_width=_prose_width(self, 0)
        ):
            body.append_text(line)
            body.append("\n")
        body.append("\n")

        # Then the full detail. One shared section model with report.py, so the
        # dashboard and the plain output can never disagree about what a job did.
        section_color = {
            "job": theme.INK,
            "timing": theme.ACCENT,
            "cpu": theme.CPU_COLOR,
            "memory": theme.MEM_COLOR,
            "filesystem": theme.DISK_COLOR,
            "gpu": theme.GPU_COLOR,
            "outcome": theme.INK,
        }
        # summarized: the gauge block above already carries walltime, CPU, kernel
        # share, memory, GPU and disk. Printing both put every headline number on
        # screen twice, each with its own differently-sized bar.
        for title, rows in render.job_sections(job, summarized=True):
            colour = section_color.get(title, theme.INK)
            body.append("  %s\n" % title, style="bold %s" % colour)

            def cell(label, value, gauge, pad, colour=colour):
                """One label/value pair. ``pad`` right-fills for a paired line."""
                # The gauge counts against the value's room. It did not, and that
                # is the whole of the `slowest task` bug: the budget was
                # `4 + PAIR_LABEL_WIDTH + 1`, the row then drew a 14-cell bar and a
                # 2-cell gap in front of the value, and 16 cells the arithmetic
                # never saw put the row past the edge -- at 80 columns, not merely
                # a narrow one. `render.pair_value_budget` is the same sum the
                # plain renderer does, which had counted the bar all along.
                bar_cells = 0 if gauge is None else render.DETAIL_BAR_WIDTH + render.DETAIL_BAR_GAP
                budget = pad or render.pair_value_budget(_text_width(self), bar_cells)
                lines = [value]
                if label in render.PATH_ROWS:
                    # A 118-character workdir wrapped to column 0, leaving the label
                    # looking empty with an orphaned line of path beneath it.
                    # Shortened middle-out rather than wrapped -- `p` shows it in
                    # full and --plain always does, because a path you cannot copy
                    # whole is no use in a ticket. Only the rows render.py declares
                    # to *be* paths: the old test was `"/" in value`, which is also
                    # true of `submitted as` -- a command line, not a path.
                    if not self._show_paths and len(value) > budget:
                        lines = [_elide(value, keep=budget)]
                elif pad:
                    # A paired cell is cut, not wrapped: the pair beside it owns the
                    # rest of the line, and a wrap would take the row it sits on.
                    if len(value) > budget:
                        lines = [_clip(value, budget)]
                else:
                    # Wrapped, exactly as `--plain` wraps the same row. This surface
                    # clipped instead, so `utilization  not gathered by this cluster
                    # (needs AutoDetect=nvml in g…` threw away the half of the
                    # sentence naming what to do about it, while a paste of the same
                    # job kept it.
                    lines = render.pair_value_lines(label, value, budget)
                body.append("    %-*s " % (render.PAIR_LABEL_WIDTH, label), style=theme.FAINT)
                if gauge is not None:
                    body.append_text(
                        render.bar(
                            gauge,
                            colour,
                            width=render.DETAIL_BAR_WIDTH,
                            ascii_mode=ascii_mode,
                        )
                    )
                    body.append(" " * render.DETAIL_BAR_GAP)
                # Values carry their section's hue. The palette already spreads
                # these across the wheel so no two read alike even under
                # red-green colour blindness; printing every value in one ink
                # threw that away and left the eye nothing to group by.
                style = colour
                if render.OVER_LIMIT_MARK in value:
                    style = theme.HEALTH_COLOR["crit"]
                elif "not recorded" in value:
                    style = theme.FAINT
                body.append("%-*s" % (pad, lines[0]) if pad else lines[0], style=style)
                # Continuations hang past the label AND the bar, so the sentence
                # stays under itself instead of restarting beneath the gauge.
                hang = " " * (4 + render.PAIR_LABEL_WIDTH + 1 + bar_cells)
                for extra in lines[1:]:
                    body.append("\n%s%s" % (hang, extra), style=style)

            # Two pairs per line where both values are short: one row per line
            # used about 40 of 120 columns and ran the screen off the bottom. One
            # per line once the terminal cannot hold two, which is the threshold
            # `report` has always applied and this screen never did -- below it a
            # paired row soft-wraps and loses the label/value alignment that made
            # pairing worth doing.
            paired = (
                render.PAIR_VALUE_WIDTH
                if (self.size.width or _DEFAULT_TABLE_WIDTH) >= render.PAIRED_LINE_WIDTH
                else 0
            )
            for group in render.pair_rows(rows, max_value=paired):
                first = group[0]
                if len(group) == 2:
                    second = group[1]
                    cell(first[0], first[1], first[2], render.PAIR_VALUE_WIDTH)
                    body.append("  ")
                    cell(second[0], second[1], second[2], 0)
                else:
                    cell(first[0], first[1], first[2], 0)
                body.append("\n")
            body.append("\n")

        body.append("\n")
        if log_path:
            shown = (
                log_path
                if self._show_paths
                else _elide(log_path, keep=self._path_budget(len("  log  ")))
            )
            body.append("  log  %s\n" % shown, style=theme.FAINT)
            if inferred:
                # Matched by when it was written, not by its name. Say so: a wrong
                # log invents a cause, which is worse than no log at all.
                #
                # From `render`, like the miss line in the `elif` below: this branch
                # kept a copy of the sentence and `report.render_job` kept another,
                # so one piece of prose was maintained in two files while the branch
                # beside it was single-sourced.
                body.append(
                    "       %s\n" % render.log_inferred_note(),
                    style=theme.HEALTH_COLOR["warn"],
                )
        elif not self.sp.no_logs:
            # One line, and the same one `--plain` prints -- `render.log_miss_detail`
            # holds the rule for both. This screen used to hardcode "none found" on
            # the grounds that "the path is unknowable", which stopped being true
            # when Slurm 24.05 began recording StdOut: on a 24.11 cluster the plain
            # renderer named the path and said whether it was absent, unreadable or
            # deliberately discarded, while this one said nothing was found at all.
            #
            # Guarded on `no_logs` for the reason `report` guards it: every spelling
            # is a claim about the filesystem, and under `--no-logs` nothing was
            # stat'd. `--demo` forces that flag, so the synthetic post-mortem still
            # shows no line here.
            body.append("  log  %s\n" % render.log_miss_detail(job), style=theme.FAINT)

        body.append("\n")
        findings = render.sort_findings(verdict.findings)
        if not findings:
            body.append("  %s\n" % render.NOTHING_TO_FLAG, style=theme.HEALTH_COLOR["ok"])
        for finding in findings:
            _finding_lines(self, body, finding)

        self.query_one("#body", Static).update(body)


class PatternsScreen(ScreenChrome, Screen[Any]):
    """Cross-run findings: the things no single job can show."""

    BINDINGS: ClassVar = [
        Binding("q", "app.pop_screen", "Back"),
        Binding("escape", "app.pop_screen", "Back", show=False),
        Binding("left", "app.pop_screen", "Back", show=False),
        *_SCREEN_BINDINGS,
    ]
    CSS = BASE_CSS

    def __init__(self, group: GroupStats | None = None) -> None:
        super().__init__()
        self._group = group

    def clipboard_row(self) -> str:
        history: History | None = self.sp.history
        if history is None:
            return ""
        from .report import Style, render_patterns

        return render_patterns(history, style=Style(enabled=False))

    clipboard_view = clipboard_row

    def compose(self) -> ComposeResult:
        yield _header()
        with VerticalScroll(id="detail"):
            yield Static(id="body")
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = "patterns" + (" · %s" % self._group.label if self._group else "")
        self.render_body()
        self.call_after_refresh(self.render_body)  # see JobScreen.on_mount

    def on_resize(self) -> None:
        """Re-wrap for the width there now is. See JobScreen.on_resize."""
        if _resize_changed_anything(self):
            self.render_body()

    def render_body(self) -> None:
        history: History | None = self.sp.history
        body = Text()
        if history is None:
            body.append("loading…", style=theme.DIM)
            self.query_one("#body", Static).update(body)
            return

        findings = (
            history.group_patterns(self._group) if self._group is not None else history.patterns
        )
        if not findings:
            body.append(
                "  %s\n" % render.patterns_empty(),
                style=theme.HEALTH_COLOR["ok"],
            )
            body.append(
                "\n  That is a real answer, not an empty screen: these detectors\n"
                "  stay silent rather than manufacture a finding.\n",
                style=theme.FAINT,
            )
        for finding in render.sort_findings(findings):
            _finding_lines(self, body, finding)
        self.query_one("#body", Static).update(body)


class NodesScreen(ScreenChrome, CentredContent, Screen[Any]):
    """Per-node reliability, workload-controlled."""

    BINDINGS: ClassVar = [
        Binding("q", "app.pop_screen", "Back"),
        Binding("escape", "app.pop_screen", "Back", show=False),
        Binding("left", "app.pop_screen", "Back", show=False),
        *_SCREEN_BINDINGS,
        Binding("m", "cycle_metric", "Metric"),
        Binding("c", "toggle_control", "Control"),
    ]
    CSS = BASE_CSS

    metric: reactive[str] = reactive("hang")
    controlled: reactive[bool] = reactive(True)

    def __init__(self) -> None:
        super().__init__()
        self._layout: list[tuple[str, int]] = []
        # Retained so tests and callers read what was composed, never the widget.
        # `Static.renderable` exists in textual 0.89 and not in 8.x, and both are
        # supported here -- so anything that has to read a screen's text reads it
        # from the screen, as OverviewScreen and JobListScreen already do.
        self.summary_text = Text()
        self.exclude_text = Text()

    def compose(self) -> ComposeResult:
        yield _header()
        with Vertical(id="content"):
            yield Static(id="summary")
            yield FastDataTable(id="nodes", cursor_type="row")
            yield Static(id="exclude")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_rows()
        # The size this build used, so the `Resize` Textual sends right after a
        # screen is laid out does not rebuild it at the same size. See
        # `_resize_changed_anything`.
        self._sized_at = self.size
        self.query_one("#nodes", DataTable).focus()

    def on_resize(self) -> None:
        if self.is_mounted and _resize_changed_anything(self):
            self.refresh_rows()

    def refresh_rows(self) -> None:
        history: History | None = self.sp.history
        table = self.query_one("#nodes", DataTable)
        self._layout = _sync_columns(
            table, render.NODE_COLUMNS, self._layout, available=self.size.width
        )
        self.fit_content(self._layout)
        if history is None:
            return
        from .nodes import dominant_workload

        workload = (
            dominant_workload(history.usable_jobs, metric=self.metric) if self.controlled else None
        )
        table_data = node_table(history.usable_jobs, workload=workload, metric=self.metric)

        summary = Text()
        summary.append("%s\n" % render.nodes_title(self.metric), style="bold %s" % theme.INK)
        # Wrapped from the terminal, like the findings on the job and patterns
        # screens. A folded workload name (`nemotron-batch-h#-tokenize-shards-
        # stage#-retry-#`) took this past 110 cells; Textual soft-wrapped it, so
        # the orphan landed at column 0 and lost the indent that marks it as a
        # note under the heading. `report.render_nodes` draws the same line and is
        # wrapped the same way.
        if workload:
            aside = render.WORKLOAD_CONTROL_ASIDE
            sentence = render.nodes_workload_control(workload)
            for line in render.wrap(sentence, _prose_width(self, 2)):
                head, marker, tail = line.partition(aside)
                summary.append("  " + head, style=theme.DIM)
                if marker:
                    summary.append(marker, style=theme.FAINT)
                summary.append(tail + "\n", style=theme.DIM)
        else:
            for line in render.wrap(
                "UNCONTROLLED — mixes workloads, so a node that hosted one bad "
                "campaign looks cursed",
                _prose_width(self, 2),
            ):
                summary.append("  " + line + "\n", style=theme.HEALTH_COLOR["warn"])
        # From `render`, wrapped to this screen, like every other sentence here.
        # Spelled out locally it said "below sample threshold" where the plain
        # report said "below threshold", and it went unwrapped in both -- the
        # drift `render` exists to make impossible.
        for line in render.wrap(render.nodes_baseline(table_data), _prose_width(self, 2)):
            summary.append("  %s\n" % line, style=theme.FAINT)
        self.summary_text = summary
        self.query_one("#summary", Static).update(summary)

        table = self.query_one("#nodes", DataTable)
        table.clear()
        # Two ways this table has nothing to say, and an empty grid says neither.
        rows = table_data["rows"]
        # Both sentences come from `render` and are wrapped to the width there is.
        # They were two hardcoded line breaks, which is a wrap guess rather than a
        # measurement: the first interpolates a folded workload name, so on a real
        # cluster its first "line" ran well past any terminal and Textual folded
        # the remainder to column 0 -- the sentence that exists to rescue an empty
        # screen, breaking it.
        # `w` here, `--since` in the plain report: the wording is shared, the
        # keystroke is not, because it is the one part of the sentence that
        # legitimately differs between the two surfaces -- and the only part the
        # reader can act on.
        empty_reason = render.nodes_empty_reason(table_data, self.metric, workload, widen="w")
        # And the grid itself goes with them. Setting `rows = []` left the DataTable
        # mounted, so the sentence was followed by a bare header --
        # `NODE  N  RATE  95% CI  VERDICT` over nothing -- which is precisely the
        # "empty grid" the comment above says says neither thing, and reads as a
        # table that failed to load rather than as a table with nothing in it.
        # `report.render_nodes` returns before drawing anything on this branch;
        # this is that early return, in the shape a mounted widget takes.
        table.display = not empty_reason
        if empty_reason:
            rows = []
            summary.append("\n")
            for line in render.wrap(empty_reason, _prose_width(self, 2)):
                summary.append("  %s\n" % line, style=theme.HEALTH_COLOR["ok"])
            self.query_one("#summary", Static).update(summary)
        for row in rows:
            grade = {"worse": "crit", "better": "ok"}.get(row["verdict"], "none")
            # Keyed by label and emitted in layout order, like the other two
            # tables: a narrow terminal drops a column, and a fixed tuple of five
            # cells then raises rather than rendering.
            cells = {
                "NODE": Text(row["node"], style=theme.INK),
                "N": Text("%d/%d" % (row["bad"], row["trials"]), style=theme.DIM),
                "RATE": Text(
                    "%.1f%%" % (100 * row["rate"]), style=theme.HEALTH_COLOR.get(grade, theme.DIM)
                ),
                render.CI_COLUMN: Text(
                    render.ci_range(row["ci_low"], row["ci_high"]), style=theme.FAINT
                ),
                "VERDICT": Text(row["verdict"], style=theme.HEALTH_COLOR.get(grade, theme.FAINT)),
            }
            table.add_row(*(cells[label] for label, _ in self._layout))

        excl = compress_nodelist(suggest_exclude(table_data))
        tested = table_data["tested_nodes"]
        note = Text()
        if empty_reason:
            # Nothing further to say. The `else` below would add "no node is worse
            # than the rest; nothing to exclude" underneath a sentence that has
            # just explained there is nothing to compare -- two lines saying no,
            # the second answering a question the first said could not be asked.
            # The plain report reaches neither.
            note = Text()
        elif excl:
            # Wrapped, like the tail note below it and like the plain report's twin.
            # These two were bare strings inside a block that only renders when a
            # node is genuinely worse than the rest -- which the demo did not
            # produce until round five, so nothing ever looked at them. The second
            # is 96 cells and soft-wrapped its last word to column 0.
            note.append("\n")
            for line in render.wrap(
                render.nodes_correction_note(tested),
                _prose_width(self, 2),
            ):
                note.append("  %s\n" % line, style=theme.DIM)
            # Not wrapped, deliberately: one #SBATCH line to copy, and a paste
            # broken across two lines is not a paste.
            note.append("    #SBATCH --exclude=%s\n" % excl, style="bold %s" % theme.ACCENT)
            for line in render.wrap(
                render.nodes_exclude_disclaimer(),
                _prose_width(self, 4),
            ):
                note.append("    %s\n" % line, style=theme.FAINT)
            # Same disclosure as the plain report: the line is capped at 8, so when
            # more nodes scored worse it has to say so rather than read complete.
            left_out = excluded_tail(table_data)
            if left_out:
                for line in render.wrap(
                    render.nodes_excluded_tail_note(left_out),
                    _prose_width(self, 4),
                ):
                    note.append("    %s\n" % line, style=theme.FAINT)
        else:
            note.append(
                "\n  %s\n" % render.nodes_nothing_to_exclude(),
                style=theme.FAINT,
            )
        # Why the CI column can disagree with the verdict beside it. Same sentence as
        # the plain-text report, from render, so the two screens cannot drift.
        if table_data["held_back"] and not empty_reason:
            for line in render.wrap(
                render.held_back_note(table_data["held_back"], tested),
                _prose_width(self, 2),
            ):
                note.append("  %s\n" % line, style=theme.FAINT)
        self.exclude_text = note
        self.query_one("#exclude", Static).update(note)
        self.sub_title = "nodes · %s%s" % (
            self.metric,
            "" if self.controlled else " · uncontrolled",
        )

    def clipboard_row(self) -> str:
        history: History | None = self.sp.history
        if history is None:
            return ""
        from .report import Style, render_nodes

        return render_nodes(
            history, metric=self.metric, controlled=self.controlled, style=Style(enabled=False)
        )

    clipboard_view = clipboard_row

    def action_cycle_metric(self) -> None:
        self.metric = "failure" if self.metric == "hang" else "hang"

    def action_toggle_control(self) -> None:
        self.controlled = not self.controlled

    def watch_metric(self) -> None:
        if self.is_mounted:
            self.refresh_rows()

    def watch_controlled(self) -> None:
        if self.is_mounted:
            self.refresh_rows()


class SlurmpastApp(App[Any]):
    TITLE = "slurmpast"
    CSS = BASE_CSS

    BINDINGS: ClassVar = [
        Binding("ctrl+c", "quit", "Quit", show=False),
        # Mouse capture is OFF by default so the terminal keeps the mouse and
        # click-drag selection works like it does anywhere else. This toggles it
        # back on for in-app clicking and wheel scrolling.
        Binding("M", "toggle_mouse", "Mouse", show=False),
        # `w` rather than `r`, which is already Reload -- and the two are
        # different operations: reload re-runs the same window to pick up jobs
        # that have finished since, `w` changes which window that is.
        Binding("w", "cycle_window", "Time range"),
    ]

    def __init__(
        self,
        loader,
        window: str,
        ascii_mode=False,
        no_logs=False,
        log_dirs=(),
        mouse=False,
        since=None,
    ):
        super().__init__()
        self._loader = loader
        self.window = window
        self.history: History | None = None
        self.ascii_mode = ascii_mode
        self.no_logs = no_logs
        self.log_dirs = list(log_dirs)
        self.mouse_enabled = bool(mouse)
        self.load_error: str | None = None
        # {job_id: (path, inferred)} for the loaded history, resolved across all
        # jobs at once so no two of them are shown the same log. Filled by a
        # background worker; until it lands, log lookups fall back to the per-job
        # search. See :func:`slurmpast.logs.assign_logs`.
        self._log_map: dict | None = None
        # {job_id: {column label: Text}} for the loaded history. Filled on demand
        # by `_job_cells`, dropped whenever the history is replaced. Shared across
        # screens on purpose: the flat job list and every workload screen draw the
        # same jobs, so the second one to open pays nothing for the cells.
        self.job_cells: dict[str, dict[str, Text]] = {}
        # {job_id: bool} for `diagnose.looks_like_noop`, which the job list's
        # summary counts over every matching job on every filter change and every
        # search keystroke -- 110 ms of a profiled 478 ms keystroke on a
        # 29,617-job list, re-deriving an answer that cannot change while a
        # history is loaded. Dropped with `job_cells`, for the same reason.
        self.noop_jobs: dict[str, bool] = {}

        # The window was fixed at launch by -S, so answering "what about last
        # month?" meant quitting and re-running. `w` cycles it in place.
        self._since = since
        self._windows = list(WINDOWS)
        if since and since not in self._windows:
            # Whatever was asked for on the command line stays in the cycle, so
            # `w` comes back round to it instead of stranding it.
            self._windows.insert(0, since)
        self._window_at = self._windows.index(since) if since in self._windows else 0
        self._can_requery = bool(since) and _loader_accepts_since(loader)
        # Saved before a re-query so a window with no jobs can be backed out of
        # rather than emptying the screen or, worse, exiting the app.
        self._previous: tuple | None = None

    def on_mount(self) -> None:
        self.register_theme(theme.theme())  # type: ignore[arg-type]
        self.theme = "slurmpast"
        # Leave the terminal the way we found it, whichever way the run ends.
        #
        # Measured in a real pty: a `q` and a SIGINT both tore the screen down
        # cleanly, while **SIGTERM and SIGHUP killed the app mid-draw and left the
        # alternate screen open** -- the user's scrollback replaced by a dead
        # dashboard until they run `reset`. Both are ordinary: slurmstepd SIGTERMs
        # the step when a job running `srun --pty slurmpast` is cancelled, and a
        # tmux pane being killed or an IDE terminal closing SIGHUPs the foreground
        # group.
        #
        # SIGINT is handled too, for the EXIT CODE rather than the screen: it
        # already restored the terminal but exited 0, so `kill -INT` and a clean
        # `q` were indistinguishable to a supervisor or a `timeout --signal=INT`.
        # A ctrl-c TYPED into the dashboard is unaffected -- in raw mode that
        # arrives as the byte 0x03 and is handled as a key.
        #
        # 128+signum, so anything reading the status sees "signalled" rather than a
        # crash. The sibling package reached the same three handlers by the same
        # route (its SW-26), which is where the numbers come from.
        with contextlib.suppress(Exception):
            loop = asyncio.get_running_loop()
            loop.add_signal_handler(signal.SIGTERM, lambda: self.exit(return_code=143))
            loop.add_signal_handler(signal.SIGHUP, lambda: self.exit(return_code=129))
            loop.add_signal_handler(signal.SIGINT, lambda: self.exit(return_code=130))
        # The overview renders its own "loading…" state, so it can be pushed
        # immediately and filled in when the worker lands. An earlier version
        # pushed a separate LoadingScreen and then popped back to it, which
        # emptied the screen stack -- stack surgery for no benefit.
        self.push_screen(OverviewScreen())
        self.load_history()

    def load_history(self) -> None:
        """Query sacct off the UI thread.

        ~1.3 s for seven months. Small, but blocking the first paint on it reads
        as a hang, and the whole point of this tool is not confusing a hang with
        work.
        """
        self.run_worker(self._load, thread=True, exclusive=True, name="load")

    def _load(self) -> None:
        # Building the history is inside the guard, not after it. Textual's
        # `run_worker` defaults to `exit_on_error=True`, so anything escaping here
        # reaches `App._handle_exception`, which "always results in the app
        # exiting" -- the dashboard died with a raw traceback instead of taking
        # `_loaded`'s error path, and `load_error` was never even set. That is the
        # one promise the except clause below makes out loud.
        #
        # `exit_on_error=False` on the worker would be the wrong fix: it only
        # suppresses the crash, and since nothing else calls `_loaded` the UI would
        # sit on "loading…" for ever, which is worse than exiting.
        try:
            jobs = self._loader(self._since) if self._can_requery else self._loader()
            history = History(jobs, window=self.window)
        except Exception as exc:  # surfaced in the UI, never swallowed
            self.call_from_thread(self._loaded, None, str(exc))
            return
        self.call_from_thread(self._loaded, history, None)

    def _loaded(self, history: History | None, error: str | None) -> None:
        if error is not None or history is None:
            if self._previous is not None:
                # A window the user cycled into has no jobs, or sacct refused it.
                # Backing out beats exiting: they still have the data they had.
                self._restore(error)
                return
            self.load_error = error
            self.exit(message="slurmpast: %s" % (error or "no data"))
            return
        self._previous = None
        self.history = history
        self._log_map = None
        # A reload brings new Job objects, and a cell drawn from an old one would
        # report a state the job has since left.
        self.job_cells = {}
        self.noop_jobs = {}
        if not self.no_logs:
            # Off the UI thread: 1.7s over 6,600 jobs, which is invisible here and
            # a visible stall if it happens on the keypress that opens a job.
            self.run_worker(self._resolve_logs, thread=True, name="logs")
        # Same trade, one panel over. `History.patterns` is deliberately lazy --
        # "paying for it at load time would slow the first paint for a panel the
        # user may never open" -- and that reasoning holds for `--plain` and for
        # a library caller. Here the first paint has already happened, so the
        # cost lands on `p` instead: measured at 505 ms of frozen dashboard on a
        # 29,624-job history, on the keypress. Warmed in a worker after the
        # overview is up, it costs the reader nothing either way. The property
        # caches, so `p` finds it done.
        self.run_worker(self._warm_patterns, thread=True, name="patterns")
        screen = self.screen
        if isinstance(screen, OverviewScreen):
            screen.refresh_rows()

    def _warm_patterns(self) -> None:
        history = self.history
        if history is None:
            return
        try:
            history.patterns  # noqa: B018 -- the property caches; that is the point
        except Exception:
            # Same rule as the log worker below: a warm-up that fails must leave
            # the dashboard exactly as it would have been without one. `p` then
            # computes them itself, and reports its own failure if there is one.
            return

    def _resolve_logs(self) -> None:
        history = self.history
        if history is None:
            return
        try:
            resolved = assign_logs(history.usable_jobs, extra_dirs=self.log_dirs, pace=_breathe)
        except Exception:
            # `except OSError` did not deliver the guarantee this comment makes: any
            # other exception escaped the worker and, per `exit_on_error=True`, took
            # the whole dashboard down -- and a log search is the most speculative
            # thing this tool does, walking directories and expanding filename
            # patterns from user-supplied strings. Logs are an enhancement to a
            # screen that is already useful without them, so failing to find them
            # costs the reader nothing.
            return  # a log search must never take the dashboard down with it
        # Only if the history has not been replaced under us by a re-query.
        if self.history is history:
            self._log_map = resolved

    def log_for(self, job):
        """``(path, text, inferred)`` for one job, cross-checked against the rest.

        Prefers the whole-history assignment, so a file that belongs to another run
        is not offered here. Falls back to the single-job search while the worker is
        still running, or for a job that is not part of the loaded history.
        """
        if self.no_logs:
            return None, None, False
        if self._log_map is not None and job.job_id in self._log_map:
            path, inferred = self._log_map[job.job_id]
            return path, (read_tail(path) if path else None), inferred
        return load_for(job, extra_dirs=self.log_dirs)

    def _restore(self, error: str | None) -> None:
        """Undo a re-query that came back with nothing."""
        assert self._previous is not None
        moved = self._previous[0] != self._window_at
        self._window_at, self._since, self.window, self.history = self._previous
        self._previous = None
        # Two callers, two things to say. `w` moved the window and found nothing
        # there; `r` asked for the same window again and the query failed. "nothing
        # found there" is the wrong sentence for the second -- there is no "there".
        self.notify(
            (
                "nothing found there — staying on %s\n%s"
                if moved
                else "reload failed — keeping the %s data you had\n%s"
            )
            % (self.window, error or ""),
            severity="warning",
            timeout=6,
        )
        if isinstance(self.screen, OverviewScreen):
            self.screen.refresh_rows()

    def action_toggle_mouse(self) -> None:
        """Hand the mouse to the terminal, or take it back.

        With capture off, the terminal does its own click-drag selection -- the
        thing every other program in your terminal does -- at the cost of in-app
        clicking and wheel scrolling. Keyboard navigation is unaffected, which is
        why off is the default.

        This reaches into the driver, so it is defensive: a Textual that renames
        these internals should degrade to a message, not a traceback.
        """
        driver: Any = getattr(self, "_driver", None)
        enable = not self.mouse_enabled
        try:
            if driver is None:
                raise RuntimeError("no driver")
            driver._mouse = True  # the enable/disable methods are gated on this
            if enable:
                driver._enable_mouse_support()
            else:
                driver._disable_mouse_support()
                driver._mouse = False
        except Exception:
            self.notify(
                "could not toggle mouse capture on this Textual build; "
                "restart with --mouse instead",
                severity="warning",
                timeout=6,
            )
            return
        self.mouse_enabled = enable
        if enable:
            self.notify(
                "mouse capture ON — in-app clicking and wheel scrolling; drag-select is disabled",
                timeout=5,
            )
        else:
            self.notify("mouse capture OFF — drag to select text as normal", timeout=5)

    def action_reload(self) -> None:
        """Re-query and return to the overview.

        A full rebuild rather than a merge: a job's state changes after it
        finishes, so incremental merging would risk showing a stale outcome for
        no measurable gain against a 1.3 s query.

        The snapshot is what makes the rebuild safe. ``_requery`` clears
        ``self.history`` first and ``_loaded`` only backs out gracefully while
        ``_previous`` is set -- and a successful load clears it -- so after any
        normal session ``r`` plus a slurmdbd blip or a query timeout tore the
        dashboard down, with the history already discarded, on a transient
        failure. ``w`` had always snapshotted and so degraded to a toast; the two
        keys now fail the same way, for the reason `_loaded` gives: "Backing out
        beats exiting: they still have the data they had."
        """
        self._previous = (self._window_at, self._since, self.window, self.history)
        self._requery()

    def action_cycle_window(self) -> None:
        """Move to the next time window and re-query.

        The window used to be settable only by ``-S`` at launch, so "what about
        last month?" meant quitting and starting again. Only day and week specs
        are offered because sacct rejects everything coarser -- verified:
        ``-S now-6months`` is "Invalid time specification".
        """
        if not self._can_requery:
            self.notify(
                "the window is fixed in this mode — pass -S to choose one",
                severity="warning",
                timeout=4,
            )
            return
        self._previous = (self._window_at, self._since, self.window, self.history)
        self._window_at = (self._window_at + 1) % len(self._windows)
        self._since = self._windows[self._window_at]
        self.window = humanize_window(self._since)
        # Say so out loud. The only thing `w` changed was one phrase in the title
        # bar -- the row you were looking at usually stays, the counts move by a few
        # -- so pressing it read as nothing happening: "users have a hard time
        # noticing that". A toast is the one element that cannot be mistaken for
        # part of the layout, and it names where the cycle has got to.
        self.notify(
            "time range: %s  (w cycles: %s)"
            % (self.window, " → ".join(humanize_window(w) for w in self._windows)),
            timeout=4,
        )
        self._requery()

    def _requery(self) -> None:
        """Drop back to the overview and load again.

        Pop down to the OverviewScreen, NOT to a stack depth. The overview is
        itself a pushed screen sitting on the App's own default Screen, so
        "pop while deeper than one" popped the overview too and left a blank,
        dead screen that swallowed every subsequent key -- `r` had always done
        this, and `w` inherited it.
        """
        self.history = None
        self._log_map = None
        while len(self.screen_stack) > 1 and not isinstance(self.screen, OverviewScreen):
            self.pop_screen()
        if isinstance(self.screen, OverviewScreen):
            self.screen.refresh_rows()
        self.load_history()


def _clip(value: str, keep: int) -> str:
    """Hard-cut ``value`` to ``keep`` cells, marking the cut.

    The backstop under every other shortening here. Eliding exists only because a
    value wider than its cell soft-wraps to column 0 and takes the label's shape
    with it, so a shortener that can return *more* than its budget has not done
    the one job it was asked to do.
    """
    if keep <= 1:
        return value[:1]
    return value if len(value) <= keep else value[: keep - 1] + "…"


def _elide(path: str, keep: int = 46) -> str:
    """Shorten a long path to ``first/…/filename``, keeping both ends readable.

    ``"/a/b/c".partition("/")`` yields an empty head, so taking the first
    component before stripping the leading slash collapsed every absolute path to
    a bare ``/…/slurm-123.out`` -- throwing away the directory that was the only
    reason to print the path rather than just the file name.

    The middle-out form is tried first because it is the readable one, but a long
    leading component or a long basename can leave it *over* ``keep`` -- and a
    shortening that still soft-wraps to column 0 has bought nothing, since not
    soft-wrapping is the only reason to shorten. So the budget is now enforced:
    where the ``first/…/last`` shape does not fit, the cut falls back to the end,
    the head of a path being the part that locates it.

    One case still overruns deliberately, and is pinned by a test: a path with no
    separator at all. There is nothing to elide *around*, so the choice is between
    a wrapped line and hiding the only name on it, and the name wins.
    """
    if len(path) <= keep:
        return path
    lead = "/" if path.startswith("/") else ""
    head, separator, _ = path.lstrip("/").partition("/")
    if not separator:
        return path  # a single long component; eliding it would hide the name
    shortened = "%s%s/…/%s" % (lead, head, path.rsplit("/", 1)[-1])
    return shortened if len(shortened) <= keep else _clip(path, keep)


#: Undo everything the dashboard turns on, in one write. Idempotent: sending it
#: when the terminal is already restored costs nothing, so no caller has to know
#: whether it was needed.
_TERMINAL_RESET = "\033[?1049l\033[?25h\033[?2026l\033[?2004l\033[0m\r"


@contextlib.contextmanager
def _guard_startup_window() -> Generator[None, None, None]:
    """Cover the gap before `on_mount` installs the app's own signal handlers.

    `SlurmpastApp.on_mount` handles SIGTERM/SIGHUP/SIGINT, which covers a
    *running* dashboard. It does not cover getting there. Measured in a real pty,
    signalling the instant the alternate-screen sequence appears -- at which point
    only **8 bytes** have been emitted, i.e. just that sequence, because Textual
    writes it as its very first output:

        without this guard   4/4  killed by signal, screen left open
        with it              4/4  exit 143, screen restored

    The user's scrollback is replaced by a dead dashboard until they run `reset`.
    Both signals are ordinary: slurmstepd SIGTERMs the step when a job running
    `srun --pty slurmpast` is cancelled, and a killed tmux pane or a closing IDE
    terminal SIGHUPs the foreground group -- and a cancel racing startup is exactly
    when this window is open.

    `os._exit(128 + signum)`, not a re-raise: the codes then match what the
    post-mount handlers report (143/129), so a supervisor sees one story either
    side of the window. A normal exit would run handlers that write to the screen
    we have just torn down. The sibling package's `_TerminalGuard` makes the same
    call for the same reason.
    """
    previous: list[tuple[signal.Signals, signal._HANDLER]] = []

    def _restore_and_die(signum: int, _frame: object) -> None:
        # Written to the file DESCRIPTOR, not through `sys.stdout`. The window this
        # guard covers opens the instant Textual emits the alternate-screen
        # sequence -- and Textual replaces `sys.stdout` and `sys.stderr` with
        # capture objects at about the same moment, whose `write` queues into the
        # app instead of reaching the terminal and whose `isatty()` still answers
        # True. So the stream version picked the capture, wrote the restore into
        # it, and `os._exit` a microsecond later dropped the queue: the process
        # reported 143 while the screen it claimed to have restored was still the
        # dead dashboard. Reproduced deterministically with a stand-in capture,
        # and seen as 1 run in 5 of the real pty test, which is the shape of a
        # race between the redirect and the signal. A descriptor cannot be
        # redirected, so this cannot lose.
        for target in (1, 2):
            if not os.isatty(target):
                continue
            with contextlib.suppress(OSError):
                os.write(target, _TERMINAL_RESET.encode())
            break
        os._exit(128 + signum)

    for signum in (signal.SIGTERM, signal.SIGHUP):
        with contextlib.suppress(ValueError, OSError, AttributeError):
            previous.append((signum, signal.signal(signum, _restore_and_die)))
    try:
        yield
    finally:
        # Put back what was there: a dashboard that could not start falls through
        # to the caller in this same process.
        for signum, handler in previous:
            with contextlib.suppress(ValueError, OSError):
                signal.signal(signum, handler)


def run(
    loader, window: str, ascii_mode=False, no_logs=False, log_dirs=(), mouse=False, since=None
) -> int:
    app = SlurmpastApp(
        loader,
        window,
        ascii_mode=ascii_mode,
        no_logs=no_logs,
        log_dirs=log_dirs,
        mouse=mouse,
        since=since,
    )
    # mouse=False is what makes text selectable: Textual never emits the
    # mouse-tracking escape sequences, so the terminal handles the mouse itself
    # and drag-select behaves normally. Textual 0.89 has no in-app selection
    # API, so this is the only way to get selection at all.
    try:
        with _guard_startup_window():
            app.run(mouse=mouse)
    finally:
        _discard_clip()
    # A load failure outranks everything: the reader got no data, and that is what
    # a script needs to know first.
    if app.load_error:
        return 2
    # Then whatever a signal handler set (143/129/130 -- see `on_mount`). Without
    # this the handlers restored the terminal and still exited 0, so `kill -TERM`
    # and a clean `q` were indistinguishable to a supervisor or to
    # `timeout --signal=INT` -- which is half the reason for handling them.
    return int(app.return_code or 0)
