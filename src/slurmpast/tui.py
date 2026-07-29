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
from .duration import format_bytes, format_duration, format_percent, humanize_window
from .index import (
    FILTERS,
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
from .nodes import MIN_SAMPLES, compress_nodelist, node_table, suggest_exclude

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
_COPY_BINDINGS = [
    Binding("y", "copy_row", "Copy row"),
    Binding("Y", "copy_view", "Copy view", show=False),
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
    import os

    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    directory = os.path.join(base, "slurmpast")
    try:
        os.makedirs(directory, exist_ok=True)
    except OSError:
        return ""
    return os.path.join(directory, "clip.txt")


class ClipboardMixin:
    """``y`` copies the focused row, ``Y`` the whole view.

    Subclasses provide the text; this handles delivery and the notification.
    """

    @property
    def sp(self) -> SlurmpastApp:
        """This screen's app, narrowed to our concrete type.

        Deliberately NOT an ``app: SlurmpastApp`` annotation. That overrides
        ``MessagePump.app``, and mypy reports the clash once per subclass -- the
        error lands on the ``class X(ClipboardMixin, Screen)`` line, not on the
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
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(text if text.endswith("\n") else text + "\n")
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
_MIN_PATH_WIDTH = 28
_MAX_PATH_WIDTH = 62
_DEFAULT_TABLE_WIDTH = 96
_MIN_TABLE_WIDTH = 40
_SCROLLBAR = 2


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
    layout = render.fit_columns(spec, max(_MIN_TABLE_WIDTH, width - _SCROLLBAR), content=content)
    if layout != current or not table.columns:
        table.clear(columns=True)
        for label, column_width in layout:
            table.add_column(label, width=column_width)
    return layout


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
        table.move_cursor(row=0 if key == "home" else table.row_count - 1)
    return True


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
    screen.query_one("#searchbar").remove_class("visible")
    screen.query_one("#search", Input).value = ""
    screen.search_text = ""
    screen.query_one(table_id, DataTable).focus()
    return True


class SearchBar(Input):
    def __init__(self) -> None:
        super().__init__(placeholder="filter by name, job id, state, node or date…", id="search")


class HelpScreen(ModalScreen[None]):
    BINDINGS: ClassVar = [
        Binding("escape", "dismiss", "Back"),
        Binding("q", "dismiss", "Back"),
        Binding("question_mark", "dismiss", "Back", show=False),
    ]
    CSS = (
        BASE_CSS
        + """
    HelpScreen { align: center middle; }
    #help-box { width: 78; height: auto; border: round $primary; background: $panel; padding: 1 2; }
    """
    )

    def compose(self) -> ComposeResult:
        body = Text()
        for key, description in (
            ("enter / →", "open the selected row"),
            ("q / escape / ←", "back, or quit from the overview"),
            ("1-9…", "jump straight to a row by number"),
            ("/", "search — name, job id, state or node"),
            ("f", "cycle filter: all → problems → failed → idle"),
            ("s", "cycle sort"),
            ("n", "node reliability, controlled for workload"),
            ("p", "cross-job patterns"),
            ("a", "flat job list, skipping the grouping"),
            ("y", "copy the selected row to the clipboard"),
            ("Y", "copy the whole view (a job screen copies the full report)"),
            ("w", "cycle the time window: 1 day → 7 → 30 → 12 weeks → 52"),
            ("r", "reload the same window from sacct"),
            ("?", "this help"),
        ):
            body.append("  %-14s " % key, style="bold %s" % theme.ACCENT)
            body.append(description + "\n", style=theme.INK)
        body.append(
            "\n  A row on the overview is one workload: every run whose job name\n"
            '  matches once digits are folded to "#", so cot-exp1 and cot-exp2\n'
            "  share a row. Its counts and hour totals cover all of those runs.\n"
            "  Open a row to see the real job names.\n"
            "\n  FLAGGED counts runs this tool marks for a look: they failed, or\n"
            "  they held the allocation without computing. One number, because\n"
            "  those two overlap — open the row to see which. It says what was\n"
            "  flagged, not that it was your mistake; a failure can be expected.\n"
            "  COMPLETED plus FLAGGED can be less than RUNS: a cancelled run is\n"
            "  neither, since a deliberate kill and an abandoned one are\n"
            "  identical in accounting.\n",
            style=theme.FAINT,
        )
        body.append(
            "\n  Groups are ranked by resources burned, not run count: a 5-run\n"
            "  group that cost 400 GPU-hours outranks 400 two-second probes.\n",
            style=theme.FAINT,
        )
        body.append(
            "\n  Selecting text: just drag. Mouse capture is off by default, so\n"
            "  your terminal handles selection exactly as it does elsewhere.\n"
            "  Press M to hand the mouse to the app instead (enables clicking\n"
            "  and wheel scrolling, disables drag-select), or start --mouse.\n"
            # The real path, not a hardcoded ~/.cache: it follows XDG_CACHE_HOME,
            # so naming the default was wrong wherever that is set.
            "  y / Y also copy via OSC 52 and write %s.\n" % (_clip_path() or "a cache file"),
            style=theme.FAINT,
        )
        with Vertical(id="help-box"):
            yield Static(Text("slurmpast — keys", style="bold %s" % theme.ACCENT))
            yield Static(body)


# Both table specs live in render.py, because --plain draws these same two tables
# and a spec kept next to only one renderer drifted: the dashboard's overview had
# already lost its NEVER RAN column and its "(2 names)" suffix while --plain was
# still printing both.
_OVERVIEW_COLUMNS = render.OVERVIEW_COLUMNS


class OverviewScreen(ClipboardMixin, CentredContent, Screen[Any]):
    """Workload groups, ranked. The landing screen."""

    BINDINGS: ClassVar = [
        *_COPY_BINDINGS,
        Binding("q", "app.quit", "Quit"),
        Binding("escape", "app.quit", "Quit", show=False),
        Binding("enter", "open", "Open"),
        Binding("right", "open", "Open", show=False),
        Binding("slash", "search", "Search"),
        Binding("f", "cycle_filter", "Filter"),
        Binding("s", "cycle_sort", "Sort"),
        Binding("n", "nodes", "Nodes"),
        Binding("p", "patterns", "Patterns"),
        Binding("a", "all_jobs", "All jobs"),
        Binding("r", "app.reload", "Reload"),
        Binding("question_mark", "help", "Help", show=False),
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
                yield SearchBar()
            yield DataTable(
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
        self.query_one("#groups", DataTable).focus()

    def on_resize(self) -> None:
        """Columns are sized to the terminal, so a resize is a relayout.

        The row set is unchanged, so the selection is carried across it -- a
        relayout that silently returned you to row 1 would be its own annoyance.
        """
        if self.is_mounted:
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
        self.summary_text = self._summary(history, shown=len(groups))
        summary.update(self.summary_text)
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
        text.append("%d jobs" % stats["jobs"], style="bold %s" % theme.INK)
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
            text.append("%.0f GPU-hours total" % idle[1], style=theme.GPU_COLOR)
            text.append(
                ", %.0f of them never used" % idle[0],
                style=theme.HEALTH_COLOR["warn"],
            )

        # Last: the facts about the history come first, then what the view is
        # currently doing to them.
        if shown and shown != total_groups:
            text.append("  ·  ", style=theme.FAINT)
            text.append("showing %d" % shown, style=theme.ACCENT)

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
                "%d problems" % group.problems,
                "%d failed" % group.failed,
                "%d never ran" % group.noop,
                # Units named here: a pasted row has no column header above it.
                "%s CPU-hours" % render.hours_text(group.core_hours),
                "%s GPU-hours" % render.hours_text(group.gpu_hours),
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

    def action_help(self) -> None:
        self.sp.push_screen(HelpScreen())

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
        self.search_text = event.value

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        self.query_one("#searchbar").remove_class("visible")
        self.query_one("#groups", DataTable).focus()

    def on_data_table_row_selected(self, _event: DataTable.RowSelected) -> None:
        self.action_open()


_JOB_COLUMNS = render.JOB_COLUMNS

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


class JobListScreen(ClipboardMixin, CentredContent, Screen[Any]):
    """A list of jobs -- inside one workload, or flat across everything."""

    BINDINGS: ClassVar = [
        *_COPY_BINDINGS,
        Binding("q", "app.pop_screen", "Back"),
        Binding("escape", "app.pop_screen", "Back", show=False),
        Binding("left", "app.pop_screen", "Back", show=False),
        Binding("enter", "open", "Open"),
        Binding("right", "open", "Open", show=False),
        Binding("slash", "search", "Search"),
        Binding("f", "cycle_filter", "Filter"),
        Binding("question_mark", "help", "Help", show=False),
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
            yield DataTable(
                id="jobs",
                cursor_type="row",
                cell_padding=1,
                cursor_foreground_priority="renderable",
            )
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_rows()
        self.query_one("#jobs", DataTable).focus()

    def on_resize(self) -> None:
        """Columns are sized to the terminal, so a resize is a relayout.

        The row set is unchanged, so the selection is carried across it -- a
        relayout that silently returned you to row 1 would be its own annoyance.
        """
        if self.is_mounted:
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
        table.clear()
        for index, job in enumerate(jobs, start=1):
            grade = theme.STATE_HEALTH.get(job.base_state, "none")
            if looks_like_noop(job):
                grade = "crit"
            util = job.cpu_utilization
            # Row number only. A health dot on every row duplicated the STATE
            # column beside it, and a filled circle leading each line was read as
            # "all the entries are selected". The overview keeps its dot: group
            # severity has no column of its own there.
            marker = Text("%-2d" % index, style=theme.FAINT)
            # MaxRSS above the ceiling is not a working set (it sums shared pages
            # across the process tree), so it is flagged rather than read as 103%.
            over_limit = bool(
                job.mem_limit_bytes and job.max_rss and job.max_rss > job.mem_limit_bytes
            )
            cells = {
                "#": marker,
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
                "NODE": Text(job.node_list or "", style=theme.FAINT),
            }
            table.add_row(*(cells[label] for label, _ in layout), key=str(index))
        if cursor and cursor < len(jobs):
            table.move_cursor(row=cursor)

        summary = Text()
        summary.append(self._title, style="bold %s" % theme.INK)
        summary.append(
            "  ·  %d job%s" % (len(jobs), "" if len(jobs) == 1 else "s"), style=theme.DIM
        )
        idle = sum(1 for j in jobs if looks_like_noop(j))
        if idle:
            # "of them" ties the count to the job count beside it. A bare "3 never
            # computed" next to a GPU-hours figure elsewhere read as hours.
            summary.append(
                "  ·  %d of them never computed" % idle, style=theme.HEALTH_COLOR["warn"]
            )
        cancelled = sum(1 for j in jobs if j.cancelled)
        if cancelled:
            # The quantity that closes the arithmetic. The overview showed this
            # workload as 15 runs / 10 completed / 2 flagged and was asked whether
            # the math was wrong: the missing 5 were cancelled, and a cancellation
            # is deliberately neither a success nor a problem, so it appeared in no
            # column at all. Dim, because it is bookkeeping rather than a finding.
            summary.append("  ·  %d cancelled" % cancelled, style=theme.DIM)
        excluded = getattr(self, "_excluded", 0)
        if excluded:
            # Terse: the window is already in the title bar, and the long
            # explanation belonged in one place, not on every workload.
            summary.append(
                "  ·  %d unterminated, excluded" % excluded,
                style=theme.FAINT,
            )
        if self.search_text:
            summary.append("  ·  search: ", style=theme.FAINT)
            summary.append(self.search_text, style=theme.ACCENT)
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
            self.query_one("#jobs", DataTable).move_cursor(row=row - 1)

    def on_key(self, event: events.Key) -> None:
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

    def action_help(self) -> None:
        self.sp.push_screen(HelpScreen())

    def watch_filter_mode(self) -> None:
        if self.is_mounted:
            self.refresh_rows()

    def watch_search_text(self) -> None:
        if self.is_mounted:
            self.refresh_rows()

    def on_input_changed(self, event: Input.Changed) -> None:
        self.search_text = event.value

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        self.query_one("#searchbar").remove_class("visible")
        self.query_one("#jobs", DataTable).focus()

    def on_data_table_row_selected(self, _event: DataTable.RowSelected) -> None:
        self.action_open()


class WorkloadScreen(JobListScreen):
    """One workload: its jobs, plus the patterns only visible across them."""

    BINDINGS: ClassVar = [
        *JobListScreen.BINDINGS,
        Binding("p", "patterns", "Patterns"),
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
            banner.append("\n  " + " ".join(render.wrap(worst.evidence, 100)), style=theme.DIM)

        # The point of reading finished jobs: what the next one should ask for.
        from .sizing import recommend

        # Each directive with the evidence behind it, on screen. It used to assert
        # "--time=09:45:00  --mem=72G" and point at `slurmpast --sizing for why` --
        # a bare number with no basis, and for the reason a different command in a
        # different program. The reason belongs where the number is.
        advice = [a for a in recommend(self._group.jobs) if a.actionable]
        for index, item in enumerate(advice):
            banner.append("\n" if banner.plain else "")
            banner.append("next run  " if index == 0 else "          ", style=theme.FAINT)
            banner.append("%-22s" % ("%s=%s" % (item.flag, item.suggestion)), style=theme.ACCENT)
            banner.append("  ".join(render.wrap(item.basis, 84)[:1]), style=theme.DIM)
        return banner if banner.plain else None

    def action_patterns(self) -> None:
        self.sp.push_screen(PatternsScreen(self._group))


class JobScreen(ClipboardMixin, Screen[Any]):
    """The post-mortem for one job."""

    BINDINGS: ClassVar = [
        *_COPY_BINDINGS,
        Binding("q", "app.pop_screen", "Back"),
        Binding("escape", "app.pop_screen", "Back", show=False),
        Binding("left", "app.pop_screen", "Back", show=False),
        Binding("p", "toggle_paths", "Full path", show=False),
        Binding("question_mark", "help", "Help", show=False),
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

    def action_help(self) -> None:
        self.sp.push_screen(HelpScreen())

    def _path_budget(self, prefix: int) -> int:
        """Cells a path may fill on a full-width line before it has to be elided.

        Fixed budgets were the defect. The log line called :func:`_elide` with its
        default 46 while the workdir two rows above used 62, so the one path a
        reader actually wants to copy was cut sixteen cells shorter than the one
        above it -- and a 47-character path came out as ``/home/…/145-train.err``
        on a 150-column terminal with a hundred cells to spare, throwing away the
        two directories that were the only reason to print a path at all.

        Eliding exists to stop a path wrapping to column 0, and whether it wraps is
        a function of the width there is. So that is what it is measured against.
        """
        width = self.size.width or self.app.size.width or _DEFAULT_TABLE_WIDTH
        # One cell for the scrollbar, one so the text never touches the edge.
        return max(_MIN_PATH_WIDTH, width - prefix - _SCROLLBAR)

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
        if history is not None and len(history) > 20:
            from .nodes import expand_nodelist, note_for_node

            nodes = expand_nodelist(job.node_list)
            if nodes:
                note = note_for_node(history.usable_jobs, nodes[0], workload=job.name)

        verdict = diagnose(job, log_text=log_text, node_note=note)

        body = Text()
        body.append("%s  " % job.job_id, style="bold %s" % theme.INK)
        body.append_text(render.state_text(job.base_state, ascii_mode))
        # No identity lines here: the "job" section below carries them, and
        # printing both put the name, account and node on screen twice.
        body.append("\n\n")

        # Lead with slurmwatch's row idiom, so a job you watched running looks
        # like the same object afterwards.
        for line in render.resource_rows(job, ascii_mode=ascii_mode):
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
                # A 118-character workdir wrapped to column 0, leaving the label
                # looking empty with an orphaned line of path beneath it. Elided
                # here only -- `p` shows it in full, and --plain always does,
                # because a path you cannot copy whole is no use in a ticket.
                if not self._show_paths and "/" in value:
                    # A paired cell must fit its column; a row on its own gets the
                    # rest of the line rather than a constant.
                    budget = pad or self._path_budget(4 + render.PAIR_LABEL_WIDTH + 1)
                    if len(value) > budget:
                        value = _elide(value, keep=budget)
                body.append("    %-*s " % (render.PAIR_LABEL_WIDTH, label), style=theme.FAINT)
                if gauge is not None:
                    body.append_text(render.bar(gauge, colour, width=14, ascii_mode=ascii_mode))
                    body.append("  ")
                # Values carry their section's hue. The palette already spreads
                # these across the wheel so no two read alike even under
                # red-green colour blindness; printing every value in one ink
                # threw that away and left the eye nothing to group by.
                style = colour
                if "ABOVE THE LIMIT" in value:
                    style = theme.HEALTH_COLOR["crit"]
                elif "not recorded" in value:
                    style = theme.FAINT
                body.append("%-*s" % (pad, value) if pad else value, style=style)

            # Two pairs per line where both values are short: one row per line
            # used about 40 of 120 columns and ran the screen off the bottom.
            for group in render.pair_rows(rows):
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
                body.append(
                    "       matched by timing, not by name — verify before trusting it\n",
                    style=theme.HEALTH_COLOR["warn"],
                )
        elif not self.sp.no_logs:
            # One line. Slurm keeps StdOut/StdErr only in slurmctld and MinJobAge
            # is 120s here, so `scontrol show job` answers "Invalid job id" for
            # anything a post-mortem looks at and sacct has no such field at all.
            # The path is unknowable, and saying so over three lines was explaining
            # a limitation the reader cannot act on.
            body.append("  log  none found — --log-dir points at one\n", style=theme.FAINT)

        body.append("\n")
        findings = render.sort_findings(verdict.findings)
        if not findings:
            body.append("  nothing to flag.\n", style=theme.HEALTH_COLOR["ok"])
        for finding in findings:
            body.append("  ")
            body.append_text(render.severity_chip(finding.severity))
            body.append("  %s\n" % finding.title, style="bold %s" % theme.INK)
            for line in render.wrap(finding.evidence, 86):
                body.append("        %s\n" % line, style=theme.DIM)
            if finding.action:
                for index, line in enumerate(render.wrap(finding.action, 82)):
                    body.append(
                        "        %s%s\n" % ("→ " if index == 0 else "  ", line),
                        style=theme.ACCENT if index == 0 else theme.DIM,
                    )
            body.append("\n")

        self.query_one("#body", Static).update(body)


class PatternsScreen(ClipboardMixin, Screen[Any]):
    """Cross-run findings: the things no single job can show."""

    BINDINGS: ClassVar = [
        Binding("q", "app.pop_screen", "Back"),
        Binding("escape", "app.pop_screen", "Back", show=False),
        Binding("left", "app.pop_screen", "Back", show=False),
        *_COPY_BINDINGS,
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
        history: History | None = self.sp.history
        self.sub_title = "patterns" + (" · %s" % self._group.label if self._group else "")
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
                "  no cross-run pattern met its evidence threshold.\n",
                style=theme.HEALTH_COLOR["ok"],
            )
            body.append(
                "\n  That is a real answer, not an empty screen: these detectors\n"
                "  stay silent rather than manufacture a finding.\n",
                style=theme.FAINT,
            )
        for finding in render.sort_findings(findings):
            body.append("  ")
            body.append_text(render.severity_chip(finding.severity))
            body.append("  %s\n" % finding.title, style="bold %s" % theme.INK)
            for line in render.wrap(finding.evidence, 86):
                body.append("        %s\n" % line, style=theme.DIM)
            if finding.action:
                for index, line in enumerate(render.wrap(finding.action, 82)):
                    body.append(
                        "        %s%s\n" % ("→ " if index == 0 else "  ", line),
                        style=theme.ACCENT if index == 0 else theme.DIM,
                    )
            body.append("\n")
        self.query_one("#body", Static).update(body)


class NodesScreen(ClipboardMixin, CentredContent, Screen[Any]):
    """Per-node reliability, workload-controlled."""

    BINDINGS: ClassVar = [
        Binding("q", "app.pop_screen", "Back"),
        Binding("escape", "app.pop_screen", "Back", show=False),
        Binding("left", "app.pop_screen", "Back", show=False),
        *_COPY_BINDINGS,
        Binding("m", "cycle_metric", "Metric"),
        Binding("c", "toggle_control", "Control"),
    ]
    CSS = BASE_CSS

    metric: reactive[str] = reactive("hang")
    controlled: reactive[bool] = reactive(True)

    def compose(self) -> ComposeResult:
        yield _header()
        with Vertical(id="content"):
            yield Static(id="summary")
            yield DataTable(id="nodes", cursor_type="row")
            yield Static(id="exclude")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#nodes", DataTable)
        layout = (
            ("NODE", 18),
            ("N", 11),
            ("RATE", 8),
            ("95% CI", 18),
            ("VERDICT", 14),
        )
        for label, width in layout:
            table.add_column(label, width=width)
        self.fit_content(layout)
        self.refresh_rows()

    def refresh_rows(self) -> None:
        history: History | None = self.sp.history
        if history is None or not self.query_one("#nodes", DataTable).columns:
            return
        from .nodes import dominant_workload

        workload = (
            dominant_workload(history.usable_jobs, metric=self.metric) if self.controlled else None
        )
        table_data = node_table(history.usable_jobs, workload=workload, metric=self.metric)

        summary = Text()
        summary.append("node reliability — %s rate\n" % self.metric, style="bold %s" % theme.INK)
        if workload:
            summary.append(
                "  controlled for workload: only %s counted " % workload, style=theme.DIM
            )
            summary.append("(placement is not random)\n", style=theme.FAINT)
        else:
            summary.append(
                "  UNCONTROLLED — mixes workloads, so a node that hosted one bad "
                "campaign looks cursed\n",
                style=theme.HEALTH_COLOR["warn"],
            )
        summary.append(
            "  baseline %s over %d placements%s\n"
            % (
                format_percent(table_data["baseline"]),
                table_data["trials"],
                "; %d nodes below sample threshold omitted" % table_data["skipped_nodes"]
                if table_data["skipped_nodes"]
                else "",
            ),
            style=theme.FAINT,
        )
        self.query_one("#summary", Static).update(summary)

        table = self.query_one("#nodes", DataTable)
        table.clear()
        # Two ways this table has nothing to say, and an empty grid says neither.
        rows = table_data["rows"]
        empty_reason = ""
        if not table_data["hits"]:
            empty_reason = (
                "\n  No %s recorded%s in this window, so there is nothing\n"
                "  to attribute to a node.\n"
                % (self.metric + "s", " for %s" % workload if workload else "")
            )
        elif not rows:
            empty_reason = (
                "\n  No node reached the %d placements a comparison needs — %d seen,\n"
                "  all below it. A wider window (w) is what fixes this.\n"
                % (MIN_SAMPLES, table_data["skipped_nodes"])
            )
        if empty_reason:
            rows = []
            summary.append(empty_reason, style=theme.HEALTH_COLOR["ok"])
            self.query_one("#summary", Static).update(summary)
        for row in rows:
            grade = {"worse": "crit", "better": "ok"}.get(row["verdict"], "none")
            table.add_row(
                Text(row["node"], style=theme.INK),
                Text("%d/%d" % (row["bad"], row["trials"]), style=theme.DIM),
                Text(
                    "%.1f%%" % (100 * row["rate"]), style=theme.HEALTH_COLOR.get(grade, theme.DIM)
                ),
                Text(
                    "%.1f – %.1f%%" % (100 * row["ci_low"], 100 * row["ci_high"]), style=theme.FAINT
                ),
                Text(row["verdict"], style=theme.HEALTH_COLOR.get(grade, theme.FAINT)),
            )

        excl = compress_nodelist(suggest_exclude(table_data))
        note = Text()
        if excl:
            note.append("\n  intervals entirely above baseline:\n", style=theme.DIM)
            note.append("    #SBATCH --exclude=%s\n" % excl, style="bold %s" % theme.ACCENT)
            note.append(
                "    not applied for you — excluding nodes trades availability for "
                "reliability, and that is your call.\n",
                style=theme.FAINT,
            )
        else:
            note.append(
                "\n  no node's interval clears the baseline; nothing to exclude.\n",
                style=theme.FAINT,
            )
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
        Binding("w", "cycle_window", "Window"),
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
        try:
            jobs = self._loader(self._since) if self._can_requery else self._loader()
        except Exception as exc:  # surfaced in the UI, never swallowed
            self.call_from_thread(self._loaded, None, str(exc))
            return
        history = History(jobs, window=self.window)
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
        if not self.no_logs:
            # Off the UI thread: 1.7s over 6,600 jobs, which is invisible here and
            # a visible stall if it happens on the keypress that opens a job.
            self.run_worker(self._resolve_logs, thread=True, name="logs")
        screen = self.screen
        if isinstance(screen, OverviewScreen):
            screen.refresh_rows()

    def _resolve_logs(self) -> None:
        history = self.history
        if history is None:
            return
        try:
            resolved = assign_logs(history.usable_jobs, extra_dirs=self.log_dirs)
        except OSError:
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
        self._window_at, self._since, self.window, self.history = self._previous
        self._previous = None
        self.notify(
            "nothing found there — staying on %s\n%s" % (self.window, error or ""),
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
        """
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


def _elide(path: str, keep: int = 46) -> str:
    """Shorten a long path to ``first/…/filename``, keeping both ends readable.

    ``"/a/b/c".partition("/")`` yields an empty head, so taking the first
    component before stripping the leading slash collapsed every absolute path to
    a bare ``/…/slurm-123.out`` -- throwing away the directory that was the only
    reason to print the path rather than just the file name.
    """
    if len(path) <= keep:
        return path
    lead = "/" if path.startswith("/") else ""
    head, separator, _ = path.lstrip("/").partition("/")
    if not separator:
        return path  # a single long component; eliding it would hide the name
    return "%s%s/…/%s" % (lead, head, path.rsplit("/", 1)[-1])


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
    app.run(mouse=mouse)
    return 2 if app.load_error else 0
