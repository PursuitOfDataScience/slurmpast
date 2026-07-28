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

from typing import Any, ClassVar

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.screen import ModalScreen, Screen
from textual.widgets import DataTable, Footer, Header, Input, Static

from . import render, theme
from .diagnose import diagnose, looks_like_noop
from .duration import format_duration, format_percent
from .index import (
    FILTERS,
    GroupStats,
    History,
    filter_groups,
    filter_jobs,
    next_sort,
    sort_groups,
    sort_label,
)
from .logs import load_for
from .nodes import compress_nodelist, node_table, suggest_exclude

BASE_CSS = """
Screen { background: $surface; }
#banner { height: auto; padding: 0 1; color: $text-muted; }
#summary { height: auto; padding: 0 1 1 1; }
DataTable { height: 1fr; }
DataTable > .datatable--cursor { background: $primary 30%; }
#detail { padding: 0 1; height: 1fr; }
#searchbar { height: auto; padding: 0 1; display: none; }
#searchbar.visible { display: block; }
.pane-title { text-style: bold; padding: 1 1 0 1; }
"""


# Textual 0.89 has copy_to_clipboard (OSC 52) but not the in-app text-selection
# API that arrived in 1.x, so dragging to select does not work. OSC 52 is
# actually the better mechanism over SSH -- it reaches the clipboard on the
# machine you are sitting at -- but it fails silently on some terminals and
# needs `set -g set-clipboard on` inside tmux. So every copy is ALSO written to
# a file, and the notification names it; that way the feature never
# half-works with no way to tell.
_COPY_BINDINGS = [
    Binding("y", "copy_row", "Copy row"),
    Binding("Y", "copy_view", "Copy view", show=False),
]


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

    # Always mixed into a Screen, which supplies `app`. Declared so the type
    # checker knows that, rather than sprinkling ignores at each use.
    app: "SlurmpastApp"

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
            self.app.notify("nothing to copy here", severity="warning", timeout=3)
            return
        self.app.copy_to_clipboard(text)
        path = _clip_path()
        written = False
        if path:
            try:
                with open(path, "w") as handle:
                    handle.write(text if text.endswith("\n") else text + "\n")
                written = True
            except OSError:
                written = False
        lines = text.count("\n") + 1
        message = "copied %s (%d line%s) to the clipboard" % (
            what,
            lines,
            "" if lines == 1 else "s",
        )
        if written:
            message += "\nalso written to %s" % path
        self.app.notify(message, timeout=6)


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


class SearchBar(Input):
    def __init__(self) -> None:
        super().__init__(placeholder="filter by name, job id, state or node…", id="search")


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
            ("r", "reload from sacct"),
            ("?", "this help"),
        ):
            body.append("  %-14s " % key, style="bold %s" % theme.ACCENT)
            body.append(description + "\n", style=theme.INK)
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
            "  y / Y also copy via OSC 52 and write ~/.cache/slurmpast/clip.txt.\n",
            style=theme.FAINT,
        )
        with Vertical(id="help-box"):
            yield Static(Text("slurmpast — keys", style="bold %s" % theme.ACCENT))
            yield Static(body)


class OverviewScreen(ClipboardMixin, Screen[Any]):
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

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static(id="summary")
        with Horizontal(id="searchbar"):
            yield SearchBar()
        yield DataTable(id="groups", cursor_type="row", zebra_stripes=False)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#groups", DataTable)
        for label, width in (
            ("#", 4),
            ("", 2),
            ("WORKLOAD", 26),
            ("PART", 9),
            ("RUNS", 6),
            ("OUTCOMES", 18),
            ("FAILED", 8),
            ("IDLE", 7),
            ("BURNED", 12),
            ("LAST RUN", 12),
            ("VARIANTS", 10),
        ):
            table.add_column(label, width=width)
        self.refresh_rows()
        table.focus()

    # -- data ------------------------------------------------------------

    def refresh_rows(self) -> None:
        history: History | None = self.app.history
        table = self.query_one("#groups", DataTable)
        # The load worker can finish before on_mount has added the columns --
        # with an in-memory loader it reliably does. Populating a zero-column
        # table raises, so bail; on_mount calls this again once set up.
        if not table.columns:
            return
        summary = self.query_one("#summary", Static)
        if history is None:
            summary.update(Text("loading…", style=theme.DIM))
            return

        groups = sort_groups(
            filter_groups(history.groups, self.filter_mode, self.search_text), self.sort_mode
        )
        self._rows = groups
        summary.update(self._summary(history, len(groups)))
        table.clear()
        ascii_mode = self.app.ascii_mode
        for index, group in enumerate(groups, start=1):
            burned = (
                "%.0f gpu-h" % group.gpu_hours
                if group.gpu_hours >= 1
                else "%.0f core-h" % group.core_hours
            )
            table.add_row(
                Text(str(index), style=theme.FAINT),
                render.health_dot(group.severity, ascii_mode),
                Text(group.name[:26], style=theme.INK),
                Text(group.partition[:9], style=theme.DIM),
                Text(str(group.total), style=theme.DIM),
                render.outcome_bar(group.completed, group.failed, group.cancelled, 16, ascii_mode),
                Text(
                    format_percent(group.failure_rate),
                    style=theme.HEALTH_COLOR["crit"] if group.failed else theme.FAINT,
                ),
                Text(
                    str(group.noop) if group.noop else "-",
                    style=theme.HEALTH_COLOR["warn"] if group.noop else theme.FAINT,
                ),
                Text(burned, style=theme.GPU_COLOR if group.gpu_hours else theme.CPU_COLOR),
                Text((group.last_seen or "")[:10], style=theme.FAINT),
                Text(
                    "%d names" % group.distinct_names if group.distinct_names > 1 else "",
                    style=theme.FAINT,
                ),
                key=str(index),
            )
        # Lead with the WINDOW: it is the single most common explanation for
        # "why is this workload missing runs?" and it was nowhere on screen.
        # The filter is named only when it is actually filtering -- a bare
        # "everything" in the title bar is noise.
        parts = [
            self.app.window,
            "%d workload%s" % (len(groups), "" if len(groups) == 1 else "s"),
            "by %s" % sort_label(self.sort_mode),
        ]
        if self.filter_mode != "all":
            parts.insert(2, dict(FILTERS).get(self.filter_mode, self.filter_mode))
        self.sub_title = "  ·  ".join(parts)

    def _summary(self, history: History, shown: int) -> Text:
        stats = history.stats
        text = Text()
        text.append("%d jobs" % stats["jobs"], style="bold %s" % theme.INK)
        text.append("  ·  ", style=theme.FAINT)
        text.append("%s completed" % format_percent(stats["completion_rate"]), style=theme.DIM)
        if stats["gpu_hours_total"]:
            text.append("  ·  ", style=theme.FAINT)
            text.append("%.0f GPU-h" % stats["gpu_hours_total"], style=theme.GPU_COLOR)
            text.append(" (%s goodput)" % format_percent(stats["gpu_goodput"]), style=theme.DIM)
        if stats["gpu_hours_noop"]:
            text.append("  ·  ", style=theme.FAINT)
            text.append(
                "%.0f GPU-h idle" % stats["gpu_hours_noop"],
                style=theme.HEALTH_COLOR["warn"],
            )
        if stats["excluded_open_records"]:
            # Never silently drop records: an unterminated row would otherwise
            # vanish with no trace, and its elapsed is now-minus-start.
            text.append("  ·  ", style=theme.FAINT)
            text.append(
                "%d unterminated record(s) excluded" % stats["excluded_open_records"],
                style=theme.FAINT,
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
                group.name,
                group.partition,
                str(group.total),
                "%d completed" % group.completed,
                "%d failed" % group.failed,
                "%d idle" % group.noop,
                "%.1f gpu-h" % group.gpu_hours
                if group.gpu_hours
                else "%.1f core-h" % group.core_hours,
                group.last_seen or "",
            ]
        )

    def clipboard_view(self) -> str:
        history: History | None = self.app.history
        if history is None:
            return ""
        from .report import Style, render_overview

        return render_overview(
            history, style=Style(enabled=False), limit=len(self._rows), sort=self.sort_mode
        )

    def action_open(self) -> None:
        group = self._selected()
        if group is not None:
            self.app.push_screen(WorkloadScreen(group))

    def action_digit(self, digit: str) -> None:
        row = self._jump.push(digit, len(self._rows))
        if row is not None:
            self.query_one("#groups", DataTable).move_cursor(row=row - 1)

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
        self.app.push_screen(NodesScreen())

    def action_patterns(self) -> None:
        self.app.push_screen(PatternsScreen())

    def action_all_jobs(self) -> None:
        history: History | None = self.app.history
        if history is not None:
            self.app.push_screen(JobListScreen(history.usable_jobs, "all jobs"))

    def action_help(self) -> None:
        self.app.push_screen(HelpScreen())

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

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.query_one("#searchbar").remove_class("visible")
        self.query_one("#groups", DataTable).focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.action_open()


class JobListScreen(ClipboardMixin, Screen[Any]):
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
        self._title = title
        self.filter_mode = initial_filter
        self._jump = _RowJump()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static(id="summary")
        with Horizontal(id="searchbar"):
            yield SearchBar()
        yield DataTable(id="jobs", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#jobs", DataTable)
        # STARTED/ENDED are load-bearing, not decoration: inside a workload with
        # 1,101 same-named runs the job id alone does not tell you which attempt
        # you are looking at.
        for label, width in (
            ("#", 5),
            ("", 2),
            ("JOBID", 12),
            ("NAME", 17),
            ("STATE", 12),
            ("STARTED", 12),
            ("ENDED", 12),
            ("ELAPSED", 9),
            ("CPU", 9),
            ("UTIL", 7),
            ("GPU", 4),
            ("NODE", 13),
        ):
            table.add_column(label, width=width)
        self.refresh_rows()
        table.focus()

    def refresh_rows(self) -> None:
        table = self.query_one("#jobs", DataTable)
        if not table.columns:  # see OverviewScreen.refresh_rows
            return
        jobs = filter_jobs(self._all, self.filter_mode, self.search_text)
        # Newest first: after a failed run you look at the most recent attempt.
        jobs.sort(key=lambda j: (j.start or j.submit or "", j.job_id), reverse=True)
        self._rows = jobs
        ascii_mode = self.app.ascii_mode
        table.clear()
        for index, job in enumerate(jobs, start=1):
            grade = theme.STATE_HEALTH.get(job.base_state, "none")
            if looks_like_noop(job):
                grade = "crit"
            util = job.cpu_utilization
            table.add_row(
                Text(str(index), style=theme.FAINT),
                render.health_dot(grade, ascii_mode),
                Text(job.job_id[:12], style=theme.INK),
                Text((job.name or "")[:17], style=theme.DIM),
                Text(job.base_state[:12], style=theme.HEALTH_COLOR.get(grade, theme.DIM)),
                Text(render.stamp_short(job.start) or "-", style=theme.ACCENT),
                Text(render.stamp_short(job.end) or "-", style=theme.FAINT),
                Text(format_duration(job.elapsed), style=theme.DIM),
                Text(format_duration(job.total_cpu), style=theme.CPU_COLOR),
                Text(
                    format_percent(util),
                    style=theme.HEALTH_COLOR["crit"]
                    if (util is not None and util < 0.02)
                    else theme.DIM,
                ),
                Text(str(job.gpu_count or "-"), style=theme.GPU_COLOR),
                Text((job.node_list or "")[:13], style=theme.FAINT),
                key=str(index),
            )

        summary = Text()
        summary.append(self._title, style="bold %s" % theme.INK)
        summary.append(
            "  ·  %d job%s" % (len(jobs), "" if len(jobs) == 1 else "s"), style=theme.DIM
        )
        idle = sum(1 for j in jobs if looks_like_noop(j))
        if idle:
            summary.append("  ·  %d never computed" % idle, style=theme.HEALTH_COLOR["warn"])
        summary.append("  ·  window %s" % self.app.window, style=theme.FAINT)
        excluded = getattr(self, "_excluded", 0)
        if excluded:
            summary.append(
                "\n%d more record%s in this window excluded as unterminated "
                "(still running, or never closed — elapsed would be now minus start)"
                % (excluded, "" if excluded == 1 else "s"),
                style=theme.FAINT,
            )
        if self.search_text:
            summary.append("  ·  search: ", style=theme.FAINT)
            summary.append(self.search_text, style=theme.ACCENT)
        self.query_one("#summary", Static).update(summary)
        parts = [
            "%d job%s" % (len(jobs), "" if len(jobs) == 1 else "s"),
            self.app.window,
        ]
        if self.filter_mode != "all":
            parts.insert(1, dict(FILTERS).get(self.filter_mode, self.filter_mode))
        self.sub_title = "  ·  ".join(parts)

    def _selected(self):
        table = self.query_one("#jobs", DataTable)
        if not self._rows or not (0 <= table.cursor_row < len(self._rows)):
            return None
        return self._rows[table.cursor_row]

    def clipboard_row(self) -> str:
        job = self._selected()
        if job is None:
            return ""
        return "\t".join(
            [
                job.job_id,
                job.name or "",
                job.base_state,
                job.start or "",
                job.end or "",
                format_duration(job.elapsed),
                format_duration(job.total_cpu),
                format_percent(job.cpu_utilization),
                str(job.gpu_count or 0),
                job.node_list or "",
            ]
        )

    def clipboard_view(self) -> str:
        header = "\t".join(
            ["JOBID", "NAME", "STATE", "STARTED", "ENDED", "ELAPSED", "CPU", "UTIL", "GPU", "NODE"]
        )
        rows = [
            "\t".join(
                [
                    j.job_id,
                    j.name or "",
                    j.base_state,
                    j.start or "",
                    j.end or "",
                    format_duration(j.elapsed),
                    format_duration(j.total_cpu),
                    format_percent(j.cpu_utilization),
                    str(j.gpu_count or 0),
                    j.node_list or "",
                ]
            )
            for j in self._rows
        ]
        return "\n".join([header] + rows)

    def action_open(self) -> None:
        job = self._selected()
        if job is not None:
            self.app.push_screen(JobScreen(job))

    def action_digit(self, digit: str) -> None:
        row = self._jump.push(digit, len(self._rows))
        if row is not None:
            self.query_one("#jobs", DataTable).move_cursor(row=row - 1)

    def action_cycle_filter(self) -> None:
        names = [name for name, _ in FILTERS]
        self.filter_mode = names[(names.index(self.filter_mode) + 1) % len(names)]

    def action_search(self) -> None:
        self.query_one("#searchbar").add_class("visible")
        self.query_one("#search", Input).focus()

    def action_help(self) -> None:
        self.app.push_screen(HelpScreen())

    def watch_filter_mode(self) -> None:
        if self.is_mounted:
            self.refresh_rows()

    def watch_search_text(self) -> None:
        if self.is_mounted:
            self.refresh_rows()

    def on_input_changed(self, event: Input.Changed) -> None:
        self.search_text = event.value

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.query_one("#searchbar").remove_class("visible")
        self.query_one("#jobs", DataTable).focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.action_open()


class WorkloadScreen(JobListScreen):
    """One workload: its jobs, plus the patterns only visible across them."""

    BINDINGS: ClassVar = [
        *JobListScreen.BINDINGS,
        Binding("p", "patterns", "Patterns"),
    ]

    def __init__(self, group: GroupStats) -> None:
        super().__init__(group.jobs, "%s · %s" % (group.name, group.partition))
        self._group = group
        self._excluded = group.excluded

    def on_mount(self) -> None:
        super().on_mount()
        history: History | None = self.app.history
        if history is None:
            return
        findings = history.group_patterns(self._group)
        if findings:
            # Surface the single worst pattern inline; `p` shows them all. The
            # point of the workload screen is that these are invisible per-job.
            worst = render.sort_findings(findings)[0]
            banner = Text()
            banner.append_text(render.severity_chip(worst.severity, self.app.ascii_mode))
            banner.append("  ")
            banner.append(worst.title, style="bold %s" % theme.INK)
            banner.append("\n  " + " ".join(render.wrap(worst.evidence, 100)), style=theme.DIM)
            existing = self.query_one("#summary", Static)
            merged = Text()
            merged.append_text(
                existing.renderable if isinstance(existing.renderable, Text) else Text()
            )
            merged.append("\n")
            merged.append_text(banner)
            existing.update(merged)

    def action_patterns(self) -> None:
        self.app.push_screen(PatternsScreen(self._group))


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
        yield Header(show_clock=False)
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
        self.app.push_screen(HelpScreen())

    def render_body(self) -> None:
        job = self._job
        ascii_mode = self.app.ascii_mode
        # Logs are read here and only here -- eagerly scanning logs for 6,574
        # jobs at load time would dominate startup for data most of them never
        # need.
        log_path, log_text = (None, None)
        if not self.app.no_logs:
            log_path, log_text = load_for(job, extra_dirs=self.app.log_dirs)
        self._log_path, self._log_text = log_path, log_text

        history: History | None = self.app.history
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

        # One shared section model with report.py, so the dashboard and the
        # plain output can never disagree about what a job did.
        section_color = {
            "job": theme.INK,
            "timing": theme.ACCENT,
            "cpu": theme.CPU_COLOR,
            "memory": theme.MEM_COLOR,
            "filesystem": theme.DISK_COLOR,
            "gpu": theme.GPU_COLOR,
            "outcome": theme.INK,
        }
        for title, rows in render.job_sections(job):
            colour = section_color.get(title, theme.INK)
            body.append("  %s\n" % title, style="bold %s" % colour)
            for label, value, gauge in rows:
                body.append("    %-16s " % label, style=theme.FAINT)
                if gauge is not None:
                    body.append_text(render.bar(gauge, colour, width=14, ascii_mode=ascii_mode))
                    body.append("  ")
                style = theme.INK
                if "ABOVE THE LIMIT" in value:
                    style = theme.HEALTH_COLOR["crit"]
                elif "not recorded" in value:
                    style = theme.FAINT
                body.append(value + "\n", style=style)
            body.append("\n")

        body.append("\n")
        if log_path:
            shown = log_path if self._show_paths else _elide(log_path)
            body.append("  log  %s\n" % shown, style=theme.FAINT)
        elif not self.app.no_logs:
            body.append("  log  not found — pass --log-dir to help\n", style=theme.FAINT)

        body.append("\n")
        findings = render.sort_findings(verdict.findings)
        if not findings:
            body.append("  nothing to flag.\n", style=theme.HEALTH_COLOR["ok"])
        for finding in findings:
            body.append("  ")
            body.append_text(render.severity_chip(finding.severity, ascii_mode))
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

    app: "SlurmpastApp"

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
        history: History | None = self.app.history
        if history is None:
            return ""
        from .report import Style, render_patterns

        return render_patterns(history, style=Style(enabled=False))

    clipboard_view = clipboard_row

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with VerticalScroll(id="detail"):
            yield Static(id="body")
        yield Footer()

    def on_mount(self) -> None:
        history: History | None = self.app.history
        self.sub_title = "patterns" + (" · %s" % self._group.name if self._group else "")
        body = Text()
        if history is None:
            body.append("loading…", style=theme.DIM)
            self.query_one("#body", Static).update(body)
            return

        findings = (
            history.group_patterns(self._group) if self._group is not None else history.patterns
        )
        ascii_mode = self.app.ascii_mode
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
            body.append_text(render.severity_chip(finding.severity, ascii_mode))
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


class NodesScreen(ClipboardMixin, Screen[Any]):
    """Per-node reliability, workload-controlled."""

    app: "SlurmpastApp"

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
        yield Header(show_clock=False)
        yield Static(id="summary")
        yield DataTable(id="nodes", cursor_type="row")
        yield Static(id="exclude")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#nodes", DataTable)
        for label, width in (
            ("NODE", 18),
            ("N", 11),
            ("RATE", 8),
            ("95% CI", 18),
            ("VERDICT", 14),
        ):
            table.add_column(label, width=width)
        self.refresh_rows()

    def refresh_rows(self) -> None:
        history: History | None = self.app.history
        if history is None or not self.query_one("#nodes", DataTable).columns:
            return
        from .nodes import dominant_workload

        workload = dominant_workload(history.usable_jobs) if self.controlled else None
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
        for row in table_data["rows"]:
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
        history: History | None = self.app.history
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
    ]

    def __init__(
        self, loader, window: str, ascii_mode=False, no_logs=False, log_dirs=(), mouse=False
    ):
        super().__init__()
        self._loader = loader
        self._window = window
        self.window = window
        self.history: History | None = None
        self.ascii_mode = ascii_mode
        self.no_logs = no_logs
        self.log_dirs = list(log_dirs)
        self.mouse_enabled = bool(mouse)
        self.load_error: str | None = None

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
            jobs = self._loader()
        except Exception as exc:  # surfaced in the UI, never swallowed
            self.call_from_thread(self._loaded, None, str(exc))
            return
        history = History(jobs, window=self._window)
        self.call_from_thread(self._loaded, history, None)

    def _loaded(self, history: History | None, error: str | None) -> None:
        if error is not None or history is None:
            self.load_error = error
            self.exit(message="slurmpast: %s" % (error or "no data"))
            return
        self.history = history
        screen = self.screen
        if isinstance(screen, OverviewScreen):
            screen.refresh_rows()

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
        self.history = None
        while len(self.screen_stack) > 1:
            self.pop_screen()
        if isinstance(self.screen, OverviewScreen):
            self.screen.refresh_rows()
        self.load_history()


def _elide(path: str, keep: int = 46) -> str:
    if len(path) <= keep:
        return path
    head, _, tail = path.partition("/")
    return "%s/…/%s" % (head, path.rsplit("/", 1)[-1])


def run(loader, window: str, ascii_mode=False, no_logs=False, log_dirs=(), mouse=False) -> int:
    app = SlurmpastApp(
        loader, window, ascii_mode=ascii_mode, no_logs=no_logs, log_dirs=log_dirs, mouse=mouse
    )
    # mouse=False is what makes text selectable: Textual never emits the
    # mouse-tracking escape sequences, so the terminal handles the mouse itself
    # and drag-select behaves normally. Textual 0.89 has no in-app selection
    # API, so this is the only way to get selection at all.
    app.run(mouse=mouse)
    return 2 if app.load_error else 0
